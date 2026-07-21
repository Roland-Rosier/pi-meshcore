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

"""Fake SPI driver for testing LoRa module detection."""

from unittest.mock import MagicMock


class FakeSpiDev:
    """Simulated SPI device for testing LoRa module detection.

    This class mimics the behavior of spidev.SpiDev but allows controlled
    simulation of different module types and error conditions.
    """

    # Frequency thresholds in kHz
    _HIGH_FREQ_MIN: int = 862000
    _LOW_FREQ_MAX: int = 525000

    # Register addresses
    REG_OP_MODE: int = 0x01
    REG_FIFO_ADDR_PTR: int = 0x0D
    REG_FIFO_TX_BASE_ADDR: int = 0x0E
    REG_FIFO_RX_BASE_ADDR: int = 0x0F
    REG_FIFO_RX_CURRENT_ADDR: int = 0x10
    REG_IRQ_FLAGS_MASK: int = 0x11
    REG_IRQ_FLAGS: int = 0x12
    REG_RX_NB_BYTES: int = 0x13
    REG_IRQ_FLAGS1: int = 0x3E
    REG_PKT_RSSI_VALUE: int = 0x1A
    REG_PKT_SNR_VALUE: int = 0x1B

    # Mode bits
    BIT_LF_MODE_ON: int = 0x08
    MODE_SLEEP: int = 0x00
    MODE_STANDBY: int = 0x01

    def __init__(self, module_type: str = "none", registers: dict[int, int] | None = None) -> None:
        """Initialize the fake SPI device.

        :param module_type: Type of module to simulate ("rfm95w", "rfm98w", "multi_band", "none")
        :param registers: Optional initial register values
        """
        self.module_type: str = module_type
        self._registers: dict[int, int] = registers.copy() if registers else {}
        self._fail_next_read: bool = False
        self._fail_next_write: bool = False
        self._opened: bool = False
        self._pll_auto_mode: bool = False  # When True, auto-set PLL based on freq range after writes

        # Initialize default register values
        self._default_registers()

    def _default_registers(self) -> None:
        """Set default register values."""
        # Default OP_MODE is Sleep mode with LF mode off
        if self.REG_OP_MODE not in self._registers:
            self._registers[self.REG_OP_MODE] = self.MODE_SLEEP

        # Default FIFO addresses
        if self.REG_FIFO_ADDR_PTR not in self._registers:
            self._registers[self.REG_FIFO_ADDR_PTR] = 0x00
        if self.REG_FIFO_TX_BASE_ADDR not in self._registers:
            self._registers[self.REG_FIFO_TX_BASE_ADDR] = 0x80
        if self.REG_FIFO_RX_BASE_ADDR not in self._registers:
            self._registers[self.REG_FIFO_RX_BASE_ADDR] = 0x00
        if self.REG_FIFO_RX_CURRENT_ADDR not in self._registers:
            self._registers[self.REG_FIFO_RX_CURRENT_ADDR] = 0x00

        # Default IRQ flags
        if self.REG_IRQ_FLAGS_MASK not in self._registers:
            self._registers[self.REG_IRQ_FLAGS_MASK] = 0x7F
        if self.REG_IRQ_FLAGS not in self._registers:
            self._registers[self.REG_IRQ_FLAGS] = 0x00

        # Default packet values
        if self.REG_PKT_RSSI_VALUE not in self._registers:
            self._registers[self.REG_PKT_RSSI_VALUE] = 0x00
        if self.REG_PKT_SNR_VALUE not in self._registers:
            self._registers[self.REG_PKT_SNR_VALUE] = 0x00

        # IRQ Flags 1 register (0x3E) — used for PLL lock simulation
        if self.REG_IRQ_FLAGS1 not in self._registers:
            self._registers[self.REG_IRQ_FLAGS1] = 0x00

    def open(self, bus: int, device: int) -> None:
        """Simulate opening the SPI device.

        :param bus: SPI bus number
        :param device: CE pin number (device select)
        :raises OSError: If simulating a disconnected device
        """
        if self.module_type == "none":
            raise OSError(f"SPI device not found on bus {bus}, device {device}")
        self._opened = True

    def close(self) -> None:
        """Simulate closing the SPI device."""
        self._opened = False

    @property
    def max_speed_hz(self) -> int:
        """Get/set maximum SPI speed."""
        return 1000000

    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None:
        """Set maximum SPI speed (no-op in simulation)."""
        pass

    @property
    def mode(self) -> int:
        """Get/set SPI mode."""
        return 0

    @mode.setter
    def mode(self, value: int) -> None:
        """Set SPI mode (no-op in simulation)."""
        pass

    @property
    def lsbfirst(self) -> bool:
        """Get/set LSB first setting."""
        return False

    @lsbfirst.setter
    def lsbfirst(self, value: bool) -> None:
        """Set LSB first setting (no-op in simulation)."""
        pass

    @property
    def no_cs(self) -> bool:
        """Get/set no CS setting."""
        return False

    @no_cs.setter
    def no_cs(self, value: bool) -> None:
        """Set no CS setting (no-op in simulation)."""
        pass

    def xfer2(self, data: list[int]) -> list[int]:
        """Simulate SPI transfer.

        :param data: Data to transfer (write bytes)
        :return: Received data (read bytes)
        :raises Exception: If simulating an error condition
        """
        if not self._opened:
            raise OSError("SPI device not opened")

        if not data:
            return []

        result: list[int] = []

        # Process each byte pair (address, value)
        i: int = 0
        while i < len(data):
            # First byte is the address/command
            cmd_byte: int = data[i]
            address: int = cmd_byte & 0x7F
            is_write: bool = (cmd_byte & 0x80) != 0

            if is_write:
                # Write operation
                if i + 1 >= len(data):
                    raise ValueError("Incomplete write command")

                value: int = data[i + 1]

                if self._fail_next_write:
                    self._fail_next_write = False
                    raise Exception("SPI write failure simulated")

                # Handle special register writes — store the full written value so that
                # mode-setting and LF-bit operations are both faithfully simulated.
                if address == self.REG_OP_MODE or address in [0x06, 0x07, 0x08]:
                    self._registers[address] = value
                else:
                    self._registers[address] = value

                # PLL auto-mode: frequency-dependent automatic PLL lock simulation.
                if address in (0x06, 0x07, 0x08) and self._pll_auto_mode:
                    if all(a in self._registers for a in (0x06, 0x07, 0x08)):
                        frf_msb = self._registers[0x06]
                        frf_mid = self._registers[0x07]
                        frf_lsb = self._registers[0x08]
                        freq_register_value = (frf_msb << 16) | (frf_mid << 8) | frf_lsb
                        freq_hz_times_100000000 = freq_register_value * 6103515625
                        freq_khz = int(freq_hz_times_100000000 / 100000000)

                        pll_would_lock = False
                        if self.module_type == "rfm95w":
                            pll_would_lock = freq_khz >= 862000  # HF band only (future hardware)
                        elif self.module_type == "rfm98w":
                            pll_would_lock = freq_khz <= 525000  # LF band only (future hardware)
                        elif self.module_type == "multi_band":
                            pll_would_lock = True  # Both bands supported

                        current_irq_flags1 = self._registers.get(self.REG_IRQ_FLAGS1, 0x00)
                        if pll_would_lock:
                            self._registers[self.REG_IRQ_FLAGS1] = current_irq_flags1 | 0x10
                        else:
                            self._registers[self.REG_IRQ_FLAGS1] = current_irq_flags1 & ~0x10

                result.append(cmd_byte)
                result.append(value)
                i += 2
            else:
                # Read operation
                if self._fail_next_read:
                    self._fail_next_read = False
                    raise Exception("SPI read failure simulated")

                # Return register value or default
                reg_value: int = self._registers.get(address, 0x00)

                # Special handling for certain registers
                if address == 0x42:  # Silicon revision (simulated)
                    if self.module_type == "rfm95w":
                        reg_value = 0x12
                    elif self.module_type == "rfm98w":
                        reg_value = 0x19
                    else:
                        reg_value = 0x00

                # PLL state management on read of IRQ_FLAGS1.
                if address == self.REG_IRQ_FLAGS1 and not is_write:
                    if self._pll_auto_mode:
                        # Auto-mode: recalculate correct PLL state from current frequency registers.
                        frf_msb = self._registers.get(0x06)
                        frf_mid = self._registers.get(0x07)
                        frf_lsb = self._registers.get(0x08)
                        if all(v is not None for v in (frf_msb, frf_mid, frf_lsb)):
                            freq_register_value: int = (frf_msb << 16) | (frf_mid << 8) | frf_lsb
                            freq_hz_times_100000000: int = freq_register_value * 6103515625
                            freq_khz: int = int(freq_hz_times_100000000 / 100000000)

                            pll_would_lock: bool = False
                            if self.module_type == "rfm95w":
                                pll_would_lock = freq_khz >= self._HIGH_FREQ_MIN
                            elif self.module_type == "rfm98w":
                                pll_would_lock = freq_khz <= self._LOW_FREQ_MAX
                            elif self.module_type == "multi_band":
                                pll_would_lock = True

                            current_irq_flags1: int = self._registers.get(self.REG_IRQ_FLAGS1, 0x00)
                            if pll_would_lock:
                                self._registers[self.REG_IRQ_FLAGS1] = current_irq_flags1 | 0x10
                            else:
                                self._registers[self.REG_IRQ_FLAGS1] = current_irq_flags1 & ~0x10
                    # In non-auto-mode, preserve the stored value unchanged.

                result.append(cmd_byte)
                result.append(reg_value)
                i += 2

        return result

    def set_register(self, reg_addr: int, value: int) -> None:
        """Set a register value directly.

        :param reg_addr: Register address
        :param value: Value to set
        """
        self._registers[reg_addr] = value

    def get_register(self, reg_addr: int) -> int:
        """Get a register value.

        :param reg_addr: Register address
        :return: Current register value
        """
        return self._registers.get(reg_addr, 0x00)

    def enable_failure_read(self) -> None:
        """Enable failure simulation for next read operation."""
        self._fail_next_read = True

    def enable_failure_write(self) -> None:
        """Enable failure simulation for next write operation."""
        self._fail_next_write = True

    def reset(self) -> None:
        """Reset the fake SPI device to initial state."""
        self._registers.clear()
        self._default_registers()
        self._fail_next_read = False
        self._fail_next_write = False

    def calculate_frequency_from_registers(self, msb: int, mid: int, lsb: int) -> int:
        """Calculate frequency in kHz from register values.

        :param msb: Most significant byte
        :param mid: Middle byte
        :param lsb: Least significant byte
        :return: Frequency in kHz
        """
        freq_register_value: int = (msb << 16) | (mid << 8) | lsb
        freq_hz_times_100000000: int = freq_register_value * 6103515625
        freq_hz: float = freq_hz_times_100000000 / 100000000000
        return int(freq_hz * 1000)

    def is_frequency_supported(self, frequency_khz: int) -> bool:
        """Check if a frequency is supported by the simulated module.

        :param frequency_khz: Frequency in kHz
        :return: True if frequency is supported
        """
        if self.module_type == "none":
            return False
        elif self.module_type == "rfm95w":
            return frequency_khz >= self._HIGH_FREQ_MIN
        elif self.module_type == "rfm98w":
            return frequency_khz <= self._LOW_FREQ_MAX
        elif self.module_type == "multi_band":
            return True
        return False

    def _verify_frequency_registers(self, msb: int, mid: int, lsb: int) -> bool:
        """Verify if frequency registers contain valid values for this module type.

        :param msb: Most significant byte
        :param mid: Middle byte
        :param lsb: Least significant byte
        :return: True if the frequency is supported
        """
        freq_khz: int = self.calculate_frequency_from_registers(msb, mid, lsb)
        return self.is_frequency_supported(freq_khz)

    def get_operating_mode(self) -> int:
        """Get the current operating mode.

        :return: Current OP_MODE register value
        """
        return self._registers.get(self.REG_OP_MODE, self.MODE_SLEEP)

    def is_lf_mode_enabled(self) -> bool:
        """Check if LF mode is enabled.

        :return: True if LF mode bit is set
        """
        op_mode: int = self.get_operating_mode()
        return (op_mode & self.BIT_LF_MODE_ON) == self.BIT_LF_MODE_ON

    def set_pll_lock_state(self, locked: bool) -> None:
        """Set the simulated PLL lock state for RegIrqFlags1 bit 4.

        :param locked: True if PLL should report as locked.
        """
        current: int = self._registers.get(self.REG_IRQ_FLAGS1, 0x00)
        if locked:
            self._registers[self.REG_IRQ_FLAGS1] = current | 0x10  # Set bit 4 (PLLLock)
        else:
            self._registers[self.REG_IRQ_FLAGS1] = current & ~0x10  # Clear bit 4

    def set_pll_auto_mode(self, enabled: bool) -> None:
        """Enable or disable frequency-dependent automatic PLL lock simulation.

        When disabled (default), PLL state persists as manually set — simulating real
        hardware where all working modules lock on both frequencies and return 'family series'.

        When enabled, PLL is auto-set/cleared based on module type and written frequency range —
        useful for testing future hardware that may behave according to original RFM95W/RFM98W specs.

        :param enabled: True to enable automatic PLL simulation based on frequency range.
        """
        self._pll_auto_mode = enabled


def create_fake_spi_dev(module_type: str = "none",
                        registers: dict[int, int] | None = None) -> FakeSpiDev:
    """Create a FakeSpiDev instance with the specified module type.

    :param module_type: Type of module to simulate ("rfm95w", "rfm98w", "multi_band", "none")
    :param registers: Optional initial register values
    :return: Configured FakeSpiDev instance
    """
    return FakeSpiDev(module_type=module_type, registers=registers)


def patch_spidev_with_fake(fake_spi: FakeSpiDev) -> MagicMock:
    """Patch spidev.SpiDev with a FakeSpiDev instance for testing.

    :param fake_spi: FakeSpiDev instance to use as replacement
    :return: Mock object that returns the fake SPI device
    """
    mock = MagicMock()
    mock.return_value = fake_spi
    return mock


def verify_frequency_in_range(fake_spi: FakeSpiDev, frequency_khz: int) -> bool:
    """Verify if a frequency is in the supported range for the module type.

    :param fake_spi: FakeSpiDev instance
    :param frequency_khz: Frequency to verify in kHz
    :return: True if frequency is supported
    """
    return fake_spi.is_frequency_supported(frequency_khz)


def simulate_lf_mode_test(fake_spi: FakeSpiDev) -> bool:
    """Simulate LF mode test sequence.

    :param fake_spi: FakeSpiDev instance configured as RFM95W or similar
    :return: True if LF mode is successfully set and retained
    """
    # Set LF mode in sleep mode
    current_op_mode: int = fake_spi.get_register(FakeSpiDev.REG_OP_MODE)
    lf_enabled_op_mode: int = current_op_mode | FakeSpiDev.BIT_LF_MODE_ON
    fake_spi.set_register(FakeSpiDev.REG_OP_MODE, lf_enabled_op_mode)

    # Switch to standby mode while keeping LF bit
    standby_with_lf: int = (FakeSpiDev.MODE_STANDBY & ~FakeSpiDev.BIT_LF_MODE_ON) | \
                            (lf_enabled_op_mode & FakeSpiDev.BIT_LF_MODE_ON)
    fake_spi.set_register(FakeSpiDev.REG_OP_MODE, standby_with_lf)

    # Verify LF mode is still enabled
    return fake_spi.is_lf_mode_enabled()


if __name__ == "__main__":
    import ast
    import sys

    try:
        with open(__file__) as f:
            ast.parse(f.read())
        print("✓ Syntax is valid")
        sys.exit(0)
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        sys.exit(1)







