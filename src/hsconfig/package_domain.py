"""Immutable domain values for the typed pre-run package boundary."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal


def _canonical_json(value: bytes) -> bytes:
    try:
        decoded = json.loads(value)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("canonical_json_invalid") from error
    canonical = json.dumps(
        decoded, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if value != canonical:
        raise ValueError("canonical_json_required")
    return canonical


def _require_stable_strings(values: tuple[str, ...], *, field: str) -> None:
    if any(not value or value != value.strip() for value in values):
        raise ValueError(f"{field}_invalid")
    if tuple(sorted(set(values))) != values:
        raise ValueError(f"{field}_must_be_unique_sorted")


def _freeze_stable_strings(values: tuple[str, ...], *, field: str) -> tuple[str, ...]:
    frozen = tuple(values)
    _require_stable_strings(frozen, field=field)
    return frozen


def canonical_relative_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or "\x00" in value
        or ":" in value
        or value.startswith("/")
        or value.startswith("//")
        or re.match(r"^[A-Za-z]:", value) is not None
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("runtime_surface_path_invalid")
    return value


class EvidenceLane(StrEnum):
    OFFICIAL_CARD_DATA = "A"
    EXACT_LIVE_GUIDE = "B"
    ARCHETYPE_OR_MECHANIC_GUIDE = "C"
    VERSIONED_INTERNAL_POLICY = "D"
    BOT_DELEGATION = "E"


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    policy_id: str
    version: int
    effective_date: str
    content_sha256: str
    rules_canonical_json: bytes

    def __post_init__(self) -> None:
        if (
            not isinstance(self.policy_id, str)
            or not self.policy_id
            or self.policy_id != self.policy_id.strip()
        ):
            raise ValueError("policy_profile_id_invalid")
        if (
            not isinstance(self.version, int)
            or isinstance(self.version, bool)
            or self.version < 1
        ):
            raise ValueError("policy_profile_version_invalid")
        try:
            parsed_date = date.fromisoformat(self.effective_date)
        except (TypeError, ValueError) as error:
            raise ValueError("policy_profile_effective_date_invalid") from error
        if parsed_date.isoformat() != self.effective_date:
            raise ValueError("policy_profile_effective_date_invalid")
        canonical_rules = _canonical_json(bytes(self.rules_canonical_json))
        expected_sha256 = f"sha256:{sha256(canonical_rules).hexdigest()}"
        if self.content_sha256 != expected_sha256:
            raise ValueError("policy_profile_content_sha256_invalid")
        rules = json.loads(canonical_rules)
        if not isinstance(rules, list) or not rules:
            raise ValueError("policy_profile_rules_invalid")
        object.__setattr__(self, "rules_canonical_json", canonical_rules)


class CardDisposition(StrEnum):
    RUNTIME_EMITTED = "runtime_emitted"
    BOT_DELEGATED = "bot_delegated"
    SUPPRESSED_UNSUPPORTED_SURFACE = "suppressed_unsupported_surface"
    SUPPRESSED_INSUFFICIENT_AUTHORITY = "suppressed_insufficient_authority"
    ANALYSIS_ONLY_SIDEBOARD = "analysis_only_sideboard"


class ClaimDisposition(StrEnum):
    RUNTIME_EMITTED = "runtime_emitted"
    CONTRACT_ONLY = "contract_only"
    BOT_DELEGATED = "bot_delegated"
    SUPPRESSED_UNSUPPORTED_SURFACE = "suppressed_unsupported_surface"
    SUPPRESSED_INSUFFICIENT_AUTHORITY = "suppressed_insufficient_authority"


class GlobalValueDecisionKind(StrEnum):
    COPY_BASELINE = "copy_baseline"
    AUTHORIZED_OVERLAY = "authorized_overlay"


@dataclass(frozen=True, slots=True)
class EvidenceAuthority:
    lane: EvidenceLane
    authority_id: str
    source_identity: str
    as_of_date: str
    claim_kind: str
    content_sha256: str
    exact_deck_fingerprint: str | None
    runtime_authorized: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LayeredEvidenceContract:
    deck_fingerprint: str
    authorities: tuple[EvidenceAuthority, ...]
    exact_guide_authority: bool
    layered_coverage_numerator: int
    layered_coverage_denominator: int
    content_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "authorities", tuple(self.authorities))


@dataclass(frozen=True, slots=True)
class CardDispositionRow:
    deck_fingerprint: str
    composite_card_key: str
    zone: Literal["main_deck", "sideboard_module"]
    official_semantics_canonical_json: bytes
    authority_lane: EvidenceLane
    evidence_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    physical_owner: str
    disposition: CardDisposition
    runtime_paths: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evidence_ids",
            _freeze_stable_strings(self.evidence_ids, field="evidence_ids"),
        )
        object.__setattr__(
            self,
            "claim_ids",
            _freeze_stable_strings(self.claim_ids, field="claim_ids"),
        )
        runtime_paths = tuple(self.runtime_paths)
        for path in runtime_paths:
            canonical_relative_path(path)
        object.__setattr__(self, "runtime_paths", runtime_paths)
        canonical_semantics = _canonical_json(
            self.official_semantics_canonical_json
        )
        expected_runtime_paths = (f"{self.physical_owner}.json",)
        if self.disposition is CardDisposition.RUNTIME_EMITTED:
            semantics = json.loads(canonical_semantics)
            if (
                not isinstance(semantics, dict)
                or not self.physical_owner
                or type(semantics.get("GameCardId")) is not str
                or semantics["GameCardId"] != self.physical_owner
            ):
                raise ValueError(
                    "card_disposition_physical_semantics_invalid"
                )
            if runtime_paths != expected_runtime_paths:
                raise ValueError("card_disposition_runtime_path_mismatch")
        elif runtime_paths:
            raise ValueError("card_disposition_runtime_path_forbidden")


@dataclass(frozen=True, slots=True)
class ClaimDispositionRow:
    deck_fingerprint: str
    claim_id: str
    claim_kind: str
    evidence_id: str
    disposition: ClaimDisposition
    runtime_paths: tuple[str, ...]
    reason_code: str

    def __post_init__(self) -> None:
        runtime_paths = tuple(self.runtime_paths)
        for path in runtime_paths:
            canonical_relative_path(path)
        object.__setattr__(self, "runtime_paths", runtime_paths)


def disposition_ledger_content_sha256(
    *,
    deck_fingerprint: str,
    cards: tuple[CardDispositionRow, ...],
    claims: tuple[ClaimDispositionRow, ...],
) -> str:
    """Hash the canonical semantic content of a disposition ledger."""

    payload = {
        "deck_fingerprint": deck_fingerprint,
        "cards": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "composite_card_key": row.composite_card_key,
                "zone": row.zone,
                "official_semantics_canonical_json": json.loads(
                    row.official_semantics_canonical_json
                ),
                "authority_lane": row.authority_lane.value,
                "evidence_ids": list(row.evidence_ids),
                "claim_ids": list(row.claim_ids),
                "physical_owner": row.physical_owner,
                "disposition": row.disposition.value,
                "runtime_paths": list(row.runtime_paths),
                "reason_code": row.reason_code,
            }
            for row in cards
        ],
        "claims": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "claim_id": row.claim_id,
                "claim_kind": row.claim_kind,
                "evidence_id": row.evidence_id,
                "disposition": row.disposition.value,
                "runtime_paths": list(row.runtime_paths),
                "reason_code": row.reason_code,
            }
            for row in claims
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


@dataclass(frozen=True, slots=True)
class DispositionLedger:
    deck_fingerprint: str
    cards: tuple[CardDispositionRow, ...]
    claims: tuple[ClaimDispositionRow, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        cards = tuple(self.cards)
        claims = tuple(self.claims)
        object.__setattr__(self, "cards", cards)
        object.__setattr__(self, "claims", claims)
        if any(row.deck_fingerprint != self.deck_fingerprint for row in cards):
            raise ValueError("card_disposition_deck_fingerprint_mismatch")
        if any(row.deck_fingerprint != self.deck_fingerprint for row in claims):
            raise ValueError("claim_disposition_deck_fingerprint_mismatch")
        if self.content_sha256 != disposition_ledger_content_sha256(
            deck_fingerprint=self.deck_fingerprint,
            cards=cards,
            claims=claims,
        ):
            raise ValueError("disposition_ledger_content_sha256_invalid")


@dataclass(frozen=True, slots=True)
class DualClosureStatus:
    pre_run_contract_status: Literal["complete", "incomplete"]
    strategy_authority_status: Literal["partial", "strong"]
    exact_guide_authority: bool
    unresolved_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unresolved_reasons",
            _freeze_stable_strings(
                self.unresolved_reasons,
                field="dual_closure_unresolved_reasons",
            ),
        )


@dataclass(frozen=True, slots=True)
class GlobalValueDecision:
    deck_fingerprint: str
    key: str
    kind: GlobalValueDecisionKind
    baseline_canonical_json: bytes
    emitted_canonical_json: bytes
    authority_id: str
    claim_ids: tuple[str, ...]
    reason: str

    def __post_init__(self) -> None:
        for field, value in (
            ("deck_fingerprint", self.deck_fingerprint),
            ("key", self.key),
            ("authority_id", self.authority_id),
            ("reason", self.reason),
        ):
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
            ):
                raise ValueError(f"globalvalue_{field}_invalid")
        if not isinstance(self.kind, GlobalValueDecisionKind):
            raise ValueError("globalvalue_kind_invalid")
        object.__setattr__(
            self,
            "claim_ids",
            _freeze_stable_strings(
                self.claim_ids,
                field="globalvalue_claim_ids",
            ),
        )
        _canonical_json(self.baseline_canonical_json)
        _canonical_json(self.emitted_canonical_json)
        if (
            self.kind is GlobalValueDecisionKind.COPY_BASELINE
            and self.baseline_canonical_json != self.emitted_canonical_json
        ):
            raise ValueError("globalvalue_copy_baseline_mismatch")
        if (
            self.kind is GlobalValueDecisionKind.AUTHORIZED_OVERLAY
            and not self.claim_ids
        ):
            raise ValueError("globalvalue_overlay_authority_missing")


@dataclass(frozen=True, slots=True)
class GlobalValuesDecisionLedger:
    deck_fingerprint: str
    baseline_sha256: str
    decisions: tuple[GlobalValueDecision, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        decisions = tuple(self.decisions)
        object.__setattr__(self, "decisions", decisions)
        keys = tuple(decision.key for decision in decisions)
        if any(
            not isinstance(key, str)
            or not key
            or key != key.strip()
            for key in keys
        ):
            raise ValueError("globalvalues_decision_key_invalid")
        if len(set(keys)) != len(keys):
            raise ValueError("globalvalues_decision_key_duplicate")


@dataclass(frozen=True, slots=True)
class MulliganRuleModel:
    card_id: str
    selector_kind: str
    selector_canonical_json: bytes
    action: Literal["hold", "discard"]
    condition_canonical_json: bytes
    reason: str
    confidence: str
    source_claim_ids: tuple[str, ...]
    claim_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_claim_ids",
            _freeze_stable_strings(
                self.source_claim_ids,
                field="mulligan_source_claim_ids",
            ),
        )
        if not self.card_id or not self.selector_kind or self.action not in {
            "hold",
            "discard",
        }:
            raise ValueError("mulligan_rule_invalid")
        if self.claim_id is not None and (
            not isinstance(self.claim_id, str)
            or not self.claim_id
            or self.claim_id != self.claim_id.strip()
        ):
            raise ValueError("mulligan_rule_claim_id_invalid")
        if not self.source_claim_ids and self.claim_id is None:
            raise ValueError("mulligan_rule_authorization_missing")
        _canonical_json(self.selector_canonical_json)
        _canonical_json(self.condition_canonical_json)

    @property
    def identity(self) -> tuple[str, str, bytes, str, bytes]:
        return (
            self.card_id,
            self.selector_kind,
            self.selector_canonical_json,
            self.action,
            self.condition_canonical_json,
        )


@dataclass(frozen=True, slots=True)
class MulliganSuppressionModel:
    card_id: str
    action: Literal["hold", "discard", "none"]
    reason_code: str
    source_claim_ids: tuple[str, ...]
    claim_id: str | None = None
    source_type: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_claim_ids",
            _freeze_stable_strings(
                self.source_claim_ids,
                field="suppression_source_claim_ids",
            ),
        )
        if not self.card_id or self.action not in {"hold", "discard", "none"}:
            raise ValueError("mulligan_suppression_invalid")
        for field_name in ("source_type", "source_url"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str)
                or not value
                or value != value.strip()
            ):
                raise ValueError(
                    f"mulligan_suppression_{field_name}_invalid"
                )


@dataclass(frozen=True, slots=True)
class BotDelegationModel:
    card_id: str
    evidence_lane: Literal["E"]
    policy_id: Literal["BOT_NATIVE_PRE_RUN"]
    reason_code: str

    def __post_init__(self) -> None:
        if (
            not self.card_id
            or self.evidence_lane != "E"
            or self.policy_id != "BOT_NATIVE_PRE_RUN"
            or not self.reason_code
        ):
            raise ValueError("bot_delegation_invalid")


@dataclass(frozen=True, slots=True)
class MulliganPlanModel:
    deck_name: str
    rules: tuple[MulliganRuleModel, ...]
    suppressed: tuple[MulliganSuppressionModel, ...]
    bot_delegated: tuple[BotDelegationModel, ...]
    merged_duplicate_rule_count: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "suppressed", tuple(self.suppressed))
        object.__setattr__(self, "bot_delegated", tuple(self.bot_delegated))
        identities = tuple(rule.identity for rule in self.rules)
        if len(set(identities)) != len(identities):
            raise ValueError("mulligan_duplicate_rule_identity")
        if tuple(sorted(identities)) != identities:
            raise ValueError("mulligan_rule_order_unstable")
        suppressed = tuple(row.card_id for row in self.suppressed)
        if len(set(suppressed)) != len(suppressed) or tuple(sorted(suppressed)) != suppressed:
            raise ValueError("mulligan_suppression_order_unstable")
        delegated = tuple(row.card_id for row in self.bot_delegated)
        if len(set(delegated)) != len(delegated) or tuple(sorted(delegated)) != delegated:
            raise ValueError("mulligan_delegation_order_unstable")
        exact_cards = {rule.card_id for rule in self.rules if rule.selector_kind == "card"}
        if exact_cards.intersection(delegated):
            raise ValueError("mulligan_card_ruled_and_delegated")
        if self.merged_duplicate_rule_count < 0:
            raise ValueError("mulligan_merged_duplicate_count_invalid")

    def to_report(self) -> dict[str, Any]:
        rules = [
            {
                "card": rule.card_id,
                "selector_kind": rule.selector_kind,
                "selector": json.loads(rule.selector_canonical_json),
                "action": rule.action,
                "condition": json.loads(rule.condition_canonical_json),
                "reason": rule.reason,
                "confidence": rule.confidence,
                "source_claim_ids": list(rule.source_claim_ids),
                "source_type": (
                    "versioned_internal_policy"
                    if rule.confidence == "policy_backed"
                    else "source_claim"
                ),
                **({"claim_id": rule.claim_id} if rule.claim_id else {}),
            }
            for rule in self.rules
        ]
        suppressed_rules = [
            {
                "card": row.card_id,
                "action": row.action,
                "reason": row.reason_code,
                "source_claim_ids": list(row.source_claim_ids),
                **({"claim_id": row.claim_id} if row.claim_id else {}),
                **(
                    {"source_type": row.source_type}
                    if row.source_type
                    else {}
                ),
                **(
                    {"source_url": row.source_url}
                    if row.source_url
                    else {}
                ),
            }
            for row in self.suppressed
        ]
        bot_delegated = [
            {
                "card_id": row.card_id,
                "evidence_lane": row.evidence_lane,
                "policy_id": row.policy_id,
                "reason_code": row.reason_code,
            }
            for row in self.bot_delegated
        ]
        source_rules = [
            row for row in rules if row["source_type"] == "source_claim"
        ]
        policy_rules = [
            row
            for row in rules
            if row["source_type"] == "versioned_internal_policy"
        ]
        source_keeps = [
            row for row in source_rules if row["action"] == "hold"
        ]
        policy_keeps = [
            row for row in policy_rules if row["action"] == "hold"
        ]
        suppressed_reasons: dict[str, int] = {}
        for row in suppressed_rules:
            reason = str(row["reason"])
            suppressed_reasons[reason] = (
                suppressed_reasons.get(reason, 0) + 1
            )
        has_concrete_keeps = bool(source_keeps or policy_keeps)
        if source_keeps:
            status = "rich"
            first_gap_reason = "none"
        elif policy_keeps:
            status = "policy_backed"
            first_gap_reason = str(policy_keeps[0]["reason"])
        elif bot_delegated:
            status = "bot_delegated"
            first_gap_reason = "delegated_to_hearthranger_bot"
        else:
            status = "thin"
            first_gap_reason = (
                str(suppressed_rules[0]["reason"])
                if suppressed_rules
                else "no_source_backed_mulligan_keeps"
            )
        policy_lanes = sorted(
            {
                *(["D"] if policy_rules else []),
                *(["E"] if bot_delegated else []),
            }
        )
        policy_reasons = sorted(
            {
                *(
                    str(row["reason"])
                    for row in policy_rules
                    if str(row["reason"])
                ),
                *(
                    str(row["reason_code"])
                    for row in bot_delegated
                    if str(row["reason_code"])
                ),
            }
        )
        quality: dict[str, Any] = {
            "has_concrete_keeps": has_concrete_keeps,
            "status": status,
            "first_gap_reason": first_gap_reason,
            "source_backed_rule_count": len(source_rules),
            "source_backed_keep_rule_count": len(source_keeps),
            "policy_backed_rule_count": len(policy_rules),
            "policy_backed_keep_rule_count": len(policy_keeps),
            "policy_lanes": policy_lanes,
            "policy_reasons": policy_reasons,
            "policy_result": {
                "status": status,
                "rules": policy_rules,
                "suppressed": suppressed_rules,
                "candidate_count": len(policy_rules) + len(bot_delegated),
                "selected_count": len(policy_rules),
                "delegated_count": len(bot_delegated),
                "excluded_count": len(suppressed_rules),
            },
            "default_only": not rules and not bot_delegated,
            "suppressed_rule_count": len(suppressed_rules),
            "suppressed_reasons": dict(sorted(suppressed_reasons.items())),
            "merged_duplicate_rule_count": self.merged_duplicate_rule_count,
            "bot_delegated_count": len(bot_delegated),
        }
        if status == "thin":
            quality["blocked_reason"] = "no_source_backed_mulligan_keeps"
        return {
            "deck_name": self.deck_name,
            "rules": rules,
            "suppressed_rules": suppressed_rules,
            "quality": quality,
            "bot_delegated": bot_delegated,
            "merged_duplicate_rule_count": self.merged_duplicate_rule_count,
        }


_RUNTIME_OWNERS = {
    "GlobalValues": "globalvalues",
    "Mulligan": "mulligan",
    "CardID": "cardid",
    "Combo": "combo",
}


@dataclass(frozen=True, slots=True)
class RuntimeSurfaceDecision:
    family: Literal["GlobalValues", "Mulligan", "CardID", "Combo"]
    relative_path: str
    owner: str
    decision_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision_ids",
            _freeze_stable_strings(
                self.decision_ids,
                field="runtime_surface_decision_ids",
            ),
        )
        if self.family not in _RUNTIME_OWNERS:
            raise ValueError("runtime_surface_family_unknown")
        if self.owner != _RUNTIME_OWNERS[self.family]:
            raise ValueError("runtime_surface_owner_unknown")
        canonical_relative_path(self.relative_path)


@dataclass(frozen=True, slots=True)
class RuntimeSurfacePlan:
    surfaces: tuple[RuntimeSurfaceDecision, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "surfaces", tuple(self.surfaces))
        paths = tuple(surface.relative_path for surface in self.surfaces)
        if tuple(sorted(paths)) != paths or len(set(paths)) != len(paths):
            raise ValueError("runtime_surface_paths_not_unique_sorted")
        families = tuple(surface.family for surface in self.surfaces)
        if families.count("GlobalValues") != 1 or families.count("Mulligan") != 1:
            raise ValueError("runtime_surface_core_missing_or_duplicate")
        core_paths = {surface.family: surface.relative_path for surface in self.surfaces}
        if (
            core_paths["GlobalValues"] != "GlobalValues.json"
            or core_paths["Mulligan"] != "Mulligan.json"
        ):
            raise ValueError("runtime_surface_core_path_invalid")
        for surface in self.surfaces:
            if surface.family == "GlobalValues" and any(
                not decision_id.startswith("globalvalues:")
                for decision_id in surface.decision_ids
            ):
                raise ValueError("runtime_surface_globalvalues_id_invalid")
            if surface.family == "Mulligan" and any(
                not decision_id.startswith("mulligan:")
                for decision_id in surface.decision_ids
            ):
                raise ValueError("runtime_surface_mulligan_id_invalid")
            if surface.family == "CardID":
                expected_ids = (
                    f"card:{surface.relative_path.removesuffix('.json')}",
                )
                if (
                    "/" in surface.relative_path
                    or not surface.relative_path.endswith(".json")
                    or surface.decision_ids != expected_ids
                ):
                    raise ValueError("runtime_surface_cardid_identity_mismatch")
        forbidden = {"Presume.json", "Concede.json", "CardBehavior.json"}
        if forbidden.intersection(paths):
            raise ValueError("runtime_surface_forbidden")

    @property
    def expected_files(self) -> tuple[str, ...]:
        return tuple(surface.relative_path for surface in self.surfaces)
