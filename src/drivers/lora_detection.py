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

from typing import List, Dict
from src.drivers.lora_module import LoRaModule

class LoRaModuleDetector:
    """Class to detect LoRa modules connected via SPI using LoRaModule class."""
    
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