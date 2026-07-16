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
