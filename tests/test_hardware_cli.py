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

"""CLI tests for the async ``hardware`` command in ``src/pi_lora/cli/test.py``.

The ``hardware`` command is an *async* Typer command. ``typer.testing.CliRunner``
does not await async commands (the coroutine is never run), so these tests invoke
``test_hardware`` directly with ``asyncio`` semantics, patching ``Application``
and the module-level ``rich.console`` so rich output is captured for assertions.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer
from rich.console import Console

import pi_lora.cli.test as _test_cmd
from pi_lora.framework.events import (
    EventType,
    ModuleEvent,
    StateChangeEvent,
)
from pi_lora.framework.exceptions import (
    AssemblyNotFoundError,
    DeviceAttachmentNotFoundError,
)
from pi_lora.types import StateBits

_SUCCESSFUL_EVENT: ModuleEvent[StateChangeEvent] = ModuleEvent(
    event_type=EventType.STATE_CHANGE,
    payload=StateChangeEvent(new_state=StateBits.RESET_STATE, reason="test_hardware_command"),
)


def _build_mock_application() -> MagicMock:
    """Return a MagicMock Application with awaitable ``start`` / ``stop``."""
    app = MagicMock()
    app.start = AsyncMock()
    app.stop = AsyncMock()
    return app


def _build_module(wait_result: Any) -> MagicMock:
    """Return a MagicMock module whose identity getters resolve synchronously and
    whose ``event_queue.put`` / ``wait_for_event`` are awaitable.

    ``test_hardware`` calls ``module.get_spi_device_id()`` / ``get_ce_number()``
    without awaiting them, so the module must expose those as synchronous getters.
    An ``AsyncMock`` would return a coroutine from those calls, which never matches
    the target set and silently yields an empty module list.
    """
    module = MagicMock()
    module.event_queue.put = AsyncMock()
    module.wait_for_event = AsyncMock(return_value=wait_result)
    return module


def _build_radio_config(spi: int, ce: int) -> MagicMock:
    """Return a MagicMock RadioInstanceConfig with the given SPI/CE slot."""
    cfg = MagicMock()
    cfg.spi_device_id = spi
    cfg.ce_number = ce
    return cfg


async def _run_hardware(
    capture: StringIO,
    mock_application: MagicMock,
    **kwargs: Any,
) -> int:
    """Invoke ``test_hardware_impl`` directly with a mocked Application.

    Patches ``pi_lora.cli.test.Application`` (returning ``mock_application``) and
    the module-level ``console`` so rich output is captured into ``capture``.
    Returns the exit code the command produced (0 on success, 1 on error).

    ``test_hardware`` is a sync Typer wrapper around the ``test_hardware_impl``
    async implementation, so ``asyncio.run()`` cannot be called from within
    pytest-asyncio's running event loop. The body is exercised by calling
    ``test_hardware_impl`` directly after resolving its ``None`` defaults.
    ``typer.Exit`` in the current Click version carries no ``code`` attribute, so
    the exit code is inferred from the captured output (the success message is
    only printed on a full transition).
    """
    resolved: dict[str, Any] = dict(kwargs)
    resolved.setdefault("spi", None)
    resolved.setdefault("ce", None)
    resolved.setdefault("config_file", None)
    with patch("pi_lora.cli.test.Application", return_value=mock_application), patch(
        "pi_lora.cli.test.console", Console(file=capture)
    ):
        try:
            await _test_cmd.test_hardware_impl(**resolved)
        except typer.Exit:
            output = capture.getvalue()
            return (
                0
                if "All modules transitioned to RESET_STATE successfully" in output
                else 1
            )
    return 0


# ---------------------------------------------------------------------------
# Test 1 -- Successful RESET_STATE transition
# ---------------------------------------------------------------------------

class TestHardwareResetStateSuccess:
    """Phase 2, test 1: a valid StateChangeEvent with new_state=RESET_STATE."""

    @pytest.mark.asyncio
    async def test_reset_state_transition_success(self) -> None:
        """Run ``hardware default`` when the module reaches RESET_STATE.

        Verify exit code 0, the success message, ``start()`` awaited with
        ``assembly_name="default"``, and ``stop()`` awaited exactly once.
        """
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(_SUCCESSFUL_EVENT)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="default"
        )

        assert exit_code == 0, f"Expected exit 0, got {exit_code}: {capture.getvalue()}"
        assert (
            "All modules transitioned to RESET_STATE successfully" in capture.getvalue()
        )
        mock_application.start.assert_awaited_once_with(assembly_name="default")
        mock_application.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 2 -- Per-module timeout
# ---------------------------------------------------------------------------

class TestHardwareTimeout:
    """Phase 2, test 2: ``wait_for_event`` returns None (timeout)."""

    @pytest.mark.asyncio
    async def test_per_module_timeout(self) -> None:
        """Run ``hardware default`` when a module never reaches RESET_STATE.

        Verify exit code 1, the timeout message, and ``stop()`` awaited once.
        """
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(None)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="default"
        )

        assert exit_code == 1, f"Expected exit 1, got {exit_code}: {capture.getvalue()}"
        assert "did not reach RESET_STATE" in capture.getvalue()
        mock_application.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 3 -- AssemblyNotFoundError propagation
# ---------------------------------------------------------------------------

class TestHardwareAssemblyNotFoundError:
    """Phase 2, test 3: get_assembly_config raises AssemblyNotFoundError."""

    @pytest.mark.asyncio
    async def test_assembly_not_found_propagates(self) -> None:
        """Run ``hardware nonexistent`` when the assembly is missing.

        Verify exit code 1, the error message, and ``stop()`` NOT awaited
        (the error is raised before ``start()``).
        """
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.side_effect = AssemblyNotFoundError(
            "default"
        )

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="nonexistent"
        )

        assert exit_code == 1, f"Expected exit 1, got {exit_code}: {capture.getvalue()}"
        assert "Error:" in capture.getvalue()
        mock_application.stop.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 4 -- DeviceAttachmentNotFoundError propagation
# ---------------------------------------------------------------------------

class TestHardwareDeviceAttachmentNotFoundError:
    """Phase 2, test 4: get_assembly_config raises DeviceAttachmentNotFoundError."""

    @pytest.mark.asyncio
    async def test_device_attachment_not_found_propagates(self) -> None:
        """Run ``hardware default --spi 99 --ce 99`` when no device matches.

        Verify exit code 1, the error message, and ``stop()`` NOT awaited.
        """
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.side_effect = (
            DeviceAttachmentNotFoundError("rfm95w", 99, 99)
        )

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="default", spi=99, ce=99
        )

        assert exit_code == 1, f"Expected exit 1, got {exit_code}: {capture.getvalue()}"
        assert "No device attachment found" in capture.getvalue()
        mock_application.stop.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test 5 -- --spi / --ce filter options
# ---------------------------------------------------------------------------

class TestHardwareFilterOptions:
    """Phase 2, test 5: --spi / --ce filters to matching modules only."""

    @pytest.mark.asyncio
    async def test_spi_ce_filter_selects_matching_modules(self) -> None:
        """Run ``hardware default --spi 0 --ce 0`` with two candidate modules.

        Verify exit code 0, the success message, the filter kwargs received by
        ``get_assembly_config``, and that only the matching module had
        ``wait_for_event`` called.
        """
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module_a = _build_module(_SUCCESSFUL_EVENT)
        module_a.get_spi_device_id.return_value = 0
        module_a.get_ce_number.return_value = 0
        module_b = _build_module(None)
        module_b.get_spi_device_id.return_value = 1
        module_b.get_ce_number.return_value = 1
        mock_application.module_manager.get_all_modules.return_value = [module_a, module_b]

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="default", spi=0, ce=0
        )

        assert exit_code == 0, f"Expected exit 0, got {exit_code}: {capture.getvalue()}"
        assert (
            "All modules transitioned to RESET_STATE successfully" in capture.getvalue()
        )
        kwargs = mock_application.get_assembly_config.call_args.kwargs
        assert kwargs.get("spi_device_id") == 0
        assert kwargs.get("ce_number") == 0
        module_a.wait_for_event.assert_awaited()
        module_b.wait_for_event.assert_not_awaited()


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
