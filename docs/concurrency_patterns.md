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

## Concurrency Anti-Patterns (Plan-37 Regression Prevention)

### Double-Checked Locking is UNSAFE for Boolean Flags that Transition False→True→False

The double-checked locking pattern (outer `if flag: return` → inner `async with lock: if flag: return`) is **only safe for one-time initialization** (False→True). It is **UNSAFE** for a boolean flag that can transition back to `False` (e.g., `_started` flag in `Application` that goes False→True on `start()`, True→False on `stop()`, then False→True again on restart).

**Why it fails**: On free-threaded builds or non-x86, a stale read of `True` (after `stop()` set it to `False` but the write hasn't propagated) causes the fast path to return early without acquiring the lock — the application fails to restart.

**Anti-pattern (BUG)**:
```python
# WRONG for False→True→False flags
already_started: bool = self._started  # Fast-path read OUTSIDE lock
if already_started:
    return
async with self._lifecycle_lock:
    if self._started:
        return
```

**Correct pattern**: Always acquire the lock for flags that can transition back to `False`:
```python
# CORRECT — always acquire lock
async with self._lifecycle_lock:
    if self._started:
        return
```

**Audit**: `grep -rn "if self\._started:" src/ --include="*.py"` should show **no fast-path reads outside a lock** for `_started` or similar state flags.

### LazyAsyncLock Holder Must Use `aiologic.Lock`, NOT `asyncio.Lock`

`LazyAsyncLock._get_or_create_holder()` in `src/pi_lora/framework/lazy_async_lock.py` creates a holder lock. This holder is shared across threads that call `get_bus_lock()` (each with their own event loop via `asyncio.run()` or `asyncio.to_thread()`). Using `asyncio.Lock()` ties the holder to **one specific event loop**, causing cross-thread contention failures ("Future attached to a different loop").

**Anti-pattern (BUG)**:
```python
def _get_or_create_holder(self) -> asyncio.Lock:
    with self._holder_init_lock:
        if self._holder is None:
            self._holder = asyncio.Lock()  # Bound to THIS thread's event loop!
        return self._holder
```

**Correct pattern**: Use `aiologic.Lock()` (synchronous constructor, works across threads):
```python
def _get_or_create_holder(self) -> 'aiologic.Lock':
    with self._holder_init_lock:
        if self._holder is None:
            self._holder = self._ensure_aiologic_imported().Lock()
        return self._holder
```

**Test verification**: `test_registry_thread_safety` in `tests/drivers/spi/test_locks.py` must pass with true concurrent `asyncio.run(get_bus_lock(0))` calls from multiple threads.

### Context Manager + `__del__` Interaction — Prevent Double-Close

When adding a context manager (`__enter__`/`__exit__`) to a class that **already has `__del__` cleanup**, the `__exit__` must clear the resource reference to prevent double-close when the object is later garbage collected.

**Anti-pattern (BUG)**:
```python
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    with contextlib.suppress(Exception):  # WRONG: wraps entire loop
        for module in self.modules:
            module.spi_device.close()
    # Missing: module.spi_device = None → double-close in __del__
```

**Correct pattern**:
```python
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    for module in self.modules:
        try:
            if hasattr(module.spi_device, 'close'):
                module.spi_device.close()
            module.spi_device = None  # Prevent double-close in __del__
        except Exception as e:
            logger.warning("Failed to close SPI device for CE %s: %s", module.ce_pin, e)
```

**Key requirements**:
1. Per-module `try/except` — one failure doesn't stop cleanup of others
2. Clear resource reference (`module.spi_device = None`) after close
3. Log failures but don't raise — cleanup must never propagate exceptions

### InterruptBridge.stop() Race Window — Acquire Lock FIRST

When a component uses a lock shared with a sync-thread callback (e.g., `_trigger_lock` shared with `trigger_interrupt()` from GPIO threads), the `stop()` method must acquire the lock **BEFORE** setting the "running" flag to `False`. Otherwise, new callbacks can fire during the window between `_running=False` and lock acquisition.

**Anti-pattern (RACE)**:
```python
async def stop(self) -> None:
    self._running = False
    await asyncio.gather(self._task.cancel(), ...)
    with self._trigger_lock:  # Too late! trigger_interrupt() can race here
        self._loop = None
```

**Correct pattern**:
```python
async def stop(self) -> None:
    with self._trigger_lock:  # Acquire FIRST — blocks new trigger_interrupt() calls
        self._running = False
        self._loop = None
    await asyncio.gather(self._task.cancel(), ...)
```