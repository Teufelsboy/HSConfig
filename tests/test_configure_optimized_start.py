from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

import hsconfig.package_request as package_request
from hsconfig.configuration_mode import (
    CONSERVATIVE,
    LLM_OPTIMIZED_START,
    configuration_mode_from_manifest,
)
from hsconfig.package_compiler import compile_package
from hsconfig.package_request import (
    PackageInvocation,
    PackageResolutionSnapshot,
    ResolvedPackageRequest,
    resolve_package_request,
)
from hsconfig.starter_context import StarterContext, build_starter_context
from hsconfig.starter_decision import load_validated_starter_selection
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_1_FILENAME,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CONTEXT_FIELDS,
    STARTER_DECISION_FIELDS,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.visionai_registry import OPTIMIZED_START_REPORT_PATHS
from tests.helpers.audited_package_request import audited_request
from tests.test_starter_decision import (
    three_candidates,
    write_selection_bundle,
)


def test_manifest_configuration_mode_is_strict_and_legacy_compatible() -> None:
    assert configuration_mode_from_manifest({}) == CONSERVATIVE
    assert configuration_mode_from_manifest(
        {"configuration_mode": CONSERVATIVE}
    ) == CONSERVATIVE
    assert configuration_mode_from_manifest(
        {"configuration_mode": LLM_OPTIMIZED_START}
    ) == LLM_OPTIMIZED_START
    for value in (None, 0, False, "unknown"):
        with pytest.raises(ValueError, match="configuration_mode_invalid"):
            configuration_mode_from_manifest({"configuration_mode": value})


def test_optimized_request_requires_one_frozen_validated_selection(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    assert conservative.invocation.configuration_mode == CONSERVATIVE
    assert conservative.starter_selection is None

    optimized_invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    with pytest.raises(ValueError, match="starter_selection_required"):
        replace(conservative, invocation=optimized_invocation)

    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    optimized = replace(
        conservative,
        invocation=optimized_invocation,
        starter_selection=selection,
    )
    selected_bytes = optimized.starter_selection.selected.document.canonical_json
    (decision_path.parent / STARTER_CANDIDATE_1_FILENAME).write_bytes(b"{}")
    assert optimized.starter_selection.selected.document.canonical_json == selected_bytes
    manifest = next(
        projection.document.to_value()
        for projection in compile_package(optimized).json_projections
        if projection.relative_path == "reports/input_manifest.json"
    )
    assert manifest["configuration_mode"] == LLM_OPTIMIZED_START

    changed_preconfig = deepcopy(
        conservative.snapshot.general_preconfig.to_value()
    )
    changed_preconfig["card_metadata"]["cards"][0]["text"] += " changed"
    with pytest.raises(ValueError, match="starter_context_mismatch"):
        replace(
            optimized,
            snapshot=PackageResolutionSnapshot.from_preconfig(
                changed_preconfig
            ),
        )

    with pytest.raises(ValueError, match="configuration_mode_invalid"):
        replace(
            conservative,
            invocation=replace(
                conservative.invocation,
                configuration_mode="UNRECOGNIZED",
            ),
        )


def test_optimized_request_reseals_every_public_selection_claim(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    reviewed_mismatch = selection.decision.to_value()
    del reviewed_mismatch["content_sha256"]
    reviewed_mismatch["reviewed_candidates"][0]["content_sha256"] = (
        "sha256:" + "0" * 64
    )
    forged_decision = seal_starter_document(
        reviewed_mismatch,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    forged_document_candidate = replace(
        selection.candidates[0],
        document=selection.candidates[1].document,
    )
    forged_runtime_candidate = replace(
        selection.candidates[0],
        runtime_intent_sha256="sha256:" + "0" * 64,
    )
    forged_selections = (
        replace(selection, selected=selection.candidates[1]),
        replace(selection, decision=forged_decision),
        replace(
            selection,
            candidates=(
                forged_document_candidate,
                *selection.candidates[1:],
            ),
            selected=forged_document_candidate,
        ),
        replace(
            selection,
            candidates=(
                forged_runtime_candidate,
                *selection.candidates[1:],
            ),
            selected=forged_runtime_candidate,
        ),
    )

    for forged in forged_selections:
        with pytest.raises(ValueError, match="^starter_selection_invalid$"):
            replace(
                conservative,
                invocation=invocation,
                starter_selection=forged,
            )


def test_optimized_request_reseals_decision_document_authority(
    tmp_path: Path,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    invocation = replace(
        conservative.invocation,
        configuration_mode=LLM_OPTIMIZED_START,
    )
    zero_digest = "sha256:" + "0" * 64
    embedded_digest_mismatch = selection.decision.to_value()
    embedded_digest_mismatch["content_sha256"] = zero_digest
    forged_canonical_decision = StarterDocument(
        document=FrozenJsonDocument.from_value(embedded_digest_mismatch),
        content_sha256=zero_digest,
    )
    forged_decisions = (
        object(),
        replace(selection.decision, content_sha256=zero_digest),
        forged_canonical_decision,
    )

    for decision in forged_decisions:
        with pytest.raises(ValueError, match="^starter_selection_invalid$"):
            replace(
                conservative,
                invocation=invocation,
                starter_selection=replace(selection, decision=decision),
            )


def test_resolver_normalizes_decision_context_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
        mutate_decision=lambda draft: draft.__setitem__(
            "starter_context_sha256",
            "sha256:" + "0" * 64,
        ),
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
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
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )

    with pytest.raises(ValueError, match="^starter_context_mismatch$"):
        resolve_package_request(
            SimpleNamespace(
                deck_name="ShadowPriest",
                deck_code=conservative.invocation.deck_code,
                runtime_root=conservative.invocation.runtime_root,
                optimized_start=True,
                starter_decision_json=decision_path,
            ),
            current_date=date(2026, 8, 19),
            fetch_latest_cards_fn=lambda: [],
            research_required_guide_sources_fn=lambda **_kwargs: {},
        )


def test_resolver_normalizes_candidate_context_digest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    conservative = audited_request(tmp_path / "conservative", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    candidates = three_candidates(context)
    candidate_value = candidates[0].to_value()
    del candidate_value["content_sha256"]
    candidate_value["starter_context_sha256"] = "sha256:" + "0" * 64
    candidates[0] = seal_starter_document(
        candidate_value,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        candidates,
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
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
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )

    with pytest.raises(ValueError, match="^starter_context_mismatch$"):
        resolve_package_request(
            SimpleNamespace(
                deck_name="ShadowPriest",
                deck_code=conservative.invocation.deck_code,
                runtime_root=conservative.invocation.runtime_root,
                optimized_start=True,
                starter_decision_json=decision_path,
            ),
            current_date=date(2026, 8, 19),
            fetch_latest_cards_fn=lambda: [],
            research_required_guide_sources_fn=lambda **_kwargs: {},
        )


def test_configure_cli_rejects_unpaired_optimized_start_values(
    tmp_path: Path,
) -> None:
    invocation = PackageInvocation(
        deck_code="fixture-code",
        runtime_root=str(tmp_path / "runtime"),
        cards_json=None,
        claims_json=None,
        guide_sources_json=None,
        plan_reports_dir=None,
        target_config_mode="preview",
        include_disposition_diagnostics=False,
    )
    assert invocation.configuration_mode == CONSERVATIVE
    assert ResolvedPackageRequest is not None
    for optimized_start, decision_path, error in (
        (True, None, "starter_decision_required"),
        (False, tmp_path / "starter_config_decision.json", "starter_decision_not_enabled"),
    ):
        with pytest.raises(ValueError, match=error):
            resolve_package_request(
                SimpleNamespace(
                    optimized_start=optimized_start,
                    starter_decision_json=decision_path,
                ),
                current_date=date(2026, 8, 19),
                fetch_latest_cards_fn=lambda: [],
                research_required_guide_sources_fn=lambda **_kwargs: {},
            )


def test_optimized_configure_summary_binds_selected_candidate(
    tmp_path: Path,
) -> None:
    from hsconfig.configure_workflow import _optimized_start_configure_summary
    from hsconfig.io import read_json, write_json

    conservative = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    package = tmp_path / "04_package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"configuration_mode": "LLM_OPTIMIZED_START"},
    )
    source_root = decision_path.parent
    for filename in (
        "starter_context.json",
        "candidate-1.json",
        "candidate-2.json",
        "candidate-3.json",
        "starter_config_decision.json",
    ):
        target = package / "reports" / "optimized_start" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source_root / filename).read_bytes())

    selected = _optimized_start_configure_summary(package)
    decision = selected["optimized_start"]

    assert decision["status"] == "selected"
    assert decision["candidate_ids"] == [
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert decision["selected_candidate_id"] == "candidate-1"
    assert decision["selection_rationale"] == (
        "The first candidate has the clearest bounded pressure plan."
    )
    assert decision["mulligan_summary"]["rule_count"] == 1
    assert decision["changed_globalvalues"] == ["FirstTurnValueWeight"]
    assert decision["per_card_rules"][0]["runtime_card_id"] == "EX1_625t"
    assert decision["combo_summary"] == {"configured": False, "rule": None}
    assert decision["risks"] == ["No gameplay outcome is claimed."]
    assert decision["next_report_path"] == "reports/operator_summary.json"

    low_decision_path = package / "reports" / "optimized_start" / (
        "starter_config_decision.json"
    )
    low_decision = read_json(low_decision_path)
    del low_decision["content_sha256"]
    low_decision["critic_identity"]["confidence"] = "low"
    resealed = seal_starter_document(
        low_decision,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    low_decision_path.write_bytes(resealed.canonical_json)
    assert _optimized_start_configure_summary(package)["optimized_start"][
        "status"
    ] == "low_confidence"


@pytest.mark.parametrize(
    "defect",
    (
        "blank_candidate_id",
        "blank_selection_rationale",
        "invalid_risks",
        "invalid_critic_identity",
        "duplicate_strategy_role",
        "reviewed_candidate_digest_mismatch",
        "candidate_context_mismatch",
    ),
)
def test_optimized_configure_summary_rejects_self_sealed_semantic_bundle_defects(
    tmp_path: Path,
    defect: str,
) -> None:
    from hsconfig.configure_workflow import _optimized_start_configure_summary
    from hsconfig.io import read_json, write_json

    conservative = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    package = tmp_path / "04_package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"configuration_mode": "LLM_OPTIMIZED_START"},
    )
    optimized = package / "reports" / "optimized_start"
    for filename in (
        "starter_context.json",
        "candidate-1.json",
        "candidate-2.json",
        "candidate-3.json",
        "starter_config_decision.json",
    ):
        target = optimized / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((decision_path.parent / filename).read_bytes())

    candidate_path = optimized / "candidate-1.json"
    decision_path = optimized / "starter_config_decision.json"
    candidate = read_json(candidate_path)
    decision = read_json(decision_path)
    del candidate["content_sha256"]
    del decision["content_sha256"]

    if defect == "blank_candidate_id":
        candidate["candidate_id"] = ""
    elif defect == "blank_selection_rationale":
        decision["selection_rationale"] = ""
    elif defect == "invalid_risks":
        decision["risks"] = [{"not": "critic text"}]
    elif defect == "invalid_critic_identity":
        decision["critic_identity"]["kind"] = "self_review"
    elif defect == "duplicate_strategy_role":
        candidate["strategy_summary"]["role"] = "balanced"
    elif defect == "reviewed_candidate_digest_mismatch":
        decision["reviewed_candidates"][0]["content_sha256"] = (
            "sha256:" + "0" * 64
        )
    elif defect == "candidate_context_mismatch":
        candidate["starter_context_sha256"] = "sha256:" + "0" * 64
    else:
        raise AssertionError(f"unknown_test_defect:{defect}")

    if defect in {
        "blank_candidate_id",
        "duplicate_strategy_role",
        "candidate_context_mismatch",
    }:
        resealed_candidate = seal_starter_document(
            candidate,
            expected_fields=STARTER_CANDIDATE_FIELDS,
            schema_version=STARTER_SCHEMA_VERSION,
        )
        candidate_path.write_bytes(resealed_candidate.canonical_json)
        if defect == "blank_candidate_id":
            decision["reviewed_candidates"][0]["candidate_id"] = ""
            decision["ranking"][0] = ""
            decision["selected_candidate_id"] = ""
        decision["reviewed_candidates"][0]["content_sha256"] = (
            resealed_candidate.content_sha256
        )

    resealed_decision = seal_starter_document(
        decision,
        expected_fields=STARTER_DECISION_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    decision_path.write_bytes(resealed_decision.canonical_json)

    with pytest.raises(
        ValueError,
        match="^optimized_start_summary_invalid$",
    ):
        _optimized_start_configure_summary(package)


def _write_fully_rebound_invalid_context_bundle(
    root: Path,
    context: StarterContext,
) -> tuple[StarterContext, Path]:
    context_value = context.document.to_value()
    del context_value["content_sha256"]
    context_value["source_evidence"] = "invalid"
    rebound_document = seal_starter_document(
        context_value,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    rebound_context = StarterContext(
        document=rebound_document,
        deck_fingerprint=context.deck_fingerprint,
        globalvalues_baseline_sha256=(
            context.globalvalues_baseline_sha256
        ),
    )
    return rebound_context, write_selection_bundle(
        root,
        rebound_context,
        three_candidates(rebound_context),
    )


def test_optimized_configure_summary_rejects_fully_rebound_invalid_context(
    tmp_path: Path,
) -> None:
    from hsconfig.configure_workflow import _optimized_start_configure_summary
    from hsconfig.io import write_json

    conservative = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    _rebound_context, decision_path = (
        _write_fully_rebound_invalid_context_bundle(
            tmp_path / "selection",
            context,
        )
    )
    package = tmp_path / "04_package"
    write_json(
        package / "reports" / "input_manifest.json",
        {"configuration_mode": "LLM_OPTIMIZED_START"},
    )
    for filename in (
        "starter_context.json",
        "candidate-1.json",
        "candidate-2.json",
        "candidate-3.json",
        "starter_config_decision.json",
    ):
        target = package / "reports" / "optimized_start" / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((decision_path.parent / filename).read_bytes())

    with pytest.raises(
        ValueError,
        match="^optimized_start_summary_invalid$",
    ):
        _optimized_start_configure_summary(package)


def test_execute_configure_rejects_rebound_invalid_context_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.configure_models import ConfigureRequest
    from hsconfig.configure_workflow import execute_configure
    from tests.helpers.package_byte_contract import (
        _offline_build_inputs,
        _offline_network_and_card_data,
    )

    conservative = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    rebound_context, decision_path = (
        _write_fully_rebound_invalid_context_bundle(
            tmp_path / "selection",
            context,
        )
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
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
        lambda **_kwargs: conservative.snapshot.strict_build_context,
    )
    monkeypatch.setattr(
        package_request,
        "build_source_acquisition_closure_report",
        lambda **_kwargs: {"acquisition_closure": closure},
    )
    monkeypatch.setattr(
        "hsconfig.starter_context.build_starter_context",
        lambda _snapshot: rebound_context,
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )
    _deck_cards, offline_cards, card_database = _offline_build_inputs()
    output_root = tmp_path / "configure-output"
    runtime_root = tmp_path / "runtime"
    request = ConfigureRequest(
        deck_name="ShadowPriest",
        deck_code=conservative.invocation.deck_code,
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

    with _offline_network_and_card_data(offline_cards, card_database):
        result = execute_configure(request)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.summary["errors"] == (
        "optimized_start_summary_invalid",
    )
    assert result.published_output is None
    assert result.package_model is None
    assert result.configure_run_model is None
    assert not (output_root / "current.json").exists()
    assert not (output_root / "revisions").exists()
    assert not runtime_root.exists()


def test_execute_configure_publishes_real_valid_optimized_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hsconfig.configure_models import ConfigureRequest
    from hsconfig.configure_workflow import execute_configure
    from tests.helpers.package_byte_contract import (
        _offline_build_inputs,
        _offline_network_and_card_data,
    )

    conservative = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)
    decision_path = write_selection_bundle(
        tmp_path / "selection",
        context,
        three_candidates(context),
    )
    preconfig = conservative.snapshot.general_preconfig.to_value()
    baseline_receipt = preconfig["globalvalues_baseline_receipt"]
    closure = conservative.acquisition_closure_input.to_value()
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
        lambda **_kwargs: conservative.snapshot.strict_build_context,
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
    _deck_cards, offline_cards, card_database = _offline_build_inputs()
    output_root = tmp_path / "configure-output"
    runtime_root = tmp_path / "runtime"
    request = ConfigureRequest(
        deck_name="ShadowPriest",
        deck_code=conservative.invocation.deck_code,
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

    with _offline_network_and_card_data(offline_cards, card_database):
        result = execute_configure(request)

    assert result.status == "OK", result.summary
    assert result.exit_code == 0
    assert result.published_output is not None
    package_root = result.published_output.package_root
    assert (output_root / "current.json").is_file()
    assert result.published_output.revision_root.is_dir()
    for relative_path in OPTIMIZED_START_REPORT_PATHS:
        assert (package_root / relative_path).read_bytes() == (
            decision_path.parent / Path(relative_path).name
        ).read_bytes()
    assert not runtime_root.exists()
