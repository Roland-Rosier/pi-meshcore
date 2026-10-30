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
            except (Exception, asyncio.CancelledError) as original_exc:
                # Locations 1 & 2 (Plan-18 §6 anti-regression). Two invariants
                # that must NOT regress:
                #
                # [1] Rollback on ALL exceptions, INCLUDING CancelledError.
                #     Plan-17 H-16-1 originally *committed* (did NOT roll back)
                #     on CancelledError: pending modules were left registered in
                #     the scheduler instead of unregistered. That leaked resources
                #     because Application._cleanup_partial_start() only tracked
                #     self.module_manager._started_modules (modules appended AFTER
                #     init_spi_bus() succeeded), so a module committed on
                #     CancelledError lived in module_manager.get_all_modules()
                #     but was absent from _started_modules -> never cleaned.
                #     Rolling back on every caught exception unregisters every
                #     pending module. asyncio.CancelledError is a BaseException,
                #     NOT an Exception, in Python 3.13, so it is NOT matched by
                #     `except Exception` alone; the explicit
                #     `(Exception, asyncio.CancelledError)` tuple catches it so
                #     it rolls back too. The caller (Application) then cleans ALL
                #     modules uniformly via get_all_modules() -- the caller owns
                #     cleanup after any exception.
                #
                # [2] Catch Exception only (plus CancelledError). KeyboardInterrupt,
                #     SystemExit, and GeneratorExit are shutdown signals, NOT
                #     recoverable errors. They are NOT matched by
                #     `(Exception, asyncio.CancelledError)`, so they propagate
                #     immediately with no async operation running. During process
                #     shutdown the event loop may be closing or already closed, so
                #     an async cleanup (await scheduler.unregister_module()) would
                #     raise RuntimeError and hang shutdown. Let them propagate.
                #
                # Inline rollback (no dedicated method): walk the pending list in
                # reverse, unregister each module from the scheduler, and collect
                # any unregister failures so a partial rollback still surfaces its
                # errors to the caller chained from the triggering exception.
                rollback_errors: list[Exception] = []
                for module in reversed(pending_modules):
                    try:
                        await scheduler.unregister_module(module)
                    except Exception as unregister_err:
                        rollback_errors.append(unregister_err)
                pending_modules.clear()
                pending_by_id.clear()
                logger.warning(
                    "Rolled back pending modules on load failure; main "
                    "tracking reset empty"
                )
                if rollback_errors:
                    raise ExceptionGroup(
                        "rollback failed", rollback_errors
                    ) from original_exc
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
