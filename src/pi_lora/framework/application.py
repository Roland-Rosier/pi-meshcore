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
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig  # noqa: F401

from .command_bus import CommandBus
from .events import StopMode
from .exceptions import AssemblyNotFoundError, DeviceAttachmentNotFoundError
from .module_manager import ModuleManager
from .scheduler import Scheduler
from ..drivers.rfm9x_sx127x_config_loader import get_preloaded_config
from ..drivers.rfm9x_sx127x_radio_instance import (
    RadioInstanceConfig,
    create_radio_instance,
)


class Application:
    """Top-level runtime owning the module lifecycle and command infrastructure."""

    def __init__(self, config: Any, spi_factory: Any | None = None) -> None:
        self.config = config
        self.scheduler = Scheduler()
        self.module_manager = ModuleManager()
        self.command_bus = CommandBus()
        if spi_factory is not None:
            self.spi_factory = spi_factory
        else:
            from ..drivers.spi.factory import RealSpiBusFactory

            self.spi_factory = RealSpiBusFactory()
        self._config: "Rfm9xSx127xConfig | None" = None
        self._config_path: Path | None = None

    async def start(self) -> None:
        """Initialize the application: load modules, register scheduler, start loops."""
        self.module_manager.load_from_config(self.config, self.scheduler, self.spi_factory)
        self.command_bus.set_module_resolver(self._resolve_module_for_command)
        await self.scheduler.start()
        for module in self.module_manager.get_all_modules():
            if module.spi_device_id is not None:
                await module.init_spi_bus()
            await module.start_event_loop()

    async def stop(self) -> None:
        """Gracefully stop all modules and the scheduler."""
        for module in self.module_manager.get_all_modules():
            await module.stop_event_loop(StopMode.DRAIN)
            await module.close_spi()
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

    def _load_config(self, config_path: Path | None = None) -> "Rfm9xSx127xConfig":
        """Load configuration, caching it for subsequent calls.

        Args:
            config_path: Optional custom config file path (forces reload).

        Returns:
            The loaded Rfm9xSx127xConfig instance.
        """
        if config_path is not None:
            config = get_preloaded_config(config_path=config_path)
            self._config_path = config_path
            self._config = config
            return config

        if self._config is not None:
            return self._config

        config = cast("Rfm9xSx127xConfig", get_preloaded_config())
        self._config = config
        return config

    def reload_config(self, config_path: Path | None = None) -> "Rfm9xSx127xConfig":
        """Force reload configuration.

        Args:
            config_path: Optional custom config file path.

        Returns:
            The reloaded Rfm9xSx127xConfig instance.
        """
        config = cast("Rfm9xSx127xConfig", get_preloaded_config(force_reload=True, config_path=config_path))
        self._config_path = config_path
        self._config = config
        return config

    def list_assemblies(self, verbose: bool = False) -> list[dict[str, Any]]:
        """Return list of available assemblies.

        Args:
            verbose: If True, include module_name and device_count for each assembly.

        Returns:
            List of dicts with assembly info.
        """
        config = self._load_config()
        results: list[dict[str, Any]] = []
        for assembly_name, assembly in config.assemblies.items():
            if verbose:
                results.append({
                    "assembly_name": assembly_name,
                    "module_name": assembly.module_name,
                    "device_count": len(assembly.devices),
                })
            else:
                results.append({"assembly_name": assembly_name})
        return results

    def get_assembly_config(
        self,
        assembly_name: str,
        spi_device_id: int | None = None,
        ce_number: int | None = None,
        config_path: Path | None = None,
    ) -> RadioInstanceConfig | list[RadioInstanceConfig]:
        """Get RadioInstanceConfig(s) for an assembly.

        Args:
            assembly_name: Name of the assembly to query.
            spi_device_id: Optional SPI device ID to filter.
            ce_number: Optional CE number to filter.
            config_path: Optional custom config file path (forces reload).

        Returns:
            Single RadioInstanceConfig if both spi_device_id and ce_number provided,
            otherwise list of all RadioInstanceConfigs for the assembly.

        Raises:
            AssemblyNotFoundError: If assembly not found.
            DeviceAttachmentNotFoundError: If SPI/CE filter doesn't match any device.
        """
        config = self._load_config(config_path)

        if assembly_name not in config.assemblies:
            raise AssemblyNotFoundError(f"Assembly '{assembly_name}' not found in configuration")

        assembly = config.assemblies[assembly_name]
        module_name = assembly.module_name

        if module_name not in config.modules:
            raise AssemblyNotFoundError(f"Module '{module_name}' for assembly '{assembly_name}' not found")

        module_obj = config.modules[module_name]

        configs: list[RadioInstanceConfig] = []
        for attachment in module_obj.devices:
            try:
                radio_config = create_radio_instance(
                    assembly_name=assembly_name,
                    spi_device_id=attachment.spi_device_id,
                    ce_number=attachment.ce_number,
                    config=config,
                )
                configs.append(radio_config)
            except (DeviceAttachmentNotFoundError, Exception):
                continue

        if not configs:
            raise DeviceAttachmentNotFoundError(
                module_name,
                spi_device_id if spi_device_id is not None else -1,
                ce_number if ce_number is not None else -1,
            )

        if spi_device_id is not None and ce_number is not None:
            for cfg in configs:
                if cfg.spi_device_id == spi_device_id and cfg.ce_number == ce_number:
                    return cfg
            raise DeviceAttachmentNotFoundError(
                module_name, spi_device_id, ce_number
            )

        return configs
