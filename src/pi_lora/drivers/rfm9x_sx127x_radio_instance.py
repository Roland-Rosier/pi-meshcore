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

"""Radio instance configuration aggregation for RFM9x/SX127x devices."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    DeviceConfig,
    Rfm9xSx127xConfig,
)


class DeviceIdentity(NamedTuple):
    """Structured key for SPI/CE device identification."""

    spi_device_id: int
    ce_number: int

    def __str__(self) -> str:
        return f"{self.spi_device_id}:{self.ce_number}"


@dataclass(frozen=True, slots=True)
class RadioInstanceConfig:
    """Aggregated configuration for a single radio module instance."""

    # Identity
    module_name: str
    spi_device_id: int
    ce_number: int

    # Device specs (from DeviceConfig)
    device_name: str
    min_radio_freq_hz: int
    max_radio_freq_hz: int
    osc_freq_hz: int | None

    # Family info (from FamilyConfig)
    family_name: str
    excluded_frequencies_hz: tuple[int, ...]

    # Module attachment (from DeviceModuleAttachment)
    dio_gpio_mappings: tuple[str, ...]

    # Assembly antenna (from assembly devices["spi:ce"])
    antenna_type: str | None
    antenna_gain_db: float | None

    @property
    def frequency_range_hz(self) -> tuple[int, int]:
        """Return the device frequency range as a tuple."""
        return (self.min_radio_freq_hz, self.max_radio_freq_hz)

    @property
    def device_id_key(self) -> DeviceIdentity:
        """Return the structured device identity key."""
        return DeviceIdentity(self.spi_device_id, self.ce_number)

    @property
    def supported_frequencies_hz(self) -> tuple[int, int]:
        """Return (min_freq_hz, max_freq_hz) bounds tuple."""
        return (self.min_radio_freq_hz, self.max_radio_freq_hz)

    def __repr__(self) -> str:
        return (f"RadioInstanceConfig(module={self.module_name!r}, "
                f"device={self.device_id_key}, "
                f"freq_range={self.frequency_range_hz})")


class RadioInstanceError(Exception):
    """Base exception with structured context for observability."""

    def __init__(self, message: str, context: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.context: dict[str, object] = context or {}


class ModuleNotFoundError(RadioInstanceError):
    """Raised when a module is not found in the config."""

    def __init__(self, module_name: str) -> None:
        super().__init__(f"Module '{module_name}' not found", {"module_name": module_name})


class DeviceAttachmentNotFoundError(RadioInstanceError):
    """Raised when no device attachment matches the given SPI/CE."""

    def __init__(self, module_name: str, spi_device_id: int, ce_number: int) -> None:
        super().__init__(
            f"No attachment for module '{module_name}' at SPI:{spi_device_id} CE:{ce_number}",
            {"module_name": module_name, "spi_device_id": spi_device_id, "ce_number": ce_number}
        )


class AssemblyNotFoundError(RadioInstanceError):
    """Raised when no assembly is found for the module."""

    def __init__(self, module_name: str, device_key: DeviceIdentity) -> None:
        super().__init__(
            f"No assembly found for module '{module_name}' device {device_key}",
            {"module_name": module_name, "device_key": str(device_key)}
        )


class DeviceSpecNotFoundError(RadioInstanceError):
    """Raised when a device spec is not found in the config."""

    def __init__(self, device_name: str) -> None:
        super().__init__(f"Device spec '{device_name}' not found", {"device_name": device_name})


class FamilyNotFoundError(RadioInstanceError):
    """Raised when no family contains the given device."""

    def __init__(self, device_name: str) -> None:
        super().__init__(f"No family found containing device '{device_name}'", {"device_name": device_name})


class ConfigConsistencyError(RadioInstanceError):
    """Raised when cross-reference validation fails."""

    def __init__(self, message: str, context: dict[str, object] | None = None) -> None:
        super().__init__(message, context)


def create_radio_instance(
    assembly_name: str,
    spi_device_id: int,
    ce_number: int,
    config: Rfm9xSx127xConfig,
) -> RadioInstanceConfig:
    """Resolve and aggregate configuration for a single radio instance.

    Args:
        assembly_name: Assembly identifier (e.g., "default").
        spi_device_id: SPI bus number (e.g., 0).
        ce_number: Chip enable slot (e.g., 0 or 1).
        config: Pre-loaded config (REQUIRED - no global default).

    Returns:
        Fully populated RadioInstanceConfig.

    Raises:
        ModuleNotFoundError: If module_name not in config.modules.
        DeviceAttachmentNotFoundError: If no attachment matches spi_device_id/ce_number.
        AssemblyNotFoundError: If no assembly found for the module.
        DeviceSpecNotFoundError: If device spec not in config.devices.
        FamilyNotFoundError: If no family contains the device_name.
        ConfigConsistencyError: If cross-reference validation fails.
    """
    # 1. Get assembly (physical deployment unit with antenna config)
    if assembly_name not in config.assemblies:
        raise AssemblyNotFoundError(assembly_name, DeviceIdentity(spi_device_id, ce_number))

    assembly = config.assemblies[assembly_name]

    # 2. Get module name from assembly
    module_name = assembly.module_name
    if module_name not in config.modules:
        raise ModuleNotFoundError(module_name)

    module_obj = config.modules[module_name]

    # 3. Find device attachment matching spi/ce
    matching_attachments = [
        att for att in module_obj.devices
        if att.spi_device_id == spi_device_id and att.ce_number == ce_number
    ]

    if len(matching_attachments) == 0:
        raise DeviceAttachmentNotFoundError(module_name, spi_device_id, ce_number)

    if len(matching_attachments) > 1:
        raise ConfigConsistencyError(
            f"Multiple attachments found for module '{module_name}' at SPI:{spi_device_id} CE:{ce_number}",
            {"module_name": module_name, "spi_device_id": spi_device_id, "ce_number": ce_number}
        )

    attachment = matching_attachments[0]
    device_name: str = attachment.device_name
    dio_gpio_mappings_list = attachment.dio_gpio_mappings if attachment.dio_gpio_mappings else []
    dio_gpio_mappings: tuple[str, ...] = tuple(dio_gpio_mappings_list)

    # 4. Get device spec
    device_spec: DeviceConfig | None = None
    for _key, spec in config.devices.items():
        if spec.name == device_name:
            device_spec = spec
            break

    if device_spec is None:
        raise DeviceSpecNotFoundError(device_name)

    # 5. RESOLVE FAMILY: Reverse lookup (device → family) — NOT device_spec.family_name
    matching_families = [
        fam for fam in config.families.values()
        if device_spec.name in fam.devices
    ]
    if not matching_families:
        raise FamilyNotFoundError(device_spec.name)
    # Tie-break: first match (documented contract)
    family_config = matching_families[0]

    # 6. Get antenna config from assembly.devices["spi:ce"]
    antenna_type: str | None = None
    antenna_gain_db: float | None = None

    antenna_key = f"{spi_device_id}:{ce_number}"
    antenna_cfg = assembly.devices.get(antenna_key) if assembly.devices else None
    if antenna_cfg is not None:
        antenna_type = antenna_cfg.antenna_type
        antenna_gain_db = antenna_cfg.antenna_gain_db

    # 7. Collect excluded frequencies for this device from family
    excluded_freqs: list[int] = []
    for exclusion in family_config.exclusions:
        if exclusion.device_name == device_name:
            excluded_freqs.append(exclusion.excluded_freq_hz)
    excluded_frequencies_hz: tuple[int, ...] = tuple(excluded_freqs)

    # 8. Cross-reference validation
    if len(excluded_freqs) > 0:
        for excl_freq in excluded_freqs:
            if excl_freq < device_spec.min_radio_freq_hz or excl_freq > device_spec.max_radio_freq_hz:
                raise ConfigConsistencyError(
                    f"Excluded frequency {excl_freq} Hz outside device '{device_name}' range "
                    f"[{device_spec.min_radio_freq_hz}, {device_spec.max_radio_freq_hz}]",
                    {
                        "device_name": device_name,
                        "excluded_freq_hz": excl_freq,
                        "min_radio_freq_hz": device_spec.min_radio_freq_hz,
                        "max_radio_freq_hz": device_spec.max_radio_freq_hz,
                    }
                )

    if antenna_gain_db is not None and (antenna_gain_db < -100.0 or antenna_gain_db > 200.0):
        raise ConfigConsistencyError(
            f"Antenna gain {antenna_gain_db} dB out of physical range for '{device_name}'",
            {"device_name": device_name, "antenna_gain_db": antenna_gain_db}
        )

    if device_spec.osc_freq_hz is not None and (device_spec.osc_freq_hz < 1000 or device_spec.osc_freq_hz > 10_000_000_000):
        raise ConfigConsistencyError(
            f"OSC frequency {device_spec.osc_freq_hz} Hz out of range for '{device_name}'",
            {"device_name": device_name, "osc_freq_hz": device_spec.osc_freq_hz}
        )

    # 9. Construct and return (without channel_spacing_hz)
    result: RadioInstanceConfig = RadioInstanceConfig(
        module_name=module_name,
        spi_device_id=spi_device_id,
        ce_number=ce_number,
        device_name=device_name,
        min_radio_freq_hz=device_spec.min_radio_freq_hz,
        max_radio_freq_hz=device_spec.max_radio_freq_hz,
        osc_freq_hz=device_spec.osc_freq_hz,
        family_name=family_config.family_name,
        excluded_frequencies_hz=excluded_frequencies_hz,
        dio_gpio_mappings=dio_gpio_mappings,
        antenna_type=antenna_type,
        antenna_gain_db=antenna_gain_db,
    )

    return result


def create_radio_instance_from_default(
    assembly_name: str,
    spi_device_id: int,
    ce_number: int,
) -> RadioInstanceConfig:
    """Convenience wrapper using the preloaded default config."""
    from pi_lora.drivers.rfm9x_sx127x_config_loader import get_preloaded_config
    return create_radio_instance(assembly_name, spi_device_id, ce_number, get_preloaded_config())
