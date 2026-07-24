from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class RepoCurrentness:
    cwd: str
    branch: str
    upstream: str | None
    dirty: bool
    ahead_origin_main: int
    behind_origin_main: int
    clean_for_runtime_work: bool
    origin_main_error: str | None = None


def parse_status_short(text: str) -> tuple[str, bool]:
    lines = [line for line in text.splitlines() if line.strip()]
    branch_line = lines[0] if lines else "## unknown"
    branch = branch_line.removeprefix("## ").split("...")[0].strip()
    dirty = any(not line.startswith("## ") for line in lines)
    return branch, dirty


def parse_ahead_behind(text: str) -> tuple[int, int]:
    parts = text.replace("\t", " ").split()
    if len(parts) < 2:
        return 0, 0
    return int(parts[0]), int(parts[1])


def _run_git(
    cwd: Path,
    *args: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_currentness(cwd: str | Path) -> RepoCurrentness:
    root = Path(cwd)
    status = _run_git(root, "status", "--short", "--branch").stdout
    branch, dirty = parse_status_short(status)

    upstream_result = _run_git(
        root,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )
    upstream = upstream_result.stdout.strip() or None

    origin_main_result = _run_git(
        root,
        "rev-list",
        "--left-right",
        "--count",
        "HEAD...origin/main",
        check=False,
    )
    origin_main_error = None
    if origin_main_result.returncode == 0:
        ahead, behind = parse_ahead_behind(origin_main_result.stdout)
    else:
        ahead, behind = 0, 1
        origin_main_error = (
            origin_main_result.stderr.strip()
            or origin_main_result.stdout.strip()
            or "Unable to compare HEAD with origin/main"
        )
    return RepoCurrentness(
        cwd=str(root),
        branch=branch,
        upstream=upstream,
        dirty=dirty,
        ahead_origin_main=ahead,
        behind_origin_main=behind,
        clean_for_runtime_work=(not dirty and behind == 0 and origin_main_error is None),
        origin_main_error=origin_main_error,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    currentness = build_currentness(args.cwd)
    if args.json:
        print(json.dumps(asdict(currentness), indent=2, sort_keys=True))
    else:
        print(
            f"branch={currentness.branch} dirty={currentness.dirty} "
            f"ahead_origin_main={currentness.ahead_origin_main} "
            f"behind_origin_main={currentness.behind_origin_main} "
            f"clean_for_runtime_work={currentness.clean_for_runtime_work}"
        )
    return 0 if currentness.clean_for_runtime_work else 1


if __name__ == "__main__":
    raise SystemExit(main())
