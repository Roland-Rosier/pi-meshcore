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

"""Integration tests exercising the ``RealSpiBus -> spidev -> kernel SPI`` chain.

The end-to-end test wires a real ``RealSpiBus`` to a :class:`FakeSpiDev` kernel
through :func:`spidev_kernel_patch` and drives :meth:`RealSpiBus.xfer2`, which
acquires the shared per-bus lock via ``await get_bus_lock`` and offloads the
blocking transfer to a worker thread. The end-to-end test wires a real ``RealSpiBus`` to a :class:`FakeSpiDev` kernel
through :func:`spidev_kernel_patch` and drives :meth:`RealSpiBus.xfer2`, which
acquires the shared per-bus lock via ``await get_bus_lock`` and offloads the
blocking transfer to a worker thread.
"""

from __future__ import annotations

import sys

import pytest

from pi_lora.drivers.spi.locks import get_bus_lock
from tests.spi.mock import FakeSpiBusKernelFactory


class TestRealSpiBusKernelChain:
    """End-to-end ``RealSpiBus -> spidev -> kernel SPI`` exercise."""

    @pytest.mark.asyncio
    async def test_real_spi_bus_to_kernel_end_to_end(self) -> None:
        """Construct a ``RealSpiBus`` opened with a fake kernel and run ``xfer2``.

        ``xfer2`` internally acquires the shared per-bus lock via
        ``await get_bus_lock`` and offloads the transfer to the fake kernel SPI,
        which responds to the write transfer with the echoed command+value pair.
        The manual pre-acquire from the original Phase L implementation is
        redundant: ``xfer2`` acquires and releases the same lock instance itself,
        so pre-acquiring it here would deadlock on the non-recursive
        ``aiologic.LowLevelLock``.
        """
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            assert bus.bus_number == 0
            assert bus.device_number == 0
            result = await bus.xfer2(bytearray([0x01 | 0x80, 0x42]))
            assert isinstance(result, list)
            assert len(result) == 2
            assert result == [0x81, 0x42]

    @pytest.mark.asyncio
    async def test_same_bus_lock_is_shared(self) -> None:
        """Two buses on the same bus number share one per-bus lock instance."""
        with (
            FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus_one,
            FakeSpiBusKernelFactory().create_bus(bus=0, device=1) as bus_two,
        ):
            assert await get_bus_lock(bus_one.bus_number) is await get_bus_lock(bus_two.bus_number)

            await bus_one.xfer2(bytearray([0x81, 0x08]))
            await bus_two.xfer2(bytearray([0x42, 0x00]))


class TestRealSpiBusFactory:
    """Tests for ``RealSpiBusFactory.create`` opening the bus itself (Fix #2)."""

    @pytest.mark.asyncio
    async def test_create_returns_opened_bus(self) -> None:
        """``create`` must return an already-opened bus so ``xfer2`` does not raise.

        The factory now calls ``open(bus, device)`` itself for backward
        compatibility, so an external caller that never calls ``open()`` gets a
        bus whose ``xfer2`` does not raise ``RuntimeError("SPI bus not opened")``.
        ``spidev`` is exercised safely through :func:`spidev_kernel_patch`.
        """
        from pi_lora.drivers.spi.factory import RealSpiBusFactory
        from tests.fakes import create_fake_spi_dev, spidev_kernel_patch

        fake_kernel = create_fake_spi_dev(module_type="rfm95w")
        with spidev_kernel_patch(fake_kernel):
            bus = RealSpiBusFactory().create(bus=0, device=1)

        assert bus.bus_number == 0
        assert bus.device_number == 1

        result = await bus.xfer2(bytearray([0x01 | 0x80, 0x42]))
        assert isinstance(result, list)
        assert len(result) == 2
        assert result == [0x81, 0x42]


class TestFakeSpiBusKernelFactoryContext:
    """Coverage for the context-manager lifetime semantics of the factory."""

    @pytest.mark.asyncio
    async def test_patch_active_inside_context(self) -> None:
        """The ``spidev`` patch is active while the bus is yielded.

        Inside the ``with`` block ``bus._spidev`` must be the injected
        :class:`FakeSpiDev` and ``import spidev`` must resolve to the injected
        module, so ``xfer2`` drives the fake kernel SPI.
        """
        from tests.fakes import FakeSpiDev

        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            assert isinstance(bus._spidev, FakeSpiDev)
            assert sys.modules.get("spidev") is not None
            result = await bus.xfer2(bytearray([0x01 | 0x80, 0x42]))
            assert result == [0x81, 0x42]

    def test_patch_restored_after_context(self) -> None:
        """After the context exits the bus is closed and the patch is removed.

        Exiting the ``with`` block must close the bus (``_spidev`` set back to
        ``None``) and restore ``sys.modules`` so no injected ``spidev`` persists.
        """
        from tests.fakes import FakeSpiDev

        preexisting: object | None = sys.modules.get("spidev", None)
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            assert isinstance(bus._spidev, FakeSpiDev)

        assert bus._spidev is None
        assert sys.modules.get("spidev", None) == preexisting
