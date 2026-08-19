from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from hashlib import sha256
from pathlib import Path

import pytest

from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.build_context import ResolvedBuildContext
from hsconfig.build_input_catalog import (
    load_audited_build_inputs,
    load_audited_build_resource_store,
)
from hsconfig.package_request import (
    AcquisitionClosureInput,
    FrozenJsonDocument,
    GeneralPreconfigSnapshot,
    MulliganGapInput,
    PackageInvocation,
    PackageResolutionSnapshot,
    PlanOverrides,
    ResolvedPackageRequest,
)
from hsconfig.globalvalues_baseline import FALLBACK_GLOBALVALUES_BASELINE

RESOURCE_ROOT = Path("src/hsconfig/resources")
SYNTHETIC_RUNTIME_ROOT = "C:" + "/runtime"


def test_package_invocation_is_slotted_frozen_and_excludes_transport_fields() -> None:
    invocation = PackageInvocation(
        deck_code="AAECAfixture",
        runtime_root=SYNTHETIC_RUNTIME_ROOT,
        cards_json="cards.json",
        claims_json=None,
        guide_sources_json="guide_sources.json",
        plan_reports_dir=None,
        target_config_mode="preview",
        include_disposition_diagnostics=True,
        configuration_mode="CONSERVATIVE",
    )

    assert tuple(field.name for field in fields(invocation)) == (
        "deck_code",
        "runtime_root",
        "cards_json",
        "claims_json",
        "guide_sources_json",
        "plan_reports_dir",
        "target_config_mode",
        "include_disposition_diagnostics",
        "configuration_mode",
    )
    assert not hasattr(invocation, "__dict__")
    assert not {"out", "command", "json"}.intersection(
        field.name for field in fields(invocation)
    )
    with pytest.raises(FrozenInstanceError):
        invocation.deck_code = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("runtime_root", None, "package_invocation_runtime_root_invalid"),
        ("runtime_root", "", "package_invocation_runtime_root_invalid"),
        ("runtime_root", Path("runtime"), "package_invocation_runtime_root_invalid"),
        (
            "target_config_mode",
            "apply",
            "package_invocation_target_config_mode_invalid",
        ),
    ],
)
def test_package_invocation_rejects_invalid_required_runtime_values(
    field_name: str,
    value: object,
    error: str,
) -> None:
    values = {
        "deck_code": "AAECAfixture",
        "runtime_root": SYNTHETIC_RUNTIME_ROOT,
        "cards_json": None,
        "claims_json": None,
        "guide_sources_json": None,
        "plan_reports_dir": None,
        "target_config_mode": "preview",
        "include_disposition_diagnostics": False,
        "configuration_mode": "CONSERVATIVE",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=error):
        PackageInvocation(**values)  # type: ignore[arg-type]


def test_general_resolution_request_detaches_every_nested_mutable_input() -> None:
    preconfig = _general_preconfig()
    overrides = {"combo_plan": {"combos": [], "suppressed": []}}
    closure = _acquisition_closure()
    gaps = [_mulligan_gap()]
    request = ResolvedPackageRequest.from_values(
        snapshot=PackageResolutionSnapshot.from_preconfig(preconfig),
        invocation=PackageInvocation(
            deck_code="AAECAgeneral",
            runtime_root=SYNTHETIC_RUNTIME_ROOT,
            cards_json=None,
            claims_json=None,
            guide_sources_json=None,
            plan_reports_dir=None,
            target_config_mode="preview",
            include_disposition_diagnostics=False,
            configuration_mode="CONSERVATIVE",
        ),
        plan_overrides={"combo_plan_report.json": overrides["combo_plan"]},
        acquisition_closure_input=closure,
        mulligan_gap_input=gaps,
        starter_selection=None,
    )

    preconfig["deck_identity"]["cards"].append("LATER")
    overrides["combo_plan"]["combos"].append({"rule_id": "later"})
    closure["attempted_urls"].append("https://example.test/later")
    gaps[0]["reason"] = "later"

    assert request.snapshot.strict_build_context is None
    assert request.snapshot.general_preconfig is not None
    assert request.snapshot.general_preconfig.to_value()["deck_identity"] == {
        "cards": ["A", "B"],
        "deck_code_hash": sha256(b"AAECAgeneral").hexdigest(),
        "deck_fingerprint": "general-fingerprint",
        "deck_name": "Unpinned Deck",
    }
    assert request.plan_overrides.to_value() == {
        "combo_plan_report.json": {"combos": [], "suppressed": []}
    }
    assert request.acquisition_closure_input.to_value()["attempted_urls"] == [
        "https://example.test/guide"
    ]
    assert request.mulligan_gap_input.to_value() == [
        _mulligan_gap()
    ]


def test_general_request_authority_graph_rejects_all_rebinding() -> None:
    request = ResolvedPackageRequest.from_values(
        snapshot=PackageResolutionSnapshot.from_preconfig(
            _general_preconfig()
        ),
        invocation=PackageInvocation(
            deck_code="AAECAgeneral",
            runtime_root=SYNTHETIC_RUNTIME_ROOT,
            cards_json=None,
            claims_json=None,
            guide_sources_json=None,
            plan_reports_dir=None,
            target_config_mode="preview",
            include_disposition_diagnostics=False,
            configuration_mode="CONSERVATIVE",
        ),
        plan_overrides={},
        acquisition_closure_input=_acquisition_closure(),
        mulligan_gap_input=[_mulligan_gap()],
        starter_selection=None,
    )
    pending: list[object] = [request]
    seen: set[int] = set()
    authority_nodes: list[object] = []

    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if hasattr(type(value), "__dataclass_fields__"):
            authority_nodes.append(value)
            pending.extend(
                getattr(value, field.name) for field in fields(value)
            )
        elif isinstance(value, tuple):
            pending.extend(value)

    assert authority_nodes
    for node in authority_nodes:
        assert not hasattr(node, "__dict__")
        for field in fields(node):
            current = getattr(node, field.name)
            with pytest.raises((AttributeError, TypeError)):
                setattr(node, field.name, current)
            with pytest.raises((AttributeError, TypeError)):
                object.__setattr__(node, field.name, current)


def test_frozen_documents_are_canonical_and_copy_their_byte_input() -> None:
    caller_bytes = bytearray(b'{"z":1,"a":[2]}')

    document = FrozenJsonDocument.from_json_bytes(caller_bytes)
    caller_bytes[:] = b"{}"

    assert document.canonical_json == b'{"a":[2],"z":1}'
    assert document.to_value() == {"a": [2], "z": 1}
    assert not hasattr(document, "__dict__")


def test_resolution_snapshot_requires_a_frozen_general_preconfig_document() -> None:
    with pytest.raises(TypeError, match="preconfig_snapshot_invalid"):
        PackageResolutionSnapshot(  # type: ignore[arg-type]
            strict_build_context=None,
            general_preconfig={"deck": "mutable"},
        )


@pytest.mark.parametrize("value", [None, 1, "x", [], {}])
def test_general_preconfig_rejects_non_contract_values(value: object) -> None:
    with pytest.raises(ValueError, match="general_preconfig_schema_invalid"):
        PackageResolutionSnapshot.from_preconfig(value)


def test_general_preconfig_requires_captured_policy_and_baseline_sections() -> None:
    preconfig = _general_preconfig()

    snapshot = PackageResolutionSnapshot.from_preconfig(preconfig)
    assert snapshot.general_preconfig.to_value()["policy_profile"] == {}

    for field_name in (
        "policy_profile",
        "globalvalues_baseline",
        "globalvalues_baseline_receipt",
    ):
        malformed = dict(preconfig)
        del malformed[field_name]
        with pytest.raises(
            ValueError,
            match="general_preconfig_schema_invalid",
        ):
            PackageResolutionSnapshot.from_preconfig(malformed)


def test_general_preconfig_closes_incomplete_effective_baseline() -> None:
    preconfig = _general_preconfig()
    preconfig["globalvalues_baseline"] = {"GameCardId": "GlobalValues"}
    preconfig["globalvalues_baseline_receipt"] = {
        "baseline": {"GameCardId": "GlobalValues"}
    }

    value = PackageResolutionSnapshot.from_preconfig(
        preconfig
    ).general_preconfig.to_value()

    assert value["globalvalues_baseline"] == FALLBACK_GLOBALVALUES_BASELINE


def test_general_preconfig_rejects_contradictory_baseline_receipt() -> None:
    preconfig = _general_preconfig()
    preconfig["globalvalues_baseline_receipt"] = {
        "baseline": {
            "GameCardId": "GlobalValues",
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "999"}]
            },
        }
    }

    with pytest.raises(
        ValueError,
        match="globalvalues_baseline_receipt_mismatch",
    ):
        PackageResolutionSnapshot.from_preconfig(preconfig)


def test_general_request_binds_invocation_code_to_frozen_identity() -> None:
    snapshot = PackageResolutionSnapshot.from_preconfig(
        _general_preconfig()
    )

    with pytest.raises(
        ValueError,
        match="resolved_package_request_deck_code_mismatch",
    ):
        ResolvedPackageRequest.from_values(
            snapshot=snapshot,
            invocation=PackageInvocation(
                deck_code="DIFFERENT",
                runtime_root=SYNTHETIC_RUNTIME_ROOT,
                cards_json=None,
                claims_json=None,
                guide_sources_json=None,
                plan_reports_dir=None,
                target_config_mode="preview",
                include_disposition_diagnostics=False,
                configuration_mode="CONSERVATIVE",
            ),
            plan_overrides={},
            acquisition_closure_input=_acquisition_closure(),
            mulligan_gap_input=[],
            starter_selection=None,
        )


def test_acquisition_closure_accepts_the_exact_absent_open_form() -> None:
    closure = AcquisitionClosureInput.from_value(
        {
            "deck_fingerprint": "fingerprint",
            "attempt_id": "",
            "attempted_at": "",
            "attempted_urls": [],
            "successful_evidence_ids": [],
            "failed_attempts": [],
            "negative_search_documented": False,
            "checked_dossier": False,
            "policy_id": None,
            "status": "open",
            "content_sha256": "sha256:" + "0" * 64,
        }
    )

    assert closure.to_value()["status"] == "open"


def test_resolution_snapshot_requires_preconfig_and_binds_optional_strict_context() -> None:
    strict_context, _mutable_resources = _strict_context_with_mutable_resources()
    matching = GeneralPreconfigSnapshot.from_value(
        _general_preconfig(
            deck_name=strict_context.inputs.deck_name,
            deck_fingerprint=strict_context.inputs.deck_fingerprint,
            deck_code_hash=strict_context.inputs.deck_code_sha256,
        )
    )
    unrelated = GeneralPreconfigSnapshot.from_value(_general_preconfig())

    with pytest.raises(TypeError, match="preconfig_snapshot_invalid"):
        PackageResolutionSnapshot(
            general_preconfig=None,
        )
    assert PackageResolutionSnapshot(
        general_preconfig=matching,
        strict_build_context=strict_context,
    ).strict_build_context is strict_context
    with pytest.raises(
        ValueError,
        match="resolution_snapshot_strict_binding_mismatch",
    ):
        PackageResolutionSnapshot(
            strict_build_context=strict_context,
            general_preconfig=unrelated,
        )


def test_strict_resolution_context_defensively_copies_all_resource_bytes() -> None:
    context, mutable_resources = _strict_context_with_mutable_resources()
    snapshot = PackageResolutionSnapshot.from_strict(
        context,
        _general_preconfig(
            deck_name=context.inputs.deck_name,
            deck_fingerprint=context.inputs.deck_fingerprint,
            deck_code_hash=context.inputs.deck_code_sha256,
        ),
    )

    for mutable in mutable_resources:
        mutable.extend(b"changed")

    assert snapshot.general_preconfig is not None
    assert snapshot.strict_build_context is not None
    assert type(snapshot.strict_build_context.deck_cards_canonical_json) is bytes
    assert all(
        type(value) is bytes
        for value in snapshot.strict_build_context.source_bundle_canonical_json
    )
    assert not snapshot.strict_build_context.deck_cards_canonical_json.endswith(
        b"changed"
    )


def test_strict_resolution_snapshot_rejects_preconfig_deck_code_hash_mismatch() -> None:
    context, _mutable_resources = _strict_context_with_mutable_resources()

    with pytest.raises(
        ValueError,
        match="resolution_snapshot_strict_binding_mismatch",
    ):
        PackageResolutionSnapshot.from_strict(
            context,
            _general_preconfig(
                deck_name=context.inputs.deck_name,
                deck_fingerprint=context.inputs.deck_fingerprint,
                deck_code_hash="0" * 64,
            ),
        )


def test_strict_resolution_snapshot_accepts_matching_preconfig_deck_code_hash() -> None:
    context, _mutable_resources = _strict_context_with_mutable_resources()

    snapshot = PackageResolutionSnapshot.from_strict(
        context,
        _general_preconfig(
            deck_name=context.inputs.deck_name,
            deck_fingerprint=context.inputs.deck_fingerprint,
            deck_code_hash=context.inputs.deck_code_sha256,
        ),
    )

    assert snapshot.strict_build_context is context


def test_resolved_request_binds_strict_context_to_invocation_deck_code() -> None:
    context, _mutable_resources = _strict_context_with_mutable_resources()
    snapshot = PackageResolutionSnapshot.from_strict(
        context,
        _general_preconfig(
            deck_name=context.inputs.deck_name,
            deck_fingerprint=context.inputs.deck_fingerprint,
            deck_code_hash=context.inputs.deck_code_sha256,
        ),
    )

    with pytest.raises(
        ValueError,
        match="resolved_package_request_deck_code_mismatch",
    ):
        ResolvedPackageRequest.from_values(
            snapshot=snapshot,
            invocation=PackageInvocation(
                deck_code="not-the-audited-deck-code",
                runtime_root=SYNTHETIC_RUNTIME_ROOT,
                cards_json=None,
                claims_json=None,
                guide_sources_json=None,
                plan_reports_dir=None,
                target_config_mode="preview",
                include_disposition_diagnostics=False,
                configuration_mode="CONSERVATIVE",
            ),
            plan_overrides={},
            acquisition_closure_input=_acquisition_closure(),
            mulligan_gap_input=[],
            starter_selection=None,
        )


def test_resolved_request_accepts_the_matching_audited_deck_code() -> None:
    context, _mutable_resources = _strict_context_with_mutable_resources()
    snapshot = PackageResolutionSnapshot.from_strict(
        context,
        _general_preconfig(
            deck_name=context.inputs.deck_name,
            deck_fingerprint=context.inputs.deck_fingerprint,
            deck_code_hash=context.inputs.deck_code_sha256,
        ),
    )
    deck_code = next(
        row["deck_code"]
        for row in load_audited_deck_catalog()
        if row["deck_name"] == context.inputs.deck_name
    )

    request = ResolvedPackageRequest.from_values(
        snapshot=snapshot,
        invocation=PackageInvocation(
            deck_code=deck_code,
            runtime_root=SYNTHETIC_RUNTIME_ROOT,
            cards_json=None,
            claims_json=None,
            guide_sources_json=None,
            plan_reports_dir=None,
            target_config_mode="preview",
            include_disposition_diagnostics=False,
            configuration_mode="CONSERVATIVE",
        ),
        plan_overrides={},
        acquisition_closure_input=_acquisition_closure(),
        mulligan_gap_input=[],
        starter_selection=None,
    )

    assert request.snapshot.strict_build_context is context


def test_strict_resolution_context_rejects_mismatched_resource_authority() -> None:
    inputs, store = _audited_inputs_and_store()

    with pytest.raises(
        ValueError,
        match="resolved_build_deck_cards_resource_sha256_mismatch",
    ):
        ResolvedBuildContext(
            inputs=inputs,
            deck_cards_canonical_json=store.read_by_sha256(
                inputs.card_snapshot_resource_sha256
            ),
            card_snapshot_canonical_json=store.read_by_sha256(
                inputs.card_snapshot_resource_sha256
            ),
            policy_profile_canonical_json=store.read_by_sha256(
                inputs.policy_profile_resource_sha256
            ),
            evidence_contract_canonical_json=store.read_by_sha256(
                inputs.evidence_contract_resource_sha256
            ),
            source_bundle_canonical_json=tuple(
                store.read_by_sha256(digest)
                for digest in inputs.source_bundle_resource_sha256s
            ),
            general_preconfig_canonical_json=store.read_by_sha256(
                inputs.general_preconfig_resource_sha256
            ),
            acquisition_closure_canonical_json=store.read_by_sha256(
                inputs.acquisition_closure_resource_sha256
            ),
            globalvalues_baseline_canonical_json=store.read_by_sha256(
                inputs.globalvalues_baseline_resource_sha256
            ),
        )


def test_specialized_request_documents_reject_unrelated_shapes() -> None:
    with pytest.raises(ValueError, match="plan_overrides_schema_invalid"):
        PlanOverrides.from_value({"unknown.json": {}})
    with pytest.raises(ValueError, match="plan_overrides_schema_invalid"):
        PlanOverrides.from_value({"combo_plan_report.json": []})
    with pytest.raises(ValueError, match="acquisition_closure_schema_invalid"):
        AcquisitionClosureInput.from_value("closed")
    with pytest.raises(ValueError, match="mulligan_gap_schema_invalid"):
        MulliganGapInput.from_value({"card_id": "A"})


def test_resolved_request_rejects_generic_documents_in_specialized_fields() -> None:
    generic = FrozenJsonDocument.from_value({})

    with pytest.raises(
        TypeError,
        match="resolved_package_request_plan_overrides_invalid",
    ):
        ResolvedPackageRequest(
            snapshot=PackageResolutionSnapshot.from_preconfig(
                _general_preconfig()
            ),
            invocation=PackageInvocation(
                deck_code="AAECAgeneral",
                runtime_root=SYNTHETIC_RUNTIME_ROOT,
                cards_json=None,
                claims_json=None,
                guide_sources_json=None,
                plan_reports_dir=None,
                target_config_mode="preview",
                include_disposition_diagnostics=False,
                configuration_mode="CONSERVATIVE",
            ),
            plan_overrides=generic,  # type: ignore[arg-type]
            acquisition_closure_input=AcquisitionClosureInput.from_value(
                _acquisition_closure()
            ),
            mulligan_gap_input=MulliganGapInput.from_value([]),
            starter_selection=None,
        )


@pytest.mark.parametrize(
    "payload",
    [
        b'{"a":1,"a":2}',
        b'{"outer":{"a":1,"a":2}}',
    ],
)
def test_frozen_json_rejects_duplicate_object_keys(payload: bytes) -> None:
    with pytest.raises(ValueError, match="frozen_json_duplicate_key"):
        FrozenJsonDocument.from_json_bytes(payload)
    with pytest.raises(ValueError, match="frozen_json_duplicate_key"):
        FrozenJsonDocument(payload)


@pytest.mark.parametrize(
    "payload",
    [b"NaN", b"Infinity", b"-Infinity"],
)
def test_frozen_json_rejects_nonfinite_numbers(payload: bytes) -> None:
    with pytest.raises(ValueError, match="frozen_json_non_finite_number"):
        FrozenJsonDocument.from_json_bytes(payload)
    with pytest.raises(ValueError, match="frozen_json_non_finite_number"):
        FrozenJsonDocument(payload)


def _general_preconfig(
    *,
    deck_name: str = "Unpinned Deck",
    deck_fingerprint: str = "general-fingerprint",
    deck_code_hash: str | None = None,
) -> dict[str, object]:
    if deck_code_hash is None:
        deck_code_hash = sha256(b"AAECAgeneral").hexdigest()
    result: dict[str, object] = {
        "cards_payload": {},
        "deck_identity": {
            "deck_name": deck_name,
            "deck_fingerprint": deck_fingerprint,
            "cards": ["A", "B"],
        },
        "card_metadata": {},
        "semantic_report": {},
        "guide_claim_bundle": {},
        "source_claims": {},
        "research_bundle": {},
        "guide_sources_generated": None,
        "guide_builder_receipt": {},
        "deck_fingerprint": {},
        "candidate_archetypes": {},
        "identity_graph_report": {},
        "identity_gap_report": {},
        "card_data_intake_report": {},
        "source_evidence_report": {},
        "source_document_draft_report": None,
        "policy_profile": {},
        "globalvalues_baseline": dict(FALLBACK_GLOBALVALUES_BASELINE),
        "globalvalues_baseline_receipt": {
            "baseline": dict(FALLBACK_GLOBALVALUES_BASELINE)
        },
    }
    result["deck_identity"]["deck_code_hash"] = deck_code_hash  # type: ignore[index]
    return result


def _acquisition_closure() -> dict[str, object]:
    return {
        "deck_fingerprint": "fingerprint",
        "attempt_id": "acquisition:fixture",
        "attempted_at": "2026-07-30",
        "attempted_urls": ["https://example.test/guide"],
        "successful_evidence_ids": [],
        "failed_attempts": [],
        "negative_search_documented": False,
        "checked_dossier": True,
        "policy_id": "BOT_NATIVE_PRE_RUN",
        "status": "closed_with_evidence",
        "content_sha256": "sha256:" + "a" * 64,
    }


def _mulligan_gap() -> dict[str, str]:
    return {
        "target_deck_name": "Unpinned Deck",
        "target_deck_fingerprint": "fingerprint",
        "target_deck_code_hash": "sha256:" + "b" * 64,
        "card_id": "A",
        "first_missing_source_action": "find_source",
        "reason": "missing_exact_source",
    }


def _audited_inputs_and_store():
    catalog = load_audited_build_inputs(
        RESOURCE_ROOT / "audited_build_inputs.json"
    )
    store = load_audited_build_resource_store(
        RESOURCE_ROOT / "audited_build_resources.json",
        audited_inputs=catalog,
    )
    return catalog.builds[0], store


def _strict_context_with_mutable_resources():
    inputs, store = _audited_inputs_and_store()
    mutable_resources = [
        bytearray(store.read_by_sha256(inputs.deck_cards_resource_sha256)),
        bytearray(store.read_by_sha256(inputs.card_snapshot_resource_sha256)),
        bytearray(store.read_by_sha256(inputs.policy_profile_resource_sha256)),
        bytearray(store.read_by_sha256(inputs.evidence_contract_resource_sha256)),
        *(
            bytearray(store.read_by_sha256(digest))
            for digest in inputs.source_bundle_resource_sha256s
        ),
        bytearray(
            store.read_by_sha256(
                inputs.general_preconfig_resource_sha256
            )
        ),
        bytearray(
            store.read_by_sha256(
                inputs.acquisition_closure_resource_sha256
            )
        ),
        bytearray(
            store.read_by_sha256(
                inputs.globalvalues_baseline_resource_sha256
            )
        ),
    ]
    source_count = len(inputs.source_bundle_resource_sha256s)
    context = ResolvedBuildContext(
        inputs=inputs,
        deck_cards_canonical_json=mutable_resources[0],
        card_snapshot_canonical_json=mutable_resources[1],
        policy_profile_canonical_json=mutable_resources[2],
        evidence_contract_canonical_json=mutable_resources[3],
        source_bundle_canonical_json=mutable_resources[4 : 4 + source_count],
        general_preconfig_canonical_json=mutable_resources[4 + source_count],
        acquisition_closure_canonical_json=mutable_resources[
            5 + source_count
        ],
        globalvalues_baseline_canonical_json=mutable_resources[-1],
    )
    return context, mutable_resources
