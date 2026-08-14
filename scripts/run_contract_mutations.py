"""Run contract mutations in a disposable source-and-test copy."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Sequence


@dataclass(frozen=True)
class MutationSpec:
    name: str
    target: str
    original: str
    replacement: str
    killing_tests: tuple[str, ...]


@dataclass(frozen=True)
class MutationResult:
    name: str
    status: str
    returncode: int | None
    killing_tests: tuple[str, ...]
    detail: str
    stdout: str
    stderr: str


MUTATIONS = (
    MutationSpec(
        name="apply_authority_report",
        target="src/hsconfig/visionai_registry.py",
        original='NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"',
        replacement='NORMAL_APPLY_AUTHORITY = "reports/source_bundle.json"',
        killing_tests=("tests/mutation/test_apply_authority_mutations.py",),
    ),
    MutationSpec(
        name="non_owner_runtime_row",
        target="src/hsconfig/runtime_entity_owner.py",
        original=(
            "    return (\n"
            "        source_card_id,\n"
            "        semantic_reason,\n"
            "        link_kind,\n"
            "        runtime_card_id,\n"
            "    ) == AUTHORIZED_HERO_POWER_OWNER"
        ),
        replacement="    return True",
        killing_tests=("tests/mutation/test_owner_policy_mutations.py",),
    ),
    MutationSpec(
        name="forbidden_runtime_surface_optional",
        target="src/hsconfig/visionai_registry.py",
        original=(
            '        "Presume.json": RuntimeSurfaceSpec(\n'
            '            file_name="Presume.json",\n'
            '            classification="forbidden",'
        ),
        replacement=(
            '        "Presume.json": RuntimeSurfaceSpec(\n'
            '            file_name="Presume.json",\n'
            '            classification="optional",'
        ),
        killing_tests=("tests/mutation/test_runtime_surface_mutations.py",),
    ),
)

_COPIED_SOURCE_FILES = (
    "src/hsconfig/__init__.py",
    "src/hsconfig/package_domain.py",
    "src/hsconfig/runtime_entity_owner.py",
    "src/hsconfig/version.py",
    "src/hsconfig/visionai_registry.py",
)
_COPIED_TEST_FILES = (
    "tests/__init__.py",
    "tests/mutation/test_apply_authority_mutations.py",
    "tests/mutation/test_owner_policy_mutations.py",
    "tests/mutation/test_runtime_surface_mutations.py",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _copy_file(source_root: Path, target_root: Path, relative_path: str) -> None:
    source = source_root / relative_path
    target = target_root / relative_path
    if not source.is_file():
        raise ValueError(f"mutation_copy_source_missing:{relative_path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_isolated_tree(source_root: Path, target_root: Path) -> None:
    for relative_path in (*_COPIED_SOURCE_FILES, *_COPIED_TEST_FILES):
        _copy_file(source_root, target_root, relative_path)


def _apply_mutation(target_root: Path, mutation: MutationSpec) -> None:
    target = target_root / mutation.target
    content = target.read_text(encoding="utf-8")
    occurrences = content.count(mutation.original)
    if occurrences != 1:
        raise ValueError(
            f"mutation_not_unique:{mutation.name}:occurrences={occurrences}"
        )
    target.write_text(
        content.replace(mutation.original, mutation.replacement, 1),
        encoding="utf-8",
        newline="\n",
    )


def _run_killing_tests(
    target_root: Path,
    mutation: MutationSpec,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_path = str(target_root / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_path
        if not existing_pythonpath
        else os.pathsep.join((source_path, existing_pythonpath))
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        *mutation.killing_tests,
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    return subprocess.run(
        command,
        cwd=target_root,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _run_one(source_root: Path, mutation: MutationSpec) -> MutationResult:
    try:
        with tempfile.TemporaryDirectory(
            prefix="hsconfig-contract-mutation-"
        ) as raw_root:
            target_root = Path(raw_root)
            _copy_isolated_tree(source_root, target_root)
            _apply_mutation(target_root, mutation)
            completed = _run_killing_tests(target_root, mutation)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        return MutationResult(
            name=mutation.name,
            status="error",
            returncode=None,
            killing_tests=mutation.killing_tests,
            detail=str(error),
            stdout="",
            stderr="",
        )
    if completed.returncode == 0:
        status = "survived"
        detail = "selected_tests_passed"
    elif completed.returncode == 1:
        status = "killed"
        detail = "selected_tests_failed"
    else:
        status = "error"
        detail = "selected_tests_unexecutable"
    return MutationResult(
        name=mutation.name,
        status=status,
        returncode=completed.returncode,
        killing_tests=mutation.killing_tests,
        detail=detail,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_mutations(
    mutations: Sequence[MutationSpec] = MUTATIONS,
    *,
    source_root: Path | None = None,
) -> tuple[MutationResult, ...]:
    root = _repository_root() if source_root is None else Path(source_root)
    return tuple(_run_one(root, mutation) for mutation in mutations)


def _exit_code(results: Sequence[MutationResult]) -> int:
    return 0 if results and all(result.status == "killed" for result in results) else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args(argv)
    results = run_mutations()
    if arguments.json:
        print(json.dumps([asdict(result) for result in results], sort_keys=True))
    else:
        for result in results:
            print(f"{result.name}: {result.status} ({result.detail})")
    return _exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
