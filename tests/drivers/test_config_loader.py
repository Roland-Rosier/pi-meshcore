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

"""Tests for the RFM9x/SX127x config loader singleton cache and force_reload.

The loader exposes a module-level ``_config_cache`` that ``get_preloaded_config``
populates on first load and shares across concurrent calls. ``force_reload=True``
with an explicit ``config_path`` (Plan-19 Fix 4) updates that cache, so a
subsequent non-forced call returns the freshly loaded configuration instead of
the stale default. Module-level globals are read through the module object, never
through ``from``-imports, which would bind a stale value.
"""

import asyncio
from contextlib import suppress
from pathlib import Path

import pytest

import pi_lora.drivers.rfm9x_sx127x_config_loader as _loader
from pi_lora.drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig


def _is_present(value: object) -> bool:
    """Return whether the module-level global was populated (not None)."""
    return value is not None


def _device_name(config: Rfm9xSx127xConfig, key: str) -> str:
    """Return the device name for the given key as a concrete string."""
    return str(config.devices[key].name)


def _make_custom_yaml(device_name: str) -> str:
    """Return a minimal valid RFM9x/SX127x YAML root with the given device name."""
    return (
        "devices:\n"
        f"  rfm95:\n"
        f"    name: \"{device_name}\"\n"
        "    min_radio_freq_hz: 868000000\n"
        "    max_radio_freq_hz: 915000000\n"
        "families:\n"
        "  rfm9x:\n"
        f"    family_name: \"{device_name}X\"\n"
        f"    devices:\n"
        f"      - \"{device_name}\"\n"
        "    exclusions:\n"
        f"      - device_name: \"{device_name}\"\n"
        "        test_invalid_freq_hz: 434000000\n"
        "modules:\n"
        "  lora_pi_434_868:\n"
        "    module_name: \"lora_pi_434_868\"\n"
        f"    devices:\n"
        f"      - device_name: \"{device_name}\"\n"
        "        spi_device_id: 0\n"
        "        ce_number: 0\n"
    )


@pytest.mark.asyncio
async def test_config_loader_force_reload_updates_cache() -> None:
    """force_reload=True with a path updates the module-level cache (Fix 4)."""
    _loader._config_cache = None

    custom_yaml: str = _make_custom_yaml("CUSTOM95")
    custom_path: Path = Path("/tmp/sandbox/config_loader_custom.yaml")
    with suppress(OSError):
        custom_path.write_text(custom_yaml)

    try:
        loaded = await _loader.get_preloaded_config(
            force_reload=True,
            config_path=custom_path,
        )
    finally:
        with suppress(OSError):
            custom_path.unlink()

    assert isinstance(loaded, Rfm9xSx127xConfig)
    assert _loader._config_cache is loaded
    assert _device_name(loaded, "rfm95") == "CUSTOM95"  # type: ignore[unreachable]


@pytest.mark.asyncio
async def test_config_loader_concurrent_import_race() -> None:
    """100 concurrent default loads share one cached object (singleton)."""
    _loader._config_cache = None
    _loader._config_lock = None
    _loader._aiologic_module = None

    results = await asyncio.gather(
        *(_loader.get_preloaded_config() for _ in range(100))
    )

    assert len(results) == 100
    for result in results:
        assert result is results[0]

    assert _is_present(_loader._config_lock)
    assert _is_present(_loader._aiologic_module)


@pytest.mark.asyncio
async def test_config_loader_full_lifecycle() -> None:
    """Default load, force-reload custom, then non-force returns custom (Fix 4)."""
    _original_cache = _loader._config_cache
    _loader._config_cache = None

    try:
        first = await _loader.get_preloaded_config()
        assert isinstance(first, Rfm9xSx127xConfig)
        assert _device_name(first, "rfm95") == "RFM95"

        custom_yaml: str = _make_custom_yaml("CUSTOM95")
        custom_path: Path = Path("/tmp/sandbox/config_loader_custom.yaml")
        with suppress(OSError):
            custom_path.write_text(custom_yaml)

        try:
            second = await _loader.get_preloaded_config(
                force_reload=True,
                config_path=custom_path,
            )
        finally:
            with suppress(OSError):
                custom_path.unlink()

        third = await _loader.get_preloaded_config()

        assert third is second
        assert third != first
        assert _device_name(third, "rfm95") == "CUSTOM95"
    finally:
        _loader._config_cache = _original_cache
