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

"""Tests for ``Rfm9xSx127xHandler`` stub methods."""



from src.pi_lora.drivers.rfm9x_sx127x_handler import Rfm9xSx127xHandler
from src.pi_lora.drivers.rfm9x_sx127x_modes import ModeBits


class TestRfm9xSx127xHandler:
    """Tests for the ``Rfm9xSx127xHandler`` class and its stub methods."""

    def test_init(self) -> None:
        handler = Rfm9xSx127xHandler()
        assert isinstance(handler, Rfm9xSx127xHandler)

    def test_init_with_kwargs(self) -> None:
        handler = Rfm9xSx127xHandler(dummy_arg=42)
        assert isinstance(handler, Rfm9xSx127xHandler)

    def test_set_module_mode_returns_none(self) -> None:
        handler = Rfm9xSx127xHandler()
        result = handler.set_module_mode(ModeBits.STANDBY)
        assert result is None

    def test_set_module_mode_with_all_modes(self) -> None:
        handler = Rfm9xSx127xHandler()
        for mode in ModeBits:
            result = handler.set_module_mode(mode)
            assert result is None, (
                f"set_module_mode({mode.name}) should return None, got {result}"
            )

    def test_write_and_verify_frequency_for_khz_returns_all_none(self) -> None:
        handler = Rfm9xSx127xHandler()
        result = handler.write_and_verify_frequency_for_khz(415000)
        assert result == (None, None, None, None, None, None, None)

    def test_write_and_verify_frequency_for_khz_with_various_frequencies(self) -> None:
        handler = Rfm9xSx127xHandler()
        frequencies: list[int] = [0, 1, 415000, 868000, 434000, 9999999]
        for freq in frequencies:
            result = handler.write_and_verify_frequency_for_khz(freq)
            assert result == (None, None, None, None, None, None, None), (
                f"write_and_verify_frequency_for_khz({freq}) should return all None"
            )

    def test_calc_freq_registers_for_khz_returns_all_none(self) -> None:
        handler = Rfm9xSx127xHandler()
        result = handler.calc_freq_registers_for_khz(415000)
        assert result == (None, None, None)

    def test_calc_freq_registers_for_khz_with_various_frequencies(self) -> None:
        handler = Rfm9xSx127xHandler()
        frequencies: list[int] = [0, 1, 415000, 868000, 434000, 9999999]
        for freq in frequencies:
            result = handler.calc_freq_registers_for_khz(freq)
            assert result == (None, None, None), (
                f"calc_freq_registers_for_khz({freq}) should return all None"
            )

    def test_handler_instance_in_module(self) -> None:
        from src.pi_lora.drivers.rfm9x_sx127x_modes import StateBits
        from src.pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        assert hasattr(module, 'handler')
        assert isinstance(module.handler, Rfm9xSx127xHandler)

    def test_handler_methods_accessible_from_module(self) -> None:
        from src.pi_lora.drivers.rfm9x_sx127x_modes import ModeBits, StateBits
        from src.pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

        module = Rfm9xSx127xModule(StateBits.FSK_OOK_SLEEP)
        assert callable(module.handler.set_module_mode)
        assert callable(module.handler.write_and_verify_frequency_for_khz)
        assert callable(module.handler.calc_freq_registers_for_khz)

        result1 = module.handler.set_module_mode(ModeBits.STANDBY)
        assert result1 is None

        result2 = module.handler.write_and_verify_frequency_for_khz(415000)
        assert result2 == (None, None, None, None, None, None, None)

        result3 = module.handler.calc_freq_registers_for_khz(415000)
        assert result3 == (None, None, None)
