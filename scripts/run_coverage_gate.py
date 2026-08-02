from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_JSON = ROOT / "coverage.json"
PYTEST_COVERAGE_COMMAND = (
    sys.executable,
    "-m",
    "pytest",
    "--cov=src/hsconfig",
    "--cov-branch",
    "--cov-config=pyproject.toml",
    "--cov-fail-under=90",
    "--cov-report=json:coverage.json",
    "--cov-report=term-missing",
    "-p",
    "no:cacheprovider",
)
CHECKER_COMMAND = (
    sys.executable,
    str(ROOT / "scripts" / "check_coverage_contract.py"),
    str(COVERAGE_JSON),
)


class CoverageGateError(RuntimeError):
    pass


@contextmanager
def isolated_coverage_environment() -> Iterator[dict[str, str]]:
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if temporary_root == ROOT or ROOT in temporary_root.parents:
        raise CoverageGateError(
            f"temporary root must be outside repository: {temporary_root}"
        )
    with tempfile.TemporaryDirectory(
        prefix="hsconfig-coverage-run-",
        dir=temporary_root,
    ) as run_directory:
        environment = os.environ.copy()
        environment.pop("PYTEST_ADDOPTS", None)
        environment["COVERAGE_FILE"] = str(
            Path(run_directory, ".coverage").resolve()
        )
        yield environment


def main() -> int:
    try:
        COVERAGE_JSON.unlink(missing_ok=True)
        try:
            with isolated_coverage_environment() as environment:
                pytest_result = subprocess.run(
                    list(PYTEST_COVERAGE_COMMAND),
                    cwd=ROOT,
                    env=environment,
                    check=False,
                )
                if pytest_result.returncode != 0:
                    return pytest_result.returncode
                checker_result = subprocess.run(
                    list(CHECKER_COMMAND),
                    cwd=ROOT,
                    env=environment,
                    check=False,
                )
                return checker_result.returncode
        except CoverageGateError as exc:
            print(f"coverage gate error: {exc}", file=sys.stderr)
            return 2
    finally:
        COVERAGE_JSON.unlink(missing_ok=True)


if __name__ == "__main__":
    if len(sys.argv) != 1:
        print("usage: run_coverage_gate.py", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(main())
