from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from hsconfig.cli import main
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
    aggregate_pre_run_closure,
    build_layered_evidence_contract_report,
    build_pre_run_closure_report,
    build_source_acquisition_closure_report,
    disposition_ledger_document,
    globalvalues_decision_report_document,
    validate_pre_run_package_reports,
    verified_emission_input_from_physical_rows,
)
from hsconfig.source_acquisition_closure import AcquisitionClosure
from hsconfig.strict_package_validation import validate_complete_package

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
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities={},
    )
    acquisition = build_source_acquisition_closure_report(
        deck_fingerprint=fingerprint,
        acquisition_closure=AcquisitionClosure(
            deck_fingerprint=fingerprint,
            attempt_id=f"inventory:{fingerprint}",
            attempted_at="2026-07-29",
            attempted_urls=("https://example.test/audited-source",),
            successful_evidence_ids=(),
            failed_attempts=(),
            negative_search_documented=True,
            checked_dossier=True,
            policy_id="audited-inventory",
            status="closed_negative_search",
            content_sha256=(
                f"sha256:{sha256(fingerprint.encode()).hexdigest()}"
            ),
        ),
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
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities={},
    )
    acquisition = acquisition or deepcopy(
        documents["reports/source_acquisition_closure.json"]
    )
    verified = verified_emission_input_from_physical_rows(
        disposition_ledger=disposition,
        physical_rows=physical_rows,
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
        }
    )
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
    assert len(layered["authorities"]) == len(dispositions["claims"])
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
    documents = {
        f"reports/{name}": _read_json(reports / name)
        for name in (
            "deck_identity.json",
            "layered_evidence_contract.json",
            "source_acquisition_closure.json",
            "disposition_ledger.json",
            "globalvalues_decision_ledger.json",
            "pre_run_closure.json",
        )
    }

    arbitrary_authority = deepcopy(documents)
    arbitrary_layered = arbitrary_authority[
        "reports/layered_evidence_contract.json"
    ]
    assert isinstance(arbitrary_layered, dict)
    arbitrary_layered["authorities"][0][
        "authority_id"
    ] = "opaque-authority-without-claim-id"
    _rehash(arbitrary_layered)
    arbitrary_pre_run = arbitrary_authority[
        "reports/pre_run_closure.json"
    ]
    assert isinstance(arbitrary_pre_run, dict)
    arbitrary_pre_run["report_hashes"][
        "layered_evidence_contract"
    ] = arbitrary_layered["content_sha256"]
    _rehash(arbitrary_pre_run)
    validate_pre_run_package_reports(
        _MemoryPackageView(arbitrary_authority)
    )

    stale = deepcopy(documents)
    stale["reports/layered_evidence_contract.json"][
        "authorities"
    ][0]["reason"] = "tampered"
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
    duplicate_layered["authorities"].append(
        deepcopy(duplicate_layered["authorities"][0])
    )
    ratio = duplicate_layered["layered_coverage"]
    ratio["numerator"] += 1
    ratio["denominator"] += 1
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
        tampered_layered["authorities"][0]["reason"] = "tampered"
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


def test_all_twelve_decks_have_complete_pre_run_closure(
    audited_packages: tuple[_MemoryPackageView, ...],
):
    totals = aggregate_pre_run_closure(audited_packages)

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
        aggregate_pre_run_closure(packages)


def test_aggregate_rejects_duplicate_deck_fingerprint(
    audited_packages: tuple[_MemoryPackageView, ...],
) -> None:
    packages = (*audited_packages[:-1], audited_packages[0])

    with pytest.raises(ValueError, match="pre_run_duplicate_package"):
        aggregate_pre_run_closure(packages)


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
        aggregate_pre_run_closure(
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
        aggregate_pre_run_closure(
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
        aggregate_pre_run_closure(
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
        aggregate_pre_run_closure(
            (mutated, *audited_packages[1:])
        )


@pytest.mark.parametrize(
    ("physical_owner", "emit_physical"),
    [("WRONG_OWNER", True), ("", False)],
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
        },
    )
    baseline = _rebuilt_audited_view(
        audited_packages[0],
        disposition=runtime_disposition,
        physical_rows=matching_physical,
    )
    assert aggregate_pre_run_closure(
        (baseline, *audited_packages[1:])
    )["eligible_emission_recall"] == 1.0

    physical_rows = (
        (
            {
                **matching_physical[0],
                "physical_owner": physical_owner,
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
        aggregate_pre_run_closure(
            (mutated, *audited_packages[1:])
        )
