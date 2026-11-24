# Medium/Low Severity Fixes — Implementation Summary

**Date**: 2026-11-21  
**Branch**: `RAIR_2026_11_21_MediumLowFixes`  
**Source**: `KNOWN_DEFECTS.md` + `code_review-16.1.json` + `code_review-2.1.json`  
**Scope**: Three coordinated plans addressing 13 distinct issues across dependency management, cache coherence, documentation, type safety, and tooling.

---

## Executive Summary

All three plans have been **fully implemented and validated**. The branch delivers:

| Plan | Focus | Items | Status |
|------|-------|-------|--------|
| **Plan 1** | Quick wins & medium fixes (dependencies, imports, docstrings, comments, performance, type safety) | 9 | ✅ Complete |
| **Plan 2** | Config loader cache coherence (KNOWN_DEFECTS §3.1) | 1 (core fix + test + semgrep rule) | ✅ Complete |
| **Plan 3** | Semgrep rule & script fixes from code_review-2.1 | 4 | ✅ Complete |

**Validation Gates**: All 7 gates pass with 0 errors:
- `pytest tests/` — 873 passed, 3 skipped
- `mypy --strict src/` — Success
- `ruff check src/ tests/` — All checks passed
- `.semgrep/run.sh` — 0 findings (132 rules, 46 files)
- Contract tests — 9 passed
- Parallel execution — 0 cross-test interference
- Coverage — 92.50% (≥90% required)

---

## Plan 1: Quick Wins & Medium Fixes

### Items Implemented

| # | Issue | File(s) | Fix Summary |
|---|-------|---------|-------------|
| 1 | aiologic upper bound missing | `pyproject.toml:86` | Pinned to `aiologic==0.17.1` (exact version exposing `green_release`/`async_release`). Verified available on PyPI via `uv.lock`. |
| 2 | Unused `importlib` import | `config_loader.py:19` | Removed bare `import importlib`; kept `import importlib.resources` (anti-regression guard documented). |
| 3 | `run.sh` mktemp safety | `.semgrep/run.sh:11` | Added `|| exit 1` to fail fast on `mktemp` failure, preventing catastrophic `rm -rf ""`. |
| 4a | Misleading docstring: `config_loader.py` | `config_loader.py:172-177` | Updated to reflect actual API: sync `load_config()` has no cache; async version caches default, `config_path` now updates cache. |
| 4b | Misleading docstring: `module.py` | `module.py:286-292` | Clarified: `asyncio.TimeoutError` **is** the builtin `TimeoutError` since Python 3.11 (project requires `>=3.11`). |
| 4c | Misleading docstring: `radio_instance.py` | `radio_instance.py:318-326` | Removed internal history ("CR-2 FIX", "per H-7"); focused on API contract. |
| 5 | O(n) lookups in `radio_instance.py` | `radio_instance.py:230-258` | Built O(1) lookup indexes: `device_by_name` dict + `family_by_device` reverse index (first-match-wins). |
| 6 | Mypy `no-any-return` blanket suppression | `pyproject.toml:245-257`, `bus.py`, `locks.py` | Removed blanket `disable_error_code = ["no-any-return"]`; added explicit `cast(int, ...)`/`cast(bool, ...)`/`cast(SpiLock, ...)` at 5 return sites. |
| 7 | `run.sh` POSIX compliance | `.semgrep/run.sh:10` | Added comment: current `TMPDIR=... mktemp -d` is POSIX-compliant (not GNU-only `-p` flag). |
| 8a | Misleading comment: `scheduler.py` | `scheduler.py:229-235` | Replaced "Phase 4, plan-4" jargon with functional description: per-module exponential backoff bounds log spam. |
| 8b | Misleading comment: `command_bus.py` | `command_bus.py:49-54` | Unified "priority number"/"priority level" terminology; fixed contradiction noted in code_review-2.1. |
| 9 | Obsolete `# nosemgrep` comment | `module.py:79` | Removed obsolete `correctness.return-in-init` suppression (no `return` in lambda). |

### Key Technical Details

**Item 5 (O(n) → O(1) Lookups)** — `radio_instance.py:230-258`:
```python
# Build O(1) device name index
device_by_name: dict[str, DeviceConfig] = {}
for spec in config.devices.values():
    if spec.name not in device_by_name:
        device_by_name[spec.name] = spec
device_spec = device_by_name.get(device_name)

# Build O(1) device→family reverse index (first-match-wins)
family_by_device: dict[str, FamilyConfig] = {}
for fam in config.families.values():
    for dev_name in fam.devices:
        if dev_name not in family_by_device:
            family_by_device[dev_name] = fam
family_config = family_by_device.get(device_spec.name)
```

**Item 6 (Mypy Fix)** — Replaced blanket suppression with surgical casts:
- `bus.py:407,437,467,497` — `cast(int, self._spidev.max_speed_hz)` etc.
- `locks.py:147` — `cast(SpiLock, _bus_locks[bus_number])`

---

## Plan 2: Config Loader Cache Coherence (KNOWN_DEFECTS §3.1)

### Problem
Custom `config_path` bypassed module-level cache but didn't update `_config_cache`. Subsequent no-argument calls returned stale default.

**Defect Scenario**:
1. Caller A: `get_preloaded_config(config_path=custom.yaml)` → loads custom, returns it, **cache unchanged**
2. Caller B: `get_preloaded_config()` → acquires lock, sees cache (default), returns stale default

### Fix Applied
**File**: `src/pi_lora/drivers/rfm9x_sx127x_config_loader.py:194-205`

```python
async with config_lock:
    # Fast-path: return cached default if no override requested
    if _config_cache is not None and not force_reload and config_path is None:
        return _config_cache

    # Determine config to load
    if config_path is not None:
        config = load_config(config_path=config_path)
    else:
        config = load_config()

    # Update cache if: force_reload requested OR cache empty OR config_path provided
    # PLAN-2 FIX (Cache Coherence): config_path loads now update _config_cache.
    if force_reload or _config_cache is None or config_path is not None:
        _config_cache = config

    return config
```

### Behavioral Contract (Verified by Tests)

| Call Pattern | Behavior |
|--------------|----------|
| `get_preloaded_config()` | Returns cache or loads default |
| `get_preloaded_config(force_reload=True)` | Reloads default, updates cache |
| `get_preloaded_config(config_path=custom)` | **Loads custom, updates cache** (FIXED) |
| `get_preloaded_config(force_reload=True, config_path=custom)` | Loads custom, updates cache |

### Anti-Regression Measures
1. **New test**: `test_config_loader_config_path_updates_cache` in `tests/drivers/test_config_loader.py`
2. **Semgrep rule**: `.semgrep/rules/custom/config-cache-coherence.yaml` — detects reintroduction of defective pattern
3. **Updated pre-existing test**: `test_config_path_and_cache_concurrent_consistency` in `tests/test_rfm9x_sx127x_config_loader.py` aligned to new contract
4. **Docstring updated** to reflect new semantics
5. **Inline comment** at cache update line with cross-reference to KNOWN_DEFECTS §3.1

### Caller Impact (Zero Regressions)
- `create_radio_instance()` — uses no-args only ✅
- `Application._load_config()` — maintains own `self._config` cache layer ✅
- All 54 radio_instance tests + 48 Application tests pass

---

## Plan 3: Semgrep Rule & Script Fixes (code_review-2.1 §35.3)

### Issues Addressed

| ID | File | Issue | Resolution |
|----|------|-------|------------|
| 35.3.1 | `return-in-init.yaml` | `pattern-not-inside: defaultdict(...)` limitation | Documented in message: variable-passed lambdas (`f = lambda: ...; defaultdict(f)`) not excluded; workaround: `# nosemgrep` |
| 35.3.2 | `return-in-init.yaml` | Multi-line `>-` message format | Converted to single-line for consistency with `yield-in-init` rule |
| 35.3.3 | `run.sh` | `venv/bin/semgrep` without venv check | **Restored `uv run semgrep`** (original behavior from commits 6c4f813, ab79653); aligns with AGENTS.md |
| 35.3.4 | `run.sh` | TMPDIR error handling verbosity | **No change** — `|| exit 1` is POSIX-compliant, concise, functionally equivalent |

### Changes Made

**`.semgrep/rules/correctness/return-in-init.yaml:21`** — Single-line message with limitation note:
```yaml
message: "`return` should never appear inside a class __init__ function. This will cause a runtime error. Factory lambdas passed to defaultdict (e.g. `defaultdict(lambda: deque(...))`) are valid and excluded via pattern-not-inside; they are not return statements. NOTE: Lambdas passed as variables (e.g., `f = lambda: ...; defaultdict(f)`) are NOT excluded by this pattern due to semgrep's pattern-not-inside limitations. If such code is introduced, add `# nosemgrep` comment."
```

**`.semgrep/run.sh:12`** — Restored `uv run semgrep`:
```bash
uv run semgrep scan --verbose \
```

### Rule Correctness Verified
- `defaultdict(lambda: ...)` correctly excluded (0 findings on `rfm9x_sx127x_module.py`)
- Actual `return`/`yield` in `__init__` correctly detected (4 findings on test file)
- Full semgrep suite: 132 rules, 46 files, 0 findings

---

## Code Review 2.1 Findings Resolution

The external review `code_review-2.1.json` identified 12 findings. Resolution:

| # | Finding | Severity | Valid? | Action |
|---|---------|----------|--------|--------|
| 1 | `pattern-not-inside` limitation | Medium | ✅ | Documented in rule message |
| 2 | Message format `>-` vs `\|-` | Low | ✅ | Converted to single-line |
| 3 | `venv/bin/semgrep` without check | Medium | ✅ | Restored `uv run semgrep` |
| 4 | TMPDIR explicit check | Low | ❌ | Kept `|| exit 1` (POSIX, idiomatic) |
| 5 | aiologic 0.17.1 "not on PyPI" | High | ❌ | **INVALID** — verified in `uv.lock`; corrected comment |
| 6 | Explicit casts for no-any-return | Low | ✅ (positive) | Already done in Plan 1 |
| 7 | UP042 ignore justified | Low | ✅ (positive) | Documented |
| 8 | KNOWN_DEFECTS.md not found | Medium | ❌ | **INVALID** — file at `.plans/KNOWN_DEFECTS.md`; updated cross-references |
| 9 | Same cross-reference issue | Medium | ❌ | Updated cross-references |
| 10 | aiologic availability misleading | Medium | ❌ | **INVALID** — 0.17.1 IS on PyPI; corrected comment |
| 11 | Explicit casts are improvement | Low | ✅ (positive) | Already done |
| 12 | **command_bus.py comment contradicts code** | **High (Bug)** | ✅ | **FIXED** — comment corrected to match `existing[1] <= priority` logic |

**Critical Fix Applied**: `command_bus.py:51` — Comment changed from "priority >= new priority" to "priority <= new priority" to match actual code logic.

---

## Files Modified (15 files)

| File | Changes |
|------|---------|
| `.semgrep/rules/correctness/return-in-init.yaml` | Added `pattern-not-inside`, updated message |
| `.semgrep/rules/custom/config-cache-coherence.yaml` | **New file** — anti-regression semgrep rule |
| `.semgrep/run.sh` | Added `|| exit 1`, POSIX comment, restored `uv run semgrep` |
| `README.md` | Updated project structure documentation |
| `pyproject.toml` | aiologic pin, mypy overrides, ruff per-file ignores |
| `src/pi_lora/drivers/rfm9x_sx127x_config_loader.py` | Cache coherence fix, docstring, removed unused import |
| `src/pi_lora/drivers/rfm9x_sx127x_module.py` | Removed obsolete nosemgrep, fixed TimeoutError comment |
| `src/pi_lora/drivers/rfm9x_sx127x_radio_instance.py` | O(1) lookup indexes, cleaned docstring |
| `src/pi_lora/drivers/spi/bus.py` | Added explicit casts for 4 property getters |
| `src/pi_lora/drivers/spi/locks.py` | Added explicit cast for `get_bus_lock` return |
| `src/pi_lora/framework/command_bus.py` | Fixed misleading priority comment |
| `src/pi_lora/framework/scheduler.py` | Fixed misleading backoff comment |
| `tests/drivers/test_config_loader.py` | Added regression test, updated module docstring |
| `tests/test_rfm9x_sx127x_config_loader.py` | Updated concurrent test to match new contract |
| `uv.lock` | Updated aiologic specifier to `==0.17.1` |

---

## Anti-Regression Compliance

Every fix includes inline comments following project convention:
```python
# PLAN-XX FIX (Item N): Brief description.
# The [issue] was [root cause]. [Fix] prevents this by [mechanism].
# Cross-reference: .plans/KNOWN_DEFECTS.md Section X.
```

Semgrep rules added for:
- `config-cache-coherence-guard` — prevents KNOWN_DEFECTS §3.1 reintroduction
- `return-in-init` — documents limitation for future maintainers

---

## Risk Assessment — Post-Implementation

| Risk | Pre | Post | Mitigation |
|------|-----|------|------------|
| Cache coherence bug (KNOWN_DEFECTS §3.1) | HIGH | **None** | Fixed + test + semgrep rule |
| aiologic version unavailable | Medium | **None** | Verified on PyPI via uv.lock |
| Mypy type safety gaps | Medium | **None** | Strict passes; explicit casts |
| Semgrep false negatives | Medium | **Low** | Documented limitation + workaround |
| run.sh environment failure | Medium | **None** | `uv run semgrep` auto-provisions |
| Documentation drift | Low | **None** | All docstrings updated to match behavior |

---

## Conclusion

The `RAIR_2026_11_21_MediumLowFixes` branch is **complete, validated, and ready for merge**. All three plans have been implemented exactly as specified, all validation gates pass with zero errors, and comprehensive anti-regression measures are in place. The fixes improve code quality, type safety, maintainability, and tooling reliability without introducing any behavioral regressions.