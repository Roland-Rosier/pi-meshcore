# MeshCore Pi4 LoRa Implementation Profile

## 1. Project Context Reference
- **Goal**: Build MeshCore Client/Repeater on RPi 4 with Uputronics LoRa Hat.
- **Stack**: Python 3.9+, FastAPI, SPI Drivers, `pytest`.
- **Install Target**: Official PyPI package is `meshcore` (GitHub: `meshcore_py` by fdlamotte).
- **Directory Layout**:
  - `src/drivers/` (e.g. RFM95W/RFM98W radio drivers, in file lora_module.py)
  - `src/meshcore/` (Protocol client/repeater logic)
  - `src/cli/` (Command Line UI - meshtui style)
  - `src/web/` (FastAPI web backend & dashboard)
  - `tests/` (Unit/integration) | `docs/` (Guides)

## 2. Hardware Specs & Pin Mapping
- **Hardware**: RPi 4 (min 4GB RAM) + Uputronics LoRa Hat.
  - Slot CE0: RFM95W (868MHz, SX1276) -> DIO0: WPi6 | DIO5: WPi5
  - Slot CE1: RFM98W (434MHz, SX1278) -> DIO0: WPi27 | DIO5: WPi26
- **Refs**: Radiolib SX127* drivers, RFM95/98 Datasheets, Semtech SX1276, Uputronics Pinout.

## 3. Passive Operational Constraints
*The constraints below must only bew applied IF the user explicitly requests code modifications in the active chat prompt:*

- **Imports**: All imports must use relative paths (`../drivers/rfm95w`) or explicit aliases. No floating imports allowed.
- **Safety Mode**: Module detection sequence must remain strictly read-only. Sequence validation: 1. Init SPI (CE0/CE1) -> 2. Read device ID register (0x12) -> 3. Validate (0x12=RFM95W, 0x19=RFM98W) -> 4. Return status. Transmission is prohibited during safety mode.
- **Compliance**: Adherence to EU LoRa transmitter duty cycle rules is mandatory.
- **Code Quality**: All code must use complete production syntax. Code placeholders (`// TODO`, `// ...`) are forbidden. Full Python type hinting is required across all functions, parameters, attributes, and returns (`from typing import...`).

## 4. Permitted Tool Behavior Adjustments
*These rules govern tool utilization boundaries when Agent Mode is actively deployed by the user:*

- **File Tool Preference**: The agent is permitted to use `edit_existing_file` rather than `create_new_file` when modifying existing codebases. Code edits should remain idempotent.
- **Modification Limits**: The agent is restricted to modifying a maximum of one file per execution cycle.
- **Testing Framework**: The authorized project verification command is `pytest`