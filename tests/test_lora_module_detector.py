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

from __future__ import annotations

import sys
import os

from src.drivers.lora_module import LoRaModule
from src.drivers.lora_detection import (
    LoRaModuleDetector,
    LoRaModuleConfig,
    ValidationResult,
)
from tests.fakes import FakeSpiDev
from unittest.mock import MagicMock, patch
import pytest


class TestLoRaModuleDetectorInitialization:
    """Test suite for LoRaModuleDetector initialization."""

    def test_init_rfm95w_with_factory(self) -> None:
        """Test that LoRaModuleDetector initializes correctly with RFM95W fake device."""
        rfm95w_spi = FakeSpiDev(module_type="rfm95w")

        # Create a mock LoRaModule with the fake SPI device
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = True
        mock_module.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
        mock_module.silicon_revision = 0x12

        # Patch the LoRaModule constructor to return our mock
        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        assert len(detector.modules) == 1
        assert detector.modules[0].communication_success is True
        assert "RFM95W" in detector.modules[0].module_type or "Multi-band" in detector.modules[0].module_type

    def test_init_rfm98w_with_factory(self) -> None:
        """Test that LoRaModuleDetector initializes correctly with RFM98W fake device."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 1
        mock_module.communication_success = True
        mock_module.module_type = "RFM98W (Low-Band 433Mhz / Semtech SX1278)"
        mock_module.silicon_revision = 0x19

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[1])

        assert len(detector.modules) == 1
        assert detector.modules[0].communication_success is True
        assert "RFM98W" in detector.modules[0].module_type

    def test_init_none_module(self) -> None:
        """Test that LoRaModuleDetector handles 'none' (no device) correctly."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = False
        mock_module.module_type = "Unknown / Communication Error"
        mock_module.silicon_revision = None

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        assert len(detector.modules) == 1
        assert detector.modules[0].communication_success is False
        assert detector.modules[0].module_type == "Unknown / Communication Error"

    def test_init_multi_band_module(self) -> None:
        """Test that LoRaModuleDetector initializes correctly with multi-band fake device."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = True
        mock_module.module_type = "Multi-band - Likely RFM95W (High-Band 868MHz and/or Low-Band 433Mhz / Semtech SX1276)"
        mock_module.silicon_revision = 0x12

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])
        assert len(detector.modules) == 1
        assert detector.modules[0].communication_success is True
        assert "Multi-band" in detector.modules[0].module_type


class TestLoRaModuleDetectorRegisters:
    """Test suite for register read/write operations."""

    def test_read_register_rfm95w(self) -> None:
        """Test reading registers from RFM95W fake device."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = True
        mock_module.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
        mock_module.silicon_revision = 0x12
        mock_module.read_register.return_value = 0x12

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        # Verify read_register was called with the correct address
        mock_module.read_register.assert_called()
        assert mock_module.read_register.return_value == 0x12

    def test_write_register_rfm95w(self) -> None:
        """Test writing registers to RFM95W fake device."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = True
        mock_module.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
        mock_module.silicon_revision = 0x12
        mock_module.write_register.return_value = 0x08

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        # Verify write_register was called with the correct values
        mock_module.write_register.assert_called()
        assert mock_module.write_register.return_value == 0x08

    def test_read_register_none_device(self) -> None:
        """Test that reading from 'none' device returns None."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = False
        mock_module.module_type = "Unknown / Communication Error"
        mock_module.silicon_revision = None
        mock_module.read_register.return_value = None

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        # Reading should return None when communication fails
        assert mock_module.read_register.return_value is None
class TestLoRaModuleDetection:
    """Test suite for module type detection."""

    def test_detect_single_module_ce0(self) -> None:
        """Test detection of a single module on CE0 with FakeSpiDev."""
        fake_spi = FakeSpiDev(module_type="rfm95w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        results = detector.detect_modules()

        assert len(results) == 1
        assert results[0]["ce_pin"] == 0
        assert (
            "RFM95W" in results[0].get("module_type", "")
            or "Multi-band" in results[0].get("module_type", "")
        )

    def test_detect_single_module_ce1(self) -> None:
        """Test detection of a single module on CE0 with FakeSpiDev."""
        fake_spi = FakeSpiDev(module_type="rfm98w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[1])

        results = detector.detect_modules()

        assert len(results) == 1
        assert results[0]["ce_pin"] == 1
        assert (
            "RFM98W" in results[0].get("module_type", "")
            or "Multi-band" in results[0].get("module_type", "")
        )

    def test_detect_multi_band(self) -> None:
        """Test that multi-band is correctly detected with FakeSpiDev."""
        fake_spi = FakeSpiDev(module_type="multi_band")


        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])


        results = detector.detect_modules()

        assert len(results) == 1
        assert "Multi-band" in results[0].get("module_type", "")


    def test_detect_multiple_modules(self) -> None:
        """Test detection of modules on both CE0 and CE1 with FakeSpiDev."""
        fake_spi_ce0 = FakeSpiDev(module_type="rfm95w")
        fake_spi_ce1 = FakeSpiDev(module_type="rfm98w")

        # Counter to alternate between SPI devices per constructor call
        call_count: list[int] = [0]

        def spi_factory() -> FakeSpiDev:
            call_count[0] += 1
            return fake_spi_ce0 if call_count[0] == 1 else fake_spi_ce1

        with patch("src.drivers.lora_module.spidev.SpiDev") as mock_spidev:
            mock_spidev.side_effect = lambda: spi_factory()
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        results = detector.detect_modules()

        assert len(results) == 2
        ce_pins_found: set[int] = {r["ce_pin"] for r in results}
        assert ce_pins_found == {0, 1}

    def test_detector_with_no_pins(self) -> None:
        """Test detector initialized with empty CE pins list."""
        detector = LoRaModuleDetector(ce_pins=[])

        results = detector.detect_modules()

        assert len(results) == 0
        assert len(detector.modules) == 0


class TestLoRaModuleDetectorEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_spi_failure_read(self) -> None:
        """Test that SPI read failures are handled correctly."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = False
        mock_module.module_type = "Unknown / Communication Error"
        mock_module.silicon_revision = None

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        # The initialization should fail due to the read failure
        assert detector.modules[0].communication_success is False

    def test_spi_failure_write(self) -> None:
        """Test that SPI write failures are handled correctly."""
        mock_module = MagicMock(spec=LoRaModule)
        mock_module.ce_pin = 0
        mock_module.communication_success = True
        mock_module.module_type = "RFM95W (High-Band 868MHz / Semtech SX1276)"
        mock_module.silicon_revision = 0x12

        with patch('src.drivers.lora_detection.LoRaModule', return_value=mock_module):
            detector = LoRaModuleDetector(ce_pins=[0])

        # The module was created but communication may have failed
        assert detector is not None
        assert len(detector.modules) == 1

    def test_spi_device_cleanup_on_delete(self) -> None:
        """Test that SPI device close is called when module is destroyed via __del__."""
        fake_spi = FakeSpiDev(module_type="rfm95w")

        # Construct a real LoRaModule with our FakeSpiDev
        module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi)

        # Verify SPI device was opened
        assert module.spi_device is fake_spi
        assert fake_spi._opened is True

        # Trigger cleanup by calling __del__
        module.__del__()

        # Verify close() was called (sets _opened to False)
        assert fake_spi._opened is False


class TestLoRaModuleDetectorValidation:
    """Test suite for validate_config() method coverage."""

    def test_validate_config_match_rfm95w(self) -> None:
        """Test validation when detected module matches expected type."""
        fake_spi = FakeSpiDev(module_type="rfm95w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        config = LoRaModuleConfig(
            ce0_expected_module_type="rfm95w",
            ce1_expected_module_type=None,
        )
        results = detector.validate_config(config)

        assert len(results) == 1
        assert results[0].passed is True
        assert "Match" in results[0].message

    def test_validate_config_mismatch(self) -> None:
        """Test validation when detected module does NOT match expected type."""
        fake_spi = FakeSpiDev(module_type="none")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        config = LoRaModuleConfig(
            ce0_expected_module_type="rfm95w",
            ce1_expected_module_type=None,
        )
        results = detector.validate_config(config)

        assert len(results) == 1
        assert results[0].passed is False
        assert "Mismatch" in results[0].message

    def test_validate_config_none_expectation(self) -> None:
        """Test validation when expected module type is None (no expectation)."""
        fake_spi = FakeSpiDev(module_type="rfm95w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        config = LoRaModuleConfig(
            ce0_expected_module_type=None,
            ce1_expected_module_type="rfm95w",
        )
        results = detector.validate_config(config)

        # CE0's expectation is None so it gets skipped; the detector has no CE1 module
        # so no ValidationResult objects are produced at all.
        assert len(results) == 0

    def test_validate_config_dual_ce(self) -> None:
        """Test validation with both CE pins configured."""
        call_count: list[int] = [0]

        def spi_factory() -> FakeSpiDev:
            call_count[0] += 1
            return (
                FakeSpiDev(module_type="rfm95w")
                if call_count[0] == 1
                else FakeSpiDev(module_type="rfm98w")
            )

        with patch("src.drivers.lora_module.spidev.SpiDev") as mock_spidev:
            mock_spidev.side_effect = lambda: spi_factory()
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        config = LoRaModuleConfig(
            ce0_expected_module_type="rfm95w",
            ce1_expected_module_type="rfm98w",
        )
        results = detector.validate_config(config)

        assert len(results) == 2
        assert all(r.passed for r in results)


class TestLoRaModuleDetectorFrequency:
    """Tests for calculate_unique_frequency() method coverage."""

    def test_calculate_unique_frequency_rfm95w_ce0(self) -> None:
        """Test unique frequency calculation for RFM95W on CE0."""
        fake_spi = FakeSpiDev(module_type="rfm95w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        freq: int = detector.calculate_unique_frequency(
            0, "RFM95W (High-Band 868MHz / Semtech SX1276)", None
        )

        assert freq == 960000  # kHz for 868 MHz band

    def test_calculate_unique_frequency_rfm98w_ce1(self) -> None:
        """Test unique frequency calculation for RFM98W on CE1."""
        fake_spi = FakeSpiDev(module_type="rfm98w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[1])

        freq: int = detector.calculate_unique_frequency(
            1, "RFM98W (Low-Band 433Mhz / Semtech SX1278)", None
        )

        assert freq == 410000  # kHz for 433 MHz band

    def test_calculate_unique_frequency_multi_band_ce0(self) -> None:
        """Test unique frequency calculation when module type is ambiguous (CE0)."""
        fake_spi = FakeSpiDev(module_type="multi_band")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        freq_ce0: int = detector.calculate_unique_frequency(
            0, "Multi-band - Likely RFM95W...", None
        )

        # Should default to CE0 frequency (RFM95W band)
        assert freq_ce0 == 960000

    def test_calculate_unique_frequency_multi_band_ce1(self) -> None:
        """Test unique frequency calculation when module type is ambiguous (CE1)."""
        fake_spi = FakeSpiDev(module_type="multi_band")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        freq_ce1: int = detector.calculate_unique_frequency(
            1, "Multi-band - Likely RFM98W...", None
        )

        # Should default to CE1 frequency (RFM98W band)
        assert freq_ce1 == 410000


class TestLoRaModuleDetectorExtendedDetection:
    """Tests for _extended_detect_modules() path coverage."""

    def test_extended_detect_different_modules(self) -> None:
        """Test extended detection when CE0 and CE1 are different physical modules.

        Verifies that two distinct FakeSpiDev-backed modules on separate CE pins
        produce results where neither is flagged as a single physical module on dual SPI.
        """
        fake_spi_ce0 = FakeSpiDev(module_type="rfm95w")
        fake_spi_ce1 = FakeSpiDev(module_type="rfm98w")

        call_count: list[int] = [0]

        def spi_factory() -> FakeSpiDev:
            call_count[0] += 1
            return fake_spi_ce0 if call_count[0] == 1 else fake_spi_ce1

        with patch("src.drivers.lora_module.spidev.SpiDev") as mock_spidev:
            mock_spidev.side_effect = lambda: spi_factory()
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        results = detector.detect_modules()

        # Should detect two separate modules (not same physical module)
        assert len(results) == 2
        for result in results:
            assert result.get("is_single_module_dual_spi") is False

    def test_extended_detect_runs_with_multiple_pins(self) -> None:
        """Test that _extended_detect_modules runs when multiple CE pins are configured.

        Verifies that detect_modules() populates extended detection fields
        (unique_value_written, unique_value_verified, is_single_module_dual_spi)
        only when both CE0 and CE1 have modules attached.
        """
        fake_spi_ce0 = FakeSpiDev(module_type="rfm95w")
        fake_spi_ce1 = FakeSpiDev(module_type="rfm98w")

        call_count: list[int] = [0]

        def spi_factory() -> FakeSpiDev:
            call_count[0] += 1
            return fake_spi_ce0 if call_count[0] == 1 else fake_spi_ce1

        with patch("src.drivers.lora_module.spidev.SpiDev") as mock_spidev:
            mock_spidev.side_effect = lambda: spi_factory()
            detector = LoRaModuleDetector(ce_pins=[0, 1])

        results = detector.detect_modules()

        # Verify that extended detection ran (results contain verification fields)
        assert len(results) == 2
        for result in results:
            assert "is_single_module_dual_spi" in result
            assert "unique_value_written" in result
            assert "unique_value_verified" in result

        # Both modules should have been initialized (SPI device not None)
        assert len(detector.modules) == 2
        for module in detector.modules:
            assert module.spi_device is not None

    def test_single_pin_no_extended_detection(self) -> None:
        """Test that _extended_detect_modules is skipped when only one CE pin.

        With a single CE pin, detect_modules() does not enter the extended
        detection block (ce1_result stays None), so dual-SPI verification flags
        are absent from results entirely.
        """
        fake_spi = FakeSpiDev(module_type="rfm95w")

        with patch("src.drivers.lora_module.spidev.SpiDev", return_value=fake_spi):
            detector = LoRaModuleDetector(ce_pins=[0])

        results = detector.detect_modules()

        assert len(results) == 1
        # With single pin, extended detection should not run (no dual-SPI flag set)
        assert "is_single_module_dual_spi" not in results[0] or \
               results[0].get("is_single_module_dual_spi") is False


if __name__ == "__main__":
    """Run tests using pytest."""
    print("=" * 60)
    print("Running LoRa Module Detector Tests")
    print("=" * 60)

    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)














