# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""Application — composes ModuleManager, Scheduler, CommandBus into a unified runtime."""

from __future__ import annotations

import asyncio  # noqa: F401
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..drivers.rfm9x_sx127x_config_model import Rfm9xSx127xConfig  # noqa: F401
    from ..drivers.rfm9x_sx127x_module import Rfm9xSx127xModule  # noqa: F401

from .command_bus import CommandBus
from .events import StopMode
from .exceptions import (
    AssemblyNotFoundError,
    ConfigLoadError,
    DeviceAttachmentNotFoundError,
)
from .module_manager import ModuleManager
from .scheduler import Scheduler
from ..drivers.rfm9x_sx127x_config_loader import get_preloaded_config
from ..drivers.rfm9x_sx127x_radio_instance import (
    AssemblyNotFoundError as DriverAssemblyNotFoundError,
    ConfigConsistencyError,
    DeviceAttachmentNotFoundError as DriverDeviceAttachmentNotFoundError,
    DeviceSpecNotFoundError,
    DriverModuleNotFoundError,
    FamilyNotFoundError,
    RadioInstanceConfig,
    create_radio_instance,
)

logger = logging.getLogger(__name__)


class Application:
    """Top-level runtime owning the module lifecycle and command infrastructure."""

    def __init__(self, config: Any, spi_factory: Any | None = None) -> None:
        self.config = config
        self.scheduler = Scheduler()
        self.module_manager = ModuleManager()
        self.command_bus = CommandBus()
        if spi_factory is not None:
            self.spi_factory = spi_factory
        else:
            from ..drivers.spi.factory import RealSpiBusFactory

            self.spi_factory = RealSpiBusFactory()
        self._config: "Rfm9xSx127xConfig | None" = None
        self._config_path: Path | None = None
        self._started_modules: list[Rfm9xSx127xModule] = []
        self._scheduler_started: bool = False
        self._started: bool = False
        self._lifecycle_lock: asyncio.Lock = asyncio.Lock()
        # PLAN-26 FIX (Findings 744, 754): Lock for config cache to prevent race
        # between _load_config() and reload_config() when called concurrently with
        # different config_path values.
        self._config_lock: asyncio.Lock = asyncio.Lock()

    async def start(self, assembly_name: str = "default") -> None:
        """Initialize the application: load modules, register scheduler, start loops.

        NR-6 FIX: the lifecycle lock is held across the ENTIRE start + cleanup
        sequence. start() holds the lock for the whole start+cleanup window so a
        concurrent stop() (which guards on _started == True) can never run its
        cleanup inside this window. Because _cleanup_partial_start() is only ever
        called from within start() while the lock is already held, it no longer
        acquires the lock itself (NR-6 FIX), so asyncio's non-recursive Lock cannot
        deadlock on a self-held lock.
        """
        exc_to_raise: BaseException | None = None
        # PLAN-25 FIX (Fix 6, Issue 24.7): double-checked locking. Fast-path read of
        # self._started outside the lock is a benign read-only optimization (avoid lock
        # contention on the common already-started case). The authoritative check is the
        # re-check inside _lifecycle_lock, which serializes the actual startup.
        # Cross-reference: code_review-24.1.json finding 24.7.
        already_started: bool = self._started
        if already_started:
            return
        async with self._lifecycle_lock:
            # Re-check inside lock (authoritative)
            if self._started:
                return
            # CR-2 FIX (Plan-16): Clear ModuleManager tracking state before
            # load_from_config() runs so a previously-failed start()/stop() does
            # not leave stale modules. load_from_config() (module_manager.py:117)
            # raises DuplicateDeviceIdentityError when a DeviceIdentity is already
            # present in modules_by_id; a stale re-keyed module from a prior
            # failed start would block the restart. Cleared here (inside the lock,
            # after the _started guard, and mirrored in stop()) to guarantee a
            # clean slate. NOTE: cleared AFTER the _started guard so a no-op
            # start() (already started) never wipes modules that stop() needs to
            # unregister — clearing before the lock would break concurrent
            # start()/stop() cleanup (see test_concurrent_start_stop_no_race).
            self.module_manager.modules.clear()
            self.module_manager.modules_by_id.clear()
            self._started_modules = []
            try:
                assembly_result = await self.get_assembly_config(assembly_name)
                radio_configs: list[RadioInstanceConfig] = assembly_result if isinstance(assembly_result, list) else [assembly_result]
                await self.module_manager.load_from_config(radio_configs, self.scheduler, self.spi_factory)
                self.command_bus.set_module_resolver(self._resolve_module_for_command)
                await self.scheduler.start()
                self._scheduler_started = True
                for module in self.module_manager.get_all_modules():
                    await module.init_spi_bus()
                    # Append after init_spi_bus() so SPI handle is tracked for cleanup.
                    # If start_event_loop() fails, stop_event_loop() handles no-task case cleanly
                    # and close_spi() releases the bus. Pre-Plan-9 behavior was correct; Plan-9
                    # over-corrected and leaked resources on start_event_loop() failure.
                    self._started_modules.append(module)
                    await module.start_event_loop()
                self._started = True
            except asyncio.CancelledError as exc:
                exc_to_raise = exc
            except Exception as exc:
                exc_to_raise = exc
            # PLAN-20: Handle KeyboardInterrupt/SystemExit (BaseException) explicitly.
            # These shutdown signals bypass `except Exception` and would skip cleanup,
            # leaking SPI handles, scheduler tasks, and module registrations.
            # Run cleanup then re-raise verbatim to preserve Ctrl+C / sys.exit semantics.
            #
            # PLAN-26 FIX (Findings 645, 684): Catch BaseException (not just Exception)
            # from cleanup, because a second Ctrl+C during cleanup raises KeyboardInterrupt
            # (a BaseException). If cleanup is interrupted by another shutdown signal,
            # re-raise the ORIGINAL shutdown signal to preserve semantics.
            except BaseException as exc:  # KeyboardInterrupt, SystemExit
                exc_to_raise = exc
                try:
                    await self._cleanup_partial_start()
                except BaseException as cleanup_exc:
                    # If cleanup is interrupted by another shutdown signal, re-raise
                    # the original shutdown signal with the cleanup interruption as __cause__.
                    # If cleanup raises a regular Exception, chain it with the original.
                    raise exc from cleanup_exc
                raise exc
            # NR-6 FIX: cleanup runs INSIDE the lock so it is mutually exclusive
            # with a concurrent stop(). _cleanup_partial_start() must NOT re-acquire
            # the lock (NR-6 FIX) or asyncio's non-recursive Lock would deadlock.
            # CR-3 FIX (Findings 562-568, 582-589, CR-3.5): The try/except that wrapped
            # _cleanup_and_reraise_cancellation() is REMOVED. _cleanup_and_reraise_cancellation()
            # already performs ALL exception logic itself (see its four-case handler): it
            # re-raises original_exc verbatim when cleanup succeeds, and chains original_exc
            # with the cleanup exception when cleanup itself raises. The old try/except was a
            # workaround for an old bug that is now fixed in the callee.
            #
            # BUG (CR-3.5): the old try/except caught the exception re-raised by the callee as
            # `cleanup_exc` and then did `raise exc_to_raise from cleanup_exc`. Because the callee
            # already re-raised `exc_to_raise` (the SAME object), this set
            # `exc_to_raise.__cause__ = exc_to_raise` — a self-referential __cause__ cycle.
            # A __cause__ that points at itself is invalid and breaks exception chaining/traceback
            # rendering. Removing the wrapper lets _cleanup_and_reraise_cancellation()'s own
            # `raise original_exc from cleanup_exc` set __cause__ to the *cleanup* exception (a
            # distinct object), which is the correct, acyclic chain.
            #
            # Alternative rejected: keeping the wrapper but catching only `Exception` — still
            # cycles when the callee re-raises the same object. Keeping it and catching
            # `BaseException` — same cycle. The only correct fix is to let the callee own the
            # raise. The bare call below still returns/reports correctly: if cleanup succeeds,
            # the callee raises original_exc; if cleanup raises, the callee raises/chains; both
            # propagate out of start() naturally.
            if exc_to_raise is not None:
                await self._cleanup_and_reraise_cancellation(
                    self._cleanup_partial_start, exc_to_raise
                )

    async def stop(self) -> None:
        """Gracefully stop all modules and the scheduler.

        Per-module failures are collected and surfaced as an ``ExceptionGroup``
        once every module and the scheduler have been drained and the state
        flags have been reset to a clean baseline.
        """
        errors: list[Exception] = []
        async with self._lifecycle_lock:
            if not self._started:
                return
            # Explicitly unregister each module from scheduler BEFORE stopping event loops
            # to prevent timer/idle/interrupt tasks from queuing events during shutdown.
            # CR-3 FIX (Findings 600-608, CR-3.6): scheduler.unregister_module() raises an
            # ExceptionGroup (Python 3.11+), NOT a single Exception. The pre-fix bare
            # `await self.scheduler.unregister_module(module)` let that ExceptionGroup
            # propagate out of stop(), skipping ALL subsequent cleanup (draining event loops,
            # close_spi, scheduler.stop, state reset) for the remaining modules and the
            # scheduler — a resource leak and a state-consistency bug.
            #
            # FIX: catch the ExceptionGroup and flatten its `.exceptions` into `errors` so the
            # per-module failures are collected alongside any real Exception, then continue the
            # cleanup loop for every module. `errors` is declared at the top of stop()
            # (line 178: `errors: list[Exception] = []`) and is raised as an ExceptionGroup at
            # the end of stop() — consistent with stop()'s contract.
            #
            # Alternative rejected: wrapping in `except Exception` only — an ExceptionGroup is
            # NOT an Exception (it is a BaseException), so `except Exception` would NOT catch it
            # and the ExceptionGroup would still propagate. Must catch ExceptionGroup first.
            for module in self.module_manager.get_all_modules():
                try:
                    await self.scheduler.unregister_module(module)
                except ExceptionGroup as eg:
                    errors.extend(eg.exceptions)
                except Exception as exc:
                    errors.append(exc)
            for module in self.module_manager.get_all_modules():
                try:
                    await module.stop_event_loop(StopMode.DRAIN)
                except Exception as exc:
                    logger.exception(
                        "stop_event_loop failed for SPI device=%s CE=%s",
                        module.get_spi_device_id(),
                        module.get_ce_number(),
                    )
                    errors.append(exc)
                try:
                    await module.close_spi()
                except Exception as exc:
                    logger.exception(
                        "close_spi failed for SPI device=%s CE=%s",
                        module.get_spi_device_id(),
                        module.get_ce_number(),
                    )
                    errors.append(exc)
            try:
                await self.scheduler.stop()
            except Exception as exc:
                logger.exception("scheduler.stop() failed during stop")
                errors.append(exc)
            self._started_modules.clear()
            self._scheduler_started = False
            self._started = False
            # CR-2 FIX (Plan-16): Clear ModuleManager tracking state after cleanup
            # and state flags are reset, BEFORE the lock exits. This mirrors the
            # start() clear so a fully-drained application leaves no stale modules
            # that would re-key on the next start() and raise
            # DuplicateDeviceIdentityError (module_manager.py:117). Clearing inside
            # the lock keeps the rollback mutually exclusive with any concurrent
            # start()/stop().
            self.module_manager.modules.clear()
            self.module_manager.modules_by_id.clear()
        if errors:
            raise ExceptionGroup("Errors during Application.stop()", errors)

    async def _cleanup_and_reraise_cancellation(
        self,
        cleanup_coro: "Callable[[], Awaitable[None]]",
        original_exc: BaseException | None = None,
    ) -> None:
        """Run cleanup then re-raise the original exception (typically CancelledError).

        CR-3 FIX / §1.3 (Plan-17): Centralizes the correct cancellation pattern
        used by start(), stop(), and _cleanup_partial_start(). The handler set covers
        EXactly four cases (Exception ⊂ BaseException, so handler ordering is Exception-first):

          Case 1 — Cleanup SUCCEEDS (no exception): the original exception that triggered
              cleanup MUST still propagate to the caller. The pre-fix returned None here,
              swallowing the exception; FIX re-raises original_exc verbatim (bottom of body).
          Case 2 — Cleanup raises CancelledError: chain with original. `raise original_exc
              from cleanup_cancelled` preserves both the original and the cleanup interruption
              as __cause__. Valid on Python 3.13 where CancelledError is a BaseException.
          Case 3 — Cleanup raises a regular Exception (possibly an ExceptionGroup): chain with
              original ONLY if original_exc is a shutdown signal (a BaseException that is NOT
              an Exception, e.g. KeyboardInterrupt/SystemExit/CancelledError); otherwise let the
              cleanup exception propagate (original_exc stays reachable via __context__).
          Case 4 — Cleanup raises a BaseException other than CancelledError (KeyboardInterrupt,
              SystemExit, GeneratorExit): chain with original if original_exc is a BaseException;
              otherwise raise verbatim. This is CR-3.7 FIX; the pre-fix code had NO handler for
              these and swallowed them.

        BUG (CR-3): the pre-fix code caught CancelledError together with generic
        Exception via ``except (Exception, asyncio.CancelledError)`` and then did
        ``await self._cleanup_partial_start(); raise``. That path swallowed the
        CancelledError: the bare ``raise`` re-raised whatever exception was active
        in the generator frame (the generic caught exception or a stale one), NOT
        the CancelledError that actually triggered the cancellation. asyncio's
        cancellation semantics require the CancelledError to be the exception that
        propagates to the awaiting coroutine (e.g. the one driving
        ``asyncio.sleep``/``create_task``), because only a CancelledError at an
        await point actually propagates cancellation to the *caller*. Re-raising
        it verbatim restores that contract.

        §1.3 (Plan-17) FIX: if ``cleanup_coro`` itself is cancelled (e.g. during
        ``await module.stop_event_loop()`` inside the cleanup path), the outer
        CancelledError would otherwise be lost. We catch that cleanup-cancelled
        CancelledError and re-raise the ORIGINAL exception so the caller still
        observes the correct cancellation.

        The alternative (catching CancelledError with generic Exception and
        dropping it) was rejected: dropping the CancelledError would let start()
        return normally to a caller that expected the coroutine to be cancelled,
        silently undoing the cancellation and leaving the caller's own await
        loop in an inconsistent state.

        Args:
            cleanup_coro: The cleanup coroutine to run.
            original_exc: The exception that triggered cleanup (e.g. CancelledError
                from start()). If None, re-raises whatever cleanup raises.

        Note: ``cleanup_coro`` already performs its own per-module cleanup and may
        itself raise an ExceptionGroup; both branches simply let that raise
        propagate after cleanup has completed.
        """
        try:
            await cleanup_coro()
        except asyncio.CancelledError as cleanup_cancelled:
            # Location 3 (Plan-18 §6 anti-regression; Plan-17 §1.3 FIX).
            #
            # Case: original_exc is a regular Exception AND cleanup_coro was
            # cancelled. Both facts must be preserved for the caller.
            #
            # NOTE: in THIS environment (Python 3.13) asyncio.CancelledError is a
            # BaseException, NOT an Exception. ExceptionGroup.__init__ rejects
            # any non-Exception member and raises TypeError
            # ("Cannot nest BaseExceptions in an ExceptionGroup"). So the
            # ExceptionGroup approach below FAILs at runtime here -- nesting
            # cleanup_cancelled (a CancelledError) would raise TypeError instead
            # of the intended ExceptionGroup. The correct fix is __cause__
            # chaining: `raise original_exc from cleanup_cancelled`, which raises
            # original_exc (what the caller expects) and records cleanup_cancelled
            # as __cause__ (the fact that cleanup was interrupted). __cause__
            # chaining preserves both facts, is valid on Python 3.11+, and never
            # raises TypeError. Do NOT document/regress to an ExceptionGroup here.
            if original_exc is None:
                raise
            if isinstance(original_exc, asyncio.CancelledError):
                # Both are cancellations — chain them. `raise original_exc from
                # cleanup_cancelled` raises original_exc with cleanup_cancelled as
                # __cause__, preserving both facts.
                raise original_exc from cleanup_cancelled
            # Regular Exception + cleanup cancellation → chain via `from`.
            # ExceptionGroup is impossible here (CancelledError is a BaseException
            # in Python 3.13); chaining preserves both facts without TypeError.
            raise original_exc from cleanup_cancelled
        except Exception as cleanup_exc:
            # C-1 FIX / PLAN-25 FIX (Issue 24.8): cleanup may raise an Exception (possibly an
            # ExceptionGroup). When original_exc is present, chain it via __cause__ so BOTH
            # the original failure and the cleanup error are preserved — the original becomes
            # the primary raised exception and the cleanup error becomes __cause__. This holds
            # whether original_exc is a shutdown signal (CancelledError, KeyboardInterrupt,
            # SystemExit) or a regular Exception (e.g. RuntimeError from start_event_loop()),
            # so neither fact is dropped.
            # Cross-reference: test_application.py TestCancellationSemantics
            # test_start_exception_chaining_preserves_cause.
            if original_exc is not None:
                raise original_exc from cleanup_exc
            raise
        except BaseException as cleanup_exc:  # KeyboardInterrupt, SystemExit, GeneratorExit
            # CR-3 FIX (Findings 610-617, CR-3.7): Missing `except BaseException` handler.
            #
            # BUG (CR-3.7): cleanup could raise a BaseException that is NOT an Exception and NOT
            # a CancelledError — e.g. KeyboardInterrupt, SystemExit, or GeneratorExit (a second
            # shutdown signal during cleanup). Because the handler set only covered
            # `asyncio.CancelledError` and `Exception`, such a BaseException fell through ALL
            # handlers and was swallowed: the method returned None instead of propagating the
            # shutdown signal, silently undoing the caller's cancellation/exit semantics.
            #
            # FIX: add `except BaseException` AFTER `except Exception`. Exception ⊂ BaseException,
            # so Python dispatches `Exception` subclasses to the earlier handler and only
            # non-Exception BaseExceptions (KeyboardInterrupt, SystemExit, GeneratorExit) reach
            # this one. If the caller passed a shutdown signal (original_exc is a BaseException),
            # chain it via `from cleanup_exc` so the original shutdown signal is preserved as the
            # primary exception and the cleanup interruption becomes __cause__. Otherwise raise
            # the cleanup signal verbatim.
            #
            # Alternative rejected: catching BaseException BEFORE Exception — would intercept all
            # Exceptions too, breaking the Exception handler's __cause__ logic. Must order
            # Exception first (more specific) then BaseException (catch-all).
            if original_exc is not None and isinstance(original_exc, BaseException):
                raise original_exc from cleanup_exc
            raise
        # FIX-2 (Plan-24): When cleanup completes normally (no exception), the
        # original exception that triggered cleanup MUST still propagate to the
        # caller. The pre-fix code returned None here, swallowing the exception
        # (e.g. a RuntimeError from scheduler.start()) and letting start()
        # return normally -- exactly the behaviour test_scheduler_started_flag_true_before_scheduler_start
        # asserts against. Re-raise original_exc verbatim so the caller observes
        # the cancellation/exception it expected.
        if original_exc is not None:
            raise original_exc

    async def _cleanup_partial_start(self) -> None:
        """Mirror stop() for partially-started modules on failure.

        MUTual EXCLUSION: This method does NOT acquire self._lifecycle_lock.
        It is only ever called from start() (the sole call site is start's
        cleanup block), which already holds the lock for the entire start+cleanup
        window via `async with self._lifecycle_lock:` at line 77.

        stop() acquires the SAME lock. Therefore start() and stop() can never
        run their cleanup concurrently. The _started flag check in stop() is a
        fast-path optimization; the lock is the synchronization primitive.
        """
        errors: list[Exception] = []
        # BUG-2 (Plan-11 Phase 2) — scheduler unregistration BEFORE module cleanup.
        #
        # `start()` registers every module with the scheduler via
        # `module_manager.load_from_config()` BEFORE `init_spi_bus()` runs (line 73).
        # When `init_spi_bus()` fails, the module is registered in the scheduler but
        # is NOT appended to `self._started_modules` (the append happens only after
        # `init_spi_bus()` succeeds, after line 83). `_cleanup_partial_start()`
        # iterates only `self._started_modules`, so without this loop the scheduler
        # retains a dangling module reference: its `_registered` set, `_intervals`
        # map, and any pending timer task still point at a module whose SPI bus was
        # never opened and whose event loop never ran. Those lingering timer tasks
        # are a resource leak — the module object keeps a live reference in
        # `_tasks` and the IdlePacer / InterruptBridge maps keep stale entries, so
        # the module can never be garbage-collected and its timer task keeps the
        # scheduler bound after cleanup.
        #
        # This loop mirrors `stop()`'s first pass (unregister every module before
        # draining), which is the correct inverse of `load_from_config()`'s
        # registration. Option A (unregister here) is chosen over Option B
        # (defer scheduler registration until after `init_spi_bus()` succeeds — a
        # larger refactor that reorders `start()`'s phases) because it is localized,
        # idempotent (`unregister_module` uses `discard`/`pop`), and matches the
        # established `stop()` contract; Option B risks regressing the SPI-init
        # tracking invariant that `test_start_event_loop_failure_still_tracked_for_cleanup`
        # depends on.
        for module in self.module_manager.get_all_modules():
            try:
                await self.scheduler.unregister_module(module)
            except ExceptionGroup as eg:
                errors.extend(eg.exceptions)
            except Exception as exc:
                logger.exception(
                    "scheduler.unregister_module failed for SPI device=%s CE=%s",
                    module.get_spi_device_id(),
                    module.get_ce_number(),
                )
                errors.append(exc)
        # Location 4 (Plan-18 §6 anti-regression). Clean ALL modules from
        # module_manager.get_all_modules(), not just self._started_modules.
        # NOTE: the attribute is self.module_manager (NOT self._module_manager --
        # that attribute does not exist and would raise AttributeError at runtime).
        # Handles modules committed before any exception, including CancelledError:
        # Plan-17 H-16-1 committed on CancelledError, and those modules live in
        # get_all_modules() but are absent from _started_modules, so iterating only
        # _started_modules leaked them. The caller owns cleanup after any
        # exception; this mirrors stop()'s get_all_modules() contract.
        for module in self.module_manager.get_all_modules():
            try:
                await module.stop_event_loop(StopMode.DRAIN)
            except Exception as exc:
                logger.exception(
                    "stop_event_loop failed for SPI device=%s CE=%s",
                    module.get_spi_device_id(),
                    module.get_ce_number(),
                )
                errors.append(exc)
            try:
                await module.close_spi()
            except Exception as exc:
                logger.exception(
                    "close_spi failed for SPI device=%s CE=%s",
                    module.get_spi_device_id(),
                    module.get_ce_number(),
                )
                errors.append(exc)
        if self._scheduler_started:
            try:
                await self.scheduler.stop()
            except Exception as exc:
                logger.exception("scheduler.stop() failed during cleanup")
                errors.append(exc)
        self._started_modules.clear()
        self._scheduler_started = False
        if errors:
            raise ExceptionGroup("Errors during Application cleanup", errors)

    async def run_blocking_command(self, cmd: Any) -> Any:
        """Execute *cmd* synchronously via CommandBus.execute()."""
        return await self.command_bus.execute(cmd)

    async def run_async_command(self, cmd: Any) -> None:
        """Dispatch *cmd* asynchronously via CommandBus.dispatch()."""
        await self.command_bus.dispatch(cmd)

    def get_status(self) -> dict[str, Any]:
        """Return a snapshot of all managed module states."""
        return {
            "modules": [
                {
                    "spi_device_id": m.get_spi_device_id(),
                    "ce_number": m.get_ce_number(),
                    "state": m.get_current_state_name(),
                    "queue_size": m.get_event_queue_size(),
                }
                for m in self.module_manager.get_all_modules()
            ]
        }

    def _resolve_module_for_command(self, command: Any) -> Any:
        """Resolve a command's target to its Rfm9xSx127xModule."""
        target = getattr(command, "target", None)
        if target == "all":
            all_modules = self.module_manager.get_all_modules()
            return all_modules[0] if all_modules else None
        elif isinstance(target, tuple) and len(target) == 2:
            result = self.module_manager.get_module(target[0], target[1])
            if result is not None:
                return result
            raise ValueError(f"No module for target {target}")
        raise ValueError(f"Invalid command target: {target}")

    async def _load_config(self, config_path: Path | None = None) -> "Rfm9xSx127xConfig":
        """Load configuration, caching it for subsequent calls.

        Args:
            config_path: Optional custom config file path (forces reload).

        Returns:
            The loaded Rfm9xSx127xConfig instance.
        """
        # PLAN-26 FIX (Findings 744, 754): Protect config cache with lock to prevent
        # race between concurrent _load_config/reload_config calls with different
        # config_path values.
        async with self._config_lock:
            if config_path is not None:
                config = await get_preloaded_config(config_path=config_path)
                self._config_path = config_path
                self._config = config
                return config

            if self._config is not None:
                return self._config

            config = await get_preloaded_config()
            self._config = config
            return config

    async def reload_config(self, config_path: Path | None = None) -> "Rfm9xSx127xConfig":
        """Force reload configuration.

        Args:
            config_path: Optional custom config file path.

        Returns:
            The reloaded Rfm9xSx127xConfig instance.
        """
        # PLAN-26 FIX (Findings 744, 754): Protect config cache with lock to prevent
        # race between concurrent _load_config/reload_config calls with different
        # config_path values.
        async with self._config_lock:
            config = await get_preloaded_config(force_reload=True, config_path=config_path)
            self._config_path = config_path
            self._config = config
            return config

    async def list_assemblies(self, verbose: bool = False, config_path: str | Path | None = None) -> list[dict[str, Any]]:
        """Return list of available assemblies.

        Args:
            verbose: If True, include module_name and device_count for each assembly.

        Returns:
            List of dicts with assembly info.
        """
        resolved_path: Path | None = Path(config_path) if isinstance(config_path, str) else config_path
        config = await self._load_config(resolved_path)
        results: list[dict[str, Any]] = []
        for assembly_name, assembly in config.assemblies.items():
            if verbose:
                results.append({
                    "assembly_name": assembly_name,
                    "module_name": assembly.module_name,
                    "device_count": len(assembly.devices),
                })
            else:
                results.append({"assembly_name": assembly_name})
        return results

    async def get_assembly_config(
        self,
        assembly_name: str,
        spi_device_id: int | None = None,
        ce_number: int | None = None,
        config_path: Path | None = None,
    ) -> RadioInstanceConfig | list[RadioInstanceConfig]:
        """Get RadioInstanceConfig(s) for an assembly.

        Args:
            assembly_name: Name of the assembly to query.
            spi_device_id: Optional SPI device ID to filter.
            ce_number: Optional CE number to filter.
            config_path: Optional custom config file path (forces reload).

        Returns:
            Single RadioInstanceConfig if both spi_device_id and ce_number provided,
            otherwise list of all RadioInstanceConfigs for the assembly.

        Raises:
            AssemblyNotFoundError: If assembly not found.
            DeviceAttachmentNotFoundError: If SPI/CE filter doesn't match any device.
        """
        config = await self._load_config(config_path)

        if assembly_name not in config.assemblies:
            raise AssemblyNotFoundError(f"Assembly '{assembly_name}' not found in configuration")

        assembly = config.assemblies[assembly_name]
        module_name = assembly.module_name

        if module_name not in config.modules:
            raise AssemblyNotFoundError(f"Module '{module_name}' for assembly '{assembly_name}' not found")

        module_obj = config.modules[module_name]

        configs: list[RadioInstanceConfig] = []
        for attachment in module_obj.devices:
            # Anti-Regression (Plan-24 Fix 3): `create_radio_instance` can raise six
            # driver exception types. Only `DriverDeviceAttachmentNotFoundError` is a
            # "skip this attachment" case (the SPI/CE simply does not match this
            # attachment). The other five — `DriverAssemblyNotFoundError`,
            # `DriverModuleNotFoundError`, `DeviceSpecNotFoundError`,
            # `FamilyNotFoundError`, and `ConfigConsistencyError` — indicate config
            # corruption and MUST be translated to framework exceptions
            # (`AssemblyNotFoundError`, `ConfigLoadError`) so callers can handle them
            # appropriately. This mirrors the canonical exception-handling convention
            # (driver exceptions are internal; framework exceptions are the public
            # contract surfaced to callers).
            try:
                radio_config = await create_radio_instance(
                    assembly_name=assembly_name,
                    spi_device_id=attachment.spi_device_id,
                    ce_number=attachment.ce_number,
                    config=config,
                )
                configs.append(radio_config)
            except DriverDeviceAttachmentNotFoundError:
                continue
            except DriverAssemblyNotFoundError as e:
                raise AssemblyNotFoundError(str(e)) from e
            except (DriverModuleNotFoundError, DeviceSpecNotFoundError, FamilyNotFoundError, ConfigConsistencyError) as e:
                raise ConfigLoadError(str(e)) from e

        if not configs:
            raise DeviceAttachmentNotFoundError(
                module_name,
                spi_device_id if spi_device_id is not None else -1,
                ce_number if ce_number is not None else -1,
            )

        if spi_device_id is not None and ce_number is not None:
            for cfg in configs:
                if cfg.spi_device_id == spi_device_id and cfg.ce_number == ce_number:
                    return cfg
            raise DeviceAttachmentNotFoundError(
                module_name, spi_device_id, ce_number
            )

        return configs
