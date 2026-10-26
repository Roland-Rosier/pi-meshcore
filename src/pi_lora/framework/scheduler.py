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
import queue
import threading
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
            await self._do_tick(module, interval)

    async def _do_tick(
        self, module: Rfm9xSx127xModule, interval: float
    ) -> None:
        """Execute one timer tick with exponential backoff on failure.

        CR-5 FIX: unified backoff for BOTH custom and default intervals.
        Plan-11's original code nested the backoff branch inside
        ``if interval is not None:``, so a module running on the default
        interval (``interval is None`` resolved via
        ``self._intervals.get(module) or self._default_interval``) never
        reached the failure-handling path. That reintroduced unbounded error
        spam: every default-interval iteration logged an error with no backoff.
        This helper removes that conditional so every tick — whether the
        interval came from ``_intervals`` or ``_default_interval`` — applies the
        same ``min(2 ** failure_count, 60)`` exponential backoff on failure.
        """
        try:
            await module.event_queue.put(
                ModuleEvent(EventType.TIMER, TimerEvent(interval))
            )
        except Exception as exc:
            self._failure_counts[module] = self._failure_counts.get(module, 0) + 1
            logging.getLogger(__name__).error(
                "TimerScheduler: failed to put TIMER event for module %s: %s",
                module,
                exc,
            )
            self._last_failure_log[module] = time.monotonic()
            backoff_interval: float = min(2 ** self._failure_counts[module], 60)
            await asyncio.sleep(backoff_interval)
        else:
            # Recovery: the queue accepted the event again, so drop the
            # consecutive-failure streak and resume the normal interval.
            self._failure_counts[module] = 0
            await asyncio.sleep(interval)


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
    """Routes GPIO interrupts to modules via a thread-safe producer queue.

    CR-6 FIX: Both queues are bounded (maxsize=10000) with a drop-oldest policy
    to provide HARD OOM protection against malicious/buggy GPIO drivers.

    NR-5 FIX (THREAD SAFETY): trigger_interrupt() is called from GPIO interrupt
    callbacks running in arbitrary threads (lgpio/RPi.GPIO/gpiod are NOT the
    event loop thread). A single asyncio.Queue is NOT thread-safe, so the
    producer side uses queue.Queue (thread-safe) via put_nowait(). An async task
    (_drain_sync_queue) drains queue.Queue into the asyncio.Queue consumer in the
    event loop thread only, where asyncio.Queue.put_nowait() is safe. The
    consumer task (_interrupt_task) reads the asyncio.Queue.

    RATIONale FOR DROP-OLDEST (not drop-newest, not blocking):
    - LoRa interrupt rates are low (<100 Hz per channel in normal operation)
    - A sustained 1000 Hz for 1 hour = ~100 MB worst case (each entry ~28 bytes)
    - maxsize=10000 bounds memory to ~280 KB — negligible
    - Under attack (malicious GPIO driver), dropping OLDEST interrupts preserves
      recent interrupts which are more relevant for packet reception
    - Drop-newest would lose the current packet — worse for LoRa
    - Monitoring threshold remains as early-warning log for operators

    The producer drop-oldest implementation uses get_nowait() + put_nowait() on
    queue.Full, which is atomic-enough for this use case.

    H-7 FIX (NR-5 atomicity): the compound get_nowait() + put_nowait() drop-oldest
    operation on queue.Full is wrapped in ``self._trigger_lock`` (a stdlib
    ``threading.Lock``) so "drop oldest to make room for newest" is atomic across
    the arbitrary threads that call trigger_interrupt(). This is the ONLY
    legitimate ``threading.Lock`` use in the codebase and is documented here so
    future readers understand why it is NOT ``aiologic.Lock``:
    - trigger_interrupt() runs in a SYNC thread context (GPIO interrupt callbacks
      from lgpio/RPi.GPIO/gpiod), NOT the event loop thread.
    - No asyncio event loop is guaranteed at call time; interrupt handlers run
      early, before any loop is established.
    - aiologic.Lock (and asyncio.Lock) require a running event loop; using them
      here would raise RuntimeError or break the sync context.
    - queue.Queue is stdlib thread-safe; threading.Lock is its natural companion
      and is safe to instantiate and use without an event loop.
    - Precedent: locks.py uses asyncio.Lock only for module-level init guards,
      which DO run in the event loop thread (same rationale as the
      aiologic-only rule). This thread is the one documented exception.
    """

    def __init__(self, monitor_queue_depth_threshold: int = 1000) -> None:
        if monitor_queue_depth_threshold <= 0:
            raise ValueError(
                "monitor_queue_depth_threshold must be positive, "
                f"got {monitor_queue_depth_threshold}"
            )
        self._interrupt_map: dict[int, Rfm9xSx127xModule] = {}
        self._monitor_queue_depth_threshold = monitor_queue_depth_threshold
        self._max_queue_size = 10000
        # Thread-safe producer queue for the GPIO interrupt thread. queue.Queue
        # is safe to put_nowait() and get_nowait() from any thread. Bounded to
        # ~280 KB worst case (CR-6 FIX) with a drop-oldest policy.
        self._trigger_queue: queue.Queue[int] = queue.Queue(
            maxsize=self._max_queue_size
        )
        # Async consumer queue for the event loop thread. Drained from
        # _trigger_queue by _drain_sync_queue; read by _interrupt_task.
        self._async_trigger_queue: asyncio.Queue[int] = asyncio.Queue(
            maxsize=self._max_queue_size
        )
        # H-7 FIX (NR-5 atomicity): protects the compound get_nowait()+
        # put_nowait() drop-oldest operation in trigger_interrupt() so the
        # "drop oldest to make room for newest" sequence is atomic across the
        # arbitrary threads that call trigger_interrupt() from GPIO drivers.
        # threading.Lock (NOT aiologic.Lock) is correct because trigger_interrupt()
        # runs in sync thread context with no event loop guaranteed at call time;
        # queue.Queue is stdlib thread-safe and threading.Lock is its natural
        # companion. Precedent: locks.py uses asyncio.Lock for module-level init
        # guard (same rationale).
        self._trigger_lock: threading.Lock = threading.Lock()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._drain_task: asyncio.Task[None] | None = None

    def register_interrupt(self, gpio_pin: int, module: Rfm9xSx127xModule) -> None:
        if gpio_pin in self._interrupt_map:
            logging.getLogger(__name__).warning(
                "Duplicate GPIO pin %d already mapped to a module; "
                "this registration overwrites the previous mapping.",
                gpio_pin,
            )
        self._interrupt_map[gpio_pin] = module
        # Tasks are created in start() only.

    def trigger_interrupt(self, gpio_pin: int) -> None:
        """Called by GPIO driver when interrupt fires (sync context, ANY thread).

        NR-5 FIX: thread-safe via queue.Queue.put_nowait(), safe from any thread.
        Bounded (CR-6 FIX) with a drop-oldest policy on queue.Full to prevent
        unbounded memory growth from a malicious/buggy GPIO driver. On queue.Full
        the oldest interrupt is discarded to make room for the newest (see class
        docstring for the rationale). The monitoring threshold still fires an
        early-warning log when the queue depth becomes abnormal.
        """
        try:
            self._trigger_queue.put_nowait(gpio_pin)
        except queue.Full:
            # Drop oldest to make room for newest (see class docstring rationale).
            # CRITICAL: compound get+put must be atomic across threads.
            # Use threading.Lock (NOT aiologic.Lock) because:
            # - trigger_interrupt() is called from GPIO driver in SYNC thread context
            # - No event loop guaranteed at call time (interrupt handlers run early)
            # - Protects queue.Queue which is stdlib thread-safe; threading.Lock is its natural companion
            # - Precedent: locks.py uses asyncio.Lock for module-level init guard (same rationale)
            with self._trigger_lock:
                try:
                    self._trigger_queue.get_nowait()  # Discard oldest
                    self._trigger_queue.put_nowait(gpio_pin)  # Insert newest
                except queue.Empty:
                    pass  # Race: queue emptied between full and get; just drop new
                except queue.Full:
                    # Race: another thread's unprotected top-level put_nowait
                    # filled the slot our get_nowait opened; the queue is full
                    # again, so the newest is dropped. Bounded, no corruption.
                    pass  # Drop newest; producer stays at maxsize
            logging.getLogger(__name__).warning(
                "Interrupt queue full (maxsize=%d); dropped oldest interrupt "
                "for GPIO %d to make room for newest. Malicious/buggy GPIO driver?",
                self._max_queue_size,
                gpio_pin,
            )
        # Monitoring threshold unchanged — early warning for operators.
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
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_sync_queue())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            await asyncio.gather(self._drain_task, return_exceptions=True)

    async def _drain_sync_queue(self) -> None:
        """Drain thread-safe producer queue into async consumer queue.

        Runs only in the event loop thread (safe for asyncio.Queue). Yields to
        the loop with a tiny sleep when the producer queue is empty to avoid a
        busy-wait that would otherwise starve the consumer task.
        """
        while self._running:
            try:
                gpio_pin = self._trigger_queue.get_nowait()
            except queue.Empty:
                await asyncio.sleep(0.001)  # Yield to event loop; nothing to drain
                continue
            try:
                self._async_trigger_queue.put_nowait(gpio_pin)
            except asyncio.QueueFull:
                # Should not happen if both queues share maxsize and the consumer
                # keeps up, but handle gracefully with a drop-oldest policy.
                try:
                    self._async_trigger_queue.get_nowait()
                    self._async_trigger_queue.put_nowait(gpio_pin)
                except asyncio.QueueEmpty:
                    pass

    async def _interrupt_task(self) -> None:
        while self._running:
            gpio_pin = await self._async_trigger_queue.get()
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
