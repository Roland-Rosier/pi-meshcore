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

"""Tests for ``RealSpiBus`` protocol compliance and lifecycle."""

import pytest
from src.pi_lora.drivers.spi.bus import SpiBus

from tests.spi.mock import FakeSpiBusKernelFactory, MockSpiBus


class TestSpiBusProtocol:
    """Verify that ``MockSpiBus`` satisfies the ``SpiBus`` protocol."""

    def test_mock_is_spi_bus(self) -> None:
        bus: SpiBus = MockSpiBus()
        assert isinstance(bus, MockSpiBus)

    def test_protocol_requires_open(self) -> None:
        bus = MockSpiBus()
        bus.open(bus=0, device=0)
        assert bus._opened is True

    def test_protocol_requires_close(self) -> None:
        bus = MockSpiBus()
        bus.open(bus=0, device=0)
        bus.close()
        assert bus._opened is False


class TestRealSpiBusLifecycle:
    """Test ``RealSpiBus`` lifecycle through the factory."""

    @pytest.mark.asyncio
    async def test_init_without_open_raises_on_xfer2(self) -> None:
        from src.pi_lora.drivers.spi.bus import RealSpiBus

        bus = RealSpiBus()
        with pytest.raises(RuntimeError, match="SPI bus not opened"):
            await bus.xfer2([0x01])


class TestMockSpiBusOpenClose:
    """Test MockSpiBus open/close lifecycle."""

    def test_open_sets_identity(self) -> None:
        bus = MockSpiBus()
        bus.open(bus=1, device=3)
        assert bus.bus_number == 1
        assert bus.device_number == 3

    @pytest.mark.asyncio
    async def test_close_clears_registers(self) -> None:
        bus = MockSpiBus()
        bus.open(bus=0, device=0)
        await bus.xfer2([0x81, 0xFF])
        bus.close()
        assert bus._registers == {}

    @pytest.mark.asyncio
    async def test_xfer2_without_open_raises(self) -> None:
        bus = MockSpiBus()
        with pytest.raises(RuntimeError, match="SPI bus not opened"):
            await bus.xfer2([0x81, 0xFF])


class TestXfer2Bytearray:
    """Verify ``xfer2`` accepts and transparently converts ``bytearray``."""

    @pytest.mark.asyncio
    async def test_xfer2_accepts_bytearray(self) -> None:
        bus = MockSpiBus()
        bus.open(bus=0, device=0)
        result = await bus.xfer2(bytearray([0x81, 0x42]))
        assert isinstance(result, list)
        assert all(isinstance(v, int) for v in result)
        assert result == [0x81, 0x42]

    @pytest.mark.asyncio
    async def test_xfer2_converts_bytearray_to_list(self) -> None:
        data = bytearray([0x81, 0x42, 0x7F, 0x00])
        list_result = await self._xfer2(data, list(data))
        bytearray_result = await self._xfer2(data, bytearray(data))
        assert list_result == bytearray_result

    @staticmethod
    async def _xfer2(data: list[int] | bytearray, payload: list[int] | bytearray) -> list[int]:
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            return await bus.xfer2(payload)
