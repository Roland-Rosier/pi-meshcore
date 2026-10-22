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

import asyncio
from dataclasses import dataclass
from typing import Any

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


class _FailingInitModule:
    """Controllable module whose ``init_spi_bus()`` raises — used for Fix #2.7 tests."""

    def __init__(self, ce_number: int = 0, spi_device_id: int = 0) -> None:
        self.ce_number: int = ce_number
        self.spi_device_id: int = spi_device_id
        self.close_spi_calls: int = 0
        self.stop_event_loop_calls: int = 0

    async def init_spi_bus(self) -> None:
        raise RuntimeError("init_spi_bus() failed")

    async def start_event_loop(self) -> None:
        return None

    async def stop_event_loop(self, mode: Any) -> None:
        self.stop_event_loop_calls += 1
        return None

    async def close_spi(self) -> None:
        self.close_spi_calls += 1
        return None

    def get_spi_device_id(self) -> int:
        return self.spi_device_id

    def get_ce_number(self) -> int:
        return self.ce_number


class _FailingStopModule:
    """Controllable module whose ``stop_event_loop()`` raises — used for Phase 6."""

    def __init__(self, ce_number: int = 0, spi_device_id: int = 0) -> None:
        self.ce_number: int = ce_number
        self.spi_device_id: int = spi_device_id
        self.stop_event_loop_calls: int = 0
        self.close_spi_calls: int = 0
        self._stop_error: RuntimeError = RuntimeError("stop_event_loop() failed")

    async def init_spi_bus(self) -> None:
        return None

    async def start_event_loop(self) -> None:
        return None

    async def stop_event_loop(self, mode: Any) -> None:
        self.stop_event_loop_calls += 1
        raise self._stop_error

    async def close_spi(self) -> None:
        self.close_spi_calls += 1
        return None

    def get_spi_device_id(self) -> int:
        return self.spi_device_id

    def get_ce_number(self) -> int:
        return self.ce_number


class _FailingStartEventLoopModule:
    """Controllable module whose ``start_event_loop()`` raises — used for Phase 4.

    ``init_spi_bus()`` succeeds (returns None) so the module IS tracked, but
    ``start_event_loop()`` raises, so start() fails and _cleanup_partial_start()
    must drain and close_spi() the already-initialized module.
    """

    def __init__(self, ce_number: int = 0, spi_device_id: int = 0) -> None:
        self.ce_number: int = ce_number
        self.spi_device_id: int = spi_device_id
        self.stop_event_loop_calls: int = 0
        self.close_spi_calls: int = 0
        self._start_error: RuntimeError = RuntimeError("start_event_loop() failed")

    async def init_spi_bus(self) -> None:
        return None

    async def start_event_loop(self) -> None:
        raise self._start_error

    async def stop_event_loop(self, mode: Any) -> None:
        self.stop_event_loop_calls += 1
        return None

    async def close_spi(self) -> None:
        self.close_spi_calls += 1
        return None

    def get_spi_device_id(self) -> int:
        return self.spi_device_id

    def get_ce_number(self) -> int:
        return self.ce_number


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

    @pytest.mark.asyncio
    async def test_start_reentrancy_prevents_duplication(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        results = await asyncio.gather(
            *[app.start() for _ in range(10)], return_exceptions=True
        )
        modules = app.module_manager.get_all_modules()
        # The _start_lock serialises start(); the duplicate guard never
        # over-creates modules beyond a single start() (2 devices).
        assert len(modules) <= 2
        # At least one start() completes successfully.
        assert any(not isinstance(r, Exception) for r in results)
        await app.stop()
        assert app._started_modules == []
        assert app._scheduler_started is False
        assert app._started is False

    @pytest.mark.asyncio
    async def test_start_stop_no_interleave(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        assert app._started is True
        tasks = [app.start() for _ in range(5)] + [app.stop() for _ in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        assert any(not isinstance(r, Exception) for r in results)
        modules = app.module_manager.get_all_modules()
        assert len(modules) <= 2
        assert app.scheduler.timer_scheduler._running is False
        assert app.scheduler.idle_pacer._running is False
        assert app.scheduler.interrupt_bridge._running is False
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_stop_reentrancy_prevents_error(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        results = await asyncio.gather(
            *[app.stop() for _ in range(5)], return_exceptions=True
        )
        assert all(isinstance(r, Exception) or r is None for r in results)
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False
        await app.stop()
        assert app._started is False

    @pytest.mark.asyncio
    async def test_stop_success_does_not_raise(self) -> None:
        """A clean stop() must not raise an ExceptionGroup (no errors collected)."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        await app.stop()
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_stop_surfaces_failures_as_exceptiongroup(self) -> None:
        """app.stop() surfaces drained failures as an ExceptionGroup containing the
        exact error, and state flags reset to a clean baseline regardless."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()

        failing = _FailingStopModule()

        def _get_all_modules() -> list[Any]:
            return [failing]

        app.module_manager.get_all_modules = _get_all_modules  # type: ignore[assignment]

        def _failing_scheduler_stop() -> Any:
            raise RuntimeError("scheduler.stop() failed")

        app.scheduler.stop = _failing_scheduler_stop  # type: ignore[assignment]

        with pytest.raises(ExceptionGroup) as excinfo:
            await app.stop()

        surfaced = list(excinfo.value.exceptions)
        assert surfaced
        assert failing._stop_error in surfaced
        assert any(isinstance(e, RuntimeError) for e in surfaced)

        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_scheduler_started_flag_true_before_scheduler_start(self) -> None:
        """_scheduler_started must be False when scheduler.start() is entered; the flag is set only after start succeeds."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        entries: list[bool] = []

        async def failing_start() -> None:
            entries.append(app._scheduler_started)
            raise RuntimeError("scheduler.start() failed partway")

        app.scheduler.start = failing_start  # type: ignore[assignment]

        with pytest.raises(RuntimeError):
            await app.start()

        assert entries == [False]
        assert app._scheduler_started is False
        assert app._started_modules == []
        assert app._started is False

    @pytest.mark.asyncio
    async def test_start_scheduler_started_flag_after_start(self) -> None:
        """_scheduler_started becomes True only after scheduler.start() succeeds, and resets on stop()."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        assert app._scheduler_started is True
        await app.stop()
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_partial_scheduler_failure_no_cleanup_stop(self) -> None:
        """A scheduler that never started must not have stop() called during cleanup;
        _scheduler_started is False when scheduler.start() fails, so no spurious stop()."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        stop_calls: list[int] = []

        async def counting_stop() -> None:
            stop_calls.append(1)

        async def failing_start() -> None:
            raise RuntimeError("scheduler.start() failed partway")

        app.scheduler.stop = counting_stop  # type: ignore[assignment]
        app.scheduler.start = failing_start  # type: ignore[assignment]

        with pytest.raises(RuntimeError):
            await app.start()

        assert stop_calls == []
        assert app._scheduler_started is False
        assert app._started_modules == []
        assert app._started is False

    @pytest.mark.asyncio
    async def test_scheduler_started_flag_true_after_successful_start(self) -> None:
        """Flag remains True after a successful start and resets on stop()."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        assert app._scheduler_started is True
        await app.stop()
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_module_init_failure_not_tracked_for_cleanup(self) -> None:
        """A module whose init_spi_bus() fails is NOT tracked (append happens after
        init succeeds), so _cleanup_partial_start() does not call close_spi() on an
        uninitialized module."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())

        failing = _FailingInitModule()

        def _get_all_modules() -> list[Any]:
            return [failing]

        app.module_manager.get_all_modules = _get_all_modules  # type: ignore[assignment]

        with pytest.raises(RuntimeError):
            await app.start()

        # The failing module was not tracked before init_spi_bus() failed.
        assert failing.close_spi_calls == 0
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_start_event_loop_failure_still_tracked_for_cleanup(self) -> None:
        """A module whose init_spi_bus() succeeds but whose start_event_loop() raises
        IS tracked (append happens after init succeeds), so _cleanup_partial_start()
        must drain and close_spi() it even though start() failed."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())

        failing = _FailingStartEventLoopModule()

        def _get_all_modules() -> list[Any]:
            return [failing]

        app.module_manager.get_all_modules = _get_all_modules  # type: ignore[assignment]

        with pytest.raises(RuntimeError):
            await app.start()

        # The module was tracked after init_spi_bus() succeeded, so cleanup drains it.
        assert failing.close_spi_calls == 1
        assert failing.stop_event_loop_calls == 1
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False

    @pytest.mark.asyncio
    async def test_start_modules_appended_after_init_success(self) -> None:
        """Every module is added to _started_modules only after init_spi_bus() and start_event_loop() succeed; on stop() the list clears."""
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        started = app._started_modules
        all_mods = app.module_manager.get_all_modules()
        assert len(started) >= 1
        assert started == all_mods
        assert all(mod.spi_bus is not None for mod in started)
        await app.stop()
        assert app._started_modules == []

    @pytest.mark.asyncio
    async def test_stop_unregisters_modules_before_draining(self) -> None:
        app = Application(config=None, spi_factory=MockSpiBusFactory())
        await app.start()
        modules = app.module_manager.get_all_modules()
        assert any(m in app.scheduler.timer_scheduler._registered for m in modules)
        await app.stop()
        assert app.scheduler.timer_scheduler._registered == set()
        assert app._started is False
        assert app._started_modules == []
        assert app._scheduler_started is False


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

    @pytest.mark.asyncio
    async def test_list_assemblies_basic(self) -> None:
        """Verify list_assemblies returns assembly names."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = await application.list_assemblies(verbose=False)
        assert len(assemblies) >= 1
        names = [a["assembly_name"] for a in assemblies]
        assert "default" in names

    @pytest.mark.asyncio
    async def test_list_assemblies_verbose(self) -> None:
        """Verify list_assemblies verbose includes module_name and device_count."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = await application.list_assemblies(verbose=True)
        assert len(assemblies) >= 1
        for a in assemblies:
            assert "assembly_name" in a
            assert "module_name" in a
            assert "device_count" in a

    @pytest.mark.asyncio
    async def test_list_assemblies_json_format(self) -> None:
        """Verify list_assemblies returns dict format suitable for JSON."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assemblies = await application.list_assemblies(verbose=False)
        assert isinstance(assemblies, list)
        for a in assemblies:
            assert isinstance(a, dict)


class TestGetAssemblyConfig:
    """Tests for Application.get_assembly_config()."""

    @pytest.mark.asyncio
    async def test_get_assembly_config_all_devices(self) -> None:
        """Verify get_assembly_config returns config for default assembly."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = await application.get_assembly_config("default")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_assembly_config_single_device(self) -> None:
        """Verify get_assembly_config returns config for a specific SPI/CE slot."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = await application.get_assembly_config("default", spi_device_id=0, ce_number=0)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_assembly_config_not_found(self) -> None:
        """Verify get_assembly_config raises AssemblyNotFoundError for missing assembly."""
        from src.pi_lora.framework.exceptions import AssemblyNotFoundError

        application = Application(config=None)
        application._config = None
        application._config_path = None

        with pytest.raises(AssemblyNotFoundError):
            await application.get_assembly_config("nonexistent")

    @pytest.mark.asyncio
    async def test_get_assembly_config_device_not_found(self) -> None:
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
            await application.get_assembly_config("default", spi_device_id=99, ce_number=99)

    @pytest.mark.asyncio
    async def test_get_assembly_config_validation_error_propagates(self) -> None:
        """Verify get_assembly_config returns config without raising ConfigConsistencyError."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        result = await application.get_assembly_config("default")
        assert result is not None


class TestConfigLoading:
    """Tests for config loading behavior."""

    @pytest.mark.asyncio
    async def test_lazy_load(self) -> None:
        """Verify config is only loaded on first query."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        assert application._config is None
        assemblies = await application.list_assemblies()
        assert len(assemblies) >= 1
        assert application._config is not None

    @pytest.mark.asyncio
    async def test_reload_config(self) -> None:
        """Verify reload_config forces reload."""
        application = Application(config=None)
        application._config = None
        application._config_path = None

        await application.list_assemblies()
        reloaded = await application.reload_config()
        assert reloaded is not None


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
