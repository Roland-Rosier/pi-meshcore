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

import typer

from pi_lora.drivers.lora_detection import LoRaModuleDetector


def _normalise_module_type(value: str | None) -> str | None:
    """Typer callback to normalise module type input to canonical form.

    Accepts case-insensitive aliases:
      - rfm95w, sx1276  → "rfm95w"
      - rfm98w, sx1278  → "rfm98w"
      - none            → "none"
    """
    if value is None:
        return None
    canonical = value.strip().lower()
    mapping: dict[str, str] = {
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


app = typer.Typer(
    name="check-hardware",
    help="Check LoRa hardware modules on the MeshCore Pi4 Hat.",
)


@app.command("detect-modules")
def detect_modules(
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
) -> None:
    """Scan hardware and optionally validate against an expected configuration."""

    detector = LoRaModuleDetector(ce_pins=[0, 1])

    results = detector.detect_modules()

    print("\nHardware Detection Results:")
    for result in results:
        print(f"  ✅ {result}")

    if ce0 is not None or ce1 is not None:
        from pi_lora.drivers.lora_detection import LoRaModuleConfig, ValidationResult

        config = LoRaModuleConfig(
            ce0_expected_module_type=ce0,  # Already normalised by callback
            ce1_expected_module_type=ce1,  # Already normalised by callback
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




