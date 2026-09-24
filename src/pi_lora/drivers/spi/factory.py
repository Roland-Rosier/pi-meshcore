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

from pi_lora.drivers.spi.bus import SpiBus


class SpiBusFactory(Protocol):
    """Protocol defining SPI bus factory interface."""

    def create(self, bus: int, device: int) -> SpiBus:
        """Create a SpiBus instance.

        Args:
            bus: The bus identifier.
            device: The device identifier.

        Returns:
            A SpiBus implementation.
        """


class RealSpiBusFactory:
    """Real implementation of SpiBusFactory."""

    def create(self, bus: int, device: int) -> SpiBus:
        """Create a RealSpiBus instance.

        Args:
            bus: The bus identifier.
            device: The device identifier.

        Returns:
            A new RealSpiBus instance.
        """
        from pi_lora.drivers.spi.bus import RealSpiBus

        return RealSpiBus(bus_number=bus, device_number=device)
