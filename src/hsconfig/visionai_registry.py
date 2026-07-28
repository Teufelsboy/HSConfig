from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Mapping


RuntimeSurfaceClassification = Literal[
    "required",
    "optional",
    "conditional_card_surface",
    "forbidden",
]


@dataclass(frozen=True, slots=True)
class RuntimeSurfaceSpec:
    file_name: str
    classification: RuntimeSurfaceClassification
    normal_apply_allowed: bool
    row_schema_id: str
    value_type_id: str
    physical_owner_rule_id: str


@dataclass(frozen=True, slots=True)
class ClaimSurfaceRule:
    claim_kind: str
    allowed_surfaces: tuple[str, ...]
    required_authority_lanes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GlobalValueKeySpec:
    key: str
    value_type_id: str
    key_class: str
    overlay_authority_required: bool


@dataclass(frozen=True, slots=True)
class ReportSpec:
    relative_path: str
    required: bool
    apply_authority: bool
    ownership: str


NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
CARDID_SURFACE_FAMILY = "CARDID.json"
CARDID_SURFACE_DISPLAY_NAME = "per-card <CARDID>.json"
GLOBALVALUES_RUNTIME_FILE = "GlobalValues.json"
MULLIGAN_RUNTIME_FILE = "Mulligan.json"
COMBO_RUNTIME_FILE = "Combo.json"
CARD_BEHAVIOR_RUNTIME_FILE = "CardBehavior.json"
CONCEDE_RUNTIME_FILE = "Concede.json"
PRESUME_RUNTIME_FILE = "Presume.json"

RUNTIME_ROW_SCHEMA_KEYS: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "RUNTIME_VALUE_ROW_KEYS": frozenset({"comment", "condition", "value"}),
        "MULLIGAN_ROW_KEYS": frozenset(
            {"comment", "condition", "mulligan", "value"}
        ),
        "COMBO_ROW_KEYS": frozenset({"comment", "condition", "combo", "value"}),
        "FORBIDDEN_RUNTIME_ROW_KEYS": frozenset(),
    }
)

RUNTIME_SURFACE_REGISTRY: Mapping[str, RuntimeSurfaceSpec] = MappingProxyType(
    {
        "GlobalValues.json": RuntimeSurfaceSpec(
            file_name="GlobalValues.json",
            classification="required",
            normal_apply_allowed=True,
            row_schema_id="RUNTIME_VALUE_ROW_KEYS",
            value_type_id="safe_numeric_expression",
            physical_owner_rule_id="physical_runtime_surface_ledger",
        ),
        "Mulligan.json": RuntimeSurfaceSpec(
            file_name="Mulligan.json",
            classification="required",
            normal_apply_allowed=True,
            row_schema_id="MULLIGAN_ROW_KEYS",
            value_type_id="hold_or_discard",
            physical_owner_rule_id="physical_runtime_surface_ledger",
        ),
        CARDID_SURFACE_FAMILY: RuntimeSurfaceSpec(
            file_name=CARDID_SURFACE_FAMILY,
            classification="conditional_card_surface",
            normal_apply_allowed=True,
            row_schema_id="RUNTIME_VALUE_ROW_KEYS",
            value_type_id="finite_decimal",
            physical_owner_rule_id="physical_runtime_surface_ledger",
        ),
        "Combo.json": RuntimeSurfaceSpec(
            file_name="Combo.json",
            classification="optional",
            normal_apply_allowed=True,
            row_schema_id="COMBO_ROW_KEYS",
            value_type_id="combo_sequence",
            physical_owner_rule_id="physical_runtime_surface_ledger",
        ),
        "CardBehavior.json": RuntimeSurfaceSpec(
            file_name="CardBehavior.json",
            classification="forbidden",
            normal_apply_allowed=False,
            row_schema_id="FORBIDDEN_RUNTIME_ROW_KEYS",
            value_type_id="not_applicable",
            physical_owner_rule_id="normal_path_drift",
        ),
        "Concede.json": RuntimeSurfaceSpec(
            file_name="Concede.json",
            classification="forbidden",
            normal_apply_allowed=False,
            row_schema_id="FORBIDDEN_RUNTIME_ROW_KEYS",
            value_type_id="not_applicable",
            physical_owner_rule_id="normal_path_drift",
        ),
        "Presume.json": RuntimeSurfaceSpec(
            file_name="Presume.json",
            classification="forbidden",
            normal_apply_allowed=False,
            row_schema_id="FORBIDDEN_RUNTIME_ROW_KEYS",
            value_type_id="not_applicable",
            physical_owner_rule_id="normal_path_drift",
        ),
    }
)

REQUIRED_RUNTIME_SURFACES = frozenset(
    name
    for name, spec in RUNTIME_SURFACE_REGISTRY.items()
    if spec.classification == "required"
)
OPTIONAL_RUNTIME_SURFACES = frozenset(
    name
    for name, spec in RUNTIME_SURFACE_REGISTRY.items()
    if spec.classification == "optional"
)
FORBIDDEN_RUNTIME_SURFACES = frozenset(
    name
    for name, spec in RUNTIME_SURFACE_REGISTRY.items()
    if spec.classification == "forbidden"
)
NORMAL_RUNTIME_SURFACES = frozenset(
    name
    for name, spec in RUNTIME_SURFACE_REGISTRY.items()
    if spec.normal_apply_allowed
)
NORMAL_SPECIAL_RUNTIME_SURFACES = frozenset(
    name for name in NORMAL_RUNTIME_SURFACES if name != CARDID_SURFACE_FAMILY
)
SPECIAL_RUNTIME_SURFACES = frozenset(
    name for name in RUNTIME_SURFACE_REGISTRY if name != CARDID_SURFACE_FAMILY
)
LEGACY_RUNTIME_SURFACES = frozenset(
    name for name in FORBIDDEN_RUNTIME_SURFACES if name != CARD_BEHAVIOR_RUNTIME_FILE
)
SERIALIZED_SPECIAL_RUNTIME_SURFACES = (
    NORMAL_SPECIAL_RUNTIME_SURFACES | LEGACY_RUNTIME_SURFACES
)
CARDID_SURFACE_ALIASES = frozenset({CARDID_SURFACE_FAMILY, "CardID.json"})
NORMAL_RUNTIME_SURFACE_BOUNDARY = (
    GLOBALVALUES_RUNTIME_FILE,
    MULLIGAN_RUNTIME_FILE,
    CARDID_SURFACE_DISPLAY_NAME,
    COMBO_RUNTIME_FILE,
)

RUNTIME_SURFACE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "globalvalues": "GlobalValues.json",
        "global_values": "GlobalValues.json",
        "GlobalValues.json": "GlobalValues.json",
        "mulligan": "Mulligan.json",
        "Mulligan.json": "Mulligan.json",
        "combo": "Combo.json",
        "Combo.json": "Combo.json",
        "cardid": CARDID_SURFACE_DISPLAY_NAME,
        "cardid_behavior": CARDID_SURFACE_DISPLAY_NAME,
        "CARDID.json": CARDID_SURFACE_DISPLAY_NAME,
        "CardID.json": CARDID_SURFACE_DISPLAY_NAME,
    }
)

SURFACE_FAMILY_RUNTIME_FILES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "mulligan": frozenset({"Mulligan.json"}),
        "globalvalues": frozenset({"GlobalValues.json"}),
        "combo": frozenset({"Combo.json"}),
    }
)

CLAIM_SURFACE_REGISTRY: Mapping[str, ClaimSurfaceRule] = MappingProxyType(
    {
        "archetype": ClaimSurfaceRule("archetype", (), ("report_only",)),
        "mulligan_keep": ClaimSurfaceRule(
            "mulligan_keep", ("Mulligan.json",), ("runtime_lowerable",)
        ),
        "mulligan_discard": ClaimSurfaceRule(
            "mulligan_discard", ("Mulligan.json",), ("runtime_lowerable",)
        ),
        "card_role": ClaimSurfaceRule(
            "card_role", (CARDID_SURFACE_FAMILY,), ("suppressed_or_conditional",)
        ),
        "targeting_rule": ClaimSurfaceRule(
            "targeting_rule", (CARDID_SURFACE_FAMILY,), ("runtime_lowerable",)
        ),
        "combo_sequence": ClaimSurfaceRule(
            "combo_sequence", ("Combo.json",), ("runtime_lowerable",)
        ),
        "gameplan_posture": ClaimSurfaceRule(
            "gameplan_posture", ("GlobalValues.json",), ("runtime_lowerable",)
        ),
        "hero_power_transform": ClaimSurfaceRule(
            "hero_power_transform",
            (CARDID_SURFACE_FAMILY,),
            ("suppressed_or_conditional",),
        ),
        "mechanic_usage": ClaimSurfaceRule(
            "mechanic_usage",
            (CARDID_SURFACE_FAMILY,),
            ("suppressed_or_conditional",),
        ),
        "known_bad_pattern": ClaimSurfaceRule(
            "known_bad_pattern",
            (CARDID_SURFACE_FAMILY,),
            ("suppressed_or_conditional",),
        ),
        "tech_slot": ClaimSurfaceRule("tech_slot", (), ("report_only",)),
        "replacement_option": ClaimSurfaceRule(
            "replacement_option", (), ("report_only",)
        ),
        "discover_choice": ClaimSurfaceRule(
            "discover_choice",
            (CARDID_SURFACE_FAMILY,),
            ("suppressed_or_conditional",),
        ),
        "choose_one_choice": ClaimSurfaceRule(
            "choose_one_choice",
            (CARDID_SURFACE_FAMILY,),
            ("suppressed_or_conditional",),
        ),
        "globalvalue_numeric_tuning": ClaimSurfaceRule(
            "globalvalue_numeric_tuning", (), ("runtime_evidence_required",)
        ),
    }
)

GLOBALVALUES_KEY_REGISTRY: Mapping[str, GlobalValueKeySpec] = MappingProxyType(
    {
        "GameCardId": GlobalValueKeySpec(
            "GameCardId", "metadata", "copy_baseline", False
        ),
        "ConfigComment": GlobalValueKeySpec(
            "ConfigComment", "metadata", "copy_baseline", False
        ),
        "FirstTurnValueWeight": GlobalValueKeySpec(
            "FirstTurnValueWeight",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "SecondTurnValueWeight": GlobalValueKeySpec(
            "SecondTurnValueWeight",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "MyHeroPowerValue": GlobalValueKeySpec(
            "MyHeroPowerValue",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "GlobalMinionAttack": GlobalValueKeySpec(
            "GlobalMinionAttack",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "GlobalMinionIntrinsicValue": GlobalValueKeySpec(
            "GlobalMinionIntrinsicValue",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "MyWeaponValue": GlobalValueKeySpec(
            "MyWeaponValue",
            "safe_numeric_expression",
            "step1_posture_overlay_allowed",
            True,
        ),
        "LowHpBoardValuePenalty": GlobalValueKeySpec(
            "LowHpBoardValuePenalty",
            "safe_numeric_expression",
            "runtime_evidence_required",
            True,
        ),
        "OpponentSpecificMatchupTuning": GlobalValueKeySpec(
            "OpponentSpecificMatchupTuning",
            "safe_numeric_expression",
            "runtime_evidence_required",
            True,
        ),
        "PostApplyRegressionTuning": GlobalValueKeySpec(
            "PostApplyRegressionTuning",
            "safe_numeric_expression",
            "runtime_evidence_required",
            True,
        ),
        "EnemyHeroPowerValue": GlobalValueKeySpec(
            "EnemyHeroPowerValue",
            "safe_numeric_expression",
            "copy_baseline",
            False,
        ),
        "EnemyWeaponValue": GlobalValueKeySpec(
            "EnemyWeaponValue",
            "safe_numeric_expression",
            "copy_baseline",
            False,
        ),
    }
)

_OWNED_REPORT_SPECS = (
    (NORMAL_APPLY_AUTHORITY, True, True, "normal_operator_gate"),
    (
        "reports/output_ownership_manifest.json",
        False,
        False,
        "diagnostic_artifact_ownership",
    ),
    ("reports/source_bundle.json", False, False, "diagnostic_source_bundle"),
    (
        "reports/02_source_acquisition/source_closure_intake_receipt.json",
        False,
        False,
        "diagnostic_source_closure_intake",
    ),
    (
        "reports/source_contract_audit.json",
        False,
        False,
        "diagnostic_source_to_runtime_explanation",
    ),
    (
        "reports/source_to_runtime_explainability.json",
        False,
        False,
        "diagnostic_source_to_runtime_projection",
    ),
    (
        "reports/source_evidence_closure.json",
        False,
        False,
        "diagnostic_source_evidence_closure",
    ),
    ("reports/source_claim_gap_report.json", False, False, "repair_contract"),
    ("reports/strong_promotion_report.json", False, False, "promotion_confirmation"),
    (
        "reports/per_card_config_readiness_report.json",
        False,
        False,
        "card_lane_diagnostics",
    ),
    (
        "reports/guide_source_depth_report.json",
        False,
        False,
        "source_depth_diagnostics",
    ),
    (
        "reports/global_values_authority_matrix.json",
        False,
        False,
        "globalvalues_diagnostics",
    ),
    (
        "reports/mechanic_drift_report.json",
        False,
        False,
        "non_blocking_mechanic_drift_visibility",
    ),
    (
        "reports/semantic_enrichment_report.json",
        False,
        False,
        "semantic_mechanic_diagnostics",
    ),
    (
        "reports/runtime_surface_ledger.json",
        True,
        False,
        "physical_runtime_surface_ledger",
    ),
)

DIAGNOSTIC_REPORT_PATHS = frozenset(
    {
        "reports/card_behavior_plan_report.json",
        "reports/card_behavior_suppression_report.json",
        "reports/card_id_map.json",
        "reports/card_semantic_audit.md",
        "reports/candidate_archetypes.json",
        "reports/claim_conflict_report.json",
        "reports/claim_coverage_report.json",
        "reports/combo_plan_report.json",
        "reports/combo_suppression_report.json",
        "reports/deck_fingerprint.json",
        "reports/deck_identity.json",
        "reports/deckstring_decode_receipt.json",
        "reports/fake_apply_receipt.json",
        "reports/gameplan_contract.json",
        "reports/global_values_blocked_changes.json",
        "reports/global_values_key_profile_report.json",
        "reports/globalvalues_baseline.json",
        "reports/globalvalues_baseline_receipt.json",
        "reports/globalvalues_profile.json",
        "reports/guide_builder_receipt.json",
        "reports/guide_claim_bundle.json",
        "reports/guide_sources.json",
        "reports/identity_gap_report.json",
        "reports/identity_graph_report.json",
        "reports/input_manifest.json",
        "reports/mulligan_plan_report.json",
        "reports/plan_input_diagnostics.json",
        "reports/runtime_apply_receipt.json",
        "reports/semantic_enrichment_report.json",
        "reports/source_contract_audit.md",
        "reports/source_evidence_closure.json",
        "reports/source_evidence_index.json",
        "reports/source_evidence_verification_report.json",
        "reports/source_bundle.json",
        "reports/surface_intent.json",
        "reports/unsupported_claims_report.json",
        "reports/validation_report.json",
    }
)

RESEARCH_REPORT_PATHS = frozenset(
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

REPORT_REGISTRY: Mapping[str, ReportSpec] = MappingProxyType(
    {
        relative_path: ReportSpec(
            relative_path=relative_path,
            required=required,
            apply_authority=apply_authority,
            ownership=ownership,
        )
        for relative_path, required, apply_authority, ownership in (
            *_OWNED_REPORT_SPECS,
            *(
                (path, False, False, "diagnostic_artifact")
                for path in sorted(
                    (DIAGNOSTIC_REPORT_PATHS | RESEARCH_REPORT_PATHS)
                    - {row[0] for row in _OWNED_REPORT_SPECS}
                )
            ),
        )
    }
)


CARD_ID_SURFACE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9_]+\.json$")


def normalize_runtime_surface(file_name: str | Path) -> str:
    name = Path(file_name).name
    if name in RUNTIME_SURFACE_REGISTRY:
        return name
    if name == "CardID.json":
        return CARDID_SURFACE_FAMILY
    if CARD_ID_SURFACE_RE.fullmatch(name):
        return CARDID_SURFACE_FAMILY
    raise KeyError(name)


def runtime_surface_spec(file_name: str | Path) -> RuntimeSurfaceSpec:
    return RUNTIME_SURFACE_REGISTRY[normalize_runtime_surface(file_name)]


def classify_runtime_surface(file_name: str | Path) -> RuntimeSurfaceClassification:
    return runtime_surface_spec(file_name).classification


def runtime_row_keys(file_name: str | Path) -> frozenset[str]:
    spec = runtime_surface_spec(file_name)
    return RUNTIME_ROW_SCHEMA_KEYS[spec.row_schema_id]


def report_spec(relative_path: str | Path) -> ReportSpec:
    normalized = str(relative_path).replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return REPORT_REGISTRY[normalized]


PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "InHandBonus",
        "OnBoardBonus",
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "BeforeEndTurnBonus",
        "BeforeOverkilledBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
        "InHandPlayPriority",
    }
)

REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "OnAdaptCardBonus",
        "BeforeUpgradeCardBonus",
        "OnBoardPlayPriority",
    }
)

CARD_BEHAVIOR_BLOCKS = (
    PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS
    | REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS
)


def _card_behavior_registry_row(block: str) -> dict[str, Any]:
    if block in REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS:
        return {
            "support": "supported",
            "normal_path_runtime": True,
            "surface_family": "card_behavior",
            "source_backing": "repo_supported_source_gap",
            "source_note": (
                "Repo-supported block; not confirmed in the latest public-doc audit."
            ),
        }
    return {
        "support": "supported",
        "normal_path_runtime": True,
        "surface_family": "card_behavior",
        "source_backing": "public_doc_confirmed",
        "source_note": (
            "Confirmed by HearthRanger VisionAI public docs or prior HSConfig surface audit."
        ),
    }


CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    block: _card_behavior_registry_row(block) for block in CARD_BEHAVIOR_BLOCKS
}

CARD_BEHAVIOR_BLOCK_REGISTRY.update(
    {
        "Presume.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
            "source_backing": "legacy_gated",
            "source_note": "Known surface, intentionally outside the normal HSConfig path.",
        },
        "Concede.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
            "source_backing": "legacy_gated",
            "source_note": "Known surface, intentionally outside the normal HSConfig path.",
        },
    }
)

NORMAL_PATH_FORBIDDEN_SURFACES = FORBIDDEN_RUNTIME_SURFACES

SPECIAL_SURFACES = {
    name: name.removesuffix(".json")
    for name in SPECIAL_RUNTIME_SURFACES
    if name != "CardBehavior.json"
}

RESERVED_NON_RUNTIME_SURFACES = frozenset(
    {
        "CardBehavior.json",
        "card_role_map.json",
        "config_row_provenance.json",
        "operator_review.json",
        "package_validation.json",
        "validation_report.json",
    }
)


def supported_surface(filename: str | Path) -> bool:
    name = Path(filename).name
    if name in SPECIAL_SURFACES:
        return True
    if name in RESERVED_NON_RUNTIME_SURFACES:
        return False
    if not name.endswith(".json"):
        return False
    return bool(CARD_ID_SURFACE_RE.fullmatch(name)) and bool(name[:-5])


def runtime_block_support(block_name: str) -> dict[str, Any]:
    if block_name in CARD_BEHAVIOR_BLOCK_REGISTRY:
        return dict(CARD_BEHAVIOR_BLOCK_REGISTRY[block_name])
    return {
        "support": "unsupported",
        "normal_path_runtime": False,
        "surface_family": "unknown",
        "source_backing": "unsupported",
        "source_note": "No HSConfig runtime support.",
    }


def is_supported_card_behavior_block(block_name: str) -> bool:
    row = runtime_block_support(block_name)
    return row["support"] == "supported" and row["normal_path_runtime"] is True


def expected_game_card_id(filename: str | Path) -> str | None:
    name = Path(filename).name
    if name in SPECIAL_SURFACES:
        return SPECIAL_SURFACES[name]
    if supported_surface(name):
        return name[:-5]
    return None


def is_special_surface(filename: str | Path) -> bool:
    return Path(filename).name in SPECIAL_SURFACES
