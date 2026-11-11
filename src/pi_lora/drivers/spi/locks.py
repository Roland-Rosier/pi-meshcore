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

import sys
from typing import Any, Protocol, Self

from pi_lora.framework.lazy_async_lock import LazyAsyncLock


class SpiLock(Protocol):
    """Protocol describing the per-bus SPI critical-section lock.

    Acquisition is async-only: callers must obtain the lock instance by awaiting
    :func:`get_bus_lock`, which is an async function requiring a running event
    loop. In synchronous code that path is ``asyncio.run(get_bus_lock(...))`` or
    similar. The returned instance supports ``async with lock:`` and
    ``await lock.async_acquire()`` for the async context.

    The concrete implementation is an :class:`aiologic.Lock`, a native dual-mode
    lock that *does* support sync ``with lock:`` at runtime — but only *after*
    the instance has been obtained by awaiting :func:`get_bus_lock()`. The
    sync context manager methods are NOT declared in this protocol because they
    are only valid after async acquisition; declaring them would imply they can
    be used directly without awaiting get_bus_lock(), which is not the case.
    Callers should use ``async with lock:`` or ``await lock.async_acquire()``.

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
    # whose public release methods are ``async_release`` (async context) and
    # ``green_release`` (sync/greenlet context). It has NO ``release`` method
    # (verified at runtime: ``hasattr(aiologic.Lock(), "release") is False``;
    # ``hasattr(aiologic.Lock(), "green_release") is True``).
    # code_review-10.1:1 flagged this as a "``async_release`` vs ``release`` mismatch"
    # bug, but that was a false positive: it wrongly assumed ``aiologic.Lock`` mirrors
    # ``asyncio.Lock``'s ``release()``. Renaming to ``release`` reintroduces an
    # ``AttributeError`` at runtime; the protocol must track the real ``aiologic.Lock`` API.
    def async_release(self) -> None: ...
    def green_release(self) -> None: ...
    def locked(self) -> bool: ...


# LAZY INITIALIZATION - no aiologic import at module level
_registry: LazyAsyncLock = LazyAsyncLock()
_aiologic_module: Any = None
_bus_locks: dict[int, Any] = {}


# PLAN-22 FIX (Item 5): Lazily verifies the single-registry invariant on the
# first call to get_bus_lock(). _verify_single_registry() is defined but never
# called; without this, dual import paths could create separate _bus_locks
# registries silently. Set True after the single verification call.
#
# PLAN-23 NOTE: This lazy verification is intentional to keep imports idempotent
# (no side effects on module import). Calling at module init would violate import
# hygiene: at init time only one import path may be loaded, causing the check to
# pass silently and setting _registry_verified=True so a later second path loads
# and is never re-checked. The lazy check runs on first get_bus_lock() call, by
# which time both import paths are typically loaded. If get_bus_lock() is never
# called, the SPI bus is never used and dual imports cannot cause harm.
_registry_verified: bool = False


async def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number.

    The returned lock is the same instance for a given bus number across every
    caller, guaranteeing per-bus mutual exclusion. Acquisition is guarded by the
    lazily-initialized :class:`LazyAsyncLock` registry so the registry dict
    mutation is race-free without blocking the asyncio event loop.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A :class:`SpiLock` (concretely an :class:`aiologic.Lock`) for the given bus number.
    """
    global _registry, _aiologic_module, _registry_verified

    if not _registry_verified:
        _verify_single_registry()
        _registry_verified = True

    if _aiologic_module is None:
        try:
            import aiologic
            _aiologic_module = aiologic
        except ImportError as e:
            raise ImportError("aiologic is required for SPI locking. Install with: pip install aiologic") from e

    registry_lock = await _registry.acquire()
    async with registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _aiologic_module.Lock()
        return _bus_locks[bus_number]


def _verify_single_registry() -> None:
    """Verify single registry across ALL import paths by scanning sys.modules."""
    registries: list[tuple[str, int]] = []
    for module in sys.modules.values():
        if hasattr(module, "_bus_locks"):
            registries.append((module.__name__, id(module._bus_locks)))

    if len(registries) > 1:
        registry_ids = {rid for _, rid in registries}
        if len(registry_ids) > 1:
            raise RuntimeError(
                f"Multiple _bus_locks registries detected: {registries}. "
                "This breaks mutual exclusion. Fix: ensure single import path."
            )
