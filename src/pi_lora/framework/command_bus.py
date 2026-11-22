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
        # Priority: lower number = higher priority (0 = highest).
        # Reject if an existing handler has priority <= new priority
        # (i.e., existing has higher or equal priority).
        # PLAN-8 FIX (Item 8b): Unified "priority number"/"priority level" terminology.
        # The mixed wording caused confusion. Cross-reference: KNOWN_DEFECTs.md Section 8.
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
        # Dispatch resolution (docs/plan_summaries/2026_10_08_hardening_spike.md,
        # Command Bus (Plans 4-38), Phase 6 / plan-4: Fix CommandBus.execute()). The previous depth-based lookup computed
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
            # CancelledError must be caught BEFORE the generic
            # except Exception. In Python 3.13+, asyncio.CancelledError is a
            # direct subclass of BaseException (NOT Exception). In Python 3.11-3.12,
            # it is a subclass of Exception. Catching it explicitly first works
            # correctly in ALL versions and logs the correct "cancelled" message
            # instead of the generic "raised" message, then re-raises verbatim so
            # asyncio cancellation semantics are preserved for the awaiting
            # coroutine. A verbatim re-raise is required: returning would swallow
            # the cancellation and the caller would never observe it.
            #
            # (docs/plan_summaries/2026_10_08_hardening_spike.md, Command Bus (Plans 4-38), Plan-34: Fix exception hierarchy in dispatch()).
            logger.warning(
                "Command handler cancelled for %s",
                type(command).__name__,
            )
            raise exc
        except ExceptionGroup as eg:
            # ExceptionGroup handling (docs/plan_summaries/2026_10_08_hardening_spike.md,
            # Command Bus (Plans 4-38), Plan-37: Fix ExceptionGroup in _cleanup_and_reraise_cancellation()). ExceptionGroup may contain a CancelledError which
            # must propagate asyncio cancellation semantics to the caller. Unpack the
            # group: if any contained exception is a CancelledError, re-raise it verbatim
            # to preserve cancellation. Otherwise re-raise the whole ExceptionGroup for
            # the caller to handle. Matches the _cleanup_and_reraise_cancellation Case 2
            # pattern in application.py. The previously computed `other_excs` was unused
            # (the group is re-raised verbatim when no CancelledError is present), so it
            # is dropped here to satisfy the ruff F841 lint.
            cancelled_excs = [
                e for e in eg.exceptions if isinstance(e, asyncio.CancelledError)
            ]
            if cancelled_excs:
                logger.warning(
                    "Command '%s' handler cancelled (via ExceptionGroup)",
                    type(command).__name__,
                )
                for suppressed in eg.exceptions:
                    if not any(suppressed is e for e in cancelled_excs):
                        logger.warning(
                            "Command '%s' handler suppressed exception: %r",
                            type(command).__name__,
                            suppressed,
                        )
                # Re-raise the first CancelledError verbatim to preserve cancellation
                # semantics. Chain from `eg` as __cause__ so the originating handler
                # error is not lost (B904 compliance: explicit `from` in an except clause).
                raise cancelled_excs[0] from eg

            # No CancelledError - log and re-raise the ExceptionGroup verbatim.
            logger.warning(
                "Command '%s' handler raised ExceptionGroup: %r",
                type(command).__name__,
                eg,
            )
            raise
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
        # module_resolver may return None to signal
        # "no module found for this command type" — a legitimate case. Guard against None
        # before dereferencing to avoid an AttributeError and raise a clear ValueError instead.
        # (docs/plan_summaries/2026_10_08_hardening_spike.md, Command Bus (Plans 4-38), Plan-16: Fix dispatch() None from module_resolver.)
        if module is None:
            raise ValueError(f"No module found for command {type(command).__name__}")
        from .events import CommandEvent, EventType, ModuleEvent

        event: ModuleEvent[CommandEvent] = ModuleEvent(
            event_type=EventType.COMMAND,
            payload=CommandEvent(command),
        )
        await module.event_queue.put(event)
