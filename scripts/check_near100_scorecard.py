from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


_REPOSITORY = Path(__file__).resolve().parents[1]
_SOURCE = _REPOSITORY / "src"
if str(_SOURCE) not in sys.path:
    sys.path.insert(0, str(_SOURCE))

from hsconfig.near100_scorecard import (  # noqa: E402
    Near100EvidenceError,
    build_near100_scorecard,
    load_json_strict,
)
from hsconfig.version import __version__  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute the evidence-backed HSConfig near-100 scorecard."
    )
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--mode", choices=("pre_cutover", "final"), required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def _failure(message: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "version": __version__,
        "passed": False,
        "errors": [message],
    }


def _emit(document: dict[str, Any]) -> None:
    print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _pre_cutover_local_passed(document: dict[str, Any]) -> bool:
    allowed_non_pass = {
        "github_repository_polish": "pending_remote",
        "gameplay_quality": "not_applicable",
    }
    metrics = document["metrics"]
    return (
        document["open_p0_findings"] == 0
        and document["open_p1_findings"] == 0
        and all(
            metric["status"]
            == allowed_non_pass.get(metric["metric_id"], "pass")
            for metric in metrics
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repository = args.repo.resolve()
    outputs = args.outputs.resolve()
    evidence_path = (
        args.evidence.resolve()
        if args.evidence is not None
        else repository / ".near100" / "base-evidence.json"
    )
    if not repository.is_dir():
        _emit(_failure(f"repository does not exist: {repository}"))
        return 2
    if not evidence_path.is_file():
        _emit(_failure(f"base evidence bundle does not exist: {evidence_path}"))
        return 2
    if not outputs.is_dir():
        _emit(_failure(f"outputs root does not exist: {outputs}"))
        return 2
    try:
        evidence = load_json_strict(
            evidence_path.read_text(encoding="utf-8"),
            source="base evidence bundle",
        )
    except (OSError, UnicodeError, Near100EvidenceError) as exc:
        _emit(_failure(f"base evidence bundle is not valid JSON: {exc}"))
        return 2
    if isinstance(evidence, dict):
        meta = evidence.get("_meta")
        evidence_root = meta.get("repository_root") if isinstance(meta, dict) else None
        if (
            isinstance(evidence_root, str)
            and Path(evidence_root).resolve() != repository
        ):
            _emit(_failure("base evidence repository_root does not match --repo"))
            return 2
    try:
        scorecard = build_near100_scorecard(evidence=evidence, mode=args.mode)
    except Near100EvidenceError as exc:
        _emit(_failure(f"invalid base evidence: {exc}"))
        return 2
    document = scorecard.to_document()
    _emit(document)
    if args.mode == "pre_cutover":
        return 0 if _pre_cutover_local_passed(document) else 1
    return 0 if scorecard.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
