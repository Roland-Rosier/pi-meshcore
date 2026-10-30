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

import asyncio
import logging
from typing import Any

from .scheduler import Scheduler
from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule
from ..drivers.rfm9x_sx127x_radio_instance import (
    DeviceIdentity,
    RadioInstanceConfig,
    RadioInstanceError,
)
from ..types import StateBits

logger = logging.getLogger(__name__)


class DuplicateDeviceIdentityError(RadioInstanceError):
    """Raised when a ``DeviceIdentity`` already exists in the manager during load."""

    def __init__(self, device_key: DeviceIdentity) -> None:
        super().__init__(
            f"Duplicate DeviceIdentity {device_key} in config",
            {"device_key": str(device_key)},
        )


class ModuleManager:
    """Centralized module lifecycle management.

    Loads modules from ``list[RadioInstanceConfig]``, creates instances, sets identity,
    and registers them with a ``Scheduler``.
    """

    def __init__(self) -> None:
        self.modules_by_id: dict[DeviceIdentity, Rfm9xSx127xModule] = {}
        self.modules: list[Rfm9xSx127xModule] = []

    async def load_from_config(
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
        # H-13/Plan-16: register-in-scheduler-then-commit-later.
        #
        # WHY register-before-track was dangerous: the previous strategy added a
        # module to the ``Scheduler`` and then to ``self.modules``/
        # ``self.modules_by_id`` in the same step. If a later config failed, the
        # scheduler already held a task for an earlier module whose instance was
        # NOT in the tracking lists -- a dangling scheduler reference with no
        # owning module, i.e. a resource leak. Rollback then had to walk tracking
        # lists that could be out of sync with the scheduler.
        #
        # HOW the pending list prevents dangling refs: each module is registered
        # in the scheduler but parked in ``pending_modules``/``pending_by_id``
        # instead of the main tracking. Rollback therefore only ever touches
        # pending modules (in reverse order), so every scheduler-registered module
        # is unregistered and no dangling reference survives. Main tracking
        # (``self.modules``/``self.modules_by_id``) is populated ONLY after the
        # whole loop completes successfully, so a caller either sees a fully
        # consistent set or an empty set -- never a partial leak.
        pending_modules: list[Rfm9xSx127xModule] = []
        pending_by_id: dict[DeviceIdentity, Rfm9xSx127xModule] = {}

        for index, radio_config in enumerate(radio_configs):
            try:
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
                        if len(parts) != 2:
                            logger.error(
                                "Unparseable GPIO mapping %r at config index %d "
                                "(device %r); Interrupt handling DISABLEd for this device",
                                mapping,
                                index,
                                radio_config.device_name,
                            )
                            continue
                        gpio_str = parts[1]
                        matched_prefix: str | None = None
                        for prefix in ("GPIO", "WPi"):
                            if gpio_str.startswith(prefix):
                                matched_prefix = prefix
                                break
                        if matched_prefix is None:
                            logger.error(
                                "Unparseable GPIO mapping %r at config index %d "
                                "(device %r); Interrupt handling DISABLEd for this device",
                                mapping,
                                index,
                                radio_config.device_name,
                            )
                            continue
                        try:
                            gpio_pins.append(int(gpio_str[len(matched_prefix):]))
                        except ValueError:
                            logger.error(
                                "Unparseable GPIO mapping %r at config index %d "
                                "(device %r); Interrupt handling DISABLEd for this device",
                                mapping,
                                index,
                                radio_config.device_name,
                            )

                device_key: DeviceIdentity = radio_config.device_id_key
                # H-13/Plan-16: a duplicate can live in the main tracking (a prior
                # load) OR in pending_by_id (an earlier module registered in this
                # same loop). Check both before registering.
                if device_key in self.modules_by_id or device_key in pending_by_id:
                    raise DuplicateDeviceIdentityError(device_key)

                scheduler.register_module(
                    module,
                    timer_interval=1.0,
                    idle_enabled=True,
                    interrupt_gpio_pins=gpio_pins,
                )

                # H-13/Plan-16: park in pending (NOT main tracking) so rollback
                # can unregister exactly the modules the scheduler owns.
                pending_modules.append(module)
                pending_by_id[device_key] = module
            except Exception:
                # Catch Exception only. Shutdown signals (KeyboardInterrupt,
                # SystemExit, GeneratorExit) propagate immediately -- the event
                # loop may be closed during process shutdown, so async operations
                # (await scheduler.unregister_module()) would fail.
                # asyncio.CancelledError extends Exception in Python 3.11+, so it
                # IS caught here and rolls back -- Application cleanup via
                # get_all_modules() then handles all modules uniformly.
                await self._rollback_pending_modules()
                raise

        # H-13/Plan-16: whole loop succeeded -- commit pending to main tracking
        # so callers see a fully consistent set. Only now is self.modules and
        # self.modules_by_id populated; a caller never sees a partial leak.
        for device_key, module in pending_by_id.items():
            self.modules.append(module)
            self.modules_by_id[device_key] = module
        pending_modules.clear()
        pending_by_id.clear()

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
