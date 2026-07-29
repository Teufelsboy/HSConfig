"""Immutable package model, views, and deterministic identity helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDispositionRow,
    ClaimDisposition,
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
    BotDelegationModel,
    RuntimeSurfaceDecision,
    RuntimeSurfacePlan,
    canonical_relative_path,
)


def _canonical_relative_path(value: str) -> str:
    try:
        return canonical_relative_path(value)
    except ValueError as error:
        raise ValueError("package_artifact_relative_path_invalid") from error


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class PackageArtifact:
    relative_path: str
    content: bytes
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise ValueError("package_artifact_content_must_be_bytes")
        if not isinstance(self.relative_path, str):
            raise ValueError("package_artifact_relative_path_invalid")
        path = _canonical_relative_path(self.relative_path)
        size = len(self.content)
        digest = hashlib.sha256(self.content).hexdigest()
        if type(self.size) is not int or self.size < 0:
            raise ValueError("package_artifact_size_invalid")
        if self.size != size:
            raise ValueError("package_artifact_size_mismatch")
        if (
            not isinstance(self.sha256, str)
            or len(self.sha256) != 64
            or self.sha256.lower() != self.sha256
            or any(char not in "0123456789abcdef" for char in self.sha256)
            or self.sha256 != digest
        ):
            raise ValueError("package_artifact_digest_mismatch")
        object.__setattr__(self, "relative_path", path)
        object.__setattr__(self, "size", size)
        object.__setattr__(self, "sha256", digest)

    @classmethod
    def from_content(cls, *, relative_path: str, content: bytes) -> "PackageArtifact":
        return cls(
            relative_path=relative_path,
            content=content,
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )


@dataclass(frozen=True, slots=True)
class PackageModel:
    deck_name: str
    deck_fingerprint: str
    mulligan_plan: MulliganPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    disposition_ledger: DispositionLedger
    evidence_contract: LayeredEvidenceContract
    runtime_surface_plan: RuntimeSurfacePlan

    def __post_init__(self) -> None:
        if not self.deck_name or not self.deck_fingerprint:
            raise ValueError("package_model_identity_invalid")
        if self.mulligan_plan.deck_name != self.deck_name:
            raise ValueError("package_model_mulligan_identity_mismatch")
        if any(
            fingerprint != self.deck_fingerprint
            for fingerprint in (
                self.globalvalues_ledger.deck_fingerprint,
                self.disposition_ledger.deck_fingerprint,
                self.evidence_contract.deck_fingerprint,
            )
        ):
            raise ValueError("package_model_fingerprint_mismatch")
        if any(
            row.deck_fingerprint != self.deck_fingerprint
            for row in self.globalvalues_ledger.decisions
        ) or any(
            row.deck_fingerprint != self.deck_fingerprint
            for row in (
                *self.disposition_ledger.cards,
                *self.disposition_ledger.claims,
            )
        ):
            raise ValueError("package_model_row_fingerprint_mismatch")
        if any(surface.family == "Combo" for surface in self.runtime_surface_plan.surfaces):
            raise ValueError("combo_typed_payload_unavailable")
        expected = build_runtime_surface_plan(
            mulligan_plan=self.mulligan_plan,
            globalvalues_ledger=self.globalvalues_ledger,
            disposition_ledger=self.disposition_ledger,
            combo_decision_ids=(),
        )
        if self.runtime_surface_plan != expected:
            raise ValueError("runtime_surface_authorization_mismatch")


@dataclass(frozen=True, slots=True)
class RenderedPackage:
    model: PackageModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifacts", tuple(self.artifacts))


class PackageView(Protocol):
    def file_names(self) -> tuple[str, ...]: ...

    def read_bytes(self, relative_path: str) -> bytes: ...

    def read_json(self, relative_path: str) -> Any: ...

    def exists(self, relative_path: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class DirectoryPackageView:
    root: Path

    def _path(self, relative_path: str) -> Path:
        return self.root / _canonical_relative_path(relative_path)

    def file_names(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(
            sorted(
                item.relative_to(self.root).as_posix()
                for item in self.root.rglob("*")
                if item.is_file()
            )
        )

    def read_bytes(self, relative_path: str) -> bytes:
        return self._path(relative_path).read_bytes()

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8"))

    def exists(self, relative_path: str) -> bool:
        return self._path(relative_path).is_file()


def content_root_sha256(artifacts: tuple[PackageArtifact, ...]) -> str:
    seen: set[str] = set()
    records: list[bytes] = []
    for artifact in sorted(artifacts, key=lambda item: item.relative_path):
        if artifact.relative_path in seen:
            raise ValueError("package_artifact_path_duplicate")
        seen.add(artifact.relative_path)
        records.append(
            (
                f"{artifact.relative_path}\0{artifact.size}\0{artifact.sha256}\n"
            ).encode("utf-8")
        )
    return hashlib.sha256(b"".join(records)).hexdigest()


def build_runtime_surface_plan(
    *,
    mulligan_plan: MulliganPlanModel,
    globalvalues_ledger: GlobalValuesDecisionLedger,
    disposition_ledger: DispositionLedger,
    combo_decision_ids: tuple[str, ...],
) -> RuntimeSurfacePlan:
    combo_ids = tuple(combo_decision_ids)
    if combo_ids:
        raise ValueError("combo_typed_payload_unavailable")
    if tuple(sorted(set(combo_ids))) != combo_ids:
        raise ValueError("combo_decision_ids_must_be_unique_sorted")
    claim_ids = {
        row.claim_id
        for row in disposition_ledger.claims
        if row.disposition is ClaimDisposition.RUNTIME_EMITTED
    }
    if any(decision_id not in claim_ids for decision_id in combo_ids):
        raise ValueError("combo_decision_id_not_authorized")
    surfaces = [
        RuntimeSurfaceDecision(
            family="GlobalValues",
            relative_path="GlobalValues.json",
            owner="globalvalues",
            decision_ids=tuple(
                sorted(
                    {
                        f"globalvalues:{row.key}"
                        for row in globalvalues_ledger.decisions
                    }
                )
            ),
        ),
        RuntimeSurfaceDecision(
            family="Mulligan",
            relative_path="Mulligan.json",
            owner="mulligan",
            decision_ids=tuple(
                sorted(
                    {
                        f"mulligan:{authorization_id}"
                        for rule in mulligan_plan.rules
                        for authorization_id in (
                            (rule.claim_id,)
                            if rule.claim_id is not None
                            else rule.source_claim_ids
                        )
                    }
                )
            ),
        ),
    ]
    for row in disposition_ledger.cards:
        if row.disposition is not CardDisposition.RUNTIME_EMITTED:
            continue
        for path in row.runtime_paths:
            surfaces.append(
                RuntimeSurfaceDecision(
                    family="CardID",
                    relative_path=path,
                    owner="cardid",
                    decision_ids=(f"card:{row.physical_owner}",),
                )
            )
    if combo_ids:
        surfaces.append(
            RuntimeSurfaceDecision(
                family="Combo",
                relative_path="Combo.json",
                owner="combo",
                decision_ids=combo_ids,
            )
        )
    return RuntimeSurfacePlan(
        surfaces=tuple(sorted(surfaces, key=lambda surface: surface.relative_path))
    )


def package_model_document(model: PackageModel) -> dict[str, Any]:
    """Canonical, typed report form used only by this new model boundary."""
    return {
        "deck_name": model.deck_name,
        "deck_fingerprint": model.deck_fingerprint,
        "mulligan_plan": model.mulligan_plan.to_report(),
        "globalvalues_ledger": {
            "deck_fingerprint": model.globalvalues_ledger.deck_fingerprint,
            "baseline_sha256": model.globalvalues_ledger.baseline_sha256,
            "content_sha256": model.globalvalues_ledger.content_sha256,
            "decisions": [
                {
                    "key": row.key,
                    "kind": row.kind.value,
                    "baseline": json.loads(row.baseline_canonical_json),
                    "emitted": json.loads(row.emitted_canonical_json),
                    "authority_id": row.authority_id,
                    "claim_ids": list(row.claim_ids),
                    "reason": row.reason,
                }
                for row in model.globalvalues_ledger.decisions
            ],
        },
        "disposition_ledger": {
            "deck_fingerprint": model.disposition_ledger.deck_fingerprint,
            "content_sha256": model.disposition_ledger.content_sha256,
            "cards": [
                {
                    "composite_card_key": row.composite_card_key,
                    "zone": row.zone,
                    "official_semantics": json.loads(row.official_semantics_canonical_json),
                    "authority_lane": row.authority_lane.value,
                    "evidence_ids": list(row.evidence_ids),
                    "claim_ids": list(row.claim_ids),
                    "physical_owner": row.physical_owner,
                    "disposition": row.disposition.value,
                    "runtime_paths": list(row.runtime_paths),
                    "reason_code": row.reason_code,
                }
                for row in model.disposition_ledger.cards
            ],
            "claims": [
                {
                    "claim_id": row.claim_id,
                    "claim_kind": row.claim_kind,
                    "evidence_id": row.evidence_id,
                    "disposition": row.disposition.value,
                    "runtime_paths": list(row.runtime_paths),
                    "reason_code": row.reason_code,
                }
                for row in model.disposition_ledger.claims
            ],
        },
        "evidence_contract": {
            "deck_fingerprint": model.evidence_contract.deck_fingerprint,
            "exact_guide_authority": model.evidence_contract.exact_guide_authority,
            "layered_coverage_numerator": model.evidence_contract.layered_coverage_numerator,
            "layered_coverage_denominator": model.evidence_contract.layered_coverage_denominator,
            "content_sha256": model.evidence_contract.content_sha256,
            "authorities": [
                {
                    "lane": row.lane.value,
                    "authority_id": row.authority_id,
                    "source_identity": row.source_identity,
                    "as_of_date": row.as_of_date,
                    "claim_kind": row.claim_kind,
                    "content_sha256": row.content_sha256,
                    "exact_deck_fingerprint": row.exact_deck_fingerprint,
                    "runtime_authorized": row.runtime_authorized,
                    "reason": row.reason,
                }
                for row in model.evidence_contract.authorities
            ],
        },
        "runtime_surface_plan": [
            {
                "family": row.family,
                "relative_path": row.relative_path,
                "owner": row.owner,
                "decision_ids": list(row.decision_ids),
            }
            for row in model.runtime_surface_plan.surfaces
        ],
    }


def load_package_model(package_root: Path) -> PackageModel:
    return load_package_model_from_view(DirectoryPackageView(package_root))


def load_package_model_from_view(package: PackageView) -> PackageModel:
    _verify_package_view_manifest(package)
    if not package.exists("reports/package_model.json"):
        raise ValueError("typed_package_model_missing")
    document = package.read_json("reports/package_model.json")
    if not isinstance(document, dict):
        raise ValueError("typed_package_model_invalid")
    try:
        mulligan_doc = document["mulligan_plan"]
        rules = tuple(
            MulliganRuleModel(
                card_id=row["card"],
                selector_kind=row["selector_kind"],
                selector_canonical_json=_canonical_bytes(row["selector"]),
                action=row["action"],
                condition_canonical_json=_canonical_bytes(row["condition"]),
                reason=row["reason"],
                confidence=row["confidence"],
                source_claim_ids=tuple(row["source_claim_ids"]),
                claim_id=row.get("claim_id"),
            )
            for row in mulligan_doc["rules"]
        )
        mulligan = MulliganPlanModel(
            deck_name=mulligan_doc["deck_name"],
            rules=rules,
            suppressed=tuple(
                MulliganSuppressionModel(
                    card_id=row["card"], action=row["action"],
                    reason_code=row["reason"],
                    source_claim_ids=tuple(row["source_claim_ids"]),
                    claim_id=row.get("claim_id"),
                )
                for row in mulligan_doc["suppressed_rules"]
            ),
            bot_delegated=tuple(
                BotDelegationModel(**row) for row in mulligan_doc["bot_delegated"]
            ),
            merged_duplicate_rule_count=mulligan_doc["merged_duplicate_rule_count"],
        )
        global_doc = document["globalvalues_ledger"]
        globalvalues = GlobalValuesDecisionLedger(
            deck_fingerprint=global_doc["deck_fingerprint"],
            baseline_sha256=global_doc["baseline_sha256"],
            content_sha256=global_doc["content_sha256"],
            decisions=tuple(
                GlobalValueDecision(
                    deck_fingerprint=global_doc["deck_fingerprint"],
                    key=row["key"],
                    kind=GlobalValueDecisionKind(row["kind"]),
                    baseline_canonical_json=_canonical_bytes(row["baseline"]),
                    emitted_canonical_json=_canonical_bytes(row["emitted"]),
                    authority_id=row["authority_id"],
                    claim_ids=tuple(row["claim_ids"]),
                    reason=row["reason"],
                )
                for row in global_doc["decisions"]
            ),
        )
        disposition_doc = document["disposition_ledger"]
        dispositions = DispositionLedger(
            deck_fingerprint=disposition_doc["deck_fingerprint"],
            content_sha256=disposition_doc["content_sha256"],
            cards=tuple(
                CardDispositionRow(
                    deck_fingerprint=disposition_doc["deck_fingerprint"],
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
                for row in disposition_doc["cards"]
            ),
            claims=tuple(
                ClaimDispositionRow(
                    deck_fingerprint=disposition_doc["deck_fingerprint"],
                    claim_id=row["claim_id"], claim_kind=row["claim_kind"],
                    evidence_id=row["evidence_id"],
                    disposition=ClaimDisposition(row["disposition"]),
                    runtime_paths=tuple(row["runtime_paths"]),
                    reason_code=row["reason_code"],
                )
                for row in disposition_doc["claims"]
            ),
        )
        evidence_doc = document["evidence_contract"]
        evidence = LayeredEvidenceContract(
            deck_fingerprint=evidence_doc["deck_fingerprint"],
            exact_guide_authority=evidence_doc["exact_guide_authority"],
            layered_coverage_numerator=evidence_doc["layered_coverage_numerator"],
            layered_coverage_denominator=evidence_doc["layered_coverage_denominator"],
            content_sha256=evidence_doc["content_sha256"],
            authorities=tuple(
                EvidenceAuthority(
                    lane=EvidenceLane(row["lane"]),
                    authority_id=row["authority_id"],
                    source_identity=row["source_identity"],
                    as_of_date=row["as_of_date"], claim_kind=row["claim_kind"],
                    content_sha256=row["content_sha256"],
                    exact_deck_fingerprint=row["exact_deck_fingerprint"],
                    runtime_authorized=row["runtime_authorized"], reason=row["reason"],
                )
                for row in evidence_doc["authorities"]
            ),
        )
        plan = RuntimeSurfacePlan(
            surfaces=tuple(
                RuntimeSurfaceDecision(
                    family=row["family"], relative_path=row["relative_path"],
                    owner=row["owner"], decision_ids=tuple(row["decision_ids"]),
                )
                for row in document["runtime_surface_plan"]
            )
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("typed_package_model_invalid") from error
    model = PackageModel(
        deck_name=document["deck_name"], deck_fingerprint=document["deck_fingerprint"],
        mulligan_plan=mulligan, globalvalues_ledger=globalvalues,
        disposition_ledger=dispositions, evidence_contract=evidence,
        runtime_surface_plan=plan,
    )
    if _canonical_bytes(package_model_document(model)) != _canonical_bytes(document):
        raise ValueError("typed_package_model_parity_mismatch")
    try:
        persisted_mulligan_report = package.read_json("reports/mulligan_plan_report.json")
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ValueError("typed_package_report_parity_mismatch") from error
    if _canonical_bytes(persisted_mulligan_report) != _canonical_bytes(
        model.mulligan_plan.to_report()
    ):
        raise ValueError("typed_package_report_parity_mismatch")
    return model


def _verify_package_view_manifest(package: PackageView) -> None:
    manifest_path = "reports/package_manifest.json"
    if not package.exists(manifest_path):
        raise ValueError("typed_package_manifest_missing")
    try:
        manifest = package.read_json(manifest_path)
        records = manifest["artifacts"]
        expected_root = manifest["content_root_sha256"]
        if not isinstance(records, list) or not isinstance(expected_root, str):
            raise ValueError("invalid")
        persisted = tuple(
            PackageArtifact(
                relative_path=row["relative_path"],
                content=package.read_bytes(row["relative_path"]),
                size=row["size"],
                sha256=row["sha256"],
            )
            for row in records
        )
        actual_names = tuple(
            name for name in package.file_names() if name != manifest_path
        )
        persisted_names = tuple(artifact.relative_path for artifact in persisted)
        if tuple(sorted(persisted_names)) != persisted_names or persisted_names != actual_names:
            raise ValueError("invalid")
        if content_root_sha256(persisted) != expected_root:
            raise ValueError("invalid")
    except (KeyError, TypeError, ValueError, OSError, UnicodeDecodeError) as error:
        raise ValueError("typed_package_manifest_mismatch") from error


def render_package_model(model: PackageModel) -> RenderedPackage:
    from hsconfig.package_renderer import render_package_model as _render

    return _render(model)
