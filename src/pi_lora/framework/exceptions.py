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

"""Framework exceptions for config query operations."""

from __future__ import annotations


class ConfigQueryError(Exception):
    """Base exception for config query errors."""
    pass


class AssemblyNotFoundError(ConfigQueryError):
    """Raised when an assembly is not found in the configuration."""
    pass


class DeviceAttachmentNotFoundError(ConfigQueryError):
    """Raised when no device attachment matches the given SPI/CE."""
    pass


class ConfigLoadError(ConfigQueryError):
    """Raised when configuration fails to load."""
    pass
