from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from pytest import MonkeyPatch

from tests.helpers.controlled_subprocess import controlled_python_environment


ROOT = Path(__file__).resolve().parents[1]


def test_controlled_python_environment_removes_outer_test_authorities(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    root = tmp_path / "repository"
    hostile = {
        "HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING": "forged",
        "COVERAGE_PROCESS_START": "forged",
        "PYTEST_ADDOPTS": "--trace",
        "HYPOTHESIS_PROFILE": "forged",
        "PYTHONSTARTUP": "forged.py",
    }
    for key, value in hostile.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("PATH", "controlled-path")

    environment = controlled_python_environment(root)

    assert not set(hostile) & set(environment)
    assert environment["PATH"] == "controlled-path"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONIOENCODING"] == "utf-8"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONSAFEPATH"] == "1"
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONPATH"].split(os.pathsep) == [
        str(root / "src"),
        str(root),
    ]


def test_controlled_python_environment_binds_child_to_repository_source(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING", "forged")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os, sys; import hsconfig; "
                "print(json.dumps({'executable': sys.executable, "
                "'module': hsconfig.__file__, "
                "'controller': os.environ.get("
                "'HSCONFIG_COVERAGE_LOCKED_TEST_RUNTIME_BINDING')}))"
            ),
        ],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert child.returncode == 0, child.stderr
    payload = json.loads(child.stdout)
    assert Path(payload["executable"]).resolve(strict=True) == Path(
        sys.executable
    ).resolve(strict=True)
    assert Path(payload["module"]).resolve(strict=True).is_relative_to(
        (ROOT / "src").resolve(strict=True)
    )
    assert payload["controller"] is None
