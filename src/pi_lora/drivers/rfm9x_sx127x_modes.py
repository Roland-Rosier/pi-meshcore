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

"""RFM9x/SX127x device mode classes using the GoF State pattern.

Defines immutable device operating modes for LoRa modules on Raspberry Pi.
Each mode class stores its bit pattern at the class level via a metaclass,
preventing runtime modification or monkey-patching.

Bit layout of RegOpMode:
  - Bits 0-2: Mode value (SLEEP, STANDBY, FSTX, etc.)
  - Bit 3: LF mode flag
  - Bit 4-5: Housekeeping states
  - Bit 7: LoRa mode flag (0x80 = LoRa, 0x00 = FSK/OOK)
"""

from enum import Enum, IntFlag
from typing import Any


class RegisterLayout:
    """Comprehensive SX127x register map per datasheet.

    Each nested class is an IntFlag defining bit fields for one hardware register.
    Values are masks/shift targets matching the Semtech/SX127x spec.
    """

    class RegOpMode(IntFlag):
        """Register OpMode -- bits 0-7 of the operation mode register."""

        MASK_MODE = 0x07
        MASK_META = 0x70
        MASK_LORA = 0x80
        BIT_LF = 0x08

    class RegFrf(IntFlag):
        """Register Frf -- frequency configuration."""

        MASK_FRF = 0xFFFFFFFF

    class RegPaConfig(IntFlag):
        """Register PaConfig -- pause configuration."""

        MASK_PA = 0xFFFF

    class RegOcp(IntFlag):
        """Register Ocp -- operating control parameter."""

        MASK_OCP = 0xFFFF

    class RegLna(IntFlag):
        """Register Lna -- line number address."""

        MASK_LNA = 0xFFFF

    class RegFifoAddrPtr(IntFlag):
        """Register FifoAddrPtr -- FIFO address pointer."""

        MASK_PTR = 0xFFFF

    class RegFifoTxBaseAddr(IntFlag):
        """Register FifoTxBaseAddr -- TX base address."""

        MASK_BASE = 0xFFFFFFFF

    class RegFifoRxBaseAddr(IntFlag):
        """Register FifoRxBaseAddr -- RX base address."""

        MASK_BASE = 0xFFFFFFFF

    class RegFifoRxCurrentAddr(IntFlag):
        """Register FifoRxCurrentAddr -- RX current address."""

        MASK_CURR_ADDR = 0xFFFFFFFF

    class RegIrqFlagsMask(IntFlag):
        """Register IrqFlagsMask -- interrupt request flags mask."""

        MASK_IRQ = 0xFFFF

    class RegIrqFlags(IntFlag):
        """Register IrqFlags -- interrupt request flags."""

        MASK_IRQ = 0xFFFF

    class RegRxNbBytes(IntFlag):
        """Register RxNbBytes -- RX number of bytes."""

        MASK_NB_BYTES = 0xFFFF

    class RegRxHeaderCntValueMsb(IntFlag):
        """Register RxHeaderCntValueMsb -- RX header count MSB."""

        MASK_MSB = 0xFFFF

    class RegRxHeaderCntValueLsb(IntFlag):
        """Register RxHeaderCntValueLsb -- RX header count LSB."""

        MASK_LSB = 0xFFFF

    class RegRxPacketCntValueMsb(IntFlag):
        """Register RxPacketCntValueMsb -- RX packet count MSB."""

        MASK_MSB = 0xFFFF

    class RegRxPacketCntValueLsb(IntFlag):
        """Register RxPacketCntValueLsb -- RX packet count LSB."""

        MASK_LSB = 0xFFFF

    class RegModemStat(IntFlag):
        """Register ModemStat -- modulation status."""

        MASK_STAT = 0xFFFF

    class RegPktSnrValue(IntFlag):
        """Register PktSnrValue -- packet SNR value."""

        MASK_SNR = 0xFFFFFFFF

    class RegPktRssiValue(IntFlag):
        """Register PktRssiValue -- packet RSSI value."""

        MASK_RSSI = 0xFFFFFFFF

    class RegRssiValue(IntFlag):
        """Register RssiValue -- RSSI value."""

        MASK_RSSI = 0xFFFFFFFF

    class RegHopChannel(IntFlag):
        """Register HopChannel -- hop channel."""

        MASK_CHANNEL = 0xFFFF

    class RegModemConfig1(IntFlag):
        """Register ModemConfig1 -- modulation config 1."""

        MASK_CFG = 0xFFFFFFFF

    class RegModemConfig2(IntFlag):
        """Register ModemConfig2 -- modulation config 2."""

        MASK_CFG = 0xFFFFFFFF

    class RegSymbTimeoutLsb(IntFlag):
        """Register SymbTimeoutLsb -- symbol timeout LSB."""

        MASK_LSB = 0xFFFF

    class RegPreambleMsb(IntFlag):
        """Register PreambleMsb -- preamble MSB."""

        MASK_MSB = 0xFFFF

    class RegPreambleLsb(IntFlag):
        """Register PreambleLsb -- preamble LSB."""

        MASK_LSB = 0xFFFF

    class RegPayloadLength(IntFlag):
        """Register PayloadLength -- payload length."""

        MASK_LEN = 0xFFFF

    class RegMaxPayloadLength(IntFlag):
        """Register MaxPayloadLength -- max payload length."""

        MASK_MAX_LEN = 0xFFFF

    class RegHopPeriod(IntFlag):
        """Register HopPeriod -- hop period."""

        MASK_PERIOD = 0xFFFFFFFF

    class RegFifoRxByteAddr(IntFlag):
        """Register FifoRxByteAddr -- RX byte address."""

        MASK_ADDR = 0xFFFFFFFF

    class RegModemConfig3(IntFlag):
        """Register ModemConfig3 -- modulation config 3."""

        MASK_CFG = 0xFFFFFFFF

    class RegFeiMsb(IntFlag):
        """Register FeiMsb -- FEI MSB."""

        MASK_MSB = 0xFFFF

    class RegFeiMib(IntFlag):
        """Register FeiMib -- FEI MIB."""

        MASK_MIB = 0xFFFF

    class RegFeiLsb(IntFlag):
        """Register FeiLsb -- FEI LSB."""

        MASK_LSB = 0xFFFF

    class RegDetectOptimize(IntFlag):
        """Register DetectOptimize -- detection optimize."""

        MASK_OPT = 0xFFFF

    class RegInvertIQ(IntFlag):
        """Register InvertIQ -- invert IQ."""

        MASK_INVERT = 0x01

    class RegDetectionThreshold(IntFlag):
        """Register DetectionThreshold -- detection threshold."""

        MASK_THRESH = 0xFFFFFFFF

    class RegSyncWord(IntFlag):
        """Register SyncWord -- sync word."""

        MASK_WORD = 0xFFFFFFFF

    class RegDioMapping1(IntFlag):
        """Register DioMapping1 -- DIO mapping 1."""

        MASK_MAP = 0xFFFFFFFF

    class RegDioMapping2(IntFlag):
        """Register DioMapping2 -- DIO mapping 2."""

        MASK_MAP = 0xFFFFFFFF

    class RegVersion(IntFlag):
        """Register Version -- device version."""

        MASK_VER = 0xFFFF

    class RegTcxo(IntFlag):
        """Register Tcxo -- TCXO."""

        MASK_TCXO = 0xFFFFFFFF

    class RegPaDac(IntFlag):
        """Register PaDac -- PA DAC."""

        MASK_DAC = 0xFFFFFFFF

    class RegFormerTemp(IntFlag):
        """Register FormerTemp -- former temperature."""

        MASK_TEMP = 0xFFFFFFFF

    class RegBitRateFrac(IntFlag):
        """Register BitRateFrac -- bit rate fraction."""

        MASK_RATE = 0xFFFF

    class RegAgcRef(IntFlag):
        """Register AgcRef -- AGC reference."""

        MASK_REF = 0xFFFFFFFF

    class RegAgcThresh1(IntFlag):
        """Register AgcThresh1 -- AGC threshold 1."""

        MASK_THRESH = 0xFFFFFFFF

    class RegAgcThresh2(IntFlag):
        """Register AgcThresh2 -- AGC threshold 2."""

        MASK_THRESH = 0xFFFFFFFF

    class RegAgcThresh3(IntFlag):
        """Register AgcThresh3 -- AGC threshold 3."""

        MASK_THRESH = 0xFFFFFFFF

    class RegPll(IntFlag):
        """Register Pll -- PLL."""

        MASK_PLL = 0xFFFFFFFF


class StateBits(Enum):
    """Immutable bit patterns for all device states."""

    FSK_OOK_SLEEP = 0x00
    LORA_SLEEP = 0x08
    FSK_OOK_STANDBY = 0x01
    LORA_STANDBY = 0x09
    FSK_OOK_FSTX = 0x02
    LORA_FSTX = 0x0A
    FSK_OOK_FSRX = 0x04
    LORA_FSRX = 0x0C
    FSK_OOK_TX = 0x03
    LORA_TX = 0x0B
    FSK_OOK_RX = 0x05
    LORA_RXCONTINUOUS = 0x0D
    LORA_RXSINGLE = 0x0E
    LORA_CAD = 0x0F
    ERROR_STATE = 0x10
    NOT_A_RFM9X_SX127X_DEVICE = 0x20
    UNDEFINED_STATE = 0x30
    UNKNOWN_STATE = 0x40
    RESET_STATE = 0x50


class ModeBits(Enum):
    """Lower 3 bits of RegOpMode -- operational mode classification."""

    SLEEP_OR_ERROR_OR_NOT_A_DEVICE_OR_UNKNOWN_OR_RESET = 0x00
    STANDBY = 0x01
    FSTX = 0x02
    TX = 0x03
    FSRX = 0x04
    RX_OR_RXCONTINUOUS = 0x05
    RXSINGLE = 0x06
    CAD = 0x07


class MetaModeBits(Enum):
    """Bits 4-6 of StateBits.value -- housekeeping state classification."""

    DEVICE_IN_KNOWN_MODE = 0x00
    ERROR_STATE = 0x01
    NOT_A_RFM9X_SX127X_DEVICE = 0x02
    UNDEFINED_STATE = 0x03
    UNKNOWN_STATE = 0x04
    RESET_STATE = 0x05


class LoraMode(Enum):
    """LoRa mode flag (bit 3 of internal StateBits representation)."""

    FSK_OOK = False
    LORA = True
    LORA_STATE_BIT = 0x08


class _ConstantsMeta(type):
    """Metaclass providing read-only class-level getters for mode constants.

    Each subclass defines a locally-scoped _Constants(Enum) with STATE_BITS set
    to the appropriate StateBits member. The metaclass provides immutable
    class-level accessors: STATE_BITS, MODE_BITS, META_MODE_BITS, and LORA_MODE.
    Reassignment of these class-level properties raises AttributeError.
    """

    @property
    def STATE_BITS(cls) -> StateBits:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        return StateBits(raw.value if isinstance(raw, StateBits) else raw)

    @property
    def MODE_BITS(cls) -> ModeBits:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        bits = raw.value if isinstance(raw, StateBits) else raw
        raw_mode: int = bits & RegisterLayout.RegOpMode.MASK_MODE
        return ModeBits(raw_mode)

    @property
    def META_MODE_BITS(cls) -> MetaModeBits:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        bits = raw.value if isinstance(raw, StateBits) else raw
        raw_meta: int = (bits & RegisterLayout.RegOpMode.MASK_META) >> 4
        return MetaModeBits(raw_meta)

    @property
    def LORA_MODE(cls) -> LoraMode:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        bits = raw.value if isinstance(raw, StateBits) else raw
        mask_result: int = bits & LoraMode.LORA_STATE_BIT.value
        return LoraMode.LORA if mask_result else LoraMode.FSK_OOK

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(
            f"Cannot set {name} on class {self.__name__}; all mode constants are immutable."
        )


class Rfm9xSx127xMode(metaclass=_ConstantsMeta):
    """Base class for RFM9x/SX127x device operating modes.

    Each concrete subclass defines a locally-scoped _Constants(Enum) with
    STATE_BITS set to the appropriate StateBits member. The metaclass provides
    immutable class-level accessors: STATE_BITS, MODE_BITS, META_MODE_BITS,
    and LORA_MODE.
    """

    class _Constants(Enum):
        STATE_BITS = StateBits.UNDEFINED_STATE

    def on_entry(self) -> None:
        """Called when the device is entered into this mode."""
        pass

    def on_exit(self) -> None:
        """Called when the device is exited from this mode."""
        pass


class ErrorState(Rfm9xSx127xMode):
    """Pseudo-state indicating unrecoverable error (0x10)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.ERROR_STATE


class NotARfm9xSx127xDeviceState(Rfm9xSx127xMode):
    """Pseudo-state indicating device is not RFM9X/SX127X (0x20)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.NOT_A_RFM9X_SX127X_DEVICE


class UndefinedState(Rfm9xSx127xMode):
    """Pseudo-state for completely undefined state (0x30)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.UNDEFINED_STATE


class UnknownState(Rfm9xSx127xMode):
    """Pseudo-state for lost track of device state (0x40)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.UNKNOWN_STATE


class ResetState(Rfm9xSx127xMode):
    """Pseudo-state for resetting device to known state (0x50)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.RESET_STATE


class FskOokSleepState(Rfm9xSx127xMode):
    """FSK/OOK Sleep mode (0x00)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_SLEEP


class LoraSleepState(Rfm9xSx127xMode):
    """LoRa Sleep mode (0x08)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_SLEEP


class FskOokStandbyState(Rfm9xSx127xMode):
    """FSK/OOK Standby mode (0x01)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_STANDBY


class LoraStandbyState(Rfm9xSx127xMode):
    """LoRa Standby mode (0x09)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_STANDBY


class FskOokFstxState(Rfm9xSx127xMode):
    """FSK/OOK FSTX mode (0x02)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_FSTX


class LoraFstxState(Rfm9xSx127xMode):
    """LoRa FSTX mode (0x0A)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_FSTX


class FskOokFsrxState(Rfm9xSx127xMode):
    """FSK/OOK FSRX mode (0x04)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_FSRX


class LoraFsrxState(Rfm9xSx127xMode):
    """LoRa FSRX mode (0x0C)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_FSRX


class FskOokTxState(Rfm9xSx127xMode):
    """FSK/OOK TX mode (0x03)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_TX


class LoraTxState(Rfm9xSx127xMode):
    """LoRa TX mode (0x0B)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_TX


class FskOokRxState(Rfm9xSx127xMode):
    """FSK/OOK RX mode (0x05)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.FSK_OOK_RX


class LoraRxContinuousState(Rfm9xSx127xMode):
    """LoRa RX continuous mode (0x0D)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_RXCONTINUOUS


class LoraRxSingleState(Rfm9xSx127xMode):
    """LoRa RX single mode (0x0E)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_RXSINGLE


class LoraCadState(Rfm9xSx127xMode):
    """LoRa CAD mode (0x0F)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_CAD


class StateBitsMapping(Enum):
    FSK_OOK_SLEEP = FskOokSleepState
    LORA_SLEEP = LoraSleepState
    FSK_OOK_STANDBY = FskOokStandbyState
    LORA_STANDBY = LoraStandbyState
    FSK_OOK_FSTX = FskOokFstxState
    LORA_FSTX = LoraFstxState
    FSK_OOK_FSRX = FskOokFsrxState
    LORA_FSRX = LoraFsrxState
    FSK_OOK_TX = FskOokTxState
    LORA_TX = LoraTxState
    FSK_OOK_RX = FskOokRxState
    LORA_RXCONTINUOUS = LoraRxContinuousState
    LORA_RXSINGLE = LoraRxSingleState
    LORA_CAD = LoraCadState
    ERROR_STATE = ErrorState
    NOT_A_RFM9X_SX127X_DEVICE = NotARfm9xSx127xDeviceState
    UNDEFINED_STATE = UndefinedState
    UNKNOWN_STATE = UnknownState
    RESET_STATE = ResetState

    @classmethod
    def from_bits(cls, bits: StateBits) -> "StateBitsMapping":
        # mypy accepts looking up by .name string safely
        return cls[bits.name]
