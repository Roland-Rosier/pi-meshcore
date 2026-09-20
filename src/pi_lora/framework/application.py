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

"""Application — composes ModuleManager, Scheduler, CommandBus into a unified runtime."""

from __future__ import annotations

import asyncio  # noqa: F401
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig  # noqa: F401

from .command_bus import CommandBus
from .events import StopMode
from .module_manager import ModuleManager
from .scheduler import Scheduler


class Application:
    """Top-level runtime owning the module lifecycle and command infrastructure."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.scheduler = Scheduler()
        self.module_manager = ModuleManager()
        self.command_bus = CommandBus()

    async def start(self) -> None:
        """Initialize the application: load modules, register scheduler, start loops."""
        self.module_manager.load_from_config(self.config, self.scheduler)
        self.command_bus.set_module_resolver(self._resolve_module_for_command)
        await self.scheduler.start()
        for module in self.module_manager.get_all_modules():
            await module.start_event_loop()

    async def stop(self) -> None:
        """Gracefully stop all modules and the scheduler."""
        for module in self.module_manager.get_all_modules():
            await module.stop_event_loop(StopMode.DRAIN)
        await self.scheduler.stop()

    async def run_blocking_command(self, cmd: Any) -> Any:
        """Execute *cmd* synchronously via CommandBus.execute()."""
        return await self.command_bus.execute(cmd)

    async def run_async_command(self, cmd: Any) -> None:
        """Dispatch *cmd* asynchronously via CommandBus.dispatch()."""
        await self.command_bus.dispatch(cmd)

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of all managed module states."""
        return {
            "modules": [
                {
                    "spi_device_id": m.get_spi_device_id(),
                    "ce_number": m.get_ce_number(),
                    "state": m.get_current_state_name(),
                    "queue_size": m.get_event_queue_size(),
                }
                for m in self.module_manager.get_all_modules()
            ]
        }

    def _resolve_module_for_command(self, command: Any) -> Any:
        """Resolve a command's target to its Rfm9xSx127xModule."""
        target = getattr(command, "target", None)
        if target == "all":
            all_modules = self.module_manager.get_all_modules()
            return all_modules[0] if all_modules else None
        elif isinstance(target, tuple) and len(target) == 2:
            result = self.module_manager.get_module(target[0], target[1])
            if result is not None:
                return result
            raise ValueError(f"No module for target {target}")
        raise ValueError(f"Invalid command target: {target}")
