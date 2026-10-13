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

"""Unit tests for scheduler components: TimerScheduler, IdlePacer, InterruptBridge."""

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from src.pi_lora.framework.events import EventType
from src.pi_lora.framework.scheduler import (
    IdlePacer,
    InterruptBridge,
    Scheduler,
    TimerScheduler,
)


@pytest.fixture
def mock_module() -> MagicMock:
    """Provide a MagicMock with an asyncio.Queue event_queue."""
    mod = MagicMock()
    mod.event_queue = asyncio.Queue()
    return mod


class TestTimerScheduler:
    """Verify TimerScheduler interval management and task creation."""

    def test_default_interval(self) -> None:
        ts = TimerScheduler(default_interval=2.0)
        assert ts._default_interval == 2.0

    def test_set_interval(self, mock_module: MagicMock) -> None:
        ts = TimerScheduler()
        ts.set_interval(mock_module, 3.5)
        assert ts.get_interval(mock_module) == 3.5

    def test_remove_interval(self, mock_module: MagicMock) -> None:
        ts = TimerScheduler()
        ts.set_interval(mock_module, 1.0)
        ts.set_interval(mock_module, None)
        assert ts.get_interval(mock_module) is None

    @pytest.mark.asyncio
    async def test_register_module_defers_task_until_start(
        self, mock_module: MagicMock
    ) -> None:
        ts = TimerScheduler()
        ts.register_module(mock_module, 1.0)
        assert mock_module not in ts._tasks
        await ts.start()
        assert mock_module in ts._tasks
        assert ts._tasks[mock_module] is not None

    @pytest.mark.asyncio
    async def test_start_sets_running(self) -> None:
        ts = TimerScheduler()
        assert ts._running is False
        await ts.start()
        assert ts._running is True

    @pytest.mark.asyncio
    async def test_stop_cancels_tasks(self, mock_module: MagicMock) -> None:
        ts = TimerScheduler()
        ts.register_module(mock_module, 1.0)
        await ts.start()
        initial_task = ts._tasks[mock_module]
        await ts.stop()
        assert not ts._running
        await asyncio.sleep(0.05)
        assert initial_task.done()


class TestIdlePacer:
    """Verify IdlePacer manages idle-enabled modules."""

    def test_add_idle_enabled_module(self, mock_module: MagicMock) -> None:
        pacer = IdlePacer()
        pacer.set_idle_enabled(mock_module, True)
        assert mock_module in pacer._idle_enabled_modules

    def test_remove_idle_enabled_module(self, mock_module: MagicMock) -> None:
        pacer = IdlePacer()
        pacer.set_idle_enabled(mock_module, True)
        pacer.set_idle_enabled(mock_module, False)
        assert mock_module not in pacer._idle_enabled_modules

    @pytest.mark.asyncio
    async def test_start_creates_task(self) -> None:
        pacer = IdlePacer()
        assert pacer._task is None
        await pacer.start()
        assert pacer._task is not None

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        pacer = IdlePacer()
        await pacer.start()
        task = pacer._task
        await pacer.stop()
        assert not pacer._running
        await asyncio.sleep(0.01)
        assert task is not None and task.done()

    async def _collect_idle_timestamps(
        self, min_interval: float, duration: float
    ) -> list[float]:
        pacer = IdlePacer(min_interval=min_interval)
        mod = MagicMock()
        mod.event_queue = asyncio.Queue()
        pacer.set_idle_enabled(mod, True)
        await pacer.start()
        start_time = time.monotonic()
        timestamps: list[float] = []
        while time.monotonic() - start_time < duration:
            try:
                event = mod.event_queue.get_nowait()
            except asyncio.QueueEmpty:
                remaining = duration - (time.monotonic() - start_time)
                await asyncio.sleep(min(0.001, max(0.0, remaining)))
                continue
            timestamps.append(event.timestamp)
        await pacer.stop()
        return timestamps

    @pytest.mark.asyncio
    async def test_idle_pacer_respects_min_interval(self) -> None:
        timestamps = await self._collect_idle_timestamps(
            min_interval=0.02, duration=0.1
        )
        assert len(timestamps) > 0
        for idx in range(1, len(timestamps)):
            gap = timestamps[idx] - timestamps[idx - 1]
            assert gap >= 0.02 - 0.003
        assert len(timestamps) <= int(0.1 / 0.02) + 3

    @pytest.mark.asyncio
    async def test_idle_pacer_larger_interval_delays_events(self) -> None:
        small_timestamps = await self._collect_idle_timestamps(
            min_interval=0.005, duration=0.15
        )
        large_timestamps = await self._collect_idle_timestamps(
            min_interval=0.03, duration=0.15
        )
        assert len(small_timestamps) > len(large_timestamps)


class TestInterruptBridge:
    """Verify InterruptBridge GPIO→module mapping."""

    @pytest.mark.asyncio
    async def test_register_interrupt_map(self, mock_module: MagicMock) -> None:
        bridge = InterruptBridge()
        bridge.register_interrupt(25, mock_module)
        assert 25 in bridge._interrupt_map
        assert bridge._interrupt_map[25] is mock_module
        await bridge.stop()

    @pytest.mark.asyncio
    async def test_register_creates_task(self, mock_module: MagicMock) -> None:
        bridge = InterruptBridge()
        bridge.register_interrupt(25, mock_module)
        assert bridge._task is not None
        await bridge.stop()

    @pytest.mark.asyncio
    async def test_start_creates_event_and_task(self) -> None:
        bridge = InterruptBridge()
        await bridge.start()
        assert bridge._interrupt_event is not None
        assert bridge._task is not None

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self) -> None:
        bridge = InterruptBridge()
        await bridge.start()
        task = bridge._task
        await bridge.stop()
        assert not bridge._running
        await asyncio.sleep(0.01)
        assert task is not None and task.done()

    def test_trigger_interrupt_sets_event(self) -> None:
        bridge = InterruptBridge()
        bridge._interrupt_event = asyncio.Event()
        bridge.trigger_interrupt(25)
        assert bridge._interrupt_event.is_set() is True

    def test_trigger_interrupt_noop_without_event(self) -> None:
        bridge = InterruptBridge()
        bridge._interrupt_event = None
        bridge.trigger_interrupt(25)  # Should not raise

    @pytest.mark.asyncio
    async def test_interrupt_routes_to_correct_module(self) -> None:
        bridge = InterruptBridge()
        module_a = MagicMock()
        module_a.event_queue = asyncio.Queue()
        module_b = MagicMock()
        module_b.event_queue = asyncio.Queue()
        bridge.register_interrupt(25, module_a)
        bridge.register_interrupt(26, module_b)
        await bridge.start()
        bridge.trigger_interrupt(26)
        await asyncio.sleep(0.05)
        await bridge.stop()

        interrupt_events: list[object] = []
        while not module_b.event_queue.empty():
            event = await module_b.event_queue.get()
            interrupt_events.append(event)
        assert any(
            event.event_type == EventType.INTERRUPT
            and event.payload.gpio_pin == 26
            for event in interrupt_events
        )
        assert module_a.event_queue.empty()


class TestScheduler:
    """Verify Scheduler composes TimerScheduler, IdlePacer, InterruptBridge."""

    def test_init_components(self) -> None:
        sched = Scheduler(default_timer_interval=0.5)
        assert sched.timer_scheduler._default_interval == 0.5
        assert isinstance(sched.idle_pacer, IdlePacer)
        assert isinstance(sched.interrupt_bridge, InterruptBridge)

    @pytest.mark.asyncio
    async def test_start_all_components(self) -> None:
        sched = Scheduler()
        await sched.start()
        assert sched.timer_scheduler._running is True
        assert sched.idle_pacer._running is True
        assert sched.interrupt_bridge._running is True

    @pytest.mark.asyncio
    async def test_stop_all_components(self) -> None:
        sched = Scheduler()
        await sched.start()
        await sched.stop()
        assert sched.timer_scheduler._running is False
        assert sched.idle_pacer._running is False
        assert sched.interrupt_bridge._running is False

    @pytest.mark.asyncio
    async def test_register_module_configures_all(self, mock_module: MagicMock) -> None:
        sched = Scheduler()
        sched.register_module(
            mock_module,
            timer_interval=2.0,
            idle_enabled=True,
            interrupt_gpio_pins=[25, 26],
        )
        assert sched.timer_scheduler.get_interval(mock_module) == 2.0
        assert mock_module in sched.idle_pacer._idle_enabled_modules
        assert 25 in sched.interrupt_bridge._interrupt_map
        assert 26 in sched.interrupt_bridge._interrupt_map
        await sched.stop()

    @pytest.mark.asyncio
    async def test_register_without_gpios(self, mock_module: MagicMock) -> None:
        sched = Scheduler()
        sched.register_module(mock_module, timer_interval=1.0, idle_enabled=False)
        assert mock_module not in sched.idle_pacer._idle_enabled_modules
        await sched.stop()

    def test_set_timer_interval(self, mock_module: MagicMock) -> None:
        sched = Scheduler()
        sched.set_timer_interval(mock_module, 3.0)
        assert sched.get_timer_interval(mock_module) == 3.0

    def test_set_idle_enabled(self, mock_module: MagicMock) -> None:
        sched = Scheduler()
        sched.set_idle_enabled(mock_module, True)
        assert mock_module in sched.idle_pacer._idle_enabled_modules
