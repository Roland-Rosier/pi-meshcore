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

from .check_hardware import app as check_hardware_app
from .config import app as config_app
from .main import app as main_app
from .test import app as test_app


def pi_lora() -> int:
    """Entry point for the ``pi-lora`` console script."""
    return cast(int, main_app())


def pi_lora_config() -> int:
    """Entry point for the ``config`` / ``pi-lora-config`` console scripts."""
    return cast(int, config_app())


def pi_lora_test() -> int:
    """Entry point for the ``pi-lora-test`` console script."""
    return cast(int, test_app())


def check_hardware() -> int:
    """Entry point for the ``check-hardware`` console script."""
    return cast(int, check_hardware_app())
