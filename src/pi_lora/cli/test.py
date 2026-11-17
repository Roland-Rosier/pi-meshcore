"""CLI commands for testing hardware."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from async_typer import AsyncTyper
from rich.console import Console

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
    application = Application()

    # CR-33.4 / Plan-34: the whole body is wrapped in a single try whose finally
    # always calls application.stop(), so clean shutdown runs on every path -- the
    # AssemblyNotFoundError/DeviceAttachmentNotFoundError catch (which raises
    # typer.Exit before start()) and any exception raised by start(). The narrow
    # inner try/except only catches the two legitimate "not-found" errors;
    # KeyboardInterrupt/SystemExit/GeneratorExit (PEP 3134) and any Exception from
    # start() propagate through the finally uncaught. See code_review-33.1.json.
    try:
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
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(code=1) from None

        if isinstance(radio_configs, RadioInstanceConfig):
            radio_configs = [radio_configs]

        if not radio_configs:
            console.print("[red]Error:[/red] No modules match the given filters")
            raise typer.Exit(code=1)

        # Start application (creates modules, starts event loops, registers scheduler).
        # start() is followed by a finally that always calls application.stop(),
        # guaranteeing clean shutdown even when start() fails.
        await application.start(assembly_name=assembly_name)

        module_manager: Any = application.module_manager
        if module_manager is None:
            console.print("[red]Error:[/red] Module manager is unavailable after start")
            raise typer.Exit(code=1)

        all_modules = module_manager.get_all_modules()

        # Filter to target modules
        target_set = {(cfg.spi_device_id, cfg.ce_number) for cfg in radio_configs}
        modules = [
            m for m in all_modules
            if (m.get_spi_device_id(), m.get_ce_number()) in target_set
        ]

        # CR-34.3-1 / Plan-35 FIX: empty modules list means no targets matched the
        # SPI/CE filter. This is a user error (wrong assembly name or filter), not
        # success. Exit with error instead of silently succeeding. See code_review-34.3.json.
        if not modules:
            console.print("[red]Error:[/red] No modules match the given SPI/CE filters")
            raise typer.Exit(code=1)

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
        raise typer.Exit(code=0)
    finally:
        # Clean shutdown via Application -- the finally always runs, regardless of
        # the exception type. ``finally`` (not a redundant ``except Exception`` catch)
        # lets ``KeyboardInterrupt``/``SystemExit``/``GeneratorExit`` (PEP 3134
        # control-flow signals) propagate to the interpreter instead of being
        # suppressed; ``application.stop()`` still executes here.
        await application.stop()


@app.command("hardware")
async def test_hardware(
    assembly_name: str = typer.Argument(..., help="Assembly name to test"),
    spi: int | None = typer.Option(None, "--spi", help="Filter by SPI device ID"),
    ce: int | None = typer.Option(None, "--ce", help="Filter by CE number"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Custom config file path"),
) -> None:
    """Test hardware by transitioning modules to RESET_STATE."""

    await test_hardware_impl(
        assembly_name=assembly_name,
        spi=spi,
        ce=ce,
        config_file=config_file,
    )


if __name__ == "__main__":
    # CR-33.4 / Plan-34: ``app`` is an AsyncTyper that drives its own event loop and raises
    # SystemExit internally. Calling ``app()`` bare defers coroutine handling to typer; the
    # canonical ``_run_app`` helper (used by all 4 console entry points in
    # ``src/pi_lora/cli/_entry_points.py``) coerces the SystemExit/None return into a
    # consistent Click exit code. See code_review-33.1.json.
    from pi_lora.cli._entry_points import _run_app
    raise SystemExit(_run_app(app))
