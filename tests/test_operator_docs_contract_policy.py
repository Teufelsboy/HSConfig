from __future__ import annotations

from pathlib import Path

from hsconfig.external_skill_bundle import load_embedded_skill_bundle
from tests.helpers.markdown_contract import scan_markdown


ROOT = Path(__file__).resolve().parents[1]
OPERATOR = ROOT / "docs/operator/README.md"
GUIDE = ROOT / "docs/operator/guide-research-policy.md"
SPINE = ROOT / "docs/operator/source-contract-spine.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compact(text: str) -> str:
    return " ".join(text.split())


def _section(text: str, heading: str) -> str:
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _markdown_table(text: str, heading: str) -> dict[str, dict[str, str]]:
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    table_lines = [line for line in section.splitlines() if line.startswith("|")]
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows: dict[str, dict[str, str]] = {}
    for line in table_lines[2:]:
        cells = [cell.strip().replace("`", "") for cell in line.strip("|").split("|")]
        row = dict(zip(headers, cells, strict=True))
        rows[cells[0]] = row
    return rows


def test_guide_names_source_truth_and_runtime_authority_boundary() -> None:
    text = _text(GUIDE)

    assert "Source Truth Is Not Runtime Authority" in text
    assert "`claim_kind` is the runtime-routing authority" in text
    assert "`operator_summary.json` remains the only normal apply authority" in text
    assert "Darkbishop Benedictus" in text
    assert "does not become a mulligan keep" in text
    assert "`globalvalue_numeric_tuning`" in text
    assert "requires runtime evidence" in text


def test_guide_keeps_source_warnings_non_blocking() -> None:
    text = _text(GUIDE)

    assert "Warnings are follow-up work, not a runtime apply blocker." in text
    assert "Do not use `source_contract_audit.json` as an apply gate." in text
    assert "`SOURCE_BACKED_STRONG` is an evidence-quality label, not a generation/apply gate." in text


def test_guide_states_the_canonical_claim_lifecycle_without_a_second_gate() -> None:
    normalized = _compact(_text(GUIDE)).lower()

    assert "canonical claim lifecycle" in normalized
    assert "conflict quarantine" in normalized
    assert "quarantined claims suppress unsafe runtime rows" in normalized
    assert "do not block load-safe valid packages" in normalized
    assert "operator_summary.json remains the only normal apply authority" in normalized
    assert "source_contract_audit.json is diagnostic" in normalized


def test_operator_docs_keep_one_apply_authority_and_supported_surfaces() -> None:
    combined = f"{_text(OPERATOR)}\n{_text(GUIDE)}\n{_text(SPINE)}"

    assert "reports/operator_summary.json remains the only normal apply authority" in combined
    assert "source_contract_audit.json is diagnostic" in combined
    assert "Presume.json" in combined
    assert "Concede.json" in combined
    assert "aggregate `CardBehavior.json`" in combined
    assert "source-contract-spine -> apply" not in combined


def test_source_contract_spine_covers_every_supported_claim_kind() -> None:
    text = _text(SPINE)
    required_claim_kinds = {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
        "discover_choice",
        "choose_one_choice",
        "globalvalue_numeric_tuning",
    }

    assert "Diagnostic reference only" in text
    assert "`reports/operator_summary.json` remains the only normal apply authority." in text
    assert "not an apply authority" in text
    for claim_kind in required_claim_kinds:
        assert f"`{claim_kind}`" in text


def test_operator_guide_links_active_contract_docs_without_path_drift() -> None:
    document = scan_markdown(_text(OPERATOR))
    targets = [link.target for link in document.links]
    first_120_lines = "\n".join(_text(OPERATOR).splitlines()[:120])

    assert targets[:5] == [
        "../architecture/overview.md",
        "../contracts/pre-run-contract.md",
        "../contracts/evidence-and-disposition.md",
        "../contracts/release-gate.md",
        "output-retention-policy.md",
    ]
    assert "hsconfig configure" in first_120_lines
    assert "source-contract-spine" not in first_120_lines


def test_source_autopilot_is_source_preflight_not_apply_authority() -> None:
    combined = f"{_text(OPERATOR)}\n{_text(GUIDE)}"

    assert "--auto-source" in combined
    assert "source-autopilot" in combined
    assert "02_source_autopilot" in combined
    assert "static records without explicit supported effect semantics do not promote `SOURCE_BACKED_STRONG`" in combined
    assert "`source-autopilot` is source-strength preflight, not runtime apply authority." in combined
    assert "operator_summary.json remains the only normal apply authority" in combined


def test_docs_keep_per_card_closure_and_default_only_debt_visible() -> None:
    combined = f"{_text(OPERATOR)}\n{_text(GUIDE)}"

    assert "per-card closure" in combined
    assert "default_only_runtime_surface_details" in combined
    assert "no-silent-default-only" in combined.lower()
    assert "visible quality" in combined.lower()
    assert "not an apply blocker" in combined.lower()
    assert "source_to_runtime_explainability.json" in combined
    assert "source_evidence_closure.json" in combined


def test_operator_docs_state_runtime_commit_recovery_without_false_rollback() -> None:
    text = _text(OPERATOR)

    assert "Before the INI\ncommit point" in text
    assert "leaves the previous complete config selected" in text
    assert "the new verified config remains selected" in text
    assert "recovery\ncompletes advisory state or receipt work" in text
    assert "the apply is rolled back" not in text


def test_exact_guide_mulligan_gate_is_machine_readable_and_fail_closed() -> None:
    gate = _markdown_table(_text(GUIDE), "### Exact Public-Guide Mulligan Gate")

    assert set(gate) == {
        "public_guide_identity",
        "deck_match_scope",
        "target_deck_fingerprint",
        "exact_deck_evidence",
        "source_receipt",
        "promotion_eligible",
        "source_visibility",
        "source_lane",
    }
    assert {row["Failure outcome"] for row in gate.values()} == {
        "suppress with visible reason"
    }
    assert gate["deck_match_scope"]["Required value"] == "exact_deck_matched"
    assert gate["promotion_eligible"]["Required value"] == "true"
    assert gate["source_lane"]["Required value"] == "deck_matched_public_guide"


def test_operator_contract_models_physical_rows_and_assurance_dimensions() -> None:
    spine = _text(SPINE)
    rows = _markdown_table(spine, "## Physical Runtime Row Contract")
    assurance = _markdown_table(spine, "## Configuration Assurance")

    assert rows["runtime_key"]["Shape"] == "(card_id, behavior_block, condition)"
    assert rows["full_signature"]["Shape"] == "(card_id, behavior_block, condition, value)"
    assert rows["conflicting_values"]["Result"] == "fail closed; suppress physical row"
    assert rows["physical_report_parity"]["Result"] == "exact row parity required"
    assert assurance["in_client_behavior"]["Contract value"] == "not_proven_by_pre_run_contract"
    assert assurance["optimality_claim_allowed"]["Contract value"] == "false"
    assert assurance["runtime_gate_impact"]["Contract value"] == "none"


def test_operator_contract_names_globalvalues_plan_trust_boundaries() -> None:
    rows = _markdown_table(_text(SPINE), "## GlobalValues Plan Trust Boundary")

    assert rows["legacy_claim_inference"]["Required outcome"] == "untyped posture text cannot mint a source receipt"
    assert rows["identity_signal_layers"]["Required outcome"] == "any explicit non-guide signal vetoes public-guide authority"
    assert rows["bundle_receipt_truth"]["Required outcome"] == "plan bundle and plan receipts cannot replace package truth"
    assert rows["canonical_runtime_plans"]["Required outcome"] == "sole runtime truth; imported same-ID rows cannot replace or restore"
    assert rows["exact_evidence_authority"]["Required outcome"] == "otherwise no receipt and a visible exact-source gap"


def test_operator_docs_define_strategic_acquisition_authority() -> None:
    rows = _markdown_table(_text(GUIDE), "## Strategic Acquisition Authority")

    assert {
        mode: (row["Authority"], row["Strategic receipt"])
        for mode, row in rows.items()
    } == {
        "live_http": ("live_verified", "eligible after all exact guide gates"),
        "captured_record": ("captured_unverified", "no; diagnostic-only"),
        "manual_evidence": ("manual_unverified", "no; diagnostic-only"),
        "fixture_map": ("fixture_only", "no; diagnostic-only"),
        "legacy_claims_json": ("legacy_unverified", "no; diagnostic-only"),
    }


def test_operator_docs_define_claim_kind_strong_and_combo_boundaries() -> None:
    spine = _text(SPINE)
    rows = _markdown_table(spine, "## Claim-Kind Strong Authority")

    assert rows["strategic_claims"]["Strong authority"] == "deck_matched_public_guide plus verified strategic receipt"
    assert rows["deterministic_static_claims"]["Strong authority"] == "deck_matched_public_guide or source_backed_static_semantics"
    assert "Static semantics can support deterministic CardID and effect claims, but they can never authorize strategic Combo order." in spine


def test_operator_docs_define_linked_runtime_owner_and_verification_limits() -> None:
    operator = _text(OPERATOR)

    for line in (
        "Source card: `SW_448` (Darkbishop Benedictus)",
        "Link: `hero_power_transform`",
        "Runtime owner: `EX1_625t` (Mind Spike)",
        "Physical row: `CardID/EX1_625t.json`",
    ):
        assert line in operator
    assert "The numeric bonus is a configuration policy value, not proof of optimal play." in _compact(operator)
    assert "Offline tests prove neither in-client behavior nor gameplay optimality." in operator


def test_operator_docs_define_simplified_fail_closed_gate_phases_and_codes() -> None:
    section = _section(_text(OPERATOR), "## Runtime Apply Authority")

    for phase in (
        "Require a readable object at `reports/operator_summary.json`.",
        "Recompute deck-input verification and require runtime apply eligibility.",
        "Verify strategic source authority.",
        "Require the derivation receipt and summary derivation metadata.",
        "Verify the receipt schema and recompute its summary-bound digest.",
        "Recompute receipt content from authoritative inputs and runtime JSON.",
        "Verify exact summary derivation consistency and generated-file parity.",
        "Authorize the runtime write only for a recomputed valid package.",
    ):
        assert phase in section
    for reason_code in (
        "strict_package_validation_failed",
        "deck_input_not_verified",
        "source_authority_receipt_invalid",
        "package_derivation_receipt_missing",
        "package_derivation_receipt_schema_unsupported",
        "package_derivation_receipt_digest_mismatch",
        "package_derivation_mismatch",
        "operator_summary_derivation_inconsistent",
    ):
        assert f"`{reason_code}`" in section


def test_operator_combo_summaries_require_live_verified_strategic_receipt() -> None:
    operator = _text(OPERATOR)

    assert "per-card `<CARDID>.json`, and `Combo.json` when exact ordered combo evidence and a matching live-verified strategic receipt exist." in _compact(operator)
    assert "`Combo.json` is conditional on a complete source-backed combo with a matching live-verified strategic receipt." in _compact(operator)


def test_docs_define_optimized_start_as_pre_game_non_optimality_contract() -> None:
    readme = _text(ROOT / "README.md")
    operator = _text(OPERATOR)
    skill = load_embedded_skill_bundle()["SKILL.md"].decode("utf-8")
    combined = f"{readme}\n{operator}\n{skill}"
    compact = _compact(combined)

    for marker in (
        "exactly three fixed candidates",
        "`candidate-1.json` (`proactive_tempo`)",
        "`candidate-2.json` (`balanced`)",
        "`candidate-3.json` (`resource_oriented`)",
        "independent clean-context critic",
        "at most two targeted repair rounds",
        "`LLM_OPTIMIZED_START`",
        "`configure_summary.json.optimized_start`",
        "`optimized_start_summary_invalid`",
        "`optimized_start_derivation_invalid`",
        "only when live writing was requested",
        "`runtime-match`",
        "best practical pre-game start config",
        "not measured gameplay optimality",
    ):
        assert marker in combined

    for document in (readme, operator, skill):
        assert "Conservative CLI Compatibility" in document
        assert "only normal generation route" in _compact(document)
    assert "source-contract-only apply blocker" in compact
    assert "visible informational limitations" in compact
    assert "live configure-result" in compact
    assert "re-derives" in compact
    assert "non-persisted" in compact
    assert "cannot roll back an already-published current pointer" in compact
    for contradiction in (
        "Preferred normal path: `hsconfig configure`.",
        "Run `hsconfig configure` for normal operation.",
        "Use `hsconfig configure` for normal operation:",
    ):
        assert contradiction not in combined
