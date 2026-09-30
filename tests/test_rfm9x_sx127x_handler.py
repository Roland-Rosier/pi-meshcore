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

"""Tests for ``Rfm9xSx127xHandler`` methods."""

import dataclasses

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_handler import (
    FrequencyCalculationConfig,
    Rfm9xSx127xHandler,
)
from src.pi_lora.drivers.rfm9x_sx127x_modes import ModeBits

from tests.spi.mock import MockSpiBusFactory


class MockModule:
    """Minimal module shim exposing a ``spi_bus`` attribute for handler static methods."""

    def __init__(self, spi_bus: object) -> None:
        self.spi_bus: object = spi_bus


class TestRfm9xSx127xHandler:
    """Tests for the ``Rfm9xSx127xHandler`` class and its methods."""

    @pytest.mark.asyncio
    async def test_set_module_mode_raises_without_spi_bus(self) -> None:
        module = MockModule(spi_bus=None)
        with pytest.raises(RuntimeError, match="module.spi_bus is None"):
            await Rfm9xSx127xHandler.set_module_mode(module, ModeBits.STANDBY)

    @pytest.mark.asyncio
    async def test_set_module_mode_with_all_modes(self) -> None:
        for mode in ModeBits:
            module = MockModule(spi_bus=None)
            with pytest.raises(RuntimeError, match="module.spi_bus is None"):
                await Rfm9xSx127xHandler.set_module_mode(module, mode)

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_raises_without_spi(self) -> None:
        module = MockModule(spi_bus=None)
        config = FrequencyCalculationConfig(osc_freq_hz=None)
        with pytest.raises(RuntimeError, match="module.spi_bus is None"):
            await Rfm9xSx127xHandler.write_and_verify_frequency_for_khz(module, config, 415000)

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_with_various_frequencies_no_spi(self) -> None:
        frequencies: list[int] = [0, 1, 415000, 868000, 434000, 9999999]
        for freq in frequencies:
            module = MockModule(spi_bus=None)
            config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
            with pytest.raises(RuntimeError, match="module.spi_bus is None"):
                await Rfm9xSx127xHandler.write_and_verify_frequency_for_khz(module, config, freq)

    def test_calc_freq_registers_for_khz_returns_valid_values(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        assert result[0] is not None
        assert result[1] is not None
        assert result[2] is not None

    def test_calc_freq_registers_for_khz_with_various_frequencies(self) -> None:
        frequencies: list[int] = [0, 1, 415000, 868000, 434000, 9999999]
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        for freq in frequencies:
            result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, freq)
            assert all(r is not None for r in result), (
                f"calc_freq_registers_for_khz({freq}) should return valid values"
            )

    @pytest.mark.asyncio
    async def test_handler_methods_accessible_via_guard(self) -> None:
        from src.pi_lora.drivers.rfm9x_sx127x_modes import StateBits
        from src.pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule
        from src.pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig

        radio_config = RadioInstanceConfig(
            module_name="LoPi4", spi_device_id=0, ce_number=0, device_name="RFM95W",
            min_radio_freq_hz=800000, max_radio_freq_hz=900000, osc_freq_hz=32_000_000,
            family_name="RFM9X", test_invalid_frequencies_hz=(999999,),
            dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"), antenna_type=None, antenna_gain_db=None,
        )
        module = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)
        assert callable(module.write_and_verify_frequency_for_khz)

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_with_mock_spi_bus(self) -> None:
        factory = MockSpiBusFactory()
        module = MockModule(factory.create(bus=0, device=0))
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = await Rfm9xSx127xHandler.write_and_verify_frequency_for_khz(module, config, 415000)
        success = result[0]
        req_msb, req_mid, req_lsb = result[1], result[2], result[3]
        read_msb, read_mid, read_lsb = result[4], result[5], result[6]
        assert success is True
        assert req_msb == read_msb
        assert req_mid == read_mid
        assert req_lsb == read_lsb
        assert all(r is not None for r in result)

    def test_calc_freq_registers_for_khz_returns_tuple_int_int_int(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        assert isinstance(result, tuple)
        assert len(result) == 3
        msb, mid, lsb = result
        assert isinstance(msb, int)
        assert isinstance(mid, int)
        assert isinstance(lsb, int)
        assert all(r is not None for r in result)

    @pytest.mark.asyncio
    async def test_set_module_mode_propagates_exception_on_invalid_register(self) -> None:
        class BrokenSpiBus:
            async def xfer2(self, data: list[int]) -> list[int]:
                raise ValueError("spi_bus xfer2 failed")

        module = MockModule(BrokenSpiBus())
        with pytest.raises(ValueError, match="spi_bus xfer2 failed"):
            await Rfm9xSx127xHandler.set_module_mode(module, ModeBits.STANDBY)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_propagates_exception_on_invalid_register(self) -> None:
        class BrokenSpiBus:
            async def xfer2(self, data: list[int]) -> list[int]:
                raise ValueError("spi_bus xfer2 failed")

        module = MockModule(BrokenSpiBus())
        config = FrequencyCalculationConfig(osc_freq_hz=None)
        with pytest.raises(ValueError, match="spi_bus xfer2 failed"):
            await Rfm9xSx127xHandler.write_and_verify_frequency_for_khz(module, config, 415000)  # type: ignore[arg-type]


class TestFrequencyCalculationConfig:
    """Tests for ``FrequencyCalculationConfig`` and ``calc_freq_registers_for_khz`` with osc_freq_hz."""

    def test_calc_with_osc_freq_32_mhz(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        msb, mid, lsb = result
        expected_value: int = int((415000 * 1_000 * 524288) / 32_000_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_with_osc_freq_26_mhz(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=26_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        msb, mid, lsb = result
        expected_value: int = int((415000 * 1_000 * 524288) / 26_000_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_with_osc_freq_38_400_000(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=38_400_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        msb, mid, lsb = result
        expected_value: int = int((415000 * 1_000 * 524288) / 38_400_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_with_none_osc_freq_fallback(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=None)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        msb, mid, lsb = result
        expected_value: int = int((415000 * 1_000 * 524288) / 32_000_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_with_none_osc_freq_fallback_logs_warning(self, caplog: object) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=None)
        Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 415000)
        assert "defaulting to 32 MHz" in caplog.text

    def test_calc_boundary_min_frequency(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 0)
        assert result == (0, 0, 0)

    def test_calc_boundary_max_frequency(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 9999999)
        msb, mid, lsb = result
        expected_value: int = int((9999999 * 1_000 * 524288) / 32_000_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_boundary_frequency_at_osc(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        result = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config, 32000)
        msb, mid, lsb = result
        expected_value: int = int((32000 * 1_000 * 524288) / 32_000_000)
        assert lsb == (expected_value & 0xFF)
        assert mid == ((expected_value & 0xFF00) >> 8)
        assert msb == ((expected_value & 0xFF0000) >> 16)

    def test_calc_different_osc_freqs_produce_different_results(self) -> None:
        config_a = FrequencyCalculationConfig(osc_freq_hz=26_000_000)
        config_b = FrequencyCalculationConfig(osc_freq_hz=38_400_000)
        result_a = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config_a, 415000)
        result_b = Rfm9xSx127xHandler.calc_freq_registers_for_khz(config_b, 415000)
        assert result_a != result_b

    def test_config_is_frozen_dataclass(self) -> None:
        config = FrequencyCalculationConfig(osc_freq_hz=32_000_000)
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.osc_freq_hz = 10_000_000

    def test_config_default_none(self) -> None:
        config = FrequencyCalculationConfig()
        assert config.osc_freq_hz is None
