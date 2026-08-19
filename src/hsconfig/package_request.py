"""Immutable values crossing from package resolution into pure compilation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePath
import re
from typing import TYPE_CHECKING, Any, Callable, Literal

from hsconfig.build_context import ResolvedBuildContext, resolve_build_context
from hsconfig.build_input_catalog import (
    load_packaged_audited_build_inputs,
    load_packaged_audited_build_resource_store,
)
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.globalvalues_decisions import (
    normalize_globalvalues_decision_baseline,
)
from hsconfig.package_domain import _ImmutableAuthorityNode
from hsconfig.pre_run_metrics import build_source_acquisition_closure_report
from hsconfig.preconfig_context import build_preconfig_context

if TYPE_CHECKING:
    from hsconfig.starter_decision import ValidatedStarterSelection


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"frozen_json_non_finite_number:{value}")


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("frozen_json_duplicate_key")
        result[key] = value
    return result


def _decode_json(value: bytes) -> Any:
    try:
        return json.loads(
            value,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ValueError("frozen_json_invalid") from error


def _json_sort_key(value: Any) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _json_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("frozen_json_mapping_key_invalid")
            normalized[key] = _json_value(item)
        return normalized
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        normalized_items = [_json_value(item) for item in value]
        return sorted(normalized_items, key=_json_sort_key)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"frozen_json_value_invalid:{type(value).__name__}")


@dataclass(frozen=True, init=False)
class FrozenJsonDocument(_ImmutableAuthorityNode):
    """Canonical JSON bytes that own no caller-provided mutable objects."""

    canonical_json: bytes

    def __post_init__(self) -> None:
        canonical_input = bytes(self.canonical_json)
        value = _decode_json(canonical_input)
        canonical = _json_sort_key(value)
        if canonical != canonical_input:
            raise ValueError("frozen_json_not_canonical")

    @classmethod
    def from_value(cls, value: Any) -> FrozenJsonDocument:
        return cls(_json_sort_key(_json_value(value)))

    @classmethod
    def from_json_bytes(
        cls,
        value: bytes | bytearray | memoryview,
    ) -> FrozenJsonDocument:
        return cls.from_value(_decode_json(bytes(value)))

    def to_value(self) -> Any:
        return _decode_json(self.canonical_json)


_GENERAL_PRECONFIG_FIELDS = frozenset(
    {
        "cards_payload",
        "deck_identity",
        "card_metadata",
        "semantic_report",
        "guide_claim_bundle",
        "source_claims",
        "research_bundle",
        "guide_sources_generated",
        "guide_builder_receipt",
        "deck_fingerprint",
        "candidate_archetypes",
        "identity_graph_report",
        "identity_gap_report",
        "card_data_intake_report",
        "source_evidence_report",
        "source_document_draft_report",
        "policy_profile",
        "globalvalues_baseline",
        "globalvalues_baseline_receipt",
    }
)
_PLAN_OVERRIDE_FILENAMES = frozenset(
    {
        "guide_claim_bundle.json",
        "mulligan_plan_report.json",
        "card_behavior_plan_report.json",
        "combo_plan_report.json",
        "global_values_authority_matrix.json",
    }
)
_ACQUISITION_CLOSURE_FIELDS = frozenset(
    {
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
)
_ACQUISITION_FAILURE_FIELDS = frozenset(
    {"source_identity", "reason_code", "attempted_at"}
)
_MULLIGAN_GAP_FIELDS = frozenset(
    {
        "target_deck_name",
        "target_deck_fingerprint",
        "target_deck_code_hash",
        "card_id",
        "first_missing_source_action",
        "reason",
    }
)
_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _document_mapping(value: Any, *, error: str) -> dict[str, Any]:
    normalized = _json_value(value)
    if not isinstance(normalized, dict):
        raise ValueError(error)
    return normalized


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


@dataclass(frozen=True, init=False)
class GeneralPreconfigSnapshot(_ImmutableAuthorityNode):
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("general_preconfig_document_invalid")
        _validate_general_preconfig(self.document.to_value())

    @classmethod
    def from_value(cls, value: Any) -> GeneralPreconfigSnapshot:
        normalized = _document_mapping(
            value,
            error="general_preconfig_schema_invalid",
        )
        normalized = _close_general_preconfig_baseline(normalized)
        _validate_general_preconfig(normalized)
        return cls(FrozenJsonDocument.from_value(normalized))

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> dict[str, Any]:
        return self.document.to_value()


def _validate_general_preconfig(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or not value
        or frozenset(value) != _GENERAL_PRECONFIG_FIELDS
    ):
        raise ValueError("general_preconfig_schema_invalid")
    baseline = value["globalvalues_baseline"]
    receipt = value["globalvalues_baseline_receipt"]
    if not isinstance(baseline, dict) or not isinstance(receipt, dict):
        raise ValueError("general_preconfig_schema_invalid")
    if normalize_globalvalues_decision_baseline(baseline) != baseline:
        raise ValueError("globalvalues_baseline_not_closed")
    receipt_baseline = receipt.get("baseline")
    if (
        not isinstance(receipt_baseline, dict)
        or normalize_globalvalues_decision_baseline(receipt_baseline)
        != baseline
    ):
        raise ValueError("globalvalues_baseline_receipt_mismatch")


def _close_general_preconfig_baseline(
    value: dict[str, Any],
) -> dict[str, Any]:
    if frozenset(value) != _GENERAL_PRECONFIG_FIELDS:
        return value
    baseline = value.get("globalvalues_baseline")
    receipt = value.get("globalvalues_baseline_receipt")
    if not isinstance(baseline, dict) or not isinstance(receipt, dict):
        return value
    effective = normalize_globalvalues_decision_baseline(baseline)
    receipt_baseline = receipt.get("baseline")
    if (
        not isinstance(receipt_baseline, dict)
        or normalize_globalvalues_decision_baseline(receipt_baseline)
        != effective
    ):
        raise ValueError("globalvalues_baseline_receipt_mismatch")
    return {**value, "globalvalues_baseline": effective}


@dataclass(frozen=True, init=False)
class PlanOverrides(_ImmutableAuthorityNode):
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("plan_overrides_document_invalid")
        _validate_plan_overrides(self.document.to_value())

    @classmethod
    def from_value(cls, value: Any) -> PlanOverrides:
        normalized = _document_mapping(
            value,
            error="plan_overrides_schema_invalid",
        )
        _validate_plan_overrides(normalized)
        return cls(FrozenJsonDocument.from_value(normalized))

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> dict[str, Any]:
        return self.document.to_value()


def _validate_plan_overrides(value: Any) -> None:
    if (
        not isinstance(value, dict)
        or not frozenset(value).issubset(_PLAN_OVERRIDE_FILENAMES)
        or any(not isinstance(payload, dict) for payload in value.values())
    ):
        raise ValueError("plan_overrides_schema_invalid")


@dataclass(frozen=True, init=False)
class AcquisitionClosureInput(_ImmutableAuthorityNode):
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("acquisition_closure_document_invalid")
        _validate_acquisition_closure(self.document.to_value())

    @classmethod
    def from_value(cls, value: Any) -> AcquisitionClosureInput:
        normalized = _document_mapping(
            value,
            error="acquisition_closure_schema_invalid",
        )
        _validate_acquisition_closure(normalized)
        return cls(FrozenJsonDocument.from_value(normalized))

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> dict[str, Any]:
        return self.document.to_value()


def _validate_acquisition_closure(value: Any) -> None:
    absent_open = (
        isinstance(value, dict)
        and value.get("status") == "open"
        and value.get("attempt_id") == ""
        and value.get("attempted_at") == ""
        and value.get("attempted_urls") == []
        and value.get("successful_evidence_ids") == []
        and value.get("failed_attempts") == []
        and value.get("negative_search_documented") is False
        and value.get("checked_dossier") is False
        and value.get("policy_id") is None
    )
    if (
        not isinstance(value, dict)
        or frozenset(value) != _ACQUISITION_CLOSURE_FIELDS
        or any(
            not _nonempty_string(value[field])
            for field in (
                "deck_fingerprint",
                "status",
            )
        )
        or (
            not absent_open
            and (
                not _nonempty_string(value["attempt_id"])
                or not _nonempty_string(value["attempted_at"])
            )
        )
        or value["status"]
        not in {"closed_with_evidence", "closed_negative_search", "open"}
        or not isinstance(value["attempted_urls"], list)
        or not all(_nonempty_string(item) for item in value["attempted_urls"])
        or not isinstance(value["successful_evidence_ids"], list)
        or not all(
            _nonempty_string(item)
            for item in value["successful_evidence_ids"]
        )
        or not isinstance(value["failed_attempts"], list)
        or type(value["negative_search_documented"]) is not bool
        or type(value["checked_dossier"]) is not bool
        or (
            value["policy_id"] is not None
            and not _nonempty_string(value["policy_id"])
        )
        or _CONTENT_SHA256_RE.fullmatch(
            str(value["content_sha256"])
        )
        is None
    ):
        raise ValueError("acquisition_closure_schema_invalid")
    for failure in value["failed_attempts"]:
        if (
            not isinstance(failure, dict)
            or frozenset(failure) != _ACQUISITION_FAILURE_FIELDS
            or not all(_nonempty_string(item) for item in failure.values())
        ):
            raise ValueError("acquisition_closure_schema_invalid")


@dataclass(frozen=True, init=False)
class MulliganGapInput(_ImmutableAuthorityNode):
    document: FrozenJsonDocument

    def __post_init__(self) -> None:
        if not isinstance(self.document, FrozenJsonDocument):
            raise TypeError("mulligan_gap_document_invalid")
        _validate_mulligan_gaps(self.document.to_value())

    @classmethod
    def from_value(cls, value: Any) -> MulliganGapInput:
        normalized = _json_value(value)
        _validate_mulligan_gaps(normalized)
        return cls(FrozenJsonDocument.from_value(normalized))

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> list[dict[str, str]]:
        return self.document.to_value()


def _validate_mulligan_gaps(value: Any) -> None:
    if not isinstance(value, list):
        raise ValueError("mulligan_gap_schema_invalid")
    for row in value:
        if (
            not isinstance(row, dict)
            or frozenset(row) != _MULLIGAN_GAP_FIELDS
            or not all(_nonempty_string(item) for item in row.values())
        ):
            raise ValueError("mulligan_gap_schema_invalid")


@dataclass(frozen=True, init=False)
class PackageInvocation(_ImmutableAuthorityNode):
    """Output-affecting invocation values, excluding transport concerns."""

    deck_code: str
    runtime_root: str
    cards_json: str | None
    claims_json: str | None
    guide_sources_json: str | None
    plan_reports_dir: str | None
    target_config_mode: str
    include_disposition_diagnostics: bool
    configuration_mode: Literal["CONSERVATIVE", "LLM_OPTIMIZED_START"] = (
        "CONSERVATIVE"
    )

    @classmethod
    def _normalize_authority_values(
        cls,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = dict(values)
        for field_name in (
            "cards_json",
            "claims_json",
            "guide_sources_json",
            "plan_reports_dir",
        ):
            value = normalized[field_name]
            if isinstance(value, PurePath):
                normalized[field_name] = str(value)
        return normalized

    def __post_init__(self) -> None:
        if (
            not isinstance(self.deck_code, str)
            or not self.deck_code
            or self.deck_code != self.deck_code.strip()
        ):
            raise ValueError("package_invocation_deck_code_invalid")
        if (
            not isinstance(self.runtime_root, str)
            or not self.runtime_root
            or self.runtime_root != self.runtime_root.strip()
        ):
            raise ValueError("package_invocation_runtime_root_invalid")
        for field_name in (
            "cards_json",
            "claims_json",
            "guide_sources_json",
            "plan_reports_dir",
        ):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str)
                or not value
                or value != value.strip()
            ):
                raise ValueError(f"package_invocation_{field_name}_invalid")
        if self.target_config_mode != "preview":
            raise ValueError("package_invocation_target_config_mode_invalid")
        if type(self.include_disposition_diagnostics) is not bool:
            raise ValueError(
                "package_invocation_disposition_diagnostics_invalid"
            )
        if not isinstance(self.configuration_mode, str) or (
            self.configuration_mode not in {
            "CONSERVATIVE",
            "LLM_OPTIMIZED_START",
            }
        ):
            raise ValueError("configuration_mode_invalid")


@dataclass(frozen=True, init=False)
class PackageResolutionSnapshot(_ImmutableAuthorityNode):
    """One preconfig authority with optional strict audited binding proof."""

    general_preconfig: GeneralPreconfigSnapshot
    strict_build_context: ResolvedBuildContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(
            self.general_preconfig,
            GeneralPreconfigSnapshot,
        ):
            raise TypeError("preconfig_snapshot_invalid")
        if self.strict_build_context is not None and not isinstance(
            self.strict_build_context, ResolvedBuildContext
        ):
            raise TypeError("strict_build_context_invalid")
        if self.strict_build_context is not None:
            deck_identity = self.general_preconfig.to_value()[
                "deck_identity"
            ]
            if (
                not isinstance(deck_identity, dict)
                or deck_identity.get("deck_name")
                != self.strict_build_context.inputs.deck_name
                or deck_identity.get("deck_fingerprint")
                != self.strict_build_context.inputs.deck_fingerprint
                or deck_identity.get("deck_code_hash")
                != self.strict_build_context.inputs.deck_code_sha256
            ):
                raise ValueError("resolution_snapshot_strict_binding_mismatch")

    @classmethod
    def from_strict(
        cls,
        context: ResolvedBuildContext,
        preconfig: Any,
    ) -> PackageResolutionSnapshot:
        if not isinstance(context, ResolvedBuildContext):
            raise TypeError("strict_build_context_invalid")
        return cls(
            general_preconfig=GeneralPreconfigSnapshot.from_value(preconfig),
            strict_build_context=context,
        )

    @classmethod
    def from_preconfig(
        cls,
        value: Any,
    ) -> PackageResolutionSnapshot:
        return cls(
            general_preconfig=GeneralPreconfigSnapshot.from_value(value),
        )

    @property
    def resolved_build_context(self) -> ResolvedBuildContext | None:
        return self.strict_build_context

    @property
    def preconfig_canonical_json(self) -> bytes:
        return self.general_preconfig.canonical_json


@dataclass(frozen=True, init=False)
class ResolvedPackageRequest(_ImmutableAuthorityNode):
    """The complete immutable input accepted by the future pure compiler."""

    snapshot: PackageResolutionSnapshot
    invocation: PackageInvocation
    plan_overrides: PlanOverrides
    acquisition_closure_input: AcquisitionClosureInput
    mulligan_gap_input: MulliganGapInput
    starter_selection: ValidatedStarterSelection | None = None

    def __post_init__(self) -> None:
        expected_types = (
            ("snapshot", self.snapshot, PackageResolutionSnapshot),
            ("invocation", self.invocation, PackageInvocation),
            ("plan_overrides", self.plan_overrides, PlanOverrides),
            (
                "acquisition_closure_input",
                self.acquisition_closure_input,
                AcquisitionClosureInput,
            ),
            ("mulligan_gap_input", self.mulligan_gap_input, MulliganGapInput),
        )
        for field_name, value, expected_type in expected_types:
            if not isinstance(value, expected_type):
                raise TypeError(f"resolved_package_request_{field_name}_invalid")
        strict_context = self.snapshot.strict_build_context
        invocation_hash = sha256(
            self.invocation.deck_code.encode("utf-8")
        ).hexdigest()
        deck_identity = self.snapshot.general_preconfig.to_value().get(
            "deck_identity",
            {},
        )
        identity_hash = (
            deck_identity.get("deck_code_hash")
            if isinstance(deck_identity, dict)
            else None
        )
        expected_hash = (
            strict_context.inputs.deck_code_sha256
            if strict_context is not None
            else identity_hash
        )
        if not isinstance(expected_hash, str) or invocation_hash != (
            expected_hash.removeprefix("sha256:")
        ):
            raise ValueError("resolved_package_request_deck_code_mismatch")
        if self.invocation.configuration_mode == "CONSERVATIVE":
            if self.starter_selection is not None:
                raise ValueError("starter_selection_forbidden")
            return
        if self.invocation.configuration_mode != "LLM_OPTIMIZED_START":
            raise ValueError("configuration_mode_invalid")

        from hsconfig.starter_candidate import validate_starter_candidate
        from hsconfig.starter_context import StarterContext, build_starter_context
        from hsconfig.starter_decision import (
            ValidatedStarterSelection,
            _validate_candidate_set,
            _validate_decision,
        )
        from hsconfig.starter_contract import (
            STARTER_DECISION_FIELDS,
            STARTER_SCHEMA_VERSION,
        )
        from hsconfig.starter_document import (
            StarterDocument,
            seal_starter_document,
        )

        selection = self.starter_selection
        if not isinstance(selection, ValidatedStarterSelection):
            raise ValueError("starter_selection_required")
        current_context = build_starter_context(self.snapshot)
        if not isinstance(selection.context, StarterContext):
            raise ValueError("starter_selection_invalid")
        if (
            selection.context.document.canonical_json
            != current_context.document.canonical_json
            or selection.context.document.content_sha256
            != current_context.document.content_sha256
        ):
            raise ValueError("starter_context_mismatch")
        try:
            if not isinstance(selection.decision, StarterDocument):
                raise TypeError("starter_decision_invalid")
            decision_value = selection.decision.to_value()
            unsigned_decision = dict(decision_value)
            embedded_digest = unsigned_decision.pop("content_sha256")
            decision = seal_starter_document(
                unsigned_decision,
                expected_fields=STARTER_DECISION_FIELDS,
                schema_version=STARTER_SCHEMA_VERSION,
            )
            if (
                selection.decision.document.canonical_json
                != decision.document.canonical_json
                or selection.decision.content_sha256
                != decision.content_sha256
                or embedded_digest != decision.content_sha256
            ):
                raise ValueError("starter_decision_reseal_mismatch")
            candidates = tuple(
                validate_starter_candidate(
                    candidate.document,
                    context=current_context,
                )
                for candidate in selection.candidates
            )
            _validate_candidate_set(candidates)
            selected_id = _validate_decision(
                decision,
                current_context=current_context,
                candidates=candidates,
            )
            selected = next(
                candidate
                for candidate in candidates
                if candidate.candidate_id == selected_id
            )
            resealed = ValidatedStarterSelection(
                context=current_context,
                candidates=candidates,
                decision=decision,
                selected=selected,
            )
        except (AttributeError, KeyError, StopIteration, TypeError, ValueError) as error:
            raise ValueError("starter_selection_invalid") from error
        if resealed != selection:
            raise ValueError("starter_selection_invalid")

    @classmethod
    def from_values(
        cls,
        *,
        snapshot: PackageResolutionSnapshot,
        invocation: PackageInvocation,
        plan_overrides: Any,
        acquisition_closure_input: Any,
        mulligan_gap_input: Any,
        starter_selection: ValidatedStarterSelection | None = None,
    ) -> ResolvedPackageRequest:
        return cls(
            snapshot=snapshot,
            invocation=invocation,
            plan_overrides=PlanOverrides.from_value(plan_overrides),
            acquisition_closure_input=AcquisitionClosureInput.from_value(
                acquisition_closure_input
            ),
            mulligan_gap_input=MulliganGapInput.from_value(
                mulligan_gap_input
            ),
            starter_selection=starter_selection,
        )

    @property
    def resolution_snapshot(self) -> PackageResolutionSnapshot:
        return self.snapshot

    @property
    def acquisition_closure(self) -> AcquisitionClosureInput:
        return self.acquisition_closure_input

    @property
    def mulligan_source_gaps(self) -> MulliganGapInput:
        return self.mulligan_gap_input


def resolve_package_request(
    args: Any,
    *,
    current_date: date,
    fetch_latest_cards_fn: Callable[..., Any],
    research_required_guide_sources_fn: Callable[..., dict[str, Any]],
    source_authority_handoff: Any = None,
    acquisition_closure: Any = None,
    mulligan_source_gaps: Sequence[Mapping[str, str]] | None = None,
    include_disposition_diagnostics: bool = False,
) -> ResolvedPackageRequest:
    """Resolve every physical input once, then seal the compiler request."""

    optimized_start = getattr(args, "optimized_start", False)
    starter_decision_json = getattr(args, "starter_decision_json", None)
    if type(optimized_start) is not bool:
        raise ValueError("optimized_start_invalid")
    if optimized_start and starter_decision_json is None:
        raise ValueError("starter_decision_required")
    if not optimized_start and starter_decision_json is not None:
        raise ValueError("starter_decision_not_enabled")
    configuration_mode: Literal["CONSERVATIVE", "LLM_OPTIMIZED_START"] = (
        "LLM_OPTIMIZED_START" if optimized_start else "CONSERVATIVE"
    )
    preconfig = build_preconfig_context(
        args,
        current_date=current_date,
        source_authority_handoff=source_authority_handoff,
        source_authority_consumer="prepare",
        fetch_latest_cards_fn=fetch_latest_cards_fn,
        fetch_latest_collectible_cards_fn=None,
        research_required_guide_sources_fn=(
            research_required_guide_sources_fn
        ),
    )
    policy = load_policy_profile()
    baseline_receipt = load_globalvalues_baseline(str(args.runtime_root))
    baseline = normalize_globalvalues_decision_baseline(
        baseline_receipt["baseline"]
    )
    resolved_preconfig = {
        **preconfig,
        "policy_profile": {
            "policy_id": policy.policy_id,
            "version": policy.version,
            "effective_date": policy.effective_date,
            "content_sha256": policy.content_sha256,
            "rules": json.loads(policy.rules_canonical_json),
        },
        "globalvalues_baseline": baseline,
        "globalvalues_baseline_receipt": baseline_receipt,
    }
    deck_identity = resolved_preconfig["deck_identity"]
    strict_context = _matching_strict_context(
        deck_name=str(args.deck_name),
        deck_fingerprint=str(deck_identity["deck_fingerprint"]),
        deck_code=str(args.deck_code),
    )
    snapshot = (
        PackageResolutionSnapshot.from_strict(
            strict_context,
            resolved_preconfig,
        )
        if strict_context is not None
        else PackageResolutionSnapshot.from_preconfig(resolved_preconfig)
    )
    starter_selection = None
    if optimized_start:
        from hsconfig.starter_context import build_starter_context
        from hsconfig.starter_decision import load_validated_starter_selection

        current_context = build_starter_context(snapshot)
        try:
            starter_selection = load_validated_starter_selection(
                Path(starter_decision_json),
                current_context=current_context,
            )
        except ValueError as error:
            if str(error) in {
                "starter_selection_context_mismatch",
                "starter_decision_context_sha256_mismatch",
                "starter_candidate_context_sha256_mismatch",
            }:
                raise ValueError("starter_context_mismatch") from error
            raise
    acquisition_input = build_source_acquisition_closure_report(
        deck_fingerprint=str(deck_identity["deck_fingerprint"]),
        acquisition_closure=acquisition_closure,
        expected_policy_profile=policy,
    )["acquisition_closure"]
    plan_reports_dir = getattr(args, "plan_reports_dir", None)
    return ResolvedPackageRequest.from_values(
        snapshot=snapshot,
        invocation=PackageInvocation(
            deck_code=str(args.deck_code),
            runtime_root=str(args.runtime_root),
            cards_json=_optional_argument(args, "cards_json"),
            claims_json=_optional_argument(args, "claims_json"),
            guide_sources_json=_optional_argument(
                args,
                "guide_sources_json",
            ),
            plan_reports_dir=(
                str(Path(plan_reports_dir))
                if plan_reports_dir is not None
                else None
            ),
            target_config_mode="preview",
            include_disposition_diagnostics=(
                include_disposition_diagnostics
            ),
            configuration_mode=configuration_mode,
        ),
        plan_overrides=_read_plan_overrides(plan_reports_dir),
        acquisition_closure_input=acquisition_input,
        mulligan_gap_input=list(mulligan_source_gaps or ()),
        starter_selection=starter_selection,
    )


def _matching_strict_context(
    *,
    deck_name: str,
    deck_fingerprint: str,
    deck_code: str,
) -> ResolvedBuildContext | None:
    deck_code_sha256 = sha256(deck_code.encode("utf-8")).hexdigest()
    audited = load_packaged_audited_build_inputs()
    matching = tuple(
        row
        for row in audited.builds
        if row.deck_name == deck_name
        and row.deck_fingerprint == deck_fingerprint
        and row.deck_code_sha256.removeprefix("sha256:")
        == deck_code_sha256
    )
    if not matching:
        return None
    if len(matching) != 1:
        raise ValueError("audited_package_request_identity_ambiguous")
    resources = load_packaged_audited_build_resource_store(
        audited_inputs=audited
    )
    return resolve_build_context(matching[0], resources=resources)


def _read_plan_overrides(value: Any) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    root = Path(value)
    if not root.is_dir():
        raise ValueError(
            f"--plan-reports-dir must be an existing directory: {root}"
        )
    result: dict[str, dict[str, Any]] = {}
    for filename in sorted(_PLAN_OVERRIDE_FILENAMES):
        path = root / filename
        if not path.exists():
            continue
        document = FrozenJsonDocument.from_json_bytes(
            path.read_bytes()
        ).to_value()
        if not isinstance(document, dict):
            raise ValueError(f"Plan report must be an object: {path}")
        result[filename] = document
    return result


def _optional_argument(args: Any, name: str) -> str | None:
    value = getattr(args, name, None)
    return None if value is None else str(value)


PackageRequest = ResolvedPackageRequest


__all__ = (
    "AcquisitionClosureInput",
    "FrozenJsonDocument",
    "GeneralPreconfigSnapshot",
    "MulliganGapInput",
    "PackageInvocation",
    "PackageRequest",
    "PackageResolutionSnapshot",
    "PlanOverrides",
    "ResolvedPackageRequest",
    "resolve_package_request",
)
