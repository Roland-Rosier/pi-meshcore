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
# WITHOUT WARRANTIES OR CONDITIONS of ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""NR-3 regression: sync CLI imports succeed without aiologic installed.

The ``spi/locks.py`` module must NOT import ``aiologic`` at module scope
(otherwise importing it transitively via ``bus.py`` -> ``factory.py`` -> the
sync CLI commands triggers an ``aiologic`` import-time failure, which is BUG-4).
These tests pin that behaviour.
"""

import sys

import pytest


def test_sync_cli_imports_without_aiologic(monkeypatch: pytest.FixtureRequest) -> None:
    monkeypatch.setitem(sys.modules, 'aiologic', None)
    from pi_lora.cli.config import app as config_app
    from pi_lora.cli.main import app as main_app
    # Import succeeds — no module-level aiologic import triggered anywhere.
    assert config_app is not None
    assert main_app is not None


def test_importing_locks_without_aiologic(monkeypatch: pytest.FixtureRequest) -> None:
    monkeypatch.setitem(sys.modules, 'aiologic', None)
    # Importing spi/locks.py must not raise even when aiologic is unavailable.
    from pi_lora.drivers.spi import locks
    assert locks.get_bus_lock is not None


@pytest.mark.asyncio
async def test_get_bus_lock_with_aiologic_present() -> None:
    # Real import of aiologic (NOT monkeypatched None) in this test.
    import aiologic

    from pi_lora.drivers.spi.locks import _GuardedLock, get_bus_lock
    lock = await get_bus_lock(0)
    # get_bus_lock now returns a _GuardedLock wrapper around an aiologic.Lock.
    assert isinstance(lock, _GuardedLock)
    assert isinstance(lock._lock, aiologic.Lock)
