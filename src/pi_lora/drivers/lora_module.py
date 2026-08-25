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

import time
from collections.abc import Callable
from contextlib import suppress
from enum import Enum, IntEnum
from typing import Any, Literal

import spidev

REG_OP_MODE = 0x01
MODE_SLEEP = 0x00
MODE_STANDBY = 0x01
BIT_LF_MODE_ON = 0x08
BIT_LORA_MODE_ON: int = 0x80
HIGH_FREQ_KHZ: int = 1015000
LOW_FREQ_KHZ: int = 415000


class LoRaModuleMode(IntEnum):
    """Operating modes for SX127x LoRa modules.

    Values correspond to the Mode field (bits [2:0]) of RegOpMode (0x01).
    When writing to the register, bit 3 (LowFrequencyModeOn) must be
    handled separately and preserved across mode changes.
    """

    SLEEP = 0x00
    STANDBY = 0x01
    FSTX = 0x02
    TX = 0x03
    FSRX = 0x04  # Frequency Synthesiser RX — Mode field value
    RXCONTINUOUS = 0x05
    RXSINGLE = 0x06 # Available in LoRa mode only
    CAD = 0x07 # Available in LoRa mode only

class LoRaModuleTypes(str, Enum):
    UNKNOWN = "Unknown"
    UNKNOWN_OR_COMM_ERROR = "Unknown / Communication Error"
    RFM95W_SX1276 = "RFM95W (High-Band 868MHz / Semtech SX1276)"
    RFM98W_SX1278 = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
    RFM9XW_SX127X_FAMILY = "RFM9XW/SX127X family series"

class LoRaModule:
    """Class to represent and interact with a LoRa module."""

    def __init__(self, ce_pin: int, spi_factory: Callable[[], Any] | None = None):
        """
        Initialize a LoRa module with its own SPI device.

        :param ce_pin: CE pin number (0 or 1)
        :param spi_factory: Optional factory function to create the SPI device for testing
        """
        self.ce_pin = ce_pin
        if spi_factory is not None:
            self.spi_device = spi_factory()
        else:
            self.spi_device = spidev.SpiDev()
        self.silicon_revision: int | None = None
        self.communication_success = False
        self.supports_high_frequency: bool = False
        self.supports_low_frequency: bool = False
        self.unique_value_written = False
        self.unique_msb: int | None = None
        self.unique_mid: int | None = None
        self.unique_lsb: int | None = None
        self.lf_mode_success = False
        self.lf_mode_not_success = False
        self.module_type = LoRaModuleTypes.UNKNOWN.value
        self._initialize()

    def _initialize(self) -> None:
        """Initialize the SPI device and check communication."""
        try:
            # Initialize SPI settings based on CE pin
            bus = 0
            device = self.ce_pin  # CE0 -> device 0, CE1 -> device 1
            self.spi_device.open(bus, device)
            self.spi_device.max_speed_hz = 1000000  # 1 MHz
            self.spi_device.mode = 0b00  # CPOL=0, CPHA=0
            self.spi_device.lsbfirst = False
            self.spi_device.no_cs = False

            # Test communication by reading a register
            test_register = self.read_register(0x12)
            if test_register is not None:
                self.communication_success = True
                self.silicon_revision = self.read_register(0x42)
                self._check_frequency_support()
                self._test_lf_mode_retention()
                self._determine_module_type()
                print(f"SPI device {self.ce_pin} initialized")
        except Exception as e:
            print(f"Initialization error for CE {self.ce_pin}: {e}")

    def __del__(self) -> None:
        """Clean up SPI device when the object is destroyed."""
        try:
            self.spi_device.close()
            print(f"SPI device for CE {self.ce_pin} closed.")
        except Exception as e:
            print(f"Error closing SPI device for CE {self.ce_pin}: {e}")

    def read_register(self, reg_addr: int) -> int | None:
        """
        Read a register from the LoRa module.

        :param reg_addr: Register address to read
        :return: Register value or None if an error occurs
        """
        try:
            # Read register (bit 7 is clear for read)
            # Note that with xfer2, CS is held between blocks in transfer
            response = self.spi_device.xfer2([reg_addr & 0x7F, 0x00])
            time.sleep(0.01)
            return int(response[1])
        except Exception as e:
            print(f"SPI read error for CE {self.ce_pin}: {e}")
            return None

    def write_register(self, reg_addr: int, value: int) -> int | None:
        """
        Write a register to the LoRa module.

        :param reg_addr: Register address to write
        :param value: Value to write
        :return: Register value or None if an error occurs
        """
        try:
            # Write register (bit 7 is set for write)
            # Note that with xfer2, CS is held between blocks in transfer
            response = self.spi_device.xfer2([reg_addr | 0x80, value])
            time.sleep(0.01)
            return int(response[1])
        except Exception as e:
            print(f"SPI write error for CE {self.ce_pin}: {e}")
            return None

    def _write_op_mode(self, mode: LoRaModuleMode) -> None:
        """Write only the Mode field (bits [2:0]) of RegOpMode.

        Preserves all other bits in the register via read-modify-write semantics.

        :param mode: The desired operating mode from LoRaModuleMode enum.
        """
        current_value: int | None = self.read_register(REG_OP_MODE)
        if current_value is None:
            return
        new_value: int = (current_value & ~0x07) | (mode & 0x07)
        self.write_register(REG_OP_MODE, new_value)

    def set_module_mode(self, mode: LoRaModuleMode) -> None:
        """Set the operating mode of the LoRa module via RegOpMode.

        Preserves the LowFrequencyModeOn bit (bit 3) and all reserved bits.

        :param mode: The desired operating mode from LoRaModuleMode enum.
        """
        self._write_op_mode(mode)

    def _set_lf_mode_bit(self) -> None:
        """Set only the LowFrequencyModeOn bit (bit 3) of RegOpMode.

        Preserves all other bits including Mode [2:0] via read-modify-write semantics.
        Used before high-frequency operations to ensure LF mode is disabled.

        :return: None
        """
        current_value: int | None = self.read_register(REG_OP_MODE)
        if current_value is not None:
            hf_value: int = current_value | BIT_LF_MODE_ON
            self.write_register(REG_OP_MODE, hf_value)

    def _clear_lf_mode_bit(self) -> None:
        """Clear only the LowFrequencyModeOn bit (bit 3) of RegOpMode.

        Preserves all other bits including Mode [2:0] via read-modify-write semantics.
        Used before high-frequency operations to ensure LF mode is disabled.

        :return: None
        """
        current_value: int | None = self.read_register(REG_OP_MODE)
        if current_value is not None:
            hf_value: int = current_value & ~BIT_LF_MODE_ON
            self.write_register(REG_OP_MODE, hf_value)

    def _set_lora_mode_bit(self) -> None:
        """Set only the LoRaMode bit (bit 7) of RegOpMode.

        Preserves all other bits including Mode [2:0] and LowFrequencyModeOn (bit 3).
        Used to enable LoRa mode before frequency synthesiser operations.
        """
        current_value: int | None = self.read_register(REG_OP_MODE)
        if current_value is not None:
            new_value: int = current_value | BIT_LORA_MODE_ON
            self.write_register(REG_OP_MODE, new_value)

    def _clear_lora_mode_bit(self) -> None:
        """Clear only the LoRaMode bit (bit 7) of RegOpMode.

        Preserves all other bits including Mode [2:0] and LowFrequencyModeOn (bit 3).
        Used to disable LoRa mode for safety-mode and standard operations.
        """
        current_value: int | None = self.read_register(REG_OP_MODE)
        if current_value is not None:
            new_value: int = current_value & ~BIT_LORA_MODE_ON
            self.write_register(REG_OP_MODE, new_value)

    def _calc_freq_registers_for_khz(self, a_freq_in_khz: int) -> tuple[int, int, int]:
        """Calculate the register values for a requested frequency.

        Assuming that this module is in the RFM9X family:
        1. The Crystal oscillator frequency (FXOSC) is 32MHz
        2. The Frequency synthesiser step (FSTEP) is FXOSC/(2^19) = 61.0 Hz (61.03515625 Hz)
        3. It takes 250 us for the XTAL Osc to wake up
        4. It takes 60 us between freq. synthesiser wake up from standby to PllLock.
        """
        # This gives frequency in micro-Hz * 100.
        freq_hz_times_100000000 = a_freq_in_khz * 100000000000
        # 6103515625 is step frequency in micro-Hz * 100
        # freq_register_value is the multiple of the FSTEP frequency
        freq_register_value = int(freq_hz_times_100000000 / 6103515625)
        lsb = int(freq_register_value & 0xFF)
        mid = int((freq_register_value & 0xFF00) >> 8)
        msb = int((freq_register_value & 0xFF0000) >> 16)
        print(f"Calculated registers for frequency of {a_freq_in_khz} kHz with register values (0x{msb:02X} 0x{mid:02X} 0x{lsb:02X})")
        return (msb, mid, lsb)

    def _read_frequency_registers(self) -> tuple[int|None, int|None, int|None]:
        """Read the frequency registers."""
        msb = self.read_register(0x06)
        mid = self.read_register(0x07)
        lsb = self.read_register(0x08)
        time.sleep(0.01)
        return (msb, mid, lsb)

    # def _write_frequency_registers(self, a_msb: int, a_mid: int, a_lsb: int) -> tuple[int|None, int|None, int|None, int|None]:
    def _write_frequency_registers(self, a_msb: int, a_mid: int, a_lsb: int) -> tuple[int|None, int|None, int|None]:
        """Write the frequency registers.

        The module must already be in SLEEP or STANDBY mode before calling this method.
        """
        # response_mode: int | None = None
        response_msb: int | None = None
        response_mid: int | None = None
        response_lsb: int | None = None
        # Module should already be in sleep mode — no need to set it here.
        response_msb = self.write_register(0x06, a_msb)
        if response_msb is not None:
            response_mid = self.write_register(0x07, a_mid)
        if response_mid is not None:
            # Note: the manual states tha a change in the center frequency will
            # only be taken into account when the least significant byte FrfLsb
            # in RegFrfLsb is written.
            response_lsb = self.write_register(0x08, a_lsb)
        # return (response_mode, response_msb, response_mid, response_lsb)
        return (response_msb, response_mid, response_lsb)

    # def _write_frequency_for_khz(self, a_freq_in_khz: int) -> tuple[int|None, int|None, int|None, int|None]:
    def _write_frequency_for_khz(self, a_freq_in_khz: int) -> tuple[int|None, int|None, int|None]:
        """Write a target frequency to the module.

        The module must already be in SLEEP or STANDBY mode before calling this method.
        """
        (msb, mid, lsb) = self._calc_freq_registers_for_khz(a_freq_in_khz)
        # (w_mode, w_msb, w_mid, w_lsb) = self._write_frequency_registers(msb, mid, lsb)
        (w_msb, w_mid, w_lsb) = self._write_frequency_registers(msb, mid, lsb)
        r_msb = msb if w_msb is not None else None
        r_mid = mid if w_mid is not None else None
        r_lsb = lsb if w_lsb is not None else None
        # return (w_mode, r_msb, r_mid, r_lsb)
        return (r_msb, r_mid, r_lsb)

    def write_and_verify_frequency_for_khz(self, a_freq_in_khz: int) -> tuple[bool, int|None, int|None, int|None, int|None, int|None, int|None]:
        """Write and verify a frequency."""
        verify_success = False
        msb = None
        mid = None
        lsb = None
        # (new_mode, req_msb, req_mid, req_lsb) = self._write_frequency_for_khz(a_freq_in_khz)
        (req_msb, req_mid, req_lsb) = self._write_frequency_for_khz(a_freq_in_khz)
        time.sleep(0.01)  # Allow time for register update
        # if all(ele is not None for ele in (new_mode, req_msb, req_mid, req_lsb)):
        if all(ele is not None for ele in (req_msb, req_mid, req_lsb)):
            (msb, mid, lsb) = self._read_frequency_registers()
            time.sleep(0.01)  # Allow time for register stabilization
            if all(ele is not None for ele in (msb, mid, lsb)) and msb == req_msb and mid == req_mid and lsb == req_lsb:
                verify_success = True
        return (verify_success, req_msb, req_mid, req_lsb, msb, mid, lsb)

    def _check_frequency_support(self) -> None:
        """Check if the module supports high and low frequency settings."""
        # Put module into sleep mode
        self.set_module_mode(LoRaModuleMode.SLEEP)
        time.sleep(0.01)

        # Clear LoRa mode bit for safety
        self._clear_lora_mode_bit()
        time.sleep(0.01)

        # Clear the LF mode bit (for high frequency)
        self._clear_lf_mode_bit()
        time.sleep(0.01)

        # Verify High Frequency (1015- MHz) to see if it supports high frequencies (which *may* indicate RFM95W)
        verify_success = False
        (verify_success, _, _, _, _, _, _) = self.write_and_verify_frequency_for_khz(HIGH_FREQ_KHZ)
        if verify_success:
            self.supports_high_frequency = True

        # Set the LF mode bit (for low frequency)
        self._set_lf_mode_bit()
        time.sleep(0.01)

        # Verify Low Frequency (415 MHz) for RFM98W validation
        verify_success = False
        (verify_success, _, _, _, _, _, _) = self.write_and_verify_frequency_for_khz(LOW_FREQ_KHZ)
        if verify_success:
            self.supports_low_frequency = True

    def _test_lf_mode_retention(self) -> None:
        """Test if LF mode can be set and unset."""
        # The LF Mode Bit might not be retained when switching between Sleep and Standby modes
        # Set LF mode - but this might be the default, so check that it can be re-set again later
        self._write_op_mode(LoRaModuleMode.SLEEP)
        time.sleep(0.01)
        self._clear_lora_mode_bit()  # New: ensure not in LoRa mode
        time.sleep(0.01)
        self._set_lf_mode_bit()
        time.sleep(0.01)
        # Change to STANDBY mode to activate internal logic
        self._write_op_mode(LoRaModuleMode.STANDBY)
        time.sleep(0.01)
        # Re-read the register after mode change
        mod_check = self.read_register(REG_OP_MODE)
        if mod_check is not None:
            self.lf_mode_success = ((mod_check & BIT_LF_MODE_ON) == BIT_LF_MODE_ON)

        # Unset LF mode
        self._write_op_mode(LoRaModuleMode.SLEEP)
        time.sleep(0.01)
        self._clear_lf_mode_bit()
        time.sleep(0.01)
        # Change to STANDBY mode again to activate internal logic
        self._write_op_mode(LoRaModuleMode.STANDBY)
        time.sleep(0.01)
        # Re-read the register after mode change
        mod_check = self.read_register(REG_OP_MODE)
        if mod_check is not None:
            self.lf_mode_not_success = ((mod_check & BIT_LF_MODE_ON) != BIT_LF_MODE_ON)

        # Put the device back into sleep mode with LF_MODE_ON
        self._write_op_mode(LoRaModuleMode.SLEEP)
        time.sleep(0.01)
        self._set_lf_mode_bit()
        time.sleep(0.01)
        # Change to STANDBY mode to activate internal logic
        self._write_op_mode(LoRaModuleMode.STANDBY)
        time.sleep(0.01)
        # Re-read the register after mode change
        mod_check = self.read_register(REG_OP_MODE)
        if mod_check is not None and self.lf_mode_success:
            self.lf_mode_success = ((mod_check & BIT_LF_MODE_ON) == BIT_LF_MODE_ON)
        else:
            self.lf_mode_success = False

        # Put the device back into sleep mode with LF_MODE_ON
        self._write_op_mode(LoRaModuleMode.SLEEP)
        time.sleep(0.01)
        self._clear_lora_mode_bit()  # New: maintain safety mode
        time.sleep(0.01)

    def _determine_module_type(self) -> None:
        """Determine the module type based on silicon revision and LF mode.

        Note: The silicon revision appears to be the same for all modules.
        """
        # if self.silicon_revision == 0x12:
        #     self.module_type = "RFM95W (Semtech SX1276)"
        # elif self.silicon_revision == 0x19:
        #     self.module_type = "RFM98W (Semtech SX1278)"
        # else:
        potentially_multi_band_support = False
        if self.supports_high_frequency and self.supports_low_frequency:
            potentially_multi_band_support = True
        elif self.supports_high_frequency:
            # self.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
            self.module_type = LoRaModuleTypes.RFM95W_SX1276.value
        elif self.supports_low_frequency:
            # self.module_type = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
            self.module_type = LoRaModuleTypes.RFM98W_SX1278.value
        else:
            # self.module_type = "Unknown / Communication Error"
            self.module_type = LoRaModuleTypes.UNKNOWN_OR_COMM_ERROR.value

        if potentially_multi_band_support:
            if self.lf_mode_not_success and self.lf_mode_success:
                # Note an SX1276 can be dropped into a slot reserved for an SX1278 and it will work perfectly at low frequencies
                # But if the pins 21 and 22 are connected to ground, it will fail at high frequencies (like an SX1278 would)
                # Software cannot detect if it is high-frequency capable; transmission has to be attempted to see if that
                # transmission fails.
                # Note also that being able to select 1010 MHz suggests that it is *not* an SX1279
                # Note it could be an SX1277, which cannot do all the spreading factors, we might want to detect that
                # self.module_type = "RFM9XW/SX127X family series"
                self.module_type = LoRaModuleTypes.RFM9XW_SX127X_FAMILY.value
            elif self.lf_mode_not_success:
                # self.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
                self.module_type = LoRaModuleTypes.RFM95W_SX1276.value
            elif self.lf_mode_success:
                # self.module_type = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
                self.module_type = LoRaModuleTypes.RFM98W_SX1278.value
            else:
                # self.module_type = "Unknown / Communication Error"
                self.module_type = LoRaModuleTypes.UNKNOWN_OR_COMM_ERROR.value

    def test_unique_value_retention(self, frequency_khz: int) -> bool:
        """
        Test if a unique value can be written and retained.

        :param frequency_khz: Frequency in kHz to test
        :return: True if the value was successfully written and retained, False otherwise
        """
        # Use the existing verification function to write and verify the frequency
        (verify_success, req_msb, req_mid, req_lsb, _, _, _) = self.write_and_verify_frequency_for_khz(frequency_khz)
        # print(f"Tested ({verify_success}) unique value initial retention for frequency of {frequency_khz} kHz with register values (0x{req_msb:02X} 0x{req_mid:02X} 0x{req_lsb:02X})")

        # Save the requested values as instance variables
        self.unique_msb = req_msb
        self.unique_mid = req_mid
        self.unique_lsb = req_lsb

        # Update the unique_value_written flag based on verification result
        self.unique_value_written = verify_success

        return self.unique_value_written

    def verify_unique_value_retention(self) -> bool:
        """
        Verify that the previously written unique values are still present in the frequency registers.

        :return: True if the stored values match and the test was successful, False otherwise
        """
        # Check if we have previously written unique values
        if self.unique_msb is None or self.unique_mid is None or self.unique_lsb is None:
            return False

        # Check if the test was previously successful
        if not self.unique_value_written:
            return False

        # Read current frequency registers
        (current_msb, current_mid, current_lsb) = self._read_frequency_registers()

        if all(ele is not None for ele in (current_msb, current_mid, current_lsb)):
            # Compare with stored values
            return (current_msb == self.unique_msb and
                    current_mid == self.unique_mid and
                    current_lsb == self.unique_lsb)
        else:
            return False

    # def _perform_extended_detection(self) -> Literal["rfm95w", "rfm98w"] | None:
    def _perform_extended_detection(self) -> Literal[
        "Unknown",
        "RFM95W (High-Band 868MHz / Semtech SX1276)",
        "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
        "RFM9XW/SX127X family series",
    ] | None:
        """Perform PLL lock test at 915 MHz to distinguish RFM95W/SX1276 from RFM98W/SX1278.

        Procedure (per module, in read-only safety mode):
          1a. Put module into SLEEP mode.
          1b. Clear LoRa mode bit (bit 7 of RegOpMode) to ensure device is not in LoRa mode.
          1c. Clear bit 3 (LowFrequencyModeOn) in RegOpMode for HF operation.
          1b. Write 915 MHz (915000 kHz) to frequency registers.
          1e. Set mode to FSRX (frequency synthesiser RX).
          1d. Wait up to 5 iterations, checking RegIrqFlags1 bit 4 for PLL lock.
              Exit loop as soon as a lock is detected (early-exit on first lock).
          1f. Record whether PLL locked in HF mode.
          2a. Put module into SLEEP mode.
          2b. Set bit 3 (LowFrequencyModeOn) in RegOpMode for LF operation.
          2c. Write 410 MHz (410000 kHz) to frequency registers.
          2d. Set mode to FSRX.
          2e. Wait up to 5 iterations, checking RegIrqFlags1 bit 4 for PLL lock.
              Exit loop as soon as a lock is detected (early-exit on first lock).
          2f. Record whether PLL locked in LF mode.
          3. Determine module type:
              - Neither locked: "Unknown"
              - Both locked: "RFM9XW/SX127X family series"
              - HF only: "RFM95W (High-Band 868MHz / Semtech SX1276)"
              - LF only: "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
          4. Put module back into SLEEP mode and clear LoRa mode bit.

        Returns:
            "Unknown" if neither locked
            "RFM9XW/SX127X family series" if both PLLs locked
            "RFM95W" if only HF PLL locked
            "RFM98W" if only LF PLL locked
            None if communication fails or module is non-functional
        """
        try:
            # ---- Step 1a — Put module into SLEEP mode ----
            self.set_module_mode(LoRaModuleMode.SLEEP)

            # ---- Step 1b — Clear LoRa mode bit ----
            self._clear_lora_mode_bit()
            time.sleep(0.01)  # Allow register update

            # ---- Steps 1c-1f: HF PLL lock test at 915 MHz ----
            # 1c: HF mode already clear from _clear_lf_mode_bit, but set it explicitly
            self._clear_lf_mode_bit()
            time.sleep(0.01)

            # 1d: Write 915 MHz (915000 kHz) to frequency registers
            verified = self.write_and_verify_frequency_for_khz(915000)
            if verified[0] is False:
                return None  # Could not write frequency; module may be non-functional

            time.sleep(0.01)

            # 1e: Set mode to FSRX
            self.set_module_mode(LoRaModuleMode.FSRX)

            # 1f: PLL lock detection — exit as soon as any lock is detected
            hf_locked: bool = False
            for _attempt in range(5):
                time.sleep(0.1)
                irq_flags: int | None = self.read_register(0x3E)  # RegIrqFlags1
                if irq_flags is not None and (irq_flags & 0x10):  # Bit 4 = PLLLock
                    hf_locked = True
                    break  # Early exit — lock detected, no need to wait further

            # ---- Steps 2a-2f: LF PLL lock test at 410 MHz ----
            # 2a: Put module into SLEEP mode
            self.set_module_mode(LoRaModuleMode.SLEEP)

            # 2b: Set LF mode bit
            self._set_lf_mode_bit()
            time.sleep(0.01)

            # 2c: Write 410 MHz (410000 kHz) to frequency registers
            verified = self.write_and_verify_frequency_for_khz(410000)
            if verified[0] is False:
                return None  # Could not write frequency; module may be non-functional

            time.sleep(0.01)

            # 2d: Set mode to FSRX
            self.set_module_mode(LoRaModuleMode.FSRX)

            # 2e-2f: PLL lock detection — exit as soon as any lock is detected
            lf_locked: bool = False
            for _attempt in range(5):
                time.sleep(0.1)
                irq_flags = self.read_register(0x3E)  # RegIrqFlags1
                if irq_flags is not None and (irq_flags & 0x10):  # Bit 4 = PLLLock
                    lf_locked = True
                    break  # Early exit — lock detected, no need to wait further

            # ---- Step 3: Classify module based on PLL lock results ----
            if not (hf_locked or lf_locked):
                return LoRaModuleTypes.UNKNOWN.value
            elif lf_locked and hf_locked:
                return LoRaModuleTypes.RFM9XW_SX127X_FAMILY.value
            elif hf_locked:
                return LoRaModuleTypes.RFM95W_SX1276.value

            return LoRaModuleTypes.RFM98W_SX1278.value

        except Exception:
            return None  # Communication or logic error during detection
        finally:
            # Step 4: Always return to SLEEP and clear LoRa mode
            with suppress(Exception):
                self.set_module_mode(LoRaModuleMode.SLEEP)
                time.sleep(0.1)
                self._clear_lora_mode_bit()
                time.sleep(0.1)












