# Task 3 Fix Report

## Scope

- Fixed strong-promotion drift for default-only and policy-backed normal runtime surfaces.
- Kept `runtime_apply_allowed=true` for technically valid packages.
- Touched:
  - `src/hsconfig/operator_summary.py`
  - `src/hsconfig/strong_promotion_report.py`
  - `tests/test_operator_summary.py`
  - `tests/test_strong_promotion_report.py`
  - `tests/fixtures/source_documents_shadowpriest_strong.json`

## Root Cause

`_strong_promotion_evidence_blockers()` skipped default-only mulligan evidence when the mulligan report was missing or empty. That let an otherwise source-backed package retain `semantic_status=SOURCE_BACKED_STRONG` even though `config_usefulness` exposed `default_only_runtime_surfaces=["mulligan"]`.

The same helper also counted source-backed/rich surfaces package-wide and skipped `policy_claim_not_strong_evidence` whenever any other surface was rich. That allowed a policy-backed mulligan surface to preserve strong promotion if another surface, such as GlobalValues, was rich.

`strong_promotion_report` also trusted `semantic_status=SOURCE_BACKED_STRONG` too much and did not independently block an operator summary that exposed default-only runtime surfaces.

## TDD Red Evidence

Command:

```powershell
python -m pytest tests/test_operator_summary.py::test_missing_mulligan_report_default_only_surface_blocks_strong_promotion tests/test_operator_summary.py::test_policy_backed_mulligan_blocks_strong_even_when_globalvalues_is_rich tests/test_strong_promotion_report.py::test_report_blocks_default_only_runtime_surface_from_operator_summary -q
```

Observed red output:

```text
3 failed in 0.60s
```

Failures:

- `test_missing_mulligan_report_default_only_surface_blocks_strong_promotion`: expected `VALID_BUT_NOT_GUIDE_STRONG`, got `SOURCE_BACKED_STRONG`.
- `test_policy_backed_mulligan_blocks_strong_even_when_globalvalues_is_rich`: expected `VALID_BUT_NOT_GUIDE_STRONG`, got `SOURCE_BACKED_STRONG`.
- `test_report_blocks_default_only_runtime_surface_from_operator_summary`: expected `promotion_ready is False`, got `True`.

## Fix

- `operator_summary.py`
  - Removed the missing-mulligan-report skip for default-only surfaces.
  - Removed the package-wide source-backed/rich surface suppression for policy-backed surfaces.
  - Removed the obsolete helper functions that supported those skips.
- `strong_promotion_report.py`
  - Adds report-level blockers from `operator_summary["default_only_runtime_surfaces"]`.
  - Prevents `static_contract_status=SOURCE_BACKED_STRONG` when any semantic/default-only/normal-path blocker is present.
- `tests/fixtures/source_documents_shadowpriest_strong.json`
  - Added explicit source-backed mulligan claims for Voidtouched Attendant and Shadowbomber from the fixture's existing Out of Games guide source, so ShadowPriest remains a truthful core source-backed fixture without relying on policy-backed mulligan rows.

## Green Evidence

Focused green:

```powershell
python -m pytest tests/test_operator_summary.py::test_missing_mulligan_report_default_only_surface_blocks_strong_promotion tests/test_operator_summary.py::test_policy_backed_mulligan_blocks_strong_even_when_globalvalues_is_rich tests/test_strong_promotion_report.py::test_report_blocks_default_only_runtime_surface_from_operator_summary -q
```

```text
3 passed in 0.17s
```

Required suite:

```powershell
python -m pytest tests/test_operator_summary.py tests/test_strong_fixture_closure.py tests/test_strong_promotion_report.py -q
```

```text
100 passed, 2 skipped in 11.71s
```

Additional fixture truth check:

```powershell
python -m pytest tests/test_fixture_source_depth_closure.py tests/test_matrix_current_truth.py -q
```

```text
11 passed in 10.77s
```

Whitespace:

```powershell
git diff --check
```

```text
exit code 0; no whitespace errors. Git printed only LF-to-CRLF working-copy warnings.
```

## Commit

Fix commit:

```text
a12ddad162dd6793e3fcad18d194eb256725e444 fix: block policy and default-only strong drift
```

## Concerns

- `tests/fixtures/source_documents_shadowpriest_strong.json` was updated because the required fixture closure test proved ShadowPriest had been relying on policy-backed mulligan rows. The added mulligan claims are backed by the fixture's existing public guide source.

## Task 3 Source Extractor Boundary Fix

### TDD Red Evidence

Command:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

Observed red output:

```text
3 failed, 3 passed
```

The failures covered `candidate_only`, `candidate_partial`, and disjoint card/hero-power mentions producing claims.

### Fix

- `source_text_claim_extractor.py` now permits full-text guide extraction only when `source_record_strength == "candidate_strong"`.
- `hero_power_transform` now requires a bounded same-sentence association between the named card, a transformation verb, and `hero power`, `Mind Spike`, or `Shadowform`.
- Card metadata and document-wide disjoint mentions no longer establish a transform claim.
- Existing Papercraft keep, `SW_448` 4-cost discard, explicit Darkbishop-to-Mind-Spike transform, and `decklist_only` behavior remain covered.

### Green Evidence

```text
6 passed in 0.09s
```

### Commit

Implementation commit SHA: `74fcfa4936b18cecd82d354ef0fd5be0d2c523ee`

Changed files:

- `src/hsconfig/source_text_claim_extractor.py`
- `tests/test_source_text_claim_extractor.py`
- `.superpowers/sdd/task-3-fix-report.md`

### Concerns

- The transform matcher intentionally accepts only bounded same-sentence wording with explicit transformation verbs; differently worded guide prose may require a future targeted pattern and test.
