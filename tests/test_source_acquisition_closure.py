from copy import deepcopy
from dataclasses import FrozenInstanceError
import hashlib
import json
from types import SimpleNamespace

import pytest

from hsconfig.package_domain import PolicyProfile
from hsconfig.commands.source_workflow import source_acquire_payload
from hsconfig.source_acquisition import collect_public_source_records
from hsconfig.source_acquisition_closure import (
    build_acquisition_closure,
    freeze_source_bundle,
)
from hsconfig.source_acquisition_provenance import (
    FIXTURE_MAP,
    build_acquisition_provenance,
)
from hsconfig.source_research_manifest import build_source_research_manifest


def _policy_profile() -> PolicyProfile:
    rules = b'[{"claim_kind":"mulligan_keep","source_family":"guide"}]'
    return PolicyProfile(
        policy_id="source-policy-2026",
        version=1,
        effective_date="2026-07-29",
        content_sha256=f"sha256:{hashlib.sha256(rules).hexdigest()}",
        rules_canonical_json=rules,
    )


def _deck_identity() -> dict[str, object]:
    return {
        "deck_name": "CuteWarrior",
        "deck_code": "AAEBA-raw-secret-deck-code",
        "deck_fingerprint": "sha256:cute-warrior",
    }


def _policy_provenance(policy: PolicyProfile) -> dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "version": policy.version,
        "effective_date": policy.effective_date,
        "content_sha256": policy.content_sha256,
    }


def _manifest(policy: PolicyProfile) -> dict[str, object]:
    return {
        "deck_name": "CuteWarrior",
        "deck_fingerprint": "sha256:cute-warrior",
        "research_date": "2026-07-29",
        "attempt_id": "acquisition-cute-warrior-20260729",
        "attempted_queries": ["Cute Warrior Wild guide"],
        "checked_dossier": True,
        "policy_id": policy.policy_id,
        "policy_sha256": policy.content_sha256,
        "policy": _policy_provenance(policy),
    }


def _negative_report(policy: PolicyProfile) -> dict[str, object]:
    return {
        "deck_name": "CuteWarrior",
        "deck_fingerprint": "sha256:cute-warrior",
        "attempt_id": "acquisition-cute-warrior-20260729",
        "attempted_at": "2026-07-29",
        "attempted_urls": ["https://example.test/cute-warrior-guide"],
        "attempts": [
            {
                "source_identity": "https://example.test/cute-warrior-guide",
                "outcome": "not_found",
                "reason_code": "http_status_404",
            }
        ],
        "checked_dossier": True,
        "policy_id": policy.policy_id,
        "policy_sha256": policy.content_sha256,
        "policy": _policy_provenance(policy),
    }


def _canonical_evidence_id(source_identity: str, content_sha256: str) -> str:
    payload = f"{source_identity.strip()}\0{content_sha256}"
    return f"evidence:{hashlib.sha256(payload.encode()).hexdigest()}"


def _positive_record() -> dict[str, object]:
    claim_text = "Keep Town Crier in the opening hand."
    source_url = "https://example.test/cute-warrior-guide"
    provenance = build_acquisition_provenance(
        mode=FIXTURE_MAP,
        content=claim_text,
    )
    evidence_id = _canonical_evidence_id(
        source_url,
        provenance["content_sha256"],
    )
    return {
        "evidence_id": evidence_id,
        "source_id": "source:cute-warrior-guide",
        "source_identity": source_url,
        "source_url": source_url,
        "as_of_date": "2026-07-29",
        "claim_kind": "mulligan_keep",
        "claim_text": claim_text,
        "content_sha256": provenance["content_sha256"],
        "acquisition_provenance": provenance,
        "local_cache_path": r"C:\private\research\cute-warrior.html",
        "deck_code": "AAEBA-raw-secret-deck-code",
    }


def test_negative_search_closes_acquisition_without_guide_authority() -> None:
    policy = _policy_profile()
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=_negative_report(policy),
        source_records=(),
        policy_profile=policy,
    )

    assert closure.status == "closed_negative_search"
    assert closure.negative_search_documented is True
    assert closure.successful_evidence_ids == ()
    assert closure.attempted_urls
    assert closure.failed_attempts
    assert closure.checked_dossier is True


def test_closure_is_immutable_and_content_addressed() -> None:
    policy = _policy_profile()
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=_negative_report(policy),
        source_records=(),
        policy_profile=policy,
    )

    with pytest.raises(FrozenInstanceError):
        closure.status = "open"  # type: ignore[misc]
    assert closure.content_sha256.startswith("sha256:")
    assert len(closure.content_sha256) == 71


@pytest.mark.parametrize(
    ("target", "field", "replacement"),
    [
        ("manifest", "deck_fingerprint", "sha256:other-deck"),
        ("report", "deck_fingerprint", "sha256:other-deck"),
        ("manifest", "research_date", "2026-07-28"),
        ("report", "attempted_at", "2026-07-28"),
        ("report", "attempt_id", "other-attempt"),
        ("manifest", "attempted_queries", []),
        ("report", "attempted_urls", []),
        ("report", "attempts", []),
        ("manifest", "checked_dossier", False),
        ("report", "checked_dossier", False),
        ("manifest", "policy_id", "other-policy"),
        ("report", "policy_sha256", "sha256:" + ("0" * 64)),
    ],
)
def test_negative_search_stays_open_when_required_binding_is_missing_or_mismatched(
    target: str,
    field: str,
    replacement: object,
) -> None:
    policy = _policy_profile()
    manifest = _manifest(policy)
    report = _negative_report(policy)
    (manifest if target == "manifest" else report)[field] = replacement

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=manifest,
        acquisition_report=report,
        source_records=(),
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.negative_search_documented is False


def test_unrecorded_attempt_outcome_stays_open() -> None:
    policy = _policy_profile()
    report = _negative_report(policy)
    report["attempted_urls"] = [
        "https://example.test/cute-warrior-guide",
        "https://example.test/cute-warrior-mulligan",
    ]

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=(),
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.negative_search_documented is False


def test_attempt_timestamp_must_match_the_normalized_research_date() -> None:
    policy = _policy_profile()
    report = _negative_report(policy)
    report["attempts"][0]["attempted_at"] = "2026-07-28T23:59:59Z"

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=(),
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.negative_search_documented is False


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("version", 2),
        ("effective_date", "2026-07-30"),
    ],
)
def test_matching_manifest_and_report_cannot_rebind_packaged_policy_provenance(
    field: str,
    replacement: object,
) -> None:
    policy = _policy_profile()
    manifest = _manifest(policy)
    report = _negative_report(policy)
    manifest["policy"][field] = replacement
    report["policy"][field] = replacement

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=manifest,
        acquisition_report=report,
        source_records=(),
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.negative_search_documented is False


def test_successful_acquisition_closes_only_with_positive_evidence_ids() -> None:
    policy = _policy_profile()
    record = _positive_record()
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_url"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    assert closure.status == "closed_with_evidence"
    assert closure.negative_search_documented is False
    assert closure.successful_evidence_ids == (record["evidence_id"],)
    assert closure.failed_attempts == ()

    missing_id = deepcopy(record)
    missing_id["evidence_id"] = ""
    open_closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[missing_id],
        policy_profile=policy,
    )
    assert open_closure.status == "open"
    assert open_closure.successful_evidence_ids == ()


@pytest.mark.parametrize(
    "invented_evidence_id",
    [
        "not-a-typed-id",
        "evidence:" + ("0" * 64),
    ],
)
def test_matching_caller_invented_evidence_ids_cannot_self_authorize(
    invented_evidence_id: str,
) -> None:
    policy = _policy_profile()
    record = _positive_record()
    record["evidence_id"] = invented_evidence_id
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": invented_evidence_id,
        }
    ]

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.successful_evidence_ids == ()


def test_positive_evidence_id_requires_canonical_acquisition_lineage() -> None:
    policy = _policy_profile()
    record = _positive_record()
    record["acquisition_provenance"] = build_acquisition_provenance(
        mode=FIXTURE_MAP,
        content="different source bytes",
    )
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]

    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    assert closure.status == "open"
    assert closure.successful_evidence_ids == ()


def test_frozen_bundle_is_deterministic_portable_and_fully_bound() -> None:
    policy = _policy_profile()
    record = _positive_record()
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_url"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    first = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record],
        policy_profile=policy,
    )
    second = freeze_source_bundle(
        deck_identity=dict(reversed(list(_deck_identity().items()))),
        closure=closure,
        source_records=[dict(reversed(list(record.items())))],
        policy_profile=policy,
    )

    assert first == second
    assert first["deck"] == {
        "name": "CuteWarrior",
        "fingerprint": "sha256:cute-warrior",
    }
    assert first["authority"] == "diagnostic_only"
    assert first["apply_blocking"] is False
    assert first["claims"] == [
        {
            "evidence_id": record["evidence_id"],
            "source_id": "source:cute-warrior-guide",
            "policy_id": None,
            "as_of_date": "2026-07-29",
            "claim_kind": "mulligan_keep",
            "text": "Keep Town Crier in the opening hand.",
            "content_sha256": record["content_sha256"],
        }
    ]
    serialized = json.dumps(first, sort_keys=True)
    assert r"C:\private" not in serialized
    assert "AAEBA-raw-secret-deck-code" not in serialized
    assert first["content_sha256"].startswith("sha256:")


def test_frozen_bundle_sorts_claims_by_every_serialized_field() -> None:
    policy = _policy_profile()
    record = _positive_record()
    claim_base = {
        "claim_kind": "mulligan_keep",
        "claim_text": "Keep Town Crier.",
    }
    first_claim = {
        **claim_base,
        "as_of_date": "2026-07-28",
        "content_sha256": "sha256:" + hashlib.sha256(b"first").hexdigest(),
    }
    second_claim = {
        **claim_base,
        "as_of_date": "2026-07-29",
        "content_sha256": "sha256:" + hashlib.sha256(b"second").hexdigest(),
    }
    record["claims"] = [first_claim, second_claim]
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    forward = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record],
        policy_profile=policy,
    )
    reversed_record = deepcopy(record)
    reversed_record["claims"] = list(reversed(reversed_record["claims"]))
    reverse = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[reversed_record],
        policy_profile=policy,
    )

    assert forward == reverse
    assert forward["content_sha256"] == reverse["content_sha256"]


def test_frozen_bundle_canonically_deduplicates_projected_claims() -> None:
    policy = _policy_profile()
    record = _positive_record()
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_text": "Keep Town Crier.",
        "as_of_date": "2026-07-29",
        "content_sha256": "sha256:" + hashlib.sha256(b"claim").hexdigest(),
    }
    record["claims"] = [claim, deepcopy(claim)]
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    bundle = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record],
        policy_profile=policy,
    )

    assert len(bundle["claims"]) == 1


def test_frozen_bundle_canonically_deduplicates_projected_sources() -> None:
    policy = _policy_profile()
    record = _positive_record()
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    bundle = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record, deepcopy(record)],
        policy_profile=policy,
    )

    assert len(bundle["sources"]) == 1


def test_frozen_bundle_fails_closed_on_incomplete_claim_binding() -> None:
    policy = _policy_profile()
    record = _positive_record()
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_url"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )
    incomplete = deepcopy(record)
    incomplete["claim_kind"] = ""

    with pytest.raises(ValueError, match="source_claim_binding_incomplete"):
        freeze_source_bundle(
            deck_identity=_deck_identity(),
            closure=closure,
            source_records=[incomplete],
            policy_profile=policy,
        )


def test_frozen_bundle_can_keep_bound_source_evidence_without_adopting_a_claim() -> None:
    policy = _policy_profile()
    record = _positive_record()
    del record["claim_kind"]
    del record["claim_text"]
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_url"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    bundle = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record],
        policy_profile=policy,
    )

    assert bundle["claims"] == []
    assert bundle["sources"] == [
        {
            "evidence_id": record["evidence_id"],
            "source_id": "source:cute-warrior-guide",
            "policy_id": None,
            "as_of_date": "2026-07-29",
            "content_sha256": record["content_sha256"],
        }
    ]


def test_frozen_bundle_accepts_the_serialized_policy_profile_mapping() -> None:
    policy = _policy_profile()
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=_negative_report(policy),
        source_records=(),
        policy_profile=policy,
    )

    bundle = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=(),
        policy_profile={
            "policy_id": policy.policy_id,
            "version": policy.version,
            "effective_date": policy.effective_date,
            "content_sha256": policy.content_sha256,
        },
    )

    assert bundle["policy"]["policy_id"] == policy.policy_id
    assert bundle["policy"]["content_sha256"] == policy.content_sha256


def test_frozen_bundle_rejects_policy_rebinding_after_closure() -> None:
    policy = _policy_profile()
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=_negative_report(policy),
        source_records=(),
        policy_profile=policy,
    )

    with pytest.raises(ValueError, match="source_bundle_closure_binding_mismatch"):
        freeze_source_bundle(
            deck_identity=_deck_identity(),
            closure=closure,
            source_records=(),
            policy_profile={
                "policy_id": policy.policy_id,
                "version": policy.version + 1,
                "effective_date": policy.effective_date,
                "content_sha256": "sha256:" + ("0" * 64),
            },
        )


@pytest.mark.parametrize(
    "absolute_path",
    [
        "/etc/hsconfig/source.txt",
        "/root/hsconfig/source.txt",
        "/opt/hsconfig/source.txt",
        "/srv/hsconfig/source.txt",
        "/workspace/hsconfig/source.txt",
        "/custom/absolute/source.txt",
        r"C:\hsconfig\source.txt",
        "D:/hsconfig/source.txt",
        r"\\server\share\source.txt",
        r"\\?\C:\hsconfig\source.txt",
        r"\\.\C:\hsconfig\source.txt",
    ],
)
def test_frozen_bundle_rejects_absolute_paths_in_every_projected_string(
    absolute_path: str,
) -> None:
    policy = _policy_profile()
    record = _positive_record()
    record["claim_text"] = f"Source notes: {absolute_path}"
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    with pytest.raises(ValueError, match="source_bundle_not_portable"):
        freeze_source_bundle(
            deck_identity=_deck_identity(),
            closure=closure,
            source_records=[record],
            policy_profile=policy,
        )


def test_frozen_bundle_allows_urls_and_ordinary_slash_text() -> None:
    policy = _policy_profile()
    record = _positive_record()
    record["claim_text"] = (
        "See https://example.test/guides/cute-warrior and use attack/weapon "
        "sequencing; keep / discard language is ordinary prose."
    )
    report = _negative_report(policy)
    report["attempts"] = [
        {
            "source_identity": record["source_identity"],
            "outcome": "acquired",
            "evidence_id": record["evidence_id"],
        }
    ]
    closure = build_acquisition_closure(
        deck_identity=_deck_identity(),
        research_manifest=_manifest(policy),
        acquisition_report=report,
        source_records=[record],
        policy_profile=policy,
    )

    bundle = freeze_source_bundle(
        deck_identity=_deck_identity(),
        closure=closure,
        source_records=[record],
        policy_profile=policy,
    )

    assert bundle["claims"][0]["text"] == record["claim_text"]


def test_cute_warrior_manifest_has_human_search_alias() -> None:
    manifest = build_source_research_manifest(
        deck_name="CuteWarrior",
        deck_identity={
            "deck_name": "CuteWarrior",
            "deck_code_hash": "sha256:cute",
            "cards": [],
        },
        candidate_archetypes={"primary_archetype": "tempo_pressure"},
    )

    assert manifest["search_aliases"] == ["CuteWarrior", "Cute Warrior"]


def test_manifest_and_acquisition_report_share_exact_attempt_policy_binding() -> None:
    policy = _policy_profile()
    deck_identity = {
        "deck_name": "CuteWarrior",
        "deck_fingerprint": "sha256:cute-warrior",
        "deck_code_hash": "sha256:cute",
        "cards": [],
    }
    manifest = build_source_research_manifest(
        deck_name="CuteWarrior",
        deck_identity=deck_identity,
        candidate_archetypes={"primary_archetype": "tempo_pressure"},
        current_date="2026-07-29",
        attempted_queries=["2026 Wild Cute Warrior guide mulligan"],
        checked_dossier=True,
        policy_profile=policy,
    )
    acquired = collect_public_source_records(
        deck_name="CuteWarrior",
        deck_identity=deck_identity,
        source_urls=["https://example.test/cute-warrior-guide"],
        current_date="2026-07-29",
        fetcher=lambda _url, _timeout: (404, "text/plain", b"not found"),
        resolver=lambda _hostname: ["93.184.216.34"],
        checked_dossier=True,
        policy_profile=policy,
    )
    report = acquired["source_acquisition_report"]

    assert manifest["deck_fingerprint"] == report["deck_fingerprint"]
    assert manifest["research_date"] == report["attempted_at"] == "2026-07-29"
    assert manifest["attempt_id"] == report["attempt_id"]
    assert manifest["policy_id"] == report["policy_id"] == policy.policy_id
    assert (
        manifest["policy_sha256"]
        == report["policy_sha256"]
        == policy.content_sha256
    )
    assert manifest["policy"] == report["policy"] == _policy_provenance(policy)
    assert report["attempts"] == [
        {
            "source_identity": "https://example.test/cute-warrior-guide",
            "outcome": "not_found",
            "reason_code": "http_status_404",
            "attempted_at": "2026-07-29",
        }
    ]


def test_source_acquire_writes_diagnostic_closure_and_frozen_bundle(tmp_path) -> None:
    cards_path = tmp_path / "cards.json"
    cards_path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "TEST_001",
                        "name": "Town Crier",
                        "count": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page_path = tmp_path / "cute-warrior.html"
    page_path.write_text(
        """
        <html><head><title>CuteWarrior guide</title></head>
        <body><main>CuteWarrior guide. Keep Town Crier in the mulligan.</main></body>
        </html>
        """,
        encoding="utf-8",
    )
    source_url = "https://example.test/cute-warrior-guide"
    fixture_map_path = tmp_path / "fixture-map.json"
    fixture_map_path.write_text(
        json.dumps({source_url: str(page_path)}),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    payload, status = source_acquire_payload(
        SimpleNamespace(
            deck_name="CuteWarrior",
            deck_code="AAEBA-raw-secret-deck-code",
            cards_json=str(cards_path),
            allow_placeholder=False,
            source_url=[source_url],
            source_fixture_url_map_json=str(fixture_map_path),
            source_fetch_timeout_seconds=6.0,
            candidate_registry_url_count=0,
            current_date="2026-07-29",
            out=str(out),
            json=True,
        )
    )

    closure = json.loads(
        (out / "source_acquisition_closure.json").read_text(encoding="utf-8")
    )
    bundle = json.loads(
        (out / "frozen_source_bundle.json").read_text(encoding="utf-8")
    )
    assert status == 0
    assert payload["source_acquisition_closure"]["status"] == "closed_with_evidence"
    assert closure["status"] == "closed_with_evidence"
    assert bundle["authority"] == "diagnostic_only"
    assert bundle["apply_blocking"] is False
    assert bundle["sources"][0]["evidence_id"].startswith("evidence:")
    assert "AAEBA-raw-secret-deck-code" not in json.dumps(bundle, sort_keys=True)
    assert payload["frozen_source_bundle_sha256"] == bundle["content_sha256"]
