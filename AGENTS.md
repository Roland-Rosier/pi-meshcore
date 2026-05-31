# MeshCore Raspberry Pi 4 LoRa Implementation Project

## Section 1. System Profile & Workspace Context
- **Application Goal**: Create a Meshcore Client/Repeater implementation on the Raspberry Pi 4 with LoRa expansion hat
- **Language & Runtime**: Python 3.9+
- **Core Frameworks**:
  - meshcore_py (https://github.com/meshcore-dev/meshcore_py)
  - FastAPI for web interface
  - SPI drivers for LoRa modules
- **Primary Tool-chain**:
  - Python virtual environments
  - Git for version control
  - pytest for unit testing

## Section 2. Structural Mapping & Domain Boundaries
You must use the following folder blueprint when navigating or creating files:
- `src/drivers/` -> LoRa radio drivers (RFM95W/RFM98W)
- `src/meshcore/` -> MeshCore protocol implementation (client/repeater logic)
- `src/cli/` -> Command line interface implementation
- `src/web/` -> FastAPI-based web interface
- `tests/` -> Unit and integration tests
- `docs/` -> Project documentation and setup guides

## Section 3. Execution Constraints & Strict Prohibitions
Because you possess tool-use and system terminal privileges, you must abide by these rules:
- **No Floating Imports**: Always use relative file paths (`../drivers/rfm95w`) or defined alias paths. 
- **Atomic Operations**: Modify one file at a time. Run tests immediately after editing a file to isolate regressions.
- **Explicit Error Envelopes**: All asynchronous services must encapsulate logic inside explicit try/catch blocks. Never bubble up raw system or DB errors to the API route.
- **Never Write Placeholders**: Writing `// TODO: Implement later` or omitting logic using `// ... rest of code` is STRICTLY FORBIDDEN. Write the complete, production-ready syntax.
- **Obey EU LoRa rules**: LoRa defines explicit rules around things such as radio duty cycle. Ensure that all of these rules are met.
- **Strict Verification Mode**: During initial module detection, the system must operate in a 'safe mode' that only performs read operations and never enables transmission, even if modules appear to be functioning.
- **Type Hinting Requirement**: All code must use Python type hinting for function parameters, return types, and variable annotations. This includes:
  - Type annotations for all public functions/methods
  - Type hints for all parameters and return values
  - Proper typing imports (from typing import List, Optional, etc.)

## Section 4. Tool-Calling Workflow Protocol
When tasked with a feature modification, You must execute these steps in strict sequence:
1. **Explore**: Use file-search tools to identify dependencies of the target module.
2. **Draft**: Create or edit the code following the patterns in Section 5.
3. **Validate**: Execute the terminal tool command `npm run lint` and `npm run test` to verify compliance.
4. **Rectify**: If validation fails, read the terminal logs, apply a patch, and re-validate. Do not ask the user for help unless a dependency is missing.

## Section 5. Reference Implementation Patterns
Use this blueprint as your exact functional baseline:
- **Type Hinting Pattern**: All implementation should follow Python type hinting best practices:
  ```python
  from typing import List, Optional, Dict, Tuple, Union
  
  def example_function(param: str) -> List[int]:
      ...
  ```
  This includes:
  - Using `Optional` for values that may be None
  - Using `List`, `Dict`, etc. for collection types
  - Annotating class attributes and methods

### Hardware Driver Implementation
- Implement SPI drivers for:
  - RFM95W (868MHz) on CE0 slot
  - RFM98W (434MHz) on CE1 slot
- Reference existing SX127* drivers in MeshCore: https://github.com/meshcore-dev/MeshCore/tree/main/src/helpers/radiolib
- **Module Detection Protocol**: The initial verification should always follow this sequence:
  1. Initialize SPI for CE0 and CE1
  2. Read device ID register (0x12) for each module
  3. Validate against known device IDs (0x12 for RFM95W, 0x19 for RFM98W)
  4. Return status without enabling any radio functions

### Software Implementation
- Python 3.9+ (Raspberry Pi OS compatible version)
- Required dependencies:
  - meshcore_py (https://github.com/meshcore-dev/meshcore_py)
  - fastapi for web interface
  - uvicorn for ASGI server

### Testing and Validation
- Unit tests for:
  - Radio driver functions
  - MeshCore protocol handlers
  - CLI/web interface interactions
- Field testing with:
  - LoRa network simulations
  - Multi-node communication tests

## Project Overview

This project implements MeshCore (https://meshcore.co.uk/) on a Raspberry Pi 4 with LoRa expansion hat containing:
- RFM95W (SX1276) for 868MHz spectrum
- RFM98W (SX1278) for 434MHz spectrum

## Hardware Requirements

### Raspberry Pi 4
- Minimum 4GB RAM
- GPIO pins for SPI communication

### LoRa Expansion Hat
- Uptronics RFM95W (868MHz) on CE0 slot
- Uptronics RFM98W (434MHz) on CE1 slot

### Pin Mapping

| Module | DIO0 | DIO5 |
|--------|-----|------|
| RFM95W | WPi6 | WPi5 |
| RFM98W | WPi27 | WPi26 |

## Software Architecture

### Core Components
1. **MeshCore Implementation**
   - Client mode
   - Repeater mode
   - Implements MeshCore API (https://github.com/meshcore-dev/meshcore_py)

2. **Command Line Interface (CLI)**
   - Similar to meshtui (https://github.com/ekollof/meshtui)
   - Status monitoring
   - Configuration management

3. **Web Interface**
   - FastAPI-based API endpoint
   - Real-time status dashboard
   - Configuration UI

### Communication Protocols
- Over-The-Air (OTA) protocol: https://github.com/meshcore-dev/MeshCore
- LoRaWAN (Class A) for RFM95W/RFM98W modules
- The transmitted RF *must* meet EU LoRa rules, including explicitly enforcing transmitter duty cycle.

## Development Guidelines

### Hardware Driver Implementation
- Use SX1276/SX1278 datasheet: https://github.com/SeeedDocument/RFM95-98_LoRa_Module/blob/master/RFM95_96_97_98_DataSheet.pdf
- Implement SPI drivers for:
  - RFM95W (868MHz) on CE0 slot
  - RFM98W (434MHz) on CE1 slot
- Reference existing SX127* drivers in MeshCore: https://github.com/meshcore-dev/MeshCore/tree/main/src/helpers/radiolib

### Software Implementation
- Python 3.9+ (Raspberry Pi OS compatible version)
- Required dependencies:
  - meshcore_py (https://github.com/meshcore-dev/meshcore_py)
  - fastapi for web interface
  - uvicorn for ASGI server

## File Operations

Before creating or modifying any file, always verify the current state of the file to ensure:
1. No existing functionality is accidentally overwritten
2. No duplicate functionality is introduced
3. Existing file structure and content is preserved

### File Existence and Content Check Rules
1. **Pre-creation Check** - Always use `file_glob_search` to check if the file already exists
2. **Content Verification** - If the file exists, read its current content to understand its purpose and structure
3. **Safe Modification** - Use `edit_existing_file` instead of `create_new_file` when the file already exists
4. **Idempotency** - Ensure changes are idempotent (can be applied multiple times without causing issues)

### Example Implementation
```python
import os

def safe_file_operation(filepath, new_content):
    # Check if file exists
    if os.path.exists(filepath):
        # Read existing content
        with open(filepath, 'r') as f:
            existing_content = f.read()
        
        # Compare with new content (basic check)
        if existing_content == new_content:
            print(f"File {filepath} already contains the requested content")
            return
    
    # If file doesn't exist or content differs, create it
    with open(filepath, 'w') as f:
        f.write(new_content)
    print(f"File {filepath} created/updated")
```

This ensures we never accidentally overwrite existing files like `src/cli/check_hardware.py` that may contain important content or functionality we're not aware of.

## Documentation Requirements

1. API documentation for:
   - MeshCore API endpoints
   - CLI command reference
   - Web interface operations

2. Hardware setup guide
   - Pin connection diagrams
   - SPI configuration details

3. Development documentation
   - Code structure overview
   - Contribution guidelines
   - Testing procedures

## Project Milestones

1. [ ] Hardware driver implementation
2. [ ] MeshCore protocol implementation
3. [ ] CLI and web interface development
4. [ ] End-to-end testing
5. [ ] Documentation completion

## References

- MeshCore website: https://meshcore.co.uk/
- RFM95W/RFM98W datasheet: https://github.com/SeeedDocument/RFM95-98_LoRa_Module/blob/master/RFM95_96_97_98_DataSheet.pdf
- SX1276/SX1278 datasheet: https://semtech.my.salesforce.com/sfc/p/#E0000000JelG/a/2R0000001Rbr/6EfVZUorrpoKFfvaF_Fkpgp5kzjiNyiAbqcpqh9qSjE
- MeshCore Python library: https://github.com/meshcore-dev/meshcore_py
- Uptronics Datasheet: https://pinout.xyz/pinout/uputronics_lora_expansion_board

## Project Clarification: meshcore (PyPI) vs meshcore_py (GitHub)

The **PyPI package `meshcore`** (https://pypi.org/project/meshcore/) and the **GitHub repository `meshcore_py`** (https://github.com/meshcore-dev/meshcore_py) are **the same project**. The confusion arises from inconsistent naming:

- **`meshcore`** is the **official PyPI package** for the MeshCore protocol (Python implementation).
- **`meshcore_py`** is the **source repository** for the same project.
- Both are maintained by **fdlamotte**.
- The README in the GitHub repo may be outdated (e.g., suggesting `pip install meshcore_py` or GitHub installation), but the **correct installation** is via `pip install meshcore`.

This clarification is critical to avoid future confusion.'