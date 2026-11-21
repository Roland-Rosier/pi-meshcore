# Module Registration & Rollback Patterns

## Overview

The `ModuleManager` (`src/pi_lora/framework/module_manager.py`) handles loading, registering, and rolling back LoRa radio modules from configuration. This document captures the hardened patterns that evolved through Plans 4-38.

---

## Core Pattern: Pending Lists + Atomic Commit

### The Pattern

```python
async def load_from_config(self, assembly_name: str) -> None:
    """
    Load modules from assembly config with atomic commit/rollback.

    SAFETY GUARANTEES (Plan-38 Fix 5):
    - Pending lists separate from committed state
    - Rollback on ANY exception (including KeyboardInterrupt/SystemExit)
    - ExceptionGroup handling preserves all errors
    - Scheduler registration AFTER tracking list append
    """
    pending_modules: list[Rfm9xSx127xModule] = []
    pending_by_id: dict[str, Rfm9xSx127xModule] = {}

    async def _rollback_pending() -> None:
        """Best-effort rollback — shielded from cancellation."""
        for module in pending_modules:
            try:
                await asyncio.shield(self.scheduler.unregister_module(module))
            except (Exception, ExceptionGroup):
                # Log but don't propagate — original error takes precedence
                logger.warning("Rollback unregister failed", exc_info=True)

    try:
        # 1. Parse and validate ALL configs first
        device_configs = parse_assembly_config(assembly_name)
        
        # 2. Create and register modules ONE BY ONE
        for device_config in device_configs:
            module = Rfm9xSx127xModule(device_config, self.spi_factory)
            
            # DUPLICATE CHECK (Plan-22): Check BEFORE registering
            if module.identity in self.modules_by_id:
                raise DuplicateDeviceIdentityError(
                    f"Duplicate device identity: {module.identity}"
                )
            if module.identity in pending_by_id:
                raise DuplicateDeviceIdentityError(
                    f"Duplicate device identity in pending: {module.identity}"
                )
            
            # REGISTER IN SCHEDULER FIRST (so cleanup can unregister)
            await self.scheduler.register_module(module)
            
            # THEN ADD TO TRACKING (so rollback iterates correctly)
            pending_modules.append(module)
            pending_by_id[module.identity] = module

        # 3. ALL SUCCEEDED — ATOMIC COMMIT
        self.modules.extend(pending_modules)
        self.modules_by_id.update(pending_by_id)
        
    except (Exception, asyncio.CancelledError) as original_exc:
        # RECOVERABLE ERRORS — Full rollback, then re-raise
        try:
            await asyncio.shield(_rollback_pending())
        except (Exception, ExceptionGroup) as rollback_exc:
            pending_modules.clear()
            pending_by_id.clear()
            if isinstance(rollback_exc, ExceptionGroup):
                raise rollback_exc from original_exc
            raise rollback_exc from original_exc
        pending_modules.clear()
        pending_by_id.clear()
        raise
        
    except BaseException as original_exc:  # KeyboardInterrupt, SystemExit, GeneratorExit
        # SHUTDOWN SIGNALS — Best-effort rollback, preserve signal
        try:
            await asyncio.shield(_rollback_pending())
        except (Exception, ExceptionGroup):
            logger.warning(
                "Rollback during shutdown signal had errors; original signal preserved",
                exc_info=True
            )
        pending_modules.clear()
        pending_by_id.clear()
        raise
```

---

## Key Patterns

### Pattern 1: Pending Lists (Not Direct Mutation)

```python
# WRONG — mutates committed state directly
self.modules.append(module)
await self.scheduler.register_module(module)
# If next module fails → inconsistent state!

# CORRECT — use pending lists
pending_modules.append(module)
await self.scheduler.register_module(module)
# Only on full success: self.modules.extend(pending_modules)
```

**Why**: If any step fails, the committed `self.modules` is untouched. Rollback only needs to clean up `pending_modules`.

---

### Pattern 2: Register in Scheduler BEFORE Adding to Tracking

```python
# CORRECT ORDER (Plan-38 Fix 5, related to Plan-13):
await self.scheduler.register_module(module)  # 1. Register
pending_modules.append(module)                # 2. Track
```

**Why**: If exception occurs AFTER registration but BEFORE tracking:
- Module is in scheduler
- Rollback iterates `pending_modules` (empty!)
- Module never unregistered → dangling reference in scheduler

By registering FIRST, the module is guaranteed to be in `pending_modules` for rollback.

---

### Pattern 3: Duplicate Check BEFORE Registration

```python
# Check BOTH committed AND pending
if module.identity in self.modules_by_id:
    raise DuplicateDeviceIdentityError(...)
if module.identity in pending_by_id:
    raise DuplicateDeviceIdentityError(...)
```

**Why**: Prevents duplicate identities across both committed and in-flight modules.

---

### Pattern 4: Two Exception Handlers (Recoverable vs Shutdown)

```python
except (Exception, asyncio.CancelledError) as original_exc:
    # Full rollback, chain exceptions
    await asyncio.shield(_rollback_pending())
    raise

except BaseException as original_exc:  # KeyboardInterrupt, SystemExit
    # Best-effort rollback, PRESERVE SHUTDOWN SIGNAL
    await asyncio.shield(_rollback_pending())
    raise  # Re-raise original signal
```

**Why**: 
- `CancelledError` is recoverable (task cancellation) — full rollback + chain
- `KeyboardInterrupt`/`SystemExit` are shutdown signals — best effort + preserve signal

---

### Pattern 5: `asyncio.shield()` for Rollback

```python
async def _rollback_pending() -> None:
    for module in pending_modules:
        try:
            await asyncio.shield(self.scheduler.unregister_module(module))
        except (Exception, ExceptionGroup):
            logger.warning("Rollback unregister failed", exc_info=True)
```

**Why**: Prevents cancellation from interrupting the rollback itself. If cleanup is cancelled mid-way, resources leak.

---

## Rollback Error Aggregation

### The Pattern

```python
try:
    await asyncio.shield(_rollback_pending())
except ExceptionGroup as eg:
    # Preserve all rollback errors as a group
    raise eg from original_exc
except Exception as rollback_exc:
    # Single rollback error
    raise rollback_exc from original_exc
```

### Why Chain with `from original_exc`

- `rollback_exc.__cause__ = original_exc`
- Debuggers show both the original failure AND the rollback failure
- Neither is lost

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Direct `self.modules.append()` before scheduler register | Dangling ref on failure | Use pending lists |
| Single `except Exception:` for all errors | Swallows `KeyboardInterrupt` | Separate `BaseException` handler |
| No `asyncio.shield()` on rollback | Cancellation leaks resources | Wrap rollback in `shield()` |
| Rollback errors not chained | Original error lost | `raise rollback_exc from original_exc` |
| Duplicate check only in committed | Allows in-flight duplicates | Check both `modules_by_id` AND `pending_by_id` |

---

## Validation Rules

### Semgrep Rules

```yaml
- id: modulemanager-direct-append
  pattern: |
    self.modules.append($MODULE)
    await self.scheduler.register_module($MODULE)
  message: "Direct append before scheduler registration — use pending lists (Plan-38 Fix 5)"
  severity: ERROR

- id: modulemanager-no-shield-rollback
  pattern: |
    for $M in $PENDING:
      await self.scheduler.unregister_module($M)
  message: "Rollback without asyncio.shield() — cancellation can leak resources"
  severity: ERROR

- id: modulemanager-single-except-baseexception
  pattern: |
    except BaseException:
      ...
      raise
  message: "Catches BaseException but doesn't distinguish shutdown signals — use two handlers"
  severity: ERROR
```

### Must-Pass Tests

```python
# tests/framework/test_module_manager.py

@pytest.mark.asyncio
async def test_rollback_on_keyboard_interrupt():
    """KeyboardInterrupt during load triggers rollback."""
    manager = ModuleManager(scheduler, spi_factory)
    
    with patch.object(manager, '_create_module', 
                      side_effect=KeyboardInterrupt()):
        with pytest.raises(KeyboardInterrupt):
            await manager.load_from_config("default")
    
    # Scheduler should have no registered modules
    assert len(manager.scheduler._modules) == 0


@pytest.mark.asyncio
async def test_rollback_on_exception_preserves_original():
    """Rollback errors chained to original exception."""
    manager = ModuleManager(scheduler, spi_factory)
    
    with patch.object(manager, '_create_module', 
                      side_effect=ValueError("original")):
        with pytest.raises(ValueError, match="original") as exc_info:
            await manager.load_from_config("default")
    
    # Original cause preserved
    assert exc_info.value.__cause__ is not None


@pytest.mark.asyncio
async def test_no_dangling_refs_on_partial_failure():
    """If module 2 fails, module 1 unregistered from scheduler."""
    manager = ModuleManager(scheduler, spi_factory)
    
    modules = [Mock(), Mock()]
    modules[1].identity = "dup"  # Trigger duplicate error
    
    with patch.object(manager, '_create_module', side_effect=modules):
        with pytest.raises(DuplicateDeviceIdentityError):
            await manager.load_from_config("default")
    
    # Module 1 should be unregistered
    assert len(scheduler._modules) == 0
```

---

## Related Patterns

- **Application Lifecycle**: `Application.start()` calls `load_from_config()` and uses `_cleanup_partial_start()` which mirrors this rollback logic
- **Exception Handling**: See `docs/patterns/exception_handling.md` for chaining/shield patterns
- **Concurrency**: `LazyAsyncLock` used for config loader cache (separate concern)

---

## Files

- `src/pi_lora/framework/module_manager.py` — Main implementation
- `tests/framework/test_module_manager.py` — Unit tests
- `docs/patterns/application_lifecycle.md` — Application start/stop
- `docs/patterns/exception_handling.md` — Exception chaining