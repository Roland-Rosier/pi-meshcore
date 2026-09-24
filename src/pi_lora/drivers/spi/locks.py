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

from __future__ import annotations

import aiologic  # noqa: F401

_bus_locks: dict[int, aiologic.LowLevelLock] = {}  # type: ignore[name-defined]


def get_bus_lock(bus_number: int) -> aiologic.LowLevelLock:  # type: ignore[name-defined]
    """Get or create a lock for the given bus number.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        The LowLevelLock for the given bus number.
    """
    if bus_number not in _bus_locks:
        _bus_locks[bus_number] = aiologic.LowLevelLock()  # type: ignore[attr-defined]
    return _bus_locks[bus_number]
