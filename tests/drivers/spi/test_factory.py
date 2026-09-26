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

"""Tests for ``RealSpiBusFactory`` and ``MockSpiBusFactory`` behavior."""
import pytest
from src.pi_lora.drivers.spi.factory import RealSpiBusFactory, SpiBusFactory

from tests.spi.mock import MockSpiBus, MockSpiBusFactory


def _is_spi_bus(bus: object) -> bool:
    """Check that *bus* satisfies the ``SpiBus`` protocol by inspecting required attributes."""
    return (
        hasattr(bus, "open")
        and hasattr(bus, "close")
        and hasattr(bus, "xfer2")
        and hasattr(bus, "max_speed_hz")
        and hasattr(bus, "mode")
        and hasattr(bus, "lsbfirst")
        and hasattr(bus, "no_cs")
    )


class TestRealSpiBusFactory:
    """Verify ``RealSpiBusFactory`` produces ``RealSpiBus`` instances.

    These tests are skipped because ``RealSpiBus.open()`` requires the
    ``spidev`` Cython extension which is not available in this environment.
    """

    @pytest.mark.skip(reason="requires spidev Cython extension")
    def test_create_returns_real_spi_bus(self) -> None:
        factory = RealSpiBusFactory()
        bus = factory.create(bus=0, device=1)
        assert _is_spi_bus(bus)

    @pytest.mark.skip(reason="requires spidev Cython extension")
    def test_create_with_defaults(self) -> None:
        factory = RealSpiBusFactory()
        bus = factory.create(bus=0, device=0)
        assert _is_spi_bus(bus)


class TestMockSpiBusFactory:
    """Verify ``MockSpiBusFactory`` produces ``MockSpiBus`` instances."""

    def test_create_returns_mock_spi_bus(self) -> None:
        factory = MockSpiBusFactory()
        bus = factory.create(bus=1, device=2)
        assert isinstance(bus, MockSpiBus)

    def test_create_opens_the_bus(self) -> None:
        factory = MockSpiBusFactory()
        bus = factory.create(bus=1, device=2)
        assert bus.bus_number == 1
        assert bus.device_number == 2
        assert bus._opened is True


class TestFactoryProtocol:
    """Verify factories satisfy the ``SpiBusFactory`` protocol."""

    @pytest.mark.skip(reason="requires spidev Cython extension")
    def test_real_factory_is_spi_bus_factory(self) -> None:
        factory: SpiBusFactory = RealSpiBusFactory()
        bus = factory.create(bus=0, device=0)
        assert _is_spi_bus(bus)

    def test_mock_factory_is_spi_bus_factory(self) -> None:
        factory: SpiBusFactory = MockSpiBusFactory()
        bus = factory.create(bus=0, device=0)
        assert _is_spi_bus(bus)
