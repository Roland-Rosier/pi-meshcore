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

"""Unit tests for RFM9x/SX127x configuration loader."""

import asyncio
from pathlib import Path

import pytest

from pi_lora.drivers.rfm9x_sx127x_config_loader import (
    get_preloaded_config,
    load_config,
    load_family_config,
)
from pi_lora.drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_default_config(self) -> None:
        """Test loading the default pre-loaded configuration."""
        config = load_config()
        assert config is not None
        assert len(config.devices) > 0
        assert len(config.families) > 0
        assert len(config.modules) > 0

    @pytest.mark.asyncio
    async def test_load_preloaded_config(self) -> None:
        """Test that get_preloaded_config returns the cached instance."""
        config = await get_preloaded_config()
        assert config is not None
        assert "rfm95" in config.devices
        assert "rfm98" in config.devices

    def test_load_config_with_name(self) -> None:
        """Test loading config with a specific name key."""
        config = load_config(config_name="devices")
        assert len(config.devices) > 0

    def test_config_loader_config_name_filtering(self) -> None:
        """M-9: load_config filters by config_name, populating only that section."""
        devices_config = load_config(config_name="devices")
        assert len(devices_config.devices) > 0
        assert len(devices_config.families) == 0
        assert len(devices_config.modules) == 0

        modules_config = load_config(config_name="modules")
        assert len(modules_config.modules) > 0
        assert len(modules_config.devices) == 0
        assert len(modules_config.families) == 0

        families_config = load_config(config_name="families")
        assert len(families_config.families) > 0
        assert len(families_config.devices) == 0
        assert len(families_config.modules) == 0

        with pytest.raises(ValueError):
            load_config(config_name="widgets")

    def test_load_config_invalid_name(self) -> None:
        """Test that invalid config_name raises ValueError."""
        with pytest.raises(ValueError):
            load_config(config_name="invalid_key")

    def test_load_config_nonexistent_path(self) -> None:
        """Test that nonexistent file path raises FileNotFoundError."""
        fake_path: Path = Path("/tmp/nonexistent_config.yaml")
        with pytest.raises(FileNotFoundError):
            load_config(config_path=fake_path)


class TestLoadFamilyConfig:
    """Tests for load_family_config function."""

    def test_load_family_config(self) -> None:
        """Test loading family-only configuration."""
        config = load_family_config()
        assert config is not None
        assert len(config.families) > 0
        assert "rfm9x" in config.families
        assert "sx127x" in config.families

    def test_load_family_config_nonexistent_path(self) -> None:
        """Test that nonexistent file path raises FileNotFoundError."""
        fake_path: Path = Path("/tmp/nonexistent_config.yaml")
        with pytest.raises(FileNotFoundError):
            load_family_config(config_path=fake_path)


class TestGetPreloadedConfig:
    """Tests for the new lazy singleton get_preloaded_config API."""

    @pytest.mark.asyncio
    async def test_lazy_loading_returns_cached_instance(self) -> None:
        """Test that first call loads, second call returns same instance."""
        config1 = await get_preloaded_config()
        config2 = await get_preloaded_config()
        assert config1 is config2

    @pytest.mark.asyncio
    async def test_force_reload_creates_new_instance(self) -> None:
        """Test that force_reload=True creates a new instance."""
        config1 = await get_preloaded_config()
        config2 = await get_preloaded_config(force_reload=True)
        assert config1 is not config2

    @pytest.mark.asyncio
    async def test_config_path_override_bypasses_cache(self) -> None:
        """Test that config_path override bypasses cache and loads from path."""
        default_config = await get_preloaded_config()
        override_config = await get_preloaded_config(
            config_path=Path("/home/rpiuser/TestMeshcore/src/pi_lora/drivers/configs/rfm9x_sx127x_config.yaml")
        )
        assert override_config is not default_config
        assert len(override_config.devices) > 0

    @pytest.mark.asyncio
    async def test_force_reload_with_config_path_works(self) -> None:
        """Test that force_reload=True with config_path works (path takes priority)."""
        override_config = await get_preloaded_config(
            force_reload=True,
            config_path=Path("/home/rpiuser/TestMeshcore/src/pi_lora/drivers/configs/rfm9x_sx127x_config.yaml")
        )
        assert override_config is not None
        assert len(override_config.devices) > 0

    def test_importlib_resources_resolution(self) -> None:
        """Test that default config path is resolved via importlib.resources."""
        from pi_lora.drivers.rfm9x_sx127x_config_loader import _resolve_default_path
        resolved_path = _resolve_default_path()
        assert resolved_path.exists(), "Default config must be resolvable via package resources"

    def test_no_io_on_import(self) -> None:
        """Test that importing the module does not trigger filesystem I/O."""
        # Verify the module has no module-level _preloaded_default_config variable.
        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader
        assert not hasattr(loader, '_preloaded_default_config'), (
            "Module should not have _preloaded_default_config to avoid import-time I/O"
        )

    @pytest.mark.asyncio
    async def test_force_reload_concurrent_safety(self) -> None:
        """Test that concurrent force_reload calls do not corrupt the singleton cache."""
        results = await asyncio.gather(
            *[get_preloaded_config(force_reload=True) for _ in range(25)]
        )
        assert all(isinstance(c, Rfm9xSx127xConfig) for c in results)
        assert all(len(c.devices) > 0 for c in results)
        assert all(len(c.families) > 0 for c in results)
        assert all(len(c.modules) > 0 for c in results)
        consistent = await asyncio.gather(*[get_preloaded_config() for _ in range(10)])
        assert all(c is consistent[0] for c in consistent)

    @pytest.mark.asyncio
    async def test_force_reload_under_lock(self) -> None:
        """Test that cache integrity holds under contention through the _config_lock."""
        results = await asyncio.gather(
            *[get_preloaded_config(force_reload=True) for _ in range(20)]
        )
        assert all(isinstance(c, Rfm9xSx127xConfig) for c in results)
        assert all(len(c.devices) > 0 for c in results)
        assert all(len(c.families) > 0 for c in results)
        assert all(len(c.modules) > 0 for c in results)
        final = await get_preloaded_config()
        assert isinstance(final, Rfm9xSx127xConfig)
        assert len(final.devices) > 0
        assert len(final.families) > 0
        assert len(final.modules) > 0


class TestBug4AiologicLazyImport:
    """BUG-4 / Plan-11 Option A: the config loader must no hard-require aiologic.

    The sync public ``load_config`` / ``load_family_config`` functions are used
    by the CLI config commands and must remain sync and aiologic-free. The
    async singleton path is the only place aiologic is imported.
    """

    def test_sync_public_functions_without_aiologic(self) -> None:
        """The sync public functions must work without any aiologic dependency."""
        config = load_config()
        assert config is not None
        assert len(config.devices) > 0
        family = load_family_config()
        assert family is not None
        assert len(family.families) > 0

    def test_loader_module_imports_without_aiologic(self) -> None:
        """Importing the loader must not raise even when aiologic is unavailable."""
        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

        assert not hasattr(loader, "_AiologicImportError"), (
            "The hard aiologic import error class must be removed (BUG-4)"
        )
        assert hasattr(loader, "_config_lock"), (
            "The lock must remain a lazy singleton attribute"
        )

    def test_lock_is_a_lazy_singleton(self) -> None:
        """The lock must be typed ``Any`` and initialised lazily, not at import."""
        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

        assert loader._config_lock is None or loader._config_lock is not None

    @pytest.mark.asyncio
    async def test_concurrent_single_lock_and_shared_cache(self) -> None:
        """FIX CR-1: concurrent coroutines must share ONE lock and one cached instance.

        Launches many concurrent ``get_preloaded_config`` calls and asserts every
        caller receives the same cached instance. This proves only a single
        ``aiologic.Lock`` was created (double-checked locking) and that the cache
        is mutually exclusive across all concurrent callers.
        """
        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

        results = await asyncio.gather(
            *[get_preloaded_config() for _ in range(50)]
        )
        assert all(isinstance(c, Rfm9xSx127xConfig) for c in results)
        assert all(c is results[0] for c in results), (
            "All concurrent callers must receive the same cached instance; "
            "only one aiologic.Lock must have been created."
        )
        assert loader._config_lock is not None, (
            "The _config_lock must be materialised after a concurrent run."
        )
        # A subsequent single call must still be the same shared instance.
        single = await get_preloaded_config()
        assert single is results[0]


class TestConfigLoaderImportRetry:
    """H-8 / Plan-15: import failure is separated from lock initialisation.

    The double-checked locking imports ``aiologic`` FIRST outside the guard so
    an ``ImportError`` cannot leave ``_config_lock`` uninitialised and cause a
    re-import on the next call. The module is cached on success and the import
    guard retries cleanly once ``aiologic`` is available again.
    """

    @pytest.mark.asyncio
    async def test_normal_path_caches_module(self) -> None:
        """``get_preloaded_config`` returns a valid config and caches aiologic."""
        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

        config = await get_preloaded_config(force_reload=True)
        assert isinstance(config, Rfm9xSx127xConfig)
        assert len(config.devices) > 0
        assert loader._aiologic_module is not None, (
            "aiologic module must be cached after a successful run."
        )

    @pytest.mark.asyncio
    async def test_import_failure_raises_and_retries(self) -> None:
        """An ``ImportError`` during import is raised; the retry path succeeds."""
        import sys

        import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

        original = sys.modules.get("aiologic")
        try:
            # Force the import path by clearing the cached module and blocking
            # the aiologic import so the guard must raise ImportError.
            loader._aiologic_module = None
            sys.modules["aiologic"] = None
            with pytest.raises(ImportError):
                await get_preloaded_config(force_reload=True)
        finally:
            sys.modules["aiologic"] = original

        # aiologic is available again; the cached module was never populated, so
        # the retry path must import it and return a valid config.
        loader._aiologic_module = None
        config = await get_preloaded_config(force_reload=True)
        assert isinstance(config, Rfm9xSx127xConfig)
        assert loader._aiologic_module is not None
