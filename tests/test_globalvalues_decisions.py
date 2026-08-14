from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.disposition_ledger import build_dual_closure
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE
from hsconfig.globalvalues_decisions import (
    GLOBALVALUES_BASELINE_DECISION_KEYS,
    build_globalvalues_decision_ledger,
    globalvalues_decision_ledger_document,
    normalize_globalvalues_decision_baseline,
)
from hsconfig.package_domain import (
    DispositionLedger,
    GlobalValueDecisionKind,
    disposition_ledger_content_sha256,
)
from hsconfig.visionai_registry import GLOBALVALUES_KEY_REGISTRY


DECK_FINGERPRINT = "f" * 64
BASELINE_SHA256 = (
    "sha256:67e6f87a792c86ffbd28b10b6289ba6d88ef17c7e8204eff3b7d968be77b5177"
)
BASELINE_LEDGER_SHA256 = (
    "sha256:4494a4829b199e029390d46b208eca60fd47f9340b852cb3049463f2bb6687fc"
)
EXPECTED_BASELINE_KEYS = (
    "GameCardId",
    "ConfigComment",
    "FirstTurnValueWeight",
    "SecondTurnValueWeight",
    "GlobalDivineShield",
    "GlobalDurability",
    "GlobalStealth",
    "GlobalHeroAttack",
    "GlobalMinionAttack",
    "GlobalWeaponAttack",
    "GlobalTaunt",
    "GlobalOverload",
    "GlobalQuestProgressValue",
    "GlobalFrozen",
    "GlobalWindfury",
    "GlobalHeroHealth",
    "GlobalMinionHealth",
    "GlobalLocationHealth",
    "GlobalCharge",
    "GlobalMinionIntrinsicValue",
    "GlobalLocationIntrinsicValue",
    "OppGlobalDivineShield",
    "OppGlobalDurability",
    "OppGlobalStealth",
    "OppGlobalHeroAttack",
    "OppGlobalMinionAttack",
    "OppGlobalWeaponAttack",
    "OppGlobalTaunt",
    "OppGlobalOverload",
    "OppGlobalQuestProgressValue",
    "OppGlobalFrozen",
    "OppGlobalWindfury",
    "OppGlobalHeroHealth",
    "OppGlobalMinionHealth",
    "OppGlobalLocationHealth",
    "OppGlobalCharge",
    "OppGlobalMinionIntrinsicValue",
    "OppGlobalLocationIntrinsicValue",
)


def _baseline_matrix() -> dict[str, object]:
    return {
        "aggression_profile": "balanced",
        "posture": "baseline",
        "allowed_step1_overlays": [
            {
                "key": "baseline",
                "overlay": "none",
                "operation": "none",
                "value": None,
                "authority": "baseline_default",
                "key_authority": {
                    "key": "baseline",
                    "category": "copy_baseline",
                    "board_value_component": "baseline",
                },
                "claim_refs": [],
                "reason": "no_source_backed_posture_overlay",
            }
        ],
        "blocked_until_runtime_evidence": [],
    }


def _overlay_row(
    *,
    key: str = "FirstTurnValueWeight",
    operation: str = "set",
    value: str | None = "0.75",
) -> dict[str, object]:
    return {
        "key": key,
        "overlay": f"set:{value}" if operation == "set" else operation,
        "operation": operation,
        "value": value,
        "authority": "step1_source_backed_posture",
        "key_authority": {
            "key": key,
            "category": "step1_posture_overlay_allowed",
            "board_value_component": "turn_weight",
        },
        "claim_refs": ["raw-posture", "guide:exact"],
        "claim_id": "lifecycle-posture",
        "reason": "exact guide posture",
    }


def _overlay_matrix(row: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "aggression_profile": "aggro",
        "posture": "aggro",
        "allowed_step1_overlays": [row or _overlay_row()],
        "blocked_until_runtime_evidence": [],
    }


def _baseline_inputs(
    *,
    baseline: dict[str, object] | None = None,
    baseline_sha256: str = BASELINE_SHA256,
    authority_matrix: dict[str, object] | None = None,
    deck_fingerprint: str = DECK_FINGERPRINT,
) -> dict[str, object]:
    return {
        "deck_fingerprint": deck_fingerprint,
        "baseline": (
            deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
            if baseline is None
            else baseline
        ),
        "baseline_sha256": baseline_sha256,
        "authority_matrix": authority_matrix or _baseline_matrix(),
    }


def _parsed_emitted_values(ledger: object) -> dict[str, object]:
    return {
        row.key: json.loads(row.emitted_canonical_json)
        for row in ledger.decisions
    }


def test_baseline_profile_closes_all_38_keys_in_registry_order() -> None:
    ledger = build_globalvalues_decision_ledger(**_baseline_inputs())

    assert GLOBALVALUES_BASELINE_DECISION_KEYS == EXPECTED_BASELINE_KEYS
    assert tuple(row.key for row in ledger.decisions) == EXPECTED_BASELINE_KEYS
    assert len(ledger.decisions) == 38
    assert {row.kind for row in ledger.decisions} == {
        GlobalValueDecisionKind.COPY_BASELINE
    }
    assert all(
        row.baseline_canonical_json == row.emitted_canonical_json
        for row in ledger.decisions
    )


def test_baseline_decision_registry_does_not_repurpose_authority_registry() -> None:
    assert len(GLOBALVALUES_KEY_REGISTRY) == 13
    assert len(GLOBALVALUES_BASELINE_DECISION_KEYS) == 38
    assert "MyHeroPowerValue" in GLOBALVALUES_KEY_REGISTRY
    assert "MyHeroPowerValue" not in GLOBALVALUES_BASELINE_DECISION_KEYS


def test_baseline_hash_and_ordered_ledger_digest_are_canonical() -> None:
    ledger = build_globalvalues_decision_ledger(**_baseline_inputs())

    assert ledger.baseline_sha256 == BASELINE_SHA256
    assert ledger.content_sha256 == BASELINE_LEDGER_SHA256


def test_sparse_runtime_baseline_overlays_pinned_38_key_fallback() -> None:
    runtime_baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Runtime baseline",
        "FirstTurnValueWeight": {
            "values": [{"condition": "*", "value": "0.25"}]
        },
        "RuntimeOnlyFullBaselineKey": {
            "values": [{"condition": "*", "value": "9"}]
        },
    }

    normalized = normalize_globalvalues_decision_baseline(runtime_baseline)
    runtime_baseline["FirstTurnValueWeight"]["values"][0]["value"] = "9.99"

    assert tuple(normalized) == EXPECTED_BASELINE_KEYS
    assert len(normalized) == 38
    assert normalized["ConfigComment"] == "Runtime baseline"
    assert normalized["FirstTurnValueWeight"]["values"][0]["value"] == "0.25"
    assert normalized["SecondTurnValueWeight"] == (
        FALLBACK_GLOBALVALUES_BASELINE["SecondTurnValueWeight"]
    )
    assert "RuntimeOnlyFullBaselineKey" not in normalized


@pytest.mark.parametrize(
    ("operation", "value", "expected_value"),
    [
        ("set", "0.75", "0.75"),
        ("increase", None, "0.93"),
    ],
)
def test_authorized_overlay_binds_operation_value_authority_and_claim_id(
    operation: str,
    value: str | None,
    expected_value: str,
) -> None:
    key = (
        "FirstTurnValueWeight"
        if operation == "set"
        else "GlobalMinionAttack"
    )
    row = _overlay_row(key=key, operation=operation, value=value)
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(authority_matrix=_overlay_matrix(row))
    )
    decision = next(item for item in ledger.decisions if item.key == key)

    assert decision.kind is GlobalValueDecisionKind.AUTHORIZED_OVERLAY
    assert json.loads(decision.emitted_canonical_json)["values"][0]["value"] == (
        expected_value
    )
    assert decision.authority_id == "step1_source_backed_posture"
    assert decision.claim_ids == ("lifecycle-posture",)
    assert decision.reason == "exact guide posture"


def test_production_compiler_uses_typed_ledger_emitted_values() -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    matrix = _overlay_matrix(
        _overlay_row(
            key="GlobalMinionAttack",
            operation="increase",
            value=None,
        )
    )
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(baseline=baseline, authority_matrix=matrix)
    )

    result = compile_globalvalues(
        baseline,
        {"global_values_authority_matrix": matrix},
        decision_ledger=ledger,
    )

    assert result["config"] == _parsed_emitted_values(ledger)
    assert result["config"]["GlobalMinionAttack"]["values"][0]["value"] == "0.93"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("", id="empty-string"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(None, id="null"),
        pytest.param(0, id="integer"),
        pytest.param(0.75, id="float"),
        pytest.param([], id="list"),
        pytest.param({}, id="mapping"),
    ],
)
def test_set_overlay_rejects_values_outside_nonempty_string_contract(
    value: object,
) -> None:
    row = _overlay_row()
    row["value"] = value

    with pytest.raises(
        ValueError,
        match="globalvalues_authority_overlay_value_invalid",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=_overlay_matrix(row))
        )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("True", id="true-literal"),
        pytest.param("False", id="false-literal"),
        pytest.param("-True", id="negated-true"),
        pytest.param("True + 1", id="true-plus-one"),
    ],
)
def test_set_overlay_rejects_boolean_numeric_expressions(value: str) -> None:
    row = _overlay_row(value=value)

    with pytest.raises(
        ValueError,
        match="globalvalues_authority_overlay_value_invalid",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=_overlay_matrix(row))
        )


def test_ledger_compiler_rejects_noop_overlay_contract_for_baseline_ledger() -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(baseline=baseline)
    )
    noop_overlay = _overlay_matrix(
        _overlay_row(
            key="FirstTurnValueWeight",
            operation="set",
            value="0",
        )
    )

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_ledger_authority_mismatch",
    ):
        compile_globalvalues(
            baseline,
            {"global_values_authority_matrix": noop_overlay},
            decision_ledger=ledger,
        )


def test_ledger_compiler_requires_explicit_authority_matrix() -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(baseline=baseline)
    )

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_ledger_authority_matrix_required",
    ):
        compile_globalvalues(
            baseline,
            {
                "aggression_profile": {
                    "global_value_overlays": {
                        "FirstTurnValueWeight": "set:0.75"
                    }
                }
            },
            decision_ledger=ledger,
        )


def test_ledger_compiler_rejects_baseline_contract_for_overlay_ledger() -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    overlay_matrix = _overlay_matrix(
        _overlay_row(
            key="FirstTurnValueWeight",
            operation="set",
            value="0.75",
        )
    )
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(
            baseline=baseline,
            authority_matrix=overlay_matrix,
        )
    )

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_ledger_authority_mismatch",
    ):
        compile_globalvalues(
            baseline,
            {"global_values_authority_matrix": _baseline_matrix()},
            decision_ledger=ledger,
        )


def test_dual_closure_consumes_the_typed_ledger_directly() -> None:
    ledger = build_globalvalues_decision_ledger(**_baseline_inputs())
    dispositions = DispositionLedger(
        deck_fingerprint=DECK_FINGERPRINT,
        cards=(),
        claims=(),
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=DECK_FINGERPRINT,
            cards=(),
            claims=(),
        ),
    )

    status = build_dual_closure(
        dispositions=dispositions,
        globalvalues_ledger=ledger,
        strategy_source_status="partial",
    )

    assert status.pre_run_contract_status == "complete"
    assert status.unresolved_reasons == ()


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_missing_or_extra_baseline_key_is_rejected(mutation: str) -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    if mutation == "missing":
        baseline.pop("GlobalTaunt")
    else:
        baseline["MyHeroPowerValue"] = {
            "values": [{"condition": "*", "value": "1.00"}]
        }

    with pytest.raises(ValueError, match="globalvalues_baseline_keys_invalid"):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(
                baseline=baseline,
                baseline_sha256="sha256:" + ("0" * 64),
            )
        )


def test_duplicate_overlay_key_is_rejected() -> None:
    row = _overlay_row()
    matrix = _overlay_matrix()
    matrix["allowed_step1_overlays"] = [row, deepcopy(row)]

    with pytest.raises(
        ValueError,
        match="globalvalues_authority_duplicate_overlay_key",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=matrix)
        )


def test_baseline_sentinel_cannot_be_mixed_with_overlay() -> None:
    matrix = _baseline_matrix()
    matrix["allowed_step1_overlays"].append(_overlay_row())

    with pytest.raises(
        ValueError,
        match="globalvalues_authority_baseline_sentinel_mixed",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=matrix)
        )


@pytest.mark.parametrize(
    ("field", "error"),
    [
        ("operation", "globalvalues_authority_overlay_operation_missing"),
        ("value", "globalvalues_authority_overlay_value_missing"),
        ("claim_id", "globalvalues_authority_overlay_claim_authority_missing"),
    ],
)
def test_overlay_requires_explicit_operation_value_and_lifecycle_claim(
    field: str,
    error: str,
) -> None:
    row = _overlay_row()
    row.pop(field)

    with pytest.raises(ValueError, match=error):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=_overlay_matrix(row))
        )


@pytest.mark.parametrize("key", ["MyHeroPowerValue", "MyWeaponValue"])
def test_overlay_for_nonbaseline_key_is_rejected(key: str) -> None:
    row = _overlay_row(key=key, operation="increase", value=None)

    with pytest.raises(
        ValueError,
        match="globalvalues_authority_overlay_key_not_baseline",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(authority_matrix=_overlay_matrix(row))
        )


def test_baseline_sha256_must_match_canonical_baseline() -> None:
    with pytest.raises(
        ValueError,
        match="globalvalues_baseline_sha256_invalid",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(baseline_sha256="sha256:" + ("0" * 64))
        )


def test_ledger_rejects_bad_content_digest() -> None:
    ledger = build_globalvalues_decision_ledger(**_baseline_inputs())

    with pytest.raises(
        ValueError,
        match="globalvalues_ledger_content_sha256_invalid",
    ):
        replace(ledger, content_sha256="sha256:" + ("0" * 64))


def test_ledger_rejects_row_fingerprint_mismatch() -> None:
    ledger = build_globalvalues_decision_ledger(**_baseline_inputs())

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_deck_fingerprint_mismatch",
    ):
        replace(ledger, deck_fingerprint="e" * 64)


def test_builder_rejects_invalid_deck_fingerprint() -> None:
    with pytest.raises(
        ValueError,
        match="globalvalues_deck_fingerprint_invalid",
    ):
        build_globalvalues_decision_ledger(
            **_baseline_inputs(deck_fingerprint="not-a-fingerprint")
        )


def test_mutating_inputs_after_build_does_not_mutate_ledger() -> None:
    baseline = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    matrix = _overlay_matrix()
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(baseline=baseline, authority_matrix=matrix)
    )
    before = globalvalues_decision_ledger_document(ledger)

    baseline["FirstTurnValueWeight"]["values"][0]["value"] = "999"
    matrix["allowed_step1_overlays"][0]["value"] = "999"
    matrix["allowed_step1_overlays"].clear()

    assert globalvalues_decision_ledger_document(ledger) == before


def test_report_serializes_canonical_bytes_as_parsed_json_values() -> None:
    ledger = build_globalvalues_decision_ledger(
        **_baseline_inputs(authority_matrix=_overlay_matrix())
    )

    document = globalvalues_decision_ledger_document(ledger)
    first_turn = next(
        row
        for row in document["decisions"]
        if row["key"] == "FirstTurnValueWeight"
    )

    assert document["deck_fingerprint"] == DECK_FINGERPRINT
    assert document["baseline_sha256"] == BASELINE_SHA256
    assert document["content_sha256"].startswith("sha256:")
    assert first_turn["kind"] == "authorized_overlay"
    assert first_turn["baseline"] == {
        "values": [{"condition": "*", "value": "0"}]
    }
    assert first_turn["emitted"] == {
        "values": [{"condition": "*", "value": "0.75"}]
    }
    assert first_turn["claim_ids"] == ["lifecycle-posture"]
