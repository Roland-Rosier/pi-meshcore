# Semgrep Anti-Regression Rules

## Overview

This document captures the Semgrep rules established during the hardening spike (Plans 4-38) to automatically detect and prevent regression of known bug patterns. Rules are stored in `.semgrep/rules/custom/`.

---

## Rule Categories

### 1. Concurrency & Locking Rules

#### `lazy-async-lock-guard.yaml`

```yaml
# .semgrep/rules/custom/lazy-async-lock-guard.yaml

rules:
  # 1. Detect old sentinel pattern (Plan-28 systemic fix)
  - id: sentinel-pattern-deprecated
    pattern-either:
      - pattern: _SENTINEL = object()
      - pattern: $LOCK = _SENTINEL
    message: "Sentinel pattern deprecated — use LazyAsyncLock instead"
    severity: ERROR

  # 2. Detect holder persistence bug (new asyncio.Lock() each call)
  - id: holder-not-persisted
    pattern: |
      with $GUARD:
          $HOLDER: asyncio.Lock = asyncio.Lock()
    message: "New holder created each call — LazyAsyncLock persists holder"
    severity: ERROR

  # 3. Detect double-checked locking without holder protecting else-branch
  - id: else-branch-unprotected
    pattern-either:
      - pattern: |
          if $LOCK is None:
            async with $HOLDER:
              if $LOCK is None:
                $LOCK = $Y.Lock()
            else:
              async with $LOCK:
                $BODY: ...
      - pattern: |
          if $LOCK is None:
            with $GUARD:
              $LOCK = $Y.Lock()
            else:
              async with $LOCK:
                $BODY: ...
    message: "Else branch outside holder — sentinel race risk. Use LazyAsyncLock."
    severity: ERROR

  # 4. Detect manual double-checked locking (should use LazyAsyncLock)
  - id: manual-double-checked-locking
    pattern-either:
      - pattern: |
          if $LOCK is None:
            async with $HOLDER:
              if $LOCK is None:
                $LOCK = $Y.Lock()
      - pattern: |
          with $INIT_LOCK:
            $HOLDER = asyncio.Lock()
          async with $HOLDER:
            if $LOCK is None:
              $LOCK = $Y.Lock()
    message: "Manual double-checked locking — use LazyAsyncLock instead"
    severity: ERROR
```

### 2. Exception Handling Rules

```yaml
# .semgrep/rules/custom/exception_handling_guard.yaml

rules:
  # 1. CancelledError swallowed
  - id: cancellederror-swallowed
    pattern: |
      except (Exception, asyncio.CancelledError) as $E:
        ...
    message: "CancelledError swallowed — split into separate handlers (re-raise CancelledError)"
    severity: ERROR

  # 2. BaseException handler without identity check before chaining
  - id: baseexception-no-identity-check
    pattern: |
      except BaseException as $CLEANUP:
        raise $ORIGINAL from $CLEANUP
    message: "Missing identity check before exception chaining — prevents self-referential __cause__ cycle"
    severity: ERROR

  # 3. ExceptionGroup caught after Exception (will never match)
  - id: exceptiongroup-after-exception
    pattern: |
      except Exception as $E:
        ...
      except ExceptionGroup as $EG:
        ...
    message: "ExceptionGroup caught after Exception — will never match. Move ExceptionGroup first."
    severity: ERROR

  # 4. contextlib.suppress(Exception) for resource cleanup
  - id: suppress-exception-cleanup
    pattern: |
      with contextlib.suppress(Exception):
        $RESOURCE.close()
    message: "contextlib.suppress(Exception) swallows real errors — use explicit try/except with logging"
    severity: ERROR
```

### 3. Application Lifecycle Rules

```yaml
# .semgrep/rules/custom/application_lifecycle_guard.yaml

rules:
  # 1. Fast-path read of _started outside lock (Plan-38 Fix 2)
  - id: application-fast-path-read
    pattern: |
      $VAR = self._started
      if $VAR:
        return
      async with self._lifecycle_lock:
    message: "Fast-path read of _started outside lock — removed in Plan-38 (False→True→False race)"
    severity: ERROR

  # 2. Errors list created outside lifecycle_lock (Plan-11 fix 3.5)
  - id: application-errors-outside-lock
    pattern: |
      errors = []
      async with self._lifecycle_lock:
    message: "Errors list created outside lifecycle_lock — race on concurrent stop()"
    severity: ERROR

  # 3. Missing lifecycle_lock in cleanup
  - id: application-cleanup-no-lock
    pattern: |
      async def _cleanup_partial_start(self) -> None:
        ...
        for module in ...:
          await self.scheduler.unregister_module(module)
    message: "_cleanup_partial_start missing lifecycle_lock — race with concurrent stop()"
    severity: ERROR
```

### 4. Module Manager Rules

```yaml
# .semgrep/rules/custom/module_manager_guard.yaml

rules:
  # 1. Direct append before scheduler registration (Plan-38 Fix 5)
  - id: modulemanager-direct-append
    pattern: |
      self.modules.append($MODULE)
      await self.scheduler.register_module($MODULE)
    message: "Direct append before scheduler registration — use pending lists (Plan-38 Fix 5)"
    severity: ERROR

  # 2. Rollback without asyncio.shield()
  - id: modulemanager-no-shield-rollback
    pattern: |
      for $M in $PENDING:
        await self.scheduler.unregister_module($M)
    message: "Rollback without asyncio.shield() — cancellation can leak resources"
    severity: ERROR

  # 3. Single except BaseException (doesn't distinguish shutdown signals)
  - id: modulemanager-single-except-baseexception
    pattern: |
      except BaseException:
        ...
        raise
    message: "Catches BaseException but doesn't distinguish shutdown signals — use two handlers"
    severity: ERROR
```

### 5. SPI Lock Rules

```yaml
# .semgrep/rules/custom/spi_lock_guard.yaml

rules:
  # 1. Sync context manager usage on SPI lock
  - id: spi-lock-sync-context-manager
    pattern: |
      with $LOCK:
        ...
    message: "SPI lock used as sync context manager — must use `async with await get_bus_lock()` first"
    severity: ERROR

  # 2. Direct _bus_locks access without registry lock
  - id: spi-lock-direct-bus-locks
    pattern: |
      _bus_locks[$BUS] = ...
    message: "Direct _bus_locks mutation — must go through get_bus_lock() registry"
    severity: ERROR
```

---

## Rule Testing

### Test File Pattern

Each rule should have test cases in the same directory:

```python
# .semgrep/rules/custom/test_lazy_async_lock_guard.py
# Test cases for lazy-async-lock-guard.yaml

# ruleid: sentinel-pattern-deprecated
_SENTINEL = object()

# ruleid: sentinel-pattern-deprecated
_lock = _SENTINEL

# ok: lazy-async-lock-guard
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
_lock = LazyAsyncLock()

# ruleid: holder-not-persisted
with guard:
    holder: asyncio.Lock = asyncio.Lock()

# ok: holder-not-persisted
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
lock = LazyAsyncLock()
await lock.acquire()

# ruleid: manual-double-checked-locking
if lock is None:
    async with holder:
        if lock is None:
            lock = aiologic.Lock()

# ok: manual-double-checked-locking
from pi_lora.framework.lazy_async_lock import LazyAsyncLock
lock = LazyAsyncLock()
await lock.acquire()
```

### Running Rule Tests

```bash
# Test specific rule file
uv run semgrep test .semgrep/rules/custom/lazy-async-lock-guard.yaml

# Test all custom rules
uv run semgrep test .semgrep/rules/custom/
```

---

## Integration in CI/CD

### `.semgrep/run.sh`

```bash
#!/usr/bin/env bash
# Semgrep security scan runner

set -euo pipefail

mkdir -p /tmp/sandbox/semgrep_tmp
TMPDIR=$(mktemp -d -p /tmp/sandbox/semgrep_tmp)
export TMPDIR

trap 'rm -rf "$TMPDIR"' EXIT INT TERM

uv run semgrep scan --verbose \
    --config=.semgrep/rules/security/ \
    --config=.semgrep/rules/best-practice/ \
    --config=.semgrep/rules/correctness/ \
    --config=.semgrep/rules/maintainability/ \
    --config=.semgrep/rules/custom/ \
    src/pi_lora/ \
    tests/
```

### Pre-commit Hook (Optional)

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: semgrep-custom
        name: Semgrep Custom Rules
        entry: uv run semgrep scan --config=.semgrep/rules/custom/ src/ tests/
        language: system
        types: [python]
        pass_filenames: false
```

---

## Rule Development Workflow

### 1. Identify Bug Pattern

When a bug is found and fixed:
1. Extract the minimal code pattern that caused the bug
2. Write a Semgrep rule to detect it
3. Add test cases (both `ruleid:` and `ok:` annotations)
4. Run `uv run semgrep test` to verify

### 2. Rule Design Principles

| Principle | Application |
|-----------|-------------|
| **Minimal pattern** | Match the bug essence, not surrounding code |
| **No false positives** | Use `pattern-not-inside` for valid similar patterns |
| **Clear message** | Explain WHY it's banned and WHAT to use instead |
| **Severity ERROR** | Block merge on detection |

### 3. Example: Creating a New Rule

```yaml
# Bug: for loop over dict while mutating it
# Fix: iterate over list(dict.keys()) or use dict.items() copy

- id: dict-mutation-during-iteration
  pattern: |
    for $K in $D:
      ...
      del $D[$K]
  message: "Mutating dict during iteration — iterate over list(dict.keys()) instead"
  severity: ERROR
```

---

## Current Rule Inventory

| Rule File | Rules | Purpose |
|-----------|-------|---------|
| `lazy-async-lock-guard.yaml` | 4 | Prevent old lock patterns |
| `exception_handling_guard.yaml` | 4 | Prevent exception bugs |
| `application_lifecycle_guard.yaml` | 3 | Prevent lifecycle races |
| `module_manager_guard.yaml` | 3 | Prevent rollback bugs |
| `spi_lock_guard.yaml` | 2 | Prevent SPI lock misuse |
| **Total** | **16** | |

---

## Validation Gates

```bash
# Full validation (must pass 0 findings)
uv run .semgrep/run.sh

# Quick custom rules only
uv run semgrep scan --config=.semgrep/rules/custom/ src/ tests/
```

### Expected Output

```
ran 16 rules on 123 files: 0 findings
```

---

## Adding Rules to Prevent Future Regressions

### When to Add a Rule

1. **After fixing a bug** that could reoccur
2. **When a pattern is deprecated** (e.g., sentinel pattern)
3. **When a subtle race condition** is discovered
4. **When exception handling** has specific ordering requirements

### Rule Template

```yaml
- id: descriptive-name
  pattern: |
    # Minimal code pattern that causes the bug
    ...
  message: "Human-readable explanation of why this is banned and what to use instead"
  severity: ERROR
```

### Testing New Rules

```bash
# 1. Test against known bad code (should flag)
uv run semgrep scan --config=.semgrep/rules/custom/new-rule.yaml tests/bad_examples/

# 2. Test against good code (should NOT flag)
uv run semgrep scan --config=.semgrep/rules/custom/new-rule.yaml src/

# 3. Run full test suite
uv run semgrep test .semgrep/rules/custom/
```

---

## Anti-Regression Notes

1. **Rules are NOT optional** — they run in CI and block on ERROR severity
2. **Test cases required** — every rule must have `ruleid:` and `ok:` examples
3. **Update on every bug fix** — if a bug is fixed, add a rule to prevent regression
4. **Review false positives** — if a rule flags valid code, refine the pattern, don't disable
5. **Document in plan** — each plan should reference the rules it adds/updates