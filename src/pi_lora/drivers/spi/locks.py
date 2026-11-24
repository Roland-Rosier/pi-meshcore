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
import threading
from typing import Any, Protocol, Self, cast

from pi_lora.framework.lazy_async_lock import LazyAsyncLock


class SpiLock(Protocol):
    """Protocol describing the per-bus SPI critical-section lock.

    Acquisition is async-only: callers must obtain the lock instance by awaiting
    :func:`get_bus_lock`, which is an async function requiring a running event
    loop.

    .. warning:: Do NOT use ``asyncio.run(get_bus_lock(...))`` — this creates a
       NEW event loop each call, breaking subsequent lock acquisition. The lock
       registry is bound to the first event loop used. Sync callers MUST refactor
       to run within an existing event loop or use a dedicated sync wrapper.
    The returned instance supports ``async with lock:`` and
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
    # Reference: durable summary docs/plan_summaries/2026_10_08_hardening_spike.md
    # category "SPI Lock Abstraction (Plans 4-28+)" (summary lines 128-133): the
    # async_release protocol. The ``async_release`` name is correct — the concrete
    # :class:`aiologic.Lock` exposes ``async_release`` and ``green_release``, not
    # ``release``; renaming to ``release`` reintroduces an AttributeError at runtime.
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
_registry_verified_lock: threading.Lock = threading.Lock()


async def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number.

    The returned lock is the same instance for a given bus number across every
    caller, guaranteeing per-bus mutual exclusion. Acquisition is guarded by the
     lazily-initialized :class:`LazyAsyncLock` registry so the registry dict
     mutation is race-free without blocking the asyncio event loop.

     .. warning:: This function MUST be awaited from within a running event loop.
        Using ``asyncio.run(get_bus_lock(...))`` is NOT supported — it creates
        a new event loop each call, breaking the shared lock registry.

     Args:
        bus_number: The bus identifier to lock.

    Returns:
        A :class:`SpiLock` (concretely an :class:`aiologic.Lock`) for the given bus number.
    """
    global _registry, _aiologic_module, _registry_verified

    # CR-34.3-2 / Plan-35 FIX: atomic check-and-set for the lazy verification flag.
    # Historical: Plan-22 introduced _verify_single_registry() as a lazy first-call
    # guard; Plan-23 justified the lazy check for import hygiene. The original
    # `if not _registry_verified:` block had a race (CR-34.3-2): multiple concurrent
    # get_bus_lock() callers could all read the flag as False before any set it True,
    # so _verify_single_registry() ran several times. Protecting the check-and-set
    # with a threading.Lock closes that window (only one first-call verifies).
    # Uses threading.Lock, NOT asyncio.Lock, because this section is synchronous
    # (no await between check and set) — an asyncio.Lock would be overkill and
    # unnecessary to acquire/release here. The lock is released before the
    # await _registry.acquire() below, so it never blocks the async path.
    # CR-38.1 (NEW): Run _verify_single_registry() on every call to eliminate
    # the race window where a second import path could create a duplicate _bus_locks
    # registry undetected. This is a cheap check (iterates sys.modules) and ensures
    # the single-registry invariant is always enforced.
    with _registry_verified_lock:
        _verify_single_registry()

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
        # PLAN-XX FIX (Item 6): Explicit return type instead of blanket no-any-return suppression.
        # get_bus_lock returned Any because _bus_locks is dict[int, Any] and aiologic.Lock lacks stubs,
        # so _bus_locks[bus_number] is Any. Explicit cast(SpiLock, ...) fixes it.
        # Cross-reference: KNOWN_DEFECTs.md Section 6.
        return cast(SpiLock, _bus_locks[bus_number])


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
