# Module Event Queue Architecture

## Overview

The `Rfm9xSx127xModule` (`src/pi_lora/drivers/rfm9x_sx127x_module.py`) contains a **centralized, single-threaded event loop** that drives all state transitions, timer handling, interrupt processing, and command dispatch for a LoRa radio module. This document captures the architecture, data flows, and invariants.

---

## Architecture Diagram

```mermaid
flowchart TB
    %% External producers
    Scheduler["Scheduler\nTimerScheduler / IdlePacer"] -->|put TIMER/IDLE| Queue
    InterruptBridge["InterruptBridge\nGPIO callback"] -->|put INTERRUPT| Queue
    CommandBus["CommandBus\ndispatch"] -->|put COMMAND| Queue
    StateChange["set_current_state()\n/ request_reset_transition()"] -->|put STATE_CHANGE| Queue

    %% Core queue
    Queue["asyncio.Queue[ModuleEvent]\nUNBOUNDED\nput_nowait() safe in __init__"] --> Loop

    %% Event loop
    Loop["_event_loop()\nasyncio.Task"] --> Buffer
    Loop --> Waiters
    Loop --> Dispatch

    %% Buffer
    Buffer["_event_buffer: dict[EventType, deque]\nmaxlen=1000 per type"] --> History["get_event_history()\ndrain_events()\nget_last_event()"]

    %% Waiters
    Waiters["_event_waiters: dict[EventType, list[_EventWaiter]]\n_EventWaiter = (predicate, asyncio.Event, result)"] --> wait_for_event["wait_for_event()\nreplays buffer FIRST"]

    %% Dispatch
    Dispatch -->|STATE_CHANGE| StateInterceptor["Intercept STATE_CHANGE\n→ set_current_state()"]
    Dispatch -->|all events| StateInstance["current_state_instance.on_event(event, self)"]
    StateInterceptor --> StateInstance

    %% State machine
    StateInstance --> Modes["Rfm9xSx127xMode subclasses\n(Sleep, Standby, FSTX, FS_RX, Tx, Rx, ...)"]
    Modes --> StateChange["request_reset_transition()\n→ queues STATE_CHANGE"]

    %% Lifecycle
    Loop -.->|start_event_loop()| Start["create_task(_event_loop())"]
    Loop -.->|stop_event_loop(StopMode)| StopModes

    subgraph StopModes [StopMode Variants]
        DRAIN["DRAIN\ncancel task → await drain"]
        CANCEL_ALL["CANCEL_ALL\ndiscard queue → await"]
        PAUSE["PAUSE\n_paused=True → sleep(0.01)"]
    end
```

---

## Core Components

### 1. Event Queue (`asyncio.Queue[ModuleEvent]`)

- **Unbounded** — `put_nowait()` never blocks/raises `QueueFull`
- Created **before** `set_current_state()` in `__init__` so `UnknownState.on_entry()` → `request_reset_transition()` can queue `RESET_STATE` during construction
- Single queue per module instance

### 2. Event Loop (`_event_loop()`)

Single background task created by `start_event_loop()`. Processing phases per event:

```python
while True:
    if self._paused:
        await asyncio.sleep(0.01)
        continue

    event = await self.event_queue.get()

    # Phase 1: BUFFER — never lose events
    self._event_buffer[event.event_type].append(event)

    # Phase 2: NOTIFY WAITERS — before dispatch
    for waiter in self._event_waiters[event.event_type]:
        if waiter.predicate(event) and waiter.result is None:
            waiter.result = event
            waiter.event.set()

    # Phase 3: DISPATCH
    try:
        # Intercept STATE_CHANGE at module level
        if event.event_type == EventType.STATE_CHANGE and is_state_change_event(event):
            new_state = event.payload.new_state
            self.set_current_state(new_state)

        # Delegate to current mode
        if self.current_state_instance is not None:
            await self.current_state_instance.on_event(event, self)
    except Exception:
        logger.exception(...)
        continue
```

### 3. Buffer System (`_event_buffer`)

- `defaultdict(lambda: deque(maxlen=1000))` — per-`EventType` ring buffer
- **Never loses events** even if dispatch fails
- Enables:
  - `wait_for_event()` **replay** (checks buffer before registering waiter)
  - `get_event_history(event_type, limit?)`
  - `drain_events(event_type)` — return + clear
  - `get_last_event(event_type)`

### 4. Waiter Pattern (`_event_waiters` + `_EventWaiter`)

```python
@dataclass
class _EventWaiter:
    predicate: Callable[[ModuleEvent[Any]], bool]
    event: asyncio.Event
    result: ModuleEvent[Any] | None = None
```

**Race-free `wait_for_event()`**:
1. Replay buffered events first (no other code runs between check and registration)
2. Register waiter with predicate
3. `asyncio.wait_for(waiter.event.wait(), timeout)`
4. Cleanup in `finally` block prevents memory leak

### 5. Stop Modes (`StopMode` enum)

| Mode | Behavior |
|------|----------|
| `DRAIN` | Cancel task → process remaining queue in `CancelledError` handler → await task |
| `CANCEL_ALL` | Discard queue via `get_nowait()` loop → await task |
| `PAUSE` | Set `_paused=True`; loop sleeps 10ms, keeps accepting events |

---

## Event Types & Payloads

Defined in `src/pi_lora/framework/events.py`:

| EventType | Payload | Source |
|-----------|---------|--------|
| `TIMER` | `TimerEvent(interval_seconds)` | `TimerScheduler._timer_task()` |
| `IDLE` | `None` | `IdlePacer._idle_task()` |
| `INTERRUPT` | `InterruptEvent(gpio_pin)` | `InterruptBridge._interrupt_task()` |
| `COMMAND` | `CommandEvent(command)` | `CommandBus.execute()` |
| `STATE_CHANGE` | `StateChangeEvent(new_state, reason)` | `set_current_state()` / `request_reset_transition()` |

---

## STATE_CHANGE Interception & State Machine Integration

The event loop **intercepts `STATE_CHANGE` events before delegating to the mode**:

```python
if event.event_type == EventType.STATE_CHANGE and is_state_change_event(event):
    new_state = event.payload.new_state
    self.set_current_state(new_state)  # Fires on_exit/on_entry hooks
```

This means:
- **Modes never handle `STATE_CHANGE`** — it's a module-level control plane event
- `request_reset_transition()` (called by `UnknownState.on_entry()`) queues `RESET_STATE`
- State transitions are **serialized through the event loop** — no concurrent transitions possible

---

## Lifecycle & Concurrency Guarantees

### Initialization Order (Critical)

```python
def __init__(...):
    # 1. Build state_instances cache FIRST
    self.state_instances = self._create_instances()

    # 2. Create event_queue BEFORE set_current_state()
    self.event_queue = asyncio.Queue()

    # 3. Initialize current_state_instance to None
    self.current_state_instance = None

    # 4. Now safe: UnknownState.on_entry() → request_reset_transition() → put_nowait()
    self.set_current_state(state)
```

### Thread Safety

- **Single event loop per module** — all `put()` calls from scheduler/interrupt bridge are `await module.event_queue.put(...)`
- **GPIO interrupt bridge** uses `call_soon_threadsafe` to cross thread boundary (see `InterruptBridge.trigger_interrupt()`)
- **No locks needed** inside event loop — single-threaded by design

### Exception Handling

- Dispatch exceptions are **logged and swallowed** — loop continues
- `CancelledError` handled per `StopMode` (see diagram)
- Buffer/waiter notification happens **before** dispatch — never lost even if dispatch crashes

---

## Public API Summary

| Method | Purpose |
|--------|---------|
| `start_event_loop()` | Create/background task if not running |
| `stop_event_loop(mode)` | Graceful shutdown with `StopMode` |
| `wait_for_event(type, predicate?, timeout=5.0)` | Race-free wait with buffer replay |
| `drain_events(type)` | Return + clear buffered events |
| `get_event_history(type, limit?)` | Copy of recent events |
| `get_last_event(type)` | Most recent or `None` |
| `get_event_queue_size()` | Pending count |
| `request_reset_transition(reason, source)` | Queue `RESET_STATE` (used by `UnknownState`) |

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| Direct `event_queue.put()` from sync code | Cross-thread `asyncio.Queue` unsafe | Use `InterruptBridge` pattern with `call_soon_threadsafe` |
| `await event_queue.get()` outside event loop | Starves the loop | Use `wait_for_event()` |
| Ignoring `StopMode` in `stop_event_loop()` | Default `DRAIN` may hang on stuck handler | Explicit `CANCEL_ALL` for forced shutdown |
| Subclassing `Rfm9xSx127xMode` handling `STATE_CHANGE` | Never delivered — intercepted | Handle transitions via `on_entry`/`on_exit` |
| Unbounded buffer growth | Memory leak | `deque(maxlen=1000)` is fixed |

---

## Validation Rules

### Semgrep Rules (to be added)

```yaml
# .semgrep/rules/custom/module_event_queue_guard.yaml
rules:
  - id: module-event-queue-direct-put-sync
    pattern: |
      $MODULE.event_queue.put_nowait(...)
    message: "Direct put_nowait from sync context — use InterruptBridge.call_soon_threadsafe"
    severity: ERROR

  - id: module-event-queue-await-get-outside-loop
    pattern: |
      await $MODULE.event_queue.get()
    message: "await get() outside event loop — use wait_for_event()"
    severity: ERROR

  - id: module-event-queue-stop-mode-default
    pattern: |
      await $MODULE.stop_event_loop()
    message: "Implicit StopMode.DRAIN — be explicit about shutdown semantics"
    severity: WARNING
```

### Must-Pass Tests

```bash
# Event loop lifecycle
uv run pytest tests/drivers/test_rfm9x_sx127x_module_event_loop.py -v

# Waiter replay race-free
uv run pytest tests/drivers/test_rfm9x_sx127x_module_waiters.py -v

# Stop modes
uv run pytest tests/drivers/test_rfm9x_sx127x_module_stop_modes.py -v

# Buffer behavior
uv run pytest tests/drivers/test_rfm9x_sx127x_module_buffer.py -v
```

---

## Related Files

- `src/pi_lora/drivers/rfm9x_sx127x_module.py` — Main implementation
- `src/pi_lora/framework/events.py` — Event types, payloads, protocols
- `src/pi_lora/framework/scheduler.py` — Producers: TimerScheduler, IdlePacer, InterruptBridge
- `src/pi_lora/drivers/rfm9x_sx127x_modes.py` — State mode implementations
- `docs/patterns/scheduler_patterns.md` — Producers that feed this queue
- `docs/patterns/application_lifecycle.md` — Application starts/stops module event loops

---

## Anti-Regression Notes

1. **Initialization order is load-bearing** — event_queue before set_current_state (Plan-1 Fix)
2. **Unbounded queue is intentional** — put_nowait in __init__ must not block (Plan-1 Fix)
3. **STATE_CHANGE interception is the ONLY way state changes** — modes cannot self-transition
4. **Waiter replay is race-free by construction** — buffer check and registration are atomic wrt event loop
5. **PAUSE mode keeps queue accepting** — events accumulate, waiters still notify
6. **Buffer maxlen=1000 per type** — bounds memory, old events evicted automatically