"""Console entry-point wrappers for the pi_lora CLI scripts.

``async_typer.AsyncTyper`` subclasses ``typer.Typer`` and wraps every async
command body with a synchronous runner, so calling ``app()`` already drives the
event loop internally and returns a Click exit code rather than a bare
coroutine. These wrappers are the targets referenced by ``[project.scripts]``;
they invoke the app (which reads ``sys.argv``) and return the exit code so the
console script exits cleanly without leaving a coroutine un-awaited.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from pi_lora.cli._logging import setup_logging

from .check_hardware import app as check_hardware_app
from .config import app as config_app
from .main import app as main_app
from .test import app as test_app


def _run_app(app_callable: Callable[[], Any]) -> int:
    # P33-1: Corrected docstring to reflect actual AsyncTyper return value (None on success).
    # See plan-33.md Section 2.1.
    """Drive a Typer app and coerce its return / SystemExit into a Click exit code.

    ``app_callable`` returns ``Any`` because ``async_typer.AsyncTyper`` drives the
    event loop internally and returns ``None`` on successful command completion,
    but raises ``SystemExit`` on CLI exits (e.g. ``--help``, invalid args). This
    helper maps every observed outcome onto the canonical three-way mapping:

    SystemExit code mapping (per Click/Typer convention):
        ``None``          → 0  (successful exit, e.g. ``--help``)
        ``int`` (0, 1, 2) → that int (explicit exit code)
        ``str``, ``typer.Exit(code="msg")`` → 1 (failure — non-int codes indicate error)

    Returns the mapped exit code (0, 1, or 2) so the console script exits cleanly.
    """
    try:
        # P33-1: async_typer.AsyncTyper returns None on successful command completion;
        # map None -> exit code 0 explicitly. See plan-33.md Section 2.1.
        result = app_callable()
        if result is None:
            return 0
        return cast(int, result)
    except SystemExit as e:
        # SystemExit code mapping per Click/Typer convention:
        #   None          → 0 (successful exit, e.g., --help)
        #   int (0, 1, 2) → that int (explicit exit code)
        #   str, typer.Exit(code="msg") → 1 (failure — non-int codes indicate error)
        # See plan-31.md Section 2.
        if e.code is None:
            return 0
        elif isinstance(e.code, int):
            return e.code
        else:
            return 1  # String codes (typer.Exit(code="msg"), sys.exit("error")) indicate failure


def pi_lora() -> int:
    """Entry point for the ``pi-lora`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # async_typer.AsyncTyper raises SystemExit on CLI exits (e.g. --help, invalid
    # args) rather than returning an int; _run_app extracts the exit code instead
    # of letting it propagate.
    return _run_app(main_app)


def pi_lora_config() -> int:
    """Entry point for the ``config`` / ``pi-lora-config`` console scripts."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # async_typer.AsyncTyper raises SystemExit on CLI exits (e.g. --help, invalid
    # args) rather than returning an int; _run_app extracts the exit code instead
    # of letting it propagate.
    return _run_app(config_app)


def pi_lora_test() -> int:
    """Entry point for the ``pi-lora-test`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # async_typer.AsyncTyper raises SystemExit on CLI exits (e.g. --help, invalid
    # args) rather than returning an int; _run_app extracts the exit code instead
    # of letting it propagate.
    return _run_app(test_app)


def check_hardware() -> int:
    """Entry point for the ``check-hardware`` console script."""
    # PLAN-23 FIX (Issue 6): setup_logging() moved from cli/main.py module-level
    # (which ran on import and polluted the test environment) to entry-point-local
    # setup here, isolating logging configuration to the actual console script run.
    setup_logging()
    # async_typer.AsyncTyper raises SystemExit on CLI exits (e.g. --help, invalid
    # args) rather than returning an int; _run_app extracts the exit code instead
    # of letting it propagate.
    return _run_app(check_hardware_app)
