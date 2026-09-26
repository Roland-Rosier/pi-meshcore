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

import threading
from typing import Any, Protocol


class SpiLock(Protocol):
    """Protocol defining a SPI critical-section lock.

    Implementations must support both synchronous (blocking) and
    asynchronous (awaitable) acquisition/release patterns so that
    ``SpiBus.xfer2`` can operate correctly in either context.
    """

    def acquire(self) -> Any:
        """Acquire the lock. Blocking in sync, awaitable in async."""

    def release(self) -> None:
        """Release the lock."""


class _AsyncSpiLock:
    """Wraps ``aiologic.LowLevelLock`` for async/sync dual compatibility."""

    def __init__(self, underlying: Any) -> None:
        self._underlying: Any = underlying

    def acquire(self) -> Any:
        return self._underlying.acquire()

    def release(self) -> None:
        self._underlying.release()


class _SyncSpiLock:
    """Wraps ``threading.Lock`` for async/sync dual compatibility."""

    def __init__(self, underlying: threading.Lock | None = None) -> None:
        self._underlying: threading.Lock = underlying if underlying is not None else threading.Lock()

    def acquire(self) -> None:
        self._underlying.acquire()

    def release(self) -> None:
        self._underlying.release()


_bus_locks: dict[int, SpiLock] = {}
_bus_lock_types: dict[int, type[_AsyncSpiLock] | type[_SyncSpiLock]] = {}


def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create a lock for the given bus number.

    The returned lock is compatible with both synchronous and asynchronous
    contexts. In async code ``await lock.acquire()`` should be used; in
    sync code ``lock.acquire()`` works directly.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A SpiLock for the given bus number.
    """
    if bus_number not in _bus_locks:
        if bus_number not in _bus_lock_types:
            _bus_lock_types[bus_number] = _AsyncSpiLock
        # Import aiologic here to avoid circular import at module level.
        try:
            import aiologic

            underlying = aiologic.LowLevelLock()  # type: ignore[attr-defined]
            _bus_locks[bus_number] = _AsyncSpiLock(underlying)
        except (ImportError, AttributeError):
            # aiologic not available or LowLevelLock missing — fall back to threading.
            _bus_lock_types[bus_number] = _SyncSpiLock
            _bus_locks[bus_number] = _SyncSpiLock()
    return _bus_locks[bus_number]
