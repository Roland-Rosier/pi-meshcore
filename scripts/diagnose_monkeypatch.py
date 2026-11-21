#!/usr/bin/env python3
"""Diagnose the monkeypatch fixture class exposed by pytest.

Usage:
    uv run python scripts/diagnose_monkeypatch.py
"""
import pytest
from _pytest.monkeypatch import MonkeyPatch


def diagnose() -> None:
    """Print the monkeypatch fixture class name and its public surface."""
    mp = pytest.MonkeyPatch.__name__
    print("monkeypatch fixture class name:", mp)
    print("has dict:", hasattr(MonkeyPatch, "dict"))
    print("methods:", [m for m in dir(MonkeyPatch) if not m.startswith("_")])


if __name__ == "__main__":
    diagnose()
