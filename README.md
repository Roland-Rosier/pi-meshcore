# MeshCore Raspberry Pi 4 LoRa Implementation

This project originally intended to implement [MeshCore](https://meshcore.io/) on a Raspberry Pi 4 with LoRa expansion hat containing:
- RFM95W (SX1276) for 868MHz spectrum
- RFM98W (SX1278) for 434MHz spectrum

However, it has pivoted to attempt to use the radio transceivers in more of a listening context.

---

## Project Overview

This implementation **currently includes**:
- **LoRa Drivers**: SPI drivers for RFM95W (868MHz) and RFM98W (434MHz) with auto-detection
- **Framework**: Application lifecycle, command bus, scheduler, module manager, SPI lock abstraction
- **CLI Tools**: `check-hardware` (detection/validation), `pi-lora-config` (configuration), `pi-lora-test` (test utilities)

**Planned / Not Yet Implemented:**
- **MeshCore Protocol**: Client/Repeater implementation (optional dependency `meshcore>=2.3` available but not integrated)
- **Web Interface**: FastAPI-based dashboard (optional dependency `fastapi>=0.115`, `uvicorn>=0.34` available but not implemented)

---

## Hardware Requirements

### Raspberry Pi 4
- Minimum 4GB RAM
- GPIO pins for SPI communication

### LoRa Expansion Hat
- Uptronics RFM95W (868MHz) on CE0 slot
- Uptronics RFM98W (434MHz) on CE1 slot

### Pin Mapping

| Module | DIO0  | DIO5  |
|--------|-------|-------|
| RFM95W | WPi6  | WPi5  |
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
uv run .semgrep/run.sh
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

## Software Architecture (UPDATED)

### Core Components (IMPLEMENTED)
1. **LoRa Driver Layer** (`src/pi_lora/drivers/`)
2. **Framework Infrastructure** (`src/pi_lora/framework/`)
3. **CLI Layer** (`src/pi_lora/cli/`)

### Core Components (PLANNED)
4. **MeshCore Protocol** (`src/pi_lora/meshcore/`) — Not started
5. **Web Interface** (`src/pi_lora/web/`) — Not started

### Ambition
6. Fully implements a CLI with hardware checks, configuration management and status monitoring.
7. Able to communicate via the (WHAD)[https://whad.io/] protocol.
8. Implements MeshCore API ([meshcore_py](https://github.com/meshcore-dev/meshcore_py)) as a Client and Repeater mode.
9. Over-The-Air (OTA) protocol ([MeshCore spec](https://github.com/meshcore-dev/MeshCore))
10. Web Interface, with FastAPI-based API endpoint, real-time status dashboard and a configuration UI
11. EU LoRa duty cycle compliance: **Not yet implemented** — tracked as deferred item (see docs/coding_culture.md)"

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
├── .continue/                        # Continue.dev agent configuration (obsolete)
├── .kilo/                            # Kilo agent configuration directory
│   ├── agents/
│   │   ├── architectreviewer.md      # Architect reviewer agent configuration
│   │   ├── repo_analyst.md           # Repository analysis agent configuration
│   │   └── planner.md                # Custom planner agent configuration (writes to root plan directories)
│   ├── kilo.jsonc                    # Kilo main configuration file
│   ├── rules/
│   │   ├── 01-strict-tool-calls.md   # Strict tool call enforcement rules
│   │   ├── 02-system-constraints.md    # Global system constraints and safety modes
│   │   ├── 03-act-execution-protocol.md # Act phase execution protocol guidelines
│   │   ├── 03-architect-execution-protocol.md # Architect phase execution protocol guidelines
│   │   ├── 03-plan-execution-protocol.md # Plan phase execution protocol guidelines
│   │   ├── 04-use-desktop-commander-mcp.md # Desktop Commander MCP tool usage rules
│   │   └── 05-use-native-edit-tools.md   # Native file editing tool (single_find_and_replace) rules
│   └── skills/                         # Agent skill definitions
│       ├── grill-me/SKILL.md           # Stress-test interview skill for design validation
│       ├── grill-me-proscons/SKILL.md  # Pros/cons interview skill for design validation
│       └── repo-analyst/SKILL.md       # Repository analysis skill
├── .gitattributes                    # Git attribute definitions for line endings, filters
├── .gitignore                        # Files and directories excluded from version control
├── .gitmodules                       # Git submodule definitions
├── .pre-commit-config.yaml           # Pre-commit hook configuration for automated linting/formatting checks
├── .prompts/                         # Reusable agent prompt templates
│   └── repo_analyst.prompt           # Repository analysis task prompt template
├── .semgrep/                         # Semgrep SAST security/correctness rules engine (80+ rule files)
│   ├── rules/
│   │   ├── best-practice/            # Best practice linting rules
│   │   ├── correctness/              # Correctness linting rules
│   │   │   └── common-mistakes/      # Common mistake patterns
│   │   ├── maintainability/          # Maintainability linting rules
│   │   └── security/                 # Security scanning rules
│   │       └── audit/                # Audit patterns (dangerous calls, injection)
│   │           ├── insecure-transport/ # Transport security rules
│   │           └── sqli/             # SQL injection patterns
│   ├── run.sh                        # Semgrep execution runner
│   ├── semgrep-semgrep-rules         # External semgrep ruleset
│   └── trailofbits-semgrep-rules     # External semgrep ruleset
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
│   ├── rfm9x_sx127x_config.yaml      # YAML config file for RFM95W/RFM98W module parameters (pins, freq)
│   └── ruff-lint-workflow.yml.disabled # Disabled ruff lint workflow configuration file
├── docs/                             # Documentation directory
│   ├── coding_culture.md             # Code style and cultural guidelines
│   ├── concurrency_patterns.md       # Concurrency design patterns
│   ├── exception_handling.md         # Exception handling patterns
│   ├── patterns/                     # Architecture pattern documentation
│   │   ├── README.md                 # Patterns index
│   │   ├── application_lifecycle.md  # Application lifecycle patterns
│   │   ├── cli_async_patterns.md     # CLI async patterns
│   │   ├── command_bus_patterns.md   # Command bus patterns
│   │   ├── concurrency_lazy_async_lock.md # Lazy async lock patterns
│   │   ├── exception_handling.md     # Exception handling patterns
│   │   ├── module_registration_rollback.md # Module registration rollback
│   │   ├── scheduler_patterns.md     # Scheduler patterns
│   │   ├── semgrep_anti_regression.md # Semgrep anti-regression patterns
│   │   ├── spi_lock_abstraction.md   # SPI lock abstraction patterns
│   │   └── validation_gates_testing.md # Validation gates testing patterns
│   ├── plan_summaries/               # Plan summary documents
│   │   └── 2026_10_08_hardening_spike.md # Hardening spike summary
│   ├── protocol_contracts.md         # Protocol contract definitions
│   ├── python_version_requirement.md # Python version requirements
│   └── regression_prevention.md      # Regression prevention strategies
├── pyproject.toml                    # Python project metadata, pytest & coverage configuration
├── requirements.txt                  # Python dependency list (FastAPI, meshcore, pytest, etc.)
├── scripts/                          # Utility scripts directory
│   ├── aiologic_probe.py             # aiologic library probe script
│   ├── diagnose_monkeypatch.py       # Monkeypatch diagnostics script
│   └── sync_semgrep_rules.py         # Sync semgrep rule files from external sources
├── uv.lock                           # Lock file pinning exact dependency versions for reproducible builds
├── src/pi_lora/                      # Main source code package
│   ├── __init__.py                   # Package initialization for pi_lora top-level module
│   ├── types.py                      # Shared type definitions and protocols
│   ├── cli/
│   │   ├── __init__.py               # CLI sub-package initialization
│   │   ├── _entry_points.py          # CLI entry point definitions
│   │   ├── _logging.py               # CLI logging configuration
│   │   ├── check_hardware.py         # CLI tool for LoRa hardware detection and status checks
│   │   ├── config.py                 # CLI configuration management
│   │   ├── main.py                   # CLI entry point and command routing
│   │   └── test.py                   # CLI test utilities
│   ├── drivers/
│   │   ├── __init__.py               # Drivers sub-package initialization
│   │   ├── configs/                    # Driver config subdirectory
│   │   │   └── rfm9x_sx127x_config.yaml  # Driver-specific YAML config
│   │   ├── spi/                        # SPI bus abstraction layer
│   │   │   ├── __init__.py           # SPI sub-package initialization
│   │   │   ├── README.md             # SPI bus abstraction layer documentation
│   │   │   ├── bus.py                # SPI bus communication wrapper
│   │   │   ├── factory.py            # SPI device factory
│   │   │   └── locks.py              # SPI bus locking primitives
│   │   ├── lora_detection.py         # LoRa module auto-detection logic (RFM95W/RFM98W)
│   │   ├── lora_module.py              # RFM95W/RFM98W radio driver implementation (SX1276/SX1278)
│   │   ├── rfm9x_sx127x_config_model.py  # Config data models for RFM95W/RFM98W module settings
│   │   ├── rfm9x_sx127x_config_loader.py   # YAML config loader for RFM95W/RFM98W parameters
│   │   ├── rfm9x_sx127x_config_validator.py  # Config validation for RFM module settings
│   │   ├── rfm9x_sx127x_handler.py         # High-level handler for RFM95W/RFM98W operations
│   │   ├── rfm9x_sx127x_modes.py         # RFM95W/RFM98W frequency mode definitions and constants
│   │   ├── rfm9x_sx127x_module.py        # RFM95W/RFM98W radio module abstraction layer
│   │   └── rfm9x_sx127x_radio_instance.py  # RFM95W/RFM98W radio instance abstraction
│   └── framework/                        # Framework infrastructure subpackage
│       ├── __init__.py                 # Framework package init
│       ├── README.md                 # Framework infrastructure documentation
│       ├── application.py            # Application lifecycle management
│       ├── command_bus.py            # Command dispatch bus
│       ├── events.py                 # Event system definitions
│       ├── lazy_async_lock.py        # Async lock primitive with context management
│       ├── module_manager.py         # Module registration and lifecycle management
│       └── scheduler.py              # Task scheduling engine
└── tests/                            # Test suite
    ├── __init__.py                   # Tests package initialization
    ├── conftest.py                   # pytest fixtures and shared test configuration
    ├── fakes.py                      # Fake/mock implementations for driver testing
    ├── cli/                          # CLI test subdirectory
    │   ├── __init__.py               # CLI tests package init
    │   ├── test_check_hardware.py    # CLI hardware check tests
    │   ├── test_test_hardware_cleanup.py # CLI hardware cleanup tests
    │   └── test_test_hardware_keyboard_interrupt.py # CLI keyboard interrupt tests
    ├── contracts/                    # Contract test subdirectory
    │   ├── __init__.py               # Contract tests package init
    │   └── test_spi_bus_contract.py  # SPI bus contract tests
    ├── drivers/                      # Driver tests
    │   ├── __init__.py               # Driver tests package init
    │   ├── spi/                      # SPI driver tests
    │   │   ├── __init__.py           # SPI tests package init
    │   │   ├── test_bus.py           # SPI bus tests
    │   │   ├── test_bus_validation.py # SPI bus validation tests
    │   │   ├── test_factory.py       # SPI factory tests
    │   │   ├── test_locks.py         # SPI locks tests
    │   │   ├── test_locks_concurrent.py # SPI locks concurrent tests
    │   │   └── test_spidev_patch_contextvar.py # SPI contextvar patch tests
    │   ├── test_config_loader.py             # Config loader tests
    │   ├── test_config_loader_concurrent.py  # Config loader concurrent tests
    │   └── test_rfm9x_sx127x_module.py       # RFM module tests
    ├── framework/                    # Framework test subdirectory
    │   ├── test_application.py       # Framework application tests
    │   ├── test_application_start_stop_race.py # App start/stop race tests
    │   ├── test_command_bus.py       # Command bus tests
    │   ├── test_events.py            # Event system tests
    │   ├── test_exceptions.py        # Framework exception class tests
    │   ├── test_interrupt_bridge_atomic_drop.py # Interrupt bridge atomic drop tests
    │   ├── test_interrupt_bridge_threadsafe.py  # Interrupt bridge threadsafe tests
    │   ├── test_lazy_async_lock.py   # Lazy async lock tests
    │   ├── test_module_event_loop.py # Module event loop tests
    │   ├── test_module_manager.py    # Module manager tests
    │   └── test_scheduler.py         # Scheduler tests
    ├── spi/                          # SPI mock tests
    │   ├── __init__.py               # SPI mock tests package init
    │   ├── mock.py                   # SPI mock implementation
    │   ├── test_bus.py               # SPI bus tests
    │   ├── test_integration.py       # SPI integration tests
    │   ├── test_locks.py             # SPI locks tests
    │   └── test_mock.py              # SPI mock tests
    ├── test_check_hardware_cli.py    # Unit tests for CLI hardware check tool
    ├── test_cli_async_integration.py # CLI async integration tests
    ├── test_config_cli.py            # Unit tests for CLI config module
    ├── test_config_cli_integration.py  # Integration tests for CLI config workflows
    ├── test_dependency_resolution.py # Dependency resolution tests
    ├── test_entry_points.py          # CLI entry point tests
    ├── test_fakes.py                 # Unit tests for fake/mock objects
    ├── test_hardware_cli.py          # Hardware CLI tests
    ├── test_hardware_integration.py  # Hardware integration tests
    ├── test_lora_module.py           # Unit tests for LoRa radio module operations
    ├── test_lora_module_detection.py   # Tests for hardware detection logic
    ├── test_lora_module_detector.py      # Tests for the detector subsystem component
    ├── test_main_cli.py              # Main CLI tests
    ├── test_rfm9x_sx127x_config_loader.py  # Tests for config loader subsystem
    ├── test_rfm9x_sx127x_config_model.py   # Tests for config data models
    ├── test_rfm9x_sx127x_config_validator.py # Tests for config validation logic
    ├── test_rfm9x_sx127x_handler.py        # Tests for RFM module handler
    ├── test_rfm9x_sx127x_modes.py        # Unit tests for RFM95W/RFM98W mode definitions
    ├── test_rfm9x_sx127x_module.py       # Unit tests for RFM95W/RFM98W radio module implementation
    ├── test_rfm9x_sx127x_radio_instance.py # Unit tests for RFM radio instance class
    ├── test_semgrep_rule_no_false_positive.py # Semgrep false positive tests
    ├── test_semgrep_run_sh.py        # Semgrep run script tests
    └── test_sync_cli_imports.py      # CLI sync import tests
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
- [Uptronics store (showing different variants)](https://store.uputronics.com/products/raspberry-pi-loratm-expansion-board)




