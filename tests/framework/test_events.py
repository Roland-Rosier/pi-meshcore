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

"""Unit tests for framework event dataclasses and enums."""

import pytest
from src.pi_lora.framework.events import (
    CommandEvent,
    EventType,
    InterruptEvent,
    ModuleEvent,
    StateChangeEvent,
    StopMode,
    TimerEvent,
)


class TestEventType:
    """Verify EventType enum values."""

    def test_timer_value(self) -> None:
        assert EventType.TIMER.value == "timer"

    def test_idle_value(self) -> None:
        assert EventType.IDLE.value == "idle"

    def test_interrupt_value(self) -> None:
        assert EventType.INTERRUPT.value == "interrupt"

    def test_command_value(self) -> None:
        assert EventType.COMMAND.value == "command"

    def test_state_change_value(self) -> None:
        assert EventType.STATE_CHANGE.value == "state_change"


class TestStopMode:
    """Verify StopMode enum values."""

    def test_drain_value(self) -> None:
        assert StopMode.DRAIN.value == "drain"

    def test_cancel_all_value(self) -> None:
        assert StopMode.CANCEL_ALL.value == "cancel_all"

    def test_pause_value(self) -> None:
        assert StopMode.PAUSE.value == "pause"


class TestModuleEvent:
    """Verify ModuleEvent dataclass creation and defaults."""

    def test_creation_with_all_fields(self) -> None:
        event = ModuleEvent(
            event_type=EventType.TIMER,
            payload="test_payload",
            timestamp=1.23,
            source="test_source",
        )
        assert event.event_type == EventType.TIMER
        assert event.payload == "test_payload"
        assert event.timestamp == 1.23
        assert event.source == "test_source"

    def test_creation_with_defaults(self) -> None:
        event = ModuleEvent(event_type=EventType.IDLE)
        assert event.event_type == EventType.IDLE
        assert event.payload is None
        assert event.timestamp == 0.0
        assert event.source == ""

    def test_frozen_immutability(self) -> None:
        event = ModuleEvent(event_type=EventType.COMMAND)
        with pytest.raises(Exception):  # noqa: B017
            event.payload = "modified"


class TestTimerEvent:
    """Verify TimerEvent dataclass."""

    def test_creation(self) -> None:
        event = TimerEvent(interval_seconds=2.5)
        assert event.interval_seconds == 2.5


class TestInterruptEvent:
    """Verify InterruptEvent dataclass."""

    def test_creation(self) -> None:
        event = InterruptEvent(gpio_pin=25)
        assert event.gpio_pin == 25


class TestCommandEvent:
    """Verify CommandEvent dataclass."""

    def test_creation(self) -> None:
        cmd = {"action": "start"}
        event = CommandEvent(command=cmd)
        assert event.command == cmd


class TestStateChangeEvent:
    """Verify StateChangeEvent dataclass."""

    def test_creation_with_reason(self) -> None:
        event = StateChangeEvent(new_state="LORA", reason="transition")
        assert event.new_state == "LORA"
        assert event.reason == "transition"

    def test_creation_without_reason(self) -> None:
        event = StateChangeEvent(new_state="SLEEP")
        assert event.new_state == "SLEEP"
        assert event.reason == ""
