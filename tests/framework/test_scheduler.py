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
import warnings
from unittest.mock import MagicMock, patch

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
    async def test_register_module_creates_task_when_running(
        self, mock_module: MagicMock
    ) -> None:
        ts = TimerScheduler()
        await ts.start()
        assert ts._running is True
        ts.register_module(mock_module, 1.0)
        assert mock_module in ts._tasks
        assert ts._tasks[mock_module] is not None
        assert mock_module in ts._registered
        await ts.stop()

    @pytest.mark.asyncio
    async def test_register_module_repeats_task_when_running(
        self, mock_module: MagicMock
    ) -> None:
        ts = TimerScheduler()
        await ts.start()
        ts.register_module(mock_module, 1.0)
        first_task = ts._tasks[mock_module]
        ts.register_module(mock_module, 2.0)
        assert ts._tasks[mock_module] is first_task
        assert ts.get_interval(mock_module) == 2.0
        await ts.stop()

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

    @pytest.mark.asyncio
    async def test_unregister_timer_module(self, mock_module: MagicMock) -> None:
        ts = TimerScheduler()
        ts.register_module(mock_module, 1.0)
        assert mock_module in ts._registered
        assert ts.get_interval(mock_module) == 1.0
        await ts.unregister_module(mock_module)
        assert ts.get_interval(mock_module) is None
        assert mock_module not in ts._tasks
        assert mock_module not in ts._registered

    @pytest.mark.asyncio
    async def test_unregister_awaits_cancelled_task(self, mock_module: MagicMock) -> None:
        ts = TimerScheduler()
        ts.register_module(mock_module, 1.0)
        await ts.start()
        task = ts._tasks[mock_module]
        with warnings.catch_warnings(record=True) as recorded:
            await ts.unregister_module(mock_module)
            await asyncio.sleep(0.05)
        assert task.done()
        for record in recorded:
            if isinstance(record.warning, RuntimeWarning) and (
                "destroyed" in str(record.warning).lower()
                or "pending" in str(record.warning).lower()
            ):
                raise AssertionError(
                    "RuntimeWarning: Task was destroyed but pending future"
                )

    @pytest.mark.asyncio
    async def test_timer_task_survives_put_failure(self) -> None:
        class _FailingQueue:
            def __init__(self) -> None:
                self._items: list[object] = []
                self._raised_once = False

            async def put(self, item: object) -> None:
                if not self._raised_once:
                    self._raised_once = True
                    raise RuntimeError("event_queue corrupted")
                self._items.append(item)

            async def get(self) -> object:
                return self._items.pop(0)

        module = MagicMock()
        module.event_queue = _FailingQueue()
        ts = TimerScheduler(default_interval=0.01)
        ts.register_module(module, 0.01)
        await ts.start()
        with patch("logging.getLogger") as mock_get_logger, pytest.raises(
            asyncio.TimeoutError
        ) as timeout_info:
            await asyncio.wait_for(ts._timer_task(module), timeout=0.2)
        assert isinstance(timeout_info.value, asyncio.TimeoutError)
        mock_logger = mock_get_logger.return_value
        assert mock_logger.error.called
        events: list[object] = []
        while module.event_queue._items:
            events.append(await module.event_queue.get())
        assert any(
            getattr(event, "event_type", None) == EventType.TIMER for event in events
        )
        await ts.stop()


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

    def test_idle_pacer_rejects_non_positive_interval(self) -> None:
        with pytest.raises(
            ValueError, match="must be positive"
        ) as exc_info:
            IdlePacer(min_interval=0.0)
        assert "must be positive" in str(exc_info.value)
        with pytest.raises(ValueError, match="must be positive"):
            IdlePacer(min_interval=-1.0)

    def test_idle_pacer_accepts_positive_interval(self) -> None:
        pacer = IdlePacer(min_interval=0.01)
        assert pacer._min_interval == 0.01

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

    @pytest.mark.asyncio
    async def test_idle_task_survives_put_failure(self) -> None:
        class _FailingQueue:
            def __init__(self) -> None:
                self._items: list[object] = []
                self._raised_once = False

            async def put(self, item: object) -> None:
                if not self._raised_once:
                    self._raised_once = True
                    raise RuntimeError("event_queue corrupted")
                self._items.append(item)

            async def get(self) -> object:
                return self._items.pop(0)

        module = MagicMock()
        module.event_queue = _FailingQueue()
        pacer = IdlePacer(min_interval=0.01)
        pacer.set_idle_enabled(module, True)
        await pacer.start()
        with patch("logging.getLogger") as mock_get_logger, pytest.raises(
            asyncio.TimeoutError
        ) as timeout_info:
            await asyncio.wait_for(pacer._idle_task(), timeout=0.2)
        assert isinstance(timeout_info.value, asyncio.TimeoutError)
        mock_logger = mock_get_logger.return_value
        assert mock_logger.error.called
        events: list[object] = []
        while module.event_queue._items:
            events.append(await module.event_queue.get())
        assert any(
            getattr(event, "event_type", None) == EventType.IDLE for event in events
        )
        await pacer.stop()

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
    async def test_register_does_not_start_task(self, mock_module: MagicMock) -> None:
        bridge = InterruptBridge()
        bridge.register_interrupt(25, mock_module)
        assert bridge._task is None
        assert bridge._running is False

    @pytest.mark.asyncio
    async def test_register_creates_task(self, mock_module: MagicMock) -> None:
        bridge = InterruptBridge()
        bridge.register_interrupt(25, mock_module)
        assert bridge._task is None
        await bridge.start()
        assert bridge._task is not None
        await bridge.stop()

    def test_interrupt_bridge_bounded_queue(self) -> None:
        bridge = InterruptBridge()
        assert bridge._trigger_queue.maxsize == 1000
        bridge.trigger_interrupt(25)
        bridge.trigger_interrupt(26)
        bridge.trigger_interrupt(27)
        assert not bridge._trigger_queue.empty()
        assert bridge._trigger_queue.get_nowait() == 25
        assert bridge._trigger_queue.get_nowait() == 26
        assert bridge._trigger_queue.get_nowait() == 27
        assert bridge._trigger_queue.empty()

    def test_interrupt_bridge_bounded_queue_reaches_maxsize(self) -> None:
        bridge = InterruptBridge(max_queue_size=3)
        assert bridge._trigger_queue.maxsize == 3
        bridge.trigger_interrupt(25)
        bridge.trigger_interrupt(26)
        bridge.trigger_interrupt(27)
        with pytest.raises(asyncio.QueueFull):
            bridge._trigger_queue.put_nowait(28)

    def test_interrupt_bridge_queue_full_handling(self) -> None:
        bridge = InterruptBridge(max_queue_size=2)
        assert bridge._trigger_queue.maxsize == 2
        with patch("logging.getLogger") as mock_get_logger:
            for gpio_pin in (25, 26, 27, 28, 29):
                bridge.trigger_interrupt(gpio_pin)
            mock_logger = mock_get_logger.return_value
            assert mock_logger.warning.called
            args = mock_logger.warning.call_args.args
            assert args[0] == (
                "Interrupt queue full (maxsize=%d); dropping interrupt for GPIO %d"
            )
            assert args[1] == 2
            assert args[2] == 29
        assert not bridge._trigger_queue.empty()
        assert bridge._trigger_queue.maxsize == 2

    @pytest.mark.asyncio
    async def test_start_creates_event_and_task(self) -> None:
        bridge = InterruptBridge()
        await bridge.start()
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
        bridge.trigger_interrupt(25)
        assert bridge._trigger_queue.get_nowait() == 25
        assert bridge._trigger_queue.empty()

    def test_trigger_interrupt_noop_without_event(self) -> None:
        bridge = InterruptBridge()
        bridge.trigger_interrupt(25)  # Should not raise

    @pytest.mark.asyncio
    async def test_unregister_module_removes_all_pins(self) -> None:
        bridge = InterruptBridge()
        mod = MagicMock()
        mod.event_queue = asyncio.Queue()
        bridge.register_interrupt(25, mod)
        bridge.register_interrupt(26, mod)
        bridge.register_interrupt(27, MagicMock())
        assert 25 in bridge._interrupt_map
        assert 26 in bridge._interrupt_map
        assert 27 in bridge._interrupt_map
        bridge.unregister_module(mod)
        assert 25 not in bridge._interrupt_map
        assert 26 not in bridge._interrupt_map
        assert 27 in bridge._interrupt_map
        await bridge.stop()

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

    @pytest.mark.asyncio
    async def test_interrupt_task_survives_put_failure(self) -> None:
        class _FailingQueue:
            def __init__(self) -> None:
                self._items: list[object] = []
                self._raised_once = False

            async def put(self, item: object) -> None:
                if not self._raised_once:
                    self._raised_once = True
                    raise RuntimeError("event_queue corrupted")
                self._items.append(item)

            async def get(self) -> object:
                return self._items.pop(0)

        module_a = MagicMock()
        module_a.event_queue = _FailingQueue()
        module_b = MagicMock()
        module_b.event_queue = asyncio.Queue()
        bridge = InterruptBridge()
        bridge.register_interrupt(25, module_a)
        bridge.register_interrupt(26, module_b)
        await bridge.start()
        with patch("logging.getLogger") as mock_get_logger:
            bridge.trigger_interrupt(25)
            bridge.trigger_interrupt(26)
            bridge.trigger_interrupt(26)
            await asyncio.sleep(0.1)
            mock_logger = mock_get_logger.return_value
            assert mock_logger.error.called
            args = mock_logger.error.call_args.args
            assert args[1] == 25
            interrupt_events: list[object] = []
            while not module_b.event_queue.empty():
                event = await module_b.event_queue.get()
                interrupt_events.append(event)
            assert len(interrupt_events) == 2
            assert all(
                event.event_type == EventType.INTERRUPT
                for event in interrupt_events
            )
        await bridge.stop()


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

    @pytest.mark.asyncio
    async def test_unregister_scheduler_module(self, mock_module: MagicMock) -> None:
        sched = Scheduler()
        sched.register_module(
            mock_module,
            timer_interval=1.0,
            idle_enabled=True,
            interrupt_gpio_pins=[25],
        )
        assert 25 in sched.interrupt_bridge._interrupt_map
        await sched.unregister_module(mock_module)
        assert sched.timer_scheduler.get_interval(mock_module) is None
        assert mock_module not in sched.idle_pacer._idle_enabled_modules
        assert 25 not in sched.interrupt_bridge._interrupt_map
        await sched.stop()

    @pytest.mark.asyncio
    async def test_unregister_scheduler_via_public_bridge(
        self, mock_module: MagicMock
    ) -> None:
        sched = Scheduler()
        sched.register_module(
            mock_module,
            timer_interval=1.0,
            idle_enabled=True,
            interrupt_gpio_pins=[25, 26],
        )
        assert 25 in sched.interrupt_bridge._interrupt_map
        assert 26 in sched.interrupt_bridge._interrupt_map
        await sched.unregister_module(mock_module)
        assert 25 not in sched.interrupt_bridge._interrupt_map
        assert 26 not in sched.interrupt_bridge._interrupt_map
        assert mock_module not in sched.idle_pacer._idle_enabled_modules
        assert sched.timer_scheduler.get_interval(mock_module) is None
        await sched.stop()

    @pytest.mark.asyncio
    async def test_unregister_scheduler_removes_all_components(
        self, mock_module: MagicMock
    ) -> None:
        sched = Scheduler()
        sched.register_module(
            mock_module,
            timer_interval=1.0,
            idle_enabled=True,
            interrupt_gpio_pins=[25],
        )
        await sched.start()
        await sched.unregister_module(mock_module)
        assert mock_module not in sched.timer_scheduler._registered
        assert sched.timer_scheduler.get_interval(mock_module) is None
        assert mock_module not in sched.idle_pacer._idle_enabled_modules
        assert 25 not in sched.interrupt_bridge._interrupt_map
        await sched.stop()

    @pytest.mark.asyncio
    async def test_stop_reverse_order(self) -> None:
        sched = Scheduler()
        order: list[str] = []

        async def record_timer() -> None:
            order.append("timer")

        async def record_idle() -> None:
            order.append("idle")

        async def record_interrupt() -> None:
            order.append("interrupt")

        sched.timer_scheduler.stop = record_timer
        sched.idle_pacer.stop = record_idle
        sched.interrupt_bridge.stop = record_interrupt
        await sched.stop()
        assert order == ["interrupt", "idle", "timer"]

    @pytest.mark.asyncio
    async def test_scheduler_stop_awaits_all_tasks(
        self, mock_module: MagicMock
    ) -> None:
        sched = Scheduler()
        sched.register_module(
            mock_module,
            timer_interval=1.0,
            idle_enabled=True,
            interrupt_gpio_pins=[25],
        )
        await sched.start()
        timer_task: asyncio.Task[None] = sched.timer_scheduler._tasks[mock_module]
        idle_task: asyncio.Task[None] | None = sched.idle_pacer._task
        interrupt_task: asyncio.Task[None] | None = sched.interrupt_bridge._task
        await sched.stop()
        await asyncio.sleep(0.05)
        assert timer_task.done()
        assert idle_task is not None and idle_task.done()
        assert interrupt_task is not None and interrupt_task.done()
        assert sched.timer_scheduler._running is False
        assert sched.idle_pacer._running is False
        assert sched.interrupt_bridge._running is False
