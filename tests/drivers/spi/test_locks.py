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


from src.pi_lora.drivers.spi.locks import SpiLock, get_bus_lock


class TestLockRegistry:
    """Verify lock registry returns consistent locks per bus number."""

    def test_same_lock_per_bus(self) -> None:
        lock_a = get_bus_lock(0)
        lock_b = get_bus_lock(0)
        assert lock_a is lock_b

    def test_different_locks_per_bus(self) -> None:
        lock_0 = get_bus_lock(0)
        lock_1 = get_bus_lock(1)
        assert lock_0 is not lock_1

    def test_multiple_buses(self) -> None:
        locks: dict[int, SpiLock] = {}
        for bus_id in range(10):
            if bus_id not in locks:
                locks[bus_id] = get_bus_lock(bus_id)
        # Verify consistency: re-fetching should return same lock
        for bus_id in range(10):
            assert get_bus_lock(bus_id) is locks[bus_id]

    def test_negative_bus_number(self) -> None:
        """Lock registry should handle negative bus numbers."""
        lock_neg = get_bus_lock(-1)
        lock_neg_again = get_bus_lock(-1)
        assert lock_neg is lock_neg_again
