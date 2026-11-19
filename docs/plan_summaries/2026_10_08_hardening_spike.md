# 2026-10-08 Hardening Spike — Durable Summary

*All plans from plan-4 through plan-38, with references to original plan locations that were referenced in code. This summary enables code edits to rewrite references from original plans to this summary.*

---

## Overview

The hardening spike ran from **2026-10-10** (plan-4) through **2026-11-17** (plan-38), addressing architectural defects, structural fixes, and quality improvements across the MeshCore Pi LoRa codebase. A total of **35 plans** (plan-4 through plan-38, plus plan-4_phase-2 variants) were written and reviewed, with **code reviews** performed at each iteration.

The plans evolved from critical architectural fixes through incremental hardening, with each plan building on the previous one. Key themes included:

- SPI lock abstraction and async/sync compatibility
- Application lifecycle and reentrancy safety
- Config loader singleton cache and race conditions
- Command bus handler specificity and exception handling
- Module manager registration and rollback
- Scheduler task management and backoff patterns
- CLI async command execution (async-typer migration)
- Test infrastructure and regression prevention
- Documentation and anti-regression patterns

---

## Plan Summary Index

| Plan | Date | Scope | Key Files |
|------|------|-------|-----------|
| **plan-4** | 2026-10-10 | Initial 45+ architectural flaws, config loading, application lifecycle, test coverage | locks.py, config_loader.py, application.py, scheduler.py, command_bus.py, bus.py, module_manager.py, events.py, modes.py, factory.py, cli/ |
| **plan-5** | 2026-10-17 | 9 high/critical fixes from external review (Plan-4 implementation review) | locks.py, factory.py, bus.py, application.py, scheduler.py, command_bus.py, module_manager.py, cli/test.py |
| **plan-6** | 2026-10-18 | 21 findings (7 critical, 5 high, 9 medium) from implementation review | locks.py, bus.py, factory.py, application.py, scheduler.py, command_bus.py, module_manager.py, config_model.py, modes.py, cli/ |
| **plan-7** | 2026-10-20 | CLI async commands fix via async-typer migration | pyproject.toml, main.py, test.py, config.py, check_hardware.py, tests/ |
| **plan-8** | 2026-10-20 | Post-Plan-7 critical regressions (code_review-7.1) | main.py, config.py, test.py, pyproject.toml, locks.py, bus.py, module_manager.py, scheduler.py, application.py, cli/_logging.py |
| **plan-9** | 2026-10-21 | 10 blocking HIGH bugs from code_review-8.1 | config_loader.py, bus.py, locks.py, application.py, scheduler.py, module_manager.py |
| **plan-10** | 2026-10-22 | 6 HIGH bugs from code_review-9.1 | factory.py, locks.py, bus.py, application.py, command_bus.py, module_manager.py |
| **plan-11** | 2026-10-22 | 7 HIGH bugs from code_review-10.1 | locks.py, config_loader.py, application.py, command_bus.py, factory.py, scheduler.py, test.py |
| **plan-12** | 2026-10-23 | 8 CRITICAL/HIGH blockers from code_review-11.1 | config_loader.py, application.py, locks.py, scheduler.py, bus.py, check_hardware.py, _entry_points.py, mock.py |
| **plan-13** | 2026-10-24 | 6 HIGH blockers from code_review-12.1 | config_loader.py, factory.py, locks.py, test.py, scheduler.py, application.py |
| **plan-14** | 2026-10-25 | 4 HIGH regressions from Plan-13 | test.py, bus.py, locks.py |
| **plan-15** | 2026-10-25 | 1 CRITICAL + 8 HIGH from code_review-14.1 | application.py, config_model.py, radio_instance.py, locks.py, bus.py, command_bus.py, handler.py |
| **plan-16** | 2026-10-26 | All findings from code_review-15.1 (CRITICAL + HIGH + MEDIUM + LOW) | Multiple files across codebase |
| **plan-17** | 2026-10-27 | 4 new HIGH + 3 pre-existing from code_review-16.1 | module_manager.py, scheduler.py, command_bus.py, config_loader.py |
| **plan-18** | 2026-10-29 | 5 HIGH/CRITICAL from code_review-17.2 | test.py, module_manager.py, application.py, scheduler.py, bus.py, cli/_logging.py |
| **plan-19** | 2026-10-31 | 7 "Must Fix Now" from code_review-18.1 | .semgrep/run.sh, check_hardware.py, rfm9x_sx127x_module.py, config_loader.py, bus.py, locks.py, command_bus.py |
| **plan-20** | 2026-11-01 | 5 HIGH from code_review-19.1 | check_hardware.py, locks.py, application.py, module_manager.py, bus.py |
| **plan-21** | 2026-11-02 | 11 findings from code_review-20.1 | bus.py, radio_instance.py, config_loader.py, .semgrep/rules/custom/, pyproject.toml |
| **plan-22** | 2026-11-03 | 7 production blockers + 3 compat issues from code_review-21.1/21.2 | config_loader.py, locks.py, bus.py, radio_instance.py, _entry_points.py |
| **plan-23** | 2026-11-06 | Plan-22 regressions + code_review-22.3 bugs | config_loader.py, module_manager.py, bus.py, _entry_points.py, cli/main.py |
| **plan-24** | 2026-11-06 | 4 CRITICAL + 1 test gap from code_review-23.1 | config_loader.py, application.py, scheduler.py, bus.py, tests/ |
| **plan-25** | 2026-11-07 | 4 CRITICAL + 8 HIGH from code_review-24.1 | config_loader.py, bus.py, locks.py, application.py, scheduler.py, command_bus.py, mock.py, fakes.py |
| **plan-26** | 2026-11-08 | 16 critical/high findings (4 Plan-25 regressions) | config_loader.py, radio_instance.py, bus.py, locks.py, application.py, module_manager.py, scheduler.py, fakes.py, mock.py |
| **plan-27** | 2026-11-08 | 11 new CRITICAL/HIGH from code_review-26.1 + Finding 1011 | config_loader.py, bus.py, locks.py, application.py, module_manager.py, scheduler.py, entry_points.py, fakes.py, test_entry_points.py, semgrep rules |
| **plan-28** | 2026-11-10 | 3 CRITICAL regressions + 3 HIGH from code_review-27.2 | lazy_async_lock.py (new), locks.py, config_loader.py, bus.py, application.py, tests/ |
| **plan-29** | 2026-11-12 | CRITICAL LazyAsyncLock bug + pattern translation gap | lazy_async_lock.py, locks.py, config_loader.py, tests/ |
| **plan-30** | 2026-11-12 | 6 HIGH pre-existing findings | _entry_points.py, factory.py, module_manager.py, command_bus.py, scheduler.py, fakes.py |
| **plan-31** | 2026-11-13 | 3 regressions + 1 test gap from code_review-30.2 | .semgrep/rules/custom/, _entry_points.py, scheduler.py, test_spidev_patch_contextvar.py |
| **plan-32** | 2026-11-14 | 3 new items from Plan-31 external review | config_loader.py, _entry_points.py, main.py |
| **plan-33** | 2026-11-14 | 2 regressions from Plan-32 + 6 KNOWN_DEFECTS entries | _entry_points.py, main.py, test_entry_points.py, KNOWN_DEFECTS.md |
| **plan-34** | 2026-11-15 | 6 HIGH + 2 MEDIUM from code_review-33.1 | main.py, check_hardware.py, config.py, test.py, fakes.py, scheduler.py, KNOWN_DEFECTS.md |
| **plan-35** | 2026-11-16 | 9 HIGH from code_review-34.3 (7 unique fixes) | test.py, locks.py, application.py, command_bus.py, fakes.py, main.py, _entry_points.py, pyproject.toml |
| **plan-36** | 2026-11-16 | 13 HIGH from code_review-35.1 | _entry_points.py, check_hardware.py, config.py, test.py, factory.py, locks.py, application.py, command_bus.py, module_manager.py, scheduler.py, fakes.py |
| **plan-37** | 2026-11-17 | 4 actionable + 3 pre-existing from code_review-36.1 | application.py, scheduler.py, check_hardware.py, lora_detection.py |
| **plan-38** | 2026-11-17 | 8 CRITICAL/HIGH from code_review-37.2 | lazy_async_lock.py, application.py, module_manager.py, scheduler.py, mock.py, lora_detection.py |

---

## Phase Subdirectories

The spike included phased changes within plan-4:

- **phase1**: Initial plan-4 foundations
- **phase2**: Post-phase-2 test fixes (6 test-fix variants)
- **phase2_A**: Alternative phase-2 approach
- **phase2_B**: Alternative phase-2 approach

---

## Key Files Modified Across All Plans

### Drivers & SPI
- `src/pi_lora/drivers/spi/locks.py` — 20+ plan iterations
- `src/pi_lora/drivers/spi/bus.py` — 15+ plan iterations
- `src/pi_lora/drivers/spi/factory.py` — 8+ plan iterations
- `src/pi_lora/drivers/rfm9x_sx127x_config_loader.py` — 15+ plan iterations
- `src/pi_lora/drivers/rfm9x_sx127x_module.py` — 5+ plan iterations
- `src/pi_lora/drivers/rfm9x_sx127x_modes.py` — 3+ plan iterations
- `src/pi_lora/drivers/rfm9x_sx127x_radio_instance.py` — 5+ plan iterations
- `src/pi_lora/drivers/lora_detection.py` — 2+ plan iterations
- `tests/spi/mock.py` — 8+ plan iterations
- `tests/fakes.py` — 5+ plan iterations

### Framework
- `src/pi_lora/framework/application.py` — 20+ plan iterations
- `src/pi_lora/framework/scheduler.py` — 15+ plan iterations
- `src/pi_lora/framework/command_bus.py` — 10+ plan iterations
- `src/pi_lora/framework/module_manager.py` — 15+ plan iterations
- `src/pi_lora/framework/events.py` — 2+ plan iterations
- `src/pi_lora/framework/lazy_async_lock.py` — Plans 28-29

### CLI
- `src/pi_lora/cli/main.py` — 8+ plan iterations
- `src/pi_lora/cli/test.py` — 12+ plan iterations
- `src/pi_lora/cli/config.py` — 8+ plan iterations
- `src/pi_lora/cli/check_hardware.py` — 8+ plan iterations
- `src/pi_lora/cli/_entry_points.py` — Plans 22-38
- `src/pi_lora/cli/_logging.py` — 3+ plan iterations

### Config Model
- `src/pi_lora/drivers/rfm9x_sx127x_config_model.py` — 3+ plan iterations
- `src/pi_lora/drivers/rfm9x_sx127x_radio_instance.py` — 5+ plan iterations

### Test Infrastructure
- `tests/test_entry_points.py` — Plans 22-38
- `tests/framework/test_application.py` — Plans 9-38
- `tests/framework/test_scheduler.py` — Plans 9-38
- `tests/framework/test_module_manager.py` — Plans 9-38
- `tests/framework/test_command_bus.py` — Plans 9-38
- `tests/drivers/spi/test_locks.py` — Plans 5-38
- `tests/drivers/spi/test_bus.py` — Plans 5-38
- `tests/drivers/spi/test_factory.py` — Plans 10-38
- `tests/drivers/test_config_loader.py` — Plans 9-38
- `tests/drivers/test_config_loader_concurrent.py` — Plans 9-38

---

## Critical & High Priority Summary by Category

### SPI Lock Abstraction (Plans 4-28+)
- **Phase 1** (plan-4): Fix `_SyncSpiLock.acquire()` return awaitable
- **Phase 3** (plan-5): Fix `async_release` → `release` protocol mismatch
- **Phase 21** (plan-11): Fix `async_release` protocol
- **Plan-28**: Extract `LazyAsyncLock` utility (shared pattern authority)
- **Plan-38**: Use `aiologic.Lock` for holder in `LazyAsyncLock`

### Application Lifecycle (Plans 4-38)
- **Phase 3** (plan-4): Fix `Application.start()` reentrancy
- **Phase 21** (plan-11): Fix `_cleanup_partial_start()` scheduler unregistration
- **Plan-18**: Fix application cleanup leak on `CancelledError`
- **Plan-25**: Fix exception chaining in `start()`
- **Plan-27**: Fix `_cleanup_and_reraise_cancellation()` BaseException gap
- **Plan-28**: Fix `_cleanup_partial_start()` ExceptionGroup handling
- **Plan-37**: Fix missing `except ExceptionGroup` in cleanup handler
- **Plan-38**: Fix double-checked locking fast-path removal

### Config Loader (Plans 4-38)
- **Phase 2** (plan-4): Fix `get_preloaded_config()` singleton cache
- **Plan-13**: Fix `_init_lock` lazy init race
- **Plan-19**: Fix cache update on `config_path` override + import race
- **Plan-25**: Protect ALL cache access under `_config_lock`
- **Plan-29**: Fix sentinel pattern + docstring
- **Plan-35**: Fix atomic `_registry_verified` check-and-set

### Command Bus (Plans 4-38)
- **Phase 6** (plan-4): Fix `CommandBus.execute()` exception handling
- **Plan-16**: Fix `dispatch()` None from module_resolver
- **Plan-25**: Fix ExceptionGroup handling in `dispatch()`
- **Plan-34**: Fix exception hierarchy in `dispatch()`
- **Plan-37**: Fix ExceptionGroup in `_cleanup_and_reraise_cancellation()`

### Scheduler (Plans 4-38)
- **Phase 4** (plan-4): Fix `IdlePacer._idle_task` CPU spin
- **Phase 5** (plan-4): Fix `InterruptBridge` broadcast
- **Phase 25** (plan-25): Fix backoff pattern
- **Plan-18**: Fix `InterruptBridge.stop()` loop capture
- **Plan-26**: Fix `_loop` race in `stop()`
- **Plan-27**: Fix InterruptBridge backoff bug (check before consuming)
- **Plan-36**: Fix `stop()` acquires `trigger_lock` first

### CLI Async (Plans 7-20)
- **Plan-7**: Migrate to `async-typer`
- **Plan-8**: Fix entry point wrappers + event loop
- **Plan-19**: Fix `setup_logging()` distribution
- **Plan-20**: Fix `SystemExit` code mapping

### Module Manager (Plans 4-38)
- **Phase 22** (plan-4): Fix duplicate `DeviceIdentity` handling
- **Phase 23** (plan-4): Fix silent GPIO parsing failures
- **Phase 24** (plan-4): Fix no cleanup on load failure
- **Plan-13**: Fix registration order + pending list pattern
- **Plan-22**: Fix `_GuardedLock._obtained` logic
- **Plan-25**: Fix rollback ExceptionGroup handling
- **Plan-27**: Fix `load_from_config()` exception handling split
- **Plan-33**: Fix `_run_app` None return handling
- **Plan-38**: Fix rollback on `KeyboardInterrupt`/`SystemExit`

### Test Infrastructure (Plans 7-38)
- **Plan-7**: Add `tests/test_cli_async_integration.py`
- **Plan-14**: Add contract tests + semgrep rules
- **Plan-22**: Add entry point tests + exception tests
- **Plan-25**: Add comprehensive regression test suite
- **Plan-26**: Add concurrency tests + negative tests
- **Plan-28**: Add `test_lazy_async_lock.py` concurrency suite
- **Plan-29**: Add negative test for direct context manager usage

### Documentation & Anti-Regression (All plans)
- Inline code comments at each fix site
- Semgrep rules to detect buggy patterns
- `KNOWN_DEFECTS.md` entries for unresolved issues
- Plan review documentation chains

---

## Review Files

All plan reviews are stored in `.plans/2026_10_08_hardening_spike/`:

- `plan-4_implementation_review.md`
- `plan-5_implementation_review.md`
- `plan-6_implementation_review.md`
- `plan-7_spike_review.md` through `plan-38_spike_review.md`
- Individual code_review-*.json and code_review-*.txt files
- `plan-37_spike_review.md` and `plan-38_spike_review.md`

---

## Using This Summary

This durable summary replaces references to individual plan files in code. When editing code to change plan references:

1. **Original references** pointed to `.plans/2026_10_08_hardening_spike/plan-N.md` or `.plans/2026_10_08_hardening_spike/code_review-.json`
2. **New references** should point to this summary file `.plans/2026_10_08_hardening_spike.md`
3. **Code can then be further edited** to remove plan references entirely, knowing the full history is preserved in this summary

The summary is intentionally structured so that:
- Each plan's scope and key changes are documented
- File paths of modifications are listed
- Critical/high priority items are categorized
- Review file locations are noted
- The progression from plan-4 to plan-38 is tracked

*This file was generated to preserve the hardening spike's institutional knowledge after the original plan files are deleted.*