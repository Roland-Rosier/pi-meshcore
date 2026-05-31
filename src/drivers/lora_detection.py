from typing import List, Optional, Dict
import spidev
# import gpiod
# from gpiod.line import Direction, Value
import time

REG_OP_MODE = 0x01

MODE_SLEEP   = 0x00
MODE_STANDBY = 0x01

# Bit 3: LowFrequencyModeOn (0 = High Band RFM95W, 1 = Low Band RFM98W)
# Note: The datasheet suggests that it is SET by default
# - This suggests that both devices have LF Mode
# - But that clearing it may only work for the HF device - RMF95W

BIT_LF_MODE_ON = 0x08

# Define Standard Raspberry PI hardware SPI 0 pins
# On the PI, CEO is GPIO 8, and CE1 is GPIO 7
CE0_NCS0_PIN = 8
CE1_NCS1_PIN = 7

class LoRaModuleDetector:
    """Class to detect LoRa modules connected via SPI."""
    def __init__(self, ce_pins: List[int] = [0, 1]):
        """
        Initialize SPI devices for CE pins.

        :param ce_pins: List of CE pins (e.g., [0, 1] for /dev/spidev0.0 and /dev/spidev0.1)
        """
        self.ce_pins = ce_pins
        self.spi_devices: List[spidev.SpiDev] = [spidev.SpiDev() for _ in ce_pins]
        # self.gpio_devices = []
        self._initialize_spi()
    
    # def _release_ncs_from_spi_driver()
    #     """Forces the kernel to unbind """

    def _initialize_spi(self) -> None:
        """Initialize SPI devices for each CE pin."""
        for idx, spi in enumerate(self.spi_devices):
            try:
                spi.open(0, idx)  # bus 0, device i
                spi.max_speed_hz = 1000000  # 1 MHz
                # spi.max_speed_hz = 5000000  # 5 MHz
                spi.mode = 0b00  # CPOL=0, CPHA=0
                # cshigh no longer supported by the Linux kernel 5+
                # spi.cshigh = False
                spi.lsbfirst = False
                spi.no_cs = False
                print(f"SPI device {idx} initialized.")
            except Exception as e:
                print(f"Failed to initialize SPI device {idx}: {e}")
            
            time.sleep(0.2)

            # try:
            #     # gpio_chip = gpiod.Chip("/dev/gpiochip0")
            #     cs_line = CE0_NCS0_PIN if idx == 0 else CE1_NCS1_PIN
            #     print(f"Trying to configure CS Line: {cs_line}")
            #     self.gpio_devices[idx] = gpiod.request_lines(
            #       "/dev/gpiochip0",
            #       consumer="Switch NCS for SPI",
            #       config={
            #           cs_line: gpiod.LineSettings(
            #               direction=Direction.OUTPUT, output_value=Value.ACTIVE
            #           )
            #       }
            #     )
            #     # self.gpio_devices[idx] = gpio_chip.get_line(CE0_NSC0_PIN if idx == 0 else CE1_NCS1_PIN)
            #     # Request the line for output
            #     self.gpio_devices[idx].request(consumer="led_script", type=gpiod.line.DIRECTION_OUTPUT)
            #     print(f"GPIO NCS Device {idx} initialized.")
            # except Exception as e:
            #     print(f"Failed to initialize GPIO NCS device {idx}: {e}")

    def read_register(self, ce_index: int, reg_addr: int) -> Optional[int]:
        """
        Read a register from the LoRa module.

        :param ce_index: Index of the CE pin (0 or 1)
        :param reg_addr: Register address to read
        :return: Register value or None if an error occurs
        """
        if ce_index >= len(self.spi_devices):
            return None

        try:
            spi = self.spi_devices[ce_index]
            # ncs = self.gpio_devices[ce_index]
            # Read register (bit 7 is clear for read)
            response = spi.xfer2([reg_addr & 0x7F, 0x00])
            time.sleep(0.01)
            return response[1]
        except Exception as e:
            print(f"SPI read error for CE {ce_index}: {e}")
            return None

    def write_register(self, ce_index: int, reg_addr: int, value: int) -> Optional[int]:
        """
        Write a register to the LoRa module.

        :param ce_index: Index of the CE pin (0 or 1)
        :param reg_addr: Register address to write
        :return: Register value or None if an error occurs
        """
        if ce_index >= len(self.spi_devices):
            return None

        try:
            spi = self.spi_devices[ce_index]
            # Read register (bit 7 is set for write)
            response = spi.xfer2([reg_addr | 0x80, value])
            time.sleep(0.01)
            return response[1]
        except Exception as e:
            print(f"SPI write error for CE {ce_index}: {e}")
            return None
    
    def _calc_freq_registers_for_khz(self, a_freq_in_khz: int) -> (int, int, int):
        # Formula: Freq (Hz) / (32MHz / 2^19) -> 868,000,000/61.035 = 14,221,348
        # Needs to truncate the (32MHz / 2^19) with more digits than just the .035 to get the registers
        # Hex: 0xD90024
        # -> (Freq (Hz) * 1000) / (32GHz/ 2^19) -> (Freq (Hz) * 1000) / 61035
        # -> (Freq (Hz) * 1000000) / (32GHz/ 2^19) -> (Freq (Hz) * 100000) / 61035156
        # freq_hz_times_1000 = a_freq_in_khz * 1000000
        freq_hz_times_100000000 = a_freq_in_khz * 100000000000
        # freq_register_value = int(freq_hz_times_1000 / 61035)
        freq_register_value = int(freq_hz_times_100000000 / 6103515625)
        lsb = int(freq_register_value & 0xFF)
        mid = int((freq_register_value & 0xFF00) >> 8)
        msb = int((freq_register_value & 0xFF0000) >>16)
        print(f"Calcualted registers for frequency of {a_freq_in_khz} kHz with register values ({msb:02X} {mid:02X} {lsb:02X})")

        return (msb, mid, lsb)
    
    def _read_frequency_registers(self, a_ce_pin: int) -> (int, int, int):
        # Read the registers
        msb = self.read_register(int(a_ce_pin), 0x06)
        mid = self.read_register(int(a_ce_pin), 0x07)
        lsb = self.read_register(int(a_ce_pin), 0x08)
        time.sleep(0.01)

        return (msb, mid, lsb)

    def _write_frequency_registers(self, a_ce_pin: int, a_msb: int, a_mid: int, a_lsb: int) -> None:
        # 1. Put the chip into Sleep Mode to allow frequency register changes
        # RegOpMode (0x01): Mode 0x00 = Sleep
        self.write_register(int(a_ce_pin), REG_OP_MODE, MODE_SLEEP)
        time.sleep(0.01)

        self.write_register(int(a_ce_pin), 0x06, a_msb)
        self.write_register(int(a_ce_pin), 0x07, a_mid)
        self.write_register(int(a_ce_pin), 0x08, a_lsb)
        time.sleep(0.01)

    def _write_frequency_for_khz(self, a_ce_pin: int, a_freq_in_khz: int) -> (int, int, int):
        (msb, mid, lsb) = self._calc_freq_registers_for_khz(a_freq_in_khz)
        self._write_frequency_registers(a_ce_pin, msb, mid, lsb)

        return (msb, mid, lsb)

    def _write_and_verify_frequency_for_khz(self, a_ce_pin: int, a_freq_in_khz: int) -> (bool, int, int, int, int, int, int):
        verify_success = False

        # Write a target high-frequency value (e.g. 868Mhz)
        (req_msb, req_mid, req_lsb) = self._write_frequency_for_khz(int(a_ce_pin), a_freq_in_khz)

        # Read the registers back to verify compliance
        (msb, mid, lsb) = self._read_frequency_registers(a_ce_pin)

        if msb == req_msb and mid == req_mid and lsb == req_lsb:
            verify_success = True
        
        return (verify_success, req_msb, req_mid, req_lsb, msb, mid, lsb)


    def detect_module_types(self) -> List[Dict]:
        """Detect the module type using the high-frequency (HF) registers which are missing in the RFM98W"""
        results = []

        for idx, ce_pin in enumerate(self.ce_pins):
            try:
                print (f"idx: {idx}, ce_pin: {ce_pin}")

                module_type = None

                # Verify Low Frequyency (433 MHz) for RFM95W validation
                # low_freq = {"supported": False, "freq_type": "low", "freq_khz": 433000}
                # low_freq = {"supported": False, "freq_type": "low", "freq_khz": 415000}
                low_freq = {"supported": False, "freq_type": "low", "freq_khz": 140000}
                # Verify High Frequyency (868 MHzr for RFM98W validation
                # high_freq = {"supported": False, "freq_type": "high", "freq_khz": 868000}
                high_freq = {"supported": False, "freq_type": "high", "freq_khz": 1015000}

                freqs_to_try = [low_freq, high_freq] if ce_pin == 0 else [high_freq, low_freq]

                for freq_to_try in freqs_to_try:
                    (verify_success, req_msb, req_mid, req_lsb, msb, mid, lsb) = self._write_and_verify_frequency_for_khz(int(ce_pin), freq_to_try["freq_khz"])
                    if verify_success:
                        print(f"Module supports {freq_to_try['freq_type']}")
                        freq_to_try["supported"] = True


                # if module_supports_low and module_supports_high:
                if low_freq["supported"] and high_freq["supported"]:
                    module_type = "Multi-band unlocked"
                # elif module_supports_high:
                elif high_freq["supported"]:
                    module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
                # elif module_supports_low:
                elif low_freq["supported"]:
                    module_type = "RFM98W (Low-Band 433MHz / Semtech SX1278)"
                else:
                    module_type = "Unknown / Communicationm Error"

                # 3. Now put the chip into Sleep Mode with LowFrequencyModeOn ACTIVE
                # Binary: 0000 1000 -> 0x08
                # self.write_register(int(ce_pin), REG_OP_MODE, MODE_SLEEP | BIT_LF_MODE_ON)
                self.write_register(int(ce_pin), REG_OP_MODE, MODE_SLEEP)
                time.sleep(0.01)

                # 4. Shift the device state to STANDBY mode while attempting to keep LF on
                self.write_register(int(ce_pin), REG_OP_MODE, MODE_STANDBY)
                time.sleep(0.02)

                # 5. Read back the status register
                mod_check = self.read_register(int(ce_pin), REG_OP_MODE)
                if (mod_check & BIT_LF_MODE_ON) == BIT_LF_MODE_ON:
                    secret_module_type = "RFM98W (Low-Band 433MHz / Semtech SX1278)"
                else:
                    secret_module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)" 

                self.write_register(int(ce_pin), REG_OP_MODE, MODE_SLEEP)
                time.sleep(0.01)

                # Now put the chip back into Sleep Mode with LowFrequencyModeOn ACTIVE
                self.write_register(int(ce_pin), REG_OP_MODE, MODE_SLEEP)

                # Create detection result
                result = {
                    "ce_pin": ce_pin,
                    "module_type": module_type,
                    "secret_module_type": secret_module_type,
                }

                results.append(result)

            except Exception as e:
                results.append({
                    "ce_pin": ce_pin,
                    "module_type": "No module detected",
                    "module_read_error": str(e)
                })

            time.sleep(0.1)

        for idx, ce_pin in enumerate(self.ce_pins):
            try:
                print (f"Reading unique frequency back from idx: {idx}, ce_pin: {ce_pin}")

                # Verify Low Frequency (433 MHz) for RFM95W validation
                # low_freq = {"supported": False, "freq_type": "low", "freq_khz": 433000}
                # low_freq = {"supported": False, "freq_type": "low", "freq_khz": 415000}
                low_freq = {"supported": False, "freq_type": "low", "freq_khz": 140000}
                # Verify High Frequency (868 MHzr for RFM98W validation
                # high_freq = {"supported": False, "freq_type": "high", "freq_khz": 868000}
                high_freq = {"supported": False, "freq_type": "high", "freq_khz": 1015000}

                freq_to_verify = high_freq if ce_pin == 0 else low_freq
                # freq_to_verify = low_freq if ce_pin == 0 else high_freq

                (req_msb, req_mid, req_lsb) = self._calc_freq_registers_for_khz(freq_to_verify["freq_khz"])
                (msb, mid, lsb) = self._read_frequency_registers(int(ce_pin))

                if (req_msb == msb) and (req_mid == mid) and (req_lsb == lsb):
                    print(f"Module on ce_pin: {ce_pin} retained unique frequency value with registers {msb:02X} {mid:02X} {lsb:02X}")
                else:
                    print(f"ERROR: Module on ce_pin: {ce_pin} FAILED TO RETAIN unique frequency value!")
            except Exception as e:
                print(f"Exception: {e}")


        return results


    def detect_modules(self) -> List[Dict]:
        """Detect LoRa modules connected to the CE pins."""
        results = []

        for idx, ce_pin in enumerate(self.ce_pins):
            try:
                # Read the RegRxBw / RegFreqIfMsb register
                # This is expected to be 0x15 as a default value
                reg_rxbw_freqifmsb = self.read_register(int(ce_pin), 0x12)

                # Read RegVersion register (0x42)
                # This is expected to be 0x12 as a default value
                silicon_revision_register = self.read_register(int(ce_pin), 0x42)

                # # Map version register to module type
                # module_type = None
                # if version_register == 0x12:
                #     module_type = "RFM95W (Semtech SX1276)"
                # elif version_register == 0x19:
                #     module_type = "RFM98W (Semtech SX1278)"
                # else:
                #     module_type = f"Unknown (Version: 0x{version_register:02X})"

                # Create detection result
                result = {
                    "ce_pin": ce_pin,
                    # "module_type": module_type,
                    # "version_register": f"0x{version_register:02X}",
                    "silicon_revision_register": f"0x{silicon_revision_register:02X}",
                    "reg_rxbw_freqifmsb": f"0x{reg_rxbw_freqifmsb:02X}",
                }

                results.append(result)

            except Exception as e:
                results.append({
                    "ce_pin": ce_pin,
                    # "module_type": "No module detected",
                    "silicon_revision_register": "None detected",
                    "reg_rxbw_freqifmsb": "None read",
                    "error": str(e)
                })

            time.sleep(0.1)

        module_types = self.detect_module_types()

        # Map the module types into an active lookup index by primary key
        module_types_lookup = {item["ce_pin"]: item for item in module_types}

        # Unpack data structures to build out the final combined output array
        combined_results = [
            {**result, **module_types_lookup.get(result["ce_pin"], {})}
            for result in results
        ]

        print("\nStatus: All modules verified (no transmission occurred)")  # Debug print preserved
        print("Note: This verification only checks for module presence and basic communication")  # Debug print preserved

        return combined_results

    def __del__(self) -> None:
        """Clean up SPI devices when the object is destroyed."""
        for spi in self.spi_devices:
            try:
                spi.close()
                print("SPI device closed.")
            except Exception as e:
                print(f"Error closing SPI device: {e}")
        # for line in self.gpio_devices:
        #     try:
        #         line.release()
        #         print("GPIO device released")
        #     except Exception as e:
        #         print(f"Error releasing GPIO device: {e}")

