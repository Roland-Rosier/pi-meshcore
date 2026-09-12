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

"""Pydantic models for RFM9x/SX127x device configuration."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, Field, model_validator


class DeviceConfig(BaseModel):
    """A specific RFM9x or SX127x device configuration.

    Required:
        name: Device identifier (e.g., "RFM95", "SX1276").
        min_radio_freq_hz: Minimum radio frequency in Hz.
        max_radio_freq_hz: Maximum radio frequency in Hz.

    Optional:
        osc_freq_hz: Oscillator/crystal frequency in Hz (e.g., 32 MHz).
    """

    name: str = Field(..., min_length=1)
    min_radio_freq_hz: int = Field(..., gt=0)
    max_radio_freq_hz: int = Field(..., gt=0)
    osc_freq_hz: int | None = Field(None, gt=0)


class DeviceConfigRoot(BaseModel):
    """Wrapper to capture the full device config with validation dependency."""

    device: DeviceConfig

    @model_validator(mode="after")
    def validate_range(self) -> DeviceConfigRoot:
        """Ensure max_radio_freq_hz > min_radio_freq_hz."""
        if self.device.max_radio_freq_hz <= self.device.min_radio_freq_hz:
            raise ValueError(
                f"Device '{self.device.name}': max_radio_freq_hz ({self.device.max_radio_freq_hz}) "
                f"must be greater than min_radio_freq_hz ({self.device.min_radio_freq_hz})"
            )

        return self


class FamilyDeviceExclusion(BaseModel):
    """A single device exclusion entry within a family.

    Required:
        device_name: Name of the device.
        excluded_freq_hz: Frequency the device does NOT support.
    """

    device_name: str = Field(..., min_length=1)
    excluded_freq_hz: int = Field(..., gt=0)


class FamilyConfig(BaseModel):
    """A family configuration (e.g., RFM9X or SX127X).

    Required:
        family_name: Family identifier.
        devices: List of potential device names in the family.
        exclusions: Per-device frequencies not supported.
    """

    family_name: str = Field(..., min_length=1)
    devices: Sequence[str] = Field(..., min_length=1)
    exclusions: Sequence[FamilyDeviceExclusion] = Field(..., min_length=1)


class AntennaConfig(BaseModel):
    """Antenna configuration for a device in an assembly.

    Optional:
        antenna_type: Type of antenna (e.g., "parabolic").
        antenna_gain_db: Gain in decibels (can be negative, positive, or zero).
    """

    antenna_type: str | None = None
    antenna_gain_db: float | None = None


class AssemblyConfig(BaseModel):
    """An assembly linking a module to antenna configurations for its devices.

    Required:
        assembly_name: Identifier for the assembly (e.g., "default").
        module_name: Name of the module this assembly belongs to (must exist in modules).
        devices: Mapping from device_id (format "spi_device_id:ce_number") to AntennaConfig.
    """

    assembly_name: str = Field(..., min_length=1)
    module_name: str = Field(..., min_length=1)
    devices: dict[str, AntennaConfig] = Field(default_factory=dict)


class DeviceModuleAttachment(BaseModel):
    """A device attached to a module with SPI/CE and GPIO pin mappings.

    Required:
        device_name: Device identifier.
        spi_device_id: SPI device number (e.g., 0).
        ce_number: CE slot number (e.g., 0 or 1).

    Optional:
        dio_gpio_mappings: List of "DIOx:GPIOy" mappings.
    """

    device_name: str = Field(..., min_length=1)
    spi_device_id: int = Field(..., ge=0)
    ce_number: int = Field(..., ge=0)
    dio_gpio_mappings: Sequence[str] | None = None


class ModuleConfig(BaseModel):
    """A module configuration describing how devices attach to RPi.

    Required:
        module_name: Module identifier (e.g., "LoRa Pi 434/868").
        devices: List of device attachments with SPI/CE/pin mappings.
    """

    module_name: str = Field(..., min_length=1)
    devices: Sequence[DeviceModuleAttachment] = Field(..., min_length=1)


class Rfm9xSx127xConfig(BaseModel):
    """Top-level configuration containing device, family, module, and assembly configs.

    Required:
        devices: Mapping of device name to DeviceConfig.
        families: Mapping of family name to FamilyConfig.
        modules: Mapping of module name to ModuleConfig.

    Optional:
        assemblies: Mapping of assembly name to AssemblyConfig.
    """

    devices: dict[str, DeviceConfig] = Field(default_factory=dict)
    families: dict[str, FamilyConfig] = Field(default_factory=dict)
    modules: dict[str, ModuleConfig] = Field(default_factory=dict)
    assemblies: dict[str, AssemblyConfig] = Field(default_factory=dict)


class Rfm9xSx127xFamilyConfig(BaseModel):
    """A configuration focused only on family definitions.

    Required:
        families: Mapping of family name to FamilyConfig.
    """

    families: dict[str, FamilyConfig] = Field(default_factory=dict)
