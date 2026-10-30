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

"""Unit tests for ModuleManager config loading and module registration."""

import asyncio
from unittest import mock

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from src.pi_lora.framework.module_manager import (
    DuplicateDeviceIdentityError,
    ModuleManager,
)
from src.pi_lora.framework.scheduler import Scheduler


def _make_test_radio_configs() -> list[RadioInstanceConfig]:
    """Build a minimal test config with two radio instance configs."""
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
            dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"),
            antenna_type=None,
            antenna_gain_db=None,
        ),
        RadioInstanceConfig(
            module_name="LoPi4",
            spi_device_id=5,
            ce_number=1,
            device_name="RFM98W",
            min_radio_freq_hz=400000,
            max_radio_freq_hz=500000,
            osc_freq_hz=38_400_000,
            family_name="SX127X",
            test_invalid_frequencies_hz=(888888,),
            dio_gpio_mappings=("DIO0:WPi27", "DIO5:WPi26"),
            antenna_type=None,
            antenna_gain_db=None,
        ),
    ]


def _make_duplicate_radio_configs() -> list[RadioInstanceConfig]:
    """Build two configs sharing the same DeviceIdentity for the duplicate guard test."""
    base: RadioInstanceConfig = RadioInstanceConfig(
        module_name="LoPi4",
        spi_device_id=0,
        ce_number=0,
        device_name="RFM95W",
        min_radio_freq_hz=800000,
        max_radio_freq_hz=900000,
        osc_freq_hz=32_000_000,
        family_name="RFM9X",
        test_invalid_frequencies_hz=(999999,),
        dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"),
        antenna_type=None,
        antenna_gain_db=None,
    )
    return [base, base]


class TestLoadFromConfig:
    """Verify ModuleManager.load_from_config behavior."""

    @pytest.mark.asyncio
    async def test_creates_modules(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        assert len(mm.modules) == 2

    @pytest.mark.asyncio
    async def test_keys_by_spi_ce(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        assert (0, 0) in mm.modules_by_id
        assert (5, 1) in mm.modules_by_id

    @pytest.mark.asyncio
    async def test_identity_setters_called(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        mod0 = mm.get_module(0, 0)
        assert mod0 is not None
        assert mod0.get_spi_device_id() == 0
        assert mod0.get_ce_number() == 0
        mod1 = mm.get_module(5, 1)
        assert mod1 is not None
        assert mod1.get_spi_device_id() == 5
        assert mod1.get_ce_number() == 1

    @pytest.mark.asyncio
    async def test_scheduler_registered_with_gpios(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        mod0 = mm.get_module(0, 0)
        assert mod0 is not None
        assert 6 in scheduler.interrupt_bridge._interrupt_map
        assert 5 in scheduler.interrupt_bridge._interrupt_map

    @pytest.mark.asyncio
    async def test_get_module_returns_none_for_missing(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        result = mm.get_module(99, 99)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_modules_returns_copy(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        mods = mm.get_all_modules()
        assert len(mods) == 2
        assert mods is not mm.modules

    @pytest.mark.asyncio
    async def test_duplicate_device_identity_raises(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        mm = ModuleManager()
        radio_configs = _make_duplicate_radio_configs()
        scheduler = Scheduler()
        with pytest.raises(DuplicateDeviceIdentityError) as exc_info:
            await mm.load_from_config(radio_configs, scheduler)
        assert exc_info.value.context["device_key"] == "0:0"
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_malformed_gpio_mapping_warns(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        mm = ModuleManager()
        radio_configs: list[RadioInstanceConfig] = [
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
                dio_gpio_mappings=("DIO0:WPi6", "DIO0:foo"),
                antenna_type=None,
                antenna_gain_db=None,
            ),
        ]
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        assert len(mm.modules) == 1
        assert 6 in scheduler.interrupt_bridge._interrupt_map
        assert any(
            "Unparseable GPIO mapping" in msg for msg in caplog.messages
        )
        malformed_records = [
            record
            for record in caplog.records
            if "Unparseable GPIO mapping" in record.getMessage()
        ]
        assert malformed_records
        for record in malformed_records:
            assert record.levelname == "ERROR"
        assert any(
            "interrupt handling disabled" in msg.lower() for msg in caplog.messages
        )

    @pytest.mark.asyncio
    async def test_load_failure_rolls_back(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        def _force_failure(*_args: object, **_kwargs: object) -> None:  # nosemgrep: maintainability.useless-inner-function
            raise RuntimeError("Module construction failed during load")

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_force_failure,
        ) as _, pytest.raises(RuntimeError) as exc_info:
            await mm.load_from_config(radio_configs, scheduler)
        assert isinstance(exc_info.value, RuntimeError)
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_partial_load_failure_unregisters_scheduler(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()

        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise RuntimeError("Second module construction failed during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(RuntimeError):
            await mm.load_from_config(radio_configs, scheduler)

        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert any("rolled back" in msg.lower() for msg in caplog.messages)
        assert scheduler.timer_scheduler._registered == set()
        assert module0 not in scheduler.idle_pacer._idle_enabled_modules
        assert all(
            m is not module0 for m in scheduler.interrupt_bridge._interrupt_map.values()
        )
        assert 6 not in scheduler.interrupt_bridge._interrupt_map

    @pytest.mark.asyncio
    async def test_load_catches_exception_not_baseexception(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A plain Exception (RuntimeError) IS caught and rolled back; BaseException subclasses are not."""
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        def _force_runtime(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("Module construction failed during load")

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_force_runtime,
        ), pytest.raises(RuntimeError):
            await mm.load_from_config(radio_configs, scheduler)

        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert scheduler.timer_scheduler._registered == set()
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_load_failure_awaits_rollback(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A RuntimeError on the 2nd module rolls back the 1st: scheduler fully drained, state cleared."""
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise RuntimeError("Second module construction failed during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(RuntimeError):
            await mm.load_from_config(radio_configs, scheduler)

        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert scheduler.timer_scheduler._registered == set()
        assert module0 not in scheduler.idle_pacer._idle_enabled_modules
        assert all(m is not module0 for m in scheduler.interrupt_bridge._interrupt_map.values())
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_cancelled_error_rolls_back(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """CancelledError rolls back (Plan-18 §5.1).

        CancelledError is a BaseException (not Exception) in Python 3.13, so it is
        NOT matched by ``except Exception`` alone. The explicit
        ``(Exception, asyncio.CancelledError)`` handler catches it and rolls back
        the pending modules exactly like a regular Exception: the first module is
        unregistered and main tracking is reset empty.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise asyncio.CancelledError("Module cancelled during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(asyncio.CancelledError):
            await mm.load_from_config(radio_configs, scheduler)

        # Rolled back: the first module is unregistered and main tracking is empty.
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert scheduler.timer_scheduler._registered == set()
        assert module0 not in scheduler.idle_pacer._idle_enabled_modules
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_module_manager_rollback_aggregates_errors(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """H-12: rollback unregister_module failures aggregate into an ExceptionGroup chained to original_exc."""
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        original_exc: BaseException = RuntimeError("Second module construction failed")

        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise original_exc
            return module0

        async def _fail_unregister(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("unregister failed during rollback")

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), mock.patch.object(
            scheduler, "unregister_module", side_effect=_fail_unregister
        ), pytest.raises(ExceptionGroup) as exc_info:
            await mm.load_from_config(radio_configs, scheduler)

        assert exc_info.value.__cause__ is original_exc
        assert any(
            isinstance(e, RuntimeError)
            and str(e) == "unregister failed during rollback"
            for e in exc_info.value.exceptions
        )
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_module_manager_pending_list_no_dangling_refs(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """H-13: a failed 2nd load leaves NO dangling scheduler reference to the 1st module.

        The 1st module is registered in the scheduler but parked in pending
        (never committed to main tracking). On the 2nd-module failure the pending
        list rollback unregisters it, so no dangling reference survives in any
        scheduler state field, and main tracking is fully empty.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise RuntimeError("Second module construction failed during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(RuntimeError) as exc_info:
            await mm.load_from_config(radio_configs, scheduler)

        assert isinstance(exc_info.value, RuntimeError)

        # Main tracking is fully empty — no partial leak visible to callers.
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0

        # No dangling reference survives in ANY scheduler state field.
        assert module0 not in scheduler.timer_scheduler._registered
        assert module0 not in scheduler.timer_scheduler._tasks
        assert module0 not in scheduler.timer_scheduler._intervals
        assert module0 not in scheduler.timer_scheduler._failure_counts
        assert module0 not in scheduler.timer_scheduler._last_failure_log
        assert module0 not in scheduler.idle_pacer._idle_enabled_modules
        assert all(
            m is not module0 for m in scheduler.interrupt_bridge._interrupt_map.values()
        )

        # Pending-list rollback fully releases scheduler state.
        assert scheduler.timer_scheduler._failure_counts == {}
        assert scheduler.timer_scheduler._last_failure_log == {}

        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_load_from_config_keyboard_interrupt_propagates_no_cleanup(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """KeyboardInterrupt propagates without async cleanup (Plan-18 §5.3).

        KeyboardInterrupt is a shutdown signal (a BaseException, not Exception, and
        not CancelledError), so it is NOT matched by the
        ``(Exception, asyncio.CancelledError)`` handler. It propagates immediately
        with no rollback: the scheduler keeps the pending module registered and no
        "rolled back" message is logged. Main tracking stays empty because nothing
        was ever committed.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise KeyboardInterrupt("KeyboardInterrupt during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(KeyboardInterrupt):
            await mm.load_from_config(radio_configs, scheduler)

        # Shutdown signal is NOT caught by the handler -> rollback never ran.
        # Main tracking stays empty (nothing was committed), but the pending
        # module remains registered in the scheduler because no rollback ran.
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert module0 in scheduler.timer_scheduler._registered
        assert module0 in scheduler.idle_pacer._idle_enabled_modules
        assert any(m is module0 for m in scheduler.interrupt_bridge._interrupt_map.values())
        assert not any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_load_from_config_system_exit_propagates_no_cleanup(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """SystemExit propagates without async cleanup (Plan-18 §5.3).

        SystemExit is a shutdown signal (a BaseException, not Exception, and not
        CancelledError), so it is NOT matched by the
        ``(Exception, asyncio.CancelledError)`` handler. It propagates immediately
        with no rollback: the scheduler keeps the pending module registered and no
        "rolled back" message is logged. Main tracking stays empty because nothing
        was ever committed.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise SystemExit("SystemExit during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(SystemExit):
            await mm.load_from_config(radio_configs, scheduler)

        # Shutdown signal is NOT caught by the handler -> rollback never ran.
        # Main tracking stays empty (nothing was committed), but the pending
        # module remains registered in the scheduler because no rollback ran.
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert module0 in scheduler.timer_scheduler._registered
        assert module0 in scheduler.idle_pacer._idle_enabled_modules
        assert any(m is module0 for m in scheduler.interrupt_bridge._interrupt_map.values())
        assert not any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_load_from_config_cancelled_error_rolls_back(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """CancelledError rolls back on load (Plan-18 §5.1).

        CancelledError is a BaseException that signals the caller's task was
        cancelled, not a recoverable load failure. Plan-18 §5.1 requires it to roll
        back exactly like a regular Exception: the pending module is unregistered
        and main tracking is reset empty. This guards against the Plan-17 regression
        that committed (never unregistered) on cancellation.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise asyncio.CancelledError("Module cancelled during load")
            return module0

        with mock.patch(
            "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
            side_effect=_construct,
        ), pytest.raises(asyncio.CancelledError):
            await mm.load_from_config(radio_configs, scheduler)

        # Rolled back (NOT committed): the first module is unregistered and main
        # tracking is reset empty.
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
        assert module0 not in scheduler.timer_scheduler._registered
        assert module0 not in scheduler.idle_pacer._idle_enabled_modules
        assert any("rolled back" in msg.lower() for msg in caplog.messages)

    @pytest.mark.asyncio
    async def test_load_from_config_keyboard_interrupt_no_async_cleanup(
        self,
    ) -> None:
        """Blocker 5.3: KeyboardInterrupt (a BaseException, not Exception) propagates
        immediately without async cleanup. The event loop may be closed during process
        shutdown, so ``_rollback_pending_modules()`` (which awaits
        ``scheduler.unregister_module()``) must NOT run. ``KeyboardInterrupt`` is not
        caught by ``except Exception`` in ``load_from_config()``.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise KeyboardInterrupt("KeyboardInterrupt during load")
            return module0

        unregister = mock.MagicMock()

        def _refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("unregister_module must not run for KeyboardInterrupt")

        unregister.side_effect = _refuse

        with (
            mock.patch(
                "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
                side_effect=_construct,
            ),
            mock.patch.object(scheduler, "unregister_module", unregister),
            pytest.raises(KeyboardInterrupt),
        ):
            await mm.load_from_config(radio_configs, scheduler)

        # KeyboardInterrupt is not caught by ``except Exception`` -> rollback never ran.
        assert unregister.call_count == 0
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0

    @pytest.mark.asyncio
    async def test_load_from_config_system_exit_no_async_cleanup(
        self,
    ) -> None:
        """Blocker 5.3: SystemExit (a BaseException, not Exception) propagates
        immediately without async cleanup. The event loop may be closed during process
        shutdown, so ``_rollback_pending_modules()`` (which awaits
        ``scheduler.unregister_module()``) must NOT run. ``SystemExit`` is not caught
        by ``except Exception`` in ``load_from_config()``.
        """
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()

        module0: object = object()
        _call_count: int = 0

        def _construct(*_args: object, **_kwargs: object) -> object:
            nonlocal _call_count
            _call_count += 1
            if _call_count >= 2:
                raise SystemExit("SystemExit during load")
            return module0

        unregister = mock.MagicMock()

        def _refuse(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("unregister_module must not run for SystemExit")

        unregister.side_effect = _refuse

        with (
            mock.patch(
                "src.pi_lora.framework.module_manager.Rfm9xSx127xModule",
                side_effect=_construct,
            ),
            mock.patch.object(scheduler, "unregister_module", unregister),
            pytest.raises(SystemExit),
        ):
            await mm.load_from_config(radio_configs, scheduler)

        # SystemExit is not caught by ``except Exception`` -> rollback never ran.
        assert unregister.call_count == 0
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0


class TestEmptyConfig:
    """Verify ModuleManager handles empty config gracefully."""

    @pytest.mark.asyncio
    async def test_no_modules_from_empty_config(self) -> None:
        mm = ModuleManager()
        radio_configs: list[RadioInstanceConfig] = []
        scheduler = Scheduler()
        await mm.load_from_config(radio_configs, scheduler)
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
