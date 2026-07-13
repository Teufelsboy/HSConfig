from __future__ import annotations

import argparse
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
    "tests/test_no_second_gate_contract.py",
    "tests/test_semantic_runtime_negative_boundaries.py",
    "tests/test_universal_wild_no_block_matrix.py",
    "tests/test_operator_docs_contract_policy.py",
    "tests/test_docs_active_path.py",
    "tests/test_claim_kind_runtime_contract.py",
    "tests/test_card_behavior_router.py",
    "tests/test_mechanic_support.py",
)


@dataclass(frozen=True)
class GuardrailCommand:
    name: str
    argv: tuple[str, ...]


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
