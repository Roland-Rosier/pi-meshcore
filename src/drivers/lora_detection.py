# Copyright 2026 Roland Rosier
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "as is" basis,
# without warranties or conditions of any kind, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

from src.drivers.lora_module import LoRaModule


@dataclass
class LoRaModuleConfig:
    """Configuration describing expected LoRa modules on CE lines.

    This class allows a user to describe what they expect to be attached
    to each CE line on the SPI bus. The LoRaModuleDetector can then
    validate this configuration against actual hardware detection results.
    """

    ce0_expected_module_type: Optional[Literal["rfm95w", "rfm98w", "multi_band", "none"]] = None
    ce1_expected_module_type: Optional[Literal["rfm95w", "rfm98w", "multi_band", "none"]] = None

    def __post_init__(self) -> None:
        """Validate that at least one CE line has a non-None expectation."""
        if self.ce0_expected_module_type is None and self.ce1_expected_module_type is None:
            raise ValueError("At least one CE line must have an expected module type specified.")


@dataclass
class ValidationResult:
    """Result of validating a configuration against detected hardware."""

    ce_pin: int
    passed: bool
    message: str
    expected_type: Optional[str]
    detected_type: Optional[str]


class LoRaModuleDetector:
    """Class to detect LoRa modules connected via SPI using LoRaModule class."""
    
    # Mapping from config module type to detected module type strings
    _MODULE_TYPE_MAP: Dict[str, List[str]] = {
        "rfm95w": [
            "RFM95W (High-Band 868MHz / Semtech SX1276)",
            "Multi-band - Likely RFM95W (High-Band 868MHz and/or Low-Band 433Mhz / Semtech SX1276)",
        ],
        "rfm98w": [
            "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            "Multi-band - Likely RFM95W (High-Band 868MHz and/or Low-Band 433Mhz / Semtech SX1276)",
        ],
        "multi_band": [
            "Multi-band - Likely RFM95W (High-Band 868MHz and/or Low-Band 433Mhz / Semtech SX1276)",
        ],
        "none": [
            "Unknown / Communication Error",
        ],
    }

    def __init__(self, ce_pins: List[int] = [0, 1]):
        """
        Initialize LoRaModule instances for CE pins.

        :param ce_pins: List of CE pins (e.g., [0, 1])
        """
        self.modules = [LoRaModule(ce_pin) for ce_pin in ce_pins]
    
    def detect_modules(self) -> List[Dict]:
        """Detect LoRa modules connected to the CE pins using LoRaModule instances."""
        results = []
        
        for module in self.modules:
            result = {
                "ce_pin": module.ce_pin,
                "module_type": module.module_type,
                "Silicon Revision": f"0x{module.silicon_revision:02X}" if module.silicon_revision is not None else "None detected",
                "reg_rxbw_freqifmsb": f"0x{module.read_register(0x12):02X}" if module.read_register(0x12) is not None else "None read"
            }
            results.append(result)
        
        return results