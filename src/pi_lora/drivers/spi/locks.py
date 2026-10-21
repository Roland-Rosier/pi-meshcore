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

import asyncio
from typing import Any, Protocol, Self

import aiologic


class SpiLock(Protocol):
    """Protocol describing the per-bus SPI critical-section lock.

    The concrete implementation returned by :func:`get_bus_lock` is an
    :class:`aiologic.Lock`, a native dual-mode lock usable in both synchronous
    and asynchronous contexts. In an async context the lock is acquired with
    ``async with lock:`` or ``await lock.async_acquire()`` and released with
    ``lock.async_release()``; in a pure sync context ``with lock:`` is used.
    The registry hands back a single shared instance per bus number so that
    transfers on the same bus never interleave.
    """

    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    async def async_acquire(
        self, *, blocking: bool = True, timeout: float | None = None
    ) -> bool: ...
    def async_release(self) -> None: ...
    def locked(self) -> bool: ...


_bus_locks: dict[int, aiologic.Lock] = {}
_registry_lock: asyncio.Lock = asyncio.Lock()


async def get_bus_lock(bus_number: int) -> aiologic.Lock:
    """Get or create the shared lock for the given bus number.

    The returned lock is the same instance for a given bus number across every
    caller, guaranteeing per-bus mutual exclusion. Acquisition is guarded by
    :data:`_registry_lock` so the registry dict mutation is race-free without
    blocking the asyncio event loop.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        An :class:`aiologic.Lock` for the given bus number.
    """
    async with _registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = aiologic.Lock()
        return _bus_locks[bus_number]
