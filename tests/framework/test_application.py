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
from src.pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from src.pi_lora.framework.application import Application
from src.pi_lora.framework.events import EventType
from tests.spi.mock import MockSpiBusFactory


def _make_test_radio_configs() -> list[RadioInstanceConfig]:
    """Build a minimal test config with one radio instance."""
    return [
        RadioInstanceConfig(
            module_name="LoPi4",
            spi_device_id=0,
            ce_number=0,
            device_name="RFM95W",
            min_radio_freq_hz=800000,
            max_radio_freq_hz=900000,
            osc_freq_hz=32_000_000,
            family_name="RFM9X",
            test_invalid_frequencies_hz=(999999,),
            dio_gpio_mappings=("DIO0:WPi6",),
            antenna_type=None,
            antenna_gain_db=None,
        ),
    ]


@dataclass(frozen=True)
class SimpleCommand:
    action: str = "noop"
    target: tuple[int, int] | None = (0, 0)


class TestApplicationLifecycle:
    """Verify Application.start() / stop() lifecycle."""

    @pytest.mark.asyncio
    async def test_start_loads_from_assembly_config(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        assert len(app.module_manager.get_all_modules()) >= 1
        for mod in app.module_manager.get_all_modules():
            assert mod.spi_bus is not None
        await app.stop()

    @pytest.mark.asyncio
    async def test_start_creates_modules(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        assert len(app.module_manager.get_all_modules()) >= 1
        mod = app.module_manager.get_module(0, 0)
        assert mod is not None
        await app.stop()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        await app.stop()
        assert app.scheduler.timer_scheduler._running is False
        assert app.scheduler.idle_pacer._running is False
        assert app.scheduler.interrupt_bridge._running is False

    @pytest.mark.asyncio
    async def test_get_status_returns_snapshot(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        status = app.get_status()
        assert "modules" in status
        assert len(status["modules"]) >= 1
        mod_infos = status["modules"]
        ce0_found = any(m["ce_number"] == 0 for m in mod_infos)
        assert ce0_found is True
        spi0_found = any(m["spi_device_id"] == 0 for m in mod_infos)
        assert spi0_found is True
        for mod_info in mod_infos:
            assert "state" in mod_info
            assert "queue_size" in mod_info
        await app.stop()

    @pytest.mark.asyncio
    async def test_run_blocking_command(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
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
        app = Application(config=None, spi_factory=MockSpiBusFactory())
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
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()

        broadcast = SimpleCommand(action="broadcast", target="all")
        await app.run_async_command(broadcast)
        all_modules = app.module_manager.get_all_modules()
        mod = all_modules[0] if all_modules else None
        assert mod is not None
        assert not mod.event_queue.empty()
        await app.stop()

    @pytest.mark.asyncio
    async def test_resolve_missing_target_raises(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()

        bad_cmd = SimpleCommand(action="bad", target=(99, 99))
        with pytest.raises(ValueError, match="No module for target"):
            await app.run_async_command(bad_cmd)
        await app.stop()


class TestEmptyConfig:
    """Verify Application handles empty config gracefully."""

    @pytest.mark.asyncio
    async def test_start_empty_config(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        status = app.get_status()
        assert "modules" in status
        await app.stop()


class TestListAssemblies:
    """Tests for Application.list_assemblies()."""

    def test_list_assemblies_basic(self) -> None:
        """Verify list_assemblies returns assembly names."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = application.list_assemblies(verbose=False)
        assert len(assemblies) >= 1
        names = [a["assembly_name"] for a in assemblies]
        assert "default" in names

    def test_list_assemblies_verbose(self) -> None:
        """Verify list_assemblies verbose includes module_name and device_count."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = application.list_assemblies(verbose=True)
        assert len(assemblies) >= 1
        for a in assemblies:
            assert "assembly_name" in a
            assert "module_name" in a
            assert "device_count" in a

    def test_list_assemblies_json_format(self) -> None:
        """Verify list_assemblies returns dict format suitable for JSON."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = application.list_assemblies(verbose=False)
        assert isinstance(assemblies, list)
        for a in assemblies:
            assert isinstance(a, dict)


class TestGetAssemblyConfig:
    """Tests for Application.get_assembly_config()."""

    def test_get_assembly_config_all_devices(self) -> None:
        """Verify get_assembly_config returns config for default assembly."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = application.get_assembly_config("default")
        assert result is not None

    def test_get_assembly_config_single_device(self) -> None:
        """Verify get_assembly_config returns config for a specific SPI/CE slot."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = application.get_assembly_config("default", spi_device_id=0, ce_number=0)
        assert result is not None

    def test_get_assembly_config_not_found(self) -> None:
        """Verify get_assembly_config raises AssemblyNotFoundError for missing assembly."""
        from src.pi_lora.framework.exceptions import AssemblyNotFoundError

        application = Application(config=None)
        application._config = None
        application._config_path = None

        with pytest.raises(AssemblyNotFoundError):
            application.get_assembly_config("nonexistent")

    def test_get_assembly_config_device_not_found(self) -> None:
        """Verify get_assembly_config raises DeviceAttachmentNotFoundError for invalid SPI/CE."""
        from unittest.mock import MagicMock, patch

        from src.pi_lora.framework.exceptions import DeviceAttachmentNotFoundError

        application = Application(config=None)
        application._config = None
        application._config_path = None

        mock_radio_config = MagicMock()
        mock_radio_config.spi_device_id = 0
        mock_radio_config.ce_number = 0

        with patch(
            "src.pi_lora.framework.application.create_radio_instance",
            return_value=mock_radio_config,
        ), pytest.raises(DeviceAttachmentNotFoundError):
            application.get_assembly_config("default", spi_device_id=99, ce_number=99)

    def test_get_assembly_config_validation_error_propagates(self) -> None:
        """Verify get_assembly_config returns config without raising ConfigConsistencyError."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = application.get_assembly_config("default")
        assert result is not None


class TestConfigLoading:
    """Tests for config loading behavior."""

    def test_lazy_load(self) -> None:
        """Verify config is only loaded on first query."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assert application._config is None
        assemblies = application.list_assemblies()
        assert len(assemblies) >= 1
        assert application._config is not None

    def test_reload_config(self) -> None:
        """Verify reload_config forces reload."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        application.list_assemblies()
        reloaded = application.reload_config()
        assert reloaded is not None


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
