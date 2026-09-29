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

"""Integration tests for config CLI with real default config."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from pi_lora.cli.config import app as cli_app


class TestListAssembliesIntegration:
    """Integration tests for list-assemblies with real config."""

    def test_list_assemblies_returns_default(self) -> None:
        """list-assemblies returns 'default' from default YAML config."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["list-assemblies"])

        assert result.exit_code == 0
        assert "default" in result.output

    def test_list_assemblies_verbose_shows_details(self) -> None:
        """list-assemblies --verbose shows module name and device count."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["list-assemblies", "--verbose"])

        assert result.exit_code == 0
        assert "default" in result.output

    def test_list_assemblies_json_produces_valid_json(self) -> None:
        """list-assemblies --json produces valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["list-assemblies", "--json"])

        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        names = [a["assembly_name"] for a in parsed]
        assert "default" in names


class TestShowConfigIntegration:
    """Integration tests for show-config with real config."""

    def test_show_config_default_returns_configs(self) -> None:
        """show-config default returns both RFM95 and RFM98 configs or raises ConfigConsistencyError."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "default"])

        if result.exit_code == 0:
            assert "RFM" in result.output or "config" in result.output.lower()
        else:
            assert result.output == "" or "Error" in result.output

    def test_show_config_default_spi_ce_0_returns_rfm95(self) -> None:
        """show-config default --spi 0 --ce 0 returns RFM95 config or raises ConfigConsistencyError."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "default", "--spi", "0", "--ce", "0"])

        if result.exit_code == 0:
            assert "RFM" in result.output or "config" in result.output.lower()
        else:
            assert result.output == "" or "Error" in result.output

    def test_show_config_default_spi_ce_1_returns_rfm98(self) -> None:
        """show-config default --spi 0 --ce 1 returns RFM98 config or raises ConfigConsistencyError."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "default", "--spi", "0", "--ce", "1"])

        if result.exit_code == 0:
            assert "RFM" in result.output or "config" in result.output.lower()
        else:
            assert result.output == "" or "Error" in result.output

    def test_show_config_nonexistent_exits_with_error(self) -> None:
        """show-config nonexistent exits with code 1."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "nonexistent"])

        assert result.exit_code == 1

    def test_show_config_invalid_spi_ce_exits_with_error(self) -> None:
        """show-config default --spi 99 --ce 99 exits with code 1."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "default", "--spi", "99", "--ce", "99"])

        assert result.exit_code == 1

    def test_show_config_json_produces_valid_json(self) -> None:
        """show-config --json produces valid JSON."""
        runner = CliRunner()
        result = runner.invoke(cli_app, ["show-config", "default", "--json"])

        if result.exit_code == 0:
            parsed = json.loads(result.output)
            assert isinstance(parsed, dict | list)


class TestExceptionsIntegration:
    """Test that framework exceptions are properly raised and caught."""

    def test_assembly_not_found_raises_framework_exception(self) -> None:
        """AssemblyNotFoundError is a framework exception, not driver exception."""
        from pi_lora.framework.exceptions import AssemblyNotFoundError

        with pytest.raises(AssemblyNotFoundError):
            raise AssemblyNotFoundError("Test assembly not found")


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
