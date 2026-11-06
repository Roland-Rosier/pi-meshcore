"""Console entry-point wrappers for the pi_lora CLI scripts.

``async_typer.AsyncTyper`` subclasses ``typer.Typer`` and wraps every async
command body with a synchronous runner, so calling ``app()`` already drives the
event loop internally and returns a Click exit code rather than a bare
coroutine. These wrappers are the targets referenced by ``[project.scripts]``;
they invoke the app (which reads ``sys.argv``) and return the exit code so the
console script exits cleanly without leaving a coroutine un-awaited.
"""

from __future__ import annotations

from typing import cast

from pi_lora.cli._logging import setup_logging

from .check_hardware import app as check_hardware_app
from .config import app as config_app
from .main import app as main_app
from .test import app as test_app


def pi_lora() -> int:
    """Entry point for the ``pi-lora`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # PLAN-23 FIX (Issue 5): async_typer.AsyncTyper raises SystemExit on CLI exits
    # (e.g. --help, invalid args) rather than returning an int. The original
    # `cast(int, app())` did NOT catch SystemExit, so it propagated. We keep cast
    # to satisfy mypy --strict (app() returns Any) and add try/except SystemExit
    # to extract the exit code instead of letting it propagate.
    try:
        return cast(int, main_app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def pi_lora_config() -> int:
    """Entry point for the ``config`` / ``pi-lora-config`` console scripts."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # PLAN-23 FIX (Issue 5): async_typer.AsyncTyper raises SystemExit on CLI exits
    # (e.g. --help, invalid args) rather than returning an int. The original
    # `cast(int, app())` did NOT catch SystemExit, so it propagated. We keep cast
    # to satisfy mypy --strict (app() returns Any) and add try/except SystemExit
    # to extract the exit code instead of letting it propagate.
    try:
        return cast(int, config_app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def pi_lora_test() -> int:
    """Entry point for the ``pi-lora-test`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # PLAN-23 FIX (Issue 5): async_typer.AsyncTyper raises SystemExit on CLI exits
    # (e.g. --help, invalid args) rather than returning an int. The original
    # `cast(int, app())` did NOT catch SystemExit, so it propagated. We keep cast
    # to satisfy mypy --strict (app() returns Any) and add try/except SystemExit
    # to extract the exit code instead of letting it propagate.
    try:
        return cast(int, test_app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1


def check_hardware() -> int:
    """Entry point for the ``check-hardware`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # PLAN-23 FIX (Issue 5): async_typer.AsyncTyper raises SystemExit on CLI exits
    # (e.g. --help, invalid args) rather than returning an int. The original
    # `cast(int, app())` did NOT catch SystemExit, so it propagated. We keep cast
    # to satisfy mypy --strict (app() returns Any) and add try/except SystemExit
    # to extract the exit code instead of letting it propagate.
    try:
        return cast(int, check_hardware_app())
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 1
