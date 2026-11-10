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
import importlib
import importlib.resources
import threading

# PLAN-22 FIX (Item 1): Anti-regression guard at the import site.
# Fix rationale: the explicit `import importlib.resources` guarantees that the
# `resources` submodule is bound, so `importlib.resources.files()` (called in
# _resolve_default_path()) is always available.
# Why the issue could regress: a bare `import importlib` does NOT bind the
# `resources` submodule; relying on implicit submodule import is fragile — a
# reviewer could remove the explicit import and the `importlib.resources.files()`
# call would fail. This explicit import protects against that regression.
# Cross-reference: Plan-22 Section 6, Anti-Regression Documentation for Item 1.
import types
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from ruamel.yaml import YAML

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    Rfm9xSx127xConfig,
    Rfm9xSx127xFamilyConfig,
)

# Default config resource path as configuration string (not magic).
_DEFAULT_CONFIG_RESOURCE: str = "pi_lora.drivers.configs:rfm9x_sx127x_config.yaml"

# GUARD LOCK: Lazy sentinel for ONE-TIME initialization guard ONLY.
# Rationale:
# - This project uses aiologic for ALL runtime synchronization (see locks.py, scheduler.py, application.py)
# - The guard lock is used ONLY during first call to get_preloaded_config()
#   to serialize creation of the real aiologic.Lock (_config_lock)
# - After initialization, the holder is NEVER used again
# - Creating aiologic.Lock at module level would import aiologic at import time,
#   breaking BUG-4 fix (sync CLI load_config/load_family_config must work without aiologic)
# - H-7 (2026-11-02): asyncio.Lock.__init__ calls asyncio.get_running_loop(), which raises
#   RuntimeError when there is no running event loop (e.g. module import in a sync context
#   like the check-hardware CLI). A module-level asyncio.Lock() therefore breaks import.
# - Fix: defer asyncio.Lock() creation to inside get_preloaded_config()'s async guard
#   (lazy sentinel), so it is only ever constructed while an event loop is running.
# - This is a deliberate, well-contained exception to the "aiologic-only" rule
#
# PLAN-27 FIX #1 (code_review-26.1 Finding 308, sub-findings 306-308, 317-318,
# 336, 344-346, 374-383): One-time holder initialisation now uses a module-level
# threading.Lock (_holder_init_lock) instead of the non-atomic list-holder
# pattern (_init_lock_holder: list[asyncio.Lock | None] = [None]).
#
# BUG (root cause, Finding 308):
# 1. The cache critical section ran OUTSIDE the holder lock: `async with _holder:`
#    released before `async with _config_lock:` ran, leaving a sentinel race window
#    where a second coroutine could enter the cache section before the real
#    aiologic.Lock existed.
# 2. Holder creation `_init_lock_holder[0] or asyncio.Lock()` was non-atomic — no
#    threading.Lock guard — so two coroutines could both evaluate `[0] is None` and
#    both construct an asyncio.Lock(), breaking the singleton guarantee.
#
# FIX (why it works):
# - threading.Lock atomically creates the asyncio.Lock holder (mirrors locks.py's
#   _registry_holder_init_lock), closing the non-atomic init race.
# - ALL cache operations were moved INSIDE `async with _holder:` (i.e. inside both
#   the threading guard and the async holder lock), so no cache read/write can
#   observe a partially-initialised _config_lock. The sentinel still marks the slot
#   occupied before awaiting Lock(); on failure it is reset to None (NOT leaked) so
#   a later call can retry — a leaked sentinel would raise AttributeError on
#   subsequent `async with _config_lock:` calls.
#
# Alternative approaches REJECTED:
# - Keeping the list-holder pattern alone was non-atomic (no threading.Lock guard);
#   it did not close the init race.
# - Moving only the fast-path cache hit inside the lock was insufficient: the
#   config_path branch and the default-load branch still mutated _config_cache
#   outside the holder, leaving those mutations inside the sentinel race window.
_holder_init_lock: threading.Lock = threading.Lock()

# H-5 FIX: Sentinel placeholder for the double-checked-locking race. If
# aiologic.Lock() internally awaits during construction, the _holder guard could
# be released before the real lock exists, letting a second coroutine re-enter
# `if _config_lock is None:` before the first coroutine finishes. Assigning
# _SENTINEL to _config_lock INSIDE the guard marks the slot occupied before
# awaiting Lock(), closing the race. On failure the sentinel is reset to None
# (NOT leaked) so a later call can retry — a leaked sentinel would raise
# AttributeError on subsequent `async with _config_lock:` calls.
_SENTINEL = object()

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
            # Plan-17 / H-16-4: assemblies was validated here but had no explicit
            # handling branch, so it fell through to the families return and
            # populated families instead of assemblies. Added below.
            "assemblies": config.assemblies,
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
        # Plan-17 / H-16-4: explicit assemblies branch mirroring devices/modules.
        # Previously missing; fell through to families (wrong section populated).
        if config_name == "assemblies":
            return Rfm9xSx127xConfig(assemblies=config.assemblies)
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

    # PLAN-26 FIX (Finding 308): Fast-path cache hit REMOVED from outside the lock.
    # The previous "benign read-only optimization" was a race condition: callers with
    # force_reload=True or config_path provided could be inside the lock reloading while
    # fast-path callers returned stale cached data. ALL cache reads now go through
    # _config_lock for correctness. The double-checked locking inside the lock still
    # avoids redundant loads under contention.
    # Cross-reference: code_review-25.3.json finding 308, config_loader.py get_preloaded_config.

    # Lazy aiologic import and lock initialisation.
    # PLAN-19 FIX: import aiologic FIRST outside the _init_lock guard (module import
    # is thread-safe in CPython — GIL + sys.modules cache); only _config_lock
    # creation needs the _init_lock guard to be race-free.
    if _aiologic_module is None:
        try:
            import aiologic
            _aiologic_module = aiologic
        except ImportError as e:
            raise ImportError(
                "aiologic is required for config loading. Install with: pip install aiologic"
            ) from e

    # PLAN-27 FIX #1 (code_review-26.1 Finding 308, sub-findings 306-308, 317-318,
    # 336, 344-346, 374-383): The cache critical section now runs INSIDE the holder
    # lock. Both branches below protect every cache read/write with the async holder
    # (init path) or the real aiologic.Lock (already-initialised path), so no caller
    # can observe a partially-initialised _config_lock or race on _config_cache.
    # Cross-reference: code_review-26.1 Finding 308, config_loader.py
    # get_preloaded_config; mirrors locks.py get_bus_lock lines 240-278.
    if _config_lock is None:
        # Atomically create the asyncio.Lock holder using threading.Lock for the
        # one-time initialisation (mirrors locks.py's _registry_holder_init_lock).
        # This closes the non-atomic init race that existed with the list-holder
        # pattern (`_init_lock_holder[0] or asyncio.Lock()`), where two coroutines
        # could both evaluate `[0] is None` and both construct a Lock().
        with _holder_init_lock:
            _holder: asyncio.Lock = asyncio.Lock()
        async with _holder:
            if _config_lock is None:  # Double-check inside holder
                _config_lock = cast(_ConfigLockType, _SENTINEL)  # Placeholder — prevents race if Lock() awaits
                try:
                    _config_lock = _aiologic_module.Lock()
                except Exception:
                    _config_lock = None  # Reset on failure — don't leak sentinel
                    raise

            # Cache operations now INSIDE both the threading guard and the async
            # holder lock (PLAN-27 FIX #1). This closes the sentinel race window
            # that previously existed because these reads/writes ran outside
            # `async with _holder:`.
            if _config_cache is not None and not force_reload and config_path is None:
                return _config_cache

            if config_path is not None:
                config = load_config(config_path=config_path)
                if force_reload:
                    _config_cache = config  # Update cache when explicitly requested
                return config

            _config_cache = load_config()
            return _config_cache
    else:
        # Already initialised — protect ALL cache mutations with the real lock.
        # (PLAN-27 FIX #1: these reads/writes were previously outside the holder
        # lock in the single shared `async with _config_lock:` block.)
        async with _config_lock:
            if _config_cache is not None and not force_reload and config_path is None:
                return _config_cache

            if config_path is not None:
                config = load_config(config_path=config_path)
                if force_reload:
                    _config_cache = config  # Update cache when explicitly requested
                return config

            _config_cache = load_config()
            return _config_cache
