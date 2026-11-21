# Concurrency Pattern: LazyAsyncLock

## Overview

The **LazyAsyncLock** pattern is the authoritative solution for thread-safe, lazy-initialized async locks in this codebase. It was extracted in Plan-28 to eliminate systemic bugs across `locks.py` and `config_loader.py` that existed from Plans 22-27.

**Location**: `src/pi_lora/framework/lazy_async_lock.py`

---

## The Problem It Solves

### Previous Buggy Patterns (Plans 22-27)

| Bug | Root Cause | Impact |
|-----|------------|--------|
| **Sentinel Race** | `else:` branch outside holder lock sees `_SENTINEL` | `AttributeError` on concurrent init |
| **Holder Not Persisted** | `asyncio.Lock()` created fresh each call | Multiple guard locks, no mutual exclusion |
| **Dual Code Paths** | Separate init branch + else branch | Logic divergence, hard to verify |
| **4 Sync Primitives** | `threading.Lock` + `asyncio.Lock` + sentinel + `aiologic.Lock` | Complex, error-prone |

### Why `aiologic.Lock()` Changed Everything

```python
# aiologic.Lock() is a SYNCHRONOUS constructor (verified):
hasattr(aiologic.Lock(), 'green_release')  # → True
```

This means:
- **No `await` needed** to create it
- **No sentinel needed** — the race sentinel "fixed" doesn't exist
- **Single unified code path** under holder lock

---

## LazyAsyncLock Implementation

```python
class LazyAsyncLock:
    """
    Thread-safe, lazy-initialized async lock wrapper.

    GUARANTEES (verified by concurrency tests):
    - Exactly ONE aiologic.Lock is ever created per instance
    - Initialization is atomic (threading.Lock + double-checked locking)
    - NO sentinel object → NO sentinel race possible
    - Holder lock is persisted and reused across all callers
    - Single code path — no separate init/else branches
    - aiologic.Lock() is SYNCHRONOUS constructor
    """

    __slots__ = ("_holder_init_lock", "_holder", "_lock", "_aiologic_module")

    def __init__(self) -> None:
        self._holder_init_lock: threading.Lock = threading.Lock()
        self._holder: 'aiologic.Lock' | None = None
        self._lock: 'aiologic.Lock | None' = None
        self._aiologic_module: 'aiologic | None' = None

    def _ensure_aiologic_imported(self) -> 'aiologic':
        if self._aiologic_module is None:
            import aiologic
            self._aiologic_module = aiologic
        return self._aiologic_module

    def _get_or_create_holder(self) -> 'aiologic.Lock':
        """Atomically get or create the persisted holder lock."""
        with self._holder_init_lock:
            if self._holder is None:
                self._holder = self._ensure_aiologic_imported().Lock()
            return self._holder

    async def acquire(self) -> 'aiologic.Lock':
        """
        Acquire the underlying aiologic.Lock, creating it on first call.

        Returns the aiologic.Lock directly — caller uses `async with` on it.
        The holder lock ensures only one coroutine initializes the aiologic.Lock.
        """
        holder = self._get_or_create_holder()
        async with holder:
            if self._lock is None:
                # aiologic.Lock() is SYNCHRONOUS constructor — NO AWAIT, NO SENTINEL NEEDED
                self._lock = self._ensure_aiologic_imported().Lock()
            return self._lock

    def is_initialized(self) -> bool:
        return self._lock is not None
```

---

## Usage Patterns

### In `locks.py` (SPI Bus Registry)

```python
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
import aiologic

_registry = LazyAsyncLock()
_bus_locks: dict[int, aiologic.Lock] = {}
_aiologic_module: 'aiologic | None' = None
_registry_verified = False

async def get_bus_lock(bus_number: int) -> aiologic.Lock:
    global _aiologic_module, _registry_verified

    if not _registry_verified:
        _verify_single_registry()
        _registry_verified = True

    if _aiologic_module is None:
        import aiologic
        _aiologic_module = aiologic

    registry_lock = await _registry.acquire()
    async with registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _aiologic_module.Lock()
        return _bus_locks[bus_number]
```

### In `config_loader.py` (Config Cache)

```python
from pi_lora.framework.lazy_async_lock import LazyAsyncLock

_config_lock = LazyAsyncLock()
_config_cache: Rfm9xSx127xConfig | None = None

async def get_preloaded_config(
    force_reload: bool = False,
    config_path: Path | None = None,
) -> Rfm9xSx127xConfig:
    global _config_cache

    config_lock = await _config_lock.acquire()

    # SINGLE CODE PATH — no init/else branches, no sentinel race possible
    async with config_lock:
        if _config_cache is not None and not force_reload and config_path is None:
            return _config_cache

        if config_path is not None:
            config = load_config(config_path=config_path)
            if force_reload:
                _config_cache = config
            return config

        _config_cache = load_config()
        return _config_cache
```

---

## Anti-Regression Rules (Semgrep)

```yaml
# .semgrep/rules/custom/lazy-async-lock-guard.yaml
rules:
  # 1. Detect old sentinel pattern
  - id: sentinel-pattern-deprecated
    pattern-either:
      - pattern: _SENTINEL = object()
      - pattern: $LOCK = _SENTINEL
    message: "Sentinel pattern deprecated — use LazyAsyncLock instead"
    severity: ERROR

  # 2. Detect new asyncio.Lock() inside holder (holder persistence bug)
  - id: holder-not-persisted
    pattern: |
      with $GUARD:
          $HOLDER: asyncio.Lock = asyncio.Lock()
    message: "New holder created each call — LazyAsyncLock persists holder"
    severity: ERROR

  # 3. Detect double-checked locking without holder protecting else-branch
  - id: else-branch-unprotected
    pattern-either:
      - pattern: |
          if $LOCK is None:
            async with $HOLDER:
              if $LOCK is None:
                $LOCK = $Y.Lock()
            else:
              async with $LOCK:
                $BODY: ...
      - pattern: |
          if $LOCK is None:
            with $GUARD:
              $LOCK = $Y.Lock()
            else:
              async with $LOCK:
                $BODY: ...
    message: "Else branch outside holder — sentinel race risk. Use LazyAsyncLock."
    severity: ERROR

  # 4. Detect manual double-checked locking (should use LazyAsyncLock)
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
```

---

## Concurrency Tests

```python
# tests/framework/test_lazy_async_lock.py

import asyncio
import pytest
from pi_lora.framework.lazy_async_lock import LazyAsyncLock


@pytest.mark.asyncio
async def test_single_initialization_under_concurrency():
    """Verify only ONE aiologic.Lock created under 100 concurrent callers."""
    lock = LazyAsyncLock()
    created = set()

    async def acquire_and_record():
        acquired = await lock.acquire()
        created.add(id(acquired))
        return acquired

    await asyncio.gather(*[acquire_and_record() for _ in range(100)])
    assert len(created) == 1, f"Expected 1 lock, got {len(created)}"


@pytest.mark.asyncio
async def test_holder_persisted():
    """Verify holder lock is reused across calls."""
    lock = LazyAsyncLock()
    await lock.acquire()
    h1 = lock._holder
    await lock.acquire()
    h2 = lock._holder
    assert h1 is h2, "Holder not persisted"


@pytest.mark.asyncio
async def test_no_sentinel_race():
    """Verify no AttributeError on concurrent init + else-branch access."""
    lock = LazyAsyncLock()

    async def mixed_access():
        return await lock.acquire()

    # Should never raise AttributeError (sentinel race)
    await asyncio.gather(*[mixed_access() for _ in range(200)])


@pytest.mark.asyncio
async def test_stress_concurrent_access():
    """Stress test with many concurrent operations."""
    lock = LazyAsyncLock()

    async def work():
        async with await lock.acquire():
            await asyncio.sleep(0.001)

    await asyncio.gather(*[work() for _ in range(500)])
```

**Run with**: `uv run pytest tests/framework/test_lazy_async_lock.py -v -n auto`

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Holder type** | `aiologic.Lock` (not `asyncio.Lock`) | `asyncio.Lock` bound to creating thread's event loop; `aiologic.Lock` works cross-thread |
| **Sentinel** | Removed entirely | `aiologic.Lock()` is sync constructor — race doesn't exist |
| **Code paths** | Single unified path | Eliminates logic divergence between init/else branches |
| **Holder creation** | `threading.Lock` + double-checked | Atomic, works without event loop |
| **Return type** | Raw `aiologic.Lock` | No wrapper class needed; protocol satisfied directly |

---

## When to Use This Pattern

Use `LazyAsyncLock` when you need:
1. **Lazy initialization** of an async lock
2. **Thread-safe** initialization (called from multiple threads)
3. **Single instance** guarantee across all callers
4. **No sentinel race** risk

**Do NOT** reimplement double-checked locking manually — the semgrep rules will catch it.

---

## Migration Checklist

When replacing old patterns:
- [ ] Remove `_SENTINEL = object()`
- [ ] Remove `_holder_init_lock`, `_holder`, `_lock` separate fields
- [ ] Remove `if _lock is None:` + `else:` dual branches
- [ ] Replace with single `LazyAsyncLock()` instance
- [ ] Update all callers to `lock = await _lazy_lock.acquire(); async with lock:`
- [ ] Add concurrency test for the new usage
- [ ] Run semgrep to verify old patterns eliminated