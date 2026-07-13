# Task 2 Report

## Status

DONE_WITH_CONCERNS

## Changed Files

- `src/hsconfig/package_builder.py`: pass the final canonical `guide_claim_bundle` to the research writer.
- `src/hsconfig/research_contract.py`: accept an optional canonical bundle override while preserving the existing research copy.
- `tests/test_guide_claim_bundle_parity.py`: add the package parity sentinel.

## Commits

- Implementation commit: `b230380`.

## Tests

- `python -m pytest tests/test_guide_claim_bundle_parity.py tests/test_report_ownership.py tests/test_research_contract.py tests/test_preconfig_context_parity.py -q` -> `16 passed`.
- `python -m compileall -q src tests` -> passed.
- `git diff --check` -> passed.
- Full `python -m pytest -q` did not complete in this environment; pytest processes remained active after partial progress and were terminated. No failure result was available.

## Self-Review

- The change is limited to Task 2 files and preserves the existing research report for active consumers.
- The normal canonical authority remains `reports/guide_claim_bundle.json`; runtime apply authority remains `reports/operator_summary.json`.
- The writer fallback preserves direct callers that provide the bundle-owned guide claim bundle.

## Concerns

- The brief's exact sentinel command includes `--skip-semantic-fetch`, but this branch's `prepare` CLI does not expose that option. The sentinel omits only that unsupported argument.
- The brief references `tests/test_output_ownership_manifest.py`, which is absent from this checkout, so the combined targeted command could not collect tests.
- Full-suite completion remains unverified because the local pytest run did not terminate normally.

## Review Findings Fix

### Changed Files

- `src/hsconfig/research_contract.py`: when `reports/guide_claim_bundle.json` already exists, copy its raw bytes into the research duplicate; retain the direct-call bundle fallback when no canonical report exists.
- `tests/test_guide_claim_bundle_parity.py`: stub the package card fetch, accept validated pointer metadata, and otherwise require byte-for-byte parity.
- `tests/test_research_contract.py`: add direct-writer coverage for an existing canonical bundle that differs from the embedded fallback object.

### Commit

- `28af188` (`fix: preserve canonical guide claim bundle bytes`).

### Tests Run

- `python -m pytest tests/test_guide_claim_bundle_parity.py tests/test_report_ownership.py tests/test_research_contract.py tests/test_preconfig_context_parity.py -q` -> `17 passed`.
- `python -m compileall -q src tests` -> passed.
- `git diff --check` -> passed.

### Self-Review

- The canonical report takes precedence only when it exists, preserving the legacy direct-call fallback for research-only output paths.
- The research duplicate is copied as bytes rather than re-serialized, so key order, indentation, and trailing-newline drift cannot pass silently.
- The package sentinel cannot access the network because it stubs `hsconfig.package_builder.fetch_latest_cards` before invoking `prepare`.
