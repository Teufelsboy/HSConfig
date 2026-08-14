from __future__ import annotations

from pathlib import Path
import re
import shutil
import stat

import pytest

from tests.helpers.markdown_contract import (
    CANONICAL_PUBLIC_METADATA_SHA256,
    normalized_utf8_sha256,
    scan_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DESCRIPTION = (
    "HSConfig builds guide-aligned HearthRanger VisionAI `CustomConfig` packages "
    "from a Hearthstone deck name and deck code."
)
REQUIRED_HEADINGS = (
    "## License and visibility",
    "## Scope and non-goals",
    "## Installation",
    "## Normal operation",
    "## Verification",
    "## Documentation",
)
EXPECTED_LINKS = (
    "docs/operator/README.md",
    "docs/architecture/overview.md",
    "docs/contracts/pre-run-contract.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
)
NORMAL_CONFIGURE_COMMAND = (
    'hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" '
    '--runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" --json'
)
PRESERVED_ANCHORS = (
    "Preferred normal path: `hsconfig configure`.",
    "Runtime writes happen only through `hsconfig apply` or `hsconfig configure --apply`.",
    "docs/operator/README.md",
    "local Clean-OID producer/verifier",
    "single locked `ci` workflow",
    "`contract`, `test`, `package`, and `security`",
)
PRESERVED_ANCHOR_EXACT_COUNTS = {anchor: 1 for anchor in PRESERVED_ANCHORS}


def _copy_readme_context(destination: Path) -> Path:
    for relative in (
        Path("README.md"),
        Path("SECURITY.md"),
        Path("CONTRIBUTING.md"),
        Path("docs/operator/README.md"),
        Path("docs/architecture/overview.md"),
        Path("docs/contracts/pre-run-contract.md"),
    ):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return destination


def _validate_internal_link(root: Path, target: str) -> str | None:
    relative = Path(target)
    if relative.is_absolute() or relative.drive or ".." in relative.parts:
        return f"readme_link_outside_root:{target}"
    root_resolved = root.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError:
        return f"readme_link_outside_root:{target}"

    current = root
    for index, part in enumerate(relative.parts):
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            return f"readme_dangling_link:{target}"
        reparse = bool(
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        if stat.S_ISLNK(metadata.st_mode) or reparse:
            return f"readme_unsafe_link:{target}"
        is_final = index == len(relative.parts) - 1
        if is_final and not stat.S_ISREG(metadata.st_mode):
            return f"readme_dangling_link:{target}"
        if not is_final and not stat.S_ISDIR(metadata.st_mode):
            return f"readme_dangling_link:{target}"
    return None


def _visible_anchor_count(normalized: str, anchor: str) -> int:
    prefix = r"(?<![\w/])" if anchor[0].isalnum() else ""
    suffix = r"(?![\w/])" if anchor[-1].isalnum() else ""
    return len(re.findall(prefix + re.escape(anchor) + suffix, normalized))


def _presentation_text(text: str) -> str:
    return " ".join(scan_markdown(text).presentation_prose.split())


def _readme_contract_errors(root: Path) -> list[str]:
    errors: list[str] = []
    readme_path = root / "README.md"
    if not readme_path.is_file():
        return ["missing_readme"]
    try:
        text = readme_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return ["readme_invalid_utf8", "readme_canonical_integrity"]
    if (
        normalized_utf8_sha256(text)
        != CANONICAL_PUBLIC_METADATA_SHA256["README.md"]
    ):
        errors.append("readme_canonical_integrity")
    document = scan_markdown(text)
    scanner_error_map = {
        "angle_autolink": "readme_unsupported_link_syntax:autolink",
        "bare_email": "readme_unsupported_link_syntax:bare_email",
        "bare_url": "readme_unsupported_link_syntax:bare_url",
        "raw_html": "readme_unsupported_link_syntax:html",
        "reference_link": "readme_unsupported_link_syntax:reference",
        "unclosed_code_span": "readme_unclosed_code_span",
        "unclosed_fence": "readme_unclosed_fence",
        "unclosed_html_comment": "readme_unclosed_html_comment",
    }
    for scanner_error in document.errors:
        mapped = scanner_error_map.get(
            scanner_error.reason,
            "readme_unsupported_link_syntax:inline",
        )
        if mapped not in errors:
            errors.append(mapped)

    prose_text = document.prose_source
    presentation_normalized = " ".join(document.presentation_prose.split())
    prose_lines = document.prose_source_lines
    rendered_lines = document.presentation_rendered_lines
    nonempty = [line for line in prose_lines if line.strip()]
    if nonempty[:2] != ["# HSConfig", PRODUCT_DESCRIPTION]:
        errors.append("readme_product_description_order")

    positions = [
        next(
            (
                token.line
                for token in document.headings
                if token.raw == heading and token.level == 2
            ),
            -1,
        )
        for heading in REQUIRED_HEADINGS
    ]
    if any(position < 0 for position in positions):
        errors.append("readme_required_sections")
    elif positions != sorted(positions):
        errors.append("readme_section_order")
    for heading in REQUIRED_HEADINGS:
        if sum(
            token.raw == heading and token.level == 2 for token in document.headings
        ) > 1:
            errors.append(f"readme_duplicate_heading:{heading}")

    status = "Publicly visible — proprietary — All Rights Reserved"
    status_position = next(
        (
            index
            for index, line in enumerate(document.ordinary_text_lines)
            if line == status
        ),
        -1,
    )
    if (
        positions[0] < 0
        or positions[1] < 0
        or not positions[0] < status_position < positions[1]
    ):
        errors.append("readme_proprietary_status_order")

    command_positions = [
        index
        for index, line in enumerate(rendered_lines)
        if line.strip() == NORMAL_CONFIGURE_COMMAND
    ]
    if (
        len(command_positions) != 1
        or positions[3] < 0
        or positions[4] < 0
        or not positions[3] < command_positions[0] < positions[4]
    ):
        errors.append("readme_normal_configure_command")

    for anchor in PRESERVED_ANCHORS:
        visible_anchor = _presentation_text(anchor)
        anchor_count = _visible_anchor_count(
            presentation_normalized,
            visible_anchor,
        )
        if anchor_count == 0:
            errors.append(f"readme_missing_anchor:{anchor}")
        if anchor_count != PRESERVED_ANCHOR_EXACT_COUNTS[anchor]:
            errors.append(f"readme_anchor_count:{anchor}")
    forbidden_routes = (
        "docs/research/",
        "docs/history/",
        "docs/superpowers/",
        ".agents/",
        "sync_installed_skill",
        "--skill-install-root",
        "Lower-level inspected path:",
    )
    for route in forbidden_routes:
        if route in prose_text:
            errors.append(f"readme_forbidden_route:{route}")

    targets = [token.target or "" for token in document.links]
    if targets != list(EXPECTED_LINKS):
        errors.append("readme_link_sequence")
    for target in EXPECTED_LINKS:
        if targets.count(target) > 1:
            errors.append(f"readme_duplicate_link:{target}")
    links = set(targets)
    if links != set(EXPECTED_LINKS):
        errors.append("readme_link_set")
    for target in targets:
        if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith(
            "//"
        ):
            errors.append(f"readme_external_link:{target}")
            continue
        link_error = _validate_internal_link(root, target)
        if link_error is not None:
            errors.append(link_error)
    return errors


def test_readme_presents_the_product_contract_in_required_order() -> None:
    assert _readme_contract_errors(ROOT) == []


def test_readme_contract_rejects_swapped_sections(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    if all(heading in text for heading in REQUIRED_HEADINGS):
        text = text.replace(REQUIRED_HEADINGS[0], "## SECTION-SWAP", 1)
        text = text.replace(REQUIRED_HEADINGS[1], REQUIRED_HEADINGS[0], 1)
        text = text.replace("## SECTION-SWAP", REQUIRED_HEADINGS[1], 1)
    else:
        text += "\n\n" + "\n\n".join(reversed(REQUIRED_HEADINGS)) + "\n"
    readme.write_text(text, encoding="utf-8")

    assert "readme_section_order" in _readme_contract_errors(root)


def test_readme_contract_ignores_a_comment_hidden_required_heading(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            REQUIRED_HEADINGS[0],
            f"<!-- {REQUIRED_HEADINGS[0]} -->",
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_required_sections" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "replacement",
    (
        f"```text\n{REQUIRED_HEADINGS[0]}\n```",
        f"    {REQUIRED_HEADINGS[0]}",
        f"This paragraph only mentions {REQUIRED_HEADINGS[0]}.",
    ),
)
def test_readme_contract_requires_an_exact_visible_level_two_heading(
    tmp_path: Path,
    replacement: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            REQUIRED_HEADINGS[0],
            replacement,
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_required_sections" in _readme_contract_errors(root)


def test_readme_contract_rejects_an_unclosed_html_comment(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            REQUIRED_HEADINGS[0],
            f"<!--\n{REQUIRED_HEADINGS[0]}",
            1,
        ),
        encoding="utf-8",
    )

    errors = _readme_contract_errors(root)
    assert "readme_unclosed_html_comment" in errors
    assert "readme_required_sections" in errors


def test_readme_contract_rejects_an_unclosed_fence(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n```text\n",
        encoding="utf-8",
    )

    errors = _readme_contract_errors(root)
    assert "readme_unclosed_fence" in errors


def test_readme_contract_rejects_an_unclosed_exact_run_code_span(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n`one-tick opener``\n",
        encoding="utf-8",
    )

    assert "readme_unclosed_code_span" in _readme_contract_errors(root)


def test_readme_contract_rejects_a_duplicate_required_heading(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{REQUIRED_HEADINGS[0]}\n",
        encoding="utf-8",
    )

    assert f"readme_duplicate_heading:{REQUIRED_HEADINGS[0]}" in (
        _readme_contract_errors(root)
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "```text\nPublicly visible — proprietary — All Rights Reserved\n```",
        "    Publicly visible — proprietary — All Rights Reserved",
    ),
)
def test_readme_contract_requires_the_status_in_ordinary_prose(
    tmp_path: Path,
    replacement: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "Publicly visible — proprietary — All Rights Reserved",
            replacement,
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_proprietary_status_order" in _readme_contract_errors(root)


def test_readme_contract_does_not_count_inline_code_as_proprietary_status(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    status = "Publicly visible — proprietary — All Rights Reserved"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            status,
            f"`{status}`",
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_proprietary_status_order" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "replacement",
    (
        "### Publicly visible — proprietary — All Rights Reserved",
        "[Publicly visible — proprietary — All Rights Reserved](SECURITY.md)",
    ),
)
def test_readme_contract_requires_the_status_as_plain_paragraph_text(
    tmp_path: Path,
    replacement: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    status = "Publicly visible — proprietary — All Rights Reserved"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(status, replacement, 1),
        encoding="utf-8",
    )

    assert "readme_proprietary_status_order" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "replacement",
    (
        "```text\nRuntime writes happen only through `hsconfig apply` or "
        "`hsconfig configure --apply`.\n```",
        "    Runtime writes happen only through `hsconfig apply` or "
        "`hsconfig configure --apply`.",
    ),
)
def test_readme_contract_requires_prose_anchors_outside_block_code(
    tmp_path: Path,
    replacement: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    anchor = PRESERVED_ANCHORS[5]
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(anchor, replacement, 1),
        encoding="utf-8",
    )

    assert f"readme_missing_anchor:{anchor}" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "payload",
    (
        "\n``literal with a `single` backtick``\n",
        "\n```text\n<!-- comment markers stay code -->\n```\n",
    ),
)
def test_readme_contract_rejects_noncanonical_cross_state_code_payloads(
    tmp_path: Path,
    payload: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + payload,
        encoding="utf-8",
    )

    assert _readme_contract_errors(root) == ["readme_canonical_integrity"]


def test_readme_contract_rejects_a_dangling_future_document_link(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n[Architecture](docs/contracts/architecture.md)\n",
        encoding="utf-8",
    )

    errors = _readme_contract_errors(root)
    assert "readme_link_set" in errors
    assert "readme_dangling_link:docs/contracts/architecture.md" in errors


def test_readme_contract_rejects_a_bare_external_url(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nVisit https://example.invalid/external for details.\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:bare_url" in _readme_contract_errors(root)


def test_readme_contract_rejects_a_bare_url_after_an_underscore(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nroute_https://example.invalid/external\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:bare_url" in _readme_contract_errors(root)


def test_readme_contract_rejects_a_bare_gfm_email_autolink(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\nContact security@example.invalid for details.\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:bare_email" in _readme_contract_errors(
        root
    )


@pytest.mark.parametrize(
    "email",
    (
        "a.b-c_d@a.b",
        "person@example.123",
        "person@under_score.example",
    ),
)
def test_readme_contract_rejects_broad_gfm_compact_emails(
    tmp_path: Path,
    email: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\nContact {email}.\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:bare_email" in _readme_contract_errors(
        root
    )


@pytest.mark.parametrize(
    "autolink",
    (
        "<ftp://example.invalid/file>",
        "<tel:+41000000000>",
        "<custom+route:value>",
    ),
)
def test_readme_contract_rejects_every_angle_uri_scheme(
    tmp_path: Path,
    autolink: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{autolink}\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:autolink" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "element",
    (
        '<img src="https://example.invalid/tracker.png">',
        '<form action="https://example.invalid/collect"></form>',
        '<iframe src="docs/contracts/architecture.md"></iframe>',
    ),
)
def test_readme_contract_rejects_every_raw_html_element(
    tmp_path: Path,
    element: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{element}\n",
        encoding="utf-8",
    )

    assert "readme_unsupported_link_syntax:html" in _readme_contract_errors(root)


def test_readme_contract_rejects_a_duplicate_allowed_link(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + "\n[Operator guide](docs/operator/README.md)\n",
        encoding="utf-8",
    )

    assert "readme_duplicate_link:docs/operator/README.md" in (
        _readme_contract_errors(root)
    )


@pytest.mark.parametrize(
    "replacement",
    (
        "![Operator guide](docs/operator/README.md)",
        r"\[Operator guide](docs/operator/README.md)",
    ),
)
def test_readme_contract_does_not_count_images_or_escaped_links(
    tmp_path: Path,
    replacement: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "[Operator guide](docs/operator/README.md)",
            replacement,
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_link_set" in _readme_contract_errors(root)


def test_readme_contract_does_not_count_a_multi_backtick_code_span_link(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    replacement = (
        "``[Operator guide](docs/operator/README.md) uses `route` syntax``"
    )
    readme.write_text(
        readme.read_text(encoding="utf-8").replace(
            "[Operator guide](docs/operator/README.md)",
            replacement,
            1,
        ),
        encoding="utf-8",
    )

    errors = _readme_contract_errors(root)
    assert "readme_link_set" in errors
    assert "readme_unclosed_code_span" not in errors


def test_readme_contract_rejects_reordered_allowed_links(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    source = readme.read_text(encoding="utf-8")
    original = """- [Security policy](SECURITY.md)
- [Contribution policy](CONTRIBUTING.md)"""
    reordered = """- [Contribution policy](CONTRIBUTING.md)
- [Security policy](SECURITY.md)"""
    readme.write_text(source.replace(original, reordered, 1), encoding="utf-8")

    assert "readme_link_sequence" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    ("label", "payload", "expected_error"),
    (
        (
            "autolink",
            "\n<https://example.invalid/external>\n",
            "readme_unsupported_link_syntax:autolink",
        ),
        (
            "reference",
            "\n[Architecture][architecture]\n\n"
            "[architecture]: docs/contracts/architecture.md\n",
            "readme_unsupported_link_syntax:reference",
        ),
        (
            "html",
            '\n<a href="docs/contracts/architecture.md">Architecture</a>\n',
            "readme_unsupported_link_syntax:html",
        ),
    ),
)
def test_readme_contract_fails_closed_on_unsupported_link_syntax(
    tmp_path: Path,
    label: str,
    payload: str,
    expected_error: str,
) -> None:
    root = _copy_readme_context(tmp_path / label)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + payload,
        encoding="utf-8",
    )

    assert expected_error in _readme_contract_errors(root)


def test_readme_round10_rejects_a_duplicate_normal_configure_command(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8")
        + f"\n## Appendix\n\n```powershell\n{NORMAL_CONFIGURE_COMMAND}\n```\n",
        encoding="utf-8",
    )

    assert "readme_normal_configure_command" in _readme_contract_errors(root)


def test_readme_round10_rejects_a_misplaced_normal_configure_command(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    source = readme.read_text(encoding="utf-8")
    source = source.replace(NORMAL_CONFIGURE_COMMAND, "# command moved", 1)
    source += f"\n## Appendix\n\n```powershell\n{NORMAL_CONFIGURE_COMMAND}\n```\n"
    readme.write_text(source, encoding="utf-8")

    assert "readme_normal_configure_command" in _readme_contract_errors(root)


@pytest.mark.parametrize("anchor", PRESERVED_ANCHORS)
def test_readme_round10_rejects_duplicate_visible_preserved_anchors(
    tmp_path: Path,
    anchor: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{anchor}\n",
        encoding="utf-8",
    )

    assert f"readme_anchor_count:{anchor}" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    "payload",
    (
        f"`{NORMAL_CONFIGURE_COMMAND}`",
        f"**`{NORMAL_CONFIGURE_COMMAND}`**",
    ),
)
def test_readme_round11_counts_visible_inline_configure_command_duplicates(
    tmp_path: Path,
    payload: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{payload}\n",
        encoding="utf-8",
    )

    assert "readme_normal_configure_command" in _readme_contract_errors(root)


@pytest.mark.parametrize(
    ("payload", "anchor"),
    (
        (
            "Preferred normal path: **`hsconfig configure`**.",
            PRESERVED_ANCHORS[0],
        ),
        (
            "Runtime writes happen only through **`hsconfig apply`** or "
            "**`hsconfig configure --apply`**.",
            PRESERVED_ANCHORS[1],
        ),
        ("**docs/operator/README.md**", PRESERVED_ANCHORS[2]),
    ),
)
def test_readme_round11_counts_visible_formatted_anchor_duplicates(
    tmp_path: Path,
    payload: str,
    anchor: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{payload}\n",
        encoding="utf-8",
    )

    assert f"readme_anchor_count:{anchor}" in _readme_contract_errors(root)


def test_readme_round12_presentation_uses_only_the_visible_link_label() -> None:
    document = scan_markdown(
        "[Operator guide](docs/operator/README.md)"
    )

    assert document.presentation_prose == "Operator guide"
    assert "docs/operator/README.md" not in document.presentation_prose


@pytest.mark.parametrize(
    ("payload", "anchor"),
    (
        ("docs/operator/README&#46;md", PRESERVED_ANCHORS[2]),
        (
            "Preferred normal path&#58; **`hsconfig configure`**.",
            PRESERVED_ANCHORS[0],
        ),
    ),
)
def test_readme_round12_counts_html_entity_anchor_duplicates(
    tmp_path: Path,
    payload: str,
    anchor: str,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + f"\n{payload}\n",
        encoding="utf-8",
    )

    assert f"readme_anchor_count:{anchor}" in _readme_contract_errors(root)


def test_readme_round13_binds_the_approved_readme_artifact(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    assert _readme_contract_errors(root) == ["readme_canonical_integrity"]


def test_markdown_round13_decodes_entities_only_in_visible_non_code_tokens() -> None:
    document = scan_markdown(
        "# Entity&#45;heading\n"
        "[Visible&#32;label](hidden&#45;destination) Plain&#45;text "
        "`inline&#45;code`\n"
        "```text\n"
        "block&#45;code\n"
        "```\n"
    )

    assert "Entity-heading" in document.presentation_prose
    assert "Visible label" in document.presentation_prose
    assert "Plain-text" in document.presentation_prose
    assert "hidden-destination" not in document.presentation_prose
    assert "inline&#45;code" in document.presentation_prose
    assert "block&#45;code" in "\n".join(document.presentation_rendered_lines)


def test_markdown_round13_preserves_inline_code_entities_literally() -> None:
    document = scan_markdown("`hsconfig source&#45;manifest`")

    assert document.presentation_prose == "hsconfig source&#45;manifest"


def test_readme_round13_rejects_an_entity_encoded_fenced_configure_command(
    tmp_path: Path,
) -> None:
    root = _copy_readme_context(tmp_path)
    readme = root / "README.md"
    text = readme.read_text(encoding="utf-8")
    readme.write_text(
        text.replace(
            NORMAL_CONFIGURE_COMMAND,
            NORMAL_CONFIGURE_COMMAND.replace("<DeckName>", "&lt;DeckName&gt;"),
            1,
        ),
        encoding="utf-8",
    )

    assert "readme_normal_configure_command" in _readme_contract_errors(root)


def test_markdown_round14_has_no_source_namespace_sentinel_collision() -> None:
    document = scan_markdown("&#57600;0&#57601;`inline&#45;code`")

    assert document.presentation_prose == "\ue1000\ue101inline&#45;code"


def test_markdown_round14_has_no_escape_marker_sentinel_collision() -> None:
    document = scan_markdown("&#57344;&#57345; \\*literal\\_")

    assert document.presentation_prose == "\ue000\ue001 *literal_"


def test_markdown_round14_setext_inline_code_fails_closed_and_stays_literal() -> None:
    document = scan_markdown("`hsconfig source&#45;manifest`\n---\n")

    assert "setext_non_text_child" in {error.reason for error in document.errors}
    assert any(token.kind == "inline_code" for token in document.tokens)
    assert document.presentation_prose_lines[0] == "hsconfig source&#45;manifest"


def test_readme_round14_returns_diagnostics_for_invalid_utf8(tmp_path: Path) -> None:
    root = _copy_readme_context(tmp_path)
    (root / "README.md").write_bytes(b"\xff\xfe\xfa")

    assert _readme_contract_errors(root) == [
        "readme_invalid_utf8",
        "readme_canonical_integrity",
    ]
