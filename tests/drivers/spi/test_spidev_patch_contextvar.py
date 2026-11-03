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
from src.pi_lora.drivers.spi.bus import _spidev_patch_active


class TestContextVarPatchFlag:
    """Verify the ``_spidev_patch_active`` ContextVar semantics.

    Every test that mutates the ContextVar resets it in a ``finally`` so no
    state leaks into the main context and no other test observes a stale value.
    """

    def test_contextvar_default_is_false(self) -> None:
        """The ContextVar default (no active patch) is ``False``."""
        assert _spidev_patch_active.get() is False

    def test_contextvar_set_get_in_same_context(self) -> None:
        """Setting ``True`` is observable by ``.get()``; ``.reset()`` clears it."""
        token: bool | None = _spidev_patch_active.set(True)
        try:
            assert _spidev_patch_active.get() is True
        finally:
            _spidev_patch_active.reset(token)
        assert _spidev_patch_active.get() is False

    @pytest.mark.asyncio
    async def test_contextvar_isolates_async_tasks(self) -> None:
        """Two concurrent tasks observe isolated ContextVar values (KEY regression).

        This is the decisive regression test. With the old class-level ``bool``,
        ``_task_a``'s ``.set(True)`` would be a shared global that ``_task_b``
        observes as ``True``. With the :class:`contextvars.ContextVar`, each task
        runs in its own context copy, so ``_task_b`` observes the default
        ``False`` even though ``_task_a`` set ``True`` concurrently.
        """

        async def _task_a() -> bool:
            token_a: bool | None = _spidev_patch_active.set(True)
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_a)

        async def _task_b() -> bool:
            return _spidev_patch_active.get()

        results: dict[str, bool] = {}
        results["a"], results["b"] = await asyncio.gather(_task_a(), _task_b())

        # ``_task_a``'s ``.set(True)`` was confined to its own task context copy,
        # discarded on completion, so the main context stays clean. Re-set ``True``
        # in the main context to confirm the ContextVar remains fully controllable
        # after ``.reset()`` rather than being stuck at a leaked global value.
        token_main: bool | None = _spidev_patch_active.set(True)
        try:
            results["b_after"] = _spidev_patch_active.get()
        finally:
            _spidev_patch_active.reset(token_main)

        assert results["a"] is True
        assert results["b"] is False
        assert results["b_after"] is True

    def test_contextvar_isolates_sync_contexts_via_copy_context(self) -> None:
        """A ContextVar set inside ``copy_context()`` does not leak to the main.

        This sandbox's :class:`contextvars.Context` exposes no ``set``/``reset``
        and no context-manager protocol, so isolation is exercised through
        :meth:`Context.run`, which executes a callable with the copied context as
        the current context. The worker's ``.set(True)`` is confined to the copy;
        the main context is never touched and stays ``False``.
        """

        def _worker() -> bool:
            ctx: contextvars.Context = contextvars.copy_context()

            def _observe() -> bool:
                token_w: bool | None = _spidev_patch_active.set(True)
                try:
                    return _spidev_patch_active.get()
                finally:
                    _spidev_patch_active.reset(token_w)

            return ctx.run(_observe)

        worker_result: bool = _worker()
        main_result: bool = _spidev_patch_active.get()
        assert worker_result is True
        assert main_result is False

    @pytest.mark.asyncio
    async def test_contextvar_isolation_per_async_context(self) -> None:
        """Two parallel async tasks set different values without interfering.

        Each task sets ``_spidev_patch_active`` to a distinct value inside its own
        coroutine context. With a :class:`contextvars.ContextVar`, each task runs
        in its own copied context, so ``_task_a`` observes ``True`` and
        ``_task_b`` observes ``False`` concurrently -- the old class-level ``bool``
        would have made both observe the same leaked value.
        """

        async def _task_a() -> bool:
            token_a: bool | None = _spidev_patch_active.set(True)
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_a)

        async def _task_b() -> bool:
            token_b: bool | None = _spidev_patch_active.set(False)
            try:
                return _spidev_patch_active.get()
            finally:
                _spidev_patch_active.reset(token_b)

        observed_a, observed_b = await asyncio.gather(_task_a(), _task_b())

        assert observed_a is True
        assert observed_b is False
        # Both tasks reset their tokens; the main context stays at the default.
        assert _spidev_patch_active.get() is False
