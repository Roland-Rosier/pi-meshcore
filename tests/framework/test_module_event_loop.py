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
from unittest.mock import AsyncMock

import pytest
from src.pi_lora.drivers.rfm9x_sx127x_modes import StateBits
from src.pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule
from src.pi_lora.framework.events import EventType, ModuleEvent, StopMode


@pytest.fixture
def module() -> Rfm9xSx127xModule:
    """Create a fresh Rfm9xSx127xModule instance."""
    return Rfm9xSx127xModule(state=StateBits.UNKNOWN_STATE)


@pytest.fixture
def mock_state(module: Rfm9xSx127xModule) -> AsyncMock:
    """Replace current_state_instance with an AsyncMock."""
    mock = AsyncMock()
    module.current_state_instance = mock
    return mock


class TestEventLoopStartStop:
    """Verify event loop start/stop behavior."""

    def test_start_event_loop_creates_task(self, module: Rfm9xSx127xModule) -> None:
        asyncio.run(module.start_event_loop())
        assert module.event_loop_task is not None

    @pytest.mark.asyncio
    async def test_stop_drain_cancels_task(
        self, module: Rfm9xSx127xModule, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.DRAIN)
        assert module.event_loop_task.done()

    @pytest.mark.asyncio
    async def test_stop_cancel_all_cancels_task(
        self, module: Rfm9xSx127xModule, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.CANCEL_ALL)
        assert module.event_loop_task.done()

    @pytest.mark.asyncio
    async def test_stop_pause_sets_paused(
        self, module: Rfm9xSx127xModule
    ) -> None:
        await module.start_event_loop()
        await module.stop_event_loop(StopMode.PAUSE)
        assert module._paused is True


class TestEventQueueProcessing:
    """Verify events are posted and processed sequentially."""

    @pytest.mark.asyncio
    async def test_process_single_event(
        self, module: Rfm9xSx127xModule, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        # Let the loop process it
        await asyncio.sleep(0.1)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        mock_state.on_event.assert_called_once_with(event)

    @pytest.mark.asyncio
    async def test_process_multiple_events_sequentially(
        self, module: Rfm9xSx127xModule, mock_state: AsyncMock
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

    def test_empty_queue(self, module: Rfm9xSx127xModule) -> None:
        assert module.get_event_queue_size() == 0

    @pytest.mark.asyncio
    async def test_nonempty_queue(self, module: Rfm9xSx127xModule) -> None:
        await module.event_queue.put(ModuleEvent(event_type=EventType.TIMER))
        await module.event_queue.put(ModuleEvent(event_type=EventType.IDLE))
        assert module.get_event_queue_size() == 2


class TestIdentitySetters:
    """Verify identity setters work correctly."""

    def test_set_spi_device_id(self, module: Rfm9xSx127xModule) -> None:
        module.set_spi_device_id(1)
        assert module.get_spi_device_id() == 1

    def test_set_ce_number(self, module: Rfm9xSx127xModule) -> None:
        module.set_ce_number(0)
        assert module.get_ce_number() == 0


class TestPauseResume:
    """Verify pause/resume preserves queue."""

    @pytest.mark.asyncio
    async def test_pause_preserves_queue(
        self, module: Rfm9xSx127xModule
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        await module.stop_event_loop(StopMode.PAUSE)
        assert module._paused is True
        assert module.get_event_queue_size() == 1

    @pytest.mark.asyncio
    async def test_resume_after_pause(
        self, module: Rfm9xSx127xModule, mock_state: AsyncMock
    ) -> None:
        await module.start_event_loop()
        event = ModuleEvent(event_type=EventType.TIMER)
        await module.event_queue.put(event)

        await module.stop_event_loop(StopMode.PAUSE)
        await module.start_event_loop()  # Resume
        assert module._paused is False

        await asyncio.sleep(0.1)
        await module.stop_event_loop(StopMode.CANCEL_ALL)

        mock_state.on_event.assert_called_once_with(event)
