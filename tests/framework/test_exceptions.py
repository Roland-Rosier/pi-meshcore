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

"""Unit tests for framework exceptions."""

from __future__ import annotations

import pytest

from pi_lora.framework.exceptions import (
    AssemblyNotFoundError,
    ConfigLoadError,
    ConfigQueryError,
    DeviceAttachmentNotFoundError,
)


class TestConfigQueryError:
    """Test base exception behavior."""

    def test_config_query_error_is_exception(self) -> None:
        """ConfigQueryError is a subclass of Exception."""
        assert issubclass(ConfigQueryError, Exception)

    def test_config_query_error_can_be_raised_and_caught(self) -> None:
        """ConfigQueryError can be raised and caught."""
        with pytest.raises(ConfigQueryError):
            raise ConfigQueryError("test error")


class TestAssemblyNotFoundError:
    """Test AssemblyNotFoundError behavior."""

    def test_assembly_not_found_error_is_config_query_error(self) -> None:
        """AssemblyNotFoundError is a subclass of ConfigQueryError."""
        assert issubclass(AssemblyNotFoundError, ConfigQueryError)

    def test_assembly_not_found_error_contains_message(self) -> None:
        """AssemblyNotFoundError contains the assembly name in its message."""
        exc = AssemblyNotFoundError("test_assembly")
        assert "test_assembly" in str(exc)


class TestDeviceAttachmentNotFoundError:
    """Test DeviceAttachmentNotFoundError behavior."""

    def test_device_attachment_not_found_error_is_config_query_error(self) -> None:
        """DeviceAttachmentNotFoundError is a subclass of ConfigQueryError."""
        assert issubclass(DeviceAttachmentNotFoundError, ConfigQueryError)

    def test_device_attachment_not_found_error_contains_info(self) -> None:
        """DeviceAttachmentNotFoundError contains SPI/CE info in message."""
        exc = DeviceAttachmentNotFoundError("test_module", 0, 1)
        assert "test_module" in str(exc)
        assert "0" in str(exc)
        assert "1" in str(exc)


class TestConfigLoadError:
    """Test ConfigLoadError behavior."""

    def test_config_load_error_is_config_query_error(self) -> None:
        """ConfigLoadError is a subclass of ConfigQueryError."""
        assert issubclass(ConfigLoadError, ConfigQueryError)

    def test_config_load_error_can_be_raised_and_caught(self) -> None:
        """ConfigLoadError can be raised and caught."""
        with pytest.raises(ConfigLoadError):
            raise ConfigLoadError("config load failed")


class TestExceptionHierarchy:
    """Test exception hierarchy relationships."""

    def test_all_exceptions_inherit_from_config_query_error(self) -> None:
        """All framework exceptions inherit from ConfigQueryError."""
        assert issubclass(AssemblyNotFoundError, ConfigQueryError)
        assert issubclass(DeviceAttachmentNotFoundError, ConfigQueryError)
        assert issubclass(ConfigLoadError, ConfigQueryError)


if __name__ == "__main__":
    import sys
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
