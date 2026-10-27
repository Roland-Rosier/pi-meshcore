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

import asyncio
import importlib.resources
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ruamel.yaml import YAML

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    Rfm9xSx127xConfig,
    Rfm9xSx127xFamilyConfig,
)

# Default config resource path as configuration string (not magic).
_DEFAULT_CONFIG_RESOURCE: str = "pi_lora.drivers.configs:rfm9x_sx127x_config.yaml"

# GUARD LOCK: Use stdlib asyncio.Lock for ONE-TIME initialization guard ONLY.
# Rationale:
# - This project uses aiologic for ALL runtime synchronization (see locks.py, scheduler.py, application.py)
# - The guard lock _init_lock is used ONLY during first call to get_preloaded_config()
#   to serialize creation of the real aiologic.Lock (_config_lock)
# - After initialization, _init_lock is NEVER used again
# - Creating aiologic.Lock at module level would import aiologic at import time,
#   breaking BUG-4 fix (sync CLI load_config/load_family_config must work without aiologic)
# - asyncio.Lock is safe to create at module level (no running loop required in Python 3.11+)
# - This is a deliberate, well-contained exception to the "aiologic-only" rule
_init_lock: asyncio.Lock = asyncio.Lock()
_config_cache: Rfm9xSx127xConfig | None = None

if TYPE_CHECKING:
    import aiologic

    _ConfigLockType = aiologic.Lock
    _AiologicModuleType = types.ModuleType
else:
    _ConfigLockType = Any
    _AiologicModuleType = Any

_config_lock: _ConfigLockType | None = None
_aiologic_module: _AiologicModuleType | None = None


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
        pydantic.ValidationError: If the configuration data fails Pydantic validation.
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

    config: Rfm9xSx127xConfig = Rfm9xSx127xConfig.model_validate(yaml_data)

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
        if config_name == "devices":
            return Rfm9xSx127xConfig(devices=config.devices)
        if config_name == "modules":
            return Rfm9xSx127xConfig(modules=config.modules)
        return Rfm9xSx127xConfig(families=config.families)

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
        pydantic.ValidationError: If the configuration data fails Pydantic validation.
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
    config: Rfm9xSx127xFamilyConfig = Rfm9xSx127xFamilyConfig.model_validate(family_data)

    return config


async def get_preloaded_config(
    force_reload: bool = False,
    config_path: Path | None = None,
) -> Rfm9xSx127xConfig:
    """Return the pre-loaded default configuration with lazy singleton support.

    This coroutine guards the singleton cache with an ``aiologic.Lock`` so the
    first load is performed safely under concurrency.

    Args:
        force_reload: If True, forces re-reading from disk regardless of cache.
        config_path: If provided, bypasses cache and loads from this path.

    Returns:
        A validated Rfm9xSx127xConfig instance.

    .. note::
        Unlike the sync ``load_config()``, this async coroutine updates the
        internal cache when ``force_reload=True``, so subsequent calls without
        ``force_reload`` return the freshly loaded config.
    """
    global _config_cache
    global _config_lock
    global _aiologic_module

    # Override path bypasses cache entirely.
    if config_path is not None:
        return load_config(config_path=config_path)

    # Fast path: cache hit and no forced reload.
    if _config_cache is not None and not force_reload:
        return _config_cache

    # Lazy aiologic import and lock initialisation (BUG-4 / Plan-11 Option A):
    # aiologic is only required for this async singleton path, so it is imported
    # here rather than at module scope to keep the sync public functions
    # (load_config / load_family_config) free of the dependency.
    #
    # Double-checked locking (FIX CR-1 / Plan-12 Option A1): the initial ``None``
    # guard is race-free because it is executed under the module-level
    # ``_init_lock`` before re-checking ``_config_lock`` inside the lock, so only
    # one coroutine ever creates the ``aiologic.Lock`` and all callers share it.
    # PATTERN (per Plan-14 R-3 / locks.py): import aiologic FIRST outside guard,
    # then initialize lock INSIDE guard. This separates import failures from
    # lock initialization and caches the module for subsequent calls.
    if _aiologic_module is None:
        try:
            import aiologic
            _aiologic_module = aiologic
        except ImportError as e:
            raise ImportError(
                "aiologic is required for config loading. Install with: pip install aiologic"
            ) from e

    if _config_lock is None:
        async with _init_lock:  # Race-free guard
            if _config_lock is None:  # Re-check inside lock
                _config_lock = _aiologic_module.Lock()

    async with _config_lock:
        # Double-checked locking: re-verify inside the lock to protect ALL cache mutations.
        if _config_cache is not None and not force_reload:
            return _config_cache
        _config_cache = load_config()
        return _config_cache
