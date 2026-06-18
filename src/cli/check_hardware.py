# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import os
import argparse
from typing import List

# Add project root to Python path if not already present
current_dir = os.path.abspath(os.path.dirname(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))

if project_root not in sys.path:
    sys.path.append(project_root)
    print(f"✅ Added project root to sys.path: {project_root}")

from src.drivers.lora_detection import LoRaModuleDetector

def main() -> None:
    """Main function to check hardware modules."""
    if len(sys.argv) < 2:
        print("Usage: check-hardware [command]")
        print("Available commands:")
        print("  detect-modules - Check for LoRa modules")
        return

    if sys.argv[1] == "detect-modules":
        # Parse only the optional arguments, excluding the command itself
        parser = argparse.ArgumentParser(description="Check LoRa hardware")
        parser.add_argument("--ce0", choices=["rfm95w", "rfm98w", "none"], default=None, help="Expected module type on CE0")
        parser.add_argument("--ce1", choices=["rfm95w", "rfm98w", "none"], default=None, help="Expected module type on CE1")
        args = parser.parse_args(sys.argv[2:])

        # Create detector instance
        detector = LoRaModuleDetector(ce_pins=[0, 1])
        
        # Get and display results
        results = detector.detect_modules()

        print("\nHardware Detection Results:")
        for result in results:
            print(f"  ✅ {result}")

        # Validate configuration if provided
        if args.ce0 is not None or args.ce1 is not None:
            from src.drivers.lora_detection import LoRaModuleConfig
            config = LoRaModuleConfig(
                ce0_expected_module_type=args.ce0,
                ce1_expected_module_type=args.ce1
            )
            validation_results = detector.validate_config(config)

            print("\nConfiguration Validation Results:")
            all_passed = True
            for vr in validation_results:
                status = "✅ PASS" if vr.passed else "❌ FAIL"
                print(f"  {status} CE{vr.ce_pin}: {vr.message}")
                if not vr.passed:
                    all_passed = False

            if all_passed:
                print("\n✅ Configuration is valid.")
            else:
                print("\n❌ Configuration is invalid.")
                sys.exit(1)
if __name__ == "__main__":
    main()