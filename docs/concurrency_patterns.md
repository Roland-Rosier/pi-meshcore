# Concurrency Patterns

**Enforced pattern:** Double-checked locking with a module-level guard lock for lazy lock initialization.

## The Contract

When a lock is laz-initialized on first use (to avoid creating an `asyncio.Lock`/`aiologic.Lock` at module import time, which may require a running event loop), the initialization must be guarded by a **separate module-level lock**. Without a guard, two concurrent coroutines can each pass the `if $LOCK is None:` check and create separate lock instances, breaking mutual exclusion.

## Correct pattern

```python
from __future__ import annotations

import asyncio
import aiologic

_registry_lock: object = None
_registry_init_lock: asyncio.Lock = asyncio.Lock()  # module-level guard


async def get_bus_lock() -> object:
    if _registry_lock is None:
        async with _registry_init_lock:  # Race-free guard
            if _registry_lock is None:  # Re-check inside lock
                _registry_lock = aiologic.Lock()
    async with _registry_lock:
        ...
```

Two checks: the outer `if` avoids lock contention on the hot path; the inner re-check inside the guard prevents a second instance from being created.

## Reference implementations

| File | Guard lock | Defect |
|------|-----------|--------|
| `src/pi_lora/drivers/rfm9x_sx127x_config_loader.py` | `_init_lock` | NR-1 / R-3 |
| `src/pi_lora/drivers/spi/locks.py` | `_registry_init_lock` | R-3 |

## Audit enforcement

- `uv run bash -c 'grep -rn "if .*_lock is None:" src/ --include="*.py" -A 2'` → **exactly 2 occurrences**, both guarded (the two files above).

Any lazy lock initialization without a double-checked-lock guard is a race condition and is flagged by the semgrep rule `lazy-lock-without-guard` (`.semgrep/rules/custom/lazy-lock-guard.yaml`).

## The ONE Exception: `threading.Lock` in sync thread context

The aiologic-only rule has exactly one sanctioned exception: a stdlib
`threading.Lock` is permitted when synchronization happens in a **synchronous
thread context with no asyncio event loop** — never in a coroutine.

| File | Lock | Context | Rationale |
|------|------|---------|-----------|
| `src/pi_lora/framework/scheduler.py` | `threading.Lock` (`_trigger_lock`) | Sync thread (GPIO interrupt callback) | `InterruptBridge.trigger_interrupt()` runs in the GPIO driver thread, not the event loop thread. No asyncio event loop is guaranteed at call time, so `aiologic.Lock`/`asyncio.Lock` (which require a running loop) are invalid. The compound `get_nowait()` + `put_nowait()` drop-oldest operation on `queue.Queue` must be atomic across threads; `threading.Lock` is the natural companion of the stdlib thread-safe `queue.Queue`. |

This is the ONLY `threading.Lock` in the codebase. It is documented inline in
`scheduler.py` (both the `InterruptBridge` class docstring and the
`trigger_interrupt` lock-wrapping comment) so future readers understand why it is
`threading.Lock` and NOT `aiologic.Lock`. Any other use of `threading.Lock`
outside this sanctioned case, or any `aiologic.Lock` used in a sync thread
without an event loop, is a violation flagged by the `lazy-lock-guard` audit.

## InterruptBridge Loop Capture (Plan-17)

`trigger_interrupt()` runs in a **sync thread context** (the GPIO driver thread
from lgpio / RPi.GPIO / gpiod), which is *not* the asyncio event loop thread.
Calling `asyncio.get_running_loop()` there returns the *wrong* loop (or raises
`RuntimeError`), so a drain Event would be signaled on the wrong loop. The fix
captures the correct loop once in `start()` (which is guaranteed to run in the
event loop thread) and uses the thread-safe `call_soon_threadsafe()`:

```python
# __init__
self._loop: asyncio.AbstractEventLoop | None = None

# start() — guaranteed to run in the event loop thread
async def start(self) -> None:
    self._running = True
    self._loop = asyncio.get_running_loop()  # capture the correct loop
    ...

# trigger_interrupt() — runs in the GPIO driver thread
if self._loop is not None:
    with contextlib.suppress(RuntimeError, AttributeError):
        self._loop.call_soon_threadsafe(self._drain_event.set)
```

`start()` captures `self._loop` and guards the use with `if self._loop is not
None` + `contextlib.suppress(RuntimeError, AttributeError)` so an early call
before `start()` is a safe no-op. This is the H-16-2 case.

## CommandBus MRO Resolution (Plan-17)

Handler lookup resolves by iterating the command's **own MRO in standard Python
order** and returning the first registered match. The previous depth-based
`command_depth - len(registered_type.__mro__)` lookup assumed a registered type's
MRO is a suffix of the command's MRO, which breaks for diamond inheritance.
Iterating `type(command).__mro__` matches `isinstance`/`except` semantics exactly;
the first match in MRO order wins and `priority` is irrelevant (the same-type
duplicate is rejected at registration):

```python
command_mro: tuple[type[Any], ...] = type(command).__mro__
best_key: type[Any] | None = None
best_tuple: tuple[Callable[..., Any], int] | None = None
for registered_type in command_mro:
    handler_tuple = self._handlers.get(registered_type)
    if handler_tuple is not None:
        best_key = registered_type
        best_tuple = handler_tuple
        break  # First match in MRO order wins
if best_key is None:
    raise ValueError(f"No handler for {type(command).__name__}")
```

This is the H-16-3 case.
