"""Shared type definitions for pi_lora."""

from enum import Enum


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
