from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL_INSTALL_ROOT = Path.home() / ".codex" / "skills"

FOCUSED_CONTRACT_TESTS = (
    "tests/test_source_claim_family_registry.py",
    "tests/test_contract_spine_sentinel.py",
    "tests/test_contract_spine_sentinel_cli.py",
    "tests/test_contract_spine_sentinel_docs.py",
    "tests/test_apply_authority_boundary.py",
    "tests/test_apply_gate.py",
    "tests/test_no_second_gate_contract.py",
    "tests/test_validate_package.py",
    "tests/test_runtime_apply.py",
    "tests/test_config_usefulness.py",
    "tests/test_operator_summary.py",
    "tests/test_configure_handoff_contract.py",
    "tests/test_no_default_only_semantic_archetype_matrix.py",
    "tests/test_shadowpriest_fresh_closure_proof.py",
    "tests/test_semantic_runtime_negative_boundaries.py",
    "tests/test_universal_wild_no_block_matrix.py",
    "tests/test_operator_docs_contract_policy.py",
    "tests/test_docs_active_path.py",
    "tests/test_skill_sync.py",
    "tests/test_skill_files.py",
    "tests/test_skill_contract_entrypoint.py",
    "tests/test_claim_kind_runtime_contract.py",
    "tests/test_card_behavior_router.py",
    "tests/test_mechanic_support.py",
    "tests/test_source_contract_conformance.py",
    "tests/test_source_to_runtime_explainability.py",
    "tests/test_source_contract_closure_wave.py",
    "tests/test_research_result_contract_sentinel.py",
    "tests/test_research_current_truth_index.py",
)


@dataclass(frozen=True)
class GuardrailCommand:
    name: str
    argv: tuple[str, ...]


def production_assert_violations(repo_root: Path) -> tuple[str, ...]:
    production_root = repo_root / "src" / "hsconfig"
    if not production_root.is_dir():
        return ()

    violations: list[str] = []
    for path in sorted(production_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        relative_path = path.relative_to(repo_root).as_posix()
        violations.extend(
            f"{relative_path}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Assert)
        )
    return tuple(violations)


def guardrail_commands(
    repo_root: Path,
    skill_install_root: Path,
) -> tuple[GuardrailCommand, ...]:
    return (
        GuardrailCommand(
            "installed skill sync",
            (
                sys.executable,
                str(repo_root / "scripts" / "sync_installed_skill.py"),
                "--check",
                "--install-root",
                str(skill_install_root),
            ),
        ),
        GuardrailCommand(
            "contract spine sentinel",
            (
                sys.executable,
                "-m",
                "hsconfig.cli",
                "contract-spine-sentinel",
                "--repo-root",
                str(repo_root),
                "--json",
            ),
        ),
        GuardrailCommand(
            "focused contract boundary tests",
            (
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *FOCUSED_CONTRACT_TESTS,
            ),
        ),
    )


def run_guardrails(
    repo_root: Path,
    skill_install_root: Path,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    assert_violations = production_assert_violations(repo_root)
    if assert_violations:
        print("FAILED: production assert guardrail", file=sys.stderr)
        for violation in assert_violations:
            print(f"  {violation}", file=sys.stderr)
        return 1
    print("OK: production assert guardrail")

    for command in guardrail_commands(repo_root, skill_install_root):
        result = runner(command.argv, cwd=repo_root)
        if result.returncode != 0:
            print(
                f"FAILED: {command.name} (exit {result.returncode})",
                file=sys.stderr,
            )
            return int(result.returncode)
        print(f"OK: {command.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run HSConfig skill-sync and contract-spine guardrails."
    )
    parser.add_argument(
        "--skill-install-root",
        type=Path,
        default=DEFAULT_SKILL_INSTALL_ROOT,
        help="Root directory that contains installed skills.",
    )
    args = parser.parse_args(argv)

    return run_guardrails(REPO_ROOT, args.skill_install_root)


if __name__ == "__main__":
    raise SystemExit(main())
