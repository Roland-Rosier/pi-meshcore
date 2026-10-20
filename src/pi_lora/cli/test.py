"""CLI commands for testing hardware."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any

import typer
from async_typer import AsyncTyper
from rich.console import Console

import pi_lora.cli._logging
from pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from pi_lora.framework.application import Application
from pi_lora.framework.events import (
    EventType,
    ModuleEvent,
    StateChangeEvent,
    is_state_change_event,
)
from pi_lora.framework.exceptions import (
    AssemblyNotFoundError,
    DeviceAttachmentNotFoundError,
)
from pi_lora.types import StateBits

app = AsyncTyper(
    name="test",
    help="Test commands for LoRa hardware.",
)

console = Console()


async def test_hardware_impl(
    assembly_name: str,
    spi: int | None = None,
    ce: int | None = None,
    config_file: str | None = None,
) -> None:
    """Test hardware by transitioning modules to RESET_STATE (async implementation)."""

    custom_path: Path | None = Path(config_file) if config_file else None
    application = Application(config=None)

    try:
        radio_configs = await application.get_assembly_config(
            assembly_name=assembly_name,
            spi_device_id=spi,
            ce_number=ce,
            config_path=custom_path,
        )
    except AssemblyNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None
    except DeviceAttachmentNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1) from None

    if isinstance(radio_configs, RadioInstanceConfig):
        radio_configs = [radio_configs]

    if not radio_configs:
        console.print("[red]Error:[/red] No modules match the given filters")
        raise typer.Exit(code=1)

    # Start application (creates modules, starts event loops, registers scheduler).
    # start() lives inside an outer try whose finally always calls application.stop(),
    # guaranteeing clean shutdown even when start() fails.
    try:
        try:
            await application.start(assembly_name=assembly_name)
        except AssemblyNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from None
        except DeviceAttachmentNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from None
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to start application: {e!r}")
            console.print("[red]Traceback:[/red]")
            traceback.print_exc()
            raise typer.Exit(code=1) from None

        module_manager: Any = application.module_manager
        if module_manager is None:
            console.print("[red]Error:[/red] Module manager is unavailable after start")
            raise typer.Exit(code=1)

        all_modules = module_manager.get_all_modules()
        if all_modules is None:
            all_modules = []

        # Filter to target modules
        target_set = {(cfg.spi_device_id, cfg.ce_number) for cfg in radio_configs}
        modules = [
            m for m in all_modules
            if (m.get_spi_device_id(), m.get_ce_number()) in target_set
        ]

        # Send STATE_CHANGE to RESET_STATE
        reset_event = ModuleEvent[StateChangeEvent](
            event_type=EventType.STATE_CHANGE,
            payload=StateChangeEvent(new_state=StateBits.RESET_STATE, reason="test_hardware_command"),
            source="cli_test_hardware",
        )

        for module in modules:
            await module.event_queue.put(reset_event)

        # Wait for all modules to confirm transition
        for module in modules:
            event = await module.wait_for_event(
                EventType.STATE_CHANGE,
                lambda e: is_state_change_event(e) and e.payload is not None and e.payload.new_state == StateBits.RESET_STATE,
                timeout=5.0,
            )
            if event is None:
                console.print(f"[red]Timeout:[/red] Module SPI:{module.get_spi_device_id()} CE:{module.get_ce_number()} did not reach RESET_STATE")
                raise typer.Exit(code=1)

        console.print("[green]✓[/green] All modules transitioned to RESET_STATE successfully")
    finally:
        # Clean shutdown via Application — always runs, even when start() failed.
        await application.stop()

    raise typer.Exit(code=0)


@app.command("hardware")
async def test_hardware(
    assembly_name: str = typer.Argument(..., help="Assembly name to test"),
    spi: int | None = typer.Option(None, "--spi", help="Filter by SPI device ID"),
    ce: int | None = typer.Option(None, "--ce", help="Filter by CE number"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Custom config file path"),
) -> None:
    """Test hardware by transitioning modules to RESET_STATE."""
    pi_lora.cli._logging.setup_logging()

    await test_hardware_impl(
        assembly_name=assembly_name,
        spi=spi,
        ce=ce,
        config_file=config_file,
    )


if __name__ == "__main__":
    app()
