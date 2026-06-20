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
import sys
import os

from enum import Enum

import typer


# Add project root to Python path if not already present
current_dir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))

if project_root not in sys.path:
    sys.path.append(project_root)
    print(f"✅ Added project root to sys.path: {project_root}")

from src.drivers.lora_detection import LoRaModuleDetector


class ModuleType(str, Enum):
    """Allowed LoRa module types for CE slot validation."""
    RFM95W = "rfm95w"
    RFM98W = "rfm98w"
    NONE = "none"


app = typer.Typer(
    name="check-hardware",
    help="Check LoRa hardware modules on the MeshCore Pi4 Hat.",
)


@app.command("detect-modules")
def detect_modules(
    ce0: ModuleType | None = typer.Option(
        None,
        "--ce0",
        help="Expected module type on CE0 slot (rfm95w, rfm98w, or none).",
    ),
    ce1: ModuleType | None = typer.Option(
        None,
        "--ce1",
        help="Expected module type on CE1 slot (rfm95w, rfm98w, or none).",
    ),
) -> None:
    """Scan hardware and optionally validate against an expected configuration."""

    detector = LoRaModuleDetector(ce_pins=[0, 1])

    results = detector.detect_modules()

    print("\nHardware Detection Results:")
    for result in results:
        print(f"  ✅ {result}")

    if ce0 is not None or ce1 is not None:
        from src.drivers.lora_detection import LoRaModuleConfig, ValidationResult

        config = LoRaModuleConfig(
            ce0_expected_module_type=ce0.value if ce0 else None,
            ce1_expected_module_type=ce1.value if ce1 else None,
        )
        validation_results: list[ValidationReport] = detector.validate_config(config)  # type: ignore[name-defined]

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
            raise typer.Exit(code=1)


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """MeshCore hardware check utility — show help when invoked without subcommand."""
    if ctx.invoked_subcommand is None:
        typer.echo("Usage: check-hardware [command]")
        typer.echo("Available commands:")
        typer.echo("  detect-modules   Check for LoRa modules")
        raise typer.Exit(code=0)


if __name__ == "__main__":
    app()