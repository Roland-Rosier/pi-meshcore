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

"""Concurrency regression test for the SPI locks double-checked-locking guard (R-3).

``get_bus_lock`` materialises exactly two ``aiologic.Lock`` instances on first
use for a single bus -- one for the registry guard (``_registry_lock``) and one
for the per-bus ``_bus_locks[bus_number]`` -- because of the double-checked
locking guarded by ``_registry_init_lock``. A counter patching ``aiologic.Lock``
therefore must see exactly 2 calls for one bus across many concurrent callers,
not 1 and not 100. Every caller must observe the same per-bus instance, proving
no race created duplicate locks. This is the R-3 race-free property.
"""

import asyncio
from typing import Any
from unittest.mock import patch

import aiologic
import pytest
from src.pi_lora.drivers.spi import locks


def _reset_registry() -> None:
    """Reset the module-level singletons so the test is deterministic."""
    locks._bus_locks.clear()
    locks._registry_lock = None
    locks._aiologic_module = None
    locks._registry_init_lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_registry_lock_created_once_under_concurrency() -> None:
    """100 concurrent callers of one bus mint exactly two ``aiologic.Lock``.

    One for the registry guard and one for the per-bus lock. All callers must
    observe the same per-bus instance, proving no race created duplicate locks.
    The registry lock is created first (under the guard) and the per-bus lock
    second, and the per-bus lock is the instance every caller receives.
    """
    _reset_registry()

    created: list[Any] = []
    real_lock_cls: type = aiologic.Lock

    def _counting_lock() -> Any:
        lk: Any = real_lock_cls()
        created.append(lk)
        return lk

    with patch.object(aiologic, "Lock", _counting_lock):

        async def _caller() -> Any:
            return await locks.get_bus_lock(0)

        results: list[Any] = await asyncio.gather(
            *[_caller() for _ in range(100)], return_exceptions=True
        )

    assert len(created) == 2, "exactly one registry lock + one per-bus lock for bus 0"
    assert all(r is results[0] for r in results), "all callers get the same bus lock"
    assert created[0] is locks._registry_lock, "registry lock is created first (under guard)"
    assert results[0]._lock is created[1], "per-bus lock is the second created"


@pytest.mark.asyncio
async def test_distinct_buses_get_distinct_locks_under_concurrency() -> None:
    """Two buses each mint one lock; same-bus identical, cross-bus distinct.

    One registry guard creation (shared across both buses) plus one per-bus
    creation per bus, so the counter must read 3. This is the true R-3
    race-free property: no race produced duplicate per-bus or registry locks.
    """
    _reset_registry()

    created: list[Any] = []
    real_lock_cls: type = aiologic.Lock

    def _counting_lock() -> Any:
        lk: Any = real_lock_cls()
        created.append(lk)
        return lk

    with patch.object(aiologic, "Lock", _counting_lock):

        async def _caller(bus_number: int) -> Any:
            return await locks.get_bus_lock(bus_number)

        results: list[Any] = await asyncio.gather(
            *[_caller(0) for _ in range(10)],
            *[_caller(1) for _ in range(10)],
            return_exceptions=True,
        )

    # 1 registry + 1 bus0 + 1 bus1 = 3 locks
    assert len(created) == 3
    bus0 = results[:10]
    bus1 = results[10:]
    assert all(lock is bus0[0] for lock in bus0), "all bus-0 results must be identical"
    assert all(lock is bus1[0] for lock in bus1), "all bus-1 results must be identical"
    assert bus0[0] is not bus1[0], "bus-0 and bus-1 locks must be distinct"
    assert created[0] is locks._registry_lock, "registry lock is created first (under guard)"
