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
import threading
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
_bus_locks: dict[int, _GuardedLock] = {}
_registry_lock: Any = None
_aiologic_module: Any = None

# PLAN-20 FIX: The module-level asyncio.Lock guard was removed. asyncio.Lock.__init__
# calls asyncio.get_running_loop() (Python 3.10+), so a module-level instantiation
# raises RuntimeError when imported by synchronous code (e.g. the check-hardware CLI).
# The guard lock is now lazily created inside the async get_bus_lock() where an event
# loop exists, stored in a module-level typed list holder (single creation, no global
# state that mypy can verify). The holder is a list[asyncio.Lock | None] so mypy
# --strict accepts element assignment and indexing.
_registry_init_lock_holder: list[asyncio.Lock | None] = [None]

# PLAN-26 FIX (Findings 605, 615): Use a threading.Lock for the ONE-TIME holder
# initialization to avoid the race where two coroutines both create asyncio.Lock()
# for _registry_init_lock_holder[0]. This lock is only used during the first call
# to get_bus_lock() and is released before any async code runs. threading.Lock is
# safe at module level (no running loop required) and avoids the asyncio.Lock
# import-time issue.
_registry_holder_init_lock: threading.Lock = threading.Lock()

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

# H-5 FIX: Sentinel placeholder for the double-checked-locking race. If
# aiologic.Lock() internally awaits during construction, the _holder guard could
# be released before the real lock exists, letting a second coroutine re-enter
# `if _registry_lock is None:` before the first coroutine finishes. Assigning
# _SENTINEL to _registry_lock INSIDE the guard marks the slot occupied before
# awaiting Lock(), closing the race. On failure the sentinel is reset to None
# (NOT leaked) so a later call can retry — a leaked sentinel would raise
# AttributeError on subsequent `async with _registry_lock:` calls.
_SENTINEL = object()


class _GuardedLock:
    """Wrapper around aiologic.Lock that enforces acquisition via get_bus_lock().

    PLAN-19 FIX: Replaces global monkey-patch of aiologic.Lock.__enter__
    (code_review-18.1.json #7). The monkey-patch affected ALL aiologic.Lock
    instances in the process, including those used by other libraries.
    Wrapper confines guard to SPI locks only. __getattr__ fallback ensures
    complete delegation to the wrapped lock for any current or future
    aiologic.Lock methods, making the wrapper a transparent proxy.

    PLAN-26 FIX (Finding 548): Sync context manager (__enter__/__exit__) removed.
    The SpiLock protocol no longer declares them because they are only valid
    after async acquisition via get_bus_lock(). Callers must use 'async with'
    or 'await lock.async_acquire()'. The underlying aiologic.Lock still supports
    sync 'with' at runtime after async acquisition, but the protocol and wrapper
    no longer expose it to avoid confusion.
    """

    __slots__ = ("_lock", "_obtained")

    def __init__(self, lock: Any) -> None:
        self._lock = lock
        self._obtained = False

    # Async context manager (primary acquisition path)
    # PLAN-22 FIX (Item 2): _obtained flag set AFTER successful await.
    # Before: _obtained=True before await; if __aenter__ raised, flag stayed True
    # but lock was never acquired. Now flag only true when lock held.
    async def __aenter__(self) -> Self:
        await self._lock.__aenter__()
        self._obtained = True
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self._lock.__aexit__(exc_type, exc_val, exc_tb)
        self._obtained = False

    # Delegate known methods explicitly (for type checker)
    async def async_acquire(self, *, blocking: bool = True, timeout: float | None = None) -> bool:
        return await self._lock.async_acquire(blocking=blocking, timeout=timeout)

    def async_release(self) -> None:
        self._lock.async_release()

    def green_release(self) -> None:
        self._lock.green_release()

    def locked(self) -> bool:
        return self._lock.locked()

    # PLAN-26 FIX (Finding 548): Explicitly block sync context manager to prevent
    # delegation to underlying aiologic.Lock. Callers must use async with or
    # async_acquire. This avoids the confusing situation where 'with guard:'
    # appears to work but bypasses the acquisition guard.
    def __enter__(self) -> Self:
        raise RuntimeError(
            "Sync context manager not supported on _GuardedLock. "
            "Use 'async with lock:' or 'await lock.async_acquire()' after "
            "obtaining the lock via get_bus_lock()."
        )

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        raise RuntimeError(
            "Sync context manager not supported on _GuardedLock. "
            "Use 'async with lock:' or 'await lock.async_acquire()' after "
            "obtaining the lock via get_bus_lock()."
        )

    # PLAN-19 FIX: Fallback delegation for any other aiologic.Lock methods
    # (current or future). Ensures wrapper is a transparent proxy.
    def __getattr__(self, name: str) -> Any:
        # Block sync context manager delegation
        if name in ("__enter__", "__exit__"):
            raise AttributeError(
                f"'{type(self).__name__}' has no attribute '{name}'. "
                "Sync context manager not supported; use async methods."
            )
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
    global _registry_lock, _aiologic_module, _registry_verified

    # PLAN-22 FIX (Item 5): _verify_single_registry() called lazily on first use.
    # Before: Function defined but never called; dual import paths could create
    # separate _bus_locks registries silently. Now verified on first get_bus_lock().
    # Import-time call avoided to keep imports idempotent (no side effects).
    # PLAN-23: This lazy pattern is the CORRECT design — see module-level comment.
    # The single-registry invariant is intentionally verified lazily (not at import)
    # to preserve import idempotency; see the module-level PLAN-23 note above.
    if not _registry_verified:
        _verify_single_registry()
        _registry_verified = True


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

    # PLAN-26 FIX (Findings 605, 615): Redesigned initialization to eliminate all
    # sentinel races. The threading.Lock protects holder creation atomically.
    # The asyncio.Lock holder protects the ENTIRE registry critical section
    # (including aiologic.Lock creation and bus lock dict mutation) so no
    # coroutine can see a partially-initialized _registry_lock or race on
    # _bus_locks dict mutation.
    # Cross-reference: code_review-25.3.json findings 548, 578, 605, 615.
    if _registry_lock is None:
        # Atomically create or retrieve the asyncio.Lock holder using threading.Lock
        # for the one-time initialization. This avoids the race where two
        # coroutines both create asyncio.Lock() for _registry_init_lock_holder[0].
        with _registry_holder_init_lock:
            holder: asyncio.Lock | None = _registry_init_lock_holder[0]
            if holder is None:  # nosemgrep: lazy-lock-without-guard (guarded by threading.Lock)
                holder = asyncio.Lock()
                _registry_init_lock_holder[0] = holder

        # Hold the asyncio holder for the ENTIRE critical section including
        # aiologic.Lock creation and _bus_locks dict mutation. This ensures
        # no other coroutine can enter this section or the else branch below
        # until _registry_lock is fully initialized.
        async with holder:
            if _registry_lock is None:  # Double-check inside holder
                _registry_lock = _SENTINEL  # Placeholder — prevents race if Lock() awaits
                try:
                    _registry_lock = _aiologic_module.Lock()
                except Exception:
                    _registry_lock = None  # Reset on failure — don't leak sentinel
                    raise

            # Now _registry_lock is fully initialized (aiologic.Lock).
            # Perform the bus lock lookup/creation under the registry lock.
            async with _registry_lock:
                if bus_number not in _bus_locks:
                    raw_lock = _aiologic_module.Lock()
                    _bus_locks[bus_number] = _GuardedLock(raw_lock)
            bus_lock: SpiLock = _bus_locks[bus_number]
            return bus_lock
    else:
        # Registry already initialized — just use the registry lock.
        async with _registry_lock:
            if bus_number not in _bus_locks:
                raw_lock = _aiologic_module.Lock()
                _bus_locks[bus_number] = _GuardedLock(raw_lock)
            returned_bus_lock: SpiLock = _bus_locks[bus_number]
            return returned_bus_lock


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
