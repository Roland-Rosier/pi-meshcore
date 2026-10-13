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

"""Integration tests exercising the ``RealSpiBus -> spidev -> kernel SPI`` chain.

The end-to-end test wires a real ``RealSpiBus`` to a :class:`FakeSpiDev` kernel
through :func:`spidev_kernel_patch` and drives :meth:`RealSpiBus.xfer2`, which
acquires the shared per-bus lock via ``await get_bus_lock`` and offloads the
blocking transfer to a worker thread. The mock test exercises the synchronous
lock path via ``get_bus_lock_sync``.
"""

from __future__ import annotations

import pytest

from pi_lora.drivers.spi.locks import get_bus_lock, get_bus_lock_sync
from tests.spi.mock import FakeSpiBusKernelFactory, MockSpiBus


class TestRealSpiBusKernelChain:
    """End-to-end ``RealSpiBus -> spidev -> kernel SPI`` exercise."""

    @pytest.mark.asyncio
    async def test_real_spi_bus_to_kernel_end_to_end(self) -> None:
        """Construct a ``RealSpiBus`` opened with a fake kernel and run ``xfer2``.

        ``xfer2`` internally acquires the shared per-bus lock via
        ``await get_bus_lock`` and offloads the transfer to the fake kernel SPI,
        which responds to the write transfer with the echoed command+value pair.
        The manual pre-acquire from the original Phase L implementation is
        redundant: ``xfer2`` acquires and releases the same lock instance itself,
        so pre-acquiring it here would deadlock on the non-recursive
        ``aiologic.LowLevelLock``.
        """
        bus = FakeSpiBusKernelFactory().create(bus=0, device=0)
        assert bus.bus_number == 0
        assert bus.device_number == 0
        result = await bus.xfer2(bytearray([0x01 | 0x80, 0x42]))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result == [0x81, 0x42]

    @pytest.mark.asyncio
    async def test_same_bus_lock_is_shared(self) -> None:
        """Two buses on the same bus number share one per-bus lock instance."""
        bus_one = FakeSpiBusKernelFactory().create(bus=0, device=0)
        bus_two = FakeSpiBusKernelFactory().create(bus=0, device=1)

        assert await get_bus_lock(bus_one.bus_number) is await get_bus_lock(bus_two.bus_number)

        await bus_one.xfer2(bytearray([0x81, 0x08]))
        await bus_two.xfer2(bytearray([0x42, 0x00]))


class TestMockSpiBusSyncLock:
    """Mock SPI bus exercises the synchronous lock path via ``get_bus_lock_sync``."""

    def test_mock_bus_uses_sync_lock(self) -> None:
        """Acquire the sync per-bus lock and confirm registry returns the same instance."""
        bus = MockSpiBus()
        bus.open(bus=0, device=0)
        assert bus.bus_number == 0

        lock = get_bus_lock_sync(0)
        lock.acquire()
        lock.release()
        assert get_bus_lock_sync(0) is lock
