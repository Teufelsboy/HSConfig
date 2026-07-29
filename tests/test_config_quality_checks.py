from __future__ import annotations

import json
import hashlib
import builtins
import importlib.resources
import os
import shutil
import socket
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import hsconfig.package_builder as package_builder
import hsconfig.package_derivation_receipt as package_derivation_receipt
import hsconfig.runtime_surface_ledger as runtime_surface_ledger
import hsconfig.visionai_registry as visionai_registry
import hsconfig.config_quality_checks as config_quality_checks_module
import hsconfig.mechanic_support as mechanic_support
import hsconfig.role_tokens as role_tokens
import hsconfig.source_document_model as source_document_model
from hsconfig.config_quality_checks import evaluate_config_quality
from hsconfig.config_quality_inputs import load_config_quality_inputs
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.globalvalues_decisions import (
    build_globalvalues_decision_ledger,
    canonical_globalvalues_baseline_sha256,
)
from hsconfig.package_model import (
    DirectoryPackageView,
    PackageModel,
    build_runtime_surface_plan,
)
from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    EvidenceLane,
    LayeredEvidenceContract,
    MulliganPlanModel,
    disposition_ledger_content_sha256,
)
from hsconfig.package_renderer import render_package_model
from hsconfig.pre_run_metrics import (
    disposition_ledger_document,
    globalvalues_decision_report_document,
    load_disposition_ledger_report,
)
from tests.helpers.fixture_prepare import (
    load_archetype_matrix,
    prepare_fixture_deck,
)
from tests.test_config_quality_contract import minimal_clean_package


class _PoisonableMemoryPackageView:
    package_label = "memory://quality-checks"

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.poisoned = False

    def file_names(self) -> tuple[str, ...]:
        self._require_live()
        return tuple(reversed(tuple(self.files)))

    def read_bytes(self, relative_path: str) -> bytes:
        self._require_live()
        return self.files[relative_path]

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8-sig"))

    def exists(self, relative_path: str) -> bool:
        self._require_live()
        return relative_path in self.files

    def _require_live(self) -> None:
        if self.poisoned:
            raise AssertionError("the source view was consulted after loading")


def _package_bytes(package: Path) -> dict[str, bytes]:
    return {
        path.relative_to(package).as_posix(): path.read_bytes()
        for path in package.rglob("*")
        if path.is_file()
    }


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _report_digest(value: dict[str, Any]) -> str:
    payload = dict(value)
    payload.pop("content_sha256", None)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def _typed_quality_model() -> PackageModel:
    fingerprint = "a" * 64
    card = CardDispositionRow(
        deck_fingerprint=fingerprint,
        composite_card_key=f"{fingerprint}:main_deck:NX2_019",
        zone="main_deck",
        official_semantics_canonical_json=json.dumps(
            {
                "GameCardId": "NX2_019",
                "BeforeBattlecryTargetBonus": {
                    "values": [{"condition": "*", "value": "10"}]
                },
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8"),
        authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
        evidence_ids=("evidence:sha256:source",),
        claim_ids=("claim_mind_sear_effect",),
        physical_owner="NX2_019",
        disposition=CardDisposition.RUNTIME_EMITTED,
        runtime_paths=("NX2_019.json",),
        reason_code="physical_meaningful_emission",
    )
    claim = ClaimDispositionRow(
        deck_fingerprint=fingerprint,
        claim_id="claim_mind_sear_effect",
        claim_kind="targeting_rule",
        evidence_id="evidence:sha256:source",
        disposition=ClaimDisposition.RUNTIME_EMITTED,
        runtime_paths=("NX2_019.json",),
        reason_code="physical_meaningful_emission",
    )
    disposition = DispositionLedger(
        deck_fingerprint=fingerprint,
        cards=(card,),
        claims=(claim,),
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=fingerprint,
            cards=(card,),
            claims=(claim,),
        ),
    )
    globalvalues = build_globalvalues_decision_ledger(
        deck_fingerprint=fingerprint,
        baseline=FALLBACK_GLOBALVALUES_BASELINE,
        baseline_sha256=canonical_globalvalues_baseline_sha256(
            FALLBACK_GLOBALVALUES_BASELINE
        ),
        authority_matrix={"allowed_step1_overlays": []},
    )
    mulligan = MulliganPlanModel(
        deck_name="Typed Quality",
        rules=(),
        suppressed=(),
        bot_delegated=(),
        merged_duplicate_rule_count=0,
    )
    evidence = LayeredEvidenceContract(
        deck_fingerprint=fingerprint,
        authorities=(),
        exact_guide_authority=False,
        layered_coverage_numerator=0,
        layered_coverage_denominator=0,
        content_sha256="fixture",
    )
    return PackageModel(
        deck_name=mulligan.deck_name,
        deck_fingerprint=fingerprint,
        mulligan_plan=mulligan,
        globalvalues_ledger=globalvalues,
        disposition_ledger=disposition,
        evidence_contract=evidence,
        runtime_surface_plan=build_runtime_surface_plan(
            mulligan_plan=mulligan,
            globalvalues_ledger=globalvalues,
            disposition_ledger=disposition,
            combo_decision_ids=(),
        ),
    )


def _typed_quality_files(package: Path) -> dict[str, bytes]:
    files = _package_bytes(package)
    model = _typed_quality_model()
    rendered = render_package_model(model)
    for artifact in rendered.artifacts:
        if "/" not in artifact.relative_path:
            files[
                f"CustomConfig/shadowpriest/{artifact.relative_path}"
            ] = artifact.content
    files["reports/deck_identity.json"] = _json_bytes(
        {"cards": [{"card_id": "NX2_019"}]}
    )
    files["reports/disposition_ledger.json"] = _json_bytes(
        disposition_ledger_document(model.disposition_ledger)
    )
    files["reports/source_contract_audit.json"] = _json_bytes(
        {
            "claim_rows": {
                "claim_mind_sear_effect": {
                    "claim_id": "claim_mind_sear_effect"
                }
            }
        }
    )
    closure = {
        "acquisition_closure": {
            "status": "closed_with_evidence",
            "successful_evidence_ids": ["evidence:sha256:source"],
        }
    }
    closure["content_sha256"] = _report_digest(closure)
    files["reports/source_acquisition_closure.json"] = _json_bytes(closure)
    files["reports/globalvalues_decision_ledger.json"] = _json_bytes(
        globalvalues_decision_report_document(model.globalvalues_ledger)
    )
    return files


def _evaluate_files(files: dict[str, bytes]) -> dict[str, Any]:
    return evaluate_config_quality(
        load_config_quality_inputs(_PoisonableMemoryPackageView(files))
    )


def _typed_diagnostics_files(files: dict[str, bytes]) -> dict[str, Any]:
    return config_quality_checks_module._typed_input_diagnostics(
        load_config_quality_inputs(_PoisonableMemoryPackageView(files))
    )


def test_evaluator_never_reconsults_the_poisoned_original_view(
    tmp_path: Path,
) -> None:
    package = minimal_clean_package(tmp_path)
    source = _PoisonableMemoryPackageView(_package_bytes(package))
    inputs = load_config_quality_inputs(source)
    expected = evaluate_config_quality(inputs)

    source.files.clear()
    source.poisoned = True

    first = evaluate_config_quality(inputs)
    second = evaluate_config_quality(inputs)

    assert first == second
    assert first == expected
    assert first["status"] == "clean"
    assert first["problems"] == []


def test_evaluator_survives_source_directory_deletion_after_load(
    tmp_path: Path,
) -> None:
    package = minimal_clean_package(tmp_path)
    inputs = load_config_quality_inputs(DirectoryPackageView(package))
    expected = evaluate_config_quality(inputs)

    shutil.rmtree(package)

    assert evaluate_config_quality(inputs) == expected


def test_passing_typed_input_preserves_the_existing_sixteen_checks(
    tmp_path: Path,
) -> None:
    assert isinstance(_typed_quality_model(), PackageModel)
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    report = _evaluate_files(files)

    assert report["status"] == "clean"
    assert tuple(report["checks"]) == (
        "operator_summary",
        "card_behavior",
        "source_to_runtime_explainability",
        "trace_completeness",
        "runtime_row_trace_inventory",
        "closure_freshness",
        "mechanic_runtime_discipline",
        "runtime_json",
        "legacy_surfaces",
        "darkbishop_boundary",
        "config_intent_self_audit",
        "surface_intent_projection",
        "visionai_semantic_surface",
        "globalvalues",
        "source_evidence",
        "semantic_intent_coverage",
    )
    assert "semantic_inventory_drift" not in report["checks"]["trace_completeness"]
    assert "disposition_errors" not in report["checks"]["source_evidence"]
    assert "evidence_digest_mismatches" not in report["checks"]["source_evidence"]
    assert "typed_runtime_surface_errors" not in report["checks"]["runtime_json"]
    assert "decision_errors" not in report["checks"]["globalvalues"]
    assert _typed_diagnostics_files(files) == {
        "semantic_inventory_drift": {
            "missing_card_dispositions": [],
            "unexpected_card_dispositions": [],
            "missing_claim_dispositions": [],
            "unexpected_claim_dispositions": [],
        },
        "source_claim_inventory_drift": {},
        "disposition_errors": [],
        "evidence_digest_mismatches": [],
        "typed_runtime_surface_errors": {
            "unexpected_physical_surfaces": [],
            "unexpected_declared_surfaces": [],
        },
        "globalvalues_decision_errors": {
            "missing_decisions": [],
            "duplicate_decisions": [],
            "extra_decisions": [],
            "decision_order_mismatch": [],
            "missing_physical_keys": [],
            "extra_physical_keys": [],
            "physical_ledger_mismatch": [],
            "invalid_ledger": [],
        },
    }


def test_real_shadowpriest_typed_package_has_no_false_positive_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    shadow = next(
        row
        for row in load_archetype_matrix()
        if row["deck_name"] == "ShadowPriest"
    )
    prepared = prepare_fixture_deck(tmp_path, shadow)
    assert prepared["exit_code"] == 0

    inputs = load_config_quality_inputs(
        DirectoryPackageView(prepared["out"])
    )
    assert inputs.package.derivation_receipt_verified is True
    assert inputs.package.rederived_runtime_surface_ledger is not None
    report = evaluate_config_quality(inputs)
    diagnostics = config_quality_checks_module._typed_input_diagnostics(inputs)

    assert "semantic_inventory_drift" not in report["checks"][
        "trace_completeness"
    ]
    assert "disposition_errors" not in report["checks"]["source_evidence"]
    assert "evidence_digest_mismatches" not in report["checks"][
        "source_evidence"
    ]
    assert "typed_runtime_surface_errors" not in report["checks"][
        "runtime_json"
    ]
    assert "decision_errors" not in report["checks"]["globalvalues"]
    assert diagnostics["semantic_inventory_drift"] == {
        "missing_card_dispositions": [],
        "unexpected_card_dispositions": [],
        "missing_claim_dispositions": [],
        "unexpected_claim_dispositions": [],
    }
    assert diagnostics["source_claim_inventory_drift"] == {}
    assert diagnostics["evidence_digest_mismatches"] == []
    assert diagnostics["typed_runtime_surface_errors"] == {
        "unexpected_physical_surfaces": [],
        "unexpected_declared_surfaces": [],
    }
    assert not any(diagnostics["globalvalues_decision_errors"].values())
    assert {
        (row["kind"], row["identity"].rsplit(":", 1)[-1])
        for row in diagnostics["disposition_errors"]
    } == {
        ("unresolved_card_disposition", "GVG_009"),
        ("unresolved_card_disposition", "NX2_019"),
        ("unresolved_card_disposition", "VAC_419"),
    }
    assert not {
        problem["check"]
        for problem in report["problems"]
    } & {
        "semantic_inventory_disposition_drift",
        "disposition_ledger_invalid",
        "source_evidence_digest_mismatch",
        "typed_runtime_surface_inventory_drift",
        "globalvalues_decision_ledger_invalid",
    }


def test_semantic_inventory_count_drift_is_diagnostic_only(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    files["reports/deck_identity.json"] = _json_bytes(
        {"cards": [{"card_id": "NX2_019"}, {"card_id": "EXTRA_001"}]}
    )

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["semantic_inventory_drift"] == {
        "missing_card_dispositions": ["EXTRA_001"],
        "unexpected_card_dispositions": [],
        "missing_claim_dispositions": [],
        "unexpected_claim_dispositions": [],
    }
    assert "semantic_inventory_drift" not in report["checks"]["trace_completeness"]
    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["runtime_write_performed"] is False


def test_cross_zone_membership_does_not_create_missing_card_disposition(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    deck_identity = json.loads(
        files["reports/deck_identity.json"].decode("utf-8")
    )
    deck_identity["sideboards"] = [
        {"cards": [{"card_id": "NX2_019"}]}
    ]
    files["reports/deck_identity.json"] = _json_bytes(deck_identity)

    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["semantic_inventory_drift"][
        "missing_card_dispositions"
    ] == []
    assert diagnostics["semantic_inventory_drift"][
        "unexpected_card_dispositions"
    ] == []


def test_missing_claim_lifecycle_is_an_unresolved_disposition(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    document = json.loads(
        files["reports/disposition_ledger.json"].decode("utf-8")
    )
    parsed = load_disposition_ledger_report(document)
    unresolved_claim = replace(
        parsed.claims[0],
        disposition=ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
        runtime_paths=(),
        reason_code="missing_claim_lifecycle",
    )
    unresolved = DispositionLedger(
        deck_fingerprint=parsed.deck_fingerprint,
        cards=parsed.cards,
        claims=(unresolved_claim,),
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=parsed.deck_fingerprint,
            cards=parsed.cards,
            claims=(unresolved_claim,),
        ),
    )
    files["reports/disposition_ledger.json"] = _json_bytes(
        disposition_ledger_document(unresolved)
    )

    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["disposition_errors"] == [
        {
            "kind": "unresolved_claim_disposition",
            "identity": (
                f"{parsed.deck_fingerprint}:claim_mind_sear_effect"
            ),
        },
    ]


def test_duplicate_disposition_is_rejected_by_canonical_parser(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    document = json.loads(
        files["reports/disposition_ledger.json"].decode("utf-8")
    )
    document["claims"].append(dict(document["claims"][0]))
    files["reports/disposition_ledger.json"] = _json_bytes(document)

    errors = _typed_diagnostics_files(files)["disposition_errors"]

    assert errors == [
        {
            "kind": "duplicate_claim_disposition",
            "identity": (
                f"{'a' * 64}:claim_mind_sear_effect"
            ),
        },
        {
            "kind": "invalid_disposition_ledger",
            "identity": "disposition_ledger_report_invalid",
        },
    ]


def test_source_evidence_digest_mismatch_fails_closed(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    closure = json.loads(
        files["reports/source_acquisition_closure.json"].decode("utf-8")
    )
    expected_digest = closure["content_sha256"]
    closure["content_sha256"] = "sha256:" + ("0" * 64)
    files["reports/source_acquisition_closure.json"] = _json_bytes(closure)

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    expected = [
        {
            "artifact": "reports/source_acquisition_closure.json",
            "expected": expected_digest,
            "reported": "sha256:" + ("0" * 64),
        }
    ]
    assert (
        diagnostics["evidence_digest_mismatches"]
        == expected
    )
    assert "evidence_digest_mismatches" not in report["checks"]["source_evidence"]


def test_cross_artifact_source_claim_counters_must_agree(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    layered = {
        "authorities": [
            {"claim_id": "claim_mind_sear_effect"},
            {"claim_id": "claim_extra"},
        ]
    }
    layered["content_sha256"] = _report_digest(layered)
    files["reports/layered_evidence_contract.json"] = _json_bytes(layered)

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["source_claim_inventory_drift"] == {
        "layered_evidence_contract": {
            "missing_claim_ids": [],
            "unexpected_claim_ids": ["claim_extra"],
        }
    }
    assert diagnostics["evidence_digest_mismatches"] == []
    assert report["status"] == "clean"


def test_unexpected_physical_and_declared_runtime_surfaces_fail_closed(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    files["CustomConfig/shadowpriest/EXTRA_001.json"] = _json_bytes(
        {
            "GameCardId": "EXTRA_001",
            "BeforePlayCardBonus": {
                "values": [{"condition": "*", "value": "1"}]
            },
        }
    )
    disposition = json.loads(
        files["reports/disposition_ledger.json"].decode("utf-8")
    )
    disposition["cards"][0]["runtime_paths"].append("MISSING_001.json")
    files["reports/disposition_ledger.json"] = _json_bytes(disposition)

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    expected = {
        "unexpected_physical_surfaces": ["EXTRA_001.json"],
        "unexpected_declared_surfaces": ["MISSING_001.json"],
    }
    assert diagnostics["typed_runtime_surface_errors"] == expected
    assert "typed_runtime_surface_errors" not in report["checks"]["runtime_json"]


def test_runtime_surface_inventory_accepts_persisted_ledger_declaration(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    disposition = json.loads(
        files["reports/disposition_ledger.json"].decode("utf-8")
    )
    disposition["cards"][0]["runtime_paths"] = []
    files["reports/disposition_ledger.json"] = _json_bytes(disposition)
    files["reports/runtime_surface_ledger.json"] = _json_bytes(
        {
            "cards": {
                "NX2_019": {
                    "runtime_emitted": True,
                    "runtime_surfaces": ["NX2_019.json"],
                }
            },
            "linked_runtime_entities": {},
        }
    )

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["typed_runtime_surface_errors"] == {
        "unexpected_physical_surfaces": [],
        "unexpected_declared_surfaces": [],
    }
    assert "typed_runtime_surface_errors" not in report["checks"]["runtime_json"]


def test_runtime_surface_inventory_ignores_special_and_nonemitted_declarations(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    files["reports/runtime_surface_ledger.json"] = _json_bytes(
        {
            "cards": {
                "NX2_019": {
                    "runtime_emitted": True,
                    "runtime_surfaces": [
                        "Mulligan.json",
                        "Combo.json",
                        "NX2_019.json",
                    ],
                }
            },
            "linked_runtime_entities": {
                "EX1_625t": {
                    "runtime_emitted": False,
                    "runtime_surface": "EX1_625t.json",
                }
            },
        }
    )

    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["typed_runtime_surface_errors"] == {
        "unexpected_physical_surfaces": [],
        "unexpected_declared_surfaces": [],
    }


def test_persisted_runtime_surface_inventory_detects_missing_cardid_file(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    files["reports/runtime_surface_ledger.json"] = _json_bytes(
        {
            "cards": {
                "NX2_019": {
                    "runtime_emitted": True,
                    "runtime_surfaces": [
                        "NX2_019.json",
                        "MISSING_001.json",
                    ],
                }
            },
            "linked_runtime_entities": {},
        }
    )

    diagnostics = _typed_diagnostics_files(files)

    assert diagnostics["typed_runtime_surface_errors"] == {
        "unexpected_physical_surfaces": [],
        "unexpected_declared_surfaces": ["MISSING_001.json"],
    }


@pytest.mark.parametrize(
    ("mutation", "expected_missing", "expected_duplicate", "expected_extra"),
    [
        (
            "missing",
            ["GlobalMinionAttack"],
            [],
            [],
        ),
        (
            "duplicate",
            [],
            ["GlobalMinionAttack"],
            [],
        ),
        (
            "extra",
            [],
            [],
            ["BogusKey"],
        ),
    ],
)
def test_globalvalues_decisions_use_authoritative_roster_not_mutual_parity(
    tmp_path: Path,
    mutation: str,
    expected_missing: list[str],
    expected_duplicate: list[str],
    expected_extra: list[str],
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    globalvalues = json.loads(
        files["CustomConfig/shadowpriest/GlobalValues.json"].decode("utf-8")
    )
    ledger = json.loads(
        files["reports/globalvalues_decision_ledger.json"].decode("utf-8")
    )
    target_index = next(
        index
        for index, row in enumerate(ledger["decisions"])
        if row["key"] == "GlobalMinionAttack"
    )
    if mutation == "missing":
        ledger["decisions"].pop(target_index)
        globalvalues.pop("GlobalMinionAttack")
    elif mutation == "duplicate":
        ledger["decisions"].insert(
            target_index,
            dict(ledger["decisions"][target_index]),
        )
    else:
        extra = dict(ledger["decisions"][target_index])
        extra["key"] = "BogusKey"
        ledger["decisions"].append(extra)
        globalvalues["BogusKey"] = globalvalues["GlobalMinionAttack"]
    files["CustomConfig/shadowpriest/GlobalValues.json"] = _json_bytes(globalvalues)
    files["reports/globalvalues_decision_ledger.json"] = _json_bytes(ledger)

    report = _evaluate_files(files)
    diagnostics = _typed_diagnostics_files(files)

    errors = diagnostics["globalvalues_decision_errors"]
    assert errors["missing_decisions"] == expected_missing
    assert errors["duplicate_decisions"] == expected_duplicate
    assert errors["extra_decisions"] == expected_extra
    assert errors["physical_ledger_mismatch"] == []
    assert errors["invalid_ledger"]
    assert "decision_errors" not in report["checks"]["globalvalues"]


def test_globalvalues_decision_order_is_exact(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    ledger = json.loads(
        files["reports/globalvalues_decision_ledger.json"].decode("utf-8")
    )
    ledger["decisions"][0], ledger["decisions"][1] = (
        ledger["decisions"][1],
        ledger["decisions"][0],
    )
    files["reports/globalvalues_decision_ledger.json"] = _json_bytes(ledger)

    errors = _typed_diagnostics_files(files)[
        "globalvalues_decision_errors"
    ]

    assert errors["missing_decisions"] == []
    assert errors["duplicate_decisions"] == []
    assert errors["extra_decisions"] == []
    assert errors["decision_order_mismatch"][:2] == [
        "ConfigComment",
        "GameCardId",
    ]
    assert errors["invalid_ledger"] == [
        "globalvalues_decision_ledger_report_invalid"
    ]


def test_evaluator_has_no_post_load_ambient_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    inputs = load_config_quality_inputs(
        _PoisonableMemoryPackageView(files)
    )
    expected = evaluate_config_quality(inputs)

    def poisoned(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("ambient authority was consulted")

    monkeypatch.setattr(builtins, "open", poisoned)
    for method in (
        "read_bytes",
        "read_text",
        "is_file",
        "is_dir",
        "rglob",
        "glob",
        "iterdir",
        "exists",
        "open",
    ):
        monkeypatch.setattr(Path, method, poisoned)
    monkeypatch.setattr(socket, "create_connection", poisoned)
    monkeypatch.setattr(os, "getenv", poisoned)
    monkeypatch.setattr(subprocess, "run", poisoned)
    monkeypatch.setattr(subprocess, "Popen", poisoned)
    monkeypatch.setattr(time, "time", poisoned)
    monkeypatch.setattr(importlib.resources, "files", poisoned)
    monkeypatch.setattr(
        package_derivation_receipt,
        "verify_package_derivation_receipt_from_view",
        poisoned,
    )
    monkeypatch.setattr(
        runtime_surface_ledger,
        "rederive_runtime_surface_ledger_from_view",
        poisoned,
    )
    monkeypatch.setattr(
        package_builder,
        "prepare_package_payload",
        poisoned,
    )
    monkeypatch.setattr(
        visionai_registry,
        "classify_runtime_surface",
        poisoned,
    )
    assert evaluate_config_quality(inputs) == expected


def test_evaluator_ignores_origin_registry_rebinding_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = load_config_quality_inputs(
        _PoisonableMemoryPackageView(
            _typed_quality_files(minimal_clean_package(tmp_path))
        )
    )
    expected = evaluate_config_quality(inputs)

    monkeypatch.setattr(visionai_registry, "RUNTIME_SURFACE_REGISTRY", {})
    monkeypatch.setattr(visionai_registry, "RUNTIME_ROW_SCHEMA_KEYS", {})
    monkeypatch.setattr(mechanic_support, "MECHANIC_SUPPORT", {})
    monkeypatch.setattr(mechanic_support, "ROLE_ALIASES", {})
    monkeypatch.setattr(role_tokens, "EXPLICIT_OPENING_HAND_MULLIGAN_ROLES", set())
    monkeypatch.setattr(
        source_document_model,
        "RUNTIME_LOWERABLE_CLAIM_READINESS",
        frozenset(),
    )
    assert config_quality_checks_module._has_target_authority(
        [{"claim_kind": "targeting_rule"}]
    )
    monkeypatch.setattr(
        config_quality_checks_module,
        "TARGET_AUTHORITY_TOKENS",
        frozenset(),
    )

    assert config_quality_checks_module._has_target_authority(
        [{"claim_kind": "targeting_rule"}]
    )
    assert evaluate_config_quality(inputs) == expected


def _reverse_mappings(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _reverse_mappings(nested)
            for key, nested in reversed(tuple(value.items()))
        }
    if isinstance(value, list):
        return [_reverse_mappings(item) for item in value]
    return value


def _reverse_json_object_bytes(files: dict[str, bytes]) -> dict[str, bytes]:
    reversed_files: dict[str, bytes] = {}
    for path, value in reversed(tuple(files.items())):
        if not path.endswith(".json"):
            reversed_files[path] = value
            continue
        document = json.loads(value.decode("utf-8-sig"))
        reversed_files[path] = _json_bytes(_reverse_mappings(document))
    return reversed_files


def test_semantically_equal_insertion_orders_have_identical_report_bytes(
    tmp_path: Path,
) -> None:
    files = _typed_quality_files(minimal_clean_package(tmp_path))
    first_inputs = load_config_quality_inputs(
        _PoisonableMemoryPackageView(dict(files))
    )
    second_inputs = load_config_quality_inputs(
        _PoisonableMemoryPackageView(_reverse_json_object_bytes(files))
    )

    first = evaluate_config_quality(first_inputs)
    second = evaluate_config_quality(second_inputs)
    canonical_first = json.dumps(
        first,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    canonical_second = json.dumps(
        second,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert first == second
    assert canonical_first == canonical_second
    assert first_inputs.package.file_names() == second_inputs.package.file_names()
