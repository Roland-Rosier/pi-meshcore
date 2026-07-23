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

"""Pytest fixtures for LoRa module testing."""

from collections.abc import Generator

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


@pytest.fixture()
def fake_spi_rfm95w_pll_locked(fake_spi_rfm95w: FakeSpiDev) -> FakeSpiDev:
    """RFM95W with PLL lock simulated (for extended detection)."""
    fake_spi_rfm95w.set_pll_lock_state(True)
    return fake_spi_rfm95w


@pytest.fixture()
def fake_spi_rfm98w_pll_not_locked(fake_spi_rfm98w: FakeSpiDev) -> FakeSpiDev:
    """RFM98W with PLL lock NOT simulated (for extended detection)."""
    fake_spi_rfm98w.set_pll_lock_state(False)
    return fake_spi_rfm98w


@pytest.fixture()
def fake_spi_rfm95w_hf_pll_only(fake_spi_rfm95w: FakeSpiDev) -> FakeSpiDev:
    """RFM95W-like module with PLL lock only on HF (915 MHz), not on LF (410 MHz).

    This simulates future hardware that strictly adheres to the original SX1276 spec.
    Requires FakeSpiDev._pll_auto_mode = True for proper behavior.
    """
    fake_spi_rfm95w.set_pll_auto_mode(True)  # Enable frequency-dependent PLL simulation
    return fake_spi_rfm95w


@pytest.fixture()
def fake_spi_rfm98w_lf_pll_only(fake_spi_rfm98w: FakeSpiDev) -> FakeSpiDev:
    """RFM98W-like module with PLL lock only on LF (410 MHz), not on HF (915 MHz).

    This simulates future hardware that strictly adheres to the original SX1278 spec.
    Requires FakeSpiDev._pll_auto_mode = True for proper behavior.
    """
    fake_spi_rfm98w.set_pll_auto_mode(True)  # Enable frequency-dependent PLL simulation
    return fake_spi_rfm98w
