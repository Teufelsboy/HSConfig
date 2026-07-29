"""Typed pre-run emission metrics derived from verified physical rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
import json
from typing import Any, Literal

from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.globalvalues_decisions import (
    GLOBALVALUES_BASELINE_DECISION_KEYS,
    globalvalues_decision_ledger_document,
)
from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    DispositionLedger,
    DualClosureStatus,
    EvidenceAuthority,
    EvidenceLane,
    GlobalValueDecision,
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    canonical_relative_path,
)
from hsconfig.package_model import PackageView
from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    acquisition_closure_payload,
)


_EMITTABLE_DISPOSITIONS = frozenset(
    {
        CardDisposition.RUNTIME_EMITTED.value,
        ClaimDisposition.RUNTIME_EMITTED.value,
    }
)
_CARD_DISPOSITIONS = frozenset(row.value for row in CardDisposition)
_CLAIM_DISPOSITIONS = frozenset(row.value for row in ClaimDisposition)
PRE_RUN_REPORT_PATHS = (
    "reports/layered_evidence_contract.json",
    "reports/source_acquisition_closure.json",
    "reports/disposition_ledger.json",
    "reports/globalvalues_decision_ledger.json",
    "reports/pre_run_closure.json",
)
_AUDITED_PRE_RUN_TOTALS = {
    "main_slot_count": 360,
    "main_card_identity_count": 205,
    "sideboard_module_count": 3,
    "card_disposition_count": 208,
    "claim_count": 316,
    "globalvalues_decision_count": 456,
}


def _require_text(value: Any, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise ValueError(f"verified_emission_{field}_invalid")
    return value


def _content_sha256(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{sha256(canonical).hexdigest()}"


def _report_content_sha256(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("content_sha256", None)
    return _content_sha256(payload)


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _diagnostic_report_base(deck_fingerprint: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "deck_fingerprint": deck_fingerprint,
    }


def build_source_acquisition_closure_report(
    *,
    deck_fingerprint: str,
    acquisition_closure: AcquisitionClosure | None,
) -> dict[str, Any]:
    """Project the exact typed acquisition handoff or an explicit open state."""

    _require_text(deck_fingerprint, field="deck_fingerprint")
    if acquisition_closure is None:
        closure_document: dict[str, Any] = {
            "deck_fingerprint": deck_fingerprint,
            "attempt_id": "",
            "attempted_at": "",
            "attempted_urls": [],
            "successful_evidence_ids": [],
            "failed_attempts": [],
            "negative_search_documented": False,
            "checked_dossier": False,
            "policy_id": None,
            "status": "open",
            "content_sha256": _content_sha256(
                {
                    "deck_fingerprint": deck_fingerprint,
                    "status": "open",
                    "reason": "standalone_prepare_without_acquisition",
                }
            ),
        }
    else:
        if acquisition_closure.deck_fingerprint != deck_fingerprint:
            raise ValueError("source_acquisition_closure_cross_deck")
        closure_document = acquisition_closure_payload(
            acquisition_closure
        )
    source_acquisition_complete = closure_document["status"] in {
        "closed_with_evidence",
        "closed_negative_search",
    }
    report = {
        **_diagnostic_report_base(deck_fingerprint),
        "source_acquisition_complete": source_acquisition_complete,
        "acquisition_closure": closure_document,
    }
    report["content_sha256"] = _report_content_sha256(report)
    return report


@dataclass(frozen=True, slots=True)
class MetricRatio:
    """Exact ratio provenance, including the valid vacuous 0/0 case."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if (
            type(self.numerator) is not int
            or type(self.denominator) is not int
            or self.numerator < 0
            or self.denominator < 0
            or self.numerator > self.denominator
        ):
            raise ValueError("pre_run_metric_ratio_invalid")
        if self.denominator == 0 and self.numerator != 0:
            raise ValueError("pre_run_metric_zero_denominator")

    @property
    def vacuous(self) -> bool:
        return self.denominator == 0

    @property
    def normalized_fraction(self) -> Fraction:
        return (
            Fraction(1, 1)
            if self.vacuous
            else Fraction(self.numerator, self.denominator)
        )

    def to_document(self) -> dict[str, int | float | str | bool]:
        return {
            "numerator": self.numerator,
            "denominator": self.denominator,
            "fraction": f"{self.numerator}/{self.denominator}",
            "value": float(self.normalized_fraction),
            "vacuous": self.vacuous,
        }


@dataclass(frozen=True, slots=True)
class VerifiedSemanticExpectation:
    """One semantic row classified before physical emission."""

    deck_fingerprint: str
    composite_identity: str
    row_kind: Literal["card", "claim"]
    disposition: str
    expected_owner: str
    allowed_runtime_surfaces: tuple[str, ...]
    claim_id: str
    claim_linked: bool
    surface_allowed: bool
    schema_supported: bool
    authority_sufficient: bool

    def __post_init__(self) -> None:
        _require_text(self.deck_fingerprint, field="deck_fingerprint")
        _require_text(self.composite_identity, field="composite_identity")
        _require_text(self.expected_owner, field="expected_owner")
        if not self.composite_identity.startswith(
            f"{self.deck_fingerprint}:"
        ):
            raise ValueError("verified_emission_composite_identity_mismatch")
        if self.row_kind not in {"card", "claim"}:
            raise ValueError("verified_emission_row_kind_invalid")
        allowed_dispositions = (
            _CARD_DISPOSITIONS
            if self.row_kind == "card"
            else _CLAIM_DISPOSITIONS
        )
        if self.disposition not in allowed_dispositions:
            raise ValueError("verified_emission_disposition_invalid")
        if (
            not isinstance(self.claim_id, str)
            or self.claim_id != self.claim_id.strip()
            or (self.row_kind == "claim" and not self.claim_id)
        ):
            raise ValueError("verified_emission_claim_id_invalid")
        surfaces = tuple(self.allowed_runtime_surfaces)
        object.__setattr__(self, "allowed_runtime_surfaces", surfaces)
        if tuple(sorted(set(surfaces))) != surfaces:
            raise ValueError("verified_emission_surface_set_invalid")
        for surface in surfaces:
            canonical_relative_path(surface)
        for field_name in (
            "claim_linked",
            "surface_allowed",
            "schema_supported",
            "authority_sufficient",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"verified_emission_{field_name}_invalid")


@dataclass(frozen=True, slots=True)
class VerifiedPhysicalEmission:
    """One observed physical row, including unmatched or rejected rows."""

    deck_fingerprint: str
    physical_identity: str
    composite_identity: str | None
    physical_owner: str
    runtime_surface: str
    claim_id: str
    claim_linked: bool
    surface_allowed: bool
    schema_supported: bool
    authority_authorized: bool
    meaningful: bool

    def __post_init__(self) -> None:
        _require_text(self.deck_fingerprint, field="deck_fingerprint")
        _require_text(self.physical_identity, field="physical_identity")
        _require_text(self.physical_owner, field="physical_owner")
        _require_text(self.runtime_surface, field="runtime_surface")
        if not self.physical_identity.startswith(
            f"{self.deck_fingerprint}:"
        ):
            raise ValueError("verified_emission_physical_identity_mismatch")
        if self.composite_identity is not None:
            _require_text(
                self.composite_identity,
                field="composite_identity",
            )
            if not self.composite_identity.startswith(
                f"{self.deck_fingerprint}:"
            ):
                raise ValueError(
                    "verified_emission_composite_identity_mismatch"
                )
        if (
            not isinstance(self.claim_id, str)
            or self.claim_id != self.claim_id.strip()
        ):
            raise ValueError("verified_emission_claim_id_invalid")
        canonical_relative_path(self.runtime_surface)
        for field_name in (
            "claim_linked",
            "surface_allowed",
            "schema_supported",
            "authority_authorized",
            "meaningful",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"verified_emission_{field_name}_invalid")


@dataclass(frozen=True, slots=True)
class VerifiedEmissionInput:
    """Frozen semantic expectations joined to all physical observations."""

    deck_fingerprint: str
    expectations: tuple[VerifiedSemanticExpectation, ...]
    physical_rows: tuple[VerifiedPhysicalEmission, ...]

    def __post_init__(self) -> None:
        _require_text(self.deck_fingerprint, field="deck_fingerprint")
        expectations = tuple(self.expectations)
        physical_rows = tuple(self.physical_rows)
        object.__setattr__(self, "expectations", expectations)
        object.__setattr__(self, "physical_rows", physical_rows)
        if any(
            row.deck_fingerprint != self.deck_fingerprint
            for row in (*expectations, *physical_rows)
        ):
            raise ValueError("verified_emission_cross_deck_row")
        composite_ids = tuple(
            row.composite_identity for row in expectations
        )
        if len(set(composite_ids)) != len(composite_ids):
            raise ValueError("verified_emission_duplicate_expectation")
        physical_ids = tuple(
            row.physical_identity for row in physical_rows
        )
        if len(set(physical_ids)) != len(physical_ids):
            raise ValueError("verified_emission_duplicate_physical_row")


def is_emission_eligible(row: VerifiedSemanticExpectation) -> bool:
    """Return true only when every semantic lowering condition is closed."""

    return (
        row.disposition in _EMITTABLE_DISPOSITIONS
        and bool(row.allowed_runtime_surfaces)
        and row.surface_allowed
        and row.schema_supported
        and row.authority_sufficient
        and row.claim_linked
    )


def _authorized_physical_emission(
    physical: VerifiedPhysicalEmission,
    expectation: VerifiedSemanticExpectation | None,
) -> bool:
    return (
        expectation is not None
        and physical.meaningful
        and is_emission_eligible(expectation)
        and physical.physical_owner == expectation.expected_owner
        and physical.runtime_surface
        in expectation.allowed_runtime_surfaces
        and physical.claim_id == expectation.claim_id
        and physical.claim_linked
        and physical.surface_allowed
        and physical.schema_supported
        and physical.authority_authorized
    )


def emission_precision(verified: VerifiedEmissionInput) -> MetricRatio:
    """Measure authorized meaningful emissions over all physical rows."""

    expectations = {
        row.composite_identity: row for row in verified.expectations
    }
    physical = tuple(
        row for row in verified.physical_rows if row.meaningful
    )
    authorized = sum(
        _authorized_physical_emission(
            row,
            expectations.get(row.composite_identity),
        )
        for row in physical
    )
    return MetricRatio(authorized, len(physical))


def eligible_emission_recall(
    verified: VerifiedEmissionInput,
) -> MetricRatio:
    """Measure eligible semantic expectations with a physical emission."""

    eligible = tuple(
        row for row in verified.expectations if is_emission_eligible(row)
    )
    emitted_identities = {
        row.composite_identity
        for row in verified.physical_rows
        if _authorized_physical_emission(
            row,
            next(
                (
                    expected
                    for expected in eligible
                    if expected.composite_identity
                    == row.composite_identity
                ),
                None,
            ),
        )
    }
    return MetricRatio(len(emitted_identities), len(eligible))


def disposition_ledger_document(
    ledger: DispositionLedger,
) -> dict[str, Any]:
    """Serialize the exact typed disposition ledger without rebuilding it."""

    return {
        **_diagnostic_report_base(ledger.deck_fingerprint),
        "content_sha256": ledger.content_sha256,
        "cards": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "composite_card_key": row.composite_card_key,
                "zone": row.zone,
                "official_semantics": json.loads(
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
            for row in ledger.cards
        ],
        "claims": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "composite_claim_identity": (
                    f"{ledger.deck_fingerprint}:{row.claim_id}"
                ),
                "claim_id": row.claim_id,
                "claim_kind": row.claim_kind,
                "evidence_id": row.evidence_id,
                "disposition": row.disposition.value,
                "runtime_paths": list(row.runtime_paths),
                "reason_code": row.reason_code,
            }
            for row in ledger.claims
        ],
    }


def globalvalues_decision_report_document(
    ledger: GlobalValuesDecisionLedger,
) -> dict[str, Any]:
    """Serialize Task-6's typed GlobalValues ledger as a canonical report."""

    return {
        **_diagnostic_report_base(ledger.deck_fingerprint),
        **globalvalues_decision_ledger_document(ledger),
    }


@dataclass(frozen=True, slots=True)
class BoundEvidenceAuthority:
    """A classified evidence authority explicitly bound to one package claim."""

    deck_fingerprint: str
    composite_claim_identity: str
    claim_id: str
    authority: EvidenceAuthority

    def __post_init__(self) -> None:
        _require_text(self.deck_fingerprint, field="deck_fingerprint")
        _require_text(
            self.composite_claim_identity,
            field="composite_claim_identity",
        )
        _require_text(self.claim_id, field="claim_id")
        if (
            self.composite_claim_identity
            != f"{self.deck_fingerprint}:{self.claim_id}"
        ):
            raise ValueError("evidence_authority_claim_binding_mismatch")
        if (
            self.authority.exact_deck_fingerprint is not None
            and self.authority.exact_deck_fingerprint
            != self.deck_fingerprint
        ):
            raise ValueError("evidence_authority_cross_deck")


def evidence_authority_from_projection(
    projection: Mapping[str, Any],
) -> EvidenceAuthority:
    """Load an already-classified authority projection, never raw guide data."""

    try:
        exact_deck_fingerprint = projection.get(
            "exact_deck_fingerprint"
        )
        if (
            exact_deck_fingerprint is not None
            and (
                not isinstance(exact_deck_fingerprint, str)
                or not exact_deck_fingerprint
            )
        ):
            raise ValueError("exact_deck_fingerprint_invalid")
        if type(projection["runtime_authorized"]) is not bool:
            raise ValueError("runtime_authorized_invalid")
        authority = EvidenceAuthority(
            lane=EvidenceLane(projection["lane"]),
            authority_id=_require_text(
                projection["authority_id"],
                field="authority_id",
            ),
            source_identity=_require_text(
                projection["source_identity"],
                field="source_identity",
            ),
            as_of_date=_require_text(
                projection["as_of_date"],
                field="as_of_date",
            ),
            claim_kind=_require_text(
                projection["claim_kind"],
                field="claim_kind",
            ),
            content_sha256=_require_text(
                projection["content_sha256"],
                field="content_sha256",
            ),
            exact_deck_fingerprint=exact_deck_fingerprint,
            runtime_authorized=projection["runtime_authorized"],
            reason=_require_text(
                projection["reason"],
                field="reason",
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("evidence_authority_projection_invalid") from error
    if not _is_sha256(authority.content_sha256):
        raise ValueError("evidence_authority_content_sha256_invalid")
    return authority


def _fallback_disposition_authority(
    *,
    ledger: DispositionLedger,
    claim: ClaimDispositionRow,
) -> EvidenceAuthority:
    card = next(
        (
            row
            for row in ledger.cards
            if claim.claim_id in row.claim_ids
        ),
        None,
    )
    lane = (
        card.authority_lane
        if card is not None
        else EvidenceLane.OFFICIAL_CARD_DATA
    )
    source_identity = (
        next(iter(card.evidence_ids), claim.evidence_id)
        if card is not None
        else claim.evidence_id
    )
    digest = _content_sha256(
        {
            "deck_fingerprint": ledger.deck_fingerprint,
            "claim_id": claim.claim_id,
            "evidence_id": claim.evidence_id,
            "lane": lane.value,
            "disposition": claim.disposition.value,
        }
    )
    return EvidenceAuthority(
        lane=lane,
        authority_id=f"disposition:{digest.removeprefix('sha256:')}",
        source_identity=source_identity,
        as_of_date="not_applicable",
        claim_kind=claim.claim_kind,
        content_sha256=digest,
        exact_deck_fingerprint=None,
        runtime_authorized=(
            claim.disposition is ClaimDisposition.RUNTIME_EMITTED
        ),
        reason="typed_final_disposition_authority_projection",
    )


def build_layered_evidence_contract_report(
    *,
    disposition_ledger: DispositionLedger,
    classified_authorities: Mapping[str, Mapping[str, Any] | EvidenceAuthority],
) -> dict[str, Any]:
    """Bind exactly one classified authority projection to every claim."""

    expected_claim_ids = tuple(
        row.claim_id for row in disposition_ledger.claims
    )
    if len(set(expected_claim_ids)) != len(expected_claim_ids):
        raise ValueError("layered_evidence_duplicate_claim")
    extra_claim_ids = set(classified_authorities) - set(expected_claim_ids)
    if extra_claim_ids:
        raise ValueError("layered_evidence_unexpected_claim")
    bound: list[BoundEvidenceAuthority] = []
    for claim in disposition_ledger.claims:
        projected = classified_authorities.get(claim.claim_id)
        if isinstance(projected, EvidenceAuthority):
            authority = projected
        elif isinstance(projected, Mapping):
            authority = evidence_authority_from_projection(projected)
        elif projected is None:
            authority = _fallback_disposition_authority(
                ledger=disposition_ledger,
                claim=claim,
            )
        else:
            raise ValueError("evidence_authority_projection_invalid")
        bound.append(
            BoundEvidenceAuthority(
                deck_fingerprint=disposition_ledger.deck_fingerprint,
                composite_claim_identity=(
                    f"{disposition_ledger.deck_fingerprint}:{claim.claim_id}"
                ),
                claim_id=claim.claim_id,
                authority=authority,
            )
        )
    identities = tuple(row.composite_claim_identity for row in bound)
    if len(set(identities)) != len(identities):
        raise ValueError("layered_evidence_duplicate_binding")
    exact_guide_authority = any(
        row.authority.lane is EvidenceLane.EXACT_LIVE_GUIDE
        and row.authority.exact_deck_fingerprint
        == disposition_ledger.deck_fingerprint
        for row in bound
    )
    report = {
        **_diagnostic_report_base(disposition_ledger.deck_fingerprint),
        "exact_guide_authority": exact_guide_authority,
        "layered_coverage": MetricRatio(
            len(bound),
            len(expected_claim_ids),
        ).to_document(),
        "authorities": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "composite_claim_identity": (
                    row.composite_claim_identity
                ),
                "claim_id": row.claim_id,
                "lane": row.authority.lane.value,
                "authority_id": row.authority.authority_id,
                "source_identity": row.authority.source_identity,
                "as_of_date": row.authority.as_of_date,
                "claim_kind": row.authority.claim_kind,
                "content_sha256": row.authority.content_sha256,
                "exact_deck_fingerprint": (
                    row.authority.exact_deck_fingerprint
                ),
                "runtime_authorized": (
                    row.authority.runtime_authorized
                ),
                "reason": row.authority.reason,
            }
            for row in bound
        ],
    }
    report["content_sha256"] = _report_content_sha256(report)
    return report


def verified_emission_input_from_ledgers(
    *,
    disposition_ledger: DispositionLedger,
    runtime_surface_ledger: Mapping[str, Any],
) -> VerifiedEmissionInput:
    """Freeze semantic eligibility separately from physical observations."""

    fingerprint = disposition_ledger.deck_fingerprint
    claim_owner_candidates: dict[str, list[CardDispositionRow]] = {}
    for card in disposition_ledger.cards:
        for claim_id in card.claim_ids:
            claim_owner_candidates.setdefault(claim_id, []).append(card)

    expectations: list[VerifiedSemanticExpectation] = []
    for card in disposition_ledger.cards:
        expectations.append(
            VerifiedSemanticExpectation(
                deck_fingerprint=fingerprint,
                composite_identity=(
                    f"{fingerprint}:card:{card.composite_card_key}"
                ),
                row_kind="card",
                disposition=card.disposition.value,
                expected_owner=card.physical_owner,
                allowed_runtime_surfaces=card.runtime_paths,
                claim_id=next(iter(card.claim_ids), ""),
                claim_linked=True,
                surface_allowed=bool(card.runtime_paths),
                schema_supported=True,
                authority_sufficient=(
                    card.disposition
                    is not CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
                ),
            )
        )
    for claim in disposition_ledger.claims:
        candidates = sorted(
            claim_owner_candidates.get(claim.claim_id, ()),
            key=lambda row: (
                row.runtime_paths != claim.runtime_paths,
                row.composite_card_key,
            ),
        )
        owner = candidates[0] if candidates else None
        expectations.append(
            VerifiedSemanticExpectation(
                deck_fingerprint=fingerprint,
                composite_identity=(
                    f"{fingerprint}:claim:{claim.claim_id}"
                ),
                row_kind="claim",
                disposition=claim.disposition.value,
                expected_owner=(
                    owner.physical_owner
                    if owner is not None
                    else "semantic_contract"
                ),
                allowed_runtime_surfaces=claim.runtime_paths,
                claim_id=claim.claim_id,
                claim_linked=owner is not None,
                surface_allowed=bool(claim.runtime_paths),
                schema_supported=True,
                authority_sufficient=(
                    claim.disposition
                    is not ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
                ),
            )
        )

    observed = _physical_cardid_observations(runtime_surface_ledger)
    physical_rows: list[VerifiedPhysicalEmission] = []
    matched_observations: set[tuple[str, str]] = set()
    for expectation in expectations:
        for surface in expectation.allowed_runtime_surfaces:
            observation = (expectation.expected_owner, surface)
            if observation not in observed:
                continue
            matched_observations.add(observation)
            physical_rows.append(
                VerifiedPhysicalEmission(
                    deck_fingerprint=fingerprint,
                    physical_identity=(
                        f"{fingerprint}:physical:"
                        f"{expectation.composite_identity.removeprefix(f'{fingerprint}:')}:"
                        f"{surface}"
                    ),
                    composite_identity=expectation.composite_identity,
                    physical_owner=expectation.expected_owner,
                    runtime_surface=surface,
                    claim_id=expectation.claim_id,
                    claim_linked=expectation.claim_linked,
                    surface_allowed=True,
                    schema_supported=True,
                    authority_authorized=(
                        expectation.authority_sufficient
                    ),
                    meaningful=True,
                )
            )
    for owner, surface in sorted(observed - matched_observations):
        physical_rows.append(
            VerifiedPhysicalEmission(
                deck_fingerprint=fingerprint,
                physical_identity=(
                    f"{fingerprint}:physical:unmatched:{owner}:{surface}"
                ),
                composite_identity=None,
                physical_owner=owner,
                runtime_surface=surface,
                claim_id="",
                claim_linked=False,
                surface_allowed=False,
                schema_supported=True,
                authority_authorized=False,
                meaningful=True,
            )
        )
    rejected_rows = [
        *runtime_surface_ledger.get("physical_errors", ()),
        *runtime_surface_ledger.get("unexpected_runtime_emissions", ()),
        *runtime_surface_ledger.get("linked_runtime_owner_collisions", ()),
    ]
    for index, rejected in enumerate(rejected_rows):
        digest = sha256(
            json.dumps(
                rejected,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        physical_rows.append(
            VerifiedPhysicalEmission(
                deck_fingerprint=fingerprint,
                physical_identity=(
                    f"{fingerprint}:physical:rejected:{index}:{digest}"
                ),
                composite_identity=None,
                physical_owner="rejected_physical_emission",
                runtime_surface=f"rejected/{index}.json",
                claim_id="",
                claim_linked=False,
                surface_allowed=False,
                schema_supported=False,
                authority_authorized=False,
                meaningful=True,
            )
        )
    return VerifiedEmissionInput(
        deck_fingerprint=fingerprint,
        expectations=tuple(expectations),
        physical_rows=tuple(physical_rows),
    )


def _physical_cardid_observations(
    runtime_surface_ledger: Mapping[str, Any],
) -> set[tuple[str, str]]:
    observations: set[tuple[str, str]] = set()
    cards = runtime_surface_ledger.get("cards", {})
    if isinstance(cards, Mapping):
        for card_id, raw_row in cards.items():
            if not isinstance(raw_row, Mapping):
                continue
            expected_path = f"{card_id}.json"
            for path in raw_row.get("runtime_surfaces", ()):
                if path == expected_path:
                    observations.add((str(card_id), expected_path))
    linked = runtime_surface_ledger.get("linked_runtime_entities", {})
    if isinstance(linked, Mapping):
        for runtime_card_id, raw_row in linked.items():
            if not isinstance(raw_row, Mapping):
                continue
            path = str(
                raw_row.get("runtime_surface")
                or f"{runtime_card_id}.json"
            )
            if (
                raw_row.get("runtime_emitted") is True
                and path == f"{runtime_card_id}.json"
            ):
                observations.add((str(runtime_card_id), path))
    return observations


def verified_emission_input_from_physical_rows(
    *,
    disposition_ledger: DispositionLedger,
    physical_rows: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Any] = (),
) -> VerifiedEmissionInput:
    """Join retained physical rows without deduplicating observations."""

    fingerprint = disposition_ledger.deck_fingerprint
    semantic_only = verified_emission_input_from_ledgers(
        disposition_ledger=disposition_ledger,
        runtime_surface_ledger={},
    )
    expectations = semantic_only.expectations
    cards_by_key = {
        row.composite_card_key: row
        for row in disposition_ledger.cards
    }
    raw_identities: list[str] = []
    normalized_rows: list[tuple[str, str, str, bool]] = []
    for raw in physical_rows:
        try:
            composite_key = _require_text(
                raw["composite_card_key"],
                field="composite_card_key",
            )
            owner = _require_text(
                raw["physical_owner"],
                field="physical_owner",
            )
            surface = _require_text(
                raw["relative_path"],
                field="runtime_surface",
            )
            meaningful = raw["meaningful"] is True
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "verified_emission_physical_row_invalid"
            ) from error
        canonical_relative_path(surface)
        physical_identity = (
            f"{fingerprint}:physical:{owner}:{surface}"
        )
        raw_identities.append(physical_identity)
        normalized_rows.append(
            (composite_key, owner, surface, meaningful)
        )
    if len(set(raw_identities)) != len(raw_identities):
        raise ValueError("verified_emission_duplicate_physical_row")

    expectation_by_identity = {
        row.composite_identity: row for row in expectations
    }
    joined: list[VerifiedPhysicalEmission] = []
    for raw_identity, raw in zip(
        raw_identities,
        normalized_rows,
        strict=True,
    ):
        composite_key, owner, surface, meaningful = raw
        card = cards_by_key.get(composite_key)
        card_identity = f"{fingerprint}:card:{composite_key}"
        card_expectation = expectation_by_identity.get(card_identity)
        if card is None or card_expectation is None:
            joined.append(
                VerifiedPhysicalEmission(
                    deck_fingerprint=fingerprint,
                    physical_identity=raw_identity,
                    composite_identity=None,
                    physical_owner=owner,
                    runtime_surface=surface,
                    claim_id="",
                    claim_linked=False,
                    surface_allowed=False,
                    schema_supported=False,
                    authority_authorized=False,
                    meaningful=meaningful,
                )
            )
            continue
        joined.append(
            VerifiedPhysicalEmission(
                deck_fingerprint=fingerprint,
                physical_identity=raw_identity,
                composite_identity=card_identity,
                physical_owner=owner,
                runtime_surface=surface,
                claim_id=card_expectation.claim_id,
                claim_linked=True,
                surface_allowed=(
                    surface
                    in card_expectation.allowed_runtime_surfaces
                ),
                schema_supported=True,
                authority_authorized=(
                    card_expectation.authority_sufficient
                ),
                meaningful=meaningful,
            )
        )
        for claim_id in card.claim_ids:
            claim_identity = f"{fingerprint}:claim:{claim_id}"
            claim_expectation = expectation_by_identity.get(
                claim_identity
            )
            if (
                claim_expectation is None
                or surface
                not in claim_expectation.allowed_runtime_surfaces
                or owner != claim_expectation.expected_owner
            ):
                continue
            joined.append(
                VerifiedPhysicalEmission(
                    deck_fingerprint=fingerprint,
                    physical_identity=(
                        f"{raw_identity}:claim:{claim_id}"
                    ),
                    composite_identity=claim_identity,
                    physical_owner=owner,
                    runtime_surface=surface,
                    claim_id=claim_id,
                    claim_linked=True,
                    surface_allowed=True,
                    schema_supported=True,
                    authority_authorized=(
                        claim_expectation.authority_sufficient
                    ),
                    meaningful=meaningful,
                )
            )
    for index, rejected in enumerate(rejected_rows):
        digest = sha256(
            json.dumps(
                rejected,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        joined.append(
            VerifiedPhysicalEmission(
                deck_fingerprint=fingerprint,
                physical_identity=(
                    f"{fingerprint}:physical:rejected:{index}:{digest}"
                ),
                composite_identity=None,
                physical_owner="rejected_physical_emission",
                runtime_surface=f"rejected/{index}.json",
                claim_id="",
                claim_linked=False,
                surface_allowed=False,
                schema_supported=False,
                authority_authorized=False,
                meaningful=True,
            )
        )
    return VerifiedEmissionInput(
        deck_fingerprint=fingerprint,
        expectations=expectations,
        physical_rows=tuple(joined),
    )


def verified_emission_input_document(
    verified: VerifiedEmissionInput,
) -> dict[str, Any]:
    return {
        "deck_fingerprint": verified.deck_fingerprint,
        "semantic_expectations": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "composite_identity": row.composite_identity,
                "row_kind": row.row_kind,
                "disposition": row.disposition,
                "expected_owner": row.expected_owner,
                "allowed_runtime_surfaces": list(
                    row.allowed_runtime_surfaces
                ),
                "claim_id": row.claim_id,
                "claim_linked": row.claim_linked,
                "surface_allowed": row.surface_allowed,
                "schema_supported": row.schema_supported,
                "authority_sufficient": row.authority_sufficient,
            }
            for row in verified.expectations
        ],
        "physical_rows": [
            {
                "deck_fingerprint": row.deck_fingerprint,
                "physical_identity": row.physical_identity,
                "composite_identity": row.composite_identity,
                "physical_owner": row.physical_owner,
                "runtime_surface": row.runtime_surface,
                "claim_id": row.claim_id,
                "claim_linked": row.claim_linked,
                "surface_allowed": row.surface_allowed,
                "schema_supported": row.schema_supported,
                "authority_authorized": row.authority_authorized,
                "meaningful": row.meaningful,
            }
            for row in verified.physical_rows
        ],
    }


def build_pre_run_closure_report(
    *,
    disposition_ledger: DispositionLedger,
    globalvalues_ledger: GlobalValuesDecisionLedger,
    dual_closure: DualClosureStatus,
    layered_evidence_report: Mapping[str, Any],
    source_acquisition_report: Mapping[str, Any],
    verified_emissions: VerifiedEmissionInput,
) -> dict[str, Any]:
    """Build one package-local closure report from typed and physical facts."""

    fingerprint = disposition_ledger.deck_fingerprint
    fingerprints = {
        fingerprint,
        globalvalues_ledger.deck_fingerprint,
        verified_emissions.deck_fingerprint,
        str(layered_evidence_report.get("deck_fingerprint", "")),
        str(source_acquisition_report.get("deck_fingerprint", "")),
    }
    if fingerprints != {fingerprint}:
        raise ValueError("pre_run_closure_cross_deck")
    precision = emission_precision(verified_emissions)
    recall = eligible_emission_recall(verified_emissions)
    layered_coverage = _metric_ratio_from_document(
        layered_evidence_report.get("layered_coverage")
    )
    acquisition_complete = (
        source_acquisition_report.get("source_acquisition_complete")
        is True
    )
    globalvalues_complete = (
        tuple(row.key for row in globalvalues_ledger.decisions)
        == GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    complete = all(
        (
            dual_closure.pre_run_contract_status == "complete",
            acquisition_complete,
            globalvalues_complete,
            precision.normalized_fraction == 1,
            recall.normalized_fraction == 1,
            layered_coverage.normalized_fraction == 1,
        )
    )
    unresolved = set(dual_closure.unresolved_reasons)
    if not acquisition_complete:
        unresolved.add("source_acquisition_open")
    if not globalvalues_complete:
        unresolved.add("incomplete_globalvalues_decision")
    if precision.normalized_fraction != 1:
        unresolved.add("physical_emission_precision_incomplete")
    if recall.normalized_fraction != 1:
        unresolved.add("eligible_emission_recall_incomplete")
    if layered_coverage.normalized_fraction != 1:
        unresolved.add("layered_evidence_coverage_incomplete")
    report = {
        **_diagnostic_report_base(fingerprint),
        "hsconfig_scope": "PRE_RUN_CONTRACT",
        "gameplay_strategy_owner": "hearthranger_bot",
        "gameplay_quality": "OUT_OF_SCOPE_ASSUMED_EXTERNAL",
        "bot_gameplay_assumption": "trusted_external",
        "pre_run_contract_status": (
            "complete" if complete else "incomplete"
        ),
        "strategy_authority_status": (
            dual_closure.strategy_authority_status
        ),
        "exact_guide_authority": layered_evidence_report.get(
            "exact_guide_authority"
        )
        is True,
        "unresolved_reasons": sorted(unresolved),
        "report_hashes": {
            "layered_evidence_contract": str(
                layered_evidence_report.get("content_sha256", "")
            ),
            "source_acquisition_closure": str(
                source_acquisition_report.get("content_sha256", "")
            ),
            "disposition_ledger": disposition_ledger.content_sha256,
            "globalvalues_decision_ledger": (
                globalvalues_ledger.content_sha256
            ),
        },
        "counts": {
            "card_disposition_count": len(disposition_ledger.cards),
            "final_card_disposition_count": len(
                disposition_ledger.cards
            ),
            "claim_count": len(disposition_ledger.claims),
            "final_claim_disposition_count": len(
                disposition_ledger.claims
            ),
            "globalvalues_decision_count": len(
                globalvalues_ledger.decisions
            ),
            "final_globalvalues_decision_count": len(
                globalvalues_ledger.decisions
            ),
        },
        "layered_pre_run_source_coverage": (
            layered_coverage.to_document()
        ),
        "emission_precision": precision.to_document(),
        "eligible_emission_recall": recall.to_document(),
        "verified_emission": verified_emission_input_document(
            verified_emissions
        ),
    }
    report["content_sha256"] = _report_content_sha256(report)
    return report


def _metric_ratio_from_document(value: Any) -> MetricRatio:
    if not isinstance(value, Mapping):
        raise ValueError("pre_run_metric_document_invalid")
    try:
        ratio = MetricRatio(
            numerator=value["numerator"],
            denominator=value["denominator"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("pre_run_metric_document_invalid") from error
    if ratio.to_document() != dict(value):
        raise ValueError("pre_run_metric_document_invalid")
    return ratio


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _load_disposition_ledger(
    document: Mapping[str, Any],
) -> DispositionLedger:
    try:
        fingerprint = document["deck_fingerprint"]
        cards = tuple(
            CardDispositionRow(
                deck_fingerprint=row["deck_fingerprint"],
                composite_card_key=row["composite_card_key"],
                zone=row["zone"],
                official_semantics_canonical_json=_canonical_bytes(
                    row["official_semantics"]
                ),
                authority_lane=EvidenceLane(row["authority_lane"]),
                evidence_ids=tuple(row["evidence_ids"]),
                claim_ids=tuple(row["claim_ids"]),
                physical_owner=row["physical_owner"],
                disposition=CardDisposition(row["disposition"]),
                runtime_paths=tuple(row["runtime_paths"]),
                reason_code=row["reason_code"],
            )
            for row in document["cards"]
        )
        claims = tuple(
            ClaimDispositionRow(
                deck_fingerprint=row["deck_fingerprint"],
                claim_id=row["claim_id"],
                claim_kind=row["claim_kind"],
                evidence_id=row["evidence_id"],
                disposition=ClaimDisposition(row["disposition"]),
                runtime_paths=tuple(row["runtime_paths"]),
                reason_code=row["reason_code"],
            )
            for row in document["claims"]
        )
        ledger = DispositionLedger(
            deck_fingerprint=fingerprint,
            cards=cards,
            claims=claims,
            content_sha256=document["content_sha256"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("disposition_ledger_report_invalid") from error
    card_ids = tuple(row.composite_card_key for row in cards)
    claim_ids = tuple(row.claim_id for row in claims)
    if (
        len(set(card_ids)) != len(card_ids)
        or len(set(claim_ids)) != len(claim_ids)
        or tuple(sorted(card_ids)) != card_ids
        or tuple(sorted(claim_ids)) != claim_ids
    ):
        raise ValueError("disposition_ledger_duplicate_or_unstable")
    for row in document["claims"]:
        if (
            row.get("composite_claim_identity")
            != f"{fingerprint}:{row.get('claim_id', '')}"
        ):
            raise ValueError("disposition_claim_identity_mismatch")
    if disposition_ledger_document(ledger) != dict(document):
        raise ValueError("disposition_ledger_report_malformed")
    return ledger


def _load_globalvalues_ledger(
    document: Mapping[str, Any],
) -> GlobalValuesDecisionLedger:
    try:
        fingerprint = document["deck_fingerprint"]
        decisions = tuple(
            GlobalValueDecision(
                deck_fingerprint=fingerprint,
                key=row["key"],
                kind=GlobalValueDecisionKind(row["kind"]),
                baseline_canonical_json=_canonical_bytes(
                    row["baseline"]
                ),
                emitted_canonical_json=_canonical_bytes(row["emitted"]),
                authority_id=row["authority_id"],
                claim_ids=tuple(row["claim_ids"]),
                reason=row["reason"],
            )
            for row in document["decisions"]
        )
        ledger = GlobalValuesDecisionLedger(
            deck_fingerprint=fingerprint,
            baseline_sha256=document["baseline_sha256"],
            decisions=decisions,
            content_sha256=document["content_sha256"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "globalvalues_decision_ledger_report_invalid"
        ) from error
    if tuple(row.key for row in decisions) != (
        GLOBALVALUES_BASELINE_DECISION_KEYS
    ):
        raise ValueError("globalvalues_decision_ledger_incomplete")
    if globalvalues_decision_report_document(ledger) != dict(document):
        raise ValueError(
            "globalvalues_decision_ledger_report_malformed"
        )
    return ledger


def _load_verified_emission_input(
    document: Any,
) -> VerifiedEmissionInput:
    if not isinstance(document, Mapping):
        raise ValueError("verified_emission_document_invalid")
    try:
        verified = VerifiedEmissionInput(
            deck_fingerprint=document["deck_fingerprint"],
            expectations=tuple(
                VerifiedSemanticExpectation(
                    deck_fingerprint=row["deck_fingerprint"],
                    composite_identity=row["composite_identity"],
                    row_kind=row["row_kind"],
                    disposition=row["disposition"],
                    expected_owner=row["expected_owner"],
                    allowed_runtime_surfaces=tuple(
                        row["allowed_runtime_surfaces"]
                    ),
                    claim_id=row["claim_id"],
                    claim_linked=row["claim_linked"],
                    surface_allowed=row["surface_allowed"],
                    schema_supported=row["schema_supported"],
                    authority_sufficient=row["authority_sufficient"],
                )
                for row in document["semantic_expectations"]
            ),
            physical_rows=tuple(
                VerifiedPhysicalEmission(
                    deck_fingerprint=row["deck_fingerprint"],
                    physical_identity=row["physical_identity"],
                    composite_identity=row["composite_identity"],
                    physical_owner=row["physical_owner"],
                    runtime_surface=row["runtime_surface"],
                    claim_id=row["claim_id"],
                    claim_linked=row["claim_linked"],
                    surface_allowed=row["surface_allowed"],
                    schema_supported=row["schema_supported"],
                    authority_authorized=row[
                        "authority_authorized"
                    ],
                    meaningful=row["meaningful"],
                )
                for row in document["physical_rows"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("verified_emission_document_invalid") from error
    if verified_emission_input_document(verified) != dict(document):
        raise ValueError("verified_emission_document_malformed")
    return verified


def _validate_layered_evidence_report(
    document: Mapping[str, Any],
    *,
    disposition_ledger: DispositionLedger,
) -> None:
    if document.get("content_sha256") != _report_content_sha256(
        document
    ):
        raise ValueError("layered_evidence_contract_hash_stale")
    fingerprint = disposition_ledger.deck_fingerprint
    if document.get("deck_fingerprint") != fingerprint:
        raise ValueError("layered_evidence_contract_cross_deck")
    rows = document.get("authorities")
    if not isinstance(rows, list):
        raise ValueError("layered_evidence_contract_malformed")
    expected = {
        f"{fingerprint}:{row.claim_id}"
        for row in disposition_ledger.claims
    }
    observed: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("layered_evidence_contract_malformed")
        authority = evidence_authority_from_projection(row)
        bound = BoundEvidenceAuthority(
            deck_fingerprint=row["deck_fingerprint"],
            composite_claim_identity=row[
                "composite_claim_identity"
            ],
            claim_id=row["claim_id"],
            authority=authority,
        )
        observed.append(bound.composite_claim_identity)
    if len(set(observed)) != len(observed):
        raise ValueError("layered_evidence_contract_duplicate")
    if set(observed) != expected:
        raise ValueError("layered_evidence_contract_claim_mismatch")
    ratio = _metric_ratio_from_document(
        document.get("layered_coverage")
    )
    if (
        ratio.numerator != len(observed)
        or ratio.denominator != len(expected)
    ):
        raise ValueError("layered_evidence_contract_totals_mismatch")
    exact = any(
        row.get("lane") == EvidenceLane.EXACT_LIVE_GUIDE.value
        and row.get("exact_deck_fingerprint") == fingerprint
        for row in rows
    )
    if document.get("exact_guide_authority") is not exact:
        raise ValueError(
            "layered_evidence_exact_guide_authority_mismatch"
        )


def _validate_acquisition_report(
    document: Mapping[str, Any],
    *,
    deck_fingerprint: str,
) -> None:
    if document.get("content_sha256") != _report_content_sha256(
        document
    ):
        raise ValueError("source_acquisition_closure_hash_stale")
    if document.get("deck_fingerprint") != deck_fingerprint:
        raise ValueError("source_acquisition_closure_cross_deck")
    closure = document.get("acquisition_closure")
    if not isinstance(closure, Mapping):
        raise ValueError("source_acquisition_closure_malformed")
    expected_fields = {
        "deck_fingerprint",
        "attempt_id",
        "attempted_at",
        "attempted_urls",
        "successful_evidence_ids",
        "failed_attempts",
        "negative_search_documented",
        "checked_dossier",
        "policy_id",
        "status",
        "content_sha256",
    }
    if set(closure) != expected_fields:
        raise ValueError("source_acquisition_closure_malformed")
    if closure.get("deck_fingerprint") != deck_fingerprint:
        raise ValueError("source_acquisition_closure_cross_deck")
    attempt_id = closure.get("attempt_id")
    attempted_at = closure.get("attempted_at")
    attempted_urls = closure.get("attempted_urls")
    successful = closure.get("successful_evidence_ids")
    failed = closure.get("failed_attempts")
    policy_id = closure.get("policy_id")
    if (
        not isinstance(attempt_id, str)
        or not isinstance(attempted_at, str)
        or not isinstance(attempted_urls, list)
        or any(
            not isinstance(value, str) or not value
            for value in attempted_urls
        )
        or attempted_urls != sorted(set(attempted_urls))
        or not isinstance(successful, list)
        or any(
            not isinstance(value, str) or not value
            for value in successful
        )
        or successful != sorted(set(successful))
        or not isinstance(failed, list)
        or type(closure.get("negative_search_documented")) is not bool
        or type(closure.get("checked_dossier")) is not bool
        or (
            policy_id is not None
            and (not isinstance(policy_id, str) or not policy_id)
        )
    ):
        raise ValueError("source_acquisition_closure_malformed")
    for failure in failed:
        if (
            not isinstance(failure, Mapping)
            or set(failure)
            != {"source_identity", "reason_code", "attempted_at"}
            or any(
                not isinstance(failure.get(field), str)
                or not failure[field]
                for field in (
                    "source_identity",
                    "reason_code",
                    "attempted_at",
                )
            )
        ):
            raise ValueError("source_acquisition_closure_malformed")
    status = closure.get("status")
    if status not in {
        "closed_with_evidence",
        "closed_negative_search",
        "open",
    }:
        raise ValueError("source_acquisition_closure_status_invalid")
    complete = status != "open"
    if document.get("source_acquisition_complete") is not complete:
        raise ValueError(
            "source_acquisition_closure_status_mismatch"
        )
    if not _is_sha256(closure.get("content_sha256")):
        raise ValueError("source_acquisition_closure_hash_invalid")
    if status == "closed_with_evidence" and (
        not successful
        or closure["negative_search_documented"] is True
    ):
        raise ValueError("source_acquisition_closure_status_mismatch")
    if status == "closed_negative_search" and (
        successful
        or closure["negative_search_documented"] is not True
    ):
        raise ValueError("source_acquisition_closure_status_mismatch")
    if status == "open" and (
        successful
        or closure["negative_search_documented"] is True
    ):
        raise ValueError("source_acquisition_closure_status_mismatch")
    if status != "open" and (
        not attempt_id
        or not attempted_at
        or not attempted_urls
        or closure["checked_dossier"] is not True
        or not policy_id
    ):
        raise ValueError("source_acquisition_closure_status_mismatch")


def _semantic_disposition_complete(
    disposition_ledger: DispositionLedger,
) -> bool:
    unresolved_reasons = {
        "conflicting_card_disposition",
        "conflicting_claim_disposition",
        "missing_claim_lifecycle",
        "unclassified_card_disposition",
    }
    return not any(
        row.reason_code in unresolved_reasons
        for row in (
            *disposition_ledger.cards,
            *disposition_ledger.claims,
        )
    )


@dataclass(frozen=True, slots=True)
class ValidatedPreRunPackage:
    deck_fingerprint: str
    deck_identity: Mapping[str, Any]
    disposition_ledger: DispositionLedger
    globalvalues_ledger: GlobalValuesDecisionLedger
    pre_run_report: Mapping[str, Any]
    exact_guide_authority: bool
    layered_coverage: MetricRatio
    emission_precision: MetricRatio
    eligible_emission_recall: MetricRatio


def validate_pre_run_package_reports(
    package: PackageView,
) -> ValidatedPreRunPackage:
    """Load and cross-check the five reports through PackageView only."""

    missing = [
        path for path in PRE_RUN_REPORT_PATHS if not package.exists(path)
    ]
    if missing:
        raise ValueError(
            f"pre_run_report_missing:{','.join(missing)}"
        )
    try:
        documents = {
            path: package.read_json(path) for path in PRE_RUN_REPORT_PATHS
        }
        deck_identity = package.read_json("reports/deck_identity.json")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("pre_run_report_malformed") from error
    if (
        not isinstance(deck_identity, Mapping)
        or any(
            not isinstance(document, Mapping)
            for document in documents.values()
        )
    ):
        raise ValueError("pre_run_report_malformed")
    disposition = _load_disposition_ledger(
        documents["reports/disposition_ledger.json"]
    )
    globalvalues = _load_globalvalues_ledger(
        documents["reports/globalvalues_decision_ledger.json"]
    )
    fingerprint = disposition.deck_fingerprint
    if globalvalues.deck_fingerprint != fingerprint:
        raise ValueError("pre_run_report_cross_deck")
    _validate_layered_evidence_report(
        documents["reports/layered_evidence_contract.json"],
        disposition_ledger=disposition,
    )
    _validate_acquisition_report(
        documents["reports/source_acquisition_closure.json"],
        deck_fingerprint=fingerprint,
    )
    pre_run = documents["reports/pre_run_closure.json"]
    if pre_run.get("content_sha256") != _report_content_sha256(
        pre_run
    ):
        raise ValueError("pre_run_closure_hash_stale")
    if pre_run.get("deck_fingerprint") != fingerprint:
        raise ValueError("pre_run_closure_cross_deck")
    if deck_identity.get("deck_fingerprint") != fingerprint:
        raise ValueError("pre_run_deck_identity_cross_deck")
    _validate_deck_identity(deck_identity, fingerprint=fingerprint)
    expected_hashes = {
        "layered_evidence_contract": documents[
            "reports/layered_evidence_contract.json"
        ]["content_sha256"],
        "source_acquisition_closure": documents[
            "reports/source_acquisition_closure.json"
        ]["content_sha256"],
        "disposition_ledger": disposition.content_sha256,
        "globalvalues_decision_ledger": globalvalues.content_sha256,
    }
    if pre_run.get("report_hashes") != expected_hashes:
        raise ValueError("pre_run_closure_report_hash_mismatch")
    counts = pre_run.get("counts")
    expected_counts = {
        "card_disposition_count": len(disposition.cards),
        "final_card_disposition_count": len(disposition.cards),
        "claim_count": len(disposition.claims),
        "final_claim_disposition_count": len(disposition.claims),
        "globalvalues_decision_count": len(globalvalues.decisions),
        "final_globalvalues_decision_count": len(
            globalvalues.decisions
        ),
    }
    if counts != expected_counts:
        raise ValueError("pre_run_closure_totals_mismatch")
    verified = _load_verified_emission_input(
        pre_run.get("verified_emission")
    )
    if verified.deck_fingerprint != fingerprint:
        raise ValueError("verified_emission_cross_deck")
    expected_semantics = verified_emission_input_from_ledgers(
        disposition_ledger=disposition,
        runtime_surface_ledger={},
    ).expectations
    if verified.expectations != expected_semantics:
        raise ValueError(
            "verified_emission_semantic_projection_mismatch"
        )
    precision = emission_precision(verified)
    recall = eligible_emission_recall(verified)
    if pre_run.get("emission_precision") != precision.to_document():
        raise ValueError("pre_run_emission_precision_mismatch")
    if (
        pre_run.get("eligible_emission_recall")
        != recall.to_document()
    ):
        raise ValueError("pre_run_emission_recall_mismatch")
    layered = _metric_ratio_from_document(
        pre_run.get("layered_pre_run_source_coverage")
    )
    report_layered = _metric_ratio_from_document(
        documents["reports/layered_evidence_contract.json"].get(
            "layered_coverage"
        )
    )
    if layered != report_layered:
        raise ValueError("pre_run_layered_coverage_mismatch")
    acquisition_complete = documents[
        "reports/source_acquisition_closure.json"
    ].get("source_acquisition_complete") is True
    expected_complete = all(
        (
            acquisition_complete,
            _semantic_disposition_complete(disposition),
            len(globalvalues.decisions)
            == len(GLOBALVALUES_BASELINE_DECISION_KEYS),
            precision.normalized_fraction == 1,
            recall.normalized_fraction == 1,
            layered.normalized_fraction == 1,
        )
    )
    expected_status = "complete" if expected_complete else "incomplete"
    if pre_run.get("pre_run_contract_status") != expected_status:
        raise ValueError("pre_run_closure_status_mismatch")
    strategy = pre_run.get("strategy_authority_status")
    if strategy not in {"partial", "strong"}:
        raise ValueError("pre_run_strategy_authority_status_invalid")
    exact = documents[
        "reports/layered_evidence_contract.json"
    ].get("exact_guide_authority") is True
    if pre_run.get("exact_guide_authority") is not exact:
        raise ValueError("pre_run_exact_guide_authority_mismatch")
    for field, expected in (
        ("hsconfig_scope", "PRE_RUN_CONTRACT"),
        ("gameplay_strategy_owner", "hearthranger_bot"),
        ("gameplay_quality", "OUT_OF_SCOPE_ASSUMED_EXTERNAL"),
        ("bot_gameplay_assumption", "trusted_external"),
    ):
        if pre_run.get(field) != expected:
            raise ValueError(f"pre_run_closure_{field}_invalid")
    return ValidatedPreRunPackage(
        deck_fingerprint=fingerprint,
        deck_identity=deck_identity,
        disposition_ledger=disposition,
        globalvalues_ledger=globalvalues,
        pre_run_report=pre_run,
        exact_guide_authority=exact,
        layered_coverage=layered,
        emission_precision=precision,
        eligible_emission_recall=recall,
    )


def _validate_deck_identity(
    deck_identity: Mapping[str, Any],
    *,
    fingerprint: str,
) -> None:
    cards = deck_identity.get("main_deck", deck_identity.get("cards"))
    if not isinstance(cards, list):
        raise ValueError("pre_run_deck_identity_malformed")
    roster: list[tuple[str, int]] = []
    for card in cards:
        if (
            not isinstance(card, Mapping)
            or not isinstance(card.get("card_id"), str)
            or not card["card_id"]
            or type(card.get("count")) is not int
            or card["count"] <= 0
        ):
            raise ValueError("pre_run_deck_identity_malformed")
        roster.append((card["card_id"], card["count"]))
    if stable_deck_fingerprint(roster) != fingerprint:
        raise ValueError("pre_run_deck_identity_hash_mismatch")


def aggregate_pre_run_closure(
    packages: Sequence[PackageView],
) -> dict[str, Any]:
    """Aggregate exactly twelve validated package-local closure reports."""

    if len(packages) != 12:
        raise ValueError("pre_run_audited_deck_total_must_equal_12")
    validated = tuple(
        validate_pre_run_package_reports(package) for package in packages
    )
    fingerprints = tuple(row.deck_fingerprint for row in validated)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("pre_run_duplicate_package")
    incomplete = [
        row.deck_fingerprint
        for row in validated
        if row.pre_run_report.get("pre_run_contract_status")
        != "complete"
    ]
    if incomplete:
        raise ValueError("pre_run_contract_incomplete")
    main_slot_count = 0
    main_card_identities: set[str] = set()
    sideboard_module_count = 0
    composite_claims: set[str] = set()
    raw_claim_ids: set[str] = set()
    exact_decks: list[str] = []
    layered_numerator = 0
    layered_denominator = 0
    precision_numerator = 0
    precision_denominator = 0
    recall_numerator = 0
    recall_denominator = 0
    card_count = 0
    claim_count = 0
    globalvalues_count = 0
    for package in validated:
        cards = package.deck_identity.get(
            "main_deck",
            package.deck_identity.get("cards"),
        )
        if not isinstance(cards, list):
            raise ValueError("pre_run_deck_identity_malformed")
        main_slot_count += sum(card["count"] for card in cards)
        main_card_identities.update(
            f"{package.deck_fingerprint}:{card['card_id']}"
            for card in cards
        )
        sideboards = package.deck_identity.get("sideboards", [])
        if not isinstance(sideboards, list):
            raise ValueError("pre_run_deck_identity_malformed")
        sideboard_module_count += sum(
            len(sideboard.get("cards", []))
            for sideboard in sideboards
            if isinstance(sideboard, Mapping)
        )
        for claim in package.disposition_ledger.claims:
            composite_claims.add(
                f"{package.deck_fingerprint}:{claim.claim_id}"
            )
            raw_claim_ids.add(claim.claim_id)
        card_count += len(package.disposition_ledger.cards)
        claim_count += len(package.disposition_ledger.claims)
        globalvalues_count += len(package.globalvalues_ledger.decisions)
        if package.exact_guide_authority:
            exact_decks.append(package.deck_fingerprint)
        layered_numerator += package.layered_coverage.numerator
        layered_denominator += package.layered_coverage.denominator
        precision_numerator += package.emission_precision.numerator
        precision_denominator += package.emission_precision.denominator
        recall_numerator += package.eligible_emission_recall.numerator
        recall_denominator += package.eligible_emission_recall.denominator
    if len(composite_claims) != claim_count:
        raise ValueError("pre_run_composite_claim_collision")
    precision = MetricRatio(
        precision_numerator,
        precision_denominator,
    )
    recall = MetricRatio(recall_numerator, recall_denominator)
    layered = MetricRatio(layered_numerator, layered_denominator)
    audited_totals = {
        "main_slot_count": main_slot_count,
        "main_card_identity_count": len(main_card_identities),
        "sideboard_module_count": sideboard_module_count,
        "card_disposition_count": card_count,
        "claim_count": claim_count,
        "globalvalues_decision_count": globalvalues_count,
    }
    if audited_totals != _AUDITED_PRE_RUN_TOTALS:
        raise ValueError("pre_run_audited_totals_mismatch")
    return {
        "deck_count": len(validated),
        "audited_deck_total": len(validated),
        **audited_totals,
        "final_card_disposition_count": audited_totals[
            "card_disposition_count"
        ],
        "final_claim_disposition_count": audited_totals[
            "claim_count"
        ],
        "raw_claim_id_count": len(raw_claim_ids),
        "raw_claim_id_collision_count": (
            claim_count - len(raw_claim_ids)
        ),
        "final_globalvalues_decision_count": audited_totals[
            "globalvalues_decision_count"
        ],
        "exact_guide_authority_count": len(exact_decks),
        "exact_guide_authority_decks": sorted(exact_decks),
        "layered_pre_run_source_coverage": layered.to_document(),
        "emission_precision": float(precision.normalized_fraction),
        "emission_precision_ratio": precision.to_document(),
        "eligible_emission_recall": float(
            recall.normalized_fraction
        ),
        "eligible_emission_recall_ratio": recall.to_document(),
    }
