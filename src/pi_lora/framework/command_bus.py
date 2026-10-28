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

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

logger: logging.Logger = logging.getLogger(__name__)

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
        """Register *handler* for *command_type* with optional *priority*.

        Raises when an existing handler is already registered at an equal or
        higher priority.
        """
        existing = self._handlers.get(command_type)
        # Lower priority number = higher priority (0=highest). Reject if existing priority <= new priority (existing is higher/equal).
        if existing is not None and existing[1] <= priority:
            raise ValueError(
                f"Handler for '{command_type.__name__}' already registered "
                f"at priority >= {existing[1]}"
            )
        self._handlers[command_type] = (handler, priority)

    def set_module_resolver(
        self,
        resolver: Callable[[Any], Any],
    ) -> None:
        """Set the callable used to resolve commands to target modules."""
        self._module_resolver = resolver

    async def execute(self, command: Any) -> Any:
        """Directly dispatch *command* to its registered handler.

        Dispatch is immediate (not queued to an event queue); the method is
        async only so coroutine handlers can be awaited. Handlers keyed by a
        command's base class also match subclasses.

        If the handler is a coroutine function it is awaited; otherwise it
        is called directly.
        """
        # H-16-3 / Plan-17: The previous depth-based lookup computed
        # `command_depth - len(registered_type.__mro__)` and assumed a
        # registered type's MRO is a suffix of the command's MRO. That assumption
        # breaks for diamond inheritance, where two base classes share a common
        # ancestor but differ in MRO length, so the shallowest match is not the
        # correct standard-Python-resolution match. Iterate the command's own
        # MRO in resolution order instead; the first registered handler wins.
        # This matches isinstance/except semantics exactly. Priority only
        # disambiguates when two handlers target the exact same type, which
        # register_handler already rejects, so it is irrelevant here.
        command_mro: tuple[type[Any], ...] = type(command).__mro__
        best_key: type[Any] | None = None
        best_tuple: tuple[Callable[..., Any], int] | None = None
        for registered_type in command_mro:
            handler_tuple = self._handlers.get(registered_type)
            if handler_tuple is not None:
                best_key = registered_type
                best_tuple = handler_tuple
                break  # First match in MRO order wins
        if best_key is None:
            raise ValueError(f"No handler for {type(command).__name__}")
        assert best_tuple is not None
        handler, _priority = best_tuple
        try:
            result = handler(command)
            # BUG-3 fix: the await must live inside the same try/except as the
            # sync call. For an async handler `handler(command)` returns a
            # coroutine without raising, so the exception surfaces only when we
            # `await` it. Leaving the await outside this block (the pre-fix
            # layout) meant async handler exceptions were never logged.
            if asyncio.iscoroutine(result):
                return await result
            return result
        except asyncio.CancelledError as exc:
            # H-10 / Plan-16: CancelledError must be caught BEFORE the generic
            # except Exception since asyncio.CancelledError is a subclass of
            # Exception. Catching it separately logs the correct "cancelled"
            # message instead of the generic "raised" message, then re-raises
            # verbatim so asyncio cancellation semantics are preserved for the
            # awaiting coroutine. A verbatim re-raise is required: returning
            # would swallow the cancellation and the caller would never observe
            # it.
            logger.warning(
                "Command handler cancelled for %s",
                type(command).__name__,
            )
            raise exc
        except Exception as exc:
            # Sync and async-await exceptions are caught here uniformly so both
            # are logged and re-raised. Option A (wrap the await) was chosen
            # over Option B (normalize every handler to async): Option B is a
            # breaking change that would force callers to await sync handlers
            # and touch every handler site, so it was rejected.
            logger.warning(
                "Command '%s' handler raised: %r",
                type(command).__name__,
                exc,
            )
            raise

    async def dispatch(self, command: Any) -> None:
        """Asynchronously post *command* to its target module's event queue."""
        if self._module_resolver is None:
            raise RuntimeError("Module resolver not set")
        module = self._module_resolver(command)
        from .events import CommandEvent, EventType, ModuleEvent

        event: ModuleEvent[CommandEvent] = ModuleEvent(
            event_type=EventType.COMMAND,
            payload=CommandEvent(command),
        )
        await module.event_queue.put(event)
