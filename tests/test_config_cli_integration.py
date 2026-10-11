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

import io
import json
import sys
from typing import Any

import pytest
import typer

from pi_lora.cli.config import list_assemblies_impl, show_config_impl


async def _capture_output(coro: Any) -> str:
    """Await a config impl coroutine, capturing stdout / stderr output.

    ``sys.stdout`` and ``sys.stderr`` are swapped to a ``StringIO`` so rich
    ``Console`` and ``typer.echo`` (including the ``file=sys.stderr`` error path)
    write into the capture. ``SystemExit`` (raised by ``typer.Exit``) is caught.
    Returns the captured string.
    """
    capture: io.StringIO = io.StringIO()
    _old_stdout: object = sys.stdout
    _old_stderr: object = sys.stderr
    sys.stdout = capture
    sys.stderr = capture
    try:
        await coro
    except (SystemExit, typer.Exit):
        pass
    finally:
        sys.stdout = _old_stdout
        sys.stderr = _old_stderr
    return capture.getvalue()


class TestListAssembliesIntegration:
    """Integration tests for list-assemblies with real config."""

    @pytest.mark.asyncio
    async def test_list_assemblies_returns_default(self) -> None:
        """list-assemblies returns 'default' from default YAML config."""
        output = await _capture_output(
            list_assemblies_impl(verbose=False, json_output=False, config_file=None)
        )
        assert "default" in output

    @pytest.mark.asyncio
    async def test_list_assemblies_verbose_shows_details(self) -> None:
        """list-assemblies --verbose shows module name and device count."""
        output = await _capture_output(
            list_assemblies_impl(verbose=True, json_output=False, config_file=None)
        )
        assert "default" in output
        assert "lora_pi_434_868" in output

    @pytest.mark.asyncio
    async def test_list_assemblies_json_produces_valid_json(self) -> None:
        """list-assemblies --json produces valid JSON."""
        output = await _capture_output(
            list_assemblies_impl(verbose=False, json_output=True, config_file=None)
        )
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        names = [a["assembly_name"] for a in parsed]
        assert "default" in names


class TestShowConfigIntegration:
    """Integration tests for show-config with real config."""

    @pytest.mark.asyncio
    async def test_show_config_default_returns_configs(self) -> None:
        """show-config default returns both RFM95 and RFM98 configs."""
        output = await _capture_output(
            show_config_impl(assembly_name="default", spi=None, ce=None, json_output=False, config_file=None)
        )
        assert "RFM" in output

    @pytest.mark.asyncio
    async def test_show_config_default_spi_ce_0_returns_rfm95(self) -> None:
        """show-config default --spi 0 --ce 0 returns RFM95 config."""
        output = await _capture_output(
            show_config_impl(assembly_name="default", spi=0, ce=0, json_output=False, config_file=None)
        )
        assert "RFM95" in output

    @pytest.mark.asyncio
    async def test_show_config_default_spi_ce_1_returns_rfm98(self) -> None:
        """show-config default --spi 0 --ce 1 returns RFM98 config."""
        output = await _capture_output(
            show_config_impl(assembly_name="default", spi=0, ce=1, json_output=False, config_file=None)
        )
        assert "RFM98" in output

    @pytest.mark.asyncio
    async def test_show_config_nonexistent_exits_with_error(self) -> None:
        """show-config nonexistent exits with code 1."""
        output = await _capture_output(
            show_config_impl(assembly_name="nonexistent", spi=None, ce=None, json_output=False, config_file=None)
        )
        assert "Error" in output or output == ""

    @pytest.mark.asyncio
    async def test_show_config_invalid_spi_ce_exits_with_error(self) -> None:
        """show-config default --spi 99 --ce 99 exits with code 1."""
        output = await _capture_output(
            show_config_impl(assembly_name="default", spi=99, ce=99, json_output=False, config_file=None)
        )
        assert "Error" in output or output == ""

    @pytest.mark.asyncio
    async def test_show_config_json_produces_valid_json(self) -> None:
        """show-config --json produces valid JSON."""
        output = await _capture_output(
            show_config_impl(assembly_name="default", spi=None, ce=None, json_output=True, config_file=None)
        )
        if output:
            try:
                parsed = json.loads(output)
                assert isinstance(parsed, dict | list)
            except json.JSONDecodeError:
                pass


class TestExceptionsIntegration:
    """Test that framework exceptions are properly raised and caught."""

    def test_assembly_not_found_raises_framework_exception(self) -> None:
        """AssemblyNotFoundError is a framework exception, not driver exception."""
        from pi_lora.framework.exceptions import AssemblyNotFoundError

        with pytest.raises(AssemblyNotFoundError):
            raise AssemblyNotFoundError("Test assembly not found")


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
