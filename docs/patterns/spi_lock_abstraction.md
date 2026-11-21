# SPI Lock Abstraction Patterns

## Overview

The SPI lock abstraction (`src/pi_lora/drivers/spi/locks.py`) provides mutual exclusion for SPI bus access across multiple radio modules. This document captures the hardened patterns that evolved through Plans 4-38, culminating in the `LazyAsyncLock` utility.

---

## Evolution History

| Plan | Change |
|------|--------|
| Plan-4 | Initial SPI lock abstraction with `_AsyncSpiLock` / `_SyncSpiLock` |
| Plan-5 | Fix `async_release` → `release` protocol mismatch |
| Plan-11 | Fix `async_release` protocol |
| Plan-28 | **Extract `LazyAsyncLock` utility** — systemic fix |
| Plan-38 | Use `aiologic.Lock` for holder in `LazyAsyncLock` |

---

## Current Architecture (Post Plan-38)

### `SpiLock` Protocol

```python
# src/pi_lora/drivers/spi/locks.py

from typing import Protocol, Self

class SpiLock(Protocol):
    """Protocol for SPI bus locks — async-only acquisition."""

    async def async_acquire(self) -> Self:
        """Acquire lock asynchronously. Must be called before use."""
        ...

    async def async_release(self) -> None:
        """Release lock asynchronously."""
        ...

    def __aenter__(self) -> Awaitable[Self]:
        """Async context manager entry."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        ...

    def locked(self) -> bool:
        """Check if lock is held."""
        ...

    def green_release(self) -> None:
        """Sync release (for aiologic compatibility)."""
        ...
```

**Key Design**: 
- **No synchronous `__enter__`/`__exit__`** — lock MUST be acquired via `await get_bus_lock()` first
- `aiologic.Lock` satisfies this protocol directly (no wrapper needed)

---

### `get_bus_lock()` — Registry Pattern

```python
# src/pi_lora/drivers/spi/locks.py

from pi_lora.framework.lazy_async_lock import LazyAsyncLock
import aiologic
import sys

_registry = LazyAsyncLock()
_bus_locks: dict[int, aiologic.Lock] = {}
_aiologic_module: 'aiologic | None' = None
_registry_verified = False


def _verify_single_registry() -> None:
    """
    Verify single registry across ALL import paths by scanning sys.modules.
    
    Catches: editable installs, symlinks, namespace packages, any import path variation.
    """
    registries = []
    for module in sys.modules.values():
        if hasattr(module, "_bus_locks"):
            registries.append((module.__name__, id(module._bus_locks)))
    
    if len(registries) > 1:
        registry_ids = {rid for _, rid in registries}
        if len(registry_ids) > 1:
            raise RuntimeError(
                f"Multiple _bus_locks registries detected: {registries}. "
                "This breaks mutual exclusion. Fix: ensure single import path."
            )


async def get_bus_lock(bus_number: int) -> aiologic.Lock:
    """
    Get or create a lock for the given SPI bus number.
    
    Returns raw aiologic.Lock — caller uses `async with lock:`.
    """
    global _aiologic_module, _registry_verified

    if not _registry_verified:
        _verify_single_registry()
        _registry_verified = True

    if _aiologic_module is None:
        import aiologic
        _aiologic_module = aiologic

    # Acquire registry lock (creates on first call via LazyAsyncLock)
    registry_lock = await _registry.acquire()
    async with registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _aiologic_module.Lock()
        return _bus_locks[bus_number]
```

---

## Usage in `RealSpiBus`

```python
# src/pi_lora/drivers/spi/bus.py

class RealSpiBus(SpiBus):
    def __init__(self, bus: int, device: int, ...) -> None:
        self._bus_number = bus
        self._device_number = device
        self._lock: aiologic.Lock | None = None
        self._spidev = None
        ...

    async def open(self) -> None:
        if self._lock is None:
            self._lock = await get_bus_lock(self._bus_number)
        # ... open spidev ...

    async def xfer2(self, data: list[int] | bytearray) -> list[int]:
        if self._lock is None:
            raise RuntimeError("SPI bus not opened — call open() first")
        
        # Run blocking SPI transfer in thread pool
        async with self._lock:
            return await asyncio.to_thread(self._spidev.xfer2, list(data))

    async def close(self) -> None:
        if self._spidev is not None:
            self._spidev.close()
            self._spidev = None
```

---

## Key Patterns

### Pattern 1: Lazy Lock Acquisition

```python
# Lock acquired on FIRST USE, not at construction
async def open(self) -> None:
    if self._lock is None:
        self._lock = await get_bus_lock(self._bus_number)
    ...
```

**Why**: 
- Avoids importing `aiologic` at module load time
- Works before event loop exists
- `LazyAsyncLock` handles thread-safe initialization

---

### Pattern 2: Registry Guarded by Single Lock

```python
registry_lock = await _registry.acquire()
async with registry_lock:
    if bus_number not in _bus_locks:
        _bus_locks[bus_number] = _aiologic_module.Lock()
    return _bus_locks[bus_number]
```

**Why**: 
- Single `LazyAsyncLock` protects the entire registry
- No check-then-act race on `_bus_locks` dict
- `_verify_single_registry()` catches multiple registry instances

---

### Pattern 3: No Sync Fallback by Design

```python
# pyproject.toml
dependencies = [
    "aiologic>=0.1.0,<0.2",  # REQUIRED — no threading fallback
]
```

**Why**: 
- `threading.Lock` cannot be used in `async with` without complex wrapping
- `_SyncSpiLock.acquire()` returning awaitable was buggy (Plan-4, Plan-5)
- `aiologic.Lock` provides sync + async context managers natively

---

### Pattern 4: `aiologic.Lock` for Holder (Not `asyncio.Lock`)

```python
# In LazyAsyncLock._get_or_create_holder()
def _get_or_create_holder(self) -> 'aiologic.Lock':
    with self._holder_init_lock:
        if self._holder is None:
            self._holder = self._ensure_aiologic_imported().Lock()  # aiologic.Lock!
        return self._holder
```

**Why**: 
- `asyncio.Lock()` is bound to the creating thread's event loop
- `aiologic.Lock()` works across threads (verified in `test_registry_thread_safety`)
- Required for `LazyAsyncLock` to work in multi-threaded contexts

---

## Anti-Patterns Eliminated

| Anti-Pattern | Plan Eliminated | Replacement |
|--------------|-----------------|-------------|
| `_SENTINEL = object()` | Plan-28 | Removed — `aiologic.Lock()` is sync constructor |
| `asyncio.Lock()` created fresh each call | Plan-28 | `LazyAsyncLock` persists holder |
| Dual init/else branches | Plan-28 | Single unified code path |
| `_GuardedLock` wrapper class | Plan-28 | Raw `aiologic.Lock` satisfies protocol |
| `_SyncSpiLock` with threading fallback | Plan-4/5 | `aiologic` required dependency |
| Check-then-act on `_bus_locks` | Plan-28 | Atomic under `LazyAsyncLock` |

---

## Validation Rules

### Semgrep Rules

```yaml
# .semgrep/rules/custom/lazy-async-lock-guard.yaml

- id: sentinel-pattern-deprecated
  pattern-either:
    - pattern: _SENTINEL = object()
    - pattern: $LOCK = _SENTINEL
  message: "Sentinel pattern deprecated — use LazyAsyncLock instead"
  severity: ERROR

- id: holder-not-persisted
  pattern: |
    with $GUARD:
        $HOLDER: asyncio.Lock = asyncio.Lock()
  message: "New holder created each call — LazyAsyncLock persists holder"
  severity: ERROR

- id: manual-double-checked-locking
  pattern-either:
    - pattern: |
        if $LOCK is None:
          async with $HOLDER:
            if $LOCK is None:
              $LOCK = $Y.Lock()
    - pattern: |
        with $INIT_LOCK:
          $HOLDER = asyncio.Lock()
        async with $HOLDER:
          if $LOCK is None:
            $LOCK = $Y.Lock()
  message: "Manual double-checked locking — use LazyAsyncLock instead"
  severity: ERROR

- id: spi-lock-sync-context-manager
  pattern: |
    with $LOCK:
      ...
  message: "SPI lock used as sync context manager — must use `async with await get_bus_lock()` first"
  severity: ERROR
```

### Must-Pass Tests

```bash
# Thread safety test (Plan-38 Fix 1 validation)
uv run pytest tests/drivers/spi/test_locks.py::TestLockRegistry::test_registry_thread_safety -v

# Full lock test suite
uv run pytest tests/drivers/spi/test_locks.py -v
uv run pytest tests/drivers/spi/test_locks_concurrent.py -v
```

---

## Concurrency Test: `test_registry_thread_safety`

```python
# tests/drivers/spi/test_locks.py

@pytest.mark.asyncio
async def test_registry_thread_safety():
    """Verify LazyAsyncLock works across threads (aiologic.Lock holder)."""
    import threading
    
    results = []
    
    def worker():
        async def get_lock():
            return await get_bus_lock(0)
        results.append(asyncio.run(get_lock()))
    
    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # All threads should get the SAME lock instance
    assert len(set(id(r) for r in results)) == 1
```

---

## Configuration

```toml
# pyproject.toml

[project]
dependencies = [
    "aiologic>=0.1.0,<0.2",  # Required for SPI locking — no sync fallback
]

[tool.mypy]
# aiologic types may be incomplete
[[tool.mypy.overrides]]
module = "pi_lora.drivers.spi.*"
ignore_missing_imports = true
```

---

## Related Files

- `src/pi_lora/drivers/spi/locks.py` — Main implementation
- `src/pi_lora/framework/lazy_async_lock.py` — Shared utility
- `src/pi_lora/drivers/spi/bus.py` — Usage in `RealSpiBus`
- `tests/drivers/spi/test_locks.py` — Unit tests
- `tests/drivers/spi/test_locks_concurrent.py` — Concurrency tests
- `docs/patterns/concurrency_lazy_async_lock.md` — LazyAsyncLock details

---

## Anti-Regression Checklist

When modifying SPI locks:
- [ ] No `_SENTINEL` anywhere
- [ ] No `asyncio.Lock()` created inside holder lock
- [ ] No dual init/else branches for lock initialization
- [ ] `_verify_single_registry()` scans `sys.modules`
- [ ] `LazyAsyncLock` used for ALL lazy async locks
- [ ] `aiologic` dependency pinned with upper bound
- [ ] Thread safety test passes
- [ ] Semgrep rules pass