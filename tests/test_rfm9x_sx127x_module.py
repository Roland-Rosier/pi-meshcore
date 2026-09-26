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

from tests.spi.mock import MockSpiBusFactory


class TestRfm9xSx127xModule:
    """Tests for the ``Rfm9xSx127xModule`` class."""

    def test_init_with_unknown_state(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        assert isinstance(module.current_state_instance, UnknownState)

    def test_set_current_state_to_fsk_ook_sleep(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)

    def test_set_current_state_back_to_unknown(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)
        module.set_current_state(StateBits.UNKNOWN_STATE)
        assert isinstance(module.current_state_instance, UnknownState)

    def test_set_current_state_to_fsk_ook_sleep_again(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)
        module.set_current_state(StateBits.UNKNOWN_STATE)
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert isinstance(module.current_state_instance, FskOokSleepState)

    def test_is_in_state(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        assert module.is_in_state(StateBits.UNKNOWN_STATE) is True
        assert module.is_in_state(StateBits.FSK_OOK_SLEEP) is False
        module.set_current_state(StateBits.FSK_OOK_SLEEP)
        assert module.is_in_state(StateBits.FSK_OOK_SLEEP) is True
        assert module.is_in_state(StateBits.UNKNOWN_STATE) is False

    def test_is_in_lora_mode(self) -> None:
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        assert module.is_in_lora_mode() is False
        module.set_current_state(StateBits.LORA_SLEEP)
        assert module.is_in_lora_mode() is True

    def test_is_in_fsk_ook_mode(self) -> None:
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        assert module.is_in_fsk_ook_mode() is True
        module.set_current_state(StateBits.LORA_SLEEP)
        assert module.is_in_fsk_ook_mode() is False

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_sleep_returns_true(self) -> None:
        factory = MockSpiBusFactory()
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP, spi_factory=factory)
        module.spi_device_id = 0
        await module.init_spi_bus()
        result: bool = await module.write_and_verify_frequency_for_khz(415000)
        assert result is True
        await module.close_spi()

    @pytest.mark.asyncio
    async def test_write_and_verify_frequency_for_khz_fstx_raises(self) -> None:
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        module.set_current_state(StateBits.FSK_OOK_FSTX)
        with pytest.raises(RuntimeError):
            await module.write_and_verify_frequency_for_khz(415000)

    def test_memory_management(self) -> None:
        module = Rfm9xSx127xModule(StateBits.UNKNOWN_STATE)
        instances = module.state_instances
        del module
        gc.collect()
        assert len(instances) > 0

    @pytest.mark.asyncio
    async def test_spi_bus_injection_and_frequency_write(self) -> None:
        factory = MockSpiBusFactory()
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP, spi_factory=factory)
        module.spi_device_id = 0
        await module.init_spi_bus()
        assert module.spi_bus is not None
        result: bool = await module.write_and_verify_frequency_for_khz(415000)
        assert result is True
        await module.close_spi()
        assert module.spi_bus is None

    def test_module_does_not_instantiate_handler(self) -> None:
        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        assert not hasattr(module, "handler")
        mock_factory = unittest.mock.MagicMock()
        module2 = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP, mock_factory)
        module2.spi_device_id = 0
        module2.ce_number = 0
