"""Audit or conservatively rebuild the twelve canonical HSConfig outputs."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from hsconfig.output_inventory import (
    inventory_is_current as _inventory_is_current,
    inventory_json,
    inventory_text,
    reconcile_audited_outputs,
)
from hsconfig.output_reconciliation import (
    apply_audited_outputs,
    propose_legacy_deletion,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("docs/operator/audited-deck-catalog.json"),
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--propose-legacy-manifest", action="store_true")
    parser.add_argument("--legacy-approval-digest")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.propose_legacy_manifest:
            if args.legacy_approval_digest is not None:
                raise ValueError("reconcile_legacy_approval_not_applicable")
            proposal = propose_legacy_deletion(
                outputs_root=args.outputs,
                catalog_path=args.catalog,
            )
            payload = {
                "approval_digest": proposal.approval_digest,
                "manifest": proposal.manifest,
            }
            print(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        inventory = (
            apply_audited_outputs(
                outputs_root=args.outputs,
                catalog_path=args.catalog,
                legacy_approval_digest=args.legacy_approval_digest,
            )
            if args.apply
            else reconcile_audited_outputs(
                outputs_root=args.outputs,
                catalog_path=args.catalog,
            )
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    output = inventory_json(inventory) if args.json else inventory_text(inventory)
    print(output, end="")
    return 0 if _inventory_is_current(inventory) else 1


if __name__ == "__main__":
    raise SystemExit(main())
