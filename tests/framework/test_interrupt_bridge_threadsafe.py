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

"""Thread-safety regression test for InterruptBridge (NR-5).

NR-5 FIX: trigger_interrupt() is called from GPIO interrupt callbacks running
in arbitrary threads (lgpio/RPi.GPIO/gpiod are not the event loop thread). The
producer side uses a thread-safe queue.Queue, so hammering it from many threads
must not corrupt it or crash. Every interrupt must ultimately be drained into
the async consumer and delivered to the registered module.
"""

import asyncio
import threading
from typing import Any

import pytest
from src.pi_lora.framework.events import EventType
from src.pi_lora.framework.scheduler import InterruptBridge


@pytest.mark.asyncio
async def test_interrupt_threadsafe_delivery() -> None:
    """trigger_interrupt() from many threads must not corrupt the queue or crash.

    Fires 10 threads x 1000 calls = 10000 interrupts for a single GPIO pin, then
    verifies the producer stays bounded and every interrupt is drained and
    delivered to the registered module's event_queue.
    """
    bridge = InterruptBridge()
    await bridge.start()

    event_queue: asyncio.Queue[Any] = asyncio.Queue()

    class _MockModule:
        """Minimal module with an asyncio.Queue event_queue."""

        def __init__(self) -> None:
            self.event_queue = event_queue

    mock_module = _MockModule()
    bridge.register_interrupt(5, mock_module)

    def trigger_from_thread() -> None:
        for _ in range(1000):
            bridge.trigger_interrupt(5)

    threads = [threading.Thread(target=trigger_from_thread) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # No crashes from concurrent producers; producer stays bounded (CR-6).
    assert bridge._trigger_queue.qsize() <= bridge._max_queue_size

    # Wait for the drain task to move every producer entry into the consumer.
    while not bridge._trigger_queue.empty():
        await asyncio.sleep(0.001)
    # Give the consumer task time to deliver every consumer entry to the module.
    await asyncio.sleep(0.2)

    interrupt_events: list[Any] = []
    while not event_queue.empty():
        event_events = await event_queue.get()
        interrupt_events.append(event_events)

    assert len(interrupt_events) == 10000, "all interrupts must be delivered"
    assert all(
        event.event_type == EventType.INTERRUPT for event in interrupt_events
    )

    await bridge.stop()
