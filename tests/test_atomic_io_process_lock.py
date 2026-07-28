from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from hsconfig.atomic_io import ExclusiveFileLock, LockTimeoutError


HOLDER_SCRIPT = """
import sys
from pathlib import Path
from hsconfig.atomic_io import ExclusiveFileLock

with ExclusiveFileLock(Path(sys.argv[1]), timeout_seconds=2.0):
    print("LOCKED", flush=True)
    sys.stdin.readline()
"""


def _subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(Path(__file__).parents[1] / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root
        if not existing_pythonpath
        else os.pathsep.join((source_root, existing_pythonpath))
    )
    return environment


def test_exclusive_file_lock_times_out_across_processes_then_can_be_reacquired(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER_SCRIPT, str(lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=_subprocess_environment(),
    )
    try:
        assert holder.stdout is not None
        assert holder.stdout.readline().strip() == "LOCKED"

        started = time.monotonic()
        with pytest.raises(LockTimeoutError, match=re.escape(str(lock_path))):
            with ExclusiveFileLock(lock_path, timeout_seconds=0.2):
                pytest.fail("a second process acquired an already-held lock")
        elapsed = time.monotonic() - started

        assert elapsed >= 0.15
        assert elapsed < 2.0
    finally:
        if holder.stdin is not None:
            holder.stdin.write("\n")
            holder.stdin.flush()
        try:
            _, stderr = holder.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            _, stderr = holder.communicate()
        assert holder.returncode == 0, stderr

    with ExclusiveFileLock(lock_path, timeout_seconds=0.5):
        assert lock_path.exists()

    assert lock_path.read_bytes() == b""


def test_exclusive_file_lock_releases_after_exception_and_supports_reuse(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock = ExclusiveFileLock(lock_path, timeout_seconds=0.5)

    with pytest.raises(RuntimeError, match="injected"):
        with lock:
            raise RuntimeError("injected")

    with lock:
        assert lock_path.exists()

    with ExclusiveFileLock(lock_path, timeout_seconds=0.5):
        assert lock_path.exists()
