# Copyright (c) 2026 Project Authors. All rights reserved.

"""Pytest fixtures for LoRa module testing."""

from typing import Generator
import pytest

from tests.fakes import FakeSpiDev


@pytest.fixture
def fake_spi_rfm95w() -> FakeSpiDev:
    """Provide a FakeSpiDev configured as an RFM95W (SX1276)."""
    spi = FakeSpiDev(module_type="rfm95w")
    return spi


@pytest.fixture
def fake_spi_rfm98w() -> FakeSpiDev:
    """Provide a FakeSpiDev configured as an RFM98W (SX1278)."""
    spi = FakeSpiDev(module_type="rfm98w")
    return spi


@pytest.fixture
def fake_spi_multi_band() -> FakeSpiDev:
    """Provide a FakeSpiDev configured as a multi-band module."""
    spi = FakeSpiDev(module_type="multi_band")
    return spi


@pytest.fixture
def fake_spi_none() -> FakeSpiDev:
    """Provide a FakeSpiDev configured as 'none' (no device)."""
    spi = FakeSpiDev(module_type="none")
    return spi


@pytest.fixture
def rfm95w_factory(fake_spi_rfm95w: FakeSpiDev) -> Generator[FakeSpiDev, None, None]:
    """Provide a SPI factory that returns an RFM95W fake device."""
    yield fake_spi_rfm95w


@pytest.fixture
def rfm98w_factory(fake_spi_rfm98w: FakeSpiDev) -> Generator[FakeSpiDev, None, None]:
    """Provide a SPI factory that returns an RFM98W fake device."""
    yield fake_spi_rfm98w
