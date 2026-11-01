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
_bus_locks: dict[int, _GuardedLock] = {}
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


class _GuardedLock:
    """Wrapper around aiologic.Lock that enforces acquisition via get_bus_lock().

    PLAN-19 FIX: Replaces global monkey-patch of aiologic.Lock.__enter__
    (code_review-18.1.json #7). The monkey-patch affected ALL aiologic.Lock
    instances in the process, including those used by other libraries.
    Wrapper confines guard to SPI locks only. __getattr__ fallback ensures
    complete delegation to the wrapped lock for any current or future
    aiologic.Lock methods, making the wrapper a transparent proxy.
    """

    __slots__ = ("_lock", "_obtained")

    def __init__(self, lock: Any) -> None:
        self._lock = lock
        self._obtained = False

    # Async context manager (primary acquisition path)
    async def __aenter__(self) -> Self:
        self._obtained = True
        await self._lock.__aenter__()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._lock.__aexit__(exc_type, exc_val, exc_tb)
        self._obtained = False

    # Sync context manager — ONLY valid after async acquisition via get_bus_lock()
    def __enter__(self) -> Self:
        if not self._obtained:
            raise RuntimeError("Lock not acquired via get_bus_lock()")
        self._lock.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._lock.__exit__(exc_type, exc_val, exc_tb)

    # Delegate known methods explicitly (for type checker)
    async def async_acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        return await self._lock.async_acquire(blocking=blocking, timeout=timeout)

    def async_release(self) -> None:
        self._lock.async_release()

    def green_release(self) -> None:
        self._lock.green_release()

    def locked(self) -> bool:
        return self._lock.locked()

    # PLAN-19 FIX: Fallback delegation for any other aiologic.Lock methods
    # (current or future). Ensures wrapper is a transparent proxy.
    def __getattr__(self, name: str) -> Any:
        return getattr(self._lock, name)


async def get_bus_lock(bus_number: int) -> SpiLock:
    """Get or create the shared lock for the given bus number.

    The returned lock is the same instance for a given bus number across every
    caller, guaranteeing per-bus mutual exclusion. Acquisition is guarded by
    :data:`_registry_lock` so the registry dict mutation is race-free without
    blocking the asyncio event loop.

    Args:
        bus_number: The bus identifier to lock.

    Returns:
        A :class:`SpiLock` (concretely a :class:`_GuardedLock` wrapping :class:`aiologic.Lock`) for the given bus number.
    """
    global _registry_lock, _aiologic_module

    # Lazy aiologic import — outside lock for first call, only imports module,
    # doesn't patch it. Safe because module import is thread-safe in Python (GIL).
    # The _registry_lock creation is guarded.
    # PLAN-19 FIX: import aiologic outside the guard (thread-safe), lock creation inside.
    if _aiologic_module is None:
        try:
            import aiologic
            _aiologic_module = aiologic
        except ImportError as e:
            raise ImportError(
                "aiologic is required for SPI locking. Install with: pip install aiologic"
            ) from e

    if _registry_lock is None:
        async with _registry_init_lock:  # Race-free guard
            if _registry_lock is None:  # Re-check inside lock
                _registry_lock = _aiologic_module.Lock()

    async with _registry_lock:
        if bus_number not in _bus_locks:
            # Wrap the raw aiologic.Lock in our guard (PLAN-19 FIX)
            raw_lock = _aiologic_module.Lock()
            _bus_locks[bus_number] = _GuardedLock(raw_lock)
        return _bus_locks[bus_number]


def _verify_single_registry() -> None:
    """Verify that both absolute import paths for this module resolve to one object.

    PLAN-19 FIX: code_review-18.1.json #7 root-cause remediation. The previous
    implementation monkey-patched aiologic.Lock.__enter__ globally and then
    attempted to unify ``pi_lora.drivers.spi.locks`` and ``src.pi_lora.drivers
    .spi.locks`` by overwriting ``sys.modules`` entries -- a fragile technique
    that broke under xdist, editable installs, and alternate PYTHONPATHs,
    allowing two independent ``_bus_locks`` registries (and hence broken mutual
    exclusion) to coexist. That sys.modules manipulation has been removed
    entirely -- the _GuardedLock wrapper confines the acquisition guard to SPI
    locks without touching global state, so no registry unification is needed.

    If both absolute import paths are present in ``sys.modules`` simultaneously,
    they MUST be the same module object; otherwise the per-bus ``_bus_locks``
    registry would not be shared and transfers on the same bus could run
    concurrently. This helper raises RuntimeError in that case so the root cause
    (an import-path configuration defect) surfaces at test time instead of being
    masked by silent dual registries.

    Raises:
        RuntimeError: If dual import paths create separate registries.
    """
    mod1 = sys.modules.get("pi_lora.drivers.spi.locks")
    mod2 = sys.modules.get("src.pi_lora.drivers.spi.locks")
    if mod1 is not None and mod2 is not None and mod1 is not mod2:
        raise RuntimeError(
            "Dual import paths detected for spi.locks: "
            f"pi_lora.drivers.spi.locks (id={id(mod1)}) != "
            f"src.pi_lora.drivers.spi.locks (id={id(mod2)}). "
            "This breaks mutual exclusion. Fix: ensure single import path "
            "(e.g., configure pyproject.toml packages correctly)."
        )
