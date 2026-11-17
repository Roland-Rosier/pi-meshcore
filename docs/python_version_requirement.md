# Python Version Requirement Rationale

**Minimum Version**: Python 3.11 (`requires-python = ">=3.11"`)

This document records the specific Python 3.11+ features used in the codebase and their locations, justifying the minimum version requirement.

---

## Features Requiring Python 3.11+

### 1. `ExceptionGroup` and `except*` syntax

**Module**: `asyncio` / built-in (PEP 654)

**Used in**:
- `src/pi_lora/framework/scheduler.py:659` — `raise ExceptionGroup("Errors during Scheduler.unregister_module()", errors)`
- `src/pi_lora/framework/module_manager.py:64-65` — `except ExceptionGroup as eg:` in `_rollback_pending()`
- `src/pi_lora/framework/module_manager.py:237` — `except (Exception, ExceptionGroup) as rollback_exc:` in `load_from_config()`
- `src/pi_lora/framework/application.py:142-155` — `except ExceptionGroup as exc:` in `start()` exception handler
- `src/pi_lora/framework/command_bus.py:124-152` — `except ExceptionGroup as eg:` in `execute()` handler
- `src/pi_lora/framework/application.py:271-400` — `_cleanup_and_reraise_cancellation()` handles `ExceptionGroup` from cleanup

**Why**: Aggregating multiple concurrent exceptions (scheduler component failures, module rollback errors) into a single raisable object. Required for structured error handling across the async scheduler framework.

---

### 2. `typing.Self` (PEP 673)

**Module**: `typing`

**Used in**:
- `src/pi_lora/drivers/spi/locks.py:19` — `from typing import Any, Protocol, Self`
- `src/pi_lora/drivers/spi/locks.py:40-41` — Protocol methods return `Self`:
  ```python
  async def __aenter__(self) -> Self: ...
  async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...
  ```

**Why**: Type-safe protocol for `SpiLock` where async context manager methods return the concrete implementing type. Avoids `TypeVar` boilerplate.

---

### 3. `asyncio.TimeoutError` distinct from builtin `TimeoutError` (PEP 654 / 3.11+)

**Module**: `asyncio`

**Used in**:
- `src/pi_lora/drivers/spi/bus.py:360-366` — `except asyncio.TimeoutError as err:` in `xfer2()` timeout handling
- `src/pi_lora/drivers/rfm9x_sx127x_module.py:286` — `except asyncio.TimeoutError:` for SPI transfer timeouts
- `src/pi_lora/drivers/rfm9x_sx127x_module.py:276` — `asyncio.wait_for(..., timeout=...)` raises `asyncio.TimeoutError`

**Why**: In Python 3.11+, `asyncio.TimeoutError` is a distinct exception class (not an alias for builtin `TimeoutError`). Code explicitly catches `asyncio.TimeoutError` to avoid accidentally catching builtin `TimeoutError` from other operations.

---

### 4. `asyncio.CancelledError` as `BaseException` (Python 3.13+ compatible)

**Module**: `asyncio`

**Used in** (with forward-compatible handler ordering):
- `src/pi_lora/framework/application.py:144, 332, 352` — `except asyncio.CancelledError` before `except Exception`
- `src/pi_lora/framework/command_bus.py:107` — `except asyncio.CancelledError` before `except Exception`
- `src/pi_lora/framework/module_manager.py:189` — `except (Exception, asyncio.CancelledError)`

**Why**: In Python 3.11/3.12, `CancelledError` inherits from `Exception`. In Python 3.13+, it inherits directly from `BaseException`. The code catches `CancelledError` **explicitly first** (before `Exception`), which works correctly on ALL versions 3.11+.

---

## Version Compatibility Matrix

| Feature | 3.10 | 3.11 | 3.12 | 3.13+ |
|---------|------|------|------|-------|
| `ExceptionGroup` | ❌ | ✅ | ✅ | ✅ |
| `typing.Self` | ❌ | ✅ | ✅ | ✅ |
| `asyncio.TimeoutError` (distinct) | ❌ (alias) | ✅ | ✅ | ✅ |
| `CancelledError` inheritance | `Exception` | `Exception` | `Exception` | `BaseException` |
| Handler ordering fix | N/A | Works | Works | Works |

---

## Verification

The codebase is tested locally on Python 3.13.5. No CI pipeline exists to validate 3.11/3.12 compatibility automatically.

**Manual verification checklist for new Python versions**:
- [ ] Run `uv run pytest tests/ -x` on target version
- [ ] Verify `ExceptionGroup` catch/raise works in `scheduler.py`, `module_manager.py`, `application.py`, `command_bus.py`
- [ ] Verify `asyncio.CancelledError` caught before `Exception` in all handler chains
- [ ] Verify `asyncio.TimeoutError` caught explicitly in `bus.py` and `rfm9x_sx127x_module.py`
- [ ] Verify `typing.Self` protocol in `locks.py` type-checks with `mypy --strict`

---

## References

- PEP 654: Exception Groups and except* — https://peps.python.org/pep-0654/
- PEP 673: Type Parameter `Self` — https://peps.python.org/pep-0673/
- Python 3.11 Release Notes — https://docs.python.org/3/whatsnew/3.11.html
- Python 3.13 Release Notes (CancelledError change) — https://docs.python.org/3/whatsnew/3.13.html