from __future__ import annotations

from pathlib import Path
import re
import shutil
import tomllib

import pytest

from tests.helpers.markdown_contract import (
    CANONICAL_PUBLIC_METADATA_SHA256,
    MarkdownDocument,
    normalized_utf8_sha256,
    scan_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_METADATA_PATHS = (
    Path("LICENSE"),
    Path("pyproject.toml"),
    Path("README.md"),
    Path("CONTRIBUTING.md"),
    Path("SECURITY.md"),
)
CANONICAL_PUBLIC_METADATA_PATHS = tuple(
    Path(relative) for relative in CANONICAL_PUBLIC_METADATA_SHA256
)
EXPECTED_LICENSE_BLOCK = """Copyright (c) 2026 Teufelsboy. All rights reserved.

This source code is publicly viewable but proprietary. No license is granted
to use, copy, modify, distribute, sublicense, or create derivative works from
this software except with prior written permission from the copyright owner."""
EXPECTED_LICENSE_TEXT = EXPECTED_LICENSE_BLOCK + """

GitHub's platform terms continue to govern platform access.
Public visibility does not make this code confidential."""
EXPECTED_README_COPYRIGHT = "Copyright (c) 2026 Teufelsboy."
EXPECTED_README_STATUS = "Publicly visible — proprietary — All Rights Reserved"
EXPECTED_CONTRIBUTION_REJECTION = (
    "External code contributions and pull requests are not accepted."
)
EXPECTED_PRIVATE_ADVISORY_URL = (
    "https://github.com/Teufelsboy/HSConfig/security/advisories/new"
)
EXPECTED_ISSUES_URL = "https://github.com/Teufelsboy/HSConfig/issues"
_OPEN_SOURCE_OR_OSI_CLAIM = re.compile(
    r"\bopen(?:[\s-]+)source\b|"
    r"\bosi(?:[\s-]+approved|[\s-]+licen[cs](?:e|ed|ing))\b",
    re.IGNORECASE,
)
_CLAUSE_BOUNDARY = re.compile(r"[.!?;:]+")
_NEGATION_BEFORE_CLAIM = re.compile(
    r"(?:"
    r"\b(?:no|not|never|neither|without|cannot|can't)\b|"
    r"\b(?:is|are|was|were|does|do|did|can|could|must|shall|will|would)\s+not\b"
    r")(?:\W+\w+){0,12}\W*$",
    re.IGNORECASE,
)
_NEGATION_AFTER_CLAIM = re.compile(
    r"^\W*(?:label\s+|claim\s+|status\s+|license\s+|designation\s+|term\s+)?"
    r"(?:is|are|was|were|does|do|did|can|could|must|shall|will|would)\s+not\b",
    re.IGNORECASE,
)
EXPECTED_CONTRIBUTING_TEXT = """# Contributing

External code contributions and pull requests are not accepted.

Report non-security bugs through
[GitHub Issues](https://github.com/Teufelsboy/HSConfig/issues). Report security
vulnerabilities through the private route documented in [SECURITY.md](SECURITY.md).
Never attach sensitive runtime evidence to a public report.

The remaining guidance is for repository maintainers.

Start with `README.md`, then follow
[docs/operator/README.md](docs/operator/README.md) for the single current
operator path.

Use test-driven development for behavior changes: add a focused failing test,
confirm the expected RED, implement the minimum change, and confirm GREEN.
Keep changes narrow and preserve existing report schemas and authority
boundaries unless the task explicitly changes them.

Do not commit raw runtime evidence, logs, replays, runtime XML exports, private
evidence folders, deck codes, or generated `outputs/`. Use redacted fixtures
that contain only the fields required by the test.

`reports/operator_summary.json` remains the only normal apply authority.
Maintenance scripts, inventories, historical documents, diagnostics, tests,
and generated contracts cannot authorize runtime writes. Runtime writes occur
only through the documented apply command.

Before recording a maintainer change, run the focused tests first and then:

```powershell
python -m ruff check --no-cache src tests scripts
python -m pytest -p no:cacheprovider
python -m pip_audit
git diff --check
```

Also parse changed YAML files and run the relevant operator, documentation,
skill, and contract tests for the affected boundary."""
EXPECTED_SECURITY_TEXT = """# Security Policy

## Private reporting

Report security vulnerabilities through
[GitHub private vulnerability reporting](https://github.com/Teufelsboy/HSConfig/security/advisories/new).
Include the affected version, impact, and a minimal redacted reproduction. Do
not disclose an unpatched vulnerability in a public issue.

## Sensitive evidence

Never attach raw runtime evidence to an issue, pull request, or commit. This
includes `Power.log`, `.hdtreplay`, `.hsreplay`, HearthRanger or Hearthstone
logs, HDT runtime XML exports, private runtime evidence folders, deck codes,
and unredacted local output packages. Share only the smallest sanitized
extract needed for diagnosis through the private reporting channel.

In particular, raw logs, replays, all deck codes, runtime XML, and unredacted
packages must not be filed publicly."""
FROZEN_POLICY_TEXT = {
    "LICENSE": EXPECTED_LICENSE_TEXT,
    "CONTRIBUTING.md": EXPECTED_CONTRIBUTING_TEXT,
    "SECURITY.md": EXPECTED_SECURITY_TEXT,
}
FROZEN_README_PREFIX_SHA256 = (
    "4b0af1f4a1c9a6ba78ca26725087002779ecf7d8370e2adcb7b8958348664d68"
)
EXPECTED_README_OPTIMIZED_ROUTE_PROSE = (
    "The installed HSConfig skill normally builds an LLM-optimized start from "
    "exactly three fixed candidates:",
    "This installed optimized workflow is the only normal generation route.",
    "Conservative CLI Compatibility",
    "Direct raw hsconfig configure remains available for explicitly conservative "
    "source-contract operation. It is compatibility/expert access, not the normal "
    "installed-skill generation route.",
)
EXPECTED_README_DOCUMENTATION_ROWS = (
    "- [Operator guide](docs/operator/README.md)",
    "- [Architecture overview](docs/architecture/overview.md)",
    "- [Pre-run contract](docs/contracts/pre-run-contract.md)",
    "- [Security policy](SECURITY.md)",
    "- [Contribution policy](CONTRIBUTING.md)",
)
EXPECTED_PROJECT_FIELDS = {
    "name": "hsconfig",
    "dynamic": ["version"],
    "description": "Guide-aligned HearthRanger VisionAI CustomConfig generator",
    "readme": "README.md",
    "license": "LicenseRef-Proprietary",
    "license-files": ["LICENSE"],
    "authors": [{"name": "Teufelsboy"}],
    "classifiers": [
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    "requires-python": ">=3.11",
    "dependencies": [
        "hearthstone>=9.0.0",
        "PyYAML>=6.0",
    ],
    "optional-dependencies": {
        "dev": [
            "pytest>=8.0",
            "pytest-cov>=6.0",
            "hypothesis>=6.0",
            "ruff>=0.12",
            "pip-audit>=2.9",
            "pip==26.1.2",
            "build>=1.0",
        ],
    },
    "scripts": {"hsconfig": "hsconfig.cli:main"},
}
EXPECTED_PROJECT_KEYS = frozenset(EXPECTED_PROJECT_FIELDS)


def _metadata_text(root: Path, relative: Path) -> tuple[str, bool]:
    path = root / relative
    if not path.is_file():
        return "", False
    try:
        return path.read_text(encoding="utf-8"), False
    except UnicodeDecodeError:
        return "", True


def _copy_public_metadata(destination: Path) -> Path:
    for relative in PUBLIC_METADATA_PATHS:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return destination


def _normalized_exact_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized[:-1] if normalized.endswith("\n") else normalized


def _contains_affirmative_open_source_claim(text: str) -> bool:
    normalized = " ".join(text.split())
    for clause in _CLAUSE_BOUNDARY.split(normalized):
        for match in _OPEN_SOURCE_OR_OSI_CLAIM.finditer(clause):
            if _NEGATION_BEFORE_CLAIM.search(clause[: match.start()]):
                continue
            if _NEGATION_AFTER_CLAIM.search(clause[match.end() :]):
                continue
            return True
    return False


def _ordinary_link_count(
    document: MarkdownDocument,
    *,
    label: str,
    target: str,
) -> int:
    return sum(
        token.text == label and token.target == target for token in document.links
    )


def _governance_errors(root: Path) -> list[str]:
    errors: list[str] = []
    metadata = {
        relative: _metadata_text(root, relative) for relative in PUBLIC_METADATA_PATHS
    }
    texts = {relative: value[0] for relative, value in metadata.items()}

    for relative, text in texts.items():
        invalid_utf8 = metadata[relative][1]
        if not text and not invalid_utf8:
            errors.append(f"missing_public_metadata:{relative.as_posix()}")
        if invalid_utf8:
            errors.append(f"invalid_utf8:{relative.as_posix()}")

    for relative in CANONICAL_PUBLIC_METADATA_PATHS:
        text = texts[relative]
        if (
            normalized_utf8_sha256(text)
            != CANONICAL_PUBLIC_METADATA_SHA256[relative.as_posix()]
        ):
            errors.append(f"canonical_integrity:{relative.as_posix()}")

    for relative, expected_text in FROZEN_POLICY_TEXT.items():
        if _normalized_exact_text(texts[Path(relative)]) != expected_text:
            errors.append(f"frozen_policy_contract:{relative}")

    markdown_paths = (
        Path("README.md"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
    )
    documents = {
        relative: scan_markdown(texts[relative]) for relative in markdown_paths
    }
    for relative, document in documents.items():
        for scanner_error in document.errors:
            contract_error = (
                f"unsupported_markdown:{relative.as_posix()}:"
                f"{scanner_error.reason}"
            )
            if contract_error not in errors:
                errors.append(contract_error)

    semantic_policy_texts = {
        Path("LICENSE"): texts[Path("LICENSE")],
        Path("pyproject.toml"): texts[Path("pyproject.toml")],
        **{
            relative: document.policy_text
            for relative, document in documents.items()
        },
    }
    for relative in PUBLIC_METADATA_PATHS:
        if _contains_affirmative_open_source_claim(
            semantic_policy_texts[relative]
        ):
            errors.append(
                f"affirmative_open_source_claim:{relative.as_posix()}"
            )

    license_text = texts[Path("LICENSE")]
    if license_text and _normalized_exact_text(license_text) != EXPECTED_LICENSE_TEXT:
        errors.append("license_text_contract")
    if license_text and EXPECTED_LICENSE_BLOCK not in license_text:
        errors.append("license_rights_wording")
    if license_text and (
        "GitHub's platform terms continue to govern platform access."
        not in license_text
    ):
        errors.append("license_platform_terms")
    if license_text and (
        "Public visibility does not make this code confidential." not in license_text
    ):
        errors.append("license_public_visibility")

    readme_document = documents[Path("README.md")]
    readme_text = texts[Path("README.md")]
    normalized_readme = readme_text.replace("\r\n", "\n").replace("\r", "\n")
    readme_prefix, documentation_marker, documentation = normalized_readme.partition(
        "\n## Documentation\n"
    )
    if (
        not documentation_marker
        or normalized_utf8_sha256(readme_prefix) != FROZEN_README_PREFIX_SHA256
    ):
        errors.append("readme_prefix_contract")
    documentation_rows = tuple(
        line for line in documentation.splitlines() if line.strip()
    )
    if not documentation_marker or documentation_rows != EXPECTED_README_DOCUMENTATION_ROWS:
        errors.append("readme_documentation_contract")
    if readme_document.ordinary_text_lines.count(EXPECTED_README_STATUS) != 1:
        errors.append("readme_proprietary_status")
    if readme_document.ordinary_text_lines.count(EXPECTED_README_COPYRIGHT) != 1:
        errors.append("readme_owner_year")
    visible_readme = " ".join(readme_document.policy_text.split())
    presented_readme = " ".join(readme_document.presentation_prose.split())
    for expected_route_prose in EXPECTED_README_OPTIMIZED_ROUTE_PROSE:
        if expected_route_prose not in presented_readme:
            errors.append(f"readme_optimized_route_contract:{expected_route_prose}")
    if "HSConfig is Open Source." in visible_readme:
        errors.append("readme_invariant:open_source")
    if "Another Company owns this repository." in visible_readme:
        errors.append("readme_invariant:ownership")

    project_text = texts[Path("pyproject.toml")]
    try:
        parsed_project = tomllib.loads(project_text).get("project", {})
    except tomllib.TOMLDecodeError:
        errors.append("pyproject_invalid_toml")
        parsed_project = {}
    project = parsed_project if isinstance(parsed_project, dict) else {}
    if set(project) != EXPECTED_PROJECT_KEYS:
        errors.append("pyproject_project_metadata")
    for field, expected in EXPECTED_PROJECT_FIELDS.items():
        if project.get(field) != expected:
            errors.append(f"pyproject_{field.replace('-', '_')}")
    classifiers = project.get("classifiers", [])
    license_classifiers = (
        [
            str(classifier)
            for classifier in classifiers
            if str(classifier).startswith("License ::")
        ]
        if isinstance(classifiers, list)
        else []
    )
    if license_classifiers:
        errors.append("pyproject_license_classifier")

    contributing_document = documents[Path("CONTRIBUTING.md")]
    visible_contributing = " ".join(contributing_document.policy_text.split())
    if (
        "External contributions and pull requests are welcome."
        in visible_contributing
    ):
        errors.append("contributing_invariant:external_code")
    if EXPECTED_CONTRIBUTION_REJECTION not in visible_contributing:
        errors.append("contributing_external_code_boundary")
    if (
        _ordinary_link_count(
            contributing_document,
            label="GitHub Issues",
            target=EXPECTED_ISSUES_URL,
        )
        != 1
    ):
        errors.append("contributing_issues_route")
    if (
        _ordinary_link_count(
            contributing_document,
            label="SECURITY.md",
            target="SECURITY.md",
        )
        != 1
    ):
        errors.append("contributing_security_route")

    security_document = documents[Path("SECURITY.md")]
    if (
        _ordinary_link_count(
            security_document,
            label="GitHub private vulnerability reporting",
            target=EXPECTED_PRIVATE_ADVISORY_URL,
        )
        != 1
    ):
        errors.append("security_private_advisory_url")
    visible_security = " ".join(security_document.policy_text.split())
    if "Raw logs may be filed publicly." in visible_security:
        errors.append("security_invariant:public_evidence")
    for required in (
        "raw logs",
        "replays",
        "all deck codes",
        "runtime XML",
        "unredacted packages",
        "must not be filed publicly",
    ):
        if required not in visible_security:
            errors.append(f"security_public_evidence_boundary:{required}")
    return errors


def test_public_metadata_declares_the_proprietary_product_contract() -> None:
    assert _governance_errors(ROOT) == []


def test_public_metadata_contract_has_a_fixed_five_file_surface() -> None:
    assert PUBLIC_METADATA_PATHS == (
        Path("LICENSE"),
        Path("pyproject.toml"),
        Path("README.md"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
    )
    assert set(CANONICAL_PUBLIC_METADATA_PATHS) == {
        Path("LICENSE"),
        Path("README.md"),
        Path("CONTRIBUTING.md"),
        Path("SECURITY.md"),
    }
    assert Path(__file__).name not in {
        relative.name for relative in PUBLIC_METADATA_PATHS
    }


@pytest.mark.parametrize("relative", PUBLIC_METADATA_PATHS)
def test_governance_fails_closed_when_public_metadata_is_missing(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    (root / relative).unlink()

    errors = _governance_errors(root)
    assert f"missing_public_metadata:{relative.as_posix()}" in errors
    if relative in CANONICAL_PUBLIC_METADATA_PATHS:
        assert f"canonical_integrity:{relative.as_posix()}" in errors


@pytest.mark.parametrize("relative", CANONICAL_PUBLIC_METADATA_PATHS)
def test_governance_canonical_digest_normalizes_crlf_only(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    lf_bytes = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    path.write_bytes(lf_bytes.replace(b"\n", b"\r\n"))

    assert f"canonical_integrity:{relative.as_posix()}" not in _governance_errors(root)


@pytest.mark.parametrize("relative", CANONICAL_PUBLIC_METADATA_PATHS)
def test_governance_round13_binds_each_approved_public_artifact(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    assert f"canonical_integrity:{relative.as_posix()}" in _governance_errors(root)


@pytest.mark.parametrize(
    ("relative", "statement"),
    [
        ("CONTRIBUTING.md", "External pull‑requests are welcome."),
        ("SECURITY.md", "Raw‑logs may be uploaded."),
        (
            "CONTRIBUTING.md",
            "Raw logs must never be attached to pull requests where external "
            "contributions are welcome.",
        ),
        (
            "CONTRIBUTING.md",
            "A pull request is not accepted; it may be submitted.",
        ),
        (
            "SECURITY.md",
            "Runtime XML must remain private; it may be uploaded.",
        ),
        (
            "CONTRIBUTING.md",
            "External contributors may contribute bug reports through GitHub Issues.",
        ),
        ("README.md", "Another Company holds title to HSConfig."),
        ("README.md", "Teufelsboy is the title holder of HSConfig."),
        ("README.md", "Owned outright by Teufelsboy."),
        (
            "CONTRIBUTING.md",
            "External contributions are not accepted because community pull requests "
            "are welcome.",
        ),
        (
            "CONTRIBUTING.md",
            "External contributions are not accepted but welcome.",
        ),
        (
            "CONTRIBUTING.md",
            "External contributions are not accepted. Please submit them.",
        ),
        (
            "CONTRIBUTING.md",
            "External contributions do not need approval and are welcome.",
        ),
        (
            "CONTRIBUTING.md",
            "External pull requests must never contain raw logs.",
        ),
        ("CONTRIBUTING.md", "Raw logs are prohibited in pull requests."),
        ("SECURITY.md", "Raw logs must not be altered and may be uploaded."),
        (
            "SECURITY.md",
            "Raw logs must not be public because the same may be uploaded.",
        ),
        ("SECURITY.md", "Raw logs must not be public but posted publicly."),
        ("SECURITY.md", "Raw logs must not be public. Please upload them."),
        ("README.md", "Another Company retains all title to HSConfig."),
        ("README.md", "HSConfig is an asset of Another Company."),
        ("README.md", "Use the open λambda function."),
    ],
)
def test_governance_round13_closes_round12_prose_mutations_with_canonical_artifacts(
    tmp_path: Path,
    relative: str,
    statement: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    path.write_text(
        path.read_text(encoding="utf-8") + f"\n{statement}\n",
        encoding="utf-8",
    )

    errors = _governance_errors(root)
    assert f"canonical_integrity:{relative}" in errors
    expected_frozen_error = (
        "readme_documentation_contract"
        if relative == "README.md"
        else f"frozen_policy_contract:{relative}"
    )
    assert expected_frozen_error in errors


@pytest.mark.parametrize(
    ("relative", "original", "replacement", "semantic_error"),
    [
        (
            "LICENSE",
            "No license is granted",
            "A license is granted",
            "license_text_contract",
        ),
        (
            "README.md",
            EXPECTED_README_STATUS,
            "Publicly visible",
            "readme_proprietary_status",
        ),
        (
            "README.md",
            EXPECTED_README_COPYRIGHT,
            "Copyright (c) 2025 Someone Else.",
            "readme_owner_year",
        ),
        (
            "CONTRIBUTING.md",
            EXPECTED_CONTRIBUTION_REJECTION,
            "External code contributions may be accepted.",
            "contributing_external_code_boundary",
        ),
        (
            "CONTRIBUTING.md",
            EXPECTED_ISSUES_URL,
            "https://example.invalid/issues",
            "contributing_issues_route",
        ),
        (
            "SECURITY.md",
            EXPECTED_PRIVATE_ADVISORY_URL,
            "https://example.invalid/private",
            "security_private_advisory_url",
        ),
        (
            "SECURITY.md",
            "must not be filed publicly",
            "may be filed publicly",
            "security_public_evidence_boundary:must not be filed publicly",
        ),
    ],
)
def test_governance_keeps_human_readable_semantic_diagnostics(
    tmp_path: Path,
    relative: str,
    original: str,
    replacement: str,
    semantic_error: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8")
    assert original in text
    path.write_text(text.replace(original, replacement, 1), encoding="utf-8")

    errors = _governance_errors(root)
    assert f"canonical_integrity:{relative}" in errors
    assert semantic_error in errors


@pytest.mark.parametrize(
    ("original", "replacement", "semantic_error"),
    [
        (
            'license = "LicenseRef-Proprietary"',
            'license = "MIT"',
            "pyproject_license",
        ),
        (
            'authors = [{name = "Teufelsboy"}]',
            'authors = [{name = "Someone Else"}]',
            "pyproject_authors",
        ),
        (
            'description = "Guide-aligned HearthRanger VisionAI CustomConfig generator"',
            'description = "Open Source generator"',
            "pyproject_description",
        ),
    ],
)
def test_governance_parses_approved_pyproject_fields_structurally(
    tmp_path: Path,
    original: str,
    replacement: str,
    semantic_error: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    assert original in text
    path.write_text(text.replace(original, replacement, 1), encoding="utf-8")

    assert semantic_error in _governance_errors(root)


def test_governance_allows_unrelated_valid_pyproject_tool_configuration(
    tmp_path: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[tool.round13]\nenabled = true\n",
        encoding="utf-8",
    )

    assert _governance_errors(root) == []


def test_governance_rejects_invalid_pyproject_toml(tmp_path: Path) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / "pyproject.toml"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n[invalid\n",
        encoding="utf-8",
    )

    assert "pyproject_invalid_toml" in _governance_errors(root)


def test_shared_scanner_uses_only_a_link_label_as_visible_policy_text() -> None:
    document = scan_markdown(
        "[GitHub Issues](https://example.invalid/hidden-policy-claim)"
    )

    assert document.presentation_prose == "GitHub Issues"
    assert "hidden-policy-claim" not in document.presentation_prose


def test_governance_rejects_unsupported_raw_html(tmp_path: Path) -> None:
    root = _copy_public_metadata(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n<div>hidden</div>\n",
        encoding="utf-8",
    )

    errors = _governance_errors(root)
    assert "canonical_integrity:README.md" in errors
    assert "unsupported_markdown:README.md:raw_html" in errors


@pytest.mark.parametrize(
    ("relative", "statement", "invariant_error"),
    [
        ("README.md", "HSConfig is Open Source.", "readme_invariant:open_source"),
        (
            "README.md",
            "Another Company owns this repository.",
            "readme_invariant:ownership",
        ),
        (
            "CONTRIBUTING.md",
            "External contributions and pull requests are welcome.",
            "contributing_invariant:external_code",
        ),
        (
            "SECURITY.md",
            "Raw logs may be filed publicly.",
            "security_invariant:public_evidence",
        ),
    ],
)
def test_governance_round14_invariants_survive_a_shared_digest_rollover(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    statement: str,
    invariant_error: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if relative == "README.md":
        text = text.replace("\n## Documentation\n", f"\n{statement}\n\n## Documentation\n")
    else:
        text += f"\n{statement}\n"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setitem(
        CANONICAL_PUBLIC_METADATA_SHA256,
        relative,
        normalized_utf8_sha256(text),
    )

    errors = _governance_errors(root)
    assert f"canonical_integrity:{relative}" not in errors
    assert invariant_error in errors


@pytest.mark.parametrize(
    ("relative", "mutation", "frozen_error"),
    [
        ("LICENSE", "\nApproved support contact.\n", "frozen_policy_contract:LICENSE"),
        (
            "CONTRIBUTING.md",
            "\nApproved support contact.\n",
            "frozen_policy_contract:CONTRIBUTING.md",
        ),
        (
            "SECURITY.md",
            "\nApproved support contact.\n",
            "frozen_policy_contract:SECURITY.md",
        ),
    ],
)
def test_governance_round14_frozen_policy_is_independent_of_shared_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutation: str,
    frozen_error: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8") + mutation
    path.write_text(text, encoding="utf-8")
    monkeypatch.setitem(
        CANONICAL_PUBLIC_METADATA_SHA256,
        relative,
        normalized_utf8_sha256(text),
    )

    errors = _governance_errors(root)
    assert f"canonical_integrity:{relative}" not in errors
    assert frozen_error in errors


def test_governance_round14_readme_prefix_is_independent_of_shared_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_public_metadata(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8").replace(
        "\n## Documentation\n",
        "\nApproved router note.\n\n## Documentation\n",
    )
    readme.write_text(text, encoding="utf-8")
    monkeypatch.setitem(
        CANONICAL_PUBLIC_METADATA_SHA256,
        "README.md",
        normalized_utf8_sha256(text),
    )

    errors = _governance_errors(root)
    assert "canonical_integrity:README.md" not in errors
    assert "readme_prefix_contract" in errors


def test_governance_round14_readme_documentation_allows_only_approved_link_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _copy_public_metadata(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8") + "\nFree policy prose.\n"
    readme.write_text(text, encoding="utf-8")
    monkeypatch.setitem(
        CANONICAL_PUBLIC_METADATA_SHA256,
        "README.md",
        normalized_utf8_sha256(text),
    )

    errors = _governance_errors(root)
    assert "canonical_integrity:README.md" not in errors
    assert "readme_documentation_contract" in errors


def test_governance_round14_closes_the_project_metadata_key_set(
    tmp_path: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    project_path = root / "pyproject.toml"
    text = project_path.read_text(encoding="utf-8").replace(
        'requires-python = ">=3.11"',
        'requires-python = ">=3.11"\nkeywords = ["Open Source"]',
    )
    project_path.write_text(text, encoding="utf-8")

    assert "pyproject_project_metadata" in _governance_errors(root)


@pytest.mark.parametrize(
    "license_classifier",
    [
        "License :: Other/Proprietary License",
        "License :: OSI Approved :: MIT License",
    ],
)
def test_governance_rejects_every_license_trove_classifier(
    tmp_path: Path,
    license_classifier: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    project_path = root / "pyproject.toml"
    text = project_path.read_text(encoding="utf-8")
    assert '  "Programming Language :: Python :: 3.11",' in text
    project_path.write_text(
        text.replace(
            '  "Programming Language :: Python :: 3.11",',
            f'  "{license_classifier}",\n'
            '  "Programming Language :: Python :: 3.11",',
            1,
        ),
        encoding="utf-8",
    )

    errors = _governance_errors(root)
    assert "pyproject_classifiers" in errors
    assert "pyproject_license_classifier" in errors


@pytest.mark.parametrize(
    ("relative", "claim"),
    [
        ("LICENSE", "HSConfig is\nOpen Source."),
        (
            "pyproject.toml",
            "description = \"HSConfig is OSI approved Open Source software\"",
        ),
        ("README.md", "HSConfig is an OSI-approved project."),
        ("CONTRIBUTING.md", "This repository is released as Open Source."),
        ("SECURITY.md", "This software uses an OSI approved license."),
    ],
)
def test_governance_rejects_affirmative_open_source_claims_across_all_metadata(
    tmp_path: Path,
    relative: str,
    claim: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if relative == "pyproject.toml":
        text = text.replace(
            'description = "Guide-aligned HearthRanger VisionAI CustomConfig generator"',
            claim,
            1,
        )
    elif relative == "README.md":
        text = text.replace("\n## Documentation\n", f"\n{claim}\n\n## Documentation\n")
    else:
        text += f"\n{claim}\n"
    path.write_text(text, encoding="utf-8")

    assert (
        f"affirmative_open_source_claim:{relative}" in _governance_errors(root)
    )


@pytest.mark.parametrize(
    ("relative", "explanation"),
    [
        ("LICENSE", "Public visibility does not make HSConfig\nOpen Source."),
        (
            "pyproject.toml",
            "description = \"This package does not claim Open Source status\"",
        ),
        ("README.md", "HSConfig is not\nOpen Source."),
        (
            "CONTRIBUTING.md",
            "No Open Source or OSI-approved license is granted.",
        ),
        (
            "SECURITY.md",
            "This policy does not claim that HSConfig is\nOpen Source or OSI approved.",
        ),
    ],
)
def test_governance_accepts_explanatory_negations_including_line_breaks(
    tmp_path: Path,
    relative: str,
    explanation: str,
) -> None:
    root = _copy_public_metadata(tmp_path)
    path = root / relative
    text = path.read_text(encoding="utf-8")
    if relative == "pyproject.toml":
        text = text.replace(
            'description = "Guide-aligned HearthRanger VisionAI CustomConfig generator"',
            explanation,
            1,
        )
    elif relative == "README.md":
        text = text.replace(
            "\n## Documentation\n", f"\n{explanation}\n\n## Documentation\n"
        )
    else:
        text += f"\n{explanation}\n"
    path.write_text(text, encoding="utf-8")

    semantic_errors = [
        error
        for error in _governance_errors(root)
        if error.startswith("affirmative_open_source_claim:")
    ]
    assert semantic_errors == []


def test_governance_negation_does_not_mask_a_later_affirmative_claim(
    tmp_path: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    readme = root / "README.md"
    claim = "HSConfig is not Open Source. HSConfig is OSI approved."
    text = readme.read_text(encoding="utf-8").replace(
        "\n## Documentation\n", f"\n{claim}\n\n## Documentation\n"
    )
    readme.write_text(text, encoding="utf-8")

    assert "affirmative_open_source_claim:README.md" in _governance_errors(root)


@pytest.mark.parametrize("relative", PUBLIC_METADATA_PATHS)
def test_governance_round14_returns_diagnostics_for_invalid_utf8(
    tmp_path: Path,
    relative: Path,
) -> None:
    root = _copy_public_metadata(tmp_path)
    (root / relative).write_bytes(b"\xff\xfe\xfa")

    errors = _governance_errors(root)
    assert f"invalid_utf8:{relative.as_posix()}" in errors
    if relative in CANONICAL_PUBLIC_METADATA_PATHS:
        assert f"canonical_integrity:{relative.as_posix()}" in errors
