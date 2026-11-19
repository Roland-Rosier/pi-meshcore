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

import warnings

from .rfm9x_sx127x_radio_instance import (
    AssemblyNotFoundError,
    ConfigConsistencyError,
    DeviceAttachmentNotFoundError,
    DeviceIdentity,
    DeviceSpecNotFoundError,
    DriverModuleNotFoundError,
    FamilyNotFoundError,
    RadioInstanceConfig,
    RadioInstanceError,
    create_radio_instance,
    create_radio_instance_from_default,
)
from .spi.bus import SpiBusError

__all__: list[str] = [
    "RadioInstanceConfig",
    "DeviceIdentity",
    "create_radio_instance",
    "create_radio_instance_from_default",
    "RadioInstanceError",
    "DriverModuleNotFoundError",
    "DeviceAttachmentNotFoundError",
    "AssemblyNotFoundError",
    "DeviceSpecNotFoundError",
    "FamilyNotFoundError",
    "ConfigConsistencyError",
    "SpiBusError",
]

# Deprecated alias for backward compatibility (see docs/plan_summaries/2026_10_08_hardening_spike.md)
# Use DriverModuleNotFoundError instead — this alias will be removed in v2.0
from .rfm9x_sx127x_radio_instance import (
    DriverModuleNotFoundError as _DriverModuleNotFoundError,
)


class ModuleNotFoundError(_DriverModuleNotFoundError):
    """Deprecated: Use DriverModuleNotFoundError instead."""

    def __init__(self, module_name: str) -> None:
        warnings.warn(
            "ModuleNotFoundError is deprecated; use DriverModuleNotFoundError",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(module_name)

