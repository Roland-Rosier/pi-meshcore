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

``get_bus_lock`` materialises exactly one raw :class:`aiologic.Lock` per bus
number. The registry guard is an ``asyncio.Lock`` holder (not an ``aiologic.Lock``),
so the per-bus lock is the single instance every caller receives. Under many
concurrent callers of one bus, no race must produce duplicate per-bus locks: every
caller observes the same instance. This is the R-3 race-free property.
"""

import asyncio
from typing import Any

import pytest

from pi_lora.drivers.spi import locks


@pytest.mark.asyncio
async def test_same_bus_returns_same_instance_under_concurrency() -> None:
    """100 concurrent callers of one bus observe the same per-bus instance."""
    locks._bus_locks.clear()

    async def _caller() -> Any:
        return await locks.get_bus_lock(0)

    results = await asyncio.gather(
        *[_caller() for _ in range(100)], return_exceptions=True
    )

    assert len(results) == 100
    assert all(r is results[0] for r in results), "all callers get the same bus lock"


@pytest.mark.asyncio
async def test_distinct_buses_get_distinct_locks_under_concurrency() -> None:
    """Two buses each get one lock; same-bus identical, cross-bus distinct."""
    locks._bus_locks.clear()

    async def _caller(bus_number: int) -> Any:
        return await locks.get_bus_lock(bus_number)

    results = await asyncio.gather(
        *[_caller(0) for _ in range(10)],
        *[_caller(1) for _ in range(10)],
        return_exceptions=True,
    )

    bus0 = results[:10]
    bus1 = results[10:]
    assert all(lock is bus0[0] for lock in bus0), "all bus-0 results identical"
    assert all(lock is bus1[0] for lock in bus1), "all bus-1 results identical"
    assert bus0[0] is not bus1[0], "bus-0 and bus-1 locks must be distinct"
