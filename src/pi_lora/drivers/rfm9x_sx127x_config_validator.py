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

"""Configuration validator for RFM9x/SX127x device configurations."""

from __future__ import annotations

from pydantic import ValidationError

from pi_lora.drivers.rfm9x_sx127x_config_model import (
    DeviceConfig,
    FamilyConfig,
    ModuleConfig,
    Rfm9xSx127xConfig,
)


def validate_device_config(device: DeviceConfig) -> bool:
    """Validate a single device configuration.

    Checks:
        - name is non-empty.
        - min_radio_freq_hz > 0.
        - max_radio_freq_hz > 0.
        - max_radio_freq_hz > min_radio_freq_hz.
        - osc_freq_hz > 0 (if provided).

    Args:
        device: DeviceConfig to validate.

    Returns:
        True if valid.

    Raises:
        ValidationError: If validation fails.
    """
    errors: list[str] = []

    if not device.name or not device.name.strip():
        errors.append("Device name must be non-empty.")

    if device.min_radio_freq_hz <= 0:
        errors.append(f"Device '{device.name}': min_radio_freq_hz must be > 0.")

    if device.max_radio_freq_hz <= 0:
        errors.append(f"Device '{device.name}': max_radio_freq_hz must be > 0.")

    if device.max_radio_freq_hz <= device.min_radio_freq_hz:
        errors.append(
            f"Device '{device.name}': max_radio_freq_hz ({device.max_radio_freq_hz}) "
            f"must be greater than min_radio_freq_hz ({device.min_radio_freq_hz})."
        )

    if device.osc_freq_hz is not None and device.osc_freq_hz <= 0:
        errors.append(f"Device '{device.name}': osc_freq_hz must be > 0.")

    if errors:
        raise ValueError("; ".join(errors))

    return True


def validate_family_config(family: FamilyConfig) -> bool:
    """Validate a single family configuration.

    Checks:
        - family_name is non-empty.
        - devices list is non-empty.
        - exclusions list is non-empty.
        - Each exclusion has valid device_name and excluded_freq_hz > 0.
        - All exclusion device_names are in the devices list.

    Args:
        family: FamilyConfig to validate.

    Returns:
        True if valid.

    Raises:
        ValidationError: If validation fails.
    """
    errors: list[str] = []

    if not family.family_name or not family.family_name.strip():
        errors.append("Family name must be non-empty.")

    if not family.devices:
        errors.append("Family devices list must be non-empty.")

    if not family.exclusions:
        errors.append("Family exclusions list must be non-empty.")

    device_set: set[str] = set(family.devices)
    for exclusion in family.exclusions:
        if not exclusion.device_name or not exclusion.device_name.strip():
            errors.append(
                f"Family '{family.family_name}': exclusion device_name must be non-empty."
            )
        elif exclusion.device_name not in device_set:
            errors.append(
                f"Family '{family.family_name}': exclusion device '{exclusion.device_name}' "
                f"not in devices list."
            )

        if exclusion.excluded_freq_hz <= 0:
            errors.append(
                f"Family '{family.family_name}': exclusion excluded_freq_hz must be > 0."
            )

    if errors:
        raise ValueError("; ".join(errors))

    return True


def validate_module_config(module: ModuleConfig) -> bool:
    """Validate a single module configuration.

    Checks:
        - module_name is non-empty.
        - devices list is non-empty.
        - Each device has valid spi_device_id >= 0 and ce_number >= 0.
        - antenna_gain_db type is enforced by Pydantic (float | None).
        - DIO GPIO mappings follow "DIOx:GPIOy" format (if provided).

    Args:
        module: ModuleConfig to validate.

    Returns:
        True if valid.

    Raises:
        ValidationError: If validation fails.
    """
    errors: list[str] = []

    if not module.module_name or not module.module_name.strip():
        errors.append("Module name must be non-empty.")

    if not module.devices:
        errors.append("Module devices list must be non-empty.")

    dio_pattern: str = r"^DIO[0-5]:GPIO\d+$"
    import re

    for attachment in module.devices:
        if not attachment.device_name or not attachment.device_name.strip():
            errors.append(
                f"Module '{module.module_name}': device name must be non-empty."
            )

        if attachment.spi_device_id < 0:
            errors.append(
                f"Module '{module.module_name}': device '{attachment.device_name}' "
                f"spi_device_id must be >= 0."
            )

        if attachment.ce_number < 0:
            errors.append(
                f"Module '{module.module_name}': device '{attachment.device_name}' "
                f"ce_number must be >= 0."
            )

        if attachment.dio_gpio_mappings:
            for mapping in attachment.dio_gpio_mappings:
                if not re.match(dio_pattern, mapping):
                    errors.append(
                        f"Module '{module.module_name}': device '{attachment.device_name}' "
                        f"invalid DIO GPIO mapping: '{mapping}'. Expected 'DIOx:GPIOy'."
                    )

    if errors:
        raise ValueError("; ".join(errors))

    return True


def validate_full_config(config: Rfm9xSx127xConfig) -> bool:
    """Validate a complete Rfm9x/SX127x configuration.

    Validates all devices, families, and modules.

    Args:
        config: Rfm9xSx127xConfig to validate.

    Returns:
        True if valid.

    Raises:
        ValidationError: If any validation fails.
    """
    all_errors: list[str] = []

    for device_name, device in config.devices.items():
        try:
            validate_device_config(device)
        except ValidationError as exc:
            all_errors.append(f"Device '{device_name}': {exc}")

    for family_name, family in config.families.items():
        try:
            validate_family_config(family)
        except ValidationError as exc:
            all_errors.append(f"Family '{family_name}': {exc}")

    for module_name, module in config.modules.items():
        try:
            validate_module_config(module)
        except ValidationError as exc:
            all_errors.append(f"Module '{module_name}': {exc}")

    if all_errors:
        raise ValueError("; ".join(all_errors))

    return True
