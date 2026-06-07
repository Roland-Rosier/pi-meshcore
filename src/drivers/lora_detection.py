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

    ce0_expected_module_type: Optional[Literal["rfm95w", "rfm98w", "none"]] = None
    ce1_expected_module_type: Optional[Literal["rfm95w", "rfm98w", "none"]] = None

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

    def calculate_unique_frequency(self, ce_pin: int, detected_type: str, config: Optional[LoRaModuleConfig] = None) -> int:
        """
        Calculate the unique frequency to use for a module based on detection and configuration.
        
        :param ce_pin: The CE pin number (0 or 1)
        :param detected_type: The detected module type string
        :param config: Optional user configuration
        :return: Frequency in kHz
        """
        # Determine if this module is assumed to be RFM95W or RFM98W
        
        is_rfm95w = False
        is_rfm98w = False
        
        if detected_type == "RFM95W (High-Band 868MHz / Semtech SX1276)":
            is_rfm95w = True
        elif detected_type == "RFM98W (Low-Band 433Mhz / Semtech SX1278)":
            is_rfm98w = True
        elif "Multi-band" in detected_type:
            # Multi-band logic
            if config is not None:
                if ce_pin == 0:
                    expected = config.ce0_expected_module_type
                else:
                    expected = config.ce1_expected_module_type
                
                if expected == "rfm95w":
                    is_rfm95w = True
                elif expected == "rfm98w":
                    is_rfm98w = True
                else:
                    # No specific config for this pin, default based on CE pin
                    if ce_pin == 0:
                        is_rfm95w = True
                    else:
                        is_rfm98w = True
            else:
                # No user configuration, default based on CE pin
                if ce_pin == 0:
                    is_rfm95w = True
                else:
                    is_rfm98w = True
        
        if is_rfm95w:
            if ce_pin == 0:
                return 960000
            else:
                return 862000
        elif is_rfm98w:
            if ce_pin == 0:
                return 480000
            else:
                return 410000
        else:
            # Default to a safe frequency if detection is ambiguous
            # This should not happen if detection is working, but just in case
            return 433000

    def extended_detect_modules(self, config: Optional[LoRaModuleConfig] = None) -> List[Dict]:
        """
        Extended detection that verifies if CE0 and CE1 are the same physical module.
        
        :param config: Optional user configuration
        :return: List of detection results with additional verification status
        """
        # First, run standard detection
        results = self.detect_modules()
        
        # Check if both CE0 and CE1 have modules attached
        ce0_result = None
        ce1_result = None
        
        for result in results:
            if result["ce_pin"] == 0:
                ce0_result = result
            elif result["ce_pin"] == 1:
                ce1_result = result
        
        # If either is missing, no need for dual verification
        if ce0_result is None or ce1_result is None:
            # Add a flag indicating no dual verification was needed
            for result in results:
                result["is_single_module_dual_spi"] = False
            return results
        
        # Both modules are detected. Perform unique value retention test.
        ce0_module = None
        ce1_module = None
        
        for module in self.modules:
            if module.ce_pin == 0:
                ce0_module = module
            elif module.ce_pin == 1:
                ce1_module = module
        
        if ce0_module is None or ce1_module is None:
            for result in results:
                result["is_single_module_dual_spi"] = False
            return results
        
        # Step 1: Write unique value to CE0
        freq_ce0 = self.calculate_unique_frequency(0, ce0_result["module_type"], config)
        ce0_written = ce0_module.test_unique_value_retention(freq_ce0)
        
        # Step 2: Write unique value to CE1
        freq_ce1 = self.calculate_unique_frequency(1, ce1_result["module_type"], config)
        ce1_written = ce1_module.test_unique_value_retention(freq_ce1)
        
        # Step 3: Verify CE0
        ce0_verified = ce0_module.verify_unique_value_retention()
        
        # Step 4: Verify CE1
        ce1_verified = ce1_module.verify_unique_value_retention()
        
        # Determine if they are the same module
        is_single_module = not (ce0_verified and ce1_verified)
        
        # Update results
        for result in results:
            if result["ce_pin"] == 0:
                result["is_single_module_dual_spi"] = is_single_module
                result["unique_value_written"] = ce0_written
                result["unique_value_verified"] = ce0_verified
            elif result["ce_pin"] == 1:
                result["is_single_module_dual_spi"] = is_single_module
                result["unique_value_written"] = ce1_written
                result["unique_value_verified"] = ce1_verified
        
        return results

    def validate_config(self, config: LoRaModuleConfig) -> List[ValidationResult]:
        """Validate the given configuration against the currently detected hardware.

        :param config: The user-spected configuration.
        :return: A list of ValidationResult objects for each CE pin.
        """
        results = []

        # Map CE pin index to config field
        ce_pin_to_config = {
            0: config.ce0_expected_module_type,
            1: config.ce1_expected_module_type,
        }

        for i, module in enumerate(self.modules):
            ce_pin = module.ce_pin
            expected_type = ce_pin_to_config.get(ce_pin)

            # If no expectation for this CE pin, skip validation
            if expected_type is None:
                continue

            detected_type = module.module_type

            # Check if the detected type is in the list of valid types for the expected type
            valid_detected_types = self._MODULE_TYPE_MAP.get(expected_type, [])

            # Special case for 'none': also accept if communication failed entirely
            # The module might still report 'Unknown' but communication_success is False
            passed = False
            if expected_type == "none":
                # If we expect 'none', we want to ensure no valid module is detected
                # 'Unknown / Communication Error' is the expected detected type for 'none'
                passed = detected_type in valid_detected_types
            else:
                passed = detected_type in valid_detected_types

            message = f"Expected: {expected_type}, Detected: {detected_type}"
            if passed:
                message += " (Match)"
            else:
                message += " (Mismatch)"

            results.append(ValidationResult(
                ce_pin=ce_pin,
                passed=passed,
                message=message,
                expected_type=expected_type,
                detected_type=detected_type
            ))

        return results
