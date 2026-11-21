# Application Lifecycle Patterns

## Overview

The `Application` class (`src/pi_lora/framework/application.py`) manages the complete lifecycle of the LoRa system: module loading, scheduler startup, and graceful shutdown. This document captures the hardened patterns that evolved through Plans 4-38.

---

## Core Lifecycle Methods

### `start(assembly_name: str) → None`

```python
async def start(self, assembly_name: str = "default") -> None:
    """
    Start the application with the given assembly.

    SAFETY GUARANTEES (Plan-38 Fix 2):
    - NO fast-path read of self._started (False→True→False race)
    - Single authoritative check inside _lifecycle_lock
    - Exception chaining preserves root cause through cleanup
    """
    # PLAN-25 FIX (Fix 6, Issue 24.7): double-checked locking was REMOVED in Plan-38.
    # The fast-path read of self._started outside the lock is UNSAFE for a boolean
    # that transitions False→True→False (code_review-37.2 Section 3.2):
    #   1. Thread A: reads _started=False, acquires lock, starts, sets _started=True
    #   2. Thread B: calls stop(), acquires lock, sets _started=False
    #   3. Thread C: reads _started=True (STALE - Thread B's write not visible), returns early WITHOUT starting!
    # The authoritative check is now ONLY the re-check inside _lifecycle_lock.
    # Cross-reference: code_review-37.2.json Section 3.2.

    async with self._lifecycle_lock:
        # Re-check inside lock (authoritative)
        if self._started:
            return

        # Clear tracking FIRST (before any await)
        self.module_manager.modules.clear()
        self.module_manager.modules_by_id.clear()
        self._started_modules = []

        try:
            await self.module_manager.load_from_config(assembly_name)
            await self.scheduler.start()
            self._scheduler_started = True
            self._started = True
            self._started_modules = self.module_manager.get_all_modules()

        except BaseException as exc:
            exc_to_raise = exc
            try:
                await self._cleanup_partial_start()
            except BaseException as cleanup_exc:
                # Prevent self-referential __cause__ cycle (code_review-37.2 Section 3.3):
                if cleanup_exc is exc_to_raise:
                    raise
                raise exc_to_raise from cleanup_exc
            raise exc_to_raise
```

### `stop() → None`

```python
async def stop(self) -> None:
    """
    Stop the application gracefully.

    SAFETY GUARANTEES:
    - Errors aggregated via ExceptionGroup
    - Lock ordering: lifecycle_lock acquired for entire operation
    - Module unregistration before scheduler stop
    """
    async with self._lifecycle_lock:
        if not self._started:
            return

        # CRITICAL: Create errors list INSIDE lock (Plan-11 fix 3.5)
        errors: list[BaseException] = []

        # 1. Stop modules (reverse order for dependency safety)
        for module in reversed(self._started_modules):
            try:
                await self.scheduler.unregister_module(module)
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception(
                    "scheduler.unregister_module failed for SPI device=%s CE=%s",
                    module.get_spi_device_id(),
                    module.get_ce_number(),
                )
                errors.append(exc)

        # 2. Stop scheduler
        if self._scheduler_started:
            try:
                await self.scheduler.stop()
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception("scheduler.stop() failed")
                errors.append(exc)

        # 3. Clear state
        self._started = False
        self._scheduler_started = False
        self._started_modules = []

        # 4. Raise aggregated errors
        if errors:
            raise ExceptionGroup("Application stop failed", errors)
```

---

## Key Patterns

### Pattern 1: No Fast-Path for Transitional Booleans

**NEVER** do this:
```python
# DANGEROUS for flags that go False→True→False
already_started = self._started
if already_started:
    return
async with self._lifecycle_lock:
    ...
```

**ALWAYS** do this:
```python
async with self._lifecycle_lock:
    if self._started:
        return
    ...
```

**Why**: For a flag with `False→True→False` transitions, a stale read outside the lock causes:
- Thread C reads `_started=True` (stale, Thread B already set `False`)
- Returns early **without starting** — silent failure!

This was proven in `code_review-37.2 Section 3.2` and fixed in Plan-38.

---

### Pattern 2: State Clearing Before Awaits

```python
async with self._lifecycle_lock:
    # Clear tracking FIRST (before any await)
    self.module_manager.modules.clear()
    self.module_manager.modules_by_id.clear()
    self._started_modules = []

    try:
        await self.module_manager.load_from_config(...)
        ...
```

**Why**: If `load_from_config()` fails, the cleanup code in `_cleanup_partial_start()` expects clean state. Clearing after the first await would race with concurrent `stop()`.

---

### Pattern 3: Exception Chaining Through Cleanup

```python
except BaseException as exc:
    exc_to_raise = exc
    try:
        await self._cleanup_partial_start()
    except BaseException as cleanup_exc:
        # Identity check prevents self-referential __cause__ cycle
        if cleanup_exc is exc_to_raise:
            raise
        raise exc_to_raise from cleanup_exc
    raise exc_to_raise
```

**Why**: If cleanup raises, we must preserve the original exception as `__cause__`. But if cleanup raises the SAME exception object (e.g., second `KeyboardInterrupt`), chaining creates a cycle.

---

### Pattern 4: `_cleanup_partial_start()` Mirrors `stop()`

```python
async def _cleanup_partial_start(self) -> None:
    """Clean up after a failed start(). Mirrors stop() logic."""
    # CRITICAL: Must acquire lifecycle_lock (Plan-11 fix 1.2)
    async with self._lifecycle_lock:
        errors: list[BaseException] = []

        # Unregister modules (same as stop)
        for module in self._started_modules:
            try:
                await self.scheduler.unregister_module(module)
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception(
                    "scheduler.unregister_module failed for SPI device=%s CE=%s",
                    module.get_spi_device_id(),
                    module.get_ce_number(),
                )
                errors.append(exc)

        # Stop scheduler if it was started
        if self._scheduler_started:
            try:
                await self.scheduler.stop()
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception("scheduler.stop() failed during partial start cleanup")
                errors.append(exc)

        # Clear state
        self._started = False
        self._scheduler_started = False
        self._started_modules = []

        if errors:
            raise ExceptionGroup("Partial start cleanup failed", errors)
```

---

### Pattern 5: Centralized Cleanup Handler

```python
async def _cleanup_and_reraise_cancellation(
    self,
    original_exc: BaseException | None,
    cleanup_coro: Awaitable[None],
) -> None:
    """
    Centralized cleanup with 4-case exception ordering.
    
    Order: CancelledError → Exception → ExceptionGroup → BaseException
    """
    try:
        await cleanup_coro
    except asyncio.CancelledError as exc:
        if original_exc is not None and isinstance(original_exc, asyncio.CancelledError):
            # Prevent self-referential __cause__ cycle (code_review-37.2 Section 3.4)
            if exc is original_exc:
                raise
            raise original_exc from exc
        raise
    except Exception as exc:
        if original_exc is not None:
            raise original_exc from exc
        raise
    except ExceptionGroup as eg:
        if original_exc is not None:
            raise original_exc from eg
        raise
    except BaseException as cleanup_exc:
        if original_exc is not None and isinstance(
            original_exc,
            asyncio.CancelledError | KeyboardInterrupt | SystemExit | GeneratorExit,
        ):
            # Prevent self-referential __cause__ cycle
            if cleanup_exc is original_exc:
                raise
            raise original_exc from cleanup_exc
        raise
```

**Usage**:
```python
await self._cleanup_and_reraise_cancellation(
    original_exc,
    self._cleanup_partial_start(),
)
```

---

## State Machine

```
┌─────────────┐
│   CREATED   │  (Application.__init__)
└──────┬──────┘
       │ start()
       ▼
┌─────────────┐     load_from_config() fails
│  STARTING   │──────────────────────────┐
└──────┬──────┘                           │
       │                                 │ _cleanup_partial_start()
       │ scheduler.start() succeeds      ▼
       ▼                           ┌─────────────┐
┌─────────────┐                     │   CREATED   │
│   RUNNING   │                     └─────────────┘
└──────┬──────┘
       │ stop()
       ▼
┌─────────────┐     stop() fails (ExceptionGroup)
│  STOPPING   │──────────────────────────┐
└──────┬──────┘                           │
       │                                 │ errors raised
       ▼                                 ▼
┌─────────────┐                     ┌─────────────┐
│   CREATED   │                     │   CREATED   │
└─────────────┘                     └─────────────┘
```

---

## Validation Rules

### Must Pass

1. **Concurrent start/stop**: `test_concurrent_start_stop_no_race`
2. **Cancellation semantics**: `TestCancellationSemantics`
3. **ExceptionGroup handling**: All cleanup paths
4. **No fast-path reads**: `grep -n "already_started" application.py` → 0 results
5. **State cleared before await**: `grep -B5 -A5 "modules.clear()" application.py`

### Semgrep Rules

```yaml
- id: application-fast-path-read
  pattern: |
    $VAR = self._started
    if $VAR:
      return
    async with self._lifecycle_lock:
  message: "Fast-path read of _started outside lock — removed in Plan-38 (False→True→False race)"
  severity: ERROR

- id: application-errors-outside-lock
  pattern: |
    errors = []
    async with self._lifecycle_lock:
  message: "Errors list created outside lifecycle_lock — race on concurrent stop()"
  severity: ERROR
```

---

## Anti-Regression Notes

| Anti-Pattern | Detection | Fix |
|--------------|-----------|-----|
| Fast-path read of `_started` | Semgrep + code review | Remove; only check inside lock |
| `errors = []` outside lock | Semgrep | Move inside `async with` |
| `except (Exception, CancelledError)` | Code review | Split handlers |
| Cleanup without `shield()` | Code review | Wrap rollback in `asyncio.shield()` |
| ExceptionGroup after Exception | Semgrep | Reorder handlers |

---

## Testing Patterns

```python
# tests/framework/test_application.py

@pytest.mark.asyncio
async def test_concurrent_start_stop_no_race():
    """Verify no race between concurrent start/stop."""
    app = Application(config, spi_factory)
    
    async def start_then_stop():
        await app.start("default")
        await app.stop()
    
    # Run many concurrent start/stop cycles
    await asyncio.gather(*[start_then_stop() for _ in range(50)])
    
    assert not app._started
    assert not app._scheduler_started


@pytest.mark.asyncio
async def test_cancelled_error_propagates():
    """CancelledError during start must propagate after cleanup."""
    app = Application(config, spi_factory)
    
    with patch.object(app.module_manager, 'load_from_config', 
                      side_effect=asyncio.CancelledError()):
        with pytest.raises(asyncio.CancelledError):
            await app.start("default")
    
    # State should be clean
    assert not app._started
    assert not app._scheduler_started
```

---

## Related Files

- `src/pi_lora/framework/application.py` — Main implementation
- `tests/framework/test_application.py` — Unit tests
- `tests/framework/test_application_start_stop_race.py` — Race condition tests
- `docs/patterns/exception_handling.md` — Exception chaining patterns
- `docs/patterns/concurrency_lazy_async_lock.md` — Lock patterns used