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

        bus = RealSpiBus()
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

        bus_a = RealSpiBus()
        bus_a.bus_number = 0
        bus_a._spidev = _BlockingKernel(running, overlap, delay)

        bus_b = RealSpiBus()
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
        bus = RealSpiBus()
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

        bus_a = RealSpiBus()
        bus_a.bus_number = 0
        bus_a._spidev = _BlockingKernel(running, overlap, delay)

        bus_b = RealSpiBus()
        bus_b.bus_number = 0
        bus_b._spidev = _BlockingKernel(running, overlap, delay)

        transfers = list(await asyncio.gather(
            bus_a.xfer2([1, 2, 3]),
            bus_b.xfer2([1, 2, 3]),
        ))
        assert transfers == [[1, 2, 3], [1, 2, 3]]
        assert overlap["detected"] is False
        assert running["active"] is False
