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

"""Unit tests for CommandBus handler registry and execute/dispatch."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import pytest

from pi_lora.framework.command_bus import CommandBus


def subclass_from_base(base: type[Any], **kwargs: Any) -> Any:
    """Build a runtime class sharing *base*'s name for subclass dispatch tests."""
    attrs: dict[str, Any] = {k: v for k, v in kwargs.items()}
    return type(base.__name__, (base,), attrs)


@dataclass(frozen=True)
class TestCommand:
    """Minimal test command with a target tuple."""

    action: str = "test"
    target: tuple[int, int] | str | None = None


@dataclass(frozen=True)
class BroadcastCommand:
    """Test command targeting all modules."""

    action: str = "broadcast"
    target: str = "all"


@dataclass(frozen=True)
class BaseCmd:
    """Base command for subclass dispatch tests with a distinct name."""

    action: str = "base"


@dataclass(frozen=True)
class DerivedCmd(BaseCmd):
    """Derived command with a distinct name for subclass dispatch tests."""

    action: str = "derived"


@dataclass(frozen=True)
class Lvl1:
    """First level of a three-level subclass chain for dispatch tests."""

    action: str = "lvl1"


@dataclass(frozen=True)
class Lvl2(Lvl1):
    """Second level of a three-level subclass chain for dispatch tests."""

    action: str = "lvl2"


@dataclass(frozen=True)
class Lvl3(Lvl2):
    """Most specific level of a three-level subclass chain for dispatch tests."""

    action: str = "lvl3"


class TestHandlerRegistry:
    """Verify register_handler behavior."""

    @pytest.mark.asyncio
    async def test_register_and_execute(self) -> None:
        bus = CommandBus()
        results: list[TestCommand] = []

        def handler(cmd: TestCommand) -> TestCommand:
            results.append(cmd)
            return cmd

        bus.register_handler(TestCommand, handler)
        cmd = TestCommand(action="hello")
        result = await bus.execute(cmd)
        assert result is cmd
        assert len(results) == 1
        assert results[0].action == "hello"

    @pytest.mark.asyncio
    async def test_priority_overrides_lower(self) -> None:
        bus = CommandBus()
        calls: list[int] = []

        def low_handler(_cmd: TestCommand) -> None:
            calls.append(1)

        def high_handler(_cmd: TestCommand) -> None:
            calls.append(2)

        bus.register_handler(TestCommand, low_handler, priority=1)
        bus.register_handler(TestCommand, high_handler, priority=0)
        await bus.execute(TestCommand())
        assert len(calls) == 1
        assert calls[0] == 2

    def test_priority_override(self) -> None:
        bus = CommandBus()
        calls: list[int] = []

        def low_handler(_cmd: TestCommand) -> None:
            calls.append(1)

        def high_handler(_cmd: TestCommand) -> None:
            calls.append(2)

        bus.register_handler(TestCommand, low_handler, priority=1)
        bus.register_handler(TestCommand, high_handler, priority=0)
        assert bus._handlers[TestCommand] == (high_handler, 0)

        with pytest.raises(
            ValueError, match=r"Handler for 'TestCommand' already registered"
        ):
            bus.register_handler(TestCommand, low_handler, priority=0)

        with pytest.raises(
            ValueError, match=r"Handler for 'TestCommand' already registered"
        ):
            bus.register_handler(TestCommand, low_handler, priority=1)
        assert bus._handlers[TestCommand] == (high_handler, 0)

    def test_priority_equal_raises(self) -> None:
        bus = CommandBus()
        calls: list[int] = []

        def first_handler(_cmd: TestCommand) -> None:
            calls.append(1)

        def second_handler(_cmd: TestCommand) -> None:
            calls.append(2)

        bus.register_handler(TestCommand, first_handler, priority=0)
        with pytest.raises(
            ValueError, match=r"Handler for 'TestCommand' already registered"
        ):
            bus.register_handler(TestCommand, second_handler, priority=0)

    @pytest.mark.asyncio
    async def test_subclass_dispatch(self) -> None:
        bus = CommandBus()
        calls: list[str] = []

        def base_handler(cmd: TestCommand) -> str:
            calls.append(cmd.action)
            return cmd.action

        bus.register_handler(TestCommand, base_handler)

        subclass = subclass_from_base(TestCommand)
        instance = subclass(action="sub")
        ret = await bus.execute(instance)
        assert ret == "sub"
        assert calls == ["sub"]

    @pytest.mark.asyncio
    async def test_subclass_dispatch_different_name(self) -> None:
        bus = CommandBus()
        calls: list[str] = []

        def base_handler(cmd: BaseCmd) -> str:
            calls.append(cmd.action)
            return cmd.action

        bus.register_handler(BaseCmd, base_handler)
        instance = DerivedCmd(action="derived")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert calls == ["derived"]

    @pytest.mark.asyncio
    async def test_most_specific_dispatch(self) -> None:
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedCmd) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseCmd) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(DerivedCmd, derived_handler)
        bus.register_handler(BaseCmd, base_handler)
        instance = DerivedCmd(action="x")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["x"]
        assert base_calls == []

    @pytest.mark.asyncio
    async def test_most_specific_dispatch_runtime_subclass(self) -> None:
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedCmd) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseCmd) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(DerivedCmd, derived_handler)
        bus.register_handler(BaseCmd, base_handler)
        subclass = subclass_from_base(DerivedCmd)
        instance = subclass(action="sub")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["sub"]
        assert base_calls == []

    @pytest.mark.asyncio
    async def test_most_specific_base_registered_first(self) -> None:
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedCmd) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseCmd) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(BaseCmd, base_handler)
        bus.register_handler(DerivedCmd, derived_handler)
        instance = DerivedCmd(action="x")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["x"]
        assert base_calls == []

    @pytest.mark.asyncio
    async def test_most_specific_three_level(self) -> None:
        bus = CommandBus()
        lvl1_calls: list[str] = []
        lvl3_calls: list[str] = []

        def lvl1_handler(cmd: Lvl1) -> str:
            lvl1_calls.append(cmd.action)
            return "lvl1"

        def lvl3_handler(cmd: Lvl3) -> str:
            lvl3_calls.append(cmd.action)
            return "lvl3"

        bus.register_handler(Lvl1, lvl1_handler)
        bus.register_handler(Lvl3, lvl3_handler)
        instance = Lvl3(action="lvl3")
        ret = await bus.execute(instance)
        assert ret == "lvl3"
        assert lvl3_calls == ["lvl3"]
        assert lvl1_calls == []

    @pytest.mark.asyncio
    async def test_most_specific_runtime_subclass(self) -> None:
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedCmd) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseCmd) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(BaseCmd, base_handler)
        bus.register_handler(DerivedCmd, derived_handler)
        subclass = subclass_from_base(DerivedCmd)
        instance = subclass(action="sub")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["sub"]
        assert base_calls == []

    @pytest.mark.asyncio
    async def test_most_specific_order_independent(self) -> None:
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedCmd) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseCmd) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(DerivedCmd, derived_handler)
        bus.register_handler(BaseCmd, base_handler)
        instance = DerivedCmd(action="x")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["x"]
        assert base_calls == []

    @pytest.mark.asyncio
    async def test_no_handler_raises(self) -> None:
        bus = CommandBus()
        with pytest.raises(ValueError, match="No handler for"):
            await bus.execute(TestCommand())

    @pytest.mark.asyncio
    async def test_execute_logs_and_rises_on_exception(self, caplog) -> None:
        bus = CommandBus()

        def raising_handler(_cmd: TestCommand) -> None:
            raise ValueError("handler failed")

        bus.register_handler(TestCommand, raising_handler)
        cmd = TestCommand(action="x")
        with pytest.raises(ValueError, match="handler failed"):
            await bus.execute(cmd)
        assert any(
            rec.levelno == logging.WARNING and "TestCommand" in rec.message
            for rec in caplog.records
        )


class TestAsyncDispatch:
    """Verify dispatch posts to module event queue."""

    @pytest.fixture
    def mock_module(self) -> Any:
        mod = type("MockModule", (), {"event_queue": asyncio.Queue()})()
        return mod  # type: ignore[return-value]

    @pytest.mark.asyncio
    async def test_dispatch_sets_resolver(self, mock_module: Any) -> None:
        bus = CommandBus()

        def resolver(cmd: TestCommand) -> Any:
            return mock_module

        bus.set_module_resolver(resolver)
        await bus.dispatch(TestCommand(target=(0, 0)))
        assert not mock_module.event_queue.empty()

    @pytest.mark.asyncio
    async def test_dispatch_without_resolver_raises(self) -> None:
        bus = CommandBus()
        with pytest.raises(RuntimeError, match="Module resolver not set"):
            await bus.dispatch(TestCommand())

    @pytest.mark.asyncio
    async def test_dispatch_resolver_returns_none_raises(self) -> None:
        bus = CommandBus()

        def resolver(cmd: TestCommand) -> Any:
            return None

        bus.set_module_resolver(resolver)
        with pytest.raises(ValueError, match="No module found for command TestCommand"):
            await bus.dispatch(TestCommand(target=(0, 0)))


class TestSyncVsAsyncHandler:
    """Verify both sync and async handlers work."""

    @pytest.mark.asyncio
    async def test_sync_handler(self) -> None:
        bus = CommandBus()
        result_holder: list[int] = []

        def sync_handler(cmd: TestCommand) -> int:
            result_holder.append(42)
            return 42

        bus.register_handler(TestCommand, sync_handler)
        ret = await bus.execute(TestCommand())
        assert ret == 42
        assert result_holder == [42]

    @pytest.mark.asyncio
    async def test_async_handler(self) -> None:
        bus = CommandBus()

        async def async_handler(cmd: TestCommand) -> str:
            return f"handled:{cmd.action}"

        bus.register_handler(TestCommand, async_handler)
        ret = await bus.execute(TestCommand(action="x"))
        assert ret == "handled:x"

    @pytest.mark.asyncio
    async def test_async_handler_logs_and_raises(self, caplog) -> None:
        # BUG-3 regression guard: an async handler's exception must be logged
        # and re-raised. The exception surfaces on `await`, so this asserts the
        # await is wrapped in the same try/except as the sync call.
        bus = CommandBus()

        async def raising_handler(_cmd: TestCommand) -> None:
            raise ValueError("async handler failed")

        bus.register_handler(TestCommand, raising_handler)
        cmd = TestCommand(action="x")
        with pytest.raises(ValueError, match="async handler failed"):
            await bus.execute(cmd)
        assert any(
            rec.levelno == logging.WARNING and "TestCommand" in rec.message
            for rec in caplog.records
        )

    @pytest.mark.asyncio
    async def test_command_bus_cancelled_error_logging(self, caplog) -> None:
        # H-10 / Plan-16 regression guard: a cancelled async handler must be
        # caught by the asyncio.CancelledError branch BEFORE the generic
        # except Exception (which is a superclass), logging the "cancelled"
        # message instead of the generic "raised" message, then re-raised
        # verbatim so asyncio cancellation semantics are preserved for the
        # awaiting coroutine. Raising asyncio.CancelledError() directly in the
        # awaited coroutine exercises the exact except asyncio.CancelledError
        # branch execute() has, since the exception surfaces on `await`.
        bus = CommandBus()

        async def cancelled_handler(_cmd: TestCommand) -> None:
            raise asyncio.CancelledError()

        bus.register_handler(TestCommand, cancelled_handler)
        cmd = TestCommand(action="x")
        with pytest.raises(asyncio.CancelledError):
            await bus.execute(cmd)
        cancelled_records = [
            rec
            for rec in caplog.records
            if rec.levelno == logging.WARNING
            and "cancelled" in rec.message
            and "TestCommand" in rec.message
        ]
        raised_records = [
            rec
            for rec in caplog.records
            if rec.levelno == logging.WARNING
            and "raised" in rec.message
        ]
        assert cancelled_records, (
            "expected a 'cancelled' warning naming the command type"
        )
        assert not raised_records, (
            "the generic 'raised' message must not be logged for a cancelled handler"
        )


@dataclass(frozen=True)
class DiamondBase:
    """Common ancestor of the diamond hierarchy for MRO dispatch tests."""

    action: str = "diamond_base"


@dataclass(frozen=True)
class DiamondLeft(DiamondBase):
    """Left branch of the diamond hierarchy for MRO dispatch tests."""

    action: str = "diamond_left"


@dataclass(frozen=True)
class DiamondRight(DiamondBase):
    """Right branch of the diamond hierarchy for MRO dispatch tests."""

    action: str = "diamond_right"


@dataclass(frozen=True)
class Diamond(DiamondLeft, DiamondRight):
    """Top of the diamond; standard MRO is Diamond, DiamondLeft, DiamondRight."""

    action: str = "diamond"


@dataclass(frozen=True)
class BaseForDerived:
    """Base command for the derived-class-wins MRO dispatch test."""

    action: str = "base_for_derived"


@dataclass(frozen=True)
class DerivedForDerived(BaseForDerived):
    """Derived command for the derived-class-wins MRO dispatch test."""

    action: str = "derived_for_derived"


class TestMROResolution:
    """H-16-3 / Plan-17: verify execute() uses standard Python MRO resolution."""

    @pytest.mark.asyncio
    async def test_command_bus_mro_diamond_inheritance(self) -> None:
        # Diamond MRO is [Diamond, DiamondLeft, DiamondRight, DiamondBase].
        # The old depth-based lookup assumed a registered type's MRO is a suffix
        # of the command's MRO and broke here: both branches have equal depth,
        # so it kept whichever was registered first. Standard resolution picks
        # the first registered type in the command's MRO, which is DiamondLeft.
        bus = CommandBus()
        left_calls: list[str] = []
        right_calls: list[str] = []

        def left_handler(cmd: DiamondLeft) -> str:
            left_calls.append(cmd.action)
            return "left"

        def right_handler(cmd: DiamondRight) -> str:
            right_calls.append(cmd.action)
            return "right"

        # Register DiamondRight first: the buggy depth-based lookup ties both
        # branches at equal depth and would return DiamondRight.
        bus.register_handler(DiamondRight, right_handler)
        bus.register_handler(DiamondLeft, left_handler)
        instance = Diamond(action="d")
        ret = await bus.execute(instance)
        assert ret == "left"
        assert left_calls == ["d"]
        assert right_calls == []

    @pytest.mark.asyncio
    async def test_command_bus_mro_derived_class_wins(self) -> None:
        # The handler registered for the most specific type (derived) must win
        # over the base handler under standard MRO resolution.
        bus = CommandBus()
        derived_calls: list[str] = []
        base_calls: list[str] = []

        def derived_handler(cmd: DerivedForDerived) -> str:
            derived_calls.append(cmd.action)
            return "derived"

        def base_handler(cmd: BaseForDerived) -> str:
            base_calls.append(cmd.action)
            return "base"

        bus.register_handler(BaseForDerived, base_handler)
        bus.register_handler(DerivedForDerived, derived_handler)
        instance = DerivedForDerived(action="x")
        ret = await bus.execute(instance)
        assert ret == "derived"
        assert derived_calls == ["x"]
        assert base_calls == []

    def test_command_bus_priority_same_type_rejected(self) -> None:
        # Priority only disambiguates handlers for the exact same type. The
        # register_handler guard rejects a duplicate same-type registration at
        # equal or higher priority, so this still raises before lookup.
        bus = CommandBus()
        bus.register_handler(TestCommand, lambda _cmd: None, priority=0)
        with pytest.raises(
            ValueError, match=r"Handler for 'TestCommand' already registered"
        ):
            bus.register_handler(
                TestCommand, lambda _cmd: None, priority=0
            )
