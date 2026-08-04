from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from hsconfig.version import __version__


MetricStatus = Literal["pass", "fail", "pending_remote", "not_applicable"]
ScorecardMode = Literal["pre_cutover", "final"]

HARD_METRIC_IDS = (
    "static_contract_safety",
    "safe_visionai_lowering",
    "testability_and_assurance",
    "semantic_disposition_closure",
    "layered_pre_run_source_coverage",
    "architecture_and_maintainability",
    "slimness_and_coherence",
    "github_repository_polish",
    "workspace_hygiene",
)

METRIC_MINIMUMS: dict[str, Decimal] = {
    "static_contract_safety": Decimal("99"),
    "safe_visionai_lowering": Decimal("99"),
    "testability_and_assurance": Decimal("98"),
    "semantic_disposition_closure": Decimal("100"),
    "layered_pre_run_source_coverage": Decimal("98"),
    "architecture_and_maintainability": Decimal("96"),
    "slimness_and_coherence": Decimal("98"),
    "github_repository_polish": Decimal("98"),
    "workspace_hygiene": Decimal("100"),
}

_METRIC_CHECK_IDS: dict[str, tuple[str, ...]] = {
    "static_contract_safety": (
        "contract_spine",
        "twelve_deck_acceptance",
        "version_consistency",
    ),
    "safe_visionai_lowering": (
        "owner_policy",
        "runtime_surface_policy",
        "lowering_precision",
        "lowering_recall",
    ),
    "testability_and_assurance": (
        "branch_coverage",
        "critical_coverage",
        "contract_mutations",
        "determinism",
        "distribution",
    ),
    "semantic_disposition_closure": (
        "deck_identity",
        "main_slots",
        "card_module_dispositions",
        "claim_dispositions",
        "globalvalues_dispositions",
    ),
    "architecture_and_maintainability": (
        "architecture_tests",
        "transaction_fault_matrix",
        "package_immutability",
    ),
    "slimness_and_coherence": (
        "distribution_contents",
        "publishable_path_scan",
    ),
    "github_repository_polish": (
        "repository_settings",
        "branch_ruleset",
        "release_tag",
        "github_release",
    ),
    "workspace_hygiene": (
        "output_inventory",
        "repository_hygiene",
        "workspace_residue",
    ),
}

ATOMIC_CHECK_OWNERS: dict[str, str] = {
    check_id: metric_id
    for metric_id in HARD_METRIC_IDS
    for check_id in _METRIC_CHECK_IDS.get(metric_id, ())
}

SEMANTIC_CARD_MODULE_COUNT = 208
SEMANTIC_CLAIM_COUNT = 316
SEMANTIC_DENOMINATOR = SEMANTIC_CARD_MODULE_COUNT + SEMANTIC_CLAIM_COUNT

_ALLOWED_EVIDENCE_KINDS = frozenset(
    {
        "completed_base_check",
        "coverage_json",
        "semantic_closure_report",
        "architecture_test",
        "repository_policy_test",
        "output_inventory",
    }
)
_SELF_SCORING_FIELDS = frozenset(
    {"metric_id", "minimum", "numerator", "denominator", "score", "status"}
)
_AUTHORITY_LANES = frozenset("ABCDE")


class Near100EvidenceError(ValueError):
    pass


def _validate_json_nesting(text: str, *, source: str) -> None:
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > 64:
                raise Near100EvidenceError(
                    f"{source} nesting exceeds safe limit of 64"
                )
        elif character in "]}" and depth:
            depth -= 1


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for key, value in pairs:
        if key in document:
            raise Near100EvidenceError(f"duplicate JSON key: {key}")
        document[key] = value
    return document


def load_json_strict(text: str, *, source: str = "JSON document") -> Any:
    _validate_json_nesting(text, source=source)
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except Near100EvidenceError:
        raise
    except json.JSONDecodeError as exc:
        raise Near100EvidenceError(f"{source} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise Near100EvidenceError(
            f"{source} nesting exceeds safe decoder limit"
        ) from exc


def _load_json_file(path: Path, *, source: str) -> Any:
    try:
        return load_json_strict(path.read_text(encoding="utf-8"), source=source)
    except (OSError, UnicodeError) as exc:
        raise Near100EvidenceError(f"cannot read {source}: {exc}") from exc


@dataclass(frozen=True, slots=True)
class ScoreMetric:
    metric_id: str
    numerator: int
    denominator: int
    score: Decimal | None
    minimum: Decimal | None
    status: MetricStatus
    evidence_paths: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    non_blocking_reasons: tuple[str, ...]
    scope: str

    def to_document(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "numerator": self.numerator,
            "denominator": self.denominator,
            "score": _decimal_text(self.score),
            "minimum": _decimal_text(self.minimum),
            "status": self.status,
            "evidence_paths": list(self.evidence_paths),
            "blocking_reasons": list(self.blocking_reasons),
            "non_blocking_reasons": list(self.non_blocking_reasons),
            "scope": self.scope,
        }


@dataclass(frozen=True, slots=True)
class Near100Scorecard:
    schema_version: int
    version: str
    metrics: tuple[ScoreMetric, ...]
    open_p0_findings: int
    open_p1_findings: int
    overall_score: Decimal
    passed: bool

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "metrics": [metric.to_document() for metric in self.metrics],
            "open_p0_findings": self.open_p0_findings,
            "open_p1_findings": self.open_p1_findings,
            "overall_score": _decimal_text(self.overall_score),
            "passed": self.passed,
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_document(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, slots=True)
class _CheckResult:
    passed: bool
    evidence_paths: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    non_blocking_reasons: tuple[str, ...]
    scope: str


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Near100EvidenceError(f"{name} must be an object")
    return value


def _sequence(value: object, name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise Near100EvidenceError(f"{name} must be an array")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise Near100EvidenceError(f"{name} must be a non-negative integer")
    return value


def _string_tuple(value: object, name: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    items = _sequence(value, name)
    if any(not isinstance(item, str) or not item.strip() for item in items):
        raise Near100EvidenceError(f"{name} must contain non-empty strings")
    normalized = tuple(item.strip() for item in items)
    if not allow_empty and not normalized:
        raise Near100EvidenceError(f"{name} must not be empty")
    if len(normalized) != len(set(normalized)):
        raise Near100EvidenceError(f"{name} must not contain duplicates")
    return normalized


def _repository_root(evidence: Mapping[str, Mapping[str, Any]]) -> Path:
    meta = _mapping(evidence.get("_meta"), "evidence._meta")
    value = meta.get("repository_root")
    if not isinstance(value, str) or not value.strip():
        raise Near100EvidenceError("evidence._meta.repository_root must be a path string")
    root = Path(value).resolve()
    if not root.is_dir():
        raise Near100EvidenceError(f"repository root does not exist: {root}")
    return root


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=text,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise Near100EvidenceError(f"repository state inspection failed: {exc}") from exc
    return completed.stdout


def _repository_identity(root: Path) -> str:
    remote = str(_git(root, "remote", "get-url", "origin")).strip()
    normalized = remote.replace("\\", "/")
    if normalized.startswith("git@github.com:"):
        normalized = normalized.removeprefix("git@github.com:")
    elif "github.com/" in normalized:
        normalized = normalized.split("github.com/", 1)[1]
    normalized = normalized.removesuffix(".git").strip("/")
    if normalized.count("/") != 1:
        raise Near100EvidenceError("repository identity cannot be derived from origin")
    return normalized


def _dirty_tree_fingerprint(root: Path) -> tuple[str, str]:
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        text=False,
    )
    diff = _git(root, "diff", "--binary", "HEAD", "--", text=False)
    untracked = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "-z",
        text=False,
    )
    if not isinstance(status, bytes):
        raise Near100EvidenceError("repository status inspection returned text")
    if not isinstance(diff, bytes):
        raise Near100EvidenceError("repository diff inspection returned text")
    if not isinstance(untracked, bytes):
        raise Near100EvidenceError("repository untracked inspection returned text")
    digest = hashlib.sha256()
    digest.update(b"status\0" + status)
    digest.update(b"diff\0" + diff)
    for encoded_path in sorted(path for path in untracked.split(b"\0") if path):
        candidate = root / encoded_path.decode("utf-8")
        try:
            candidate_stat = candidate.lstat()
        except OSError as exc:
            raise Near100EvidenceError(
                f"cannot inspect untracked repository path: {candidate}"
            ) from exc
        if not stat.S_ISREG(candidate_stat.st_mode) or _is_reparse(candidate_stat):
            raise Near100EvidenceError(
                f"untracked repository path is not a regular file: {candidate}"
            )
        digest.update(b"untracked\0" + encoded_path + b"\0" + candidate.read_bytes())
    return ("dirty" if status else "clean", digest.hexdigest())


def _validate_repository_binding(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    root: Path,
    mode: ScorecardMode,
) -> None:
    meta = _mapping(evidence.get("_meta"), "evidence._meta")
    allowed_meta_fields = {
        "producer",
        "repository_root",
        "repository_identity",
        "version",
        "commit_oid",
        "tree_oid",
        "tree_state",
        "dirty_tree_fingerprint",
        "generation_mode",
    }
    unknown_meta_fields = sorted(set(meta) - allowed_meta_fields)
    if unknown_meta_fields:
        raise Near100EvidenceError(
            f"evidence._meta contains unknown fields: {unknown_meta_fields}"
        )
    missing_meta_fields = sorted(allowed_meta_fields - set(meta))
    if missing_meta_fields:
        raise Near100EvidenceError(
            f"evidence._meta is missing required fields: {missing_meta_fields}"
        )
    expected = (
        ("producer", "hsconfig.release_gate.base_evidence", "producer mismatch"),
        ("version", __version__, "version mismatch"),
        ("repository_identity", _repository_identity(root), "repository identity mismatch"),
        ("commit_oid", str(_git(root, "rev-parse", "HEAD")).strip(), "commit OID mismatch"),
        ("tree_oid", str(_git(root, "rev-parse", "HEAD^{tree}")).strip(), "tree OID mismatch"),
        ("generation_mode", mode, "generation mode mismatch"),
    )
    for field, expected_value, message in expected:
        if meta.get(field) != expected_value:
            raise Near100EvidenceError(message)
    tree_state, fingerprint = _dirty_tree_fingerprint(root)
    if meta.get("tree_state") != tree_state:
        raise Near100EvidenceError("tree state mismatch")
    if meta.get("dirty_tree_fingerprint") != fingerprint:
        raise Near100EvidenceError("dirty-tree fingerprint mismatch")


def _is_reparse(path_stat: Any) -> bool:
    attribute = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(path_stat, "st_file_attributes", 0) & attribute)


def _secure_evidence_path(repository_root: Path, path_text: str) -> Path:
    pure = PurePosixPath(path_text)
    if (
        not path_text
        or "\\" in path_text
        or pure.is_absolute()
        or path_text != pure.as_posix()
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise Near100EvidenceError(
            f"evidence path must be a repo-relative canonical path: {path_text}"
        )
    root = repository_root.resolve()
    candidate = root
    for index, part in enumerate(pure.parts):
        candidate /= part
        try:
            candidate_stat = candidate.lstat()
        except FileNotFoundError as exc:
            raise Near100EvidenceError(
                f"evidence path does not exist: {path_text}"
            ) from exc
        except OSError as exc:
            raise Near100EvidenceError(f"cannot inspect evidence path: {path_text}") from exc
        if stat.S_ISLNK(candidate_stat.st_mode) or _is_reparse(candidate_stat):
            raise Near100EvidenceError(
                f"evidence path contains a link or reparse point: {path_text}"
            )
        final = index == len(pure.parts) - 1
        if final and not stat.S_ISREG(candidate_stat.st_mode):
            raise Near100EvidenceError(
                f"evidence path is not a regular file: {path_text}"
            )
        if final and candidate_stat.st_nlink != 1:
            raise Near100EvidenceError(
                f"evidence path must not be a hardlink: {path_text}"
            )
        if not final and not stat.S_ISDIR(candidate_stat.st_mode):
            raise Near100EvidenceError(
                f"evidence path component is not a directory: {path_text}"
            )
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise Near100EvidenceError(
            f"evidence path must be a repo-relative canonical path: {path_text}"
        )
    return candidate


def _is_scorecard_mapping(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    keys = set(value)
    return (
        {"schema_version", "version", "metrics", "overall_score", "passed"}
        <= keys
        or _SELF_SCORING_FIELDS <= keys
    )


def _contains_scorecard(
    value: object, *, top: bool = True, depth: int = 0
) -> tuple[bool, bool]:
    if depth > 64:
        raise Near100EvidenceError("evidence nesting exceeds safe inspection depth")
    if _is_scorecard_mapping(value):
        return (top, not top)
    if isinstance(value, Mapping):
        for child in value.values():
            direct, embedded = _contains_scorecard(
                child, top=False, depth=depth + 1
            )
            if direct or embedded:
                return (False, True)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            direct, embedded = _contains_scorecard(
                child, top=False, depth=depth + 1
            )
            if direct or embedded:
                return (False, True)
    elif isinstance(value, str):
        if len(value) > 1_000_000:
            raise Near100EvidenceError(
                "evidence free-text exceeds safe inspection length"
            )
        _validate_json_nesting(value, source="embedded JSON evidence")
        decoder = json.JSONDecoder(object_pairs_hook=_reject_duplicate_keys)
        attempts = 0
        for index, character in enumerate(value):
            if character not in "[{\"":
                continue
            attempts += 1
            if attempts > 512:
                raise Near100EvidenceError(
                    "evidence free-text exceeds safe JSON inspection complexity"
                )
            try:
                decoded, _ = decoder.raw_decode(value, index)
            except json.JSONDecodeError:
                continue
            except RecursionError as exc:
                raise Near100EvidenceError(
                    "embedded JSON evidence nesting exceeds safe decoder limit"
                ) from exc
            direct, embedded = _contains_scorecard(
                decoded, top=False, depth=depth + 1
            )
            if direct or embedded:
                return (False, True)
    return (False, False)


def _validate_receipt(
    path: Path,
    *,
    expected_check_id: str,
    expected_producer: str,
    expected_passed: bool | None,
) -> None:
    document = _load_json_file(path, source=f"evidence receipt {path}")
    direct, embedded = _contains_scorecard(document)
    if direct:
        raise Near100EvidenceError("self-produced scorecard cannot be base evidence")
    if embedded:
        raise Near100EvidenceError("evidence receipt contains an embedded scorecard result")
    receipt = _mapping(document, f"evidence receipt {path}")
    allowed_receipt_fields = {"schema_version", "producer", "check_id", "result"}
    unknown_receipt_fields = sorted(set(receipt) - allowed_receipt_fields)
    if unknown_receipt_fields:
        raise Near100EvidenceError(
            f"evidence receipt contains unknown fields: {unknown_receipt_fields}"
        )
    if receipt.get("schema_version") != 1:
        raise Near100EvidenceError("evidence receipt schema_version mismatch")
    if receipt.get("producer") != expected_producer:
        raise Near100EvidenceError("evidence receipt producer mismatch")
    if receipt.get("check_id") != expected_check_id:
        raise Near100EvidenceError("receipt check_id mismatch")
    result = _mapping(receipt.get("result"), "evidence receipt result")
    if set(result) != {"passed"}:
        raise Near100EvidenceError("evidence receipt result schema mismatch")
    receipt_passed = result.get("passed")
    if not isinstance(receipt_passed, bool):
        raise Near100EvidenceError("evidence receipt result.passed must be boolean")
    if expected_passed is not None and receipt_passed is not expected_passed:
        consumption = (
            "semantic obligations"
            if expected_check_id == "semantic_obligations"
            else f"atomic check {expected_check_id}"
        )
        raise Near100EvidenceError(f"receipt result mismatch for {consumption}")


def _validate_evidence_paths(
    value: object,
    name: str,
    *,
    repository_root: Path,
    expected_check_id: str,
    expected_producer: str,
    expected_passed: bool | None = None,
) -> tuple[str, ...]:
    paths = _string_tuple(value, name, allow_empty=False)
    for path_text in paths:
        resolved = _secure_evidence_path(repository_root, path_text)
        _validate_receipt(
            resolved,
            expected_check_id=expected_check_id,
            expected_producer=expected_producer,
            expected_passed=expected_passed,
        )
    return paths


def _validate_checks(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    mode: ScorecardMode,
    repository_root: Path,
) -> dict[str, _CheckResult]:
    raw_checks = _mapping(evidence.get("checks"), "evidence.checks")
    supplied = set(raw_checks)
    known = set(ATOMIC_CHECK_OWNERS)
    unknown = sorted(supplied - known)
    if unknown:
        raise Near100EvidenceError(f"unknown atomic checks: {unknown}")
    github_checks = {
        check_id
        for check_id, owner in ATOMIC_CHECK_OWNERS.items()
        if owner == "github_repository_polish"
    }
    required = known if mode == "final" else known - github_checks
    missing = sorted(required - supplied)
    if missing:
        raise Near100EvidenceError(f"missing atomic checks: {missing}")
    supplied_github = supplied & github_checks
    if mode == "pre_cutover" and supplied_github:
        raise Near100EvidenceError(
            "pre_cutover evidence must omit all GitHub checks"
        )

    checks: dict[str, _CheckResult] = {}
    for check_id in sorted(supplied):
        payload = _mapping(raw_checks[check_id], f"evidence.checks.{check_id}")
        _, embedded = _contains_scorecard(payload)
        if embedded:
            raise Near100EvidenceError(
                f"atomic check {check_id} contains an embedded scorecard result"
            )
        self_fields = sorted(_SELF_SCORING_FIELDS & set(payload))
        if self_fields:
            raise Near100EvidenceError(
                f"atomic check {check_id} contains self-scoring field(s): {self_fields}"
            )
        allowed_payload_fields = {
            "passed",
            "kind",
            "evidence_paths",
            "blocking_reasons",
            "non_blocking_reasons",
            "scope",
            "owner",
        }
        unknown_payload_fields = sorted(set(payload) - allowed_payload_fields)
        if unknown_payload_fields:
            raise Near100EvidenceError(
                f"atomic check {check_id} contains unknown fields: "
                f"{unknown_payload_fields}"
            )
        owner = payload.get("owner")
        expected_owner = ATOMIC_CHECK_OWNERS[check_id]
        if owner is not None and owner != expected_owner:
            raise Near100EvidenceError(
                f"atomic check owner mismatch for {check_id}: expected {expected_owner}"
            )
        passed = payload.get("passed")
        if not isinstance(passed, bool):
            raise Near100EvidenceError(f"evidence.checks.{check_id}.passed must be boolean")
        kind = payload.get("kind")
        if kind not in _ALLOWED_EVIDENCE_KINDS:
            raise Near100EvidenceError(
                f"evidence.checks.{check_id}.kind is not an allowed base evidence kind"
            )
        paths = _validate_evidence_paths(
            payload.get("evidence_paths"),
            f"evidence.checks.{check_id}.evidence_paths",
            repository_root=repository_root,
            expected_check_id=check_id,
            expected_producer="hsconfig.release_gate.base_check",
            expected_passed=passed,
        )
        blocking = _string_tuple(
            payload.get("blocking_reasons", []),
            f"evidence.checks.{check_id}.blocking_reasons",
        )
        non_blocking = _string_tuple(
            payload.get("non_blocking_reasons", []),
            f"evidence.checks.{check_id}.non_blocking_reasons",
        )
        if passed and blocking:
            raise Near100EvidenceError(
                f"passing atomic check {check_id} cannot have blocking reasons"
            )
        if not passed and not blocking:
            raise Near100EvidenceError(
                f"failed atomic check {check_id} must have a blocking reason"
            )
        scope = payload.get("scope")
        if scope != "PRE_RUN_CONTRACT":
            raise Near100EvidenceError(
                f"evidence.checks.{check_id}.scope must be PRE_RUN_CONTRACT"
            )
        checks[check_id] = _CheckResult(
            passed=passed,
            evidence_paths=paths,
            blocking_reasons=blocking,
            non_blocking_reasons=non_blocking,
            scope=scope,
        )
    return checks


def _semantic_rows(
    evidence: Mapping[str, Mapping[str, Any]],
    *,
    repository_root: Path,
) -> tuple[int, tuple[str, ...], tuple[str, ...], bool, bool]:
    obligations = _mapping(
        evidence.get("semantic_obligations"), "evidence.semantic_obligations"
    )
    allowed_obligation_fields = {"card_module_rows", "claim_rows"}
    unknown_obligation_fields = sorted(set(obligations) - allowed_obligation_fields)
    if unknown_obligation_fields:
        raise Near100EvidenceError(
            "evidence.semantic_obligations contains unknown fields: "
            f"{unknown_obligation_fields}"
        )
    missing_obligation_fields = sorted(allowed_obligation_fields - set(obligations))
    if missing_obligation_fields:
        raise Near100EvidenceError(
            "evidence.semantic_obligations is missing required fields: "
            f"{missing_obligation_fields}"
        )
    specifications = (
        ("card_module_rows", SEMANTIC_CARD_MODULE_COUNT, "card/module"),
        ("claim_rows", SEMANTIC_CLAIM_COUNT, "claim"),
    )
    numerator = 0
    evidence_paths: set[str] = set()
    incomplete: list[str] = []
    all_ids: list[str] = []
    completeness: list[bool] = []
    for field, expected_count, label in specifications:
        rows = _sequence(obligations.get(field), f"semantic_obligations.{field}")
        if len(rows) != expected_count:
            raise Near100EvidenceError(
                f"semantic obligations require exactly {expected_count} {label} rows"
            )
        field_complete = True
        for index, value in enumerate(rows):
            row = _mapping(value, f"semantic_obligations.{field}[{index}]")
            allowed_row_fields = {
                "obligation_id",
                "authority_lanes",
                "final_disposition",
                "evidence_paths",
            }
            unknown_row_fields = sorted(set(row) - allowed_row_fields)
            if unknown_row_fields:
                raise Near100EvidenceError(
                    f"semantic_obligations.{field}[{index}] contains unknown fields: "
                    f"{unknown_row_fields}"
                )
            missing_row_fields = sorted(allowed_row_fields - set(row))
            if missing_row_fields:
                raise Near100EvidenceError(
                    f"semantic_obligations.{field}[{index}] is missing required fields: "
                    f"{missing_row_fields}"
                )
            obligation_id = row.get("obligation_id")
            if (
                not isinstance(obligation_id, str)
                or not obligation_id
            ):
                raise Near100EvidenceError(
                    f"semantic_obligations.{field}[{index}].obligation_id must be non-empty"
                )
            all_ids.append(obligation_id)
            lanes = _string_tuple(
                row.get("authority_lanes"),
                f"semantic_obligations.{field}[{index}].authority_lanes",
            )
            if any(lane not in _AUTHORITY_LANES for lane in lanes):
                raise Near100EvidenceError(
                    f"semantic obligation {obligation_id} has an invalid authority lane"
                )
            final_disposition = row.get("final_disposition")
            if not isinstance(final_disposition, bool):
                raise Near100EvidenceError(
                    f"semantic obligation {obligation_id}.final_disposition must be boolean"
                )
            paths = _validate_evidence_paths(
                row.get("evidence_paths"),
                f"semantic_obligations.{field}[{index}].evidence_paths",
                repository_root=repository_root,
                expected_check_id="semantic_obligations",
                expected_producer="hsconfig.semantic_inventory",
                expected_passed=True,
            )
            evidence_paths.update(paths)
            if final_disposition and len(lanes) == 1:
                numerator += 1
            else:
                field_complete = False
                incomplete.append(
                    f"{obligation_id} lacks a final disposition with exactly one A-E authority"
                )
        completeness.append(field_complete)
    if len(all_ids) != len(set(all_ids)):
        raise Near100EvidenceError("semantic obligations contain duplicate obligation IDs")
    expected_card_ids, expected_claim_ids = _canonical_semantic_identities(repository_root)
    actual_card_ids = set(all_ids[:SEMANTIC_CARD_MODULE_COUNT])
    actual_claim_ids = set(all_ids[SEMANTIC_CARD_MODULE_COUNT:])
    if actual_card_ids != expected_card_ids or actual_claim_ids != expected_claim_ids:
        raise Near100EvidenceError(
            "semantic obligations do not match the canonical semantic identity set"
        )
    return (
        numerator,
        tuple(sorted(evidence_paths)),
        tuple(incomplete),
        completeness[0],
        completeness[1],
    )


def _canonical_semantic_identities(root: Path) -> tuple[set[str], set[str]]:
    inventory_path = _secure_evidence_path(
        root, "tests/fixtures/near100/current_semantic_inventory.json"
    )
    inventory = _mapping(
        _load_json_file(inventory_path, source="canonical semantic inventory"),
        "canonical semantic inventory",
    )
    decks = _sequence(inventory.get("decks"), "canonical semantic inventory.decks")
    cards: set[str] = set()
    claims: set[str] = set()
    for deck_index, value in enumerate(decks):
        deck = _mapping(value, f"canonical semantic inventory.decks[{deck_index}]")
        for field in ("main_cards", "sideboard_modules"):
            for row_value in _sequence(deck.get(field), f"canonical deck.{field}"):
                row = _mapping(row_value, f"canonical deck.{field} row")
                key = row.get("composite_card_key")
                if not isinstance(key, str) or not key:
                    raise Near100EvidenceError("canonical semantic inventory is malformed")
                cards.add(key)
        for row_value in _sequence(deck.get("claims"), "canonical deck.claims"):
            row = _mapping(row_value, "canonical deck.claim row")
            key = row.get("claim_key")
            if not isinstance(key, str) or not key:
                raise Near100EvidenceError("canonical semantic inventory is malformed")
            claims.add(key)
    if len(cards) != SEMANTIC_CARD_MODULE_COUNT or len(claims) != SEMANTIC_CLAIM_COUNT:
        raise Near100EvidenceError("canonical semantic inventory counts are invalid")
    return cards, claims


def _validate_score_metric_contract(root: Path) -> None:
    path = _secure_evidence_path(root, "tests/fixtures/near100/score_metric_contract.json")
    contract = _mapping(
        _load_json_file(path, source="score metric contract"),
        "score metric contract",
    )
    expected = {
        "metric_ids": list(HARD_METRIC_IDS),
        "minimums": [int(METRIC_MINIMUMS[item]) for item in HARD_METRIC_IDS],
        "overall_minimum": 98,
        "gameplay_quality": "not_applicable",
        "open_p0_maximum": 0,
        "open_p1_maximum": 0,
    }
    if dict(contract) != expected:
        raise Near100EvidenceError("score metric contract drift")


def _check_metric(metric_id: str, checks: Mapping[str, _CheckResult]) -> ScoreMetric:
    check_ids = _METRIC_CHECK_IDS[metric_id]
    rows = [checks[check_id] for check_id in check_ids]
    numerator = sum(row.passed for row in rows)
    denominator = len(rows)
    score = Decimal(100) * Decimal(numerator) / Decimal(denominator)
    minimum = METRIC_MINIMUMS[metric_id]
    status: MetricStatus = "pass" if score >= minimum else "fail"
    return ScoreMetric(
        metric_id=metric_id,
        numerator=numerator,
        denominator=denominator,
        score=score,
        minimum=minimum,
        status=status,
        evidence_paths=tuple(
            sorted({path for row in rows for path in row.evidence_paths})
        ),
        blocking_reasons=tuple(
            reason for row in rows for reason in row.blocking_reasons
        ),
        non_blocking_reasons=tuple(
            reason for row in rows for reason in row.non_blocking_reasons
        ),
        scope="PRE_RUN_CONTRACT",
    )


def _semantic_metric(
    numerator: int,
    evidence_paths: tuple[str, ...],
    incomplete: tuple[str, ...],
) -> ScoreMetric:
    score = Decimal(100) * Decimal(numerator) / Decimal(SEMANTIC_DENOMINATOR)
    minimum = METRIC_MINIMUMS["layered_pre_run_source_coverage"]
    status: MetricStatus = "pass" if score >= minimum else "fail"
    return ScoreMetric(
        metric_id="layered_pre_run_source_coverage",
        numerator=numerator,
        denominator=SEMANTIC_DENOMINATOR,
        score=score,
        minimum=minimum,
        status=status,
        evidence_paths=evidence_paths,
        blocking_reasons=incomplete if status == "fail" else (),
        non_blocking_reasons=incomplete if status == "pass" else (),
        scope="PRE_RUN_CONTRACT",
    )


def _github_pending_metric() -> ScoreMetric:
    return ScoreMetric(
        metric_id="github_repository_polish",
        numerator=0,
        denominator=len(_METRIC_CHECK_IDS["github_repository_polish"]),
        score=None,
        minimum=METRIC_MINIMUMS["github_repository_polish"],
        status="pending_remote",
        evidence_paths=(),
        blocking_reasons=(),
        non_blocking_reasons=("excluded_from_pre_cutover_overall",),
        scope="PRE_RUN_CONTRACT",
    )


def _findings(evidence: Mapping[str, Mapping[str, Any]]) -> tuple[int, int]:
    findings = _mapping(evidence.get("findings"), "evidence.findings")
    allowed = {"open_p0", "open_p1"}
    unknown = sorted(set(findings) - allowed)
    if unknown:
        raise Near100EvidenceError(f"unknown findings fields: {unknown}")
    return (
        _non_negative_int(findings.get("open_p0"), "findings.open_p0"),
        _non_negative_int(findings.get("open_p1"), "findings.open_p1"),
    )


def build_near100_scorecard(
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    mode: ScorecardMode,
) -> Near100Scorecard:
    if mode not in ("pre_cutover", "final"):
        raise Near100EvidenceError(f"unsupported scorecard mode: {mode}")
    if not isinstance(evidence, Mapping):
        raise Near100EvidenceError("evidence must be an object")
    reserved_inputs = sorted(
        key
        for key in evidence
        if key
        in {
            *_SELF_SCORING_FIELDS,
            "metrics",
            "near100_scorecard",
            "overall_pre_run",
            "overall_score",
            "passed",
        }
    )
    if reserved_inputs:
        raise Near100EvidenceError(
            f"scorecard cannot consume scorecard result fields: {reserved_inputs}"
        )
    direct_scorecard, embedded_scorecard = _contains_scorecard(evidence)
    if direct_scorecard or embedded_scorecard:
        raise Near100EvidenceError(
            "base evidence contains an embedded scorecard result"
        )
    root = _repository_root(evidence)
    _validate_repository_binding(evidence, root=root, mode=mode)
    _validate_score_metric_contract(root)
    checks = _validate_checks(evidence, mode=mode, repository_root=root)
    (
        semantic_numerator,
        semantic_paths,
        semantic_incomplete,
        card_modules_complete,
        claims_complete,
    ) = _semantic_rows(evidence, repository_root=root)
    open_p0, open_p1 = _findings(evidence)

    metrics: list[ScoreMetric] = []
    for metric_id in HARD_METRIC_IDS:
        if metric_id == "layered_pre_run_source_coverage":
            metric = _semantic_metric(
                semantic_numerator, semantic_paths, semantic_incomplete
            )
        elif metric_id == "github_repository_polish" and mode == "pre_cutover":
            metric = _github_pending_metric()
        else:
            metric = _check_metric(metric_id, checks)
            if metric_id == "semantic_disposition_closure" and semantic_incomplete:
                derived_failures = sum(
                    (
                        not card_modules_complete
                        and checks["card_module_dispositions"].passed,
                        not claims_complete and checks["claim_dispositions"].passed,
                    )
                )
                numerator = metric.numerator - derived_failures
                score = Decimal(100) * Decimal(numerator) / Decimal(metric.denominator)
                metric = ScoreMetric(
                    metric_id=metric.metric_id,
                    numerator=numerator,
                    denominator=metric.denominator,
                    score=score,
                    minimum=metric.minimum,
                    status="fail",
                    evidence_paths=tuple(
                        sorted(set(metric.evidence_paths) | set(semantic_paths))
                    ),
                    blocking_reasons=tuple(
                        (*metric.blocking_reasons, *semantic_incomplete)
                    ),
                    non_blocking_reasons=metric.non_blocking_reasons,
                    scope=metric.scope,
                )
        metrics.append(metric)

    included = [
        metric
        for metric in metrics
        if not (
            mode == "pre_cutover"
            and metric.metric_id == "github_repository_polish"
        )
    ]
    overall_numerator = sum(metric.numerator for metric in included)
    overall_denominator = sum(metric.denominator for metric in included)
    overall_score = (
        Decimal(100) * Decimal(overall_numerator) / Decimal(overall_denominator)
    )
    hard_metrics_pass = all(metric.status == "pass" for metric in included)
    overall_status: MetricStatus = (
        "pass"
        if overall_score >= Decimal("98") and hard_metrics_pass
        else "fail"
    )
    overall_non_blocking = (
        ("github_repository_polish_pending_remote",)
        if mode == "pre_cutover"
        else ()
    )
    metrics.append(
        ScoreMetric(
            metric_id="overall_pre_run",
            numerator=overall_numerator,
            denominator=overall_denominator,
            score=overall_score,
            minimum=Decimal("98"),
            status=overall_status,
            evidence_paths=tuple(
                sorted({path for metric in included for path in metric.evidence_paths})
            ),
            blocking_reasons=tuple(
                reason
                for metric in included
                if metric.status == "fail"
                for reason in (
                    metric.blocking_reasons
                    or (f"hard metric failed: {metric.metric_id}",)
                )
            ),
            non_blocking_reasons=overall_non_blocking,
            scope="PRE_RUN_CONTRACT",
        )
    )
    metrics.append(
        ScoreMetric(
            metric_id="gameplay_quality",
            numerator=0,
            denominator=0,
            score=None,
            minimum=None,
            status="not_applicable",
            evidence_paths=(),
            blocking_reasons=(),
            non_blocking_reasons=(),
            scope="OUT_OF_SCOPE_ASSUMED_EXTERNAL",
        )
    )
    passed = (
        mode == "final"
        and hard_metrics_pass
        and overall_status == "pass"
        and open_p0 == 0
        and open_p1 == 0
    )
    return Near100Scorecard(
        schema_version=1,
        version=__version__,
        metrics=tuple(metrics),
        open_p0_findings=open_p0,
        open_p1_findings=open_p1,
        overall_score=overall_score,
        passed=passed,
    )


__all__ = (
    "ATOMIC_CHECK_OWNERS",
    "HARD_METRIC_IDS",
    "METRIC_MINIMUMS",
    "Near100EvidenceError",
    "Near100Scorecard",
    "ScoreMetric",
    "build_near100_scorecard",
    "load_json_strict",
)
