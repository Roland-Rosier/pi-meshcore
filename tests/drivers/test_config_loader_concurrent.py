# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# you may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""Concurrency regression test for the config_loader LazyAsyncLock guard (NR-1)."""

import asyncio
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_get_preloaded_config_concurrent() -> None:
    """100 concurrent coroutines must create exactly one aiologic.Lock.

    Verifies the race-free asyncio.Lock guard introduced by NR-1: launching many
    concurrent ``get_preloaded_config`` calls must materialise a single
    ``aiologic.Lock`` (double-checked locking) and every caller must receive the
    same cached instance.
    """
    import aiologic

    import pi_lora.drivers.rfm9x_sx127x_config_loader as loader

    loader._config_cache = None
    loader._config_lock._lock = None  # force a fresh aiologic.Lock creation
    counter = {"locks": 0}
    real_lock_cls: type = aiologic.Lock

    def _counting_lock() -> object:
        counter["locks"] += 1
        return real_lock_cls()

    with patch.object(aiologic, "Lock", _counting_lock):

        async def _caller() -> object:
            return await loader.get_preloaded_config()

        results = await asyncio.gather(
            *[_caller() for _ in range(100)], return_exceptions=True
        )

    assert counter["locks"] == 1, (
        "exactly one aiologic.Lock must be created under concurrency"
    )
    assert all(r is results[0] for r in results), (
        "all callers must receive the same cached instance"
    )
