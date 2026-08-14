from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.io import write_json


def run_contract_spine_sentinel_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, contract_spine_sentinel_payload)


def contract_spine_sentinel_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    repo_root = _resolve_repo_root(Path(args.repo_root))
    report = build_contract_spine_sentinel_report(repo_root=repo_root)
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_json_output(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json(out, report)
        report = {**report, "written_report": str(out)}
    return report, 0 if report.get("status") == "clean" else 1


def _resolve_repo_root(path: Path) -> Path:
    repo_root = path.expanduser().resolve(strict=True)
    sentinel = repo_root / "src" / "hsconfig" / "contract_spine_sentinel.py"
    if not repo_root.is_dir() or not sentinel.is_file():
        raise ValueError(
            "contract-spine-sentinel --repo-root must be an HSConfig repository root"
        )
    return repo_root


def _assert_safe_json_output(path: Path) -> None:
    parts = {part.lower() for part in path.parts}
    runtime_file_names = {
        "deck_config.ini",
        "globalvalues.json",
        "mulligan.json",
        "combo.json",
        "concede.json",
        "presume.json",
    }
    name = path.name.lower()
    if path.suffix.lower() != ".json":
        raise ValueError("contract-spine-sentinel --out must be a .json diagnostic report path")
    if "customconfig" in parts or name in runtime_file_names:
        raise ValueError(
            "contract-spine-sentinel --out must not target HearthRanger runtime files"
        )
