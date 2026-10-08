"""Main CLI entry point for pi_lora package."""

import logging
import os

import typer


def setup_logging() -> None:
    """Configure root logger using PI_LORA_LOG_LEVEL environment variable.

    Safe to call multiple times — basicConfig is idempotent after first call.
    """
    log_level = os.environ.get("PI_LORA_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


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
