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

from enum import Enum
from typing import Any


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
    """LoRa mode flag (bit 7 of RegOpMode)."""

    FSK_OOK = False
    LORA = True


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
        raw_mode: int = bits & 0x07
        return ModeBits(raw_mode)

    @property
    def META_MODE_BITS(cls) -> MetaModeBits:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        bits = raw.value if isinstance(raw, StateBits) else raw
        raw_meta: int = (bits & 0x70) >> 4
        return MetaModeBits(raw_meta)

    @property
    def LORA_MODE(cls) -> LoraMode:
        raw = getattr(cls, '_Constants').STATE_BITS.value  # noqa: B009
        bits = raw.value if isinstance(raw, StateBits) else raw
        mask_result: int = bits & 0x08
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


class LoraRxcontinuousState(Rfm9xSx127xMode):
    """LoRa RX continuous mode (0x0D)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_RXCONTINUOUS


class LoraRxingleState(Rfm9xSx127xMode):
    """LoRa RX single mode (0x0E)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_RXSINGLE


class LoraCadState(Rfm9xSx127xMode):
    """LoRa CAD mode (0x0F)."""

    class _Constants(Enum):
        STATE_BITS = StateBits.LORA_CAD
