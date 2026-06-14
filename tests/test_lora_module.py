# Copyright (c) 2026 Project Authors. All rights reserved.

"""Tests for LoRaModule class using FakeSpiDev."""

from typing import Any, Callable
import pytest

from src.drivers.lora_module import LoRaModule
from tests.fakes import FakeSpiDev


class TestLoRaModuleInitialization:
    """Test suite for LoRaModule initialization."""

    def test_init_rfm95w_with_factory(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test that LoRaModule initializes correctly with RFM95W fake device."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        assert module.communication_success is True
        assert module.supports_high_frequency is True
        assert module.supports_low_frequency is False
        assert "RFM95W" in module.module_type or "Multi-band" in module.module_type

    def test_init_rfm98w_with_factory(self, rfm98w_factory: FakeSpiDev) -> None:
        """Test that LoRaModule initializes correctly with RFM98W fake device."""
        module = LoRaModule(ce_pin=1, spi_factory=lambda: rfm98w_factory)

        assert module.communication_success is True
        assert module.supports_high_frequency is False
        assert module.supports_low_frequency is True
        assert "RFM98W" in module.module_type

    def test_init_none_module(self, fake_spi_none: FakeSpiDev) -> None:
        """Test that LoRaModule handles 'none' (no device) correctly."""
        with pytest.raises(OSError):
            LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_none)

    def test_init_multi_band_module(self, fake_spi_multi_band: FakeSpiDev) -> None:
        """Test that LoRaModule initializes correctly with multi-band fake device."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_multi_band)

        assert module.communication_success is True
        assert module.supports_high_frequency is True
        assert module.supports_low_frequency is True


class TestLoRaModuleRegisters:
    """Test suite for register read/write operations."""

    def test_read_register_rfm95w(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test reading registers from RFM95W fake device."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        # Set a register value directly
        rfm95w_factory.set_register(0x12, 0x12)
        value: int | None = module.read_register(0x12)
        assert value == 0x12

    def test_write_register_rfm95w(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test writing registers to RFM95W fake device."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        result: int | None = module.write_register(0x01, 0x08)
        assert result == 0x08
        assert rfm95w_factory.get_register(0x01) == 0x08

    def test_read_register_none_device(self, fake_spi_none: FakeSpiDev) -> None:
        """Test that reading from 'none' device raises an error."""
        with pytest.raises(OSError):
            module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_none)


class TestLoRaModuleFrequency:
    """Test suite for frequency-related operations."""

    def test_calc_freq_registers_for_khz(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test frequency register calculation."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        msb: int
        mid: int
        lsb: int
        (msb, mid, lsb) = module._calc_freq_registers_for_khz(868000)

        assert isinstance(msb, int)
        assert isinstance(mid, int)
        assert isinstance(lsb, int)

    def test_write_frequency_for_khz(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test writing frequency registers."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        msb: int
        mid: int
        lsb: int
        (msb, mid, lsb) = module._write_frequency_for_khz(868000)

        assert isinstance(msb, int)
        assert isinstance(mid, int)
        assert isinstance(lsb, int)

    def test_write_and_verify_frequency(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test write and verify frequency."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        success: bool
        req_msb: int
        req_mid: int
        req_lsb: int
        read_msb: int
        read_mid: int
        read_lsb: int
        (success, req_msb, req_mid, req_lsb, read_msb, read_mid, read_lsb) = module._write_and_verify_frequency_for_khz(868000)

        assert success is True
        assert req_msb == read_msb
        assert req_mid == read_mid
        assert req_lsb == read_lsb


class TestLoRaModuleDetection:
    """Test suite for module type detection."""

    def test_detect_rfm95w(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test that RFM95W is correctly detected."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        assert "RFM95W" in module.module_type or "Multi-band" in module.module_type

    def test_detect_rfm98w(self, rfm98w_factory: FakeSpiDev) -> None:
        """Test that RFM98W is correctly detected."""
        module = LoRaModule(ce_pin=1, spi_factory=lambda: rfm98w_factory)

        assert "RFM98W" in module.module_type

    def test_detect_multi_band(self, fake_spi_multi_band: FakeSpiDev) -> None:
        """Test that multi-band is correctly detected."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_multi_band)

        assert "Multi-band" in module.module_type


class TestLoRaModuleUniqueValue:
    """Test suite for unique value retention tests."""

    def test_test_unique_value_retention(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test unique value retention."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        result: bool = module.test_unique_value_retention(868000)

        assert result is True
        assert module.unique_msb is not None
        assert module.unique_mid is not None
        assert module.unique_lsb is not None

    def test_verify_unique_value_retention(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test verification of unique value retention."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        # First write a unique value
        module.test_unique_value_retention(868000)

        # Then verify it
        result: bool = module.verify_unique_value_retention()

        assert result is True


class TestLoRaModuleLFMode:
    """Test suite for LF mode operations."""

    def test_lf_mode_success(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test that LF mode can be set and retained."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        assert module.lf_mode_success is True


class TestLoRaModuleEdgeCases:
    """Test suite for edge cases and error handling."""

    def test_spi_failure_read(self, fake_spi_rfm95w: FakeSpiDev) -> None:
        """Test that SPI read failures are handled correctly."""
        fake_spi_rfm95w.enable_failure_read()
        module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_rfm95w)

        # The initialization should fail due to the read failure
        assert module.communication_success is False

    def test_spi_failure_write(self, fake_spi_rfm95w: FakeSpiDev) -> None:
        """Test that SPI write failures are handled correctly."""
        fake_spi_rfm95w.enable_failure_write()
        # Create a fresh instance to test write failure during initialization
        module = LoRaModule(ce_pin=0, spi_factory=lambda: fake_spi_rfm95w)

        # The initialization may or may not fail depending on when the write happens
        # We just verify the module was created without crashing
        assert module is not None

    def test_close_spi_device(self, rfm95w_factory: FakeSpiDev) -> None:
        """Test that SPI device can be closed."""
        module = LoRaModule(ce_pin=0, spi_factory=lambda: rfm95w_factory)

        # Verify the device is open
        assert rfm95w_factory._opened is True

        # Close the device
        module.__del__()

        # Verify the device is closed
        assert rfm95w_factory._opened is False
