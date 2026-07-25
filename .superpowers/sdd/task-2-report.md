# Task 2 Report: Strict Research Result Contract Classifier

## Status

DONE

## Scope

- Added `src/hsconfig/research_result_contract.py` with a pure-Python classifier.
- Updated `src/hsconfig/research_status_sync.py` to append contract diagnostics to each research snapshot row.
- Added and updated focused tests in `tests/test_research_result_contract.py` and `tests/test_research_status_sync.py`.
- No runtime package, `reports/operator_summary.json`, or HearthRanger runtime file was written.
- No `--apply` command was run.

## Contract Behavior Implemented

- Missing deck identity returns `contract_valid=false` and `snapshot_kind="invalid"`.
- Seed strengths, including `unfetched_acquisition_seed`, remain `seed_only` and non-promoting.
- Snippet-only evidence is `partial` and non-promoting, never a URL-seed or strong proof surrogate.
- Strong status or strength requires `first_missing_source_action="none"`, accepted lowerable claim kinds, and full-text or explicit canonical evidence before it becomes promotion-eligible.
- Strong-looking but incomplete input is classified as `partial`.
- Canonical downgrade and source-status apply blocking are always `false`.
- The classifier recognizes a strong marker from any supported status/strength field, not merely the first populated one.
- `research-status-sync` stays diagnostic-only and preserves `reports/operator_summary.json` as the normal apply authority.

## TDD Evidence

### RED

1. Before the module existed:

```text
ModuleNotFoundError: No module named 'hsconfig.research_result_contract'
```

2. Before checking all source status/strength fields:

```text
AssertionError: assert 'partial' == 'strong'
```

Both failures were expected and directly exercised the missing behavior.

### GREEN

Focused Task 2 verification:

```powershell
python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py -q -p no:cacheprovider
```

Result: `16 passed`.

Final regression command:

```powershell
python -m pytest tests\test_research_result_contract.py tests\test_research_status_sync.py tests\test_source_status_resolver.py tests\test_source_acquisition.py tests\test_source_text_claim_extractor.py tests\test_universal_wild_no_block_matrix.py -q -p no:cacheprovider
```

Result: `73 passed in 18.05s`.

Additional syntax verification:

```powershell
python -m compileall -q src\hsconfig\research_result_contract.py src\hsconfig\research_status_sync.py
```

Result: passed.

## Diff Review

- `git diff --check` passed; only Git's existing LF-to-CRLF informational warnings were emitted.
- The existing untracked plan file `docs/superpowers/plans/2026-07-18-hsconfig-live-source-strong-config-closure.md` was preserved unchanged.
- No commit was created.

## Concerns

- None. The classifier intentionally reports promotion eligibility only as a diagnostic input signal; it does not modify canonical package status resolution or apply gating.
