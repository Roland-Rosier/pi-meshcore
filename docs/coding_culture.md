# Coding Culture & Conventions

## Overview

This document captures the coding culture, conventions, and unwritten rules that emerged during the hardening spike (Plans 4-38). These are the standards that all code in this repository should follow.

---

## Python Version & Tooling

| Tool | Version | Config |
|------|---------|--------|
| Python | ≥ 3.11 | `pyproject.toml: requires-python = ">=3.11"` |
| Type Checker | mypy --strict | `pyproject.toml: [tool.mypy]` |
| Linter | ruff | `pyproject.toml: [tool.ruff]` |
| Security | semgrep | `.semgrep/run.sh` |
| Tests | pytest + pytest-asyncio | `pyproject.toml: [tool.pytest.ini_options]` |
| Coverage | pytest-cov ≥ 90% | `--cov-fail-under=90` |

---

## Type Hinting Standards

### Required
- **All functions**: Parameters + return type
- **All attributes**: Type annotations
- **No `Any`** without explicit justification
- **Generics fully parameterized**: `list[int]`, not `list`

### Patterns
```python
# Good
async def get_bus_lock(bus_number: int) -> aiologic.Lock: ...
_config_cache: Rfm9xSx127xConfig | None = None

# Avoid
async def get_bus_lock(bus_number): ...  # Missing types
_config_cache = None  # No annotation
```

### Imports
```python
# Use TYPE_CHECKING for circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import aiologic

# Relative imports within package
from ..framework.lazy_async_lock import LazyAsyncLock
```

---

## Async Patterns

### Always Await
```python
# Good
lock = await _lazy_lock.acquire()
async with lock:
    ...

# Bad — missing await
lock = _lazy_lock.acquire()  # Returns coroutine!
```

### Exception Handling Order
```python
# ALWAYS this order:
try:
    await operation()
except asyncio.CancelledError:
    await cleanup()
    raise
except ExceptionGroup as eg:
    handle_group(eg)
except Exception as exc:
    handle_single(exc)
except BaseException as exc:  # KeyboardInterrupt, SystemExit
    handle_shutdown(exc)
```

### Never Swallow CancelledError
```python
# WRONG
except (Exception, asyncio.CancelledError):
    ...

# CORRECT — separate handlers
except asyncio.CancelledError:
    raise
except Exception:
    ...
```

---

## Concurrency Patterns

### Lazy Initialization: Use LazyAsyncLock
```python
# Good
_registry = LazyAsyncLock()
lock = await _registry.acquire()

# Bad — manual double-checked locking
if _lock is None:
    async with _holder:
        if _lock is None:
            _lock = aiologic.Lock()
```

### No Sentinel Objects
```python
# Bad — sentinel race
_SENTINEL = object()
_lock = _SENTINEL

# Good — aiologic.Lock() is sync constructor
_lock = aiologic.Lock()  # No await, no sentinel needed
```

### Holder Persistence
```python
# Bad — new holder each call
with guard:
    holder = asyncio.Lock()

# Good — LazyAsyncLock persists holder
holder = lock._get_or_create_holder()  # Reused
```

---

## Resource Management

### Deterministic Cleanup
```python
# Good — context manager + shield
async with asyncio.shield(cleanup_coro()):
    ...

# Bad — rely on __del__
class Foo:
    def __del__(self):
        self.resource.close()  # Unreliable!
```

### Bounded Queues
```python
# Good — OOM protection
queue = asyncio.Queue(maxsize=10000)

# Bad — unbounded
queue = asyncio.Queue()
```

---

## Logging

### Module-Level Logger
```python
# At module top
logger = logging.getLogger(__name__)

# In methods
logger.exception("Operation failed", extra={"key": value})
```

### No Inline Loggers
```python
# Bad
logging.getLogger(__name__).error("Failed")

# Good
logger.error("Failed")
```

---

## Testing Standards

### Concurrency Tests Required
```python
@pytest.mark.asyncio
async def test_single_initialization_under_concurrency():
    lock = LazyAsyncLock()
    created = set()
    async def acquire_and_record():
        acquired = await lock.acquire()
        created.add(id(acquired))
    await asyncio.gather(*[acquire_and_record() for _ in range(100)])
    assert len(created) == 1
```

### Negative Tests for Every Bug Fix
```python
@pytest.mark.asyncio
async def test_fast_path_read_removed():
    """Verify fast-path read of _started was removed (Plan-38)."""
    source = inspect.getsource(Application.start)
    assert "already_started = self._started" not in source
```

### Contract Tests for Protocols
```python
def test_mock_spi_bus_satisfies_contract():
    mock = MockSpiBus(...)
    assert hasattr(type(mock).max_speed_hz, 'fset')  # Setter exists
```

---

## Semgrep Rules as Documentation

Every known bug pattern has a semgrep rule. Rules are:
- **Executable documentation** — they codify the "why"
- **Enforced in CI** — 0 findings required
- **Tested** — `ruleid:` (bad) and `ok:` (good) examples

```yaml
# Example rule structure
- id: descriptive-name
  pattern: |
    # Minimal bug pattern
    ...
  message: "Why this is banned + what to use instead"
  severity: ERROR
```

---

## Documentation Standards

### In-Code Anti-Regression Comments
Every fix site includes:
```python
# PLAN-XX FIX (Issue N): Brief description.
# The [bug] was [root cause]. [Fix] prevents this by [mechanism].
# Cross-reference: code_review-YY.json Section Z.
```

### Plan References
- Plans are in `.plans/2026_10_08_hardening_spike/plan-*.md`
- Reviews in same directory: `plan-*_review.md`, `code_review-*.json`
- Durable summary: `docs/plan_summaries/2026_10_08_hardening_spike.md`

---

## Git & Commit Practices

### Commit Messages
```
fix: Prevent self-referential __cause__ cycle in Application.start()

Plan-38 Fix 3 (code_review-37.2 Section 3.3).
Identity check before exception chaining prevents exc.__cause__ = exc
when cleanup raises the same exception object.

Refs: .plans/2026_10_08_hardening_spike/plan-38.md
```

### Branch Names
- `fix/issue-description` for bug fixes
- `feat/feature-name` for features
- `refactor/subsystem` for refactoring

---

## Code Review Checklist

### For Author
- [ ] All 4 validation gates pass locally
- [ ] Concurrency tests for any new locks
- [ ] Negative tests for bug fixes
- [ ] Semgrep rules added for new patterns
- [ ] Anti-regression comments at fix sites
- [ ] Type hints complete (mypy --strict clean)

### For Reviewer
- [ ] Check anti-pattern checklist (see patterns/README.md)
- [ ] Verify semgrep passes (no suppressed findings)
- [ ] Check exception handling order
- [ ] Verify `asyncio.shield()` on rollbacks
- [ ] Check for fast-path reads on transitional flags
- [ ] Verify pending list pattern for atomic commit
- [ ] Check lock ordering in stop() methods

---

## Deferred Items (Not Blocking)

| Item | Status | Effort |
|------|--------|--------|
| Duty cycle enforcement (EU compliance) | Deferred | ~1 day |
| `osc_freq_hz` required in model | Deferred | ~2 hours |
| `LoraMode` enum cleanup | Deferred | ~1 hour |
| Web API / background tasks | Out of scope | Separate effort |
| MeshCore protocol | Out of scope | Separate effort |
| Real hardware integration tests | Missing | ~2 days (CI runner) |

---

## Philosophy

> **"Make it impossible to write the wrong code."**

- Semgrep rules catch bug patterns at PR time
- Type system catches interface mismatches
- Concurrency tests catch races
- Negative tests catch regressions
- Code review catches the rest

> **"Document the why, not the what."**

- Anti-regression comments explain root cause
- Plan references provide full context
- Semgrep rules are executable documentation
- Pattern documents capture decisions

> **"Test the boundary, not the happy path."**

- Concurrency stress tests (100+ parallel)
- Cancellation during cleanup
- KeyboardInterrupt during load
- QueueFull during interrupt burst
- ExceptionGroup from multiple handlers

---

## Quick Reference: Forbidden Patterns

| Pattern | Replacement |
|---------|-------------|
| `except (Exception, CancelledError)` | Separate handlers |
| `raise exc from cleanup` (no identity check) | `if cleanup is exc: raise` |
| `asyncio.sleep(0)` in loop | `sleep(min_interval)` |
| `asyncio.Queue()` unbounded | `Queue(maxsize=10000)` |
| Manual double-checked locking | `LazyAsyncLock` |
| `_SENTINEL = object()` | Remove (aiologic.Lock is sync) |
| Module-level `setup_logging()` | Entry-point `_run_app()` |
| `cast(int, app())` no try/except | `_run_app()` helper |
| Inline `logging.getLogger()` | Module-level `logger` |
| Direct `self.modules.append()` | Pending lists + atomic commit |
| Stop: flag → cancel → lock | Lock → flag → cancel |

---

## Onboarding Checklist

For new contributors:
1. Read `docs/patterns/README.md`
2. Run `uv run pytest tests/ -x` — all pass
3. Run `uv run mypy --strict src/` — 0 errors
4. Run `uv run ruff check src/ tests/` — 0 warnings
5. Run `uv run .semgrep/run.sh` — 0 findings
5. Pick a pattern doc relevant to your task
6. Write code following the patterns
7. Add tests (concurrency + negative)
8. Run all gates again
9. Submit PR

---

*This document evolves. When you discover a new pattern or anti-pattern, update the relevant pattern doc and this culture doc.*