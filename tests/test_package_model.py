from pathlib import Path

import pytest

from hsconfig.package_domain import (
    BotDelegationModel,
    CardDisposition,
    CardDispositionRow,
    DispositionLedger,
    EvidenceAuthority,
    EvidenceLane,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    LayeredEvidenceContract,
    MulliganPlanModel,
    MulliganRuleModel,
    RuntimeSurfaceDecision,
    RuntimeSurfacePlan,
)
from hsconfig.package_model import (
    PackageArtifact,
    PackageModel,
    build_runtime_surface_plan,
    content_root_sha256,
)


def test_package_artifact_is_frozen_slotted_and_hashes_content() -> None:
    artifact = PackageArtifact(relative_path=Path("card.json"), content=b"abc")

    assert artifact.size == 3
    assert artifact.sha256 == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert hasattr(PackageArtifact, "__slots__")
    with pytest.raises((AttributeError, TypeError)):
        artifact.relative_path = Path("other.json")


@pytest.mark.parametrize("relative_path", [Path("/absolute.json"), Path("../escape.json"), Path("folder\\file.json")])
def test_package_artifact_rejects_unsafe_relative_paths(relative_path: Path) -> None:
    with pytest.raises(ValueError):
        PackageArtifact(relative_path=relative_path, content=b"abc")


def test_content_root_is_sorted_and_records_path_size_and_digest() -> None:
    artifacts = (
        PackageArtifact(relative_path="b.json", content=b"b"),
        PackageArtifact(relative_path="a.json", content=b"a"),
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
    globalvalues = GlobalValuesDecisionLedger(
        deck_fingerprint="fingerprint",
        baseline_sha256="baseline",
        decisions=(
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
        ),
        content_sha256="globalvalues",
    )
    dispositions = DispositionLedger(
        deck_fingerprint="fingerprint",
        cards=(
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
        ),
        claims=(),
        content_sha256="dispositions",
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
