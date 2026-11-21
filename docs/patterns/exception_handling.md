# Exception Handling Patterns

## Overview

This document captures the exception handling patterns established during the hardening spike (Plans 4-38) to prevent common bugs like exception chaining cycles, `CancelledError` swallowing, and `ExceptionGroup` handling.

---

## Pattern 1: Self-Referential `__cause__` Cycle Prevention

### The Bug

When chaining exceptions with `raise exc from cleanup_exc`, if `cleanup_exc` is the **same object** as `exc`, Python creates a self-referential cycle: `exc.__cause__ = exc`. This breaks traceback rendering.

### When It Happens

- Second `KeyboardInterrupt` during cleanup
- `SystemExit` during shutdown handling
- Any `BaseException` subclass re-raised during cleanup of the same exception

### The Fix: Identity Check Before Chaining

```python
# WRONG — creates self-referential cycle if same exception
except BaseException as cleanup_exc:
    raise exc from cleanup_exc

# CORRECT — check identity first
except BaseException as cleanup_exc:
    if cleanup_exc is exc:
        raise  # Re-raise original without chaining
    raise exc from cleanup_exc
```

### Locations Fixed

| File | Method | Plan |
|------|--------|------|
| `application.py` | `start()` BaseException handler | Plan-38 Fix 3 |
| `application.py` | `_cleanup_and_reraise_cancellation()` BaseException handler | Plan-38 Fix 4 |

### Anti-Regression Comment Template

```python
# Prevent self-referential __cause__ cycle (code_review-37.2 Section 3.3):
# If cleanup_exc IS the same object as exc, `raise exc from cleanup_exc`
# would set exc.__cause__ = exc, breaking traceback rendering.
if cleanup_exc is exc:
    raise
raise exc from cleanup_exc
```

---

## Pattern 2: `CancelledError` Handling — Never Swallow

### The Bug

Catching `asyncio.CancelledError` alongside `Exception` and treating it as a regular error:

```python
# WRONG — swallows cancellation
except (Exception, asyncio.CancelledError) as exc:
    await cleanup()
    # Never re-raises CancelledError!
```

### The Fix: Separate Handlers

```python
# CORRECT — preserve cancellation semantics
try:
    await operation()
except asyncio.CancelledError:
    await cleanup()
    raise  # MUST re-raise to propagate cancellation
except Exception as exc:
    await cleanup()
    raise
```

### Enforcement Rule

**Never** write `except (Exception, asyncio.CancelledError):`. Always split:
1. `except asyncio.CancelledError:` — cleanup + re-raise
2. `except Exception:` — cleanup + raise (or handle)
3. `except ExceptionGroup:` — handle grouped exceptions
4. `except BaseException:` — shutdown signals (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`)

### Locations Enforced

| File | Plan |
|------|------|
| `application.py` `start()`, `stop()`, `_cleanup_partial_start()` | Plan-11, Plan-27, Plan-38 |
| `module_manager.py` `load_from_config()` | Plan-38 Fix 5 |

---

## Pattern 3: `ExceptionGroup` Handling

### The Protocol

When catching exceptions that may raise `ExceptionGroup` during cleanup, handle **before** `Exception`:

```python
except ExceptionGroup as eg:
    errors.extend(eg.exceptions)
except Exception as exc:
    logger.exception("Operation failed")
    errors.append(exc)
```

### Why Order Matters

`ExceptionGroup` is a subclass of `Exception`. If `except Exception:` comes first, it catches `ExceptionGroup` and loses the grouped structure.

### Locations

| File | Method | Plan |
|------|--------|------|
| `application.py` | `_cleanup_partial_start()` | Plan-27, Plan-38 |
| `application.py` | `stop()` | Plan-11 |
| `module_manager.py` | `load_from_config()` rollback | Plan-25, Plan-38 |

---

## Pattern 4: Rollback with `asyncio.shield`

### The Problem

During rollback (e.g., config load failure), a cancellation could interrupt the rollback itself, leaving resources leaked.

### The Fix

```python
except (Exception, asyncio.CancelledError) as original_exc:
    try:
        await asyncio.shield(_rollback_pending(pending_modules, scheduler))
    except (Exception, ExceptionGroup) as rollback_exc:
        # Aggregate or log rollback errors
        if isinstance(rollback_exc, ExceptionGroup):
            raise rollback_exc from original_exc
        raise rollback_exc from original_exc
    raise  # Re-raise original

except BaseException as original_exc:  # KeyboardInterrupt, SystemExit
    try:
        await asyncio.shield(_rollback_pending(pending_modules, scheduler))
    except (Exception, ExceptionGroup):
        logger.warning("Rollback during shutdown signal had errors", exc_info=True)
    raise  # Preserve shutdown signal
```

### Key Points

- `asyncio.shield()` prevents cancellation from interrupting cleanup
- Separate `BaseException` handler for shutdown signals
- Log rollback failures but **don't mask** the original exception/shutdown signal

---

## Pattern 5: Exception Chaining for Preserving Root Cause

### When Cleanup Raises

```python
exc_to_raise = original_exc
try:
    await cleanup()
except BaseException as cleanup_exc:
    if cleanup_exc is exc_to_raise:
        raise  # Same object — re-raise
    raise exc_to_raise from cleanup_exc  # Chain: root cause in __cause__
```

### Why This Matters

- `exc.__cause__` = cleanup exception (explicit chain)
- `exc.__context__` = original exception (implicit)
- Debuggers show both; traceback preserved

---

## Pattern 6: Module-Level Logger (Not Inline)

### Anti-Pattern

```python
# WRONG — creates logger on every call
def execute(self, command):
    logging.getLogger(__name__).error("Failed")  # New logger each call
```

### Correct Pattern

```python
# At module level
logger = logging.getLogger(__name__)

def execute(self, command):
    logger.error("Failed", extra={"command": type(command).__name__})
```

### Files Fixed

- `command_bus.py` — Plan-14 (finding 8.14)
- `lora_detection.py` — Plan-38 Fix 8

---

## Pattern 7: Structured Exception Hierarchy

### Radio Instance Exceptions

```python
class RadioInstanceError(Exception):
    """Base exception for radio instance operations."""
    def __init__(self, message: str, **context):
        super().__init__(message)
        self.context = context

class DriverModuleNotFoundError(RadioInstanceError):
    def __init__(self, module_name: str, spi_device_id: int, ce_number: int):
        self.module_name = module_name
        self.spi_device_id = spi_device_id
        self.ce_number = ce_number
        super().__init__(
            f"Driver module '{module_name}' not found",
            module_name=module_name,
            spi_device_id=spi_device_id,
            ce_number=ce_number,
        )

class AssemblyNotFoundError(RadioInstanceError):
    def __init__(self, assembly_name: str):
        self.assembly_name = assembly_name
        super().__init__(f"Assembly '{assembly_name}' not found", assembly_name=assembly_name)

    @property
    def module_name(self) -> str:  # Deprecated alias
        warnings.warn("Use assembly_name instead", DeprecationWarning, stacklevel=2)
        return self.assembly_name
```

### Benefits

- Explicit attributes for programmatic access
- Context dict for logging/serialization
- Deprecation path for renamed fields

---

## Validation Gates

### Code Review Checks

- [ ] No `except (Exception, asyncio.CancelledError):` patterns
- [ ] All `BaseException` handlers check identity before chaining
- [ ] `ExceptionGroup` caught before `Exception`
- [ ] `asyncio.shield()` used for rollback cleanup
- [ ] Module-level loggers used (not inline)
- [ ] Custom exceptions have explicit attributes

### Semgrep Rules (to add)

```yaml
- id: cancellederror-swallowed
  pattern: except (Exception, asyncio.CancelledError):
  message: "CancelledError swallowed — split into separate handlers"
  severity: ERROR

- id: baseexception-no-identity-check
  pattern: |
    except BaseException as $CLEANUP:
      raise $ORIGINAL from $CLEANUP
  message: "Missing identity check before exception chaining — prevents self-referential __cause__"
  severity: ERROR

- id: exceptiongroup-after-exception
  pattern: |
    except Exception as $E:
      ...
    except ExceptionGroup as $EG:
      ...
  message: "ExceptionGroup caught after Exception — will never match. Move ExceptionGroup first."
  severity: ERROR
```

---

## Summary: Exception Handling Checklist

| Scenario | Pattern |
|----------|---------|
| Normal operation + cleanup | `try/except Exception/except asyncio.CancelledError/except BaseException` |
| Cleanup may raise | Wrap cleanup in inner `try/except`, chain with `raise original from cleanup` |
| Same exception during cleanup | `if cleanup_exc is original: raise` |
| Rollback during failure | `asyncio.shield(_rollback())` + separate `BaseException` handler |
| Logging exceptions | Module-level logger + structured context |
| Custom exceptions | Explicit attributes + context dict + deprecation aliases |

---

## Anti-Regression Notes

1. **Never re-add fast-path reads** for boolean flags that transition `False→True→False` (see `Application.start()` Plan-38 Fix 2)
2. **Never catch `BaseException` without identity check** before chaining
3. **Never use `contextlib.suppress(Exception)`** for resource cleanup — logs failures but swallows real errors
4. **Always use `asyncio.shield()`** for rollback operations that must complete