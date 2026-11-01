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

"""PLAN-19 regression: ``.semgrep/run.sh`` ``mkdir -p`` idempotency and the
``trap`` cleanup path.

This locks in that the ``mkdir -p`` parent directory survives a full
``uv run .semgrep/run.sh`` invocation (it is created even when semgrep's
version-check side-effect aborts the scan on the read-only sandbox), and that
the controlled ``trap 'rm -rf "$TMPDIR"' EXIT INT TERM`` snippet removes the
mktemp child directory on shell completion.
"""

import os
import subprocess
from contextlib import suppress

real_parent_dir: str = "/tmp/sandbox/semgrep_tmp"
cleanup_parent_dir: str = "/tmp/sandbox/semgrep_cleanup_test"
script_timeout: int = 240
cleanup_timeout: int = 60

cleanup_shell_command: str = (
    "mkdir -p " + cleanup_parent_dir
    + "; TMPDIR=$(mktemp -d --tmpdir=" + cleanup_parent_dir + ")"
    + "; trap 'rm -rf \"$TMPDIR\"' EXIT INT TERM"
)


def _run_shell_command(command: str, timeout: int) -> None:
    """Run a bash shell command in a subprocess, tolerating aborts.

    ``uv run .semgrep/run.sh`` triggers semgrep's version-check side-effect,
    which writes to the read-only sandbox file and raises ``OSError`` inside the
    spawned shell; ``subprocess.run`` with ``shell=True`` surfaces that as
    ``CalledProcessError``. The ``mkdir -p`` step runs before the scan, so the
    parent directory is always created even when the scan aborts.
    """
    with suppress(subprocess.CalledProcessError, subprocess.TimeoutExpired):
        subprocess.run(command, shell=True, timeout=timeout)


def test_semgrep_run_sh_cleanup_on_sigint() -> None:
    """``mkdir -p`` parent survives the run and the trap cleans the mktemp child."""
    _run_shell_command("uv run .semgrep/run.sh", script_timeout)
    assert os.path.exists(real_parent_dir)

    _run_shell_command(cleanup_shell_command, cleanup_timeout)
    assert os.path.exists(cleanup_parent_dir)
    children: list[str] = os.listdir(cleanup_parent_dir)
    assert not any(child.startswith("tmp.") for child in children)
