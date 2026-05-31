# src/cli/check_hardware.py
import sys
import os
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
        # Create detector instance
        detector = LoRaModuleDetector(ce_pins=[0, 1])
        
        # Get and display results
        results = detector.detect_modules()

        print("\nHardware Detection Results:")
        for result in results:
            print(f"  ✅ {result}")

        # print("\nStatus: All modules verified (no transmission occurred)")
        # print("Note: This verification only checks for module presence and basic communication")

if __name__ == "__main__":
    main()