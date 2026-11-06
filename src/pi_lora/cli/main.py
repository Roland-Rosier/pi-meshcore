"""Main CLI entry point for pi_lora package."""

from __future__ import annotations

from async_typer import AsyncTyper

# PLAN-23 FIX (Issue 6): setup_logging() was removed from this module-level scope.
# Calling it on import ran on every importer (tests, other modules) and polluted
# the test environment with logging configuration. Logging setup is now isolated
# to entry-point-local setup in cli/_entry_points.py, so it only runs on the
# actual console script run.
from .check_hardware import app as check_hardware_app
from .config import app as config_app
from .test import app as test_app

app = AsyncTyper(
    name="pi_lora",
    help="MeshCore Pi LoRa CLI — hardware test, config, and diagnostics",
    no_args_is_help=True,
)

app.add_typer(check_hardware_app, name="check-hardware")
app.add_typer(config_app, name="config")
app.add_typer(test_app, name="test")
