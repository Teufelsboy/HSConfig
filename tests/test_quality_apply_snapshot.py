"""The quality gate replays exact frozen identity without a second card database."""

from copy import deepcopy
import base64
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

import hsconfig.deck_input_verification as verification
import hsconfig.live_start_controller as controller
from hsconfig.apply_gate import _deck_input_verification_reasons, evaluate_apply_gate
from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
from hsconfig.package_request import FrozenApprovedLiveConfigureRequest, FrozenJsonDocument
from tests.test_quality_live_start_controller import quality_request as _quality_request
from tests.test_quality_start_summary import _approved_quality


@pytest.fixture(scope="module")
def compiled_quality(tmp_path_factory):
    root = tmp_path_factory.mktemp("quality-apply-snapshot")
    with pytest.MonkeyPatch.context() as patch:
        request = _quality_request.__wrapped__(root, patch)
        prepared, _, _, _, _ = _approved_quality(request, root)
        frozen = load_frozen_compiler_inputs(prepared.run_root)
        approval = controller._load_frozen_approval(
            session_root=prepared.run_root, frozen=frozen,
        )
        compile_request = FrozenApprovedLiveConfigureRequest.from_values(
            frozen_compiler_inputs=frozen, starter_approval=approval,
        )
        rendered = controller.render_configure_run_model(
            controller.build_frozen_live_configure_run(request=compile_request)
        )
        artifacts = {
            row.relative_path.removeprefix("04_package/"): row.content
            for row in rendered.artifacts
            if row.relative_path.startswith("04_package/")
        }
    return SimpleNamespace(
        root=root, frozen=frozen, approval=approval, artifacts=artifacts,
    )


@pytest.fixture
def quality_package(compiled_quality, tmp_path):
    package = tmp_path / "package"
    for logical, content in compiled_quality.artifacts.items():
        path = package / logical
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return package


def _forbid_legacy(monkeypatch):
    from hearthstone import cardxml

    def forbidden(*_args, **_kwargs):
        pytest.fail("quality gate reached the secondary legacy card database")

    monkeypatch.setattr(verification, "decode_deck_code", forbidden)
    monkeypatch.setattr(cardxml, "load_dbf", forbidden)


def test_real_quality_gate_does_not_reacquire_card_database(
    compiled_quality, quality_package, monkeypatch,
):
    # Break caught: normal quality identity depends on mutable cardxml/web data.
    _forbid_legacy(monkeypatch)
    gate = evaluate_apply_gate(
        quality_package, frozen_compiler_inputs=compiled_quality.frozen,
    )
    assert gate["status"] == "allowed"


def _read(package, logical):
    return json.loads((package / logical).read_bytes())


def _write(package, logical, value):
    (package / logical).write_bytes(FrozenJsonDocument.from_value(value).canonical_json)


def _reasons(package, frozen):
    return _deck_input_verification_reasons(
        package, _read(package, "reports/operator_summary.json"),
        frozen_compiler_inputs=frozen,
    )


@pytest.mark.parametrize("defect", [
    "code", "same_roster_code_bytes", "count", "dbf", "card_id", "hero",
    "format", "sideboard", "manifest_parity", "summary_parity", "route",
    "candidate_context", "context_dbf", "snapshot_manifest",
])
def test_quality_gate_rejects_changed_package_identity_without_legacy_fallback(
    compiled_quality, quality_package, monkeypatch, defect,
):
    # Break caught: snapshot success is treated as permission to trust stale JSON.
    _forbid_legacy(monkeypatch)
    manifest = _read(quality_package, "reports/input_manifest.json")
    identity = _read(quality_package, "reports/deck_identity.json")
    if defect == "code":
        manifest["deck_code"] = "not-a-deckstring"
    elif defect == "same_roster_code_bytes":
        manifest["deck_code"] += " "
    elif defect in {"count", "dbf", "card_id"}:
        field = {"count": "count", "dbf": "dbf_id", "card_id": "card_id"}[defect]
        identity["cards"][0][field] = "OTHER_CARD" if defect == "card_id" else 999
    elif defect == "hero":
        identity["hero_dbf_id"] = 7
    elif defect == "format":
        identity["format"] = "STANDARD"
    elif defect == "sideboard":
        identity["sideboards"] = [{"owner_card_id": "OTHER", "cards": []}]
    elif defect == "manifest_parity":
        manifest["deck_input_verification"]["normalized_roster_sha256"] = "sha256:" + "f" * 64
    elif defect == "summary_parity":
        summary = _read(quality_package, "reports/operator_summary.json")
        summary["deck_input_verification"]["normalized_roster_sha256"] = "sha256:" + "f" * 64
        _write(quality_package, "reports/operator_summary.json", summary)
    elif defect == "route":
        manifest["optimized_start_authority_schema"] = "single_candidate_review_v1"
    else:
        filename = {
            "candidate_context": "starter_config_candidate.json",
            "context_dbf": "starter_context.json",
            "snapshot_manifest": "input_snapshot_manifest.json",
        }[defect]
        logical = "reports/optimized_start/" + filename
        document = _read(quality_package, logical)
        if defect == "candidate_context":
            document["starter_context_sha256"] = "sha256:" + "f" * 64
        elif defect == "context_dbf":
            next(iter(document["card_metadata"].values()))["dbf_id"] = 999
        else:
            document["content_sha256"] = "sha256:" + "f" * 64
        _write(quality_package, logical, document)
    _write(quality_package, "reports/input_manifest.json", manifest)
    _write(quality_package, "reports/deck_identity.json", identity)
    reasons = _reasons(quality_package, compiled_quality.frozen)
    assert reasons and reasons[0]["reason"] == "deck_input_not_verified"


@pytest.mark.parametrize("defect", [
    "missing_dbf", "conflicting_dbf", "card_id", "full_blob", "snapshot_hash",
    "missing_quality", "manifest_cache", "wrong_carrier",
])
def test_quality_gate_revalidates_carrier_not_just_dataclass_type(
    compiled_quality, quality_package, monkeypatch, defect,
):
    # Break caught: stale/mutated frozen bytes bypass package-to-input authority.
    _forbid_legacy(monkeypatch)
    frozen = compiled_quality.frozen
    full = frozen.full_cards.to_value()
    if defect == "wrong_carrier":
        frozen = object()
    elif defect == "manifest_cache":
        frozen = replace(frozen, manifest=replace(frozen.manifest, blobs=()))
    elif defect == "missing_quality":
        frozen = replace(frozen, quality_inputs=None)
    elif defect == "snapshot_hash":
        quality = frozen.quality_inputs.to_value()
        quality["card_snapshot_sha256"] = "sha256:" + "f" * 64
        frozen = replace(frozen, quality_inputs=FrozenJsonDocument.from_value(quality))
    else:
        if defect == "missing_dbf":
            full[0]["dbf_id"] = None
        elif defect == "conflicting_dbf":
            full[0]["dbf_id"] = full[1]["dbf_id"]
        elif defect == "card_id":
            full[0]["id"] = "OTHER_CARD"
        else:
            full[0]["name"] += " changed"
        frozen = replace(frozen, full_cards=FrozenJsonDocument.from_value(full))
    reasons = _reasons(quality_package, frozen)
    assert reasons and reasons[0]["reason"] == "deck_input_not_verified"


def test_fake_plan_uses_bound_quality_snapshot(compiled_quality, quality_package, monkeypatch):
    from hsconfig.runtime_apply import plan_apply_package

    # Break caught: the second normal prepublication gate forgets the carrier.
    _forbid_legacy(monkeypatch)
    planned = plan_apply_package(
        package_root=quality_package, runtime_root=compiled_quality.root / "runtime",
        frozen_compiler_inputs=compiled_quality.frozen,
    )
    assert planned["status"] == "fake_apply_ready"
    assert planned["runtime_write_performed"] is False
    assert planned["apply_gate"]["status"] == "allowed"


def test_absent_carrier_keeps_legacy_verifier(compiled_quality, quality_package, monkeypatch):
    # Break caught: standalone expert calls silently trust package snapshot labels.
    calls = []

    def legacy(code):
        calls.append(code)
        return {"cards": compiled_quality.frozen.deck.to_value()["deck_identity"]["cards"]}

    monkeypatch.setattr(verification, "decode_deck_code", legacy)
    assert evaluate_apply_gate(quality_package)["status"] == "allowed"
    assert calls == [_read(quality_package, "reports/input_manifest.json")["deck_code"]]


def test_resealed_self_consistent_context_cannot_replace_frozen_dbf_identity(
    compiled_quality, quality_package, monkeypatch,
):
    from hsconfig.optimized_start_authority import load_optimized_start_authority
    from hsconfig.starter_candidate import validate_starter_candidate
    from tests.test_quality_starter_candidate import reseal_context, seal_quality_candidate
    from tests.test_quality_starter_review import quality_receipt, quality_review

    # Break caught: trusting a self-consistent package instead of rebuilding from blobs.
    _forbid_legacy(monkeypatch)
    context_value = compiled_quality.approval.context.document.to_value()
    context_value["card_metadata"]["TOY_518"]["dbf_id"] = 999999
    context = reseal_context(context_value)
    draft = compiled_quality.approval.candidate.document.to_value()
    draft.pop("content_sha256")
    draft["starter_context_sha256"] = context.document.content_sha256
    candidate = validate_starter_candidate(seal_quality_candidate(draft), context=context)
    receipt = quality_receipt(context, candidate)
    review = quality_review(context, candidate, receipt)
    for filename, document in (
        ("starter_context.json", context.document),
        ("starter_config_candidate.json", candidate.document),
        ("candidate_validation_receipt.json", receipt),
        ("starter_config_review.json", review),
    ):
        _write(quality_package, "reports/optimized_start/" + filename, document.to_value())
    # This forged set passes its own hashes, review and receipt binding.
    approval = load_optimized_start_authority(
        report_root=quality_package / "reports/optimized_start",
        manifest=_read(quality_package, "reports/input_manifest.json"),
    )
    assert approval.context.document.to_value()["card_metadata"]["TOY_518"]["dbf_id"] == 999999
    assert _reasons(quality_package, compiled_quality.frozen)[0]["reason"] == "deck_input_not_verified"


def test_other_session_frozen_inputs_cannot_authorize_package(
    compiled_quality, quality_package, tmp_path, monkeypatch,
):
    from tests.test_quality_start_summary import _frozen_quality

    request = _quality_request.__wrapped__(tmp_path, monkeypatch)
    prepared = _frozen_quality(request, tmp_path)
    other = load_frozen_compiler_inputs(prepared.run_root)
    assert other.manifest.document.content_sha256 != compiled_quality.frozen.manifest.document.content_sha256
    _forbid_legacy(monkeypatch)
    assert _reasons(quality_package, other)[0]["reason"] == "deck_input_not_verified"


@pytest.mark.parametrize("heroes", [b"\x00", b"\x02\xad\x06\xbf\x84\x3d"])
def test_snapshot_recompute_does_not_discard_extra_or_missing_heroes(compiled_quality, heroes):
    # Break caught: decoder's first-hero projection hides malformed cardinality.
    frozen = compiled_quality.frozen
    deck = frozen.deck.to_value()
    raw = base64.b64decode(deck["cards_payload"]["deck_code"])
    assert raw[3:6] == b"\x01\xad\x06"
    code = base64.b64encode(raw[:3] + heroes + raw[6:]).decode()
    deck["cards_payload"]["deck_code"] = code
    changed = replace(frozen, deck=FrozenJsonDocument.from_value(deck))
    with pytest.raises(ValueError, match="^quality_deck_hero_invalid$"):
        verification.verify_frozen_deck_input(
            deck_code=code, deck_identity=deck["deck_identity"], source="deckstring",
            frozen_compiler_inputs=changed,
        )


def test_snapshot_recompute_rejects_resolved_minion_hero(compiled_quality):
    from hearthstone.deckstrings import parse_deckstring, write_deckstring

    frozen = compiled_quality.frozen
    deck = frozen.deck.to_value()
    cards, _, deck_format, sideboards = parse_deckstring(deck["cards_payload"]["deck_code"])
    code = write_deckstring(cards, [64443], deck_format, sideboards)
    deck["cards_payload"]["deck_code"] = code
    changed = replace(frozen, deck=FrozenJsonDocument.from_value(deck))
    with pytest.raises(ValueError, match="^quality_deck_hero_invalid$"):
        verification.verify_frozen_deck_input(
            deck_code=code, deck_identity=deck["deck_identity"], source="deckstring",
            frozen_compiler_inputs=changed,
        )


def test_real_mechpala_sideboard_is_recomputed_not_just_main_roster(tmp_path, monkeypatch):
    from hsconfig.card_snapshot import validated_card_snapshot
    from tests.helpers.quality_start import quality_frozen_inputs
    from tests.test_quality_live_start_controller import _empty_draft

    # Break caught: a matching main-roster hash hides missing/wrong Zilliax parts.
    source = quality_frozen_inputs(
        tmp_path, monkeypatch, deck_name="MechPala", bind_deck_code=True,
        include_source_documents=False,
    )
    # These are already normalized records: preserve their source_fields instead
    # of pretending every normalized default was present in the upstream JSON.
    quality = source.quality_inputs.to_value()
    full = source.full_cards.to_value()
    snapshot = FrozenJsonDocument.from_value({
        "full_cards": full,
        "collectible_cards": source.collectible_cards.to_value(),
        "dbf_to_card_id": {str(row["dbf_id"]): row["id"] for row in full if row["dbf_id"] is not None},
        "captured_at": quality["card_snapshot_captured_at"],
        "upstream_version": quality["card_snapshot_upstream_version"],
        "dataset_sha256": quality["card_snapshot_sha256"],
    })
    validated_card_snapshot(snapshot)
    monkeypatch.setattr(controller, "fetch_card_snapshot", lambda **_: snapshot)
    request = controller.LiveStartRequest(
        deck_name="MechPala", deck_code=source.deck.to_value()["cards_payload"]["deck_code"],
        preview_requested=True,
    )
    prepared = controller.prepare_quality_live_start(request)
    prepared = controller.complete_live_start_research(
        session_root=prepared.run_root, draft_path=_empty_draft(tmp_path, prepared),
    )
    frozen = load_frozen_compiler_inputs(prepared.run_root)
    deck = frozen.deck.to_value()
    identity = deck["deck_identity"]
    assert identity["sideboards"][0]["owner_card_id"] == "TOY_330"
    assert {row["card_id"] for row in identity["sideboards"][0]["cards"]} == {
        "TOY_330t95", "TOY_330t98", "TOY_330t11",
    }
    _forbid_legacy(monkeypatch)

    def verify(value):
        return verification.verify_frozen_deck_input(
            deck_code=deck["cards_payload"]["deck_code"], deck_identity=value,
            source="deckstring", frozen_compiler_inputs=frozen,
        )

    assert verify(identity)["runtime_apply_eligible"] is True
    for defect in ("missing", "owner", "dbf", "count", "card"):
        changed = deepcopy(identity)
        board = changed["sideboards"][0]
        if defect == "missing":
            changed["sideboards"] = []
        elif defect == "owner":
            board["owner_card_id"] = "ETC_080"
        else:
            field = {"dbf": "dbf_id", "count": "count", "card": "card_id"}[defect]
            board["cards"][0][field] = "OTHER_CARD" if defect == "card" else 999999
        with pytest.raises(ValueError, match="^quality_deck_identity_mismatch$"):
            verify(changed)


def test_real_quality_controller_forwards_snapshot_through_both_prepublication_gates(tmp_path, monkeypatch):
    from hsconfig.live_start_session import load_live_start_session

    # Break caught: pure gate works but the real controller/fake-plan path omits it.
    request = _quality_request.__wrapped__(tmp_path, monkeypatch)
    prepared, _, _, _, _ = _approved_quality(request, tmp_path)
    _forbid_legacy(monkeypatch)
    result = controller.finalize_live_start(session_root=prepared.run_root)
    assert result.status == "PREVIEW_READY"
    completed = load_live_start_session(prepared.run_root)
    assert "receipts/package_validation.json" in completed.artifact_bindings
    assert "receipts/prepublication_apply_check.json" in completed.artifact_bindings
    assert completed.apply_invocation_sha256 is None
    assert list((tmp_path / "runtime").iterdir()) == []


def test_controller_rejects_crossed_physically_loaded_manifest_before_materialization(
    compiled_quality, tmp_path, monkeypatch,
):
    from hsconfig.live_start_session import load_live_start_session

    # Break caught: a valid carrier from another run crosses the active session.
    request = _quality_request.__wrapped__(tmp_path, monkeypatch)
    prepared, _, _, _, _ = _approved_quality(request, tmp_path)
    original = controller._load_frozen_compiler_inputs
    calls = []

    def crossed(root, **kwargs):
        loaded = original(root, **kwargs)
        calls.append(root)
        # The first load is finalization's request construction; the second is
        # the new physical rebind at the active prepublication boundary.
        return compiled_quality.frozen if len(calls) == 2 else loaded

    monkeypatch.setattr(controller, "_load_frozen_compiler_inputs", crossed)
    _forbid_legacy(monkeypatch)
    with pytest.raises(controller.SessionConflictError, match="^live_start_input_snapshot_mismatch$"):
        controller.finalize_live_start(session_root=prepared.run_root)
    current = load_live_start_session(prepared.run_root)
    assert current.phase.value == "REVIEW_APPROVED"
    assert "receipts/package_validation.json" not in current.artifact_bindings
    assert current.apply_invocation_sha256 is None
    assert list((tmp_path / "runtime").iterdir()) == []
