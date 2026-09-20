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

"""CommandBus — handler registry with module resolver for async/sync dispatch."""

from __future__ import annotations

import asyncio  # noqa: F401
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .module_manager import ModuleManager  # noqa: F401


class CommandBus:
    """Registry of command handlers keyed by command type with module resolver."""

    def __init__(self) -> None:
        self._handlers: dict[type[Any], tuple[Callable[..., Any], int]] = {}
        self._module_resolver: Callable[[Any], Any] | None = None

    def register_handler(
        self,
        command_type: type[Any],
        handler: Callable[..., Any],
        priority: int = 0,
    ) -> None:
        """Register *handler* for *command_type* with optional *priority*."""
        existing = self._handlers.get(command_type)
        if existing is not None and existing[1] >= priority:
            return
        self._handlers[command_type] = (handler, priority)

    def set_module_resolver(
        self,
        resolver: Callable[[Any], Any],
    ) -> None:
        """Set the callable used to resolve commands to target modules."""
        self._module_resolver = resolver

    async def execute(self, command: Any) -> Any:
        """Synchronously dispatch *command* to its registered handler.

        If the handler is a coroutine function it is awaited; otherwise it
        is called directly.
        """
        handler_tuple = self._handlers.get(type(command))
        if handler_tuple is None:
            raise ValueError(f"No handler for {type(command).__name__}")
        handler, _priority = handler_tuple
        result = handler(command)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def dispatch(self, command: Any) -> None:
        """Asynchronously post *command* to its target module's event queue."""
        if self._module_resolver is None:
            raise RuntimeError("Module resolver not set")
        module = self._module_resolver(command)
        from .events import CommandEvent, EventType, ModuleEvent

        event = ModuleEvent(
            event_type=EventType.COMMAND,
            payload=CommandEvent(command),
        )
        await module.event_queue.put(event)
