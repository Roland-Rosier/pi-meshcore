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

"""Integration tests for Application start/stop lifecycle."""

from dataclasses import dataclass

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_config_model import (
    DeviceModuleAttachment,
    ModuleConfig,
    Rfm9xSx127xConfig,
)
from src.pi_lora.framework.application import Application
from src.pi_lora.framework.events import EventType
from tests.spi.mock import MockSpiBusFactory


def _make_test_config() -> Rfm9xSx127xConfig:
    devices = [
        DeviceModuleAttachment(
            device_name="RFM95W",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:WPi6"],
        ),
    ]
    modules = {
        "LoPi4": ModuleConfig(module_name="LoRa Pi 4", devices=devices),
    }
    return Rfm9xSx127xConfig(modules=modules)


@dataclass(frozen=True)
class SimpleCommand:
    action: str = "noop"
    target: tuple[int, int] | None = (0, 0)


class TestApplicationLifecycle:
    """Verify Application.start() / stop() lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_modules(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()
        assert len(app.module_manager.get_all_modules()) == 1
        mod = app.module_manager.get_module(0, 0)
        assert mod is not None
        await app.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()
        await app.stop()
        assert app.scheduler.timer_scheduler._running is False
        assert app.scheduler.idle_pacer._running is False
        assert app.scheduler.interrupt_bridge._running is False

    @pytest.mark.asyncio
    async def test_get_status_returns_snapshot(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()
        status = app.get_status()
        assert "modules" in status
        assert len(status["modules"]) == 1
        mod_info = status["modules"][0]
        assert mod_info["spi_device_id"] == 0
        assert mod_info["ce_number"] == 0
        assert "state" in mod_info
        assert "queue_size" in mod_info
        await app.stop()

    @pytest.mark.asyncio
    async def test_run_blocking_command(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()

        results: list[SimpleCommand] = []

        def handler(cmd: SimpleCommand) -> SimpleCommand:
            results.append(cmd)
            return cmd

        app.command_bus.register_handler(SimpleCommand, handler)
        cmd = SimpleCommand(action="test_cmd")
        result = await app.run_blocking_command(cmd)
        assert result is cmd
        assert len(results) == 1

        await app.stop()

    @pytest.mark.asyncio
    async def test_run_async_command_posts_to_queue(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()

        cmd = SimpleCommand(action="async_cmd")
        await app.run_async_command(cmd)

        mod = app.module_manager.get_module(0, 0)
        assert mod is not None
        assert not mod.event_queue.empty()
        event = await mod.event_queue.get()
        assert event.event_type == EventType.COMMAND

        await app.stop()

    @pytest.mark.asyncio
    async def test_resolve_all_target(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()

        broadcast = SimpleCommand(action="broadcast", target="all")
        await app.run_async_command(broadcast)
        mod = app.module_manager.get_module(0, 0)
        assert mod is not None
        assert not mod.event_queue.empty()
        await app.stop()

    @pytest.mark.asyncio
    async def test_resolve_missing_target_raises(self) -> None:
        config = _make_test_config()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()

        bad_cmd = SimpleCommand(action="bad", target=(99, 99))
        with pytest.raises(ValueError, match="No module for target"):
            await app.run_async_command(bad_cmd)
        await app.stop()


class TestEmptyConfig:
    """Verify Application handles empty config gracefully."""

    @pytest.mark.asyncio
    async def test_start_empty_config(self) -> None:
        config = Rfm9xSx127xConfig()
        app = Application(config=config, spi_factory=MockSpiBusFactory())
        await app.start()
        assert len(app.module_manager.get_all_modules()) == 0
        status = app.get_status()
        assert status["modules"] == []
        await app.stop()
