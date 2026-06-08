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

from typing import List, Optional, Dict, Tuple
import spidev
import time

REG_OP_MODE = 0x01
MODE_SLEEP = 0x00
MODE_STANDBY = 0x01
BIT_LF_MODE_ON = 0x08

class LoRaModule:
    """Class to represent and interact with a LoRa module."""
    
    def __init__(self, ce_pin: int):
        """
        Initialize a LoRa module with its own SPI device.
        
        :param ce_pin: CE pin number (0 or 1)
        """
        self.ce_pin = ce_pin
        self.spi_device = spidev.SpiDev()
        self.silicon_revision = None
        self.communication_success = False
        self.supports_high_frequency = False
        self.supports_low_frequency = False
        self.unique_value_written = False
        self.unique_msb = None
        self.unique_mid = None
        self.unique_lsb = None
        self.lf_mode_success = False
        self.lf_mode_not_success = False
        self.module_type = "Unknown"
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
    
    def read_register(self, reg_addr: int) -> Optional[int]:
        """
        Read a register from the LoRa module.

        :param reg_addr: Register address to read
        :return: Register value or None if an error occurs
        """
        try:
            # Read register (bit 7 is clear for read)
            response = self.spi_device.xfer2([reg_addr & 0x7F, 0x00])
            time.sleep(0.01)
            return response[1]
        except Exception as e:
            print(f"SPI read error for CE {self.ce_pin}: {e}")
            return None

    def write_register(self, reg_addr: int, value: int) -> Optional[int]:
        """
        Write a register to the LoRa module.

        :param reg_addr: Register address to write
        :param value: Value to write
        :return: Register value or None if an error occurs
        """
        try:
            # Write register (bit 7 is set for write)
            response = self.spi_device.xfer2([reg_addr | 0x80, value])
            time.sleep(0.01)
            return response[1]
        except Exception as e:
            print(f"SPI write error for CE {self.ce_pin}: {e}")
            return None

    def _calc_freq_registers_for_khz(self, a_freq_in_khz: int) -> Tuple[int, int, int]:
        """Calculate the register values for a requested frequency."""
        freq_hz_times_100000000 = a_freq_in_khz * 100000000000
        freq_register_value = int(freq_hz_times_100000000 / 6103515625)
        lsb = int(freq_register_value & 0xFF)
        mid = int((freq_register_value & 0xFF00) >> 8)
        msb = int((freq_register_value & 0xFF0000) >> 16)
        print(f"Calculated registers for frequency of {a_freq_in_khz} kHz with register values (0x{msb:02X} 0x{mid:02X} 0x{lsb:02X})")
        return (msb, mid, lsb)

    def _read_frequency_registers(self) -> Tuple[int, int, int]:
        """Read the frequency registers."""
        msb = self.read_register(0x06)
        mid = self.read_register(0x07)
        lsb = self.read_register(0x08)
        time.sleep(0.01)
        return (msb, mid, lsb)

    def _write_frequency_registers(self, a_msb: int, a_mid: int, a_lsb: int) -> None:
        """Write the frequency registers."""
        # 1. Put the chip into Sleep Mode to allow frequency register changes
        self.write_register(REG_OP_MODE, MODE_SLEEP)
        time.sleep(0.01)
        self.write_register(0x06, a_msb)
        self.write_register(0x07, a_mid)
        self.write_register(0x08, a_lsb)
        time.sleep(0.01)

    def _write_frequency_for_khz(self, a_freq_in_khz: int) -> Tuple[int, int, int]:
        """Write a target frequency to the module."""
        (msb, mid, lsb) = self._calc_freq_registers_for_khz(a_freq_in_khz)
        self._write_frequency_registers(msb, mid, lsb)
        return (msb, mid, lsb)

    def _write_and_verify_frequency_for_khz(self, a_freq_in_khz: int) -> Tuple[bool, int, int, int, int, int, int]:
        """Write and verify a frequency."""
        verify_success = False
        (req_msb, req_mid, req_lsb) = self._write_frequency_for_khz(a_freq_in_khz)
        time.sleep(0.01)  # Allow time for register update
        (msb, mid, lsb) = self._read_frequency_registers()
        time.sleep(0.01)  # Allow time for register stabilization
        if msb == req_msb and mid == req_mid and lsb == req_lsb:
            verify_success = True
        return (verify_success, req_msb, req_mid, req_lsb, msb, mid, lsb)

    def _check_frequency_support(self) -> None:
        """Check if the module supports high and low frequency settings."""
        # Verify High Frequency (1015- MHz) to see if it supports high frequencies (which *may* indicate RFM95W)
        high_freq = {"supported": False, "freq_type": "high", "freq_khz": 1015000}
        (verify_success, _, _, _, _, _, _) = self._write_and_verify_frequency_for_khz(high_freq["freq_khz"])
        if verify_success:
            self.supports_high_frequency = True

        # Verify Low Frequency (415 MHz) for RFM98W validation
        low_freq = {"supported": False, "freq_type": "low", "freq_khz": 415000}
        (verify_success, _, _, _, _, _, _) = self._write_and_verify_frequency_for_khz(low_freq["freq_khz"])
        if verify_success:
            self.supports_low_frequency = True

    def _test_lf_mode_retention(self) -> None:
        """Test if LF mode can be set and unset."""
        # The LF Mode Bit might not be retained when switching between Sleep and Standby modes
        # Set LF mode
        self.write_register(REG_OP_MODE, MODE_SLEEP | BIT_LF_MODE_ON)
        time.sleep(0.01)
        # Change to STANDBY mode to activate internal logic
        self.write_register(REG_OP_MODE, MODE_STANDBY | BIT_LF_MODE_ON)
        time.sleep(0.01)
        # Re-read the register after mode change
        mod_check = self.read_register(REG_OP_MODE)
        if mod_check is not None:
            self.lf_mode_success = ((mod_check & BIT_LF_MODE_ON) == BIT_LF_MODE_ON)

        # Unset LF mode
        self.write_register(REG_OP_MODE, MODE_SLEEP)
        time.sleep(0.01)
        # Change to STANDBY mode again to activate internal logic
        self.write_register(REG_OP_MODE, MODE_STANDBY)
        time.sleep(0.01)
        # Re-read the register after mode change
        mod_check = self.read_register(REG_OP_MODE)
        if mod_check is not None:
            self.lf_mode_not_success = ((mod_check & BIT_LF_MODE_ON) != BIT_LF_MODE_ON)
        
        # Put the device back into sleep mode with LF_MODE_ON
        self.write_register(REG_OP_MODE, MODE_SLEEP | BIT_LF_MODE_ON)
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
            self.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
        elif self.supports_low_frequency:
            self.module_type = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
        else:
            self.module_type = "Unknown / Communication Error"

        if potentially_multi_band_support:
            if self.lf_mode_not_success and self.lf_mode_success:
                # Note an SX1276 can be dropped into a slot reserved for an SX1278 and it will work perfectly at low frequencies
                # But if the pins 21 and 22 are connected to ground, it will fail at high frequencies (like an SX1278 would)
                # Software cannot detect if it is high-frequency capable; transmission has to be attempted to see if that
                # transmission fails.
                # Note also that being able to select 1010 MHz suggests that it is *not* an SX1279
                # Note it could be an SX1277, which cannot do all the spreading factors, we might want to detect that
                self.module_type = "Multi-band - Likely RFM95W (High-Band 868MHz and/or Low-Band 433Mhz / Semtech SX1276)"
            elif self.lf_mode_not_success:
                self.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
            elif self.lf_mode_success:
                self.module_type = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
            else:
                self.module_type = "Unknown / Communication Error"

    def test_unique_value_retention(self, frequency_khz: int) -> bool:
        """
        Test if a unique value can be written and retained.
        
        :param frequency_khz: Frequency in kHz to test
        :return: True if the value was successfully written and retained, False otherwise
        """
        # Use the existing verification function to write and verify the frequency
        (verify_success, req_msb, req_mid, req_lsb, _, _, _) = self._write_and_verify_frequency_for_khz(frequency_khz)
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
        
        # Compare with stored values
        return (current_msb == self.unique_msb and 
                current_mid == self.unique_mid and 
                current_lsb == self.unique_lsb)
    