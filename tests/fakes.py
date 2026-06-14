# Copyright (c) 2026 Project Authors. All rights reserved.

"""Fake SPI driver for testing LoRa module detection."""

from typing import Dict, List, Optional, Tuple
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
    REG_PKT_RSSI_VALUE: int = 0x1A
    REG_PKT_SNR_VALUE: int = 0x1B
    
    # Mode bits
    BIT_LF_MODE_ON: int = 0x08
    MODE_SLEEP: int = 0x00
    MODE_STANDBY: int = 0x01

    def __init__(self, module_type: str = "none", registers: Optional[Dict[int, int]] = None) -> None:
        """Initialize the fake SPI device.
        
        :param module_type: Type of module to simulate ("rfm95w", "rfm98w", "multi_band", "none")
        :param registers: Optional initial register values
        """
        self.module_type: str = module_type
        self._registers: Dict[int, int] = registers.copy() if registers else {}
        self._fail_next_read: bool = False
        self._fail_next_write: bool = False
        self._opened: bool = False
        
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

    def xfer2(self, data: List[int]) -> List[int]:
        """Simulate SPI transfer.
        
        :param data: Data to transfer (write bytes)
        :return: Received data (read bytes)
        :raises Exception: If simulating an error condition
        """
        if not self._opened:
            raise OSError("SPI device not opened")
            
        if not data:
            return []
            
        result: List[int] = []
        
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
                    
                # Handle special register writes
                if address == self.REG_OP_MODE:
                    # Track LF mode bit state
                    current_op_mode: int = self._registers.get(address, 0)
                    new_op_mode: int = (current_op_mode & ~self.BIT_LF_MODE_ON) | (value & self.BIT_LF_MODE_ON)
                    self._registers[address] = new_op_mode
                elif address in [0x06, 0x07, 0x08]:  # Frequency registers
                    self._registers[address] = value
                else:
                    self._registers[address] = value
                    
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
                        
                result.append(cmd_byte)
                result.append(reg_value)
                i += 1
                
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
        self._opened = False

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


def create_fake_spi_dev(module_type: str = "none", 
                        registers: Optional[Dict[int, int]] = None) -> FakeSpiDev:
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
        with open(__file__, 'r') as f:
            ast.parse(f.read())
        print("✓ Syntax is valid")
        sys.exit(0)
    except SyntaxError as e:
        print(f"✗ Syntax error: {e}")
        sys.exit(1)

