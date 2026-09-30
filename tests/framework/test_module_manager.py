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

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from src.pi_lora.framework.module_manager import ModuleManager
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


class TestLoadFromConfig:
    """Verify ModuleManager.load_from_config behavior."""

    @pytest.mark.asyncio
    async def test_creates_modules(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
        assert len(mm.modules) == 2

    @pytest.mark.asyncio
    async def test_keys_by_spi_ce(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
        assert (0, 0) in mm.modules_by_id
        assert (5, 1) in mm.modules_by_id

    @pytest.mark.asyncio
    async def test_identity_setters_called(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
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
        mm.load_from_config(radio_configs, scheduler)
        mod0 = mm.get_module(0, 0)
        assert mod0 is not None
        assert 6 in scheduler.interrupt_bridge._interrupt_map
        assert 5 in scheduler.interrupt_bridge._interrupt_map

    @pytest.mark.asyncio
    async def test_get_module_returns_none_for_missing(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
        result = mm.get_module(99, 99)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_modules_returns_copy(self) -> None:
        mm = ModuleManager()
        radio_configs = _make_test_radio_configs()
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
        mods = mm.get_all_modules()
        assert len(mods) == 2
        assert mods is not mm.modules


class TestEmptyConfig:
    """Verify ModuleManager handles empty config gracefully."""

    def test_no_modules_from_empty_config(self) -> None:
        mm = ModuleManager()
        radio_configs: list[RadioInstanceConfig] = []
        scheduler = Scheduler()
        mm.load_from_config(radio_configs, scheduler)
        assert len(mm.modules) == 0
        assert len(mm.modules_by_id) == 0
