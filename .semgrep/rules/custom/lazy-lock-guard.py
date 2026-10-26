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

"""Example for the `lazy-lock-without-guard` semgrep rule (see .semgrep/rules/custom/lazy-lock-guard.yaml).

This file is a semgrep rule self-test example. It is intentionally NOT scanned
by `.semgrep/run.sh` (its targets exclude `.semgrep/rules/*`); the `# ruleid:`
and `# ok:` annotations are consumed only by semgrep's rule validation mode.
"""

from __future__ import annotations

import asyncio

import aiologic

_registry_lock: object = None
_registry_guard: asyncio.Lock = asyncio.Lock()


def get_registry_lock_bad() -> object:
    """BUG: the lock is created directly with no guard lock (race condition)."""
    # ruleid:lazy-lock-without-guard
    if _registry_lock is None:
        _registry_lock = aiologic.Lock()
        ...
    async with _registry_lock:
        return _registry_lock


def get_registry_lock_good() -> object:
    """OK: double-checked locking guarded by a module-level asyncio.Lock."""
    if _registry_lock is None:
        async with _registry_guard:
            if _registry_lock is None:
                _registry_lock = aiologic.Lock()
    # ok:lazy-lock-without-guard
    async with _registry_lock:
        return _registry_lock
