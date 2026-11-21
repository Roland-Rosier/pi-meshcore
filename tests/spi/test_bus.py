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

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pi_lora.drivers.spi.bus import RealSpiBus, SpiBusError, _spidev_patch_active
from tests.spi.mock import FakeSpiBusKernelFactory


async def _timeout_kernel(*_args: Any) -> None:
    """Simulate a blocking ``spidev.xfer2`` that exceeds the timeout budget.

    ``asyncio.wait_for`` surfaces this as ``asyncio.TimeoutError``, exercising the
    hardware-reset recovery branch of :meth:`RealSpiBus.xfer2`.
    """
    raise TimeoutError("xfer exceeded budget")


def _fake_to_thread(_callable_: Any, *args: Any) -> Any:
    """Return a coroutine that raises ``asyncio.TimeoutError`` (mirrors a timeout)."""
    return _timeout_kernel(*args)


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


class TestRealSpiBusTimeoutRecovery:
    """CR-1 Fix: ``xfer2`` hardware reset recovery on ``asyncio.TimeoutError``."""

    @pytest.mark.asyncio
    async def test_spi_bus_timeout_resets_hardware(self) -> None:
        """On timeout, ``xfer2`` closes the bus and raises ``SpiBusError`` with no reopen."""
        bus = RealSpiBus(bus_number=0, device_number=0)
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        with patch.object(bus, "close") as mock_close, patch.object(
            bus, "open"
        ) as mock_open, patch("asyncio.to_thread", _fake_to_thread), pytest.raises(
            SpiBusError
        ):
            await bus.xfer2([1, 2, 3])

        mock_close.assert_called_once()
        mock_open.assert_not_called()

    @pytest.mark.asyncio
    async def test_spi_bus_timeout_recovery_failure(self) -> None:
        """If ``close()`` fails, its ``RuntimeError`` propagates out of ``xfer2`` rather than the timeout."""
        bus = RealSpiBus(bus_number=0, device_number=0)
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        with patch.object(bus, "close") as mock_close, patch.object(
            bus, "open"
        ) as mock_open:
            mock_close.side_effect = RuntimeError("hardware reset failed")

            with patch("asyncio.to_thread", _fake_to_thread), pytest.raises(
                RuntimeError
            ) as exc_info:
                await bus.xfer2([1, 2, 3])

        assert exc_info.value is not None
        mock_close.assert_called_once()
        mock_open.assert_not_called()

    @pytest.mark.asyncio
    async def test_spi_bus_timeout_chains_original_error(self) -> None:
        """On timeout, the raised ``SpiBusError`` chains the original
        ``asyncio.TimeoutError`` via ``from err``.

        Verifies the anti-regression fix (Issue 24.2): the timeout traceback is
        preserved on ``__cause__`` so debuggers see the real hang source instead
        of a bare ``SpiBusError`` raised with ``from None``.
        """
        bus = RealSpiBus(bus_number=0, device_number=0)
        bus._spidev = MagicMock()
        bus._spidev.xfer2 = MagicMock(return_value=[1, 2, 3])

        with patch.object(bus, "close"), patch(
            "asyncio.to_thread", _fake_to_thread
        ), pytest.raises(SpiBusError) as exc_info:
            await bus.xfer2([1, 2, 3])

        assert isinstance(exc_info.value.__cause__, asyncio.TimeoutError)


class TestRealSpiBusSetters:
    """H-2 Fix: setters raise ``RuntimeError`` on an unopened bus."""

    def test_setters_raise_on_unopened_bus(self) -> None:
        """Setting ``max_speed_hz``, ``mode``, ``lsbfirst``, ``no_cs`` raises when closed."""
        bus = RealSpiBus(bus_number=0, device_number=0)
        assert bus._spidev is None
        with pytest.raises(RuntimeError):
            bus.max_speed_hz = 1000
        with pytest.raises(RuntimeError):
            bus.mode = 1
        with pytest.raises(RuntimeError):
            bus.lsbfirst = True
        with pytest.raises(RuntimeError):
            bus.no_cs = True


class TestFactoryOwnedFlag:
    """H-3 Fix: ``_factory_owned`` distinguishes factory buses from production."""

    def test_factory_owned_flag(self) -> None:
        """``factory_owned=True`` sets the flag; the default bus leaves it False."""
        factory_bus = RealSpiBus(
            bus_number=0, device_number=0, factory_owned=True
        )
        assert factory_bus._factory_owned is True
        production_bus = RealSpiBus(bus_number=0, device_number=0)
        assert production_bus._factory_owned is False


class TestConstructorRequirements:
    """H-4 Fix: ``bus_number`` and ``device_number`` are required positional args."""

    def test_constructor_requires_bus_device(self) -> None:
        """``RealSpiBus()`` with no args raises; explicit bus/device constructs."""
        with pytest.raises(TypeError):
            RealSpiBus()
        bus = RealSpiBus(bus_number=1, device_number=2)
        assert bus.bus_number == 1
        assert bus.device_number == 2


class TestVerifyPatchActive:
    """H-8 Fix: ``_verify_patch_active`` keys on resolved bus/device, not defaults."""

    def test_verify_patch_after_bus_device_resolve(self) -> None:
        """A production bus with resolved bus/device passes the guard (no raise)."""
        token: bool | None = _spidev_patch_active.set(False)
        try:
            bus = RealSpiBus(bus_number=5, device_number=3)
            assert bus.bus_number == 5
            assert bus.device_number == 3
            # Production bus (``factory_owned=False``): guard disabled, no raise.
            bus._verify_patch_active()
        finally:
            _spidev_patch_active.reset(token)


class TestRealSpiBusOpenResourceLeak:
    """Issue 24.3 Fix: ``open()`` only assigns ``_spidev`` after a successful open."""

    def test_open_failure_leaves_bus_closed(self) -> None:
        """If ``spidev.SpiDev().open`` raises, ``_spidev`` stays ``None`` after open()."""
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            bus.close()
            with patch("spidev.SpiDev") as mock_spiddev:
                mock_instance = MagicMock()
                mock_instance.open.side_effect = RuntimeError("fake open failed")
                mock_spiddev.return_value = mock_instance
                with pytest.raises(RuntimeError) as exc_info:
                    bus.open()
                # Assignment order: _spidev is only assigned once open() succeeds.
                assert bus._spidev is None
                assert "already open" not in str(exc_info.value)


class TestRealSpiBusCloseResourceLeak:
    """Issue 24.4 Fix + Plan-26 Finding 484: ``close()`` raises and chains on failure
    and ALWAYS nulls ``_spidev`` to allow reopening. The old behavior preserved the
    handle but left the bus unopenable (stuck with "already open" error).
    """

    def test_close_failure_chains_and_clears_handle_for_reopen(self) -> None:
        """If ``spidev.close`` raises, ``SpiBusError`` is chained and ``_spidev`` is
        cleared to allow reopen (Plan-26 Finding 484).
        """
        with FakeSpiBusKernelFactory().create_bus(bus=0, device=0) as bus:
            assert bus._spidev is not None
            failure = RuntimeError("hardware close failed")
            with patch.object(
                bus._spidev, "close", side_effect=failure
            ), pytest.raises(SpiBusError) as exc_info:
                bus.close()
            # PLAN-26 FIX (Finding 484): _spidev IS nulled on failure to allow reopen.
            assert bus._spidev is None
            assert exc_info.value.__cause__ is failure
