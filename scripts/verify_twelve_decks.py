"""Run the offline twelve-deck cold-build and recovery verification."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hsconfig.build_input_catalog import (  # noqa: E402
    load_audited_build_inputs,
    load_audited_build_resource_store,
)
from hsconfig.audited_deck_catalog import load_audited_deck_catalog  # noqa: E402
from hsconfig.release_verification import verify_audited_decks  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify deterministic cold builds for the audited deck set."
    )
    parser.add_argument("--build-inputs", required=True, type=Path)
    parser.add_argument(
        "--deck-catalog",
        type=Path,
        default=ROOT / "docs" / "operator" / "audited-deck-catalog.json",
    )
    parser.add_argument(
        "--build-resources",
        type=Path,
        default=ROOT / "src" / "hsconfig" / "resources" / "audited_build_resources.json",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    build_inputs = load_audited_build_inputs(args.build_inputs)
    resources = load_audited_build_resource_store(
        args.build_resources,
        audited_inputs=build_inputs,
    )
    deck_codes = {
        str(row["deck_name"]): str(row["deck_code"])
        for row in load_audited_deck_catalog(args.deck_catalog)
    }
    with TemporaryDirectory(prefix="hsconfig-twelve-decks-") as temporary:
        root = Path(temporary)
        rows = verify_audited_decks(
            build_inputs=build_inputs,
            resource_store=resources,
            deck_codes=deck_codes,
            work_root_a=root / "cold-a",
            work_root_b=root / "cold-b",
        )
    passed = all(
        row.configure_run_bytes_equal and row.runtime_old_or_new_safe
        for row in rows
    ) and tuple(row.deck_name for row in rows) == tuple(
        build.deck_name for build in build_inputs.builds
    )
    payload = {
        "passed": passed,
        "decks": [asdict(row) for row in rows],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    else:
        for row in rows:
            print(
                f"{row.deck_name}: digest={row.first_content_root_sha256} "
                f"bytes_equal={row.configure_run_bytes_equal} "
                f"runtime_safe={row.runtime_old_or_new_safe}"
            )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
