"""Immutable domain values for the typed pre-run package boundary."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import json
import re
from dataclasses import MISSING, dataclass, fields
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from typing import Any, Literal


class _ImmutableAuthorityMeta(type):
    """Ensure every authority tuple subclass remains slotless."""

    def __new__(
        metaclass,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        namespace.setdefault("__slots__", ())
        return super().__new__(
            metaclass,
            name,
            bases,
            namespace,
            **kwargs,
        )


class _ImmutableAuthorityNode(
    tuple,
    metaclass=_ImmutableAuthorityMeta,
):
    """Dataclass-compatible tuple storage with no writable object state."""

    __slots__ = ()

    def __new__(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> _ImmutableAuthorityNode:
        return cls._create_authority_node(*args, **kwargs)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del self, args, kwargs

    @classmethod
    def _create_authority_node(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> _ImmutableAuthorityNode:
        declared = fields(cls)
        if len(args) > len(declared):
            raise TypeError(
                f"{cls.__name__} expected at most {len(declared)} arguments"
            )
        values: list[Any] = []
        remaining = dict(kwargs)
        for index, field in enumerate(declared):
            if index < len(args):
                if field.name in remaining:
                    raise TypeError(
                        f"{cls.__name__} got multiple values for "
                        f"{field.name}"
                    )
                value = args[index]
            elif field.name in remaining:
                value = remaining.pop(field.name)
            elif field.default is not MISSING:
                value = field.default
            elif field.default_factory is not MISSING:
                value = field.default_factory()
            else:
                raise TypeError(
                    f"{cls.__name__} missing required argument: "
                    f"{field.name}"
                )
            values.append(value)
        if remaining:
            unexpected = next(iter(remaining))
            raise TypeError(
                f"{cls.__name__} got an unexpected argument: {unexpected}"
            )
        normalized = cls._normalize_authority_values(
            {
                field.name: value
                for field, value in zip(declared, values, strict=True)
            }
        )
        instance = tuple.__new__(
            cls,
            tuple(normalized[field.name] for field in declared),
        )
        post_init = getattr(instance, "__post_init__", None)
        if post_init is not None:
            post_init()
        return instance

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            field.name: _freeze_authority_field(
                field.type,
                values[field.name],
            )
            for field in fields(cls)
        }

    def __getattribute__(self, name: str) -> Any:
        for index, field in enumerate(fields(type(self))):
            if field.name == name:
                return tuple.__getitem__(self, index)
        return tuple.__getattribute__(self, name)

    def __reduce__(self) -> tuple[type, tuple[Any, ...]]:
        return type(self), tuple(self)


def _freeze_authority_field(annotation: Any, value: Any) -> Any:
    annotation_name = str(annotation)
    if annotation is bytes or annotation_name == "bytes":
        return bytes(value)
    if annotation is tuple or annotation_name.startswith("tuple["):
        return tuple(value)
    return value


class FrozenDefinitionMapping(tuple, Mapping[Any, Any]):
    """Immutable mapping storage with detached-copy compatibility."""

    __slots__ = ()

    def __new__(
        cls,
        values: Mapping[Any, Any],
    ) -> FrozenDefinitionMapping:
        return tuple.__new__(
            cls,
            tuple(values.items()),
        )

    def __setattr__(self, name: str, value: Any) -> None:
        del name, value
        raise TypeError("frozen_definition")

    def __getitem__(self, key: Any) -> Any:
        for item_key, item_value in tuple.__iter__(self):
            if item_key == key:
                return item_value
        raise KeyError(key)

    def __iter__(self):
        return (
            item_key
            for item_key, _item_value in tuple.__iter__(self)
        )

    def __len__(self) -> int:
        return tuple.__len__(self)

    def __contains__(self, key: object) -> bool:
        return any(
            item_key == key
            for item_key, _item_value in tuple.__iter__(self)
        )

    def __repr__(self) -> str:
        return repr(dict(self))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Mapping) and dict(self) == dict(other)

    def __setitem__(self, key: Any, value: Any) -> None:
        del key, value
        raise TypeError("frozen_definition")

    def __delitem__(self, key: Any) -> None:
        del key
        raise TypeError("frozen_definition")

    def __ior__(self, other: object):
        del other
        raise TypeError("frozen_definition")

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[Any, Any]:
        from copy import deepcopy

        return deepcopy(dict(self), memo)

    def __reduce__(self):
        return type(self), (dict(self),)


class FrozenDefinitionList(tuple):
    """Immutable sequence storage with list-compatible equality."""

    __slots__ = ()

    def __new__(cls, values: Iterable[Any]) -> FrozenDefinitionList:
        return tuple.__new__(cls, tuple(values))

    def __setattr__(self, name: str, value: Any) -> None:
        del name, value
        raise TypeError("frozen_definition")

    def __repr__(self) -> str:
        return repr(list(self))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Sequence) and tuple(self) == tuple(other)

    def __deepcopy__(self, memo: dict[int, Any]) -> list[Any]:
        from copy import deepcopy

        return deepcopy(list(self), memo)

def deep_freeze_definition(value: Any) -> Any:
    """Recursively freeze a module-level canonical definition."""

    if isinstance(value, Mapping):
        return FrozenDefinitionMapping(
            {
                key: deep_freeze_definition(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, list):
        return FrozenDefinitionList(
            deep_freeze_definition(item) for item in value
        )
    if isinstance(value, tuple):
        return tuple(deep_freeze_definition(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(deep_freeze_definition(item) for item in value)
    return value


def materialize_definition(value: Any) -> Any:
    """Return a detached mutable JSON-style copy of a frozen definition."""

    if isinstance(value, Mapping):
        return {
            key: materialize_definition(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, FrozenDefinitionList)):
        return [materialize_definition(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return {materialize_definition(item) for item in value}
    return value


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


_UNICODE_CONFUSABLE_PATH_SEPARATORS = frozenset(
    {
        "\u2044",  # fraction slash
        "\u2215",  # division slash
        "\u29f5",  # reverse solidus operator
        "\u29f8",  # big solidus
        "\ufe68",  # small reverse solidus
        "\uff0f",  # fullwidth solidus
        "\uff3c",  # fullwidth reverse solidus
    }
)


def canonical_relative_path(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(separator in value for separator in _UNICODE_CONFUSABLE_PATH_SEPARATORS)
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


@dataclass(frozen=True, init=False)
class PolicyProfile(_ImmutableAuthorityNode):
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


def globalvalues_baseline_sha256(
    decisions: tuple["GlobalValueDecision", ...],
) -> str:
    baseline = {
        decision.key: json.loads(decision.baseline_canonical_json)
        for decision in decisions
    }
    canonical = json.dumps(
        baseline,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def globalvalues_decision_ledger_content_sha256(
    decisions: tuple["GlobalValueDecision", ...],
) -> str:
    records = [
        {
            "key": decision.key,
            "kind": decision.kind.value,
            "value": json.loads(decision.emitted_canonical_json),
            "authority_id": decision.authority_id,
            "claim_ids": list(decision.claim_ids),
        }
        for decision in decisions
    ]
    canonical = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


@dataclass(frozen=True, init=False)
class EvidenceAuthority(_ImmutableAuthorityNode):
    lane: EvidenceLane
    authority_id: str
    source_identity: str
    as_of_date: str
    claim_kind: str
    content_sha256: str
    exact_deck_fingerprint: str | None
    runtime_authorized: bool
    reason: str


@dataclass(frozen=True, init=False)
class LayeredEvidenceContract(_ImmutableAuthorityNode):
    deck_fingerprint: str
    authorities: tuple[EvidenceAuthority, ...]
    exact_guide_authority: bool
    layered_coverage_numerator: int
    layered_coverage_denominator: int
    content_sha256: str

    def __post_init__(self) -> None:
        tuple(self.authorities)


@dataclass(frozen=True, init=False)
class CardDispositionRow(_ImmutableAuthorityNode):
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
        _freeze_stable_strings(
            self.evidence_ids,
            field="evidence_ids",
        )
        _freeze_stable_strings(
            self.claim_ids,
            field="claim_ids",
        )
        runtime_paths = tuple(self.runtime_paths)
        for path in runtime_paths:
            canonical_relative_path(path)
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


@dataclass(frozen=True, init=False)
class ClaimDispositionRow(_ImmutableAuthorityNode):
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


@dataclass(frozen=True, init=False)
class DispositionLedger(_ImmutableAuthorityNode):
    deck_fingerprint: str
    cards: tuple[CardDispositionRow, ...]
    claims: tuple[ClaimDispositionRow, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        cards = tuple(self.cards)
        claims = tuple(self.claims)
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


@dataclass(frozen=True, init=False)
class DualClosureStatus(_ImmutableAuthorityNode):
    pre_run_contract_status: Literal["complete", "incomplete"]
    strategy_authority_status: Literal["partial", "strong"]
    exact_guide_authority: bool
    unresolved_reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        _freeze_stable_strings(
            self.unresolved_reasons,
            field="dual_closure_unresolved_reasons",
        )


@dataclass(frozen=True, init=False)
class GlobalValueDecision(_ImmutableAuthorityNode):
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
        _freeze_stable_strings(
            self.claim_ids,
            field="globalvalue_claim_ids",
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


@dataclass(frozen=True, init=False)
class GlobalValuesDecisionLedger(_ImmutableAuthorityNode):
    deck_fingerprint: str
    baseline_sha256: str
    decisions: tuple[GlobalValueDecision, ...]
    content_sha256: str

    def __post_init__(self) -> None:
        decisions = tuple(self.decisions)
        if (
            not isinstance(self.deck_fingerprint, str)
            or not self.deck_fingerprint
            or self.deck_fingerprint != self.deck_fingerprint.strip()
        ):
            raise ValueError("globalvalues_deck_fingerprint_invalid")
        if any(
            decision.deck_fingerprint != self.deck_fingerprint
            for decision in decisions
        ):
            raise ValueError("globalvalues_decision_deck_fingerprint_mismatch")
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
        if self.baseline_sha256 != globalvalues_baseline_sha256(decisions):
            raise ValueError("globalvalues_baseline_sha256_invalid")
        if (
            self.content_sha256
            != globalvalues_decision_ledger_content_sha256(decisions)
        ):
            raise ValueError("globalvalues_ledger_content_sha256_invalid")


@dataclass(frozen=True, init=False)
class MulliganRuleModel(_ImmutableAuthorityNode):
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
        _freeze_stable_strings(
            self.source_claim_ids,
            field="mulligan_source_claim_ids",
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


@dataclass(frozen=True, init=False)
class MulliganSuppressionModel(_ImmutableAuthorityNode):
    card_id: str
    action: Literal["hold", "discard", "none"]
    reason_code: str
    source_claim_ids: tuple[str, ...]
    claim_id: str | None = None
    source_type: str | None = None
    source_url: str | None = None

    def __post_init__(self) -> None:
        _freeze_stable_strings(
            self.source_claim_ids,
            field="suppression_source_claim_ids",
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


@dataclass(frozen=True, init=False)
class BotDelegationModel(_ImmutableAuthorityNode):
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


@dataclass(frozen=True, init=False)
class MulliganPlanModel(_ImmutableAuthorityNode):
    deck_name: str
    rules: tuple[MulliganRuleModel, ...]
    suppressed: tuple[MulliganSuppressionModel, ...]
    bot_delegated: tuple[BotDelegationModel, ...]
    merged_duplicate_rule_count: int

    def __post_init__(self) -> None:
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


class ComboTiming(StrEnum):
    SAME_TURN = "same_turn"
    CROSS_TURN = "cross_turn"

    @property
    def operator(self) -> str:
        return {
            ComboTiming.SAME_TURN: ">>",
            ComboTiming.CROSS_TURN: ">->",
        }[self]

    @classmethod
    def from_operator(cls, operator: str) -> ComboTiming:
        timings = {
            timing.operator: timing
            for timing in cls
        }
        try:
            return timings[operator]
        except KeyError as error:
            raise ValueError("combo_operator_invalid") from error


def _combo_strings(
    values: Any,
    *,
    field: str,
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field}_container_invalid")
    frozen = tuple(values)
    if any(
        not isinstance(value, str)
        or not value
        or value != value.strip()
        for value in frozen
    ):
        raise ValueError(f"{field}_invalid")
    return frozen


@dataclass(frozen=True, init=False)
class ComboDecisionModel(_ImmutableAuthorityNode):
    rule_id: str
    cards: tuple[str, ...]
    timing: ComboTiming
    values: tuple[str, ...]
    condition: str
    source_claim_ids: tuple[str, ...]
    confidence: str
    source_refs: tuple[str, ...]
    claim_id: str | None = None

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["cards"] = _combo_strings(
            values["cards"],
            field="combo_cards",
        )
        normalized["values"] = _combo_strings(
            values["values"],
            field="combo_values",
        )
        normalized["source_claim_ids"] = _combo_strings(
            values["source_claim_ids"],
            field="combo_source_claim_ids",
        )
        normalized["source_refs"] = _combo_strings(
            values["source_refs"],
            field="combo_source_refs",
        )
        return normalized

    def __post_init__(self) -> None:
        for field_name in ("rule_id", "condition", "confidence"):
            value = getattr(self, field_name)
            if (
                not isinstance(value, str)
                or not value
                or value != value.strip()
            ):
                raise ValueError(f"combo_{field_name}_invalid")
        if not isinstance(self.timing, ComboTiming):
            raise ValueError("combo_timing_invalid")
        cards = _combo_strings(self.cards, field="combo_cards")
        values = _combo_strings(self.values, field="combo_values")
        if len(cards) < 2:
            raise ValueError("combo_sequence_too_short")
        if len(cards) != len(values):
            raise ValueError("combo_value_segment_mismatch")
        for value in values:
            try:
                decimal_value = Decimal(value)
            except InvalidOperation as error:
                raise ValueError("combo_value_invalid") from error
            if not decimal_value.is_finite():
                raise ValueError("combo_value_invalid")
        _combo_strings(
            self.source_claim_ids,
            field="combo_source_claim_ids",
        )
        _combo_strings(
            self.source_refs,
            field="combo_source_refs",
        )
        if self.claim_id is not None and (
            not isinstance(self.claim_id, str)
            or not self.claim_id
            or self.claim_id != self.claim_id.strip()
        ):
            raise ValueError("combo_claim_id_invalid")
        if not self.source_claim_ids and self.claim_id is None:
            raise ValueError("combo_decision_authority_missing")

    @property
    def operator(self) -> str:
        return self.timing.operator

    @classmethod
    def from_plan_row(
        cls,
        row: Mapping[str, Any],
    ) -> ComboDecisionModel:
        operator = str(row.get("operator", ">>"))
        timing_value = row.get("timing_kind")
        timing = (
            ComboTiming(str(timing_value))
            if timing_value is not None
            else ComboTiming.from_operator(operator)
        )
        if operator != timing.operator:
            raise ValueError("combo_operator_timing_mismatch")
        return cls(
            rule_id=str(row.get("rule_id", "combo_sequence")),
            cards=_combo_mapping_strings(row, "cards"),
            timing=timing,
            values=_combo_mapping_strings(row, "values"),
            condition=str(row.get("condition", "*")),
            source_claim_ids=_combo_mapping_strings(
                row,
                "source_claim_ids",
            ),
            confidence=str(row.get("confidence", "source_backed")),
            source_refs=_combo_mapping_strings(row, "source_refs"),
            claim_id=(
                str(row["claim_id"])
                if row.get("claim_id") is not None
                else None
            ),
        )

    def to_report_row(self) -> dict[str, Any]:
        first_value = self.values[0] if self.values else "10"
        try:
            report_value = int(first_value)
        except (TypeError, ValueError):
            report_value = 10
        return {
            "rule_id": self.rule_id,
            "cards": list(self.cards),
            "timing_kind": self.timing.value,
            "operator": self.operator,
            "values": list(self.values),
            "condition": self.condition,
            "source_claim_ids": list(self.source_claim_ids),
            "confidence": self.confidence,
            **({"claim_id": self.claim_id} if self.claim_id else {}),
            "source_refs": list(self.source_refs),
            "combo": self.operator.join(self.cards),
            "value": report_value,
        }


def _combo_mapping_strings(
    row: Mapping[str, Any],
    field: str,
) -> tuple[str, ...]:
    values = row.get(field, ())
    frozen = _combo_strings(values, field=f"combo_{field}")
    return tuple(str(value) for value in frozen)


@dataclass(frozen=True, init=False)
class ComboSuppressionModel(_ImmutableAuthorityNode):
    cards: tuple[str, ...]
    reason_code: str
    claim_id: str | None = None
    missing_cards: tuple[str, ...] = ()

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["cards"] = _combo_strings(
            values["cards"],
            field="combo_suppression_cards",
        )
        normalized["missing_cards"] = _combo_strings(
            values["missing_cards"],
            field="combo_suppression_missing_cards",
        )
        return normalized

    def __post_init__(self) -> None:
        _combo_strings(
            self.cards,
            field="combo_suppression_cards",
        )
        _combo_strings(
            self.missing_cards,
            field="combo_suppression_missing_cards",
        )
        if (
            not isinstance(self.reason_code, str)
            or not self.reason_code
            or self.reason_code != self.reason_code.strip()
        ):
            raise ValueError("combo_suppression_reason_invalid")
        if (
            not isinstance(self.claim_id, str)
            or not self.claim_id
            or self.claim_id != self.claim_id.strip()
        ):
            raise ValueError("combo_suppression_claim_id_invalid")

    @property
    def identity(
        self,
    ) -> tuple[str, tuple[str, ...], str, tuple[str, ...]]:
        return (
            self.claim_id or "",
            self.cards,
            self.reason_code,
            self.missing_cards,
        )

    @classmethod
    def from_report_row(
        cls,
        row: Mapping[str, Any],
    ) -> ComboSuppressionModel:
        return cls(
            cards=_combo_mapping_strings(row, "cards"),
            reason_code=str(row.get("reason", "")),
            claim_id=(
                str(row["claim_id"])
                if row.get("claim_id") is not None
                else None
            ),
            missing_cards=_combo_mapping_strings(row, "missing_cards"),
        )

    def to_report_row(self) -> dict[str, Any]:
        return {
            **({"claim_id": self.claim_id} if self.claim_id else {}),
            "cards": list(self.cards),
            "reason": self.reason_code,
            **(
                {"missing_cards": list(self.missing_cards)}
                if self.missing_cards
                else {}
            ),
        }


@dataclass(frozen=True, init=False)
class ComboPlanModel(_ImmutableAuthorityNode):
    decisions: tuple[ComboDecisionModel, ...]
    suppressions: tuple[ComboSuppressionModel, ...]

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        normalized["decisions"] = _combo_model_container(
            values["decisions"],
            field="combo_decisions",
        )
        normalized["suppressions"] = _combo_model_container(
            values["suppressions"],
            field="combo_suppressions",
        )
        return normalized

    def __post_init__(self) -> None:
        decisions = _combo_model_container(
            self.decisions,
            field="combo_decisions",
        )
        suppressions = _combo_model_container(
            self.suppressions,
            field="combo_suppressions",
        )
        if any(
            not isinstance(decision, ComboDecisionModel)
            for decision in decisions
        ):
            raise TypeError("combo_decision_invalid")
        if any(
            not isinstance(suppression, ComboSuppressionModel)
            for suppression in suppressions
        ):
            raise TypeError("combo_suppression_invalid")
        decision_ids = tuple(decision.rule_id for decision in decisions)
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("combo_decision_id_duplicate")
        suppression_ids = tuple(
            suppression.identity for suppression in suppressions
        )
        if len(set(suppression_ids)) != len(suppression_ids):
            raise ValueError("combo_suppression_duplicate")
        if tuple(sorted(suppression_ids)) != suppression_ids:
            raise ValueError("combo_suppression_order_unstable")

    @classmethod
    def from_report(cls, report: Mapping[str, Any]) -> ComboPlanModel:
        combos = _combo_report_rows(report, "combos")
        suppressions = _combo_report_rows(report, "suppressed")
        return cls(
            decisions=tuple(
                ComboDecisionModel.from_plan_row(row)
                for row in combos
            ),
            suppressions=tuple(
                ComboSuppressionModel.from_report_row(row)
                for row in suppressions
            ),
        )

    def to_report(self) -> dict[str, Any]:
        return {
            "combos": [
                decision.to_report_row()
                for decision in self.decisions
            ],
            "suppressed": [
                suppression.to_report_row()
                for suppression in self.suppressions
            ],
        }


def _combo_model_container(
    values: Any,
    *,
    field: str,
) -> tuple[Any, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError(f"{field}_container_invalid")
    return tuple(values)


def _combo_report_rows(
    report: Mapping[str, Any],
    field: str,
) -> tuple[Mapping[str, Any], ...]:
    values = report.get(field, ())
    if not isinstance(values, (list, tuple)):
        raise ValueError("Invalid combo sequence collection")
    rows = tuple(values)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("Invalid combo sequence collection")
    return rows


ComboDecision = ComboDecisionModel
ComboSuppression = ComboSuppressionModel
ComboPlan = ComboPlanModel


_RUNTIME_OWNERS = {
    "GlobalValues": "globalvalues",
    "Mulligan": "mulligan",
    "CardID": "cardid",
    "Combo": "combo",
}
_RUNTIME_OWNERS = deep_freeze_definition(_RUNTIME_OWNERS)


@dataclass(frozen=True, init=False)
class RuntimeSurfaceDecision(_ImmutableAuthorityNode):
    family: Literal["GlobalValues", "Mulligan", "CardID", "Combo"]
    relative_path: str
    owner: str
    decision_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _freeze_stable_strings(
            self.decision_ids,
            field="runtime_surface_decision_ids",
        )
        if self.family not in _RUNTIME_OWNERS:
            raise ValueError("runtime_surface_family_unknown")
        if self.owner != _RUNTIME_OWNERS[self.family]:
            raise ValueError("runtime_surface_owner_unknown")
        canonical_relative_path(self.relative_path)


@dataclass(frozen=True, init=False)
class RuntimeSurfacePlan(_ImmutableAuthorityNode):
    surfaces: tuple[RuntimeSurfaceDecision, ...]

    def __post_init__(self) -> None:
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
