from __future__ import annotations

import argparse


NEGATIVE_SCOPE_TEXT = (
    "HSConfig is pre-run only: it does not parse replays, inspect "
    "win"
    "rate, or tune after games."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hsconfig",
        description="HSConfig builds lean HearthRanger VisionAI CustomConfig packages before games are played.",
        epilog=(
            "Normal operator docs: docs/operator/README.md\n"
            "Preferred normal path: configure.\n"
            "Lower-level inspected path: source-manifest -> "
            "draft-source-documents -> research-deck -> "
            f"prepare -> validate -> apply. {NEGATIVE_SCOPE_TEXT}\n"
            "Expert and legacy path: build, --claims-json, "
            "--cards-json, --plan-reports-dir."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure = subparsers.add_parser(
        "configure",
        help="preferred one-command pre-run package path",
        description=(
            "Preferred one-command pre-run package path. Decode a deck, build "
            "source/research artifacts, prepare a load-safe package, validate it, "
            "and optionally apply it through the existing guarded apply gate."
        ),
    )
    configure.add_argument("--deck-name", required=True)
    configure.add_argument("--deck-code", required=True)
    configure.add_argument("--out", required=True)
    configure.add_argument("--runtime-root", required=True)
    configure.add_argument("--source-evidence-json")
    configure.add_argument("--auto-source", action="store_true")
    configure.add_argument("--source-search-results-json")
    configure.add_argument("--cards-json")
    configure.add_argument("--collectible-cards-json")
    configure.add_argument("--full-cards-json")
    configure.add_argument("--allow-placeholder", action="store_true")
    configure.add_argument("--apply", action="store_true")
    configure.add_argument("--json", action="store_true")

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
        help="inspected package creation stage",
        description=(
            "Inspected package creation stage. Use deck identity, source-backed guide "
            "documents, and a runtime root to compile a pre-run CustomConfig package."
        ),
    )
    prepare_normal = prepare.add_argument_group("required package inputs")
    prepare_normal.add_argument("--deck-name", required=True)
    prepare_normal.add_argument("--deck-code", required=True)
    prepare_normal.add_argument("--out", required=True)
    prepare_normal.add_argument("--runtime-root", required=True)

    prepare_source = prepare.add_argument_group("source inputs")
    prepare_source.add_argument("--guide-sources-json")
    prepare_source.add_argument("--source-documents-json")

    prepare_execution = prepare.add_argument_group("execution modifiers")
    prepare_execution.add_argument(
        "--auto-research-fallback",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    prepare_execution.add_argument("--json", action="store_true")

    prepare_expert = prepare.add_argument_group("expert/fixture inputs")
    prepare_expert.add_argument("--cards-json")
    prepare_expert.add_argument("--claims-json")
    prepare_expert.add_argument("--plan-reports-dir")
    prepare_expert.add_argument("--allow-placeholder", action="store_true")

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
        help="inspected source research manifest stage",
        description="Inspected source research manifest stage.",
    )
    source_manifest.add_argument("--deck-name", required=True)
    source_manifest.add_argument("--deck-code", required=True)
    source_manifest.add_argument("--out", required=True)
    source_manifest.add_argument("--cards-json")
    source_manifest.add_argument("--allow-placeholder", action="store_true")
    source_manifest.add_argument("--json", action="store_true")

    draft_source_documents = subparsers.add_parser(
        "draft-source-documents",
        help="inspected source document drafting stage",
        description="Inspected source document drafting stage.",
    )
    draft_source_documents.add_argument("--deck-name", required=True)
    draft_source_documents.add_argument("--deck-code", required=True)
    draft_source_documents.add_argument("--source-evidence-json", required=True)
    draft_source_documents.add_argument("--out", required=True)
    draft_source_documents.add_argument("--cards-json")
    draft_source_documents.add_argument("--allow-placeholder", action="store_true")
    draft_source_documents.add_argument("--json", action="store_true")

    source_autopilot = subparsers.add_parser(
        "source-autopilot",
        help="inspected source search to strict source documents stage",
        description=(
            "Inspected source search to strict source documents stage. "
            "Consumes compact public source records, ranks them, emits source evidence rows, "
            "drafts strict source_documents.json, and reports whether the input can support "
            "source-backed strong promotion. This command does not write runtime files."
        ),
    )
    source_autopilot.add_argument("--deck-name", required=True)
    source_autopilot.add_argument("--deck-code", required=True)
    source_autopilot.add_argument("--source-search-results-json", required=True)
    source_autopilot.add_argument("--out", required=True)
    source_autopilot.add_argument("--cards-json")
    source_autopilot.add_argument("--allow-placeholder", action="store_true")
    source_autopilot.add_argument("--current-date")
    source_autopilot.add_argument("--json", action="store_true")

    research_deck = subparsers.add_parser(
        "research-deck",
        help="inspected source document normalization stage",
        description="Inspected source document normalization stage.",
    )
    research_deck.add_argument("--deck-name", required=True)
    research_deck.add_argument("--deck-code", required=True)
    research_deck.add_argument("--out", required=True)
    research_deck.add_argument("--cards-json")
    research_deck.add_argument("--source-documents-json")
    research_deck.add_argument("--source-evidence-json")
    research_deck.add_argument("--allow-placeholder", action="store_true")
    research_deck.add_argument("--json", action="store_true")

    acceptance_matrix = subparsers.add_parser(
        "acceptance-matrix",
        help="read-only package acceptance matrix",
        description=(
            "Read one or more prepared HSConfig packages and summarize load-safe "
            "status, runtime files, warning boundaries, and no-block hard stops. "
            "This command is diagnostic only and never writes runtime files."
        ),
    )
    acceptance_matrix.add_argument(
        "--package",
        action="append",
        required=True,
        help="Prepared package directory. Repeat for multiple packages.",
    )
    acceptance_matrix.add_argument("--out", help="Optional JSON output path.")
    acceptance_matrix.add_argument("--json", action="store_true")

    contract_doctor = subparsers.add_parser(
        "contract-doctor",
        help="read-only source-contract diagnostic for prepared packages",
        description=(
            "Read a prepared package and explain source -> claim_kind -> surface "
            "gate -> builder/router -> runtime effect diagnostics. This command "
            "does not grant apply permission and never writes runtime files."
        ),
    )
    contract_doctor.add_argument("--package", required=True)
    contract_doctor.add_argument("--out", help="Optional Markdown output path.")
    contract_doctor.add_argument("--json", action="store_true")

    contract_spine_sentinel = subparsers.add_parser(
        "contract-spine-sentinel",
        help="read-only contract-spine drift diagnostic",
        description=(
            "read-only contract-spine drift diagnostic. Read the current "
            "source-contract policy, conformance snapshot, "
            "diagnostic-only reports, and apply-boundary files to detect drift. "
            "This command does not grant apply permission and never writes runtime files."
        ),
    )
    contract_spine_sentinel.add_argument("--out", help="Optional JSON output path.")
    contract_spine_sentinel.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--package", required=True)
    validate.add_argument("--json", action="store_true")

    apply = subparsers.add_parser(
        "apply",
        description=(
            "Apply a validated pre-run CustomConfig package. "
            "--allow-source-informed is retained as a legacy no-op for diagnostic "
            "compatibility. Normal load-safe packages do not require this flag."
        ),
        epilog=(
            "Legacy diagnostic compatibility: --allow-source-informed is a no-op, "
            "not the normal runtime write gate. Normal load-safe packages do not "
            "require this flag; runtime_apply_mode=load_safe_apply is the "
            "operator-facing write mode."
        ),
    )
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument(
        "--allow-source-informed",
        action="store_true",
        help="Legacy no-op retained for diagnostic compatibility.",
    )
    fake_apply_mode = apply.add_mutually_exclusive_group()
    fake_apply_mode.add_argument(
        "--fake",
        action="store_true",
        help="Create a receipt-bound fake apply without mutating runtime files.",
    )
    fake_apply_mode.add_argument(
        "--from-fake-receipt",
        help="Apply only if the package and runtime match this fake apply receipt.",
    )
    apply.add_argument("--json", action="store_true")
    return parser
