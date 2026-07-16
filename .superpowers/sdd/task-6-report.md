# Task 6 Report: Explainability and First Missing Source Action

Status: DONE

## Files Changed

- `src/hsconfig/source_to_runtime_explainability.py`
- `tests/test_source_to_runtime_explainability.py`
- `.superpowers/sdd/task-6-report.md`

`src/hsconfig/source_claim_gap_report.py` and `tests/test_source_claim_gap_report.py` were exercised by the focused test run but did not need code changes.

## Implementation

- Added a policy-backed autonomous mulligan regression that covers compact `audit={claim_rows: [...]}` input plus `runtime_files`.
- Kept the existing positional `source_contract_audit_report` input path working.
- Added per-card `source_lane`, `first_missing_source_action`, and `runtime_lowering_status`.
- Mirrored the same three fields into `operator_attention` so the operator-facing row names the source lane, the first missing source action, and the runtime lowering state.
- Preserved legacy `best_source_lane`, `next_source_action`, and `closure` fields.

## Red Evidence

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Result before implementation:

```text
1 failed, 22 passed in 0.33s
```

Failure:

```text
TypeError: build_source_to_runtime_explainability_report() got an unexpected keyword argument 'audit'
```

## Green Evidence

Focused task tests:

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py -q
```

Result:

```text
23 passed in 0.34s
```

Directly relevant operator/closure tests:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_source_contract_closure_wave.py -q
```

Result:

```text
91 passed in 14.79s
```

## Concerns

- The red test initially failed at the new compact interface boundary rather than at field lookup. That still proves the requested compact source-policy explainability path was absent before implementation.
- Pre-existing unrelated working-tree edits remain untouched in docs and skill files outside this task scope.

## Review Follow-up: Legacy Policy Fallback Preservation

### RED

Added a regression that creates a source-contract audit from a
`policy_backed_autonomous_mulligan` `mulligan_keep` claim with
`source_lane=policy_fallback`, emits `Mulligan.json`, and passes that audit
through the legacy positional explainability interface.

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py::test_explainability_preserves_policy_fallback_from_legacy_audit_report -q
```

Before the fix: `1 failed in 0.29s`.

The legacy row was incorrectly projected as `source_lane=runtime_lowered`
because `build_source_contract_audit()` discarded the original source metadata.

### GREEN

`build_source_contract_audit()` now carries `source_type` and `source_lane`
from each original claim into its canonical `claim_rows` projection. The
existing explainability enrichment therefore retains the policy fallback
without inventing source-backed evidence.

The regression now verifies:

- `source_lane=policy_fallback`
- `first_missing_source_action=add_explicit_mulligan_source`
- `runtime_lowering_status=policy_backed_runtime`

### Files Changed

- `src/hsconfig/source_contract_audit.py`
- `tests/test_source_to_runtime_explainability.py`
- `.superpowers/sdd/task-6-report.md`

### Tests

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py::test_explainability_preserves_policy_fallback_from_legacy_audit_report -q
# 1 passed in 0.11s

python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py tests/test_operator_summary.py tests/test_source_contract_closure_wave.py -q
# 115 passed in 15.14s

git diff --check
# exit 0
```

### Concerns

- This remains diagnostic-only: no apply gate or deck-blocking behavior was added.
- Pre-existing unrelated working-tree edits remain untouched.

## Review Follow-up: Mulligan Claim-Kind Boundary

### RED

Added a compact-path regression with `source_type=policy_backed_autonomous_mulligan`,
`claim_kind=card_role`, and runtime evidence. Before the production fix:

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py::test_explainability_does_not_treat_policy_fallback_non_mulligan_as_mulligan -q
# 1 failed in 0.24s
# expected first_missing_source_action=none, got add_explicit_mulligan_source
```

### GREEN

Narrowed `_has_policy_backed_mulligan()` so policy-backed explainability fallback
requires both `source_type=policy_backed_autonomous_mulligan` and
`claim_kind=mulligan_keep`. The regression now confirms non-mulligan claims use
ordinary source-backed runtime values:

- `first_missing_source_action=none`
- `runtime_lowering_status=source_backed_runtime`

### Files Changed

- `src/hsconfig/source_to_runtime_explainability.py`
- `tests/test_source_to_runtime_explainability.py`
- `.superpowers/sdd/task-6-report.md`

### Tests

```powershell
python -m pytest tests/test_source_to_runtime_explainability.py -q
# 14 passed in 0.13s

python -m pytest tests/test_source_to_runtime_explainability.py tests/test_source_claim_gap_report.py tests/test_operator_summary.py tests/test_source_contract_closure_wave.py -q
# 116 passed in 14.13s

git diff --check
# exit 0
```

### Concerns

- The predicate intentionally keeps policy fallback specific to explicit
  `mulligan_keep` claims; other claim kinds retain normal source-backed status.
- Pre-existing unrelated working-tree edits remain untouched in docs and skill files outside this task scope.

---

# Task 6 Report: Surface Profile Closure In Reports And Skill Guidance

Status: DONE

## Scope

- Added the requested profile-closure fields to the compact diagnostic report.
- Added a focused ShadowPriest strong-fixture regression test.
- Added the exact profile-aware Strong closure rule to the repository skill.
- Synced the repository skill to the installed skill location.

## Implementation

`build_source_evidence_closure_report()` now reads
`operator_summary["source_backed_strong_closure"]` when present and exposes:

- `closure_profile`, defaulting to `"unknown"`
- `closure_profile_closed`, defaulting to `false`
- `closure_profile_first_missing_link`, defaulting to `"unknown"`

The compact report remains diagnostic-only. `operator_summary.json` remains the
only normal apply authority; profile closure is source confidence, not a runtime
apply gate.

## Regression Evidence

### Red

```powershell
python -m pytest tests/test_source_evidence_closure.py::test_source_evidence_closure_reports_profile_verdict -q
```

Before the implementation: `1 failed in 10.48s`.

Expected failure:

```text
KeyError: 'closure_profile'
```

### Green

```powershell
python -m pytest tests/test_source_evidence_closure.py::test_source_evidence_closure_reports_profile_verdict -q
# 1 passed in 10.45s

python -m pytest tests/test_source_evidence_closure.py tests/test_skill_sync.py -q
# 5 passed in 10.84s
```

## Installed Skill Sync

```powershell
python scripts\sync_installed_skill.py
# Synced HSConfig skill to C:\Users\darbo\.codex\skills\hsconfig

python scripts\sync_installed_skill.py --check
# HSConfig skill is in sync: C:\Users\darbo\.codex\skills\hsconfig
```

The installed skill was updated outside the repository and is intentionally not
included in the repository commit.

## Scope Check

Changed repository files:

- `.agents/skills/hsconfig/SKILL.md`
- `src/hsconfig/source_evidence_closure.py`
- `tests/test_source_evidence_closure.py`
- `.superpowers/sdd/task-6-report.md`

No runtime apply behavior, source schema, replay analysis, winrate logic,
HSTuner logic, or post-game tuning behavior was changed.

## Concerns

None.

## Review Follow-up: Report History Preservation

The pre-Task-6 report history from commit `1534332` is preserved above. This Surface Profile Closure report is appended without replacing prior policy-fallback or mulligan claim-kind findings.
