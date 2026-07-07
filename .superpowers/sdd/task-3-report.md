# Task 3 Report: Curated Linked-Entity Supplement

## Scope

- Added deterministic, source-last curated linked-entity supplement support.
- Kept scope limited to the Task 3 files.
- Did not add sideboard handling, token graph expansion, or broader closure logic.

## RED Evidence

Command:

```powershell
python -m pytest tests/test_option_identity_resolver.py -q
```

Result:

- Exit code: `1`
- Failure mode: `resolve_linked_entities() got an unexpected keyword argument 'supplement_links'`
- Failing tests:
  - `test_curated_supplement_adds_missing_link_source_last`
  - `test_upstream_link_wins_over_curated_duplicate`

## GREEN Evidence

Command:

```powershell
python -m pytest tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py -q
```

Result:

- Exit code: `0`
- Summary: `10 passed in 0.07s`

## Changes

- Created [src/hsconfig/linked_entity_supplement.py](/C:/Users/darbo/Documents/HSConfig/src/hsconfig/linked_entity_supplement.py)
  - Added the small curated supplement map for `SW_448` and `EX1_625`.
- Updated [src/hsconfig/option_identity_resolver.py](/C:/Users/darbo/Documents/HSConfig/src/hsconfig/option_identity_resolver.py)
  - Added optional `supplement_links`.
  - Appends curated rows only when no equivalent upstream `(link_kind, card_id)` link exists.
- Updated [src/hsconfig/semantic_enrichment.py](/C:/Users/darbo/Documents/HSConfig/src/hsconfig/semantic_enrichment.py)
  - Builds a deck-local curated supplement map.
  - Passes it into the resolver.
  - Accepts `hero_power_transform` as a valid starting hero power link for Shadowform resolution.
- Updated tests in:
  - [tests/test_option_identity_resolver.py](/C:/Users/darbo/Documents/HSConfig/tests/test_option_identity_resolver.py)
  - [tests/test_semantic_enrichment.py](/C:/Users/darbo/Documents/HSConfig/tests/test_semantic_enrichment.py)

## Notes

- Existing semantic enrichment expectations for Darkbishop were updated to reflect the new source-last curated supplement behavior.
- Fallback warning behavior remains unchanged for cases where neither upstream data nor curated supplement provides the linked entity.

## Review Fix Addendum

### Finding 1: Pre-existing upstream links must suppress curated fallback duplicates

Change:

- Updated [src/hsconfig/semantic_enrichment.py](/C:/Users/darbo/Documents/HSConfig/src/hsconfig/semantic_enrichment.py) so linked-entity merge equivalence is keyed by `(link_kind, card_id)` instead of `(link_kind, card_id, source)`.
- This preserves the pre-existing upstream row and blocks a curated supplement row for the same semantic target, matching source-last behavior.

### Finding 2: Regression coverage for upstream `hero_power_transform -> EX1_625t`

Change:

- Added `test_existing_upstream_hero_power_transform_suppresses_curated_duplicate()` to [tests/test_semantic_enrichment.py](/C:/Users/darbo/Documents/HSConfig/tests/test_semantic_enrichment.py).
- The test feeds a card with an existing upstream `linked_entities` row for `hero_power_transform -> EX1_625t` and asserts the enriched result keeps exactly that row with no curated duplicate.

### RED Evidence

Command:

```powershell
python -m pytest tests/test_semantic_enrichment.py -q
```

Result:

- Exit code: `1`
- Failure: `test_existing_upstream_hero_power_transform_suppresses_curated_duplicate`
- Cause: enriched output still contained both the upstream row and the curated supplement row for the same `(link_kind, card_id)` target.

### GREEN Evidence

Command:

```powershell
python -m pytest tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py -q
```

Result:

- Exit code: `0`
- Summary: `11 passed in 0.07s`

### Required Verification Suite

Command:

```powershell
python -m pytest tests/test_option_identity_resolver.py tests/test_semantic_enrichment.py tests/test_gameplan_contract.py tests/test_shadowpriest_e2e.py tests/test_semantic_audit.py -q
```

Result:

- Exit code: `0`
- Summary: `22 passed in 7.23s`
