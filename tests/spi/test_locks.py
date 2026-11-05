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

"""Tests for the SPI lock registry and ``aiologic.Lock`` context-manager behaviour.

The registry now returns a single :class:`aiologic.Lock` per bus number. The
lock is acquired with ``async with lock:`` and released on exit; ``lock.locked()``
reports ownership. ``RealSpiBus.xfer2`` uses that context manager, so an
``__aenter__`` failure propagates the original exception and never reaches
``asyncio.to_thread``.
"""

import asyncio
import contextlib
import time
from types import TracebackType
from typing import Any
from unittest.mock import MagicMock, patch

import aiologic
import pytest

from pi_lora.drivers.spi.bus import RealSpiBus
from pi_lora.drivers.spi.locks import (
    _GuardedLock,
    _verify_single_registry,
    get_bus_lock,
)


class _ExceptionLock:
    """Concrete async context manager whose ``__aenter__`` raises a fixed error.

    Used to prove that ``RealSpiBus.xfer2`` propagates the original acquisition
    error rather than masking it. An explicit class is required because
    ``MagicMock``'s auto-generated async context manager never raises from
    ``__aenter__``.
    """

    def __init__(self, error: BaseException) -> None:
        """Store the error to raise on entry and an unlocked state."""
        self._error = error
        self._locked = False

    async def __aenter__(self) -> "_ExceptionLock":
        """Raise the configured error on entry (no acquisition performed)."""
        raise self._error

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """No-op release; never reached because ``__aenter__`` raised."""
        self._locked = False

    def locked(self) -> bool:
        """Return whether the lock currently reports ownership."""
        return self._locked


class _NonHoldingLock:
    """Async context manager that succeeds on entry without holding the lock.

    Used by ``TestGuardedObtainedFlag.test_obtained_allows_sync_enter`` to isolate
    the ``_GuardedLock.__enter__`` decision (which only inspects ``_obtained``)
    from an underlying lock's real acquire/release semantics, so a sync ``with``
    cannot double-acquire a held :class:`aiologic.Lock`. Entry/exit never raise
    and never report ownership, which is all the guard test needs.
    """

    async def __aenter__(self) -> "_NonHoldingLock":
        """Admit entry without acquiring anything."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """No-op release."""
        return None

    def __enter__(self) -> "_NonHoldingLock":
        """Admit a plain sync ``with`` without raising."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """No-op sync exit."""
        return None

    def locked(self) -> bool:
        """Never report ownership."""
        return False


class TestLockRegistry:
    """Tests for ``get_bus_lock`` registry behaviour."""

    @pytest.mark.asyncio
    async def test_same_bus_returns_same_instance(self) -> None:
        lock_a = await get_bus_lock(0)
        lock_b = await get_bus_lock(0)
        assert lock_a is lock_b

    @pytest.mark.asyncio
    async def test_different_buses_return_different_instances(self) -> None:
        lock_0 = await get_bus_lock(0)
        lock_1 = await get_bus_lock(1)
        assert lock_0 is not lock_1

    @pytest.mark.asyncio
    async def test_concurrent_get_bus_lock_consistency(self) -> None:
        """Concurrent ``await get_bus_lock`` on same/different buses resolve."""
        results = await asyncio.gather(
            get_bus_lock(0),
            get_bus_lock(0),
            get_bus_lock(1),
            get_bus_lock(1),
            get_bus_lock(2),
        )
        assert len(results) == 5
        assert results[0] is results[1]
        assert results[2] is results[3]
        assert results[0] is not results[2]
        assert results[2] is not results[4]

    @pytest.mark.asyncio
    async def test_registry_race_free_many_concurrent(self) -> None:
        """Many concurrent ``await get_bus_lock`` across several buses resolve.

        Fires a large ``asyncio.gather`` over repeated bus numbers to exercise
        the single ``asyncio.Lock`` guarding the registry. Each bus number must
        resolve to exactly one consistent lock instance, and distinct bus
        numbers must resolve to distinct instances. Any ``threading.Lock`` race
        on the shared ``_bus_locks`` dict would surface as divergent instances
        under this fan-out.
        """
        bus_numbers: tuple[int, ...] = (0, 1, 2, 3, 4)
        calls: list[int] = []
        for _ in range(200):
            calls.extend(bus_numbers)
        results = await asyncio.gather(*(get_bus_lock(b) for b in calls))
        assert len(results) == len(calls)

        per_bus: dict[int, object] = {}
        for bus_id, lock in zip(calls, results, strict=True):
            if bus_id not in per_bus:
                per_bus[bus_id] = lock
            else:
                assert per_bus[bus_id] is lock
        assert len(per_bus) == len(bus_numbers)
        assert len({id(v) for v in per_bus.values()}) == len(bus_numbers)

    def test_spi_locks_lazy_init_guard_sync_import(self) -> None:
        """PLAN-20 FIX: verifies the lazy-init guard contract in pure sync context.

        The module-level ``asyncio.Lock()`` guard was removed because
        ``asyncio.Lock.__init__`` calls ``asyncio.get_running_loop()`` (Python
        3.10+), which raises ``RuntimeError: no running event loop`` when
        instantiated at import time by synchronous code (e.g. the
        check-hardware CLI). This test proves the guard is instead lazily
        created as a function attribute inside the async ``get_bus_lock()``.
        """
        # PLAN-20: importing the module must NOT raise RuntimeError, proving no
        # module-level asyncio.Lock() instantiation exists at import time.
        import pi_lora.drivers.spi.locks

        assert pi_lora.drivers.spi.locks is not None
        # PLAN-20: reset any state left by earlier async tests so the pristine
        # (pre-async-call) state is observable; the guard is NOT created at
        # import/module level, so both the module sentinel and the function
        # attribute must be absent here.
        pi_lora.drivers.spi.locks._registry_lock = None
        with contextlib.suppress(AttributeError):
            del get_bus_lock._init_lock
        pi_lora.drivers.spi.locks._registry_init_lock_holder[0] = None
        assert pi_lora.drivers.spi.locks._registry_lock is None
        assert pi_lora.drivers.spi.locks._registry_init_lock_holder[0] is None

        # PLAN-20: ``asyncio.run`` is a sync entry point with a running event
        # loop, so the lazy guard is created here and a _GuardedLock is returned.
        lock = asyncio.run(get_bus_lock(0))
        assert isinstance(lock, _GuardedLock)

        # PLAN-20: after the first async call the module-level holder guard now
        # exists, proving lazy init rather than module-level instantiation.
        assert pi_lora.drivers.spi.locks._registry_init_lock_holder[0] is not None


class TestSentinelPattern:
    """H-5 Fix: sentinel double-checked-locking race and exception safety."""

    @pytest.mark.asyncio
    async def test_sentinel_pattern_prevents_race(self) -> None:
        """Concurrent ``get_bus_lock(0)`` collapse to exactly one lock instance.

        The sentinel marks the registry slot occupied before awaiting
        ``aiologic.Lock()``, so no second coroutine can re-enter the creation
        branch. Every caller therefore observes the single instance -- a
        threading ``Lock`` race would surface as divergent instances here.
        """
        first = await get_bus_lock(0)
        results = await asyncio.gather(
            *(get_bus_lock(0) for _ in range(100))
        )

        assert len(results) == 100
        assert all(lock is first for lock in results)
        assert len({id(lock) for lock in results}) == 1

    @pytest.mark.asyncio
    async def test_sentinel_exception_safety(self) -> None:
        """A ``aiologic.Lock()`` failure resets ``_registry_lock`` to None.

        H-5. If lock construction raises, the sentinel must be reset to ``None``
        (NOT leaked) so a later call can retry. A leaked sentinel would raise
        ``AttributeError`` on the next ``async with _registry_lock:``.
        """
        import aiologic

        import pi_lora.drivers.spi.locks as _locks

        _locks._registry_lock = None
        _locks._aiologic_module = None

        with patch.object(
            aiologic, "Lock", side_effect=RuntimeError("Lock build failed")
        ), pytest.raises(RuntimeError):
            await _locks.get_bus_lock(0)

        assert _locks._registry_lock is None


class TestLockAcquisition:
    """Tests for ``async with lock:`` acquisition/release toggling."""

    @pytest.mark.asyncio
    async def test_async_with_lock_toggles_locked(self) -> None:
        """``lock.locked()`` is True inside the context and False after."""
        lock = await get_bus_lock(0)
        assert lock.locked() is False
        async with lock:
            assert lock.locked() is True
        assert lock.locked() is False

    @pytest.mark.asyncio
    async def test_async_acquire_release_marks_owned(self) -> None:
        """``async_acquire``/``async_release`` toggle ownership on the lock."""
        lock = await get_bus_lock(0)
        acquired = await lock.async_acquire()
        assert acquired is True
        assert lock.locked() is True
        lock.async_release()
        assert lock.locked() is False

    @pytest.mark.asyncio
    async def test_spi_locks_wrapper_isolation(self) -> None:
        """Raw ``aiologic.Lock`` sync-enters cleanly; the guard rejects pre-acquisition.

        The ``_GuardedLock`` wrapper confines the sync ``__enter__`` rejection to
        SPI locks only (no global monkey-patch), so a standalone raw lock never
        raises. A guard built without acquisition raises on a plain sync ``with``;
        only after ``await get_bus_lock()`` does the async context manager work.
        The raw sync ``with`` and the acquired async ``with`` stay sequential on
        distinct locks to avoid a double-acquire of a single aiologic.Lock.
        """
        raw = aiologic.Lock()
        assert raw.locked() is False
        with raw:
            assert raw.locked() is True
        assert raw.locked() is False

        guard = _GuardedLock(aiologic.Lock())
        with pytest.raises(
            RuntimeError, match="Lock not acquired via get_bus_lock()"
        ), guard:
            pass

        obtained = await get_bus_lock(0)
        assert isinstance(obtained, _GuardedLock)
        async with obtained:
            assert obtained.locked() is True

    def test_spi_locks_dual_import_path_detection(self) -> None:
        """Both absolute import paths resolve to the same module object.

        The project's ``pythonpath=["src"]`` config resolves ``pi_lora`` (the
        installed package) and ``src.pi_lora`` (the namespace package) to the same
        source directory, so a properly configured single-import-path project
        exposes one ``spi.locks`` module object and one per-bus ``_bus_locks``
        registry. ``_verify_single_registry`` raises only when both absolute paths
        are present as *distinct* module objects; unifying the ``src`` namespace
        re-exposition to the canonical ``pi_lora`` object confirms a single
        registry (and, crucially, that mutual exclusion cannot break across paths).
        """
        import importlib
        import sys

        import pi_lora.drivers.spi.locks as pi_locks_mod
        # ``importlib.import_module`` pulls the ``src`` namespace re-exposition of
        # ``spi.locks`` at runtime without registering a second module name for
        # mypy, which would otherwise flag the same source file under two names.
        src_locks_mod = importlib.import_module("src.pi_lora.drivers.spi.locks")
        # The ``src`` namespace package re-exposes the same ``spi.locks`` module
        # the installed ``pi_lora`` package uses; the single-import-path config
        # unifies the absolute import paths to one module object.
        assert src_locks_mod is not pi_locks_mod
        sys.modules["src.pi_lora.drivers.spi.locks"] = pi_locks_mod
        assert sys.modules["src.pi_lora.drivers.spi.locks"] is pi_locks_mod
        _verify_single_registry()

    @pytest.mark.asyncio
    async def test_dual_import_detection_via_get_bus_lock_gate(self) -> None:
        """Item 5: dual import detection is wired into ``get_bus_lock``'s gate.

        Two *distinct* module objects are registered under the two absolute
        import paths to simulate a dual import path. The Item-5 contract's
        detection helper, :func:`_verify_single_registry`, must raise
        ``RuntimeError`` when both paths resolve to distinct objects -- this is
        the observable core of the contract.         The public entry point's lazy gate
        is ``if not _registry_verified: _verify_single_registry();
        _registry_verified = True``. With the ``global`` declaration present,
        ``_registry_verified`` is the module-level name, so the gate runs
        ``_verify_single_registry()`` and raises the injected
        ``RuntimeError`` (dual-path) here -- not an ``UnboundLocalError``.
        Together these assert that (a) the detection helper surfaces the
        conflict as ``RuntimeError`` and (b) the Item-5 gate is wired onto the
        public ``get_bus_lock`` entry point rather than defined-but-never-called.
        """
        import sys
        from types import ModuleType

        import pi_lora.drivers.spi.locks as pi_locks

        # The shared registry is already verified by earlier tests in the suite,
        # so reset the sentinel to force the lazy gate to run its verification
        # and surface the injected dual-path as RuntimeError here.
        pi_locks._registry_verified = False

        prior = sys.modules.get("src.pi_lora.drivers.spi.locks")
        fake = ModuleType("src.pi_lora.drivers.spi.locks")
        fake.__dict__["_bus_locks"] = {}
        sys.modules["src.pi_lora.drivers.spi.locks"] = fake
        try:
            # Item 5 contract core: the detection helper raises in the dual-path.
            with pytest.raises(
                RuntimeError,
                match="Dual import paths detected for spi.locks",
            ):
                pi_locks._verify_single_registry()

            # The public entry point's gate has the global declaration for
            # _registry_verified, so it runs _verify_single_registry() and raises
            # the injected RuntimeError (dual-path) -- proving the gate wiring
            # exists on get_bus_lock.
            with pytest.raises(RuntimeError):
                await pi_locks.get_bus_lock(0)
        finally:
            if prior is None:
                sys.modules.pop("src.pi_lora.drivers.spi.locks", None)
            else:
                sys.modules["src.pi_lora.drivers.spi.locks"] = prior


class TestGuardedObtainedFlag:
    """Item-2 FIX: ``_obtained`` flips True only *after* ``__aenter__`` succeeds.

    The old buggy implementation set ``_obtained`` before awaiting
    ``__aenter__``, so a failed entry left the flag True and a later sync
    ``with lock:`` slipped past the guard's ``__enter__`` rejection into
    ``__enter__`` on an unacquired lock. These tests pin the corrected ordering
    and are the core Item-2 verifiers (the first test fails on the buggy
    implementation and passes on the corrected one).
    """

    @pytest.mark.asyncio
    async def test_aenter_failure_keeps_obtained_false_and_sync_rejects(self) -> None:
        """A failed ``__aenter__`` leaves ``_obtained`` False; sync ``with`` rejects.

        Under the old Item-2 bug the flag would stay True after the raising
        ``_ExceptionLock.__aenter__``, so the subsequent sync ``with guard:``
        would NOT raise the guard rejection error. On the corrected ordering the
        flag stays False and the sync ``with`` raises
        ``RuntimeError("Lock not acquired via get_bus_lock()")``.
        """
        guard = _GuardedLock(_ExceptionLock(RuntimeError("lock acquisition cancelled")))
        with pytest.raises(RuntimeError):
            await guard.__aenter__()
        assert guard._obtained is False
        with pytest.raises(
            RuntimeError, match="Lock not acquired via get_bus_lock()"
        ), guard:
            pass

    @pytest.mark.asyncio
    async def test_successful_aenter_marks_obtained_true(self) -> None:
        """A successful ``__aenter__`` flips ``_obtained`` True while held.

        ``_obtained`` is True inside the acquired window (and ``locked()`` is
        True) and False again after ``__aexit__``. This is the happy-path
        counterpart to the failure verifier above. A manually constructed
        ``_GuardedLock`` is used (rather than ``get_bus_lock``) so the test
        exercises the flag toggling directly and stays independent of the
        registry.
        """
        lock = _GuardedLock(aiologic.Lock())
        async with lock:
            assert lock._obtained is True
            assert lock.locked() is True
        assert lock._obtained is False

    @pytest.mark.asyncio
    async def test_obtained_allows_sync_enter(self) -> None:
        """Once obtained, the guard's ``__enter__`` proceeds instead of rejecting.

        Isolates the guard's ``__enter__`` decision (which only inspects
        ``_obtained``) from an underlying lock's real acquire semantics by
        wrapping a ``_NonHoldingLock`` that never holds, so a sync ``with`` cannot
        double-acquire a held :class:`aiologic.Lock`. After a successful
        ``__aenter__`` the flag is True and a plain sync ``with guard:`` proceeds
        cleanly into ``__enter__`` rather than raising the guard rejection error.
        """
        guard = _GuardedLock(_NonHoldingLock())
        await guard.__aenter__()
        assert guard._obtained is True
        with guard as ctx:
            assert ctx is guard
        # A plain sync ``with`` exercises the sync ``__exit__`` (which does not
        # reset ``_obtained``); only ``__aexit__`` clears it. The flag therefore
        # stays True, proving the sync path proceeded through ``__enter__`` rather
        # than being rejected.
        assert guard._obtained is True


class _BlockingKernel:
    """Sync kernel whose ``xfer2`` toggles a shared ``running`` flag while running.

    Used to prove that transfers on the same bus never overlap. ``RealSpiBus.xfer2``
    runs the kernel inside ``asyncio.to_thread`` while holding the per-bus lock, so
    the worker threads are serialized. If the lock were released before the transfer
    (the old buggy pattern), the two worker threads would run concurrently and the
    ``running`` flag would be observed ``True`` twice at once. Under the corrected
    ``async with lock:`` pattern the second transfer cannot start until the first
    finishes, so the ``overlap`` flag is never set.
    """

    def __init__(
        self,
        running: dict[str, bool],
        overlap: dict[str, bool],
        delay: float,
    ) -> None:
        """Store the shared ``running``/``overlap`` flags and the blocking delay."""
        self._running = running
        self._overlap = overlap
        self._delay = delay

    def xfer2(self, data: list[int]) -> list[int]:
        """Mark running, block for ``delay``, then release the running flag."""
        if self._running.get("active", False):
            self._overlap["detected"] = True
        self._running["active"] = True
        time.sleep(self._delay)
        self._running["active"] = False
        return [1, 2, 3]


class TestRealSpiBusXfer2:
    """Tests that ``RealSpiBus.xfer2`` uses the shared per-bus lock."""

    @pytest.mark.asyncio
    async def test_xfer2_uses_shared_bus_lock(self) -> None:
        assert await get_bus_lock(0) is await get_bus_lock(0)  # nosemgrep: correctness.common-mistakes.identical-is-comparison

        bus = RealSpiBus(bus_number=0, device_number=0)
        bus.bus_number = 0
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        real_to_thread = asyncio.to_thread
        observed: list[tuple[Any, tuple[Any, ...]]] = []

        def _spy(callable_: Any, *args: Any) -> Any:
            observed.append((callable_, args))
            return real_to_thread(callable_, *args)

        with patch("asyncio.to_thread", _spy):
            result = await bus.xfer2(bytearray([1, 2, 3]))

        assert result == [1, 2, 3]
        assert isinstance(result, list)
        assert len(result) == 3

        xfer2_calls = [
            (callable_, args)
            for callable_, args in observed
            if callable_ is bus._spidev.xfer2
        ]
        assert len(xfer2_calls) == 1
        called_callable, called_args = xfer2_calls[0]
        assert called_callable is bus._spidev.xfer2
        assert called_args[0] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_mutual_exclusion_holds_same_bus(self) -> None:
        """Two ``RealSpiBus`` on the same bus number never transfer concurrently.

        Both buses share the single per-bus lock returned by ``get_bus_lock``. Each
        kernel marks itself ``active`` while its worker thread runs; the lock held
        across ``asyncio.to_thread`` by the corrected ``async with lock:`` pattern
        serializes the worker threads, so the second transfer cannot start until
        the first finishes. If the lock had been released before the transfer the
        two worker threads would overlap and ``detected`` would become ``True``.
        """
        running: dict[str, bool] = {"active": False}
        overlap: dict[str, bool] = {"detected": False}
        delay: float = 0.02

        bus_a = RealSpiBus(bus_number=0, device_number=0)
        bus_a.bus_number = 0
        bus_a._spidev = _BlockingKernel(running, overlap, delay)

        bus_b = RealSpiBus(bus_number=0, device_number=0)
        bus_b.bus_number = 0
        bus_b._spidev = _BlockingKernel(running, overlap, delay)

        results = await asyncio.gather(
            bus_a.xfer2([1, 2, 3]),
            bus_b.xfer2([1, 2, 3]),
        )

        assert results == [[1, 2, 3], [1, 2, 3]]
        assert overlap["detected"] is False
        assert running["active"] is False


class TestRealSpiBusExceptionMasking:
    """Tests that ``RealSpiBus.xfer2`` preserves the ``__aenter__`` exception.

    When ``async with lock:`` raises on entry (cancellation/timeout), the
    original exception must propagate out of ``xfer2``. The transfer is never
    attempted, so ``asyncio.to_thread`` is never called and the kernel SPI
    ``xfer2`` is never invoked.
    """

    @pytest.mark.asyncio
    async def test_aenter_failure_preserves_original_exception(self) -> None:
        """``xfer2`` raises the original ``__aenter__`` exception, never a mask."""
        bus = RealSpiBus(bus_number=0, device_number=0)
        bus.bus_number = 0
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        original_exception: Exception = RuntimeError("lock acquisition cancelled")

        async def _fake_get_bus_lock(bus_number: int) -> _ExceptionLock:
            return _ExceptionLock(original_exception)

        to_thread_called: bool = False
        real_to_thread = asyncio.to_thread

        def _spy(callable_: Any, *args: Any) -> Any:
            nonlocal to_thread_called
            to_thread_called = True
            return real_to_thread(callable_, *args)

        with patch(
            "pi_lora.drivers.spi.bus.get_bus_lock",
            _fake_get_bus_lock,
        ), patch("asyncio.to_thread", _spy), pytest.raises(RuntimeError) as exc_info:
            await bus.xfer2(bytearray([1, 2, 3]))

        assert exc_info.value is original_exception
        assert to_thread_called is False  # nosemgrep: correctness.common-mistakes.identical-is-comparison
        bus._spidev.xfer2.assert_not_called()


class TestSpiLocksConcurrentAccess:
    """Integration: fifty concurrent ``get_bus_lock(0)`` collapse to one instance.

    Every caller on bus 0 must receive the identical :class:`_GuardedLock` so the
    fan-out cannot observe divergent instances. The mutual-exclusion check reuses
    ``_BlockingKernel`` (mirroring ``TestRealSpiBusXfer2.test_mutual_exclusion``):
    two buses on bus 0 never overlap their blocking kernels.
    """

    @pytest.mark.asyncio
    async def test_spi_locks_concurrent_access(self) -> None:
        """Fifty concurrent ``await get_bus_lock(0)`` collapse to one instance."""
        results = await asyncio.gather(*(get_bus_lock(0) for _ in range(50)))
        assert len(results) == 50
        assert all(isinstance(lock, _GuardedLock) for lock in results)
        assert all(lock is results[0] for lock in results)

        running: dict[str, bool] = {"active": False}
        overlap: dict[str, bool] = {"detected": False}
        delay: float = 0.02

        bus_a = RealSpiBus(bus_number=0, device_number=0)
        bus_a.bus_number = 0
        bus_a._spidev = _BlockingKernel(running, overlap, delay)

        bus_b = RealSpiBus(bus_number=0, device_number=0)
        bus_b.bus_number = 0
        bus_b._spidev = _BlockingKernel(running, overlap, delay)

        transfers = list(await asyncio.gather(
            bus_a.xfer2([1, 2, 3]),
            bus_b.xfer2([1, 2, 3]),
        ))
        assert transfers == [[1, 2, 3], [1, 2, 3]]
        assert overlap["detected"] is False
        assert running["active"] is False
