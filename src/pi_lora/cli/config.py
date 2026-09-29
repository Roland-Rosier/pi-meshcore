# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""CLI commands for querying radio instance configuration."""

from __future__ import annotations

import json
import sys
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from pi_lora.framework.application import Application
from pi_lora.framework.exceptions import (
    AssemblyNotFoundError,
    DeviceAttachmentNotFoundError,
)

app = typer.Typer(
    name="config",
    help="Query radio instance configuration.",
)


def _format_config_text(config: RadioInstanceConfig) -> str:
    """Return human-readable key-value format for a RadioInstanceConfig."""
    lines: list[str] = []
    lines.append(f"  Module:      {config.module_name}")
    lines.append(f"  Device:      SPI:{config.spi_device_id} CE:{config.ce_number}")
    lines.append(f"  Device Name: {config.device_name}")
    lines.append(f"  Freq Range:  {config.min_radio_freq_hz}-{config.max_radio_freq_hz} Hz")
    if config.osc_freq_hz is not None:
        lines.append(f"  OSC Freq:    {config.osc_freq_hz} Hz")
    else:
        lines.append("  OSC Freq:    N/A")
    lines.append(f"  Family:      {config.family_name}")
    if config.test_invalid_frequencies_hz:
        lines.append(f"  Test Invalid: {', '.join(str(f) for f in config.test_invalid_frequencies_hz)} Hz")
    else:
        lines.append("  Test Invalid: none")
    if config.dio_gpio_mappings:
        lines.append(f"  Mappings:    {', '.join(config.dio_gpio_mappings)}")
    else:
        lines.append("  Mappings:    N/A")
    if config.antenna_type is not None:
        lines.append(f"  Antenna:     {config.antenna_type} (gain: {config.antenna_gain_db} dB)")
    else:
        lines.append("  Antenna:     N/A")
    return '\n'.join(lines)


def _format_config_json(config: RadioInstanceConfig | list[RadioInstanceConfig]) -> str:
    """Return JSON serialization of a RadioInstanceConfig or list thereof."""
    def _serialize(obj: Any) -> Any:
        if isinstance(obj, RadioInstanceConfig):
            return {
                "module_name": obj.module_name,
                "spi_device_id": obj.spi_device_id,
                "ce_number": obj.ce_number,
                "device_name": obj.device_name,
                "min_radio_freq_hz": obj.min_radio_freq_hz,
                "max_radio_freq_hz": obj.max_radio_freq_hz,
                "osc_freq_hz": obj.osc_freq_hz,
                "family_name": obj.family_name,
                "test_invalid_frequencies_hz": list(obj.test_invalid_frequencies_hz),
                "dio_gpio_mappings": list(obj.dio_gpio_mappings),
                "antenna_type": obj.antenna_type,
                "antenna_gain_db": obj.antenna_gain_db,
            }
        if hasattr(obj, '__dataclass_fields__'):
            return {
                field: _serialize(getattr(obj, field))
                for field in obj.__dataclass_fields__
            }
        if isinstance(obj, list | tuple):
            return [_serialize(item) for item in obj]
        return obj

    return json.dumps(_serialize(config), indent=2)


@app.command("list-assemblies")
def list_assemblies(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show module name and device count"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Custom config file path"),
) -> None:
    """List available assemblies."""

    application = Application(config=None)

    assemblies = application.list_assemblies(verbose=verbose)

    if json_output:
        typer.echo(json.dumps(assemblies, indent=2))
    elif verbose:
        console = Console()
        table = Table(title="Available Assemblies")
        table.add_column("Assembly Name", style="dim")
        table.add_column("Module", style="dim")
        table.add_column("Devices", style="dim")
        for a in assemblies:
            table.add_row(
                a["assembly_name"],
                a.get("module_name", ""),
                str(a.get("device_count", "")),
            )
        console.print(table)
    else:
        for a in assemblies:
            typer.echo(f"  {a['assembly_name']}")


@app.command("show-config")
def show_config(
    assembly_name: str = typer.Argument(..., help="Assembly name to query"),
    spi: int | None = typer.Option(None, "--spi", help="SPI device ID (e.g., 0)"),
    ce: int | None = typer.Option(None, "--ce", help="CE number (e.g., 0 or 1)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Custom config file path"),
) -> None:
    """Show configuration for an assembly."""
    from pathlib import Path

    custom_path: Path | None = Path(config_file) if config_file else None

    application = Application(config=None)

    try:
        result = application.get_assembly_config(
            assembly_name=assembly_name,
            spi_device_id=spi,
            ce_number=ce,
            config_path=custom_path,
        )
    except AssemblyNotFoundError as e:
        typer.echo(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1) from None
    except DeviceAttachmentNotFoundError as e:
        typer.echo(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1) from None

    if json_output:
        typer.echo(_format_config_json(result))
    else:
        if isinstance(result, list):
            for cfg in result:
                typer.echo(_format_config_text(cfg))
                typer.echo()
        else:
            typer.echo(_format_config_text(result))


if __name__ == "__main__":
    app()
