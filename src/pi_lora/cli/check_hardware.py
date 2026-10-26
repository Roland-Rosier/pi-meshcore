# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Literal, cast

import typer
from async_typer import AsyncTyper

import pi_lora.cli._logging
from pi_lora.drivers.lora_detection import (
    LoRaModuleConfig,
    LoRaModuleDetector,
    ValidationResult,
)


def _normalise_module_type(value: str | None) -> Literal["rfm95w", "rfm98w", "none"] | None:
    """Typer callback to normalise module type input to canonical form.

    Accepts case-insensitive aliases:
      - rfm95w, sx1276  → "rfm95w"
      - rfm98w, sx1278  → "rfm98w"
      - none            → "none"
    """
    if value is None:
        return None
    canonical = value.strip().lower()
    mapping: dict[str, Literal["rfm95w", "rfm98w", "none"]] = {
        "rfm95w": "rfm95w",
        "sx1276": "rfm95w",
        "rfm98w": "rfm98w",
        "sx1278": "rfm98w",
        "none":   "none",
    }
    if canonical not in mapping:
        raise typer.BadParameter(
            f"Invalid module type '{value}'. Expected one of: rfm95w/sx1276, rfm98w/sx1278, none."
        )
    return mapping[canonical]


# FIX CR-7: migrated from a sync ``typer.Typer`` to ``async_typer.AsyncTyper``.
#
# With the sync Typer, ``typer.BadParameter`` raised inside the ``--ce0``/``--ce1``
# callback aborted option parsing, but ``_entry_points.check_hardware()`` performed
# ``cast(int, app())`` -- a sync Typer returns ``None`` on error, so the wrapper
# yielded exit code ``0`` and rejected input was silently accepted.
#
# ``async_typer.AsyncTyper`` subclasses ``typer.Typer`` and drives each async command
# body through a synchronous runner, so ``app()`` returns a genuine Click exit code
# (``1`` on rejected input). The rejected alternative -- forcing exit code ``1`` via a
# ``cast`` hack in the wrapper -- would not change the underlying sync Typer behaviour
# and would leave this CLI inconsistent with the other async entry points.
app = AsyncTyper(
    name="check-hardware",
    help="Check LoRa hardware modules on the MeshCore Pi4 Hat.",
)


@app.command("detect-modules")
async def detect_modules(
    # ``async`` is retained for AsyncTyper API consistency (the ``app`` is an
    # ``async_typer.AsyncTyper``); no ``await`` is required and behaviour is unchanged.
    ce0: str | None = typer.Option(
        None,
        "--ce0",
        callback=_normalise_module_type,
        help="Expected module type on CE0 slot (rfm95w/sx1276, rfm98w/sx1278, or none).",
    ),
    ce1: str | None = typer.Option(
        None,
        "--ce1",
        callback=_normalise_module_type,
        help="Expected module type on CE1 slot (rfm95w/sx1276, rfm98w/sx1278, or none).",
    ),
    extended: bool = typer.Option(
        False,
        "--extended",
        help="Run extended detection to distinguish RFM95W from RFM98W via PLL lock test.",
    ),
) -> None:
    """Scan hardware and optionally validate against an expected configuration."""
    pi_lora.cli._logging.setup_logging()

    detector = LoRaModuleDetector(ce_pins=[0, 1])

    results = detector.detect_modules(extended=extended)

    print("\nHardware Detection Results:")
    for result in results:
        print(f"  ✅ {result}")

    if ce0 is not None or ce1 is not None:
        config = LoRaModuleConfig(
            ce0_expected_module_type=cast(Literal["rfm95w", "rfm98w", "none"], ce0) if ce0 is not None else None,  # Already normalised by callback
            ce1_expected_module_type=cast(Literal["rfm95w", "rfm98w", "none"], ce1) if ce1 is not None else None,  # Already normalised by callback
        )

        validation_results: list[ValidationResult] = detector.validate_config(config)

        print("\nConfiguration Validation Results:")
        all_passed = True
        for vr in validation_results:
            status = "✅ PASS" if vr.passed else "❌ FAIL"
            print(f"  {status} CE{vr.ce_pin}: {vr.message}")
            if not vr.passed:
                all_passed = False

        if all_passed:
            print("\n✅ Configuration is valid.")
        else:
            print("❌ Configuration validation failed.")
            raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
async def main_callback(ctx: typer.Context) -> None:
    """MeshCore hardware check utility — show help when invoked without subcommand."""
    # ``async`` is retained for AsyncTyper API consistency (the ``app`` is an
    # ``async_typer.AsyncTyper``); no ``await`` is required and behaviour is unchanged.
    pi_lora.cli._logging.setup_logging()

    if ctx.invoked_subcommand is None:
        typer.echo("Usage: check-hardware [command]")
        typer.echo("Available commands:")
        typer.echo("  detect-modules   Check for LoRa modules")
        raise typer.Exit(code=0)


if __name__ == "__main__":
    app()




