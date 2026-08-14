from __future__ import annotations

from pathlib import Path

from tests.helpers.markdown_contract import scan_markdown


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "docs/operator/README.md"
ACTIVE_DOCS = (
    ROOT / "README.md",
    OPERATOR,
    ROOT / "docs/operator/guide-research-policy.md",
    ROOT / "docs/operator/output-retention-policy.md",
    ROOT / "docs/operator/source-contract-spine.md",
    ROOT / "docs/architecture/overview.md",
    ROOT / "docs/architecture/transaction-model.md",
    ROOT / "docs/contracts/pre-run-contract.md",
    ROOT / "docs/contracts/evidence-and-disposition.md",
    ROOT / "docs/contracts/release-gate.md",
    ROOT / "docs/contracts/v1.0.0-release-notes.md",
)
SECONDARY_DOCS = ACTIVE_DOCS[2:]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined(*paths: Path) -> str:
    return "\n".join(_text(path) for path in paths)


def _markdown_table(text: str, heading: str) -> dict[str, dict[str, str]]:
    lines = text.splitlines()
    start = lines.index(heading)
    header = [cell.strip() for cell in lines[start + 2].strip("|").split("|")]
    rows: dict[str, dict[str, str]] = {}
    for line in lines[start + 4 :]:
        if not line.startswith("|"):
            break
        cells = [
            cell.strip().replace("`", "")
            for cell in line.strip("|").split("|")
        ]
        rows[cells[0]] = dict(zip(header[1:], cells[1:], strict=True))
    return rows


def test_root_readme_routes_only_to_the_active_public_path() -> None:
    document = scan_markdown(_text(ROOT / "README.md"))

    assert [link.target for link in document.links] == [
        "docs/operator/README.md",
        "docs/architecture/overview.md",
        "docs/contracts/pre-run-contract.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
    ]


def test_active_docs_do_not_route_to_frozen_legacy_authority() -> None:
    text = _combined(*ACTIVE_DOCS)
    forbidden = (
        "docs/" + "research/",
        "docs/" + "history/",
        "docs/" + "superpowers/",
        ".ag" + "ents/",
        "sync_" + "installed_skill",
        "--skill-" + "install-root",
    )

    for marker in forbidden:
        assert marker not in text


def test_active_doc_links_are_renderable_and_resolve_to_regular_files() -> None:
    for path in ACTIVE_DOCS:
        document = scan_markdown(_text(path))
        assert document.errors == (), path
        for link in document.links:
            target = link.target or ""
            assert "://" not in target, (path, target)
            relative, _separator, anchor = target.partition("#")
            linked = (path.parent / relative).resolve()
            assert linked.is_file(), (path, target)
            assert linked.is_relative_to(ROOT), (path, target)
            if anchor:
                headings = {
                    token.raw.lower().replace(" ", "-")
                    for token in scan_markdown(_text(linked)).headings
                }
                assert anchor.lower() in headings, (path, target)


def test_active_secondary_docs_have_real_operator_backlinks() -> None:
    for path in SECONDARY_DOCS:
        targets = {
            (path.parent / (link.target or "")).resolve()
            for link in scan_markdown(_text(path)).links
        }
        assert OPERATOR.resolve() in targets, path


def test_operator_guide_owns_the_detailed_normal_command_path() -> None:
    operator = _text(OPERATOR)
    secondary = _combined(*SECONDARY_DOCS)

    assert "## Preferred Normal Path" in operator
    assert "Preferred normal path: `hsconfig configure`." in operator
    assert 'hsconfig configure --deck-name "<DeckName>"' in operator
    assert 'hsconfig configure --deck-name "<DeckName>"' not in secondary


def test_runtime_write_authority_stays_single_and_explicit() -> None:
    operator = _text(OPERATOR)
    contracts = _combined(
        ROOT / "docs/contracts/pre-run-contract.md",
        ROOT / "docs/architecture/overview.md",
        ROOT / "docs/architecture/transaction-model.md",
    )

    assert "reports/operator_summary.json remains the only normal apply authority." in operator
    assert "Apply only through `hsconfig apply` or `hsconfig configure --apply`." in operator
    assert "sole normal apply authority" in contracts
    assert "explicit apply path" in " ".join(contracts.split())


def test_source_strength_is_not_runtime_apply_permission() -> None:
    docs = _combined(
        OPERATOR,
        ROOT / "docs/operator/guide-research-policy.md",
        ROOT / "docs/operator/source-contract-spine.md",
    )

    assert "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation/apply gate." in docs
    assert "It is not a runtime apply permission" in docs
    assert "runtime_apply_mode" in docs


def test_diagnostics_remain_explanations_not_additional_gates() -> None:
    operator = _text(OPERATOR)

    assert "contract-spine-sentinel" in operator
    assert "diagnostic" in operator.lower()
    assert "contract-spine-sentinel -> apply" not in operator
    assert "source_contract_audit.json` is diagnostic." in operator
    assert "Do not add another runtime-write authority" in operator


def test_effect_semantics_do_not_become_mulligan_inference() -> None:
    docs = _combined(
        ROOT / "docs/operator/guide-research-policy.md",
        ROOT / "docs/operator/source-contract-spine.md",
        ROOT / "docs/contracts/pre-run-contract.md",
    )

    assert "cannot prove opening-hand keeps" in docs
    assert "mulligan_keep" in docs
    assert "mulligan_discard" in docs
    assert "cannot be inferred" in docs


def test_pre_run_contract_keeps_external_outcomes_out_of_scope() -> None:
    contract = _text(ROOT / "docs/contracts/pre-run-contract.md")
    release_notes = _text(ROOT / "docs/contracts/v1.0.0-release-notes.md")

    assert "OUT_OF_SCOPE_ASSUMED_EXTERNAL" in contract
    assert "OUT_OF_SCOPE_ASSUMED_EXTERNAL" in release_notes
    assert "do not prove in-client loading" in contract
    assert "does not claim" in release_notes


def test_operator_route_exposes_structured_semantic_closure_contract() -> None:
    operator_document = scan_markdown(_text(OPERATOR))
    routed_targets = {
        (OPERATOR.parent / (link.target or "")).resolve()
        for link in operator_document.links
    }

    spine_path = ROOT / "docs/operator/source-contract-spine.md"
    guide_path = ROOT / "docs/operator/guide-research-policy.md"
    assert spine_path.resolve() in routed_targets
    assert guide_path.resolve() in routed_targets

    rows = _markdown_table(
        _text(spine_path),
        "## Audited Semantic Closure Contract",
    )
    assert rows["source_identity"]["Authority"] == "decoded canonical deck fingerprint"
    assert rows["source_identity"]["Outcome"] == "exact_deck_matched"
    assert rows["mulligan_authority"]["Authority"] == "exact_deck_matched"
    assert rows["hero_power_transform"]["Outcome"] == "CardID only"
    assert rows["metadata_only_cardid"]["Outcome"] == "not runtime_emitted"
    assert rows["load_safety"]["Outcome"] == "in-client optimality remains unproven"
    assert rows["configuration_assurance"]["Outcome"] == "runtime_gate_impact=none"
