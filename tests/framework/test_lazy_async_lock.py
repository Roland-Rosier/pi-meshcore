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

import asyncio
from pi_lora.framework.lazy_async_lock import LazyAsyncLock


def test_single_initialization_under_concurrency() -> None:
    """Verify only ONE aiologic.Lock created under 100 concurrent callers."""

    async def _acquire_and_record() -> object:
        acquired = await lock.acquire()
        created.add(id(acquired))
        return acquired

    lock = LazyAsyncLock()
    created: set[int] = set()
    asyncio.run(asyncio.gather(*[_acquire_and_record() for _ in range(100)]))
    assert len(created) == 1, f"Expected 1 lock, got {len(created)}"


def test_holder_persisted() -> None:
    """Verify holder lock is reused across calls."""

    async def _run() -> None:
        await lock.acquire()
        h1 = lock._holder
        await lock.acquire()
        h2 = lock._holder
        assert h1 is h2, "Holder not persisted"

    lock = LazyAsyncLock()
    asyncio.run(_run())


def test_no_sentinel_race() -> None:
    """Verify no AttributeError on concurrent init + else-branch access."""

    async def _mixed_access() -> object:
        return await lock.acquire()

    lock = LazyAsyncLock()
    asyncio.run(asyncio.gather(*[_mixed_access() for _ in range(200)]))


def test_stress_concurrent_access() -> None:
    """Stress test with many concurrent operations."""

    async def _work() -> None:
        async with await lock.acquire():
            await asyncio.sleep(0.001)

    lock = LazyAsyncLock()
    asyncio.run(asyncio.gather(*[_work() for _ in range(500)]))
