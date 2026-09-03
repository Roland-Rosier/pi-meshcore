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

"""Tests for RFM9x/SX127x device mode classes."""

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_modes import (
    ErrorState,
    FskOokFsrxState,
    FskOokFstxState,
    FskOokRxState,
    FskOokSleepState,
    FskOokStandbyState,
    FskOokTxState,
    LoraCadState,
    LoraFsrxState,
    LoraFstxState,
    LoraMode,
    LoraRxcontinuousState,
    LoraRxingleState,
    LoraSleepState,
    LoraStandbyState,
    LoraTxState,
    MetaModeBits,
    ModeBits,
    NotARfm9xSx127xDeviceState,
    ResetState,
    Rfm9xSx127xMode,
    StateBits,
    UndefinedState,
    UnknownState,
)


class TestRfm9xSx127xMode:
    """Test suite for base class and metaclass behavior."""

    def test_unknown_state_class_attributes(self) -> None:
        assert type(UnknownState.STATE_BITS) is StateBits
        assert UnknownState.STATE_BITS.value == 0x40
        assert UnknownState.MODE_BITS.value == 0x00
        assert UnknownState.META_MODE_BITS.value == 0x04
        assert type(UnknownState.LORA_MODE) is LoraMode
        assert UnknownState.LORA_MODE.value is False

    def test_reset_state_class_attributes(self) -> None:
        assert type(ResetState.STATE_BITS) is StateBits
        assert ResetState.STATE_BITS.value == 0x50
        assert ResetState.MODE_BITS.value == 0x00
        assert ResetState.META_MODE_BITS.value == 0x05
        assert type(ResetState.LORA_MODE) is LoraMode
        assert ResetState.LORA_MODE.value is False

    def test_fsk_ook_sleep_state_class_attributes(self) -> None:
        assert type(FskOokSleepState.STATE_BITS) is StateBits
        assert FskOokSleepState.STATE_BITS.value == 0x00
        assert FskOokSleepState.MODE_BITS.value == 0x00
        assert FskOokSleepState.META_MODE_BITS.value == 0x00
        assert type(FskOokSleepState.LORA_MODE) is LoraMode
        assert FskOokSleepState.LORA_MODE.value is False

    def test_lora_sleep_state_class_attributes(self) -> None:
        assert type(LoraSleepState.STATE_BITS) is StateBits
        assert LoraSleepState.STATE_BITS.value == 0x08
        assert LoraSleepState.MODE_BITS.value == 0x00
        assert LoraSleepState.META_MODE_BITS.value == 0x00
        assert type(LoraSleepState.LORA_MODE) is LoraMode
        assert LoraSleepState.LORA_MODE.value is True

    def test_instantiation(self) -> None:
        unknown = UnknownState()
        reset = ResetState()
        sleep = FskOokSleepState()

        assert type(type(unknown).STATE_BITS) is StateBits
        assert type(unknown).STATE_BITS.value == 0x40
        assert type(reset).STATE_BITS.value == 0x50
        assert type(sleep).STATE_BITS.value == 0x00

    def test_on_entry_on_exit(self) -> None:
        mode = UnknownState()
        assert callable(mode.on_entry)
        assert callable(mode.on_exit)
        mode.on_entry()
        mode.on_exit()


class TestMetaModeBitsExtraction:
    """Test META_MODE_BITS extraction matches expected bit patterns."""

    def test_reset_state_meta_bits(self) -> None:
        # ResetState = 0x50, (0x50 & 0x70) >> 4 = 0x05 → RESET_STATE
        assert ResetState.META_MODE_BITS.value == 0x05

    def test_unknown_state_meta_bits(self) -> None:
        # UnknownState = 0x40, (0x40 & 0x70) >> 4 = 0x04 → UNKNOWN_STATE
        assert UnknownState.META_MODE_BITS.value == 0x04

    def test_error_state_meta_bits(self) -> None:
        # ErrorState = 0x10, (0x10 & 0x70) >> 4 = 0x01 → ERROR_STATE
        assert ErrorState.META_MODE_BITS.value == 0x01

    def test_not_a_rfm9x_meta_bits(self) -> None:
        # NotARfm9xSx127xDeviceState = 0x20, (0x20 & 0x70) >> 4 = 0x02 → NOT_A_RFM9X_SX127X_DEVICE
        assert NotARfm9xSx127xDeviceState.META_MODE_BITS.value == 0x02

    def test_undefined_meta_bits(self) -> None:
        # UndefinedState = 0x30, (0x30 & 0x70) >> 4 = 0x03 → UNDEFINED_STATE
        assert UndefinedState.META_MODE_BITS.value == 0x03

    def test_fsk_ook_sleep_meta_bits(self) -> None:
        # FskOokSleepState = 0x00, (0x00 & 0x70) >> 4 = 0x00 → DEVICE_IN_KNOWN_MODE
        assert FskOokSleepState.META_MODE_BITS.value == 0x00

    def test_lora_sleep_meta_bits(self) -> None:
        # LoraSleepState = 0x08, (0x08 & 0x70) >> 4 = 0x00 → DEVICE_IN_KNOWN_MODE
        assert LoraSleepState.META_MODE_BITS.value == 0x00

    def test_all_real_modes_have_meta_device_known(self) -> None:
        """All real device modes (0x00-0x0F) should have META_MODE_BITS = 0x00."""
        real_mode_classes: list[type[Rfm9xSx127xMode]] = [
            FskOokSleepState, LoraSleepState,
            FskOokStandbyState, LoraStandbyState,
            FskOokFstxState, LoraFstxState,
            FskOokFsrxState, LoraFsrxState,
            FskOokTxState, LoraTxState,
            FskOokRxState, LoraRxcontinuousState, LoraRxingleState,
            LoraCadState,
        ]
        for cls in real_mode_classes:
            assert cls.META_MODE_BITS.value == 0x00, (
                f"{cls.__name__} ({cls.STATE_BITS.value:02x}) should have META=0, got {cls.META_MODE_BITS.value}"
            )

    def test_all_pseudo_states_map_correctly(self) -> None:
        """All pseudo-states should map to their corresponding MetaModeBits."""
        expected: dict[type[Rfm9xSx127xMode], int] = {
            ErrorState: 0x01,
            NotARfm9xSx127xDeviceState: 0x02,
            UndefinedState: 0x03,
            UnknownState: 0x04,
            ResetState: 0x05,
        }
        for cls, expected_value in expected.items():
            assert cls.META_MODE_BITS.value == expected_value, (
                f"{cls.__name__} ({cls.STATE_BITS.value:02x}) should have META={expected_value:01x}, got {cls.META_MODE_BITS.value}"
            )


class TestFskOokModes:
    """Test FSK/OOK mode classes (bit 7 = 0)."""

    def test_fsk_ook_sleep(self) -> None:
        assert type(FskOokSleepState.STATE_BITS) is StateBits
        assert FskOokSleepState.STATE_BITS.value == 0x00
        assert FskOokSleepState.MODE_BITS.value == 0x00
        assert FskOokSleepState.LORA_MODE.value is False

    def test_fsk_ook_standby(self) -> None:
        assert type(FskOokStandbyState.STATE_BITS) is StateBits
        assert FskOokStandbyState.STATE_BITS.value == 0x01
        assert FskOokStandbyState.MODE_BITS.value == 0x01
        assert FskOokStandbyState.LORA_MODE.value is False

    def test_fsk_ook_fstx(self) -> None:
        assert type(FskOokFstxState.STATE_BITS) is StateBits
        assert FskOokFstxState.STATE_BITS.value == 0x02
        assert FskOokFstxState.MODE_BITS.value == 0x02
        assert FskOokFstxState.LORA_MODE.value is False

    def test_fsk_ook_tx(self) -> None:
        assert type(FskOokTxState.STATE_BITS) is StateBits
        assert FskOokTxState.STATE_BITS.value == 0x03
        assert FskOokTxState.MODE_BITS.value == 0x03
        assert FskOokTxState.LORA_MODE.value is False

    def test_fsk_ook_fsrx(self) -> None:
        assert type(FskOokFsrxState.STATE_BITS) is StateBits
        assert FskOokFsrxState.STATE_BITS.value == 0x04
        assert FskOokFsrxState.MODE_BITS.value == 0x04
        assert FskOokFsrxState.LORA_MODE.value is False

    def test_fsk_ook_rx(self) -> None:
        assert type(FskOokRxState.STATE_BITS) is StateBits
        assert FskOokRxState.STATE_BITS.value == 0x05
        assert FskOokRxState.MODE_BITS.value == 0x05
        assert FskOokRxState.LORA_MODE.value is False


class TestLoraModes:
    """Test LoRa mode classes (bit 7 = 1)."""

    def test_lora_sleep(self) -> None:
        assert type(LoraSleepState.STATE_BITS) is StateBits
        assert LoraSleepState.STATE_BITS.value == 0x08
        assert LoraSleepState.MODE_BITS.value == 0x00
        assert LoraSleepState.LORA_MODE.value is True

    def test_lora_standby(self) -> None:
        assert type(LoraStandbyState.STATE_BITS) is StateBits
        assert LoraStandbyState.STATE_BITS.value == 0x09
        assert LoraStandbyState.MODE_BITS.value == 0x01
        assert LoraStandbyState.LORA_MODE.value is True

    def test_lora_fstx(self) -> None:
        assert type(LoraFstxState.STATE_BITS) is StateBits
        assert LoraFstxState.STATE_BITS.value == 0x0A
        assert LoraFstxState.MODE_BITS.value == 0x02
        assert LoraFstxState.LORA_MODE.value is True

    def test_lora_fsrx(self) -> None:
        assert type(LoraFsrxState.STATE_BITS) is StateBits
        assert LoraFsrxState.STATE_BITS.value == 0x0C
        assert LoraFsrxState.MODE_BITS.value == 0x04
        assert LoraFsrxState.LORA_MODE.value is True

    def test_lora_tx(self) -> None:
        assert type(LoraTxState.STATE_BITS) is StateBits
        assert LoraTxState.STATE_BITS.value == 0x0B
        assert LoraTxState.MODE_BITS.value == 0x03
        assert LoraTxState.LORA_MODE.value is True

    def test_lora_rx_continuous(self) -> None:
        assert type(LoraRxcontinuousState.STATE_BITS) is StateBits
        assert LoraRxcontinuousState.STATE_BITS.value == 0x0D
        assert LoraRxcontinuousState.MODE_BITS.value == 0x05
        assert LoraRxcontinuousState.LORA_MODE.value is True

    def test_lora_rx_single(self) -> None:
        assert type(LoraRxingleState.STATE_BITS) is StateBits
        assert LoraRxingleState.STATE_BITS.value == 0x0E
        assert LoraRxingleState.MODE_BITS.value == 0x06
        assert LoraRxingleState.LORA_MODE.value is True

    def test_lora_cad(self) -> None:
        assert type(LoraCadState.STATE_BITS) is StateBits
        assert LoraCadState.STATE_BITS.value == 0x0F
        assert LoraCadState.MODE_BITS.value == 0x07
        assert LoraCadState.LORA_MODE.value is True


class TestImmutability:
    """Test that state constants are truly immutable at the class level."""

    def test_state_bits_immutable(self) -> None:
        with pytest.raises(AttributeError):
            UnknownState.STATE_BITS = StateBits.RESET  # type: ignore[assignment]

    def test_mode_bits_immutable(self) -> None:
        with pytest.raises(AttributeError):
            FskOokSleepState.MODE_BITS = ModeBits.STANDBY  # type: ignore[assignment]

    def test_lora_mode_immutable(self) -> None:
        with pytest.raises(AttributeError):
            FskOokSleepState.LORA_MODE = LoraMode.LORA  # type: ignore[assignment]

    def test_meta_mode_bits_immutable(self) -> None:
        with pytest.raises(AttributeError):
            FskOokSleepState.META_MODE_BITS = MetaModeBits.DEVICE_IN_KNOWN_MODE  # type: ignore[assignment]


class TestBaseClassBehavior:
    """Test base class methods and inheritance."""

    def test_base_on_entry_exit_noop(self) -> None:
        mode = Rfm9xSx127xMode()
        mode.on_entry()
        mode.on_exit()

    def test_subclass_inherits_base_methods(self) -> None:
        state = UnknownState()
        assert hasattr(state, 'on_entry')
        assert hasattr(state, 'on_exit')
        state.on_entry()
        state.on_exit()

    def test_all_19_states_exist(self) -> None:
        expected_classes: list[type[Rfm9xSx127xMode]] = [
            ErrorState,
            NotARfm9xSx127xDeviceState,
            UndefinedState,
            UnknownState,
            ResetState,
            FskOokSleepState,
            LoraSleepState,
            FskOokStandbyState,
            LoraStandbyState,
            FskOokFstxState,
            LoraFstxState,
            FskOokFsrxState,
            LoraFsrxState,
            FskOokTxState,
            LoraTxState,
            FskOokRxState,
            LoraRxcontinuousState,
            LoraRxingleState,
            LoraCadState,
        ]
        for cls in expected_classes:
            instance = cls()
            assert isinstance(instance, Rfm9xSx127xMode)
            assert type(cls.STATE_BITS) is StateBits
            assert type(cls.MODE_BITS) is ModeBits
            assert type(cls.META_MODE_BITS) is MetaModeBits
            assert type(cls.LORA_MODE) is LoraMode


class TestStateBitsEnum:
    """Test the StateBits enum values."""

    def test_all_state_bits_values(self) -> None:
        expected: dict[StateBits, int] = {
            StateBits.FSK_OOK_SLEEP: 0x00,
            StateBits.LORA_SLEEP: 0x08,
            StateBits.FSK_OOK_STANDBY: 0x01,
            StateBits.LORA_STANDBY: 0x09,
            StateBits.FSK_OOK_FSTX: 0x02,
            StateBits.LORA_FSTX: 0x0A,
            StateBits.FSK_OOK_FSRX: 0x04,
            StateBits.LORA_FSRX: 0x0C,
            StateBits.FSK_OOK_TX: 0x03,
            StateBits.LORA_TX: 0x0B,
            StateBits.FSK_OOK_RX: 0x05,
            StateBits.LORA_RXCONTINUOUS: 0x0D,
            StateBits.LORA_RXSINGLE: 0x0E,
            StateBits.LORA_CAD: 0x0F,
            StateBits.ERROR_STATE: 0x10,
            StateBits.NOT_A_RFM9X_SX127X_DEVICE: 0x20,
            StateBits.UNDEFINED_STATE: 0x30,
            StateBits.UNKNOWN_STATE: 0x40,
            StateBits.RESET_STATE: 0x50,
        }
        for member, expected_value in expected.items():
            assert member.value == expected_value


class TestModeBitsEnum:
    """Test the ModeBits enum values."""

    def test_all_mode_bits_values(self) -> None:
        expected: dict[ModeBits, int] = {
            ModeBits.SLEEP_OR_ERROR_OR_NOT_A_DEVICE_OR_UNKNOWN_OR_RESET: 0x00,
            ModeBits.STANDBY: 0x01,
            ModeBits.FSTX: 0x02,
            ModeBits.TX: 0x03,
            ModeBits.FSRX: 0x04,
            ModeBits.RX_OR_RXCONTINUOUS: 0x05,
            ModeBits.RXSINGLE: 0x06,
            ModeBits.CAD: 0x07,
        }
        for member, expected_value in expected.items():
            assert member.value == expected_value


class TestLoraModeEnum:
    """Test the LoraMode enum values."""

    def test_lora_mode_values(self) -> None:
        assert LoraMode.FSK_OOK.value is False
        assert LoraMode.LORA.value is True
