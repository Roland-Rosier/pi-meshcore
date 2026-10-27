# Exception Handling

**Enforced pattern:** `except Exception:` + `finally`, never `except BaseException:` or a bare `except:`.

## The Contract

Every catch site in `src/pi_lora/` must catch `Exception` only. The `finally` block is what guarantees side-effect cleanup (locks released, event loop stopped), so `finally` is the correct anchor for cleanup — not the `except`.

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

- `uv run bash -c 'grep -rn "except BaseException:" src/ --include="*.py"'` → **0 results** (clean).
- `uv run bash -c 'grep -rn "except:" src/ --include="*.py"'` → **0 results** (clean).

Any live `except BaseException:` or bare `except:` in `src/` must be converted to `except Exception:` unless an inline comment justifies the intentional catch of an interpreter-level exception.

## Reference

- Fixed defect: `src/pi_lora/cli/test.py` NR-4 — `except BaseException:` replaced with `except Exception:` (Plan-14, R-1).
