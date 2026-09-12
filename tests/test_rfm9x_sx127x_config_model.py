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

"""Unit tests for RFM9x/SX127x configuration model."""

import pytest
from pydantic import ValidationError

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    AntennaConfig,
    AssemblyConfig,
    DeviceConfig,
    DeviceConfigRoot,
    DeviceModuleAttachment,
    FamilyConfig,
    FamilyDeviceExclusion,
    ModuleConfig,
    Rfm9xSx127xConfig,
    Rfm9xSx127xFamilyConfig,
)


class TestDeviceConfig:
    """Tests for DeviceConfig model."""

    def test_valid_device_config(self) -> None:
        """Test creation of a valid device configuration."""
        device: DeviceConfig = DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            osc_freq_hz=32000000,
        )
        assert device.name == "RFM95"
        assert device.min_radio_freq_hz == 868000000
        assert device.max_radio_freq_hz == 915000000

    def test_device_config_no_optional_fields(self) -> None:
        """Test creation of a device config without optional fields."""
        device: DeviceConfig = DeviceConfig(
            name="SX1276",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
        )
        assert device.name == "SX1276"
        assert device.osc_freq_hz is None

    def test_device_config_invalid_zero_min_freq(self) -> None:
        """Test that min_radio_freq_hz must be > 0."""
        with pytest.raises(ValidationError):
            DeviceConfig(
                name="INVALID",
                min_radio_freq_hz=0,
                max_radio_freq_hz=915000000,
            )

    def test_device_config_invalid_negative_max_freq(self) -> None:
        """Test that max_radio_freq_hz must be > 0."""
        with pytest.raises(ValidationError):
            DeviceConfig(
                name="INVALID",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=-1,
            )


class TestDeviceConfigRoot:
    """Tests for DeviceConfigRoot model."""

    def test_valid_device_config_root(self) -> None:
        """Test valid DeviceConfigRoot with range validation."""
        device: DeviceConfig = DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
        )
        root: DeviceConfigRoot = DeviceConfigRoot(device=device)
        assert root.device.name == "RFM95"

    def test_device_config_root_invalid_range(self) -> None:
        """Test that max must be > min."""
        device: DeviceConfig = DeviceConfig(
            name="INVALID",
            min_radio_freq_hz=915000000,
            max_radio_freq_hz=868000000,
        )
        with pytest.raises(ValidationError):
            DeviceConfigRoot(device=device)

    def test_device_config_root_equal_freq(self) -> None:
        """Test that max must be strictly > min (equal fails)."""
        device: DeviceConfig = DeviceConfig(
            name="INVALID",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=868000000,
        )
        with pytest.raises(ValidationError):
            DeviceConfigRoot(device=device)


class TestFamilyDeviceExclusion:
    """Tests for FamilyDeviceExclusion model."""

    def test_valid_exclusion(self) -> None:
        """Test valid exclusion entry."""
        exclusion: FamilyDeviceExclusion = FamilyDeviceExclusion(
            device_name="RFM95",
            excluded_freq_hz=434000000,
        )
        assert exclusion.device_name == "RFM95"
        assert exclusion.excluded_freq_hz == 434000000

    def test_exclusion_invalid_zero_freq(self) -> None:
        """Test that excluded_freq_hz must be > 0."""
        with pytest.raises(ValidationError):
            FamilyDeviceExclusion(
                device_name="RFM95",
                excluded_freq_hz=0,
            )


class TestFamilyConfig:
    """Tests for FamilyConfig model."""

    def test_valid_family_config(self) -> None:
        """Test valid family configuration."""
        exclusions: list[FamilyDeviceExclusion] = [
            FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000),
            FamilyDeviceExclusion(device_name="RFM98", excluded_freq_hz=868000000),
        ]
        family: FamilyConfig = FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95", "RFM98"],
            exclusions=exclusions,
        )
        assert family.family_name == "RFM9X"
        assert len(family.devices) == 2

    def test_family_config_empty_devices(self) -> None:
        """Test that devices list must be non-empty."""
        with pytest.raises(ValidationError):
            FamilyConfig(
                family_name="EMPTY",
                devices=[],
                exclusions=[FamilyDeviceExclusion(device_name="X", excluded_freq_hz=100)],
            )


class TestDeviceModuleAttachment:
    """Tests for DeviceModuleAttachment model."""

    def test_valid_attachment(self) -> None:
        """Test valid device attachment."""
        attachment: DeviceModuleAttachment = DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:GPIO25", "DIO5:GPIO24"],
        )
        assert attachment.device_name == "RFM95"
        assert attachment.spi_device_id == 0

    def test_attachment_no_mappings(self) -> None:
        """Test attachment without DIO GPIO mappings."""
        attachment: DeviceModuleAttachment = DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
        )
        assert attachment.dio_gpio_mappings is None


class TestAntennaConfig:
    """Tests for AntennaConfig model."""

    def test_valid_antenna_config(self) -> None:
        """Test valid antenna configuration."""
        config: AntennaConfig = AntennaConfig(
            antenna_type="parabolic",
            antenna_gain_db=25.0,
        )
        assert config.antenna_type == "parabolic"
        assert config.antenna_gain_db == 25.0

    def test_antenna_config_no_optional_fields(self) -> None:
        """Test antenna config without optional fields."""
        config: AntennaConfig = AntennaConfig()
        assert config.antenna_type is None
        assert config.antenna_gain_db is None

    def test_antenna_config_negative_gain(self) -> None:
        """Test antenna config with negative gain."""
        config: AntennaConfig = AntennaConfig(
            antenna_type="parabolic",
            antenna_gain_db=-10.0,
        )
        assert config.antenna_gain_db == -10.0

    def test_antenna_config_zero_gain(self) -> None:
        """Test antenna config with zero gain."""
        config: AntennaConfig = AntennaConfig(
            antenna_type="parabolic",
            antenna_gain_db=0.0,
        )
        assert config.antenna_gain_db == 0.0


class TestAssemblyConfig:
    """Tests for AssemblyConfig model."""

    def test_valid_assembly_config(self) -> None:
        """Test valid assembly configuration."""
        devices: dict[str, AntennaConfig] = {
            "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=25.0),
        }
        assembly: AssemblyConfig = AssemblyConfig(
            assembly_name="default",
            module_name="LoRa Pi 434/868",
            devices=devices,
        )
        assert assembly.assembly_name == "default"
        assert assembly.module_name == "LoRa Pi 434/868"
        assert len(assembly.devices) == 1

    def test_assembly_config_empty_devices(self) -> None:
        """Test assembly with empty devices dict."""
        assembly: AssemblyConfig = AssemblyConfig(
            assembly_name="empty",
            module_name="LoRa Pi 434/868",
        )
        assert assembly.devices == {}

    def test_assembly_config_empty_assembly_name(self) -> None:
        """Test that assembly_name must be non-empty."""
        with pytest.raises(ValidationError):
            AssemblyConfig(
                assembly_name="",
                module_name="LoRa Pi 434/868",
            )

    def test_assembly_config_empty_module_name(self) -> None:
        """Test that module_name must be non-empty."""
        with pytest.raises(ValidationError):
            AssemblyConfig(
                assembly_name="default",
                module_name="",
            )


class TestModuleConfig:
    """Tests for ModuleConfig model."""

    def test_valid_module_config(self) -> None:
        """Test valid module configuration."""
        devices: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]
        module: ModuleConfig = ModuleConfig(
            module_name="LoRa Pi 434/868",
            devices=devices,
        )
        assert module.module_name == "LoRa Pi 434/868"

    def test_module_config_empty_devices(self) -> None:
        """Test that devices list must be non-empty."""
        with pytest.raises(ValidationError):
            ModuleConfig(
                module_name="EMPTY",
                devices=[],
            )


class TestRfm9xSx127xConfig:
    """Tests for Rfm9xSx127xConfig model."""

    def test_valid_full_config(self) -> None:
        """Test valid full configuration."""
        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices={"rfm95": DeviceConfig(name="RFM95", min_radio_freq_hz=868000000, max_radio_freq_hz=915000000)},
            families={},
            modules={},
            assemblies={},
        )
        assert "rfm95" in config.devices

    def test_config_default_empty(self) -> None:
        """Test default empty configuration."""
        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig()
        assert config.devices == {}
        assert config.families == {}
        assert config.modules == {}
        assert config.assemblies == {}


class TestRfm9xSx127xFamilyConfig:
    """Tests for Rfm9xSx127xFamilyConfig model."""

    def test_valid_family_only_config(self) -> None:
        """Test valid family-only configuration."""
        config: Rfm9xSx127xFamilyConfig = Rfm9xSx127xFamilyConfig(
            families={
                "rfm9x": FamilyConfig(
                    family_name="RFM9X",
                    devices=["RFM95"],
                    exclusions=[FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000)],
                ),
            },
        )
        assert "rfm9x" in config.families
