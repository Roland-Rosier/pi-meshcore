# Exception Handling

**Enforced pattern:** `except Exception:` + `finally`, never `except BaseException:` or a bare `except:` — **unless an inline comment justifies the intentional catch** (see the two Plan-17 cases below).

## The Contract

Every catch site in `src/pi_lora/` must catch `Exception` only. The `finally` block is what guarantees side-effect cleanup (locks released, event loop stopped), so `finally` is the correct anchor for cleanup — not the `except`.

Catching `BaseException` is reserved for exactly two well-justified, deliberate cases. Each is (a) split from `asyncio.CancelledError` so cancellation semantics are preserved and (b) annotated with an inline comment stating why the `BaseException` catch is intentional. Outside those two sites, a `BaseException` catch is a defect.

```python
async def run() -> None:
    lock = await get_bus_lock()
    try:
        await do_work()
    except Exception:
        handle_error()
    finally:
        await lock.async_release()
```

The `finally` block runs for **every** exception type, including `KeyboardInterrupt`, `SystemExit`, and `GeneratorExit`. Therefore catching `Exception` (not `BaseException`) is sufficient to guarantee cleanup while leaving interpreter-level exceptions free to propagate.

## Why `except BaseException:` / bare `except:` are forbidden

`BaseException` is the root of the entire exception hierarchy. Catching it swallows three interpreter-level exceptions that the Python interpreter raises to signal control flow, not program errors:

| Exception | Raised by | Semantics |
|-----------|-----------|-----------|
| `KeyboardInterrupt` | CPython eval loop | Interpreter pause / PEP 3134 |
| `SystemExit` | `sys.exit()`, REPL loop | Program termination |
| `GeneratorExit` | End of a generator | Generator finalization |

Per **PEP 3134** ("No Catch `BaseException`"), these must **propagate**. Suppressing them masks interpreter signals, corrupts REPL state, and breaks generator finalization. `pytest` frames and the CPython eval loop rely on them escaping cleanly.

## Audit enforcement

- `uv run bash -c 'grep -rn "except BaseException:" src/ --include="*.py"'` → **0 results** (clean). The two Plan-17 intentional catches use the *bound* form `except BaseException as base_exc:` (annotated), not this bare form.
- `uv run bash -c 'grep -rn "except:" src/ --include="*.py"'` → **0 results** (clean).

Any live `except BaseException:` (bare) or bare `except:` in `src/` is a defect and must be converted to `except Exception:` unless an inline comment justifies the intentional catch of an interpreter-level exception.

## The Two Deliberate Catches (Plan-17)

### 1. `asyncio.CancelledError` / `BaseException` split — `module_manager.py`

`load_from_config()` in `src/pi_lora/framework/module_manager.py` deliberately catches `BaseException` **after** catching `asyncio.CancelledError`, because a cancelled load task is a *recoverable* state (successfully-created modules should remain committed) whereas every other interpreter-level exception (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`) plus a normal load failure must roll back and re-raise:

```python
except asyncio.CancelledError:
    # Only task cancellation commits partial modules.
    for device_key, module in pending_by_id.items():
        self.modules.append(module)
        self.modules_by_id[device_key] = module
    pending_modules.clear()
    pending_by_id.clear()
    raise

except BaseException as base_exc:
    # Every OTHER BaseException must roll back and re-raise.
    rollback_errors: list[Exception] = []
    while pending_modules:
        module = pending_modules.pop()
        try:
            await scheduler.unregister_module(module)
        except Exception as e:
            rollback_errors.append(e)
    self.modules.clear()
    self.modules_by_id.clear()
    pending_modules.clear()
    pending_by_id.clear()
    if rollback_errors:
        raise ExceptionGroup("Rollback failures during load_from_config", rollback_errors) from base_exc
    raise base_exc
```

The `asyncio.CancelledError` handler must appear **before** the `except BaseException` handler so cancellation commits rather than rolls back. This is the H-16-1 case.

### 2. `_cleanup_and_reraise_cancellation()` contract — `application.py`

`_cleanup_and_reraise_cancellation()` in `src/pi_lora/framework/application.py` re-raises the **original** exception after cleanup, and if cleanup itself is cancelled it logs the cancellation but still re-raises the original exception to preserve asyncio cancellation semantics for the caller:

```python
async def _cleanup_and_reraise_cancellation(
    self,
    cleanup_coro: "Callable[[], Awaitable[None]]",
    original_exc: BaseException | None = None,
) -> None:
    try:
        await cleanup_coro()
    except asyncio.CancelledError as cleanup_cancelled:
        # Cleanup was cancelled. Log it but re-raise the original exception.
        logger.warning(
            "Cleanup was cancelled during exception handling; "
            "re-raising original exception: %r",
            original_exc,
        )
        if original_exc is not None:
            raise original_exc from cleanup_cancelled
        raise  # No original exception; re-raise cleanup cancellation
    except Exception:
        raise
```

This is the §1.3 case.

## Reference

- Fixed defect: `src/pi_lora/cli/test.py` NR-4 — `except BaseException:` replaced with `except Exception:` (Plan-14, R-1).
- Deliberate catches (Plan-17): the `CancelledError`/`BaseException` split in `module_manager.py` (H-16-1) and the `_cleanup_and_reraise_cancellation()` contract in `application.py` (§1.3).
