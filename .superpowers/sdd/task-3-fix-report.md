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

## Task 3 Second-Fix: Direct Hero Power Association

### TDD Red Evidence

Added `test_same_sentence_disjoint_clauses_do_not_create_transform_claim` for:

```text
Darkbishop Benedictus changes the matchup; Mind Spike is the hero power to use.
```

Before the matcher change, the required focused command reported:

```text
1 failed, 6 passed
```

The failure confirmed that same-sentence but semantically disjoint clauses still emitted a `hero_power_transform` claim.

### Fix

- Replaced the sentence-wide co-occurrence matcher with card-first direct-association patterns.
- Accepted explicit `change`, `turn`, `transform`, `upgrade`, and `replace` forms when their direct object is `hero power`, `Mind Spike`, or `Shadowform`.
- Accepted the explicit `hero power into/to Mind Spike|Shadowform` construction.
- Disjoint clauses such as `changes the matchup; Mind Spike ...` no longer qualify because `the matchup` is not an allowed direct object.

### Green Evidence

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

```text
7 passed in 0.09s
```

The existing positive `Darkbishop Benedictus changes your hero power into Mind Spike` test remains green.

### Commit

Implementation commit SHA:

```text
12f2713544009e5fe89c18f9ced6c4d82eb0a397 fix: require direct hero power transform claims
```

## Task 3 Final Fix: Direct Transform Wording and Gate Coverage

### TDD Red Evidence

Command:

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

Observed red output:

```text
1 failed, 8 passed in 0.20s
```

The failing regression was `test_hero_power_strategy_is_not_a_direct_transform_claim`: the previous matcher accepted `Darkbishop Benedictus changes your hero power strategy.` because it stopped matching immediately after `hero power`. The decklist and stats/snippet no-claim fixtures were also upgraded to strong source metadata, including deck-match metadata and keep/transform wording, so their rejection exercises family/visibility gates independently of source strength.

### Fix

- The matcher now accepts a bare direct `hero power` object only when it is not followed by another noun, while retaining explicit `into/to Mind Spike|Shadowform` targets.
- Direct named targets such as `changes into Shadowform` remain supported.
- Added explicit positive coverage for `Darkbishop Benedictus changes your hero power into Shadowform.`
- Added the requested negative coverage for `hero power strategy`.

### Green Evidence

```powershell
python -m pytest -p no:cacheprovider tests\test_source_text_claim_extractor.py -q
```

```text
9 passed in 0.09s
```

### Latest Implementation Commit

```text
948a4e6c70500c89c2eb2f5040750942c00ae45d fix: harden direct transform text matching
```
