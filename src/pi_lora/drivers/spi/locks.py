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

from typing import Any, Protocol, Self


class _AiologicImportError(ImportError):
    """Raised when aiologic is unavailable (hard runtime dependency for SPI locking)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


try:
    import aiologic
except ImportError as _aiologic_import_error:
    raise _AiologicImportError(
        "aiologic is required for SPI locking. Install with: pip install aiologic"
    ) from _aiologic_import_error


class SpiLock(Protocol):
    """    Protocol describing the per-bus SPI critical-section lock.

    Acquisition is async-only: callers must obtain the lock instance by awaiting
    :func:`get_bus_lock`, which is an async function requiring a running event
    loop. In synchronous code that path is ``asyncio.run(get_bus_lock(...))`` or
    similar. The returned instance supports ``async with lock:`` and
    ``await lock.async_acquire()`` for the async context.

    The concrete implementation is an :class:`aiologic.Lock`, a native dual-mode
    lock that *does* support sync ``with lock:`` at runtime — but only *after*
    the instance has been obtained by awaiting :func:`get_bus_lock()`. The
    protocol deliberately does **not** declare sync ``__enter__``/``__exit__``
    because declaring them would imply the lock is directly usable in a sync
    context without first awaiting :func:`get_bus_lock()`, which is false. The
    acquisition contract is async-only; the runtime dual-mode capability is an
    implementation detail of :class:`aiologic.Lock`, not part of this protocol.

    The registry hands back a single shared instance per bus number so that
    transfers on the same bus never interleave.
    """

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    async def async_acquire(
        self, *, blocking: bool = True, timeout: float | None = None
    ) -> bool: ...
    # Keep this member named ``async_release`` (NOT ``release``). The concrete
    # implementation returned by :func:`get_bus_lock` is :class:`aiologic.Lock`,
    # whose public release method is ``async_release`` and which has NO ``release``
    # method (verified at runtime: ``hasattr(aiologic.Lock(), "release") is False``).
    # code_review-10.1:1 flagged this as a "``async_release`` vs ``release`` mismatch"
    # bug, but that was a false positive: it wrongly assumed ``aiologic.Lock`` mirrors
    # ``asyncio.Lock``'s ``release()``. Renaming to ``release`` reintroduces an
    # ``AttributeError`` at runtime; the protocol must track the real ``aiologic.Lock`` API.
    def async_release(self) -> None: ...
    def locked(self) -> bool: ...


_bus_locks: dict[int, aiologic.Lock] = {}
_registry_lock: aiologic.Lock = aiologic.Lock()


async def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number.

    The returned lock is the same instance for a given bus number across every
    caller, guaranteeing per-bus mutual exclusion. Acquisition is guarded by
    :data:`_registry_lock` so the registry dict mutation is race-free without
    blocking the asyncio event loop.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A :class:`SpiLock` (concretely an :class:`aiologic.Lock`) for the given bus number.
    """
    async with _registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = aiologic.Lock()
        return _bus_locks[bus_number]
