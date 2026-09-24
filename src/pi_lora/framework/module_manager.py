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

"""ModuleManager — loads config, creates Rfm9xSx127xModule instances, registers with Scheduler."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig
    from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

from .scheduler import Scheduler


class ModuleManager:
    """Centralized module lifecycle management.

    Loads modules from ``Rfm9xSx127xConfig``, creates instances, sets identity,
    and registers them with a ``Scheduler``.
    """

    def __init__(self) -> None:
        self.modules_by_id: dict[tuple[int, int], Rfm9xSx127xModule] = {}
        self.modules: list[Rfm9xSx127xModule] = []

    def load_from_config(
        self,
        config: Rfm9xSx127xConfig,
        scheduler: Scheduler,
        spi_factory: Any | None = None,
    ) -> None:
        """Load modules from *config*, create them, set identity, register with *scheduler*.

        For each module in ``config.modules``, iterates over ``devices`` and creates a
        ``Rfm9xSx127xModule`` per ``DeviceModuleAttachment``. Sets ``spi_device_id``
        and ``ce_number`` via setters. Extracts GPIO pins from ``dio_gpio_mappings``
        for ``InterruptBridge.register_interrupt()``.
        """
        from ..drivers.rfm9x_sx127x_modes import StateBits
        from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

        for module_config in config.modules.values():
            for attachment in module_config.devices:
                module = Rfm9xSx127xModule(state=StateBits.UNKNOWN_STATE, spi_factory=spi_factory)
                module.set_spi_device_id(attachment.spi_device_id)
                module.set_ce_number(attachment.ce_number)

                # Extract GPIO pins from DIO->GPIO mappings
                gpio_pins: list[int] = []
                if attachment.dio_gpio_mappings:
                    for mapping in attachment.dio_gpio_mappings:
                        parts = mapping.split(":")
                        if len(parts) == 2:
                            gpio_str = parts[1]
                            for prefix in ("GPIO", "WPi"):
                                if gpio_str.startswith(prefix):
                                    with suppress(ValueError):
                                        gpio_pins.append(int(gpio_str[len(prefix) :]))
                                    break

                scheduler.register_module(
                    module,
                    timer_interval=1.0,
                    idle_enabled=True,
                    interrupt_gpio_pins=gpio_pins,
                )

                self.modules_by_id[(attachment.spi_device_id, attachment.ce_number)] = (
                    module
                )
                self.modules.append(module)

    def get_module(
        self,
        spi_device_id: int,
        ce_number: int,
    ) -> Rfm9xSx127xModule | None:
        """Return the module keyed by ``(spi_device_id, ce_number)``, or ``None``."""
        return self.modules_by_id.get((spi_device_id, ce_number))

    def get_all_modules(self) -> list[Rfm9xSx127xModule]:
        """Return all managed modules in registration order."""
        return list(self.modules)
