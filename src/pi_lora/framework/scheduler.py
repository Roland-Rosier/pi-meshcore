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

"""Scheduler components for Rfm9xSx127xModule event dispatch."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

from .events import EventType, InterruptEvent, ModuleEvent, TimerEvent


class SchedulerRegistration(Protocol):
    """Sync-compatible protocol for state registration in on_entry/on_exit."""

    def set_timer_interval(
        self, module: Rfm9xSx127xModule, interval_seconds: float | None
    ) -> None: ...

    def set_idle_enabled(self, module: Rfm9xSx127xModule, enabled: bool) -> None: ...

    def get_timer_interval(self, module: Rfm9xSx127xModule) -> float | None: ...


class TimerScheduler:
    """One async task per module that posts TIMER events at intervals."""

    def __init__(self, default_interval: float = 1.0) -> None:
        self._validate_interval(default_interval)
        self._default_interval = default_interval
        self._intervals: dict[Rfm9xSx127xModule, float] = {}
        self._failure_counts: dict[Rfm9xSx127xModule, int] = {}
        self._last_failure_log: dict[Rfm9xSx127xModule, float] = {}
        self._tasks: dict[Rfm9xSx127xModule, asyncio.Task[None]] = {}
        self._registered: set[Rfm9xSx127xModule] = set()
        self._running = False

    @staticmethod
    def _validate_interval(interval: float | None) -> None:
        if interval is not None and interval <= 0:
            raise ValueError(f"Timer interval must be positive, got {interval}")

    def set_interval(self, module: Rfm9xSx127xModule, interval: float | None) -> None:
        self._validate_interval(interval)
        if interval is None:
            self._intervals.pop(module, None)
        else:
            self._intervals[module] = interval

    def get_interval(self, module: Rfm9xSx127xModule) -> float | None:
        return self._intervals.get(module, None)

    async def start(self) -> None:
        self._running = True
        for module in list(self._registered):
            if module not in self._tasks:
                self._tasks[module] = asyncio.create_task(self._timer_task(module))

    async def stop(self) -> None:
        self._running = False
        tasks = list(self._tasks.values())
        self._tasks.clear()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def unregister_module(self, module: Rfm9xSx127xModule) -> None:
        self._registered.discard(module)
        self._intervals.pop(module, None)
        task = self._tasks.pop(module, None)
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)  # Await cancellation

    def register_module(
        self, module: Rfm9xSx127xModule, interval: float | None
    ) -> None:
        self._validate_interval(interval)
        if interval is not None:
            self._intervals[module] = interval
        self._registered.add(module)
        if self._running and module not in self._tasks:
            self._tasks[module] = asyncio.create_task(self._timer_task(module))

    async def _timer_task(self, module: Rfm9xSx127xModule) -> None:
        # BUG-7 (TimerScheduler error spam loop) fixed with Option A: exponential
        # backoff. The rationale below is written inline on purpose so that any
        # future change to this loop has to re-derive the trade-off instead of
        # silently reverting the backoff and reintroducing unbounded error spam.
        #
        # * WHY unbounded error spam must be prevented. The regression that
        #   BUG-7 exists to fix logged an error on *every* iteration when
        #   ``module.event_queue.put()`` failed (queue full, module stopped, or
        #   any other ``Exception``). With the default 1s interval that is one
        #   ``logging.error`` call per second, forever, while the queue stayed
        #   full. That is an unbounded stream of identical error lines that buries
        #   the real signal and grows log volume without bound. Error spam must be
        #   bounded by construction.
        #
        # * Option A (exponential backoff, chosen). On each failure we log once,
        #   increment ``_failure_counts[module]``, and wait
        #   ``min(2 ** failure_count, 60)`` seconds before the next attempt. The
        #   interval grows 1s -> 2s -> 4s -> 8s -> ... -> 60s cap, so consecutive
        #   failures are logged logarithmically rather than linearly. A successful
        #   ``put`` resets ``_failure_counts[module]`` to 0, so the next failure
        #   starts again at ``2 ** 1``. This bounds spam: even if the queue stays
        #   full indefinitely a module logs at most ~log2(60) ~= 6 times.
        #
        # * Why not Option B (fail fast / unregister the module on repeated
        #   failures)? Option B removes the module's timer task after N
        #   consecutive failures, which hides the underlying issue: the module
        #   keeps running but its TIMER events stop being delivered, and the
        #   failure mode becomes opaque to callers. Backoff instead preserves the
        #   module's lifecycle and keeps the task alive so it resumes delivering
        #   events the moment the queue recovers. A timer scheduler must tolerate a
        #   transient QueueFull by pausing, not by dropping the module.
        while self._running:
            interval = self._intervals.get(module) or self._default_interval
            backoff_interval: float = interval or self._default_interval or 1.0
            if interval is not None:
                try:
                    await module.event_queue.put(
                        ModuleEvent(EventType.TIMER, TimerEvent(interval))
                    )
                except Exception as exc:
                    self._failure_counts[module] = (
                        self._failure_counts.get(module, 0) + 1
                    )
                    logging.getLogger(__name__).error(
                        "TimerScheduler: failed to put TIMER event for module %s: %s",
                        module,
                        exc,
                    )
                    self._last_failure_log[module] = time.monotonic()
                    backoff_interval = min(
                        2 ** self._failure_counts[module], 60
                    )
                else:
                    # Recovery: the queue accepted the event again, so drop the
                    # consecutive-failure streak and resume the normal interval.
                    self._failure_counts[module] = 0
            await asyncio.sleep(backoff_interval)


class IdlePacer:
    """Single task that paces all idle-enabled modules with IDLE events."""

    @staticmethod
    def _validate_interval(interval: float) -> None:
        if interval <= 0:
            raise ValueError(f"Idle min_interval must be positive, got {interval}")

    def __init__(self, min_interval: float = 0.01) -> None:
        self._validate_interval(min_interval)
        self._idle_enabled_modules: set[Rfm9xSx127xModule] = set()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._min_interval: float = min_interval

    def set_idle_enabled(self, module: Rfm9xSx127xModule, enabled: bool) -> None:
        if enabled:
            self._idle_enabled_modules.add(module)
        else:
            self._idle_enabled_modules.discard(module)

    async def start(self) -> None:
        self._running = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._idle_task())

    async def stop(self) -> None:
        self._running = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _idle_task(self) -> None:
        while self._running:
            await asyncio.sleep(self._min_interval)
            for module in list(self._idle_enabled_modules):
                try:
                    await module.event_queue.put(ModuleEvent(EventType.IDLE))
                except Exception as exc:
                    logging.getLogger(__name__).error(
                        "IdlePacer: failed to put IDLE event for module %s: %s",
                        module,
                        exc,
                    )


class InterruptBridge:
    """Routes GPIO interrupts to modules via an unbounded asyncio.Queue.

    BUG-6 fix (Option A): the trigger queue is intentionally *unbounded* so no
    interrupt can ever be silently dropped on QueueFull. LoRa interrupt rates are
    low (<100 Hz per channel); each entry is a small int (a GPIO pin number,
    ~28 bytes), so even a sustained 1000 Hz for one hour is ~100 MB worst case
    (extremely unlikely). The ``monitor_queue_depth_threshold`` provides an
    early-warning log when the queue depth becomes abnormal, surfacing the
    anomaly upstream as a backpressure signal for the GPIO driver rather than
    losing packet receptions.
    """

    def __init__(self, monitor_queue_depth_threshold: int = 1000) -> None:
        if monitor_queue_depth_threshold <= 0:
            raise ValueError(
                "monitor_queue_depth_threshold must be positive, "
                f"got {monitor_queue_depth_threshold}"
            )
        self._interrupt_map: dict[int, Rfm9xSx127xModule] = {}
        self._monitor_queue_depth_threshold = monitor_queue_depth_threshold
        # Unbounded queue: asyncio.Queue() with no maxsize (BUG-6, Option A).
        self._trigger_queue: asyncio.Queue[int] = asyncio.Queue()
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register_interrupt(self, gpio_pin: int, module: Rfm9xSx127xModule) -> None:
        if gpio_pin in self._interrupt_map:
            logging.getLogger(__name__).warning(
                "Duplicate GPIO pin %d already mapped to a module; "
                "this registration overwrites the previous mapping.",
                gpio_pin,
            )
        self._interrupt_map[gpio_pin] = module
        # Task is created in start() only.

    def trigger_interrupt(self, gpio_pin: int) -> None:
        """Called by GPIO driver when interrupt fires (sync context).

        BUG-6 fix (Option A): the trigger queue is unbounded, so put_nowait never
        raises asyncio.QueueFull and no interrupt can be silently dropped. This is
        safe because LoRa interrupt rates are low (<100 Hz per channel) and each
        entry is a small int (a GPIO pin number, ~28 bytes). The
        ``monitor_queue_depth_threshold`` fires an early-warning log when the queue
        depth becomes abnormal, giving the GPIO driver a backpressure signal to
        surface the anomaly upstream rather than losing packet receptions.
        """
        self._trigger_queue.put_nowait(gpio_pin)
        if self._trigger_queue.qsize() >= self._monitor_queue_depth_threshold:
            logging.getLogger(__name__).warning(
                "Interrupt queue depth %d reached monitoring threshold %d; "
                "abnormal interrupt rate detected (GPIO %d).",
                self._trigger_queue.qsize(),
                self._monitor_queue_depth_threshold,
                gpio_pin,
            )

    async def start(self) -> None:
        self._running = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._interrupt_task())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _interrupt_task(self) -> None:
        while self._running:
            gpio_pin = await self._trigger_queue.get()
            module = self._interrupt_map.get(gpio_pin)
            if module is None:
                logging.getLogger(__name__).warning(
                    "Unknown GPIO pin %d has no registered module; interrupt ignored.",
                    gpio_pin,
                )
            else:
                try:
                    await module.event_queue.put(
                        ModuleEvent(EventType.INTERRUPT, InterruptEvent(gpio_pin))
                    )
                except Exception as exc:
                    logging.getLogger(__name__).error(
                        "InterruptBridge: failed to put INTERRUPT event for GPIO %d: %s",
                        gpio_pin,
                        exc,
                    )

    def unregister_module(self, module: Rfm9xSx127xModule) -> None:
        """Remove every GPIO pin entry that references *module*."""
        for gpio_pin, m in list(self._interrupt_map.items()):
            if m is module:
                del self._interrupt_map[gpio_pin]


class Scheduler:
    """Composes TimerScheduler, IdlePacer, and InterruptBridge."""

    def __init__(self, default_timer_interval: float = 1.0) -> None:
        self.timer_scheduler = TimerScheduler(default_interval=default_timer_interval)
        self.idle_pacer = IdlePacer()
        self.interrupt_bridge = InterruptBridge()

    async def start(self) -> None:
        await self.timer_scheduler.start()
        await self.idle_pacer.start()
        await self.interrupt_bridge.start()

    async def stop(self) -> None:
        await self.interrupt_bridge.stop()
        await self.idle_pacer.stop()
        await self.timer_scheduler.stop()

    async def unregister_module(self, module: Rfm9xSx127xModule) -> None:
        await self.timer_scheduler.unregister_module(module)
        self.idle_pacer.set_idle_enabled(module, False)
        self.interrupt_bridge.unregister_module(module)

    def register_module(
        self,
        module: Rfm9xSx127xModule,
        timer_interval: float | None = None,
        idle_enabled: bool = True,
        interrupt_gpio_pins: list[int] | None = None,
    ) -> None:
        self.timer_scheduler.register_module(module, timer_interval)
        self.idle_pacer.set_idle_enabled(module, idle_enabled)
        if interrupt_gpio_pins:
            for gpio_pin in interrupt_gpio_pins:
                self.interrupt_bridge.register_interrupt(gpio_pin, module)

    # SchedulerRegistration protocol implementation
    def set_timer_interval(
        self, module: Rfm9xSx127xModule, interval_seconds: float | None
    ) -> None:
        self.timer_scheduler.set_interval(module, interval_seconds)

    def set_idle_enabled(self, module: Rfm9xSx127xModule, enabled: bool) -> None:
        self.idle_pacer.set_idle_enabled(module, enabled)

    def get_timer_interval(self, module: Rfm9xSx127xModule) -> float | None:
        return self.timer_scheduler.get_interval(module)
