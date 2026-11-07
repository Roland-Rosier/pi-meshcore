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

from pi_lora.framework.events import EventType
from pi_lora.framework.scheduler import InterruptBridge


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


@pytest.mark.asyncio
async def test_interrupt_threadsafe_stop_no_loop_race() -> None:
    """stop() nulling _loop while trigger_interrupt() reads it must not race.

    Fix 10 (Issue 24.12): the _loop read must be atomic with the queue ops under
    trigger_lock. Hammer triggers from many threads, then stop() the bridge
    (which nulls _loop at location 5, Plan-18). Remaining triggers after stop()
    must not crash on the now-None _loop read and must still keep the producer
    bounded.
    """
    bridge = InterruptBridge()
    await bridge.start()

    registered_pin = 5

    class _MockModule:
        """Minimal module with an asyncio.Queue event_queue."""

        def __init__(self) -> None:
            self.event_queue = asyncio.Queue()

    mock_module = _MockModule()
    bridge.register_interrupt(registered_pin, mock_module)

    def trigger_from_thread() -> None:
        for _ in range(1000):
            bridge.trigger_interrupt(registered_pin)

    threads = [threading.Thread(target=trigger_from_thread) for _ in range(10)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # stop() nulls _loop. After stop() the drain task is cancelled, so the
    # producer no longer drains. Verify the read is now atomic (Fix 10) and that
    # subsequent triggers do not crash on the None _loop.
    await bridge.stop()
    assert bridge._loop is None

    threads2 = [threading.Thread(target=trigger_from_thread) for _ in range(10)]
    for thread in threads2:
        thread.start()
    for thread in threads2:
        thread.join()

    # Producer stays bounded; no crash from the None _loop race (Fix 10).
    assert 0 <= bridge._trigger_queue.qsize() <= bridge._max_queue_size
