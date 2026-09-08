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
All methods are stubs pending implementation of the actual SPI write logic.
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
        pass  # stub: no state yet

    def set_module_mode(self, mode: ModeBits) -> bool | None:
        """Set the module operational mode to *mode*.

        Returns ``bool | None`` indicating success/failure of the mode transition.
        Currently returns ``None`` as a stub.
        """
        return None

    def write_and_verify_frequency_for_khz(
        self, a_freq_in_khz: int
    ) -> tuple[bool | None, int | None, int | None, int | None, int | None, int | None, int | None]:
        """Write and verify the frequency register for *a_freq_in_khz*.

        Returns a 7-tuple of ``(success, reg1, reg2, reg3, reg4, reg5, reg6)``
        where each ``regN`` is an integer register value or ``None``.
        Currently returns all ``None`` as a stub.
        """
        return (None, None, None, None, None, None, None)

    def calc_freq_registers_for_khz(
        self, a_freq_in_khz: int
    ) -> tuple[int | None, int | None, int | None]:
        """Calculate frequency register values for *a_freq_in_khz*.

        Returns a 3-tuple of ``(reg1, reg2, reg3)`` where each value is an
        integer register or ``None``. Currently returns all ``None`` as a stub.
        """
        return (None, None, None)
