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

from typing import Any, Protocol


class SpiBus(Protocol):
    """Protocol defining the SPI bus interface."""

    def open(self, bus: int, device: int) -> None:
        """Open the SPI bus for the given device."""

    def close(self) -> None:
        """Close the SPI bus."""

    def xfer2(self, data: list[int]) -> list[int]:
        """Transfer data through the SPI bus.

        Args:
            data: List of byte values to transfer.

        Returns:
            List of received byte values.
        """

    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz."""

    @property
    def mode(self) -> int:
        """SPI mode setting."""

    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first."""

    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled."""


class RealSpiBus:
    """Real implementation of SpiBus wrapping spidev.SpiDev."""

    def __init__(self, bus_number: int = 0, device_number: int = 0) -> None:
        """Initialize the real SPI bus.

        Args:
            bus_number: The bus identifier.
            device_number: The device identifier.
        """
        self.bus_number: int = bus_number
        self.device_number: int = device_number
        # spidev.SpiDev has no stubs; use Any to suppress attr-defined errors.
        self._spidev: Any | None = None

    def open(self, bus: int, device: int) -> None:
        """Open the SPI bus for the given device.

        Args:
            bus: The bus identifier.
            device: The device identifier.
        """
        import spidev

        self.bus_number = bus
        self.device_number = device
        self._spidev = spidev.SpiDev()
        self._spidev.open(bus, device)

    def close(self) -> None:
        """Close the SPI bus."""
        if self._spidev is not None:
            self._spidev.close()
            self._spidev = None

    def xfer2(self, data: list[int]) -> list[int]:
        """Transfer data through the SPI bus.

        Args:
            data: List of byte values to transfer.

        Returns:
            List of received byte values.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened")

        return self._spidev.xfer2(data)  # type: ignore[no-any-return]

    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz."""
        if self._spidev is not None:
            return self._spidev.max_speed_hz  # type: ignore[no-any-return]
        return 0

    @property
    def mode(self) -> int:
        """SPI mode setting."""
        if self._spidev is not None:
            return self._spidev.mode  # type: ignore[no-any-return]
        return 0

    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first."""
        if self._spidev is not None:
            return self._spidev.lsbfirst  # type: ignore[no-any-return]
        return False

    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled."""
        if self._spidev is not None:
            return self._spidev.no_cs  # type: ignore[no-any-return]
        return False
