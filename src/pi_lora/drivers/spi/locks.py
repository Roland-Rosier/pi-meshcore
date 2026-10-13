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

    Implementations expose a context-aware dual-mode acquisition pattern:

    * In a pure synchronous context (no running asyncio event loop) ``acquire()``
      blocks the calling thread directly and returns ``None``.
    * Inside a running event loop ``acquire()`` returns an awaitable that
      offloads the blocking acquisition to a worker thread via
      ``asyncio.to_thread``, so callers ``await`` it without blocking the loop.
    """

    def acquire(self) -> Any:
        """Acquire the lock. Blocks in sync, returns an awaitable in async."""

    def release(self) -> None:
        """Release the lock."""


class _AsyncSpiLock:
    """Wraps ``aiologic.LowLevelLock`` for async compatibility.

    The underlying ``aiologic.LowLevelLock.acquire()`` returns an awaitable.
    This is the native dual-mode lock used when ``aiologic.LowLevelLock`` is
    available; otherwise the registry falls back to ``_SyncSpiLock``.
    """

    def __init__(self, underlying: Any) -> None:
        self._underlying: Any = underlying

    def acquire(self) -> Any:
        return self._underlying.acquire()

    def release(self) -> None:
        self._underlying.release()


class _SyncSpiLock:
    """Wraps ``threading.Lock`` as a context-aware dual-mode lock.

    In a pure synchronous context (no running asyncio event loop) the blocking
    ``threading.Lock.acquire`` is executed directly and ``acquire`` returns
    ``None``. Inside a running event loop the blocking acquisition is offloaded
    to a worker thread via ``asyncio.to_thread`` so callers ``await`` it without
    blocking the event loop.
    """

    def __init__(self, underlying: Any | None = None) -> None:
        self._underlying: Any = underlying if underlying is not None else threading.Lock()

    def acquire(self) -> Any:
        """Acquire in sync by blocking, or in async via ``asyncio.to_thread``.

        Detects whether a running asyncio event loop exists. Without one (pure
        sync context) the blocking ``threading.Lock.acquire`` runs directly and
        ``None`` is returned. With one (async context) the blocking acquisition
        is offloaded to a worker thread so callers can ``await`` it.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self._underlying.acquire()
            return None
        return asyncio.to_thread(self._underlying.acquire)

    def release(self) -> None:
        self._underlying.release()


_bus_locks: dict[int, SpiLock] = {}
_registry_lock: threading.Lock = threading.Lock()


def _create_bus_lock() -> SpiLock:
    """Create the native lock for a bus, falling back to ``_SyncSpiLock``.

    Prefers ``aiologic.LowLevelLock`` (via ``_AsyncSpiLock``) when available and
    otherwise uses the context-aware ``_SyncSpiLock``.
    """
    underlying: Any = None
    try:
        import aiologic

        underlying = aiologic.LowLevelLock()  # type: ignore[attr-defined]
    except (ImportError, AttributeError):
        return _SyncSpiLock()
    return _AsyncSpiLock(underlying)


async def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number (async version).

    The returned lock is the same instance for a given bus number across every
    caller — synchronous and asynchronous alike — guaranteeing per-bus mutual
    exclusion. Acquisition is guarded by ``_registry_lock`` so the registry dict
    mutation is race-free.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A SpiLock for the given bus number.
    """
    with _registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _create_bus_lock()
        return _bus_locks[bus_number]


def get_bus_lock_sync(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number (sync version).

    Uses the same registry and lock instances as :func:`get_bus_lock`, so the
    returned lock is identical to the one an async caller receives for the same
    bus number. Intended for legacy synchronous callers.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A SpiLock for the given bus number.
    """
    with _registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _create_bus_lock()
        return _bus_locks[bus_number]
