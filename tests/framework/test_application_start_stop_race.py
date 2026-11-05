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

"""NR-6 regression: concurrent start() failure and stop() never double-cleanup."""

import asyncio

import pytest
from tests.spi.mock import MockSpiBusFactory

from pi_lora.framework.application import Application


class _TrackModule:
    """Controllable module that counts close_spi/stop_event_loop calls."""

    def __init__(self, ce_number: int = 0, spi_device_id: int = 0) -> None:
        self.ce_number: int = ce_number
        self.spi_device_id: int = spi_device_id
        self.close_spi_calls: int = 0
        self.stop_event_loop_calls: int = 0

    async def init_spi_bus(self) -> None:
        return None

    async def start_event_loop(self) -> None:
        return None

    async def stop_event_loop(self, mode: object) -> None:
        self.stop_event_loop_calls += 1
        return None

    async def close_spi(self) -> None:
        self.close_spi_calls += 1
        return None

    def get_spi_device_id(self) -> int:
        return self.spi_device_id

    def get_ce_number(self) -> int:
        return self.ce_number


class _TrackStartFailModule(_TrackModule):
    """start_event_loop() raises so the module IS tracked, then cleanup drains it."""

    def __init__(self) -> None:
        super().__init__()
        self._start_error: RuntimeError = RuntimeError("start_event_loop() failed")

    async def start_event_loop(self) -> None:
        raise self._start_error


@pytest.mark.asyncio
async def test_start_stop_concurrent_no_double_cleanup() -> None:
    """NR-6 FIX: concurrent start() failure and stop() never double-cleanup.

    start() holds the lifecycle lock across the entire start+cleanup window, so a
    concurrent stop() cannot interleave with _cleanup_partial_start(). Each module
    is drained exactly once, the gather completes without deadlock, and no
    ExceptionGroup is produced by a cleanup race.
    """
    app = Application(config=None, spi_factory=MockSpiBusFactory())

    module = _TrackStartFailModule()

    async def _register_module(
        radio_configs: object,
        scheduler: object,
        spi_factory: object = None,
    ) -> None:
        scheduler.register_module(module, timer_interval=1.0, idle_enabled=True)
        app.module_manager.modules.append(module)

    def _get_all_modules() -> list:
        return [module]

    app.module_manager.load_from_config = _register_module  # type: ignore[assignment]
    app.module_manager.get_all_modules = _get_all_modules  # type: ignore[assignment]

    async def failing_start() -> None:
        await app.start()

    async def concurrent_stop() -> None:
        await asyncio.sleep(0.01)  # let start() acquire the lock first
        await app.stop()

    coro = asyncio.gather(
        failing_start(),
        concurrent_stop(),
        return_exceptions=True,
    )

    try:
        results = await asyncio.wait_for(coro, timeout=5.0)
    except TimeoutError:
        pytest.fail(
            "start() deadlocked on the self-held lifecycle lock -- NR-6 not fixed"
        )

    # No double-close: the tracked module is drained exactly once.
    assert module.close_spi_calls == 1
    assert module.stop_event_loop_calls == 1

    # State flags reset cleanly to a baseline.
    assert app._started is False
    assert app._started_modules == []
    assert app._scheduler_started is False

    # No ExceptionGroup leaked from the cleanup race (stop() returned early on
    # _started == False).
    assert not any(isinstance(r, ExceptionGroup) for r in results)
