"""Typed pre-run emission metrics derived from verified physical rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Literal

from hsconfig.configuration_mode import (
    CONSERVATIVE,
    LLM_OPTIMIZED_START,
    configuration_mode_from_manifest,
)
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.evidence_contract import PolicyProfile, load_policy_profile
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
from hsconfig.semantic_inventory import validate_semantic_inventory
from hsconfig.source_acquisition_closure import (
    AcquisitionClosure,
    AcquisitionFailure,
    acquisition_closure_content_sha256,
    acquisition_closure_payload,
    policy_provenance_payload,
)
from hsconfig.validate_package import validate_card_runtime_payload


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
PRE_RUN_CONTRACT_SCHEMA_VERSION = 1


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
    expected_policy_profile: PolicyProfile | None = None,
) -> dict[str, Any]:
    """Project the exact typed acquisition handoff or an explicit open state."""

    _require_text(deck_fingerprint, field="deck_fingerprint")
    policy_profile = (
        expected_policy_profile
        if expected_policy_profile is not None
        else load_policy_profile()
    )
    if acquisition_closure is None:
        acquisition_closure = AcquisitionClosure(
            deck_fingerprint=deck_fingerprint,
            attempt_id="",
            attempted_at="",
            attempted_urls=(),
            successful_evidence_ids=(),
            failed_attempts=(),
            negative_search_documented=False,
            checked_dossier=False,
            policy_id=None,
            status="open",
            content_sha256="sha256:" + ("0" * 64),
        )
        acquisition_closure = replace(
            acquisition_closure,
            content_sha256=acquisition_closure_content_sha256(
                acquisition_closure,
                policy_profile=policy_profile,
            ),
        )
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
        "policy_provenance": policy_provenance_payload(policy_profile),
        "acquisition_closure": closure_document,
    }
    report["content_sha256"] = _report_content_sha256(report)
    return report


def source_acquisition_input_binding(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind the acquisition attempt and policy into the upstream manifest."""

    closure = report.get("acquisition_closure")
    policy = report.get("policy_provenance")
    if not isinstance(closure, Mapping) or not isinstance(
        policy,
        Mapping,
    ):
        raise ValueError("source_acquisition_input_binding_invalid")
    return {
        "policy_provenance": dict(policy),
        "acquisition_closure": dict(closure),
    }


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

    def __post_init__(
        self,
        _card_dispositions: frozenset[str] = _CARD_DISPOSITIONS,
        _claim_dispositions: frozenset[str] = _CLAIM_DISPOSITIONS,
    ) -> None:
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
            _card_dispositions
            if self.row_kind == "card"
            else _claim_dispositions
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
    semantic_bindings: tuple[str, ...] = ()

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
        bindings = tuple(self.semantic_bindings)
        if not bindings and self.composite_identity is not None:
            bindings = (self.composite_identity,)
        if tuple(sorted(set(bindings))) != bindings:
            raise ValueError(
                "verified_emission_semantic_bindings_invalid"
            )
        if any(
            not binding.startswith(f"{self.deck_fingerprint}:")
            for binding in bindings
        ):
            raise ValueError(
                "verified_emission_semantic_bindings_invalid"
            )
        object.__setattr__(self, "semantic_bindings", bindings)
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
        and expectation.composite_identity
        in physical.semantic_bindings
        and physical.meaningful
        and is_emission_eligible(expectation)
        and physical.physical_owner
        in {
            expectation.expected_owner,
            physical.runtime_surface.removesuffix(".json"),
        }
        and physical.runtime_surface
        in expectation.allowed_runtime_surfaces
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
        any(
            _authorized_physical_emission(
                row,
                expectations.get(binding),
            )
            for binding in row.semantic_bindings
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
    eligible_by_identity = {
        row.composite_identity: row for row in eligible
    }
    emitted_identities = {
        binding
        for row in verified.physical_rows
        for binding in row.semantic_bindings
        if _authorized_physical_emission(
            row,
            eligible_by_identity.get(binding),
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


_BOUND_EVIDENCE_AUTHORITY_FIELDS = frozenset(
    {
        "deck_fingerprint",
        "composite_claim_identity",
        "claim_id",
        "lane",
        "authority_id",
        "source_identity",
        "as_of_date",
        "claim_kind",
        "content_sha256",
        "exact_deck_fingerprint",
        "runtime_authorized",
        "reason",
    }
)


def _bound_evidence_authority_document(
    row: BoundEvidenceAuthority,
) -> dict[str, Any]:
    return {
        "deck_fingerprint": row.deck_fingerprint,
        "composite_claim_identity": row.composite_claim_identity,
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
        "runtime_authorized": row.authority.runtime_authorized,
        "reason": row.authority.reason,
    }


def _bind_evidence_authorities(
    *,
    disposition_ledger: DispositionLedger,
    classified_authorities: Mapping[
        str,
        Mapping[str, Any] | EvidenceAuthority,
    ],
) -> tuple[BoundEvidenceAuthority, ...]:
    expected_claim_ids = tuple(
        row.claim_id for row in disposition_ledger.claims
    )
    if len(set(expected_claim_ids)) != len(expected_claim_ids):
        raise ValueError("layered_evidence_duplicate_claim")
    extra_claim_ids = set(classified_authorities) - set(
        expected_claim_ids
    )
    if extra_claim_ids:
        raise ValueError("layered_evidence_unexpected_claim")
    bound: list[BoundEvidenceAuthority] = []
    claims_by_id = {
        row.claim_id: row for row in disposition_ledger.claims
    }
    for claim_id in expected_claim_ids:
        projected = classified_authorities.get(claim_id)
        if isinstance(projected, EvidenceAuthority):
            authority = projected
        elif isinstance(projected, Mapping):
            authority = evidence_authority_from_projection(projected)
        elif projected is None:
            continue
        else:
            raise ValueError("evidence_authority_projection_invalid")
        if authority.claim_kind != claims_by_id[claim_id].claim_kind:
            raise ValueError(
                "layered_evidence_contract_claim_semantics_mismatch"
            )
        bound.append(
            BoundEvidenceAuthority(
                deck_fingerprint=disposition_ledger.deck_fingerprint,
                composite_claim_identity=(
                    f"{disposition_ledger.deck_fingerprint}:{claim_id}"
                ),
                claim_id=claim_id,
                authority=authority,
            )
        )
    identities = tuple(row.composite_claim_identity for row in bound)
    if len(set(identities)) != len(identities):
        raise ValueError("layered_evidence_duplicate_binding")
    return tuple(bound)


def build_pre_run_authority_handoff(
    *,
    disposition_ledger: DispositionLedger,
    classified_authorities: Mapping[
        str,
        Mapping[str, Any] | EvidenceAuthority,
    ],
) -> dict[str, Any]:
    """Freeze typed authority projections into the audited input manifest."""

    bound = _bind_evidence_authorities(
        disposition_ledger=disposition_ledger,
        classified_authorities=classified_authorities,
    )
    handoff = {
        "schema_version": 1,
        "deck_fingerprint": disposition_ledger.deck_fingerprint,
        "authorities": [
            _bound_evidence_authority_document(row) for row in bound
        ],
    }
    handoff["content_sha256"] = _report_content_sha256(handoff)
    return handoff


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


def build_layered_evidence_contract_report(
    *,
    disposition_ledger: DispositionLedger,
    classified_authorities: Mapping[str, Mapping[str, Any] | EvidenceAuthority],
) -> dict[str, Any]:
    """Bind exactly one classified authority projection to every claim."""

    expected_claim_ids = tuple(
        row.claim_id for row in disposition_ledger.claims
    )
    bound = _bind_evidence_authorities(
        disposition_ledger=disposition_ledger,
        classified_authorities=classified_authorities,
    )
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
            _bound_evidence_authority_document(row)
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


def optimized_verified_emission_input_from_ledgers(
    *,
    disposition_ledger: DispositionLedger,
    runtime_surface_ledger: Mapping[str, Any],
) -> VerifiedEmissionInput:
    """Bind optimized semantics to each distinct physical observation once."""

    expectations = verified_emission_input_from_ledgers(
        disposition_ledger=disposition_ledger,
        runtime_surface_ledger={},
    ).expectations
    physical_rows = tuple(
        {
            "physical_owner": owner,
            "relative_path": surface,
            "meaningful": True,
            "schema_supported": True,
        }
        for owner, surface in sorted(
            _physical_cardid_observations(runtime_surface_ledger)
        )
    )
    rejected_rows = [
        *runtime_surface_ledger.get("physical_errors", ()),
        *runtime_surface_ledger.get("unexpected_runtime_emissions", ()),
        *runtime_surface_ledger.get("linked_runtime_owner_collisions", ()),
    ]
    return verified_emission_input_from_physical_rows(
        disposition_ledger=disposition_ledger,
        physical_rows=physical_rows,
        rejected_rows=rejected_rows,
        semantic_expectations=expectations,
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


def pre_emission_expectations_from_audit(
    *,
    disposition_ledger: DispositionLedger,
    source_contract_audit: Mapping[str, Any],
) -> tuple[VerifiedSemanticExpectation, ...]:
    """Freeze intended eligibility before final physical disposition."""

    fingerprint = disposition_ledger.deck_fingerprint
    claim_rows = source_contract_audit.get("claim_rows", {})
    lifecycle_rows = source_contract_audit.get(
        "claim_lifecycle_rows",
        (),
    )
    if not isinstance(claim_rows, Mapping) or not isinstance(
        lifecycle_rows,
        Sequence,
    ):
        raise ValueError("verified_emission_source_audit_invalid")
    lifecycle_by_id = {
        str(row.get("claim_id", "")): row
        for row in lifecycle_rows
        if isinstance(row, Mapping) and row.get("claim_id")
    }
    owner_by_claim: dict[str, CardDispositionRow] = {}
    for card in disposition_ledger.cards:
        for claim_id in card.claim_ids:
            owner_by_claim.setdefault(claim_id, card)

    expectations: list[VerifiedSemanticExpectation] = []
    claimed_cards = {
        card.composite_card_key
        for card in disposition_ledger.cards
        if card.claim_ids
    }
    final_semantics = verified_emission_input_from_ledgers(
        disposition_ledger=disposition_ledger,
        runtime_surface_ledger={},
    ).expectations
    expectations.extend(
        row
        for row in final_semantics
        if row.row_kind == "card"
        and row.composite_identity.removeprefix(
            f"{fingerprint}:card:"
        )
        not in claimed_cards
    )
    for claim in disposition_ledger.claims:
        raw_claim = claim_rows.get(claim.claim_id)
        raw_claim = (
            raw_claim if isinstance(raw_claim, Mapping) else {}
        )
        lifecycle = lifecycle_by_id.get(claim.claim_id, {})
        intended_paths = tuple(
            sorted(
                {
                    str(path)
                    for path in lifecycle.get("emitted_files", ())
                    if isinstance(path, str) and path
                }
            )
        )
        intended_emission = (
            lifecycle.get("builder_or_router_decision") == "emitted"
            and bool(intended_paths)
        )
        owner_card = owner_by_claim.get(claim.claim_id)
        expected_owner = (
            intended_paths[0].removesuffix(".json")
            if intended_emission
            else (
                owner_card.physical_owner
                if owner_card is not None
                else "semantic_contract"
            )
        )
        authority = raw_claim.get("evidence_authority")
        authority_sufficient = (
            isinstance(authority, Mapping)
            and authority.get("runtime_authorized") is True
        )
        expectations.append(
            VerifiedSemanticExpectation(
                deck_fingerprint=fingerprint,
                composite_identity=(
                    f"{fingerprint}:claim:{claim.claim_id}"
                ),
                row_kind="claim",
                disposition=(
                    ClaimDisposition.RUNTIME_EMITTED.value
                    if intended_emission
                    else claim.disposition.value
                ),
                expected_owner=expected_owner,
                allowed_runtime_surfaces=(
                    intended_paths
                    if intended_emission
                    else claim.runtime_paths
                ),
                claim_id=claim.claim_id,
                claim_linked=owner_card is not None,
                surface_allowed=(
                    bool(intended_paths)
                    if intended_emission
                    else bool(claim.runtime_paths)
                ),
                schema_supported=all(
                    path.endswith(".json")
                    for path in intended_paths
                )
                if intended_emission
                else True,
                authority_sufficient=authority_sufficient,
            )
        )
    return tuple(
        sorted(
            expectations,
            key=lambda row: row.composite_identity,
        )
    )


def verified_emission_input_from_physical_rows(
    *,
    disposition_ledger: DispositionLedger,
    physical_rows: Sequence[Mapping[str, Any]],
    rejected_rows: Sequence[Any] = (),
    semantic_expectations: Sequence[
        VerifiedSemanticExpectation
    ] | None = None,
) -> VerifiedEmissionInput:
    """Join unique physical observations to separate semantic bindings."""

    fingerprint = disposition_ledger.deck_fingerprint
    expectations = tuple(
        semantic_expectations
        if semantic_expectations is not None
        else verified_emission_input_from_ledgers(
            disposition_ledger=disposition_ledger,
            runtime_surface_ledger={},
        ).expectations
    )
    if any(
        row.deck_fingerprint != fingerprint
        for row in expectations
    ):
        raise ValueError("verified_emission_cross_deck_row")
    raw_identities: list[str] = []
    normalized_rows: list[tuple[str, str, bool, bool]] = []
    for raw in physical_rows:
        try:
            owner = _require_text(
                raw["physical_owner"],
                field="physical_owner",
            )
            surface = _require_text(
                raw["relative_path"],
                field="runtime_surface",
            )
            meaningful = raw["meaningful"]
            schema_supported = raw.get(
                "schema_supported",
                False,
            )
            if type(meaningful) is not bool:
                raise ValueError("meaningful_invalid")
            if type(schema_supported) is not bool:
                raise ValueError("schema_supported_invalid")
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
            (owner, surface, meaningful, schema_supported)
        )
    if len(set(raw_identities)) != len(raw_identities):
        raise ValueError("verified_emission_duplicate_physical_row")

    joined: list[VerifiedPhysicalEmission] = []
    for raw_identity, raw in zip(
        raw_identities,
        normalized_rows,
        strict=True,
    ):
        owner, surface, meaningful, schema_supported = raw
        bound_expectations = tuple(
            row
            for row in expectations
            if surface in row.allowed_runtime_surfaces
            and owner
            in {
                row.expected_owner,
                surface.removesuffix(".json"),
            }
        )
        bindings = tuple(
            sorted(
                row.composite_identity
                for row in bound_expectations
            )
        )
        claim_ids = tuple(
            sorted(
                {
                    row.claim_id
                    for row in bound_expectations
                    if row.claim_id
                }
            )
        )
        joined.append(
            VerifiedPhysicalEmission(
                deck_fingerprint=fingerprint,
                physical_identity=raw_identity,
                composite_identity=(
                    bindings[0] if bindings else None
                ),
                physical_owner=owner,
                runtime_surface=surface,
                claim_id=(
                    claim_ids[0] if len(claim_ids) == 1 else ""
                ),
                claim_linked=bool(bindings),
                surface_allowed=bool(bindings),
                schema_supported=schema_supported,
                authority_authorized=(
                    bool(bound_expectations)
                    and all(
                        row.authority_sufficient
                        for row in bound_expectations
                    )
                ),
                meaningful=meaningful,
                semantic_bindings=bindings,
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
                semantic_bindings=(),
            )
        )
    return VerifiedEmissionInput(
        deck_fingerprint=fingerprint,
        expectations=expectations,
        physical_rows=tuple(
            sorted(
                joined,
                key=lambda row: row.physical_identity,
            )
        ),
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
                "semantic_bindings": list(row.semantic_bindings),
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
    configuration_mode: str = CONSERVATIVE,
    runtime_surface_ledger: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one package-local closure report from typed and physical facts."""

    configuration_mode = configuration_mode_from_manifest(
        {"configuration_mode": configuration_mode}
    )
    if configuration_mode == LLM_OPTIMIZED_START:
        if runtime_surface_ledger is None:
            raise ValueError("optimized_verified_emission_authority_missing")
        expected_verified = optimized_verified_emission_input_from_ledgers(
            disposition_ledger=disposition_ledger,
            runtime_surface_ledger=runtime_surface_ledger,
        )
        if verified_emissions != expected_verified:
            raise ValueError("optimized_verified_emission_authority_mismatch")
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


def load_disposition_ledger_report(
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


def load_globalvalues_decision_ledger_report(
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
                    semantic_bindings=tuple(
                        row["semantic_bindings"]
                    ),
                )
                for row in document["physical_rows"]
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("verified_emission_document_invalid") from error
    if verified_emission_input_document(verified) != dict(document):
        raise ValueError("verified_emission_document_malformed")
    return verified


def _verified_emission_from_package_view(
    *,
    package: PackageView,
    disposition_ledger: DispositionLedger,
    source_contract_audit: Mapping[str, Any] | None,
    configuration_mode: str = CONSERVATIVE,
) -> VerifiedEmissionInput:
    try:
        runtime_ledger = package.read_json(
            "reports/runtime_surface_ledger.json"
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError(
            "verified_emission_package_view_mismatch"
        ) from error
    if (
        not isinstance(runtime_ledger, Mapping)
        or runtime_ledger.get("schema_version") != 2
    ):
        raise ValueError("verified_emission_package_view_mismatch")
    reported_observations = _physical_cardid_observations(
        runtime_ledger
    )
    actual_observations: set[tuple[str, str]] = set()
    payload_by_observation: dict[
        tuple[str, str],
        Mapping[str, Any],
    ] = {}
    for name in package.file_names():
        normalized = name.replace("\\", "/")
        if (
            not normalized.startswith("CustomConfig/")
            or not normalized.endswith(".json")
            or normalized.rsplit("/", 1)[-1]
            in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
        ):
            continue
        try:
            payload = package.read_json(normalized)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise ValueError(
                "verified_emission_package_view_mismatch"
            ) from error
        if not isinstance(payload, Mapping):
            raise ValueError(
                "verified_emission_package_view_mismatch"
            )
        if validate_card_runtime_payload(
            Path(normalized),
            payload,
        ):
            raise ValueError(
                "verified_emission_runtime_schema_invalid"
            )
        owner = payload.get("GameCardId")
        if not isinstance(owner, str) or not owner:
            raise ValueError(
                "verified_emission_package_view_mismatch"
            )
        meaningful_keys = {
            key
            for key in payload
            if key not in {"GameCardId", "ConfigComment"}
        }
        if not meaningful_keys:
            continue
        surface = normalized.rsplit("/", 1)[-1]
        observation = (owner, surface)
        if observation in payload_by_observation:
            raise ValueError(
                "verified_emission_package_view_mismatch"
            )
        actual_observations.add(observation)
        payload_by_observation[observation] = payload
    if actual_observations != reported_observations:
        raise ValueError("verified_emission_package_view_mismatch")

    expectations = _verified_emission_expectations_for_mode(
        configuration_mode=configuration_mode,
        disposition_ledger=disposition_ledger,
        source_contract_audit=source_contract_audit,
    )
    physical_rows = tuple(
        {
            "physical_owner": owner,
            "relative_path": surface,
            "meaningful": True,
            "schema_supported": True,
        }
        for owner, surface in sorted(actual_observations)
    )
    rejected_rows = [
        *runtime_ledger.get("physical_errors", ()),
        *runtime_ledger.get("unexpected_runtime_emissions", ()),
        *runtime_ledger.get(
            "linked_runtime_owner_collisions",
            (),
        ),
    ]
    return verified_emission_input_from_physical_rows(
        disposition_ledger=disposition_ledger,
        physical_rows=physical_rows,
        rejected_rows=rejected_rows,
        semantic_expectations=expectations,
    )


def _verified_emission_expectations_for_mode(
    *,
    configuration_mode: str,
    disposition_ledger: DispositionLedger,
    source_contract_audit: Mapping[str, Any] | None,
) -> tuple[VerifiedSemanticExpectation, ...]:
    mode = configuration_mode_from_manifest(
        {"configuration_mode": configuration_mode}
    )
    if mode == LLM_OPTIMIZED_START or source_contract_audit is None:
        return verified_emission_input_from_ledgers(
            disposition_ledger=disposition_ledger,
            runtime_surface_ledger={},
        ).expectations
    return pre_emission_expectations_from_audit(
        disposition_ledger=disposition_ledger,
        source_contract_audit=source_contract_audit,
    )


def _load_pre_run_authority_handoff(
    document: Mapping[str, Any],
    *,
    disposition_ledger: DispositionLedger,
) -> dict[str, EvidenceAuthority]:
    if set(document) != {
        "schema_version",
        "deck_fingerprint",
        "authorities",
        "content_sha256",
    }:
        raise ValueError("pre_run_authority_handoff_malformed")
    if (
        type(document.get("schema_version")) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("pre_run_authority_handoff_schema_invalid")
    if document.get("content_sha256") != _report_content_sha256(
        document
    ):
        raise ValueError("pre_run_authority_handoff_hash_stale")
    if (
        document.get("deck_fingerprint")
        != disposition_ledger.deck_fingerprint
    ):
        raise ValueError("pre_run_authority_handoff_cross_deck")
    rows = document.get("authorities")
    if not isinstance(rows, list):
        raise ValueError("pre_run_authority_handoff_malformed")
    claim_ids: list[str] = []
    identities: list[str] = []
    classified_authorities: dict[str, EvidenceAuthority] = {}
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or set(row) != _BOUND_EVIDENCE_AUTHORITY_FIELDS
        ):
            raise ValueError("pre_run_authority_handoff_malformed")
        try:
            authority = evidence_authority_from_projection(row)
            bound = BoundEvidenceAuthority(
                deck_fingerprint=row["deck_fingerprint"],
                composite_claim_identity=row[
                    "composite_claim_identity"
                ],
                claim_id=row["claim_id"],
                authority=authority,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "pre_run_authority_handoff_malformed"
            ) from error
        claim_ids.append(bound.claim_id)
        identities.append(bound.composite_claim_identity)
        classified_authorities[bound.claim_id] = authority
    if (
        len(set(claim_ids)) != len(claim_ids)
        or len(set(identities)) != len(identities)
    ):
        raise ValueError("pre_run_authority_handoff_duplicate")
    try:
        canonical_bound = _bind_evidence_authorities(
            disposition_ledger=disposition_ledger,
            classified_authorities=classified_authorities,
        )
    except ValueError as error:
        raise ValueError(
            "pre_run_authority_handoff_claim_mismatch"
        ) from error
    if rows != [
        _bound_evidence_authority_document(row)
        for row in canonical_bound
    ]:
        raise ValueError("pre_run_authority_handoff_malformed")
    return classified_authorities


def _validate_layered_evidence_report(
    document: Mapping[str, Any],
    *,
    disposition_ledger: DispositionLedger,
    source_contract_audit: Mapping[str, Any] | None,
    authority_handoff: Mapping[str, EvidenceAuthority],
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
    raw_identities = [
        row.get("composite_claim_identity")
        for row in rows
        if isinstance(row, Mapping)
    ]
    if len(raw_identities) != len(rows):
        raise ValueError("layered_evidence_contract_malformed")
    if len(set(raw_identities)) != len(raw_identities):
        raise ValueError("layered_evidence_contract_duplicate")
    canonical_bound = _bind_evidence_authorities(
        disposition_ledger=disposition_ledger,
        classified_authorities=authority_handoff,
    )
    canonical_rows = [
        _bound_evidence_authority_document(row)
        for row in canonical_bound
    ]
    if rows != canonical_rows:
        raise ValueError(
            "layered_evidence_contract_upstream_mismatch"
        )
    source_claim_rows = (
        source_contract_audit.get("claim_rows", {})
        if isinstance(source_contract_audit, Mapping)
        else {}
    )
    if not isinstance(source_claim_rows, Mapping):
        raise ValueError(
            "layered_evidence_contract_upstream_mismatch"
        )
    source_authorities: dict[str, Mapping[str, Any]] = {}
    for raw_claim_id, source_row in source_claim_rows.items():
        if (
            isinstance(source_row, Mapping)
            and "evidence_authority" in source_row
        ):
            projection = source_row["evidence_authority"]
            if projection is None:
                continue
            if not isinstance(projection, Mapping):
                raise ValueError(
                    "layered_evidence_contract_upstream_mismatch"
                )
            claim_id = str(raw_claim_id)
            if (
                source_row.get("claim_id") not in {None, claim_id}
                or claim_id in source_authorities
            ):
                raise ValueError(
                    "layered_evidence_contract_upstream_mismatch"
                )
            source_authorities[claim_id] = projection
    try:
        source_bound = _bind_evidence_authorities(
            disposition_ledger=disposition_ledger,
            classified_authorities=source_authorities,
        )
    except ValueError as error:
        raise ValueError(
            "layered_evidence_contract_upstream_mismatch"
        ) from error
    if [
        _bound_evidence_authority_document(row)
        for row in source_bound
    ] != canonical_rows:
        raise ValueError(
            "layered_evidence_contract_upstream_mismatch"
        )
    expected = {
        f"{fingerprint}:{row.claim_id}"
        for row in disposition_ledger.claims
    }
    ratio = _metric_ratio_from_document(
        document.get("layered_coverage")
    )
    if (
        ratio.numerator != len(canonical_rows)
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
    expected_policy = policy_provenance_payload(load_policy_profile())
    if document.get("policy_provenance") != expected_policy:
        raise ValueError("source_acquisition_policy_binding_mismatch")
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
    try:
        typed_closure = AcquisitionClosure(
            deck_fingerprint=str(closure["deck_fingerprint"]),
            attempt_id=str(closure["attempt_id"]),
            attempted_at=str(closure["attempted_at"]),
            attempted_urls=tuple(closure["attempted_urls"]),
            successful_evidence_ids=tuple(
                closure["successful_evidence_ids"]
            ),
            failed_attempts=tuple(
                AcquisitionFailure(
                    source_identity=str(row["source_identity"]),
                    reason_code=str(row["reason_code"]),
                    attempted_at=str(row["attempted_at"]),
                )
                for row in closure["failed_attempts"]
            ),
            negative_search_documented=closure[
                "negative_search_documented"
            ],
            checked_dossier=closure["checked_dossier"],
            policy_id=closure["policy_id"],
            status=closure["status"],
            content_sha256=closure["content_sha256"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "source_acquisition_closure_malformed"
        ) from error
    if typed_closure.content_sha256 != acquisition_closure_content_sha256(
        typed_closure,
        policy_profile=load_policy_profile(),
    ):
        raise ValueError(
            "source_acquisition_closure_content_hash_mismatch"
        )
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
        source_contract_audit = (
            package.read_json("reports/source_contract_audit.json")
            if package.exists("reports/source_contract_audit.json")
            else None
        )
        input_manifest = (
            package.read_json("reports/input_manifest.json")
            if package.exists("reports/input_manifest.json")
            else None
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("pre_run_report_malformed") from error
    if (
        not isinstance(deck_identity, Mapping)
        or any(
            not isinstance(document, Mapping)
            for document in documents.values()
        )
        or (
            source_contract_audit is not None
            and not isinstance(source_contract_audit, Mapping)
        )
    ):
        raise ValueError("pre_run_report_malformed")
    if input_manifest is None:
        raise ValueError("pre_run_input_manifest_missing")
    if not isinstance(input_manifest, Mapping):
        raise ValueError("pre_run_input_manifest_malformed")
    if (
        type(
            input_manifest.get("pre_run_contract_schema_version")
        )
        is not int
        or input_manifest["pre_run_contract_schema_version"]
        != PRE_RUN_CONTRACT_SCHEMA_VERSION
    ):
        raise ValueError(
            "pre_run_contract_schema_version_invalid"
        )
    configuration_mode = configuration_mode_from_manifest(input_manifest)
    disposition = load_disposition_ledger_report(
        documents["reports/disposition_ledger.json"]
    )
    globalvalues = load_globalvalues_decision_ledger_report(
        documents["reports/globalvalues_decision_ledger.json"]
    )
    fingerprint = disposition.deck_fingerprint
    if globalvalues.deck_fingerprint != fingerprint:
        raise ValueError("pre_run_report_cross_deck")
    authority_handoff_document = input_manifest.get(
        "pre_run_authority_handoff"
    )
    if authority_handoff_document is None:
        raise ValueError("pre_run_authority_handoff_missing")
    if not isinstance(authority_handoff_document, Mapping):
        raise ValueError("pre_run_authority_handoff_malformed")
    authority_handoff = _load_pre_run_authority_handoff(
        authority_handoff_document,
        disposition_ledger=disposition,
    )
    _validate_layered_evidence_report(
        documents["reports/layered_evidence_contract.json"],
        disposition_ledger=disposition,
        source_contract_audit=source_contract_audit,
        authority_handoff=authority_handoff,
    )
    _validate_acquisition_report(
        documents["reports/source_acquisition_closure.json"],
        deck_fingerprint=fingerprint,
    )
    if input_manifest.get(
        "source_acquisition_input_binding"
    ) != source_acquisition_input_binding(
        documents["reports/source_acquisition_closure.json"]
    ):
        raise ValueError(
            "source_acquisition_upstream_manifest_mismatch"
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
    expected_semantics = _verified_emission_expectations_for_mode(
        configuration_mode=configuration_mode,
        disposition_ledger=disposition,
        source_contract_audit=source_contract_audit,
    )
    if verified.expectations != expected_semantics:
        raise ValueError(
            "verified_emission_semantic_projection_mismatch"
        )
    if package.exists("reports/runtime_surface_ledger.json"):
        if (
            configuration_mode == CONSERVATIVE
            and source_contract_audit is None
        ):
            raise ValueError(
                "verified_emission_package_view_mismatch"
            )
        rederived_verified = _verified_emission_from_package_view(
            package=package,
            disposition_ledger=disposition,
            source_contract_audit=source_contract_audit,
            configuration_mode=configuration_mode,
        )
        if verified != rederived_verified:
            raise ValueError(
                "verified_emission_package_view_mismatch"
            )
    elif verified.physical_rows:
        raise ValueError("verified_emission_package_view_mismatch")
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
    *,
    semantic_inventory: Mapping[str, Any],
    audited_catalog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate package closure only against the approved audited inventory."""

    inventory_summary = validate_semantic_inventory(
        semantic_inventory,
        audited_catalog=audited_catalog,
    )
    if len(packages) != inventory_summary.deck_count:
        raise ValueError("pre_run_audited_deck_total_must_equal_12")
    validated = tuple(
        validate_pre_run_package_reports(package) for package in packages
    )
    fingerprints = tuple(row.deck_fingerprint for row in validated)
    if len(set(fingerprints)) != len(fingerprints):
        raise ValueError("pre_run_duplicate_package")
    inventory_by_fingerprint = {
        str(row["deck_fingerprint"]): row
        for row in semantic_inventory["decks"]
    }
    if set(fingerprints) != set(inventory_by_fingerprint):
        raise ValueError("pre_run_semantic_inventory_mismatch")
    for package in validated:
        inventory_row = inventory_by_fingerprint[
            package.deck_fingerprint
        ]
        expected_cards = {
            str(row["composite_card_key"])
            for row in (
                *inventory_row["main_cards"],
                *inventory_row["sideboard_modules"],
            )
        }
        expected_claims = {
            str(row["claim_id"])
            for row in inventory_row["claims"]
        }
        if (
            package.deck_identity.get("deck_name")
            != inventory_row["deck_name"]
        ):
            raise ValueError("pre_run_semantic_inventory_mismatch")
        if (
            {
                row.composite_card_key
                for row in package.disposition_ledger.cards
            }
            != expected_cards
            or {
                row.claim_id
                for row in package.disposition_ledger.claims
            }
            != expected_claims
            or {
                row.key
                for row in package.globalvalues_ledger.decisions
            }
            != set(inventory_row["globalvalues_decisions"])
        ):
            raise ValueError("pre_run_audited_totals_mismatch")
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
    expected_totals = {
        "main_slot_count": inventory_summary.main_slot_count,
        "main_card_identity_count": (
            inventory_summary.main_card_identity_count
        ),
        "sideboard_module_count": (
            inventory_summary.sideboard_module_count
        ),
        "card_disposition_count": (
            inventory_summary.disposition_row_count
        ),
        "claim_count": inventory_summary.claim_count,
        "globalvalues_decision_count": (
            inventory_summary.globalvalues_decision_count
        ),
    }
    if audited_totals != expected_totals:
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


def audited_semantic_inventory_acceptance(
    *,
    semantic_inventory: Mapping[str, Any],
    audited_catalog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate the approved 12-deck inventory without claiming package closure."""

    summary = validate_semantic_inventory(
        semantic_inventory,
        audited_catalog=audited_catalog,
    )
    return {
        "schema_version": 1,
        "scope": "AUDITED_SEMANTIC_INVENTORY_ONLY",
        "package_closure_claimed": False,
        "gameplay_quality_claimed": False,
        "runtime_emission_claimed": False,
        "canonical_content_sha256": semantic_inventory[
            "canonical_content_sha256"
        ],
        "deck_count": summary.deck_count,
        "main_slot_count": summary.main_slot_count,
        "main_card_identity_count": (
            summary.main_card_identity_count
        ),
        "sideboard_module_count": summary.sideboard_module_count,
        "card_disposition_count": summary.disposition_row_count,
        "claim_count": summary.claim_count,
        "globalvalues_decision_count": (
            summary.globalvalues_decision_count
        ),
    }
