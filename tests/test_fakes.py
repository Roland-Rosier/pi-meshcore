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

"""Unit tests for FakeSpiDev class."""

import pytest
from typing import Dict, List

from tests.fakes import FakeSpiDev


class TestFakeSpiDevInitialization:
    """Test cases for FakeSpiDev initialization."""

    def test_default_initialization(self) -> None:
        """Test default initialization with 'none' module type."""
        fake = FakeSpiDev()
        assert fake.module_type == "none"
        assert not fake.is_lf_mode_enabled()
        assert fake.get_operating_mode() == 0x00

    def test_custom_module_types(self) -> None:
        """Test initialization with different module types."""
        for module_type in ["rfm95w", "rfm98w", "multi_band", "none"]:
            fake = FakeSpiDev(module_type=module_type)
            assert fake.module_type == module_type

    def test_custom_registers(self) -> None:
        """Test initialization with custom register values."""
        custom_regs: Dict[int, int] = {0x01: 0x08, 0x42: 0x12}
        fake = FakeSpiDev(registers=custom_regs)
        assert fake.get_register(0x01) == 0x08
        assert fake.get_register(0x42) == 0x12

    def test_default_registers(self) -> None:
        """Test that default register values are set correctly."""
        fake = FakeSpiDev()
        assert fake.get_register(FakeSpiDev.REG_OP_MODE) == 0x00
        assert fake.get_register(FakeSpiDev.REG_FIFO_ADDR_PTR) == 0x00
        assert fake.get_register(FakeSpiDev.REG_FIFO_TX_BASE_ADDR) == 0x80
        assert fake.get_register(FakeSpiDev.REG_FIFO_RX_BASE_ADDR) == 0x00


class TestFakeSpiDevOpenClose:
    """Test cases for SPI device open/close operations."""

    def test_open_success(self) -> None:
        """Test successful opening of SPI device."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        assert fake._opened is True

    def test_open_failure_none_module(self) -> None:
        """Test opening fails for 'none' module type."""
        fake = FakeSpiDev(module_type="none")
        with pytest.raises(OSError):
            fake.open(0, 0)

    def test_close(self) -> None:
        """Test closing SPI device."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        fake.close()
        assert fake._opened is False


class TestFakeSpiDevRegisters:
    """Test cases for register read/write operations."""

    def test_set_register(self) -> None:
        """Test setting a register value."""
        fake = FakeSpiDev()
        fake.set_register(0x42, 0x12)
        assert fake.get_register(0x42) == 0x12

    def test_get_default_register(self) -> None:
        """Test getting default register values."""
        fake = FakeSpiDev()
        assert fake.get_register(0x42) == 0x00

    def test_multiple_registers(self) -> None:
        """Test setting and reading multiple registers."""
        fake = FakeSpiDev()
        regs: Dict[int, int] = {0x01: 0x08, 0x42: 0x19}
        for addr, val in regs.items():
            fake.set_register(addr, val)
        assert fake.get_register(0x01) == 0x08
        assert fake.get_register(0x42) == 0x19


class TestFakeSpiDevXFer:
    """Test cases for SPI transfer operations."""

    def test_xfer2_empty_data(self) -> None:
        """Test xfer2 with empty data."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        result = fake.xfer2([])
        assert result == []

    def test_xfer2_write_operation(self) -> None:
        """Test xfer2 with write operation."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        result = fake.xfer2([0x81, 0x08])  # Write to REG_OP_MODE
        assert len(result) == 2

    def test_xfer2_read_operation(self) -> None:
        """Test xfer2 with read operation."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        result = fake.xfer2([0x42, 0x00])  # Read from register 0x42
        assert len(result) == 2
        assert result[1] == 0x12  # Should return silicon revision

    def test_xfer2_unopened_device(self) -> None:
        """Test xfer2 on unopened device raises OSError."""
        fake = FakeSpiDev(module_type="rfm95w")
        with pytest.raises(OSError):
            fake.xfer2([0x42, 0x00])

    def test_xfer2_write_failure_simulation(self) -> None:
        """Test xfer2 write failure simulation."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        fake.enable_failure_write()
        with pytest.raises(Exception):
            fake.xfer2([0x81, 0x08])

    def test_xfer2_read_failure_simulation(self) -> None:
        """Test xfer2 read failure simulation."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        fake.enable_failure_read()
        with pytest.raises(Exception):
            fake.xfer2([0x42, 0x00])


class TestFakeSpiDevFrequency:
    """Test cases for frequency-related operations."""

    def test_calculate_frequency_from_registers(self) -> None:
        """Test frequency calculation from register values."""
        fake = FakeSpiDev()
        freq_khz = fake.calculate_frequency_from_registers(0x12, 0x34, 0x56)
        assert freq_khz > 0

    def test_is_frequency_supported_rfm95w_high(self) -> None:
        """Test frequency support for RFM95W at high frequencies."""
        fake = FakeSpiDev(module_type="rfm95w")
        assert fake.is_frequency_supported(868000) is True
        assert fake.is_frequency_supported(1015000) is True

    def test_is_frequency_supported_rfm95w_low(self) -> None:
        """Test frequency support for RFM95W at low frequencies."""
        fake = FakeSpiDev(module_type="rfm95w")
        assert fake.is_frequency_supported(433000) is False

    def test_is_frequency_supported_rfm98w_low(self) -> None:
        """Test frequency support for RFM98W at low frequencies."""
        fake = FakeSpiDev(module_type="rfm98w")
        assert fake.is_frequency_supported(433000) is True
        assert fake.is_frequency_supported(525000) is True

    def test_is_frequency_supported_rfm98w_high(self) -> None:
        """Test frequency support for RFM98W at high frequencies."""
        fake = FakeSpiDev(module_type="rfm98w")
        assert fake.is_frequency_supported(868000) is False

    def test_is_frequency_supported_multi_band(self) -> None:
        """Test frequency support for multi-band module."""
        fake = FakeSpiDev(module_type="multi_band")
        assert fake.is_frequency_supported(433000) is True
        assert fake.is_frequency_supported(868000) is True

    def test_is_frequency_supported_none_module(self) -> None:
        """Test frequency support for 'none' module type."""
        fake = FakeSpiDev(module_type="none")
        assert fake.is_frequency_supported(433000) is False
        assert fake.is_frequency_supported(868000) is False


class TestFakeSpiDevLFMode:
    """Test cases for LF mode operations."""

    def test_lf_mode_enabled(self) -> None:
        """Test LF mode can be enabled."""
        fake = FakeSpiDev()
        fake.set_register(FakeSpiDev.REG_OP_MODE, 0x08)
        assert fake.is_lf_mode_enabled() is True

    def test_lf_mode_disabled(self) -> None:
        """Test LF mode can be disabled."""
        fake = FakeSpiDev()
        fake.set_register(FakeSpiDev.REG_OP_MODE, 0x00)
        assert fake.is_lf_mode_enabled() is False

    def test_operating_mode_read(self) -> None:
        """Test reading operating mode register."""
        fake = FakeSpiDev()
        fake.set_register(FakeSpiDev.REG_OP_MODE, 0x01)
        assert fake.get_operating_mode() == 0x01


class TestFakeSpiDevReset:
    """Test cases for reset operations."""

    def test_reset_clears_registers(self) -> None:
        """Test that reset clears all registers to defaults."""
        fake = FakeSpiDev()
        fake.set_register(0x42, 0xFF)
        fake.reset()
        assert fake.get_register(0x42) == 0x00

    def test_reset_clears_failure_flags(self) -> None:
        """Test that reset clears failure simulation flags."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        fake.enable_failure_read()
        fake.enable_failure_write()
        fake.reset()
        # After reset, no exception should be raised
        result = fake.xfer2([0x42, 0x00])
        assert len(result) == 2


class TestFakeSpiDevUtilities:
    """Test cases for utility functions."""

    def test_verify_frequency_registers(self) -> None:
        """Test frequency register verification."""
        fake = FakeSpiDev(module_type="rfm95w")
        result = fake._verify_frequency_registers(0x12, 0x34, 0x56)
        assert isinstance(result, bool)

    def test_factory_function(self) -> None:
        """Test the factory function for creating FakeSpiDev instances."""
        from fakes import create_fake_spi_dev
        fake = create_fake_spi_dev("rfm95w")
        assert isinstance(fake, FakeSpiDev)

    def test_patch_spidev_with_fake(self) -> None:
        """Test patching spidev with fake device."""
        from fakes import patch_spidev_with_fake
        fake = FakeSpiDev(module_type="rfm95w")
        mock = patch_spidev_with_fake(fake)
        assert mock.return_value == fake

    def test_verify_frequency_in_range(self) -> None:
        """Test frequency range verification utility."""
        from fakes import verify_frequency_in_range
        fake = FakeSpiDev(module_type="multi_band")
        result = verify_frequency_in_range(fake, 868000)
        assert result is True

    def test_simulate_lf_mode_test(self) -> None:
        """Test LF mode simulation utility."""
        from fakes import simulate_lf_mode_test
        fake = FakeSpiDev(module_type="rfm95w")
        result = simulate_lf_mode_test(fake)
        assert isinstance(result, bool)
