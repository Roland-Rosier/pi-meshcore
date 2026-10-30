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
import sys
import weakref
from typing import Any, Protocol, Self


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
    sync context manager methods are declared here to satisfy type checkers,
    but callers MUST NOT use them before awaiting get_bus_lock().

    The registry hands back a single shared instance per bus number so that
    transfers on the same bus never interleave.
    """

    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

    # CR-4 FIX: The original SpiLock protocol omitted sync __enter__/__exit__, yet
    # the concrete aiologic.Lock supports them at runtime. Type checkers (mypy
    # --strict) could not therefore verify ``with lock:`` in synchronous code,
    # leaving a static-vs-runtime mismatch. Declaring __enter__/__exit__ here
    # closes that gap. The acquisition contract stays async-only on purpose: the
    # sync context managers are only valid AFTER the instance is obtained by
    # awaiting get_bus_lock(), because the registry hands back a coroutine-bound
    # instance. Declaring them as directly usable in sync without awaiting
    # get_bus_lock() first would be a lie (a caller holding a lock never obtained
    # through the event loop would have no owner), so the docstring explicitly
    # rejects that alternative and pins validity to post-acquisition.
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None: ...

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
_bus_locks: dict[int, Any] = {}
_registry_lock: Any = None
_aiologic_module: Any = None

# GUARD LOCK: module-level asyncio.Lock for ONE-TIME initialization guard ONLY.
# Rationale: aiologic must stay lazily imported (sync CLI constraint), so the
# aiologic.Lock registry guard cannot be materialised at module scope. Instead
# a stdlib asyncio.Lock serialises ONLY the first-time creation of the
# aiologic.Lock registry lock; once _registry_lock is populated this guard is
# never awaited again. asyncio.Lock is safe to instantiate at module level in
# Python 3.11+ (no running loop required), mirroring config_loader.py's NR-1.
_registry_init_lock: asyncio.Lock = asyncio.Lock()

# CR-16 (M-16) runtime guard: aiologic.Lock supports sync ``with lock:`` at
# runtime, but the SPI contract forbids using it before the instance is obtained
# by awaiting :func:`get_bus_lock`. aiologic.Lock is ``__slots__``-restricted (no
# ``__dict__``), so the returned instance cannot carry an ``_acquired`` flag.
# Acquisition is therefore tracked by object identity in ``_obtained_locks`` — a
# ``weakref.WeakSet`` of the lock instances themselves. Because the set holds the
# actual lock objects (not bare ids) and drops them on GC, ids are never reused
# across cycles and cross-test false positives/negatives disappear. The base
# class's sync ``__enter__`` is wrapped exactly once (see ``_ensure_enter_guard``)
# to raise ``RuntimeError`` on pre-acquisition sync misuse. The async acquisition
# path (``__aenter__``) is left untouched.
_obtained_locks: weakref.WeakSet[Any] = weakref.WeakSet()
_enter_guard_patched: bool = False


def _ensure_enter_guard() -> None:
    """Wrap aiologic.Lock's sync ``__enter__`` to reject pre-acquisition misuse.

    Called once, lazily, the first time :func:`get_bus_lock` imports aiologic.
    The wrapper raises ``RuntimeError`` when ``with lock:`` is used on an instance
    that was never handed back by :func:`get_bus_lock`; the async acquisition
    path is unaffected. Idempotent via ``_enter_guard_patched``.
    """
    global _enter_guard_patched
    if _enter_guard_patched:
        return
    import aiologic
    _original_enter = aiologic.Lock.__enter__

    def _guarded_enter(self: Any) -> Any:
        if self not in _obtained_locks:
            raise RuntimeError("Lock not acquired via get_bus_lock()")
        return _original_enter(self)

    aiologic.Lock.__enter__ = _guarded_enter  # type: ignore[method-assign]
    _enter_guard_patched = True


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
    global _registry_lock, _aiologic_module
    if _aiologic_module is None:
        try:
            import aiologic
            _aiologic_module = aiologic
        except ImportError as e:
            raise ImportError(
                "aiologic is required for SPI locking. Install with: pip install aiologic"
            ) from e
        _ensure_enter_guard()
    if _registry_lock is None:
        async with _registry_init_lock:  # Race-free guard
            if _registry_lock is None:  # Re-check inside lock
                _registry_lock = _aiologic_module.Lock()
    async with _registry_lock:
        if bus_number not in _bus_locks:
            _bus_locks[bus_number] = _aiologic_module.Lock()
        _obtained_locks.add(_bus_locks[bus_number])
        return _bus_locks[bus_number]


# pi_lora.drivers.spi.locks and src.pi_lora.drivers.spi.locks are the same physical
# namespace package but resolve to distinct module objects under pythonpath implicit
# namespace packaging. The lock registry and the sync __enter__ guard must be a single
# shared singleton: the guard is patched once onto aiologic.Lock.__enter__ (global),
# while get_bus_lock exists on both module objects and would otherwise populate the
# wrong registry, producing an order-dependent false positive under xdist. Unify the
# registry so both import paths share one set, one dict, one guard.
_registry_duals: tuple[str, ...] = ("pi_lora.drivers.spi.locks", "src.pi_lora.drivers.spi.locks")
_here: Any = sys.modules.get(__name__)
_candidates: list[Any] = []
for _name in _registry_duals:
    _module: Any = sys.modules.get(_name)
    if _module is not None:
        _candidates.append(_module)
if _here is not None and len(_candidates) > 1:
    _shared: Any = max(_candidates, key=lambda _obj: id(_obj))  # nosemgrep: maintainability.return-not-in-function
    for _name in _registry_duals:
        _module = sys.modules.get(_name)
        if _module is not None and _module is not _shared:
            sys.modules[_name] = _shared
    for _attr in ("_bus_locks", "_obtained_locks", "_registry_lock", "_aiologic_module", "_enter_guard_patched"):
        globals()[_attr] = getattr(_shared, _attr)
