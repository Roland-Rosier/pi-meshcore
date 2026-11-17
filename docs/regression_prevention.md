# Regression Prevention Guide for Plan Writers, Reviewers, and Implementers

**Purpose**: This document provides specific, actionable guidance to reduce or eliminate regressions introduced during the planning, review, and implementation phases. It is based on concrete failures observed in the Plan-37 cycle where 8 CRITICAL/HIGH regressions were introduced despite explicit "no regression" instructions.

---

## For Plan Writers

### 1. Specify Exact Code Patterns, Not Conceptual Fixes

**Problem**: Plan-37 Fix 2.4 said "best effort cleanup" — implementer used `contextlib.suppress(Exception)` wrapping entire loop instead of per-module try/except.

**Rule**: Always provide **exact pseudocode** showing:
- Loop structure (per-item try/except vs. wrapper)
- Resource reference clearing (`resource = None`)
- Logging but not raising in cleanup

```markdown
### Fix 2.4: Context Manager for LoRaModuleDetector

**Exact pattern required**:
```python
def __exit__(self, exc_type, exc_val, exc_tb) -> None:
    for module in self.modules:
        try:
            if hasattr(module.spi_device, 'close'):
                module.spi_device.close()
            module.spi_device = None  # Prevent double-close in __del__
        except Exception as e:
            logger.warning("Failed to close SPI device for CE %s: %s", module.ce_pin, e)
```
**Anti-patterns FORBIDDEN**:
- `with contextlib.suppress(Exception):` wrapping the loop
- Missing `module.spi_device = None` after close
```

### 2. Specify Identity Checks for Exception Chaining

**Problem**: Plan-37 Fix 2.1/2.2 specified `raise original_exc from cleanup_exc` without identity check, causing self-referential `__cause__` cycles.

**Rule**: For ANY exception chaining with `from`, mandate identity check:

```markdown
### Fix 2.1/2.2: Exception Chaining

**Required pattern**:
```python
except BaseException as cleanup_exc:
    if original_exc is not None and isinstance(original_exc, SHUTDOWN_SIGNALS):
        # CRITICAL: Check identity to avoid self-referential __cause__ cycle
        if cleanup_exc is original_exc:
            raise  # Avoid exc.__cause__ = exc cycle
        raise original_exc from cleanup_exc
    raise
```
```

### 3. Explicitly Address `__del__` Interaction

**Problem**: Plan-37 added context manager to class with existing `__del__` cleanup — created double-close risk.

**Rule**: If class has `__del__` doing cleanup, context manager `__exit__` MUST clear resource reference:

```markdown
### Interaction with Existing `__del__`

**Check**: Does the class or its members have `__del__` doing cleanup?
- YES → `__exit__` MUST set `resource = None` after close
- NO → Standard cleanup pattern applies
```

### 4. Specify Lock Acquisition Order for Shared Locks

**Problem**: Plan-37 Fix 2.3 documented trade-off but didn't fix race window in `InterruptBridge.stop()`.

**Rule**: For locks shared with sync-thread callbacks, specify EXACT acquisition order:

```markdown
### Fix 2.3: InterruptBridge.stop() Lock Order

**Required pattern**:
```python
async def stop(self) -> None:
    with self._trigger_lock:  # Acquire FIRST — blocks new callbacks
        self._running = False
        self._loop = None
    await asyncio.gather(self._task.cancel(), ...)  # THEN await
```
**Anti-pattern**: Setting `_running=False` before lock acquisition.
```

### 5. Specify Protocol Parameter Requirements for Mocks

**Problem**: Plan-36 updated `SpiBusFactory` protocol but Plan-37 didn't require mock updates.

**Rule**: Every protocol change MUST list all implementations (production + test) that need updating:

```markdown
### Protocol Change Checklist

When modifying Protocol X:
1. Update protocol definition
2. Production implementations to update: [list]
3. Test implementations to update: [MockX, FakeX, ...]
4. Contract test parametrization to include: [list]
```

---

## For Plan Reviewers

### 1. Diff Implementation Against Plan Pseudocode

**Problem**: Plan reviewer validated the *plan's logic* but not the *implementation's fidelity*.

**Rule**: During implementation review, **diff each changed file against the plan's pseudocode**:

```bash
# For each fix in the plan:
# 1. Extract plan's pseudocode
# 2. Compare with actual implementation
# 3. Flag any deviations
```

**Checklist per fix**:
- [ ] Loop structure matches (per-item try/except vs wrapper)
- [ ] Resource clearing present (`resource = None`)
- [ ] Identity check in exception chaining
- [ ] Lock acquisition order correct
- [ ] All protocol params accepted in mocks
- [ ] No `contextlib.suppress` wrapping loops in cleanup

### 2. Verify "No Regression" Claims with Concrete Analysis

**Problem**: Plan-37 reviewer said "No Regression Risk" for Fix 2.1/2.2 without checking identity edge case.

**Rule**: For ANY claim of "no regression risk", require the reviewer to:
- Identify the specific exception types being caught/raised
- Consider concurrent signal delivery during exception handling
- Check if `cleanup_exc` can be same object as `original_exc`
- Verify `__cause__` chain won't create cycles

**Red flag phrases** that require deeper analysis:
- "harmless" / "benign" — **must prove** why stale read is safe
- "dead code" — **must prove** branch is truly unreachable
- "no regression risk" — **must analyze** edge cases

### 3. Verify Dead Code Flags and `__del__` Interactions

**Problem**: Plan reviewer missed dead `_entered` flag and double-close with `__del__`.

**Rule**: For any new context manager:
- [ ] Check if class has `__del__` doing cleanup
- [ ] Check for unused flags/attributes (`_entered`, etc.)
- [ ] Verify resource reference cleared after close

### 4. Validate Lock Ordering with Thread Model

**Problem**: Reviewer accepted "trade-off" documentation without fixing race window.

**Rule**: For locks shared with sync threads:
- Draw the thread interaction diagram
- Identify window between flag change and lock acquisition
- Require lock FIRST pattern unless proven impossible

---

## For Implementation Reviewers (Code Reviewers)

### 1. Enforce Exact Pattern Compliance

**Problem**: Implementer deviated from plan's "per-module try/except" to `contextlib.suppress`.

**Rule**: Reject any implementation that:
- Wraps cleanup loop in `contextlib.suppress` or bare `except:`
- Omits resource reference clearing when `__del__` exists
- Omits identity check in exception chaining
- Accepts protocol params in production but not mocks

### 2. Check Test Infrastructure LSP Compliance

**Problem**: `MockSpiBusFactory.create()` missing `xfer_timeout`/`factory_owned` params.

**Rule**: When protocol changes:
- Verify ALL mock/fake implementations accept new params
- Verify contract tests parametrize mock implementations
- Run `uv run pytest tests/contracts/` with mocks included

### 3. Verify Exception Handler Ordering

**Problem**: Missing `except ExceptionGroup` before `except Exception`.

**Rule**: For any cleanup handler that can receive `ExceptionGroup`:
- [ ] `except ExceptionGroup` BEFORE `except Exception`
- [ ] `except BaseException` (shutdown signals) LAST
- [ ] Identity check in `BaseException` handler

### 4. Check for Double-Checked Locking on State Flags

**Problem**: Double-checked locking on `_started` flag (False→True→False).

**Rule**: Flag any `if self._flag:` fast-path read OUTSIDE lock for flags that can transition back to `False`. Require always-acquire-lock pattern.

---

## Cross-Cutting Rules

### 1. Regression Test Requirements

For every fix addressing a regression class:
- Add a test that would have caught the regression
- Document the test in the plan's validation gates

Example: Plan-37 should have required test for concurrent `KeyboardInterrupt` during cleanup.

### 2. Documentation Updates Required

Every plan that introduces/changes patterns must update `docs/`:
- `exception_handling.md` — new anti-patterns
- `concurrency_patterns.md` — new anti-patterns
- `protocol_contracts.md` — new LSP requirements

### 3. Sign-Off Gates

No plan approved without:
- [ ] Plan writer provided exact pseudocode for all behavioral changes
- [ ] Plan reviewer verified implementation fidelity (diff check)
- [ ] Plan reviewer analyzed edge cases for "no regression" claims
- [ ] Implementation reviewer enforced exact pattern compliance
- [ ] Test infrastructure LSP compliance verified
- [ ] `docs/` updated with new anti-patterns

---

## Quick Reference: Plan-37 Regression Root Causes

| Regression | Root Cause | Prevention |
|------------|------------|------------|
| `contextlib.suppress` wrapping loop | Plan said "best effort cleanup" — too vague | Require exact per-item try/except pattern |
| Self-referential `__cause__` cycle | No identity check in exception chaining | Mandate `if cleanup_exc is original_exc: raise` |
| Dead `_entered` flag | No dead code check in review | Flag unused attributes in review |
| Double-close with `__del__` | No `__del__` interaction analysis | Require `resource = None` after close in `__exit__` |
| `InterruptBridge` race window | Lock acquired AFTER flag change | Require lock FIRST pattern for shared locks |
| Mock missing protocol params | Protocol change didn't list mocks | Protocol change checklist must include test impls |
| Missing `except ExceptionGroup` | Handler order not validated | Require explicit handler ordering rules |
| DCL on `_started` flag | "Harmless" claim accepted without proof | Require proof for stale-read safety on cyclic flags |

---

## Enforcement Checklist for Each Role

### Plan Writer
- [ ] Exact pseudocode for all behavioral changes
- [ ] Identity checks in exception chaining
- [ ] `__del__` interaction analysis
- [ ] Lock acquisition order for shared locks
- [ ] Protocol change checklist with test impls
- [ ] `docs/` updates planned

### Plan Reviewer
- [ ] Diff plan pseudocode vs implementation intent
- [ ] Analyze edge cases for "no regression" claims
- [ ] Verify `__del__` interaction
- [ ] Validate lock ordering with thread model
- [ ] Check dead code flags

### Implementation Reviewer
- [ ] Enforce exact pattern compliance (no `contextlib.suppress` in cleanup)
- [ ] Verify test infrastructure LSP compliance
- [ ] Check exception handler ordering
- [ ] Flag DCL on cyclic state flags
- [ ] Run contract tests with mocks

---

**Document Version**: 1.0  
**Based on**: Plan-37 regression analysis (code_review-37.2.json)  
**Status**: Active — apply to all future plans