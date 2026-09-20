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
        self._default_interval = default_interval
        self._intervals: dict[Rfm9xSx127xModule, float] = {}
        self._tasks: dict[Rfm9xSx127xModule, asyncio.Task[None]] = {}
        self._running = False

    def set_interval(self, module: Rfm9xSx127xModule, interval: float | None) -> None:
        if interval is None:
            self._intervals.pop(module, None)
        else:
            self._intervals[module] = interval

    def get_interval(self, module: Rfm9xSx127xModule) -> float | None:
        return self._intervals.get(module, None)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks.values():
            task.cancel()
        self._tasks.clear()

    def register_module(
        self, module: Rfm9xSx127xModule, interval: float | None
    ) -> None:
        if interval is not None:
            self._intervals[module] = interval
        if module not in self._tasks:
            self._tasks[module] = asyncio.create_task(self._timer_task(module))

    async def _timer_task(self, module: Rfm9xSx127xModule) -> None:
        while self._running:
            interval = self._intervals.get(module) or self._default_interval
            if interval is not None:
                await module.event_queue.put(
                    ModuleEvent(EventType.TIMER, TimerEvent(interval))
                )
            await asyncio.sleep(interval or self._default_interval or 1.0)


class IdlePacer:
    """Single task that paces all idle-enabled modules with IDLE events."""

    def __init__(self) -> None:
        self._idle_enabled_modules: set[Rfm9xSx127xModule] = set()
        self._running = False
        self._task: asyncio.Task[None] | None = None

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
        if self._task and not self._task.done():
            self._task.cancel()

    async def _idle_task(self) -> None:
        while self._running:
            await asyncio.sleep(0)
            for module in self._idle_enabled_modules:
                await module.event_queue.put(ModuleEvent(EventType.IDLE))


class InterruptBridge:
    """Single asyncio.Event with GPIO→module mapping."""

    def __init__(self) -> None:
        self._interrupt_map: dict[int, Rfm9xSx127xModule] = {}
        self._interrupt_event: asyncio.Event | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register_interrupt(self, gpio_pin: int, module: Rfm9xSx127xModule) -> None:
        self._interrupt_map[gpio_pin] = module
        if self._interrupt_event is None:
            self._interrupt_event = asyncio.Event()
            self._task = asyncio.create_task(self._interrupt_task())

    async def start(self) -> None:
        self._running = True
        if self._interrupt_event is None:
            self._interrupt_event = asyncio.Event()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._interrupt_task())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _interrupt_task(self) -> None:
        while self._running:
            if self._interrupt_event is not None:
                await self._interrupt_event.wait()
                for gpio_pin, module in self._interrupt_map.items():
                    await module.event_queue.put(
                        ModuleEvent(EventType.INTERRUPT, InterruptEvent(gpio_pin))
                    )
                self._interrupt_event.clear()

    def trigger_interrupt(self, gpio_pin: int) -> None:
        """Called by GPIO driver when interrupt fires."""
        if self._interrupt_event is not None:
            self._interrupt_event.set()


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
