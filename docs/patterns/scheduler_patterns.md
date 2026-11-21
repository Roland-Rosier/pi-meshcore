# Scheduler Patterns

## Overview

The `Scheduler` (`src/pi_lora/framework/scheduler.py`) coordinates timer tasks, idle pacing, and interrupt handling for LoRa radio modules. This document captures the hardened patterns that evolved through Plans 4-38.

---

## Core Components

### 1. TimerScheduler — Periodic Tasks with Backoff

```python
class TimerScheduler:
    """Manages periodic timer tasks for registered modules."""
    
    def __init__(self, default_interval: float = 1.0) -> None:
        self._default_interval = default_interval
        self._modules: dict[Rfm9xSx127xModule, float | None] = {}
        self._tasks: dict[Rfm9xSx127xModule, asyncio.Task[None]] = {}
        self._failure_counts: dict[Rfm9xSx127xModule, int] = {}
        self._running = False
        self._lock = asyncio.Lock()
    
    def register_module(self, module: Rfm9xSx127xModule, interval: float | None = None) -> None:
        """Register module with optional custom interval."""
        self._modules[module] = interval
        if self._running:
            self._create_task(module)
    
    def unregister_module(self, module: Rfm9xSx127xModule) -> None:
        """Unregister module and cancel its task."""
        task = self._tasks.pop(module, None)
        if task and not task.done():
            task.cancel()
        self._modules.pop(module, None)
        # CLEANUP FAILURE TRACKING (Plan-14 finding 8.15)
        self._failure_counts.pop(module, None)
    
    async def start(self) -> None:
        """Start all registered module tasks."""
        async with self._lock:
            self._running = True
            for module in self._modules:
                self._create_task(module)
    
    async def stop(self) -> None:
        """Stop all tasks."""
        async with self._lock:
            self._running = False
            for task in self._tasks.values():
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
            self._tasks.clear()
    
    def _create_task(self, module: Rfm9xSx127xModule) -> None:
        """Create timer task for module."""
        interval = self._modules[module] or self._default_interval
        self._tasks[module] = asyncio.create_task(self._timer_task(module, interval))
    
    async def _timer_task(self, module: Rfm9xSx127xModule, interval: float) -> None:
        """Timer task with exponential backoff on failure."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                await module.event_queue.put(ModuleEvent(EventType.TIMER))
                # RESET FAILURE COUNT ON SUCCESS (Plan-11 Phase 7)
                self._failure_counts[module] = 0
            except ExceptionGroup as eg:
                self._handle_failure(module, eg.exceptions)
            except Exception as exc:
                self._handle_failure(module, [exc])
    
    def _handle_failure(self, module: Rfm9xSx127xModule, errors: list[BaseException]) -> None:
        """Handle task failure with exponential backoff."""
        count = self._failure_counts.get(module, 0) + 1
        self._failure_counts[module] = count
        
        # BACKOFF ALWAYS APPLIED (Plan-11 fix 1.5 — not conditional on custom interval)
        backoff_interval = min(2 ** count, 60.0)
        logger.warning(
            "Timer task for module %s failed (count=%d), backing off to %.1fs: %s",
            module, count, backoff_interval, errors
        )
        
        # Reschedule with backoff
        self._tasks[module] = asyncio.create_task(
            self._timer_task(module, backoff_interval)
        )
```

---

### 2. IdlePacer — Rate-Limited Idle Events

```python
class IdlePacer:
    """Sends IDLE events to modules at a configurable minimum interval."""
    
    def __init__(self, min_interval: float = 0.01) -> None:  # 10ms default (Plan-4 Phase 4)
        self._idle_enabled_modules: set[Rfm9xSx127xModule] = set()
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._min_interval = min_interval
    
    def enable_idle(self, module: Rfm9xSx127xModule) -> None:
        self._idle_enabled_modules.add(module)
    
    def disable_idle(self, module: Rfm9xSx127xModule) -> None:
        self._idle_enabled_modules.discard(module)
    
    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._idle_task())
    
    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
    
    async def _idle_task(self) -> None:
        while self._running:
            await asyncio.sleep(self._min_interval)  # Rate-limited, not sleep(0)
            if not self._running:
                break
            # SNAPSHOT AFTER SLEEP (Plan-14 finding 8.16 — documented)
            for module in self._idle_enabled_modules:
                try:
                    await module.event_queue.put(ModuleEvent(EventType.IDLE))
                except Exception:
                    logger.exception("IdlePacer put failed for module")
```

---

### 3. InterruptBridge — GPIO Interrupt Handling

```python
class InterruptBridge:
    """Bridges GPIO interrupts to module event queues."""
    
    def __init__(self) -> None:
        self._interrupt_map: dict[int, Rfm9xSx127xModule] = {}  # gpio_pin -> module
        self._trigger_queue: asyncio.Queue[int] = asyncio.Queue(maxsize=10000)  # Plan-11 fix 1.6
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._drain_task: asyncio.Task[None] | None = None
        self._producer_queue: list[int] = []
        self._trigger_lock = threading.RLock()  # Plan-38 Fix 6
        self._loop: asyncio.AbstractEventLoop | None = None
    
    def register_interrupt(self, gpio_pin: int, module: Rfm9xSx127xModule) -> None:
        """Register GPIO pin to module mapping."""
        self._interrupt_map[gpio_pin] = module
    
    def unregister_interrupt(self, gpio_pin: int) -> None:
        self._interrupt_map.pop(gpio_pin, None)
    
    def trigger_interrupt(self, gpio_pin: int) -> None:
        """Called by GPIO driver when interrupt fires (thread-safe)."""
        with self._trigger_lock:
            if self._running:
                try:
                    self._trigger_queue.put_nowait(gpio_pin)
                except asyncio.QueueFull:
                    # DROP OLDEST — make room for newest (Plan-11 fix 1.6)
                    try:
                        self._trigger_queue.get_nowait()
                        self._trigger_queue.put_nowait(gpio_pin)
                    except asyncio.QueueEmpty:
                        pass
    
    async def start(self) -> None:
        self._running = True
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._interrupt_task())
        self._drain_task = asyncio.create_task(self._drain_sync_queue())
    
    async def stop(self) -> None:
        # Plan-38 Fix 6: ACQUIRE LOCK FIRST to prevent race window
        with self._trigger_lock:
            self._running = False
            self._loop = None
        # Now safe to cancel — no new interrupts can be processed
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self._drain_task and not self._drain_task.done():
            self._drain_task.cancel()
            await asyncio.gather(self._drain_task, return_exceptions=True)
    
    async def _interrupt_task(self) -> None:
        """Process interrupts from trigger_queue."""
        while self._running:
            try:
                gpio_pin = await self._trigger_queue.get()
                if not self._running:
                    break
                module = self._interrupt_map.get(gpio_pin)
                if module:
                    await module.event_queue.put(
                        ModuleEvent(EventType.INTERRUPT, InterruptEvent(gpio_pin))
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("InterruptBridge task error")
    
    async def _drain_sync_queue(self) -> None:
        """Drain thread-safe producer queue (for GPIO driver callback)."""
        while self._running:
            with self._trigger_lock:
                while self._producer_queue:
                    gpio_pin = self._producer_queue.pop(0)
                    try:
                        self._trigger_queue.put_nowait(gpio_pin)
                    except asyncio.QueueFull:
                        pass
            await asyncio.sleep(0.001)  # Plan-14 finding 8.17 — known busy-wait
```

---

## Key Patterns

### Pattern 1: Task Creation Only When Running

```python
def register_module(self, module: Rfm9xSx127xModule, interval: float | None = None) -> None:
    self._modules[module] = interval
    if self._running:  # Only create task if scheduler already started
        self._create_task(module)
```

**Why**: Prevents orphan tasks if module registered before `start()`.

---

### Pattern 2: Failure Count Cleanup on Unregister

```python
def unregister_module(self, module: Rfm9xSx127xModule) -> None:
    task = self._tasks.pop(module, None)
    if task and not task.done():
        task.cancel()
    self._modules.pop(module, None)
    # MEMORY LEAK FIX (Plan-14 finding 8.15)
    self._failure_counts.pop(module, None)
```

**Why**: Without cleanup, `_failure_counts` grows indefinitely with stale module references.

---

### Pattern 3: Backoff Applied Unconditionally

```python
# Plan-11 fix 1.5: Backoff NOT conditional on custom interval
# WRONG: if interval is not None: backoff...
# CORRECT: Always apply backoff
backoff_interval = min(2 ** count, 60.0)
```

**Why**: Default interval failures were silently ignored before fix.

---

### Pattern 4: Bounded Queue with Drop-Oldest

```python
def trigger_interrupt(self, gpio_pin: int) -> None:
    with self._trigger_lock:
        if self._running:
            try:
                self._trigger_queue.put_nowait(gpio_pin)
            except asyncio.QueueFull:
                # Drop oldest to make room for newest (OOM protection)
                try:
                    self._trigger_queue.get_nowait()
                    self._trigger_queue.put_nowait(gpio_pin)
                except asyncio.QueueEmpty:
                    pass
```

**Why**: Unbounded queue → OOM risk from malicious/buggy GPIO driver.

---

### Pattern 5: Lock Ordering for Stop Race (Plan-38 Fix 6)

```python
async def stop(self) -> None:
    # ACQUIRE LOCK FIRST — prevents new interrupts during shutdown
    with self._trigger_lock:
        self._running = False
        self._loop = None
    # Now safe to cancel — no new interrupts can be processed
    if self._task and not self._task.done():
        self._task.cancel()
        await asyncio.gather(self._task, return_exceptions=True)
```

**Why**: Previous code set `_running=False` THEN awaited cancellation THEN acquired lock. During the window, `trigger_interrupt()` could fire and contend.

---

### Pattern 6: Rate-Limited Idle (Not CPU Spin)

```python
# Plan-4 Phase 4 fix: was sleep(0) → 100% CPU
async def _idle_task(self) -> None:
    while self._running:
        await asyncio.sleep(self._min_interval)  # 10ms default
        ...
```

**Why**: `sleep(0)` yields but re-queues instantly → busy spin.

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| `asyncio.sleep(0)` in loop | 100% CPU | Use `min_interval` (default 0.01s) |
| Unbounded `asyncio.Queue()` | OOM risk | `maxsize=10000` + drop-oldest |
| Backoff only for custom intervals | Default interval failures ignored | Always apply backoff |
| `_failure_counts` not cleaned | Memory leak | Pop on `unregister_module()` |
| Stop: set flag → cancel → lock | Race window | Lock FIRST, then flag, then cancel |
| No try/except on `put()` | Task crashes on full queue | Wrap each `put()` in try/except |

---

## Validation Rules

### Semgrep Rules

```yaml
# .semgrep/rules/custom/scheduler_guard.yaml

rules:
  - id: scheduler-sleep-zero
    pattern: await asyncio.sleep(0)
    message: "sleep(0) in loop causes CPU spin — use min_interval (Plan-4 Phase 4)"
    severity: ERROR

  - id: scheduler-unbounded-queue
    pattern: asyncio.Queue()
    message: "Unbounded queue — OOM risk. Use maxsize=10000 (Plan-11 fix 1.6)"
    severity: ERROR

  - id: scheduler-backoff-conditional
    pattern: |
      if interval is not None:
        backoff = ...
    message: "Backoff conditional on interval — apply always (Plan-11 fix 1.5)"
    severity: ERROR

  - id: scheduler-failure-counts-not-cleaned
    pattern: |
      def unregister_module(self, $M):
        ...
        self._modules.pop($M)
    message: "unregister_module missing _failure_counts cleanup — memory leak (Plan-14)"
    severity: ERROR

  - id: interruptbridge-stop-race
    pattern: |
      async def stop(self):
        self._running = False
        ...
        with self._trigger_lock:
    message: "Stop sets _running=False before acquiring lock — race window (Plan-38 Fix 6)"
    severity: ERROR
```

### Must-Pass Tests

```bash
uv run pytest tests/framework/test_scheduler.py -v
uv run pytest tests/framework/test_interrupt_bridge_atomic_drop.py -v
uv run pytest tests/framework/test_interrupt_bridge_threadsafe.py -v
```

---

## Related Files

- `src/pi_lora/framework/scheduler.py` — Main implementation
- `tests/framework/test_scheduler.py` — Unit tests
- `tests/framework/test_interrupt_bridge_atomic_drop.py` — Queue drop tests
- `tests/framework/test_interrupt_bridge_threadsafe.py` — Thread safety tests
- `docs/patterns/exception_handling.md` — Exception patterns used

---

## Anti-Regression Notes

1. **Never revert to `sleep(0)`** — Plan-4 fixed this, re-added in Plan-13, fixed again
2. **Always use bounded queues** — OOM is a security issue
3. **Backoff is unconditional** — Plan-11 proved conditional backoff loses failures
4. **Cleanup tracking dicts** — Memory leaks are hard to detect in tests
5. **Lock ordering in stop()** — Plan-38 proved the race window is real