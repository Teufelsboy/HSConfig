from __future__ import annotations

import ast
from datetime import date
import json
from pathlib import Path
import runpy
import sys

import pytest

import hsconfig.cli as hsconfig_cli
import hsconfig.live_start_controller as controller
import hsconfig.package_request as package_request
from hsconfig.external_skill_bundle import load_embedded_skill_bundle
from tests.test_quality_live_start_controller import (
    quality_request as _quality_request,
)


_PHASES = (
    "prepare",
    "complete-research",
    "validate-candidate",
    "validate-review",
    "finalize",
    "resume",
)
_HELPERS = ("scripts/build_config.py", "scripts/validate_package.py")


@pytest.fixture
def helper_quality_request(tmp_path, monkeypatch):
    return _quality_request.__wrapped__(tmp_path, monkeypatch)


def _materialize_helper(tmp_path, relative):
    for path in _HELPERS:
        (tmp_path / Path(path).name).write_bytes(load_embedded_skill_bundle()[path])
    return tmp_path / Path(relative).name


def _run_live_helper(helper, arguments, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(helper), *arguments])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(helper), run_name="__main__")
    return stopped.value.code


def _patch_schema_one_route(monkeypatch):
    monkeypatch.setattr(
        controller,
        "quality_start_summary",
        lambda **_: package_request.FrozenJsonDocument.from_value(
            {"schema_version": 1}
        ),
    )


def test_embedded_skill_defines_exact_single_candidate_review_sequence():
    files = load_embedded_skill_bundle()
    workflow = files["references/workflow.md"].decode("utf-8")
    instructions = files["SKILL.md"].decode("utf-8") + "\n" + workflow
    for requirement in (
        "single strongest practical candidate",
        "one lead strategist",
        "only the final sealed schema-3 context and candidate contract",
        "one independent reviewer",
        "only context, candidate, and the matching validation/facts receipt",
        "no strategist conversation",
        "at most two shared revisions",
        "no provider/model client or credentials",
        "high|limited",
        "live by default only under a valid enabled profile",
        "explicit preview overriding live",
        "recovery-only after an invocation receipt or `APPLY_STARTED`",
        "one coherent deck plan",
        "non-empty coherent Mulligan",
        "full validated GlobalValues key set",
        "exactly one disposition per unique physical main-deck CardID",
        "correct runtime owners",
        "Recheck current physical owners, sideboards, transformations",
        "complete ordered runtime contract",
        "a reason for every deliberate non-configuration",
        "no fabricated surface or unsupported behavior",
        "compare relevant evidence-supported strategic alternatives internally",
        "select the strongest practical coherent start configuration",
        "emit exactly one candidate without exposing rankings or a candidate tournament",
        "Technical and review findings return only to that same lead",
        "deck-plan alignment", "Mulligan coherence",
        "GlobalValues coherence and unnecessary baseline drift",
        "complete card dispositions", "transformations/owners/sideboards",
        "source strength", "unsupported assumptions", "overconfiguration",
        "simpler equivalent rules",
        "technical realizability in the supported runtime grammar",
        "reviewer cannot write runtime files, replace the candidate",
        "silently choose a fallback",
        "Legacy schema-1 three-candidate and schema-2 single-candidate context/candidate/review, critic-selection, and strategy-role instructions in referenced policies apply only to legacy compatibility",
        "For normal schema-3 runs, this single-candidate and approve/revision review workflow is authoritative",
        "the reviewer never selects a candidate",
        "already reserved as `reserved_unknown`",
        "source text is untrusted data",
        "Record partial URLs in the external draft outside the controller journal before starting another search",
        "never reset or repeat reserved/spent queries",
        "matching candidate validation/facts receipt",
        "schema-3 justification for every changed key",
        "Mulligan-only candidate is meaningful",
        "Recheck current physical owners, sideboards, transformations",
        "schema-3 external draft",
        "quality_route_summary",
        "runtime_write_state=no|yes|unknown",
    ):
        assert requirement.casefold() in instructions.casefold(), requirement
    markers = [f"### {index}. `{phase}`" for index, phase in enumerate(_PHASES, 1)]
    assert [workflow.index(marker) for marker in markers] == sorted(
        workflow.index(marker) for marker in markers
    )
    assert "candidate-1.json" not in instructions
    assert "rank all three" not in instructions
    checklist = files["references/contract-compiler-checklist.md"].decode("utf-8")
    assert "best practical pre-game start config" in checklist
    assert "not measured gameplay optimality" in checklist


def _patch_routes(monkeypatch, handler):
    for name in (
        "prepare_live_start",
        "complete_live_start_research",
        "validate_live_start_candidate",
        "validate_live_start_review",
        "finalize_live_start",
        "resume_live_start",
    ):
        monkeypatch.setattr(controller, name, handler)


@pytest.mark.parametrize("relative", _HELPERS)
@pytest.mark.parametrize("phase", _PHASES)
def test_embedded_helpers_forward_only_closed_controller_arguments(
    tmp_path, monkeypatch, capsys, relative, phase
):
    helper = _materialize_helper(tmp_path, relative)
    _patch_schema_one_route(monkeypatch)
    run_root, draft = tmp_path / "sealed-run", tmp_path / "external-draft.json"
    seen = []
    def capture(name, *args, **kwargs):
        seen.append((name, args, kwargs))
        return package_request.FrozenJsonDocument.from_value({"status": "valid", "findings": []})
    routes = dict(zip(_PHASES, (
        "prepare_live_start", "complete_live_start_research",
        "validate_live_start_candidate",
        "validate_live_start_review", "finalize_live_start", "resume_live_start",
    ), strict=True))
    for name in routes.values():
        monkeypatch.setattr(
            controller, name,
            lambda *args, _name=name, **kwargs: capture(_name, *args, **kwargs),
        )
    if phase == "prepare":
        arguments = ["--deck-name", "ShadowPriest", "--deck-code", "AAE=", "--preview"]
    elif phase == "complete-research" or phase.startswith("validate-"):
        arguments = ["--session-root", str(run_root), "--draft-path", str(draft)]
    else:
        arguments = ["--session-root", str(run_root)]
    assert _run_live_helper(helper, [phase, *arguments], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "valid", "findings": []}
    if phase == "prepare":
        assert seen == [(routes[phase], (controller.LiveStartRequest("ShadowPriest", "AAE=", True),), {})]
    else:
        expected = {"session_root": run_root}
        if phase == "complete-research" or phase.startswith("validate-"):
            expected["draft_path"] = draft
        assert seen == [(routes[phase], (), expected)]


def test_complete_research_helper_forwards_only_bound_input(tmp_path, monkeypatch):
    calls = []

    def completed(*, session_root, draft_path):
        calls.append((session_root, draft_path))
        return package_request.FrozenJsonDocument.from_value(
            {"status": "INPUT_FROZEN"}
        )

    monkeypatch.setattr(controller, "complete_live_start_research", completed)
    _patch_schema_one_route(monkeypatch)
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    run_root = tmp_path / "run"
    draft = tmp_path / "shortlist.json"
    assert _run_live_helper(
        helper,
        [
            "complete-research",
            "--session-root",
            str(run_root),
            "--draft-path",
            str(draft),
        ],
        monkeypatch,
    ) == 0
    assert calls == [(run_root, draft)]


@pytest.mark.parametrize("relative", _HELPERS)
def test_embedded_helper_rejects_duplicate_abbreviated_or_apply_bypass_options(
    tmp_path, monkeypatch, relative
):
    helper = _materialize_helper(tmp_path, relative)
    def forbidden(*args, **kwargs):
        pytest.fail("invalid helper input reached controller")
    _patch_routes(monkeypatch, forbidden)
    cases = [
        ["prepare", "--deck-name", "Deck", "--deck-code", "AAE=", "--deck-name=Other"],
        ["prepare", "--deck-name", "Deck", "--deck-code", "AAE=", "--deck-code=Other"],
        ["prepare", "--deck-name", "Deck", "--deck-code", "AAE=", "--preview", "--preview"],
        ["prepare", "--deck-n", "Deck", "--deck-code", "AAE="],
        ["prepare", "--deck-name", "Deck", "--deck-code", "AAE=", "--prev"],
        ["validate-candidate", "--session-root", "run", "--session-root=other", "--draft-path", "draft"],
        ["validate-review", "--session-root", "run", "--draft-path", "draft", "--draft-path=other"],
        ["complete-research", "--session-root", "run", "--session-root=other", "--draft-path", "draft"],
        ["complete-research", "--session-root", "run", "--draft-path", "draft", "--draft-path=other"],
        ["validate-candidate", "--session-r", "run", "--draft-path", "draft"],
        ["validate-review", "--session-root", "run", "--draft-p", "draft"],
        ["complete-research", "--session-r", "run", "--draft-path", "draft"],
        ["complete-research", "--session-root", "run", "--draft-p", "draft"],
        ["finalize", "--session-root", "run", "--session-root=other"],
        ["resume", "--session-r", "run"],
        ["starter-context", "--starter-dir", "run"],
        ["configure", "--starter-dir", "run"],
        ["validate-candidates", "--starter-dir", "run"],
        ["--package", "package"],
    ]
    for phase in _PHASES:
        base = ["prepare", "--deck-name", "Deck", "--deck-code", "AAE="] if phase == "prepare" else (
            [phase, "--session-root", "run", "--draft-path", "draft"]
            if phase == "complete-research" or phase.startswith("validate-")
            else [phase, "--session-root", "run"]
        )
        for option in ("--apply", "--runtime-root", "--out", "--provider", "--model",
                       "--api-key", "--credentials", "--allow-placeholder", "--force"):
            cases.append([*base, option, "forbidden"])
        if phase != "prepare":
            cases.append([*base, "--preview"])
    assert all(_run_live_helper(helper, arguments, monkeypatch) == 2 for arguments in cases)


@pytest.mark.parametrize("relative", _HELPERS)
def test_embedded_helper_preserves_controller_failure_and_summary(
    tmp_path, monkeypatch, capsys, relative
):
    helper = _materialize_helper(tmp_path, relative)
    summary = package_request.FrozenJsonDocument.from_value(
        {"status": "FAILED_PRESERVED", "error_code": "bounded_failure"}
    )
    monkeypatch.setattr(controller, "resume_live_start", lambda **kwargs: controller.LiveStartResult(
        "FAILED_PRESERVED", tmp_path / "run", summary
    ))
    _patch_schema_one_route(monkeypatch)
    assert _run_live_helper(helper, ["resume", "--session-root", str(tmp_path / "run")], monkeypatch) == 1
    assert json.loads(capsys.readouterr().out) == summary.to_value()


def test_embedded_prepare_serializes_sealed_context_without_draft_authority(
    tmp_path, monkeypatch, capsys
):
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    def prepare(request):
        assert request.preview_requested is False
        return controller.LiveStartPreparation(
            tmp_path / "run", tmp_path / "context.json", 1, ("limited source evidence",)
        )
    monkeypatch.setattr(controller, "prepare_live_start", prepare)
    _patch_schema_one_route(monkeypatch)
    assert _run_live_helper(helper, [
        "prepare", "--deck-name", "Deck", "--deck-code", "AAE="
    ], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "INPUT_FROZEN", "run_root": str(tmp_path / "run"),
        "starter_context_path": str(tmp_path / "context.json"),
        "candidate_revision": 1, "visible_limitations": ["limited source evidence"],
    }


def test_embedded_prepare_serializes_discovery_request_without_candidate_authority(
    tmp_path, monkeypatch, capsys
):
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    request_path = tmp_path / "run/research/request.json"
    monkeypatch.setattr(
        controller,
        "prepare_live_start",
        lambda _request: controller.LiveStartDiscovery(
            tmp_path / "run", request_path, "sha256:" + "1" * 64
        ),
    )
    _patch_schema_one_route(monkeypatch)
    assert _run_live_helper(
        helper,
        ["prepare", "--deck-name", "Deck", "--deck-code", "AAE="],
        monkeypatch,
    ) == 0
    assert json.loads(capsys.readouterr().out) == {
        "status": "DISCOVERY_REQUIRED",
        "run_root": str(tmp_path / "run"),
        "acquisition_request_path": str(request_path),
        "acquisition_request_sha256": "sha256:" + "1" * 64,
    }


def test_embedded_quality_envelope_preserves_receipt_and_original_exit_status(
    tmp_path, monkeypatch, capsys
):
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "session.json").write_bytes(b"sealed session sentinel")
    route = package_request.FrozenJsonDocument.from_value(
        {
            "schema_version": 2,
            "status": "CANDIDATE_DRAFTED",
            "next_action": "return_exact_findings_to_same_lead",
        }
    )
    monkeypatch.setattr(controller, "quality_start_summary", lambda **_: route)
    original = package_request.FrozenJsonDocument.from_value(
        {"status": "revision_required", "findings": ["exact_finding"]}
    )
    monkeypatch.setattr(
        controller, "validate_live_start_candidate", lambda **_: original
    )

    assert _run_live_helper(
        helper,
        [
            "validate-candidate",
            "--session-root",
            str(run_root),
            "--draft-path",
            str(tmp_path / "candidate.json"),
        ],
        monkeypatch,
    ) == 1
    assert json.loads(capsys.readouterr().out) == {
        "controller_result": original.to_value(),
        "quality_route_summary": route.to_value(),
    }


def test_actual_default_helper_reaches_preview_with_synthetic_transport(
    tmp_path, monkeypatch, capsys, helper_quality_request
):
    from hsconfig.package_request import FrozenJsonDocument
    from hsconfig.starter_context import (
        STARTER_CONTEXT_MAX_BYTES,
        validate_starter_context_document,
    )
    from hsconfig.starter_contract import QUALITY_STARTER_CONTEXT_FIELDS
    from hsconfig.starter_document import load_starter_document
    from tests.test_quality_starter_candidate import quality_draft
    from tests.test_quality_starter_review import quality_review

    quality_request = helper_quality_request
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    assert _run_live_helper(
        helper,
        [
            "prepare",
            "--deck-name",
            quality_request.deck_name,
            "--deck-code",
            quality_request.deck_code,
            "--preview",
        ],
        monkeypatch,
    ) == 0
    discovery_output = json.loads(capsys.readouterr().out)
    discovery = discovery_output["controller_result"]
    assert discovery["status"] == "DISCOVERY_REQUIRED"
    assert discovery_output["quality_route_summary"]["next_action"] == (
        "complete_or_resume_same_research_request"
    )
    run_root = Path(discovery["run_root"])
    shortlist = tmp_path / "shortlist.json"
    shortlist.write_bytes(
        FrozenJsonDocument.from_value(
            {
                "acquisition_request_sha256": discovery[
                    "acquisition_request_sha256"
                ],
                "urls": [],
                "discovery_outcome": "unavailable",
            }
        ).canonical_json
    )

    assert _run_live_helper(
        helper,
        [
            "complete-research",
            "--session-root",
            str(run_root),
            "--draft-path",
            str(shortlist),
        ],
        monkeypatch,
    ) == 0
    prepared_output = json.loads(capsys.readouterr().out)
    prepared = prepared_output["controller_result"]
    assert prepared["status"] == "INPUT_FROZEN"
    assert prepared_output["quality_route_summary"]["next_action"] == (
        "dispatch_lead_strategist"
    )
    context = validate_starter_context_document(
        load_starter_document(
            Path(prepared["starter_context_path"]),
            maximum_bytes=STARTER_CONTEXT_MAX_BYTES,
            expected_fields=QUALITY_STARTER_CONTEXT_FIELDS,
            schema_version=3,
        )
    )
    assert context.document.to_value()["schema_version"] == 3
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_bytes(
        FrozenJsonDocument.from_value(quality_draft(context)).canonical_json
    )

    assert _run_live_helper(
        helper,
        [
            "validate-candidate",
            "--session-root",
            str(run_root),
            "--draft-path",
            str(candidate_path),
        ],
        monkeypatch,
    ) == 0
    candidate_output = json.loads(capsys.readouterr().out)
    candidate_receipt = FrozenJsonDocument.from_value(
        candidate_output["controller_result"]
    )
    assert candidate_output["quality_route_summary"]["next_action"] == (
        "dispatch_independent_reviewer"
    )
    candidate = controller._load_bound_candidate(
        session_root=run_root, context=context
    )
    assert candidate.document.to_value()["schema_version"] == 3
    review = quality_review(context, candidate, candidate_receipt).to_value()
    review.pop("content_sha256")
    review_path = tmp_path / "review.json"
    review_path.write_bytes(FrozenJsonDocument.from_value(review).canonical_json)

    assert _run_live_helper(
        helper,
        [
            "validate-review",
            "--session-root",
            str(run_root),
            "--draft-path",
            str(review_path),
        ],
        monkeypatch,
    ) == 0
    review_output = json.loads(capsys.readouterr().out)
    assert review_output["controller_result"]["review_status"] == "approved"
    assert review_output["quality_route_summary"]["next_action"] == (
        "finalize_reviewed_candidate"
    )
    installed_review = FrozenJsonDocument.from_json_bytes(
        (run_root / "starter/starter_config_review.json").read_bytes()
    ).to_value()
    assert installed_review["schema_version"] == 3

    assert _run_live_helper(
        helper,
        ["finalize", "--session-root", str(run_root)],
        monkeypatch,
    ) == 0
    final_output = json.loads(capsys.readouterr().out)
    assert final_output["controller_result"]["status"] == "PREVIEW_READY"
    assert final_output["quality_route_summary"]["next_action"] == (
        "inspect_preserved_preview"
    )
    assert final_output["quality_route_summary"]["runtime_write_state"] == "no"
    runtime_root = tmp_path / "runtime"
    assert runtime_root.is_dir()
    assert not any(runtime_root.rglob("*"))


@pytest.mark.parametrize("relative", _HELPERS)
def test_embedded_review_helper_accepts_approved_receipt_without_status(
    tmp_path, monkeypatch, capsys, relative
):
    from hsconfig.live_start_session import seal_validation_receipt

    helper = _materialize_helper(tmp_path, relative)
    receipt = package_request.FrozenJsonDocument.from_value(
        seal_validation_receipt(
            receipt_kind="review_validation",
            unsigned_value={
                "run_id": "a" * 32,
                "candidate_revision": 1,
                "starter_context_sha256": "sha256:" + "1" * 64,
                "candidate_sha256": "sha256:" + "2" * 64,
                "review_sha256": "sha256:" + "3" * 64,
                "review_status": "approved",
                "confidence": "limited",
            },
        )
    )
    monkeypatch.setattr(controller, "validate_live_start_review", lambda **kwargs: receipt)
    _patch_schema_one_route(monkeypatch)
    assert _run_live_helper(helper, [
        "validate-review", "--session-root", "run", "--draft-path", "review.json"
    ], monkeypatch) == 0
    assert json.loads(capsys.readouterr().out) == receipt.to_value()


def _render_real_optimized_package(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    confidence: str = "high",
) -> tuple[Path, dict[str, object], Path]:
    from hsconfig.configure_models import ConfigureRequest
    from hsconfig.configure_workflow import execute_configure
    from hsconfig.starter_context import build_starter_context
    from tests.helpers.audited_package_request import audited_request
    from tests.helpers.package_byte_contract import (
        _offline_build_inputs,
        _offline_network_and_card_data,
    )
    from tests.test_starter_decision import (
        three_candidates,
        write_selection_bundle,
    )

    conservative = audited_request(root / "request", "ShadowPriest")
    context = build_starter_context(conservative.snapshot)

    def set_confidence(draft: dict[str, object]) -> None:
        critic = draft["critic_identity"]
        assert isinstance(critic, dict)
        critic["confidence"] = confidence

    decision_path = write_selection_bundle(
        root / "selection",
        context,
        three_candidates(context),
        mutate_decision=set_confidence,
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
    request = ConfigureRequest(
        deck_name="ShadowPriest",
        deck_code=conservative.invocation.deck_code,
        output_root=root / "configure-output",
        runtime_root=root / "runtime",
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
    assert not request.runtime_root.exists()
    summary = result.materialized_summary()
    assert "optimized_start" in summary
    return result.published_output.package_root, summary, decision_path.parent


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )


def test_legacy_package_retains_optimized_summary_and_assurance(tmp_path, monkeypatch):
    package, summary, starter_dir = _render_real_optimized_package(tmp_path / "legacy", monkeypatch)
    decision = json.loads((starter_dir / "starter_config_decision.json").read_bytes())
    selected = json.loads((starter_dir / f"{decision['selected_candidate_id']}.json").read_bytes())
    assert summary["optimized_start"]["selected_candidate_sha256"] == selected["content_sha256"]
    assert summary["optimized_start"]["decision_sha256"] == decision["content_sha256"]
    assurance = json.loads(
        (package / "reports/operator_summary.json").read_bytes()
    )["configuration_assurance"]
    assert assurance["assurance"] == "LLM_OPTIMIZED_START"
    assert assurance["load_safety"] == "validated"
    assert assurance["in_client_behavior"] == "not_proven_by_pre_run_contract"
    assert assurance["optimality_claim_allowed"] is False
    assert assurance["runtime_gate_impact"] == "none"
    assert hsconfig_cli.main(["validate", "--package", str(package), "--json"]) == 0


def test_legacy_package_rejects_real_authority_tampering(tmp_path, monkeypatch):
    from hsconfig.apply_gate import recompute_apply_decision
    package, _summary, _starter_dir = _render_real_optimized_package(tmp_path / "legacy", monkeypatch)
    operator_path = package / "reports/operator_summary.json"
    receipt_path = package / "package_derivation_receipt.json"
    candidate_path = package / "reports/optimized_start/candidate-2.json"
    originals = {path: path.read_bytes() for path in (operator_path, receipt_path, candidate_path)}
    for defect in ("missing_receipt", "downgraded_receipt",
                   "missing_candidate_report", "forged_operator_core"):
        for path, content in originals.items():
            path.write_bytes(content)
        if defect == "missing_receipt":
            receipt_path.unlink()
        elif defect == "downgraded_receipt":
            receipt = json.loads(originals[receipt_path])
            receipt["schema_version"] = 2
            _write_json(receipt_path, receipt)
        elif defect == "missing_candidate_report":
            candidate_path.unlink()
        else:
            operator = json.loads(originals[operator_path])
            operator["optimized_start_derivation_validity"] = False
            _write_json(operator_path, operator)
        try:
            decision, _facts = recompute_apply_decision(
                package, json.loads(operator_path.read_bytes()), enforce_summary_core_fields=True
            )
        except (ValueError, OSError):
            continue
        assert not decision.allowed, defect

    # Diagnostic assurance cannot promote a package whose authority is denied.
    for path, content in originals.items():
        path.write_bytes(content)
    operator = json.loads(originals[operator_path])
    operator["optimized_start_derivation_validity"] = False
    operator["configuration_assurance"].update({
        "in_client_behavior": "proven_in_client",
        "optimality_claim_allowed": True,
        "runtime_gate_impact": "apply_authority",
        "forged_extra": True,
    })
    _write_json(operator_path, operator)
    decision, _facts = recompute_apply_decision(
        package, operator, enforce_summary_core_fields=True
    )
    assert not decision.allowed


def test_legacy_low_confidence_remains_visible(tmp_path, monkeypatch):
    _package, summary, _starter_dir = _render_real_optimized_package(
        tmp_path / "legacy-low", monkeypatch, confidence="low"
    )
    assert summary["optimized_start"]["status"] == "low_confidence"


def test_embedded_bundle_contains_no_model_client_import_or_call() -> None:
    files = load_embedded_skill_bundle()
    forbidden_modules = {
        "anthropic",
        "google.generativeai",
        "openai",
    }
    forbidden_calls = {
        "Anthropic",
        "OpenAI",
        "chat.completions.create",
        "responses.create",
    }

    for path in ("scripts/build_config.py", "scripts/validate_package.py"):
        source = files[path].decode("utf-8")
        tree = ast.parse(source, filename=path)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imports.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        calls = {
            ast.unparse(node.func)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert imports.isdisjoint(forbidden_modules)
        assert calls.isdisjoint(forbidden_calls)
