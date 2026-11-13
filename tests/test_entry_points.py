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

import pathlib
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


def test_system_exit_none_maps_to_zero() -> None:
    """``SystemExit(None)`` maps to exit code 0 (FIX CR-29-1).

    In Unix/Click/Typer a bare ``SystemExit(None)`` signals a *successful* exit
    and must resolve to code ``0``, not ``1``. This exercises the ``--help`` path
    (which the underlying Typer raises as ``SystemExit(None)``) through a real
    wrapper and asserts the returned exit code is ``0``.
    """
    _old_argv: list[str] = sys.argv
    sys.argv = ["pi-lora", "--help"]
    try:
        _code: Any = pi_lora()
    finally:
        sys.argv = _old_argv

    assert isinstance(_code, int), "pi_lora did not return an int exit code"
    assert _code == 0, f"SystemExit(None) must map to 0, got {_code}"


def test_system_exit_fallback_logic() -> None:
    """Direct unit test of the ``SystemExit`` fallback used by the wrappers.

    Mirrors the handler in ``src/pi_lora/cli/_entry_points``: an int code is
    returned verbatim, while a non-int (including ``None``) falls back to ``0``
    (successful exit in Unix/Click/Typer), never ``1``.
    """

    def _handler(e: SystemExit) -> int:
        # PLAN-30 FIX (CR-29-1): SystemExit(None) = successful exit (code 0) in Unix/Click/Typer.
        # Fallback to 0, not 1. See plan-30.md Section 1.
        return e.code if isinstance(e.code, int) else 0

    assert _handler(SystemExit(None)) == 0
    assert _handler(SystemExit(0)) == 0
    assert _handler(SystemExit(2)) == 2


def test_entry_points_expose_all_four_wrappers() -> None:
    """The module exposes exactly the four console entry-point wrappers."""
    import pi_lora.cli._entry_points as _ep

    for _name in ("pi_lora", "pi_lora_config", "pi_lora_test", "check_hardware"):
        assert hasattr(_ep, _name), f"missing entry-point wrapper {_name}"


def _locate_workspace_pyproject() -> pathlib.Path:
    """Return the workspace-root ``pyproject.toml`` path.

    ``pyproject.toml`` lives at the workspace root as a sibling of the test
    package, so the helper walks up parents until a directory that itself
    contains a ``pyproject.toml`` file is found. ``pathlib.Path.parent`` of a
    root path returns the same path, so the walk terminates without recursion.
    """
    _current: pathlib.Path = pathlib.Path(__file__).parent
    while True:
        _candidate: pathlib.Path = _current.joinpath("pyproject.toml")
        if _candidate.exists():
            return _candidate
        _parent: pathlib.Path = _current.parent
        if _parent is _current:
            return _candidate
        _current = _parent


def _extract_project_scripts_fallback(_raw: str) -> dict[str, str]:
    """Extract ``[project.scripts]`` via line scanning when ``tomllib`` is absent.

    Robust string extraction: locate the ``[project.scripts]`` header, then read
    ``key = value`` pairs until a new TOMl table header (``[``) or the end of
    the file. Inline ``#`` comments and blank lines are skipped; value quotes
    are stripped. This is the interpreter < 3.11 fallback path only.
    """
    _scripts: dict[str, str] = {}
    _in_block: bool = False
    for _line in _raw.splitlines():
        _stripped: str = _line.strip()
        if not _in_block:
            _in_block = _stripped == "[project.scripts]"
            continue
        if _stripped.startswith("[") and _stripped != "[project.scripts]":
            break
        if not _stripped or _stripped.startswith("#"):
            continue
        _key, _sep, _value = _line.partition("=")
        if _sep:
            _scripts[_key.strip()] = _value.strip().strip('"').strip("'")
    return _scripts


def _read_project_scripts() -> dict[str, str]:
    """Return the ``[project.scripts]`` mapping from the workspace ``pyproject.toml``.

    Prefers ``tomllib`` (stdlib on a 3.11+ interpreter, which is the current
    interpreter); falls back to a robust line-scanning extraction when
    ``tomllib`` is unavailable. The package is not installed (no ``dist``/
    ``egg-info``), so console scripts cannot be resolved via
    ``importlib.metadata.scripts`` without first building a wheel — the mapping
    is therefore verified statically against the TOMl file itself.
    """
    _path: pathlib.Path = _locate_workspace_pyproject()
    with _path.open() as _fh:
        _raw: str = _fh.read()
    try:
        import tomllib
    except ModuleNotFoundError:
        return _extract_project_scripts_fallback(_raw)
    _parsed: dict[str, Any] = tomllib.loads(_raw)
    _scripts: Any = _parsed.get("project", {}).get("scripts", {})
    return dict(_scripts)


def test_project_scripts_maps_pi_lora_config_and_excludes_config() -> None:
    """The packaging-level ``[project.scripts]`` maps ``pi-lora-config`` and omits ``config``.

    Item 8 of Plan-22 Section 5: ``pi-lora-config`` is the console entry point
    (``pi_lora.cli._entry_points:pi_lora_config``) and the old ``config`` name is
    intentionally NOT aliased. The package is not installed, so the mapping is
    verified statically against ``pyproject.toml`` via ``tomllib``. The
    ``pi-lora-config`` entry must resolve to ``pi_lora.cli._entry_points:pi_lora_config``
    and no ``config`` entry must exist.
    """
    _scripts: dict[str, str] = _read_project_scripts()

    assert "pi-lora-config" in _scripts, "pi-lora-config must be a project script"
    assert _scripts["pi-lora-config"] == "pi_lora.cli._entry_points:pi_lora_config"

    assert "config" not in _scripts, "old 'config' name must not be aliased"


if __name__ == "__main__":
    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
