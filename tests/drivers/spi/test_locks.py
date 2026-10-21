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

"""Tests for lock registry correctness in ``spi/locks.py``."""

import asyncio
import inspect
import types

import pytest
from src.pi_lora.drivers.spi.locks import SpiLock, get_bus_lock


class TestLockRegistry:
    """Verify lock registry returns consistent locks per bus number.

    ``get_bus_lock`` is an ``async def`` per Phase H; every call must be
    ``await``-ed inside an ``async def`` marked ``@pytest.mark.asyncio``.
    """

    @pytest.mark.asyncio
    async def test_same_lock_per_bus(self) -> None:
        lock_a = await get_bus_lock(0)
        lock_b = await get_bus_lock(0)
        assert lock_a is lock_b

    @pytest.mark.asyncio
    async def test_different_locks_per_bus(self) -> None:
        lock_0 = await get_bus_lock(0)
        lock_1 = await get_bus_lock(1)
        assert lock_0 is not lock_1

    @pytest.mark.asyncio
    async def test_multiple_buses(self) -> None:
        locks: dict[int, SpiLock] = {}
        for bus_id in range(10):
            if bus_id not in locks:
                locks[bus_id] = await get_bus_lock(bus_id)
        # Verify consistency: re-fetching should return same lock
        for bus_id in range(10):
            assert await get_bus_lock(bus_id) is locks[bus_id]

    @pytest.mark.asyncio
    async def test_negative_bus_number(self) -> None:
        """Lock registry should handle negative bus numbers."""
        lock_neg = await get_bus_lock(-1)
        lock_neg_again = await get_bus_lock(-1)
        assert lock_neg is lock_neg_again


class TestCancellationLeak:
    """Verify ``async with lock:`` never leaks a release on cancellation.

    Section 2.5 remediation. With the old ``acquired``/``finally``/``release()``
    pattern, a coroutine cancelled during ``await lock.acquire()`` could leave the
    worker thread holding the lock while ``acquired`` stayed ``False``, producing
    a leak. The corrected ``async with lock:`` pattern relies on ``aiologic.Lock``
    managing cancellation internally: if ``__aenter__`` never completes acquisition,
    the lock never reports ownership and no release is ever issued. This test
    cancels a task while it is inside the lock scope and asserts the lock ends up
    un-held (``lock.locked() is False``) with no ``RuntimeError: release
    unlocked lock``. The scenario is deterministic: the task is cancelled after it
    has demonstrably entered the lock scope, so ``__aexit__`` must run and release.
    """

    @pytest.mark.asyncio
    async def test_cancellation_inside_lock_scope_does_not_leak(self) -> None:
        """A task cancelled inside ``async with lock:`` leaves the lock un-held."""
        lock = await get_bus_lock(0)
        assert lock.locked() is False

        async def _coro() -> None:
            async with lock:
                await asyncio.sleep(0.5)

        coro = _coro()
        task = asyncio.ensure_future(coro)

        # Let the task acquire the lock and reach the blocking ``sleep``.
        await asyncio.sleep(0)
        await asyncio.sleep(0)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # No leak: the lock is not left held; no ``RuntimeError: release
        # unlocked lock`` could have occurred because aiologic.Lock never
        # issued a release for an unacquired state.
        assert lock.locked() is False

    @pytest.mark.asyncio
    async def test_cancellation_at_acquire_boundary_does_not_leak(self) -> None:
        """Cancelled during ``__aenter__`` (acquire) leaves the lock un-held."""
        lock = await get_bus_lock(1)
        assert lock.locked() is False

        async def _coro() -> None:
            # Cancel the outer task right as it begins acquiring the lock.
            await asyncio.sleep(0)
            async with lock:
                await asyncio.sleep(0.5)

        coro = _coro()
        task = asyncio.ensure_future(coro)

        # Give the task a chance to enter ``async with lock:``; cancel while it
        # is still within the acquisition or inside the scope — either way the
        # lock must end un-held.
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert lock.locked() is False


class TestLockProtocolSignatures:
    """Verify the ``SpiLock`` protocol signatures match ``aiologic.Lock``.

    Phase 11 corrections. ``async_acquire`` must be a coroutine (an ``async
    def``) because the concrete ``aiologic.Lock.async_acquire`` is a coroutine;
    calling it without ``await`` yields a ``types.CoroutineType`` and awaiting
    it yields a ``bool``. ``__enter__`` and ``__aenter__`` must return the lock
    instance itself so they are faithful self-returning context managers.

    Each test exercises a distinct bus number so the shared per-bus
    :class:`aiologic.Lock` instances never leak ownership across tests.
    """

    @pytest.mark.asyncio
    async def test_async_acquire_is_a_coroutine(self) -> None:
        """``async_acquire`` returns a coroutine object when awaited-less."""
        lock = await get_bus_lock(0)
        raw = lock.async_acquire()
        assert isinstance(raw, types.CoroutineType)
        raw.close()

    @pytest.mark.asyncio
    async def test_async_acquire_returns_bool(self) -> None:
        """Awaited ``async_acquire`` resolves to a boolean."""
        lock = await get_bus_lock(1)
        result = await lock.async_acquire()
        assert isinstance(result, bool)
        lock.async_release()

    def test_enter_returns_self(self) -> None:
        """``with lock:`` returns the lock instance itself."""
        lock = asyncio.new_event_loop().run_until_complete(get_bus_lock(2))
        with lock as entered:
            assert entered is lock
        assert entered is lock

    @pytest.mark.asyncio
    async def test_aenter_returns_self(self) -> None:
        """``async with lock:`` returns the lock instance itself."""
        lock = await get_bus_lock(3)
        async with lock as entered:
            assert entered is lock
        assert entered is lock

    @pytest.mark.asyncio
    async def test_protocol_async_acquire_is_coroutine_function(self) -> None:
        """The concrete lock's ``async_acquire`` is a coroutine function."""
        lock = await get_bus_lock(4)
        assert inspect.iscoroutinefunction(lock.async_acquire) is True
