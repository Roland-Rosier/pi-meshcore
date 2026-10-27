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

"""Contract tests pinning ``SpiBus`` protocol conformance (R-2 regression).

These tests verify that the ``SpiBus.open`` protocol declares optional
``bus``/``device`` parameters that mirror :meth:`RealSpiBus.open`, closing the
Liskov Substitution violation that existed while the protocol used required
parameters.
"""

import inspect
from unittest.mock import MagicMock

import aiologic
from src.pi_lora.drivers.spi.bus import RealSpiBus, SpiBus
from src.pi_lora.drivers.spi.factory import RealSpiBusFactory
from src.pi_lora.drivers.spi.locks import SpiLock

from tests.fakes import spidev_kernel_patch
from tests.spi.mock import MockSpiBus, MockSpiBusFactory


def _is_spi_bus(bus: object) -> bool:
    """Return True when *bus* duck-types the ``SpiBus`` protocol.

    ``SpiBus`` is not ``@runtime_checkable``, so a direct ``isinstance`` against
    the protocol is unavailable; the required members are inspected instead.
    The ``max_speed_hz``/``mode``/``lsbfirst``/``no_cs`` members are properties
    declared on the class, so they are checked on ``type(bus)`` (property objects
    on the class do not invoke the getter and therefore do not raise the
    closed-property ``RuntimeError``), while the methods are checked on the
    instance.
    """
    bus_type = type(bus)
    return (
        hasattr(bus, "open")
        and hasattr(bus, "close")
        and hasattr(bus, "xfer2")
        and hasattr(bus_type, "max_speed_hz")
        and hasattr(bus_type, "mode")
        and hasattr(bus_type, "lsbfirst")
        and hasattr(bus_type, "no_cs")
    )


class TestSpiBusContract:
    """Contract tests for the ``SpiBus`` protocol conformance."""

    def test_create_returns_unopened_bus(self) -> None:
        real_bus = RealSpiBusFactory().create(bus=5, device=6)
        assert isinstance(real_bus, RealSpiBus)
        assert _is_spi_bus(real_bus)
        assert real_bus.bus_number == 5
        assert real_bus.device_number == 6

        mock_bus = MockSpiBusFactory().create(bus=5, device=6)
        assert isinstance(mock_bus, MockSpiBus)
        assert _is_spi_bus(mock_bus)
        assert mock_bus._opened is False
        assert mock_bus.bus_number == 5
        assert mock_bus.device_number == 6

    def test_open_with_no_args_uses_stored_params(self) -> None:
        real_bus = RealSpiBusFactory().create(bus=5, device=6)
        kernel = MagicMock()
        with spidev_kernel_patch(kernel):
            real_bus.open()
        assert kernel.open.call_args == ((5, 6),)
        assert real_bus.bus_number == 5
        assert real_bus.device_number == 6

        mock_bus = MockSpiBusFactory().create(bus=5, device=6)
        assert mock_bus.bus_number == 5
        assert mock_bus.device_number == 6

    def test_open_with_explicit_args_overrides_stored(self) -> None:
        real_bus = RealSpiBusFactory().create(bus=5, device=6)
        kernel = MagicMock()
        with spidev_kernel_patch(kernel):
            real_bus.open(bus=7, device=8)
        assert kernel.open.call_args == ((7, 8),)
        assert real_bus.bus_number == 7
        assert real_bus.device_number == 8

        mock_bus = MockSpiBusFactory().create(bus=5, device=6)
        mock_bus.open(7, 8)
        assert mock_bus.bus_number == 7
        assert mock_bus.device_number == 8
        assert mock_bus._opened is True

    def test_protocol_signature_matches_implementation(self) -> None:
        proto_params = [
            param
            for param in inspect.signature(SpiBus.open).parameters.values()
            if param.name != "self"
        ]
        impl_params = [
            param
            for param in inspect.signature(RealSpiBus.open).parameters.values()
            if param.name != "self"
        ]
        assert [param.name for param in proto_params] == ["bus", "device"]
        assert [param.name for param in impl_params] == ["bus", "device"]
        for param in (*proto_params, *impl_params):
            assert param.default is not inspect.Parameter.empty

    def test_mock_open_params_are_optional(self) -> None:
        mock_params = [
            param
            for param in inspect.signature(MockSpiBus.open).parameters.values()
            if param.name != "self"
        ]
        assert [param.name for param in mock_params] == ["bus", "device"]
        for param in mock_params:
            assert param.default is not inspect.Parameter.empty

    def test_mock_property_setters(self) -> None:
        mock_bus = MockSpiBus()
        mock_bus.max_speed_hz = 5
        assert mock_bus.max_speed_hz == 5
        mock_bus.mode = 1
        assert mock_bus.mode == 1
        mock_bus.lsbfirst = True
        assert mock_bus.lsbfirst is True
        mock_bus.no_cs = True
        assert mock_bus.no_cs is True

    def test_mock_open_with_no_args_uses_stored_params(self) -> None:
        mock_bus = MockSpiBusFactory().create(bus=5, device=6)
        mock_bus.open()
        assert mock_bus.bus_number == 5
        assert mock_bus.device_number == 6
        assert mock_bus._opened is True


class TestSpiLockContract:
    """Contract tests for the ``SpiLock`` protocol release API (H-4 regression).

    Verifies that ``green_release`` is present both on the concrete
    :class:`aiologic.Lock` runtime object and on the ``SpiLock`` protocol,
    closing the static-vs-runtime mismatch that existed while the protocol
    omitted the sync/greenlet release method.
    """

    def test_aiologic_lock_has_green_release_at_runtime(self) -> None:
        assert hasattr(aiologic.Lock(), "green_release") is True
        assert hasattr(aiologic.Lock(), "release") is False

    def test_green_release_is_declared_on_protocol(self) -> None:
        declared = getattr(SpiLock, "__annotations__", {})
        method_names = set(declared) | {
            member
            for member in dir(SpiLock)
            if callable(getattr(SpiLock, member, None))
        }
        assert "green_release" in method_names
        assert "async_release" in method_names
