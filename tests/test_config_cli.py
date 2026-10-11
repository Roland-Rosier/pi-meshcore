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

"""CLI tests for config.py — list-assemblies and show-config commands."""

from __future__ import annotations

import io
import json
import sys
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from pi_lora.cli.config import (
    list_assemblies,
    show_config,
)
from pi_lora.framework.exceptions import (
    AssemblyNotFoundError,
    DeviceAttachmentNotFoundError,
)


async def _invoke_cli(
    command: Any,
    mock_application: MagicMock,
    *args: Any,
    **kwargs: Any,
) -> tuple[str, int]:
    """Invoke an async CLI command directly with a mocked Application.

    ``typer.testing.CliRunner`` does not await async commands (the coroutine is
    never run), and the ``@app.command`` decorator injects ``typer.OptionInfo``
    for any option not supplied, so the command body is exercised by calling the
    command function directly with explicit option values after patching
    ``Application``. Rich/typer output is captured via ``sys.stdout`` swap and
    restored in a ``finally``. Returns ``(output, exit_code)``.
    """
    capture: io.StringIO = io.StringIO()
    _old_stdout: object = sys.stdout
    sys.stdout = capture
    exit_code: int = 0
    with patch("pi_lora.cli.config.Application", return_value=mock_application):
        try:
            await command(*args, **kwargs)
        except (SystemExit, typer.Exit) as exc:
            exit_code = getattr(exc, "code", 1)
        finally:
            sys.stdout = _old_stdout
    return capture.getvalue(), exit_code


class TestListAssembliesCli:
    """Tests for the list-assemblies CLI command."""

    @pytest.mark.asyncio
    async def test_list_assemblies_basic(self) -> None:
        """Verify list-assemblies returns assembly names."""
        mock_application = MagicMock()
        mock_application.list_assemblies = AsyncMock(return_value=[
            {"assembly_name": "default"},
        ])
        output, exit_code = await _invoke_cli(
            list_assemblies,
            mock_application,
            verbose=False,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 0
        assert "default" in output

    @pytest.mark.asyncio
    async def test_list_assemblies_verbose(self) -> None:
        """Verify list-assemblies --verbose shows module name and device count."""
        mock_application = MagicMock()
        mock_application.list_assemblies = AsyncMock(return_value=[
            {
                "assembly_name": "default",
                "module_name": "lora_pi_434_868",
                "device_count": 2,
            },
        ])
        output, exit_code = await _invoke_cli(
            list_assemblies,
            mock_application,
            verbose=True,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 0
        assert "default" in output
        assert "lora_pi_434_868" in output

    @pytest.mark.asyncio
    async def test_list_assemblies_json(self) -> None:
        """Verify list-assemblies --json outputs valid JSON."""
        mock_application = MagicMock()
        mock_application.list_assemblies = AsyncMock(return_value=[
            {"assembly_name": "default"},
        ])
        output, exit_code = await _invoke_cli(
            list_assemblies,
            mock_application,
            verbose=False,
            json_output=True,
            config_file=None,
        )
        assert exit_code == 0
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert parsed[0]["assembly_name"] == "default"


class TestShowConfigCli:
    """Tests for the show-config CLI command."""

    @pytest.mark.asyncio
    async def test_show_config_valid_assembly(self) -> None:
        """Verify show-config works with valid assembly name."""
        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "lora_pi_434_868"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config = AsyncMock(return_value=[mock_result])
        output, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "default",
            spi=None,
            ce=None,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 0
        assert "RFM95" in output

    @pytest.mark.asyncio
    async def test_show_config_with_spi_ce(self) -> None:
        """Verify show-config --spi --ce filters to single device."""
        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "lora_pi_434_868"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config = AsyncMock(return_value=[mock_result])
        output, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "default",
            spi=0,
            ce=0,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 0
        mock_application.get_assembly_config.assert_called_with(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config_path=None,
        )
        assert "RFM95" in output

    @pytest.mark.asyncio
    async def test_show_config_invalid_assembly(self) -> None:
        """Verify show-config exits with code 1 for invalid assembly."""
        mock_application = MagicMock()
        mock_application.get_assembly_config = AsyncMock(
            side_effect=AssemblyNotFoundError("test")
        )
        _, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "nonexistent",
            spi=None,
            ce=None,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_show_config_invalid_spi_ce(self) -> None:
        """Verify show-config exits with code 1 for invalid SPI/CE."""
        mock_application = MagicMock()
        mock_application.get_assembly_config = AsyncMock(
            side_effect=DeviceAttachmentNotFoundError("mod", 99, 99)
        )
        _, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "default",
            spi=99,
            ce=99,
            json_output=False,
            config_file=None,
        )
        assert exit_code == 1

    @pytest.mark.asyncio
    async def test_show_config_json(self) -> None:
        """Verify show-config --json outputs valid JSON."""
        mock_application = MagicMock()

        @dataclass
        class MockRadioConfig:
            module_name: str = "lora_pi_434_868"
            spi_device_id: int = 0
            ce_number: int = 0
            device_name: str = "RFM95"
            min_radio_freq_hz: int = 868000000
            max_radio_freq_hz: int = 915000000
            osc_freq_hz: int | None = 32000000
            family_name: str = "RFM9X"
            test_invalid_frequencies_hz: tuple[int, ...] = (434000000,)
            dio_gpio_mappings: tuple[str, ...] = ("DIO0:GPIO25", "DIO5:GPIO24")
            antenna_type: str | None = "parabolic"
            antenna_gain_db: float | None = 25.0

        mock_result = MockRadioConfig()
        mock_application.get_assembly_config = AsyncMock(return_value=mock_result)
        output, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "default",
            spi=None,
            ce=None,
            json_output=True,
            config_file=None,
        )
        assert exit_code == 0
        parsed = json.loads(output)
        assert isinstance(parsed, dict)


class TestShowConfigCustomConfig:
    """Tests for custom config file option."""

    @pytest.mark.asyncio
    async def test_show_config_with_custom_config(self) -> None:
        """Verify show-config --config loads custom config."""
        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "test_module"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config = AsyncMock(return_value=[mock_result])
        _, exit_code = await _invoke_cli(
            show_config,
            mock_application,
            "default",
            spi=None,
            ce=None,
            json_output=False,
            config_file="/path/to/config.yaml",
        )
        assert exit_code == 0
        call_kwargs = mock_application.get_assembly_config.call_args
        assert call_kwargs.kwargs.get("config_path") is not None


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
