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

"""Tests for ``Rfm9xSx127xModule`` state management context."""

import gc
import unittest.mock

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_modes import (
    FskOokSleepState,
    StateBits,
    UnknownState,
)
from src.pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule
from src.pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig

from tests.spi.mock import MockSpiBusFactory


class TestRfm9xSx127xModule:
    """Tests for the ``Rfm9xSx127xModule`` class."""

    def _make_radio_config(
        self,
        spi_device_id: int = 0,
        ce_number: int = 0,
        osc_freq_hz: int | None = 32_000_000,
    ) -> RadioInstanceConfig:
        return RadioInstanceConfig(
            module_name="LoPi4", spi_device_id=spi_device_id, ce_number=ce_number,
            device_name="RFM95W", min_radio_freq_hz=800000, max_radio_freq_hz=900000,
            osc_freq_hz=osc_freq_hz, family_name="RFM9X", test_invalid_frequencies_hz=(999999,),
            dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"), antenna_type=None, antenna_gain_db=None,
        )

    def test_init_with_unknown_state(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        assert isinstance(module.current_state_instance, UnknownState)

    def test_set_current_state_to_fsk_ook_sleep(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)

    def test_set_current_state_back_to_unknown(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)
        module.set_current_state(StateBits.UNKNOWN_STATE)
        assert isinstance(module.current_state_instance, UnknownState)

    def test_set_current_state_to_fsk_ook_sleep_again(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)
        module.set_current_state(StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)

    def test_is_in_state(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        assert module.is_in_state(StateBits.UNKNOWN_STATE) is True
        assert module.is_in_state(StateBits.FSK_OOK_SLEEP) is False
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert module.is_in_state(StateBits.FSK_OOK_SLEEP) is True
        assert module.is_in_state(StateBits.UNKNOWN_STATE) is False

    def test_is_in_lora_mode(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)
        assert module.is_in_lora_mode() is False
        module.set_current_state(StateBits.LORA_SLEEP)
        assert module.is_in_lora_mode() is True

    def test_is_in_fsk_ook_mode(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)
        assert module.is_in_fsk_ook_mode() is True
        module.set_current_state(StateBits.LORA_SLEEP)
        assert module.is_in_fsk_ook_mode() is False

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_sleep_returns_true(self) -> None:
        factory = MockSpiBusFactory()
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP, spi_factory=factory)
        module.spi_device_id = 0
        await module.init_spi_bus()
        result: bool = await module.write_and_verify_frequency_for_khz(415000)
        assert result is True
        await module.close_spi()

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_fstx_raises(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)
        module.set_current_state(StateBits.FSK_OOK_FSTX)
        with pytest.raises(RuntimeError):
            await module.write_and_verify_frequency_for_khz(415000)

    def test_memory_management(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
        instances = module.state_instances
        del module
        gc.collect()
        assert len(instances) > 0

    @pytest.mark.asyncio
    async def test_spi_bus_injection_and_frequency_write(self) -> None:
        factory = MockSpiBusFactory()
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP, spi_factory=factory)
        module.spi_device_id = 0
        await module.init_spi_bus()
        assert module.spi_bus is not None
        result: bool = await module.write_and_verify_frequency_for_khz(415000)
        assert result is True
        await module.close_spi()
        assert module.spi_bus is None

    def test_module_does_not_instantiate_handler(self) -> None:
        radio_config = self._make_radio_config()
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)
        assert not hasattr(module, "handler")
        mock_factory = unittest.mock.MagicMock()
        module2 = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP, mock_factory)
        module2.spi_device_id = 0
        module2.ce_number = 0


def _make_radio_config(
    spi_device_id: int = 0,
    ce_number: int = 0,
    osc_freq_hz: int | None = 32_000_000,
    device_name: str = "RFM95W",
) -> RadioInstanceConfig:
    """Build a minimal ``RadioInstanceConfig`` for testing."""
    return RadioInstanceConfig(
        module_name="LoPi4",
        spi_device_id=spi_device_id,
        ce_number=ce_number,
        device_name=device_name,
        min_radio_freq_hz=800000,
        max_radio_freq_hz=900000,
        osc_freq_hz=osc_freq_hz,
        family_name="RFM9X",
        test_invalid_frequencies_hz=(999999,),
        dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"),
        antenna_type=None,
        antenna_gain_db=None,
    )


class TestRadioInstanceConfigFixture:
    """Tests for ``RadioInstanceConfig`` as a fixture for module construction."""

    def test_radio_config_all_fields_populated(self) -> None:
        config = _make_radio_config()
        assert config.module_name == "LoPi4"
        assert config.spi_device_id == 0
        assert config.ce_number == 0
        assert config.device_name == "RFM95W"
        assert config.min_radio_freq_hz == 800000
        assert config.max_radio_freq_hz == 900000
        assert config.osc_freq_hz == 32_000_000
        assert config.family_name == "RFM9X"
        assert config.test_invalid_frequencies_hz == (999999,)
        assert config.dio_gpio_mappings == ("DIO0:WPi6", "DIO5:WPi5")
        assert config.antenna_type is None
        assert config.antenna_gain_db is None

    def test_radio_config_device_id_key(self) -> None:
        config = _make_radio_config(spi_device_id=5, ce_number=1)
        key = config.device_id_key
        assert key.spi_device_id == 5
        assert key.ce_number == 1

    def test_radio_config_frequency_range(self) -> None:
        config = _make_radio_config()
        freq_range = config.frequency_range_hz
        assert freq_range == (800000, 900000)

    def test_radio_config_supported_frequencies(self) -> None:
        config = _make_radio_config()
        supported = config.supported_frequencies_hz
        assert supported == (800000, 900000)


class TestRfm9xSx127xModuleWithRadioConfig:
    """Tests for ``Rfm9xSx127xModule`` constructed with ``RadioInstanceConfig``."""

    def test_init_with_radio_config_sets_identity(self) -> None:
        config = _make_radio_config(spi_device_id=3, ce_number=2)
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)
        assert module.spi_device_id == 3
        assert module.ce_number == 2
        assert module.radio_config is config

    def test_get_spi_device_id_returns_config_value(self) -> None:
        config = _make_radio_config(spi_device_id=7, ce_number=4)
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)
        assert module.get_spi_device_id() == 7

    def test_get_ce_number_returns_config_value(self) -> None:
        config = _make_radio_config(spi_device_id=1, ce_number=3)
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)
        assert module.get_ce_number() == 3

    def test_get_current_state_name_returns_class_name(self) -> None:
        config = _make_radio_config()
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)
        state_name = module.get_current_state_name()
        assert state_name == "FskOokSleepState"

    def test_get_event_queue_size_returns_zero(self) -> None:
        config = _make_radio_config()
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)
        assert module.get_event_queue_size() == 0

    @pytest.mark.asyncio
    async def test_write_frequency_uses_config_osc_freq(self) -> None:
        config = _make_radio_config(osc_freq_hz=26_000_000)
        module = Rfm9xSx127xModule(config, StateBits.FSK_OOK_SLEEP)

        class CaptureSpiBus:
            def __init__(self) -> None:
                self._regs: dict[int, int] = {}

            async def xfer2(self, data: list[int]) -> list[int]:
                reg = data[0] & 0x7F
                if data[0] & 0x80:
                    self._regs[reg] = data[1]
                return [reg, self._regs.get(reg, 0)]

        spi_bus = CaptureSpiBus()
        module.spi_bus = spi_bus
        result: bool = await module.write_and_verify_frequency_for_khz(415000)
        assert result is True
