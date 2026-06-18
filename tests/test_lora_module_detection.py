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

"""Integration tests for LoRa module detection using FakeSpiDev."""

import sys
import os
from unittest.mock import MagicMock, patch
from typing import Dict

# Add the project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

import pytest
from fakes import FakeSpiDev


class TestLoRaModuleDetection:
    """Test cases for LoRa module detection using FakeSpiDev."""

    def test_rfm95w_detection(self) -> None:
        """Test detection of RFM95W module type."""
        fake = FakeSpiDev(module_type="rfm95w")
        
        # Simulate the initialization sequence
        fake.open(0, 0)
        
        # Check silicon revision (register 0x42)
        response = fake.xfer2([0x42, 0x00])  # Read register 0x42
        assert response[1] == 0x12  # RFM95W silicon revision
        
        # Check high frequency support
        freq_khz = 1015000
        fake.set_register(0x06, 0x00)
        fake.set_register(0x07, 0x00)
        fake.set_register(0x08, 0x00)
        
        msb, mid, lsb = fake.calculate_frequency_from_registers(0x00, 0x00, 0x00)
        assert fake.is_frequency_supported(freq_khz) is True
        
        # Check LF mode retention
        fake.set_register(FakeSpiDev.REG_OP_MODE, FakeSpiDev.MODE_SLEEP | FakeSpiDev.BIT_LF_MODE_ON)
        fake.set_register(FakeSpiDev.REG_OP_MODE, FakeSpiDev.MODE_STANDBY | FakeSpiDev.BIT_LF_MODE_ON)
        current_op_mode = fake.get_register(FakeSpiDev.REG_OP_MODE)
        lf_retained = (current_op_mode & FakeSpiDev.BIT_LF_MODE_ON) == FakeSpiDev.BIT_LF_MODE_ON
        
        # RFM95W should have LF mode retention
        assert lf_retained is True

    def test_rfm98w_detection(self) -> None:
        """Test detection of RFM98W module type."""
        fake = FakeSpiDev(module_type="rfm98w")
        
        # Simulate the initialization sequence
        fake.open(0, 0)
        
        # Check silicon revision (register 0x42)
        response = fake.xfer2([0x42, 0x00])  # Read register 0x42
        assert response[1] == 0x19  # RFM98W silicon revision
        
        # Check low frequency support
        freq_khz = 415000
        assert fake.is_frequency_supported(freq_khz) is True
        
        # Check high frequency not supported
        assert fake.is_frequency_supported(1015000) is False

    def test_multi_band_detection(self) -> None:
        """Test detection of multi-band module type."""
        fake = FakeSpiDev(module_type="multi_band")
        
        # Simulate the initialization sequence
        fake.open(0, 0)
        
        # Check both high and low frequency support
        assert fake.is_frequency_supported(1015000) is True
        assert fake.is_frequency_supported(415000) is True

    def test_none_module_detection(self) -> None:
        """Test handling of 'none' module type."""
        fake = FakeSpiDev(module_type="none")
        
        # Should raise OSError on open
        with pytest.raises(OSError):
            fake.open(0, 0)

    def test_frequency_calculation(self) -> None:
        """Test frequency calculation from register values."""
        fake = FakeSpiDev()
        
        # Test various frequencies
        test_cases = [
            (0x00, 0x00, 0x00, 0),  # Zero frequency
            (0x12, 0x34, 0x56, None),  # Valid frequency
            (0xFF, 0xFF, 0xFF, None),  # Maximum frequency
        ]
        
        for msb, mid, lsb, expected_min in test_cases:
            freq_khz = fake.calculate_frequency_from_registers(msb, mid, lsb)
            assert freq_khz >= 0
            if expected_min is not None:
                assert freq_khz >= expected_min

    def test_lf_mode_retention_simulation(self) -> None:
        """Test LF mode retention simulation."""
        fake = FakeSpiDev(module_type="rfm95w")
        
        # Simulate LF mode test sequence
        fake.set_register(FakeSpiDev.REG_OP_MODE, FakeSpiDev.MODE_SLEEP | FakeSpiDev.BIT_LF_MODE_ON)
        standby_mode = (FakeSpiDev.MODE_STANDBY & ~FakeSpiDev.BIT_LF_MODE_ON) | \
                       (FakeSpiDev.MODE_STANDBY & FakeSpiDev.BIT_LF_MODE_ON)
        fake.set_register(FakeSpiDev.REG_OP_MODE, standby_mode)
        
        # Check LF mode bit retention
        current_op_mode = fake.get_register(FakeSpiDev.REG_OP_MODE)
        assert (current_op_mode & FakeSpiDev.BIT_LF_MODE_ON) == FakeSpiDev.BIT_LF_MODE_ON

    def test_error_handling(self) -> None:
        """Test error handling in SPI operations."""
        fake = FakeSpiDev(module_type="rfm95w")
        fake.open(0, 0)
        
        # Test read failure simulation
        fake.enable_failure_read()
        with pytest.raises(Exception):
            fake.xfer2([0x42, 0x00])
        
        # Test write failure simulation
        fake.enable_failure_write()
        with pytest.raises(Exception):
            fake.xfer2([0x81, 0x08])

    def test_register_reset(self) -> None:
        """Test register reset functionality."""
        fake = FakeSpiDev()
        
        # Set some registers
        fake.set_register(0x42, 0xFF)
        fake.set_register(0x01, 0x08)
        
        # Reset and verify
        fake.reset()
        assert fake.get_register(0x42) == 0x00
        assert fake.get_register(0x01) == 0x00


class TestFakeSpiDevUtilities:
    """Test cases for FakeSpiDev utility functions."""

    def test_create_fake_spi_dev(self) -> None:
        """Test the create_fake_spi_dev factory function."""
        from fakes import create_fake_spi_dev
        
        fake = create_fake_spi_dev("rfm95w")
        assert isinstance(fake, FakeSpiDev)
        assert fake.module_type == "rfm95w"

    def test_patch_spidev_with_fake(self) -> None:
        """Test patching spidev with fake device."""
        from fakes import patch_spidev_with_fake
        
        fake = FakeSpiDev(module_type="rfm95w")
        mock = patch_spidev_with_fake(fake)
        assert mock.return_value == fake

    def test_verify_frequency_in_range(self) -> None:
        """Test frequency range verification."""
        from fakes import verify_frequency_in_range
        
        fake = FakeSpiDev(module_type="rfm95w")
        assert verify_frequency_in_range(fake, 868000) is True
        assert verify_frequency_in_range(fake, 433000) is False

    def test_simulate_lf_mode_test(self) -> None:
        """Test LF mode simulation utility."""
        from fakes import simulate_lf_mode_test
        
        fake = FakeSpiDev(module_type="rfm95w")
        result = simulate_lf_mode_test(fake)
        assert isinstance(result, bool)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_boundary_frequencies(self) -> None:
        """Test boundary frequency values."""
        fake_rfm95w = FakeSpiDev(module_type="rfm95w")
        fake_rfm98w = FakeSpiDev(module_type="rfm98w")
        
        # RFM95W boundary (862 MHz)
        assert fake_rfm95w.is_frequency_supported(862000) is True
        assert fake_rfm95w.is_frequency_supported(861999) is False
        
        # RFM98W boundary (525 MHz)
        assert fake_rfm98w.is_frequency_supported(525000) is True
        assert fake_rfm98w.is_frequency_supported(525001) is False

    def test_multiple_module_types(self) -> None:
        """Test creating multiple FakeSpiDev instances."""
        modules = [
            FakeSpiDev(module_type="rfm95w"),
            FakeSpiDev(module_type="rfm98w"),
            FakeSpiDev(module_type="multi_band"),
            FakeSpiDev(module_type="none"),
        ]
        
        for i, module in enumerate(modules):
            assert module.module_type == ["rfm95w", "rfm98w", "multi_band", "none"][i]

    def test_register_overflow(self) -> None:
        """Test register value overflow handling."""
        fake = FakeSpiDev()
        
        # Test with maximum register value
        fake.set_register(0x42, 0xFF)
        assert fake.get_register(0x42) == 0xFF
        
        # Test with zero register value
        fake.set_register(0x42, 0x00)
        assert fake.get_register(0x42) == 0x00


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
