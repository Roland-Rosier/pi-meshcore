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

"""Entry-point wrapper tests for ``pi_lora.cli._entry_points`` (Phase 1).

The console scripts now resolve through thin wrappers that invoke the
underlying ``app`` directly. ``async_typer.AsyncTyper`` subclasses
``typer.Typer`` and wraps async command bodies with a synchronous runner, so
``app()`` already drives the event loop and returns a Click exit code rather
than a bare coroutine. Each wrapper therefore runs the CLI via ``sys.argv`` and
exits cleanly without leaving a coroutine un-awaited.
"""

from __future__ import annotations

import sys
import warnings
from typing import Any

import pytest

from pi_lora.cli._entry_points import (
    check_hardware,
    pi_lora,
    pi_lora_config,
    pi_lora_test,
)

_ENTRY_POINT_CALLS: dict[str, tuple[Any, list[str]]] = {
    "pi_lora": (pi_lora, ["pi-lora", "--help"]),
    "pi_lora_config": (pi_lora_config, ["config", "--help"]),
    "pi_lora_test": (pi_lora_test, ["pi-lora-test", "--help"]),
    "check_hardware": (check_hardware, ["check-hardware", "--help"]),
}


@pytest.mark.parametrize("name", list(_ENTRY_POINT_CALLS))
def test_entry_point_runs_cli_and_exits_cleanly(name: str) -> None:
    """Each entry-point wrapper runs the CLI via ``sys.argv`` and exits cleanly.

    The wrappers invoke ``app()`` directly (which reads ``sys.argv``), so the
    CLI renders its ``--help`` output and returns exit code ``0``. No
    ``RuntimeWarning`` about a never-awaited coroutine is emitted.
    """
    target: Any
    argv: list[str]
    target, argv = _ENTRY_POINT_CALLS[name]
    _old_argv: list[str] = sys.argv
    sys.argv = argv
    try:
        with warnings.catch_warnings(record=True) as _log:
            warnings.simplefilter("always")
            try:
                _code: Any = target()
            except SystemExit as _exc:
                _code = _exc.code
            _warnings: list[str] = [str(_w) for _w in _log]
    finally:
        sys.argv = _old_argv

    assert isinstance(_code, int), f"{name} did not return an int exit code"
    assert _code == 0, f"{name} --help should exit 0, got {_code}"
    for _note in _warnings:
        _lowered = _note.lower()
        assert "never awaited" not in _lowered, _note
        assert "coroutine" not in _lowered, _note


def test_check_hardware_entry_point_invalid_input_rejected() -> None:
    """``check_hardware()`` entry point rejects invalid input (FIX CR-7).

    The wrapper performs ``cast(int, check_hardware_app())``. With AsyncTyper the
    app drives the async body through a synchronous runner and returns a genuine
    Click exit code, so ``--ce0 invalid`` yields a non-zero exit code (Click reports
    ``2`` for ``typer.BadParameter``) instead of the pre-fix ``0`` that silently
    accepted rejected input. The rejected alternative (a ``cast`` hack over a sync
    Typer returning ``None``) would have yielded exit code 0.
    """
    _old_argv: list[str] = sys.argv
    sys.argv = ["check-hardware", "detect-modules", "--ce0", "invalid"]
    try:
        with warnings.catch_warnings(record=True) as _log:
            warnings.simplefilter("always")
            try:
                _code: Any = check_hardware()
            except SystemExit as _exc:
                _code = _exc.code
            _warnings: list[str] = [str(_w) for _w in _log]
    finally:
        sys.argv = _old_argv

    assert isinstance(_code, int), "check_hardware did not return an int exit code"
    assert _code != 0, f"check-hardware --ce0 invalid should reject input, got {_code}"
    for _note in _warnings:
        _lowered = _note.lower()
        assert "never awaited" not in _lowered, _note
        assert "coroutine" not in _lowered, _note


def test_entry_points_expose_all_four_wrappers() -> None:
    """The module exposes exactly the four console entry-point wrappers."""
    import pi_lora.cli._entry_points as _ep

    for _name in ("pi_lora", "pi_lora_config", "pi_lora_test", "check_hardware"):
        assert hasattr(_ep, _name), f"missing entry-point wrapper {_name}"


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
