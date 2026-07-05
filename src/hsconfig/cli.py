from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hsconfig.card_metadata import hydrate_card_metadata
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_combo import compile_combo
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.deck_identity import build_deck_identity
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.guide_research import normalize_source_claims
from hsconfig.io import read_json, slugify_deck_name, write_json
from hsconfig.models import InputManifest
from hsconfig.runtime_apply import apply_package
from hsconfig.surface_intent import build_surface_intent
from hsconfig.validate_package import validate_config_package


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            payload, code = _build(args)
        elif args.command == "validate":
            payload, code = _validate(args)
        elif args.command == "apply":
            payload, code = _apply(args)
        else:
            payload, code = {"status": "failed", "errors": [f"Unknown command: {args.command}"]}, 1
    except Exception as exc:
        payload, code = {"status": "failed", "errors": [str(exc)]}, 1
    return _emit(payload, args.json, code)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hsconfig")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--deck-name", required=True)
    build.add_argument("--deck-code", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--cards-json")
    build.add_argument("--claims-json")
    build.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--package", required=True)
    validate.add_argument("--json", action="store_true")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument("--json", action="store_true")
    return parser


def _build(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    deck_slug = slugify_deck_name(args.deck_name)
    deck_dir = out / "CustomConfig" / deck_slug
    reports_dir = out / "reports"
    if deck_dir.exists():
        shutil.rmtree(deck_dir)

    cards = _load_cards(args.cards_json, deck_name=args.deck_name, deck_code=args.deck_code)
    claims = _load_claims(args.claims_json)
    source_records = _source_records_from_cards(cards)
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards,
    )
    card_metadata = hydrate_card_metadata(
        cards=deck_identity["cards"],
        source_records=source_records,
    )
    source_claims = normalize_source_claims(claims)
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=source_claims,
    )
    surface_intent = build_surface_intent(gameplan_contract)

    baseline_receipt = load_globalvalues_baseline(args.runtime_root)
    baseline = baseline_receipt["baseline"]
    globalvalues = compile_globalvalues(baseline, gameplan_contract)
    write_json(deck_dir / "GlobalValues.json", globalvalues["config"])
    write_json(deck_dir / "Mulligan.json", compile_mulligan(gameplan_contract))
    for filename, payload in compile_cardid_behaviors(gameplan_contract).items():
        write_json(deck_dir / filename, payload)

    combo = compile_combo(gameplan_contract)
    if combo is not None:
        write_json(deck_dir / "Combo.json", combo)

    manifest = InputManifest(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        runtime_root=args.runtime_root,
        target_config_mode="preview",
    ).to_dict()
    manifest["cards_json"] = str(Path(args.cards_json)) if args.cards_json else None
    manifest["claims_json"] = str(Path(args.claims_json)) if args.claims_json else None
    write_json(reports_dir / "input_manifest.json", manifest)
    write_json(reports_dir / "deck_identity.json", deck_identity)
    write_json(reports_dir / "gameplan_contract.json", gameplan_contract)
    write_json(reports_dir / "surface_intent.json", surface_intent)
    write_json(reports_dir / "globalvalues_baseline.json", baseline)
    write_json(reports_dir / "globalvalues_baseline_receipt.json", baseline_receipt)
    write_json(reports_dir / "globalvalues_profile.json", globalvalues["profile"])

    report = validate_config_package(
        out,
        globalvalues_baseline=baseline,
        globalvalues_profile=globalvalues["profile"],
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    write_json(reports_dir / "validation_report.json", report)
    code = 0 if report["status"] == "passed" else 1
    return (
        {
            "status": report["status"],
            "package": str(out),
            "deck_slug": deck_slug,
            "errors": report["errors"],
        },
        code,
    )


def _validate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"], "checked_files": 0}, 1
    baseline = _read_required_baseline(package)
    profile = _read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    return report, 0 if report["status"] == "passed" else 1


def _apply(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1

    baseline = _read_required_baseline(package)
    profile = _read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    if report["status"] != "passed":
        return {"status": "failed", "errors": report["errors"], "validation_report": report}, 1

    receipt = apply_package(package_root=package, runtime_root=args.runtime_root)
    return {"status": "applied", "receipt": receipt}, 0


def _load_cards(cards_json: str | None, *, deck_name: str, deck_code: str) -> list[dict[str, Any]]:
    if cards_json is None:
        return _placeholder_cards(deck_name=deck_name, deck_code=deck_code)
    payload = read_json(cards_json)
    if isinstance(payload, dict):
        payload = payload.get("cards")
    if not isinstance(payload, list):
        raise ValueError("--cards-json must contain a list or an object with a cards list")
    cards = [_normalize_card_input(card) for card in payload]
    if not cards:
        raise ValueError("--cards-json did not contain any cards")
    return cards


def _load_claims(claims_json: str | None) -> list[dict[str, Any]]:
    if claims_json is None:
        return []
    payload = read_json(claims_json)
    if isinstance(payload, dict):
        payload = payload.get("claims")
    if not isinstance(payload, list):
        raise ValueError("--claims-json must contain a list or an object with a claims list")
    claims = []
    for claim in payload:
        if not isinstance(claim, dict):
            raise ValueError("Every claim row must be an object")
        claims.append(dict(claim))
    return claims


def _placeholder_cards(*, deck_name: str, deck_code: str) -> list[dict[str, Any]]:
    seed = hashlib.sha256(f"{deck_name}\0{deck_code}".encode("utf-8")).hexdigest().upper()
    cards: list[dict[str, Any]] = []
    for index, count in enumerate((2, 2, 1), start=1):
        chunk = seed[(index - 1) * 6 : index * 6]
        cards.append(
            {
                "card_id": f"HSC_{chunk}_{index}",
                "dbf_id": int(seed[index * 6 : index * 6 + 6], 16),
                "count": count,
                "name": f"Preview Placeholder {index}",
                "type": "MINION",
                "text": "Generated preview placeholder for deterministic package validation.",
                "mechanics": [],
            }
        )
    return cards


def _normalize_card_input(card: Any) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError("Every card row must be an object")
    if not card.get("card_id"):
        raise ValueError("Every card row must include card_id")
    normalized = {
        "card_id": str(card["card_id"]),
        "dbf_id": int(card["dbf_id"]) if card.get("dbf_id") is not None else None,
        "count": int(card.get("count", 1)),
    }
    for optional_key in ("name", "cost", "type", "text", "mechanics", "card_class", "class"):
        if optional_key in card:
            normalized[optional_key] = card[optional_key]
    return normalized


def _source_records_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    metadata_keys = {"name", "cost", "type", "text", "mechanics", "card_class", "class"}
    for card in cards:
        source = {key: card[key] for key in metadata_keys if key in card}
        if source:
            records[str(card["card_id"])] = source
    return records


def _read_optional_profile(package: Path) -> dict[str, Any] | None:
    profile_path = package / "reports" / "globalvalues_profile.json"
    if not profile_path.exists():
        return None
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise ValueError(f"GlobalValues profile must be an object: {profile_path}")
    return profile


def _read_required_baseline(package: Path) -> dict[str, Any]:
    baseline_path = package / "reports" / "globalvalues_baseline.json"
    if not baseline_path.exists():
        raise ValueError(f"Missing GlobalValues baseline report: {baseline_path}")
    baseline = read_json(baseline_path)
    if not isinstance(baseline, dict):
        raise ValueError(f"GlobalValues baseline must be an object: {baseline_path}")
    return baseline


def _emit(payload: dict[str, Any], as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
