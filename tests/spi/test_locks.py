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

"""Tests for the SPI lock registry and context-aware dual-mode locks."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from pi_lora.drivers.spi.bus import RealSpiBus
from pi_lora.drivers.spi.locks import _SyncSpiLock, get_bus_lock, get_bus_lock_sync


class TestLockRegistry:
    """Tests for ``get_bus_lock`` / ``get_bus_lock_sync`` registry behaviour."""

    def test_registry_returns_same_instance_sync(self) -> None:
        lock_a = get_bus_lock_sync(0)
        lock_b = get_bus_lock_sync(0)
        assert lock_a is lock_b

    @pytest.mark.asyncio
    async def test_registry_returns_same_instance_async(self) -> None:
        lock_a = await get_bus_lock(0)
        lock_b = await get_bus_lock(0)
        assert lock_a is lock_b

    def test_different_buses_return_different_instances(self) -> None:
        assert get_bus_lock_sync(0) is not get_bus_lock_sync(1)

    @pytest.mark.asyncio
    async def test_different_buses_return_different_instances_async(self) -> None:
        assert await get_bus_lock(0) is not await get_bus_lock(1)

    @pytest.mark.asyncio
    async def test_sync_and_async_share_instance(self) -> None:
        async_lock = await get_bus_lock(0)
        sync_lock = get_bus_lock_sync(0)
        assert async_lock is sync_lock


class TestLockAcquisition:
    """Tests for acquire/release across both contexts."""

    @pytest.mark.asyncio
    async def test_acquire_release_async(self) -> None:
        lock = await get_bus_lock(0)
        await lock.acquire()
        lock.release()

    def test_sync_acquire_release(self) -> None:
        lock = get_bus_lock_sync(0)
        lock.acquire()
        lock.release()


class TestSyncSpiLockDualMode:
    """Tests for the context-aware dual-mode ``_SyncSpiLock`` branches."""

    def test_sync_context_returns_none_and_blocks(self) -> None:
        lock = _SyncSpiLock()
        result = lock.acquire()
        assert result is None
        lock.release()

    @pytest.mark.asyncio
    async def test_async_context_returns_awaitable(self) -> None:
        lock = _SyncSpiLock()
        awaitable = lock.acquire()
        assert awaitable is not None
        await awaitable
        lock.release()


class TestRealSpiBusXfer2:
    """Tests that ``RealSpiBus.xfer2`` uses the shared per-bus lock."""

    @pytest.mark.asyncio
    async def test_xfer2_uses_shared_bus_lock(self) -> None:
        bus_one = RealSpiBus()
        bus_one.bus_number = 0
        bus_one._spidev = AsyncMock()
        bus_one._spidev.xfer2 = MagicMock(return_value=[0, 0, 0])

        bus_two = RealSpiBus()
        bus_two.bus_number = 0
        bus_two._spidev = AsyncMock()
        bus_two._spidev.xfer2 = MagicMock(return_value=[0, 0])

        assert await get_bus_lock(0) is await get_bus_lock(0)

        result = await bus_one.xfer2(bytearray([1, 2, 3]))
        assert isinstance(result, list)
        assert len(result) == 3

        second_result = await bus_two.xfer2(bytearray([4, 5]))
        assert isinstance(second_result, list)
        assert len(second_result) == 2
