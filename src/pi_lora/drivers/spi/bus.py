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
from typing import Any, Protocol

from .locks import get_bus_lock


class SpiBus(Protocol):
    """Protocol defining the SPI bus interface."""

    def open(self, bus: int | None = None, device: int | None = None) -> None:
        """Open the SPI bus.

        Args:
            bus: The bus identifier. When omitted (``None``), the value stored by
                the factory's ``create()`` is used instead.
            device: The device identifier. When omitted (``None``), the value
                stored by the factory's ``create()`` is used instead.

        The factory-stored bus/device values set by ``create()`` are applied when
        the corresponding argument is not supplied, so ``open()`` may be called
        with no arguments. This matches :meth:`RealSpiBus.open` and upholds the
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


class RealSpiBus:
    """Real implementation of SpiBus wrapping spidev.SpiDev."""

    # CONTEXT-LOCAL FLAG: use contextvars.ContextVar for async-context isolation.
    # Class-level flag shared across all instances causes cross-test interference
    # in parallel test execution (pytest-xdist or concurrent async tasks).
    # contextvars.ContextVar isolates per async context (task); default is False.
    # This replaces the class attribute _spidev_patch_active (CR-8/Plan-11 debt).
    _spidev_patch_active: contextvars.ContextVar[bool] = contextvars.ContextVar(
        "_spidev_patch_active", default=False
    )

    def __init__(self, xfer_timeout: float = 5.0) -> None:
        """Initialize the real SPI bus.

        Bus/device identity is set by ``open()`` — matching the underlying
        ``spidev.SpiDev`` lifecycle (init → open).

        Args:
            xfer_timeout: Upper bound in seconds for a single blocking
                ``spidev.SpiDev.xfer2`` transfer. :func:`asyncio.wait_for`
                raises :class:`asyncio.TimeoutError` if the transfer exceeds
                this budget, preventing an unbounded hang on the event loop.
        """
        self._xfer_timeout: float = xfer_timeout
        # spidev.SpiDev has no stubs; use Any to suppress attr-defined errors.
        self._spidev: Any | None = None
        self.bus_number: int = 0
        self.device_number: int = 0
        self._factory_owned: bool = False  # CR-8 FIX: set True when yielded by create_bus

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
        if self._factory_owned and not self._spidev_patch_active.get():
            raise RuntimeError(
                "RealSpiBus operation failed: the spidev kernel patch is no longer "
                "active. This happens when you retain a bus reference after the "
                "FakeSpiBusKernelFactory.create_bus() context manager exits. "
                "Fix: do not store the bus outside the 'with' block, or restructure "
                "the test to keep the context manager open for the bus's lifetime."
            )

    def open(self, bus: int | None = None, device: int | None = None) -> None:
        """Open the SPI bus. Uses stored bus/device from create() if not provided.

        Args:
            bus: The bus identifier. If None, the value stored by create() is used.
            device: The device identifier. If None, the value stored by create() is used.

        Raises:
            RuntimeError: If the bus is already open. Call close() first.
        """
        # PLAN-19 FIX: Prevent resource leak from multiple open() without close().
        # code_review-18.1.json #6: open() can be called multiple times without close()
        # -> kernel FD leak. Explicit guard forces caller to manage lifecycle correctly.
        if self._spidev is not None:
            raise RuntimeError(
                f"SPI bus {self.bus_number}.{self.device_number} already open. "
                "Call close() before open()."
            )

        # CR-8 FIX: ensure the spidev kernel patch is active before importing it.
        self._verify_patch_active()
        # Note: spidev is a real python library; do not assume otherwise
        import spidev

        # Use stored values if not overridden
        if bus is not None:
            self.bus_number = bus
        if device is not None:
            self.device_number = device

        self._spidev = spidev.SpiDev()
        self._spidev.open(self.bus_number, self.device_number)

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
            return await asyncio.wait_for(
                asyncio.to_thread(self._spidev.xfer2, data),
                timeout=self._xfer_timeout,
            )

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
        """Set maximum speed in Hertz."""
        if self._spidev is not None:
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
        """Set SPI mode setting."""
        if self._spidev is not None:
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
        """Set whether least significant bit comes first."""
        if self._spidev is not None:
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
        """Set whether chip select is disabled."""
        if self._spidev is not None:
            self._spidev.no_cs = value
