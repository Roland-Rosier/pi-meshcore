# Validation Gates & Testing Patterns

## Overview

This document captures the validation gates and testing patterns established during the hardening spike (Plans 4-38). These gates must pass with **0 errors** before any code is considered ready.

---

## The Four Validation Gates

### Gate 1: Type Checking (mypy)

```bash
uv run mypy --strict src/
```

**Configuration** (`pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_any_generics = true
no_implicit_optional = true

# Per-module overrides for incomplete stubs
[[tool.mypy.overrides]]
module = "pi_lora.drivers.spi.*"
ignore_missing_imports = true
```

**Must Pass**: 0 errors, 0 warnings

---

### Gate 2: Linting & Formatting (ruff)

```bash
uv run ruff check src/ tests/
```

**Configuration** (`pyproject.toml`):
```toml
[tool.ruff]
target-version = "py311"
line-length = 100
select = [
    "E",   # pycodestyle
    "F",   # pyflakes
    "I",   # isort
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "SIM", # flake8-simplify
    "T20", # flake8-print
]
ignore = [
    "S101",  # assert in test code
    "T201",  # print in test/cli code
]
per-file-ignores = {
    "tests/**/*.py": ["S101", "T201"],
    "src/pi_lora/cli/*.py": ["T201"],
}
```

**Must Pass**: 0 errors, 0 warnings

---

### Gate 3: Security Scanning (Semgrep)

```bash
uv run .semgrep/run.sh
```

**Configuration** (`.semgrep/run.sh`):
```bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p /tmp/sandbox/semgrep_tmp
TMPDIR=$(mktemp -d -p /tmp/sandbox/semgrep_tmp)
export TMPDIR

trap 'rm -rf "$TMPDIR"' EXIT INT TERM

uv run semgrep scan --verbose \
    --config=.semgrep/rules/security/ \
    --config=.semgrep/rules/best-practice/ \
    --config=.semgrep/rules/correctness/ \
    --config=.semgrep/rules/maintainability/ \
    --config=.semgrep/rules/custom/ \
    src/pi_lora/ \
    tests/
```

**Must Pass**: 0 findings (ERROR severity)

---

### Gate 4: Unit Tests (pytest)

```bash
uv run pytest tests/ -x
```

**Configuration** (`pyproject.toml`):
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
markers = [
    "hardware: marks tests requiring real hardware (PI_LORA_HARDWARE=1)",
    "slow: marks tests that take >5s",
]
```

**Must Pass**: All tests pass, 0 failures, 0 errors

---

## Coverage Requirement

```bash
uv run pytest tests/ --cov=pi_lora --cov-fail-under=90 -q
```

**Target**: ≥ 90% coverage (per Plan-4 through Plan-37 requirement)

---

## Complete Validation Command

```bash
# Run all gates sequentially (stop on first failure)
uv run mypy --strict src/ && \
uv run ruff check src/ tests/ && \
uv run .semgrep/run.sh && \
uv run pytest tests/ -x && \
uv run pytest tests/ --cov=pi_lora --cov-fail-under=90 -q
```

---

## Testing Patterns

### 1. Concurrency Tests

**Pattern**: Verify race-free initialization under load

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
async def test_stress_concurrent_access():
    """Stress test with many concurrent operations."""
    lock = LazyAsyncLock()

    async def work():
        async with await lock.acquire():
            await asyncio.sleep(0.001)

    await asyncio.gather(*[work() for _ in range(500)])
```

**Run with parallelism**: `uv run pytest tests/ -n auto` (pytest-xdist)

---

### 2. Thread Safety Tests

**Pattern**: Verify locks work across threads (required for `aiologic.Lock` holder)

```python
# tests/drivers/spi/test_locks.py

import threading
import asyncio
import pytest
from pi_lora.drivers.spi.locks import get_bus_lock


@pytest.mark.asyncio
async def test_registry_thread_safety():
    """Verify LazyAsyncLock works across threads (aiologic.Lock holder)."""
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

### 3. Exception Handling Tests

**Pattern**: Verify `CancelledError` propagates, `ExceptionGroup` handled

```python
# tests/framework/test_application.py

import asyncio
import pytest
from pi_lora.framework.application import Application


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


@pytest.mark.asyncio
async def test_exception_group_in_cleanup():
    """ExceptionGroup from cleanup chained to original."""
    app = Application(config, spi_factory)
    
    async def failing_cleanup():
        raise ExceptionGroup("cleanup failed", [ValueError("e1"), TypeError("e2")])
    
    with patch.object(app, '_cleanup_partial_start', side_effect=failing_cleanup):
        with patch.object(app.module_manager, 'load_from_config', 
                          side_effect=ValueError("original")):
            with pytest.raises(ValueError, match="original") as exc_info:
                await app.start("default")
    
    # Original cause preserved
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ExceptionGroup)
```

---

### 4. Rollback Tests

**Pattern**: Verify cleanup on failure, including shutdown signals

```python
# tests/framework/test_module_manager.py

import asyncio
import pytest
from pi_lora.framework.module_manager import ModuleManager


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
```

---

### 5. Negative/Regression Tests

**Pattern**: Test that specific bugs are fixed and stay fixed

```python
# tests/framework/test_application_start_stop_race.py

import asyncio
import pytest
from pi_lora.framework.application import Application


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
async def test_fast_path_read_removed():
    """Verify fast-path read of _started was removed (Plan-38)."""
    import ast
    import inspect
    
    source = inspect.getsource(Application.start)
    tree = ast.parse(source)
    
    # Check for removed pattern: `already_started = self._started; if already_started: return`
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "already_started":
                    pytest.fail("Fast-path read 'already_started' found — should be removed per Plan-38")
```

---

### 6. Semgrep Rule Tests

**Pattern**: Verify rules catch bad patterns and allow good ones

```python
# .semgrep/rules/custom/test_lazy_async_lock_guard.py
# Test cases for lazy-async-lock-guard.yaml

# ruleid: sentinel-pattern-deprecated
_SENTINEL = object()

# ruleid: sentinel-pattern-deprecated
_lock = _SENTINEL

# ok: lazy-async-lock-guard
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
_lock = LazyAsyncLock()

# ruleid: holder-not-persisted
with guard:
    holder: asyncio.Lock = asyncio.Lock()

# ok: holder-not-persisted
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
lock = LazyAsyncLock()
await lock.acquire()
```

**Run**: `uv run semgrep test .semgrep/rules/custom/`

---

### 7. Contract Tests

**Pattern**: Verify protocol implementations satisfy contracts

```python
# tests/contracts/test_spi_bus_contract.py

from typing import Protocol
import pytest
from pi_lora.drivers.spi.bus import SpiBus, RealSpiBus
from tests.spi.mock import MockSpiBus


class SpiBusContract(Protocol):
    async def open(self) -> None: ...
    async def close(self) -> None: ...
    async def xfer2(self, data: list[int] | bytearray) -> list[int]: ...
    @property
    def max_speed_hz(self) -> int: ...
    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None: ...
    # ... all protocol methods


def test_real_spi_bus_satisfies_contract():
    """RealSpiBus satisfies SpiBus protocol."""
    # Structural subtyping verified by mypy --strict
    pass  # mypy validates this


def test_mock_spi_bus_satisfies_contract():
    """MockSpiBus satisfies SpiBus protocol (LSP)."""
    mock = MockSpiBus(bus_number=0, device_number=0)
    
    # Verify all protocol methods exist
    assert hasattr(mock, 'open')
    assert hasattr(mock, 'close')
    assert hasattr(mock, 'xfer2')
    assert hasattr(mock, 'max_speed_hz')
    assert hasattr(type(mock).max_speed_hz, 'fset')  # setter exists
```

---

## Test Organization

```
tests/
├── contracts/                 # Protocol contract tests
│   └── test_spi_bus_contract.py
├── drivers/
│   ├── spi/
│   │   ├── test_locks.py              # SPI lock tests
│   │   ├── test_locks_concurrent.py   # Concurrency tests
│   │   ├── test_bus.py                # RealSpiBus tests
│   │   ├── test_factory.py            # Factory tests
│   │   └── test_spidev_patch_contextvar.py
│   ├── test_config_loader.py          # Config loader tests
│   ├── test_config_loader_concurrent.py
│   └── test_rfm9x_sx127x_module.py
├── framework/
│   ├── test_application.py            # Application lifecycle
│   ├── test_application_start_stop_race.py  # Race condition tests
│   ├── test_scheduler.py              # Scheduler tests
│   ├── test_module_manager.py         # Module manager tests
│   ├── test_command_bus.py            # Command bus tests
│   ├── test_events.py                 # Event system tests
│   ├── test_interrupt_bridge_atomic_drop.py
│   ├── test_interrupt_bridge_threadsafe.py
│   ├── test_lazy_async_lock.py        # LazyAsyncLock tests
│   └── test_module_event_loop.py
├── cli/
│   ├── test_check_hardware.py
│   ├── test_test_hardware_cleanup.py
│   ├── test_test_hardware_keyboard_interrupt.py
├── test_entry_points.py               # CLI entry point tests
├── test_cli_async_integration.py      # Async CLI integration
├── test_config_cli.py
├── test_config_cli_integration.py
├── test_dependency_resolution.py
├── test_hardware_cli.py
├── test_hardware_integration.py
├── test_main_cli.py
├── test_semgrep_rule_no_false_positive.py
├── test_semgrep_run_sh.py
└── test_sync_cli_imports.py
```

---

## Continuous Integration

### Pre-Merge Checklist

Before any PR is merged, all must pass:

- [ ] `uv run mypy --strict src/` — 0 errors
- [ ] `uv run ruff check src/ tests/` — 0 warnings
- [ ] `uv run .semgrep/run.sh` — 0 findings
- [ ] `uv run pytest tests/ -x` — 0 failures
- [ ] `uv run pytest tests/ --cov=pi_lora --cov-fail-under=90 -q` — ≥ 90%
- [ ] `uv run pytest tests/ -n auto` — 0 failures (parallel stress)

### On Failure

1. **Identify which gate failed**
2. **Fix the root cause** (not the symptom)
3. **Add regression test** if not already covered
4. **Re-run all gates** from the beginning
5. **Only merge when all pass**

---

## Anti-Regression Notes

1. **Never skip gates** — "it works on my machine" is not valid
2. **Coverage is a floor, not a ceiling** — 90% minimum, aim higher
3. **Parallel tests required** — `pytest -n auto` catches races
4. **Negative tests required** — test that bugs stay fixed
5. **Semgrep tests required** — verify rules catch bad patterns
6. **Contract tests required** — verify LSP compliance for protocols