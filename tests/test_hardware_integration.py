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

"""Hardware integration tests gated on the ``PI_LORA_HARDWARE`` runtime flag.

All tests are decorated with ``@pytest.mark.hardware`` and gated on
:func:`hardware_enabled` (``os.environ["PI_LORA_HARDWARE"] == "1"``). When the
flag is unset the tests are valid no-ops. The real SPI path test additionally
requires :func:`spidev_available` and only runs on actual RPi hardware.

CLI integration tests invoke ``test_hardware_impl`` directly with ``asyncio``
semantics (never ``typer.testing.CliRunner.invoke()``), patching ``Application``
and ``rich.console`` so rich output is captured for assertions.
"""

from __future__ import annotations

from io import StringIO

import pytest

from pi_lora.drivers.spi.bus import RealSpiBus
from pi_lora.drivers.spi.locks import get_bus_lock
from tests.spi.mock import hardware_enabled, spidev_available
from tests.test_hardware_cli import (
    _SUCCESSFUL_EVENT,
    _build_mock_application,
    _build_module,
    _build_radio_config,
    _run_hardware,
)


class TestHardwareRealPath:
    """Real ``RealSpiBus -> spidev -> kernel SPI`` path, gated on hardware."""

    @pytest.mark.hardware
    @pytest.mark.asyncio
    async def test_real_hardware_xfer2(self) -> None:
        """Run ``xfer2`` on a real spidev kernel when hardware is enabled.

        No-op when ``PI_LORA_HARDWARE`` is unset or the ``spidev`` extension is
        unavailable. When active, opens a real bus, acquires the per-bus lock via
        ``await get_bus_lock`` and runs the transfer.
        """
        if not hardware_enabled() or not spidev_available():
            return

        bus = RealSpiBus()
        bus.open(bus=0, device=0)

        lock = await get_bus_lock(0)
        await lock.acquire()
        try:
            result = await bus.xfer2(bytearray([0x01 | 0x80, 0x42]))
        finally:
            lock.release()

        assert isinstance(result, list)
        assert len(result) == 2


class TestHardwareCliIntegration:
    """CLI ``hardware`` command integration, gated on hardware (direct async call)."""

    @pytest.mark.hardware
    @pytest.mark.asyncio
    async def test_hardware_cli_async_direct_call(self) -> None:
        """Exercise ``test_hardware_impl`` directly with a mocked Application.

        No-op when ``PI_LORA_HARDWARE`` is unset. When active, verifies the async
        direct-call path (not ``CliRunner.invoke()``) transitions modules to
        ``RESET_STATE`` and awaits ``start`` / ``stop``.
        """
        if not hardware_enabled():
            return

        capture = StringIO()
        mock_application = _build_mock_application()
        mock_application.get_assembly_config.return_value = [_build_radio_config(0, 0)]
        module = _build_module(_SUCCESSFUL_EVENT)
        module.get_spi_device_id.return_value = 0
        module.get_ce_number.return_value = 0
        mock_application.module_manager.get_all_modules.return_value = [module]

        exit_code = await _run_hardware(capture, mock_application, assembly_name="default")

        assert exit_code == 0, f"Expected exit 0, got {exit_code}: {capture.getvalue()}"
        assert "All modules transitioned to RESET_STATE successfully" in capture.getvalue()
        mock_application.start.assert_awaited_once_with(assembly_name="default")
        mock_application.stop.assert_awaited_once()
