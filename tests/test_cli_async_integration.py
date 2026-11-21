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

"""End-to-end CLI integration tests for async command execution.

These tests verify that the ``async_typer.AsyncTyper`` commands
(``test hardware``, ``config list-assemblies``, ``config show-config``) execute
their coroutine bodies fully -- producing the expected output -- and that no
``RuntimeWarning: coroutine ... was never awaited`` is emitted.

They also prove the regression fixed in Plan-7: a plain ``typer.Typer`` wraps an
``async def`` callback without awaiting it, which raises the
``RuntimeWarning``. ``async_typer`` instead drives the coroutine through an
``asyncio.Runner`` inside a *synchronous* callback, so the coroutine is always
awaited.

Invocation contract
---------------------
``typer.testing.CliRunner`` does **not** execute async commands (it returns
``exit_code == 2`` and never runs the coroutine), so it cannot be used here.
The real execution path is ``get_command(sub_app)(argv)`` invoked from a plain
synchronous context. ``async_typer``'s command wrapper manages the event loop
internally via ``asyncio.Runner`` -- which *cannot* run inside an already-running
event loop -- so these tests must be plain ``def`` tests (not
``@pytest.mark.asyncio`` coroutines). Passing argv through an ``asyncio.run``
wrapper would trigger ``Runner.run() cannot be called from a running event
loop``; that failure mode is exactly what this test family avoids by invoking in
a sync context.
"""

from __future__ import annotations

import sys
import warnings
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rich.console import Console
from typer.main import get_command

from pi_lora.cli.check_hardware import app as check_hardware_app
from pi_lora.cli.config import app as config_app
from pi_lora.cli.test import app as test_app
from pi_lora.framework.events import EventType, ModuleEvent, StateChangeEvent
from pi_lora.framework.exceptions import AssemblyNotFoundError
from pi_lora.types import StateBits

_SUCCESSFUL_EVENT: ModuleEvent[StateChangeEvent] = ModuleEvent(
    event_type=EventType.STATE_CHANGE,
    payload=StateChangeEvent(
        new_state=StateBits.RESET_STATE,
        reason="test_hardware_command",
    ),
)


def _invoke_command(cmd: Any, argv: list[str]) -> tuple[int, list[str]]:
    """Invoke a Typer command from a synchronous context and capture warnings.

    ``cmd`` is the object returned by ``get_command(sub_app)``. The command runs
    its (possibly async) callback through ``asyncio.Runner`` internally, so this
    must be called from a plain synchronous context -- never from inside an
    already-running event loop. ``typer.Exit`` (mapped by Click to ``SystemExit``)
    yields the reported exit code; a callback that returns ``None`` is exit 0.

    Every warning emitted during the invocation is recorded (with
    ``warnings.simplefilter("always")``) and returned as its string form so the
    caller can assert that no ``"never awaited"`` ``RuntimeWarning`` occurred.
    """
    with warnings.catch_warnings(record=True) as log:
        warnings.simplefilter("always")
        try:
            cmd(argv)
        except SystemExit as exc:
            exit_code = int(exc.code) if exc.code is not None else 0
        else:
            exit_code = 0
    flagged = [str(warning) for warning in log]
    return exit_code, flagged


def _assert_no_coroutine_warning(flagged: list[str]) -> None:
    """Assert none of the recorded warnings is a coroutine-never-awaited warning."""
    for note in flagged:
        lowered = note.lower()
        assert "never awaited" not in lowered, (
            f"Coroutine was never awaited: {note}"
        )
        assert "coroutine" not in lowered, (
            f"Coroutine warning detected: {note}"
        )


def _build_module() -> MagicMock:
    """Return a MagicMock module that reaches ``RESET_STATE`` on the test command."""
    module = MagicMock()
    # ``get_spi_device_id`` / ``get_ce_number`` are read *without* awaiting in
    # ``test_hardware_impl``, so they must be synchronous getters. An ``AsyncMock``
    # would hand back a coroutine that never matches the target set.
    module.get_spi_device_id.return_value = 0
    module.get_ce_number.return_value = 0
    module.event_queue.put = AsyncMock()
    module.wait_for_event = AsyncMock(return_value=_SUCCESSFUL_EVENT)
    return module


def _build_mock_application() -> MagicMock:
    """Return a MagicMock ``Application`` that yields a valid radio config."""
    application = MagicMock()
    radio_config = MagicMock()
    radio_config.spi_device_id = 0
    radio_config.ce_number = 0
    application.get_assembly_config = AsyncMock(return_value=[radio_config])
    application.start = AsyncMock()
    application.stop = AsyncMock()
    application.module_manager.get_all_modules.return_value = [_build_module()]
    return application


class TestHardwareCommandAwaited:
    """``test hardware`` executes its coroutine end-to-end without a warning."""

    def test_hardware_awaited_no_runtime_warning(self) -> None:
        """``get_command(test_app)(["default"])`` transitions modules to RESET_STATE."""
        application = _build_mock_application()
        capture = StringIO()
        with patch(
            "pi_lora.cli.test.Application",
            return_value=application,
        ), patch("pi_lora.cli.test.console", Console(file=capture)):
            exit_code, flagged = _invoke_command(
                get_command(test_app),
                ["default"],
            )

        _assert_no_coroutine_warning(flagged)
        assert exit_code == 0, f"Expected exit 0, got {exit_code}: {capture.getvalue()}"
        assert (
            "All modules transitioned to RESET_STATE successfully" in capture.getvalue()
        ), capture.getvalue()
        application.start.assert_awaited_once_with(assembly_name="default")
        application.stop.assert_awaited_once()


class TestListAssembliesCommandAwaited:
    """``config list-assemblies`` executes its coroutine end-to-end without a warning."""

    def test_list_assemblies_awaited_no_runtime_warning(self) -> None:
        """``get_command(config_app)(["list-assemblies"])`` echoes the assembly name."""
        application = MagicMock()
        application.list_assemblies = AsyncMock(
            return_value=[{"assembly_name": "default"}],
        )
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        capture = StringIO()
        sys.stdout = capture
        sys.stderr = capture
        try:
            with patch(
                "pi_lora.cli.config.Application",
                return_value=application,
            ):
                exit_code, flagged = _invoke_command(
                    get_command(config_app),
                    ["list-assemblies"],
                )
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr

        _assert_no_coroutine_warning(flagged)
        assert exit_code == 0
        assert "default" in capture.getvalue()
        application.list_assemblies.assert_awaited_once()


class TestShowConfigCommandAwaited:
    """``config show-config`` executes its coroutine end-to-end without a warning."""

    def test_show_config_awaited_no_runtime_warning(self) -> None:
        """``get_command(config_app)(["show-config", "default"])`` echoes RFM95."""
        application = MagicMock()
        result = MagicMock()
        result.module_name = "lora_pi_434_868"
        result.spi_device_id = 0
        result.ce_number = 0
        result.device_name = "RFM95"
        application.get_assembly_config = AsyncMock(return_value=result)
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        capture = StringIO()
        sys.stdout = capture
        sys.stderr = capture
        try:
            with patch(
                "pi_lora.cli.config.Application",
                return_value=application,
            ):
                exit_code, flagged = _invoke_command(
                    get_command(config_app),
                    ["show-config", "default"],
                )
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr

        _assert_no_coroutine_warning(flagged)
        assert exit_code == 0
        assert "RFM95" in capture.getvalue()
        application.get_assembly_config.assert_awaited_once()


class TestInvalidAssemblyNoCoroutineWarning:
    """The invalid-assembly path exits cleanly without a coroutine warning."""

    def test_invalid_assembly_exits_without_runtime_warning(self) -> None:
        """``get_command(config_app)(["show-config", "nonexistent"])`` exits with code 1."""
        application = MagicMock()
        application.get_assembly_config = AsyncMock(
            side_effect=AssemblyNotFoundError("nonexistent"),
        )
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        capture = StringIO()
        sys.stdout = capture
        sys.stderr = capture
        try:
            with patch(
                "pi_lora.cli.config.Application",
                return_value=application,
            ):
                exit_code, flagged = _invoke_command(
                    get_command(config_app),
                    ["show-config", "nonexistent"],
                )
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr

        _assert_no_coroutine_warning(flagged)
        assert exit_code == 1
        assert "nonexistent" in capture.getvalue()


class TestCheckHardwareSyncStillWorks:
    """The synchronous ``check-hardware`` sub-app still executes under AsyncTyper."""

    def test_detect_modules_sync_exit_zero(self) -> None:
        """``get_command(check_hardware_app)(["detect-modules"])`` reports hardware."""
        detector = MagicMock()
        detector.detect_modules = MagicMock(
            return_value=[{"ce_pin": 0, "module_type": "rfm95w"}],
        )
        _old_stdout = sys.stdout
        _old_stderr = sys.stderr
        capture = StringIO()
        sys.stdout = capture
        sys.stderr = capture
        try:
            with patch(
                "pi_lora.cli.check_hardware.LoRaModuleDetector",
                return_value=detector,
            ):
                exit_code, flagged = _invoke_command(
                    get_command(check_hardware_app),
                    ["detect-modules"],
                )
        finally:
            sys.stdout = _old_stdout
            sys.stderr = _old_stderr

        _assert_no_coroutine_warning(flagged)
        assert exit_code == 0
        assert "Hardware Detection Results:" in capture.getvalue()


if __name__ == "__main__":
    import sys as _sys

    exit_code = pytest.main([__file__, "-v"])
    _sys.exit(exit_code)
