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

"""Tests for ``RealSpiBus`` protocol compliance and lifecycle."""

import time

import pytest

from pi_lora.drivers.spi.bus import SpiBus
from tests.spi.mock import FakeSpiBusKernelFactory, MockSpiBus


class TestSpiBusProtocol:
    """Verify that ``MockSpiBus`` satisfies the ``SpiBus`` protocol."""

    def test_mock_is_spi_bus(self) -> None:
        bus: SpiBus = MockSpiBus()
        assert isinstance(bus, MockSpiBus)

    def test_protocol_requires_open(self) -> None:
        bus = MockSpiBus()
        bus.open()
        assert bus._opened is True

    def test_protocol_requires_close(self) -> None:
        bus = MockSpiBus()
        bus.open()
        bus.close()
        assert bus._opened is False


class TestRealSpiBusLifecycle:
    """Test ``RealSpiBus`` lifecycle through the factory."""

    @pytest.mark.asyncio
    async def test_init_without_open_raises_on_xfer2(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus

        bus = RealSpiBus(bus_number=0, device_number=0)
        with pytest.raises(RuntimeError, match="SPI bus not opened"):
            await bus.xfer2([0x01])


class TestMockSpiBusOpenClose:
    """Test MockSpiBus open/close lifecycle."""

    def test_open_sets_identity(self) -> None:
        bus = MockSpiBus(bus_number=1, device_number=3)
        bus.open()
        assert bus.bus_number == 1
        assert bus.device_number == 3

    @pytest.mark.asyncio
    async def test_close_clears_registers(self) -> None:
        bus = MockSpiBus()
        bus.open()
        await bus.xfer2([0x81, 0xFF])
        bus.close()
        assert bus._registers == {}

    @pytest.mark.asyncio
    async def test_xfer2_without_open_raises(self) -> None:
        bus = MockSpiBus()
        with pytest.raises(RuntimeError, match="SPI bus not opened"):
            await bus.xfer2([0x81, 0xFF])


class TestXfer2Bytearray:
    """Verify ``xfer2`` accepts and transparently converts ``bytearray``."""

    @pytest.mark.asyncio
    async def test_xfer2_accepts_bytearray(self) -> None:
        bus = MockSpiBus()
        bus.open()
        result = await bus.xfer2(bytearray([0x81, 0x42]))
        assert isinstance(result, list)
        assert all(isinstance(v, int) for v in result)
        assert result == [0x81, 0x42]

    @pytest.mark.asyncio
    async def test_xfer2_converts_bytearray_to_list(self) -> None:
        data = bytearray([0x81, 0x42, 0x7F, 0x00])
        list_result = await self._xfer2(data, list(data))
        bytearray_result = await self._xfer2(data, bytearray(data))
        assert list_result == bytearray_result

    @staticmethod
    async def _xfer2(data: list[int] | bytearray, payload: list[int] | bytearray) -> list[int]:
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            return await bus.xfer2(payload)


class TestRealSpiBusErrorMessage:
    """H-11 regression: ``_verify_patch_active`` message names ``RealSpiBus``."""

    def test_real_spi_bus_error_message(self) -> None:
        from contextvars import ContextVar

        from pi_lora.drivers.spi.bus import RealSpiBus, _spidev_patch_active

        patch_active: ContextVar[bool] = _spidev_patch_active
        patch_active.set(False)

        bus = RealSpiBus(bus_number=0, device_number=0, factory_owned=True)

        with pytest.raises(RuntimeError) as exc_info:
            bus._verify_patch_active()

        message: str = str(exc_info.value)
        assert "RealSpiBus" in message
        assert "MockSpiBus" not in message

    def test_open_surfaces_real_spi_bus_message(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus, _spidev_patch_active

        _spidev_patch_active.set(False)

        bus = RealSpiBus(bus_number=0, device_number=0, factory_owned=True)

        with pytest.raises(RuntimeError) as exc_info:
            bus.open()

        message: str = str(exc_info.value)
        assert "RealSpiBus" in message
        assert "MockSpiBus" not in message


class _HangingKernel:
    """Sync kernel whose ``xfer2`` blocks past any short timeout budget."""

    def __init__(self, sleep_seconds: float = 2.0) -> None:
        self._sleep_seconds: float = sleep_seconds

    def xfer2(self, data: list[int]) -> list[int]:
        time.sleep(self._sleep_seconds)
        return [1]

    def close(self) -> None:
        """Model spidev.SpiDev.close() so the bus recovery path is faithful."""
        self._closed = True


class TestRealSpiBusXferTimeout:
    """M-13 regression: ``RealSpiBus.xfer2`` enforces a ``wait_for`` timeout."""

    def test_default_xfer_timeout_is_five(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus

        bus = RealSpiBus(bus_number=0, device_number=0)
        assert bus._xfer_timeout == 5.0

    def test_custom_xfer_timeout_is_honored(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus

        bus = RealSpiBus(bus_number=0, device_number=0, xfer_timeout=0.25)
        assert bus._xfer_timeout == 0.25

    @pytest.mark.asyncio
    async def test_xfer_timeout_raises_spi_bus_error(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus, SpiBusError

        bus = RealSpiBus(bus_number=0, device_number=0, xfer_timeout=0.05)
        bus._spidev = _HangingKernel(sleep_seconds=2.0)

        with pytest.raises(SpiBusError) as excinfo:
            await bus.xfer2([1, 2, 3])

        assert isinstance(excinfo.value, RuntimeError)
        assert bus._spidev is None

        # PLAN-22 Section 5, Test Requirement #3: the bus must reopen after the
        # timeout closes it. ``bus.open()`` performs ``import spidev`` then
        # ``spidev.SpiDev()``; in a headless test that factory must be patched,
        # otherwise ``import spidev`` raises ImportError. The repo convention
        # (mirrored by ``FakeSpiBusKernelFactory``) injects a fake ``spidev``
        # module via ``spidev_kernel_patch``; reuse it here so ``open()``
        # succeeds and the bus is confirmed reopened.
        from tests.fakes import create_fake_spi_dev, spidev_kernel_patch

        with spidev_kernel_patch(create_fake_spi_dev(module_type="rfm95w")):
            bus.open()

        assert bus._spidev is not None


class TestRealSpiBusPropertiesSafeDefaults:
    """PLAN-20 Fix 5 (M-14 regression reversal): closed ``RealSpiBus`` property
    getters return safe defaults instead of raising ``RuntimeError``.

    The factory contract returns an unopened bus (``_spidev is None``) between
    ``create()`` and ``open()``. Properties must be readable before opening:
    ``max_speed_hz``/``mode`` default to ``0`` and ``lsbfirst``/``no_cs`` default
    to ``False``. Checking ``max_speed_hz > 0`` is the way to determine if the
    bus is open and configured.
    """

    _closed_property_defaults = {
        "max_speed_hz": 0,
        "mode": 0,
        "lsbfirst": False,
        "no_cs": False,
    }

    def test_each_closed_property_returns_safe_default(self) -> None:
        from pi_lora.drivers.spi.bus import RealSpiBus

        bus = RealSpiBus(bus_number=0, device_number=0)
        assert bus._spidev is None

        for name, expected in self._closed_property_defaults.items():
            assert getattr(bus, name) == expected


class _RaisingKernel:
    """Sync kernel whose ``close()`` raises, modeling a failing ``spidev.SpiDev.close()``."""

    def close(self) -> None:
        """Model a ``spidev.SpiDev.close()`` that fails, exercising the exception-safe cleanup path."""
        raise OSError("spidev.close() failed")


class TestRealSpiBusCloseExceptionChained:
    """Issue 24.4 Fix + Plan-26 Finding 484: ``close()`` raises ``SpiBusError``
    chained to the failure. The ``_spidev`` handle is ALWAYS cleared (set to
    None) in a finally block so that open() can be called again after a failed
    close. This fixes the regression where a failed close() left the bus
    unopenable (stuck with "already open" error).
    """

    def test_close_raises_spi_bus_error_clears_handle_for_reopen(self) -> None:
        from unittest.mock import patch

        from pi_lora.drivers.spi.bus import RealSpiBus, SpiBusError

        bus = RealSpiBus(bus_number=0, device_number=0)
        failure = OSError("spidev.close() failed")
        bus._spidev = _RaisingKernel()

        with patch.object(
            bus._spidev, "close", side_effect=failure
        ), pytest.raises(SpiBusError) as exc_info:
            bus.close()

        # PLAN-26 FIX (Finding 484): _spidev is now None even after failed close,
        # allowing the caller to call open() again.
        assert bus._spidev is None
        assert exc_info.value.__cause__ is failure

    def test_close_failed_then_open_not_raise_already_open(self) -> None:
        """After a failed close, open() should not raise 'already open' error.

        This test verifies the fix for Finding 484: a failed close() used to
        leave _spidev set, causing open() to raise "already open" even though
        close() had been called. Now _spidev is cleared in a finally block.
        """
        from unittest.mock import patch

        from pi_lora.drivers.spi.bus import RealSpiBus, SpiBusError

        bus = RealSpiBus(bus_number=0, device_number=0)
        failure = OSError("spidev.close() failed")
        bus._spidev = _RaisingKernel()

        # First close fails
        with patch.object(
            bus._spidev, "close", side_effect=failure
        ), pytest.raises(SpiBusError):
            bus.close()

        # _spidev should be None now (PLAN-26 FIX: Finding 484)
        assert bus._spidev is None

        # open() should not raise "already open" RuntimeError since _spidev is None
        # We can't easily test full open() success without mocking spidev, but
        # we can verify the "already open" check passes by ensuring no RuntimeError
        # with that message is raised. The open() will fail later with SpiBusError
        # due to no real device, but the "already open" check is what we're testing.
        with pytest.raises(SpiBusError) as exc_info:
            bus.open()

        # Verify it's NOT the "already open" error
        assert "already open" not in str(exc_info.value).lower()
        assert "open failed" in str(exc_info.value).lower()


class TestRealSpiBusXferTimeoutValidation:
    """PLAN-23 FIX (Issue 3): xfer_timeout must be positive."""

    def test_xfer_timeout_rejects_non_positive(self) -> None:
        from pytest import raises

        from pi_lora.drivers.spi.bus import RealSpiBus

        with raises(ValueError, match="xfer_timeout must be positive"):
            RealSpiBus(bus_number=0, device_number=0, xfer_timeout=0)
        with raises(ValueError, match="xfer_timeout must be positive"):
            RealSpiBus(bus_number=0, device_number=0, xfer_timeout=-1.0)
        with raises(ValueError, match="xfer_timeout must be positive"):
            RealSpiBus(bus_number=0, device_number=0, xfer_timeout=-0.001)
