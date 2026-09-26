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

Provides ``Rfm9xSx127xHandler`` as a pure stateless utility class that performs
frequency calculations, writes, and verifications against SPI driver registers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .rfm9x_sx127x_modes import ModeBits, RegisterLayout

if TYPE_CHECKING:
    from .rfm9x_sx127x_module import Rfm9xSx127xModule


class Rfm9xSx127xHandler:
    """Pure stateless utility for RFM9x/SX127x register operations."""

    @staticmethod
    async def read_reg(module: "Rfm9xSx127xModule", register: int) -> int:  # noqa: UP037
        """Read a single register via module's SPI bus."""
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        response = await spi_bus.xfer2([register & 0x7F, 0x00])  # type: ignore[misc]
        return response[1] if len(response) > 1 else 0

    @staticmethod
    async def write_reg(module: "Rfm9xSx127xModule", register: int, value: int) -> None:  # noqa: UP037
        """Write a single register via module's SPI bus."""
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        await spi_bus.xfer2([register | 0x80, value])  # type: ignore[misc]

    @staticmethod
    async def set_module_mode(module: "Rfm9xSx127xModule", mode: ModeBits) -> bool:  # noqa: UP037
        """Set module operational mode using read-modify-write on RegOpMode."""
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        try:
            current_value: int = await Rfm9xSx127xHandler.read_reg(
                module, RegisterLayout.REG_OP_MODE
            )
            new_value: int = (
                current_value
                & ~RegisterLayout.RegOpMode.MASK_MODE
                & ~RegisterLayout.RegOpMode.BIT_LF
                & ~RegisterLayout.RegOpMode.MASK_LORA
                & ~RegisterLayout.RegOpMode.MASK_META
            )
            new_value |= int(mode.value) & RegisterLayout.RegOpMode.MASK_MODE
            await Rfm9xSx127xHandler.write_reg(
                module, RegisterLayout.REG_OP_MODE, new_value
            )
            return True
        except Exception:
            raise

    @staticmethod
    async def write_and_verify_frequency_for_khz(
        module: "Rfm9xSx127xModule", freq_khz: int  # noqa: UP037
    ) -> tuple[bool, int, int, int, int, int, int]:
        """Write and verify frequency registers (Frf MSB/MID/LSB)."""
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        try:
            freq_registers = Rfm9xSx127xHandler.calc_freq_registers_for_khz(freq_khz)
            req_msb, req_mid, req_lsb = freq_registers

            await Rfm9xSx127xHandler.write_reg(module, RegisterLayout.REG_FRF_MSB, req_msb)
            await Rfm9xSx127xHandler.write_reg(module, RegisterLayout.REG_FRF_MID, req_mid)
            await Rfm9xSx127xHandler.write_reg(module, RegisterLayout.REG_FRF_LSB, req_lsb)

            read_msb: int = await Rfm9xSx127xHandler.read_reg(module, RegisterLayout.REG_FRF_MSB)
            read_mid: int = await Rfm9xSx127xHandler.read_reg(module, RegisterLayout.REG_FRF_MID)
            read_lsb: int = await Rfm9xSx127xHandler.read_reg(module, RegisterLayout.REG_FRF_LSB)

            success: bool = (read_msb == req_msb and read_mid == req_mid and read_lsb == req_lsb)
            return (success, req_msb, req_mid, req_lsb, read_msb, read_mid, read_lsb)
        except Exception:
            raise

    @staticmethod
    def calc_freq_registers_for_khz(freq_khz: int) -> tuple[int, int, int]:
        """Calculate frequency register values (pure calculation, no I/O).

        FSTEP = 61.03515625 Hz. freq_register_value = (freq_khz * 1_000_000) / FSTEP.
        Returns (msb, mid, lsb).
        """
        freq_hz_times_100000000: int = freq_khz * 100000000000
        freq_register_value: int = freq_hz_times_100000000 // 6103515625
        lsb: int = freq_register_value & 0xFF
        mid: int = (freq_register_value & 0xFF00) >> 8
        msb: int = (freq_register_value & 0xFF0000) >> 16
        return (msb, mid, lsb)
