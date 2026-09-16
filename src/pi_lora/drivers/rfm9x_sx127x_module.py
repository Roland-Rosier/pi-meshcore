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


from .rfm9x_sx127x_handler import Rfm9xSx127xHandler
from .rfm9x_sx127x_modes import (
    LoraMode,
    ModeBits,
    Rfm9xSx127xMode,
    StateBits,
    StateBitsMapping,
)


class Rfm9xSx127xModule:
    """State management context for a RFM9x/SX127x radio module.

    Stores one active ``Rfm9xSx127xMode`` instance in ``current_state_instance``
    and a cache of every known state in ``state_instances`` keyed by the concrete
    class type.
    """

    def __init__(self, state: StateBits) -> None:
        self.current_state_instance: Rfm9xSx127xMode|None = self._create_state_instance(state)
        self.state_instances: dict[type[Rfm9xSx127xMode], Rfm9xSx127xMode] = (
            self._create_instances()
        )
        self.handler: Rfm9xSx127xHandler = Rfm9xSx127xHandler()

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

    def set_current_state(self, state: StateBits) -> None:
        """Transition the module to *state*, firing ``on_exit``/``on_entry`` hooks."""
        if self.current_state_instance is not None:
            current_cls = type(self.current_state_instance)
            cached = self.state_instances.get(current_cls)
            if cached is not None and isinstance(cached, Rfm9xSx127xMode):
                cached.on_exit()

        new_instance = self.state_instances.get(StateBitsMapping.from_bits(state).value)
        if new_instance is None:
            new_instance = self._create_state_instance(state)
            self.state_instances[type(new_instance)] = new_instance

        self.current_state_instance = new_instance
        self.current_state_instance.on_entry()

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

    def write_and_verify_frequency_for_khz(
        self, frequency_khz: int
    ) -> bool | None:
        """Return ``True`` if current state is SLEEP or STANDBY; ``None`` otherwise.

        This method acts as a guard — actual frequency writing is delegated to
        the SPI driver layer.  Only states whose ``MODE_BITS`` indicate sleep or
        standby are permitted to proceed with frequency writes.
        """
        if self.current_state_instance is not None:
            mode_bits = type(self.current_state_instance).MODE_BITS
            if mode_bits in (ModeBits.SLEEP_OR_ERROR_OR_NOT_A_DEVICE_OR_UNKNOWN_OR_RESET, ModeBits.STANDBY):
                return True
        return None
