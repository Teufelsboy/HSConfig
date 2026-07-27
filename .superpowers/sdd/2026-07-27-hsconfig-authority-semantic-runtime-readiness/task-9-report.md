# Task 9 Report — Fixture Safety and Current Apply Authority

Separated captured fixture expectations from productive current-package apply
authority.

Implemented:

- Removed `runtime_apply_allowed` from all 11 representative fixture rows.
- Added `fixture_expected_load_safe=true` and
  `fixture_runtime_apply_authority=diagnostic_only` to all 11 representative
  rows and all three supplemental rows.
- Preserved CuteWarrior's `proof_scope=supplemental_load_safe_only` and
  `representative_output_competence=false`.
- Added stable `runtime_apply_reason` values to the productive operator summary.
- Extended `runtime_apply_contract` with
  `authority_scope=current_package_operator_gate` while retaining
  `apply_authority=reports/operator_summary.json`.
- Documented that historical/captured fixtures cannot authorize a current
  runtime write.
- Proved both sides of the boundary: diagnostic-source representative prepares
  remain load-safe but apply-ineligible, while a freshly prepared supplemental
  CuteWarrior package can still pass the current package operator gate without
  deck-name special casing.

TDD evidence:

- Initial focused run failed five tests on the missing fixture and operator
  fields.
- A second RED case showed that an invalid package must take precedence over a
  diagnostic-source reason.
- GREEN verification passed after the minimal production and fixture changes.

Verification:

- `137 passed` across operator summary, representative matrix, and supplemental
  fixture tests.
- Multi-deck source-backed E2E passed in bounded groups: `18 + 1 + 1 + 1`.
- Universal Wild regression matrix: `35 passed`.
- Active-path documentation regression: `1 passed`.
- Targeted Ruff: clean.
- Both JSON manifests parsed successfully.
- `git diff --check`: clean apart from Git's existing LF-to-CRLF notices.

The repository-wide contract guardrail wrapper completed its skill-sync and
contract-spine checks successfully. Its focused legacy boundary group reported
`868 passed, 80 failed` before the directly caused documentation expectation
was repaired and re-run green. The remaining observed failures are existing
Task-8 integration drift, dominated by old package fixtures missing
`runtime_surface_ledger`, plus old closure-lane expectations outside Task 9.
They were not widened into this task.

No runtime, HSTuner, HearthRanger Desktop, or runtime write path was used.
