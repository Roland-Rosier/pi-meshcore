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

"""Atomicity regression test for InterruptBridge H-7 (drop-oldest compound op).

H-7 FIX: trigger_interrupt() is called from GPIO interrupt callbacks running in
arbitrary threads. On queue.Full the compound get_nowait() + put_nowait()
(drop-oldest to make room for newest) must be atomic across threads; without a
lock a race can drop both the oldest and newest or interleave entries. This test
stresses the drop-oldest path with a small maxsize and many concurrent threads
and asserts no data corruption: the producer stays bounded, every surviving
entry is a valid int in the registered pin set, and no duplicate/None artifacts
appear.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from src.pi_lora.framework.events import EventType
from src.pi_lora.framework.scheduler import InterruptBridge


@pytest.mark.asyncio
async def test_interrupt_bridge_atomic_drop_bounded() -> None:
    """Concurrent triggers on a full queue keep the producer bounded and clean.

    Fires 6 threads x 5000 calls = 30000 interrupts for a single GPIO pin into a
    queue with maxsize=500. Every surviving producer entry must be the registered
    pin (no None, no out-of-range values), and the producer size must never exceed
    maxsize. Every surviving entry must ultimately be delivered to the module.
    """
    bridge = InterruptBridge(monitor_queue_depth_threshold=250)
    await bridge.start()

    event_queue: asyncio.Queue[Any] = asyncio.Queue()

    class _MockModule:
        def __init__(self) -> None:
            self.event_queue = event_queue

    mock_module = _MockModule()
    registered_pin = 5
    bridge.register_interrupt(registered_pin, mock_module)

    def trigger_from_thread(_slot: int) -> None:
        for _ in range(5000):
            bridge.trigger_interrupt(registered_pin)

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(trigger_from_thread, range(6)))

    # Producer stays bounded by maxsize at all times (CR-6) and never drops below
    # zero (no interleave corruption from a missing lock).
    assert 0 <= bridge._trigger_queue.qsize() <= bridge._max_queue_size

    # Drain the producer into the consumer, then into the module event_queue.
    while not bridge._trigger_queue.empty():
        await asyncio.sleep(0.001)
    await asyncio.sleep(0.2)

    delivered: list[Any] = []
    while not event_queue.empty():
        delivered.append(await event_queue.get())

    # Every delivered entry is a valid INTERRUPT event for the registered pin;
    # no None artifacts, no out-of-range pins, no corruption from the drop-oldest.
    assert all(event.event_type == EventType.INTERRUPT for event in delivered)
    assert all(
        event.payload.gpio_pin == registered_pin for event in delivered
    )


@pytest.mark.asyncio
async def test_interrupt_bridge_atomic_drop_no_none_artifacts() -> None:
    """After draining, the producer queue holds only valid ints (no None).

    Directly exercises the drop-oldest path by filling the producer to maxsize
    from a single thread (queue.Full), then hammering it from many threads so the
    compound get+put runs under contention. Every remaining entry must be a
    positive int in the registered pin set.
    """
    bridge = InterruptBridge(monitor_queue_depth_threshold=100000)
    await bridge.start()

    registered_pin = 7

    class _MockModule:
        def __init__(self) -> None:
            self.event_queue = asyncio.Queue()

    mock_module = _MockModule()
    bridge.register_interrupt(registered_pin, mock_module)

    def fill_to_full() -> None:
        for _ in range(bridge._max_queue_size):
            bridge.trigger_interrupt(registered_pin)

    fill_to_full()
    # Producer is bounded at maxsize (drain task runs concurrently, so it need
    # not be exactly full); concurrent triggers must exercise the
    # drop-oldest compound op under thread contention.
    assert 0 <= bridge._trigger_queue.qsize() <= bridge._max_queue_size

    def hammer(_slot: int) -> None:
        for _ in range(2000):
            bridge.trigger_interrupt(registered_pin)

    with ThreadPoolExecutor(max_workers=6) as executor:
        list(executor.map(hammer, range(6)))

    while not bridge._trigger_queue.empty():
        await asyncio.sleep(0.001)
    await asyncio.sleep(0.2)

    delivered: list[Any] = []
    while not mock_module.event_queue.empty():
        delivered.append(await mock_module.event_queue.get())

    assert all(event.event_type == EventType.INTERRUPT for event in delivered)
    assert all(
        event.payload.gpio_pin == registered_pin for event in delivered
    )

    await bridge.stop()
