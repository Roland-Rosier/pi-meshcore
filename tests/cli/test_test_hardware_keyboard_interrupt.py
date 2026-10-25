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

"""R-1 regression test for ``src/pi_lora/cli/test.py::test_hardware_impl``.

R-1 changed the cleanup guard from ``except BaseException`` to ``except
Exception``. ``KeyboardInterrupt``, ``SystemExit`` and ``GeneratorExit`` are
``BaseException`` subclasses (PEP 3134 control-flow signals) and must NOT be
caught by the cleanup handler so they propagate to the interpreter; they must
still be allowed through the ``finally`` that always calls ``application.stop()``.
These tests assert that ``stop()`` runs even when ``Application.start`` raises a
non-``Exception`` signal, and that a normal ``Exception`` is caught and handled
while ``stop()`` still executes.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import src.pi_lora.cli.test as _test_cmd


def _mock_app(*, start_effect: BaseException) -> Any:
    """Build a patched ``Application`` that reaches ``start()``.

    ``get_assembly_config`` returns a truthy value so the function proceeds past
    the "no modules match" guard to ``application.start()``; ``stop`` is a fresh
    ``AsyncMock`` that does not raise, guaranteeing cleanup runs once.
    """
    mock_app: Any = AsyncMock()
    mock_app.get_assembly_config.return_value = ["dummy"]
    mock_app.start.side_effect = start_effect
    mock_app.stop = AsyncMock()
    return mock_app


class TestControlFlowSignals:
    @pytest.mark.asyncio
    async def test_keyboard_interrupt_propagates_through_cleanup(self) -> None:
        """KeyboardInterrupt is not caught by ``except Exception``; stop() still runs."""
        with patch("src.pi_lora.cli.test.Application") as mock_app_class:
            mock_app = _mock_app(start_effect=KeyboardInterrupt("User cancelled"))
            mock_app_class.return_value = mock_app
            with pytest.raises(KeyboardInterrupt):
                await _test_cmd.test_hardware_impl(assembly_name="test")
            mock_app.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_system_exit_propagates_through_cleanup(self) -> None:
        """SystemExit is not caught by ``except Exception``; stop() still runs."""
        with patch("src.pi_lora.cli.test.Application") as mock_app_class:
            mock_app = _mock_app(start_effect=SystemExit(1))
            mock_app_class.return_value = mock_app
            with pytest.raises(SystemExit):
                await _test_cmd.test_hardware_impl(assembly_name="test")
            mock_app.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_normal_exception_is_caught_and_handled(self) -> None:
        """RuntimeError is caught by ``except Exception``; stop() still runs."""
        with patch("src.pi_lora.cli.test.Application") as mock_app_class:
            mock_app = _mock_app(start_effect=RuntimeError("normal error"))
            mock_app_class.return_value = mock_app
            with pytest.raises(RuntimeError):
                await _test_cmd.test_hardware_impl(assembly_name="test")
            mock_app.stop.assert_called_once()


if __name__ == "__main__":
    import sys

    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
