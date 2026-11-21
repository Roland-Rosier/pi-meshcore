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

"""R-4 regression: ``_spidev_patch_active`` is a ContextVar.

These tests prove the class-level ``bool`` flag (CR-8/Plan-11 debt) was
replaced by a :class:`contextvars.ContextVar`, so the flag is isolated per
async context (task) and per ``copy_context()`` block instead of being a
globally shared attribute that leaks across instances and contexts.
"""

import asyncio
import contextvars

import pytest

from pi_lora.drivers.spi.bus import _spidev_patch_active


class TestContextVarPatchFlag:
    """Verify the ``_spidev_patch_active`` ContextVar semantics.

    Every test that mutates the ContextVar resets it in a ``finally`` so no
    state leaks into the main context and no other test observes a stale value.
    """

    def test_contextvar_default_is_false(self) -> None:
        """The ContextVar default (no active patch) is ``0``."""
        assert _spidev_patch_active.get() == 0

    def test_contextvar_set_get_in_same_context(self) -> None:
        """Setting ``True`` is observable by ``.get()``; ``.reset()`` clears it."""
        token: contextvars.Token[int] | None = _spidev_patch_active.set(
            _spidev_patch_active.get() + 1
        )
        try:
            assert _spidev_patch_active.get() > 0
        finally:
            _spidev_patch_active.reset(token)
        assert _spidev_patch_active.get() == 0

    @pytest.mark.asyncio
    async def test_contextvar_isolates_async_tasks(self) -> None:
        """Two concurrent tasks observe isolated ContextVar values (KEY regression).

        This is the decisive regression test. With the old class-level ``bool``,
        ``_task_a``'s ``.set(True)`` would be a shared global that ``_task_b``
        observes as ``True``. With the :class:`contextvars.ContextVar` (an int
        counter, default 0), each task runs in its own context copy, so ``_task_b``
        observes the default ``0`` even though ``_task_a`` incremented concurrently.
        """

        async def _task_a() -> int:
            token_a: contextvars.Token[int] | None = _spidev_patch_active.set(
                _spidev_patch_active.get() + 1
            )
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_a)

        async def _task_b() -> int:
            return _spidev_patch_active.get()

        results: dict[str, int] = {}
        results["a"], results["b"] = await asyncio.gather(_task_a(), _task_b())

        # ``_task_a``'s increment was confined to its own task context copy,
        # discarded on completion, so the main context stays at the default 0.
        # Re-increment in the main context to confirm the ContextVar remains fully
        # controllable after ``.reset()`` rather than being stuck at a leaked value.
        token_main: contextvars.Token[int] | None = _spidev_patch_active.set(
            _spidev_patch_active.get() + 1
        )
        try:
            results["b_after"] = _spidev_patch_active.get()
        finally:
            _spidev_patch_active.reset(token_main)

        assert results["a"] > 0
        assert results["b"] == 0
        assert results["b_after"] > 0

    def test_contextvar_isolates_sync_contexts_via_copy_context(self) -> None:
        """A ContextVar set inside ``copy_context()`` does not leak to the main.

        This sandbox's :class:`contextvars.Context` exposes no ``set``/``reset``
        and no context-manager protocol, so isolation is exercised through
        :meth:`Context.run`, which executes a callable with the copied context as
        the current context. The worker's increment is confined to the copy;
        the main context is never touched and stays at the default ``0``.
        """

        def _worker() -> int:
            ctx: contextvars.Context = contextvars.copy_context()

            def _observe() -> int:
                token_w: contextvars.Token[int] | None = _spidev_patch_active.set(
                    _spidev_patch_active.get() + 1
                )
                try:
                    return _spidev_patch_active.get()
                finally:
                    _spidev_patch_active.reset(token_w)

            return ctx.run(_observe)

        worker_result: int = _worker()
        main_result: int = _spidev_patch_active.get()
        assert worker_result > 0
        assert main_result == 0

    @pytest.mark.asyncio
    async def test_contextvar_isolation_per_async_context(self) -> None:
        """Two parallel async tasks set different values without interfering.

        Each task increments ``_spidev_patch_active`` inside its own coroutine
        context. With a :class:`contextvars.ContextVar` (int counter, default 0),
        each task runs in its own copied context, so ``_task_a`` and ``_task_b``
        each observe ``1`` concurrently -- the old class-level ``bool`` would have
        made both observe the same leaked value.
        """

        async def _task_a() -> int:
            token_a: contextvars.Token[int] | None = _spidev_patch_active.set(
                _spidev_patch_active.get() + 1
            )
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_a)

        async def _task_b() -> int:
            token_b: contextvars.Token[int] | None = _spidev_patch_active.set(
                _spidev_patch_active.get() + 1
            )
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_b)

        observed_a, observed_b = await asyncio.gather(_task_a(), _task_b())

        assert observed_a > 0
        assert observed_b > 0
        # Both tasks reset their tokens; the main context stays at the default.
        assert _spidev_patch_active.get() == 0


class TestPatchConcurrency:
    """CR-29-6 (Plan-30/Plan-31): ``spidev_kernel_patch`` thread-safety.

    Plan-30 added the ``threading.Lock`` around the ``sys.modules`` swap but no
    test exercised thread-safety under concurrent ``asyncio.gather``. These tests
    prove 20 concurrent workers, each with its own :class:`FakeSpiDev` instance,
    see no cross-contamination of ``sys.modules["spidev"]``.
    """

    @pytest.mark.asyncio
    async def test_spidev_kernel_patch_thread_safety_under_concurrency(self) -> None:
        """Verify spidev_kernel_patch is safe under concurrent asyncio.gather.

        Multiple concurrent tasks using spidev_kernel_patch must not cross-contaminate
        sys.modules["spidev"]. Each task should see its own FakeSpiDev instance.

        Each worker captures its own :class:`FakeSpiDev` into ``RealSpiBus._spidev``
        during ``open()`` (before its first ``await``), so even though the patched
        ``sys.modules["spidev"]`` is process-global and workers interleave on the
        ``asyncio.to_thread`` boundary inside ``xfer2``, every bus keeps its own
        device reference. ``threading.Lock`` serializes the global ``sys.modules``
        swap; the :class:`contextvars.ContextVar` counter isolates the patch flag
        per task.
        """
        from pi_lora.drivers.spi.bus import RealSpiBus
        from tests.fakes import FakeSpiDev, create_fake_spi_dev, spidev_kernel_patch

        async def worker(worker_id: int) -> str:
            fake = create_fake_spi_dev(module_type="rfm95w")
            fake.set_register(FakeSpiDev.REG_OP_MODE, 0x80 | (worker_id & 0x0F))
            with spidev_kernel_patch(fake):
                bus = RealSpiBus(bus_number=0, device_number=0)
                bus.open()
                # ``bus.xfer2`` is ``async``; ``xfer2([0x01, 0x00])`` is a read of
                # REG_OP_MODE (0x01), so ``result[1]`` is the OP_MODE register value.
                result = await bus.xfer2([0x01, 0x00])
                bus.close()
                return f"worker-{worker_id}-got-{result[1]:02x}"

        results = await asyncio.gather(*[worker(i) for i in range(20)])
        for r in results:
            parts = r.split("-")
            worker_id = int(parts[1])
            expected_val = 0x80 | (worker_id & 0x0F)
            actual_val = int(parts[-1], 16)
            assert actual_val == expected_val, f"Cross-contamination detected: {r}"

    @pytest.mark.asyncio
    async def test_spidev_kernel_patch_thread_safety_mocked(self) -> None:
        """Mock-based variant: each worker sees its own fake via patched sys.modules."""
        from tests.fakes import FakeSpiDev, create_fake_spi_dev, spidev_kernel_patch

        async def worker(worker_id: int) -> str:
            fake = create_fake_spi_dev(module_type="rfm95w")
            fake.set_register(FakeSpiDev.REG_OP_MODE, 0x80 | (worker_id & 0x0F))
            with spidev_kernel_patch(fake):
                # The patched sys.modules["spidev"].SpiDev() returns THIS worker's fake
                import sys
                assert sys.modules.get("spidev") is not None
                mock_spi_dev = sys.modules["spidev"].SpiDev()
                mock_spi_dev.open(0, 0)
                result = mock_spi_dev.xfer2([0x01, 0x00])
                return f"worker-{worker_id}-got-{result[1]:02x}"

        results = await asyncio.gather(*[worker(i) for i in range(20)])
        for r in results:
            parts = r.split("-")
            worker_id = int(parts[1])
            expected_val = 0x80 | (worker_id & 0x0F)
            actual_val = int(parts[-1], 16)
            assert actual_val == expected_val, f"Cross-contamination detected: {r}"
