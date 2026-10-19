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

import asyncio
from typing import Any, Protocol

from .locks import get_bus_lock


class SpiBus(Protocol):
    """Protocol defining the SPI bus interface."""

    def open(self, bus: int, device: int) -> None:
        """Open the SPI bus for the given device."""

    def close(self) -> None:
        """Close the SPI bus."""

    async def xfer2(self, data: list[int] | bytearray) -> list[int]:
        """Transfer data through the SPI bus.

        Args:
            data: Byte array of byte values to transfer.

        Returns:
            List of received byte values.
        """

    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz."""

    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None:
        """Set maximum speed in Hertz."""

    @property
    def mode(self) -> int:
        """SPI mode setting."""

    @mode.setter
    def mode(self, value: int) -> None:
        """Set SPI mode setting."""

    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first."""

    @lsbfirst.setter
    def lsbfirst(self, value: bool) -> None:
        """Set whether least significant bit comes first."""

    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled."""

    @no_cs.setter
    def no_cs(self, value: bool) -> None:
        """Set whether chip select is disabled."""


class RealSpiBus:
    """Real implementation of SpiBus wrapping spidev.SpiDev."""

    def __init__(self) -> None:
        """Initialize the real SPI bus.

        Bus/device identity is set by ``open()`` — matching the underlying
        ``spidev.SpiDev`` lifecycle (init → open).
        """
        # spidev.SpiDev has no stubs; use Any to suppress attr-defined errors.
        self._spidev: Any | None = None
        self.bus_number: int = 0
        self.device_number: int = 0

    def open(self, bus: int, device: int) -> None:
        """Open the SPI bus for the given device.

        Args:
            bus: The bus identifier.
            device: The device identifier.
        """
        # Note: spidev is a real python library; do not assume otherwise
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

    async def xfer2(self, data: list[int] | bytearray) -> list[int]:
        """Transfer data through the SPI bus.

        Acquires the shared per-bus critical-section lock from the lock registry
        (the same lock instance for every bus on the same bus number) via an
        ``async with lock`` context manager, then offloads the blocking
        ``spidev.SpiDev.xfer2`` call to a worker thread via ``asyncio.to_thread``
        *inside* the lock scope so it does not block the event loop while still
        preserving per-bus mutual exclusion. The lock is held for the entire
        transfer duration, guaranteeing that two ``RealSpiBus`` instances on the
        same bus number never run their transfers concurrently.

        ``aiologic.Lock`` acquires on entry and releases on exit of the
        ``async with`` block, so the lock is released automatically on normal
        completion. If ``__aenter__`` raises (cancellation/timeout) the original
        exception propagates out of ``xfer2`` and the transfer is never
        attempted, so ``asyncio.to_thread`` is never called; aiologic.Lock manages
        cancellation internally and never leaks a release on an unacquired state.

        Args:
            data: Byte array of byte values to transfer.

        Returns:
            List of received byte values.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened")

        lock = await get_bus_lock(self.bus_number)
        async with lock:
            return await asyncio.to_thread(self._spidev.xfer2, data)

    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz."""
        if self._spidev is not None:
            return self._spidev.max_speed_hz  # type: ignore[no-any-return]
        return 0

    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None:
        """Set maximum speed in Hertz."""
        if self._spidev is not None:
            self._spidev.max_speed_hz = value

    @property
    def mode(self) -> int:
        """SPI mode setting."""
        if self._spidev is not None:
            return self._spidev.mode  # type: ignore[no-any-return]
        return 0

    @mode.setter
    def mode(self, value: int) -> None:
        """Set SPI mode setting."""
        if self._spidev is not None:
            self._spidev.mode = value

    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first."""
        if self._spidev is not None:
            return self._spidev.lsbfirst  # type: ignore[no-any-return]
        return False

    @lsbfirst.setter
    def lsbfirst(self, value: bool) -> None:
        """Set whether least significant bit comes first."""
        if self._spidev is not None:
            self._spidev.lsbfirst = value

    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled."""
        if self._spidev is not None:
            return self._spidev.no_cs  # type: ignore[no-any-return]
        return False

    @no_cs.setter
    def no_cs(self, value: bool) -> None:
        """Set whether chip select is disabled."""
        if self._spidev is not None:
            self._spidev.no_cs = value
