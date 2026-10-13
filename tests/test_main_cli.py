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

"""CLI smoke tests for main.py — Phase 3 of remediation plan.

Verifies the Typer-based ``pi_lora`` entry-point exposes its three
subcommands (check-hardware, config, test) and that each sub-app's
``--help`` output renders correctly through the Typer CliRunner.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from pi_lora.cli.main import app as cli_app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invoke(*argv: str) -> Any:
    """Invoke the ``pi_lora`` CLI with the given argv and return the result."""
    runner = CliRunner()
    return runner.invoke(cli_app, list(argv))


# ---------------------------------------------------------------------------
# Test 1 — top-level --help lists all three subcommands
# ---------------------------------------------------------------------------

class TestMainHelp:
    """Phase 3, test 1 of the remediation plan."""

    def test_main_help_lists_all_subcommands(self) -> None:
        """Invoke ``pi_lora --help``.

        Verify:
          - Exit code is 0.
          - Output contains the three subcommand names:
            ``check-hardware``, ``config``, and ``test``.
        """
        result = _invoke("--help")

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "check-hardware" in result.output
        assert "config" in result.output
        assert "test" in result.output


# ---------------------------------------------------------------------------
# Test 2 — check-hardware detect-modules --help
# ---------------------------------------------------------------------------

class TestCheckHardwareHelp:
    """Phase 3, test 2 of the remediation plan."""

    def test_detect_modules_help(self) -> None:
        """Invoke ``pi_lora check-hardware detect-modules --help``.

        Verify:
          - Exit code is 0 (help output renders without error).
          - Output contains the command name ``detect-modules``.
        """
        result = _invoke("check-hardware", "detect-modules", "--help")

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "detect-modules" in result.output


# ---------------------------------------------------------------------------
# Test 3 — config list-assemblies --help
# ---------------------------------------------------------------------------

class TestConfigHelp:
    """Phase 3, test 3 of the remediation plan."""

    def test_list_assemblies_help(self) -> None:
        """Invoke ``pi_lora config list-assemblies --help``.

        Verify:
          - Exit code is 0.
          - Output contains the command name ``list-assemblies``.
        """
        result = _invoke("config", "list-assemblies", "--help")

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "list-assemblies" in result.output


# ---------------------------------------------------------------------------
# Test 4 — test hardware --help
# ---------------------------------------------------------------------------

class TestHardwareHelp:
    """Phase 3, test 4 of the remediation plan."""

    def test_hardware_help(self) -> None:
        """Invoke ``pi_lora test hardware --help``.

        Verify:
          - Exit code is 0.
          - Output contains the command name ``hardware``.
        """
        result = _invoke("test", "hardware", "--help")

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "hardware" in result.output


# ---------------------------------------------------------------------------
# Test 5 — no args shows help (no_args_is_help=True)
# ---------------------------------------------------------------------------

class TestNoArgsShowsHelp:
    """Phase 3, test 5 of the remediation plan."""

    def test_no_args_shows_help(self) -> None:
        """Invoke ``pi_lora`` with no arguments.

        Verify:
          - Exit code is 0 (``no_args_is_help=True``).
          - Output contains the top-level name ``pi_lora``.
          - Output lists the subcommands (check-hardware, config, test).
        """
        result = _invoke()

        # Typer's ``no_args_is_help=True`` path raises ``typer.Exit(code=2)``
        # when invoked with no argv, so ``exit_code`` is 2 (SystemExit) while
        # the help text and command list are still rendered.
        assert result.exit_code == 2, (
            f"Expected exit code 2 (help path) but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "pi_lora" in result.output
        assert "check-hardware" in result.output
        assert "config" in result.output
        assert "test" in result.output


# ---------------------------------------------------------------------------
# Test 6 — shared logging module is the single source of truth
# ---------------------------------------------------------------------------

class TestSharedLogging:
    """Phase 15: ``pi_lora.cli._logging`` owns the shared logging setup."""

    def test_setup_logging_exists_and_is_callable(self) -> None:
        """Import and call ``pi_lora.cli._logging.setup_logging`` directly.

        Verify the module exposes ``setup_logging`` and that calling it does
        not raise.
        """
        import pi_lora.cli._logging as _shared

        assert callable(_shared.setup_logging)
        assert callable(_shared._ensure_logged)
        _shared.setup_logging()
        _shared._ensure_logged()

    def test_check_hardware_ensure_logged_delegates(self) -> None:
        """``check_hardware._ensure_logged`` must delegate to the shared module."""
        import pi_lora.cli._logging as _shared
        import pi_lora.cli.check_hardware as _ch

        with patch.object(_shared, "setup_logging", autospec=True) as _spy:
            _ch._ensure_logged()
            _spy.assert_called_once()


if __name__ == "__main__":
    import sys

    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
