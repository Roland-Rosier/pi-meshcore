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

"""Tests for the Plan-19 SPI bus double-open guard on ``RealSpiBus.open``.

``RealSpiBus.open`` refuses a second ``open()`` without an intervening
``close()`` by raising ``RuntimeError`` containing "already open". The
complementary test proves the guard lifts once the bus has been closed.
"""

import pytest

from tests.spi.mock import FakeSpiBusKernelFactory


class TestRealSpiBusOpenGuard:
    """Plan-19 Fix 5: ``open()`` guards against a second open without close()."""

    def test_spi_bus_open_twice_raises(self) -> None:
        """A second ``open()`` inside the opened block raises "already open".

        ``FakeSpiBusKernelFactory.create_bus`` yields an opened
        :class:`RealSpiBus` whose ``_spidev`` is set, so the Plan-19 guard fires
        on the second ``open()`` before it reaches ``import spidev``.
        """
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus, pytest.raises(
            RuntimeError, match="already open"
        ):
            bus.open()

    def test_spi_bus_reopen_after_close(self) -> None:
        """After ``close()``, ``open()`` reopens without raising.

        The guard only fires while ``_spidev`` is set. Closing clears it, so a
        subsequent ``open()`` inside the active patch block succeeds.
        """
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            bus.close()
            bus.open()
