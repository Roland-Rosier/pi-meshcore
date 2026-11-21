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

"""Dependency resolution tests — async-typer / typer version compatibility.

Phase 9 verifies that ``async-typer==0.27.2`` and ``typer[all]==0.27.2`` resolve
to a single consistent ``typer`` version under ``uv``'s constraint solver. The
``async-typer`` 0.27.2 package declares ``typer<0.28.0,>=0.27.2``, which accepts
the pinned ``typer 0.27.2``. This suite locks that compatibility in.
"""

from __future__ import annotations

import importlib.metadata as im
import re
import tomllib
from pathlib import Path

import pytest

_CLAUSE_RE: re.Pattern[str] = re.compile(r"^(<=|>=|==|!=|<|>)(.+)$")
_DEPEND_RE: re.Pattern[str] = re.compile(r"^\s*([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(.*)$")
_NAME_RE: re.Pattern[str] = re.compile(r"^([A-Za-z0-9._-]+)(.*)$")
_VERSION_RE: re.Pattern[str] = re.compile(r"\d+(?:\.\d+)*")


def _load_dependencies() -> dict[str, str]:
    """Return a mapping of dependency name to specifier from ``pyproject.toml``."""
    root: Path = Path(__file__).parent.parent
    pyproject_path: Path = root.joinpath("pyproject.toml")
    with pyproject_path.open(mode="rb") as handle:
        data: dict[str, object] = tomllib.load(handle)
    project: dict[str, object] = data["project"]
    raw_deps: list[str] = project["dependencies"]
    result: dict[str, str] = {}
    for spec in raw_deps:
        match: re.Match[str] | None = _DEPEND_RE.match(spec)
        if not match:
            continue
        name: str = match.group(1)
        specifier: str = match.group(2).strip()
        result[name] = specifier
    return result


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a dotted version string into a tuple of integers."""
    return tuple(int(part) for part in version.split("."))


def _pinned_version(specifier: str) -> tuple[int, ...] | None:
    """Extract the first pinned version number from a specifier string."""
    found: list[str] = _VERSION_RE.findall(specifier)
    if not found:
        return None
    return _parse_version(found[0])


def _clause_satisfied(
    operator: str,
    bound: tuple[int, ...],
    pinned: tuple[int, ...],
) -> bool:
    """Return whether ``pinned`` satisfies a single specifier clause."""
    match operator:
        case ">=":
            return pinned >= bound
        case ">":
            return pinned > bound
        case "<=":
            return pinned <= bound
        case "<":
            return pinned < bound
        case "==":
            return pinned == bound
        case _:
            raise ValueError(f"Unsupported specifier operator {operator!r}")


def _typer_constraint_satisfied(
    requirements: list[str] | None,
    pinned: tuple[int, ...],
) -> bool:
    """Return whether every ``typer`` clause in ``requirements`` accepts ``pinned``."""
    if not requirements:
        return False
    for requirement in requirements:
        marker_part: str = requirement.split(";", 1)[0]
        name_match: re.Match[str] | None = _NAME_RE.match(marker_part)
        if not name_match:
            continue
        name: str = name_match.group(1)
        if name.lower() != "typer":
            continue
        specifier: str = name_match.group(2).strip()
        for clause in specifier.split(","):
            stripped: str = clause.strip()
            if not stripped:
                continue
            clause_match: re.Match[str] | None = _CLAUSE_RE.match(stripped)
            if not clause_match:
                continue
            operator: str = clause_match.group(1)
            version: str = clause_match.group(2).strip()
            bound: tuple[int, ...] = _parse_version(version)
            if not _clause_satisfied(operator, bound, pinned):
                return False
    return True


def _import_module(module_name: str) -> object:
    """Import and return a module by its (possibly hyphenated) name."""
    return __import__(module_name.replace("-", "_"))


class TestDependencyResolution:
    """Verify async-typer and typer resolve to a single consistent version."""

    def test_typer_and_async_typer_pinned(self) -> None:
        """Both ``typer`` and ``async-typer`` must be pinned in the dependency set."""
        deps: dict[str, str] = _load_dependencies()
        assert "typer" in deps
        assert "async-typer" in deps

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("typer", (0, 27, 2)),
            ("async-typer", (0, 27, 2)),
        ],
    )
    def test_pinned_versions(self, name: str, expected: tuple[int, ...]) -> None:
        """Each pinned dependency must resolve to its declared version."""
        deps = _load_dependencies()
        assert name in deps
        specifier: str = deps[name]
        pinned: tuple[int, ...] | None = _pinned_version(specifier)
        assert pinned == expected

    def test_async_typer_installed_matches_pin(self) -> None:
        """The installed ``async-typer`` version must match the ``pyproject`` pin."""
        deps = _load_dependencies()
        pinned: tuple[int, ...] | None = _pinned_version(deps["async-typer"])
        assert pinned is not None
        installed: str | None = im.version("async_typer")
        assert installed is not None
        assert _parse_version(installed) == pinned

    def test_async_typer_requirement_satisfied_by_pin(self) -> None:
        """``async-typer``'s declared ``typer`` constraint must accept the pin."""
        deps = _load_dependencies()
        pinned_typer: tuple[int, ...] | None = _pinned_version(deps["typer"])
        assert pinned_typer is not None
        requirements: list[str] | None = im.requires("async_typer")
        assert _typer_constraint_satisfied(requirements, pinned_typer)

    def test_no_typer_version_conflict(self) -> None:
        """``async-typer`` and the ``typer`` pin resolve without contradiction."""
        deps = _load_dependencies()
        pinned_typer = _pinned_version(deps["typer"])
        assert pinned_typer is not None
        pinned_async = _pinned_version(deps["async-typer"])
        assert pinned_async is not None
        installed_async: str | None = im.version("async_typer")
        assert installed_async is not None
        if _parse_version(installed_async) == pinned_async:
            requirements = im.requires("async_typer")
            assert _typer_constraint_satisfied(requirements, pinned_typer)

    def test_installed_typer_matches_pin(self) -> None:
        """The installed ``typer`` version must equal the ``pyproject`` pin (0.27.2).

        This locks in that the resolved environment ships the pinned ``typer
        0.27.2`` rather than merely satisfying ``async-typer``'s constraint
        abstractly — both the pin and the installed version are 0.27.2.
        """
        deps = _load_dependencies()
        pinned_typer: tuple[int, ...] | None = _pinned_version(deps["typer"])
        assert pinned_typer is not None
        installed: str | None = im.version("typer")
        assert installed is not None
        assert _parse_version(installed) == pinned_typer


class TestRuntimeImports:
    """Both packages must import cleanly at runtime."""

    def test_async_typer_imports(self) -> None:
        """``async_typer`` must import cleanly into the resolved environment."""
        module: object = _import_module("async_typer")
        assert module is not None

    def test_typer_imports(self) -> None:
        """``typer`` must import cleanly into the resolved environment."""
        module: object = _import_module("typer")
        assert module is not None
