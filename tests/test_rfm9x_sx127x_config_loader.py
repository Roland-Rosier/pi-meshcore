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

from pathlib import Path

import pytest

from pi_lora.drivers.rfm9x_sx127x_config_loader import (
    get_preloaded_config,
    load_config,
    load_family_config,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_default_config(self) -> None:
        """Test loading the default pre-loaded configuration."""
        config = load_config()
        assert config is not None
        assert len(config.devices) > 0
        assert len(config.families) > 0
        assert len(config.modules) > 0

    def test_load_preloaded_config(self) -> None:
        """Test that get_preloaded_config returns the cached instance."""
        config = get_preloaded_config()
        assert config is not None
        assert "rfm95" in config.devices
        assert "rfm98" in config.devices

    def test_load_config_with_name(self) -> None:
        """Test loading config with a specific name key."""
        config = load_config(config_name="devices")
        assert len(config.devices) > 0

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

    def test_lazy_loading_returns_cached_instance(self) -> None:
        """Test that first call loads, second call returns same instance."""
        config1 = get_preloaded_config()
        config2 = get_preloaded_config()
        assert config1 is config2

    def test_force_reload_creates_new_instance(self) -> None:
        """Test that force_reload=True creates a new instance."""
        config1 = get_preloaded_config()
        config2 = get_preloaded_config(force_reload=True)
        assert config1 is not config2

    def test_config_path_override_bypasses_cache(self) -> None:
        """Test that config_path override bypasses cache and loads from path."""
        default_config = get_preloaded_config()
        override_config = get_preloaded_config(
            config_path=Path("/home/rpiuser/TestMeshcore/src/pi_lora/drivers/configs/rfm9x_sx127x_config.yaml")
        )
        assert override_config is not default_config
        assert len(override_config.devices) > 0

    def test_force_reload_with_config_path_works(self) -> None:
        """Test that force_reload=True with config_path works (path takes priority)."""
        override_config = get_preloaded_config(
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
