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


def _uses_nodes(value: object, node: Node):
    if isinstance(value, dict) and isinstance(node, MappingNode):
        semantic_items = list(value.items())
        if len(semantic_items) != len(node.value):
            raise AssertionError("workflow mappings must not use merged or duplicate keys")
        for (key, child_value), (_key_node, child_node) in zip(
            semantic_items,
            node.value,
            strict=True,
        ):
            if key == "uses":
                yield child_value, child_node
            yield from _uses_nodes(child_value, child_node)
    elif isinstance(value, list) and isinstance(node, SequenceNode):
        if len(value) != len(node.value):
            raise AssertionError("workflow sequence shape changed during YAML loading")
        for child_value, child_node in zip(value, node.value, strict=True):
            yield from _uses_nodes(child_value, child_node)


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
    semantic_uses = [
        reference for reference, _value_node in _uses_nodes(workflow, root_node)
    ]
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
