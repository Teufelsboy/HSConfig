from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

import pytest

import hsconfig.near100_scorecard as scorecard_module
from hsconfig.near100_scorecard import (
    ATOMIC_CHECK_OWNERS,
    HARD_METRIC_IDS,
    Near100EvidenceError,
    build_near100_scorecard,
    load_json_strict,
)
from hsconfig.semantic_inventory import canonical_semantic_claim


EXPECTED_HARD_METRICS = (
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


def _git(root: Path, *args: str, text: bool = True) -> str | bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=text,
    )
    return completed.stdout


def _dirty_tree_fingerprint(root: Path) -> str:
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
    digest = hashlib.sha256()
    digest.update(b"status\0" + status)
    digest.update(b"diff\0" + diff)
    for encoded_path in sorted(path for path in untracked.split(b"\0") if path):
        path = root / encoded_path.decode("utf-8")
        digest.update(b"untracked\0" + encoded_path + b"\0" + path.read_bytes())
    return digest.hexdigest()


def _initialize_repository(root: Path) -> None:
    if (root / ".git").is_dir():
        return
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "tests@example.invalid")
    _git(root, "config", "user.name", "HSConfig Tests")
    _git(root, "remote", "add", "origin", "https://github.com/Teufelsboy/HSConfig.git")
    (root / ".gitignore").write_text(".near100/\n", encoding="utf-8")
    (root / "outputs").mkdir()
    (root / "outputs" / ".gitkeep").write_text("", encoding="utf-8")
    fixture_root = Path(__file__).parent / "fixtures" / "near100"
    destination = root / "tests" / "fixtures" / "near100"
    destination.mkdir(parents=True)
    shutil.copyfile(
        fixture_root / "current_semantic_inventory.json",
        destination / "current_semantic_inventory.json",
    )
    shutil.copyfile(
        fixture_root / "score_metric_contract.json",
        destination / "score_metric_contract.json",
    )
    catalog = root / "docs" / "operator" / "audited-deck-catalog.json"
    catalog.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(__file__).parents[1] / "docs" / "operator" / "audited-deck-catalog.json",
        catalog,
    )
    receipt_root = root / "receipts"
    receipt_root.mkdir()
    for check_id in ATOMIC_CHECK_OWNERS:
        (receipt_root / f"{check_id}.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "producer": "hsconfig.release_gate.base_check",
                    "check_id": check_id,
                    "result": {"passed": True},
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    (receipt_root / "semantic_obligations.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "producer": "hsconfig.semantic_inventory",
                "check_id": "semantic_obligations",
                "result": {"passed": True},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")


def _complete_evidence(
    tmp_path: Path, *, mode: str = "final"
) -> dict[str, Any]:
    _initialize_repository(tmp_path)
    inventory = json.loads(
        (
            tmp_path
            / "tests"
            / "fixtures"
            / "near100"
            / "current_semantic_inventory.json"
        ).read_text(encoding="utf-8")
    )
    checks: dict[str, Any] = {}
    for check_id, owner in ATOMIC_CHECK_OWNERS.items():
        checks[check_id] = {
            "passed": True,
            "kind": (
                "coverage_json"
                if check_id in {"branch_coverage", "critical_coverage"}
                else "completed_base_check"
            ),
            "evidence_paths": [f"receipts/{check_id}.json"],
            "blocking_reasons": [],
            "non_blocking_reasons": [],
            "scope": "PRE_RUN_CONTRACT",
            "owner": owner,
        }
    card_rows = []
    claim_rows = []
    for deck in inventory["decks"]:
        for row in (*deck["main_cards"], *deck["sideboard_modules"]):
            card_rows.append(
                {
                    "obligation_id": row["composite_card_key"],
                    "authority_lanes": ["A"],
                    "final_disposition": True,
                    "evidence_paths": ["receipts/semantic_obligations.json"],
                }
            )
    for row in inventory["semantic_claims"]:
        claim_rows.append(
            {
                "obligation_id": row["claim_key"],
                "authority_lanes": ["E"],
                "final_disposition": True,
                "evidence_paths": ["receipts/semantic_obligations.json"],
            }
        )
    status = _git(
        tmp_path,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        text=False,
    )
    return {
        "_meta": {
            "producer": "hsconfig.release_gate.base_evidence",
            "repository_root": str(tmp_path),
            "repository_identity": "Teufelsboy/HSConfig",
            "version": "1.0.0",
            "commit_oid": _git(tmp_path, "rev-parse", "HEAD").strip(),
            "tree_oid": _git(tmp_path, "rev-parse", "HEAD^{tree}").strip(),
            "tree_state": "dirty" if status else "clean",
            "dirty_tree_fingerprint": _dirty_tree_fingerprint(tmp_path),
            "generation_mode": mode,
        },
        "checks": checks,
        "semantic_obligations": {
            "card_module_rows": card_rows,
            "claim_rows": claim_rows,
        },
        "findings": {"open_p0": 0, "open_p1": 0},
    }


def _embedded_bundle(tmp_path: Path, *, mode: str = "final") -> dict[str, Any]:
    evidence = _complete_evidence(tmp_path, mode=mode)
    if mode == "final":
        evidence["_meta"].update(
            {
                "transaction_id": "a" * 32,
                "observed_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
        )
    receipt_ids = {
        path
        for payload in evidence["checks"].values()
        for path in payload["evidence_paths"]
    }
    receipt_ids.update(
        path
        for field in ("card_module_rows", "claim_rows")
        for row in evidence["semantic_obligations"][field]
        for path in row["evidence_paths"]
    )
    base_binding_fields = (
        "repository_identity",
        "commit_oid",
        "tree_oid",
        "tree_state",
        "dirty_tree_fingerprint",
        "generation_mode",
    )
    receipts = {
        receipt_id: json.loads((tmp_path / receipt_id).read_text(encoding="utf-8"))
        for receipt_id in sorted(receipt_ids)
    }
    for receipt_id, receipt in receipts.items():
        receipt["schema_version"] = 2
        receipt["binding"] = {
            field: evidence["_meta"][field] for field in base_binding_fields
        }
        check_id = receipt_id.removeprefix("receipts/").removesuffix(".json")
        if (
            mode == "final"
            and ATOMIC_CHECK_OWNERS.get(check_id) == "github_repository_polish"
        ):
            receipt["binding"].update(
                {
                    "transaction_id": evidence["_meta"]["transaction_id"],
                    "observed_at": evidence["_meta"]["observed_at"],
                }
            )
    return {
        "schema_version": 1,
        "evidence": evidence,
        "receipts": receipts,
    }


def _refresh_repository_state(evidence: dict[str, Any], root: Path) -> None:
    status = _git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        text=False,
    )
    evidence["_meta"].update(
        {
            "commit_oid": _git(root, "rev-parse", "HEAD").strip(),
            "tree_oid": _git(root, "rev-parse", "HEAD^{tree}").strip(),
            "tree_state": "dirty" if status else "clean",
            "dirty_tree_fingerprint": _dirty_tree_fingerprint(root),
        }
    )


def _refresh_embedded_receipt_bindings(bundle: dict[str, Any]) -> None:
    meta = bundle["evidence"]["_meta"]
    base_fields = (
        "repository_identity",
        "commit_oid",
        "tree_oid",
        "tree_state",
        "dirty_tree_fingerprint",
        "generation_mode",
    )
    for receipt_id, receipt in bundle["receipts"].items():
        receipt["binding"] = {field: meta[field] for field in base_fields}
        check_id = receipt_id.removeprefix("receipts/").removesuffix(".json")
        if ATOMIC_CHECK_OWNERS.get(check_id) == "github_repository_polish":
            receipt["binding"].update(
                {
                    "transaction_id": meta["transaction_id"],
                    "observed_at": meta["observed_at"],
                }
            )


def _set_check_result(
    evidence: dict[str, Any], root: Path, check_id: str, *, passed: bool
) -> None:
    evidence["checks"][check_id]["passed"] = passed
    receipt_path = root / evidence["checks"][check_id]["evidence_paths"][0]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["result"]["passed"] = passed
    receipt_path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    _refresh_repository_state(evidence, root)


def _metric(scorecard: object, metric_id: str) -> object:
    return next(metric for metric in scorecard.metrics if metric.metric_id == metric_id)


def _expect_evidence_error(
    label: str,
    pattern: str,
    operation: Any,
) -> None:
    try:
        operation()
    except Near100EvidenceError as exc:
        assert re.search(pattern, str(exc)), (
            f"{label}: expected {pattern!r}, received {str(exc)!r}"
        )
    else:
        pytest.fail(f"{label}: expected Near100EvidenceError")


def test_final_truth_table_uses_exact_ids_minimums_and_decimal_scores(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)

    scorecard = build_near100_scorecard(evidence=evidence, mode="final")

    assert HARD_METRIC_IDS == EXPECTED_HARD_METRICS
    assert tuple(metric.metric_id for metric in scorecard.metrics) == (
        *EXPECTED_HARD_METRICS,
        "overall_pre_run",
        "gameplay_quality",
    )
    assert tuple(metric.minimum for metric in scorecard.metrics[:-2]) == (
        Decimal("99"),
        Decimal("99"),
        Decimal("98"),
        Decimal("100"),
        Decimal("98"),
        Decimal("96"),
        Decimal("98"),
        Decimal("98"),
        Decimal("100"),
    )
    assert all(metric.status == "pass" for metric in scorecard.metrics[:-1])
    assert scorecard.overall_score == Decimal("100")
    assert scorecard.passed is True


def test_metric_score_is_computed_from_owned_checks_with_decimal_not_float(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    _set_check_result(evidence, tmp_path, "version_consistency", passed=False)
    evidence["checks"]["version_consistency"]["blocking_reasons"] = [
        "version mismatch"
    ]

    metric = _metric(
        build_near100_scorecard(evidence=evidence, mode="final"),
        "static_contract_safety",
    )

    assert metric.numerator == 2
    assert metric.denominator == 3
    assert metric.score == Decimal(200) / Decimal(3)
    assert isinstance(metric.score, Decimal)
    assert metric.status == "fail"
    assert metric.blocking_reasons == ("version mismatch",)


def test_layered_source_metric_has_fixed_208_plus_316_denominator(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["semantic_obligations"]["card_module_rows"][0][
        "final_disposition"
    ] = False
    evidence["semantic_obligations"]["claim_rows"][0]["authority_lanes"] = [
        "A",
        "B",
    ]

    metric = _metric(
        build_near100_scorecard(evidence=evidence, mode="final"),
        "layered_pre_run_source_coverage",
    )

    assert metric.numerator == 522
    assert metric.denominator == 524
    assert metric.score == Decimal(52200) / Decimal(524)
    assert metric.status == "pass"
    assert metric.scope == "PRE_RUN_CONTRACT"
    assert metric.blocking_reasons == ()
    assert len(metric.non_blocking_reasons) == 2


def test_semantic_closure_cannot_be_gamed_by_contradictory_passing_checks(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["semantic_obligations"]["card_module_rows"][0][
        "final_disposition"
    ] = False
    evidence["semantic_obligations"]["claim_rows"][0]["authority_lanes"] = []

    metric = _metric(
        build_near100_scorecard(evidence=evidence, mode="final"),
        "semantic_disposition_closure",
    )

    assert metric.numerator == 3
    assert metric.denominator == 5
    assert metric.score == Decimal("60")
    assert metric.status == "fail"
    assert len(metric.blocking_reasons) == 2


def test_pre_cutover_excludes_github_checks_and_can_never_be_final_passed(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path, mode="pre_cutover")
    for check_id, owner in tuple(ATOMIC_CHECK_OWNERS.items()):
        if owner == "github_repository_polish":
            del evidence["checks"][check_id]

    scorecard = build_near100_scorecard(evidence=evidence, mode="pre_cutover")

    github = _metric(scorecard, "github_repository_polish")
    overall = _metric(scorecard, "overall_pre_run")
    assert github.status == "pending_remote"
    assert github.score is None
    assert github.numerator == 0
    assert github.denominator == 4
    assert "excluded_from_pre_cutover_overall" in github.non_blocking_reasons
    assert overall.status == "pass"
    assert overall.score == Decimal("100")
    assert scorecard.passed is False


def test_gameplay_is_explicitly_not_applicable_and_never_scored(tmp_path: Path) -> None:
    gameplay = _metric(
        build_near100_scorecard(evidence=_complete_evidence(tmp_path), mode="final"),
        "gameplay_quality",
    )

    assert gameplay.numerator == 0
    assert gameplay.denominator == 0
    assert gameplay.score is None
    assert gameplay.minimum is None
    assert gameplay.status == "not_applicable"
    assert gameplay.scope == "OUT_OF_SCOPE_ASSUMED_EXTERNAL"


@pytest.mark.parametrize("finding", ["open_p0", "open_p1"])
def test_open_p0_or_p1_finding_blocks_an_otherwise_passing_card(
    tmp_path: Path, finding: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["findings"][finding] = 1

    scorecard = build_near100_scorecard(evidence=evidence, mode="final")

    assert scorecard.overall_score == Decimal("100")
    assert scorecard.passed is False
    assert getattr(scorecard, f"{finding}_findings") == 1


def test_failed_hard_metric_blocks_even_when_overall_exceeds_minimum(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    _set_check_result(evidence, tmp_path, "package_immutability", passed=False)
    evidence["checks"]["package_immutability"]["blocking_reasons"] = [
        "immutability check failed"
    ]

    scorecard = build_near100_scorecard(evidence=evidence, mode="final")

    assert scorecard.overall_score >= Decimal("98")
    assert _metric(scorecard, "architecture_and_maintainability").status == "fail"
    overall = _metric(scorecard, "overall_pre_run")
    assert overall.status == "fail"
    assert overall.blocking_reasons == ("immutability check failed",)
    assert scorecard.passed is False


@pytest.mark.parametrize(
    ("unsafe_path", "expected"),
    [
        ("../outside.json", "repo-relative canonical path"),
        ("receipts\\contract_spine.json", "repo-relative canonical path"),
    ],
)
def test_evidence_paths_reject_traversal_and_alternative_separators(
    tmp_path: Path, unsafe_path: str, expected: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    (tmp_path.parent / "outside.json").write_text("{}", encoding="utf-8")
    evidence["checks"]["contract_spine"]["evidence_paths"] = [unsafe_path]

    with pytest.raises(Near100EvidenceError, match=expected):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_evidence_paths_reject_absolute_paths_even_inside_repository(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["checks"]["contract_spine"]["evidence_paths"] = [
        str(tmp_path / "receipts" / "contract_spine.json")
    ]

    with pytest.raises(Near100EvidenceError, match="repo-relative canonical path"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_evidence_paths_reject_symlink_aliases(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    alias = tmp_path / ".near100" / "alias.json"
    alias.parent.mkdir(exist_ok=True)
    try:
        alias.symlink_to(tmp_path / "receipts" / "contract_spine.json")
    except OSError as exc:
        pytest.skip(f"platform does not permit test symlink: {exc}")
    evidence["checks"]["contract_spine"]["evidence_paths"] = [
        ".near100/alias.json"
    ]

    with pytest.raises(Near100EvidenceError, match="link or reparse point"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_evidence_paths_reject_hardlink_aliases(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    external = tmp_path.parent / "external-receipt.json"
    external.write_text(
        (tmp_path / "receipts" / "contract_spine.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    alias = tmp_path / ".near100" / "hardlinked-receipt.json"
    alias.parent.mkdir(exist_ok=True)
    try:
        os.link(external, alias)
    except OSError as exc:
        pytest.skip(f"platform does not permit test hardlink: {exc}")
    evidence["checks"]["contract_spine"]["evidence_paths"] = [
        ".near100/hardlinked-receipt.json"
    ]

    with pytest.raises(Near100EvidenceError, match="hardlink"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_renamed_scorecard_payload_cannot_be_reused_as_base_evidence(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    disguised = tmp_path / ".near100" / "ordinary-receipt.json"
    disguised.parent.mkdir(exist_ok=True)
    disguised.write_text(scorecard.to_json(), encoding="utf-8")
    evidence["checks"]["contract_spine"]["evidence_paths"] = [
        ".near100/ordinary-receipt.json"
    ]

    with pytest.raises(Near100EvidenceError, match="self-produced scorecard"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_release_gate_receipt_cannot_embed_a_scorecard_result(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    disguised = tmp_path / ".near100" / "release-check.json"
    disguised.parent.mkdir(exist_ok=True)
    disguised.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "producer": "hsconfig.release_gate.base_check",
                "check_id": "contract_spine",
                "result": {"passed": True},
                "details": {"renamed_result": scorecard.to_document()},
            }
        ),
        encoding="utf-8",
    )
    evidence["checks"]["contract_spine"]["evidence_paths"] = [
        ".near100/release-check.json"
    ]

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_atomic_check_payload_cannot_embed_a_scorecard_result(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    evidence["checks"]["contract_spine"]["details"] = scorecard.to_document()

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_receipt_cannot_embed_a_json_serialized_scorecard_result(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    receipt_path = tmp_path / "receipts" / "contract_spine.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["details"] = {"captured_stdout": scorecard.to_json()}
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_receipt_provenance_must_match_the_consuming_atomic_check(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["checks"]["version_consistency"]["evidence_paths"] = [
        "receipts/contract_spine.json"
    ]

    with pytest.raises(Near100EvidenceError, match="receipt check_id mismatch"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize(("check_passed", "receipt_passed"), [(False, True), (True, False)])
def test_receipt_result_must_match_consumed_atomic_check_status(
    tmp_path: Path, check_passed: bool, receipt_passed: bool
) -> None:
    evidence = _complete_evidence(tmp_path)
    check = evidence["checks"]["contract_spine"]
    check["passed"] = check_passed
    check["blocking_reasons"] = [] if check_passed else ["contract failure"]
    receipt_path = tmp_path / "receipts" / "contract_spine.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["result"]["passed"] = receipt_passed
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="receipt result mismatch") as caught:
        build_near100_scorecard(evidence=evidence, mode="final")
    assert "atomic check contract_spine" in str(caught.value)


def test_multiple_receipts_must_each_match_consumed_atomic_check_status(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    second = tmp_path / "receipts" / "contract_spine-second.json"
    second.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "producer": "hsconfig.release_gate.base_check",
                "check_id": "contract_spine",
                "result": {"passed": False},
            }
        ),
        encoding="utf-8",
    )
    _git(tmp_path, "add", str(second.relative_to(tmp_path)))
    _git(tmp_path, "commit", "-q", "-m", "second receipt")
    evidence["checks"]["contract_spine"]["evidence_paths"].append(
        "receipts/contract_spine-second.json"
    )
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="receipt result mismatch") as caught:
        build_near100_scorecard(evidence=evidence, mode="final")
    assert "atomic check contract_spine" in str(caught.value)


def test_pre_cutover_rejects_supplied_github_checks_instead_of_ignoring_them(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path, mode="pre_cutover")

    with pytest.raises(Near100EvidenceError, match="must omit all GitHub checks"):
        build_near100_scorecard(evidence=evidence, mode="pre_cutover")


@pytest.mark.parametrize(
    "mutation",
    [
        "fabricated",
        "whitespace",
        "swapped_classes",
    ],
)
def test_semantic_identity_sets_must_match_the_canonical_inventory_exactly(
    tmp_path: Path, mutation: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    card_rows = evidence["semantic_obligations"]["card_module_rows"]
    claim_rows = evidence["semantic_obligations"]["claim_rows"]
    if mutation == "fabricated":
        card_rows[0]["obligation_id"] = "fabricated-card-identity"
    elif mutation == "whitespace":
        card_rows[0]["obligation_id"] = f" {card_rows[0]['obligation_id']} "
    else:
        card_rows[0]["obligation_id"], claim_rows[0]["obligation_id"] = (
            claim_rows[0]["obligation_id"],
            card_rows[0]["obligation_id"],
        )

    with pytest.raises(Near100EvidenceError, match="canonical semantic identity set"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_scorecard_rejects_rehashed_semantic_inventory_substitution(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    inventory_path = (
        tmp_path / "tests" / "fixtures" / "near100" / "current_semantic_inventory.json"
    )
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    claim = inventory["semantic_claims"][0]
    previous = claim["claim_key"]
    claim["evidence_text_short"] += " changed"
    claim.pop("claim_key")
    inventory["semantic_claims"][0] = canonical_semantic_claim(claim)
    replacement = inventory["semantic_claims"][0]["claim_key"]
    content = {
        key: value
        for key, value in inventory.items()
        if key != "canonical_content_sha256"
    }
    inventory["canonical_content_sha256"] = hashlib.sha256(
        json.dumps(content, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    claim_rows = evidence["semantic_obligations"]["claim_rows"]
    matching = next(row for row in claim_rows if row["obligation_id"] == previous)
    matching["obligation_id"] = replacement
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="canonical semantic inventory is invalid"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_semantic_receipt_must_record_a_successful_result(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    receipt_path = tmp_path / "receipts" / "semantic_obligations.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["result"]["passed"] = False
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="receipt result mismatch") as caught:
        build_near100_scorecard(evidence=evidence, mode="final")
    assert "semantic obligations" in str(caught.value)


def test_every_semantic_receipt_must_record_a_successful_result(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    extra_path = tmp_path / ".near100" / "semantic-second.json"
    extra_path.parent.mkdir(exist_ok=True)
    extra_receipt = {
        "schema_version": 1,
        "producer": "hsconfig.semantic_inventory",
        "check_id": "semantic_obligations",
        "result": {"passed": True},
    }
    extra_path.write_text(json.dumps(extra_receipt), encoding="utf-8")
    evidence["semantic_obligations"]["card_module_rows"][0][
        "evidence_paths"
    ].append(".near100/semantic-second.json")

    assert build_near100_scorecard(evidence=evidence, mode="final").passed is True

    extra_receipt["result"]["passed"] = False
    extra_path.write_text(json.dumps(extra_receipt), encoding="utf-8")
    with pytest.raises(Near100EvidenceError, match="receipt result mismatch"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize(
    "location",
    ["meta_mapping", "meta_string", "semantic_wrapper", "card_row", "claim_row"],
)
def test_complete_evidence_bundle_rejects_embedded_scorecards_everywhere(
    tmp_path: Path, location: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    if location == "meta_mapping":
        evidence["_meta"]["details"] = scorecard.to_document()
    elif location == "meta_string":
        evidence["_meta"]["captured_stdout"] = scorecard.to_json()
    elif location == "semantic_wrapper":
        evidence["semantic_obligations"]["details"] = [
            {"wrapper": [scorecard.to_document()]}
        ]
    elif location == "card_row":
        evidence["semantic_obligations"]["card_module_rows"][0]["details"] = {
            "result": scorecard.to_document()
        }
    else:
        evidence["semantic_obligations"]["claim_rows"][0]["details"] = [
            {"captured_stdout": scorecard.to_json()}
        ]

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize("reason_field", ["blocking_reasons", "non_blocking_reasons"])
def test_reason_text_cannot_contain_a_prefixed_serialized_scorecard(
    tmp_path: Path, reason_field: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    if reason_field == "blocking_reasons":
        _set_check_result(evidence, tmp_path, "contract_spine", passed=False)
    evidence["checks"]["contract_spine"][reason_field] = [
        f"captured release output: {scorecard.to_json()}"
    ]

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_reason_text_cannot_contain_a_multiply_json_encoded_scorecard(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    encoded = build_near100_scorecard(evidence=evidence, mode="final").to_json()
    for _ in range(3):
        encoded = json.dumps(encoded)
    evidence["checks"]["contract_spine"]["non_blocking_reasons"] = [encoded]

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_unknown_top_level_text_cannot_hide_a_prefixed_scorecard(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    scorecard = build_near100_scorecard(evidence=evidence, mode="final")
    evidence["diagnostic_capture"] = f"tool output follows: {scorecard.to_json()}"

    with pytest.raises(Near100EvidenceError, match="embedded scorecard result"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize(
    "document",
    [
        "[" * 1200 + "0" + "]" * 1200,
        '{"nested":' * 1200 + "0" + "}" * 1200,
    ],
    ids=["deep_arrays", "deep_objects"],
)
def test_strict_json_loader_translates_excessive_nesting_to_evidence_error(
    document: str,
) -> None:
    with pytest.raises(Near100EvidenceError, match="nesting exceeds safe limit"):
        load_json_strict(document, source="deep evidence")


def test_builder_translates_deep_json_fragment_to_evidence_error(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["checks"]["contract_spine"]["non_blocking_reasons"] = ["[" * 2000]

    with pytest.raises(Near100EvidenceError, match="nesting exceeds safe limit"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_builder_rejects_deep_python_object_with_public_evidence_error(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)
    nested: dict[str, Any] = {"leaf": "plain"}
    for _ in range(200):
        nested = {"nested": nested}
    evidence["diagnostic_capture"] = nested

    with pytest.raises(Near100EvidenceError, match="safe inspection depth"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize(
    "document",
    [
        "[" * 1200 + "0" + "]" * 1200,
        '{"nested":' * 1200 + "0" + "}" * 1200,
    ],
    ids=["deep_arrays", "deep_objects"],
)
def test_cli_emits_one_machine_readable_failure_for_excessive_json_nesting(
    tmp_path: Path, document: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence_path = tmp_path / ".near100" / "deep-evidence.json"
    evidence_path.parent.mkdir(exist_ok=True)
    evidence_path.write_text(document, encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            evidence["_meta"]["repository_root"],
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence",
            str(evidence_path),
            "--mode",
            "final",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    lines = completed.stdout.splitlines()
    assert completed.returncode == 2
    assert len(lines) == 1
    assert json.loads(lines[0])["passed"] is False
    assert "nesting exceeds safe limit" in lines[0]
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize("location", ["meta", "semantic_wrapper", "card_row", "claim_row"])
def test_meta_and_semantic_schemas_reject_unknown_fields(
    tmp_path: Path, location: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    if location == "meta":
        evidence["_meta"]["unexpected"] = "plain"
    elif location == "semantic_wrapper":
        evidence["semantic_obligations"]["unexpected"] = "plain"
    elif location == "card_row":
        evidence["semantic_obligations"]["card_module_rows"][0][
            "unexpected"
        ] = "plain"
    else:
        evidence["semantic_obligations"]["claim_rows"][0]["unexpected"] = "plain"

    with pytest.raises(Near100EvidenceError, match="unknown fields"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("version", "0.0.0", "version mismatch"),
        ("commit_oid", "0" * 40, "commit OID mismatch"),
        ("tree_oid", "f" * 40, "tree OID mismatch"),
        ("repository_identity", "SomeoneElse/HSConfig", "repository identity mismatch"),
        ("dirty_tree_fingerprint", "a" * 64, "dirty-tree fingerprint mismatch"),
    ],
)
def test_stale_or_replayed_evidence_metadata_is_rejected(
    tmp_path: Path, field: str, value: str, expected: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["_meta"][field] = value

    with pytest.raises(Near100EvidenceError, match=expected):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_evidence_generation_mode_must_match_requested_mode(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path, mode="pre_cutover")

    with pytest.raises(Near100EvidenceError, match="generation mode mismatch"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_repository_change_after_evidence_generation_is_rejected(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    (tmp_path / "outputs" / ".gitkeep").write_text("changed", encoding="utf-8")

    with pytest.raises(Near100EvidenceError, match="tree state mismatch"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_score_metric_contract_drift_is_rejected(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    contract_path = (
        tmp_path / "tests" / "fixtures" / "near100" / "score_metric_contract.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["minimums"][0] = 1
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    _refresh_repository_state(evidence, tmp_path)

    with pytest.raises(Near100EvidenceError, match="score metric contract drift"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_missing_or_extra_atomic_check_is_rejected(tmp_path: Path) -> None:
    missing = _complete_evidence(tmp_path)
    del missing["checks"]["contract_spine"]
    with pytest.raises(Near100EvidenceError, match="missing atomic checks"):
        build_near100_scorecard(evidence=missing, mode="final")

    extra = _complete_evidence(tmp_path)
    extra["checks"]["scorecard_says_pass"] = dict(
        extra["checks"]["contract_spine"]
    )
    with pytest.raises(Near100EvidenceError, match="unknown atomic checks"):
        build_near100_scorecard(evidence=extra, mode="final")


def test_atomic_owner_is_fixed_and_cannot_be_reassigned(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["checks"]["contract_spine"]["owner"] = "workspace_hygiene"

    with pytest.raises(Near100EvidenceError, match="atomic check owner mismatch"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize("reserved", ["score", "status", "numerator", "denominator"])
def test_metric_cannot_consume_or_assert_its_own_result(
    tmp_path: Path, reserved: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence["checks"]["contract_spine"][reserved] = 100

    with pytest.raises(Near100EvidenceError, match="self-scoring field"):
        build_near100_scorecard(evidence=evidence, mode="final")


@pytest.mark.parametrize("reserved", ["overall_score", "metrics", "passed", "status"])
def test_top_level_evidence_cannot_embed_a_prior_scorecard_result(
    tmp_path: Path, reserved: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    evidence[reserved] = 100

    with pytest.raises(Near100EvidenceError, match="scorecard result fields"):
        build_near100_scorecard(evidence=evidence, mode="final")


def test_missing_evidence_path_is_rejected(tmp_path: Path) -> None:
    missing = _complete_evidence(tmp_path)
    missing["checks"]["contract_spine"]["evidence_paths"] = ["missing.json"]
    with pytest.raises(Near100EvidenceError, match="evidence path does not exist"):
        build_near100_scorecard(evidence=missing, mode="final")


def test_semantic_denominators_and_duplicate_ids_are_fail_closed(tmp_path: Path) -> None:
    wrong_count = _complete_evidence(tmp_path)
    wrong_count["semantic_obligations"]["claim_rows"].pop()
    with pytest.raises(Near100EvidenceError, match="exactly 316 claim rows"):
        build_near100_scorecard(evidence=wrong_count, mode="final")

    duplicate = _complete_evidence(tmp_path)
    duplicate["semantic_obligations"]["card_module_rows"][1]["obligation_id"] = (
        duplicate["semantic_obligations"]["card_module_rows"][0]["obligation_id"]
    )
    with pytest.raises(Near100EvidenceError, match="duplicate obligation IDs"):
        build_near100_scorecard(evidence=duplicate, mode="final")


def test_scorecard_document_uses_decimal_strings_and_stable_json(tmp_path: Path) -> None:
    scorecard = build_near100_scorecard(
        evidence=_complete_evidence(tmp_path), mode="final"
    )

    document = scorecard.to_document()
    encoded = scorecard.to_json()

    assert document["overall_score"] == "100"
    assert document["metrics"][0]["score"] == "100"
    assert document["metrics"][-1]["score"] is None
    assert encoded == json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )


def test_cli_fails_closed_when_base_evidence_bundle_is_absent(tmp_path: Path) -> None:
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--mode",
            "pre_cutover",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert payload["passed"] is False
    assert payload["errors"] == [
        f"base evidence bundle does not exist: {tmp_path / '.near100' / 'base-evidence.json'}"
    ]


def test_cli_reads_explicit_evidence_and_emits_one_json_document(tmp_path: Path) -> None:
    evidence_path = tmp_path / ".near100" / "evidence.json"
    evidence_path.parent.mkdir(exist_ok=True)
    evidence_path.write_text(
        json.dumps(_complete_evidence(tmp_path)), encoding="utf-8"
    )
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence",
            str(evidence_path),
            "--mode",
            "final",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["passed"] is True
    assert payload["version"] == "1.0.0"
    assert payload["overall_score"] == "100"
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "duplicate_scope",
    ["top", "meta", "check_id", "check_field", "finding", "semantic_row"],
)
def test_cli_rejects_duplicate_json_keys_at_every_object_level(
    tmp_path: Path, duplicate_scope: str
) -> None:
    evidence = _complete_evidence(tmp_path)
    raw = json.dumps(evidence, separators=(",", ":"))
    if duplicate_scope == "top":
        raw = '{"findings":{},' + raw[1:]
    elif duplicate_scope == "meta":
        raw = raw.replace(
            '"producer":"hsconfig.release_gate.base_evidence"',
            '"producer":"duplicate","producer":"hsconfig.release_gate.base_evidence"',
            1,
        )
    elif duplicate_scope == "check_id":
        raw = raw.replace(
            '"checks":{', '"checks":{"contract_spine":{},', 1
        )
    elif duplicate_scope == "check_field":
        raw = raw.replace('"passed":true', '"passed":false,"passed":true', 1)
    elif duplicate_scope == "finding":
        raw = raw.replace('"open_p0":0', '"open_p0":1,"open_p0":0', 1)
    else:
        raw = raw.replace(
            '"obligation_id":"',
            '"obligation_id":"duplicate","obligation_id":"',
            1,
        )
    evidence_path = tmp_path / ".near100" / "duplicate.json"
    evidence_path.parent.mkdir(exist_ok=True)
    evidence_path.write_text(raw, encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence",
            str(evidence_path),
            "--mode",
            "final",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "duplicate JSON key" in json.loads(completed.stdout)["errors"][0]


def test_cli_pre_cutover_exits_zero_only_when_every_local_gate_passes(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path, mode="pre_cutover")
    for check_id, owner in tuple(ATOMIC_CHECK_OWNERS.items()):
        if owner == "github_repository_polish":
            del evidence["checks"][check_id]
    evidence_path = tmp_path / ".near100" / "evidence.json"
    evidence_path.parent.mkdir(exist_ok=True)
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"
    command = [
        sys.executable,
        str(script),
        "--repo",
        str(tmp_path),
        "--outputs",
        str(tmp_path / "outputs"),
        "--evidence",
        str(evidence_path),
        "--mode",
        "pre_cutover",
        "--json",
    ]

    green = subprocess.run(command, check=False, capture_output=True, text=True)
    _set_check_result(evidence, tmp_path, "version_consistency", passed=False)
    evidence["checks"]["version_consistency"]["blocking_reasons"] = [
        "version mismatch"
    ]
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    red = subprocess.run(command, check=False, capture_output=True, text=True)

    assert green.returncode == 0
    assert json.loads(green.stdout)["passed"] is False
    assert red.returncode == 1
    assert json.loads(red.stdout)["passed"] is False


def test_cli_binds_evidence_to_the_requested_repository(tmp_path: Path) -> None:
    requested_repo = tmp_path / "requested"
    other_repo = tmp_path / "other"
    requested_repo.mkdir()
    (requested_repo / "outputs").mkdir()
    other_repo.mkdir()
    evidence = _complete_evidence(other_repo)
    evidence_path = requested_repo / "evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(requested_repo),
            "--outputs",
            str(requested_repo / "outputs"),
            "--evidence",
            str(evidence_path),
            "--mode",
            "final",
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["errors"] == [
        "base evidence repository_root does not match --repo"
    ]


def test_embedded_receipts_are_resolved_without_named_evidence_files(
    tmp_path: Path,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    shutil.rmtree(tmp_path / "receipts")
    _refresh_repository_state(bundle["evidence"], tmp_path)
    _refresh_embedded_receipt_bindings(bundle)

    scorecard = build_near100_scorecard(
        evidence=bundle["evidence"],
        mode="final",
        receipt_documents=bundle["receipts"],
    )

    assert scorecard.passed is True


@pytest.mark.parametrize(
    "field,replacement",
    (
        ("repository_identity", "SomeoneElse/HSConfig"),
        ("commit_oid", "0" * 40),
        ("tree_oid", "f" * 40),
        ("tree_state", "dirty"),
        ("dirty_tree_fingerprint", "a" * 64),
        ("generation_mode", "pre_cutover"),
    ),
)
def test_embedded_receipt_binding_matches_validated_evidence_meta_exactly(
    tmp_path: Path,
    field: str,
    replacement: str,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    bundle["receipts"]["receipts/contract_spine.json"]["binding"][field] = (
        replacement
    )

    with pytest.raises(Near100EvidenceError, match="receipt binding mismatch"):
        build_near100_scorecard(
            evidence=bundle["evidence"],
            mode="final",
            receipt_documents=bundle["receipts"],
        )


def test_embedded_receipt_cannot_be_swapped_across_repository_envelopes(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _embedded_bundle(first_root)
    _initialize_repository(second_root)
    (second_root / "second-state.txt").write_text("distinct", encoding="utf-8")
    _git(second_root, "add", "second-state.txt")
    _git(second_root, "commit", "-q", "-m", "distinct second state")
    second = _embedded_bundle(second_root)
    first["receipts"]["receipts/contract_spine.json"] = second["receipts"][
        "receipts/contract_spine.json"
    ]

    with pytest.raises(Near100EvidenceError, match="receipt binding mismatch"):
        build_near100_scorecard(
            evidence=first["evidence"],
            mode="final",
            receipt_documents=first["receipts"],
        )


@pytest.mark.parametrize("field", ("transaction_id", "observed_at"))
def test_final_github_receipts_bind_the_validated_live_transaction(
    tmp_path: Path,
    field: str,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    receipt = bundle["receipts"]["receipts/github_release.json"]
    receipt["binding"][field] = "b" * 32 if field == "transaction_id" else "2000-01-01T00:00:00Z"

    with pytest.raises(Near100EvidenceError, match="receipt binding mismatch"):
        build_near100_scorecard(
            evidence=bundle["evidence"],
            mode="final",
            receipt_documents=bundle["receipts"],
        )


@pytest.mark.parametrize(
    "mutation,match",
    (
        ("producer", "producer mismatch"),
        ("check_id", "receipt check_id mismatch"),
        ("passed", "receipt result mismatch"),
        ("schema", "unknown fields"),
        ("self_score", "embedded scorecard"),
        ("extra_receipt", "unexpected embedded receipt"),
    ),
)
def test_embedded_receipts_fail_closed_on_tampering_and_unconsumed_entries(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    receipt_id = "receipts/contract_spine.json"
    receipt = bundle["receipts"][receipt_id]
    if mutation == "producer":
        receipt["producer"] = "untrusted.producer"
    elif mutation == "check_id":
        receipt["check_id"] = "owner_policy"
    elif mutation == "passed":
        receipt["result"]["passed"] = False
    elif mutation == "schema":
        receipt["unexpected"] = True
    elif mutation == "self_score":
        receipt["nested"] = {
            "schema_version": 1,
            "version": "1.0.0",
            "metrics": [],
            "overall_score": "100",
            "passed": True,
        }
    else:
        bundle["receipts"]["receipts/unconsumed.json"] = {
            "schema_version": 1,
            "producer": "hsconfig.release_gate.base_check",
            "check_id": "contract_spine",
            "result": {"passed": True},
        }

    with pytest.raises(Near100EvidenceError, match=match):
        build_near100_scorecard(
            evidence=bundle["evidence"],
            mode="final",
            receipt_documents=bundle["receipts"],
        )


def test_cli_reads_one_closed_stdin_envelope_without_receipt_files(
    tmp_path: Path,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    shutil.rmtree(tmp_path / "receipts")
    _refresh_repository_state(bundle["evidence"], tmp_path)
    _refresh_embedded_receipt_bindings(bundle)
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence-stdin",
            "--mode",
            "final",
            "--json",
        ],
        input=json.dumps(bundle, separators=(",", ":")),
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert payload["passed"] is True
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""


@pytest.mark.parametrize(
    "raw_mutation",
    ("second_document", "duplicate_receipt_id", "unknown_envelope_field"),
)
def test_cli_stdin_rejects_noncanonical_or_nonexclusive_documents_with_one_json_error(
    tmp_path: Path,
    raw_mutation: str,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    raw = json.dumps(bundle, separators=(",", ":"))
    if raw_mutation == "second_document":
        raw += "\n{}"
    elif raw_mutation == "duplicate_receipt_id":
        marker = '"receipts":{'
        receipt_id = "receipts/contract_spine.json"
        duplicate = json.dumps(bundle["receipts"][receipt_id], separators=(",", ":"))
        raw = raw.replace(marker, marker + json.dumps(receipt_id) + ":" + duplicate + ",", 1)
    else:
        raw = '{"unexpected":true,' + raw[1:]
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence-stdin",
            "--mode",
            "final",
            "--json",
        ],
        input=raw,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert payload["passed"] is False
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""
    assert "Traceback" not in completed.stdout


@pytest.mark.parametrize("duplicate_kind", ("github", "sensitive", "local_path"))
def test_cli_invalid_stdin_failure_never_echoes_sensitive_duplicate_keys_or_values(
    tmp_path: Path,
    duplicate_kind: str,
) -> None:
    (tmp_path / "outputs").mkdir()
    github = "ghp_" + "A" * 36
    local_path = "C:" + chr(92) + chr(92).join(("Users", "operator", "private"))
    if duplicate_kind == "github":
        duplicate_key = github
        duplicate_value = "ordinary"
    elif duplicate_kind == "sensitive":
        duplicate_key = "service.auth.token"
        duplicate_value = github
    else:
        duplicate_key = local_path
        duplicate_value = local_path
    raw = (
        "{"
        + json.dumps(duplicate_key)
        + ":"
        + json.dumps(duplicate_value)
        + ","
        + json.dumps(duplicate_key)
        + ":0}"
    )
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence-stdin",
            "--mode",
            "final",
            "--json",
        ],
        input=raw,
        check=False,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    encoded = completed.stdout
    assert completed.returncode == 2
    assert payload["passed"] is False
    assert payload["errors"] == ["stdin evidence envelope rejected: invalid_envelope"]
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""
    assert github not in encoded
    assert "service.auth.token" not in encoded
    assert local_path not in encoded
    assert "Traceback" not in encoded


def test_cli_rejects_simultaneous_file_and_stdin_evidence_with_one_json_error(
    tmp_path: Path,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(json.dumps(bundle["evidence"]), encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence",
            str(evidence_path),
            "--evidence-stdin",
            "--mode",
            "final",
            "--json",
        ],
        input=json.dumps(bundle),
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["passed"] is False
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""


@pytest.mark.parametrize("invalid_kind", ("excessive_nesting", "oversized"))
def test_cli_stdin_bounds_evidence_nesting_and_size_with_one_json_error(
    tmp_path: Path,
    invalid_kind: str,
) -> None:
    (tmp_path / "outputs").mkdir()
    raw = (
        "[" * 65 + "0" + "]" * 65
        if invalid_kind == "excessive_nesting"
        else "x" * (8 * 1024 * 1024 + 1)
    )
    script = Path(__file__).parents[1] / "scripts" / "check_near100_scorecard.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo",
            str(tmp_path),
            "--outputs",
            str(tmp_path / "outputs"),
            "--evidence-stdin",
            "--mode",
            "final",
            "--json",
        ],
        input=raw,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["passed"] is False
    assert completed.stdout.count("\n") == 1
    assert completed.stderr == ""


def test_builder_rejects_primitive_meta_and_reason_shape_boundaries(
    tmp_path: Path,
) -> None:
    baseline = _complete_evidence(tmp_path)

    _expect_evidence_error(
        "unsupported mode",
        "unsupported scorecard mode",
        lambda: build_near100_scorecard(
            evidence=copy.deepcopy(baseline),
            mode="candidate",  # type: ignore[arg-type]
        ),
    )
    _expect_evidence_error(
        "non-object evidence",
        "evidence must be an object",
        lambda: build_near100_scorecard(
            evidence=[],  # type: ignore[arg-type]
            mode="final",
        ),
    )

    cases: tuple[tuple[str, str, Any], ...] = (
        (
            "non-object metadata",
            "evidence._meta must be an object",
            lambda evidence: evidence.__setitem__("_meta", []),
        ),
        (
            "non-string repository root",
            "repository_root must be a path string",
            lambda evidence: evidence["_meta"].__setitem__("repository_root", None),
        ),
        (
            "missing repository root",
            "repository root does not exist",
            lambda evidence: evidence["_meta"].__setitem__(
                "repository_root", str(tmp_path / "absent")
            ),
        ),
        (
            "missing metadata field",
            "missing required fields",
            lambda evidence: evidence["_meta"].pop("producer"),
        ),
        (
            "boolean finding count",
            "must be a non-negative integer",
            lambda evidence: evidence["findings"].__setitem__("open_p0", True),
        ),
        (
            "unknown finding field",
            "unknown findings fields",
            lambda evidence: evidence["findings"].__setitem__("open_p2", 0),
        ),
        (
            "reason is not an array",
            "blocking_reasons must be an array",
            lambda evidence: evidence["checks"]["contract_spine"].__setitem__(
                "blocking_reasons", "plain text"
            ),
        ),
        (
            "blank reason",
            "must contain non-empty strings",
            lambda evidence: evidence["checks"]["contract_spine"].__setitem__(
                "non_blocking_reasons", [""]
            ),
        ),
        (
            "duplicate reasons",
            "must not contain duplicates",
            lambda evidence: evidence["checks"]["contract_spine"].__setitem__(
                "non_blocking_reasons", ["same", "same"]
            ),
        ),
        (
            "empty evidence paths",
            "must not be empty",
            lambda evidence: evidence["checks"]["contract_spine"].__setitem__(
                "evidence_paths", []
            ),
        ),
    )
    for label, pattern, mutate in cases:
        evidence = copy.deepcopy(baseline)
        mutate(evidence)
        _expect_evidence_error(
            label,
            pattern,
            lambda evidence=evidence: build_near100_scorecard(
                evidence=evidence,
                mode="final",
            ),
        )


def test_builder_accepts_supported_origin_forms_and_rejects_ambiguous_identity(
    tmp_path: Path,
) -> None:
    evidence = _complete_evidence(tmp_path)

    _git(
        tmp_path,
        "remote",
        "set-url",
        "origin",
        "git@github.com:Teufelsboy/HSConfig.git",
    )
    assert build_near100_scorecard(
        evidence=copy.deepcopy(evidence), mode="final"
    ).passed

    _git(tmp_path, "remote", "set-url", "origin", "Teufelsboy/HSConfig")
    assert build_near100_scorecard(
        evidence=copy.deepcopy(evidence), mode="final"
    ).passed

    _git(tmp_path, "remote", "set-url", "origin", "not-a-repository")
    _expect_evidence_error(
        "ambiguous origin",
        "repository identity cannot be derived",
        lambda: build_near100_scorecard(
            evidence=copy.deepcopy(evidence),
            mode="final",
        ),
    )


def test_final_embedded_envelope_rejects_transaction_receipt_and_check_boundaries(
    tmp_path: Path,
) -> None:
    baseline = _embedded_bundle(tmp_path)

    cases: tuple[tuple[str, str, Any], ...] = (
        (
            "transaction identity",
            "transaction identity mismatch",
            lambda bundle: bundle["evidence"]["_meta"].__setitem__(
                "transaction_id", "not-a-transaction"
            ),
        ),
        (
            "transaction observation type",
            "observation time invalid",
            lambda bundle: bundle["evidence"]["_meta"].__setitem__(
                "observed_at", 1
            ),
        ),
        (
            "transaction observation syntax",
            "observation time invalid",
            lambda bundle: bundle["evidence"]["_meta"].__setitem__(
                "observed_at", "not-a-time"
            ),
        ),
        (
            "transaction observation timezone",
            "observation is stale",
            lambda bundle: bundle["evidence"]["_meta"].__setitem__(
                "observed_at", "2026-08-06T12:00:00"
            ),
        ),
        (
            "transaction observation freshness",
            "observation is stale",
            lambda bundle: bundle["evidence"]["_meta"].__setitem__(
                "observed_at", "2000-01-01T00:00:00Z"
            ),
        ),
        (
            "receipt schema version",
            "schema_version mismatch",
            lambda bundle: bundle["receipts"][
                "receipts/contract_spine.json"
            ].__setitem__("schema_version", 1),
        ),
        (
            "receipt result schema",
            "result schema mismatch",
            lambda bundle: bundle["receipts"]["receipts/contract_spine.json"][
                "result"
            ].__setitem__("detail", "unbound"),
        ),
        (
            "receipt result type",
            "result.passed must be boolean",
            lambda bundle: bundle["receipts"]["receipts/contract_spine.json"][
                "result"
            ].__setitem__("passed", "yes"),
        ),
        (
            "noncanonical embedded receipt ID",
            "exactly canonical embedded receipt ID",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("evidence_paths", ["receipts/version_consistency.json"]),
        ),
        (
            "unknown atomic field",
            "contains unknown fields",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("diagnostic", "unbound"),
        ),
        (
            "atomic result type",
            "passed must be boolean",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("passed", "yes"),
        ),
        (
            "atomic evidence kind",
            "not an allowed base evidence kind",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("kind", "scorecard"),
        ),
        (
            "passing check with blocking reason",
            "cannot have blocking reasons",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("blocking_reasons", ["contradiction"]),
        ),
        (
            "failed check without blocking reason",
            "must have a blocking reason",
            lambda bundle: (
                bundle["evidence"]["checks"]["contract_spine"].__setitem__(
                    "passed", False
                ),
                bundle["receipts"]["receipts/contract_spine.json"][
                    "result"
                ].__setitem__("passed", False),
            ),
        ),
        (
            "atomic scope",
            "scope must be PRE_RUN_CONTRACT",
            lambda bundle: bundle["evidence"]["checks"][
                "contract_spine"
            ].__setitem__("scope", "POST_RUN"),
        ),
    )
    for label, pattern, mutate in cases:
        bundle = copy.deepcopy(baseline)
        mutate(bundle)
        _expect_evidence_error(
            label,
            pattern,
            lambda bundle=bundle: build_near100_scorecard(
                evidence=bundle["evidence"],
                mode="final",
                receipt_documents=bundle["receipts"],
            ),
        )

    _expect_evidence_error(
        "receipt collection type",
        "embedded receipts must be an object",
        lambda: build_near100_scorecard(
            evidence=copy.deepcopy(baseline["evidence"]),
            mode="final",
            receipt_documents=[],  # type: ignore[arg-type]
        ),
    )
    non_string_receipts = copy.deepcopy(baseline["receipts"])
    non_string_receipts[1] = non_string_receipts["receipts/contract_spine.json"]
    _expect_evidence_error(
        "receipt identifier type",
        "embedded receipt IDs must be strings",
        lambda: build_near100_scorecard(
            evidence=copy.deepcopy(baseline["evidence"]),
            mode="final",
            receipt_documents=non_string_receipts,
        ),
    )


def test_builder_rejects_each_closed_semantic_row_boundary(tmp_path: Path) -> None:
    baseline = _embedded_bundle(tmp_path)
    cases: tuple[tuple[str, str, Any], ...] = (
        (
            "missing semantic collection",
            "missing required fields",
            lambda evidence: evidence["semantic_obligations"].pop("claim_rows"),
        ),
        (
            "missing semantic row field",
            "missing required fields",
            lambda evidence: evidence["semantic_obligations"][
                "card_module_rows"
            ][0].pop("obligation_id"),
        ),
        (
            "empty semantic identity",
            "obligation_id must be non-empty",
            lambda evidence: evidence["semantic_obligations"][
                "card_module_rows"
            ][0].__setitem__("obligation_id", ""),
        ),
        (
            "unknown authority lane",
            "invalid authority lane",
            lambda evidence: evidence["semantic_obligations"][
                "card_module_rows"
            ][0].__setitem__("authority_lanes", ["Z"]),
        ),
        (
            "semantic disposition type",
            "final_disposition must be boolean",
            lambda evidence: evidence["semantic_obligations"][
                "card_module_rows"
            ][0].__setitem__("final_disposition", "final"),
        ),
    )
    for label, pattern, mutate in cases:
        bundle = copy.deepcopy(baseline)
        mutate(bundle["evidence"])
        _expect_evidence_error(
            label,
            pattern,
            lambda bundle=bundle: build_near100_scorecard(
                evidence=bundle["evidence"],
                mode="final",
                receipt_documents=bundle["receipts"],
            ),
        )


def test_builder_bounds_free_text_and_accepts_non_scorecard_json_fragment(
    tmp_path: Path,
) -> None:
    baseline = _complete_evidence(tmp_path)

    oversized = copy.deepcopy(baseline)
    oversized["diagnostic"] = "x" * 1_000_001
    _expect_evidence_error(
        "oversized free text",
        "free-text exceeds safe inspection length",
        lambda: build_near100_scorecard(evidence=oversized, mode="final"),
    )

    excessive_fragments = copy.deepcopy(baseline)
    excessive_fragments["diagnostic"] = '"x" ' * 257
    _expect_evidence_error(
        "excessive JSON fragments",
        "safe JSON inspection complexity",
        lambda: build_near100_scorecard(
            evidence=excessive_fragments,
            mode="final",
        ),
    )

    ordinary_fragment = copy.deepcopy(baseline)
    ordinary_fragment["checks"]["contract_spine"]["non_blocking_reasons"] = [
        'diagnostic {"kind":"ordinary"}'
    ]
    assert build_near100_scorecard(
        evidence=ordinary_fragment,
        mode="final",
    ).passed


def test_builder_rejects_real_directory_and_intermediate_file_evidence_paths(
    tmp_path: Path,
) -> None:
    baseline = _complete_evidence(tmp_path)
    cases = (
        ("receipts", "not a regular file"),
        (".gitignore/receipt.json", "component is not a directory"),
    )
    for path_text, pattern in cases:
        evidence = copy.deepcopy(baseline)
        evidence["checks"]["contract_spine"]["evidence_paths"] = [path_text]
        _expect_evidence_error(
            path_text,
            pattern,
            lambda evidence=evidence: build_near100_scorecard(
                evidence=evidence,
                mode="final",
            ),
        )


def test_dirty_tree_fingerprint_fails_closed_on_command_types_and_real_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_repository(tmp_path)
    original_git = scorecard_module._git
    command_cases = (
        ("status", "repository status inspection returned text"),
        ("diff", "repository diff inspection returned text"),
        ("ls-files", "repository untracked inspection returned text"),
    )
    for command, pattern in command_cases:
        def wrong_type(
            root: Path,
            *args: str,
            text: bool = True,
            command: str = command,
        ) -> str | bytes:
            if args and args[0] == command:
                return "not bytes"
            return original_git(root, *args, text=text)

        monkeypatch.setattr(scorecard_module, "_git", wrong_type)
        _expect_evidence_error(
            command,
            pattern,
            lambda: scorecard_module._dirty_tree_fingerprint(tmp_path),
        )

    def untracked_directory(
        root: Path,
        *args: str,
        text: bool = True,
    ) -> str | bytes:
        if args and args[0] == "ls-files":
            return b"outputs\0"
        return original_git(root, *args, text=text)

    monkeypatch.setattr(scorecard_module, "_git", untracked_directory)
    _expect_evidence_error(
        "untracked directory",
        "untracked repository path is not a regular file",
        lambda: scorecard_module._dirty_tree_fingerprint(tmp_path),
    )


def test_builder_hashes_a_real_untracked_regular_file(tmp_path: Path) -> None:
    evidence = _complete_evidence(tmp_path)
    (tmp_path / "untracked.txt").write_text("bound bytes", encoding="utf-8")
    _refresh_repository_state(evidence, tmp_path)

    assert build_near100_scorecard(evidence=evidence, mode="final").passed


def test_internal_defense_layers_reject_embedded_check_and_missing_resolver(
    tmp_path: Path,
) -> None:
    bundle = _embedded_bundle(tmp_path)
    evidence = bundle["evidence"]
    evidence["checks"]["contract_spine"]["diagnostic"] = {
        "schema_version": 1,
        "version": "1.0.0",
        "metrics": [],
        "overall_score": "100",
        "passed": True,
    }
    _expect_evidence_error(
        "embedded scorecard at atomic validation layer",
        "atomic check contract_spine contains an embedded scorecard result",
        lambda: scorecard_module._validate_checks(
            evidence,
            mode="final",
            repository_root=tmp_path,
            receipt_documents=bundle["receipts"],
            consumed_receipts=set(),
            evidence_meta=evidence["_meta"],
        ),
    )

    _expect_evidence_error(
        "missing embedded receipt resolver",
        "embedded receipt resolver is unavailable",
        lambda: scorecard_module._validate_evidence_paths(
            ["receipts/contract_spine.json"],
            "contract spine evidence paths",
            repository_root=tmp_path,
            expected_check_id="contract_spine",
            expected_producer="hsconfig.release_gate.base_check",
            expected_passed=True,
            receipt_documents=bundle["receipts"],
            consumed_receipts=None,
            expected_binding=scorecard_module._receipt_binding(
                evidence["_meta"],
                include_final_transaction=False,
            ),
        ),
    )
