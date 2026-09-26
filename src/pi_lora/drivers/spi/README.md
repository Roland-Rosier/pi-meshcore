# SPI Driver Abstraction Layer

## Overview

The `src/pi_lora/drivers/spi/` package provides a clean abstraction layer for SPI communication with RFM9x/SX127x LoRa modules on Raspberry Pi. It implements the **Abstract Factory** pattern with protocol-based dependency injection, enabling seamless switching between real hardware (`spidev`) and mock implementations for testing.

## Architecture

```
src/pi_lora/drivers/spi/
├── __init__.py       # Public API exports
├── bus.py            # SpiBus protocol + RealSpiBus implementation
├── factory.py        # SpiBusFactory protocol + RealSpiBusFactory
└── locks.py          # Per-bus critical section locking (async/sync)
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Interface** | Protocol-based (`SpiBus`, `SpiBusFactory`) | Zero runtime overhead, full static type checking |
| **Factory Location** | Dedicated `spi/` package | Separation of concerns; SPI abstraction independent of radio logic |
| **Mock Implementation** | Test-only (`tests/spi/mock.py`) | Production code stays clean; no test dependencies |
| **Critical Section** | `aiologic.LowLevelLock` per bus number | Prevents concurrent access when multiple CE pins share one SPI bus |
| **Injection Point** | `Rfm9xSx127xModule.__init__(spi_factory: SpiBusFactory)` | Module owns SPI lifecycle; factory creates bus instances |

## Core Components

### 1. `SpiBus` Protocol (`bus.py`)

Defines the minimal SPI bus interface required by the radio handler:

```python
class SpiBus(Protocol):
    def open(self, bus: int, device: int) -> None: ...
    def close(self) -> None: ...
    async def xfer2(self, data: list[int]) -> list[int]: ...

    # Properties with getters/setters
    max_speed_hz: int
    mode: int
    lsbfirst: bool
    no_cs: bool
```

**Key points:**
- `xfer2` is `async` to support lock acquisition in async context
- Properties mirror `spidev.SpiDev` attributes for drop-in compatibility
- Protocol enables structural subtyping — no inheritance required

### 2. `RealSpiBus` (`bus.py`)

Production implementation wrapping `spidev.SpiDev`:

```python
class RealSpiBus:
    def __init__(self) -> None:
        self._spidev: Any | None = None
        self.bus_number: int = 0
        self.device_number: int = 0

    def open(self, bus: int, device: int) -> None:
        import spidev
        self.bus_number = bus
        self.device_number = device
        self._spidev = spidev.SpiDev()
        self._spidev.open(bus, device)

    async def xfer2(self, data: list[int]) -> list[int]:
        lock = get_bus_lock(self.bus_number)
        await lock.acquire()
        try:
            return self._spidev.xfer2(data)
        finally:
            lock.release()
```

**Critical section behavior:**
- Lock acquired **per bus number** (not per device)
- Covers entire `xfer2()` call atomically
- Works in both async (`await lock.acquire()`) and sync (`lock.acquire()`) contexts
- Falls back to `threading.Lock` if `aiologic` unavailable

### 3. `SpiBusFactory` Protocol (`factory.py`)

```python
class SpiBusFactory(Protocol):
    def create(self, bus: int, device: int) -> SpiBus: ...
```

### 4. `RealSpiBusFactory` (`factory.py`)

```python
class RealSpiBusFactory:
    def create(self, bus: int, device: int) -> SpiBus:
        bus_instance = RealSpiBus()
        bus_instance.open(bus=bus, device=device)
        return bus_instance
```

**Usage in Application:**
```python
# src/pi_lora/framework/application.py
self.spi_factory = RealSpiBusFactory()
module_manager.load_from_config(config, scheduler, self.spi_factory)
```

### 5. Per-Bus Locking (`locks.py`)

```python
_bus_locks: dict[int, SpiLock] = {}

def get_bus_lock(bus_number: int) -> SpiLock:
    if bus_number not in _bus_locks:
        try:
            import aiologic
            _bus_locks[bus_number] = _AsyncSpiLock(aiologic.LowLevelLock())
        except (ImportError, AttributeError):
            _bus_locks[bus_number] = _SyncSpiLock()
    return _bus_locks[bus_number]
```

**Dual-mode compatibility:**
- `_AsyncSpiLock` wraps `aiologic.LowLevelLock` — `acquire()` returns awaitable
- `_SyncSpiLock` wraps `threading.Lock` — `acquire()` blocks synchronously
- Same lock instance returned for same bus number across all callers

## Integration with Radio Module

### `Rfm9xSx127xModule` (`../rfm9x_sx127x_module.py`)

```python
class Rfm9xSx127xModule:
    def __init__(
        self,
        state: StateBits,
        spi_factory: SpiBusFactory | None = None,
    ) -> None:
        self._spi_factory: SpiBusFactory | None = spi_factory
        self.spi_bus: SpiBus | None = None
        # ... state management fields ...

    async def init_spi_bus(self) -> None:
        if self._spi_factory is None or self.spi_device_id is None:
            return
        self.spi_bus = self._spi_factory.create(
            bus=self.spi_device_id, device=self.ce_number or 0
        )
        self.spi_bus.open(self.spi_device_id, self.ce_number or 0)

    async def close_spi(self) -> None:
        if self.spi_bus is not None:
            self.spi_bus.close()
            self.spi_bus = None
```

**Lifecycle:**
1. Module constructed with `spi_factory` (injected by `ModuleManager`)
2. `spi_device_id` and `ce_number` set by `ModuleManager` after construction
3. `init_spi_bus()` called during startup → creates and opens `SpiBus`
4. `close_spi()` called by `Application.stop()` during shutdown

### `Rfm9xSx127xHandler` (`../rfm9x_sx127x_handler.py`)

Stateless utility class — all methods are `@staticmethod` taking `module: Rfm9xSx127xModule` as first parameter:

```python
class Rfm9xSx127xHandler:
    @staticmethod
    async def read_reg(module: "Rfm9xSx127xModule", register: int) -> int:
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        response = await spi_bus.xfer2([register & 0x7F, 0x00])
        return response[1] if len(response) > 1 else 0

    @staticmethod
    async def write_reg(module: "Rfm9xSx127xModule", register: int, value: int) -> None:
        spi_bus = module.spi_bus
        if spi_bus is None:
            raise RuntimeError("module.spi_bus is None")
        await spi_bus.xfer2([register | 0x80, value])

    @staticmethod
    async def set_module_mode(module: "Rfm9xSx127xModule", mode: ModeBits) -> bool:
        # Read-modify-write on RegOpMode using RegisterLayout bit masks
        ...

    @staticmethod
    async def write_and_verify_frequency_for_khz(
        module: "Rfm9xSx127xModule", freq_khz: int
    ) -> tuple[bool, int, int, int, int, int, int]:
        # Write Frf MSB/MID/LSB, read back, compare
        ...

    @staticmethod
    def calc_freq_registers_for_khz(freq_khz: int) -> tuple[int, int, int]:
        # Pure calculation: FSTEP = 61.03515625 Hz
        ...
```

**Register protocol (SX127x datasheet):**
- Write: `[register | 0x80, value]`
- Read:  `[register & 0x7F, 0x00]` → response[1] contains register value

## Testing

### Mock Implementation (`tests/spi/mock.py`)

```python
class MockSpiBus:
    """In-memory register simulation matching FakeSpiDev behavior."""

    def __init__(self, max_speed_hz=1_000_000, mode=0, lsbfirst=False, no_cs=False):
        self._registers: dict[int, int] = {}
        self._opened: bool = False

    async def xfer2(self, data: list[int]) -> list[int]:
        # Simulates address-based register read/write
        # Write: cmd_byte & 0x80 != 0 → store value
        # Read:  cmd_byte & 0x80 == 0 → return stored value (default 0x00)
        ...

class MockSpiBusFactory:
    def create(self, bus: int = 0, device: int = 0) -> SpiBus:
        mock_bus = MockSpiBus()
        mock_bus.open(bus=bus, device=device)
        return mock_bus
```

### Test Usage Pattern

```python
# tests/test_rfm9x_sx127x_module.py
def test_spi_bus_injection_and_frequency_write():
    factory = MockSpiBusFactory()
    module = Rfm9xSx127xModule(state=StateBits.LORA_SLEEP, spi_factory=factory)
    module.set_spi_device_id(0)
    module.set_ce_number(0)
    await module.init_spi_bus()

    success = await module.write_and_verify_frequency_for_khz(415_000)
    assert success is True
```

## Hardware Mapping (RPi 4 + Uputronics LoRa Hat)

| Slot | Chip | Frequency | SPI Bus | CE Pin | DIO0 | DIO5 |
|------|------|-----------|---------|--------|------|------|
| CE0  | RFM95W (SX1276) | 868 MHz | 0 | 0 (CE0) | WPi6 | WPi5 |
| CE1  | RFM98W (SX1278) | 434 MHz | 0 | 1 (CE1) | WPi27 | WPi26 |

**Note:** Both slots share **SPI bus 0** (main SPI). The per-bus lock in `RealSpiBus.xfer2()` ensures atomic transactions when both radios are active.

## Configuration

### SPI Settings (Typical)

```python
# Default spidev settings for SX127x
spi_bus.max_speed_hz = 5_000_000  # 5 MHz max per datasheet
spi_bus.mode = 0                   # SPI Mode 0 (CPOL=0, CPHA=0)
spi_bus.lsbfirst = False           # MSB first
spi_bus.no_cs = False              # Hardware CS controlled by kernel
```

These can be configured after `open()` via the property setters.

## Validation Commands

After any changes to the SPI package, run:

```bash
uv run pytest tests/ -v
uv run mypy src/
uv run ruff check src/ tests/
uv run .semgrep/run.sh
```

All four must pass with zero errors.

## Migration Notes

- **Legacy `LoRaModule`** (`lora_module.py`) — uses `spidev` directly, **not modified** in this abstraction. Marked for eventual removal.
- **`LoRaModuleDetector`** — uses legacy module, **out of scope** for SPI abstraction.
- **CLI `check_hardware.py`** — unchanged, continues using direct `spidev` access.

## Future Extensions

- **Auxiliary SPI (bus 1)** — Supported by `bus_number` parameter; requires device tree overlay
- **DMA transfers** — Would require `spidev` 3.6+ and kernel support; `xfer2` signature compatible
- **Multiple bus factories** — `SpiBusFactory` protocol allows per-bus factory implementations