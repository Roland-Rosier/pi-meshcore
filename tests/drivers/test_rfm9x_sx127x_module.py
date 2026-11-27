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

"""Deterministic verification of ``Rfm9xSx127xModule.wait_for_event`` timeout contract.

Plan-19 Fix 3 changed the catch from builtin ``TimeoutError`` to explicit
``asyncio.TimeoutError``. The observable behaviour is unchanged: when the timeout
elapses with no matching buffered event, ``wait_for_event`` returns ``None``.
The replay branch returns a pre-buffered matching event immediately, with no
timing dependency, which proves the method returns the correct event when one
already matches.
"""

from typing import Any

import pytest

from pi_lora.drivers.rfm9x_sx127x_modes import StateBits
from pi_lora.drivers.rfm9x_sx127x_radio_instance import RadioInstanceConfig
from pi_lora.framework.events import EventType, ModuleEvent, StateChangeEvent


@pytest.mark.asyncio
async def test_rfm9x_module_explicit_timeout_error() -> None:
    from pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

    radio_config: RadioInstanceConfig = RadioInstanceConfig(
        module_name="LoPi4", spi_device_id=0, ce_number=0, device_name="RFM95W",
        min_radio_freq_hz=800000, max_radio_freq_hz=900000, osc_freq_hz=32_000_000,
        family_name="RFM9X", test_invalid_frequencies_hz=(999999,),
        dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"), antenna_type=None, antenna_gain_db=None,
    )
    module: Rfm9xSx127xModule = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)

    # Timeout path: empty buffer and nothing sets the waiter event, so the
    # asyncio.TimeoutError fires and the method returns None (Plan-19 Fix 3).
    timeout_result: ModuleEvent[Any] | None = await module.wait_for_event(
        EventType.COMMAND, predicate=None, timeout=0.01
    )
    assert timeout_result is None

    # Replay path: a pre-buffered matching event is returned immediately, with
    # no timing dependency, proving the method returns correctly.
    pre_buffered: ModuleEvent[StateChangeEvent] = ModuleEvent(
        event_type=EventType.STATE_CHANGE,
        payload=StateChangeEvent(new_state=StateBits.UNKNOWN_STATE, reason="replay"),
    )
    module._event_buffer[EventType.STATE_CHANGE].append(pre_buffered)
    replayed: ModuleEvent[Any] | None = await module.wait_for_event(
        EventType.STATE_CHANGE, predicate=lambda event: True, timeout=5.0
    )
    assert replayed is pre_buffered


@pytest.mark.asyncio
async def test_is_in_state_returns_false_when_no_current_state() -> None:
    from pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

    radio_config: RadioInstanceConfig = RadioInstanceConfig(
        module_name="LoPi4", spi_device_id=0, ce_number=0, device_name="RFM95W",
        min_radio_freq_hz=800000, max_radio_freq_hz=900000, osc_freq_hz=32_000_000,
        family_name="RFM9X", test_invalid_frequencies_hz=(999999,),
        dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"), antenna_type=None, antenna_gain_db=None,
    )
    module: Rfm9xSx127xModule = Rfm9xSx127xModule(radio_config, StateBits.UNKNOWN_STATE)
    module.current_state_instance = None

    # Plan §Testing Strategy item 1: is_in_state() must return False when
    # current_state_instance is None instead of raising on the type() comparison.
    # Cross-reference: rfm9x_sx127x_module.py is_in_state() None guard (PLAN-2 FIX Issue 4.18).
    assert module.is_in_state(StateBits.UNKNOWN_STATE) is False
    assert module.is_in_state(StateBits.RESET_STATE) is False
    assert module.is_in_state(StateBits.FSK_OOK_SLEEP) is False


@pytest.mark.asyncio
async def test_request_reset_transition_accepts_custom_event_source() -> None:
    from pi_lora.drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

    radio_config: RadioInstanceConfig = RadioInstanceConfig(
        module_name="LoPi4", spi_device_id=0, ce_number=0, device_name="RFM95W",
        min_radio_freq_hz=800000, max_radio_freq_hz=900000, osc_freq_hz=32_000_000,
        family_name="RFM9X", test_invalid_frequencies_hz=(999999,),
        dio_gpio_mappings=("DIO0:WPi6", "DIO5:WPi5"), antenna_type=None, antenna_gain_db=None,
    )
    module: Rfm9xSx127xModule = Rfm9xSx127xModule(radio_config, StateBits.FSK_OOK_SLEEP)

    # Plan §Testing Strategy items 2-3: request_reset_transition() forwards the caller's
    # event_source into the queued STATE_CHANGE event's source field.
    module.request_reset_transition(reason="custom_reset", event_source="my_source")
    event = module.event_queue.get_nowait()
    assert event.event_type == EventType.STATE_CHANGE
    assert event.source == "my_source"
    assert event.payload is not None
    assert event.payload.new_state == StateBits.RESET_STATE
    assert event.payload.reason == "custom_reset"
