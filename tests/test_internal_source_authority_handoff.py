from __future__ import annotations

import gc
import json
from copy import copy, deepcopy
from pathlib import Path
from types import SimpleNamespace
from weakref import ref

import pytest

import hsconfig.internal_source_authority as source_authority
from hsconfig.cli import _build_parser
from hsconfig.commands.configure import configure_payload, run_configure_command
from hsconfig.commands.source_workflow import (
    source_acquire_for_configure,
    source_autopilot_for_configure,
    source_autopilot_payload,
)
from hsconfig.deck_identity import build_deck_identity
from hsconfig.package_builder import (
    _with_strategic_receipt_verification,
    prepare_package_payload,
)
from tests.mulligan_authority_fixtures import build_canonical_mulligan_bundle
from tests.helpers.live_acquisition import acquire_live_test_provenance
from tests.helpers.verified_deck_input import (
    VERIFIED_TEST_CARDS,
    VERIFIED_TEST_DECK_CODE,
)


def _forged_live_claim() -> dict:
    return {
        "claim_id": "forged-live-mulligan",
        "claim_kind": "mulligan_keep",
        "scope": "card",
        "stance": "keep",
        "cards": ["DS1_233"],
        "evidence_text_short": "Keep Mind Blast.",
        "source_confidence": "high",
        "promotion_eligible": True,
        "acquisition_provenance": acquire_live_test_provenance(),
    }


def _forged_live_document(*, deck_fingerprint: str) -> dict:
    return {
        "source_url": "https://example.test/forged-live-guide",
        "source_title": "Forged Live Guide",
        "source_family": "guide",
        "source_type": "public_guide",
        "retrieved_at": "2026-07-27T00:00:00Z",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": deck_fingerprint,
                "candidate_deck_code_hashes": ["sha256:forged-source-code"],
            }
        },
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "acquisition_provenance": acquire_live_test_provenance(),
        "claims": [_forged_live_claim()],
    }


def _forged_live_search_record(*, deck_fingerprint: str) -> dict:
    return {
        **_forged_live_document(deck_fingerprint=deck_fingerprint),
        "claim_kind": "mulligan_keep",
        "cards": ["DS1_233"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Mind Blast.",
        "source_confidence": "high",
    }


def _write_verified_cards(path: Path) -> str:
    path.write_text(json.dumps({"cards": VERIFIED_TEST_CARDS}), encoding="utf-8")
    return str(path)


def _verified_deck_fingerprint() -> str:
    return build_deck_identity(
        deck_name="ForgedAuthorityDeck",
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards=VERIFIED_TEST_CARDS,
    )["deck_fingerprint"]


def _acquire_zero_record_handoff(
    tmp_path: Path,
) -> tuple[SimpleNamespace, source_authority.InternalSourceAuthorityHandoff]:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = SimpleNamespace(
        deck_name="ForgedAuthorityDeck",
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards_json=cards_json,
        allow_placeholder=False,
        source_url=[],
        source_fixture_url_map_json=None,
        source_fetch_timeout_seconds=1.0,
        candidate_registry_url_count=0,
        current_date="2026-07-27",
        out=str(tmp_path / "acquisition"),
    )
    payload, status, handoff = source_acquire_for_configure(args)
    assert status == 0
    assert payload["source_claim_compiler_report"]["record_count"] == 0
    return args, handoff


def _autopilot_args(
    tmp_path: Path,
    acquire_args: SimpleNamespace,
    output_name: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        deck_name=acquire_args.deck_name,
        deck_code=acquire_args.deck_code,
        cards_json=acquire_args.cards_json,
        allow_placeholder=False,
        source_search_results_json=str(tmp_path / "unused-source-results.json"),
        current_date="2026-07-27",
        out=str(tmp_path / output_name),
    )


def _cyclic_row() -> dict:
    row: dict = {}
    row["self"] = row
    return row


def _deeply_nested_row() -> dict:
    row: dict = {}
    current = row
    for _index in range(2000):
        child: dict = {}
        current["child"] = child
        current = child
    return row


class _CopyBombList(list):
    def __deepcopy__(self, memo):
        del memo
        raise RuntimeError("copy-bomb")


def _issue_document_handoff(
    documents: list[dict] | None = None,
) -> source_authority.InternalSourceAuthorityHandoff:
    search_handoff = source_authority._issue_acquired_search_records_handoff(
        [{"source_url": "https://example.test/authority"}]
    )
    _records, lineage = source_authority._consume_acquired_search_records_handoff(
        search_handoff
    )
    return source_authority._issue_generated_source_documents_handoff(
        lineage,
        documents
        if documents is not None
        else [{"source_url": "https://example.test/authority", "claims": []}],
    )


def _assert_token_active_and_registered(
    handoff: source_authority.InternalSourceAuthorityHandoff,
    *,
    state: str,
) -> None:
    token = handoff._token
    assert token.state == state
    assert source_authority._ACTIVE_ORIGINAL_TOKENS.get(token.nonce) is token


def test_document_handoff_split_issues_consumer_scoped_one_shot_capabilities() -> None:
    documents = [{"source_url": "https://example.test/authority", "claims": []}]
    document_handoff = _issue_document_handoff(documents)

    research_handoff, prepare_handoff = (
        source_authority.split_source_documents_handoff(document_handoff)
    )

    assert research_handoff.consumer == "research"
    assert prepare_handoff.consumer == "prepare"
    with pytest.raises(ValueError, match="source_authority_handoff_replayed"):
        source_authority.split_source_documents_handoff(document_handoff)
    assert source_authority.trusted_source_documents_from_handoff(
        research_handoff,
        consumer="research",
    ) == documents
    with pytest.raises(ValueError, match="source_authority_handoff_replayed"):
        source_authority.trusted_source_documents_from_handoff(
            research_handoff,
            consumer="research",
        )
    with pytest.raises(ValueError, match="source_authority_consumer_mismatch"):
        source_authority.trusted_source_documents_from_handoff(
            prepare_handoff,
            consumer="research",
        )
    assert source_authority.trusted_source_documents_from_handoff(
        prepare_handoff,
        consumer="prepare",
    ) == documents


def test_search_handoff_copy_failure_preserves_capability_for_retry() -> None:
    records = [{"source_url": "https://example.test/authority", "tags": ["guide"]}]
    handoff = source_authority._issue_acquired_search_records_handoff(records)
    original_records = handoff.search_records
    object.__setattr__(
        handoff,
        "search_records",
        ({"source_url": records[0]["source_url"], "tags": _CopyBombList(["guide"])},),
    )

    with pytest.raises(ValueError, match="source_authority_payload_copy_failed") as exc:
        source_authority._consume_acquired_search_records_handoff(handoff)

    assert isinstance(exc.value.__cause__, RuntimeError)
    _assert_token_active_and_registered(handoff, state="active_search")
    object.__setattr__(handoff, "search_records", original_records)
    copied_records, _lineage = (
        source_authority._consume_acquired_search_records_handoff(handoff)
    )
    assert copied_records == records


def test_document_issuance_copy_failure_preserves_lineage_for_retry() -> None:
    search_handoff = source_authority._issue_acquired_search_records_handoff([])
    _records, lineage = source_authority._consume_acquired_search_records_handoff(
        search_handoff
    )
    search_token = lineage._token
    registry_before = dict(source_authority._ACTIVE_ORIGINAL_TOKENS.items())

    with pytest.raises(ValueError, match="source_authority_payload_copy_failed") as exc:
        source_authority._issue_generated_source_documents_handoff(
            lineage,
            [{"source_url": "https://example.test/authority", "claims": _CopyBombList()}],
        )

    assert isinstance(exc.value.__cause__, RuntimeError)
    assert search_token.state == "consumed_search"
    assert dict(source_authority._ACTIVE_ORIGINAL_TOKENS.items()) == registry_before
    handoff = source_authority._issue_generated_source_documents_handoff(
        lineage,
        [{"source_url": "https://example.test/authority", "claims": []}],
    )
    _assert_token_active_and_registered(handoff, state="active_document")


def test_document_split_copy_failure_preserves_capability_for_retry() -> None:
    documents = [{"source_url": "https://example.test/authority", "claims": []}]
    handoff = _issue_document_handoff(documents)
    original_documents = handoff.source_documents
    object.__setattr__(
        handoff,
        "source_documents",
        (
            {
                "source_url": documents[0]["source_url"],
                "claims": _CopyBombList(),
            },
        ),
    )

    with pytest.raises(ValueError, match="source_authority_payload_copy_failed") as exc:
        source_authority.split_source_documents_handoff(handoff)

    assert isinstance(exc.value.__cause__, RuntimeError)
    _assert_token_active_and_registered(handoff, state="active_document")
    object.__setattr__(handoff, "source_documents", original_documents)
    research_handoff, prepare_handoff = (
        source_authority.split_source_documents_handoff(handoff)
    )
    assert research_handoff.consumer == "research"
    assert prepare_handoff.consumer == "prepare"


def test_document_split_canonicalization_failure_preserves_capability_for_retry() -> None:
    handoff = _issue_document_handoff([])
    cyclic_document = _cyclic_row()
    object.__setattr__(handoff, "source_documents", (cyclic_document,))

    with pytest.raises(
        ValueError,
        match="source_authority_handoff_lineage_mismatch",
    ):
        source_authority.split_source_documents_handoff(handoff)

    _assert_token_active_and_registered(handoff, state="active_document")
    object.__setattr__(handoff, "source_documents", ())
    research_handoff, prepare_handoff = (
        source_authority.split_source_documents_handoff(handoff)
    )
    assert research_handoff.consumer == "research"
    assert prepare_handoff.consumer == "prepare"


def test_document_extraction_copy_failure_preserves_capability_for_retry() -> None:
    documents = [{"source_url": "https://example.test/authority", "claims": []}]
    document_handoff = _issue_document_handoff(documents)
    research_handoff, _prepare_handoff = (
        source_authority.split_source_documents_handoff(document_handoff)
    )
    original_documents = research_handoff.source_documents
    object.__setattr__(
        research_handoff,
        "source_documents",
        (
            {
                "source_url": documents[0]["source_url"],
                "claims": _CopyBombList(),
            },
        ),
    )

    with pytest.raises(ValueError, match="source_authority_payload_copy_failed") as exc:
        source_authority.trusted_source_documents_from_handoff(
            research_handoff,
            consumer="research",
        )

    assert isinstance(exc.value.__cause__, RuntimeError)
    _assert_token_active_and_registered(research_handoff, state="active_document")
    object.__setattr__(
        research_handoff,
        "source_documents",
        original_documents,
    )
    assert source_authority.trusted_source_documents_from_handoff(
        research_handoff,
        consumer="research",
    ) == documents


def test_prepare_rejects_caller_supplied_trusted_source_documents(
    tmp_path: Path,
) -> None:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = _build_parser().parse_args(
        [
            "prepare",
            "--deck-name",
            "ForgedAuthorityDeck",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(tmp_path / "package"),
            "--cards-json",
            cards_json,
        ]
    )
    args.trusted_source_documents = [
        _forged_live_document(deck_fingerprint=_verified_deck_fingerprint())
    ]

    with pytest.raises(
        ValueError,
        match="caller_supplied_trusted_source_documents_not_allowed",
    ):
        prepare_package_payload(args)
    assert not (tmp_path / "package").exists()


def test_source_autopilot_rejects_caller_supplied_trusted_search_records(
    tmp_path: Path,
) -> None:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = _build_parser().parse_args(
        [
            "source-autopilot",
            "--deck-name",
            "ForgedAuthorityDeck",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--cards-json",
            cards_json,
            "--source-search-results-json",
            str(tmp_path / "unused-source-search-results.json"),
            "--out",
            str(tmp_path / "source-autopilot"),
        ]
    )
    args.trusted_source_search_records = [
        _forged_live_search_record(deck_fingerprint=_verified_deck_fingerprint())
    ]

    with pytest.raises(
        ValueError,
        match="caller_supplied_trusted_source_search_records_not_allowed",
    ):
        source_autopilot_payload(args)
    assert not (tmp_path / "source-autopilot").exists()


def test_strategic_receipt_annotation_rejects_mismatched_provenance() -> None:
    bundle, deck_identity = build_canonical_mulligan_bundle(
        [
            {
                "cards": ["EX1_001"],
                "acquisition_provenance": acquire_live_test_provenance(
                    b"Canonical claim source."
                ),
            }
        ]
    )
    receipt = dict(bundle["canonical_source_receipts"][0])
    receipt["acquisition_provenance"] = acquire_live_test_provenance(
        b"Different acquired source."
    )

    annotated = _with_strategic_receipt_verification(
        bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=[receipt],
    )

    assert annotated[0]["strategic_receipt_verified"] is False


def test_search_handoff_is_single_use_and_replay_is_rejected(
    tmp_path: Path,
) -> None:
    acquire_args, handoff = _acquire_zero_record_handoff(tmp_path)
    autopilot_args = SimpleNamespace(
        deck_name=acquire_args.deck_name,
        deck_code=acquire_args.deck_code,
        cards_json=acquire_args.cards_json,
        allow_placeholder=False,
        source_search_results_json=str(tmp_path / "unused-source-results.json"),
        current_date="2026-07-27",
        out=str(tmp_path / "autopilot"),
    )

    payload, status, document_handoff = source_autopilot_for_configure(
        autopilot_args,
        handoff,
    )

    assert status == 0
    assert payload["status"] == "OK"
    assert document_handoff.stage == "verified_source_documents"
    with pytest.raises(ValueError, match="source_authority_handoff_replayed"):
        source_autopilot_for_configure(
            SimpleNamespace(
                **{
                    **vars(autopilot_args),
                    "out": str(tmp_path / "replay"),
                }
            ),
            handoff,
        )
    assert not (tmp_path / "replay").exists()
    with pytest.raises(
        ValueError,
        match="invalid_internal_source_authority_handoff_stage",
    ):
        source_autopilot_for_configure(
            SimpleNamespace(
                **{
                    **vars(autopilot_args),
                    "out": str(tmp_path / "wrong-stage"),
                }
            ),
            document_handoff,
        )
    assert not (tmp_path / "wrong-stage").exists()


def test_zero_record_handoff_cannot_be_paired_with_forged_live_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    acquire_args, search_handoff = _acquire_zero_record_handoff(tmp_path)
    _payload, _status, document_handoff = source_autopilot_for_configure(
        SimpleNamespace(
            deck_name=acquire_args.deck_name,
            deck_code=acquire_args.deck_code,
            cards_json=acquire_args.cards_json,
            allow_placeholder=False,
            source_search_results_json=str(tmp_path / "unused-source-results.json"),
            current_date="2026-07-27",
            out=str(tmp_path / "autopilot"),
        ),
        search_handoff,
    )
    _research_handoff, prepare_handoff = (
        source_authority.split_source_documents_handoff(document_handoff)
    )
    object.__setattr__(
        prepare_handoff,
        "source_documents",
        (
            _forged_live_document(
                deck_fingerprint=_verified_deck_fingerprint(),
            ),
        ),
    )
    prepare_args = _build_parser().parse_args(
        [
            "prepare",
            "--deck-name",
            acquire_args.deck_name,
            "--deck-code",
            acquire_args.deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(tmp_path / "forged-package"),
            "--cards-json",
            acquire_args.cards_json,
        ]
    )
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    with pytest.raises(
        ValueError,
        match="source_authority_handoff_lineage_mismatch",
    ):
        prepare_package_payload(
            prepare_args,
            source_authority_handoff=prepare_handoff,
        )
    assert not (tmp_path / "forged-package").exists()
    assert not (tmp_path / "runtime").exists()
    assert not (
        tmp_path
        / "forged-package"
        / "reports"
        / "guide_claim_bundle.json"
    ).exists()


def test_no_public_document_advance_api_accepts_unrelated_documents() -> None:
    assert not hasattr(source_authority, "advance_to_source_documents_handoff")


@pytest.mark.parametrize(
    ("entrypoint", "attribute"),
    [
        (configure_payload, "trusted_source_documents"),
        (configure_payload, "trusted_source_search_records"),
        (run_configure_command, "trusted_source_documents"),
        (run_configure_command, "trusted_source_search_records"),
    ],
)
def test_configure_rejects_caller_authority_before_creating_output(
    tmp_path: Path,
    entrypoint,
    attribute: str,
) -> None:
    out = tmp_path / f"{entrypoint.__name__}-{attribute}"
    args = _build_parser().parse_args(
        [
            "configure",
            "--deck-name",
            "ForgedAuthorityDeck",
            "--deck-code",
            "invalid-deck-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
        ]
    )
    setattr(args, attribute, [])

    with pytest.raises(
        ValueError,
        match=f"caller_supplied_{attribute}_not_allowed",
    ):
        entrypoint(args)
    assert not out.exists()


@pytest.mark.parametrize(
    "bad_handoff",
    [
        None,
        object(),
        SimpleNamespace(stage="verified_search_records"),
        source_authority.InternalSourceAuthorityHandoff(
            stage="verified_search_records",
            record_fingerprint="sha256:fake",
            document_fingerprint="",
            lineage_fingerprint="sha256:fake",
            search_records=(),
            source_documents=(),
            _token=object(),
        ),
    ],
)
def test_source_autopilot_for_configure_rejects_invalid_handoffs(
    tmp_path: Path,
    bad_handoff,
) -> None:
    cards_json = _write_verified_cards(tmp_path / "cards.json")
    args = SimpleNamespace(
        deck_name="ForgedAuthorityDeck",
        deck_code=VERIFIED_TEST_DECK_CODE,
        cards_json=cards_json,
        allow_placeholder=False,
        source_search_results_json=str(tmp_path / "unused-source-results.json"),
        current_date="2026-07-27",
        out=str(tmp_path / "autopilot"),
    )

    with pytest.raises(ValueError, match="invalid_internal_source_authority_handoff"):
        source_autopilot_for_configure(args, bad_handoff)
    assert not (tmp_path / "autopilot").exists()


@pytest.mark.parametrize("clone_first", [False, True])
def test_deepcopied_search_handoff_never_replays_original_authority(
    tmp_path: Path,
    clone_first: bool,
) -> None:
    acquire_args, original = _acquire_zero_record_handoff(tmp_path)
    cloned = deepcopy(original)

    if clone_first:
        with pytest.raises(
            ValueError,
            match="invalid_internal_source_authority_handoff",
        ):
            source_autopilot_for_configure(
                _autopilot_args(tmp_path, acquire_args, "clone-first"),
                cloned,
            )
        assert not (tmp_path / "clone-first").exists()

    payload, status, _document_handoff = source_autopilot_for_configure(
        _autopilot_args(tmp_path, acquire_args, "original"),
        original,
    )
    assert status == 0
    assert payload["status"] == "OK"

    if not clone_first:
        with pytest.raises(
            ValueError,
            match="invalid_internal_source_authority_handoff",
        ):
            source_autopilot_for_configure(
                _autopilot_args(tmp_path, acquire_args, "clone-after-original"),
                cloned,
            )
        assert not (tmp_path / "clone-after-original").exists()


def test_shallow_search_handoff_copy_shares_single_use_state(
    tmp_path: Path,
) -> None:
    acquire_args, original = _acquire_zero_record_handoff(tmp_path)
    shallow = copy(original)
    source_autopilot_for_configure(
        _autopilot_args(tmp_path, acquire_args, "original"),
        original,
    )

    with pytest.raises(ValueError, match="source_authority_handoff_replayed"):
        source_autopilot_for_configure(
            _autopilot_args(tmp_path, acquire_args, "shallow-replay"),
            shallow,
        )
    assert not (tmp_path / "shallow-replay").exists()


@pytest.mark.parametrize("clone_first", [False, True])
def test_deepcopied_document_handoff_never_inherits_original_authority(
    tmp_path: Path,
    clone_first: bool,
) -> None:
    acquire_args, search_handoff = _acquire_zero_record_handoff(tmp_path)
    _payload, _status, original = source_autopilot_for_configure(
        _autopilot_args(tmp_path, acquire_args, "autopilot"),
        search_handoff,
    )
    _research_handoff, original = source_authority.split_source_documents_handoff(
        original
    )
    cloned = deepcopy(original)

    if clone_first:
        with pytest.raises(
            ValueError,
            match="invalid_internal_source_authority_handoff",
        ):
            source_authority.trusted_source_documents_from_handoff(
                cloned,
                consumer="prepare",
            )

    assert source_authority.trusted_source_documents_from_handoff(
        original,
        consumer="prepare",
    ) == []

    if not clone_first:
        with pytest.raises(
            ValueError,
            match="invalid_internal_source_authority_handoff",
        ):
            source_authority.trusted_source_documents_from_handoff(
                cloned,
                consumer="prepare",
            )


@pytest.mark.parametrize(
    "invalid_row",
    [
        pytest.param({"value": object()}, id="nonserializable-object"),
        pytest.param(_cyclic_row(), id="cyclic-row"),
        pytest.param(_deeply_nested_row(), id="recursive-depth"),
    ],
)
def test_invalid_search_record_canonicalization_fails_before_output(
    tmp_path: Path,
    invalid_row: dict,
) -> None:
    acquire_args, handoff = _acquire_zero_record_handoff(tmp_path)
    object.__setattr__(handoff, "search_records", (invalid_row,))

    with pytest.raises(
        ValueError,
        match="source_authority_handoff_lineage_mismatch",
    ):
        source_autopilot_for_configure(
            _autopilot_args(tmp_path, acquire_args, "invalid-search"),
            handoff,
        )
    assert not (tmp_path / "invalid-search").exists()


@pytest.mark.parametrize(
    "invalid_document",
    [
        pytest.param({"value": object()}, id="nonserializable-object"),
        pytest.param(_cyclic_row(), id="cyclic-document"),
        pytest.param(_deeply_nested_row(), id="recursive-depth"),
    ],
)
def test_invalid_document_canonicalization_fails_before_package_output(
    tmp_path: Path,
    invalid_document: dict,
) -> None:
    acquire_args, search_handoff = _acquire_zero_record_handoff(tmp_path)
    _payload, _status, document_handoff = source_autopilot_for_configure(
        _autopilot_args(tmp_path, acquire_args, "autopilot"),
        search_handoff,
    )
    _research_handoff, prepare_handoff = (
        source_authority.split_source_documents_handoff(document_handoff)
    )
    object.__setattr__(
        prepare_handoff,
        "source_documents",
        (invalid_document,),
    )
    prepare_args = _build_parser().parse_args(
        [
            "prepare",
            "--deck-name",
            acquire_args.deck_name,
            "--deck-code",
            acquire_args.deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(tmp_path / "invalid-package"),
            "--cards-json",
            acquire_args.cards_json,
        ]
    )

    with pytest.raises(
        ValueError,
        match="source_authority_handoff_lineage_mismatch",
    ):
        prepare_package_payload(
            prepare_args,
            source_authority_handoff=prepare_handoff,
        )
    assert not (tmp_path / "invalid-package").exists()


def test_abandoned_original_token_is_not_retained(
    tmp_path: Path,
) -> None:
    _acquire_args, handoff = _acquire_zero_record_handoff(tmp_path)
    token = handoff._token
    nonce = token.nonce
    token_ref = ref(token)
    assert source_authority._ACTIVE_ORIGINAL_TOKENS.get(nonce) is token

    del token
    del handoff
    gc.collect()

    assert token_ref() is None
    assert nonce not in source_authority._ACTIVE_ORIGINAL_TOKENS
