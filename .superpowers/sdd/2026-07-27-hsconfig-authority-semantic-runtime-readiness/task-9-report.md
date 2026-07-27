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

## Fix Round 1

Closed the integration findings that remained after the initial Task 9
implementation:

- A technically valid diagnostic-source package now exposes one coherent
  blocked operator tuple:
  `runtime_apply_mode=blocked`, `runtime_apply_allowed=false`,
  `runtime_apply_reason=diagnostic_source_not_apply_eligible`,
  `apply_policy=BLOCKED`, and
  `next_action=ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY`.
- `no_block_failure_mode_summary` mirrors that tuple without turning it into a
  technical hard block. Operator guidance now requests a live-verified
  exact-deck source instead of presenting a generic package-repair path.
- `fixture_classification=load_safe_fixture` is emitted only for a technically
  valid diagnostic/captured fixture. It is descriptive output, separate from
  `runtime_load_safe`, and is never consumed as gate authority.
- The universal matrix now derives the exact analysis-card universe from main
  deck cards plus allowed sideboards and checks linked runtime entities through
  the derivation receipt. Arbitrary report supersets no longer pass.
- Legacy apply test packages now install the current schema-2 runtime-surface
  ledger contract. Empty physical CardID behaviors were replaced with honest
  metadata-only fixtures, linked-owner fixtures use a verified matching
  deckstring, and stale-receipt tests mutate only valid physical content.
- ShadowPriest and no-default-only expectations now use the current closure
  lanes.
- The source-backed closure document marks its fixture and blocker tables as
  dated historical snapshots, not present promotion or apply truth.

Fix-round verification:

- `scripts/check_contract_guardrails.py`: `949 passed`; installed-skill sync,
  contract-spine sentinel, and focused contract-boundary checks all reported
  `OK`.
- Runtime apply: `66 passed`.
- Operator documentation, policy, skill, and current-truth contracts:
  `168 passed`.
- Apply gate: `35 passed`; apply-authority boundary: `8 passed`.
- Targeted Ruff: clean.
- Operator JSON manifests parsed successfully.
- `git diff --check`: clean apart from Git's existing LF-to-CRLF notices.

No runtime, HSTuner, HearthRanger Desktop, or runtime write path was used in
the fix round.

## Fix Round 2

Closed the remaining operator-document and acceptance-matrix parity findings:

- Consolidated the Quick Start to seven bullets while preserving the complete
  diagnostic-source semantics and HSTuner ownership statement.
- Acceptance rows now mirror `runtime_load_safe`, `runtime_apply_reason`,
  `apply_policy`, and `fixture_classification` from the operator summary.
- A package blocked solely by a fully consistent
  `diagnostic_source_not_apply_eligible` provenance veto is classified as
  `diagnostic_source_apply_ineligible`. It remains matrix-failed and
  apply-ineligible, but does not mint a technical hard block.
- The exemption requires exact agreement between operator summary,
  `no_block_failure_mode_summary`, and the recomputed apply gate. Invalid,
  load-unsafe, inconsistent, or otherwise technically blocked packages remain
  hard-blocking.
- The real diagnostic-source ShadowPriest configuration path proves
  `technical_hard_block_count=0`, no
  `technical_hard_block_present` failure reason, and retained
  blocked/false/diagnostic apply fields.
- Updated the ShadowPriest regression's pre-existing closure expectations to
  the current runtime-lowering lane.

Fix-round verification:

- Acceptance, operator-guidance, and ShadowPriest acceptance suites:
  `31 passed`.
- Full contract guardrail: exit code `0`.
- Targeted Ruff and `git diff --check`: clean.

No runtime, HSTuner, HearthRanger Desktop, or runtime write path was used in
the fix round.
