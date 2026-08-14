from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
from typing import Any

import pytest

import hsconfig.publishable_tree as publishable_tree
from hsconfig.publishable_tree import (
    WORKING_PRE_CUTOVER_LEGACY_BASELINE,
    PublishableTreeError,
    capture_publishable_inventory,
    evaluate_publishable_tree,
    git_blob_oid,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_publishable_tree.py"


def _row(
    path: str,
    content: bytes = b"safe\n",
    *,
    git_mode: str = "100644",
    entry_kind: str = "regular",
    tracked: bool = True,
) -> dict[str, Any]:
    return {
        "path": path,
        "git_mode": git_mode,
        "entry_kind": entry_kind,
        "tracked": tracked,
        "blob_oid": git_blob_oid(content),
        "content_sha256": hashlib.sha256(content).hexdigest(),
        "content": content,
    }


def _git(repository: Path, *arguments: str, env: dict[str, str] | None = None) -> str:
    environment = os.environ.copy()
    for key in tuple(environment):
        if key.upper().startswith("GIT_"):
            environment.pop(key, None)
    if env:
        environment.update(env)
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env=environment,
        capture_output=True,
        check=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "HSConfig Tests")
    _git(repository, "config", "user.email", "tests@example.invalid")
    (repository / "README.md").write_text("# HSConfig\n", encoding="utf-8")
    (repository / "src" / "hsconfig").mkdir(parents=True)
    (repository / "src" / "hsconfig" / "module.py").write_text(
        "VALUE = 'safe'\n", encoding="utf-8"
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "fixture")
    return repository.resolve(strict=True)


def test_evaluator_accepts_only_closed_rows_and_returns_closed_document() -> None:
    result = evaluate_publishable_tree(
        (_row("README.md", b"# HSConfig\n"),),
        mode="final",
    )

    assert result == {
        "schema_version": 1,
        "mode": "final",
        "passed": True,
        "violations": [],
        "files_scanned": 1,
        "legacy_files_scanned": 0,
        "legacy_inventory_sha256": None,
    }

    unknown = _row("README.md")
    unknown["unexpected"] = True
    with pytest.raises(PublishableTreeError, match="schema"):
        evaluate_publishable_tree((unknown,), mode="final")


def test_release_gate_scanner_aliases_delegate_to_publishable_tree_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hsconfig.release_gate as release_gate

    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def path_classifier(relative: str) -> list[str]:
        calls.append(("path", (relative,), {}))
        return ["path-result"]

    def text_classifier(
        relative: str,
        data: bytes,
        **kwargs: Any,
    ) -> list[str]:
        calls.append(("text", (relative, data), kwargs))
        return ["text-result"]

    monkeypatch.setattr(release_gate, "publishable_path_violations", path_classifier)
    monkeypatch.setattr(release_gate, "publishable_text_violations", text_classifier)

    assert release_gate._path_violations("README.md") == ["path-result"]
    assert release_gate._text_violations(
        "README.md",
        b"# HSConfig\n",
        public_doc=True,
    ) == ["text-result"]
    assert calls[0] == ("path", ("README.md",), {})
    assert calls[1][0:2] == ("text", ("README.md", b"# HSConfig\n"))
    assert calls[1][2]["public_doc"] is True


@pytest.mark.parametrize(
    "path",
    (
        "../README.md",
        "/README.md",
        "C" + ":/README.md",
        "docs\\operator\\README.md",
        "docs/operator/../README.md",
        "docs/operator/readme.md:stream",
        "docs/operator/unsafe\x01.md",
        "docs/operator/e\u0301.md",
    ),
)
def test_evaluator_rejects_noncanonical_or_unsafe_paths(path: str) -> None:
    result = evaluate_publishable_tree((_row(path),), mode="final")

    assert result["passed"] is False
    assert any("path" in violation for violation in result["violations"])


def test_evaluator_rejects_casefold_duplicates_unknown_roots_and_untracked_final() -> None:
    rows = (
        _row("docs/contracts/Guide.md"),
        _row("docs/contracts/guide.md"),
        _row("private/notes.md"),
        _row("src/hsconfig/untracked.py", tracked=False),
    )

    result = evaluate_publishable_tree(rows, mode="final")

    assert result["passed"] is False
    assert any(row.startswith("casefold_duplicate:") for row in result["violations"])
    assert "unexpected_root:private/notes.md" in result["violations"]
    assert "untracked:src/hsconfig/untracked.py" in result["violations"]


@pytest.mark.parametrize(
    ("git_mode", "entry_kind"),
    (
        ("120000", "symlink"),
        ("160000", "gitlink"),
        ("100644", "reparse"),
        ("100644", "other"),
    ),
)
def test_evaluator_rejects_nonregular_link_reparse_and_gitlink(
    git_mode: str,
    entry_kind: str,
) -> None:
    result = evaluate_publishable_tree(
        (_row("src/hsconfig/module.py", git_mode=git_mode, entry_kind=entry_kind),),
        mode="final",
    )

    assert result["passed"] is False
    assert any(row.startswith("non_regular:") for row in result["violations"])


@pytest.mark.parametrize(
    ("path", "content", "prefix"),
    (
        ("build/result.txt", b"safe\n", "residue:"),
        ("src/hsconfig/client-secret.pem", b"safe\n", "secret:"),
        ("Power.log", b"safe\n", "private_runtime_evidence:"),
        (
            "src/hsconfig/settings.json",
            b'{"database' b'Password":"A7b9C2d4E6f8G1h3J5k7L9m2' b'N4p6Q8r1S3t5U7v9W2x4"}\n',
            "secret:",
        ),
        ("docs/contracts/guide.md", b"PLACE" b"HOLDER\n", "public_placeholder:"),
    ),
)
def test_evaluator_reuses_secret_runtime_residue_and_placeholder_detection(
    path: str,
    content: bytes,
    prefix: str,
) -> None:
    result = evaluate_publishable_tree((_row(path, content),), mode="final")

    assert any(row.startswith(prefix) for row in result["violations"])


def test_evaluator_rejects_unsafe_or_unresolved_markdown_links_and_anchors() -> None:
    rows = tuple(sorted((
        _row(
            "docs/contracts/guide.md",
            b"# Guide\n[missing](missing.md)\n[bad](../research/private.md)\n"
            b"[anchor](#missing-heading)\n[unsafe](file:///private)\n",
        ),
        _row("README.md", b"# HSConfig\n[guide](docs/contracts/guide.md#guide)\n"),
    ), key=lambda row: row["path"].encode("utf-8")))

    result = evaluate_publishable_tree(rows, mode="final")

    assert result["passed"] is False
    assert any(row.startswith("unresolved_markdown_link:") for row in result["violations"])
    assert any(row.startswith("unsafe_markdown_link:") for row in result["violations"])
    assert any(row.startswith("unresolved_markdown_anchor:") for row in result["violations"])


def test_evaluator_rejects_missing_markdown_images_and_undefined_references() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n![missing](missing.md)\n[reference][missing-id]\n",
            ),
        ),
        mode="final",
    )

    assert "unresolved_markdown_link:docs/contracts/guide.md:missing.md" in result[
        "violations"
    ]
    assert "undefined_markdown_reference:docs/contracts/guide.md:missing-id" in result[
        "violations"
    ]


def test_evaluator_accepts_defined_link_and_image_references_outside_code() -> None:
    rows = tuple(
        sorted(
            (
                _row(
                    "docs/contracts/guide.md",
                    b"# Guide\n[operator][Operator Ref]\n![diagram][diagram ref]\n"
                    b"[collapsed][]\n![collapsed image][]\n"
                    b"[operator ref]: ../operator/README.md#operator-guide\n"
                    b"[diagram ref]: diagram.png\n"
                    b"[collapsed]: ../operator/README.md\n"
                    b"[collapsed image]: diagram.png\n"
                    b"`[ignored](missing-inline.md)`\n"
                    b"```markdown\n[ignored][missing-fenced]\n"
                    b"![ignored](missing-fenced.md)\n```\n",
                ),
                _row("docs/contracts/diagram.png", b"PNG\n"),
                _row("docs/operator/README.md", b"# Operator Guide\n"),
            ),
            key=lambda row: row["path"].encode("utf-8"),
        )
    )

    result = evaluate_publishable_tree(rows, mode="final")

    assert result["passed"] is True
    assert result["violations"] == []


def test_markdown_scanner_rejects_invalid_fence_entity_scheme_and_balanced_gap() -> None:
    rows = tuple(
        sorted(
            (
                _row(
                    "docs/contracts/guide.md",
                    b"# Guide\n```bad`\n[x](file:///private)\n"
                    b"[entity](javascript&colon;alert.md)\n"
                    b"[balanced](guide(v1).md)\n````\n",
                ),
                _row("docs/contracts/guide(v1", b"# Truncated\n"),
                _row("docs/contracts/javascript&colon;alert.md", b"# Unsafe\n"),
            ),
            key=lambda row: row["path"].encode("utf-8"),
        )
    )

    result = evaluate_publishable_tree(rows, mode="final")

    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///private" in result[
        "violations"
    ]
    assert (
        "unsafe_markdown_link:docs/contracts/guide.md:javascript:alert.md"
        in result["violations"]
    )
    assert "unresolved_markdown_link:docs/contracts/guide.md:guide(v1).md" in result[
        "violations"
    ]


def test_markdown_scanner_ignores_multiline_exact_inline_code_span() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n`literal\n[x](missing.md)\n![x][missing]\nend`\n",
            ),
        ),
        mode="final",
    )

    assert result["passed"] is True
    assert result["violations"] == []


def test_markdown_scanner_does_not_join_code_spans_across_paragraphs() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n`open\n\n[x](file:///private)\n\nclose`\n",
            ),
        ),
        mode="final",
    )

    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///private" in result[
        "violations"
    ]


def test_markdown_scanner_parses_escaped_and_nested_inline_labels() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n[label \\]](file:///escaped)\n"
                b"![outer [inner]](file:///nested)\n",
            ),
        ),
        mode="final",
    )

    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///escaped" in result[
        "violations"
    ]
    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///nested" in result[
        "violations"
    ]


def test_markdown_scanner_preserves_angle_destination_whitespace() -> None:
    rows = tuple(
        sorted(
            (
                _row(
                    "docs/contracts/guide.md",
                    b"# Guide\n[missing](<guide v1.md>)\n",
                ),
                _row("docs/contracts/guide", b"# Truncated\n"),
            ),
            key=lambda row: row["path"].encode("utf-8"),
        )
    )

    result = evaluate_publishable_tree(rows, mode="final")

    assert "unresolved_markdown_link:docs/contracts/guide.md:guide v1.md" in result[
        "violations"
    ]


def test_markdown_scanner_ignores_fenced_code_inside_blockquote() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n> ~~~markdown\n> [x](missing.md)\n> ~~~\n",
            ),
        ),
        mode="final",
    )

    assert result["passed"] is True
    assert result["violations"] == []


def test_markdown_blockquote_code_never_masks_unquoted_unsafe_links() -> None:
    fenced = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/fenced.md",
                b"# Guide\n> ~~~markdown\n[x](file:///outside)\n~~~\n",
            ),
        ),
        mode="final",
    )
    inline = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/inline.md",
                b"# Guide\n> `open\n> close`\n\n[x](file:///outside-inline)\n",
            ),
        ),
        mode="final",
    )

    assert "unsafe_markdown_link:docs/contracts/fenced.md:file:///outside" in fenced[
        "violations"
    ]
    assert (
        "unsafe_markdown_link:docs/contracts/inline.md:file:///outside-inline"
        in inline["violations"]
    )


def test_unmarked_lazy_blockquote_inline_code_remains_inert() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/lazy-code.md",
                b"> `open\n[code](missing-code.md)\n> close`\n",
            ),
        ),
        mode="final",
    )

    assert result["passed"] is True
    assert result["violations"] == []


def test_markdown_code_spans_do_not_cross_atx_heading_blocks() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/heading-boundary.md",
                b"`open\n# Heading\n[x](file:///outside-heading)\nclose`\n",
            ),
        ),
        mode="final",
    )

    assert (
        "unsafe_markdown_link:docs/contracts/heading-boundary.md:"
        "file:///outside-heading"
        in result["violations"]
    )


def test_markdown_code_spans_do_not_cross_list_block_boundaries() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/list-boundary.md",
                b"`open\n- [x](file:///outside-list)\nclose`\n",
            ),
        ),
        mode="final",
    )

    assert (
        "unsafe_markdown_link:docs/contracts/list-boundary.md:file:///outside-list"
        in result["violations"]
    )


def test_markdown_indented_continuation_links_remain_visible() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/list-continuation.md",
                b"- item\n    [x](file:///outside-list-continuation)\n",
            ),
            _row(
                "docs/contracts/paragraph-continuation.md",
                b"Paragraph\n    [x](file:///outside-paragraph-continuation)\n",
            ),
            _row(
                "docs/contracts/standalone-code.md",
                b"    [x](file:///ignored-standalone-code)\n",
            ),
        ),
        mode="final",
    )

    assert (
        "unsafe_markdown_link:docs/contracts/list-continuation.md:"
        "file:///outside-list-continuation"
        in result["violations"]
    )
    assert (
        "unsafe_markdown_link:docs/contracts/paragraph-continuation.md:"
        "file:///outside-paragraph-continuation"
        in result["violations"]
    )
    assert all("ignored-standalone-code" not in item for item in result["violations"])


@pytest.mark.parametrize(
    ("source", "target"),
    (
        ("> quote\n    [x](missing.md)\n", "missing.md"),
        ("> quote\n    ![x](missing.png)\n", "missing.png"),
        ("> [x](\n> missing.md\n> )\n", "missing.md"),
        ("> ![x](\n> missing.png\n> )\n", "missing.png"),
    ),
)
def test_commonmark_blockquote_continuations_expose_link_and_image_targets(
    source: str,
    target: str,
) -> None:
    scan = publishable_tree._scan_markdown_document(source)
    result = evaluate_publishable_tree(
        (_row("docs/contracts/blockquote.md", source.encode("utf-8")),),
        mode="final",
    )

    assert target in scan.targets
    assert f"unresolved_markdown_link:docs/contracts/blockquote.md:{target}" in result[
        "violations"
    ]


def test_commonmark_blockquote_indented_code_remains_non_navigating() -> None:
    source = "> quote\n>\n>     [x](missing.md)\n"
    scan = publishable_tree._scan_markdown_document(source)
    result = evaluate_publishable_tree(
        (_row("docs/contracts/blockquote-code.md", source.encode("utf-8")),),
        mode="final",
    )

    assert scan.targets == ()
    assert result["passed"] is True


@pytest.mark.parametrize(
    ("markdown", "target"),
    (
        ("[multi\nlabel](file:///multiline-label)\n", "file:///multiline-label"),
        ("![multi\nalt](file:///multiline-image)\n", "file:///multiline-image"),
        (
            "[x](\n" + "file:" + "/" * 3 + "multiline-destination\n)\n",
            "file:" + "/" * 3 + "multiline-destination",
        ),
        (
            "[x](" + "file:" + "/" * 3 + "multiline-title\n\"two\nline title\")\n",
            "file:" + "/" * 3 + "multiline-title",
        ),
    ),
)
def test_markdown_commonmark_multiline_inline_targets_are_enforced(
    markdown: str,
    target: str,
) -> None:
    result = evaluate_publishable_tree(
        (_row("docs/contracts/multiline.md", markdown.encode("utf-8")),),
        mode="final",
    )
    scan = publishable_tree._scan_markdown_document(markdown)

    assert target in scan.targets
    assert f"unsafe_markdown_link:docs/contracts/multiline.md:{target}" in result[
        "violations"
    ]


def test_markdown_multiline_reference_definition_and_missing_target_are_enforced() -> None:
    source = (
        "[defined]\n[missing\nreference][]\n\n"
        "[defined]:\n  "
        + "file:"
        + "/" * 3
        + "multiline-reference\n  \"two line title\"\n"
    )
    result = evaluate_publishable_tree(
        (_row("docs/contracts/references.md", source.encode("utf-8")),),
        mode="final",
    )

    assert (
        "unsafe_markdown_link:docs/contracts/references.md:"
        "file:///multiline-reference"
        in result["violations"]
    )
    assert (
        "undefined_markdown_reference:docs/contracts/references.md:missing reference"
        in result["violations"]
    )


def test_blank_separated_nested_ordered_list_targets_are_not_indented_code() -> None:
    active = (
        "1. outer\n\n"
        "   1. nested\n\n"
        "      [x](file:///nested-list)\n"
    )
    genuine_code = (
        "1. outer\n\n"
        "   1. nested\n\n"
        "          [x](file:///nested-code)\n"
    )
    result = evaluate_publishable_tree(
        (
            _row("docs/contracts/nested-code.md", genuine_code.encode("utf-8")),
            _row("docs/contracts/nested-list.md", active.encode("utf-8")),
        ),
        mode="final",
    )

    assert (
        "unsafe_markdown_link:docs/contracts/nested-list.md:file:///nested-list"
        in result["violations"]
    )
    assert all("nested-code" not in row for row in result["violations"])


@pytest.mark.parametrize(
    "raw_html",
    (
        '<a\n href="file:///raw-href">unsafe</a>',
        '<img\n src="javascript&colon;alert">',
    ),
)
def test_raw_html_navigation_attributes_fail_closed(raw_html: str) -> None:
    source = f"# Guide\n{raw_html}\n"
    result = evaluate_publishable_tree(
        (_row("docs/contracts/raw-html.md", source.encode("utf-8")),),
        mode="final",
    )

    assert "markdown_parse_error:docs/contracts/raw-html.md" in result["violations"]


def test_raw_html_navigation_text_inside_code_remains_ignored() -> None:
    source = (
        '`<a href="file:///inline-code">x</a>`\n\n'
        "```html\n<img src=\"file:///fenced-code\">\n```\n"
    )
    result = evaluate_publishable_tree(
        (_row("docs/contracts/raw-html-code.md", source.encode("utf-8")),),
        mode="final",
    )

    assert result["passed"] is True


@pytest.mark.parametrize(
    "raw_html",
    (
        '<a\fhref="missing.md">unsafe</a>',
        '<svg><a xlink:href="missing.md">unsafe</a></svg>',
    ),
)
def test_html5_space_and_namespaced_navigation_attributes_fail_closed(
    raw_html: str,
) -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/raw-html-navigation.md",
                f"{raw_html}\n".encode("utf-8"),
            ),
        ),
        mode="final",
    )

    assert "markdown_parse_error:docs/contracts/raw-html-navigation.md" in result[
        "violations"
    ]


def test_html5_space_and_namespaced_navigation_inside_code_remain_ignored() -> None:
    source = (
        '`<a\fhref="missing-inline.md">x</a>`\n\n'
        "```html\n<svg><a xlink:href=\"missing-fenced.md\">x</a></svg>\n```\n"
    )
    result = evaluate_publishable_tree(
        (_row("docs/contracts/raw-html-code.md", source.encode("utf-8")),),
        mode="final",
    )

    assert result["passed"] is True


@pytest.mark.parametrize(
    "source,target",
    (
        ("> [multi\nlabel](missing-label.md)\n", "missing-label.md"),
        ("> [x](\nmissing-destination.md\n)\n", "missing-destination.md"),
        ('> [x](missing-title.md\n"title")\n', "missing-title.md"),
        ("> ![x](\nmissing-image.png\n)\n", "missing-image.png"),
    ),
)
def test_unmarked_lazy_blockquote_continuations_keep_navigation_visible(
    source: str,
    target: str,
) -> None:
    result = evaluate_publishable_tree(
        (_row("docs/contracts/lazy-blockquote.md", source.encode("utf-8")),),
        mode="final",
    )

    assert (
        f"unresolved_markdown_link:docs/contracts/lazy-blockquote.md:{target}"
        in result["violations"]
    )


def test_lazy_blockquote_navigation_does_not_open_closed_code_containers() -> None:
    source = (
        "> paragraph\n"
        ">\n"
        ">     [code](missing-code.md)\n\n"
        "> ```md\n"
        "> [fenced](missing-fenced.md)\n"
        "> ```\n\n"
        "[outside](https://example.com/current)\n"
    )
    result = evaluate_publishable_tree(
        (_row("docs/contracts/lazy-controls.md", source.encode("utf-8")),),
        mode="final",
    )

    assert result["passed"] is True


def test_multiline_markdown_scanning_stays_within_the_linear_work_budget() -> None:
    construct = "[multi\nlabel](https://example.com/path\n\"title\")\n"
    source = construct * 2_000

    scan = publishable_tree._scan_markdown_document(source)

    assert scan.targets.count("https://example.com/path") == 2_000
    assert scan.work_units <= len(source) * 32 + 1024


def test_markdown_tokenizer_rejects_nested_targets_shortcuts_and_unsafe_autolinks() -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                b"# Guide\n[![nested](file:///nested-only)](https://example.com)\n"
                b"[missing shortcut]\n![missing shortcut image]\n"
                b"<file:///private>\n<javascript:alert>\n",
            ),
        ),
        mode="final",
    )

    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///nested-only" in result[
        "violations"
    ]
    assert "unsafe_markdown_link:docs/contracts/guide.md:file:///private" in result[
        "violations"
    ]
    assert "unsafe_markdown_link:docs/contracts/guide.md:javascript:alert" in result[
        "violations"
    ]
    assert "undefined_markdown_reference:docs/contracts/guide.md:missing shortcut" in result[
        "violations"
    ]
    assert (
        "undefined_markdown_reference:docs/contracts/guide.md:missing shortcut image"
        in result["violations"]
    )


def test_markdown_autolinks_with_backticks_are_not_hidden_as_code_spans() -> None:
    source = "# Guide\n<file:///private`ignored`>\n<https://example.com/`safe`>\n"
    result = evaluate_publishable_tree(
        (_row("docs/contracts/guide.md", source.encode("utf-8")),),
        mode="final",
    )
    scan = publishable_tree._scan_markdown_document(source)

    assert (
        "unsafe_markdown_link:docs/contracts/guide.md:file:///private`ignored`"
        in result["violations"]
    )
    assert "file:///private`ignored`" in scan.targets
    assert "https://example.com/`safe`" in scan.targets


def test_markdown_tokenizer_accepts_https_email_and_defined_shortcut_autolinks() -> None:
    source = (
        "# Guide\n<https://example.com/hsconfig>\n<operator@example.com>\n"
        "[policy]\n![policy image]\n"
        "[policy]: policy.md\n[policy image]: policy.png\n"
    )
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/contracts/guide.md",
                source.encode("utf-8"),
            ),
            _row("docs/contracts/policy.md", b"# Policy\n"),
            _row("docs/contracts/policy.png", b"PNG\n"),
        ),
        mode="final",
    )

    assert result["passed"] is True
    assert result["violations"] == []
    scan = publishable_tree._scan_markdown_document(source)
    assert scan.targets.count("policy.md") == 2
    assert scan.targets.count("policy.png") == 2
    assert "https://example.com/hsconfig" in scan.targets
    assert "mailto:operator@example.com" in scan.targets


def test_markdown_tokenizer_has_a_deterministic_linear_work_budget() -> None:
    malformed = "[x](<" * 20_000
    repeated_valid = "[x](https://example.com)\n" * 5_000

    scan = publishable_tree._scan_markdown_document(repeated_valid)

    assert scan.work_units <= len(repeated_valid) * 32 + 1024
    with pytest.raises(PublishableTreeError, match="work budget"):
        publishable_tree._scan_markdown_document(malformed)
    with pytest.raises(PublishableTreeError, match="work budget"):
        publishable_tree._scan_markdown_document(malformed, operation_limit=32)


@pytest.mark.parametrize(
    "legacy_path",
    (
        ".agents/old.md",
        ".superpowers/old.md",
        "docs/history/old.md",
        "docs/research/old.md",
        "docs/superpowers/old.md",
        "docs/operator/autonomous-source-builder-next.md",
        "docs/operator/boarlock-fracking-source-decision.md",
        "docs/operator/git-branch-cleanup-audit-2026-07-17.md",
        "docs/operator/kingslayer-quick-pick-source-decision.md",
        "docs/operator/source-backed-strong-closure.md",
        "docs/operator/source-builder-workflow.md",
        "docs/operator/universal-wild-no-block-contract.md",
    ),
)
def test_working_mode_rejects_active_links_and_images_into_every_legacy_path(
    legacy_path: str,
) -> None:
    legacy = _row(legacy_path, b"# Historical\n[ignored](file:///private)\n")
    source_parent = PurePosixPath("docs/contracts")
    target_parts = [".."] * len(source_parent.parts) + legacy_path.split("/")
    raw_target = "/".join(target_parts)
    active = _row(
        "docs/contracts/guide.md",
        (
            f"# Guide\n[legacy]({raw_target})\n![legacy image]({raw_target})\n"
        ).encode("utf-8"),
    )
    inventory = tuple(
        sorted((legacy, active), key=lambda row: str(row["path"]).encode("utf-8"))
    )
    baseline = {
        "schema_version": 1,
        "count": 1,
        "aggregate_sha256": publishable_tree._legacy_digest((legacy,)),
    }

    result = evaluate_publishable_tree(
        inventory,
        mode="working-pre-cutover",
        legacy_baseline=baseline,
    )

    assert f"legacy_markdown_link:docs/contracts/guide.md:{raw_target}" in result[
        "violations"
    ]
    assert not any(
        violation.startswith(f"unsafe_markdown_link:{legacy_path}:")
        for violation in result["violations"]
    )
    scan = publishable_tree._scan_markdown_document(active["content"].decode("utf-8"))
    assert scan.targets.count(raw_target) == 2


def test_working_mode_rejects_percent_encoded_traversal_into_legacy_path() -> None:
    legacy = _row("docs/research/old.md", b"# Historical\n")
    raw_target = "%2E%2E/%2E%2E/docs/research/old.md"
    active = _row(
        "docs/contracts/guide.md",
        f"# Guide\n[legacy]({raw_target})\n".encode("utf-8"),
    )
    inventory = tuple(
        sorted((legacy, active), key=lambda row: str(row["path"]).encode("utf-8"))
    )
    baseline = {
        "schema_version": 1,
        "count": 1,
        "aggregate_sha256": publishable_tree._legacy_digest((legacy,)),
    }

    result = evaluate_publishable_tree(
        inventory,
        mode="working-pre-cutover",
        legacy_baseline=baseline,
    )

    assert f"legacy_markdown_link:docs/contracts/guide.md:{raw_target}" in result[
        "violations"
    ]


def test_working_mode_rejects_multiline_and_nested_list_links_into_legacy() -> None:
    legacy_path = "docs/research/old.md"
    legacy = _row(legacy_path, b"# Historical\n")
    source = PurePosixPath("docs/contracts/guide.md")
    target = "../research/old.md"
    active = _row(
        source.as_posix(),
        (
            f"[multi\nlegacy]({target})\n\n"
            "1. outer\n\n"
            "   1. nested\n\n"
            f"      ![legacy image]({target})\n"
        ).encode("utf-8"),
    )
    baseline = {
        "schema_version": 1,
        "count": 1,
        "aggregate_sha256": publishable_tree._legacy_digest((legacy,)),
    }

    result = evaluate_publishable_tree(
        tuple(sorted((legacy, active), key=lambda row: str(row["path"]).encode("utf-8"))),
        mode="working-pre-cutover",
        legacy_baseline=baseline,
    )

    assert f"legacy_markdown_link:{source.as_posix()}:{target}" in result["violations"]


@pytest.mark.parametrize(
    "legacy_reference",
    (
        ".agents/",
        ".superpowers/",
        "docs/history/",
        "docs/research/",
        "docs/superpowers/",
        "docs/operator/autonomous-source-builder-next.md",
        "docs/operator/boarlock-fracking-source-decision.md",
        "docs/operator/git-branch-cleanup-audit-2026-07-17.md",
        "docs/operator/kingslayer-quick-pick-source-decision.md",
        "docs/operator/source-backed-strong-closure.md",
        "docs/operator/source-builder-workflow.md",
        "docs/operator/universal-wild-no-block-contract.md",
    ),
)
def test_active_docs_reject_every_legacy_authority_string_even_in_code_prose(
    legacy_reference: str,
) -> None:
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/operator/active-policy.md",
                f"Future authority: `{legacy_reference}`.\n".encode("utf-8"),
            ),
        ),
        mode="final",
    )

    assert (
        f"legacy_authority_reference:docs/operator/active-policy.md:{legacy_reference}"
        in result["violations"]
    )


@pytest.mark.parametrize(
    "legacy_reference",
    (
        ".agents/",
        ".superpowers/",
        "docs/history/",
        "docs/research/",
        "docs/superpowers/",
        "docs/operator/autonomous-source-builder-next.md",
        "docs/operator/boarlock-fracking-source-decision.md",
        "docs/operator/git-branch-cleanup-audit-2026-07-17.md",
        "docs/operator/kingslayer-quick-pick-source-decision.md",
        "docs/operator/source-backed-strong-closure.md",
        "docs/operator/source-builder-workflow.md",
        "docs/operator/universal-wild-no-block-contract.md",
    ),
)
@pytest.mark.parametrize("variant", ("casefold", "backslash", "dot_segment"))
def test_active_docs_semantically_normalize_every_legacy_authority_reference(
    legacy_reference: str,
    variant: str,
) -> None:
    if variant == "casefold":
        rendered = legacy_reference.upper()
    elif variant == "backslash":
        rendered = legacy_reference.replace("/", "\\")
    else:
        parts = legacy_reference.rstrip("/").split("/")
        if len(parts) == 1:
            rendered = f"{parts[0]}/./"
        else:
            rendered = "/".join((*parts[:-1], ".", parts[-1]))
            if legacy_reference.endswith("/"):
                rendered += "/"
    result = evaluate_publishable_tree(
        (
            _row(
                "docs/operator/active-policy.md",
                f"Future authority: `{rendered}`.\n".encode("utf-8"),
            ),
        ),
        mode="final",
    )

    assert (
        f"legacy_authority_reference:docs/operator/active-policy.md:{legacy_reference}"
        in result["violations"]
    )


def test_active_operator_no_block_route_does_not_target_frozen_obsolete_doc() -> None:
    operator = (ROOT / "docs/operator/README.md").read_text(encoding="utf-8")

    assert "docs/operator/universal-wild-no-block-contract.md" not in operator
    assert "[pre-run contract](../contracts/pre-run-contract.md)" in operator
    assert "source-candidate plan visibility,\nvisibility" not in operator


def test_working_mode_requires_the_exact_bound_legacy_inventory() -> None:
    legacy = _row("docs/research/old.md", b"historical\n")

    missing = evaluate_publishable_tree((legacy,), mode="working-pre-cutover")
    wrong = evaluate_publishable_tree(
        (legacy,),
        mode="working-pre-cutover",
        legacy_baseline={
            "schema_version": 1,
            "count": 1,
            "aggregate_sha256": "0" * 64,
        },
    )
    final = evaluate_publishable_tree((legacy,), mode="final")

    assert "legacy_baseline_missing" in missing["violations"]
    assert any(row.startswith("legacy_inventory_mismatch:") for row in wrong["violations"])
    assert "legacy_path:docs/research/old.md" in final["violations"]


def test_working_mode_accepts_complete_cutover_but_rejects_partial_legacy() -> None:
    active = _row("README.md", b"# HSConfig\n")
    partial = _row("docs/research/old.md", b"historical\n")

    complete_cutover = evaluate_publishable_tree(
        (active,),
        mode="working-pre-cutover",
        legacy_baseline=WORKING_PRE_CUTOVER_LEGACY_BASELINE,
    )
    partial_cutover = evaluate_publishable_tree(
        tuple(sorted((active, partial), key=lambda row: str(row["path"]).encode("utf-8"))),
        mode="working-pre-cutover",
        legacy_baseline=WORKING_PRE_CUTOVER_LEGACY_BASELINE,
    )

    assert complete_cutover["passed"] is True
    assert complete_cutover["legacy_files_scanned"] == 0
    assert complete_cutover["legacy_inventory_sha256"] is None
    assert any(
        row.startswith("legacy_inventory_mismatch:")
        for row in partial_cutover["violations"]
    )


def test_repository_working_inventory_is_bound_baseline_or_complete_cutover() -> None:
    inventory = capture_publishable_inventory(ROOT, mode="working-pre-cutover")
    result = evaluate_publishable_tree(
        inventory,
        mode="working-pre-cutover",
        legacy_baseline=WORKING_PRE_CUTOVER_LEGACY_BASELINE,
    )

    assert (
        result["legacy_files_scanned"],
        result["legacy_inventory_sha256"],
    ) in {
        (
            538,
            "e512a342802139b4f61dc5e9a216b1c840f833fa35b924077647fcaa042f5e9d",
        ),
        (0, None),
    }
    assert not any(row.startswith("legacy_inventory_mismatch:") for row in result["violations"])


def test_candidate_index_reads_only_the_named_index_and_rejects_legacy(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    index = tmp_path / "candidate.index"
    env = {"GIT_INDEX_FILE": str(index)}
    _git(repository, "read-tree", "HEAD", env=env)

    # The synthetic blob must exist in the object database before the index can name it.
    # Rewrite the row through hash-object, then validate the detached candidate inventory.
    blob = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"],
        cwd=repository,
        input=b"old\n",
        capture_output=True,
        check=True,
        timeout=60,
    ).stdout.decode().strip()
    _git(repository, "update-index", "--add", "--cacheinfo", "100644", blob, "docs/research/old.md", env=env)

    inventory = capture_publishable_inventory(
        repository,
        mode="candidate-index",
        index_file=index,
    )
    result = evaluate_publishable_tree(inventory, mode="candidate-index")

    assert "legacy_path:docs/research/old.md" in result["violations"]


def test_cli_emits_one_json_and_uses_0_1_2_exit_contract(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    passing = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(repository),
            "--mode",
            "final",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    (repository / "private").mkdir()
    (repository / "private" / "result.txt").write_text("not public\n", encoding="utf-8")
    failing = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(repository),
            "--mode",
            "final",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    invalid = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--root",
            str(repository),
            "--mode",
            "candidate-index",
            "--json",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert passing.returncode == 0
    assert json.loads(passing.stdout)["passed"] is True
    assert passing.stderr == ""
    assert failing.returncode == 1
    assert json.loads(failing.stdout)["passed"] is False
    assert failing.stderr == ""
    assert invalid.returncode == 2
    assert set(json.loads(invalid.stdout)) == {"error", "schema_version"}
    assert invalid.stderr == ""
