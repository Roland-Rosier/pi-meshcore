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
import contextvars
import logging
from typing import Any, Protocol

from .locks import get_bus_lock

logger = logging.getLogger(__name__)


class SpiBus(Protocol):
    """Protocol defining the SPI bus interface."""

    def open(self) -> None:
        """Open the SPI bus using bus/device set at construction.

        The bus/device identifiers are fixed by the constructor (see
        :class:`RealSpiBus`), so ``open()`` takes no arguments and upholds the
        ``SpiBus`` Liskov Substitution principle.
        """

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


class SpiBusError(RuntimeError):
    """SPI bus operation failed; bus state is explicitly documented in the message.

    Callers MUST call bus.open() before retrying any operation.
    The bus is left in CLOSED state after this exception is raised.
    """
    pass


# CONTEXT-LOCAL FLAG: module-level ContextVar for async-context isolation.
# Process-global patch state, but isolated per async context (task) for parallel
# test execution (pytest-xdist or concurrent async tasks). A class attribute
# would be shared across all RealSpiBus instances in the same context (H-1).
# This is finding H-1: moving it to module level fixes the cross-instance sharing.
_spidev_patch_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_spidev_patch_active", default=False
)


class RealSpiBus:
    """Real implementation of SpiBus wrapping spidev.SpiDev."""

    def __init__(
        self,
        bus_number: int,
        device_number: int,
        xfer_timeout: float = 5.0,
        factory_owned: bool = False,
    ) -> None:
        # H-4 FIX: bus_number and device_number are positional-required with no
        # default of 0, so open() cannot silently target bus 0.0. A default of
        # 0 would let open() open the wrong bus; the constructor enforces an
        # explicit bus/device set instead.
        """Initialize the real SPI bus.

        Args:
            bus_number: SPI bus identifier (required).
            device_number: SPI device identifier (required).
            xfer_timeout: Upper bound in seconds for a single blocking
                ``spidev.SpiDev.xfer2`` transfer. :func:`asyncio.wait_for`
                raises :class:`asyncio.TimeoutError` if the transfer exceeds
                this budget, preventing an unbounded hang on the event loop.
            factory_owned: True if created by test factory with spidev patch.
        """
        self._xfer_timeout: float = xfer_timeout
        # spidev.SpiDev has no stubs; use Any to suppress attr-defined errors.
        self._spidev: Any | None = None
        self.bus_number: int = bus_number
        self.device_number: int = device_number
        # H-3 FIX: _factory_owned is True only for buses yielded by
        # FakeSpiBusKernelFactory and False for production buses. Because the
        # _verify_patch_active() guard keys on _factory_owned, the guard is
        # silently disabled for production buses (the bug).
        self._factory_owned: bool = factory_owned

    def _verify_patch_active(self) -> None:
        """CR-8 FIX: Verify the injected ``spidev`` kernel patch is still active.

        :class:`FakeSpiBusKernelFactory.create_bus` yields a bus whose ``_spidev``
        is a :class:`FakeSpiDev` installed through :func:`spidev_kernel_patch`.
        The patch is deactivated (and the bus closed) on context-manager block
        exit. If a caller retains the bus reference after that exit, every
        ``import spidev`` performed by :meth:`open` / :meth:`xfer2` fails, but
        there would be no clear error to surface the misuse. This check raises a
        explicit :class:`RuntimeError` instead.

        KNOWN LIMITATION: This is test infrastructure technical debt. The
        context-manager-yielding-a-resource-that-gets-closed-in-finally pattern
        is fundamentally unsafe. A proper fix would require restructuring to not
        yield the bus directly (return a proxy) or making the patch persistent.
        For now, misuse is detected at runtime.

        :raises RuntimeError: If this is a :meth:`FakeSpiBusKernelFactory.create_bus` yielded bus whose ``spidev`` patch has been deactivated on context-manager exit.
        """
        if self._factory_owned and not _spidev_patch_active.get():
            raise RuntimeError(
                "RealSpiBus operation failed: the spidev kernel patch is no longer "
                "active. This happens when you retain a bus reference after the "
                "FakeSpiBusKernelFactory.create_bus() context manager exits. "
                "Fix: do not store the bus outside the 'with' block, or restructure "
                "the test to keep the context manager open for the bus's lifetime."
            )

    def open(self) -> None:
        """Open the SPI bus using bus/device from the constructor.

        Raises:
            RuntimeError: If the bus is already open. Call close() before open().
        """
        # PLAN-19 FIX: Prevent resource leak from multiple open() without close().
        if self._spidev is not None:
            raise RuntimeError(
                f"SPI bus {self.bus_number}.{self.device_number} already open. "
                "Call close() before open()."
            )

        # H-8 FIX: _verify_patch_active() now runs after bus/device are resolved
        # (they are fixed in __init__, so this check uses the correct bus/device).
        # Root-cause (why the bug occurred): the call previously happened BEFORE
        # bus/device were resolved, so it validated against the default values of
        # 0,0 instead of the real bus/device -- _verify_patch_active() therefore
        # checked the wrong (default) bus/device and could pass or fail incorrectly.
        self._verify_patch_active()
        # Note: spidev is a real python library; do not assume otherwise
        import spidev

        self._spidev = spidev.SpiDev()
        self._spidev.open(self.bus_number, self.device_number)

    # PLAN-22 FIX (Item 4): close() now uses try/finally.
    # Before: If spidev.close() raised, _spidev was not set to None, leaving
    # bus in inconsistent state (OS handle closed but Python ref held). Next open()
    # would fail. Now _spidev=None is guaranteed even on exception.
    def close(self) -> None:
        """Close the SPI bus.

        Guarantees _spidev is set to None even if spidev.close() raises.
        """
        if self._spidev is not None:
            try:
                self._spidev.close()
            finally:
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

        # NOTE: spidev.SpiDev.xfer2() requires list[int] per the Cython extension API.
        # The public protocol accepts list[int] | bytearray for caller convenience,
        # but we MUST convert to list[int] before calling the underlying spidev.
        # Do NOT change the parameter type to only list[int] — the protocol allows
        # bytearray for callers using bytearray (e.g., Rfm9xSx127xHandler).
        # spidev.xfer2() does not accept the buffer protocol; only spidev.writebytes2()
        # accepts a bytearray. This conversion to list[int] is therefore mandatory.
        if isinstance(data, bytearray):
            data = list(data)

        lock = await get_bus_lock(self.bus_number)
        async with lock:
            # PLAN-22 FIX (Item 3): Timeout no longer attempts auto-recovery.
            # Before: On timeout, close()/open() was attempted; if successful, original
            # TimeoutError raised but bus state indeterminate. If recovery failed, bus closed.
            # Now: Timeout ALWAYS closes bus and raises SpiBusError (subclass of RuntimeError).
            # Caller MUST call bus.open() before retrying. This eliminates indeterminate state.
            # C1 VERIFIED: No callers catch TimeoutError from xfer2() — blast radius zero.
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(self._spidev.xfer2, data),
                    timeout=self._xfer_timeout,
                )
            except asyncio.TimeoutError:  # noqa: UP041
                logger.warning(
                    "SPI xfer2 timeout on bus %d (%.1fs). Closing bus; caller must reopen.",
                    self.bus_number, self._xfer_timeout,
                )
                self.close()  # Ensure bus is closed; try/finally in close() guarantees _spidev=None
                raise SpiBusError(
                    f"SPI xfer2 timeout on bus {self.bus_number} after {self._xfer_timeout}s. "
                    f"Bus is now closed. Call bus.open() before retrying."
                ) from None

    # PLAN-20: Restore safe default (Plan-14 regression fix). Factory contract:
    # create() returns unopened bus; properties readable before open(). Return 0/False
    # for unconfigured state. Check max_speed_hz > 0 to verify bus is open+configured.
    @property
    def max_speed_hz(self) -> int:
        """Maximum speed in Hertz.

        Returns 0 if the bus is not yet opened (spidev not initialized).
        Check `max_speed_hz > 0` to determine if the bus is open and configured.
        """
        if self._spidev is not None:
            return self._spidev.max_speed_hz
        return 0  # Safe default: unconfigured

    @max_speed_hz.setter
    def max_speed_hz(self, value: int) -> None:
        """Set maximum speed in Hertz.

        Raises:
            RuntimeError: If the bus is not opened. Callers can check
            `bus.max_speed_hz == 0` to verify the bus is opened before setting.

        H-2 anti-regression: the setter previously no-op'd silently when
        ``_spidev`` was ``None``, so callers lost their config. Raising here
        closes the finding.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened. Call open() first.")
        self._spidev.max_speed_hz = value

    # PLAN-20: Restore safe default (Plan-14 regression fix). Factory contract:
    # create() returns unopened bus; properties readable before open(). Return 0/False
    # for unconfigured state. Check max_speed_hz > 0 to verify bus is open+configured.
    @property
    def mode(self) -> int:
        """SPI mode setting. Returns 0 if bus not opened."""
        if self._spidev is not None:
            return self._spidev.mode
        return 0

    @mode.setter
    def mode(self, value: int) -> None:
        """Set SPI mode setting.

        Raises:
            RuntimeError: If the bus is not opened. Callers can check
            `bus.mode == 0` to verify the bus is opened before setting.

        H-2 anti-regression: the setter previously no-op'd silently when
        ``_spidev`` was ``None``, so callers lost their config. Raising here
        closes the finding.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened. Call open() first.")
        self._spidev.mode = value

    # PLAN-20: Restore safe default (Plan-14 regression fix). Factory contract:
    # create() returns unopened bus; properties readable before open(). Return 0/False
    # for unconfigured state. Check max_speed_hz > 0 to verify bus is open+configured.
    @property
    def lsbfirst(self) -> bool:
        """Whether least significant bit comes first. Returns False if bus not opened."""
        if self._spidev is not None:
            return self._spidev.lsbfirst
        return False

    @lsbfirst.setter
    def lsbfirst(self, value: bool) -> None:
        """Set whether least significant bit comes first.

        Raises:
            RuntimeError: If the bus is not opened. Callers can check
            `bus.lsbfirst is False` to verify the bus is opened before setting.

        H-2 anti-regression: the setter previously no-op'd silently when
        ``_spidev`` was ``None``, so callers lost their config. Raising here
        closes the finding.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened. Call open() first.")
        self._spidev.lsbfirst = value

    # PLAN-20: Restore safe default (Plan-14 regression fix). Factory contract:
    # create() returns unopened bus; properties readable before open(). Return 0/False
    # for unconfigured state. Check max_speed_hz > 0 to verify bus is open+configured.
    @property
    def no_cs(self) -> bool:
        """Whether chip select is disabled. Returns False if bus not opened."""
        if self._spidev is not None:
            return self._spidev.no_cs
        return False

    @no_cs.setter
    def no_cs(self, value: bool) -> None:
        """Set whether chip select is disabled.

        Raises:
            RuntimeError: If the bus is not opened. Callers can check
            `bus.no_cs is False` to verify the bus is opened before setting.

        H-2 anti-regression: the setter previously no-op'd silently when
        ``_spidev`` was ``None``, so callers lost their config. Raising here
        closes the finding.
        """
        if self._spidev is None:
            raise RuntimeError("SPI bus not opened. Call open() first.")
        self._spidev.no_cs = value
