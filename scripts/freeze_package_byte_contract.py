from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
if str(REPOSITORY_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from tests.helpers.package_byte_contract import (  # noqa: E402
    AUDITED_DECK_NAMES,
    assert_trees_byte_equal,
    build_fixture_from_roots,
    prepare_audited_packages,
)


DEFAULT_FIXTURE = Path("tests/fixtures/package-byte-contract-v1.json")


def build_contract(*, verify_twice: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="hsconfig-package-byte-contract-") as temp:
        root = Path(temp)
        first = prepare_audited_packages(root / "first")
        fixture = build_fixture_from_roots(first)
        if verify_twice:
            second = prepare_audited_packages(root / "second")
            assert_trees_byte_equal(first, second)
            comparison = build_fixture_from_roots(second)
            for deck_name in AUDITED_DECK_NAMES:
                if (
                    comparison["decks"][deck_name]["deck_fingerprint"]
                    != fixture["decks"][deck_name]["deck_fingerprint"]
                ):
                    raise AssertionError(
                        f"package_byte_contract_fingerprint_mismatch:{deck_name}"
                    )
        return fixture


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(
        description="Freeze the reviewed metadata-only twelve-deck package byte contract."
    )
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-twice", action="store_true")
    args = parser.parse_args(argv)
    fixture_path = args.fixture

    if fixture_path.exists() and not args.write:
        raise SystemExit("refusing_to_overwrite_without_explicit_write")
    if not args.write:
        raise SystemExit("write_requires_explicit_write")
    if not args.verify_twice:
        raise SystemExit("verify_twice_required_for_write")

    fixture = build_contract(verify_twice=True)
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fixture


if __name__ == "__main__":
    main()
