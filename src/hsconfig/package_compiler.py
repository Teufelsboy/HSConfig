"""Pure package compilation from one fully resolved immutable request."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from hsconfig.card_behavior_router import (
    diagnose_card_behavior_claims,
    route_card_behavior_claims,
)
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_combo import compile_combo
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.config_readiness import (
    build_config_readiness_report,
    project_config_readiness_from_dispositions,
)
from hsconfig.combo_plan import build_typed_combo_plan
from hsconfig.configure_stages import (
    build_lowered_runtime_stage,
    build_verified_deck_stage,
    materialize_stage_value,
)
from hsconfig.disposition_ledger import (
    DispositionLedger,
    DualClosureStatus,
)
from hsconfig.evidence_contract import policy_profile_from_mapping
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.globalvalues_authority import (
    build_globalvalues_authority_matrix,
)
from hsconfig.globalvalues_decisions import (
    build_globalvalues_decision_ledger,
    canonical_globalvalues_baseline_sha256,
    normalize_globalvalues_decision_baseline,
)
from hsconfig.guide_source_depth import build_guide_source_depth_report
from hsconfig.mechanic_drift import build_mechanic_drift_report
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.package_domain import (
    ComboPlanModel,
    GlobalValuesDecisionLedger,
    MulliganPlanModel,
    _ImmutableAuthorityNode,
)
from hsconfig.package_compiler_support import (
    _build_package_disposition_ledger,
    _build_plan_input_diagnostics,
    _card_behavior_identity_links,
    _explicit_bot_delegation_claims,
    _filter_plan_reports_by_lifecycle,
    _is_internal_mulligan_policy_claim,
    _normalize_claim_conflict_report,
    _policy_mulligan_deck_cards,
    _runtime_evidence_globalvalue_claims,
    _with_strategic_receipt_verification,
    seal_function_definition_closure,
)
from hsconfig.package_request import (
    FrozenJsonDocument,
    ResolvedPackageRequest,
)
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.pre_run_metrics import (
    PRE_RUN_CONTRACT_SCHEMA_VERSION,
    build_layered_evidence_contract_report,
    build_pre_run_authority_handoff,
    build_pre_run_closure_report,
    build_source_acquisition_closure_report,
    disposition_ledger_document,
    globalvalues_decision_report_document,
    source_acquisition_input_binding,
)
from hsconfig.runtime_surface_ledger import build_runtime_surface_ledger
from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    AcquisitionFailure,
)
from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.source_claim_lifecycle import (
    build_initial_lifecycle_rows,
    claim_can_lower_to_runtime,
    diagnostic_claims_for_surface,
    lifecycle_claim_id,
    runtime_claims_for_surface,
    select_claims_for_surface,
)
from hsconfig.source_document_model import normalized_claim_kind
from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    project_source_contract_audit_from_dispositions,
    render_source_contract_audit_markdown,
)
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.surface_intent import build_surface_intent
from hsconfig.models import InputManifest
from hsconfig.io import slugify_deck_name


class ProjectionOwner(StrEnum):
    RESOLUTION = "resolution"
    RESEARCH = "research"
    PACKAGE_COMPILER = "package_compiler"


_RESOLUTION_PROJECTION_PATHS = frozenset(
    {
        "reports/candidate_archetypes.json",
        "reports/card_id_map.json",
        "reports/claim_coverage_report.json",
        "reports/deck_fingerprint.json",
        "reports/deck_identity.json",
        "reports/deckstring_decode_receipt.json",
        "reports/guide_builder_receipt.json",
        "reports/guide_claim_bundle.json",
        "reports/guide_sources.json",
        "reports/identity_gap_report.json",
        "reports/identity_graph_report.json",
        "reports/input_manifest.json",
        "reports/semantic_enrichment_report.json",
        "reports/source_evidence_verification_report.json",
        "reports/unsupported_claims_report.json",
    }
)
_RESEARCH_PROJECTION_PATHS = frozenset(
    {
        "reports/research/archetype_research.json",
        "reports/research/card_role_map.json",
        "reports/research/card_usage_expectations.json",
        "reports/research/claims.json",
        "reports/research/coverage_summary.json",
        "reports/research/globalvalue_intent.json",
        "reports/research/guide_claim_bundle.json",
        "reports/research/known_bad_patterns.json",
        "reports/research/mulligan_anchor_map.json",
    }
)
_COMPILER_PROJECTION_PATHS = frozenset(
    {
        "reports/card_behavior_plan_report.json",
        "reports/claim_conflict_report.json",
        "reports/combo_plan_report.json",
        "reports/disposition_ledger.json",
        "reports/gameplan_contract.json",
        "reports/global_values_authority_matrix.json",
        "reports/globalvalues_baseline.json",
        "reports/globalvalues_baseline_receipt.json",
        "reports/globalvalues_decision_ledger.json",
        "reports/globalvalues_profile.json",
        "reports/guide_source_depth_report.json",
        "reports/layered_evidence_contract.json",
        "reports/mechanic_drift_report.json",
        "reports/mulligan_plan_report.json",
        "reports/per_card_config_readiness_report.json",
        "reports/pre_run_closure.json",
        "reports/source_acquisition_closure.json",
        "reports/source_claim_gap_report.json",
        "reports/source_contract_audit.json",
        "reports/source_contract_audit.md",
        "reports/source_to_runtime_explainability.json",
        "reports/surface_intent.json",
    }
)
PRE_AUTHORITY_OWNER_BY_PATH = MappingProxyType({
    **{
        path: ProjectionOwner.RESOLUTION
        for path in _RESOLUTION_PROJECTION_PATHS
    },
    **{
        path: ProjectionOwner.RESEARCH
        for path in _RESEARCH_PROJECTION_PATHS
    },
    **{
        path: ProjectionOwner.PACKAGE_COMPILER
        for path in _COMPILER_PROJECTION_PATHS
    },
    "reports/plan_input_diagnostics.json": (
        ProjectionOwner.PACKAGE_COMPILER
    ),
})
_OPTIONAL_JSON_PROJECTION_PATHS = frozenset(
    {
        "reports/card_id_map.json",
        "reports/deckstring_decode_receipt.json",
        "reports/guide_sources.json",
        "reports/plan_input_diagnostics.json",
    }
)
_ALLOWED_JSON_PROJECTION_PATHS = frozenset(
    path
    for path in PRE_AUTHORITY_OWNER_BY_PATH
    if path.endswith(".json")
)
_REQUIRED_JSON_PROJECTION_PATHS = (
    _ALLOWED_JSON_PROJECTION_PATHS - _OPTIONAL_JSON_PROJECTION_PATHS
)
_REQUIRED_TEXT_PROJECTION_PATHS = frozenset(
    {"reports/source_contract_audit.md"}
)


def _validate_projection_owner(
    relative_path: object,
    owner: object,
    *,
    kind: str,
) -> None:
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError(f"named_{kind}_projection_path_invalid")
    if not isinstance(owner, ProjectionOwner):
        raise ValueError(f"named_{kind}_projection_owner_invalid")
    expected = PRE_AUTHORITY_OWNER_BY_PATH.get(relative_path)
    if expected is None:
        raise ValueError(f"named_{kind}_projection_path_unknown")
    if owner is not expected:
        raise ValueError(f"named_{kind}_projection_owner_mismatch")


@dataclass(frozen=True, init=False)
class NamedJsonProjection(_ImmutableAuthorityNode):
    relative_path: str
    owner: ProjectionOwner
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        _validate_projection_owner(
            self.relative_path,
            self.owner,
            kind="json",
        )
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("named_json_projection_document_invalid")

    @classmethod
    def from_value(
        cls,
        relative_path: str,
        owner: ProjectionOwner,
        value: Any,
    ) -> NamedJsonProjection:
        return cls(
            relative_path=relative_path,
            owner=owner,
            document=FrozenJsonDocument.from_value(value),
        )


@dataclass(frozen=True, init=False)
class PackageDecisionSnapshot(_ImmutableAuthorityNode):
    deck_name: str
    deck_slug: str
    deck_fingerprint: str
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    decision_projections: tuple[NamedJsonProjection, ...]
    compiler_state: FrozenJsonDocument

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.deck_name,
                self.deck_slug,
                self.deck_fingerprint,
            )
        ):
            raise ValueError("package_decision_identity_invalid")
        if not isinstance(self.mulligan_plan, MulliganPlanModel):
            raise TypeError("package_decision_mulligan_plan_invalid")
        if not isinstance(self.combo_plan, ComboPlanModel):
            raise TypeError("package_decision_combo_plan_invalid")
        if not isinstance(self.decision_projections, tuple) or any(
            not isinstance(row, NamedJsonProjection)
            for row in self.decision_projections
        ):
            raise TypeError("package_decision_projection_invalid")
        if not isinstance(self.compiler_state, FrozenJsonDocument):
            raise TypeError("package_decision_state_invalid")


def compile_package_decisions(
    request: ResolvedPackageRequest,
) -> PackageDecisionSnapshot:
    """Compile C3 source/claim decisions without external observation."""

    if not isinstance(request, ResolvedPackageRequest):
        raise TypeError("resolved_package_request_required")
    context = request.snapshot.general_preconfig.to_value()
    cards_payload = context["cards_payload"]
    verified_deck_stage = build_verified_deck_stage(
        identity=context["deck_identity"],
        cards=cards_payload["cards"],
        input_verification=cards_payload["deck_input_verification"],
    )
    verified_cards = materialize_stage_value(verified_deck_stage.cards)
    deck_input_verification = materialize_stage_value(
        verified_deck_stage.input_verification
    )
    cards_payload = {
        **cards_payload,
        "cards": verified_cards,
        "deck_input_verification": deck_input_verification,
    }
    mechanic_drift_report = build_mechanic_drift_report(verified_cards)
    deck_identity = materialize_stage_value(verified_deck_stage.identity)
    card_metadata = context["card_metadata"]
    guide_claim_bundle = _normalize_claim_conflict_report(
        context["guide_claim_bundle"]
    )
    canonical_guide_claim_bundle = guide_claim_bundle
    verified_source_receipts = list(
        guide_claim_bundle.get(
            "canonical_source_receipts",
            guide_claim_bundle.get("globalvalues_source_receipts", []),
        )
    )
    plan_claims = _with_strategic_receipt_verification(
        guide_claim_bundle.get("claims", []),
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    authority_guide_claim_bundle = {
        **guide_claim_bundle,
        "claims": plan_claims,
    }
    source_claim_conflict_report = guide_claim_bundle.get(
        "claim_conflict_report",
        {"conflict_count": 0, "conflicts": []},
    )
    mulligan_internal_policy_claims = [
        claim
        for claim in plan_claims
        if _is_internal_mulligan_policy_claim(claim)
    ]
    source_plan_claims = [
        claim
        for claim in plan_claims
        if not _is_internal_mulligan_policy_claim(claim)
    ]
    runtime_claims = [
        claim
        for claim in source_plan_claims
        if claim_can_lower_to_runtime(claim)
    ]
    initial_lifecycle_rows = build_initial_lifecycle_rows(
        source_plan_claims,
        conflict_report=source_claim_conflict_report,
    )
    non_mulligan_runtime_claims = [
        claim
        for claim in runtime_claims
        if normalized_claim_kind(claim)
        not in {"mulligan_keep", "mulligan_discard"}
    ]
    preliminary_research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims={
            "claims": non_mulligan_runtime_claims,
            "claim_count": len(non_mulligan_runtime_claims),
        },
        guide_claim_bundle=guide_claim_bundle,
    )
    surface_context = {
        "deck_identity": deck_identity,
        "verified_source_receipts": verified_source_receipts,
    }
    mulligan_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "mulligan",
        context=surface_context,
        card_roles=preliminary_research_bundle.get("card_role_map", {}),
    )
    mulligan_runtime_claims = mulligan_selection["accepted_claims"]
    runtime_source_claims = {
        "claims": [*non_mulligan_runtime_claims, *mulligan_runtime_claims],
        "claim_count": (
            len(non_mulligan_runtime_claims)
            + len(mulligan_runtime_claims)
        ),
    }
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        guide_claim_bundle=guide_claim_bundle,
    )
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        research_bundle=research_bundle,
    )
    card_roles = research_bundle.get("card_role_map", {})
    mulligan_report_claims = [
        *mulligan_runtime_claims,
        *mulligan_selection["rejected_claims"],
    ]
    cardid_claims = runtime_claims_for_surface(
        initial_lifecycle_rows,
        "cardid",
        context=surface_context,
    )
    cardid_diagnostic_claims = diagnostic_claims_for_surface(
        initial_lifecycle_rows,
        "cardid",
        context=surface_context,
    )
    combo_claims = runtime_claims_for_surface(
        initial_lifecycle_rows,
        "combo",
        context=surface_context,
    )
    globalvalues_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "globalvalues",
        context=surface_context,
    )
    globalvalues_claims = globalvalues_selection["accepted_claims"]
    globalvalues_decision_claims = [
        *globalvalues_claims,
        *globalvalues_selection["rejected_claims"],
    ]
    globalvalues_decision_claim_ids = {
        lifecycle_claim_id(claim)
        for claim in globalvalues_decision_claims
    }
    globalvalues_authority_claims = [
        *globalvalues_decision_claims,
        *[
            claim
            for claim in _runtime_evidence_globalvalue_claims(
                initial_lifecycle_rows
            )
            if lifecycle_claim_id(claim)
            not in globalvalues_decision_claim_ids
        ],
    ]
    policy_profile = policy_profile_from_mapping(context["policy_profile"])
    mulligan_deck_cards = _policy_mulligan_deck_cards(
        gameplan_contract.get("cards", {}),
        card_metadata,
    )
    mulligan_internal_policy_claims = [
        *mulligan_internal_policy_claims,
        *_explicit_bot_delegation_claims(
            card_ids=mulligan_deck_cards,
            existing_claims=mulligan_internal_policy_claims,
            policy_id=policy_profile.policy_id,
        ),
    ]
    mulligan_plan_model = build_mulligan_plan(
        deck_name=request.invocation.deck_code
        and str(deck_identity["deck_name"]),
        claims=mulligan_report_claims,
        card_roles=card_roles,
        deck_cards=mulligan_deck_cards,
        policy_profile=policy_profile,
        expected_policy_profile=policy_profile,
        internal_policy_claims=mulligan_internal_policy_claims,
        source_claim_lifecycle_rows=initial_lifecycle_rows,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    mulligan_plan = mulligan_plan_model.to_report()
    card_behavior_plan = route_card_behavior_claims(
        cardid_claims,
        identity_links=_card_behavior_identity_links(gameplan_contract),
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        verified_source_receipts=verified_source_receipts,
    )
    card_behavior_plan["suppressed"].extend(
        diagnose_card_behavior_claims(
            cardid_diagnostic_claims,
            card_metadata=card_metadata,
        )
    )
    combo_plan_model = build_typed_combo_plan(
        deck_cards=set(gameplan_contract.get("cards", {})),
        claims=combo_claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    combo_plan = combo_plan_model.to_report()
    global_values_authority_matrix = (
        build_globalvalues_authority_matrix(
            aggression_profile=str(
                gameplan_contract.get("aggression_profile", {}).get(
                    "speed",
                    "balanced",
                )
            ),
            claims=globalvalues_authority_claims,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
    )
    canonical_global_values_authority_matrix = (
        global_values_authority_matrix
    )
    plan_input_diagnostics: dict[str, Any] | None = None
    overrides = request.plan_overrides.to_value()
    if overrides:
        imported_guide_claim_bundle = _normalize_claim_conflict_report(
            overrides.get("guide_claim_bundle.json", {})
        )
        imported_globalvalues = overrides.get(
            "global_values_authority_matrix.json"
        )
        if imported_globalvalues is not None:
            global_values_authority_matrix = imported_globalvalues
        plan_input_diagnostics = _build_plan_input_diagnostics(
            canonical_guide_claim_bundle=canonical_guide_claim_bundle,
            imported_guide_claim_bundle=imported_guide_claim_bundle,
            imported_mulligan_plan=overrides.get(
                "mulligan_plan_report.json"
            ),
            imported_card_behavior_plan=overrides.get(
                "card_behavior_plan_report.json"
            ),
            imported_combo_plan=overrides.get("combo_plan_report.json"),
            imported_global_values_authority_matrix=(
                imported_globalvalues or {}
            ),
        )
        (
            mulligan_plan,
            card_behavior_plan,
            combo_plan,
            global_values_authority_matrix,
        ) = _filter_plan_reports_by_lifecycle(
            initial_lifecycle_rows=initial_lifecycle_rows,
            mulligan_plan=mulligan_plan,
            card_behavior_plan=card_behavior_plan,
            combo_plan=combo_plan,
            global_values_authority_matrix=(
                global_values_authority_matrix
            ),
            canonical_global_values_authority_matrix=(
                canonical_global_values_authority_matrix
            ),
            card_roles=card_roles,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
        )
        combo_plan_model = ComboPlanModel.from_report(combo_plan)
    gameplan_contract = {
        **gameplan_contract,
        "guide_claim_bundle": guide_claim_bundle,
        "mulligan_plan": mulligan_plan,
        "card_behavior_plan": card_behavior_plan,
        "combo_plan": combo_plan,
        "global_values_authority_matrix": (
            global_values_authority_matrix
        ),
    }
    state = {
        **context,
        "cards_payload": cards_payload,
        "deck_identity": deck_identity,
        "deck_input_verification": deck_input_verification,
        "mechanic_drift_report": mechanic_drift_report,
        "guide_claim_bundle": guide_claim_bundle,
        "authority_guide_claim_bundle": authority_guide_claim_bundle,
        "source_claim_conflict_report": source_claim_conflict_report,
        "initial_lifecycle_rows": initial_lifecycle_rows,
        "runtime_source_claims": runtime_source_claims,
        "research_bundle": research_bundle,
        "gameplan_contract": gameplan_contract,
        "mulligan_plan": mulligan_plan,
        "card_behavior_plan": card_behavior_plan,
        "combo_plan": combo_plan,
        "global_values_authority_matrix": (
            global_values_authority_matrix
        ),
        "plan_input_diagnostics": plan_input_diagnostics,
    }
    projections = _c3_projections(state)
    return PackageDecisionSnapshot(
        deck_name=str(deck_identity["deck_name"]),
        deck_slug=slugify_deck_name(str(deck_identity["deck_name"])),
        deck_fingerprint=str(deck_identity["deck_fingerprint"]),
        mulligan_plan=mulligan_plan_model,
        combo_plan=combo_plan_model,
        decision_projections=projections,
        compiler_state=FrozenJsonDocument.from_value(state),
    )


def _c3_projections(
    state: dict[str, Any],
) -> tuple[NamedJsonProjection, ...]:
    values = {
        "reports/mechanic_drift_report.json": state[
            "mechanic_drift_report"
        ],
        "reports/guide_claim_bundle.json": state["guide_claim_bundle"],
        "reports/claim_conflict_report.json": state[
            "source_claim_conflict_report"
        ],
        "reports/gameplan_contract.json": state["gameplan_contract"],
        "reports/mulligan_plan_report.json": state["mulligan_plan"],
        "reports/card_behavior_plan_report.json": state[
            "card_behavior_plan"
        ],
        "reports/combo_plan_report.json": state["combo_plan"],
        "reports/global_values_authority_matrix.json": state[
            "global_values_authority_matrix"
        ],
    }
    if state["plan_input_diagnostics"] is not None:
        values["reports/plan_input_diagnostics.json"] = state[
            "plan_input_diagnostics"
        ]
    return tuple(
        NamedJsonProjection.from_value(
            path,
            PRE_AUTHORITY_OWNER_BY_PATH[path],
            value,
        )
        for path, value in sorted(values.items())
    )


@dataclass(frozen=True, init=False)
class NamedTextProjection(_ImmutableAuthorityNode):
    relative_path: str
    owner: ProjectionOwner
    text: str

    def __post_init__(self) -> None:
        _validate_projection_owner(
            self.relative_path,
            self.owner,
            kind="text",
        )
        if not isinstance(self.text, str):
            raise TypeError("named_text_projection_text_invalid")


@dataclass(frozen=True, init=False)
class CompiledRuntimeSurface(_ImmutableAuthorityNode):
    file_name: str
    family: str
    owner: str
    decision_ids: tuple[str, ...]
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        if (
            not isinstance(self.file_name, str)
            or not self.file_name.endswith(".json")
            or "/" in self.file_name
            or "\\" in self.file_name
        ):
            raise ValueError("compiled_runtime_file_name_invalid")
        if self.family not in {"GlobalValues", "Mulligan", "CardID", "Combo"}:
            raise ValueError("compiled_runtime_family_invalid")
        if self.owner not in {"globalvalues", "mulligan", "cardid", "combo"}:
            raise ValueError("compiled_runtime_owner_invalid")
        expected_owner = {
            "GlobalValues": "globalvalues",
            "Mulligan": "mulligan",
            "CardID": "cardid",
            "Combo": "combo",
        }[self.family]
        if self.owner != expected_owner:
            raise ValueError("compiled_runtime_owner_mismatch")
        expected_file = {
            "GlobalValues": "GlobalValues.json",
            "Mulligan": "Mulligan.json",
            "Combo": "Combo.json",
        }.get(self.family)
        if (
            (expected_file is not None and self.file_name != expected_file)
            or (
                self.family == "CardID"
                and self.file_name
                in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
            )
        ):
            raise ValueError("compiled_runtime_file_family_mismatch")
        if not isinstance(self.decision_ids, tuple) or any(
            not isinstance(value, str) or not value
            for value in self.decision_ids
        ):
            raise ValueError("compiled_runtime_decision_ids_invalid")
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("compiled_runtime_document_invalid")


@dataclass(frozen=True, init=False)
class CompiledPackage(_ImmutableAuthorityNode):
    deck_name: str
    deck_slug: str
    deck_fingerprint: str
    deck_code_sha256: str
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    disposition_ledger: DispositionLedger
    dual_closure: DualClosureStatus
    decision_snapshot: PackageDecisionSnapshot
    runtime_surfaces: tuple[CompiledRuntimeSurface, ...]
    json_projections: tuple[NamedJsonProjection, ...]
    text_projections: tuple[NamedTextProjection, ...]
    semantic_runtime_ledger: FrozenJsonDocument
    layered_evidence: FrozenJsonDocument
    pre_run_closure: FrozenJsonDocument
    c6_inputs: FrozenJsonDocument

    def __new__(
        cls,
        *args: object,
        **kwargs: object,
    ) -> CompiledPackage:
        del cls, args, kwargs
        raise TypeError("compiled_package_internal_construction_only")

    def __init__(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        raise TypeError("compiled_package_internal_construction_only")

    @classmethod
    def _create(
        cls,
        *,
        deck_name: str,
        deck_slug: str,
        deck_fingerprint: str,
        deck_code_sha256: str,
        mulligan_plan: MulliganPlanModel,
        combo_plan: ComboPlanModel,
        globalvalues_ledger: GlobalValuesDecisionLedger,
        disposition_ledger: DispositionLedger,
        dual_closure: DualClosureStatus,
        decision_snapshot: PackageDecisionSnapshot,
        runtime_surfaces: tuple[CompiledRuntimeSurface, ...],
        json_projections: tuple[NamedJsonProjection, ...],
        text_projections: tuple[NamedTextProjection, ...],
        semantic_runtime_ledger: FrozenJsonDocument,
        layered_evidence: FrozenJsonDocument,
        pre_run_closure: FrozenJsonDocument,
        c6_inputs: FrozenJsonDocument,
    ) -> CompiledPackage:
        values = {
            "deck_name": deck_name,
            "deck_slug": deck_slug,
            "deck_fingerprint": deck_fingerprint,
            "deck_code_sha256": deck_code_sha256,
            "mulligan_plan": mulligan_plan,
            "combo_plan": combo_plan,
            "globalvalues_ledger": globalvalues_ledger,
            "disposition_ledger": disposition_ledger,
            "dual_closure": dual_closure,
            "decision_snapshot": decision_snapshot,
            "runtime_surfaces": runtime_surfaces,
            "json_projections": json_projections,
            "text_projections": text_projections,
            "semantic_runtime_ledger": semantic_runtime_ledger,
            "layered_evidence": layered_evidence,
            "pre_run_closure": pre_run_closure,
            "c6_inputs": c6_inputs,
        }
        return cls._create_authority_node(**values)

    def __post_init__(
        self,
        _allowed_json_paths: frozenset[str] = (
            _ALLOWED_JSON_PROJECTION_PATHS
        ),
        _required_json_paths: frozenset[str] = (
            _REQUIRED_JSON_PROJECTION_PATHS
        ),
        _required_text_paths: frozenset[str] = (
            _REQUIRED_TEXT_PROJECTION_PATHS
        ),
    ) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (
                self.deck_name,
                self.deck_slug,
                self.deck_fingerprint,
                self.deck_code_sha256,
            )
        ):
            raise ValueError("compiled_package_identity_invalid")
        typed = (
            (self.mulligan_plan, MulliganPlanModel),
            (self.combo_plan, ComboPlanModel),
            (self.globalvalues_ledger, GlobalValuesDecisionLedger),
            (self.disposition_ledger, DispositionLedger),
            (self.dual_closure, DualClosureStatus),
            (self.decision_snapshot, PackageDecisionSnapshot),
            (self.semantic_runtime_ledger, FrozenJsonDocument),
            (self.layered_evidence, FrozenJsonDocument),
            (self.pre_run_closure, FrozenJsonDocument),
            (self.c6_inputs, FrozenJsonDocument),
        )
        if any(not isinstance(value, kind) for value, kind in typed):
            raise TypeError("compiled_package_model_invalid")
        if (
            self.decision_snapshot.deck_name != self.deck_name
            or self.decision_snapshot.deck_slug != self.deck_slug
            or self.decision_snapshot.deck_fingerprint
            != self.deck_fingerprint
            or self.decision_snapshot.mulligan_plan != self.mulligan_plan
            or self.decision_snapshot.combo_plan != self.combo_plan
        ):
            raise ValueError("compiled_package_decision_snapshot_mismatch")
        if not isinstance(self.runtime_surfaces, tuple) or any(
            not isinstance(row, CompiledRuntimeSurface)
            for row in self.runtime_surfaces
        ):
            raise TypeError("compiled_package_runtime_surfaces_invalid")
        if not isinstance(self.json_projections, tuple) or any(
            not isinstance(row, NamedJsonProjection)
            for row in self.json_projections
        ):
            raise TypeError("compiled_package_json_projections_invalid")
        if not isinstance(self.text_projections, tuple) or any(
            not isinstance(row, NamedTextProjection)
            for row in self.text_projections
        ):
            raise TypeError("compiled_package_text_projections_invalid")
        json_paths = tuple(
            row.relative_path for row in self.json_projections
        )
        text_paths = tuple(
            row.relative_path for row in self.text_projections
        )
        projection_paths = (*json_paths, *text_paths)
        if len(set(projection_paths)) != len(projection_paths):
            raise ValueError("compiled_package_projection_duplicate")
        compiler_state = self.decision_snapshot.compiler_state.to_value()
        cards_payload = compiler_state.get("cards_payload")
        if not isinstance(cards_payload, dict):
            raise ValueError("compiled_package_decision_snapshot_invalid")
        optional_json_paths = {
            path
            for path, value in {
                "reports/deckstring_decode_receipt.json": (
                    cards_payload.get("deckstring_decode_receipt")
                ),
                "reports/card_id_map.json": cards_payload.get(
                    "card_id_map"
                ),
                "reports/guide_sources.json": compiler_state.get(
                    "guide_sources_generated"
                ),
                "reports/plan_input_diagnostics.json": compiler_state.get(
                    "plan_input_diagnostics"
                ),
            }.items()
            if value is not None
        }
        expected_json_paths = (
            _required_json_paths | optional_json_paths
        )
        if (
            set(json_paths) != expected_json_paths
            or set(json_paths) - _allowed_json_paths
            or set(text_paths) != _required_text_paths
        ):
            raise ValueError("compiled_package_projection_incomplete")
        deck_identity = compiler_state.get("deck_identity")
        if not isinstance(deck_identity, dict):
            raise ValueError("compiled_package_decision_snapshot_invalid")
        identity_cards = deck_identity.get("cards")
        if not isinstance(identity_cards, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("card_id"), str)
            or not row["card_id"]
            for row in identity_cards
        ):
            raise ValueError("compiled_package_deck_identity_invalid")
        runtime_files = tuple(
            row.file_name for row in self.runtime_surfaces
        )
        if len(set(runtime_files)) != len(runtime_files):
            raise ValueError("compiled_package_runtime_duplicate")
        expected_runtime_files = {
            "GlobalValues.json",
            "Mulligan.json",
            *(f"{row['card_id']}.json" for row in identity_cards),
            *(
                path
                for row in self.disposition_ledger.cards
                for path in row.runtime_paths
            ),
        }
        if self.combo_plan.decisions:
            expected_runtime_files.add("Combo.json")
        if set(runtime_files) != expected_runtime_files:
            raise ValueError("compiled_package_runtime_incomplete")


def compile_package(
    request: ResolvedPackageRequest,
    *,
    build_lowered_runtime_stage_fn=None,
) -> CompiledPackage:
    """Compile one complete pre-authority package without external I/O."""

    decisions = compile_package_decisions(request)
    state = decisions.compiler_state.to_value()
    gameplan = state["gameplan_contract"]
    card_plan = state["card_behavior_plan"]
    card_files = compile_cardid_behaviors(
        gameplan,
        rows=card_plan["rows"],
        static_runtime_suppressed_card_ids=card_plan.get(
            "static_runtime_suppressed_card_ids",
            [],
        ),
    )
    card_plan.setdefault("merged_duplicate_runtime_row_count", 0)
    card_plan.setdefault("runtime_row_conflicts", [])
    card_plan["compiler_merged_duplicate_runtime_row_count"] = (
        card_files.merged_duplicate_runtime_row_count
    )
    card_plan["compiler_runtime_row_conflicts"] = (
        card_files.runtime_row_conflicts
    )
    gameplan = {
        **gameplan,
        "card_behavior_plan": card_plan,
    }
    state["gameplan_contract"] = gameplan
    baseline = normalize_globalvalues_decision_baseline(
        state["globalvalues_baseline"]
    )
    globalvalues_ledger = build_globalvalues_decision_ledger(
        deck_fingerprint=decisions.deck_fingerprint,
        baseline=baseline,
        baseline_sha256=canonical_globalvalues_baseline_sha256(baseline),
        authority_matrix=state["global_values_authority_matrix"],
    )
    globalvalues = compile_globalvalues(
        baseline,
        gameplan,
        decision_ledger=globalvalues_ledger,
    )
    compiled_mulligan = compile_mulligan(decisions.mulligan_plan)
    compiled_combo = compile_combo(
        decisions.combo_plan,
        deck_name=decisions.deck_name,
    )
    semantic_ledger = build_runtime_surface_ledger(
        deck_identity=state["deck_identity"],
        compiled_mulligan=compiled_mulligan,
        compiled_globalvalues=globalvalues["config"],
        globalvalues_baseline=baseline,
        compiled_combo=compiled_combo,
        compiled_cardid_files=card_files,
        linked_runtime_owners=[
            {
                "source_card_id": str(
                    row.get("source_card_id") or row.get("card_id", "")
                ),
                "runtime_card_id": str(
                    row.get("runtime_card_id") or row.get("card_id", "")
                ),
                "link_kind": str(row.get("link_kind") or "self"),
            }
            for row in card_plan["rows"]
            if isinstance(row, dict)
            and row.get("meaningful_runtime_surface") is True
        ],
    )
    readiness = build_config_readiness_report(
        deck_identity=state["deck_identity"],
        claim_coverage=state["guide_claim_bundle"]["coverage"],
        gameplan_contract=gameplan,
        mulligan_plan=state["mulligan_plan"],
        card_behavior_plan=card_plan,
        combo_plan=state["combo_plan"],
        global_values_authority_matrix=state[
            "global_values_authority_matrix"
        ],
        emitted_cardid_files=card_files,
        runtime_surface_ledger=semantic_ledger,
    )
    source_depth = build_guide_source_depth_report(
        guide_claim_bundle=state["guide_claim_bundle"],
        config_readiness_report=readiness,
        source_evidence_verification_report=state[
            "source_evidence_report"
        ],
    )
    surface_intent = build_surface_intent(
        gameplan,
        mulligan_plan_report=state["mulligan_plan"],
    )
    runtime_values = {
        "GlobalValues.json": globalvalues["config"],
        "Mulligan.json": compiled_mulligan,
        **dict(card_files.items()),
    }
    if compiled_combo is not None:
        runtime_values["Combo.json"] = compiled_combo
    lowered_runtime_builder = (
        build_lowered_runtime_stage
        if build_lowered_runtime_stage_fn is None
        else build_lowered_runtime_stage_fn
    )
    lowered = lowered_runtime_builder(
        runtime_files=runtime_values,
        warnings=[
            row
            for row in state["mulligan_plan"].get(
                "suppressed_rules",
                [],
            )
            if isinstance(row, dict)
        ],
        source_contract=gameplan,
    )
    runtime_values = materialize_stage_value(lowered.runtime_files)
    state["mulligan_plan"] = {
        **state["mulligan_plan"],
        "suppressed_rules": materialize_stage_value(lowered.warnings),
    }
    gameplan = {
        **materialize_stage_value(lowered.source_contract),
        "mulligan_plan": state["mulligan_plan"],
        "card_behavior_plan": card_plan,
    }
    state["gameplan_contract"] = gameplan
    policy = policy_profile_from_mapping(state["policy_profile"])
    policy_mapping = state["policy_profile"]
    source_audit = build_source_contract_audit(
        deck_name=decisions.deck_name,
        deck_identity=state["deck_identity"],
        guide_claim_bundle=state["authority_guide_claim_bundle"],
        mulligan_plan=state["mulligan_plan"],
        card_behavior_plan=card_plan,
        combo_plan=state["combo_plan"],
        global_values_authority_matrix=state[
            "global_values_authority_matrix"
        ],
        config_readiness_report=readiness,
        initial_lifecycle_rows=state["initial_lifecycle_rows"],
        plan_input_diagnostics=state["plan_input_diagnostics"],
        policy_profile=policy_mapping,
        expected_policy_profile=policy,
        include_evidence_authority=True,
    )
    disposition, dual_closure, verified_emissions = (
        _build_package_disposition_ledger(
            deck_identity=state["deck_identity"],
            source_contract_audit_report=source_audit,
            runtime_surface_ledger=semantic_ledger,
            globalvalues_ledger=globalvalues_ledger,
            strategy_source_status=(
                "strong"
                if str(
                    state["guide_claim_bundle"].get(
                        "source_backed_status",
                        "",
                    )
                )
                == "SOURCE_BACKED_STRONG"
                else "partial"
            ),
        )
    )
    classified = {
        str(claim_id): row["evidence_authority"]
        for claim_id, row in source_audit.get("claim_rows", {}).items()
        if isinstance(row, dict)
        and isinstance(row.get("evidence_authority"), dict)
    }
    acquisition_closure = _acquisition_closure(
        request.acquisition_closure_input.to_value()
    )
    acquisition_report = build_source_acquisition_closure_report(
        deck_fingerprint=decisions.deck_fingerprint,
        acquisition_closure=acquisition_closure,
        expected_policy_profile=policy,
    )
    layered = build_layered_evidence_contract_report(
        disposition_ledger=disposition,
        classified_authorities=classified,
    )
    pre_run_closure = build_pre_run_closure_report(
        disposition_ledger=disposition,
        globalvalues_ledger=globalvalues_ledger,
        dual_closure=dual_closure,
        layered_evidence_report=layered,
        source_acquisition_report=acquisition_report,
        verified_emissions=verified_emissions,
    )
    if request.invocation.include_disposition_diagnostics:
        source_audit = project_source_contract_audit_from_dispositions(
            source_audit,
            dispositions=disposition,
            dual_closure=dual_closure,
        )
        readiness = project_config_readiness_from_dispositions(
            readiness,
            dispositions=disposition,
            dual_closure=dual_closure,
        )
    gap = build_source_claim_gap_report(
        deck_name=decisions.deck_name,
        config_readiness_report=readiness,
        claim_coverage_report=state["guide_claim_bundle"].get(
            "claim_coverage_report",
            state["guide_claim_bundle"]["coverage"],
        ),
        card_behavior_plan=card_plan,
        mulligan_plan=state["mulligan_plan"],
        combo_plan=state["combo_plan"],
        source_contract_audit=source_audit,
    )
    explainability = build_source_to_runtime_explainability_report(
        source_audit,
        card_behavior_plan=card_plan,
        runtime_surface_ledger=semantic_ledger,
        disposition_ledger=(
            disposition
            if request.invocation.include_disposition_diagnostics
            else None
        ),
        dual_closure_status=(
            dual_closure
            if request.invocation.include_disposition_diagnostics
            else None
        ),
    )
    manifest = InputManifest(
        deck_name=decisions.deck_name,
        deck_code=request.invocation.deck_code,
        runtime_root=request.invocation.runtime_root,
        target_config_mode=request.invocation.target_config_mode,
        format=state["cards_payload"].get("format"),
    ).to_dict()
    manifest.update(
        {
            "cards_json": request.invocation.cards_json,
            "claims_json": request.invocation.claims_json,
            "guide_sources_json": request.invocation.guide_sources_json,
            "plan_reports_dir": request.invocation.plan_reports_dir,
            "card_source": state["cards_payload"]["card_source"],
            "deck_input_verification": state["deck_input_verification"],
            "pre_run_contract_schema_version": (
                PRE_RUN_CONTRACT_SCHEMA_VERSION
            ),
            "source_acquisition_input_binding": (
                source_acquisition_input_binding(acquisition_report)
            ),
            "pre_run_authority_handoff": build_pre_run_authority_handoff(
                disposition_ledger=disposition,
                classified_authorities=classified,
            ),
        }
    )
    if request.invocation.configuration_mode == "LLM_OPTIMIZED_START":
        manifest["configuration_mode"] = "LLM_OPTIMIZED_START"
    json_projections = _all_json_projections(
        state=state,
        manifest=manifest,
        card_plan=card_plan,
        readiness=readiness,
        source_depth=source_depth,
        surface_intent=surface_intent,
        source_audit=source_audit,
        gap=gap,
        explainability=explainability,
        baseline=baseline,
        globalvalues=globalvalues,
        globalvalues_ledger=globalvalues_ledger,
        acquisition_report=acquisition_report,
        disposition=disposition,
        layered=layered,
        pre_run_closure=pre_run_closure,
    )
    runtime_surfaces = _runtime_surfaces(
        runtime_values,
        decisions=decisions,
        globalvalues_ledger=globalvalues_ledger,
        disposition=disposition,
    )
    c6_inputs = {
        "semantic_report": state["semantic_report"],
        "guide_source_depth_report": source_depth,
        "source_claim_gap_report": gap,
        "source_to_runtime_explainability_report": explainability,
        "config_readiness_report": readiness,
        "global_values_authority_matrix": state[
            "global_values_authority_matrix"
        ],
        "gameplan_contract": gameplan,
    }
    text_projections = (
        NamedTextProjection(
            "reports/source_contract_audit.md",
            ProjectionOwner.PACKAGE_COMPILER,
            render_source_contract_audit_markdown(source_audit),
        ),
    )
    return CompiledPackage._create(
        deck_name=decisions.deck_name,
        deck_slug=decisions.deck_slug,
        deck_fingerprint=decisions.deck_fingerprint,
        deck_code_sha256=(
            request.snapshot.strict_build_context.inputs.deck_code_sha256
            if request.snapshot.strict_build_context is not None
            else state["deck_identity"]["deck_code_hash"]
        ),
        mulligan_plan=decisions.mulligan_plan,
        combo_plan=decisions.combo_plan,
        globalvalues_ledger=globalvalues_ledger,
        disposition_ledger=disposition,
        dual_closure=dual_closure,
        decision_snapshot=decisions,
        runtime_surfaces=runtime_surfaces,
        json_projections=json_projections,
        text_projections=text_projections,
        semantic_runtime_ledger=FrozenJsonDocument.from_value(
            semantic_ledger
        ),
        layered_evidence=FrozenJsonDocument.from_value(layered),
        pre_run_closure=FrozenJsonDocument.from_value(pre_run_closure),
        c6_inputs=FrozenJsonDocument.from_value(c6_inputs),
    )


def _acquisition_closure(value: dict[str, Any]) -> AcquisitionClosure:
    return AcquisitionClosure(
        deck_fingerprint=value["deck_fingerprint"],
        attempt_id=value["attempt_id"],
        attempted_at=value["attempted_at"],
        attempted_urls=tuple(value["attempted_urls"]),
        successful_evidence_ids=tuple(value["successful_evidence_ids"]),
        failed_attempts=tuple(
            AcquisitionFailure(**row) for row in value["failed_attempts"]
        ),
        negative_search_documented=value["negative_search_documented"],
        checked_dossier=value["checked_dossier"],
        policy_id=value["policy_id"],
        status=value["status"],
        content_sha256=value["content_sha256"],
    )


def _runtime_surfaces(
    runtime_values: dict[str, Any],
    *,
    decisions: PackageDecisionSnapshot,
    globalvalues_ledger: GlobalValuesDecisionLedger,
    disposition: DispositionLedger,
) -> tuple[CompiledRuntimeSurface, ...]:
    card_claims = {
        path.removeprefix("CustomConfig/").split("/", 1)[-1]: (
            f"card:{row.physical_owner}",
        )
        for row in disposition.cards
        for path in row.runtime_paths
    }
    rows: list[CompiledRuntimeSurface] = []
    for name, value in sorted(runtime_values.items()):
        if name == "GlobalValues.json":
            family, owner = "GlobalValues", "globalvalues"
            ids = tuple(
                sorted(
                    f"globalvalues:{row.key}"
                    for row in globalvalues_ledger.decisions
                )
            )
        elif name == "Mulligan.json":
            family, owner = "Mulligan", "mulligan"
            ids = tuple(
                sorted(
                    {
                        f"mulligan:{claim_id}"
                        for rule in decisions.mulligan_plan.rules
                        for claim_id in (
                            (rule.claim_id,)
                            if rule.claim_id
                            else rule.source_claim_ids
                        )
                    }
                )
            )
        elif name == "Combo.json":
            family, owner = "Combo", "combo"
            ids = tuple(row.rule_id for row in decisions.combo_plan.decisions)
        else:
            family, owner = "CardID", "cardid"
            ids = card_claims.get(name, (f"card:{name[:-5]}",))
        rows.append(
            CompiledRuntimeSurface(
                file_name=name,
                family=family,
                owner=owner,
                decision_ids=ids,
                document=FrozenJsonDocument.from_value(value),
            )
        )
    return tuple(rows)


def _all_json_projections(**values: Any) -> tuple[NamedJsonProjection, ...]:
    state = values["state"]
    research = state["research_bundle"]
    documents: dict[str, tuple[ProjectionOwner, Any]] = {
        "reports/input_manifest.json": (ProjectionOwner.RESOLUTION, values["manifest"]),
        "reports/deck_identity.json": (ProjectionOwner.RESOLUTION, state["deck_identity"]),
        "reports/semantic_enrichment_report.json": (ProjectionOwner.RESOLUTION, state["semantic_report"]),
        "reports/mechanic_drift_report.json": (ProjectionOwner.PACKAGE_COMPILER, state["mechanic_drift_report"]),
        "reports/deck_fingerprint.json": (ProjectionOwner.RESOLUTION, state["deck_fingerprint"]),
        "reports/candidate_archetypes.json": (ProjectionOwner.RESOLUTION, state["candidate_archetypes"]),
        "reports/guide_builder_receipt.json": (ProjectionOwner.RESOLUTION, state["guide_builder_receipt"]),
        "reports/identity_graph_report.json": (ProjectionOwner.RESOLUTION, state["identity_graph_report"]),
        "reports/identity_gap_report.json": (ProjectionOwner.RESOLUTION, state["identity_gap_report"]),
        "reports/source_evidence_verification_report.json": (ProjectionOwner.RESOLUTION, state["source_evidence_report"]),
        "reports/guide_claim_bundle.json": (ProjectionOwner.RESOLUTION, state["guide_claim_bundle"]),
        "reports/claim_coverage_report.json": (ProjectionOwner.RESOLUTION, {**state["guide_claim_bundle"].get("coverage", {}), **state["guide_claim_bundle"].get("claim_coverage_report", {})}),
        "reports/claim_conflict_report.json": (ProjectionOwner.PACKAGE_COMPILER, state["source_claim_conflict_report"]),
        "reports/unsupported_claims_report.json": (ProjectionOwner.RESOLUTION, state["guide_claim_bundle"]["unsupported_claims"]),
        "reports/gameplan_contract.json": (ProjectionOwner.PACKAGE_COMPILER, state["gameplan_contract"]),
        "reports/surface_intent.json": (ProjectionOwner.PACKAGE_COMPILER, values["surface_intent"]),
        "reports/mulligan_plan_report.json": (ProjectionOwner.PACKAGE_COMPILER, state["mulligan_plan"]),
        "reports/card_behavior_plan_report.json": (ProjectionOwner.PACKAGE_COMPILER, values["card_plan"]),
        "reports/combo_plan_report.json": (ProjectionOwner.PACKAGE_COMPILER, state["combo_plan"]),
        "reports/global_values_authority_matrix.json": (ProjectionOwner.PACKAGE_COMPILER, state["global_values_authority_matrix"]),
        "reports/per_card_config_readiness_report.json": (ProjectionOwner.PACKAGE_COMPILER, values["readiness"]),
        "reports/guide_source_depth_report.json": (ProjectionOwner.PACKAGE_COMPILER, values["source_depth"]),
        "reports/source_contract_audit.json": (ProjectionOwner.PACKAGE_COMPILER, values["source_audit"]),
        "reports/source_claim_gap_report.json": (ProjectionOwner.PACKAGE_COMPILER, values["gap"]),
        "reports/source_to_runtime_explainability.json": (ProjectionOwner.PACKAGE_COMPILER, values["explainability"]),
        "reports/globalvalues_baseline.json": (ProjectionOwner.PACKAGE_COMPILER, values["baseline"]),
        "reports/globalvalues_baseline_receipt.json": (ProjectionOwner.PACKAGE_COMPILER, state["globalvalues_baseline_receipt"]),
        "reports/globalvalues_profile.json": (ProjectionOwner.PACKAGE_COMPILER, values["globalvalues"]["profile"]),
        "reports/source_acquisition_closure.json": (ProjectionOwner.PACKAGE_COMPILER, values["acquisition_report"]),
        "reports/globalvalues_decision_ledger.json": (ProjectionOwner.PACKAGE_COMPILER, globalvalues_decision_report_document(values["globalvalues_ledger"])),
        "reports/disposition_ledger.json": (ProjectionOwner.PACKAGE_COMPILER, disposition_ledger_document(values["disposition"])),
        "reports/layered_evidence_contract.json": (ProjectionOwner.PACKAGE_COMPILER, values["layered"]),
        "reports/pre_run_closure.json": (ProjectionOwner.PACKAGE_COMPILER, values["pre_run_closure"]),
    }
    optional = {
        "reports/deckstring_decode_receipt.json": state["cards_payload"].get("deckstring_decode_receipt"),
        "reports/card_id_map.json": state["cards_payload"].get("card_id_map"),
        "reports/guide_sources.json": state.get("guide_sources_generated"),
        "reports/plan_input_diagnostics.json": state.get("plan_input_diagnostics"),
    }
    for path, value in optional.items():
        if value is not None:
            owner = (
                ProjectionOwner.PACKAGE_COMPILER
                if path.endswith("plan_input_diagnostics.json")
                else ProjectionOwner.RESOLUTION
            )
            documents[path] = (owner, value)
    for key in (
        "archetype_research",
        "card_role_map",
        "mulligan_anchor_map",
        "card_usage_expectations",
        "known_bad_patterns",
        "globalvalue_intent",
        "coverage_summary",
    ):
        documents[f"reports/research/{key}.json"] = (
            ProjectionOwner.RESEARCH,
            research[key],
        )
    documents["reports/research/claims.json"] = (
        ProjectionOwner.RESEARCH,
        {"claims": research["claims"]},
    )
    documents["reports/research/guide_claim_bundle.json"] = (
        ProjectionOwner.RESEARCH,
        state["guide_claim_bundle"],
    )
    return tuple(
        NamedJsonProjection.from_value(path, owner, document)
        for path, (owner, document) in sorted(documents.items())
    )


__all__ = (
    "CompiledPackage",
    "CompiledRuntimeSurface",
    "NamedJsonProjection",
    "NamedTextProjection",
    "PackageDecisionSnapshot",
    "PRE_AUTHORITY_OWNER_BY_PATH",
    "ProjectionOwner",
    "compile_package",
    "compile_package_decisions",
)


compile_package_decisions = seal_function_definition_closure(
    compile_package_decisions
)
compile_package = seal_function_definition_closure(compile_package)
