import inspect
import pytest

mp = pytest.MonkeyPatch.__name__
print("monkeypatch fixture class name:", mp)

from _pytest.monkeypatch import MonkeyPatch
print("has dict:", hasattr(MonkeyPatch, "dict"))
print("methods:", [m for m in dir(MonkeyPatch) if not m.startswith("_")])
