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
import threading
from typing import Any, Protocol


class SpiLock(Protocol):
    """Protocol defining a SPI critical-section lock.

    Implementations provide an async-compatible acquisition pattern.
    The `acquire()` method returns an awaitable; callers must ``await`` it.
    Blocking acquisition is offloaded to a thread pool for sync-compatible
    lock implementations so it does not block the event loop.
    """

    def acquire(self) -> Any:
        """Acquire the lock. Blocking in sync, awaitable in async."""

    def release(self) -> None:
        """Release the lock."""


class _AsyncSpiLock:
    """Wraps ``aiologic.LowLevelLock`` for async compatibility.

    The underlying ``aiologic.LowLevelLock.acquire()`` returns an awaitable.
    """

    def __init__(self, underlying: Any) -> None:
        self._underlying: Any = underlying

    def acquire(self) -> Any:
        return self._underlying.acquire()

    def release(self) -> None:
        self._underlying.release()


class _SyncSpiLock:
    """Wraps ``threading.Lock`` for async compatibility.

    Blocking acquisition is offloaded to a worker thread via ``asyncio.to_thread``
    so it does not block the event loop. Callers must ``await lock.acquire()``.
    Requires a running asyncio event loop.
    """

    def __init__(self, underlying: Any | None = None) -> None:
        self._underlying: Any = underlying if underlying is not None else threading.Lock()

    def acquire(self) -> Any:
        """Return an awaitable that runs the blocking ``acquire`` in a thread pool.

        The blocking ``threading.Lock.acquire`` cannot be awaited directly, so it
        is offloaded to a worker thread via ``asyncio.to_thread``; the returned
        awaitable resolves once the lock is acquired. Callers should always
        ``await lock.acquire()``.
        """
        return asyncio.to_thread(self._underlying.acquire)

    def release(self) -> None:
        self._underlying.release()


class _SpiAsyncContextLock:
    """Wraps ``threading.Lock`` as an async context manager for per-instance use.

    ``__aenter__`` offloads the blocking ``acquire`` to a worker thread via
    ``asyncio.to_thread``; ``__aexit__`` offloads ``release`` the same way, so
    neither blocks the event loop. Usable as ``with self._lock:`` inside an
    ``async def`` so the entire critical section is atomic per bus instance.
    """

    def __init__(self, underlying: Any | None = None) -> None:
        self._underlying: Any = underlying if underlying is not None else threading.Lock()

    async def __aenter__(self) -> _SpiAsyncContextLock:
        await asyncio.to_thread(self._underlying.acquire)
        return self

    async def __aexit__(self, exc: Any = None) -> None:
        await asyncio.to_thread(self._underlying.release)


_bus_locks: dict[int, SpiLock] = {}
_bus_lock_types: dict[int, type[_AsyncSpiLock] | type[_SyncSpiLock]] = {}


def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create a lock for the given bus number.

    The returned lock is compatible with both synchronous and asynchronous
    contexts. Callers should always ``await lock.acquire()``; the returned
    awaitable resolves once the lock is acquired (blocking acquisition is
    offloaded to a worker thread in the sync fallback).

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
