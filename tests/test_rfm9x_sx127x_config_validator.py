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

"""Unit tests for RFM9x/SX127x configuration validator."""

import pytest
from pydantic import ValidationError

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    DeviceConfig,
    DeviceModuleAttachment,
    FamilyConfig,
    FamilyDeviceExclusion,
    ModuleConfig,
    Rfm9xSx127xConfig,
)
from pi_lora.drivers.rfm9x_sx127x_config_validator import (
    validate_device_config,
    validate_family_config,
    validate_full_config,
    validate_module_config,
)

_VALIDATION_ERRORS: tuple[type, ...] = (ValidationError, ValueError)


class TestValidateDeviceConfig:
    """Tests for validate_device_config function."""

    def test_valid_device(self) -> None:
        """Test valid device config passes validation."""
        device: DeviceConfig = DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            osc_freq_hz=32000000,
            antenna_type="parabolic",
            antenna_gain_db=25.0,
        )
        assert validate_device_config(device) is True

    def test_invalid_zero_min_freq(self) -> None:
        """Test device with min_radio_freq_hz = 0 fails validation."""
        with pytest.raises(_VALIDATION_ERRORS):
            DeviceConfig(
                name="INVALID",
                min_radio_freq_hz=0,
                max_radio_freq_hz=915000000,
            )

    def test_invalid_max_less_than_min(self) -> None:
        """Test device with max < min fails validation."""
        device: DeviceConfig = DeviceConfig(
            name="INVALID",
            min_radio_freq_hz=915000000,
            max_radio_freq_hz=868000000,
        )
        with pytest.raises(_VALIDATION_ERRORS):
            validate_device_config(device)

    def test_invalid_negative_osc_freq(self) -> None:
        """Test device with negative osc_freq_hz fails validation."""
        with pytest.raises(_VALIDATION_ERRORS):
            DeviceConfig(
                name="INVALID",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
                osc_freq_hz=-1,
            )

    def test_invalid_negative_antenna_gain(self) -> None:
        """Test device with negative antenna_gain_db fails validation."""
        device: DeviceConfig = DeviceConfig(
            name="INVALID",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            antenna_gain_db=-1.0,
        )
        with pytest.raises(_VALIDATION_ERRORS):
            validate_device_config(device)


class TestValidateFamilyConfig:
    """Tests for validate_family_config function."""

    def test_valid_family(self) -> None:
        """Test valid family config passes validation."""
        exclusions: list[FamilyDeviceExclusion] = [
            FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000),
        ]
        family: FamilyConfig = FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95"],
            exclusions=exclusions,
        )
        assert validate_family_config(family) is True

    def test_invalid_empty_devices(self) -> None:
        """Test family with empty devices list fails validation."""
        with pytest.raises(_VALIDATION_ERRORS):
            validate_family_config(
                FamilyConfig(
                    family_name="EMPTY",
                    devices=[],
                    exclusions=[FamilyDeviceExclusion(device_name="X", excluded_freq_hz=100)],
                )
            )

    def test_invalid_exclusion_not_in_devices(self) -> None:
        """Test exclusion device not in devices list fails validation."""
        exclusions: list[FamilyDeviceExclusion] = [
            FamilyDeviceExclusion(device_name="NONEXISTENT", excluded_freq_hz=100),
        ]
        family: FamilyConfig = FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95"],
            exclusions=exclusions,
        )
        with pytest.raises(_VALIDATION_ERRORS):
            validate_family_config(family)

    def test_invalid_zero_excluded_freq(self) -> None:
        """Test exclusion with excluded_freq_hz = 0 fails validation."""
        with pytest.raises(_VALIDATION_ERRORS):
            FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=0)


class TestValidateModuleConfig:
    """Tests for validate_module_config function."""

    def test_valid_module(self) -> None:
        """Test valid module config passes validation."""
        devices: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25", "DIO5:GPIO24"],
            ),
        ]
        module: ModuleConfig = ModuleConfig(
            module_name="LoRa Pi 434/868",
            devices=devices,
        )
        assert validate_module_config(module) is True

    def test_invalid_negative_spi_id(self) -> None:
        """Test device with negative spi_device_id fails validation."""
        with pytest.raises(_VALIDATION_ERRORS):
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=-1,
                ce_number=0,
            )

    def test_invalid_dio_mapping_format(self) -> None:
        """Test invalid DIO GPIO mapping format fails validation."""
        devices: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["INVALID:MAPPING"],
            ),
        ]
        module: ModuleConfig = ModuleConfig(
            module_name="INVALID",
            devices=devices,
        )
        with pytest.raises(_VALIDATION_ERRORS):
            validate_module_config(module)


class TestValidateFullConfig:
    """Tests for validate_full_config function."""

    def test_valid_full_config(self) -> None:
        """Test valid full config passes validation."""
        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices={
                "rfm95": DeviceConfig(
                    name="RFM95",
                    min_radio_freq_hz=868000000,
                    max_radio_freq_hz=915000000,
                ),
            },
            families={
                "rfm9x": FamilyConfig(
                    family_name="RFM9X",
                    devices=["RFM95"],
                    exclusions=[FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000)],
                ),
            },
            modules={
                "lora_pi": ModuleConfig(
                    module_name="LoRa Pi 434/868",
                    devices=[
                        DeviceModuleAttachment(
                            device_name="RFM95",
                            spi_device_id=0,
                            ce_number=0,
                            dio_gpio_mappings=["DIO0:GPIO25"],
                        ),
                    ],
                ),
            },
        )
        assert validate_full_config(config) is True

    def test_invalid_full_config(self) -> None:
        """Test invalid full config raises ValidationError."""
        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices={
                "invalid": DeviceConfig(
                    name="INVALID",
                    min_radio_freq_hz=915000000,
                    max_radio_freq_hz=868000000,
                ),
            },
            families={},
            modules={},
        )
        with pytest.raises(_VALIDATION_ERRORS):
            validate_full_config(config)
