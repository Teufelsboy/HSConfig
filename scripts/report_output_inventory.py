"""Print the canonical read-only audited-output inventory."""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hsconfig.output_inventory import (  # noqa: E402
    inventory_json,
    reconcile_audited_outputs,
)


def build_inventory(
    output_root: Path,
    *,
    catalog_path: Path | None = None,
) -> dict[str, int]:
    """Compatibility adapter over the one canonical counter definition."""

    inventory = reconcile_audited_outputs(
        outputs_root=output_root,
        catalog_path=(
            ROOT / "docs" / "operator" / "audited-deck-catalog.json"
            if catalog_path is None
            else catalog_path
        ),
    )
    return {name: int(value) for name, value in asdict(inventory).items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_root",
        nargs="?",
        type=Path,
        default=Path("outputs"),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "docs" / "operator" / "audited-deck-catalog.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inventory = reconcile_audited_outputs(
        outputs_root=args.output_root,
        catalog_path=args.catalog,
    )
    print(inventory_json(inventory), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
