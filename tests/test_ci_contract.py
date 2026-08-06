from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml
from yaml.nodes import MappingNode, Node, SequenceNode
from yaml.tokens import AliasToken, AnchorToken, KeyToken, ScalarToken, ValueToken


ROOT = Path(__file__).resolve().parents[1]
PYTHON_WORKFLOWS = (
    "ci.yml",
)
DEPENDABOT_VERSION_UPDATE_CONFIGS = (
    ROOT / ".github" / "dependabot.yml",
    ROOT / ".github" / "dependabot.yaml",
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


class _WorkflowStructureError(Exception):
    pass


def _uses_nodes(
    value: object,
    node: Node,
    active: set[tuple[int, int]] | None = None,
):
    if active is None:
        active = set()
    marker = (id(value), id(node))
    if isinstance(value, dict) and isinstance(node, MappingNode):
        semantic_items = list(value.items())
        if len(semantic_items) != len(node.value):
            raise _WorkflowStructureError(
                "duplicate or merged mapping keys are not allowed"
            )
        if marker in active:
            raise _WorkflowStructureError(
                "recursive YAML aliases are not allowed"
            )
        active.add(marker)
        try:
            for (key, child_value), (_key_node, child_node) in zip(
                semantic_items,
                node.value,
                strict=True,
            ):
                if key == "uses":
                    yield child_value, child_node
                yield from _uses_nodes(child_value, child_node, active)
        finally:
            active.remove(marker)
    elif isinstance(value, list) and isinstance(node, SequenceNode):
        if len(value) != len(node.value):
            raise _WorkflowStructureError(
                "ambiguous YAML sequence structure"
            )
        if marker in active:
            raise _WorkflowStructureError(
                "recursive YAML aliases are not allowed"
            )
        active.add(marker)
        try:
            for child_value, child_node in zip(
                value,
                node.value,
                strict=True,
            ):
                yield from _uses_nodes(child_value, child_node, active)
        finally:
            active.remove(marker)


def _uses_token_sites(source: str):
    tokens = list(yaml.scan(source))
    sites = []
    for index, token in enumerate(tokens):
        if not isinstance(token, KeyToken) or index + 3 >= len(tokens):
            continue
        key_token = tokens[index + 1]
        value_marker = tokens[index + 2]
        if (
            not isinstance(key_token, ScalarToken)
            or key_token.value != "uses"
            or not isinstance(value_marker, ValueToken)
        ):
            continue
        value_index = index + 3
        while (
            value_index < len(tokens)
            and isinstance(tokens[value_index], AnchorToken)
        ):
            value_index += 1
        if value_index >= len(tokens):
            sites.append(("unsupported", None, value_marker))
            continue
        value_token = tokens[value_index]
        if isinstance(value_token, AliasToken):
            sites.append(("alias", None, value_token))
        elif isinstance(value_token, ScalarToken):
            kind = "multiline" if value_token.style in {">", "|"} else "direct"
            sites.append((kind, value_token.value, value_token))
        else:
            sites.append(("unsupported", None, value_token))
    return sites


def _external_action_pin_errors(path: Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    try:
        workflow = yaml.safe_load(source)
        root_node = yaml.compose(source)
        token_sites = _uses_token_sites(source)
    except yaml.YAMLError as exc:
        problem = getattr(exc, "problem", None) or str(exc)
        return [f"{path}: invalid workflow YAML: {problem}"]
    if workflow is None or root_node is None:
        return []

    external_ref = re.compile(
        r"^[^/@\s]+/[^/@\s]+(?:/[^/@\s]+)*@[0-9a-f]{40}$"
    )
    version_comment = re.compile(r"#\s+v[^\s#]+\s*$")
    lines = source.splitlines()
    errors = []
    try:
        semantic_uses = [
            reference
            for reference, _value_node in _uses_nodes(workflow, root_node)
        ]
    except _WorkflowStructureError as exc:
        return [f"{path}: {exc}"]
    except RecursionError:
        return [f"{path}: recursive YAML aliases are not allowed"]
    if len(semantic_uses) != len(token_sites):
        return [f"{path}: ambiguous uses token mapping"]
    for reference, (site_kind, token_value, value_token) in zip(
        semantic_uses,
        token_sites,
        strict=True,
    ):
        line_number = value_token.start_mark.line + 1
        location = f"{path}:{line_number}"
        if site_kind == "alias":
            errors.append(f"{location} aliases are not allowed for uses values")
            continue
        if site_kind == "multiline":
            errors.append(
                f"{location} multiline uses values are not allowed"
            )
            continue
        if site_kind != "direct":
            errors.append(f"{location} unsupported uses value syntax")
            continue
        if not isinstance(reference, str):
            errors.append(f"{location} uses value must be a string")
            continue
        if token_value != reference:
            errors.append(f"{location} ambiguous uses value construction")
            continue
        if reference.startswith("./"):
            continue
        if not external_ref.fullmatch(reference):
            errors.append(
                f"{location} external uses {reference!r} must pin a "
                "40-character lowercase commit SHA"
            )
            continue
        if value_token.end_mark.line >= len(lines):
            errors.append(
                f"{location} external uses {reference!r} must keep a "
                "trailing version comment"
            )
            continue
        source_line = lines[value_token.end_mark.line]
        comment_suffix = source_line[value_token.end_mark.column :]
        if not version_comment.search(comment_suffix):
            errors.append(
                f"{location} external uses {reference!r} must keep a "
                "trailing version comment"
            )
    return errors


def test_runtime_dependencies_declare_yaml_parser():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert any(
        dependency.lower().startswith("pyyaml")
        for dependency in project["project"]["dependencies"]
    )


def test_sole_main_policy_disables_dependabot_version_update_configuration():
    present_configs = [
        path.relative_to(ROOT).as_posix()
        for path in DEPENDABOT_VERSION_UPDATE_CONFIGS
        if path.exists()
    ]

    assert present_configs == [], (
        "Dependabot version updates create branches and pull requests, which "
        "violates the repository's sole-main policy"
    )


def test_ruff_uses_the_declared_baseline_rules():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["tool"]["ruff"]["lint"]["select"] == ["E4", "E7", "E9", "F"]


def test_consolidated_ci_routes_full_tests_through_the_locked_bootstrap():
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
    )
    test_job = workflow["jobs"]["test"]
    commands = [
        step["run"].strip()
        for step in test_job["steps"]
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ]

    assert test_job["env"]["HYPOTHESIS_STORAGE_DIRECTORY"] == (
        "${{ runner.temp }}/hypothesis"
    )
    assert (
        "python scripts/check_release_gate.py --repo . --outputs outputs "
        "--tree-mode working-pre-cutover --locked-check full-tests-and-coverage "
        "--json"
    ) in commands


def test_docs_describe_the_single_locked_ci_workflow_without_promising_final_governance():
    for relative in ("README.md", "docs/operator/README.md"):
        source = (ROOT / relative).read_text(encoding="utf-8")
        normalized = " ".join(source.split())
        assert "local Clean-OID producer/verifier" in normalized
        assert "single locked `ci` workflow" in normalized
        assert "`contract`, `test`, `package`, and `security`" in normalized
        assert "claims final GitHub governance" not in normalized


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
    assert "check_contract_guardrails.py" in workflows
    assert "contract-spine-sentinel --json" in workflows
    assert "--locked-check full-tests-and-coverage" in workflows


def test_external_workflow_actions_use_immutable_sha_with_version_comment():
    workflow_paths = sorted(
        path
        for path in (ROOT / ".github" / "workflows").iterdir()
        if path.suffix in {".yml", ".yaml"}
    )

    assert workflow_paths
    assert [
        error
        for path in workflow_paths
        for error in _external_action_pin_errors(path)
    ] == []


def test_semantic_action_guard_handles_yaml_syntax_and_reusable_workflows(
    tmp_path: Path,
):
    sha = "a" * 40
    workflow = tmp_path / "semantic.yml"
    workflow.write_text(
        f"""
jobs:
  local:
    "uses" : "./.github/workflows/local.yml"
  reusable:
    uses : "owner/repo/.github/workflows/reuse.yml@{sha}" # v1.2.3
  build:
    steps:
      - {{ "uses" : "owner/repo/action/subpath@{sha}" }} # v2.0.0
      - run: 'echo "# uses: ./comment-is-not-an-action"'
""",
        encoding="utf-8",
    )

    assert _external_action_pin_errors(workflow) == []


def test_semantic_action_guard_rejects_mutable_uppercase_and_uncommented_refs(
    tmp_path: Path,
):
    uppercase_sha = "A" * 40
    lowercase_sha = "b" * 40
    workflow = tmp_path / "unsafe.yml"
    workflow.write_text(
        f"""
# uses: ./spoof-comment
jobs:
  mutable:
    uses : "owner/repo/.github/workflows/reuse.yml@v1" # v1
  uppercase:
    "uses": "owner/repo/action@{uppercase_sha}" # v2
  missing-comment:
    steps:
      - {{uses: "owner/repo/action@{lowercase_sha}"}}
  local:
    uses: "./.github/workflows/local.yml"
""",
        encoding="utf-8",
    )

    errors = _external_action_pin_errors(workflow)

    assert len(errors) == 3
    assert any("@v1" in error for error in errors)
    assert any(uppercase_sha in error for error in errors)
    assert any("version comment" in error for error in errors)


def test_semantic_action_guard_rejects_alias_with_comment_only_at_anchor(
    tmp_path: Path,
):
    sha = "c" * 40
    workflow = tmp_path / "anchor-comment.yml"
    workflow.write_text(
        f"""
anchored-action: &checkout "owner/repo/action@{sha}" # v4.0.0
jobs:
  build:
    steps:
      - uses: *checkout
""",
        encoding="utf-8",
    )

    errors = _external_action_pin_errors(workflow)

    assert len(errors) == 1
    assert "aliases" in errors[0]
    assert ":6" in errors[0]


def test_semantic_action_guard_rejects_alias_even_with_comment_at_use(
    tmp_path: Path,
):
    sha = "d" * 40
    workflow = tmp_path / "alias-comment.yml"
    workflow.write_text(
        f"""
anchored-action: &checkout "owner/repo/action@{sha}"
jobs:
  build:
    steps:
      - "uses" : *checkout # v4.0.0
""",
        encoding="utf-8",
    )

    errors = _external_action_pin_errors(workflow)

    assert len(errors) == 1
    assert "aliases" in errors[0]
    assert ":6" in errors[0]


@pytest.mark.parametrize(
    ("name", "style", "chomp"),
    [
        ("folded", ">", "-"),
        ("literal", "|", "-"),
    ],
)
def test_semantic_action_guard_rejects_multiline_uses_scalars(
    tmp_path: Path,
    name: str,
    style: str,
    chomp: str,
):
    sha = "e" * 40
    workflow = tmp_path / f"multiline-{name}.yml"
    workflow.write_text(
        f"""
jobs:
  build:
    steps:
      - uses: {style}{chomp}
          owner/repo/action@{sha}
""",
        encoding="utf-8",
    )

    errors = _external_action_pin_errors(workflow)

    assert len(errors) == 1
    assert "multiline" in errors[0]


def test_semantic_action_guard_reports_duplicate_mapping_keys(
    tmp_path: Path,
):
    sha = "f" * 40
    workflow = tmp_path / "duplicate-keys.yml"
    workflow.write_text(
        f"""
jobs:
  build:
    steps:
      - uses: "owner/repo/action@{sha}" # v1
        uses: "owner/repo/action@{sha}" # v1
""",
        encoding="utf-8",
    )

    assert _external_action_pin_errors(workflow) == [
        f"{workflow}: duplicate or merged mapping keys are not allowed"
    ]


def test_semantic_action_guard_reports_recursive_aliases(tmp_path: Path):
    workflow = tmp_path / "recursive-alias.yml"
    workflow.write_text(
        """
recursive: &recursive
  uses: *recursive
""",
        encoding="utf-8",
    )

    assert _external_action_pin_errors(workflow) == [
        f"{workflow}: recursive YAML aliases are not allowed"
    ]
