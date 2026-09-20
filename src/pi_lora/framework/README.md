# MeshCore Asyncio Framework for RPi 4 LoRa Hat

## Architecture Overview

The `src/pi_lora/framework/` package implements an asyncio-based actor framework that manages multiple
`Rfm9xSx127xModule` instances (one per LoRa radio slot: CE0=RFM95W, CE1=RFM98W) through a unified
event queue per module. Each module runs its own event loop task that processes events sequentially,
eliminating race conditions on `current_state_instance`.

**Key Design**: `Rfm9xSx127xModule` exposes state via getter methods only; no direct attribute access
to `current_state_instance` or `event_queue`. Module identity (`spi_device_id`, `ce_number`) is set
via setters after construction, avoiding constructor coupling.

## Architecture Overview Diagram

```
┌───────────────────────────────────────────────────────────────┐
│                      Application                              │
│  ┌────────────────┐  ┌────────────────┐  ┌──────────────────┐ │
│  │   ModuleManager│  │    Scheduler   │  │    CommandBus    │ │
│  │                │  │                │  │                  │ │
│  │ - load config  │  │ - TimerEvent   │  │ - register_hndr  │ │
│  │ - create mods  │  │ - Interval mgmt│  │ - execute (syn)  │ │
│  │ - set identity │  │ - Idle pacer   │  │ - dispatch (asyn)│ │
│  │ - register     │  │ - Interrupts   │  │                  │ │
│  └────────┬───────┘  └────────┬───────┘  └─────────┬────────┘ │
│           │                   │                    │          │
│           ▼                   ▼                    ▼          │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │            Rfm9xSx127xModule (×N)                       │  │
│  │  - event_queue: asyncio.Queue[ModuleEvent]              │  │
│  │  - event_loop task: processes queue sequentially        │  │
│  │  - current_state_instance: PRIVATE (encapsulated)       │  │
│  │  - spi_device_id, ce_number: set via setters            │  │
│  │  - GETTERS: get_current_state_name(),                   │  │
│  │             get_event_queue_size(),                     │  │
│  │             get_spi_device_id(), get_ce_number()        │  │
│  │  - delegates event handling to current_state_instance   │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
src/pi_lora/framework/
├── __init__.py          # Public API exports (all types and classes)
├── events.py            # EventType enum, StopMode enum, ModuleEvent + typed payloads
├── scheduler.py         # TimerScheduler, IdlePacer, InterruptBridge, Scheduler compositor
├── module_manager.py    # ModuleManager — loads config, creates modules, registers with scheduler
├── command_bus.py       # CommandBus — handler registry + module resolver for sync/async dispatch
└── application.py       # Application — owns all components; start/stop/run_blocking_command/run_async_command/get_status
```

## Core Components

### Events (`events.py`)

| Type | Description |
|------|-------------|
| `EventType` | Enum: `TIMER`, `IDLE`, `INTERRUPT`, `COMMAND`, `STATE_CHANGE` |
| `StopMode` | Enum: `DRAIN` (process remaining), `CANCEL_ALL` (drop all), `PAUSE` (pause, keep queue) |
| `ModuleEvent` | Base dataclass: `(event_type, payload, timestamp, source)` |
| `TimerEvent` | Payload: `(interval_seconds)` |
| `InterruptEvent` | Payload: `(gpio_pin)` |
| `CommandEvent` | Payload: `(command)` |
| `StateChangeEvent` | Payload: `(new_state, reason)` |
| `EventHandler` | Protocol: `async on_event(event: ModuleEvent) -> None` |

All event dataclasses are `frozen=True`.

### Scheduler (`scheduler.py`)

| Component | Concurrency | Responsibility |
|-----------|-------------|----------------|
| `TimerScheduler` | One task per module | Posts `TIMER` events at configurable intervals |
| `IdlePacer` | Single task | Paces all idle-enabled modules with `IDLE` events via `await asyncio.sleep(0)` |
| `InterruptBridge` | Single task | Maps GPIO pins to modules; single `asyncio.Event` triggers broadcast to all registered modules |
| `Scheduler` | Compositor | Composes all three; implements `SchedulerRegistration` protocol for state-level registration |

**`SchedulerRegistration` Protocol** (sync-compatible, used by states in `on_entry`/`on_exit`):
- `set_timer_interval(module, interval)` 
- `set_idle_enabled(module, enabled)`
- `get_timer_interval(module)`

### ModuleManager (`module_manager.py`)

Centralized module lifecycle management. `load_from_config(config, scheduler)`:
1. Iterates `config.modules[module_name].devices[]` → `DeviceModuleAttachment`
2. Creates `Rfm9xSx127xModule(state=StateBits.UNKNOWN_STATE)` per attachment
3. Sets identity via `set_spi_device_id()` and `set_ce_number()`
4. Extracts GPIO pins from `dio_gpio_mappings` (handles both `GPIO` and `WPi` prefixes)
5. Registers module with scheduler (timer_interval=1.0, idle_enabled=True, interrupt_gpio_pins)
6. Stores in `modules_by_id[(spi_device_id, ce_number)]` and `modules` list

Lookup: `get_module(spi_device_id, ce_number)`, `get_all_modules()`.

### CommandBus (`command_bus.py`)

Dual dispatch model:
- **`execute(cmd)`** — Synchronous dispatch. Resolves handler by `type(command)`, calls it (awaits if coroutine). Used for blocking commands.
- **`dispatch(cmd)`** — Asynchronous dispatch. Resolves target module via `set_module_resolver()`, posts `CommandEvent` to module's event queue.

Handler registry supports priority-based override: `register_handler(command_type, handler, priority=0)`.

### Application (`application.py`)

Top-level runtime compositor:
1. **`start()`** — Loads config → registers scheduler → starts all event loops
2. **`stop()`** — Drains all module queues → stops scheduler (reverse order: interrupt, idle, timer)
3. **`run_blocking_command(cmd)`** — Via `CommandBus.execute()`
4. **`run_async_command(cmd)`** — Via `CommandBus.dispatch()`
5. **`get_status()`** — Snapshot of all modules: `{spi_device_id, ce_number, state, queue_size}`

Command target resolution (`_resolve_module_for_command`):
- `target == "all"` → returns first module (broadcast handler iterates all)
- `target == (spi_device_id, ce_number)` → direct lookup via `ModuleManager.get_module()`

## Event Flow Diagram

```
┌──────────────────┐     ┌──────────────────┐      ┌──────────────────┐
│    Scheduler     │     │   CommandBus     │      │  GPIO Driver     │
│   (timers)       │     │   (commands)     │      │  (interrupts)    │
│    IdlePacer     │     │                  │      │                  │
│  InterruptBridge │     │                  │      │                  │
└────────┬─────────┘     └────────┬─────────┘      └────────┬─────────┘
         │                        │                         │
         ▼                        ▼                         ▼
┌──────────────────────────────────────────────────────────────┐
│          module.event_queue (per module, asyncio.Queue)      │
│  [TimerEvent] [CommandEvent] [InterruptEvent] [...]          │
└────────────────────────────────┬─────────────────────────────┘
                                 │
                                 ▼
┌──────────────────────────────────────────────────────────────┐
│          module.event_loop() task                            │
│  while running:                                              │
│      event = await event_queue.get()                         │
│      await current_state_instance.on_event(event)            │
└──────────────────────────────────────────────────────────────┘
```

### Event Processing Sequence

1. **Scheduler/CommandBus/GPIO Driver** produce typed events (`TimerEvent`, `CommandEvent`, `InterruptEvent`)
2. Events are posted to `module.event_queue` (asyncio.Queue, one per module)
3. Each module's `_event_loop()` task runs concurrently on the global event loop:
   - `await event_queue.get()` — dequeue next event
   - `await current_state_instance.on_event(event)` — delegate to active state handler
4. States implement `on_event()` polymorphically; base class provides no-op default
5. Cancellation modes (`StopMode.DRAIN`, `CANCEL_ALL`, `PAUSE`) control queue processing behavior

### Concurrency Model

- **One task per module** — events serialized within each module's queue
- No concurrent access to `current_state_instance` — only one event processed at a time
- If `on_event()` blocks (e.g., SPI bus lock), **only that module's task suspends**
- Other modules continue executing on the shared event loop

## Concurrency Guarantees

- One event loop task per module processes events sequentially from its queue
- No concurrent access to `current_state_instance` — events serialized by queue
- If `current_state_instance.on_event()` blocks on `aiologic.Lock`, **only that module's task suspends**
- Other modules' event loops continue executing on the same event loop
- `IdleEvent` paced via `await asyncio.sleep(0)` yields control cooperatively
- Timer precision: `asyncio.sleep(interval)` — sufficient for radio duty cycles (ms resolution)
- **Pause/Resume**: `stop_event_loop(PAUSE)` keeps queue accepting events; `start_event_loop()` resumes dispatching

## Configuration Integration

Uses existing models from `rfm9x_sx127x_config_model.py`:
- `Rfm9xSx127xConfig.modules[module_name].devices[]` → `DeviceModuleAttachment`
- Each attachment provides `spi_device_id`, `ce_number`, `dio_gpio_mappings`
- ModuleManager extracts GPIO pins for `InterruptBridge.register_interrupt(gpio_pin, module)`

## Public API (`__init__.py`)

```python
from meshcore.framework import (
    EventType, StopMode,                          # Enums
    ModuleEvent, TimerEvent, InterruptEvent,      # Event payloads
    CommandEvent, StateChangeEvent,               # Event payloads
    EventHandler, SchedulerRegistration,           # Protocols
    TimerScheduler, IdlePacer, InterruptBridge,   # Scheduler components
    Scheduler,                                    # Compositor
    CommandBus,                                   # Handler registry + resolver
    Application,                                  # Top-level runtime
)
```

## CLI Integration Points (Skeleton)

| CLI Mode | Application Method |
|----------|-------------------|
| 5a: Blocking test | `app.run_blocking_command(TestHardwareCommand())` |
| 5b: Async start | `await app.run_async_command(StartCommand())` |
| 5c: Status | `app.get_status()` |
| 5d: Network | `command_bus.dispatch(NetworkCommand(...))` |

Commands are dataclasses; handlers registered by type in application initialization.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| aiologic not available in all environments | Kept as optional dependency; fallback to asyncio.Event |
| Too many tasks if N grows | N ≤ 2 (CE0/CE1) in practice; task overhead negligible |
| Interrupt storm starves event loop | Rate-limit in InterruptBridge; batch events |
| Config changes at runtime | ModuleManager reload() method (future work) |
| Encapsulation drift | Getters enforced; direct attribute access caught by code review |

## Out of Scope (Future Work)

- Actual SPI driver implementation
- `on_jiffy`/`on_idle`/`on_interrupt` method bodies in state classes
- GPIO interrupt wiring (gpiod/RPi.GPIO integration)
- FastAPI web server mounting
- CLI command definitions
- Duty-cycle enforcement logic
- Frequency management / scanner tasks

## Implementation Stages

| Stage | Scope | Validation |
|-------|-------|------------|
| 1: Foundation | Event types, module event loop + identity setters/getters, state `on_event` handler | Unit tests for events and event loop with mock state |
| 2: Scheduler | TimerScheduler, IdlePacer, InterruptBridge, ModuleManager config loading | Unit tests for scheduler components and config loading |
| 3: Integration | CommandBus, Application compositor, public API exports | Integration tests for start/stop lifecycle and command bus |

All stages validated with `pytest`, `mypy`, `ruff`, and `.semgrep/run.sh`. All four commands must exit with code 0.
