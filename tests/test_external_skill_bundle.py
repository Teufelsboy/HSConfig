from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
from typing import Any
import unicodedata

import pytest

import hsconfig.external_skill_bundle as external_skill_bundle
import hsconfig.package_io as package_io
from hsconfig.external_skill_bundle import (
    BUNDLE_FILE_PATHS,
    BundleValidationError,
    compute_bundle_aggregate,
    decode_skill_bundle,
    install_external_skill,
    load_embedded_skill_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
RESOURCE = ROOT / "src/hsconfig/resources/codex_skill_bundle.json"
EXPECTED_AGGREGATE_SHA256 = (
    "04b2fd914e7e39ec6e65ae16726e46b404f4d8de69594fe271aaedb540756de1"
)


def test_bundle_resource_is_checkout_byte_stable() -> None:
    relative = RESOURCE.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "check-attr", "text", "--", relative],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{relative}: text: unset"
    assert b"\r" not in RESOURCE.read_bytes()


def _document() -> dict[str, object]:
    return json.loads(RESOURCE.read_text(encoding="utf-8"))


def _resign(document: dict[str, object]) -> bytes:
    rows = document["files"]
    assert isinstance(rows, list)
    decoded: dict[str, bytes] = {}
    for row in rows:
        assert isinstance(row, dict)
        content = str(row["content"]).encode("utf-8")
        row["size"] = len(content)
        row["sha256"] = hashlib.sha256(content).hexdigest()
        decoded[str(row["path"])] = content
    document["aggregate_sha256"] = compute_bundle_aggregate(decoded)
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _mutate_file(
    document: dict[str, object],
    path: str,
    content: str,
) -> bytes:
    rows = document["files"]
    assert isinstance(rows, list)
    row = next(
        item
        for item in rows
        if isinstance(item, dict) and item.get("path") == path
    )
    row["content"] = content
    return _resign(document)


def _replace_skill_frontmatter(skill: str, frontmatter: str) -> str:
    assert skill.startswith("---\n")
    _old, separator, body = skill[4:].partition("\n---\n")
    assert separator
    return f"---\n{frontmatter}\n---\n{body}"


def _test_tree_aggregate(root: Path) -> str:
    """Compute the closed full-tree identity expected by the installer contract."""
    rows: list[tuple[str, str, bytes | None]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            rows.append((relative, "directory", None))
        elif path.is_file():
            rows.append((relative, "file", path.read_bytes()))
        else:
            raise AssertionError(f"unexpected test tree member: {relative}")
    digest = hashlib.sha256(b"hsconfig-external-skill-tree-v1\0")
    for relative, kind, content in sorted(
        rows,
        key=lambda row: row[0].encode("utf-8"),
    ):
        digest.update(b"D\0" if kind == "directory" else b"F\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if content is not None:
            digest.update(str(len(content)).encode("ascii"))
            digest.update(b"\0")
            digest.update(hashlib.sha256(content).hexdigest().encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def _materialize_test_bundle(root: Path) -> dict[str, bytes]:
    files = load_embedded_skill_bundle()
    for relative, content in files.items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return files


def _transaction_residue(parent: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in parent.iterdir()
            if path.name.startswith(".hsconfig-install-")
        ),
        key=lambda path: path.name,
    )


def test_embedded_bundle_is_exact_closed_nine_file_contract() -> None:
    files = load_embedded_skill_bundle()
    document = _document()

    assert tuple(files) == BUNDLE_FILE_PATHS
    assert len(files) == 9
    assert document["schema_version"] == 1
    assert document["bundle_name"] == "hsconfig"
    assert document["aggregate_sha256"] == compute_bundle_aggregate(files)
    assert document["aggregate_sha256"] == EXPECTED_AGGREGATE_SHA256
    assert "installed-" + "skill sync" not in files["SKILL.md"].decode("utf-8")
    assert "--skill-" + "install-root" not in files["SKILL.md"].decode("utf-8")
    assert all(b"\r" not in content for content in files.values())


def test_embedded_workflow_routes_source_gaps_through_live_configure_receipt() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")

    assert "contract-preflight.research_context" not in workflow
    assert "latest_research_result_contract_first_non_promoting_" not in workflow
    assert (
        "`configure_summary.json.source_closure_receipt.first_missing_source_action`"
        in workflow
    )


def test_bundle_decoder_rejects_duplicate_keys_and_nonfinite_numbers() -> None:
    duplicate = b'{"schema_version":1,"schema_version":1}'
    nonfinite = b'{"schema_version":NaN}'

    with pytest.raises(BundleValidationError, match="duplicate_key"):
        decode_skill_bundle(duplicate)
    with pytest.raises(BundleValidationError, match="nonfinite"):
        decode_skill_bundle(nonfinite)


def test_bundle_decoder_rejects_unknown_fields() -> None:
    document = _document()
    document["unexpected"] = True

    with pytest.raises(BundleValidationError, match="schema"):
        decode_skill_bundle(_resign(document))


def test_bundle_decoder_rejects_boolean_schema_version() -> None:
    document = _document()
    document["schema_version"] = True

    with pytest.raises(BundleValidationError, match="schema_version"):
        decode_skill_bundle(_resign(document))


@pytest.mark.parametrize(
    "path",
    (
        "../SKILL.md",
        "references\\workflow.md",
        "/SKILL.md",
        "C:" + "/SKILL.md",
        "references/workflow.md:stream",
        "references/con.txt",
        "references/trailing. ",
        "references/control\x01.md",
        unicodedata.normalize("NFD", "references/café.md"),
    ),
)
def test_bundle_decoder_rejects_unsafe_paths(path: str) -> None:
    document = _document()
    rows = document["files"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["path"] = path

    with pytest.raises(BundleValidationError, match="path|inventory"):
        decode_skill_bundle(_resign(document))


def test_bundle_decoder_rejects_casefold_collisions() -> None:
    document = _document()
    rows = document["files"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    assert isinstance(rows[1], dict)
    rows[1]["path"] = str(rows[0]["path"]).swapcase()

    with pytest.raises(BundleValidationError, match="casefold|inventory"):
        decode_skill_bundle(_resign(document))


@pytest.mark.parametrize(
    ("payload", "reason"),
    (
        (b"\xef\xbb\xbf{}", "bom"),
        (b"\xff", "utf8"),
        (b'{"schema_version":1}\x00', "nul"),
        (b'{"schema_version":1}\r{}', "bare_cr"),
    ),
)
def test_bundle_decoder_rejects_ambiguous_json_bytes(
    payload: bytes,
    reason: str,
) -> None:
    with pytest.raises(BundleValidationError, match=reason):
        decode_skill_bundle(payload)


@pytest.mark.parametrize(
    ("content", "reason"),
    (
        ("\ufeff# Skill\n", "bom"),
        ("# Skill\x00\n", "nul"),
        ("# Skill\rtext\n", "bare_cr"),
    ),
)
def test_bundle_decoder_rejects_ambiguous_file_content(
    content: str,
    reason: str,
) -> None:
    raw = _mutate_file(_document(), "SKILL.md", content)

    with pytest.raises(BundleValidationError, match=reason):
        decode_skill_bundle(raw)


def test_bundle_decoder_rejects_oversize_content_and_hash_drift() -> None:
    oversize = _mutate_file(_document(), "SKILL.md", "x" * 600_000)
    drift = _document()
    rows = drift["files"]
    assert isinstance(rows, list)
    assert isinstance(rows[0], dict)
    rows[0]["sha256"] = "0" * 64
    drift_raw = (json.dumps(drift, ensure_ascii=False) + "\n").encode("utf-8")

    with pytest.raises(BundleValidationError, match="oversize"):
        decode_skill_bundle(oversize)
    with pytest.raises(BundleValidationError, match="hash"):
        decode_skill_bundle(drift_raw)


def test_bundle_decoder_rejects_aggregate_drift() -> None:
    document = _document()
    document["aggregate_sha256"] = "0" * 64
    raw = (json.dumps(document, ensure_ascii=False) + "\n").encode("utf-8")

    with pytest.raises(BundleValidationError, match="aggregate"):
        decode_skill_bundle(raw)


def test_bundle_decoder_rejects_frontmatter_link_and_thin_router_failures() -> None:
    skill = load_embedded_skill_bundle()["SKILL.md"].decode("utf-8")
    missing_frontmatter = _mutate_file(
        _document(),
        "SKILL.md",
        skill.removeprefix("---\n"),
    )
    broken_link = _mutate_file(
        _document(),
        "SKILL.md",
        skill.replace(
            "[guide research policy](references/guide-research-policy.md)",
            "[guide research policy](references/missing.md)",
            1,
        )
        + "\nreferences/guide-research-policy.md\n",
    )
    thin_router = _mutate_file(
        _document(),
        "SKILL.md",
        "---\nname: hsconfig\ndescription: thin\n---\n\n# HSConfig\n",
    )
    normalized_duplicate_frontmatter = _mutate_file(
        _document(),
        "SKILL.md",
        skill.replace("name: hsconfig", "name: evil\n name: hsconfig", 1),
    )

    with pytest.raises(BundleValidationError, match="frontmatter"):
        decode_skill_bundle(missing_frontmatter)
    with pytest.raises(BundleValidationError, match="link"):
        decode_skill_bundle(broken_link)
    with pytest.raises(BundleValidationError, match="thin_router"):
        decode_skill_bundle(thin_router)
    with pytest.raises(BundleValidationError, match="frontmatter"):
        decode_skill_bundle(normalized_duplicate_frontmatter)


@pytest.mark.parametrize(
    "frontmatter",
    (
        "name: hsconfig\ndescription: # comment",
        'name: hsconfig\n"name": evil\ndescription: valid',
        "Name: hsconfig\ndescription: valid",
        "name: &canonical hsconfig\ndescription: *canonical",
        "name: hsconfig\ndescription: .nan",
        "name: hsconfig\ndescription: [not, text]",
        "name: hsconfig\ndescription: {not: text}",
        "name: hsconfig\ndescription: !!str tagged",
        "name: hsconfig\ndescription: valid\n...\nname: second",
        "name: hsconfig",
        "name: hsconfig\ndescription: valid\nextra: rejected",
    ),
)
def test_bundle_skill_frontmatter_uses_closed_duplicate_aware_yaml_semantics(
    frontmatter: str,
) -> None:
    skill = load_embedded_skill_bundle()["SKILL.md"].decode("utf-8")
    malformed = _mutate_file(
        _document(),
        "SKILL.md",
        _replace_skill_frontmatter(skill, frontmatter),
    )

    with pytest.raises(BundleValidationError, match="frontmatter"):
        decode_skill_bundle(malformed)


def test_bundle_skill_frontmatter_closes_yaml_reader_errors() -> None:
    skill = load_embedded_skill_bundle()["SKILL.md"].decode("utf-8")
    malformed = _mutate_file(
        _document(),
        "SKILL.md",
        _replace_skill_frontmatter(
            skill,
            "name: hsconfig\ndescription: bad\x01control",
        ),
    )

    with pytest.raises(BundleValidationError, match="bundle_skill_frontmatter"):
        decode_skill_bundle(malformed)


@pytest.mark.parametrize(
    "frontmatter",
    (
        'name: "hsconfig"\ndescription: "quoted description"',
        "name: hsconfig\ndescription: >\n  folded\n  description",
    ),
)
def test_bundle_skill_frontmatter_accepts_safe_yaml_string_semantics(
    frontmatter: str,
) -> None:
    skill = load_embedded_skill_bundle()["SKILL.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "SKILL.md",
        _replace_skill_frontmatter(skill, frontmatter),
    )

    assert decode_skill_bundle(valid)["SKILL.md"].startswith(b"---\n")


def test_bundle_decoder_rejects_undefined_reference_links_and_images() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    undefined = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n[missing link][missing]\n![missing image][missing-image]\n",
    )

    with pytest.raises(BundleValidationError, match="reference.*undefined"):
        decode_skill_bundle(undefined)


def test_bundle_decoder_accepts_defined_references_and_ignores_code() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    defined = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow
        + "\n[policy][shared policy]\n![policy diagram][shared policy]\n"
        + "[shared policy]: guide-research-policy.md\n"
        + "`[ignored][missing-inline-code]`\n"
        + "```markdown\n![ignored][missing-fenced-code]\n```\n",
    )

    decoded = decode_skill_bundle(defined)

    assert decoded["references/workflow.md"].endswith(b"```\n")


@pytest.mark.parametrize(
    "adversarial_line",
    (
        "[![nested](file:///nested-only)](https://example.com)",
        "[missing shortcut]",
        "![missing shortcut image]",
        "<file:///private>",
        "<file:///private`ignored`>",
        "<javascript:alert>",
    ),
)
def test_bundle_decoder_rejects_nested_shortcut_and_autolink_bypasses(
    adversarial_line: str,
) -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + f"\n{adversarial_line}\n",
    )

    with pytest.raises(BundleValidationError, match="link|reference"):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_accepts_safe_https_email_and_defined_shortcut_autolinks() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow
        + "\n<https://example.com/hsconfig>\n<https://example.com/`ignored`>\n"
        + "<operator@example.com>\n"
        + "[policy]\n[policy]: guide-research-policy.md\n",
    )

    assert decode_skill_bundle(valid)["references/workflow.md"].endswith(
        b"[policy]: guide-research-policy.md\n"
    )


def test_bundle_decoder_does_not_hide_links_across_list_block_boundaries() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n`open\n- [x](file:///outside-list)\nclose`\n",
    )

    with pytest.raises(BundleValidationError, match="bundle_markdown_link_unsafe"):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_keeps_indented_list_continuation_links_visible() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n- item\n    [x](file:///outside-list-continuation)\n",
    )

    with pytest.raises(BundleValidationError, match="bundle_markdown_link_unsafe"):
        decode_skill_bundle(adversarial)


@pytest.mark.parametrize(
    "addition",
    (
        "> quote\n    [x](references/missing.md)\n",
        "> quote\n    ![x](references/missing.png)\n",
        "> [x](\n> references/missing.md\n> )\n",
        "> ![x](\n> references/missing.png\n> )\n",
    ),
)
def test_bundle_decoder_enforces_commonmark_blockquote_navigation(
    addition: str,
) -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n" + addition,
    )

    with pytest.raises(BundleValidationError, match="bundle_markdown_link_missing"):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_ignores_actual_indented_code_inside_blockquotes() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n> quote\n>\n>     [x](references/missing.md)\n",
    )

    assert decode_skill_bundle(valid)["references/workflow.md"].endswith(
        b">     [x](references/missing.md)\n"
    )


@pytest.mark.parametrize(
    "addition",
    (
        '<a\fhref="references/missing.md">x</a>\n',
        '<svg><a xlink:href="references/missing.md">x</a></svg>\n',
    ),
)
def test_bundle_decoder_closes_html5_space_and_namespaced_navigation(
    addition: str,
) -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n" + addition,
    )

    with pytest.raises(BundleValidationError, match="bundle_markdown_parse"):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_ignores_namespaced_html_navigation_inside_code() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow
        + '\n`<a\fhref="references/missing-inline.md">x</a>`\n'
        + "```html\n<svg><a xlink:href=\"references/missing-fenced.md\">x</a></svg>\n```\n",
    )

    assert decode_skill_bundle(valid)["references/workflow.md"].endswith(b"```\n")


@pytest.mark.parametrize(
    "addition",
    (
        "> [multi\nlabel](references/missing-label.md)\n",
        "> [x](\nreferences/missing-destination.md\n)\n",
        '> [x](references/missing-title.md\n"title")\n',
        "> ![x](\nreferences/missing-image.png\n)\n",
    ),
)
def test_bundle_decoder_enforces_unmarked_lazy_blockquote_navigation(
    addition: str,
) -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n" + addition,
    )

    with pytest.raises(BundleValidationError, match="bundle_markdown_link_missing"):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_lazy_blockquotes_keep_closed_code_inert() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow
        + "\n> paragraph\n>\n>     [code](references/missing-code.md)\n"
        + "> ```md\n> [fenced](references/missing-fenced.md)\n> ```\n",
    )

    assert decode_skill_bundle(valid)["references/workflow.md"].endswith(b"> ```\n")


def test_bundle_decoder_keeps_unmarked_lazy_blockquote_inline_code_inert() -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    valid = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow
        + "\n> `open\n[code](references/missing-code.md)\n> close`\n",
    )

    assert decode_skill_bundle(valid)["references/workflow.md"].endswith(b"> close`\n")


@pytest.mark.parametrize(
    ("addition", "reason"),
    (
        ("[multi\nlabel](file:///bundle-multiline)\n", "link_unsafe"),
        ("[missing\ntarget](references/missing.md)\n", "link_missing"),
        (
            "1. outer\n\n   1. nested\n\n      [x](file:///bundle-nested)\n",
            "link_unsafe",
        ),
        ('<a\n href="file:///bundle-html">x</a>\n', "markdown_parse"),
        ('<img\n src="javascript&colon;alert">\n', "markdown_parse"),
    ),
)
def test_bundle_decoder_enforces_multiline_list_and_raw_html_navigation(
    addition: str,
    reason: str,
) -> None:
    workflow = load_embedded_skill_bundle()["references/workflow.md"].decode("utf-8")
    adversarial = _mutate_file(
        _document(),
        "references/workflow.md",
        workflow + "\n" + addition,
    )

    with pytest.raises(BundleValidationError, match=reason):
        decode_skill_bundle(adversarial)


def test_bundle_decoder_compiles_both_python_helpers() -> None:
    files = load_embedded_skill_bundle()
    for path in ("scripts/build_config.py", "scripts/validate_package.py"):
        compile(files[path], path, "exec", dont_inherit=True)

    invalid = _mutate_file(
        _document(),
        "scripts/build_config.py",
        "def invalid(:\n",
    )
    with pytest.raises(BundleValidationError, match="compile"):
        decode_skill_bundle(invalid)


def test_import_has_no_install_side_effect_and_destination_is_explicit(
    tmp_path: Path,
) -> None:
    before = tuple(tmp_path.iterdir())
    reloaded = importlib.reload(external_skill_bundle)

    assert tuple(tmp_path.iterdir()) == before
    assert inspect.signature(reloaded.install_external_skill).parameters[
        "destination"
    ].default is inspect.Parameter.empty


def test_explicit_installer_materializes_exact_bundle_and_cleans_transaction(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    parent.mkdir()
    destination = parent / "hsconfig"
    destination.mkdir()
    (destination / "old.txt").write_text("old\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    result = install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=predecessor,
    )
    expected = load_embedded_skill_bundle()
    root_identity = external_skill_bundle.path_identity(destination)
    file_state = {
        path.relative_to(destination).as_posix(): (
            external_skill_bundle.path_identity(path),
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in destination.rglob("*")
        if path.is_file()
    }
    repeated = install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=None,
    )

    assert result == {
        "aggregate_sha256": compute_bundle_aggregate(expected),
        "destination": str(destination.resolve()),
        "files_installed": 9,
        "status": "installed",
    }
    assert repeated == {
        "aggregate_sha256": compute_bundle_aggregate(expected),
        "destination": str(destination.resolve()),
        "files_installed": 9,
        "status": "already_current",
    }
    assert external_skill_bundle.path_identity(destination) == root_identity
    assert {
        path.relative_to(destination).as_posix(): (
            external_skill_bundle.path_identity(path),
            path.stat().st_mtime_ns,
            path.read_bytes(),
        )
        for path in destination.rglob("*")
        if path.is_file()
    } == file_state
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == expected
    assert not [
        path
        for path in parent.iterdir()
        if path != destination and path.name.startswith(".hsconfig-install-")
    ]


def test_explicit_installer_rejects_unknown_existing_tree_before_mutation(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    old = destination / "old.txt"
    old.write_text("unreviewed\n", encoding="utf-8")
    before = (external_skill_bundle.path_identity(destination), old.read_bytes())

    with pytest.raises(ValueError, match="predecessor"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
        )

    assert (external_skill_bundle.path_identity(destination), old.read_bytes()) == before
    assert _transaction_residue(parent) == []


def test_installer_revalidates_controller_bound_predecessor_after_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    old = destination / "old.txt"
    old.write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    recover = external_skill_bundle._recover_committed_transaction_if_present

    def replace_after_recovery(*args: object, **kwargs: object) -> None:
        recover(*args, **kwargs)
        old.write_text("noncooperative replacement\n", encoding="utf-8")

    monkeypatch.setattr(
        external_skill_bundle,
        "_recover_committed_transaction_if_present",
        replace_after_recovery,
    )

    with pytest.raises(ValueError, match="predecessor"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert old.read_text(encoding="utf-8") == "noncooperative replacement\n"
    assert _transaction_residue(parent) == []


def test_installer_rejects_same_bytes_new_root_identity_after_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    original_identity = external_skill_bundle.path_identity(destination)
    recover = external_skill_bundle._recover_committed_transaction_if_present

    def replace_root_after_recovery(*args: object, **kwargs: object) -> None:
        recover(*args, **kwargs)
        moved = parent / "foreign-old-root"
        destination.rename(moved)
        destination.mkdir()
        (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")

    monkeypatch.setattr(
        external_skill_bundle,
        "_recover_committed_transaction_if_present",
        replace_root_after_recovery,
    )

    with pytest.raises(ValueError, match="predecessor"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert _test_tree_aggregate(destination) == predecessor
    assert external_skill_bundle.path_identity(destination) != original_identity
    assert _transaction_residue(parent) == []


@pytest.mark.parametrize(
    ("boundary", "exception_type"),
    tuple(
        (boundary, exception_type)
        for boundary in (
            "after_journal_temp_create",
            "after_journal_temp_write",
            "after_journal_temp_flush",
            "before_journal_publish",
            "after_journal_publish",
        )
        for exception_type in (KeyboardInterrupt, SystemExit)
    ),
)
def test_initial_journal_publish_is_baseexception_atomic_and_retryable(
    tmp_path: Path,
    boundary: str,
    exception_type: type[BaseException],
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    old = destination / "old.txt"
    old.write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    interrupted = False

    def interrupt_once(event: str) -> None:
        nonlocal interrupted
        if event == boundary and not interrupted:
            interrupted = True
            raise exception_type(f"interrupt:{boundary}")

    with pytest.raises(exception_type, match="interrupt"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=interrupt_once,
        )

    assert interrupted is True
    assert _test_tree_aggregate(destination) == predecessor
    assert old.read_text(encoding="utf-8") == "reviewed\n"
    assert _transaction_residue(parent) == []

    result = install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=predecessor,
    )
    assert result["status"] == "installed"
    assert _transaction_residue(parent) == []


def test_initial_journal_partial_write_interrupt_cleans_only_owned_temp_and_retries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    write_all = external_skill_bundle._write_all

    def interrupt_after_partial_write(descriptor: int, payload: bytes) -> None:
        assert os.write(descriptor, payload[:7]) == 7
        raise KeyboardInterrupt("partial journal write")

    monkeypatch.setattr(
        external_skill_bundle,
        "_write_all",
        interrupt_after_partial_write,
    )
    with pytest.raises(KeyboardInterrupt, match="partial journal"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert _test_tree_aggregate(destination) == predecessor
    assert _transaction_residue(parent) == []
    monkeypatch.setattr(external_skill_bundle, "_write_all", write_all)
    assert install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=predecessor,
    )["status"] == "installed"


@pytest.mark.parametrize("exception_type", (KeyboardInterrupt, SystemExit))
def test_initial_journal_identity_capture_interrupt_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exception_type: type[BaseException],
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    old = destination / "old.txt"
    old.write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    descriptor_identity = external_skill_bundle._journal_descriptor_identity
    interrupted = False

    def interrupt_first_identity_capture(descriptor: int) -> tuple[int, int, int]:
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise exception_type("journal identity capture")
        return descriptor_identity(descriptor)

    monkeypatch.setattr(
        external_skill_bundle,
        "_journal_descriptor_identity",
        interrupt_first_identity_capture,
    )
    with pytest.raises(exception_type, match="journal identity capture"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert interrupted is True
    assert _test_tree_aggregate(destination) == predecessor
    assert old.read_text(encoding="utf-8") == "reviewed\n"
    assert _transaction_residue(parent) == []
    assert install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=predecessor,
    )["status"] == "installed"
    assert _transaction_residue(parent) == []


def test_tree_identity_exposes_closed_controller_bindable_predecessor(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "hsconfig"
    destination.mkdir()
    (destination / "empty").mkdir()
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")

    identity = external_skill_bundle.external_skill_tree_identity(destination)

    assert identity == {
        "schema_version": 1,
        "present": True,
        "aggregate_sha256": _test_tree_aggregate(destination),
        "files": 1,
        "directories": 1,
    }


@pytest.mark.parametrize(
    ("file_names", "directory_names"),
    (
        (("A/one.txt", "a/two.txt"), ("A", "a")),
        (("A",), ("a",)),
        (
            (
                "caf\N{LATIN SMALL LETTER E WITH ACUTE}/one.txt",
                "cafe\N{COMBINING ACUTE ACCENT}/two.txt",
            ),
            (
                "caf\N{LATIN SMALL LETTER E WITH ACUTE}",
                "cafe\N{COMBINING ACUTE ACCENT}",
            ),
        ),
    ),
)
def test_external_tree_identity_rejects_windows_ambiguous_name_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    file_names: tuple[str, ...],
    directory_names: tuple[str, ...],
) -> None:
    destination = tmp_path / "hsconfig"
    destination.mkdir()

    class FakeSnapshot:
        def file_names(self) -> tuple[str, ...]:
            return file_names

        @property
        def directory_names(self) -> tuple[str, ...]:
            return directory_names

        def read_bytes(self, _relative: str) -> bytes:
            return b"reviewed\n"

    monkeypatch.setattr(
        external_skill_bundle,
        "snapshot_bounded_filesystem_package",
        lambda _root: FakeSnapshot(),
    )

    with pytest.raises(ValueError, match="collision|ambiguous"):
        external_skill_bundle.external_skill_tree_identity(destination)


def test_explicit_installer_rejects_prelock_to_locked_tree_drift(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    old = destination / "old.txt"
    old.write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    def drift(stage: str) -> None:
        if stage == "after_prelock_snapshot":
            old.write_text("changed-under-lock\n", encoding="utf-8")

    with pytest.raises(ValueError, match="predecessor.*changed|changed.*predecessor"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=drift,
        )

    assert old.read_text(encoding="utf-8") == "changed-under-lock\n"
    assert _transaction_residue(parent) == []


def test_postcommit_backup_cleanup_interrupt_retains_verified_new_tree(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    def interrupt(stage: str) -> None:
        if stage == "before_backup_cleanup":
            raise SystemExit(17)

    with pytest.raises(SystemExit, match="17"):
        kwargs: dict[str, Any] = {"fault_hook": interrupt}
        if (
            "expected_predecessor_aggregate_sha256"
            in inspect.signature(install_external_skill).parameters
        ):
            kwargs["expected_predecessor_aggregate_sha256"] = predecessor
        install_external_skill(destination, **kwargs)

    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()
    journal = next(parent.glob(".hsconfig-install-*.journal.json"))
    assert json.loads(journal.read_text(encoding="utf-8"))["phase"] == "committed"
    assert len(list(parent.glob(".hsconfig-install-*.backup"))) == 1

    recovered = install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=None,
    )

    assert recovered["status"] == "already_current"
    assert _transaction_residue(parent) == []


def test_exact_current_rejects_unclassified_transaction_residue(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    _materialize_test_bundle(destination)
    residue = parent / (".hsconfig-install-" + ("a" * 32) + ".journal.json")
    residue.write_text("{}\n", encoding="utf-8")
    residue_before = residue.read_bytes()

    with pytest.raises(ValueError, match="transaction|journal"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
        )

    assert residue.read_bytes() == residue_before
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()


def test_postcommit_mid_backup_cleanup_interrupt_is_resumable(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    (destination / "nested" / "empty").mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    (destination / "nested" / "old.txt").write_text("nested\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    interrupted = False

    def interrupt(stage: str) -> None:
        nonlocal interrupted
        if stage == "after_backup_cleanup_entry" and not interrupted:
            interrupted = True
            raise SystemExit(19)

    with pytest.raises(SystemExit, match="19"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=interrupt,
        )

    assert interrupted is True
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1

    recovered = install_external_skill(
        destination,
        expected_predecessor_aggregate_sha256=None,
    )

    assert recovered["status"] == "already_current"
    assert _transaction_residue(parent) == []


def test_postcommit_cleanup_rejects_same_inode_content_drift_after_crash(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    (destination / "nested" / "empty").mkdir(parents=True)
    (destination / "old.txt").write_bytes(b"reviewed\n")
    (destination / "nested" / "old.txt").write_bytes(b"nested\n")
    predecessor = _test_tree_aggregate(destination)
    interrupted = False

    def interrupt(stage: str) -> None:
        nonlocal interrupted
        if stage == "after_backup_cleanup_entry" and not interrupted:
            interrupted = True
            raise SystemExit(23)

    with pytest.raises(SystemExit, match="23"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=interrupt,
        )

    journal = next(parent.glob(".hsconfig-install-*.journal.json"))
    backup = next(parent.glob(".hsconfig-install-*.backup"))
    remaining = backup / "old.txt"
    document = json.loads(journal.read_text(encoding="utf-8"))
    original_identity = external_skill_bundle.path_identity_from_status(
        external_skill_bundle.plain_file_status(remaining)
    )
    with remaining.open("r+b") as handle:
        handle.write(b"tampered\n")
        handle.flush()
        os.fsync(handle.fileno())

    assert interrupted is True
    assert document["cleanup_cursor"] == 0
    assert external_skill_bundle.path_identity_from_status(
        external_skill_bundle.plain_file_status(remaining)
    ) == original_identity
    with pytest.raises(ValueError, match="cleanup.*state|content.*changed"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
        )

    assert remaining.read_bytes() == b"tampered\n"
    assert json.loads(journal.read_text(encoding="utf-8"))["cleanup_cursor"] == 0
    assert journal.exists()
    assert backup.exists()
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()


def test_postcommit_cleanup_never_deletes_bytes_changed_after_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_bytes(b"reviewed\n")
    predecessor = _test_tree_aggregate(destination)
    secure_unlink_verified = external_skill_bundle.secure_unlink_verified
    raced = False
    mutated_backup: Path | None = None

    def mutate_after_validation(path: Path, **kwargs: Any) -> None:
        nonlocal raced, mutated_backup
        if path.name == "old.txt" and path.parent.name.endswith(".backup"):
            before = external_skill_bundle.path_identity_from_status(
                external_skill_bundle.plain_file_status(path)
            )
            with path.open("r+b") as handle:
                handle.write(b"tampered\n")
                handle.flush()
                os.fsync(handle.fileno())
            assert external_skill_bundle.path_identity_from_status(
                external_skill_bundle.plain_file_status(path)
            ) == before
            raced = True
            mutated_backup = path
        secure_unlink_verified(path, **kwargs)

    monkeypatch.setattr(
        external_skill_bundle,
        "secure_unlink_verified",
        mutate_after_validation,
    )

    with pytest.raises(ValueError, match="cleanup.*changed"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert raced is True
    assert mutated_backup is not None
    assert mutated_backup.read_bytes() == b"tampered\n"
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1
    assert len(list(parent.glob(".hsconfig-install-*.backup"))) == 1
    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_holds_the_verified_handle_through_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)
    identity = package_io.path_identity_from_status(package_io.plain_file_status(victim))
    disposition = package_io._set_windows_native_handle_delete
    sharing_error: OSError | None = None

    def prove_exclusive_handle(native_handle: int, *, delete: bool = True) -> None:
        nonlocal sharing_error
        if not delete:
            disposition(native_handle, delete=False)
            return
        try:
            competing = victim.open("r+b")
        except OSError as error:
            sharing_error = error
        else:
            competing.close()
            raise AssertionError("verified-delete handle permitted a competing writer")
        disposition(native_handle, delete=True)

    monkeypatch.setattr(
        package_io,
        "_set_windows_native_handle_delete",
        prove_exclusive_handle,
    )

    package_io.secure_unlink_verified(
        victim,
        expected_identity=identity,
        expected_parent_identity=package_io.path_identity(tmp_path),
        expected_size=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert sharing_error is not None
    assert victim.exists() is False


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
@pytest.mark.parametrize(
    ("expected_size", "expected_sha256"),
    (
        (8, hashlib.sha256(b"reviewed\n").hexdigest()),
        (9, hashlib.sha256(b"tampered\n").hexdigest()),
    ),
)
def test_verified_unlink_rejects_size_and_same_size_digest_mismatch(
    tmp_path: Path,
    expected_size: int,
    expected_sha256: str,
) -> None:
    victim = tmp_path / "victim.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)

    with pytest.raises(ValueError, match="verified_unlink.*content"):
        package_io.secure_unlink_verified(
            victim,
            expected_identity=package_io.path_identity_from_status(
                package_io.plain_file_status(victim)
            ),
            expected_parent_identity=package_io.path_identity(tmp_path),
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )

    assert victim.read_bytes() == content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_rejects_a_preexisting_writer_without_mutation(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)
    identity = package_io.path_identity_from_status(package_io.plain_file_status(victim))

    with victim.open("r+b") as writer:
        with pytest.raises(OSError):
            package_io.secure_unlink_verified(
                victim,
                expected_identity=identity,
                expected_parent_identity=package_io.path_identity(tmp_path),
                expected_size=len(content),
                expected_sha256=hashlib.sha256(content).hexdigest(),
            )
        writer.seek(0)
        assert writer.read() == content

    assert victim.read_bytes() == content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_owns_the_descriptor_before_any_baseexception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    renamed = tmp_path / "renamed.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)
    inspect_handle = package_io._windows_native_handle_state
    interrupted = False

    def interrupt_immediately_after_native_acquisition(native_handle: int) -> Any:
        nonlocal interrupted
        interrupted = True
        assert native_handle > 0
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        package_io,
        "_windows_native_handle_state",
        interrupt_immediately_after_native_acquisition,
    )
    with pytest.raises(KeyboardInterrupt):
        package_io.secure_unlink_verified(
            victim,
            expected_identity=package_io.path_identity_from_status(
                package_io.plain_file_status(victim)
            ),
            expected_parent_identity=package_io.path_identity(tmp_path),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )
    monkeypatch.setattr(package_io, "_windows_native_handle_state", inspect_handle)

    assert interrupted is True
    with victim.open("r+b") as handle:
        assert handle.read() == content
    victim.rename(renamed)
    renamed.rename(victim)

    assert victim.read_bytes() == content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_rejects_existing_alternate_data_streams(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim.txt"
    stream = Path(f"{victim}:unbound")
    content = b"reviewed\n"
    stream_content = b"unreviewed stream\n"
    victim.write_bytes(content)
    stream.write_bytes(stream_content)

    with pytest.raises(ValueError, match="verified_unlink.*stream|content.*changed"):
        package_io.secure_unlink_verified(
            victim,
            expected_identity=package_io.path_identity_from_status(
                package_io.plain_file_status(victim)
            ),
            expected_parent_identity=package_io.path_identity(tmp_path),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )

    assert victim.read_bytes() == content
    assert stream.read_bytes() == stream_content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_blocks_late_alternate_stream_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    late_stream = Path(f"{victim}:late")
    content = b"reviewed\n"
    victim.write_bytes(content)
    disposition = package_io._set_windows_native_handle_delete
    creation_error: OSError | None = None

    def prove_whole_link_barrier(native_handle: int, *, delete: bool = True) -> None:
        nonlocal creation_error
        disposition(native_handle, delete=delete)
        if not delete:
            return
        try:
            late_stream.write_bytes(b"late unreviewed bytes\n")
        except OSError as error:
            creation_error = error
        else:
            raise AssertionError("delete-pending file permitted a late alternate stream")

    monkeypatch.setattr(
        package_io,
        "_set_windows_native_handle_delete",
        prove_whole_link_barrier,
    )

    package_io.secure_unlink_verified(
        victim,
        expected_identity=package_io.path_identity_from_status(
            package_io.plain_file_status(victim)
        ),
        expected_parent_identity=package_io.path_identity(tmp_path),
        expected_size=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert creation_error is not None
    assert victim.exists() is False


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_cancels_delete_with_independent_native_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    late_stream = Path(f"{victim}:late")
    content = b"reviewed\n"
    stream_content = b"late unreviewed bytes\n"
    victim.write_bytes(content)
    disposition = package_io._set_windows_native_handle_delete

    def write_stream_with_permissive_sharing() -> None:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            ctypes.c_wchar_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        handle = create_file(
            str(late_stream),
            0x40000000,
            0x00000001 | 0x00000002 | 0x00000004,
            None,
            2,
            0x00000080,
            None,
        )
        if handle == ctypes.c_void_p(-1).value:
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error), str(late_stream))
        try:
            written = wintypes.DWORD()
            if not kernel32.WriteFile(
                handle,
                stream_content,
                len(stream_content),
                ctypes.byref(written),
                None,
            ) or written.value != len(stream_content):
                error = ctypes.get_last_error()
                raise OSError(error, ctypes.FormatError(error), str(late_stream))
            if not kernel32.FlushFileBuffers(handle):
                error = ctypes.get_last_error()
                raise OSError(error, ctypes.FormatError(error), str(late_stream))
        finally:
            kernel32.CloseHandle(handle)

    def inject_stream_and_break_primary_cancel(
        native_handle: int,
        *,
        delete: bool = True,
    ) -> None:
        if delete:
            write_stream_with_permissive_sharing()
            disposition(native_handle, delete=True)
            return
        raise OSError("primary cancellation surface unavailable")

    monkeypatch.setattr(
        package_io,
        "_set_windows_native_handle_delete",
        inject_stream_and_break_primary_cancel,
    )

    with pytest.raises(ValueError, match="verified_unlink.*(?:stream|content)"):
        package_io.secure_unlink_verified(
            victim,
            expected_identity=package_io.path_identity_from_status(
                package_io.plain_file_status(victim)
            ),
            expected_parent_identity=package_io.path_identity(tmp_path),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )

    assert victim.read_bytes() == content
    assert late_stream.read_bytes() == stream_content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_rejects_a_hardlink_added_before_disposition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    alias = tmp_path / "alias.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)
    disposition = package_io._set_windows_native_handle_delete
    linked = False

    def add_alias_then_set_disposition(
        native_handle: int,
        *,
        delete: bool = True,
    ) -> None:
        nonlocal linked
        if delete and not linked:
            os.link(victim, alias)
            linked = True
        disposition(native_handle, delete=delete)

    monkeypatch.setattr(
        package_io,
        "_set_windows_native_handle_delete",
        add_alias_then_set_disposition,
    )

    with pytest.raises(ValueError, match="verified_unlink.*content"):
        package_io.secure_unlink_verified(
            victim,
            expected_identity=package_io.path_identity_from_status(
                package_io.plain_file_status(victim)
            ),
            expected_parent_identity=package_io.path_identity(tmp_path),
            expected_size=len(content),
            expected_sha256=hashlib.sha256(content).hexdigest(),
        )

    assert linked is True
    assert victim.read_bytes() == content
    assert alias.read_bytes() == content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_unlink_closes_with_native_fallback_after_os_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    victim = tmp_path / "victim.txt"
    content = b"reviewed\n"
    victim.write_bytes(content)
    identity = package_io.path_identity_from_status(package_io.plain_file_status(victim))
    close_handle = package_io._close_windows_handle_primary
    injected = False

    def fail_verified_handle_once(native_handle: int) -> None:
        nonlocal injected
        if not injected:
            injected = True
            raise OSError("injected native handle close failure")
        close_handle(native_handle)

    monkeypatch.setattr(
        package_io,
        "_close_windows_handle_primary",
        fail_verified_handle_once,
    )

    package_io.secure_unlink_verified(
        victim,
        expected_identity=identity,
        expected_parent_identity=package_io.path_identity(tmp_path),
        expected_size=len(content),
        expected_sha256=hashlib.sha256(content).hexdigest(),
    )

    assert injected is True
    assert victim.exists() is False
    victim.write_bytes(b"replacement\n")
    assert victim.read_bytes() == b"replacement\n"


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_verified_rmdir_rejects_directory_alternate_data_streams(
    tmp_path: Path,
) -> None:
    victim = tmp_path / "victim"
    victim.mkdir()
    stream = Path(f"{victim}:unbound")
    stream_content = b"unreviewed directory stream\n"
    stream.write_bytes(stream_content)

    with pytest.raises(ValueError, match="verified_rmdir.*stream|content.*changed"):
        package_io.secure_rmdir_verified(
            victim,
            expected_identity=package_io.path_identity(victim),
            expected_parent_identity=package_io.path_identity(tmp_path),
        )

    assert victim.is_dir()
    assert stream.read_bytes() == stream_content


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
def test_external_install_rejects_predecessor_alternate_stream_before_mutation(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "skills" / "hsconfig"
    destination.mkdir(parents=True)
    owned = destination / "old.txt"
    stream = Path(f"{owned}:unbound")
    content = b"reviewed\n"
    stream_content = b"unreviewed stream\n"
    owned.write_bytes(content)
    predecessor = _test_tree_aggregate(destination)
    stream.write_bytes(stream_content)

    with pytest.raises(ValueError, match="alternate_data_stream"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert owned.read_bytes() == content
    assert stream.read_bytes() == stream_content
    assert not list(destination.parent.glob(".hsconfig-install-*"))


@pytest.mark.skipif(os.name != "nt", reason="verified deletion is Windows-only")
@pytest.mark.parametrize("stream_owner", ("file", "directory", "root"))
def test_precommit_rollback_never_deletes_unknown_staging_streams(
    tmp_path: Path,
    stream_owner: str,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    parent.mkdir()
    stream_content = b"unreviewed staging stream\n"
    stage: Path | None = None
    stream: Path | None = None

    def inject_stream_and_interrupt(stage_name: str) -> None:
        nonlocal stage, stream
        if stage_name != "after_stage_write":
            return
        stage = next(parent.glob(".hsconfig-install-*.stage"))
        owner = (
            stage / "SKILL.md"
            if stream_owner == "file"
            else stage / "references"
            if stream_owner == "directory"
            else stage
        )
        stream = Path(f"{owner}:unbound")
        stream.write_bytes(stream_content)
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
            fault_hook=inject_stream_and_interrupt,
        )

    assert destination.exists() is False
    assert stage is not None and stage.is_dir()
    assert stream is not None and stream.read_bytes() == stream_content
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1


def test_phase_only_or_tampered_commit_journal_never_authorizes_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    replace_journal = external_skill_bundle._replace_journal

    def tamper(path: Path, value: dict[str, object]) -> None:
        altered = dict(value)
        altered["successor_tree_sha256"] = "0" * 64
        replace_journal(path, altered)
        raise KeyboardInterrupt()

    monkeypatch.setattr(external_skill_bundle, "_replace_journal", tamper)
    with pytest.raises(KeyboardInterrupt):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )
    monkeypatch.setattr(external_skill_bundle, "_replace_journal", replace_journal)

    with pytest.raises(ValueError, match="transaction|journal"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
        )

    assert destination.is_dir()
    assert len(list(parent.glob(".hsconfig-install-*.backup"))) == 1
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1


def test_oversize_committed_journal_rolls_back_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    for index in range(24):
        (destination / f"reviewed-{index:02d}.txt").write_text(
            f"reviewed-{index}\n",
            encoding="utf-8",
        )
    predecessor = _test_tree_aggregate(destination)
    before = {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    }
    monkeypatch.setattr(external_skill_bundle, "_MAX_JOURNAL_BYTES", 1_400)

    with pytest.raises(ValueError, match="journal_oversize"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
        )

    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == before
    assert _transaction_residue(parent) == []


@pytest.mark.parametrize("drift", ("target", "backup"))
def test_precommit_rollback_preserves_ambiguous_target_and_backup(
    tmp_path: Path,
    drift: str,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    def interrupt(stage: str) -> None:
        if stage != "after_destination_promote":
            return
        if drift == "target":
            (destination / "foreign.txt").write_text("foreign\n", encoding="utf-8")
        else:
            backup = next(parent.glob(".hsconfig-install-*.backup"))
            (backup / "foreign.txt").write_text("foreign\n", encoding="utf-8")
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=interrupt,
        )

    assert destination.is_dir()
    assert len(list(parent.glob(".hsconfig-install-*.backup"))) == 1
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1
    if drift == "target":
        assert (destination / "foreign.txt").read_text(encoding="utf-8") == "foreign\n"
    else:
        backup = next(parent.glob(".hsconfig-install-*.backup"))
        assert (backup / "foreign.txt").read_text(encoding="utf-8") == "foreign\n"
        assert {
            path.relative_to(destination).as_posix(): path.read_bytes()
            for path in destination.rglob("*")
            if path.is_file()
        } == load_embedded_skill_bundle()


def test_committed_cleanup_revalidates_target_after_fault_hook(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    def corrupt_target(stage: str) -> None:
        if stage == "before_backup_cleanup":
            (destination / "SKILL.md").unlink()

    with pytest.raises(ValueError, match="committed_target|materialization"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=corrupt_target,
        )

    backup = next(parent.glob(".hsconfig-install-*.backup"))
    assert (backup / "old.txt").read_text(encoding="utf-8") == "reviewed\n"
    assert len(list(parent.glob(".hsconfig-install-*.journal.json"))) == 1


def test_postcommit_journal_unlink_interrupt_never_deletes_new_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    (destination / "old.txt").write_text("reviewed\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)
    delete_owned_file = external_skill_bundle._delete_owned_file

    def interrupt_journal_unlink(
        path: Path,
        parent_identity: tuple[int, int, int],
    ) -> None:
        if path.name.endswith(".journal.json"):
            raise KeyboardInterrupt()
        delete_owned_file(path, parent_identity)

    monkeypatch.setattr(
        external_skill_bundle,
        "_delete_owned_file",
        interrupt_journal_unlink,
    )

    with pytest.raises(KeyboardInterrupt):
        kwargs = {}
        if (
            "expected_predecessor_aggregate_sha256"
            in inspect.signature(install_external_skill).parameters
        ):
            kwargs["expected_predecessor_aggregate_sha256"] = predecessor
        install_external_skill(destination, **kwargs)

    assert {
        path.relative_to(destination).as_posix(): path.read_bytes()
        for path in destination.rglob("*")
        if path.is_file()
    } == load_embedded_skill_bundle()
    journal = next(parent.glob(".hsconfig-install-*.journal.json"))
    assert json.loads(journal.read_text(encoding="utf-8"))["phase"] == "committed"


@pytest.mark.parametrize(
    ("stage", "error"),
    (
        ("after_destination_backup", KeyboardInterrupt()),
        ("after_destination_promote", SystemExit(7)),
    ),
)
def test_explicit_installer_rolls_back_baseexception_without_residue(
    tmp_path: Path,
    stage: str,
    error: BaseException,
) -> None:
    parent = tmp_path / "skills"
    destination = parent / "hsconfig"
    destination.mkdir(parents=True)
    original = destination / "original.txt"
    original.write_text("original\n", encoding="utf-8")
    predecessor = _test_tree_aggregate(destination)

    def fail(current: str) -> None:
        if current == stage:
            raise error

    with pytest.raises(type(error)):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=predecessor,
            fault_hook=fail,
        )

    assert original.read_text(encoding="utf-8") == "original\n"
    assert destination.is_dir()
    assert not [
        path for path in parent.iterdir() if path.name.startswith(".hsconfig-install-")
    ]


def test_explicit_installer_rejects_reparse_destination(tmp_path: Path) -> None:
    parent = tmp_path / "skills"
    parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = parent / "hsconfig"
    try:
        destination.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"platform does not permit test symlink: {error}")

    with pytest.raises(ValueError, match="unsafe|reparse|link"):
        install_external_skill(
            destination,
            expected_predecessor_aggregate_sha256=None,
        )

    assert tuple(outside.iterdir()) == ()
