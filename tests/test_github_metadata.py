from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from yaml.constructor import ConstructorError
from yaml.tokens import AliasToken, AnchorToken


ROOT = Path(__file__).resolve().parents[1]
GITHUB = ROOT / ".github"
ISSUE_TEMPLATE = GITHUB / "ISSUE_TEMPLATE"
BUG_FORM = ISSUE_TEMPLATE / "bug.yml"
ISSUE_CONFIG = ISSUE_TEMPLATE / "config.yml"
CODEOWNERS = GITHUB / "CODEOWNERS"
PRIVATE_ADVISORY_URL = (
    "https://github.com/Teufelsboy/HSConfig/security/advisories/new"
)
SENSITIVE_DATA_TERMS = (
    "deckcodes",
    "logs",
    "replays",
    "runtime XML",
    "unredacted packages",
)


class _MetadataLoader(yaml.SafeLoader):
    """Safe loader that rejects every YAML ambiguity GitHub metadata must avoid."""


def _construct_unique_mapping(
    loader: _MetadataLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        if key_node.tag == "tag:yaml.org,2002:merge":
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "merged mapping keys are not allowed",
                key_node.start_mark,
            )
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_MetadataLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_metadata(path: Path) -> object:
    source = path.read_text(encoding="utf-8")
    tokens = list(yaml.scan(source))
    assert not any(
        isinstance(token, (AliasToken, AnchorToken)) for token in tokens
    ), f"{path} must not use YAML anchors or aliases"
    return yaml.load(source, Loader=_MetadataLoader)


def _metadata_documents() -> dict[Path, object]:
    paths = sorted(
        path
        for path in GITHUB.rglob("*")
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    assert paths, "GitHub metadata must contain YAML files"
    return {path: _load_metadata(path) for path in paths}


def _required_input(form: dict[str, object], field_id: str) -> dict[str, object]:
    body = form.get("body")
    assert isinstance(body, list)
    for field in body:
        if isinstance(field, dict) and field.get("id") == field_id:
            attributes = field.get("attributes")
            validations = field.get("validations")
            assert isinstance(attributes, dict)
            assert isinstance(validations, dict)
            assert validations.get("required") is True
            return field
    pytest.fail(f"missing required issue-form field {field_id!r}")


def test_all_github_yaml_is_safe_unambiguous_and_parseable() -> None:
    documents = _metadata_documents()
    assert all(document is not None for document in documents.values())


@pytest.mark.parametrize("filename", ("bug.yml", "config.yml"))
def test_metadata_loader_rejects_duplicate_keys(filename: str, tmp_path: Path) -> None:
    path = tmp_path / filename
    path.write_text("key: first\nkey: second\n", encoding="utf-8")
    with pytest.raises(ConstructorError, match="duplicate key"):
        _load_metadata(path)


def test_metadata_loader_rejects_merge_keys_and_aliases(tmp_path: Path) -> None:
    path = tmp_path / "ambiguous.yml"
    path.write_text("base: &base\n  key: value\ncopy: *base\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="anchors or aliases"):
        _load_metadata(path)

    path.write_text("copy:\n  <<: {key: value}\n", encoding="utf-8")
    with pytest.raises(ConstructorError, match="merged mapping keys"):
        _load_metadata(path)


def test_issue_config_disables_blank_issues_and_has_one_private_contact() -> None:
    config = _load_metadata(ISSUE_CONFIG)
    assert isinstance(config, dict)
    assert config.get("blank_issues_enabled") is False
    contacts = config.get("contact_links")
    assert isinstance(contacts, list) and len(contacts) == 1
    assert contacts[0] == {
        "name": "Private security report",
        "url": PRIVATE_ADVISORY_URL,
        "about": "Report vulnerabilities privately without runtime evidence.",
    }


def test_bug_form_requires_redacted_reproduction_and_behavior_details() -> None:
    form = _load_metadata(BUG_FORM)
    assert isinstance(form, dict)
    assert form.get("name") == "Redacted bug report"
    assert form.get("labels") == ["bug"]

    _required_input(form, "version")
    sanitized = _required_input(form, "sanitized-reproduction")
    _required_input(form, "expected-behavior")
    _required_input(form, "actual-behavior")

    attributes = sanitized["attributes"]
    assert isinstance(attributes, dict)
    assert "sanitized" in str(attributes).lower()
    assert "upload" not in str(form).lower()


def test_bug_form_requires_positive_sensitive_data_confirmation() -> None:
    form = _load_metadata(BUG_FORM)
    assert isinstance(form, dict)
    body = form.get("body")
    assert isinstance(body, list)
    checkbox = next(
        (
            field
            for field in body
            if isinstance(field, dict) and field.get("type") == "checkboxes"
        ),
        None,
    )
    assert isinstance(checkbox, dict)
    validations = checkbox.get("validations")
    attributes = checkbox.get("attributes")
    assert isinstance(validations, dict) and validations.get("required") is True
    assert isinstance(attributes, dict)
    options = attributes.get("options")
    assert isinstance(options, list) and len(options) == 1
    option = options[0]
    assert isinstance(option, dict) and option.get("required") is True
    text = str(option.get("label", "")).lower()
    assert all(term.lower() in text for term in SENSITIVE_DATA_TERMS)


def test_codeowners_has_one_effective_catch_all_owner() -> None:
    lines = [
        line.strip()
        for line in CODEOWNERS.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert lines == ["* @Teufelsboy"]


def test_no_feature_contribution_or_dependabot_version_update_surface() -> None:
    prohibited_templates = (
        "feature_request.md",
        "feature_request.yml",
        "feature_request.yaml",
        "contributing.md",
        "CONTRIBUTING.md",
    )
    assert not any((ISSUE_TEMPLATE / name).exists() for name in prohibited_templates)
    assert not (GITHUB / "dependabot.yml").exists()
    assert not (GITHUB / "dependabot.yaml").exists()
