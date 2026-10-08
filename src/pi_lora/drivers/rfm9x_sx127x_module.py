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

"""RFM9x/SX127x module state management context.

Provides `Rfm9xSx127xModule` as a stateful wrapper that manages transitions
between concrete ``Rfm9xSx127xMode`` subclasses (sleep, standby, FSTX, etc.)
using a shared ``state_instances`` dictionary to avoid redundant object creation.
"""


import asyncio
import logging
from collections import defaultdict, deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

from .rfm9x_sx127x_handler import FrequencyCalculationConfig, Rfm9xSx127xHandler
from .rfm9x_sx127x_modes import Rfm9xSx127xMode, StateBitsMapping
from .rfm9x_sx127x_radio_instance import RadioInstanceConfig
from .spi.bus import SpiBus
from .spi.factory import SpiBusFactory
from ..framework.events import EventType, ModuleEvent, StopMode, is_state_change_event
from ..types import LoraMode, ModeBits, StateBits

logger = logging.getLogger(__name__)


@dataclass
class _EventWaiter:
    predicate: Callable[[ModuleEvent[Any]], bool]
    event: asyncio.Event
    result: ModuleEvent[Any] | None = None


class Rfm9xSx127xModule:
    """State management context for a RFM9x/SX127x radio module.

    Stores one active ``Rfm9xSx127xMode`` instance in ``current_state_instance``
    and a cache of every known state in ``state_instances`` keyed by the concrete
    class type.
    """

    def __init__(
        self,
        radio_config: RadioInstanceConfig,
        state: StateBits,
        spi_factory: SpiBusFactory | None = None,
    ) -> None:
        self.radio_config: RadioInstanceConfig = radio_config
        self.spi_device_id: int = radio_config.spi_device_id
        self.ce_number: int = radio_config.ce_number
        self._spi_factory: SpiBusFactory | None = spi_factory
        self.spi_bus: SpiBus | None = None
        self.current_state_instance: Rfm9xSx127xMode|None = self._create_state_instance(state)
        self.state_instances: dict[type[Rfm9xSx127xMode], Rfm9xSx127xMode] = (
            self._create_instances()
        )

        # Event loop infrastructure
        self.event_queue: asyncio.Queue[ModuleEvent[Any]] = asyncio.Queue()
        self.event_loop_task: asyncio.Task[None] | None = None
        self._stop_mode: StopMode = StopMode.DRAIN
        self._paused: bool = False
        self._event_buffer: dict[EventType, deque[ModuleEvent[Any]]] = defaultdict(
            lambda: deque(maxlen=1000)
        )
        self._event_waiters: dict[EventType, list[_EventWaiter]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _create_state_instance(state: StateBits) -> Rfm9xSx127xMode:
        """Map a ``StateBits`` enum to its corresponding mode class and instantiate it."""
        mode_class: type[Rfm9xSx127xMode] = StateBitsMapping.from_bits(state).value
        return mode_class()

    def _create_instances(self) -> dict[type[Rfm9xSx127xMode], Rfm9xSx127xMode]:
        """Build and return the ``state_instances`` cache for every known ``StateBits``."""
        instances: dict[type[Rfm9xSx127xMode], Rfm9xSx127xMode] = {}
        for state_bit in set(StateBits):
            mode_instance = self._create_state_instance(state_bit)
            instances[type(mode_instance)] = mode_instance
        return instances

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def init_spi_bus(self) -> None:
        """Open the SPI bus using the injected factory."""
        if self._spi_factory is None:
            return
        self.spi_bus = self._spi_factory.create(
            bus=self.spi_device_id, device=self.ce_number
        )
        self.spi_bus.open(self.spi_device_id, self.ce_number)

    async def close_spi(self) -> None:
        """Close the SPI bus if one is open."""
        if self.spi_bus is not None:
            self.spi_bus.close()
            self.spi_bus = None

    def set_current_state(self, state: StateBits) -> None:
        """Transition the module to *state*, firing ``on_exit``/``on_entry`` hooks."""
        if self.current_state_instance is not None:
            current_cls = type(self.current_state_instance)
            cached = self.state_instances.get(current_cls)
            if cached is not None and isinstance(cached, Rfm9xSx127xMode):
                cached.on_exit(self)

        new_instance = self.state_instances.get(StateBitsMapping.from_bits(state).value)
        if new_instance is None:
            new_instance = self._create_state_instance(state)
            self.state_instances[type(new_instance)] = new_instance

        self.current_state_instance = new_instance
        self.current_state_instance.on_entry(self)

    def is_in_state(self, state: StateBits) -> bool:
        """Return ``True`` when the current active instance matches *state*."""
        expected_cls = StateBitsMapping.from_bits(state).value
        if expected_cls is None:
            return False
        return type(self.current_state_instance) is expected_cls

    def is_in_lora_mode(self) -> bool:
        """Return ``True`` when the current state's ``LORA_MODE`` is ``LoraMode.LORA``."""
        if self.current_state_instance is not None:
            lora_mode = type(self.current_state_instance).LORA_MODE
            return lora_mode == LoraMode.LORA
        else:
            return False

    def is_in_fsk_ook_mode(self) -> bool:
        """Return ``True`` when the module is **not** in LoRa mode."""
        return not self.is_in_lora_mode()

    async def write_and_verify_frequency_for_khz(self, frequency_khz: int) -> bool:
        """Guard method: only allows frequency write in SLEEP or STANDBY state."""
        if self.current_state_instance is not None:
            mode_bits = type(self.current_state_instance).MODE_BITS
            if mode_bits in (ModeBits.SLEEP_OR_ERROR_OR_NOT_A_DEVICE_OR_UNKNOWN_OR_RESET, ModeBits.STANDBY):
                freq_config = FrequencyCalculationConfig(
                    osc_freq_hz=self.radio_config.osc_freq_hz
                )
                success, *_ = await Rfm9xSx127xHandler.write_and_verify_frequency_for_khz(
                    self, freq_config, frequency_khz
                )
                return success
        raise RuntimeError("Frequency write only allowed in SLEEP or STANDBY mode")

    # Encapsulation getters (for Application.get_status())
    def get_current_state_name(self) -> str:
        if self.current_state_instance is not None:
            return type(self.current_state_instance).__name__
        return "None"

    def get_event_queue_size(self) -> int:
        return self.event_queue.qsize()

    def get_spi_device_id(self) -> int:
        """Return the SPI device ID (always ``int``, never ``None``)."""
        return self.radio_config.spi_device_id

    def get_ce_number(self) -> int:
        """Return the CE number (always ``int``, never ``None``)."""
        return self.radio_config.ce_number

    # Event loop control
    async def start_event_loop(self) -> None:
        self._paused = False
        if self.event_loop_task is None or self.event_loop_task.done():
            self.event_loop_task = asyncio.create_task(self._event_loop())
        # If paused, just resume; queue kept and accepting new events

    async def stop_event_loop(self, mode: StopMode = StopMode.DRAIN) -> None:
        self._stop_mode = mode
        if mode == StopMode.PAUSE:
            self._paused = True
            return  # Keep task running but stop dispatching

        if self.event_loop_task and not self.event_loop_task.done():
            self.event_loop_task.cancel()
            if mode == StopMode.DRAIN:
                # Wait for task to finish draining
                with suppress(asyncio.CancelledError):
                    await self.event_loop_task
            elif mode == StopMode.CANCEL_ALL:
                # Drain queue without processing
                while not self.event_queue.empty():
                    try:
                        self.event_queue.get_nowait()
                    except Exception:
                        break
                with suppress(asyncio.CancelledError):
                    await self.event_loop_task

    async def _event_loop(self) -> None:
        try:
            while True:
                if self._paused:
                    await asyncio.sleep(0.01)  # Brief sleep while paused
                    continue
                event = await self.event_queue.get()

                # Buffer all events for waiters (never lose events even if dispatch fails)
                self._event_buffer[event.event_type].append(event)

                # Notify waiters atomically (before dispatch so waiters get the event)
                for waiter in self._event_waiters[event.event_type]:
                    if waiter.predicate(event) and waiter.result is None:
                        waiter.result = event
                        waiter.event.set()

                # THEN dispatch — exceptions here don't affect buffering/waiters
                try:
                    # Intercept STATE_CHANGE at module level
                    if event.event_type == EventType.STATE_CHANGE and is_state_change_event(event):
                        new_state: StateBits = event.payload.new_state if event.payload is not None else StateBits.UNDEFINED_STATE
                        self.set_current_state(new_state)

                    if self.current_state_instance is not None:
                        await self.current_state_instance.on_event(event, self)
                except Exception:
                    logger.exception(
                        "Event dispatch failed for event_type=%s; continuing loop",
                        event.event_type,
                    )
                    continue
        except asyncio.CancelledError:
            if self._stop_mode == StopMode.DRAIN:
                while not self.event_queue.empty():
                    try:
                        ev = self.event_queue.get_nowait()
                        if self.current_state_instance is not None:
                            await self.current_state_instance.on_event(ev, self)
                    except Exception:
                        break
            raise

    async def wait_for_event(
        self,
        event_type: EventType,
        predicate: Callable[[ModuleEvent[Any]], bool] | None = None,
        timeout: float = 5.0,
    ) -> ModuleEvent[Any] | None:
        """Wait for an event matching predicate, with timeout. Replays already-buffered events."""
        check_pred = predicate or (lambda _: True)

        # Replay check: return buffered events that already match (race-free: nothing else runs between check and registration)
        buffered = self._event_buffer.get(event_type)
        if buffered is not None:
            events: list[ModuleEvent[Any]] = list(buffered)
            for ev in reversed(events):
                if check_pred(ev):
                    found: ModuleEvent[Any] = ev
                    return found

        # No match yet — register and wait
        waiter = _EventWaiter(
            predicate=check_pred,
            event=asyncio.Event(),
        )
        self._event_waiters[event_type].append(waiter)

        try:
            try:
                await asyncio.wait_for(waiter.event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                return None
            return waiter.result
        finally:
            # Clean up waiter from registry to prevent memory leak
            with suppress(ValueError):
                self._event_waiters[event_type].remove(waiter)

    def drain_events(self, event_type: EventType) -> list[ModuleEvent[Any]]:
        """Return and clear all buffered events of the given type."""
        buffer = self._event_buffer.get(event_type)
        if not buffer:
            return []
        events = list(buffer)
        buffer.clear()
        return events

    def get_event_history(self, event_type: EventType, limit: int | None = None) -> list[ModuleEvent[Any]]:
        """Return a copy of recent events of the given type, up to limit."""
        buffer = self._event_buffer.get(event_type)
        if not buffer:
            return []
        if limit is None or limit >= len(buffer):
            return list(buffer)
        if limit <= 0:
            return []
        return list(buffer)[-limit:]

    def get_last_event(self, event_type: EventType) -> ModuleEvent[Any] | None:
        """Return the most recent event of the given type, or None if empty."""
        buffer = self._event_buffer.get(event_type)
        return buffer[-1] if buffer else None
