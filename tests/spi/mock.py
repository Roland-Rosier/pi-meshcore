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

import os

from pi_lora.drivers.spi.bus import RealSpiBus, SpiBus
from tests.fakes import create_fake_spi_dev, spidev_kernel_patch


class MockSpiBus:
    """Mock implementation of SpiBus protocol with in-memory register simulation."""

    def __init__(
        self,
        max_speed_hz: int = 1000000,
        mode: int = 0,
        lsbfirst: bool = False,
        no_cs: bool = False,
    ) -> None:
        """Initialize the mock SPI bus.

        Bus/device identity is set by ``open()`` — matching the underlying
        ``spidev.SpiDev`` lifecycle (init → open).

        Args:
            max_speed_hz: Maximum speed in Hertz.
            mode: SPI mode setting.
            lsbfirst: Whether least significant bit comes first.
            no_cs: Whether chip select is disabled.
        """
        self.bus_number: int = 0
        self.device_number: int = 0
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

    async def xfer2(self, data: list[int]) -> list[int]:
        """Transfer data through the SPI bus using in-memory simulation.

        Implements address-based register simulation matching ``FakeSpiDev``:
        each byte pair is (address_cmd, value) where the high bit of the
        address byte indicates write (0x80) vs read (0x7F).  Read operations
        return the stored register value; write operations store the value
        and echo back the command+value pair.

        Args:
            data: List of byte values to transfer.

        Returns:
            List of received byte values (simulated response).
        """
        if not self._opened:
            raise RuntimeError("SPI bus not opened")

        if not data:
            return []

        result: list[int] = []
        i: int = 0
        while i < len(data):
            cmd_byte: int = data[i]
            address: int = cmd_byte & 0x7F
            is_write: bool = (cmd_byte & 0x80) != 0

            if is_write:
                if i + 1 >= len(data):
                    raise ValueError("Incomplete write command")
                value: int = data[i + 1]
                self._registers[address] = value
                result.append(cmd_byte)
                result.append(value)
                i += 2
            else:
                reg_value: int = self._registers.get(address, 0x00)
                result.append(cmd_byte)
                result.append(reg_value)
                i += 2

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
        mock_bus = MockSpiBus(max_speed_hz=1000000, mode=0, lsbfirst=False, no_cs=False)
        mock_bus.open(bus=bus, device=device)
        return mock_bus


def hardware_enabled() -> bool:
    """Return True when the ``PI_LORA_HARDWARE`` runtime flag is set to ``1``.

    Real-hardware integration tests are gated on this flag so they run only on
    actual RPi hardware and remain valid no-ops when the flag is unset.

    :return: True when ``os.environ["PI_LORA_HARDWARE"] == "1"``.
    """
    return os.environ.get("PI_LORA_HARDWARE", "0") == "1"


def spidev_available() -> bool:
    """Return True when the real ``spidev`` Cython extension is importable.

    :return: True if ``import spidev`` succeeds.
    """
    try:
        import spidev  # noqa: F401

        return True
    except ImportError:
        return False


class FakeSpiBusKernelFactory:
    """Produces a ``RealSpiBus`` wired to a fake ``spidev`` kernel SPI.

    The factory builds a real :class:`RealSpiBus`, then opens it inside
    :func:`spidev_kernel_patch` so ``RealSpiBus.open`` exercises the genuine
    ``import spidev`` / ``spidev.SpiDev()`` / ``.open()`` path with a
    :class:`FakeSpiDev` kernel instead of the real Cython extension. This
    exercises the ``RealSpiBus -> spidev -> kernel SPI`` chain end-to-end.
    """

    def create(self, bus: int, device: int) -> RealSpiBus:
        """Return an opened ``RealSpiBus`` whose ``_spidev`` is a :class:`FakeSpiDev`.

        Args:
            bus: The bus identifier.
            device: The device identifier.

        Returns:
            An opened ``RealSpiBus`` whose ``_spidev`` is the fake kernel.
        """
        bus_instance: RealSpiBus = RealSpiBus()
        fake_kernel = create_fake_spi_dev(module_type="rfm95w")
        with spidev_kernel_patch(fake_kernel):
            bus_instance.open(bus=bus, device=device)
        return bus_instance
