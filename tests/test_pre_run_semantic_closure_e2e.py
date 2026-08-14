from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from hsconfig import pre_run_metrics
from hsconfig.cli import main
from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.evidence_contract import (
    classify_evidence_authority,
    load_policy_profile,
)
from hsconfig.globalvalues_decisions import (
    GLOBALVALUES_BASELINE_DECISION_KEYS,
)
from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    DualClosureStatus,
    EvidenceLane,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    disposition_ledger_content_sha256,
    globalvalues_baseline_sha256,
    globalvalues_decision_ledger_content_sha256,
)
from hsconfig.package_model import DirectoryPackageView
from hsconfig.pre_run_metrics import (
    _validate_acquisition_report,
    aggregate_pre_run_closure,
    audited_semantic_inventory_acceptance,
    build_layered_evidence_contract_report,
    build_pre_run_authority_handoff,
    build_pre_run_closure_report,
    build_source_acquisition_closure_report,
    disposition_ledger_document,
    globalvalues_decision_report_document,
    pre_emission_expectations_from_audit,
    source_acquisition_input_binding,
    validate_pre_run_package_reports,
    verified_emission_input_from_physical_rows,
)
from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    build_acquisition_closure,
    policy_provenance_payload,
)
from hsconfig.strict_package_validation import validate_complete_package
from tests.helpers.current_apply_eligible_package import (
    write_current_apply_eligible_package,
)

SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class _MemoryPackageView:
    def __init__(self, documents: dict[str, object]):
        self.documents = documents

    def file_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.documents))

    def read_bytes(self, relative_path: str) -> bytes:
        return json.dumps(self.documents[relative_path]).encode("utf-8")

    def read_json(self, relative_path: str):
        return deepcopy(self.documents[relative_path])

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.documents


def _rehash(report: dict) -> None:
    payload = dict(report)
    payload.pop("content_sha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    report["content_sha256"] = (
        f"sha256:{sha256(canonical).hexdigest()}"
    )


def _audited_view(row: dict) -> _MemoryPackageView:
    fingerprint = row["deck_fingerprint"]
    card_rows = []
    for card in row["main_cards"]:
        card_rows.append(
            CardDispositionRow(
                deck_fingerprint=fingerprint,
                composite_card_key=card["composite_card_key"],
                zone="main_deck",
                official_semantics_canonical_json=json.dumps(
                    {"GameCardId": card["card_id"]},
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
                authority_lane=EvidenceLane.BOT_DELEGATION,
                evidence_ids=("policy:bot-native-pre-run",),
                claim_ids=(),
                physical_owner=card["card_id"],
                disposition=CardDisposition.BOT_DELEGATED,
                runtime_paths=(),
                reason_code="bot_native_pre_run",
            )
        )
    for card in row["sideboard_modules"]:
        card_rows.append(
            CardDispositionRow(
                deck_fingerprint=fingerprint,
                composite_card_key=card["composite_card_key"],
                zone="sideboard_module",
                official_semantics_canonical_json=json.dumps(
                    {"GameCardId": card["card_id"]},
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8"),
                authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
                evidence_ids=("official:sideboard-module",),
                claim_ids=(),
                physical_owner=card["card_id"],
                disposition=CardDisposition.ANALYSIS_ONLY_SIDEBOARD,
                runtime_paths=(),
                reason_code="sideboard_analysis_only",
            )
        )
    cards = tuple(
        sorted(card_rows, key=lambda item: item.composite_card_key)
    )
    claims = tuple(
        ClaimDispositionRow(
            deck_fingerprint=fingerprint,
            claim_id=claim["claim_id"],
            claim_kind="audited_semantic_claim",
            evidence_id=f"inventory:{claim['claim_id']}",
            disposition=ClaimDisposition.CONTRACT_ONLY,
            runtime_paths=(),
            reason_code="claim_kind_has_no_runtime_surface",
        )
        for claim in sorted(
            row["claims"],
            key=lambda item: item["claim_id"],
        )
    )
    disposition = DispositionLedger(
        deck_fingerprint=fingerprint,
        cards=cards,
        claims=claims,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=fingerprint,
            cards=cards,
            claims=claims,
        ),
    )
    decisions = tuple(
        GlobalValueDecision(
            deck_fingerprint=fingerprint,
            key=key,
            kind=GlobalValueDecisionKind.COPY_BASELINE,
            baseline_canonical_json=b"0",
            emitted_canonical_json=b"0",
            authority_id="baseline:canonical",
            claim_ids=(),
            reason="copied canonical baseline",
        )
        for key in GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    globalvalues = GlobalValuesDecisionLedger(
        deck_fingerprint=fingerprint,
        baseline_sha256=globalvalues_baseline_sha256(decisions),
        decisions=decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            decisions
        ),
    )
    policy = load_policy_profile()
    policy_provenance = policy_provenance_payload(policy)
    policy_mapping = {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "effective_date": policy.effective_date,
        "content_sha256": policy.content_sha256,
        "rules": json.loads(policy.rules_canonical_json),
    }
    guide_claims = []
    classified_authorities = {}
    source_claim_rows = {}
    source_lifecycle_rows = []
    for claim in row["claims"]:
        claim_id = claim["claim_id"]
        guide_claim = {
            "claim_id": claim_id,
            "claim_kind": "audited_semantic_claim",
            "source_family": "versioned_internal_policy",
            "source_identity": f"audited-inventory:{claim_id}",
            "as_of_date": policy.effective_date,
            "policy_id": policy.policy_id,
            "policy_version": policy.version,
            "policy_content_sha256": policy.content_sha256,
            "policy_rule_id": "explicit_policy_claim",
            "cards": ["semantic_contract"],
            "action": "accept_explicit_policy_claim",
            "reason_code": "audited_inventory_contract",
        }
        authority = classify_evidence_authority(
            claim=guide_claim,
            deck_identity={
                "deck_fingerprint": fingerprint,
            },
            verified_source_receipts=(),
            policy_profile=policy_mapping,
        )
        projection = {
            "lane": authority.lane.value,
            "authority_id": authority.authority_id,
            "source_identity": authority.source_identity,
            "as_of_date": authority.as_of_date,
            "claim_kind": authority.claim_kind,
            "content_sha256": authority.content_sha256,
            "exact_deck_fingerprint": (
                authority.exact_deck_fingerprint
            ),
            "runtime_authorized": authority.runtime_authorized,
            "reason": authority.reason,
        }
        guide_claims.append(guide_claim)
        classified_authorities[claim_id] = authority
        source_claim_rows[claim_id] = {
            "claim_id": claim_id,
            "claim_kind": "audited_semantic_claim",
            "cards": [],
            "evidence_authority": projection,
        }
        source_lifecycle_rows.append(
            {
                "claim_id": claim_id,
                "builder_or_router_decision": "suppressed",
                "emitted_files": [],
            }
        )
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities=classified_authorities,
    )
    authority_handoff = build_pre_run_authority_handoff(
        disposition_ledger=disposition,
        classified_authorities=classified_authorities,
    )
    attempt_id = f"acquisition:{fingerprint}"
    attempted_url = (
        f"https://example.test/audited/{row['deck_name']}"
    )
    acquisition_closure = build_acquisition_closure(
        deck_identity={
            "deck_name": row["deck_name"],
            "deck_fingerprint": fingerprint,
        },
        research_manifest={
            "deck_name": row["deck_name"],
            "deck_fingerprint": fingerprint,
            "research_date": "2026-07-29",
            "attempt_id": attempt_id,
            "attempted_queries": [
                f"{row['deck_name']} audited semantic source"
            ],
            "checked_dossier": True,
            "policy_id": policy.policy_id,
            "policy_sha256": policy.content_sha256,
            "policy": policy_provenance,
        },
        acquisition_report={
            "deck_name": row["deck_name"],
            "deck_fingerprint": fingerprint,
            "attempt_id": attempt_id,
            "attempted_at": "2026-07-29",
            "attempted_urls": [attempted_url],
            "attempts": [
                {
                    "source_identity": attempted_url,
                    "outcome": "not_found",
                    "reason_code": "audited_negative_search",
                }
            ],
            "checked_dossier": True,
            "policy_id": policy.policy_id,
            "policy_sha256": policy.content_sha256,
            "policy": policy_provenance,
        },
        source_records=(),
        policy_profile=policy,
    )
    acquisition = build_source_acquisition_closure_report(
        deck_fingerprint=fingerprint,
        acquisition_closure=acquisition_closure,
    )
    verified = verified_emission_input_from_physical_rows(
        disposition_ledger=disposition,
        physical_rows=(),
    )
    pre_run = build_pre_run_closure_report(
        disposition_ledger=disposition,
        globalvalues_ledger=globalvalues,
        dual_closure=DualClosureStatus(
            pre_run_contract_status="complete",
            strategy_authority_status="partial",
            exact_guide_authority=False,
            unresolved_reasons=(),
        ),
        layered_evidence_report=layered,
        source_acquisition_report=acquisition,
        verified_emissions=verified,
    )
    sideboards = [
        {
            "sideboard_index": index,
            "owner_card_id": card["owner_card_id"],
            "owner_dbf_id": card["owner_dbf_id"],
            "cards": [
                {
                    "card_id": card["card_id"],
                    "count": card["count"],
                }
            ],
        }
        for index, card in enumerate(
            row["sideboard_modules"],
            start=1,
        )
    ]
    return _MemoryPackageView(
        {
            "reports/deck_identity.json": {
                "deck_name": row["deck_name"],
                "deck_fingerprint": fingerprint,
                "cards": [
                    {
                        "card_id": card["card_id"],
                        "count": card["count"],
                    }
                    for card in row["main_cards"]
                ],
                "main_deck": [
                    {
                        "card_id": card["card_id"],
                        "count": card["count"],
                    }
                    for card in row["main_cards"]
                ],
                "sideboards": sideboards,
            },
            "reports/layered_evidence_contract.json": layered,
            "reports/source_acquisition_closure.json": acquisition,
            "reports/disposition_ledger.json": (
                disposition_ledger_document(disposition)
            ),
            "reports/globalvalues_decision_ledger.json": (
                globalvalues_decision_report_document(globalvalues)
            ),
            "reports/pre_run_closure.json": pre_run,
            "reports/input_manifest.json": {
                "pre_run_contract_schema_version": 1,
                "source_acquisition_input_binding": (
                    source_acquisition_input_binding(acquisition)
                ),
                "pre_run_authority_handoff": authority_handoff,
            },
            "reports/guide_claim_bundle.json": {
                "claims": guide_claims,
                "canonical_source_receipts": [],
            },
            "reports/source_contract_audit.json": {
                "claim_rows": source_claim_rows,
                "claim_lifecycle_rows": source_lifecycle_rows,
            },
        }
    )


@pytest.fixture
def audited_packages() -> tuple[_MemoryPackageView, ...]:
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    return tuple(_audited_view(row) for row in inventory["decks"])


def _disposition_with_rows(
    original: DispositionLedger,
    *,
    cards: tuple[CardDispositionRow, ...] | None = None,
    claims: tuple[ClaimDispositionRow, ...] | None = None,
) -> DispositionLedger:
    card_rows = original.cards if cards is None else cards
    claim_rows = original.claims if claims is None else claims
    return DispositionLedger(
        deck_fingerprint=original.deck_fingerprint,
        cards=card_rows,
        claims=claim_rows,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=original.deck_fingerprint,
            cards=card_rows,
            claims=claim_rows,
        ),
    )


def _globalvalues_with_decisions(
    original: GlobalValuesDecisionLedger,
    decisions: tuple[GlobalValueDecision, ...],
) -> GlobalValuesDecisionLedger:
    return GlobalValuesDecisionLedger(
        deck_fingerprint=original.deck_fingerprint,
        baseline_sha256=globalvalues_baseline_sha256(decisions),
        decisions=decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            decisions
        ),
    )


def _rebuilt_audited_view(
    original: _MemoryPackageView,
    *,
    disposition: DispositionLedger | None = None,
    globalvalues: GlobalValuesDecisionLedger | None = None,
    acquisition: dict | None = None,
    physical_rows: tuple[dict, ...] = (),
) -> _MemoryPackageView:
    validated = validate_pre_run_package_reports(original)
    disposition = disposition or validated.disposition_ledger
    globalvalues = globalvalues or validated.globalvalues_ledger
    documents = deepcopy(original.documents)
    source_audit = documents[
        "reports/source_contract_audit.json"
    ]
    disposition_claim_ids = {
        row.claim_id for row in disposition.claims
    }
    source_audit["claim_rows"] = {
        claim_id: row
        for claim_id, row in source_audit["claim_rows"].items()
        if claim_id in disposition_claim_ids
    }
    source_audit["claim_lifecycle_rows"] = [
        row
        for row in source_audit["claim_lifecycle_rows"]
        if row.get("claim_id") in disposition_claim_ids
    ]
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities={
            claim_id: row["evidence_authority"]
            for claim_id, row in source_audit["claim_rows"].items()
            if any(
                claim.claim_id == claim_id
                for claim in disposition.claims
            )
        },
    )
    authority_handoff = build_pre_run_authority_handoff(
        disposition_ledger=disposition,
        classified_authorities={
            claim_id: row["evidence_authority"]
            for claim_id, row in source_audit["claim_rows"].items()
            if any(
                claim.claim_id == claim_id
                for claim in disposition.claims
            )
        },
    )
    acquisition = acquisition or deepcopy(
        documents["reports/source_acquisition_closure.json"]
    )
    semantic_expectations = pre_emission_expectations_from_audit(
        disposition_ledger=disposition,
        source_contract_audit=source_audit,
    )
    verified = verified_emission_input_from_physical_rows(
        disposition_ledger=disposition,
        physical_rows=physical_rows,
        semantic_expectations=semantic_expectations,
    )
    pre_run = build_pre_run_closure_report(
        disposition_ledger=disposition,
        globalvalues_ledger=globalvalues,
        dual_closure=DualClosureStatus(
            pre_run_contract_status="complete",
            strategy_authority_status="partial",
            exact_guide_authority=False,
            unresolved_reasons=(),
        ),
        layered_evidence_report=layered,
        source_acquisition_report=acquisition,
        verified_emissions=verified,
    )
    documents.update(
        {
            "reports/layered_evidence_contract.json": layered,
            "reports/source_acquisition_closure.json": acquisition,
            "reports/disposition_ledger.json": (
                disposition_ledger_document(disposition)
            ),
            "reports/globalvalues_decision_ledger.json": (
                globalvalues_decision_report_document(globalvalues)
            ),
            "reports/pre_run_closure.json": pre_run,
            "reports/input_manifest.json": {
                **documents["reports/input_manifest.json"],
                "pre_run_contract_schema_version": 1,
                "source_acquisition_input_binding": (
                    source_acquisition_input_binding(acquisition)
                ),
                "pre_run_authority_handoff": authority_handoff,
            },
        }
    )
    if physical_rows:
        runtime_cards: dict[str, dict[str, list[str]]] = {}
        for row in physical_rows:
            owner = str(row["physical_owner"])
            surface = str(row["relative_path"])
            runtime_cards.setdefault(
                owner,
                {"runtime_surfaces": []},
            )["runtime_surfaces"].append(surface)
            documents[f"CustomConfig/deck/{surface}"] = {
                "GameCardId": owner,
                "ConfigComment": "audited physical fixture",
                "BeforePlayCardBonus": {
                    "values": [
                        {
                            "condition": "*",
                            "value": "1",
                        }
                    ]
                },
            }
        documents["reports/runtime_surface_ledger.json"] = {
            "schema_version": 2,
            "cards": runtime_cards,
            "linked_runtime_entities": {},
            "physical_errors": [],
            "unexpected_runtime_emissions": [],
            "linked_runtime_owner_collisions": [],
        }
    return _MemoryPackageView(documents)


def test_standalone_prepare_acquisition_is_explicitly_open_not_synthetic_closed():
    report = build_source_acquisition_closure_report(
        deck_fingerprint="a" * 64,
        acquisition_closure=None,
    )

    assert report["deck_fingerprint"] == "a" * 64
    assert report["acquisition_closure"]["status"] == "open"
    assert report["acquisition_closure"]["successful_evidence_ids"] == []
    assert report["source_acquisition_complete"] is False
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False


def test_acquisition_validator_recomputes_the_nested_typed_closure_hash():
    fingerprint = "a" * 64
    report = build_source_acquisition_closure_report(
        deck_fingerprint=fingerprint,
        acquisition_closure=AcquisitionClosure(
            deck_fingerprint=fingerprint,
            attempt_id="acquisition:attempt",
            attempted_at="2026-07-29",
            attempted_urls=("https://example.test/source",),
            successful_evidence_ids=(),
            failed_attempts=(),
            negative_search_documented=True,
            checked_dossier=True,
            policy_id="BOT_NATIVE_PRE_RUN",
            status="closed_negative_search",
            content_sha256="sha256:" + ("f" * 64),
        ),
    )

    with pytest.raises(
        ValueError,
        match="source_acquisition_closure_content_hash_mismatch",
    ):
        _validate_acquisition_report(
            report,
            deck_fingerprint=fingerprint,
        )


def test_complete_pre_run_rejects_forged_acquisition_without_input_manifest():
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    package = _audited_view(inventory["decks"][0])
    package.documents.pop("reports/input_manifest.json")

    assert (
        package.documents["reports/pre_run_closure.json"][
            "pre_run_contract_status"
        ]
        == "complete"
    )
    with pytest.raises(
        ValueError,
        match="pre_run_input_manifest_missing",
    ):
        validate_pre_run_package_reports(package)


@pytest.mark.parametrize(
    "schema_version",
    [None, 0, "1", True],
    ids=("missing", "downgraded", "string", "boolean"),
)
def test_current_pre_run_requires_exact_manifest_schema_version(
    schema_version: object,
) -> None:
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    package = _audited_view(inventory["decks"][0])
    manifest = package.documents["reports/input_manifest.json"]
    assert isinstance(manifest, dict)
    if schema_version is None:
        manifest.pop("pre_run_contract_schema_version")
    else:
        manifest["pre_run_contract_schema_version"] = schema_version

    with pytest.raises(
        ValueError,
        match="pre_run_contract_schema_version_invalid",
    ):
        validate_pre_run_package_reports(package)


@pytest.mark.parametrize(
    "binding",
    [None, {}, {"acquisition_closure": {}}],
    ids=("missing", "empty", "partial"),
)
def test_current_pre_run_requires_exact_acquisition_manifest_binding(
    binding: object,
) -> None:
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    package = _audited_view(inventory["decks"][0])
    manifest = package.documents["reports/input_manifest.json"]
    assert isinstance(manifest, dict)
    if binding is None:
        manifest.pop("source_acquisition_input_binding")
    else:
        manifest["source_acquisition_input_binding"] = binding

    with pytest.raises(
        ValueError,
        match="source_acquisition_upstream_manifest_mismatch",
    ):
        validate_pre_run_package_reports(package)


def test_pre_run_authority_handoff_hash_is_validated() -> None:
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    package = _audited_view(inventory["decks"][0])
    manifest = package.documents["reports/input_manifest.json"]
    assert isinstance(manifest, dict)
    handoff = manifest["pre_run_authority_handoff"]
    assert isinstance(handoff, dict)
    handoff["authorities"][0]["reason"] = "coordinated-but-stale"

    with pytest.raises(
        ValueError,
        match="pre_run_authority_handoff_hash_stale",
    ):
        validate_pre_run_package_reports(package)


def test_coordinated_raw_authority_reports_cannot_self_sign_without_typed_handoff():
    inventory = _read_json(
        Path("tests/fixtures/near100/current_semantic_inventory.json")
    )
    package = _audited_view(inventory["decks"][0])
    acquisition = package.documents[
        "reports/source_acquisition_closure.json"
    ]
    package.documents["reports/input_manifest.json"] = {
        "pre_run_contract_schema_version": 1,
        "source_acquisition_input_binding": (
            source_acquisition_input_binding(acquisition)
        ),
    }

    with pytest.raises(
        ValueError,
        match="pre_run_authority_handoff_missing",
    ):
        validate_pre_run_package_reports(package)


def test_pre_run_rejects_schema_invalid_runtime_row_even_with_current_ledger(
    tmp_path: Path,
) -> None:
    package = write_current_apply_eligible_package(
        tmp_path / "package",
        runtime_files={
            "DS1_233.json": {
                "GameCardId": "DS1_233",
                "ConfigComment": "coordinated but schema-invalid",
                "BeforePlayCardBonus": {
                    "values": [{"unsupported": "self-signed"}]
                },
            }
        },
    )
    strict = validate_complete_package(package)

    assert strict["status"] == "failed"
    assert any(
        "missing condition" in error
        or "missing value" in error
        or "unsupported keys" in error
        for error in strict["errors"]
    )
    with pytest.raises(
        ValueError,
        match="verified_emission_runtime_schema_invalid",
    ):
        validate_pre_run_package_reports(
            DirectoryPackageView(package)
        )


def test_standalone_package_emits_owned_acquisition_and_globalvalues_reports(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    out = tmp_path / "package"

    assert (
        main(
            [
                "prepare",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )

    reports = out / "reports"
    deck = _read_json(reports / "deck_identity.json")
    acquisition = _read_json(
        reports / "source_acquisition_closure.json"
    )
    decisions = _read_json(
        reports / "globalvalues_decision_ledger.json"
    )
    dispositions = _read_json(reports / "disposition_ledger.json")
    layered = _read_json(
        reports / "layered_evidence_contract.json"
    )
    pre_run = _read_json(reports / "pre_run_closure.json")
    ownership = _read_json(
        reports / "output_ownership_manifest.json"
    )
    owned = {row["file"]: row for row in ownership["files"]}
    for name in (
        "reports/layered_evidence_contract.json",
        "reports/source_acquisition_closure.json",
        "reports/disposition_ledger.json",
        "reports/globalvalues_decision_ledger.json",
        "reports/pre_run_closure.json",
    ):
        assert owned[name]["classification"] == "diagnostic"
        assert owned[name]["can_block_apply"] is False

    assert acquisition["deck_fingerprint"] == deck["deck_fingerprint"]
    assert acquisition["acquisition_closure"]["status"] == "open"
    assert acquisition["source_acquisition_complete"] is False
    assert decisions["deck_fingerprint"] == deck["deck_fingerprint"]
    assert len(decisions["decisions"]) == len(
        GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    assert dispositions["deck_fingerprint"] == deck["deck_fingerprint"]
    assert dispositions["content_sha256"].startswith("sha256:")
    assert len(dispositions["cards"]) == 16
    assert len(dispositions["claims"]) == 22
    assert layered["deck_fingerprint"] == deck["deck_fingerprint"]
    assert len(layered["authorities"]) <= len(dispositions["claims"])
    assert layered["layered_coverage"]["numerator"] == len(
        layered["authorities"]
    )
    assert layered["layered_coverage"]["denominator"] == len(
        dispositions["claims"]
    )
    assert pre_run["deck_fingerprint"] == deck["deck_fingerprint"]
    assert pre_run["pre_run_contract_status"] == "incomplete"
    assert "source_acquisition_open" in pre_run["unresolved_reasons"]
    assert pre_run["counts"] == {
        "card_disposition_count": len(dispositions["cards"]),
        "final_card_disposition_count": len(dispositions["cards"]),
        "claim_count": len(dispositions["claims"]),
        "final_claim_disposition_count": len(dispositions["claims"]),
        "globalvalues_decision_count": len(decisions["decisions"]),
        "final_globalvalues_decision_count": len(decisions["decisions"]),
    }
    for field in ("emission_precision", "eligible_emission_recall"):
        assert set(pre_run[field]) == {
            "numerator",
            "denominator",
            "fraction",
            "value",
            "vacuous",
        }
        assert pre_run[field]["numerator"] <= pre_run[field]["denominator"]
    assert "audited_deck_total" not in pre_run
    assert "exact_guide_authority_count" not in pre_run
    validated = validate_pre_run_package_reports(
        DirectoryPackageView(out)
    )
    assert validated.deck_fingerprint == deck["deck_fingerprint"]
    assert (
        validated.pre_run_report["pre_run_contract_status"]
        == "incomplete"
    )
    assert validate_complete_package(out)["status"] == "passed"
    emitted_card = next(
        row
        for row in pre_run["verified_emission"]["physical_rows"]
        if row["meaningful"] is True
    )
    runtime_path = next(
        path
        for path in out.rglob(emitted_card["runtime_surface"])
        if "CustomConfig" in path.parts
    )
    runtime_bytes = runtime_path.read_bytes()
    runtime_path.unlink()
    try:
        with pytest.raises(
            ValueError,
            match="verified_emission_package_view_mismatch",
        ):
            validate_pre_run_package_reports(
                DirectoryPackageView(out)
            )
    finally:
        runtime_path.write_bytes(runtime_bytes)
    documents = {
        f"reports/{name}": _read_json(reports / name)
        for name in (
            "deck_identity.json",
            "layered_evidence_contract.json",
            "source_acquisition_closure.json",
            "disposition_ledger.json",
            "globalvalues_decision_ledger.json",
            "pre_run_closure.json",
            "input_manifest.json",
            "source_contract_audit.json",
        )
    }

    arbitrary_authority = deepcopy(documents)
    arbitrary_layered = arbitrary_authority[
        "reports/layered_evidence_contract.json"
    ]
    assert isinstance(arbitrary_layered, dict)
    first_claim = dispositions["claims"][0]
    arbitrary_layered["authorities"] = [
        {
            "deck_fingerprint": deck["deck_fingerprint"],
            "composite_claim_identity": (
                f"{deck['deck_fingerprint']}:{first_claim['claim_id']}"
            ),
            "claim_id": first_claim["claim_id"],
            "lane": "A",
            "authority_id": "A:coordinated-rehash",
            "source_identity": "forged-source",
            "as_of_date": "2026-07-29",
            "claim_kind": first_claim["claim_kind"],
            "content_sha256": "sha256:" + ("a" * 64),
            "exact_deck_fingerprint": None,
            "runtime_authorized": True,
            "reason": "official_card_data_authority",
        }
    ]
    arbitrary_layered["layered_coverage"] = {
        "numerator": 1,
        "denominator": len(dispositions["claims"]),
        "fraction": f"1/{len(dispositions['claims'])}",
        "value": 1 / len(dispositions["claims"]),
        "vacuous": False,
    }
    _rehash(arbitrary_layered)
    arbitrary_pre_run = arbitrary_authority[
        "reports/pre_run_closure.json"
    ]
    assert isinstance(arbitrary_pre_run, dict)
    arbitrary_pre_run["report_hashes"][
        "layered_evidence_contract"
    ] = arbitrary_layered["content_sha256"]
    _rehash(arbitrary_pre_run)
    with pytest.raises(
        ValueError,
        match="layered_evidence_contract_upstream_mismatch",
    ):
        validate_pre_run_package_reports(
            _MemoryPackageView(arbitrary_authority)
        )

    stale = deepcopy(documents)
    stale["reports/layered_evidence_contract.json"][
        "exact_guide_authority"
    ] = True
    with pytest.raises(
        ValueError,
        match="layered_evidence_contract_hash_stale",
    ):
        validate_pre_run_package_reports(_MemoryPackageView(stale))

    cross_deck = deepcopy(documents)
    cross_deck["reports/source_acquisition_closure.json"] = (
        build_source_acquisition_closure_report(
            deck_fingerprint="b" * 64,
            acquisition_closure=None,
        )
    )
    with pytest.raises(
        ValueError,
        match="source_acquisition_closure_cross_deck",
    ):
        validate_pre_run_package_reports(
            _MemoryPackageView(cross_deck)
        )

    duplicate = deepcopy(documents)
    duplicate_layered = duplicate[
        "reports/layered_evidence_contract.json"
    ]
    duplicate_layered["authorities"] = [
        deepcopy(arbitrary_layered["authorities"][0]),
        deepcopy(arbitrary_layered["authorities"][0]),
    ]
    ratio = duplicate_layered["layered_coverage"]
    ratio["numerator"] = 2
    ratio["denominator"] = len(dispositions["claims"])
    ratio["fraction"] = (
        f"{ratio['numerator']}/{ratio['denominator']}"
    )
    ratio["value"] = ratio["numerator"] / ratio["denominator"]
    _rehash(duplicate_layered)
    with pytest.raises(
        ValueError,
        match="layered_evidence_contract_duplicate",
    ):
        validate_pre_run_package_reports(
            _MemoryPackageView(duplicate)
        )

    missing = deepcopy(documents)
    missing.pop("reports/pre_run_closure.json")
    with pytest.raises(ValueError, match="pre_run_report_missing"):
        validate_pre_run_package_reports(_MemoryPackageView(missing))

    malformed = deepcopy(documents)
    malformed["reports/disposition_ledger.json"] = []
    with pytest.raises(ValueError, match="pre_run_report_malformed"):
        validate_pre_run_package_reports(
            _MemoryPackageView(malformed)
        )

    layered_path = reports / "layered_evidence_contract.json"
    original_layered = layered_path.read_text(encoding="utf-8")
    try:
        tampered_layered = json.loads(original_layered)
        tampered_layered["exact_guide_authority"] = True
        layered_path.write_text(
            json.dumps(tampered_layered),
            encoding="utf-8",
        )
        strict_report = validate_complete_package(out)
        assert strict_report["status"] == "failed"
        assert any(
            "layered_evidence_contract_hash_stale" in error
            for error in strict_report["errors"]
        )
    finally:
        layered_path.write_text(original_layered, encoding="utf-8")

    pre_run_path = reports / "pre_run_closure.json"
    original_pre_run = pre_run_path.read_bytes()
    try:
        pre_run_path.unlink()
        strict_report = validate_complete_package(out)
        assert strict_report["status"] == "failed"
        assert any(
            "pre_run_report_missing" in error
            for error in strict_report["errors"]
        )
    finally:
        pre_run_path.write_bytes(original_pre_run)


def _approved_inventory_and_catalog() -> tuple[dict, list[dict]]:
    return (
        _read_json(
            Path(
                "tests/fixtures/near100/"
                "current_semantic_inventory.json"
            )
        ),
        load_audited_deck_catalog(),
    )


def _aggregate_audited_packages(
    packages: tuple[_MemoryPackageView, ...],
) -> dict:
    inventory, catalog = _approved_inventory_and_catalog()
    return aggregate_pre_run_closure(
        packages,
        semantic_inventory=inventory,
        audited_catalog=catalog,
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("manifest_not_mapping", "pre_run_input_manifest_malformed"),
        ("handoff_not_mapping", "pre_run_authority_handoff_malformed"),
        ("pre_run_hash_stale", "pre_run_closure_hash_stale"),
        ("pre_run_cross_deck", "pre_run_closure_cross_deck"),
        ("deck_identity_cross_deck", "pre_run_deck_identity_cross_deck"),
        ("report_hash_drift", "pre_run_closure_report_hash_mismatch"),
        ("verified_cross_deck", "verified_emission_cross_deck"),
        (
            "semantic_projection_drift",
            "verified_emission_semantic_projection_mismatch",
        ),
        ("precision_drift", "pre_run_emission_precision_mismatch"),
        ("recall_drift", "pre_run_emission_recall_mismatch"),
        ("layered_ratio_drift", "pre_run_layered_coverage_mismatch"),
        ("status_drift", "pre_run_closure_status_mismatch"),
        ("strategy_drift", "pre_run_strategy_authority_status_invalid"),
        ("exact_flag_drift", "pre_run_exact_guide_authority_mismatch"),
        ("scope_drift", "pre_run_closure_hsconfig_scope_invalid"),
        ("deck_cards_not_list", "pre_run_deck_identity_malformed"),
        ("deck_card_malformed", "pre_run_deck_identity_malformed"),
        ("deck_hash_drift", "pre_run_deck_identity_hash_mismatch"),
    ),
)
def test_public_pre_run_validator_rejects_each_integrity_mutation(
    audited_packages: tuple[_MemoryPackageView, ...],
    mutation: str,
    reason: str,
) -> None:
    documents = deepcopy(audited_packages[0].documents)
    manifest = documents["reports/input_manifest.json"]
    pre_run = documents["reports/pre_run_closure.json"]
    deck_identity = documents["reports/deck_identity.json"]
    assert isinstance(manifest, dict)
    assert isinstance(pre_run, dict)
    assert isinstance(deck_identity, dict)

    if mutation == "manifest_not_mapping":
        documents["reports/input_manifest.json"] = []
    elif mutation == "handoff_not_mapping":
        manifest["pre_run_authority_handoff"] = []
    elif mutation == "pre_run_hash_stale":
        pre_run["strategy_authority_status"] = "strong"
    elif mutation == "pre_run_cross_deck":
        pre_run["deck_fingerprint"] = "sha256:" + ("b" * 64)
        _rehash(pre_run)
    elif mutation == "deck_identity_cross_deck":
        deck_identity["deck_fingerprint"] = "sha256:" + ("b" * 64)
    elif mutation == "report_hash_drift":
        pre_run["report_hashes"]["disposition_ledger"] = (
            "sha256:" + ("0" * 64)
        )
        _rehash(pre_run)
    elif mutation == "verified_cross_deck":
        verified = pre_run["verified_emission"]
        original_fingerprint = verified["deck_fingerprint"]
        other_fingerprint = "sha256:" + ("b" * 64)
        verified["deck_fingerprint"] = other_fingerprint
        for row in verified["semantic_expectations"]:
            row["deck_fingerprint"] = other_fingerprint
            row["composite_identity"] = row["composite_identity"].replace(
                original_fingerprint,
                other_fingerprint,
                1,
            )
        _rehash(pre_run)
    elif mutation == "semantic_projection_drift":
        pre_run["verified_emission"]["semantic_expectations"].pop()
        _rehash(pre_run)
    elif mutation == "precision_drift":
        pre_run["emission_precision"] = {
            "numerator": 0,
            "denominator": 1,
            "fraction": "0/1",
            "value": 0.0,
            "vacuous": False,
        }
        _rehash(pre_run)
    elif mutation == "recall_drift":
        pre_run["eligible_emission_recall"] = {
            "numerator": 0,
            "denominator": 1,
            "fraction": "0/1",
            "value": 0.0,
            "vacuous": False,
        }
        _rehash(pre_run)
    elif mutation == "layered_ratio_drift":
        pre_run["layered_pre_run_source_coverage"] = {
            "numerator": 0,
            "denominator": 1,
            "fraction": "0/1",
            "value": 0.0,
            "vacuous": False,
        }
        _rehash(pre_run)
    elif mutation == "status_drift":
        pre_run["pre_run_contract_status"] = "incomplete"
        _rehash(pre_run)
    elif mutation == "strategy_drift":
        pre_run["strategy_authority_status"] = "future"
        _rehash(pre_run)
    elif mutation == "exact_flag_drift":
        pre_run["exact_guide_authority"] = True
        _rehash(pre_run)
    elif mutation == "scope_drift":
        pre_run["hsconfig_scope"] = "RUNTIME"
        _rehash(pre_run)
    elif mutation == "deck_cards_not_list":
        deck_identity["main_deck"] = {}
    elif mutation == "deck_card_malformed":
        deck_identity["main_deck"] = [{}]
    else:
        deck_identity["main_deck"][0]["count"] += 1

    with pytest.raises(ValueError, match=reason):
        validate_pre_run_package_reports(_MemoryPackageView(documents))


def test_public_pre_run_validator_rejects_cross_deck_globalvalues_ledger(
    audited_packages: tuple[_MemoryPackageView, ...],
) -> None:
    documents = deepcopy(audited_packages[0].documents)
    validated = validate_pre_run_package_reports(audited_packages[0])
    other_fingerprint = "sha256:" + ("b" * 64)
    decisions = tuple(
        replace(decision, deck_fingerprint=other_fingerprint)
        for decision in validated.globalvalues_ledger.decisions
    )
    cross_deck = GlobalValuesDecisionLedger(
        deck_fingerprint=other_fingerprint,
        baseline_sha256=globalvalues_baseline_sha256(decisions),
        decisions=decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(decisions),
    )
    documents["reports/globalvalues_decision_ledger.json"] = (
        globalvalues_decision_report_document(cross_deck)
    )

    with pytest.raises(ValueError, match="pre_run_report_cross_deck"):
        validate_pre_run_package_reports(_MemoryPackageView(documents))


def _aggregate_with_validated_rows(
    monkeypatch: pytest.MonkeyPatch,
    packages: tuple[_MemoryPackageView, ...],
    validated_rows: tuple[pre_run_metrics.ValidatedPreRunPackage, ...],
) -> dict:
    # Every row comes from the real package validator before the one targeted
    # aggregate mutation is applied; isolate aggregation from a second reload.
    by_package = {
        id(package): validated
        for package, validated in zip(packages, validated_rows, strict=True)
    }
    monkeypatch.setattr(
        pre_run_metrics,
        "validate_pre_run_package_reports",
        lambda package: by_package[id(package)],
    )
    inventory, catalog = _approved_inventory_and_catalog()
    return aggregate_pre_run_closure(
        packages,
        semantic_inventory=inventory,
        audited_catalog=catalog,
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    (
        ("fingerprint_set", "pre_run_semantic_inventory_mismatch"),
        ("deck_name", "pre_run_semantic_inventory_mismatch"),
        ("cards_not_list", "pre_run_deck_identity_malformed"),
        ("sideboards_not_list", "pre_run_deck_identity_malformed"),
        ("claim_collision", "pre_run_composite_claim_collision"),
        ("audited_totals", "pre_run_audited_totals_mismatch"),
    ),
)
def test_aggregate_rejects_each_validated_integrity_mutation(
    audited_packages: tuple[_MemoryPackageView, ...],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    reason: str,
) -> None:
    validated = [
        validate_pre_run_package_reports(package)
        for package in audited_packages
    ]
    first = validated[0]
    if mutation == "fingerprint_set":
        validated[0] = replace(
            first,
            deck_fingerprint="sha256:" + ("b" * 64),
        )
    elif mutation == "deck_name":
        validated[0] = replace(
            first,
            deck_identity={**first.deck_identity, "deck_name": "OtherDeck"},
        )
    elif mutation == "cards_not_list":
        validated[0] = replace(
            first,
            deck_identity={**first.deck_identity, "main_deck": {}},
        )
    elif mutation == "sideboards_not_list":
        validated[0] = replace(
            first,
            deck_identity={**first.deck_identity, "sideboards": {}},
        )
    elif mutation == "claim_collision":
        duplicate_claims = (
            *first.disposition_ledger.claims,
            first.disposition_ledger.claims[0],
        )
        validated[0] = replace(
            first,
            disposition_ledger=_disposition_with_rows(
                first.disposition_ledger,
                claims=duplicate_claims,
            ),
        )
    else:
        deck_identity = deepcopy(first.deck_identity)
        deck_identity["main_deck"][0]["count"] += 1
        validated[0] = replace(first, deck_identity=deck_identity)

    with pytest.raises(ValueError, match=reason):
        _aggregate_with_validated_rows(
            monkeypatch,
            audited_packages,
            tuple(validated),
        )


def test_aggregate_records_exact_guide_authority_from_validated_package(
    audited_packages: tuple[_MemoryPackageView, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    validated = tuple(
        validate_pre_run_package_reports(package)
        for package in audited_packages
    )
    exact = (replace(validated[0], exact_guide_authority=True), *validated[1:])

    result = _aggregate_with_validated_rows(
        monkeypatch,
        audited_packages,
        exact,
    )

    assert result["exact_guide_authority_count"] == 1
    assert result["exact_guide_authority_decks"] == [exact[0].deck_fingerprint]


def test_audited_twelve_deck_acceptance_uses_only_validated_inventory_catalog():
    inventory, catalog = _approved_inventory_and_catalog()

    acceptance = audited_semantic_inventory_acceptance(
        semantic_inventory=inventory,
        audited_catalog=catalog,
    )

    assert acceptance == {
        "schema_version": 1,
        "scope": "AUDITED_SEMANTIC_INVENTORY_ONLY",
        "package_closure_claimed": False,
        "gameplay_quality_claimed": False,
        "runtime_emission_claimed": False,
        "canonical_content_sha256": (
            inventory["canonical_content_sha256"]
        ),
        "deck_count": 12,
        "main_slot_count": 360,
        "main_card_identity_count": 205,
        "sideboard_module_count": 3,
        "card_disposition_count": 208,
        "claim_count": 316,
        "globalvalues_decision_count": 456,
    }


def test_audited_acceptance_rejects_claim_substitution_after_rehash():
    inventory, catalog = _approved_inventory_and_catalog()
    substituted = deepcopy(inventory)
    claim = substituted["decks"][0]["claims"][0]
    claim["claim_id"] = "claim_substituted"
    claim["claim_key"] = (
        f"{substituted['decks'][0]['deck_fingerprint']}:"
        "claim_substituted"
    )
    payload = dict(substituted)
    payload.pop("canonical_content_sha256")
    substituted["canonical_content_sha256"] = sha256(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    with pytest.raises(
        ValueError,
        match="semantic_inventory_approved_content_sha256_invalid",
    ):
        audited_semantic_inventory_acceptance(
            semantic_inventory=substituted,
            audited_catalog=catalog,
        )


def test_package_aggregate_requires_validated_inventory_and_catalog():
    inventory, catalog = _approved_inventory_and_catalog()

    with pytest.raises(
        ValueError,
        match="pre_run_audited_deck_total_must_equal_12",
    ):
        aggregate_pre_run_closure(
            (),
            semantic_inventory=inventory,
            audited_catalog=catalog,
        )


def test_all_twelve_decks_have_complete_pre_run_closure(
    audited_packages: tuple[_MemoryPackageView, ...],
):
    totals = _aggregate_audited_packages(audited_packages)

    assert totals == {
        "deck_count": 12,
        "audited_deck_total": 12,
        "main_slot_count": 360,
        "main_card_identity_count": 205,
        "sideboard_module_count": 3,
        "card_disposition_count": 208,
        "final_card_disposition_count": 208,
        "claim_count": 316,
        "final_claim_disposition_count": 316,
        "raw_claim_id_count": 286,
        "raw_claim_id_collision_count": 30,
        "globalvalues_decision_count": 456,
        "final_globalvalues_decision_count": 456,
        "exact_guide_authority_count": 0,
        "exact_guide_authority_decks": [],
        "layered_pre_run_source_coverage": {
            "numerator": 316,
            "denominator": 316,
            "fraction": "316/316",
            "value": 1.0,
            "vacuous": False,
        },
        "emission_precision": 1.0,
        "emission_precision_ratio": {
            "numerator": 0,
            "denominator": 0,
            "fraction": "0/0",
            "value": 1.0,
            "vacuous": True,
        },
        "eligible_emission_recall": 1.0,
        "eligible_emission_recall_ratio": {
            "numerator": 0,
            "denominator": 0,
            "fraction": "0/0",
            "value": 1.0,
            "vacuous": True,
        },
    }
    assert totals["claim_count"] == 316
    assert totals["raw_claim_id_count"] == 286
    assert totals["raw_claim_id_collision_count"] == 30


@pytest.mark.parametrize("package_count", [11, 13])
def test_aggregate_rejects_non_twelve_package_cohorts(
    audited_packages: tuple[_MemoryPackageView, ...],
    package_count: int,
) -> None:
    packages = (
        audited_packages[:11]
        if package_count == 11
        else (*audited_packages, audited_packages[0])
    )

    with pytest.raises(
        ValueError,
        match="pre_run_audited_deck_total_must_equal_12",
    ):
        _aggregate_audited_packages(packages)


def test_aggregate_rejects_duplicate_deck_fingerprint(
    audited_packages: tuple[_MemoryPackageView, ...],
) -> None:
    packages = (*audited_packages[:-1], audited_packages[0])

    with pytest.raises(ValueError, match="pre_run_duplicate_package"):
        _aggregate_audited_packages(packages)


def test_aggregate_rejects_stale_report_hash_and_claimed_totals(
    audited_packages: tuple[_MemoryPackageView, ...],
) -> None:
    stale_documents = deepcopy(audited_packages[0].documents)
    stale_documents["reports/layered_evidence_contract.json"][
        "authorities"
    ][0]["reason"] = "stale"
    with pytest.raises(
        ValueError,
        match="layered_evidence_contract_hash_stale",
    ):
        _aggregate_audited_packages(
            (
                _MemoryPackageView(stale_documents),
                *audited_packages[1:],
            )
        )

    false_totals = deepcopy(audited_packages[0].documents)
    pre_run = false_totals["reports/pre_run_closure.json"]
    pre_run["counts"]["card_disposition_count"] += 1
    _rehash(pre_run)
    with pytest.raises(
        ValueError,
        match="pre_run_closure_totals_mismatch",
    ):
        _aggregate_audited_packages(
            (
                _MemoryPackageView(false_totals),
                *audited_packages[1:],
            )
        )


@pytest.mark.parametrize(
    ("row_kind", "mutation", "expected_error"),
    [
        ("card", "extra", "pre_run_audited_totals_mismatch"),
        ("card", "missing", "pre_run_audited_totals_mismatch"),
        ("claim", "extra", "pre_run_audited_totals_mismatch"),
        ("claim", "missing", "pre_run_audited_totals_mismatch"),
        (
            "globalvalues",
            "extra",
            "globalvalues_decision_ledger_incomplete",
        ),
        (
            "globalvalues",
            "missing",
            "globalvalues_decision_ledger_incomplete",
        ),
    ],
)
def test_aggregate_rejects_extra_or_missing_semantic_rows(
    audited_packages: tuple[_MemoryPackageView, ...],
    row_kind: str,
    mutation: str,
    expected_error: str,
) -> None:
    original = validate_pre_run_package_reports(audited_packages[0])
    disposition = original.disposition_ledger
    globalvalues = original.globalvalues_ledger
    if row_kind == "card":
        if mutation == "extra":
            extra = CardDispositionRow(
                deck_fingerprint=disposition.deck_fingerprint,
                composite_card_key=(
                    f"{disposition.deck_fingerprint}:"
                    "main_deck:ZZZ_EXTRA"
                ),
                zone="main_deck",
                official_semantics_canonical_json=(
                    b'{"GameCardId":"ZZZ_EXTRA"}'
                ),
                authority_lane=EvidenceLane.BOT_DELEGATION,
                evidence_ids=("policy:bot-native-pre-run",),
                claim_ids=(),
                physical_owner="ZZZ_EXTRA",
                disposition=CardDisposition.BOT_DELEGATED,
                runtime_paths=(),
                reason_code="bot_native_pre_run",
            )
            cards = tuple(
                sorted(
                    (*disposition.cards, extra),
                    key=lambda row: row.composite_card_key,
                )
            )
        else:
            cards = disposition.cards[1:]
        disposition = _disposition_with_rows(
            disposition,
            cards=cards,
        )
    elif row_kind == "claim":
        if mutation == "extra":
            extra_claim = ClaimDispositionRow(
                deck_fingerprint=disposition.deck_fingerprint,
                claim_id="zzzz-extra-claim",
                claim_kind="audited_semantic_claim",
                evidence_id="inventory:zzzz-extra-claim",
                disposition=ClaimDisposition.CONTRACT_ONLY,
                runtime_paths=(),
                reason_code="claim_kind_has_no_runtime_surface",
            )
            claims = tuple(
                sorted(
                    (*disposition.claims, extra_claim),
                    key=lambda row: row.claim_id,
                )
            )
        else:
            claims = disposition.claims[1:]
        disposition = _disposition_with_rows(
            disposition,
            claims=claims,
        )
    else:
        if mutation == "extra":
            extra_decision = GlobalValueDecision(
                deck_fingerprint=globalvalues.deck_fingerprint,
                key="zzzz_extra",
                kind=GlobalValueDecisionKind.COPY_BASELINE,
                baseline_canonical_json=b"0",
                emitted_canonical_json=b"0",
                authority_id="baseline:canonical",
                claim_ids=(),
                reason="copied canonical baseline",
            )
            decisions = (*globalvalues.decisions, extra_decision)
        else:
            decisions = globalvalues.decisions[:-1]
        globalvalues = _globalvalues_with_decisions(
            globalvalues,
            decisions,
        )
    mutated = _rebuilt_audited_view(
        audited_packages[0],
        disposition=disposition,
        globalvalues=globalvalues,
    )

    with pytest.raises(ValueError, match=expected_error):
        _aggregate_audited_packages(
            (mutated, *audited_packages[1:])
        )


def test_aggregate_rejects_open_source_acquisition(
    audited_packages: tuple[_MemoryPackageView, ...],
) -> None:
    fingerprint = validate_pre_run_package_reports(
        audited_packages[0]
    ).deck_fingerprint
    open_acquisition = build_source_acquisition_closure_report(
        deck_fingerprint=fingerprint,
        acquisition_closure=None,
    )
    mutated = _rebuilt_audited_view(
        audited_packages[0],
        acquisition=open_acquisition,
    )

    with pytest.raises(ValueError, match="pre_run_contract_incomplete"):
        _aggregate_audited_packages(
            (mutated, *audited_packages[1:])
        )


@pytest.mark.parametrize(
    ("physical_owner", "emit_physical"),
    [("WRONG_001", True), ("", False)],
)
def test_aggregate_rejects_physical_owner_mismatch_or_missing_eligible_emission(
    audited_packages: tuple[_MemoryPackageView, ...],
    physical_owner: str,
    emit_physical: bool,
) -> None:
    original = validate_pre_run_package_reports(audited_packages[0])
    disposition = original.disposition_ledger
    source_card = disposition.cards[0]
    runtime_card = replace(
        source_card,
        authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
        disposition=CardDisposition.RUNTIME_EMITTED,
        runtime_paths=(f"{source_card.physical_owner}.json",),
        reason_code="runtime_emitted",
    )
    runtime_disposition = _disposition_with_rows(
        disposition,
        cards=tuple(
            sorted(
                (runtime_card, *disposition.cards[1:]),
                key=lambda row: row.composite_card_key,
            )
        ),
    )
    matching_physical = (
        {
            "composite_card_key": runtime_card.composite_card_key,
            "physical_owner": runtime_card.physical_owner,
            "relative_path": runtime_card.runtime_paths[0],
            "meaningful": True,
            "schema_supported": True,
        },
    )
    baseline = _rebuilt_audited_view(
        audited_packages[0],
        disposition=runtime_disposition,
        physical_rows=matching_physical,
    )
    assert _aggregate_audited_packages(
        (baseline, *audited_packages[1:])
    )["eligible_emission_recall"] == 1.0

    physical_rows = (
        (
            {
                **matching_physical[0],
                "physical_owner": physical_owner,
                "relative_path": f"{physical_owner}.json",
            },
        )
        if emit_physical
        else ()
    )
    mutated = _rebuilt_audited_view(
        audited_packages[0],
        disposition=runtime_disposition,
        physical_rows=physical_rows,
    )

    with pytest.raises(ValueError, match="pre_run_contract_incomplete"):
        _aggregate_audited_packages(
            (mutated, *audited_packages[1:])
        )
