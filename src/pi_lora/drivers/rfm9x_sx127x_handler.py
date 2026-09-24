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

"""Handler layer for RFM9x/SX127x LoRa frequency register operations.

Provides ``Rfm9xSx127xHandler`` as a stateless utility class that performs
frequency calculations, writes, and verifications against SPI driver registers.
"""

from typing import Any

from .rfm9x_sx127x_modes import ModeBits


class Rfm9xSx127xHandler:
    """Stateless handler for RFM9x/SX127x frequency register operations.

    All methods operate purely on their inputs and return calculated results
    without mutating instance state. This class is intended to be instantiated
    once per module context and shared across the driver layer.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.spi_bus: Any | None = None
        self._reg_op_mode: int = 0x01
        self._bit_lf_mode_on: int = 0x08
        self._bit_lora_mode_on: int = 0x80
        self._bit_access_shared_reg: int = 0x40

    def set_module_mode(self, mode: ModeBits) -> bool | None:
        """Set the module operational mode to *mode* via SPI.

        Uses read-modify-write on RegOpMode to preserve LF and LoRa bits.
        Returns ``True`` on success, ``False`` if SPI bus is unavailable or read fails.
        """
        if self.spi_bus is None:
            return False
        try:
            response = self.spi_bus.xfer2([self._reg_op_mode & 0x7F, 0x00])
            current_value: int = response[1] if len(response) > 1 else 0
            new_value: int = (current_value & ~0x07) | (int(mode.value) & 0x07)
            self.spi_bus.xfer2([self._reg_op_mode | 0x80, new_value])
            return True
        except Exception:
            return False

    def write_and_verify_frequency_for_khz(
        self, a_freq_in_khz: int
    ) -> tuple[bool | None, int | None, int | None, int | None, int | None, int | None, int | None]:
        """Write and verify the frequency register for *a_freq_in_khz*.

        Returns a 7-tuple of ``(success, req_msb, req_mid, req_lsb, read_msb, read_mid, read_lsb)``.
        """
        if self.spi_bus is None:
            return (None, None, None, None, None, None, None)

        freq_registers = self.calc_freq_registers_for_khz(a_freq_in_khz)
        req_msb = freq_registers[0]
        req_mid = freq_registers[1]
        req_lsb = freq_registers[2]

        if any(r is None for r in (req_msb, req_mid, req_lsb)):
            return (None, None, None, None, None, None, None)

        try:
            self.spi_bus.xfer2([0x06 | 0x80, req_msb])
            self.spi_bus.xfer2([0x07 | 0x80, req_mid])
            self.spi_bus.xfer2([0x08 | 0x80, req_lsb])

            read_msb = None
            read_mid = None
            read_lsb = None

            resp_msb = self.spi_bus.xfer2([0x06 & 0x7F, 0x00])
            read_msb = resp_msb[1] if len(resp_msb) > 1 else None

            resp_mid = self.spi_bus.xfer2([0x07 & 0x7F, 0x00])
            read_mid = resp_mid[1] if len(resp_mid) > 1 else None

            resp_lsb = self.spi_bus.xfer2([0x08 & 0x7F, 0x00])
            read_lsb = resp_lsb[1] if len(resp_lsb) > 1 else None

            if all(r is not None for r in (read_msb, read_mid, read_lsb)):
                success: bool = (read_msb == req_msb and read_mid == req_mid and read_lsb == req_lsb)
            else:
                success = False

            return (success, req_msb, req_mid, req_lsb, read_msb, read_mid, read_lsb)
        except Exception:
            return (None, None, None, None, None, None, None)

    def calc_freq_registers_for_khz(
        self, a_freq_in_khz: int
    ) -> tuple[int | None, int | None, int | None]:
        """Calculate frequency register values for *a_freq_in_khz*.

        FSTEP = 61.03515625 Hz. freq_register_value = (freq_khz * 1_000_000) / FSTEP.
        Returns (msb, mid, lsb).
        """
        try:
            freq_hz_times_100000000: int = a_freq_in_khz * 100000000000
            freq_register_value: int = freq_hz_times_100000000 // 6103515625
            lsb: int = freq_register_value & 0xFF
            mid: int = (freq_register_value & 0xFF00) >> 8
            msb: int = (freq_register_value & 0xFF0000) >> 16
            return (msb, mid, lsb)
        except Exception:
            return (None, None, None)
