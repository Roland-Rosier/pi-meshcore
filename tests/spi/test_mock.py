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

"""Tests for ``MockSpiBus`` register simulation behavior."""

import pytest

from tests.spi.mock import MockSpiBus


class TestMockSpiBus:
    """Tests for the ``MockSpiBus`` class."""

    def test_init_defaults(self) -> None:
        bus = MockSpiBus()
        assert bus.bus_number == 0
        assert bus.device_number == 0
        assert bus.max_speed_hz == 1000000
        assert bus.mode == 0
        assert bus.lsbfirst is False
        assert bus.no_cs is False

    def test_init_with_custom_values(self) -> None:
        bus = MockSpiBus(max_speed_hz=500000, mode=3, lsbfirst=True, no_cs=True)
        assert bus.bus_number == 0
        assert bus.device_number == 0
        assert bus.max_speed_hz == 500000
        assert bus.mode == 3
        assert bus.lsbfirst is True
        assert bus.no_cs is True

    def test_open_opens_device(self) -> None:
        bus = MockSpiBus(bus_number=0, device_number=1)
        bus.open()
        assert bus.bus_number == 0
        assert bus.device_number == 1

    def test_open_takes_no_args_and_bus_device_fixed_at_construction(self) -> None:
        import inspect

        bus = MockSpiBus(bus_number=2, device_number=7)
        assert [
            param.name
            for param in inspect.signature(MockSpiBus.open).parameters.values()
            if param.name != "self"
        ] == []
        bus.open()
        assert bus.bus_number == 2
        assert bus.device_number == 7
        assert bus._opened is True

    def test_close_closes_device(self) -> None:
        bus = MockSpiBus(bus_number=0, device_number=1)
        bus.open()
        bus.close()
        assert bus._opened is False

    @pytest.mark.asyncio
    async def test_xfer2_raises_when_not_opened(self) -> None:
        bus = MockSpiBus()
        try:
            await bus.xfer2([0x01 | 0x80, 0xFF])
        except RuntimeError:
            pass
        else:
            raise AssertionError("Should have raised")

    @pytest.mark.asyncio
    async def test_xfer2_returns_simulated_response(self) -> None:
        bus = MockSpiBus(bus_number=0, device_number=1)
        bus.open()
        result = await bus.xfer2([0x01 | 0x80, 0xFF])
        assert isinstance(result, list)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_xfer2_empty_data_returns_empty(self) -> None:
        bus = MockSpiBus(bus_number=0, device_number=1)
        bus.open()
        result = await bus.xfer2([])
        assert result == []

    def test_properties_return_initial_values(self) -> None:
        bus = MockSpiBus(max_speed_hz=2000000, mode=1, lsbfirst=True, no_cs=False)
        assert bus.max_speed_hz == 2000000
        assert bus.mode == 1
        assert bus.lsbfirst is True
        assert bus.no_cs is False

    @pytest.mark.asyncio
    async def test_protocol_compliance(self) -> None:
        bus = MockSpiBus(bus_number=0, device_number=0)
        bus.open()
        result = await bus.xfer2([1])
        assert isinstance(result, list)
        assert len(result) == 2
        bus.close()


class TestMockSpiBusFactory:
    """Tests for the ``MockSpiBusFactory`` class (exercises the moved ``SpiBus`` import)."""

    def test_create_exposes_spi_bus_interface(self) -> None:
        from tests.spi.mock import MockSpiBusFactory

        bus = MockSpiBusFactory().create(bus=2, device=3)
        assert callable(bus.open)
        assert callable(bus.close)
        assert bus.max_speed_hz == 1000000
        assert bus.mode == 0
        assert bus.lsbfirst is False
        assert bus.no_cs is False
        bus.open()
        assert bus.bus_number == 2
        assert bus.device_number == 3
        bus.close()
        assert bus._opened is False


class TestFakeSpiBusKernelFactory:
    """Tests for the ``FakeSpiBusKernelFactory`` context-manager factory."""

    @pytest.mark.asyncio
    async def test_create_bus_wires_fake_kernel_and_closes(self) -> None:
        from tests.fakes import FakeSpiDev
        from tests.spi.mock import FakeSpiBusKernelFactory

        with FakeSpiBusKernelFactory().create_bus(bus=0, device=1) as bus:
            assert bus.bus_number == 0
            assert bus.device_number == 1
            assert isinstance(bus._spidev, FakeSpiDev)
            result = await bus.xfer2([0x01 | 0x80, 0xFF])
            assert isinstance(result, list)
            assert result == [0x81, 0xFF]
        assert bus._spidev is None


class TestMockModuleImport:
    """Defensive coverage that ``tests.spi.mock`` imports without ``spidev``."""

    def test_mock_importable_without_spidev(self) -> None:
        import tests.spi.mock as mock_module

        assert hasattr(mock_module, "MockSpiBusFactory")
        assert hasattr(mock_module, "FakeSpiBusKernelFactory")
        assert mock_module.spidev_available() in (True, False)
