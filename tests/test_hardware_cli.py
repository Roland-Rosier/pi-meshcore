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
    app.get_assembly_config = AsyncMock()
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

        Verify exit code 1, the error message, and ``stop()`` awaited once.
        NR-4 wraps the whole body in a ``try`` whose ``finally`` always calls
        ``application.stop()``, so cleanup runs even when the error fires before
        ``start()``.
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
        mock_application.stop.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test 4 -- DeviceAttachmentNotFoundError propagation
# ---------------------------------------------------------------------------

class TestHardwareDeviceAttachmentNotFoundError:
    """Phase 2, test 4: get_assembly_config raises DeviceAttachmentNotFoundError."""

    @pytest.mark.asyncio
    async def test_device_attachment_not_found_propagates(self) -> None:
        """Run ``hardware default --spi 99 --ce 99`` when no device matches.

        Verify exit code 1, the error message, and ``stop()`` awaited once.
        NR-4's ``finally`` always calls ``application.stop()``.
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
        mock_application.stop.assert_awaited_once()


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


# ---------------------------------------------------------------------------
# Phase 6 & 7 — narrowed except + module-level traceback import
# ---------------------------------------------------------------------------

class TestHardwareRuntimeError:
    """NR-4: a non-``typer.Exit`` exception from ``Application.start`` is caught by
    the ``except BaseException`` guard, cleanup runs, and the exception propagates."""

    @pytest.mark.asyncio
    async def test_runtime_error_propagates(self) -> None:
        """When ``Application.start`` raises RuntimeError, NR-4 lets it propagate
        after the ``finally`` cleanup runs."""
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(_SUCCESSFUL_EVENT)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]
        mock_application.start.side_effect = RuntimeError("startup failed")

        with (
            patch("pi_lora.cli.test.Application", return_value=mock_application),
            patch("pi_lora.cli.test.console", Console(file=capture)),
            pytest.raises(RuntimeError),
        ):
            await _test_cmd.test_hardware_impl(assembly_name="default")
        mock_application.stop.assert_awaited_once()


class TestHardwareHardwareException:
    """NR-4: ``OSError``, ``TimeoutError`` and ``ConnectionError`` raised by
    ``Application.start`` are caught by the ``except BaseException`` guard, cleanup
    runs, and the exception propagates out of ``test_hardware_impl``.

    ``_SUCCESSFUL_EVENT`` is set so the code path reaches ``start()`` before the
    exception fires; the exception short-circuits the transition block.
    """

    @pytest.mark.parametrize(
        "exc",
        [
            OSError("hardware init failed"),
            TimeoutError("event loop timeout"),
            ConnectionError("radio bus connection lost"),
        ],
    )
    @pytest.mark.asyncio
    async def test_hardware_exceptions_propagate(self, exc: OSError) -> None:
        """Each hardware startup exception propagates after the cleanup runs."""
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(_SUCCESSFUL_EVENT)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]
        mock_application.start.side_effect = exc

        with (
            patch("pi_lora.cli.test.Application", return_value=mock_application),
            patch("pi_lora.cli.test.console", Console(file=capture)),
            pytest.raises((OSError, TimeoutError, ConnectionError)),
        ):
            await _test_cmd.test_hardware_impl(assembly_name="default")
        mock_application.stop.assert_awaited_once()


class TestHardwareGenericException:
    """NR-4: any ``Exception`` raised by ``Application.start`` (here ``IndexError``)
    is caught by the ``except BaseException`` guard, cleanup runs, and the exception
    propagates out of ``test_hardware_impl``."""

    @pytest.mark.asyncio
    async def test_generic_exception_propagates(self) -> None:
        """A generic startup exception (``IndexError``) propagates after cleanup."""
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(_SUCCESSFUL_EVENT)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]
        mock_application.start.side_effect = IndexError("unexpected startup failure")

        with (
            patch("pi_lora.cli.test.Application", return_value=mock_application),
            patch("pi_lora.cli.test.console", Console(file=capture)),
            pytest.raises(IndexError),
        ):
            await _test_cmd.test_hardware_impl(assembly_name="default")
        mock_application.stop.assert_awaited_once()


class TestTracebackModuleLevel:
    """NR-4: ``traceback`` is NOT imported at module level in ``pi_lora.cli.test``.
    The ``finally`` cleanup path does not surface a traceback message, so no
    module-level ``traceback`` import is required."""

    def test_traceback_absent_from_module_namespace(self) -> None:
        """``pi_lora.cli.test`` does not expose ``traceback`` in its namespace."""
        import pi_lora.cli.test as _test_cmd

        assert not hasattr(_test_cmd, "traceback")
        assert "traceback" not in _test_cmd.__dict__


# ---------------------------------------------------------------------------
# Phase 2 — defensive module-manager NoneType check
# ---------------------------------------------------------------------------

class TestHardwareModuleManagerNone:
    """Phase 2, test 6: ``application.module_manager`` is None after ``start()``.

    Verify exit code 1, the "Module manager is unavailable" message, and that
    ``stop()`` still runs exactly once (the resource-leak fix).
    """

    @pytest.mark.asyncio
    async def test_module_manager_unavailable_exits(self) -> None:
        """Run ``hardware default`` when the module manager is None after start."""
        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        mock_application.module_manager = None

        exit_code = await _run_hardware(
            capture, mock_application, assembly_name="default"
        )

        assert exit_code == 1, f"Expected exit 1, got {exit_code}: {capture.getvalue()}"
        assert "Module manager is unavailable" in capture.getvalue()
        mock_application.stop.assert_awaited_once()


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
