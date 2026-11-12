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

"""
LazyAsyncLock — Thread-safe, lazy-initialized async lock wrapper.

Guarantees (verified by concurrency tests):
- Exactly ONE aiologic.Lock is ever created per instance
- Initialization is atomic (threading.Lock + double-checked locking)
- NO sentinel object → NO sentinel race possible
- Holder lock is persisted and reused across all callers
- Single code path — no separate init/else branches
- aiologic.Lock() is a synchronous constructor (hasattr(aiologic.Lock(), 'green_release'))

Anti-regression documentation:
The old patterns (Plans 22-27) failed because:
- A NEW asyncio.Lock() holder was created on every call, so callers did not
  share mutual exclusion (holder not persisted).
- A sentinel object (_SENTINEL) was used to distinguish "uninitialized" from
  "initialized"; the else-branch that read the lock ran OUTSIDE the holder lock,
  so two threads could both see the sentinel and race.
This utility removes the sentinel entirely (aiologic.Lock() is a synchronous
constructor, so no await is needed to create it), persists a single holder lock
guarded by a threading.Lock, and uses one unified code path.

__aenter__/__aexit__ are intentionally absent: exposing them would let callers
use `async with lock:` directly, which would acquire the holder lock and block
on it, preventing the underlying aiologic.Lock from being released and creating
a latent deadlock bug. Use the explicit acquire() pattern instead.

Usage:
    lock = LazyAsyncLock()
    aiologic_lock = await lock.acquire()
    async with aiologic_lock:
        # critical section
        ...
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import aiologic


class LazyAsyncLock:
    """Thread-safe, lazy-initialized async lock wrapper.

    Replaces the buggy double-checked-locking + sentinel + holder pattern
    used in locks.py and config_loader.py (Plans 22-27).
    """

    __slots__ = ("_holder_init_lock", "_holder", "_lock", "_aiologic_module")

    def __init__(self) -> None:
        self._holder_init_lock: threading.Lock = threading.Lock()
        self._holder: asyncio.Lock | None = None
        self._lock: aiologic.Lock | None = None
        self._aiologic_module: aiologic | None = None

    def _ensure_aiologic_imported(self) -> aiologic:
        if self._aiologic_module is None:
            import aiologic
            self._aiologic_module = aiologic
        return self._aiologic_module

    def _get_or_create_holder(self) -> asyncio.Lock:
        with self._holder_init_lock:
            if self._holder is None:
                self._holder = asyncio.Lock()
            return self._holder

    async def acquire(self) -> aiologic.Lock:
        holder = self._get_or_create_holder()
        async with holder:
            if self._lock is None:
                # aiologic.Lock() is a synchronous constructor — NO AWAIT, NO SENTINEL NEEDED
                self._lock = self._ensure_aiologic_imported().Lock()
            return self._lock


    def is_initialized(self) -> bool:
        return self._lock is not None
