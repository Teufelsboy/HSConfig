from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from typing import Any

import pytest

import hsconfig.package_request as package_request
from hsconfig.commands.apply import apply_payload
from hsconfig.commands.runtime_match import runtime_match_payload
from hsconfig.configuration_mode import LLM_OPTIMIZED_START
from hsconfig.configure_models import ConfigureRequest
from hsconfig.configure_workflow import execute_configure
from hsconfig.package_derivation_receipt import (
    OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_installer import plan_runtime_install
from hsconfig.runtime_surface_ledger import (
    rederive_runtime_surface_ledger_from_package,
)
from hsconfig.visionai_registry import OPTIMIZED_START_REPORT_PATHS
from tests.helpers.package_byte_contract import (
    _offline_build_inputs,
    _offline_network_and_card_data,
)
from tests.starter_fixtures import (
    SHADOWPRIEST_DECK_CODE,
    SHADOWPRIEST_DECK_FINGERPRINT,
    SHADOWPRIEST_DECK_NAME,
    SHADOWPRIEST_HDT_DECK_ID,
    SHADOWPRIEST_HS_ID,
    ShadowPriestStarterFixture,
    build_shadowpriest_starter_fixture,
    write_invalid_selected_candidate_bundle,
)


_EXPECTED_CARD_COUNTS = {
    "CFM_637": 1,
    "DRG_056": 2,
    "DS1_233": 2,
    "GVG_009": 2,
    "NX2_019": 2,
    "REV_290": 2,
    "SCH_514": 2,
    "SW_444": 2,
    "SW_446": 2,
    "SW_448": 1,
    "TOY_381": 2,
    "TOY_518": 2,
    "VAC_419": 2,
    "VAC_512": 2,
    "WON_065": 2,
    "YOD_032": 2,
}
_EXPECTED_CANDIDATES = (
    ("candidate-1", "proactive_tempo", "FirstTurnValueWeight", "0.75"),
    ("candidate-2", "balanced", "SecondTurnValueWeight", "0.25"),
    ("candidate-3", "resource_oriented", "GlobalTaunt", "1.25"),
)
_EXPECTED_LINK = ("SW_448", "EX1_625t", "hero_power_transform")


def test_shadowpriest_optimized_start_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: any Task 1-8 seam can silently fall back to a blank,
    # unbound, unpublishable, or non-matchable ShadowPriest start.
    fixture = build_shadowpriest_starter_fixture(tmp_path / "starter")
    context = fixture.context.document.to_value()
    identity = context["deck_identity"]
    assert fixture.request.invocation.deck_code == SHADOWPRIEST_DECK_CODE
    assert identity == {
        "card_count_total": 30,
        "deck_code_sha256": (
            "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
        ),
        "deck_fingerprint": SHADOWPRIEST_DECK_FINGERPRINT,
        "deck_name": SHADOWPRIEST_DECK_NAME,
        "format": "FT_WILD",
        "hdt_deck_id": SHADOWPRIEST_HDT_DECK_ID,
        "hero_dbf_id": 813,
        "hs_id": SHADOWPRIEST_HS_ID,
        "unique_card_count": 16,
    }
    card_counts = {str(row["card_id"]): int(row["count"]) for row in context["cards"]}
    assert card_counts == _EXPECTED_CARD_COUNTS
    assert len(card_counts) == 16
    assert sum(card_counts.values()) == 30

    selection = fixture.selection
    assert len(selection.candidates) == 3
    assert len({row.runtime_intent_sha256 for row in selection.candidates}) == 3
    for candidate, expected in zip(
        selection.candidates,
        _EXPECTED_CANDIDATES,
        strict=True,
    ):
        candidate_id, role, changed_key, changed_value = expected
        value = candidate.document.to_value()
        assert (candidate.candidate_id, candidate.strategy_role) == (
            candidate_id,
            role,
        )
        assert value["mulligan"] == [
            {
                "action": "hold",
                "condition": "*",
                "rule_id": "keep-toy-518",
                "selector": "TOY_518",
                "selector_kind": "card",
            }
        ]
        assert value["card_rules"] == [
            {
                "behavior_block": "BeforeUseHeroPowerBonus",
                "condition": "*",
                "link_kind": "hero_power_transform",
                "rule_id": "darkbishop-mind-spike",
                "runtime_card_id": "EX1_625t",
                "source_card_id": "SW_448",
                "value": "12",
            }
        ]
        assert value["combo"] is None
        dispositions = {str(row["card_id"]): row for row in value["card_dispositions"]}
        assert set(dispositions) == set(_EXPECTED_CARD_COUNTS)
        assert len(dispositions) == 16
        assert {
            card_id
            for card_id, row in dispositions.items()
            if row["disposition"] == "configured"
        } == {"SW_448", "TOY_518"}
        assert all(
            row["disposition"] == "deliberately_unconfigured"
            for card_id, row in dispositions.items()
            if card_id not in {"SW_448", "TOY_518"}
        )
        assert value["globalvalues"][changed_key]["values"] == [
            {"condition": "*", "value": changed_value}
        ]
        assert value["rule_rationales"]
        assert value["assumptions"]

    critic = selection.decision.to_value()
    assert [row["candidate_id"] for row in critic["reviewed_candidates"]] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert critic["ranking"] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert critic["selected_candidate_id"] == "candidate-1"
    assert critic["critic_identity"] == {
        "confidence": "high",
        "kind": "independent_codex_agent",
        "review_id": "shadowpriest-independent-critic-1",
    }
    assert selection.selected is selection.candidates[0]

    _install_offline_resolver_seams(monkeypatch, fixture)
    _deck_cards, offline_cards, card_database = _offline_build_inputs()
    output_root = tmp_path / "published"
    runtime_root = tmp_path / "synthetic-runtime"
    request = _configure_request(
        output_root=output_root,
        runtime_root=runtime_root,
        decision_path=fixture.decision_path,
    )
    with _offline_network_and_card_data(offline_cards, card_database):
        result = execute_configure(request)

    assert result.status == "OK", result.materialized_summary()
    assert result.exit_code == 0
    assert result.published_output is not None
    assert result.package_model is not None
    assert result.configure_run_model is not None
    published = result.published_output
    package = published.package_root
    manifest = _read_json(package / "reports" / "input_manifest.json")
    deck_identity = _read_json(package / "reports" / "deck_identity.json")
    assert manifest["configuration_mode"] == LLM_OPTIMIZED_START
    assert manifest["deck_name"] == SHADOWPRIEST_DECK_NAME
    assert manifest["deck_code"] == SHADOWPRIEST_DECK_CODE
    assert manifest["deck_input_verification"] == {
        "normalized_roster_sha256": ("sha256:" + SHADOWPRIEST_DECK_FINGERPRINT),
        "runtime_apply_eligible": True,
        "status": "decoded_from_deck_code",
    }
    assert deck_identity["deck_fingerprint"] == SHADOWPRIEST_DECK_FINGERPRINT
    assert deck_identity["card_count_total"] == 30

    selected_digest = selection.selected.document.content_sha256
    decision_digest = selection.decision.content_sha256
    for relative_path in OPTIMIZED_START_REPORT_PATHS:
        source = fixture.decision_path.parent / Path(relative_path).name
        target = package / relative_path
        raw = target.read_bytes()
        assert raw == source.read_bytes()
        _assert_canonical_self_digest(raw)

    summary = result.materialized_summary()
    configure_selection = summary["optimized_start"]
    operator = _read_json(package / "reports" / "operator_summary.json")
    operator_derivation = operator["package_derivation"]
    assert configure_selection["selected_candidate_sha256"] == selected_digest
    assert configure_selection["decision_sha256"] == decision_digest
    assert operator_derivation["selected_candidate_sha256"] == selected_digest
    assert operator_derivation["decision_sha256"] == decision_digest
    assert operator["configuration_assurance"] == {
        "assurance": LLM_OPTIMIZED_START,
        "in_client_behavior": "not_proven_by_pre_run_contract",
        "load_safety": "validated",
        "optimality_claim_allowed": False,
        "runtime_gate_impact": "none",
        "semantic_closure": "closed",
        "source_authority": "exact",
    }

    receipt_path = package / "package_derivation_receipt.json"
    receipt_raw = receipt_path.read_bytes()
    receipt = json.loads(receipt_raw)
    assert receipt["schema_version"] == OPTIMIZED_DERIVATION_RECEIPT_SCHEMA_VERSION == 3
    assert operator_derivation["receipt_sha256"] == (
        "sha256:" + sha256(receipt_raw).hexdigest()
    )
    for relative_path in OPTIMIZED_START_REPORT_PATHS:
        report_raw = (package / relative_path).read_bytes()
        assert receipt["inputs"][relative_path] == (
            "sha256:" + sha256(report_raw).hexdigest()
        )

    config_dir = next(
        path for path in (package / "CustomConfig").iterdir() if path.is_dir()
    )
    assert config_dir.name == "shadowpriest"
    globalvalues = _read_json(config_dir / "GlobalValues.json")
    baseline = context["globalvalues_baseline"]["values"]
    assert len(globalvalues) == 38
    assert set(globalvalues) == set(baseline)
    assert globalvalues != baseline
    assert globalvalues["FirstTurnValueWeight"]["values"] == [
        {"condition": "*", "value": "0.75"}
    ]
    mulligan = _read_json(config_dir / "Mulligan.json")
    assert mulligan["Mulligan"]["values"][0] | {"comment": "ignored"} == {
        "comment": "ignored",
        "condition": "*",
        "mulligan": "TOY_518",
        "value": "hold",
    }
    assert not (config_dir / "Combo.json").exists()
    mind_spike = _read_json(config_dir / "EX1_625t.json")
    assert mind_spike["GameCardId"] == "EX1_625t"
    assert mind_spike["BeforeUseHeroPowerBonus"]["values"][0] | {
        "comment": "ignored"
    } == {
        "comment": "ignored",
        "condition": "*",
        "value": "12",
    }
    darkbishop = _read_json(config_dir / "SW_448.json")
    assert "BeforeUseHeroPowerBonus" not in darkbishop

    behavior = _read_json(package / "reports" / "card_behavior_plan_report.json")
    behavior_row = behavior["rows"][0]
    ownership = _read_json(package / "reports" / "output_ownership_manifest.json")
    ownership_row = ownership["runtime_entity_ownership"][0]
    ledger_path = package / "reports" / "runtime_surface_ledger.json"
    ledger = _read_json(ledger_path)
    rederived_ledger = rederive_runtime_surface_ledger_from_package(package)
    assert ledger == rederived_ledger
    ledger_row = ledger["linked_runtime_entities"]["EX1_625t"]
    receipt_owner = receipt["linked_runtime_owners"][0]
    assert {
        (
            behavior_row["source_card_id"],
            behavior_row["runtime_card_id"],
            behavior_row["link_kind"],
        ),
        (
            ownership_row["source_card_id"],
            ownership_row["runtime_card_id"],
            ownership_row["link_kind"],
        ),
        (
            ledger_row["source_card_id"],
            ledger_row["runtime_card_id"],
            ledger_row["link_kind"],
        ),
        (
            receipt_owner["source_card_id"],
            receipt_owner["runtime_card_id"],
            receipt_owner["link_kind"],
        ),
    } == {_EXPECTED_LINK}
    assert behavior_row["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert behavior_row["claim_id"] == (
        f"starter:{selected_digest}:candidate-1:darkbishop-mind-spike"
    )
    assert receipt_owner["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert ledger_row["runtime_emitted"] is True
    assert ledger["cardid"]["card_ids"] == ["EX1_625t"]
    assert ledger["mulligan"]["card_ids"] == ["TOY_518"]
    assert ledger["globalvalues"]["changed_keys"] == ["FirstTurnValueWeight"]
    assert (
        operator["config_usefulness"]["surface_ledger_sha256"]
        == ledger["surface_ledger_sha256"]
    )

    runtime_before_fake = _tree_bytes(runtime_root)
    fake_apply, fake_status = apply_payload(
        SimpleNamespace(
            package=str(output_root),
            runtime_root=str(runtime_root),
            fake=True,
            from_fake_receipt=None,
            allow_source_informed=False,
            immutable_package=True,
            json=True,
        )
    )
    assert fake_status == 0
    assert fake_apply["status"] == "fake_apply_ready"
    assert fake_apply["receipt"]["runtime_write_performed"] is False
    assert runtime_before_fake is None
    assert _tree_bytes(runtime_root) is None

    runtime_root.mkdir()
    install_plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    runtime_config = runtime_root / "CustomConfig" / install_plan.versioned_config_dir
    runtime_config.parent.mkdir()
    shutil.copytree(
        package / "CustomConfig" / install_plan.logical_config_dir,
        runtime_config,
    )
    (runtime_root / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\n{SHADOWPRIEST_DECK_NAME}={install_plan.versioned_config_dir}\n",
        encoding="utf-8",
    )
    runtime_match, runtime_match_status = runtime_match_payload(
        SimpleNamespace(
            package=str(output_root),
            runtime_root=str(runtime_root),
            config_dir=None,
        )
    )
    assert runtime_match_status == 0
    assert runtime_match["status"] == "matched"
    assert runtime_match["runtime_write_performed"] is False
    assert runtime_match["logical_config_dir"] == "shadowpriest"
    assert runtime_match["runtime_config_dir"] == install_plan.versioned_config_dir
    assert runtime_match["publication_content_root_sha256"] == (
        published.content_root_sha256
    )

    output_before_invalid = _tree_bytes(output_root)
    runtime_before_invalid = _tree_bytes(runtime_root)
    invalid_decision_path = write_invalid_selected_candidate_bundle(
        tmp_path / "invalid-starter",
        fixture,
    )
    invalid_request = _configure_request(
        output_root=output_root,
        runtime_root=runtime_root,
        decision_path=invalid_decision_path,
    )
    with _offline_network_and_card_data(offline_cards, card_database):
        invalid_result = execute_configure(invalid_request)

    assert invalid_result.status == "failed"
    assert invalid_result.exit_code == 1
    assert invalid_result.published_output is None
    assert invalid_result.package_model is None
    assert invalid_result.configure_run_model is None
    assert "starter_candidate" in " ".join(
        invalid_result.materialized_summary()["errors"]
    )
    assert _tree_bytes(output_root) == output_before_invalid
    assert _tree_bytes(runtime_root) == runtime_before_invalid


def _install_offline_resolver_seams(
    monkeypatch: pytest.MonkeyPatch,
    fixture: ShadowPriestStarterFixture,
) -> None:
    request = fixture.request
    preconfig = request.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = request.acquisition_closure_input.to_value()
    monkeypatch.setattr(
        package_request,
        "build_preconfig_context",
        lambda *_args, **_kwargs: preconfig,
    )
    monkeypatch.setattr(
        package_request,
        "load_globalvalues_baseline",
        lambda _runtime_root: baseline_receipt,
    )
    monkeypatch.setattr(
        package_request,
        "_matching_strict_context",
        lambda **_kwargs: request.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def _configure_request(
    *,
    output_root: Path,
    runtime_root: Path,
    decision_path: Path,
) -> ConfigureRequest:
    return ConfigureRequest(
        deck_name=SHADOWPRIEST_DECK_NAME,
        deck_code=SHADOWPRIEST_DECK_CODE,
        output_root=output_root,
        runtime_root=runtime_root,
        apply_requested=False,
        current_date=date(2026, 7, 29),
        source_urls=(),
        online_source=False,
        auto_source=False,
        source_evidence_json=None,
        source_search_results_json=None,
        cards_json=None,
        collectible_cards_json=None,
        full_cards_json=None,
        source_fixture_url_map_json=None,
        source_fetch_timeout_seconds=6.0,
        allow_placeholder=False,
        json_output=True,
        optimized_start=True,
        starter_decision_json=decision_path,
    )


def _assert_canonical_self_digest(raw: bytes) -> None:
    frozen = FrozenJsonDocument.from_json_bytes(raw)
    assert frozen.canonical_json == raw
    value = frozen.to_value()
    claimed = value.pop("content_sha256")
    unsigned = FrozenJsonDocument.from_value(value).canonical_json
    assert claimed == "sha256:" + sha256(unsigned).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _tree_bytes(root: Path) -> dict[str, bytes] | None:
    if not root.exists():
        return None
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
