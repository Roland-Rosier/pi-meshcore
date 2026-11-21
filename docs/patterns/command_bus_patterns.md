# Command Bus Patterns

## Overview

The `CommandBus` (`src/pi_lora/framework/command_bus.py`) dispatches commands to registered handlers with priority-based ordering. This document captures the hardened patterns that evolved through Plans 4-38.

---

## Core Implementation

```python
# src/pi_lora/framework/command_bus.py

from typing import Protocol, TypeVar, Generic
import logging
import asyncio

logger = logging.getLogger(__name__)

T = TypeVar("T")

class CommandHandler(Protocol[T]):
    async def handle(self, command: T) -> None: ...


class CommandBus:
    """
    Async command bus with priority-based handler dispatch.
    
    SAFETY GUARANTEES (Plans 4, 16, 25, 34, 37):
    - ExceptionGroup handling in dispatch()
    - Module resolver None checks
    - Proper exception hierarchy
    - Module-level logger (not inline)
    """
    
    def __init__(self) -> None:
        self._handlers: dict[type, list[tuple[int, CommandHandler]]] = {}
        self._module_resolver: Callable[[type], Rfm9xSx127xModule | None] | None = None
    
    def register_handler(
        self,
        command_type: type[T],
        handler: CommandHandler[T],
        priority: int = 0,
    ) -> None:
        """Register handler for command type with priority (higher = first)."""
        if command_type not in self._handlers:
            self._handlers[command_type] = []
        self._handlers[command_type].append((priority, handler))
        # Sort by priority DESC (higher priority first)
        self._handlers[command_type].sort(key=lambda x: x[0], reverse=True)
    
    def set_module_resolver(
        self,
        resolver: Callable[[type], Rfm9xSx127xModule | None],
    ) -> None:
        self._module_resolver = resolver
    
    async def dispatch(self, command: object) -> None:
        """
        Dispatch command to registered handlers.
        
        SAFETY: ExceptionGroup handling (Plan-25, Plan-34, Plan-37)
        """
        command_type = type(command)
        handlers = self._handlers.get(command_type, [])
        
        if not handlers:
            logger.debug("No handlers for command type: %s", command_type)
            return
        
        errors: list[BaseException] = []
        
        for priority, handler in handlers:
            try:
                await handler.handle(command)
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception(
                    "Handler %s for command %s failed",
                    handler, command_type
                )
                errors.append(exc)
        
        if errors:
            raise ExceptionGroup(
                f"Command {command_type.__name__} dispatch failed",
                errors
            )
    
    async def execute(self, command: object) -> None:
        """
        Execute command via module resolver + dispatch.
        
        Plan-16 Fix: Module resolver can return None — check before dispatch.
        Plan-34 Fix: Exception hierarchy preserved.
        """
        if self._module_resolver is None:
            raise RuntimeError("Module resolver not set")
        
        module = self._module_resolver(type(command))
        if module is None:
            raise RuntimeError(f"No module registered for command {type(command)}")
        
        await self.dispatch(command)
```

---

## Key Patterns

### Pattern 1: ExceptionGroup Aggregation

```python
errors: list[BaseException] = []

for priority, handler in handlers:
    try:
        await handler.handle(command)
    except ExceptionGroup as eg:
        errors.extend(eg.exceptions)
    except Exception as exc:
        logger.exception("Handler failed")
        errors.append(exc)

if errors:
    raise ExceptionGroup(f"Command {command_type.__name__} dispatch failed", errors)
```

**Why**: 
- Multiple handlers can fail — don't stop at first error
- `ExceptionGroup` preserves all failures
- `ExceptionGroup` caught before `Exception` in callers

---

### Pattern 2: Module Resolver None Check

```python
async def execute(self, command: object) -> None:
    if self._module_resolver is None:
        raise RuntimeError("Module resolver not set")
    
    module = self._module_resolver(type(command))
    if module is None:
        raise RuntimeError(f"No module registered for command {type(command)}")
    
    await self.dispatch(command)
```

**Why**: 
- Resolver returns `Module | None` — must check
- Plan-16 fixed: `dispatch()` called with `None` module
- Clear error message for debugging

---

### Pattern 3: Priority-Based Handler Ordering

```python
def register_handler(self, command_type, handler, priority=0):
    self._handlers[command_type].append((priority, handler))
    # Sort DESC — higher priority first
    self._handlers[command_type].sort(key=lambda x: x[0], reverse=True)
```

**Why**: 
- Higher priority handlers execute first
- Allows override behavior (e.g., test handler > production handler)

---

### Pattern 4: Module-Level Logger

```python
# At module level
logger = logging.getLogger(__name__)

# In methods
logger.exception("Handler %s for command %s failed", handler, command_type)
```

**Why**: 
- Single logger instance, not created on every call
- Plan-14 finding 8.14 fixed inline logger creation

---

### Pattern 5: MRO-Based Depth Calculation (Future)

```python
# Current (buggy for diamond inheritance):
depth = command_depth - len(registered_type.__mro__)

# Fixed (Plan-4 finding 4.12):
depth = command_mro.index(registered_type)
```

---

## Handler Implementation Pattern

```python
# In module or command handler
class MyCommandHandler:
    async def handle(self, command: MyCommand) -> None:
        # Access module via dependency injection or context
        module = get_current_module()
        await module.do_something(command.param)
```

---

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Fix |
|--------------|---------|-----|
| `except Exception:` without `ExceptionGroup` first | Loses grouped errors | Catch `ExceptionGroup` first |
| No None check on resolver | `dispatch(None)` crashes | Check `if module is None` |
| Inline `logging.getLogger(__name__)` | New logger each call | Module-level logger |
| `type(command)` for lookup | Subclasses don't match | Use MRO walk (future) |
| Silent handler rejection | Debugging impossible | Log rejection with context |

---

## Validation Rules

### Semgrep Rules

```yaml
# .semgrep/rules/custom/command_bus_guard.yaml

rules:
  - id: commandbus-exceptiongroup-order
    pattern: |
      except Exception as $E:
        ...
      except ExceptionGroup as $EG:
        ...
    message: "ExceptionGroup caught after Exception — will never match. Move ExceptionGroup first."
    severity: ERROR

  - id: commandbus-no-resolver-check
    pattern: |
      async def execute(self, $CMD):
        $MODULE = self._module_resolver(...)
        await self.dispatch($CMD)
    message: "Module resolver result not checked for None — Plan-16 fix"
    severity: ERROR

  - id: commandbus-inline-logger
    pattern: |
      logging.getLogger(__name__).exception(...)
    message: "Inline logger creation — use module-level logger (Plan-14)"
    severity: ERROR
```

### Must-Pass Tests

```bash
uv run pytest tests/framework/test_command_bus.py -v
```

---

## Related Files

- `src/pi_lora/framework/command_bus.py` — Main implementation
- `tests/framework/test_command_bus.py` — Unit tests
- `docs/patterns/exception_handling.md` — ExceptionGroup patterns
- `docs/patterns/application_lifecycle.md` — Application uses CommandBus

---

## Anti-Regression Notes

1. **ExceptionGroup always first** in except clauses — mypy enforces but semgrep catches
2. **Resolver None check mandatory** — Plan-16 proved it's a real bug
3. **Module-level logger** — Not optional, enforced by semgrep
4. **Priority sort on every registration** — Ensures correct order
5. **Clear error messages** — Include command type for debugging