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

"""Asyncio framework event types and payloads for Rfm9xSx127xModule instances."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class EventType(Enum):
    """Types of events that can be posted to a module's event queue."""

    TIMER = "timer"
    IDLE = "idle"
    INTERRUPT = "interrupt"
    COMMAND = "command"
    STATE_CHANGE = "state_change"


class StopMode(Enum):
    """Cancellation modes for stopping an event loop."""

    DRAIN = "drain"
    CANCEL_ALL = "cancel_all"
    PAUSE = "pause"


@dataclass(frozen=True)
class ModuleEvent:
    """Base event posted to module event queues."""

    event_type: EventType
    payload: Any = None
    timestamp: float = 0.0
    source: str = ""


@dataclass(frozen=True)
class TimerEvent:
    """Payload for TIMER events."""

    interval_seconds: float


@dataclass(frozen=True)
class InterruptEvent:
    """Payload for INTERRUPT events."""

    gpio_pin: int


@dataclass(frozen=True)
class CommandEvent:
    """Payload for COMMAND events."""

    command: Any


@dataclass(frozen=True)
class StateChangeEvent:
    """Payload for STATE_CHANGE events."""

    new_state: Any
    reason: str = ""


class EventHandler(Protocol):
    """Protocol for objects that handle ModuleEvent instances."""

    async def on_event(self, event: ModuleEvent) -> None: ...
