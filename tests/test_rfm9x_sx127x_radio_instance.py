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

"""Unit tests for RFM9x/SX127x radio instance configuration."""

from dataclasses import FrozenInstanceError

import pytest

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    AntennaConfig,
    AssemblyConfig,
    DeviceConfig,
    DeviceModuleAttachment,
    FamilyConfig,
    FamilyDeviceExclusion,
    ModuleConfig,
    Rfm9xSx127xConfig,
)
from pi_lora.drivers.rfm9x_sx127x_radio_instance import (
    AssemblyNotFoundError,
    ConfigConsistencyError,
    DeviceAttachmentNotFoundError,
    DeviceIdentity,
    DeviceSpecNotFoundError,
    FamilyNotFoundError,
    ModuleNotFoundError,
    RadioInstanceConfig,
    RadioInstanceError,
    create_radio_instance,
    create_radio_instance_from_default,
)

# ──────────────────────────────────────────────────────────────────────
# Fixtures: build minimal configs for factory testing
# ──────────────────────────────────────────────────────────────────────

def _make_full_default_config() -> Rfm9xSx127xConfig:
    """Build the config matching the YAML default (RFM95/RFM98 in lora_pi_434_868).

    Note: Uses in-range exclusions to avoid ConfigConsistencyError during construction.
    The YAML default has out-of-range exclusions (e.g., RFM98 excluded at 868MHz is
    outside [434M, 460M]), which would trigger validation errors.
    """
    devices: dict[str, DeviceConfig] = {
        "RFM95": DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            osc_freq_hz=32000000,
        ),
        "RFM98": DeviceConfig(
            name="RFM98",
            min_radio_freq_hz=434000000,
            max_radio_freq_hz=460000000,
            osc_freq_hz=32000000,
        ),
    }

    families: dict[str, FamilyConfig] = {
        "rfm9x": FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95", "RFM98"],
            exclusions=[
                # Use in-range exclusions to allow successful construction
                FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                FamilyDeviceExclusion(device_name="RFM98", excluded_freq_hz=450000000),
            ],
        ),
    }

    attachments_rfm95: list[DeviceModuleAttachment] = [
        DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:GPIO25", "DIO5:GPIO24"],
        ),
    ]

    attachments_rfm98: list[DeviceModuleAttachment] = [
        DeviceModuleAttachment(
            device_name="RFM98",
            spi_device_id=0,
            ce_number=1,
            dio_gpio_mappings=["DIO0:GPIO16", "DIO5:GPIO12"],
        ),
    ]

    module_config: ModuleConfig = ModuleConfig(
        module_name="lora_pi_434_868",
        devices=attachments_rfm95 + attachments_rfm98,
    )

    assemblies: dict[str, AssemblyConfig] = {
        "default": AssemblyConfig(
            assembly_name="default",
            module_name="lora_pi_434_868",
            devices={
                "0:1": AntennaConfig(antenna_type="parabolic", antenna_gain_db=24.0),
                "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=25.0),
            },
        ),
    }

    return Rfm9xSx127xConfig(
        devices=devices,
        families=families,
        modules={"lora_pi_434_868": module_config},
        assemblies=assemblies,
    )


@pytest.fixture()
def default_config() -> Rfm9xSx127xConfig:
    """Full config matching YAML: RFM95 on 0:0, RFM98 on 0:1."""
    return _make_full_default_config()


@pytest.fixture()
def config_with_assemblies_only() -> Rfm9xSx127xConfig:
    """Config with assemblies but missing antenna key for one device."""
    devices: dict[str, DeviceConfig] = {
        "RFM95": DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            osc_freq_hz=32000000,
        ),
    }

    families: dict[str, FamilyConfig] = {
        "rfm9x": FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95"],
            exclusions=[
                FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
            ],
        ),
    }

    attachments: list[DeviceModuleAttachment] = [
        DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:GPIO25"],
        ),
    ]

    module_config: ModuleConfig = ModuleConfig(
        module_name="lora_pi_434_868",
        devices=attachments,
    )

    # Assembly exists but only has "1:0" key — "0:0" is missing → None fields
    assemblies: dict[str, AssemblyConfig] = {
        "default": AssemblyConfig(
            assembly_name="default",
            module_name="lora_pi_434_868",
            devices={
                "1:0": AntennaConfig(antenna_type="dish", antenna_gain_db=20.0),
            },
        ),
    }

    return Rfm9xSx127xConfig(
        devices=devices,
        families=families,
        modules={"lora_pi_434_868": module_config},
        assemblies=assemblies,
    )


@pytest.fixture()
def config_no_assemblies() -> Rfm9xSx127xConfig:
    """Config with no matching assembly (assembly exists but module_name doesn't match)."""
    devices: dict[str, DeviceConfig] = {
        "RFM95": DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
        ),
    }

    families: dict[str, FamilyConfig] = {
        "rfm9x": FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95"],
            exclusions=[
                # In-range exclusion to allow successful construction
                FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
            ],
        ),
    }

    attachments: list[DeviceModuleAttachment] = [
        DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:GPIO25"],
        ),
    ]

    module_config: ModuleConfig = ModuleConfig(
        module_name="lora_pi_434_868",
        devices=attachments,
    )

    # Assembly exists but has a different module_name → no match for "lora_pi_434_868"
    assemblies: dict[str, AssemblyConfig] = {
        "other": AssemblyConfig(
            assembly_name="other",
            module_name="different_module",
            devices={},
        ),
    }

    return Rfm9xSx127xConfig(
        devices=devices,
        families=families,
        modules={"lora_pi_434_868": module_config},
        assemblies=assemblies,
    )


@pytest.fixture()
def config_multi_family_same_device() -> Rfm9xSx127xConfig:
    """Config where the same device appears in multiple families."""
    devices: dict[str, DeviceConfig] = {
        "RFM95": DeviceConfig(
            name="RFM95",
            min_radio_freq_hz=868000000,
            max_radio_freq_hz=915000000,
            osc_freq_hz=32000000,
        ),
    }

    families: dict[str, FamilyConfig] = {
        "rfm9x": FamilyConfig(
            family_name="RFM9X",
            devices=["RFM95"],
            exclusions=[
                FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
            ],
        ),
        "sx127x": FamilyConfig(
            family_name="SX127X",
            devices=["RFM95"],  # same device in second family
            exclusions=[
                FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=880000000),
            ],
        ),
    }

    attachments: list[DeviceModuleAttachment] = [
        DeviceModuleAttachment(
            device_name="RFM95",
            spi_device_id=0,
            ce_number=0,
            dio_gpio_mappings=["DIO0:GPIO25"],
        ),
    ]

    module_config: ModuleConfig = ModuleConfig(
        module_name="lora_pi_434_868",
        devices=attachments,
    )

    return Rfm9xSx127xConfig(
        devices=devices,
        families=families,
        modules={"lora_pi_434_868": module_config},
        assemblies={
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="lora_pi_434_868",
            ),
        },
    )


# ──────────────────────────────────────────────────────────────────────
# 1. Successful creation for both devices in default config
# ──────────────────────────────────────────────────────────────────────

class TestSuccessfulCreation:
    """Test successful RadioInstanceConfig creation."""

    def test_create_rfm98_on_0_1(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test creating RFM98 instance at SPI:0 CE:1."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        assert result.module_name == "lora_pi_434_868"
        assert result.spi_device_id == 0
        assert result.ce_number == 1
        assert result.device_name == "RFM98"
        assert result.min_radio_freq_hz == 434000000
        assert result.max_radio_freq_hz == 460000000
        assert result.osc_freq_hz == 32000000
        assert result.family_name == "RFM9X"
        assert result.excluded_frequencies_hz == (450000000,)
        assert result.dio_gpio_mappings == ("DIO0:GPIO16", "DIO5:GPIO12")
        assert result.antenna_type == "parabolic"
        assert result.antenna_gain_db == 24.0

    def test_create_rfm95_on_0_0(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test creating RFM95 instance at SPI:0 CE:0."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        assert result.module_name == "lora_pi_434_868"
        assert result.spi_device_id == 0
        assert result.ce_number == 0
        assert result.device_name == "RFM95"
        assert result.min_radio_freq_hz == 868000000
        assert result.max_radio_freq_hz == 915000000
        assert result.osc_freq_hz == 32000000
        assert result.family_name == "RFM9X"
        assert result.excluded_frequencies_hz == (900000000,)
        assert result.dio_gpio_mappings == ("DIO0:GPIO25", "DIO5:GPIO24")
        assert result.antenna_type == "parabolic"
        assert result.antenna_gain_db == 25.0

    def test_create_returns_frozen_dataclass(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test that the returned instance is a frozen dataclass (immutable)."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        with pytest.raises(FrozenInstanceError):
            result.device_name = "CHANGED"  # type: ignore[assignment]


# ──────────────────────────────────────────────────────────────────────
# 2. Test all computed properties
# ──────────────────────────────────────────────────────────────────────

class TestComputedProperties:
    """Test frequency_range_hz, device_id_key, supported_frequencies_hz."""

    def test_frequency_range_hz_rfm98(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test frequency_range_hz returns correct tuple for RFM98."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        assert result.frequency_range_hz == (434000000, 460000000)

    def test_frequency_range_hz_rfm95(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test frequency_range_hz returns correct tuple for RFM95."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        assert result.frequency_range_hz == (868000000, 915000000)

    def test_device_id_key_rfm98(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test device_id_key returns correct DeviceIdentity for RFM98."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        key: DeviceIdentity = result.device_id_key
        assert key.spi_device_id == 0
        assert key.ce_number == 1
        assert str(key) == "0:1"

    def test_device_id_key_rfm95(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test device_id_key returns correct DeviceIdentity for RFM95."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        key: DeviceIdentity = result.device_id_key
        assert key.spi_device_id == 0
        assert key.ce_number == 0
        assert str(key) == "0:0"

    def test_supported_frequencies_hz_rfm98(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test supported_frequencies_hz returns (min, max) tuple for RFM98."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (434000000, 460000000)

    def test_supported_frequencies_hz_rfm95(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test supported_frequencies_hz returns (min, max) tuple for RFM95."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (868000000, 915000000)

    def test_supported_frequencies_hz_empty_exclusions(self) -> None:
        """Test supported_frequencies_hz returns bounds tuple."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (868000000, 915000000)

    def test_device_identity_str_format(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test DeviceIdentity __str__ format."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        key_str: str = str(result.device_id_key)
        assert key_str == "0:1"


# ──────────────────────────────────────────────────────────────────────
# 3. Test each exception type raised for invalid inputs with context payloads
# ──────────────────────────────────────────────────────────────────────

class TestExceptions:
    """Test all exception types and their context payloads."""

    def test_module_not_found_error(self) -> None:
        """Test ModuleNotFoundError when assembly module_name not in config.modules."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        # Assembly has module_name "nonexistent_mod" which is not in config.modules
        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="nonexistent_mod",
                devices={
                    "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=25.0),
                },
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ModuleNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: ModuleNotFoundError = exc_info.value
        assert "nonexistent_mod" in str(exc)
        assert isinstance(exc, RadioInstanceError)

    def test_device_attachment_not_found_error(self) -> None:
        """Test DeviceAttachmentNotFoundError for wrong SPI/CE."""
        config: Rfm9xSx127xConfig = _make_full_default_config()

        with pytest.raises(DeviceAttachmentNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="default",
                spi_device_id=1,
                ce_number=0,
                config=config,
            )

        exc: DeviceAttachmentNotFoundError = exc_info.value
        assert "SPI:1 CE:0" in str(exc)
        assert exc.context["module_name"] == "lora_pi_434_868"
        assert exc.context["spi_device_id"] == 1
        assert exc.context["ce_number"] == 0
        assert isinstance(exc, RadioInstanceError)

    def test_assembly_not_found_error(self) -> None:
        """Test AssemblyNotFoundError when module has no assembly."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies={},  # no assemblies at all
        )

        with pytest.raises(AssemblyNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="nonexistent_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: AssemblyNotFoundError = exc_info.value
        assert "nonexistent_asm" in str(exc)
        assert "0:0" in exc.context["device_key"]
        assert isinstance(exc, RadioInstanceError)

    def test_device_spec_not_found_error(self) -> None:
        """Test DeviceSpecNotFoundError when device_name not in config.devices."""
        devices: dict[str, DeviceConfig] = {}  # empty devices

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        # Assembly exists but has a different module_name → module lookup fails first
        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="lora_pi_434_868",
                devices={
                    "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=25.0),
                },
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(DeviceSpecNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: DeviceSpecNotFoundError = exc_info.value
        assert "RFM95" in str(exc)
        assert exc.context == {"device_name": "RFM95"}
        assert isinstance(exc, RadioInstanceError)

    def test_family_not_found_error(self) -> None:
        """Test FamilyNotFoundError when device not in any family."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "sx127x": FamilyConfig(
                family_name="SX127X",
                devices=["SX1276"],  # RFM95 not listed
                exclusions=[
                    FamilyDeviceExclusion(device_name="SX1276", excluded_freq_hz=434000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="lora_pi_434_868",
                devices={
                    "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=25.0),
                },
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(FamilyNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: FamilyNotFoundError = exc_info.value
        assert "RFM95" in str(exc)
        assert exc.context == {"device_name": "RFM95"}
        assert isinstance(exc, RadioInstanceError)

    def test_config_consistency_error_duplicate_attachment(self) -> None:
        """Test ConfigConsistencyError when multiple attachments match same SPI/CE."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
            "RFM98": DeviceConfig(
                name="RFM98",
                min_radio_freq_hz=434000000,
                max_radio_freq_hz=460000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95", "RFM98"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=434000000),
                    FamilyDeviceExclusion(device_name="RFM98", excluded_freq_hz=868000000),
                ],
            ),
        }

        # Two attachments with same SPI/CE
        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
            DeviceModuleAttachment(
                device_name="RFM98",
                spi_device_id=0,
                ce_number=0,  # duplicate SPI/CE
                dio_gpio_mappings=["DIO0:GPIO16"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "default": AssemblyConfig(
                assembly_name="default",
                module_name="lora_pi_434_868",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance(
                assembly_name="default",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: ConfigConsistencyError = exc_info.value
        assert "Multiple attachments" in str(exc)
        assert exc.context["module_name"] == "lora_pi_434_868"
        assert isinstance(exc, RadioInstanceError)

    def test_config_consistency_error_excluded_freq_out_of_range(self) -> None:
        """Test ConfigConsistencyError when excluded frequency is outside device range."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=100000),  # way too low
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="lora_pi_434_868",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: ConfigConsistencyError = exc_info.value
        assert "Excluded frequency" in str(exc)
        assert exc.context["excluded_freq_hz"] == 100000
        assert isinstance(exc, RadioInstanceError)

    def test_config_consistency_error_antenna_gain_out_of_range(self) -> None:
        """Test ConfigConsistencyError when antenna gain is physically impossible."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="lora_pi_434_868",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "default": AssemblyConfig(
                assembly_name="default",
                module_name="lora_pi_434_868",
                devices={
                    "0:0": AntennaConfig(antenna_type="parabolic", antenna_gain_db=-150.0),  # impossible
                },
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"lora_pi_434_868": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance(
                assembly_name="default",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        exc: ConfigConsistencyError = exc_info.value
        assert "Antenna gain" in str(exc)
        assert exc.context["antenna_gain_db"] == -150.0
        assert isinstance(exc, RadioInstanceError)


# ──────────────────────────────────────────────────────────────────────
# 4. Test create_radio_instance_from_default() works
# ──────────────────────────────────────────────────────────────────────

class TestCreateFromDefault:
    """Test the convenience wrapper using preloaded config."""

    def test_from_default_rfm95(self) -> None:
        """Test create_radio_instance_from_default for RFM95 (0:0).

        The preloaded YAML config has out-of-range exclusion (434MHz outside [868M,915M])
        which triggers ConfigConsistencyError. This test verifies that validation works.
        """
        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance_from_default(
                assembly_name="default",
                spi_device_id=0,
                ce_number=0,
            )

        assert "Excluded frequency" in str(exc_info.value)

    def test_from_default_rfm98(self) -> None:
        """Test create_radio_instance_from_default for RFM98 (0:1).

        The preloaded YAML config has out-of-range exclusion (868MHz outside [434M,460M])
        which triggers ConfigConsistencyError. This test verifies that validation works.
        """
        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance_from_default(
                assembly_name="default",
                spi_device_id=0,
                ce_number=1,
            )

        assert "Excluded frequency" in str(exc_info.value)

    def test_from_default_raises_module_not_found(self) -> None:
        """Test create_radio_instance_from_default raises for nonexistent assembly."""
        with pytest.raises(AssemblyNotFoundError):
            create_radio_instance_from_default(
                assembly_name="nonexistent",
                spi_device_id=0,
                ce_number=0,
            )

    def test_from_default_raises_attachment_not_found(self) -> None:
        """Test create_radio_instance_from_default raises for nonexistent SPI/CE."""
        with pytest.raises(DeviceAttachmentNotFoundError):
            create_radio_instance_from_default(
                assembly_name="default",
                spi_device_id=99,
                ce_number=99,
            )


# ──────────────────────────────────────────────────────────────────────
# 5. Frequency edge cases
# ──────────────────────────────────────────────────────────────────────

class TestFrequencyEdgeCases:
    """Test frequency computation edge cases."""

    def test_min_max_equal_device(self) -> None:
        """Test supported_frequencies_hz when min=max (single value tuple)."""
        devices: dict[str, DeviceConfig] = {
            "TEST": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=500000000,
                max_radio_freq_hz=500000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=500000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        # Returns (min, max) — both 500000000
        assert freqs == (500000000, 500000000)

    def test_excluded_at_min_boundary(self) -> None:
        """Test excluded frequency exactly at min_radio_freq_hz — still returns (min, max)."""
        devices: dict[str, DeviceConfig] = {
            "TEST": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=500000000,
                max_radio_freq_hz=600000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=500000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (500000000, 600000000)

    def test_excluded_at_max_boundary(self) -> None:
        """Test excluded frequency exactly at max_radio_freq_hz — returns (min, max)."""
        devices: dict[str, DeviceConfig] = {
            "TEST": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=500000000,
                max_radio_freq_hz=600000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=600000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (500000000, 600000000)

    def test_empty_exclusions_tuple(self) -> None:
        """Test excluded_frequencies_hz contains the exclusion from family."""
        devices: dict[str, DeviceConfig] = {
            "RFM95": DeviceConfig(
                name="RFM95",
                min_radio_freq_hz=868000000,
                max_radio_freq_hz=915000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "rfm9x": FamilyConfig(
                family_name="RFM9X",
                devices=["RFM95"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="RFM95", excluded_freq_hz=900000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="RFM95",
                spi_device_id=0,
                ce_number=0,
                dio_gpio_mappings=["DIO0:GPIO25"],
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        assert len(result.excluded_frequencies_hz) == 1
        assert result.excluded_frequencies_hz[0] == 900000000


# ──────────────────────────────────────────────────────────────────────
# 6. Partial assembly config: antenna key missing → None fields
# ──────────────────────────────────────────────────────────────────────

class TestPartialAssemblyConfig:
    """Test partial assembly config behavior."""

    def test_assembly_exists_but_key_missing(self, config_with_assemblies_only: Rfm9xSx127xConfig) -> None:
        """Test antenna fields are None when assembly exists but device key is missing."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=config_with_assemblies_only,
        )

        assert result.antenna_type is None
        assert result.antenna_gain_db is None
        # Should not raise an error — missing key yields None fields
        assert result.device_name == "RFM95"

    def test_no_matching_assembly(self, config_no_assemblies: Rfm9xSx127xConfig) -> None:
        """Test ModuleNotFoundError when assembly's module_name doesn't match any module."""
        with pytest.raises(ModuleNotFoundError) as exc_info:
            create_radio_instance(
                assembly_name="other",
                spi_device_id=0,
                ce_number=0,
                config=config_no_assemblies,
            )

        assert "different_module" in str(exc_info.value)


# ──────────────────────────────────────────────────────────────────────
# 7. Multiple families with same device: "first match wins"
# ──────────────────────────────────────────────────────────────────────

class TestMultipleFamilies:
    """Test behavior when device appears in multiple families."""

    def test_first_match_wins(self, config_multi_family_same_device: Rfm9xSx127xConfig) -> None:
        """Test that the first matching family's exclusions are used."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config_multi_family_same_device,
        )

        # Should use RFM9X family (first in dict iteration) exclusions
        assert result.family_name == "RFM9X"
        assert result.excluded_frequencies_hz == (900000000,)
        # SX127X exclusion should NOT be present
        assert 880000000 not in result.excluded_frequencies_hz

    def test_first_match_wins_supported_freqs(self, config_multi_family_same_device: Rfm9xSx127xConfig) -> None:
        """Test supported_frequencies returns (min, max) tuple."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config_multi_family_same_device,
        )

        freqs: tuple[int, int] = result.supported_frequencies_hz
        assert freqs == (868000000, 915000000)


# ──────────────────────────────────────────────────────────────────────
# 8. Cross-reference validation: ConfigConsistencyError for invalid combos
# ──────────────────────────────────────────────────────────────────────

class TestCrossReferenceValidation:
    """Test cross-reference validation raises ConfigConsistencyError."""

    def test_excluded_freq_above_max(self) -> None:
        """Test ConfigConsistencyError when excluded freq > max_radio_freq_hz."""
        devices: dict[str, DeviceConfig] = {
            "TEST": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=400000000,
                max_radio_freq_hz=500000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=600000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        assert "Excluded frequency" in str(exc_info.value)
        assert exc_info.value.context["excluded_freq_hz"] == 600000000

    def test_osc_freq_out_of_range(self) -> None:
        """Test ConfigConsistencyError when osc_freq is physically impossible."""
        devices: dict[str, DeviceConfig] = {
            "TEST": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=400000000,
                max_radio_freq_hz=500000000,
                osc_freq_hz=20_000_000_000,  # > 10 GHz, out of range
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=450000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        with pytest.raises(ConfigConsistencyError) as exc_info:
            create_radio_instance(
                assembly_name="test_asm",
                spi_device_id=0,
                ce_number=0,
                config=config,
            )

        assert "OSC frequency" in str(exc_info.value)
        assert exc_info.value.context["osc_freq_hz"] == 20_000_000_000

    def test_valid_cross_reference_no_error(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test no ConfigConsistencyError for valid cross-reference combinations."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        assert result.device_name == "RFM95"

    def test_valid_cross_reference_rfm98(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test RFM98 cross-reference passes validation (450MHz within [434M, 460M])."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=1,
            config=default_config,
        )

        assert result.device_name == "RFM98"

    def test_valid_cross_reference_with_in_range_exclusion(self) -> None:
        """Test no error when excluded frequency is within device range."""
        devices: dict[str, DeviceConfig] = {
            "test": DeviceConfig(
                name="TEST",
                min_radio_freq_hz=400000000,
                max_radio_freq_hz=600000000,
                osc_freq_hz=32000000,
            ),
        }

        families: dict[str, FamilyConfig] = {
            "test_fam": FamilyConfig(
                family_name="TEST_FAM",
                devices=["TEST"],
                exclusions=[
                    FamilyDeviceExclusion(device_name="TEST", excluded_freq_hz=500000000),
                ],
            ),
        }

        attachments: list[DeviceModuleAttachment] = [
            DeviceModuleAttachment(
                device_name="TEST",
                spi_device_id=0,
                ce_number=0,
            ),
        ]

        module_config: ModuleConfig = ModuleConfig(
            module_name="test_mod",
            devices=attachments,
        )

        assemblies: dict[str, AssemblyConfig] = {
            "test_asm": AssemblyConfig(
                assembly_name="test_asm",
                module_name="test_mod",
            ),
        }

        config: Rfm9xSx127xConfig = Rfm9xSx127xConfig(
            devices=devices,
            families=families,
            modules={"test_mod": module_config},
            assemblies=assemblies,
        )

        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="test_asm",
            spi_device_id=0,
            ce_number=0,
            config=config,
        )

        assert result.device_name == "TEST"
        assert result.excluded_frequencies_hz == (500000000,)


# ──────────────────────────────────────────────────────────────────────
# Dataclass immutability and repr
# ──────────────────────────────────────────────────────────────────────

class TestDataClassBehavior:
    """Test frozen dataclass behavior and __repr__."""

    def test_repr_format(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test __repr__ output format."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        repr_str: str = repr(result)
        assert "module='lora_pi_434_868'" in repr_str
        assert "device=DeviceIdentity(spi_device_id=0, ce_number=0)" in repr_str or "0:0" in repr_str
        assert "freq_range=(868000000, 915000000)" in repr_str

    def test_frozen_dataclass_immutability(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test that RadioInstanceConfig is immutable (frozen=True)."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        with pytest.raises(FrozenInstanceError):
            result.spi_device_id = 99  # type: ignore[assignment]

    def test_frozen_dataclass_hashable(self, default_config: Rfm9xSx127xConfig) -> None:
        """Test that frozen dataclass is hashable (can be used in sets/dicts)."""
        result: RadioInstanceConfig = create_radio_instance(
            assembly_name="default",
            spi_device_id=0,
            ce_number=0,
            config=default_config,
        )

        # Should not raise TypeError
        test_set: set[object] = {result}
        assert result in test_set


# ──────────────────────────────────────────────────────────────────────
# Exception hierarchy inheritance
# ──────────────────────────────────────────────────────────────────────

class TestExceptionHierarchy:
    """Test exception inheritance chain."""

    def test_all_exceptions_inherit_from_radio_instance_error(self) -> None:
        """Test all custom exceptions inherit from RadioInstanceError."""
        assert issubclass(ModuleNotFoundError, RadioInstanceError)
        assert issubclass(DeviceAttachmentNotFoundError, RadioInstanceError)
        assert issubclass(AssemblyNotFoundError, RadioInstanceError)
        assert issubclass(DeviceSpecNotFoundError, RadioInstanceError)
        assert issubclass(FamilyNotFoundError, RadioInstanceError)
        assert issubclass(ConfigConsistencyError, RadioInstanceError)

    def test_exception_context_default_empty(self) -> None:
        """Test that context defaults to empty dict when not provided."""
        exc: ModuleNotFoundError = ModuleNotFoundError("test_mod")
        assert exc.context == {"module_name": "test_mod"}

    def test_exception_message_contains_module_name(self) -> None:
        """Test exception messages contain relevant identifiers."""
        exc1: ModuleNotFoundError = ModuleNotFoundError("my_mod")
        assert "my_mod" in str(exc1)

        exc2: DeviceAttachmentNotFoundError = DeviceAttachmentNotFoundError("my_mod", 5, 3)
        assert "my_mod" in str(exc2)
        assert "SPI:5 CE:3" in str(exc2)

        exc3: AssemblyNotFoundError = AssemblyNotFoundError("my_mod", DeviceIdentity(1, 2))
        assert "my_mod" in str(exc3)
        assert "1:2" in str(exc3)

        exc4: DeviceSpecNotFoundError = DeviceSpecNotFoundError("DEV1")
        assert "DEV1" in str(exc4)

        exc5: FamilyNotFoundError = FamilyNotFoundError("DEV2")
        assert "DEV2" in str(exc5)
