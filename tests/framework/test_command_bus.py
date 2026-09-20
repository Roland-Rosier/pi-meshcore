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
from dataclasses import dataclass
from typing import Any

import pytest
from src.pi_lora.framework.command_bus import CommandBus


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


class TestHandlerRegistry:
    """Verify register_handler behavior."""

    def test_register_and_execute(self) -> None:
        bus = CommandBus()
        results: list[TestCommand] = []

        def handler(cmd: TestCommand) -> TestCommand:
            results.append(cmd)
            return cmd

        bus.register_handler(TestCommand, handler)
        cmd = TestCommand(action="hello")
        result = asyncio.run(bus.execute(cmd))
        assert result is cmd
        assert len(results) == 1
        assert results[0].action == "hello"

    def test_priority_overrides_lower(self) -> None:
        bus = CommandBus()
        calls: list[int] = []

        def low_handler(_cmd: TestCommand) -> None:
            calls.append(1)

        def high_handler(_cmd: TestCommand) -> None:
            calls.append(2)

        bus.register_handler(TestCommand, low_handler, priority=0)
        bus.register_handler(TestCommand, high_handler, priority=1)
        asyncio.run(bus.execute(TestCommand()))
        assert len(calls) == 1
        assert calls[0] == 2

    def test_priority_does_not_override_equal(self) -> None:
        bus = CommandBus()
        calls: list[int] = []

        def first_handler(_cmd: TestCommand) -> None:
            calls.append(1)

        def second_handler(_cmd: TestCommand) -> None:
            calls.append(2)

        bus.register_handler(TestCommand, first_handler, priority=0)
        bus.register_handler(TestCommand, second_handler, priority=0)
        asyncio.run(bus.execute(TestCommand()))
        assert len(calls) == 1
        assert calls[0] == 1

    def test_no_handler_raises(self) -> None:
        bus = CommandBus()
        with pytest.raises(ValueError, match="No handler for"):
            asyncio.run(bus.execute(TestCommand()))


class TestAsyncDispatch:
    """Verify dispatch posts to module event queue."""

    @pytest.fixture
    def mock_module(self) -> Any:
        import asyncio
        mod = type("MockModule", (), {"event_queue": asyncio.Queue()})()
        return mod  # type: ignore[return-value]

    def test_dispatch_sets_resolver(self, mock_module: Any) -> None:
        bus = CommandBus()

        def resolver(cmd: TestCommand) -> Any:
            return mock_module

        bus.set_module_resolver(resolver)
        asyncio.run(bus.dispatch(TestCommand(target=(0, 0))))
        assert not mock_module.event_queue.empty()

    def test_dispatch_without_resolver_raises(self) -> None:
        bus = CommandBus()
        with pytest.raises(RuntimeError, match="Module resolver not set"):
            asyncio.run(bus.dispatch(TestCommand()))


class TestSyncVsAsyncHandler:
    """Verify both sync and async handlers work."""

    def test_sync_handler(self) -> None:
        bus = CommandBus()
        result_holder: list[int] = []

        def sync_handler(cmd: TestCommand) -> int:
            result_holder.append(42)
            return 42

        bus.register_handler(TestCommand, sync_handler)
        ret = asyncio.run(bus.execute(TestCommand()))
        assert ret == 42
        assert result_holder == [42]

    def test_async_handler(self) -> None:
        bus = CommandBus()

        async def async_handler(cmd: TestCommand) -> str:
            return f"handled:{cmd.action}"

        bus.register_handler(TestCommand, async_handler)
        ret = asyncio.run(bus.execute(TestCommand(action="x")))
        assert ret == "handled:x"
