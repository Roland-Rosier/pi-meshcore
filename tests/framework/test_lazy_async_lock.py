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

"""Concurrency tests for LazyAsyncLock — verifies race-free initialization."""

from __future__ import annotations

import asyncio

from pi_lora.framework.lazy_async_lock import LazyAsyncLock


def test_single_initialization_under_concurrency() -> None:
    """Verify only ONE aiologic.Lock created under 100 concurrent callers."""

    async def _coro() -> set[int]:
        lock = LazyAsyncLock()
        created: set[int] = set()

        async def _acquire_and_record() -> object:
            acquired = await lock.acquire()
            created.add(id(acquired))
            return acquired

        await asyncio.gather(*[_acquire_and_record() for _ in range(100)])
        assert len(created) == 1, f"Expected 1 lock, got {len(created)}"
        return created

    asyncio.run(_coro())


def test_holder_persisted() -> None:
    """Verify holder lock is reused across calls."""

    async def _coro() -> None:
        lock = LazyAsyncLock()
        await lock.acquire()
        h1 = lock._holder
        await lock.acquire()
        h2 = lock._holder
        assert h1 is h2, "Holder not persisted"

    asyncio.run(_coro())


def test_no_sentinel_race() -> None:
    """Verify no AttributeError on concurrent init + else-branch access."""

    async def _coro() -> None:
        lock = LazyAsyncLock()

        async def _mixed_access() -> object:
            return await lock.acquire()

        await asyncio.gather(*[_mixed_access() for _ in range(200)])

    asyncio.run(_coro())


def test_stress_concurrent_access() -> None:
    """Stress test with many concurrent operations."""

    async def _coro() -> None:
        lock = LazyAsyncLock()

        async def _work() -> None:
            acquired = await lock.acquire()
            async with acquired:
                await asyncio.sleep(0.001)

        await asyncio.gather(*[_work() for _ in range(500)])

    asyncio.run(_coro())


def test_no_direct_context_manager() -> None:
    """Verify LazyAsyncLock cannot be used directly as async context manager.

    The class is designed for: await lock.acquire(); async with result:
    Direct usage (async with lock:) fails because __aenter__/__aexit__
    are intentionally not implemented (removed entirely).
    """
    import asyncio

    async def _coro() -> None:
        lock = LazyAsyncLock()
        assert not hasattr(lock, "__aenter__"), "__aenter__ must be absent"
        assert not hasattr(lock, "__aexit__"), "__aexit__ must be absent"
        try:
            async with lock:  # type: ignore[attr-defined] — should fail
                pass
            raise AssertionError("Expected TypeError for direct async with usage")
        except TypeError:
            pass  # Expected — no __aenter__/__aexit__ methods exist

    asyncio.run(_coro())
