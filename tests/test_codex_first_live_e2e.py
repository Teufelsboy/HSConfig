from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.current_output import resolve_current_package
from hsconfig.deck_identity import normalize_roster, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.live_start_session import SessionConflictError, load_live_start_session
from hsconfig.operator_profile import derive_deck_output_binding
from hsconfig.runtime_installer import _parse_owner_retirement_tombstone_bytes
from hsconfig.runtime_package_match import build_runtime_package_match_report
from hsconfig.runtime_transaction_journal import (
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from hsconfig.starter_contract import (
    SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
    SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    STARTER_REVIEW_FIELDS,
)
from hsconfig.starter_document import seal_starter_document
from tests import starter_fixtures
from tests.test_live_start_controller import _write_unsigned_document


def _prepare(root, monkeypatch, *, deck_kind="shadowpriest", preview=False, confidence="high", profile=None):
    fixture = starter_fixtures.build_codex_first_fixture(
        root, deck_kind=deck_kind, existing_profile=profile, confidence=confidence,
    )
    with monkeypatch.context() as acquisition:
        acquisition.setattr(controller, "_capture_live_start_inputs", lambda *_args: fixture.frozen_inputs)
        prepared = controller._prepare_legacy_live_start(controller.LiveStartRequest(
            deck_name=fixture.deck_name, deck_code=fixture.deck_code, preview_requested=preview,
        ))
    assert isinstance(prepared, controller.LiveStartPreparation)
    return fixture, prepared


def _approve(root, fixture, prepared):
    candidate_path = root / "candidate-draft.json"
    review_path = root / "review-draft.json"
    _write_unsigned_document(candidate_path, fixture.candidate)
    _write_unsigned_document(review_path, fixture.review)
    controller.validate_live_start_candidate(session_root=prepared.run_root, draft_path=candidate_path)
    controller.validate_live_start_review(session_root=prepared.run_root, draft_path=review_path)


def _prepare_approved(root, monkeypatch, *, deck_kind="shadowpriest", preview=False, confidence="high", profile=None):
    fixture, prepared = _prepare(
        root, monkeypatch, deck_kind=deck_kind, preview=preview,
        confidence=confidence, profile=profile,
    )
    _approve(root, fixture, prepared)
    return fixture, prepared


def _local_state(tmp_path, monkeypatch):
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))


def _tree_bytes(root):
    """Include directory shape and every file, including controller metadata."""
    return {
        path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
        for path in root.rglob("*")
    }


def _matched_package(fixture):
    output = derive_deck_output_binding(fixture.profile, fixture.deck_name).output_root
    package = resolve_current_package(output)
    report = build_runtime_package_match_report(
        package_root=package, runtime_root=fixture.profile.runtime_root,
    )
    assert report["status"] == "matched"
    assert report["runtime_mapping_identity_valid"] is True
    assert report["runtime_tree_identity_valid"] is True
    assert report["missing_in_runtime"] == report["extra_in_runtime"] == []
    assert report["semantic_mismatch_count"] == 0
    assert _tree_bytes(Path(report["package_config_path"])) == _tree_bytes(Path(report["runtime_config_path"]))
    return output, package, Path(report["runtime_config_path"])


def _changed_candidate(fixture):
    value = fixture.candidate.to_value()
    value.pop("content_sha256")
    value["globalvalues"]["FirstTurnValueWeight"]["values"][0]["value"] = "0.85"
    candidate = seal_starter_document(
        value, expected_fields=SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    )
    review = fixture.review.to_value()
    review.pop("content_sha256")
    review["candidate_sha256"] = candidate.content_sha256
    return replace(fixture, candidate=candidate, review=seal_starter_document(
        review, expected_fields=STARTER_REVIEW_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    ))


def test_supported_non_thirty_resolvable_deck_reaches_preview_with_exact_coverage(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "forty", monkeypatch, deck_kind="uncatalogued_40", preview=True, confidence="limited")
    result = controller.finalize_live_start(session_root=prepared.run_root)
    terminal = load_live_start_session(prepared.run_root)
    summary = result.summary.to_value()
    assert result.status == "PREVIEW_READY"
    decoded = decode_deck_code(fixture.deck_code)
    deck = fixture.frozen_inputs.deck.to_value()
    roster = normalize_roster(decoded["cards"])
    assert decoded["unresolved_identity_count"] == 0
    assert decoded["card_count_total"] == len(roster) == 40
    assert all(count == 1 for _, count in roster)
    assert "REV_018" in dict(roster)  # Actual Prince Renathal supports the 40-card structure.
    assert normalize_roster(deck["cards_payload"]["cards"]) == roster
    assert normalize_roster(deck["deck_identity"]["main_deck"]) == roster
    assert fixture.context.deck_fingerprint == stable_deck_fingerprint(roster)
    assert deck["cards_payload"]["deck_code"] == fixture.deck_code
    assert deck["deck_identity"]["deck_code_hash"] == sha256(fixture.deck_code.encode("utf-8")).hexdigest()
    assert all(row["deck_name"] != fixture.deck_name and row["deck_code"] != fixture.deck_code for row in load_audited_deck_catalog())
    context_cards = fixture.context.document.to_value()["cards"]
    dispositions = fixture.candidate.to_value()["card_dispositions"]
    assert len(context_cards) == len(dispositions) == len(roster)
    assert {row["card_id"] for row in context_cards} == {row["card_id"] for row in dispositions} == set(dict(roster))
    assert terminal.result_intent["unique_main_deck_cards"] == summary["unique_main_deck_cards"] == 40
    assert summary["configured_cards"] + summary["deliberately_unconfigured_cards"] == 40
    assert summary["deck_name"] == fixture.deck_name
    assert json.loads((prepared.run_root / "result/summary.json").read_bytes()) == summary
    assert (
        f"- Card coverage: {summary['configured_cards']} configured, "
        f"{summary['deliberately_unconfigured_cards']} deliberately unconfigured, "
        "40 unique main-deck cards"
    ) in (prepared.run_root / "result/summary.md").read_text(encoding="utf-8")
    assert not tuple(fixture.profile.runtime_root.iterdir())


def test_shadowpriest_reaches_live_and_matched_through_real_downstream_pipeline(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "shadow", monkeypatch)
    result = controller.finalize_live_start(session_root=prepared.run_root)
    terminal = load_live_start_session(prepared.run_root)
    assert result.status == terminal.terminal_status == "LIVE_AND_MATCHED"
    summary = result.summary.to_value()
    assert summary["deck_name"] == "ShadowPriest"
    assert summary["configured_cards"] + summary["deliberately_unconfigured_cards"] == 16
    catalog = next(row for row in load_audited_deck_catalog() if row["deck_name"] == fixture.deck_name)
    assert catalog["deck_code"] == fixture.deck_code == starter_fixtures.SHADOWPRIEST_DECK_CODE
    assert fixture.context.deck_fingerprint == starter_fixtures.SHADOWPRIEST_DECK_FINGERPRINT
    # Optional identities are checked against code-bound evidence, never invented.
    for identity in (catalog, fixture.frozen_inputs.deck.to_value()["deck_identity"], fixture.context.document.to_value()["deck_identity"]):
        for field, expected in (("hs_id", starter_fixtures.SHADOWPRIEST_HS_ID), ("hdt_deck_id", starter_fixtures.SHADOWPRIEST_HDT_DECK_ID)):
            if identity.get(field) is not None:
                assert str(identity[field]) == expected
    assert terminal.apply_invocation_sha256 is not None
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert not Path(terminal.runtime_admission_binding["admission_path"]).exists()
    assert fixture.profile.runtime_root.is_dir()
    _matched_package(fixture)


def test_limited_review_is_visible_but_still_valid(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    _fixture, prepared = _prepare_approved(tmp_path / "limited", monkeypatch, preview=True, confidence="limited")
    result = controller.finalize_live_start(session_root=prepared.run_root)
    assert result.status == "PREVIEW_READY"
    summary = result.summary.to_value()
    assert summary["review_confidence"] == "limited"
    assert summary["visible_limitations"]
    assert "limited" in (prepared.run_root / "result/summary.md").read_text(encoding="utf-8")


def test_second_identical_run_is_already_live_and_does_not_add_runtime_revision(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    first_fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    first_result = controller.finalize_live_start(session_root=first.run_root)
    assert first_result.status == "LIVE_AND_MATCHED"
    runtime = first_fixture.profile.runtime_root
    before = _tree_bytes(runtime)
    output, first_package, first_target = _matched_package(first_fixture)
    first_terminal = load_live_start_session(first.run_root)
    first_publication = first_terminal.publication_binding
    owners = [journal for journal in load_runtime_transaction_journals(runtime)
              if journal.owns_target and runtime / journal.target_path == first_target]
    assert len(owners) == 1
    receipt_relative = f".hsconfig/receipts/{owners[0].state_key}/last_apply_receipt.json"
    first_receipt = json.loads(before[receipt_relative])
    assert first_receipt["source_manifest_sha256"] == first_publication["content_root_sha256"].removeprefix("sha256:")
    assert "sha256:" + sha256(before[receipt_relative]).hexdigest() == first_terminal.result_intent["last_apply_receipt_sha256"]
    assert json.loads((first_package / "reports/optimized_start/starter_config_candidate.json").read_bytes()) == first_fixture.candidate.to_value()

    second_fixture, second = _prepare_approved(tmp_path / "second", monkeypatch, profile=first_fixture.profile)
    assert second.run_root != first.run_root
    first_candidate = first_fixture.candidate.to_value()
    second_candidate = second_fixture.candidate.to_value()
    assert first_candidate["content_sha256"] != second_candidate["content_sha256"]
    assert first_candidate["starter_context_sha256"] != second_candidate["starter_context_sha256"]
    assert first_fixture.frozen_inputs.manifest.document.content_sha256 != second_fixture.frozen_inputs.manifest.document.content_sha256
    for value in (first_candidate, second_candidate):
        value.pop("content_sha256")
        value.pop("starter_context_sha256")
    assert first_candidate == second_candidate
    second_result = controller.finalize_live_start(session_root=second.run_root)
    assert second_result.status == "ALREADY_LIVE"
    second_terminal = load_live_start_session(second.run_root)
    second_output, second_package, second_target = _matched_package(second_fixture)
    assert second_output == output
    assert second_target == first_target
    publication = second_terminal.publication_binding
    current = json.loads((output / "current.json").read_bytes())
    assert current["content_root_sha256"] == publication["content_root_sha256"].removeprefix("sha256:")
    assert current["revision"] == publication["revision"]
    assert second_package == output / publication["revision"] / "04_package"
    assert json.loads((second_package / "reports/optimized_start/starter_config_candidate.json").read_bytes()) == second_fixture.candidate.to_value()
    assert json.loads((second_package / "reports/optimized_start/input_snapshot_manifest.json").read_bytes()) == second_fixture.frozen_inputs.manifest.document.to_value()

    after = _tree_bytes(runtime)
    assert after.keys() == before.keys()
    assert {path: raw for path, raw in after.items() if path != receipt_relative} == {
        path: raw for path, raw in before.items() if path != receipt_relative
    }
    second_receipt = json.loads(after[receipt_relative])
    assert "sha256:" + sha256(after[receipt_relative]).hexdigest() == second_terminal.result_intent["last_apply_receipt_sha256"]
    assert second_receipt["source_manifest_sha256"] == publication["content_root_sha256"].removeprefix("sha256:")
    # A fresh publication may update source provenance, never gameplay bytes.
    assert {key for key in first_receipt.keys() | second_receipt.keys()
            if first_receipt.get(key) != second_receipt.get(key)} == {"source_manifest_sha256"}
    assert controller.resume_live_start(session_root=first.run_root).summary.canonical_json == first_result.summary.canonical_json


def test_later_changed_package_cleans_only_authenticated_old_runtime_revision(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    first_result = controller.finalize_live_start(session_root=first.run_root)
    assert first_result.status == "LIVE_AND_MATCHED"
    runtime = fixture.profile.runtime_root
    output, old_package, old_target = _matched_package(fixture)
    old_current = (output / "current.json").read_bytes()
    first_result_bytes = _tree_bytes(first.run_root / "result")
    owners = [journal for journal in load_runtime_transaction_journals(runtime)
              if journal.owns_target and runtime / journal.target_path == old_target]
    assert len(owners) == 1
    old_owner = owners[0]
    old_owner_path = runtime_transaction_journal_path(runtime, old_owner.transaction_id)
    old_owner_sha256 = sha256(old_owner_path.read_bytes()).hexdigest()

    # Same logical prefix and even identical contents are not ownership evidence.
    lookalike = old_target.with_name(f"{old_owner.logical_config_dir}--sha256-{'f' * 64}")
    shutil.copytree(old_target, lookalike)
    manual = runtime / "CustomConfig/ManualDeck"
    manual.mkdir()
    (manual / "operator-note.txt").write_bytes(b"unrelated operator configuration\r\n")
    sentinel = runtime / "operator-owned.bin"
    sentinel.write_bytes(b"\x00preserve unrelated runtime data\xff")
    unrelated = {path: _tree_bytes(path) for path in (lookalike, manual)}
    sentinel_before = sentinel.read_bytes()

    second_fixture, second = _prepare(tmp_path / "second", monkeypatch, profile=fixture.profile)
    second_fixture = _changed_candidate(second_fixture)
    _approve(tmp_path / "second", second_fixture, second)
    second_result = controller.finalize_live_start(session_root=second.run_root)
    assert second_result.status == "LIVE_AND_MATCHED"
    _output, new_package, new_target = _matched_package(second_fixture)
    assert new_package != old_package and new_target != old_target
    assert (output / "current.json").read_bytes() != old_current
    publication = load_live_start_session(second.run_root).publication_binding
    current = json.loads((output / "current.json").read_bytes())
    assert current["content_root_sha256"] == publication["content_root_sha256"].removeprefix("sha256:")
    assert current["revision"] == publication["revision"]
    assert new_package == output / publication["revision"] / "04_package"
    assert not old_package.parent.exists()
    assert _tree_bytes(first.run_root / "result") == first_result_bytes
    assert not old_target.exists()
    assert not old_owner_path.exists()
    assert all(_tree_bytes(path) == before for path, before in unrelated.items())
    assert sentinel.read_bytes() == sentinel_before
    assert {path for path in (runtime / "CustomConfig").iterdir() if path.is_dir()} == {new_target, lookalike, manual}

    tombstone_path = runtime / ".hsconfig/owner-retirements" / f"{old_owner.transaction_id}.json"
    tombstone = _parse_owner_retirement_tombstone_bytes(tombstone_path.read_bytes(), runtime_root=runtime)
    assert tombstone["state"] == "COMPLETED"
    assert tombstone["retired_owner_transaction_id"] == old_owner.transaction_id
    assert Path(tombstone["retired_target_path"]) == old_target
    assert Path(tombstone["initial_owner_journal_path"]) == old_owner_path
    assert str(tombstone["initial_owner_journal_sha256"]).removeprefix("sha256:") == old_owner_sha256
    new_owners = [journal for journal in load_runtime_transaction_journals(runtime)
                  if journal.owns_target and runtime / journal.target_path == new_target]
    assert len(new_owners) == 1
    assert tombstone["successor_transaction_id"] == new_owners[0].transaction_id
    assert tombstone["successor_package_root_sha256"] == publication["content_root_sha256"]
    assert str(tombstone["successor_package_root_sha256"]).removeprefix("sha256:") == new_owners[0].source_manifest_sha256
    assert new_target.name == f"{new_owners[0].logical_config_dir}--sha256-{new_owners[0].package_root_sha256}"
    assert tombstone["completed_cleanup_cursor"] == tombstone["cleanup_entry_count"]
    assert controller.resume_live_start(session_root=first.run_root).summary.canonical_json == first_result.summary.canonical_json


def test_invalid_candidate_preserves_publication_and_runtime_byte_exact(tmp_path, monkeypatch):
    _local_state(tmp_path, monkeypatch)
    fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    first_result = controller.finalize_live_start(session_root=first.run_root)
    assert first_result.status == "LIVE_AND_MATCHED"
    output, old_package, _old_target = _matched_package(fixture)
    runtime_before = _tree_bytes(fixture.profile.runtime_root)
    output_before = _tree_bytes(fixture.profile.output_base_root)
    current_before = (output / "current.json").read_bytes()

    second_fixture, second = _prepare(tmp_path / "second", monkeypatch, profile=fixture.profile)
    invalid = second_fixture.candidate.to_value()
    invalid.pop("content_sha256")
    invalid["card_dispositions"].pop()  # Complete physical-card accounting is mandatory.
    invalid_document = seal_starter_document(
        invalid, expected_fields=SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
        schema_version=SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION,
    )
    draft = tmp_path / "second/invalid-candidate.json"
    _write_unsigned_document(draft, invalid_document)
    validation = controller.validate_live_start_candidate(session_root=second.run_root, draft_path=draft)
    assert validation.to_value()["status"] == "revision_required"
    assert validation.to_value()["findings"] == ["starter_candidate_card_dispositions_invalid"]
    with pytest.raises(SessionConflictError, match="live_start_review_approval_required"):
        controller.finalize_live_start(session_root=second.run_root)
    rejected = load_live_start_session(second.run_root)
    assert rejected.revisions_used == 1
    assert rejected.apply_invocation_sha256 is None
    assert rejected.publication_binding is None
    assert rejected.output_child_binding is None
    assert not (second.run_root / "receipts/apply_invocation.json").exists()
    assert _tree_bytes(fixture.profile.runtime_root) == runtime_before
    assert _tree_bytes(fixture.profile.output_base_root) == output_before
    assert (output / "current.json").read_bytes() == current_before
    assert resolve_current_package(output) == old_package
    assert controller.resume_live_start(session_root=first.run_root).summary.canonical_json == first_result.summary.canonical_json
