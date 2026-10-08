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

"""Unit tests for Rfm9xSx127xModule event loop with mock state."""

import asyncio
import importlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_modes import StateBits
from src.pi_lora.framework.events import (
    EventType,
    ModuleEvent,
    StateChangeEvent,
    StopMode,
)


def _get_module_class() -> type:
    """Lazily import Rfm9xSx127xModule to avoid circular import at module level."""
    mod = importlib.import_module("src.pi_lora.drivers.rfm9x_sx127x_module")
    return mod.Rfm9xSx127xModule


@pytest.fixture
def mock_radio_config() -> MagicMock:
    """Create a mock RadioInstanceConfig for tests."""
    config = MagicMock()
    config.spi_device_id = 0
    config.ce_number = 0
    config.osc_freq_hz = 868000000
    return config


@pytest.fixture
def module(mock_radio_config: MagicMock) -> Any:
    """Create a fresh Rfm9xSx127xModule instance."""
    Rfm9xSx127xModule = _get_module_class()
    return Rfm9xSx127xModule(radio_config=mock_radio_config, state=StateBits.UNKNOWN_STATE)


@pytest.fixture
def mock_state(module: Any) -> AsyncMock:
    """Replace current_state_instance with an AsyncMock."""
    mock = AsyncMock()
    module.current_state_instance = mock  # type: ignore[attr-defined]
    return mock


class TestEventLoopStartStop:
    """Verify event loop start/stop behavior."""

    def test_start_event_loop_creates_task(self, module: Any) -> None:
        asyncio.run(module.start_event_loop())
        assert module.event_loop_task is not None

    @pytest.mark.asyncio
    async def test_stop_drain_cancels_task(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.DRAIN)
        assert module.event_loop_task.done()

    @pytest.mark.asyncio
    async def test_stop_cancel_all_cancels_task(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.CANCEL_ALL)
        assert module.event_loop_task.done()

    @pytest.mark.asyncio
    async def test_stop_pause_sets_paused(
        self, module: Any
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.PAUSE)
        assert module._paused is True


class TestEventQueueProcessing:
    """Verify events are posted and processed sequentially."""

    @pytest.mark.asyncio
    async def test_process_single_event(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        # Let the loop process it
        await asyncio.sleep(0.1)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        mock_state.on_event.assert_called_once_with(event, module)

    @pytest.mark.asyncio
    async def test_process_multiple_events_sequentially(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        events = [
            ModuleEvent(event_type=EventType.TIMER),
            ModuleEvent(event_type=EventType.IDLE),
            ModuleEvent(event_type=EventType.INTERRUPT),
        ]
        for ev in events:
            await module.event_queue.put(ev)

        await asyncio.sleep(0.2)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        assert mock_state.on_event.call_count == len(events)


class TestQueueSizeGetter:
    """Verify get_event_queue_size returns correct count."""

    def test_empty_queue(self, module: Any) -> None:
        assert module.get_event_queue_size() == 0

    @pytest.mark.asyncio
    async def test_nonempty_queue(self, module: Any) -> None:
        await module.event_queue.put(ModuleEvent(event_type=EventType.TIMER))
        await module.event_queue.put(ModuleEvent(event_type=EventType.IDLE))
        assert module.get_event_queue_size() == 2


class TestIdentitySetters:
    """Verify identity getters return config values."""

    def test_get_spi_device_id(self, module: Any, mock_radio_config: MagicMock) -> None:
        mock_radio_config.spi_device_id = 1
        assert module.get_spi_device_id() == 1

    def test_get_ce_number(self, module: Any, mock_radio_config: MagicMock) -> None:
        mock_radio_config.ce_number = 0
        assert module.get_ce_number() == 0


class TestPauseResume:
    """Verify pause/resume preserves queue."""

    @pytest.mark.asyncio
    async def test_pause_preserves_queue(
        self, module: Any
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        await module.stop_event_loop(StopMode.PAUSE)
        assert module._paused is True
        assert module.get_event_queue_size() == 1

    @pytest.mark.asyncio
    async def test_resume_after_pause(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        await module.stop_event_loop(StopMode.PAUSE)
        await module.start_event_loop()  # Resume
        assert module._paused is False

        await asyncio.sleep(0.1)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        mock_state.on_event.assert_called_once_with(event, module)


class TestEventWaiters:
    """Verify wait_for_event predicate matching, timeout, race conditions, cleanup."""

    @pytest.mark.asyncio
    async def test_wait_for_event_matches_predicate(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        new_state = StateBits.FSK_OOK_SLEEP
        payload = ModuleEvent(
            event_type=EventType.STATE_CHANGE,
            payload=StateChangeEvent(new_state=new_state, reason="test"),
        )
        await module.event_queue.put(payload)

        def pred(ev: ModuleEvent[Any]) -> bool:
            return ev.event_type == EventType.STATE_CHANGE

        result = await module.wait_for_event(
            event_type=EventType.STATE_CHANGE, predicate=pred, timeout=1.0
        )
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        assert result is not None
        assert result.event_type == EventType.STATE_CHANGE

    @pytest.mark.asyncio
    async def test_wait_for_event_timeout(
        self, module: Any
    ) -> None:
        result = await module.wait_for_event(
            event_type=EventType.TIMER, timeout=0.05
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_wait_for_event_race_condition(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()

        async def collector(idx: int) -> ModuleEvent[Any] | None:
            ev = ModuleEvent(
                event_type=EventType.STATE_CHANGE,
                payload=StateChangeEvent(new_state=StateBits.FSK_OOK_SLEEP, reason=f"idx-{idx}"),
            )
            await module.event_queue.put(ev)
            return await module.wait_for_event(
                event_type=EventType.STATE_CHANGE, timeout=1.0
            )

        tasks = [asyncio.create_task(collector(i)) for i in range(5)]
        await asyncio.gather(*tasks)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        for res in tasks:
            assert res.result() is not None

    @pytest.mark.asyncio
    async def test_wait_for_event_waiter_cleanup(
        self, module: Any
    ) -> None:
        waiter_list = module._event_waiters.get(EventType.TIMER, [])
        assert len(waiter_list) == 0

        await module.wait_for_event(event_type=EventType.TIMER, timeout=0.05)

        waiter_list_after = module._event_waiters.get(EventType.TIMER, [])
        assert len(waiter_list_after) == 0


class TestStateTransitions:
    """Verify state transition logging and ResetState stubs."""

    def test_state_transition_logs(
        self, module: Any, capfd: pytest.CaptureFixture
    ) -> None:
        import logging
        from io import StringIO

        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.INFO)
        modes_logger = logging.getLogger("src.pi_lora.drivers.rfm9x_sx127x_modes")
        orig_level = modes_logger.level
        modes_logger.setLevel(logging.INFO)
        modes_logger.addHandler(handler)

        module.set_current_state(StateBits.FSK_OOK_SLEEP)

        output = stream.getvalue()
        modes_logger.removeHandler(handler)
        modes_logger.setLevel(orig_level)
        assert "Entering" in output or "Exiting" in output

    @pytest.mark.asyncio
    async def test_reset_state_handler_stubs(self) -> None:
        from unittest.mock import MagicMock

        from src.pi_lora.drivers.rfm9x_sx127x_modes import ResetState
        from src.pi_lora.framework.events import ModuleEvent

        rs = ResetState()
        module = MagicMock()

        # on_event is a no-op by design (event loop must survive dispatch into RESET_STATE)
        await rs.on_event(ModuleEvent(event_type=EventType.TIMER), module)

        with pytest.raises(NotImplementedError):
            await rs.on_jiffy(module)

        with pytest.raises(NotImplementedError):
            await rs.on_idle(module)

        with pytest.raises(NotImplementedError):
            await rs.on_interrupt(gpio_pin=0, module=module)


class TestEventBuffer:
    """Verify event buffer bounded capacity and reader API."""

    def test_event_buffer_bounded(self, module: Any) -> None:
        for i in range(1500):
            module._event_buffer[EventType.TIMER].append(
                ModuleEvent(event_type=EventType.TIMER, timestamp=float(i))
            )
        assert len(module._event_buffer[EventType.TIMER]) == 1000

    def test_event_buffer_reader_api(self, module: Any) -> None:
        for i in range(5):
            module._event_buffer[EventType.IDLE].append(
                ModuleEvent(event_type=EventType.IDLE, timestamp=float(i))
            )

        drained = module.drain_events(EventType.IDLE)
        assert len(drained) == 5
        assert len(module._event_buffer[EventType.IDLE]) == 0

        for i in range(3):
            module._event_buffer[EventType.COMMAND].append(
                ModuleEvent(event_type=EventType.COMMAND, timestamp=float(i))
            )

        history = module.get_event_history(EventType.COMMAND, limit=2)
        assert len(history) == 2

        last = module.get_last_event(EventType.COMMAND)
        assert last is not None
        assert last.timestamp == 2.0

        empty_last = module.get_last_event(EventType.TIMER)
        assert empty_last is None


class TestScopeLimitations:
    """Verify unimplemented event types are noops on mock state."""

    @pytest.mark.asyncio
    async def test_unimplemented_event_types_are_noops(
        self, module: Any, mock_state: AsyncMock
    ) -> None:
        initial_state = module.get_current_state_name()

        await module.start_event_loop()
        events = [
            ModuleEvent(event_type=EventType.TIMER),
            ModuleEvent(event_type=EventType.IDLE),
            ModuleEvent(event_type=EventType.INTERRUPT),
            ModuleEvent(event_type=EventType.COMMAND),
        ]
        for ev in events:
            await module.event_queue.put(ev)

        await asyncio.sleep(0.15)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        final_state = module.get_current_state_name()
        assert initial_state == final_state
