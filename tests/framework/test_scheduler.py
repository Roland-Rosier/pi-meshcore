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
import threading
import time
import warnings
from unittest.mock import MagicMock, patch

import pytest

from pi_lora.framework.events import EventType
from pi_lora.framework.scheduler import (
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
    async def test_timer_scheduler_unregister_cleans_state(
        self, mock_module: MagicMock
    ) -> None:
        # M-19 FIX (Plan-16): unregister_module() must pop the module from
        # _failure_counts and _last_failure_log in addition to _registered,
        # _intervals, and _tasks. A stale entry would keep the module bound in
        # those dicts, preventing garbage-collection of the module object and
        # leaving a dangling failure record.
        ts = TimerScheduler()
        ts.register_module(mock_module, 1.0)
        ts._failure_counts[mock_module] = 3
        ts._last_failure_log[mock_module] = 1234.5
        assert ts._failure_counts.get(mock_module) == 3
        assert ts._last_failure_log.get(mock_module) == 1234.5
        await ts.unregister_module(mock_module)
        assert ts._failure_counts.get(mock_module) is None
        assert ts._last_failure_log.get(mock_module) is None
        assert mock_module not in ts._registered
        assert ts.get_interval(mock_module) is None
        assert mock_module not in ts._tasks
        assert mock_module not in ts._failure_counts
        assert mock_module not in ts._last_failure_log

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
        ts._running = True

        recorded: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            recorded.append(seconds)
            if len(recorded) >= 3:
                ts._running = False

        with patch("logging.getLogger") as mock_get_logger, patch(
            "asyncio.sleep", side_effect=fake_sleep
        ):
            await ts._timer_task(module)

        mock_logger = mock_get_logger.return_value
        assert mock_logger.error.called
        # First put failed -> backoff min(2 ** 1, 60) == 2.0s, then recovered.
        assert recorded[0] == 2.0
        # Recovery resets the consecutive-failure streak to 0.
        assert ts._failure_counts.get(module) == 0
        events: list[object] = []
        while module.event_queue._items:
            events.append(await module.event_queue.get())
        assert any(
            getattr(event, "event_type", None) == EventType.TIMER for event in events
        )

    @pytest.mark.asyncio
    async def test_timer_task_backoff_matches_formula(self) -> None:
        class _AlwaysFailingQueue:
            async def put(self, item: object) -> None:
                raise RuntimeError("event_queue full")

            async def get(self) -> object:
                return None

        module = MagicMock()
        module.event_queue = _AlwaysFailingQueue()
        ts = TimerScheduler(default_interval=0.01)
        ts.register_module(module, 0.01)
        ts._running = True

        recorded: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            recorded.append(seconds)
            if len(recorded) >= 6:
                ts._running = False

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await ts._timer_task(module)

        # BUG-7 (Option A): backoff is min(2 ** failure_count, 60), capped at 60.
        expected = [min(2 ** i, 60) for i in range(1, 7)]
        assert recorded == expected
        # Six consecutive failures -> count is six; spam stays logarithmic.
        assert ts._failure_counts.get(module) == 6
        assert ts._last_failure_log.get(module) is not None

    @pytest.mark.asyncio
    async def test_timer_task_default_interval_applies_backoff(self) -> None:
        # CR-5 FIX: the default interval path (module not registered with a
        # custom interval, so ``interval is None`` resolved to
        # ``_default_interval``) must ALSO apply exponential backoff. Plan-11
        # skipped backoff here, reintroducing unbounded error spam.
        class _AlwaysFailingQueue:
            async def put(self, item: object) -> None:
                raise RuntimeError("event_queue full")

            async def get(self) -> object:
                return None

        module = MagicMock()
        module.event_queue = _AlwaysFailingQueue()
        ts = TimerScheduler(default_interval=0.01)
        ts.register_module(module, None)
        assert ts.get_interval(module) is None
        ts._running = True

        recorded: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            recorded.append(seconds)
            if len(recorded) >= 6:
                ts._running = False

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await ts._timer_task(module)

        # Same exponential backoff as the custom interval path: min(2 ** k, 60).
        expected = [min(2 ** i, 60) for i in range(1, 7)]
        assert recorded == expected
        assert ts._failure_counts.get(module) == 6
        assert ts._last_failure_log.get(module) is not None

    @pytest.mark.asyncio
    async def test_timer_task_custom_interval_backoff_matches_formula(
        self,
    ) -> None:
        # Custom interval with N consecutive failures must produce sleeps of
        # min(2 ** k, 60), identical to the default interval path (CR-5).
        class _AlwaysFailingQueue:
            async def put(self, item: object) -> None:
                raise RuntimeError("event_queue full")

            async def get(self) -> object:
                return None

        module = MagicMock()
        module.event_queue = _AlwaysFailingQueue()
        ts = TimerScheduler(default_interval=0.01)
        ts.register_module(module, 0.5)
        ts._running = True

        recorded: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            recorded.append(seconds)
            if len(recorded) >= 5:
                ts._running = False

        with patch("asyncio.sleep", side_effect=fake_sleep):
            await ts._timer_task(module)

        expected = [min(2 ** i, 60) for i in range(1, 6)]
        assert recorded == expected
        assert ts._failure_counts.get(module) == 5


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
                    raise asyncio.QueueFull()
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
        # Plan-18 §5.5: a QueueFull put failure is logged as a warning (with
        # exponential backoff), not an error, and the idle task survives it.
        assert mock_logger.warning.called
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

    def test_idle_pacer_docstring_mentions_breaking_change(self) -> None:
        import pi_lora.framework.scheduler as scheduler_module

        doc: str = IdlePacer.__doc__ or ""
        assert "Breaking change" in doc
        assert "asyncio.sleep(0)" in doc
        assert "asyncio.sleep(min_interval)" in doc or "min_interval" in doc

        module_doc: str = scheduler_module.__doc__ or ""
        assert "IdlePacer" in module_doc
        assert "min_interval" in module_doc

    @pytest.mark.asyncio
    async def test_idle_pacer_backoff_on_failure(self) -> None:
        """Blocker 5.5: IdlePacer applies exponential backoff once the per-module
        failure count exceeds 5. Fill the module queue to full so ``put()`` raises
        ``QueueFull``; verify a warning is logged, the backoff delay increases
        (0.0s -> 0.2s) once count > 5, and spamming stops (the module is skipped while
        inside ``_backoff_until``).
        """
        class _AlwaysFullQueue:
            def __init__(self) -> None:
                self.put_calls: int = 0

            async def put(self, item: object) -> None:
                self.put_calls += 1
                raise asyncio.QueueFull()

            async def get(self, *_args: object, **_kwargs: object) -> None:
                return None

        module = MagicMock()
        module.event_queue = _AlwaysFullQueue()

        pacer = IdlePacer(min_interval=0.01)
        pacer.set_idle_enabled(module, True)
        pacer._running = True

        recorded: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            recorded.append(seconds)
            if len(recorded) >= 8:
                pacer._running = False

        with patch("logging.getLogger") as mock_get_logger, patch(
            "asyncio.sleep", side_effect=fake_sleep
        ):
            await pacer._idle_task()

        mock_logger = mock_get_logger.return_value
        assert mock_logger.warning.called

        # Failure count exceeded 5 -> backoff engaged.
        assert pacer._failure_count.get(id(module)) == 6
        # Backoff delay for the 6th failure: min(0.1 * 2**(6-5), 60) == 0.2s.
        assert pacer._backoff_until.get(id(module)) is not None

        warning_texts = [
            call.args[0] for call in mock_logger.warning.call_args_list if call.args
        ]
        # Counts 1-5 log with no backoff (0.0s); count 6 engages backoff (0.2s).
        assert any("backoff=0.0s" in text for text in warning_texts)
        assert any("backoff=0.2s" in text for text in warning_texts)

        # Spamming stopped after backoff engaged: put() called exactly 6 times
        # (counts 1-6); iterations 7-8 were skipped while inside _backoff_until.
        assert module.event_queue.put_calls == 6


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
        assert bridge._trigger_queue.maxsize == bridge._max_queue_size == 10000
        bridge.trigger_interrupt(25)
        bridge.trigger_interrupt(26)
        bridge.trigger_interrupt(27)
        assert not bridge._trigger_queue.empty()
        assert bridge._trigger_queue.get_nowait() == 25
        assert bridge._trigger_queue.get_nowait() == 26
        assert bridge._trigger_queue.get_nowait() == 27
        assert bridge._trigger_queue.empty()

    def test_interrupt_bridge_monitoring_threshold_logs(self) -> None:
        bridge = InterruptBridge(monitor_queue_depth_threshold=2)
        assert bridge._trigger_queue.maxsize == 10000
        with patch("logging.getLogger") as mock_get_logger:
            bridge.trigger_interrupt(25)
            bridge.trigger_interrupt(26)
            bridge.trigger_interrupt(27)
            mock_logger = mock_get_logger.return_value
            assert mock_logger.warning.called
            args = mock_logger.warning.call_args.args
            assert args[0] == (
                "Interrupt queue depth %d reached monitoring threshold %d; "
                "abnormal interrupt rate detected (GPIO %d)."
            )
            assert args[1] == 3
            assert args[2] == 2
            assert args[3] == 27

    def test_interrupt_bridge_bounded_queue_drop_oldest(self) -> None:
        # CR-6 FIX: the trigger queue is bounded (maxsize=10000) with a
        # drop-oldest policy. A burst of >10000 interrupts must never grow the
        # queue past maxsize (hard OOM protection), and after overflow the queue
        # must retain the most recent pins (drop-oldest, not drop-newest).
        bridge = InterruptBridge()
        assert bridge._max_queue_size == 10000
        assert bridge._trigger_queue.maxsize == 10000
        # Fill to capacity with pins 0..9999.
        for gpio_pin in range(10000):
            bridge.trigger_interrupt(gpio_pin)
        assert bridge._trigger_queue.qsize() == 10000
        # Overflow with pins 10000..19999: each new insert drops the oldest.
        for gpio_pin in range(10000, 20000):
            bridge.trigger_interrupt(gpio_pin)
        # Memory bound: depth never exceeded maxsize; still exactly maxsize.
        assert bridge._trigger_queue.qsize() == 10000
        # Drop-oldest: oldest surviving pin is 10000, newest is 19999.
        pins: list[int] = []
        while not bridge._trigger_queue.empty():
            pins.append(bridge._trigger_queue.get_nowait())
        assert len(pins) == 10000
        assert pins[0] == 10000
        assert pins[-1] == 19999
        assert bridge._trigger_queue.empty()

    @pytest.mark.asyncio
    async def test_interrupt_bridge_monitoring_threshold_rejects_non_positive(
        self,
    ) -> None:
        with pytest.raises(
            ValueError, match="monitor_queue_depth_threshold must be positive"
        ) as exc_info:
            InterruptBridge(monitor_queue_depth_threshold=0)
        assert "monitor_queue_depth_threshold must be positive" in str(exc_info.value)
        with pytest.raises(ValueError, match="monitor_queue_depth_threshold must be positive"):
            InterruptBridge(monitor_queue_depth_threshold=-5)

    @pytest.mark.asyncio
    async def test_interrupt_bridge_rapid_no_drops(self) -> None:
        bridge = InterruptBridge()
        module = MagicMock()
        module.event_queue = asyncio.Queue()
        for gpio_pin in range(25, 50):
            bridge.register_interrupt(gpio_pin, module)
        await bridge.start()
        total = 4975
        for offset in range(total):
            bridge.trigger_interrupt(25 + offset % 25)
        while not bridge._trigger_queue.empty():
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        await bridge.stop()
        interrupt_events: list[object] = []
        while not module.event_queue.empty():
            event = await module.event_queue.get()
            interrupt_events.append(event)
        assert len(interrupt_events) == total
        assert all(
            event.event_type == EventType.INTERRUPT for event in interrupt_events
        )

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

    def test_interrupt_bridge_reentrant_lock(self) -> None:
        # H-9 FIX (Plan-16): the producer lock is a threading.RLock (re-entrant),
        # NOT a plain threading.Lock. GPIO interrupt handlers can be re-entrant —
        # an edge-triggered/recursive callback may call trigger_interrupt() while
        # another call already holds self._trigger_lock. A plain Lock would
        # self-lock and deadlock on that recursive call; RLock allows the same
        # thread to re-acquire.
        bridge = InterruptBridge()

        # 1. The lock must be a threading.RLock (re-entrant), never a plain
        # threading.Lock. ``threading.RLock`` is a factory function, not a type,
        # so the concrete type is captured via an instance's ``type``; a plain
        # Lock resolves to a distinct ``_thread.lock`` type and would deadlock
        # on the re-entrant path below.
        rlock_type = type(threading.RLock())
        lock_type = type(threading.Lock())
        assert isinstance(bridge._trigger_lock, rlock_type)
        assert type(bridge._trigger_lock) is not lock_type

        # 2. Demonstrate genuine re-entrancy in a single thread: a plain Lock
        # would deadlock here (raise RuntimeError on the second acquire); RLock
        # counts acquisitions and releases only on the outermost exit.
        with bridge._trigger_lock, bridge._trigger_lock:
            pass

        # 3. Functional stress test: hammer trigger_interrupt() from a single
        # thread while driving the producer queue to full. Every overflow hits
        # the drop-oldest `with self._trigger_lock:` branch. A plain Lock would
        # deadlock on the first overflow's compound get_nowait()+put_nowait()
        # re-entrant path; RLock must not. The queue must stay bounded at
        # maxsize with no deadlock, and the drop-oldest policy must retain the
        # most recent pins.
        for gpio_pin in range(bridge._max_queue_size):
            bridge.trigger_interrupt(gpio_pin)
        assert bridge._trigger_queue.qsize() == bridge._max_queue_size

        # 4. Re-entrancy through the real code path: while this thread already
        # holds self._trigger_lock (simulating a re-entrant/recursive GPIO
        # callback that fires trigger_interrupt() mid-another-call), a full
        # trigger_interrupt() re-acquires the same lock in its drop-oldest
        # branch. A plain Lock would self-lock and deadlock here; RLock does
        # not, so execution must reach the end of this block.
        with bridge._trigger_lock:
            bridge.trigger_interrupt(999_999)
            assert bridge._trigger_queue.qsize() == bridge._max_queue_size

        # 5. Overflow past maxsize keeps the queue bounded and drop-oldest:
        # the most recent pins survive.
        for gpio_pin in range(
            bridge._max_queue_size, bridge._max_queue_size * 2
        ):
            bridge.trigger_interrupt(gpio_pin)
        assert bridge._trigger_queue.qsize() == bridge._max_queue_size
        pins: list[int] = []
        while not bridge._trigger_queue.empty():
            pins.append(bridge._trigger_queue.get_nowait())
        assert len(pins) == bridge._max_queue_size
        assert pins[0] == bridge._max_queue_size
        assert pins[-1] == bridge._max_queue_size * 2 - 1
        assert bridge._trigger_queue.empty()

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

    @pytest.mark.asyncio
    async def test_interrupt_bridge_event_not_polling(
        self, mock_module: MagicMock
    ) -> None:
        # M-21 FIX (Plan-16): the drain task is driven by an asyncio.Event, not a
        # busy-wait asyncio.sleep(0.001) poll. This regression proves both the
        # type contract and the functional event-driven delivery.
        #
        # (1) Type contract: _drain_event must be an asyncio.Event, proving the
        # drain task waits on an event rather than polling with a fixed 1ms sleep.
        bridge = InterruptBridge()
        assert isinstance(bridge._drain_event, asyncio.Event)

        # (2) Functional delivery through the event-driven mechanism. Fill the
        # producer queue with trigger_interrupt() (which sets the drain event via
        # loop.call_soon_threadsafe), start the bridge, and confirm the module's
        # event_queue receives the INTERRUPT events — proving the drain no longer
        # relies on a fixed 1ms poll.
        module = MagicMock()
        module.event_queue = asyncio.Queue()
        bridge.register_interrupt(25, module)
        await bridge.start()
        try:
            for _ in range(3):
                bridge.trigger_interrupt(25)
            await asyncio.sleep(0.05)
        finally:
            await bridge.stop()
        interrupt_events: list[object] = []
        while not module.event_queue.empty():
            event = await module.event_queue.get()
            interrupt_events.append(event)
        assert len(interrupt_events) == 3
        assert all(
            event.event_type == EventType.INTERRUPT for event in interrupt_events
        )
        assert all(
            event.payload.gpio_pin == 25 for event in interrupt_events
        )

    @pytest.mark.asyncio
    async def test_interrupt_bridge_drain_awaits_event_not_sleep(
        self, mock_module: MagicMock
    ) -> None:
        # M-21 FIX (Plan-16, preferred): demonstrate the drain task awaits the
        # asyncio.Event rather than polling with asyncio.sleep. Patch asyncio.sleep
        # to raise; with an empty producer queue and the drain event pre-set, the
        # first drain pass must proceed by awaiting the event without consuming
        # asyncio.sleep. If the drain had busy-waited with sleep(0.001), the
        # patched sleep would raise and this test would fail.
        bridge = InterruptBridge()
        bridge._drain_event.set()
        bridge._running = True
        sleep_calls: list[float] = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            raise RuntimeError("polling detected")

        with patch("asyncio.sleep", side_effect=fake_sleep):
            task = asyncio.create_task(bridge._drain_sync_queue())
            # The task awaits the pre-set event, drains the empty producer, clears
            # the event, then awaits the cleared event (hangs). Let the loop advance
            # past the first pass via a timeout; the patched sleep must never fire.
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(task, timeout=0.05)
            if not task.done():
                task.cancel()
        assert sleep_calls == []

    @pytest.mark.asyncio
    async def test_interrupt_bridge_loop_capture_cross_thread(
        self, mock_module: MagicMock
    ) -> None:
        # H-16-2/Plan-17 FIX: trigger_interrupt() must use the event loop captured
        # in start() (guaranteed the event loop thread), NOT
        # asyncio.get_running_loop() which returns the *current thread's* loop.
        # GPIO interrupt callbacks run in arbitrary threads (lgpio/RPi.GPIO/
        # gpiod), so get_running_loop() there returns the wrong loop or raises
        # RuntimeError. This regression proves both branches:
        #
        #   1. Before start() there is no captured loop; trigger_interrupt() from
        #      the event loop thread must be a no-op (AttributeError on _loop is
        #      None is guarded), not a RuntimeError.
        #   2. After start(), trigger_interrupt() from a *different* thread (not
        #      the event loop thread) must still signal the drain event on the
        #      captured loop via call_soon_threadsafe() and deliver the interrupt.
        bridge = InterruptBridge()

        # (1) No captured loop yet. trigger_interrupt() from the event loop
        # thread must not raise; the try/except (RuntimeError, AttributeError)
        # guard handles _loop is None gracefully.
        bridge.trigger_interrupt(25)
        assert bridge._loop is None
        assert not bridge._trigger_queue.empty()

        # (2) start() captures the event loop.
        await bridge.start()
        assert bridge._loop is not None

        # (3) Deliver from a non-event-loop thread after start(). This is the
        # cross-thread case that the old get_running_loop() code got wrong: from
        # another thread get_running_loop() returns the wrong loop (or raises),
        # but the captured loop makes call_soon_threadsafe() correct.
        module = MagicMock()
        module.event_queue = asyncio.Queue()
        bridge.register_interrupt(25, module)

        def _from_other_thread() -> None:
            bridge.trigger_interrupt(25)

        thread = threading.Thread(target=_from_other_thread)
        thread.start()
        thread.join()
        await asyncio.sleep(0.05)
        await bridge.stop()

        interrupt_events: list[object] = []
        while not module.event_queue.empty():
            event = await module.event_queue.get()
            interrupt_events.append(event)
        assert any(
            event.event_type == EventType.INTERRUPT
            and event.payload.gpio_pin == 25
            for event in interrupt_events
        )

    @pytest.mark.asyncio
    async def test_interrupt_bridge_restart_captures_new_loop(
        self,
    ) -> None:
        """Blocker 5.4: ``stop()`` clears ``self._loop`` to None so a restart captures
        a fresh running loop. A stale (possibly closed) loop reference would raise
        ``RuntimeError`` in ``call_soon_threadsafe()`` on restart.
        """
        bridge = InterruptBridge()

        await bridge.start()
        first_loop = bridge._loop
        assert first_loop is not None

        await bridge.stop()
        # stop() clears _loop so the next start() does not reuse a stale reference.
        assert bridge._loop is None

        await bridge.start()
        second_loop = bridge._loop
        assert second_loop is not None
        # The restart re-captured the currently-running loop (fresh, not stale/None).
        assert second_loop is asyncio.get_running_loop()

        # trigger_interrupt() can safely signal the drain event on the captured loop
        # without raising RuntimeError (which a stale closed loop would).
        bridge.trigger_interrupt(25)
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
    async def test_unregister_module_aggregates_exception_groups(self) -> None:
        # CR-29-5 FIX: Scheduler.unregister_module() raises an ExceptionGroup at
        # the end, so it must catch ExceptionGroup (a BaseException, NOT an
        # Exception) from each component's unregister. An ExceptionGroup raised by
        # a component would otherwise propagate out of the try block and skip the
        # remaining components. Match Application.stop() (application.py:217).
        timer_exc = ExceptionGroup("timer error", [ValueError("timer-1")])
        idle_exc = ExceptionGroup(
            "idle error", [KeyError("idle-1"), KeyError("idle-2")]
        )
        interrupt_exc = ExceptionGroup(
            "interrupt error", [RuntimeError("interrupt-1")]
        )

        async def _timer_raise(module: MagicMock) -> None:
            raise timer_exc

        def _idle_raise(module: MagicMock, enabled: bool) -> None:
            raise idle_exc

        def _interrupt_raise(module: MagicMock) -> None:
            raise interrupt_exc

        sched = Scheduler()
        sched.timer_scheduler.unregister_module = _timer_raise  # type: ignore[assignment]
        sched.idle_pacer.set_idle_enabled = _idle_raise  # type: ignore[assignment]
        sched.interrupt_bridge.unregister_module = _interrupt_raise  # type: ignore[assignment]

        def _flatten(exc: BaseException) -> list[BaseException]:
            if isinstance(exc, ExceptionGroup):
                flattened: list[BaseException] = []
                for sub in exc.exceptions:
                    flattened.extend(_flatten(sub))
                return flattened
            return [exc]

        with pytest.raises(ExceptionGroup) as exc_info:
            await sched.unregister_module(MagicMock())

        raised = exc_info.value
        # Final ExceptionGroup must contain every contained exception from all
        # three components, flattened.
        contained = _flatten(raised)
        expected = [
            ValueError("timer-1"),
            KeyError("idle-1"),
            KeyError("idle-2"),
            RuntimeError("interrupt-1"),
        ]
        assert len(contained) == len(expected)
        for got, want in zip(contained, expected, strict=True):
            assert type(got) is type(want)
            assert got.args == want.args

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
