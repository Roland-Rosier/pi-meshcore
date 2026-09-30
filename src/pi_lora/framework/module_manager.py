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
    from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

from .scheduler import Scheduler
from ..drivers.rfm9x_sx127x_radio_instance import DeviceIdentity, RadioInstanceConfig


class ModuleManager:
    """Centralized module lifecycle management.

    Loads modules from ``list[RadioInstanceConfig]``, creates instances, sets identity,
    and registers them with a ``Scheduler``.
    """

    def __init__(self) -> None:
        self.modules_by_id: dict[DeviceIdentity, Rfm9xSx127xModule] = {}
        self.modules: list[Rfm9xSx127xModule] = []

    def load_from_config(
        self,
        radio_configs: list[RadioInstanceConfig],
        scheduler: Scheduler,
        spi_factory: Any | None = None,
    ) -> None:
        """Load modules from *radio_configs*, create them, set identity, register with *scheduler*.

        Iterates over ``radio_configs`` directly. Creates a ``Rfm9xSx127xModule`` per
        ``RadioInstanceConfig``. Uses ``radio_config.dio_gpio_mappings`` for
        ``interrupt_gpio_pins``. Keys modules by ``radio_config.device_id_key`` (DeviceIdentity).
        """
        from ..drivers.rfm9x_sx127x_modes import StateBits
        from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule

        for radio_config in radio_configs:
            module = Rfm9xSx127xModule(
                radio_config=radio_config,
                state=StateBits.UNKNOWN_STATE,
                spi_factory=spi_factory,
            )

            # Extract GPIO pins from DIO->GPIO mappings
            gpio_pins: list[int] = []
            if radio_config.dio_gpio_mappings:
                for mapping in radio_config.dio_gpio_mappings:
                    parts = mapping.split(":")
                    if len(parts) == 2:
                        gpio_str = parts[1]
                        for prefix in ("GPIO", "WPi"):
                            if gpio_str.startswith(prefix):
                                with suppress(ValueError):
                                    gpio_pins.append(int(gpio_str[len(prefix):]))
                                break

            scheduler.register_module(
                module,
                timer_interval=1.0,
                idle_enabled=True,
                interrupt_gpio_pins=gpio_pins,
            )

            device_key: DeviceIdentity = radio_config.device_id_key
            if device_key in self.modules_by_id:
                import logging
                logging.getLogger(__name__).warning(
                    "Duplicate DeviceIdentity %s in config; overwriting previous module", device_key
                )
            self.modules_by_id[device_key] = module
            self.modules.append(module)

    def get_module(
        self,
        spi_device_id: int,
        ce_number: int,
    ) -> Rfm9xSx127xModule | None:
        """Return the module keyed by ``(spi_device_id, ce_number)``, or ``None``."""
        device_identity: DeviceIdentity = DeviceIdentity(spi_device_id, ce_number)
        return self.modules_by_id.get(device_identity)

    def get_all_modules(self) -> list[Rfm9xSx127xModule]:
        """Return all managed modules in registration order."""
        return list(self.modules)
