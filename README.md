# MeshCore Raspberry Pi 4 LoRa Implementation

This project implements [MeshCore](https://meshcore.co.uk/) on a Raspberry Pi 4 with LoRa expansion hat containing:
- RFM95W (SX1276) for 868MHz spectrum
- RFM98W (SX1278) for 434MHz spectrum

---

## Project Overview

This implementation includes:
- **MeshCore Protocol**: Client/Repeater implementation using [meshcore_py](https://github.com/meshcore-dev/meshcore_py)
- **LoRa Drivers**: SPI drivers for RFM95W (868MHz) and RFM98W (434MHz)
- **Web Interface**: FastAPI-based dashboard for status monitoring and configuration
- **CLI Tools**: Command-line interface for hardware checks and configuration

---

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

---

## Getting Started

### Prerequisites

- Python 3.9+ installed on your system
- [uv](https://github.com/astral-sh/uv) package manager (install via `curl -LsSf https://astral.sh/uv/install.sh | sh`) or `sudo pipx install uv --global`
- Raspberry Pi OS with SPI and GPIO enabled (`raspi-config` → Interface Options)

### Installation

```bash
# Clone the repository
git clone <repository-url> && cd pi-lora

# Create virtual environment and install all dependencies
uv sync
```

This installs both runtime (spidev, gpiod, typer) and development (pytest, mypy, coverage) dependencies.

### Running Tests

```bash
# Run all tests with coverage reporting
uv run pytest

# Run all tests with coverage report to terminal + HTML
# Configuration is defined in `pyproject.toml` under `[tool.coverage.*]`.
uv run pytest --cov=src --cov=tests --cov-report=term-missing --cov-report=html

# View the interactive HTML report in your browser at `htmlcov/index.html` after running:
open htmlcov/index.html   # macOS
xdg-open htmlcov/index.html  # Linux

```

### Type Checking

```bash
# Run mypy static analysis on source code
uv run mypy src/
```

### Linting

This project uses [`ruff`](https://docs.astral.sh/ruff/) for fast Python linting, covering style rules (pycodestyle), import sorting (isort), common bug patterns (flake8-bugbear), and more. Configuration lives in `[tool.ruff]` inside `pyproject.toml`.

```bash
# Quick lint check (CI-compatible)
uv run ruff check src/ tests/

# Auto-fix safe violations
uv run ruff check src/ tests/ --fix
```

### Security Scanning

This project uses [`semgrep`](https://semgrep.dev/) for SAST-based security and supply-chain scanning. Configuration lives in `[tool.semgrep]` inside `pyproject.toml`.

```bash
# Run semgrep security scan on source code
uv run semgrep --config semgrep-rules/ src/ tests/
```

### Adding Dependencies

```bash
# Add a runtime dependency
uv add <package-name>

# Add a development dependency
uv add --group dev <package-name>

# Remove a dependency
uv remove <package-name>
```

---

## Software Architecture

### Core Components
1. **MeshCore Implementation**
   - Client mode
   - Repeater mode
   - Implements MeshCore API ([meshcore_py](https://github.com/meshcore-dev/meshcore_py))

2. **Command Line Interface (CLI)**
   - Hardware checks
   - Configuration management
   - Status monitoring

3. **Web Interface**
   - FastAPI-based API endpoint
   - Real-time status dashboard
   - Configuration UI

4. **Communication Protocols**
   - Over-The-Air (OTA) protocol ([MeshCore spec](https://github.com/meshcore-dev/MeshCore))
   - LoRaWAN (Class A) for RFM95W/RFM98W modules
   - EU LoRa duty cycle compliance enforced

---

## Development Guidelines

### Hardware Driver Implementation
- Use SX1276/SX1278 datasheet: [RFM95-98 DataSheet](https://github.com/SeeedDocument/RFM95-98_LoRa_Module/blob/master/RFM95_96_97_98_DataSheet.pdf)
- SPI drivers for:
  - RFM95W (868MHz) on CE0 slot
  - RFM98W (434MHz) on CE1 slot
- Reference existing SX127* drivers in MeshCore: [MeshCore Radiolib](https://github.com/meshcore-dev/MeshCore/tree/main/src/helpers/radiolib)

### Software Implementation
- Python 3.9+ (Raspberry Pi OS compatible)
- Required dependencies:
  - `meshcore` (PyPI package)
  - `fastapi` for web interface
  - `uvicorn` for ASGI server
  - `pytest` for unit testing

---

## Project Structure

```
├── .continue/                        # Continue.dev agent configuration
│   ├── get_tree.py                   # Tree structure retrieval script for agent workflows
│   ├── mcpServers/
│   │   └── desktop-commander-mcp.yaml  # MCP server config for Desktop Commander integration
│   └── rules/
│       ├── 01-system-constraints.md    # Global system constraints and safety modes
│       ├── 02-execution-protocol.md    # Phase-based execution protocol guidelines
│       ├── 03-use-desktop-commander-mcp.md  # Desktop Commander MCP tool usage rules
│       └── 04-use-native-edit-tools.md    # Native file editing tool (single_find_and_replace) rules
├── .kilo/                            # Kilo agent configuration directory
│   ├── agents/
│   │   └── repo_analyst.md           # Repository analysis agent configuration
│   ├── kilo.jsonc                    # Kilo main configuration file
│   └── rules/
│       ├── 01-strict-tool-calls.md     # Strict tool call enforcement rules
│       ├── 02-system-constraints.md    # Global system constraints and safety modes
│       ├── 03-act--execution-protocol.md  # Act phase execution protocol guidelines
│       ├── 03-plan-execution-protocol.md  # Plan phase execution protocol guidelines
│       ├── 04-use-desktop-commander-mcp.md  # Desktop Commander MCP tool usage rules
│       └── 05-use-native-edit-tools.md    # Native file editing tool (single_find_and_replace) rules
├── .gitattributes                    # Git attribute definitions for line endings, filters
├── .gitignore                        # Files and directories excluded from version control
├── .pre-commit-config.yaml           # Pre-commit hook configuration for automated linting/formatting checks
├── .prompts/                         # Reusable agent prompt templates
│   └── repo_analyst.prompt           # Repository analysis task prompt template
├── .vscode/
│   └── settings.json                 # VS Code workspace settings and configurations
├── AGENTS.md                         # AI agent configuration and behavior definitions
├── LICENSE                           # Open-source license terms for the project
├── NOTICE                            # Attribution and third-party notice file
├── Prompts.txt                       # General prompt reference documentation
├── README.md                         # Project overview, architecture, and setup guide
├── SECURITY.md                       # Security policy and vulnerability reporting guidelines
├── configs/                          # Configuration files directory
│   ├── continue/
│   │   └── config_lmstudio.yaml      # LM Studio configuration for Continue.dev agent workflows
│   └── ruff-lint-workflow.yml.disabled  # Disabled ruff lint workflow configuration file
├── pyproject.toml                    # Python project metadata, pytest & coverage configuration
├── requirements.txt                  # Python dependency list (FastAPI, meshcore, pytest, etc.)
├── uv.lock                           # Lock file pinning exact dependency versions for reproducible builds
├── src/pi_lora/                      # Main source code package
│   ├── __init__.py                   # Package initialization for pi_lora top-level module
│   ├── cli/
│   │   ├── __init__.py               # CLI sub-package initialization
│   │   └── check_hardware.py         # CLI tool for LoRa hardware detection and status checks
│   └── drivers/
│       ├── __init__.py               # Drivers sub-package initialization
│       ├── lora_detection.py          # LoRa module auto-detection logic (RFM95W/RFM98W)
│       └── lora_module.py             # RFM95W/RFM98W radio driver implementation (SX1276/SX1278)
└── tests/                            # Test suite
    ├── __init__.py                   # Tests package initialization
    ├── conftest.py                   # pytest fixtures and shared test configuration
    ├── fakes.py                      # Fake/mock implementations for driver testing
    ├── test_check_hardware_cli.py    # Unit tests for CLI hardware check tool
    ├── test_fakes.py                 # Unit tests for fake/mock objects
    ├── test_lora_module.py           # Unit tests for LoRa radio module operations
    ├── test_lora_module_detection.py # Tests for hardware detection logic
    └── test_lora_module_detector.py  # Tests for the detector subsystem component
```

---

## Documentation

- **API Documentation**: MeshCore API endpoints, CLI commands, and web interface operations
- **Hardware Setup Guide**: Pin diagrams, SPI configuration, and module detection
- **Development Guide**: Code structure, contribution guidelines, and testing procedures

---

## Testing & Validation

- **Unit Tests**:
  - Radio driver functions
  - MeshCore protocol handlers
  - CLI/web interface interactions

- **Field Tests**:
  - LoRa network simulations
  - Multi-node communication tests

---

## Project Milestones

1. [ ] Hardware driver implementation
2. [ ] MeshCore protocol implementation
3. [ ] CLI and web interface development
4. [ ] End-to-end testing
5. [ ] Documentation completion

---

## References

- [Official Meshcore Website](https://meshcore.io/)
- [Andy Kirby MeshCore Website](https://meshcore.co.uk/)
- [RFM95W/RFM98W Datasheet](https://github.com/SeeedDocument/RFM95-98_LoRa_Module/blob/master/RFM95_96_97_98_DataSheet.pdf)
- [SX1276/SX1278 Datasheet](https://semtech.my.salesforce.com/sfc/p/#E0000000JelG/a/2R0000001Rbr/6EfVZUorrpoKFfvaF_Fkpgp5kzjiNyiAbqcpqh9qSjE)
- [MeshCore Python Library](https://github.com/meshcore-dev/meshcore_py)
- [Uptronics Datasheet](https://pinout.xyz/pinout/uputronics_lora_expansion_board)




