# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared logging setup for the ``pi_lora.cli`` sub-apps.

This module is the single source of truth for CLI logging configuration. It
intentionly imports nothing from ``main``, ``test``, ``check_hardware``, or
``config`` so that those sub-apps can import :func:`setup_logging` without
creating a circular import.
"""

from __future__ import annotations

import logging
import os


def setup_logging() -> None:
    """Configure root logger using ``PI_LORA_LOG_LEVEL`` environment variable. Idempotent."""
    log_level = os.environ.get("PI_LORA_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _ensure_logged() -> None:
    """Convenience wrapper that delegates to the shared :func:`setup_logging`."""
    setup_logging()
