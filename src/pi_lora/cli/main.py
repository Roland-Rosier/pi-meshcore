"""Main CLI entry point for pi_lora package."""

from __future__ import annotations

import typer

from pi_lora.cli._logging import setup_logging

setup_logging()

from .check_hardware import app as check_hardware_app
from .config import app as config_app
from .test import app as test_app

app = typer.Typer(
    name="pi_lora",
    help="MeshCore Pi LoRa CLI — hardware test, config, and diagnostics",
    no_args_is_help=True,
)

app.add_typer(check_hardware_app, name="check-hardware")
app.add_typer(config_app, name="config")
app.add_typer(test_app, name="test")
