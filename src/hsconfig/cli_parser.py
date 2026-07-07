from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsconfig",
        description="HSConfig builds lean HearthRanger VisionAI CustomConfig packages before games are played.",
        epilog=(
            "Normal operator docs: docs/operator/README.md\n"
            "Normal path: source-manifest -> draft-source-documents -> research-deck -> "
            "prepare -> apply. Expert and legacy path: build, --claims-json, "
            "--cards-json, --plan-reports-dir."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build",
        help="expert lower-level package builder",
        description="Expert lower-level package builder.",
    )
    build.add_argument("--deck-name", required=True)
    build.add_argument("--deck-code", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--cards-json")
    build.add_argument("--claims-json")
    build.add_argument("--guide-sources-json")
    build.add_argument("--source-documents-json")
    build.add_argument("--plan-reports-dir")
    build.add_argument("--allow-placeholder", action="store_true")
    build.add_argument("--json", action="store_true")

    prepare = subparsers.add_parser(
        "prepare",
        help="normal package creation path",
        description="Normal package creation path.",
    )
    prepare.add_argument("--deck-name", required=True)
    prepare.add_argument("--deck-code", required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.add_argument("--cards-json")
    prepare.add_argument("--claims-json")
    prepare.add_argument("--guide-sources-json")
    prepare.add_argument("--source-documents-json")
    prepare.add_argument("--auto-research-fallback", action=argparse.BooleanOptionalAction, default=True)
    prepare.add_argument("--plan-reports-dir")
    prepare.add_argument("--allow-placeholder", action="store_true")
    prepare.add_argument("--json", action="store_true")

    research_contract = subparsers.add_parser("research-contract")
    research_contract.add_argument("--deck-name", required=True)
    research_contract.add_argument("--deck-code", required=True)
    research_contract.add_argument("--out", required=True)
    research_contract.add_argument("--cards-json")
    research_contract.add_argument("--claims-json")
    research_contract.add_argument("--guide-sources-json")
    research_contract.add_argument("--source-documents-json")
    research_contract.add_argument("--allow-placeholder", action="store_true")
    research_contract.add_argument("--json", action="store_true")

    source_manifest = subparsers.add_parser(
        "source-manifest",
        help="normal path source research manifest",
    )
    source_manifest.add_argument("--deck-name", required=True)
    source_manifest.add_argument("--deck-code", required=True)
    source_manifest.add_argument("--out", required=True)
    source_manifest.add_argument("--cards-json")
    source_manifest.add_argument("--allow-placeholder", action="store_true")
    source_manifest.add_argument("--json", action="store_true")

    draft_source_documents = subparsers.add_parser(
        "draft-source-documents",
        help="normal path source document drafting",
    )
    draft_source_documents.add_argument("--deck-name", required=True)
    draft_source_documents.add_argument("--deck-code", required=True)
    draft_source_documents.add_argument("--source-evidence-json", required=True)
    draft_source_documents.add_argument("--out", required=True)
    draft_source_documents.add_argument("--cards-json")
    draft_source_documents.add_argument("--allow-placeholder", action="store_true")
    draft_source_documents.add_argument("--json", action="store_true")

    research_deck = subparsers.add_parser(
        "research-deck",
        help="normal path source document normalization",
    )
    research_deck.add_argument("--deck-name", required=True)
    research_deck.add_argument("--deck-code", required=True)
    research_deck.add_argument("--out", required=True)
    research_deck.add_argument("--cards-json")
    research_deck.add_argument("--source-documents-json")
    research_deck.add_argument("--source-evidence-json")
    research_deck.add_argument("--allow-placeholder", action="store_true")
    research_deck.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--package", required=True)
    validate.add_argument("--json", action="store_true")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument("--allow-source-informed", action="store_true")
    apply.add_argument("--json", action="store_true")
    return parser
