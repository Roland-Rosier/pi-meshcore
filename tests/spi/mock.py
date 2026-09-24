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

from __future__ import annotations

from typing import Protocol


class SpiBus(Protocol):
    """Minimal SPI bus protocol for mocking."""

    def open(self, bus: int, device: int) -> None: ...
    def close(self) -> None: ...
    def xfer2(self, data: list[int]) -> list[int]: ...


class MockSpiBus:
    """Mock implementation of SpiBus protocol with in-memory register simulation."""

    def __init__(
        self,
        bus_number: int = 0,
        device_number: int = 0,
        max_speed_hz: int = 1000000,
        mode: int = 0,
        lsbfirst: bool = False,
        no_cs: bool = False,
    ) -> None:
        """Initialize the mock SPI bus.

        Args:
            bus_number: The bus identifier.
            device_number: The device identifier.
            max_speed_hz: Maximum speed in Hertz.
            mode: SPI mode setting.
            lsbfirst: Whether least significant bit comes first.
            no_cs: Whether chip select is disabled.
        """
        self.bus_number: int = bus_number
        self.device_number: int = device_number
        self._max_speed_hz: int = max_speed_hz
        self._mode: int = mode
        self._lsbfirst: bool = lsbfirst
        self._no_cs: bool = no_cs
        self._registers: dict[int, int] = {}
        self._opened: bool = False

    def open(self, bus: int, device: int) -> None:
        """Open the SPI bus for the given device.

        Args:
            bus: The bus identifier.
            device: The device identifier.
        """
        self.bus_number = bus
        self.device_number = device
        self._opened = True
        self._registers = {}

    def close(self) -> None:
        """Close the SPI bus."""
        self._opened = False
        self._registers = {}

    def xfer2(self, data: list[int]) -> list[int]:
        """Transfer data through the SPI bus using in-memory simulation.

        Args:
            data: List of byte values to transfer.

        Returns:
            List of received byte values (simulated echo).
        """
        if not self._opened:
            raise RuntimeError("SPI bus not opened")

        result: list[int] = []
        for byte_value in data:
            reg_key: int = hash(byte_value) % 256
            simulated_response: int = self._registers.get(reg_key, byte_value) ^ 0xFF
            self._registers[reg_key] = byte_value
            result.append(simulated_response)
        return result

    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz."""
        return self._max_speed_hz

    @property
    def mode(self) -> int:
        """SPI mode setting."""
        return self._mode

    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first."""
        return self._lsbfirst

    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled."""
        return self._no_cs


class MockSpiBusFactory:
    """Mock SPI bus factory that produces ``MockSpiBus`` instances."""

    def create(
        self,
        bus: int = 0,
        device: int = 0,
    ) -> SpiBus:
        """Return a new mock SPI bus configured for *bus* and *device*."""
        return MockSpiBus(bus_number=bus, device_number=device)
