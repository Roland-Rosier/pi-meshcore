# CLI Async Patterns (async-typer Migration)

## Overview

The CLI was migrated from `typer` to `async-typer` in Plan-7 to properly support async commands. This document captures the patterns established through Plans 7-38.

---

## Migration Summary

| Before (typer) | After (async-typer) |
|----------------|---------------------|
| `typer.Typer()` | `async_typer.AsyncTyper()` |
| Sync command functions | `async def` command functions |
| `app()` returns `None` | `app()` returns `int` (exit code) |
| `cast(int, app())` | `_run_app(app)` helper |

---

## Entry Point Pattern

### `src/pi_lora/cli/_entry_points.py`

```python
# Copyright 2026 Roland Rosier
# Licensed under the Apache License, Version 2.0

"""Console script entry points — isolated logging, SystemExit handling."""

from typing import cast
import async_typer
from pi_lora.cli._logging import setup_logging
from pi_lora.cli.main import app as main_app
from pi_lora.cli.config import app as config_app
from pi_lora.cli.test import app as test_app
from pi_lora.cli.check_hardware import app as check_hardware_app


def _run_app(app: async_typer.AsyncTyper) -> int:
    """
    Shared helper for running AsyncTyper apps and handling SystemExit.
    
    PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    (which ran on import and polluted the test environment) to entry-point-local
    setup here, isolating logging configuration to the actual console script run.
    
    PLAN-23 FIX (Issue 5): async_typer.AsyncTyper raises SystemExit on CLI exits
    (e.g. --help, invalid args) rather than returning an int. The original
    `cast(int, app())` did NOT catch SystemExit, so it propagated. We keep cast
    to satisfy mypy --strict (app() returns Any) and add try/except SystemExit
    to extract the exit code instead of letting it propagate.
    """
    setup_logging()
    try:
        return cast(int, app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def pi_lora() -> int:
    """Entry point for the ``pi-lora`` console script."""
    return _run_app(main_app)


def pi_lora_config() -> int:
    """Entry point for the ``config`` / ``pi-lora-config`` console scripts."""
    return _run_app(config_app)


def pi_lora_test() -> int:
    """Entry point for the ``pi-lora-test`` console script."""
    return _run_app(test_app)


def check_hardware() -> int:
    """Entry point for the ``check-hardware`` console script."""
    return _run_app(check_hardware_app)
```

---

## Command Definition Pattern

### `src/pi_lora/cli/main.py`

```python
# Copyright 2026 Roland Rosier
# Licensed under the Apache License, Version 2.0

"""Main CLI application."""

import async_typer
from pi_lora.cli._logging import setup_logging
from pi_lora.cli.config import app as config_app
from pi_lora.cli.test import app as test_app

app = async_typer.AsyncTyper(
    name="pi-lora",
    help="MeshCore LoRa Radio Control",
    no_args_is_help=True,
)

# Sub-commands
app.add_typer(config_app, name="config")
app.add_typer(test_app, name="test")


@app.callback()
def main_callback() -> None:
    """Root callback — no module-level setup_logging() call."""
    # PLAN-23 FIX: setup_logging() moved to _entry_points.py
    # This prevents side effects on import during testing
    pass
```

### `src/pi_lora/cli/test.py`

```python
# Copyright 2026 Roland Rosier
# Licensed under the Apache License, Version 2.0

"""Test hardware CLI commands."""

import async_typer
from pi_lora.framework.application import Application

app = async_typer.AsyncTyper(name="test", help="Hardware test commands")


@app.command()
async def test_hardware(
    assembly: str = async_typer.Option("default", help="Assembly name"),
) -> None:
    """Test hardware by starting application and running detection."""
    app_instance = Application(config, spi_factory)
    try:
        await app_instance.start(assembly)
        # ... run tests ...
    finally:
        await app_instance.stop()
```

---

## Key Patterns

### Pattern 1: Shared Entry Point Helper

```python
# Single helper handles ALL entry points
def _run_app(app: async_typer.AsyncTyper) -> int:
    setup_logging()
    try:
        return cast(int, app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
```

**Why**: 
- DRY — 4 entry points, 1 helper
- Isolates `setup_logging()` to actual script execution (not import)
- Handles `SystemExit` from `--help`, invalid args, etc.

---

### Pattern 2: No Module-Level `setup_logging()`

```python
# WRONG — runs on import, pollutes test environment
setup_logging()
app = async_typer.AsyncTyper()

# CORRECT — only in entry point
def _run_app(app):
    setup_logging()
    return cast(int, app())
```

**Why**: 
- Module-level calls run when `import pi_lora.cli.main` happens
- Test imports pollute logging configuration
- Entry-point-local ensures clean isolation

---

### Pattern 3: Async Commands with Proper Cleanup

```python
@app.command()
async def test_hardware(assembly: str = "default") -> None:
    app_instance = Application(config, spi_factory)
    try:
        await app_instance.start(assembly)
        # ... test operations ...
    finally:
        await app_instance.stop()  # ALWAYS cleanup
```

**Why**: 
- `try/finally` guarantees `stop()` called even on error
- `async def` allows `await` on async operations
- No `return` value — exit code handled by `_run_app`

---

### Pattern 4: SystemExit Handling

```python
try:
    return cast(int, app())
except SystemExit as e:
    return e.code if isinstance(e.code, int) else 1
```

**Why**: 
- `async_typer` raises `SystemExit` for `--help`, `--version`, invalid args
- `cast(int, app())` alone lets `SystemExit` propagate (crashes)
- Extract exit code cleanly

---

## Logging Pattern

### `src/pi_lora/cli/_logging.py`

```python
# Copyright 2026 Roland Rosier
# Licensed under the Apache License, Version 2.0

"""Centralized logging setup for CLI entry points."""

import logging
import os
import warnings

# Module-level logger (Plan-14 finding 8.14)
logger = logging.getLogger(__name__)

_INITIALIZED = False


def setup_logging() -> None:
    """Configure logging — idempotent, safe to call multiple times."""
    global _INITIALIZED
    
    if _INITIALIZED:
        return
    
    _INITIALIZED = True
    
    level = os.getenv("PI_LORA_LOG_LEVEL", "INFO").upper()
    
    # Validate log level
    if not hasattr(logging, level):
        warnings.warn(
            f"Invalid log level '{level}', defaulting to INFO",
            UserWarning,
            stacklevel=2,
        )
        level = "INFO"
    
    # Intentional: ensure consistent log format across all CLI entry points
    # force=True removes ALL existing handlers from root logger before configuring
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| `setup_logging()` at module level | Pollutes test imports | Move to `_run_app()` |
| Duplicate `setup_logging()` calls | Redundant, warning spam | Use `_INITIALIZED` guard |
| `except Exception:` in commands | Swallows `SystemExit` | Let `SystemExit` propagate to `_run_app` |
| Sync `typer.Typer` for async commands | `RuntimeWarning: coroutine never awaited` | Use `async_typer.AsyncTyper` |
| `cast(int, app())` without try/except | `SystemExit` crashes process | Wrap in `_run_app()` |

---

## Validation Rules

### Semgrep Rules

```yaml
# .semgrep/rules/custom/cli_async_guard.yaml

rules:
  - id: cli-module-level-logging
    pattern: |
      setup_logging()
      ...
      app = async_typer.AsyncTyper()
    message: "Module-level setup_logging() — move to entry point _run_app()"
    severity: ERROR

  - id: cli-sync-typer-for-async
    pattern: |
      import typer
      app = typer.Typer()
      ...
      @app.command()
      async def $CMD(...):
    message: "Sync Typer with async command — use async_typer.AsyncTyper"
    severity: ERROR

  - id: cli-cast-without-systemexit
    pattern: |
      cast(int, $APP())
    message: "cast(int, app()) without SystemExit handling — use _run_app()"
    severity: ERROR
```

### Must-Pass Tests

```bash
# CLI integration tests
uv run pytest tests/test_cli_async_integration.py -v
uv run pytest tests/test_entry_points.py -v
uv run pytest tests/test_main_cli.py -v
uv run pytest tests/test_config_cli.py -v
uv run pytest tests/test_test_cli.py -v
```

---

## Related Files

- `src/pi_lora/cli/_entry_points.py` — Entry points
- `src/pi_lora/cli/_logging.py` — Logging setup
- `src/pi_lora/cli/main.py` — Main CLI
- `src/pi_lora/cli/config.py` — Config commands
- `src/pi_lora/cli/test.py` — Test commands
- `src/pi_lora/cli/check_hardware.py` — Hardware check
- `tests/test_entry_points.py` — Entry point tests
- `tests/test_cli_async_integration.py` — Async CLI integration
- `pyproject.toml` — `async-typer` dependency

---

## Anti-Regression Notes

1. **Never re-add module-level `setup_logging()`** — Plan-23 fixed this
2. **Always use `_run_app()`** for new entry points
3. **Use `async_typer.AsyncTyper`** for any new CLI app
4. **Commands must be `async def`** — sync commands in async app cause warnings
5. **`try/finally` for `Application` lifecycle** — guarantees cleanup