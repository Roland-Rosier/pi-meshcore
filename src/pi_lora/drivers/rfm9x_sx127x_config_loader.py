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

"""Configuration loader for RFM9x/SX127x device configurations."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import aiologic
from pydantic import ValidationError
from ruamel.yaml import YAML

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    Rfm9xSx127xConfig,
    Rfm9xSx127xFamilyConfig,
)

# Default config resource path as configuration string (not magic).
_DEFAULT_CONFIG_RESOURCE: str = "pi_lora.drivers.configs:rfm9x_sx127x_config.yaml"

# Lazy singleton cache and lock.
_config_cache: Rfm9xSx127xConfig | None = None
_config_lock: aiologic.Lock = aiologic.Lock()


def _resolve_default_path() -> Path:
    """Resolve the default config path via importlib.resources from package data.

    Returns:
        The resolved Path to the default configuration YAML file.
    """
    pkg_name: str = _DEFAULT_CONFIG_RESOURCE.split(":")[0]
    resource_name: str = _DEFAULT_CONFIG_RESOURCE.split(":")[1]
    return Path(str(
        importlib.resources.files(pkg_name).joinpath(resource_name)
    ))


def load_config(
    config_path: Path | None = None,
    config_name: str | None = None,
) -> Rfm9xSx127xConfig:
    """Load and validate a full RFM9x/SX127x configuration.

    Args:
        config_path: Explicit YAML file path. Defaults to the built-in default.
        config_name: Name key to look up in the YAML (e.g., "devices", "families").

    Returns:
        Validated Rfm9xSx127xConfig instance.

    Raises:
        ValidationError: If the configuration data fails Pydantic validation.
        FileNotFoundError: If the config file does not exist.
        ValueError: If config_name is provided but not found in YAML.
    """
    path: Path = config_path or _resolve_default_path()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    yaml_instance: YAML = YAML(typ='rt')
    yaml_data: dict[str, object] = yaml_instance.load(path)
    if not isinstance(yaml_data, dict):
        raise ValueError("YAML root must be a mapping (dict).")

    try:
        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig.model_validate(yaml_data)
    except ValidationError as exc:
        raise exc

    if config_name is not None:
        key_map: dict[str, object] = {
            "devices": config.devices,
            "families": config.families,
            "modules": config.modules,
        }
        if config_name not in key_map:
            raise ValueError(
                f"config_name '{config_name}' not recognized. "
                f"Valid keys: {list(key_map.keys())}"
            )

    return config


def load_family_config(
    config_path: Path | None = None,
) -> Rfm9xSx127xFamilyConfig:
    """Load and validate a family-only configuration.

    Args:
        config_path: Explicit YAML file path. Defaults to the built-in default.

    Returns:
        Validated Rfm9xSx127xFamilyConfig instance.

    Raises:
        ValidationError: If the configuration data fails Pydantic validation.
        FileNotFoundError: If the config file does not exist.
    """
    path: Path = config_path or _resolve_default_path()
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    yaml_instance: YAML = YAML(typ='rt')
    yaml_data: dict[str, object] = yaml_instance.load(path)
    if "families" not in yaml_data:
        raise ValueError("YAML data missing 'families' key.")

    family_data: dict[str, object] = {"families": yaml_data["families"]}
    try:
        config: Rfm9xSx127xFamilyConfig = Rfm9xSx127xFamilyConfig.model_validate(family_data)
    except ValidationError as exc:
        raise exc

    return config


def get_preloaded_config(
    force_reload: bool = False,
    config_path: Path | None = None,
) -> Rfm9xSx127xConfig:
    """Return the pre-loaded default configuration with lazy singleton support.

    Args:
        force_reload: If True, forces re-reading from disk regardless of cache.
        config_path: If provided, bypasses cache and loads from this path.

    Returns:
        A validated Rfm9xSx127xConfig instance.
    """
    # Override path bypasses cache entirely.
    if config_path is not None:
        return load_config(config_path=config_path)

    # Force reload bypasses cache.
    if force_reload:
        return load_config()

    # Lazy singleton: load on first call, cache thereafter.
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    with _config_lock:
        if _config_cache is not None:
            return _config_cache  # type: ignore[unreachable]  # pragma: no cover
        _config_cache = load_config()
    return _config_cache
