# MeshCore Pi4 LoRa Implementation Profile

## 1. Context & Workspace
- **Goal**: Build MeshCore Client/Repeater on RPi 4 with Uputronics LoRa Hat.
- **Stack**: Python 3.9+, FastAPI, SPI Drivers, `pytest`.
- **Install Target**: Official PyPI package is `meshcore` (equivalent to GitHub repository `meshcore_py` by fdlamotte).
- **Directory Boundaries**:
  - `src/drivers/` (RFM95W/RFM98W radio drivers)
  - `src/meshcore/` (Protocol client/repeater logic)
  - `src/cli/` (Command Line UI - meshtui style)
  - `src/web/` (FastAPI web backend & dashboard)
  - `tests/` (Unit/integration) | `docs/` (Guides)

## 2. Hardware Specs & Pin Mapping
- **Hardware**: RPi 4 (min 4GB RAM) + Uputronics LoRa Hat.
  - Slot CE0: RFM95W (868MHz, SX1276) -> DIO0: WPi6 | DIO5: WPi5
  - Slot CE1: RFM98W (434MHz, SX1278) -> DIO0: WPi27 | DIO5: WPi26
- **Refs**: Radiolib SX127* drivers, RFM95/98 Datasheets, Semtech SX1276, Uputronics Pinout.

## 3. Strict Prohibitions & Regulatory Constraints
- **Imports**: No floating imports. Use relative paths (`../drivers/rfm95w`) or explicit aliases.
- **Safety Mode**: Module detection must be strictly read-only. Verification sequence: 1. Init SPI (CE0/CE1) -> 2. Read device ID register (0x12) -> 3. Validate (0x12=RFM95W, 0x19=RFM98W) -> 4. Return status. Never transmit in safety mode.
- **Compliance**: Explicitly enforce transmitter duty cycles adhering to EU LoRa rules.
- **Code Quality**: Complete production syntax only. No placeholders (`// TODO`, `// ...`). Forced Python type hinting across all functions, parameters, attributes, and returns (`from typing import...`).
- **File Safety**: Before operations, call `file_glob_search`. Verify content. Use `edit_existing_file` over `create_new_file` for existing files. Keep edits idempotent.

## 4. Execution Workflow
1. **Explore**: Search files for dependencies.
2. **Draft**: Code matching patterns.
3. **Validate**: Run terminal command `npm run lint && npm run test`.
4. **Rectify**: Fix log issues automatically. Ask user only if dependencies are missing. 
- **Limits**: Modify one file at a time; run tests immediately after.