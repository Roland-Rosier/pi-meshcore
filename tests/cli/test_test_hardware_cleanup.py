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

"""NR-4 regression test for ``src/pi_lora/cli/test.py::test_hardware_impl``.

``typer.Exit`` subclasses ``BaseException``, not ``Exception``. Fix NR-4 wraps
``test_hardware_impl`` in a single ``try`` whose ``finally`` always calls
``application.stop()`` and whose ``except BaseException`` re-raises any exception
after cleanup. This test asserts that ``stop()`` runs even when
``Application.start`` raises ``typer.Exit`` — the exact bug NR-4 fixes, where the
old ``except Exception`` around ``start()`` never caught ``typer.Exit`` and the
cleanup ``finally`` was skipped.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import typer

import pi_lora.cli.test as _test_cmd
from pi_lora.framework.application import Application


async def _raises_typer_exit(*_args: Any, **_kwargs: Any) -> None:
    """Coroutine that raises ``typer.Exit`` when awaited."""
    raise typer.Exit(1)


@pytest.mark.asyncio
async def test_test_hardware_cleanup_on_typer_exit() -> None:
    """application.stop() called even when typer.Exit raised during start."""
    with patch.object(
        Application, "get_assembly_config", new=AsyncMock(return_value=[object()])
    ), patch.object(Application, "start", _raises_typer_exit), patch.object(
        Application, "stop", new=AsyncMock()
    ) as mock_stop:
        with pytest.raises(typer.Exit):
            await _test_cmd.test_hardware_impl("default")
        mock_stop.assert_called_once()


if __name__ == "__main__":
    import sys

    exit_code = pytest.main([__file__, "-v"])
    sys.exit(exit_code)
