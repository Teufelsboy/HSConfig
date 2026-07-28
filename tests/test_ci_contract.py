from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
PYTHON_WORKFLOWS = (
    "contract-guardrails.yml",
    "contract-spine.yml",
    "full-test-suite.yml",
)


def _workflow_commands() -> list[str]:
    commands: list[str] = []
    for path in (ROOT / ".github" / "workflows").glob("*.yml"):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                run = step.get("run") if isinstance(step, dict) else None
                if isinstance(run, str):
                    commands.append(run)
    return commands


def test_runtime_dependencies_declare_yaml_parser():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert any(
        dependency.lower().startswith("pyyaml")
        for dependency in project["project"]["dependencies"]
    )


def test_ruff_uses_the_declared_baseline_rules():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["ruff"]["lint"]["select"] == ["E4", "E7", "E9", "F"]


def test_full_suite_updates_audited_packaging_tools():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "full-test-suite.yml").read_text(
            encoding="utf-8"
        )
    )
    commands = "\n".join(
        step["run"]
        for job in workflow["jobs"].values()
        for step in job["steps"]
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ).lower()

    assert "python -m pip install --upgrade pip setuptools" in commands


def test_python_workflow_jobs_disable_bytecode_cache():
    for filename in PYTHON_WORKFLOWS:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / filename).read_text(encoding="utf-8")
        )
        for job_name, job in workflow["jobs"].items():
            assert job.get("env", {}).get("PYTHONDONTWRITEBYTECODE") == "1", (
                f"{filename}:{job_name} must disable Python bytecode writes"
            )


def test_ci_runs_lint_full_suite_and_contract_sentinels():
    workflows = "\n".join(_workflow_commands()).lower()

    assert "ruff check --no-cache src tests scripts" in workflows
    assert "python -m pytest -p no:cacheprovider" in workflows
    assert "check_contract_guardrails.py" in workflows
    assert "contract-spine-sentinel --json" in workflows


def test_external_workflow_actions_use_immutable_sha_with_version_comment():
    action_line = re.compile(
        r"^\s*-\s+uses:\s+([^@\s]+)@([0-9a-f]{40})\s+#\s+v[^\s]+\s*$"
    )
    external_uses: list[tuple[Path, int, str]] = []
    workflow_paths = sorted(
        path
        for path in (ROOT / ".github" / "workflows").iterdir()
        if path.suffix in {".yml", ".yaml"}
    )
    for path in workflow_paths:
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if re.match(r"^\s*-\s+uses:", line) and "uses: ./" not in line:
                external_uses.append((path, line_number, line))

    assert external_uses
    for path, line_number, line in external_uses:
        assert action_line.match(line), (
            f"{path.relative_to(ROOT)}:{line_number} must pin the external "
            "action to a 40-character lowercase commit SHA and keep a "
            "trailing version comment"
        )
