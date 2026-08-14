from dataclasses import fields, replace
from pathlib import Path

import pytest

from hsconfig.package_domain import (
    BotDelegationModel,
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    EvidenceAuthority,
    EvidenceLane,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    LayeredEvidenceContract,
    MulliganPlanModel,
    MulliganRuleModel,
    MulliganSuppressionModel,
    RuntimeSurfaceDecision,
    RuntimeSurfacePlan,
    disposition_ledger_content_sha256,
    globalvalues_baseline_sha256,
    globalvalues_decision_ledger_content_sha256,
)
from hsconfig.package_model import (
    PackageArtifact,
    PackageModel,
    RenderedPackage,
    build_runtime_surface_plan,
    content_root_sha256,
)


def test_package_artifact_is_frozen_slotted_and_hashes_content() -> None:
    artifact = PackageArtifact.from_content(relative_path="card.json", content=b"abc")

    assert artifact.size == 3
    assert artifact.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hasattr(PackageArtifact, "__slots__")
    with pytest.raises((AttributeError, TypeError)):
        artifact.relative_path = Path("other.json")


def test_package_artifact_exposes_only_verified_public_fields() -> None:
    assert tuple(field.name for field in fields(PackageArtifact)) == (
        "relative_path", "content", "size", "sha256",
    )
    with pytest.raises(ValueError, match="package_artifact_size_mismatch"):
        PackageArtifact("card.json", b"abc", 0, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    with pytest.raises(ValueError, match="package_artifact_digest_mismatch"):
        PackageArtifact("card.json", b"abc", 3, "0" * 64)


@pytest.mark.parametrize("size", [True, 3.0, "3", -1])
def test_package_artifact_requires_a_nonnegative_exact_integer_size(
    size: object,
) -> None:
    with pytest.raises(ValueError, match="package_artifact_size_invalid"):
        PackageArtifact(
            "card.json",
            b"abc",
            size,  # type: ignore[arg-type]
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        )


def test_package_artifact_accepts_verified_zero_size_for_empty_content() -> None:
    artifact = PackageArtifact(
        "empty.bin",
        b"",
        0,
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855",
    )

    assert artifact.size == 0


@pytest.mark.parametrize("relative_path", [Path("/absolute.json"), Path("../escape.json"), Path("folder\\file.json")])
def test_package_artifact_rejects_unsafe_relative_paths(relative_path: Path) -> None:
    with pytest.raises(ValueError):
        PackageArtifact.from_content(relative_path=str(relative_path), content=b"abc")


def test_content_root_is_sorted_and_records_path_size_and_digest() -> None:
    artifacts = (
        PackageArtifact.from_content(relative_path="b.json", content=b"b"),
        PackageArtifact.from_content(relative_path="a.json", content=b"a"),
    )

    assert content_root_sha256(artifacts) == (
        "b6ca8c44cb01c53dcafc45db2e003c4458f196d5165bbdb40eac09ac72d0d922"
    )


def test_mulligan_plan_rejects_noncanonical_and_unstable_rows() -> None:
    with pytest.raises(ValueError, match="canonical_json_required"):
        MulliganRuleModel(
            card_id="A",
            selector_kind="card",
            selector_canonical_json=b'{"card": "A"}',
            action="hold",
            condition_canonical_json=b'"*"',
            reason="guide",
            confidence="high",
            source_claim_ids=("c1",),
        )


def test_mulligan_plan_rejects_a_card_that_is_ruled_and_delegated() -> None:
    rule = MulliganRuleModel(
        card_id="A",
        selector_kind="card",
        selector_canonical_json=b'{"card":"A"}',
        action="hold",
        condition_canonical_json=b'"*"',
        reason="guide",
        confidence="high",
        source_claim_ids=("c1",),
    )
    delegation = BotDelegationModel(
        card_id="A",
        evidence_lane="E",
        policy_id="BOT_NATIVE_PRE_RUN",
        reason_code="native",
    )

    with pytest.raises(ValueError, match="mulligan_card_ruled_and_delegated"):
        MulliganPlanModel(
            deck_name="Deck",
            rules=(rule,),
            suppressed=(),
            bot_delegated=(delegation,),
            merged_duplicate_rule_count=0,
        )


def test_runtime_surface_plan_requires_the_exact_core_paths() -> None:
    with pytest.raises(ValueError, match="runtime_surface_core_path_invalid"):
        RuntimeSurfacePlan(
            surfaces=(
                RuntimeSurfaceDecision(
                    family="Mulligan",
                    relative_path="Mulligan.json",
                    owner="mulligan",
                    decision_ids=(),
                ),
                RuntimeSurfaceDecision(
                    family="GlobalValues",
                    relative_path="Other.json",
                    owner="globalvalues",
                    decision_ids=(),
                ),
            )
        )


@pytest.mark.parametrize("path", ["folder//card.json", "./card.json", "../card.json"])
def test_runtime_surface_decision_rejects_noncanonical_paths(path: str) -> None:
    with pytest.raises(ValueError, match="runtime_surface_path_invalid"):
        RuntimeSurfaceDecision(
            family="CardID",
            relative_path=path,
            owner="cardid",
            decision_ids=("card:CARD_A",),
        )


def test_combo_is_fail_closed_without_a_typed_payload_source() -> None:
    model = package_model()
    with pytest.raises(ValueError, match="combo_typed_payload_unavailable"):
        build_runtime_surface_plan(
            mulligan_plan=model.mulligan_plan,
            globalvalues_ledger=model.globalvalues_ledger,
            disposition_ledger=model.disposition_ledger,
            combo_decision_ids=("claim-card",),
        )


def test_runtime_surface_plan_uses_canonical_cross_model_authorization_ids() -> None:
    plan = package_model().runtime_surface_plan

    assert {
        surface.relative_path: surface.decision_ids for surface in plan.surfaces
    } == {
        "CARD_A.json": ("card:CARD_A",),
        "GlobalValues.json": ("globalvalues:HeroValue",),
        "Mulligan.json": ("mulligan:claim-mulligan",),
    }


def test_globalvalues_ledger_preserves_registry_order_while_refs_sort_separately() -> None:
    registry_order = (
        "GameCardId",
        "ConfigComment",
        "FirstTurnValueWeight",
        "SecondTurnValueWeight",
        "MyHeroPowerValue",
        "GlobalMinionAttack",
        "GlobalMinionIntrinsicValue",
        "MyWeaponValue",
        "LowHpBoardValuePenalty",
        "OpponentSpecificMatchupTuning",
        "PostApplyRegressionTuning",
        "EnemyHeroPowerValue",
        "EnemyWeaponValue",
    )
    expected_references = (
        "globalvalues:ConfigComment",
        "globalvalues:EnemyHeroPowerValue",
        "globalvalues:EnemyWeaponValue",
        "globalvalues:FirstTurnValueWeight",
        "globalvalues:GameCardId",
        "globalvalues:GlobalMinionAttack",
        "globalvalues:GlobalMinionIntrinsicValue",
        "globalvalues:LowHpBoardValuePenalty",
        "globalvalues:MyHeroPowerValue",
        "globalvalues:MyWeaponValue",
        "globalvalues:OpponentSpecificMatchupTuning",
        "globalvalues:PostApplyRegressionTuning",
        "globalvalues:SecondTurnValueWeight",
    )
    model = package_model()
    decisions = tuple(
        GlobalValueDecision(
            deck_fingerprint="fingerprint",
            key=key,
            kind=GlobalValueDecisionKind.COPY_BASELINE,
            baseline_canonical_json=b'"baseline"',
            emitted_canonical_json=b'"baseline"',
            authority_id="baseline",
            claim_ids=(),
            reason="fixture",
        )
        for key in registry_order
    )
    ledger = replace(
        model.globalvalues_ledger,
        baseline_sha256=globalvalues_baseline_sha256(decisions),
        decisions=decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            decisions
        ),
    )

    plan = build_runtime_surface_plan(
        mulligan_plan=model.mulligan_plan,
        globalvalues_ledger=ledger,
        disposition_ledger=model.disposition_ledger,
        combo_decision_ids=(),
    )
    references = next(
        surface.decision_ids
        for surface in plan.surfaces
        if surface.family == "GlobalValues"
    )

    assert tuple(decision.key for decision in ledger.decisions) == registry_order
    assert references == expected_references


def test_globalvalues_ledger_rejects_an_identical_duplicate_key() -> None:
    model = package_model()
    decision = model.globalvalues_ledger.decisions[0]

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_key_duplicate",
    ):
        replace(
            model.globalvalues_ledger,
            decisions=(decision, decision),
        )


def test_globalvalues_ledger_rejects_a_conflicting_duplicate_key() -> None:
    model = package_model()
    decision = model.globalvalues_ledger.decisions[0]
    conflicting = replace(
        decision,
        kind=GlobalValueDecisionKind.AUTHORIZED_OVERLAY,
        emitted_canonical_json=(
            b'{"values":[{"condition":"*","value":"2"}]}'
        ),
        authority_id="claim-overlay",
        claim_ids=("claim-overlay",),
        reason="conflicting fixture",
    )

    with pytest.raises(
        ValueError,
        match="globalvalues_decision_key_duplicate",
    ):
        replace(
            model.globalvalues_ledger,
            decisions=(decision, conflicting),
        )


def test_globalvalues_ledger_rejects_an_empty_decision_key() -> None:
    model = package_model()

    with pytest.raises(
        ValueError,
        match="globalvalue_key_invalid",
    ):
        replace(
            model.globalvalues_ledger.decisions[0],
            key="",
        )


@pytest.mark.parametrize(
    ("relative_path", "decision_ids", "error"),
    [
        (
            "GlobalValues.json",
            ("globalvalues:Missing",),
            "runtime_surface_authorization_mismatch",
        ),
        (
            "Mulligan.json",
            ("mulligan:missing",),
            "runtime_surface_authorization_mismatch",
        ),
        (
            "CARD_A.json",
            ("card:CARD_B",),
            "runtime_surface_cardid_identity_mismatch",
        ),
    ],
)
def test_package_model_rejects_dangling_or_mismatched_surface_ids(
    relative_path: str,
    decision_ids: tuple[str, ...],
    error: str,
) -> None:
    model = package_model()
    surfaces = tuple(
        replace(surface, decision_ids=decision_ids)
        if surface.relative_path == relative_path
        else surface
        for surface in model.runtime_surface_plan.surfaces
    )

    with pytest.raises(ValueError, match=error):
        replace(
            model,
            runtime_surface_plan=RuntimeSurfacePlan(surfaces=surfaces),
        )


def test_package_model_rejects_a_direct_suppressed_cardid_surface() -> None:
    model = package_model()
    suppressed = CardDispositionRow(
        deck_fingerprint="fingerprint",
        composite_card_key="CARD_B",
        zone="main_deck",
        official_semantics_canonical_json=b'{"GameCardId":"CARD_B"}',
        authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
        evidence_ids=("evidence-card",),
        claim_ids=(),
        physical_owner="CARD_B",
        disposition=CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
        runtime_paths=(),
        reason_code="suppressed",
    )
    cards = (*model.disposition_ledger.cards, suppressed)
    ledger = replace(
        model.disposition_ledger,
        cards=cards,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=model.disposition_ledger.deck_fingerprint,
            cards=cards,
            claims=model.disposition_ledger.claims,
        ),
    )
    direct_plan = RuntimeSurfacePlan(
        surfaces=tuple(
            sorted(
                (
                    *model.runtime_surface_plan.surfaces,
                    RuntimeSurfaceDecision(
                        family="CardID",
                        relative_path="CARD_B.json",
                        owner="cardid",
                        decision_ids=("card:CARD_B",),
                    ),
                ),
                key=lambda surface: surface.relative_path,
            )
        )
    )

    with pytest.raises(ValueError, match="runtime_surface_authorization_mismatch"):
        replace(
            model,
            disposition_ledger=ledger,
            runtime_surface_plan=direct_plan,
        )


def test_runtime_surface_plan_rejects_cardid_path_owner_id_mismatch() -> None:
    with pytest.raises(
        ValueError,
        match="runtime_surface_cardid_identity_mismatch",
    ):
        RuntimeSurfacePlan(
            surfaces=(
                RuntimeSurfaceDecision(
                    family="CardID",
                    relative_path="CARD_A.json",
                    owner="cardid",
                    decision_ids=("card:CARD_B",),
                ),
                RuntimeSurfaceDecision(
                    family="GlobalValues",
                    relative_path="GlobalValues.json",
                    owner="globalvalues",
                    decision_ids=(),
                ),
                RuntimeSurfaceDecision(
                    family="Mulligan",
                    relative_path="Mulligan.json",
                    owner="mulligan",
                    decision_ids=(),
                ),
            )
        )


@pytest.mark.parametrize(
    ("physical_owner", "runtime_paths"),
    [
        ("CARD_B", ("CARD_A.json",)),
        ("CARD_A", ("BAD.json",)),
        ("CARD_A", ("CARD_A.json", "CARD_B.json")),
    ],
)
def test_runtime_emitted_cardid_requires_exact_path_owner_id_parity(
    physical_owner: str, runtime_paths: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match="card_disposition_runtime_path_mismatch"):
        CardDispositionRow(
            deck_fingerprint="fingerprint",
            composite_card_key="CARD_A",
            zone="main_deck",
            official_semantics_canonical_json=(
                f'{{"GameCardId":"{physical_owner}"}}'.encode("utf-8")
            ),
            authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
            evidence_ids=("evidence-card",),
            claim_ids=(),
            physical_owner=physical_owner,
            disposition=CardDisposition.RUNTIME_EMITTED,
            runtime_paths=runtime_paths,
            reason_code="fixture",
        )


def test_suppressed_cardid_cannot_retain_a_runtime_path() -> None:
    with pytest.raises(ValueError, match="card_disposition_runtime_path_forbidden"):
        CardDispositionRow(
            deck_fingerprint="fingerprint",
            composite_card_key="CARD_A",
            zone="main_deck",
            official_semantics_canonical_json=b'{"GameCardId":"CARD_A"}',
            authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
            evidence_ids=("evidence-card",),
            claim_ids=(),
            physical_owner="CARD_A",
            disposition=CardDisposition.SUPPRESSED_UNSUPPORTED_SURFACE,
            runtime_paths=("CARD_A.json",),
            reason_code="suppressed",
        )


@pytest.mark.parametrize(
    "semantics",
    [
        b"[]",
        b'{"ConfigComment":"missing identity"}',
        b'{"GameCardId":""}',
        b'{"GameCardId":"CARD_B"}',
    ],
)
def test_runtime_emitted_cardid_requires_linked_physical_owner_semantics(
    semantics: bytes,
) -> None:
    with pytest.raises(
        ValueError,
        match="card_disposition_physical_semantics_invalid",
    ):
        CardDispositionRow(
            deck_fingerprint="fingerprint",
            composite_card_key="CARD_A",
            zone="main_deck",
            official_semantics_canonical_json=semantics,
            authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
            evidence_ids=("evidence-card",),
            claim_ids=(),
            physical_owner="CARD_A",
            disposition=CardDisposition.RUNTIME_EMITTED,
            runtime_paths=("CARD_A.json",),
            reason_code="fixture",
        )


def test_mulligan_rule_rejects_missing_source_and_policy_authorization() -> None:
    with pytest.raises(ValueError, match="mulligan_rule_authorization_missing"):
        MulliganRuleModel(
            card_id="CARD_A",
            selector_kind="card",
            selector_canonical_json=b'{"card":"CARD_A"}',
            action="hold",
            condition_canonical_json=b'"*"',
            reason="fixture",
            confidence="high",
            source_claim_ids=(),
        )


def test_mulligan_refs_dedupe_shared_sources_and_prefer_explicit_claim_ids() -> None:
    model = package_model()
    mulligan = MulliganPlanModel(
        deck_name="Fixture Deck",
        rules=(
            MulliganRuleModel(
                "CARD_A",
                "card",
                b'{"card":"CARD_A"}',
                "hold",
                b'"*"',
                "fixture",
                "high",
                ("shared-source",),
            ),
            MulliganRuleModel(
                "CARD_B",
                "card",
                b'{"card":"CARD_B"}',
                "hold",
                b'"*"',
                "fixture",
                "high",
                ("shared-source",),
            ),
            MulliganRuleModel(
                "CARD_C",
                "card",
                b'{"card":"CARD_C"}',
                "hold",
                b'"*"',
                "fixture",
                "high",
                ("raw-source",),
                "canonical-claim",
            ),
            MulliganRuleModel(
                "CARD_D",
                "card",
                b'{"card":"CARD_D"}',
                "hold",
                b'"*"',
                "fixture",
                "high",
                (),
                "policy-decision",
            ),
        ),
        suppressed=(),
        bot_delegated=(),
        merged_duplicate_rule_count=0,
    )

    plan = build_runtime_surface_plan(
        mulligan_plan=mulligan,
        globalvalues_ledger=model.globalvalues_ledger,
        disposition_ledger=model.disposition_ledger,
        combo_decision_ids=(),
    )

    assert next(
        surface.decision_ids
        for surface in plan.surfaces
        if surface.family == "Mulligan"
    ) == (
        "mulligan:canonical-claim",
        "mulligan:policy-decision",
        "mulligan:shared-source",
    )


def test_mulligan_authorization_references_remain_sorted_above_100_rows() -> None:
    model = package_model()
    rules = tuple(
        MulliganRuleModel(
            card_id=f"CARD_{index:03d}",
            selector_kind="card",
            selector_canonical_json=(
                f'{{"card":"CARD_{index:03d}"}}'.encode("utf-8")
            ),
            action="hold",
            condition_canonical_json=b'"*"',
            reason="fixture",
            confidence="high",
            source_claim_ids=(f"claim-{index:03d}",),
        )
        for index in range(101)
    )
    mulligan = replace(model.mulligan_plan, rules=rules)

    plan = build_runtime_surface_plan(
        mulligan_plan=mulligan,
        globalvalues_ledger=model.globalvalues_ledger,
        disposition_ledger=model.disposition_ledger,
        combo_decision_ids=(),
    )
    references = next(
        surface.decision_ids
        for surface in plan.surfaces
        if surface.family == "Mulligan"
    )

    assert len(references) == 101
    assert references == tuple(
        f"mulligan:claim-{index:03d}" for index in range(101)
    )


def test_all_domain_tuple_fields_copy_caller_lists() -> None:
    model = package_model()
    caller_evidence_ids = ["evidence-card"]
    caller_claim_ids = ["claim-card"]
    caller_runtime_paths = ["CARD_A.json"]
    card = replace(
        model.disposition_ledger.cards[0],
        evidence_ids=caller_evidence_ids,
        claim_ids=caller_claim_ids,
        runtime_paths=caller_runtime_paths,
    )
    caller_claim_paths = ["Mulligan.json"]
    claim = ClaimDispositionRow(
        deck_fingerprint="fingerprint",
        claim_id="claim-mulligan",
        claim_kind="mulligan",
        evidence_id="evidence-card",
        disposition=ClaimDisposition.RUNTIME_EMITTED,
        runtime_paths=caller_claim_paths,
        reason_code="fixture",
    )
    caller_cards = [card]
    caller_claims = [claim]
    ledger = DispositionLedger(
        "fingerprint",
        caller_cards,
        caller_claims,
        disposition_ledger_content_sha256(
            deck_fingerprint="fingerprint",
            cards=tuple(caller_cards),
            claims=tuple(caller_claims),
        ),
    )
    caller_global_claim_ids = ["claim-global"]
    decision = replace(
        model.globalvalues_ledger.decisions[0],
        claim_ids=caller_global_claim_ids,
    )
    caller_decisions = [decision]
    globalvalues = replace(
        model.globalvalues_ledger,
        baseline_sha256=globalvalues_baseline_sha256(
            tuple(caller_decisions)
        ),
        decisions=caller_decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            tuple(caller_decisions)
        ),
    )
    caller_rule_claim_ids = ["claim-mulligan"]
    rule = replace(
        model.mulligan_plan.rules[0],
        source_claim_ids=caller_rule_claim_ids,
    )
    caller_suppression_claim_ids = ["claim-suppressed"]
    suppression = MulliganSuppressionModel(
        card_id="CARD_B",
        action="none",
        reason_code="fixture",
        source_claim_ids=caller_suppression_claim_ids,
    )
    caller_rules = [rule]
    caller_suppressions = [suppression]
    caller_delegations: list[BotDelegationModel] = []
    mulligan = MulliganPlanModel(
        "Fixture Deck",
        caller_rules,
        caller_suppressions,
        caller_delegations,
        0,
    )
    caller_authorities = [model.evidence_contract.authorities[0]]
    evidence = replace(model.evidence_contract, authorities=caller_authorities)
    caller_surface_ids = ["card:CARD_A"]
    card_surface = replace(
        next(
            surface
            for surface in model.runtime_surface_plan.surfaces
            if surface.family == "CardID"
        ),
        decision_ids=caller_surface_ids,
    )
    caller_surfaces = [
        card_surface,
        *(
            surface
            for surface in model.runtime_surface_plan.surfaces
            if surface.family != "CardID"
        ),
    ]
    caller_surfaces.sort(key=lambda surface: surface.relative_path)
    plan = RuntimeSurfacePlan(caller_surfaces)
    caller_artifacts = [
        PackageArtifact.from_content(relative_path="a.json", content=b"a")
    ]
    rendered = RenderedPackage(
        model=model,
        artifacts=caller_artifacts,
        content_root_sha256=content_root_sha256(tuple(caller_artifacts)),
    )

    caller_evidence_ids.append("later")
    caller_claim_ids.append("later")
    caller_runtime_paths.append("later.json")
    caller_claim_paths.append("later.json")
    caller_cards.clear()
    caller_claims.clear()
    caller_global_claim_ids.append("later")
    caller_decisions.clear()
    caller_rule_claim_ids.append("later")
    caller_suppression_claim_ids.append("later")
    caller_rules.clear()
    caller_suppressions.clear()
    caller_delegations.append(
        BotDelegationModel("LATER", "E", "BOT_NATIVE_PRE_RUN", "later")
    )
    caller_authorities.clear()
    caller_surface_ids.append("card:LATER")
    caller_surfaces.clear()
    caller_artifacts.clear()

    assert card.evidence_ids == ("evidence-card",)
    assert card.claim_ids == ("claim-card",)
    assert card.runtime_paths == ("CARD_A.json",)
    assert claim.runtime_paths == ("Mulligan.json",)
    assert ledger.cards == (card,)
    assert ledger.claims == (claim,)
    assert decision.claim_ids == ("claim-global",)
    assert globalvalues.decisions == (decision,)
    assert rule.source_claim_ids == ("claim-mulligan",)
    assert suppression.source_claim_ids == ("claim-suppressed",)
    assert mulligan.rules == (rule,)
    assert mulligan.suppressed == (suppression,)
    assert mulligan.bot_delegated == ()
    assert evidence.authorities == (model.evidence_contract.authorities[0],)
    assert card_surface.decision_ids == ("card:CARD_A",)
    assert len(plan.surfaces) == 3
    assert rendered.artifacts[0].relative_path == "a.json"


@pytest.mark.parametrize(
    "suppressed",
    [
        (
            MulliganSuppressionModel("B", "none", "fixture", ()),
            MulliganSuppressionModel("A", "none", "fixture", ()),
        ),
        (
            MulliganSuppressionModel("A", "none", "fixture", ()),
            MulliganSuppressionModel("A", "none", "fixture", ()),
        ),
    ],
)
def test_mulligan_suppressions_must_be_unique_sorted(
    suppressed: tuple[MulliganSuppressionModel, ...]
) -> None:
    with pytest.raises(ValueError, match="mulligan_suppression_order_unstable"):
        MulliganPlanModel("Deck", (), suppressed, (), 0)


def test_package_model_requires_mulligan_deck_identity_parity() -> None:
    model = package_model()

    with pytest.raises(ValueError, match="package_model_mulligan_identity_mismatch"):
        replace(
            model,
            mulligan_plan=replace(model.mulligan_plan, deck_name="Other Deck"),
        )


def package_model() -> PackageModel:
    mulligan = MulliganPlanModel(
        deck_name="Fixture Deck",
        rules=(
            MulliganRuleModel(
                card_id="CARD_A",
                selector_kind="card",
                selector_canonical_json=b'{"card":"CARD_A"}',
                action="hold",
                condition_canonical_json=b'"*"',
                reason="fixture",
                confidence="high",
                source_claim_ids=("claim-mulligan",),
            ),
        ),
        suppressed=(),
        bot_delegated=(),
        merged_duplicate_rule_count=0,
    )
    globalvalue_decisions = (
        GlobalValueDecision(
            deck_fingerprint="fingerprint",
            key="HeroValue",
            kind=GlobalValueDecisionKind.COPY_BASELINE,
            baseline_canonical_json=b'{"values":[{"condition":"*","value":"1"}]}',
            emitted_canonical_json=b'{"values":[{"condition":"*","value":"1"}]}',
            authority_id="baseline",
            claim_ids=(),
            reason="fixture",
        ),
    )
    globalvalues = GlobalValuesDecisionLedger(
        deck_fingerprint="fingerprint",
        baseline_sha256=globalvalues_baseline_sha256(
            globalvalue_decisions
        ),
        decisions=globalvalue_decisions,
        content_sha256=globalvalues_decision_ledger_content_sha256(
            globalvalue_decisions
        ),
    )
    disposition_cards = (
            CardDispositionRow(
                deck_fingerprint="fingerprint",
                composite_card_key="CARD_A",
                zone="main_deck",
                official_semantics_canonical_json=b'{"GameCardId":"CARD_A"}',
                authority_lane=EvidenceLane.OFFICIAL_CARD_DATA,
                evidence_ids=("evidence-card",),
                claim_ids=("claim-card",),
                physical_owner="CARD_A",
                disposition=CardDisposition.RUNTIME_EMITTED,
                runtime_paths=("CARD_A.json",),
                reason_code="fixture",
            ),
        )
    dispositions = DispositionLedger(
        deck_fingerprint="fingerprint",
        cards=disposition_cards,
        claims=(),
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint="fingerprint",
            cards=disposition_cards,
            claims=(),
        ),
    )
    evidence = LayeredEvidenceContract(
        deck_fingerprint="fingerprint",
        authorities=(
            EvidenceAuthority(
                lane=EvidenceLane.OFFICIAL_CARD_DATA,
                authority_id="evidence-card",
                source_identity="fixture",
                as_of_date="2026-07-28",
                claim_kind="card",
                content_sha256="content",
                exact_deck_fingerprint=None,
                runtime_authorized=True,
                reason="fixture",
            ),
        ),
        exact_guide_authority=False,
        layered_coverage_numerator=1,
        layered_coverage_denominator=1,
        content_sha256="evidence",
    )
    return PackageModel(
        deck_name="Fixture Deck",
        deck_fingerprint="fingerprint",
        mulligan_plan=mulligan,
        globalvalues_ledger=globalvalues,
        disposition_ledger=dispositions,
        evidence_contract=evidence,
        runtime_surface_plan=build_runtime_surface_plan(
            mulligan_plan=mulligan,
            globalvalues_ledger=globalvalues,
            disposition_ledger=dispositions,
            combo_decision_ids=(),
        ),
    )
