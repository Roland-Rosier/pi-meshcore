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

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pi_lora.cli.config import app as cli_app


class TestListAssembliesCli:
    """Tests for the list-assemblies CLI command."""

    def test_list_assemblies_basic(self) -> None:
        """Verify list-assemblies returns assembly names."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_application.list_assemblies.return_value = [
            {"assembly_name": "default"},
        ]

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["list-assemblies"])

        assert result.exit_code == 0
        assert "default" in result.output

    def test_list_assemblies_verbose(self) -> None:
        """Verify list-assemblies --verbose shows module name and device count."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_application.list_assemblies.return_value = [
            {
                "assembly_name": "default",
                "module_name": "lora_pi_434_868",
                "device_count": 2,
            },
        ]

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["list-assemblies", "--verbose"])

        assert result.exit_code == 0
        assert "default" in result.output
        assert "lora_pi_434_868" in result.output

    def test_list_assemblies_json(self) -> None:
        """Verify list-assemblies --json outputs valid JSON."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_application.list_assemblies.return_value = [
            {"assembly_name": "default"},
        ]

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["list-assemblies", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert parsed[0]["assembly_name"] == "default"


class TestShowConfigCli:
    """Tests for the show-config CLI command."""

    def test_show_config_valid_assembly(self) -> None:
        """Verify show-config works with valid assembly name."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "lora_pi_434_868"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config.return_value = [mock_result]

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "default"])

        assert result.exit_code == 0

    def test_show_config_with_spi_ce(self) -> None:
        """Verify show-config --spi --ce filters to single device."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "lora_pi_434_868"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config.return_value = mock_result

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "default", "--spi", "0", "--ce", "0"])

        assert result.exit_code == 0
        mock_application.get_assembly_config.assert_called_with(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config_path=None,
        )

    def test_show_config_invalid_assembly(self) -> None:
        """Verify show-config exits with code 1 for invalid assembly."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_application.get_assembly_config.side_effect = Exception("Assembly not found")

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "nonexistent"])

        assert result.exit_code == 1

    def test_show_config_invalid_spi_ce(self) -> None:
        """Verify show-config exits with code 1 for invalid SPI/CE."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_application.get_assembly_config.side_effect = Exception("Device not found")

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "default", "--spi", "99", "--ce", "99"])

        assert result.exit_code == 1

    def test_show_config_json(self) -> None:
        """Verify show-config --json outputs valid JSON."""
        runner = CliRunner()

        mock_application = MagicMock()
        from dataclasses import dataclass

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
            excluded_frequencies_hz: tuple[int, ...] = (434000000,)
            dio_gpio_mappings: tuple[str, ...] = ("DIO0:GPIO25", "DIO5:GPIO24")
            antenna_type: str | None = "parabolic"
            antenna_gain_db: float | None = 25.0

        mock_result = MockRadioConfig()
        mock_application.get_assembly_config.return_value = mock_result

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "default", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)


class TestShowConfigCustomConfig:
    """Tests for custom config file option."""

    def test_show_config_with_custom_config(self) -> None:
        """Verify show-config --config loads custom config."""
        runner = CliRunner()

        mock_application = MagicMock()
        mock_result = MagicMock()
        mock_result.module_name = "test_module"
        mock_result.spi_device_id = 0
        mock_result.ce_number = 0
        mock_result.device_name = "RFM95"
        mock_application.get_assembly_config.return_value = [mock_result]

        with patch("pi_lora.cli.config.Application", return_value=mock_application):
            result = runner.invoke(cli_app, ["show-config", "default", "--config", "/path/to/config.yaml"])

        assert result.exit_code == 0
        call_kwargs = mock_application.get_assembly_config.call_args
        assert call_kwargs.kwargs.get("config_path") is not None


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
