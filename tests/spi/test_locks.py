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

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

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

    @pytest.mark.asyncio
    async def test_concurrent_get_bus_lock_no_deadlock(self) -> None:
        """Concurrent ``await get_bus_lock`` on same/different buses resolve."""
        results = await asyncio.gather(
            get_bus_lock(0),
            get_bus_lock(0),
            get_bus_lock(1),
            get_bus_lock(1),
            get_bus_lock(2),
        )
        assert len(results) == 5
        assert results[0] is results[1]
        assert results[2] is results[3]
        assert results[0] is not results[2]
        assert results[2] is not results[4]


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
        assert await get_bus_lock(0) is await get_bus_lock(0)

        bus = RealSpiBus()
        bus.bus_number = 0
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        real_to_thread = asyncio.to_thread
        observed: list[tuple[Any, tuple[Any, ...]]] = []

        def _spy(callable_: Any, *args: Any) -> Any:
            observed.append((callable_, args))
            return real_to_thread(callable_, *args)

        with patch("asyncio.to_thread", _spy):
            result = await bus.xfer2(bytearray([1, 2, 3]))

        assert result == [1, 2, 3]
        assert isinstance(result, list)
        assert len(result) == 3

        xfer2_calls = [
            (callable_, args)
            for callable_, args in observed
            if callable_ is bus._spidev.xfer2
        ]
        assert len(xfer2_calls) == 1
        called_callable, called_args = xfer2_calls[0]
        assert called_callable is bus._spidev.xfer2
        assert called_args[0] == bytearray([1, 2, 3])


class TestAsyncSpiLockRelease:
    """Tests for ``_AsyncSpiLock.release`` dual branches (Fix #4)."""

    def test_release_awaitable_is_awaited(self) -> None:
        """A ``release`` returning an awaitable is awaited so the lock is not leaked."""
        from pi_lora.drivers.spi.locks import _AsyncSpiLock

        released: bool = False

        async def _release_coroutine() -> None:
            nonlocal released
            released = True

        underlying = MagicMock()
        underlying.release.return_value = _release_coroutine()

        lock = _AsyncSpiLock(underlying)
        lock.release()

        assert released is True

    def test_release_non_awaitable_is_sync(self) -> None:
        """A ``release`` returning a non-awaitable is released synchronously."""
        from pi_lora.drivers.spi.locks import _AsyncSpiLock

        underlying = MagicMock()
        underlying.release.return_value = None

        lock = _AsyncSpiLock(underlying)
        lock.release()

        underlying.release.assert_called_once()


class TestRealSpiBusExceptionMasking:
    """Tests that ``RealSpiBus.xfer2`` preserves the acquire() exception (Fix #1).

    When ``await lock.acquire()`` raises (cancellation/timeout), the original
    exception must propagate out of ``xfer2``. The pre-fix implementation called
    ``lock.release()`` unconditionally in ``finally`` on an unacquired lock,
    raising ``RuntimeError: release unlocked lock`` and masking the original
    exception. The fix tracks acquisition success so ``release()`` runs only
    when ``acquire()`` succeeded.
    """

    @pytest.mark.asyncio
    async def test_acquire_failure_preserves_original_exception(self) -> None:
        """``xfer2`` raises the original acquire() exception, never the mask.

        ``get_bus_lock`` is replaced with an async stub returning a lock whose
        ``acquire()`` raises and whose ``release()`` asserts it is never called,
        proving ``release()`` is skipped when ``acquire()`` failed.
        """
        bus = RealSpiBus()
        bus.bus_number = 0
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        original_exception: Exception = RuntimeError("lock acquisition cancelled")
        release_called: bool = False

        async def _acquire() -> None:
            raise original_exception

        def _release() -> None:
            nonlocal release_called
            release_called = True

        fake_lock = MagicMock()
        fake_lock.acquire = _acquire
        fake_lock.release = _release

        with patch(
            "pi_lora.drivers.spi.bus.get_bus_lock",
            return_value=fake_lock,
        ), pytest.raises(RuntimeError) as exc_info:
            await bus.xfer2(bytearray([1, 2, 3]))

        assert exc_info.value is original_exception
        assert release_called is False
        bus._spidev.xfer2.assert_not_called()
