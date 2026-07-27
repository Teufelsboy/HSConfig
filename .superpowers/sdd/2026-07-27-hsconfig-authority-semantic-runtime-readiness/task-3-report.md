# Task 3 Report: Sideboard Identity Through Metadata and Readiness

## Status

PASS

MechPala keeps its 30-card main-deck identity and three-card sideboard identity. The three `TOY_330` modules are analysis-only records in semantic metadata, config readiness, source-contract audit, and source-to-runtime explainability. They remain runtime-ineligible and do not create CardID files.

## Files

- `src/hsconfig/deckstring_decode.py`
- `src/hsconfig/preconfig_context.py`
- `src/hsconfig/card_metadata.py`
- `src/hsconfig/config_readiness.py`
- `src/hsconfig/source_contract_audit.py`
- `src/hsconfig/source_to_runtime_explainability.py`
- `tests/test_deckstring_decode.py`
- `tests/test_card_metadata.py`
- `tests/test_config_readiness.py`
- `tests/test_multideck_source_backed_e2e.py`

`source_contract_audit.py` only passes through the three approved fields: `deck_zone`, `sideboard_owner_card_id`, and `runtime_eligible`.

## RED

- Deck decode: missing `card_count` alias and unpadded MechPala/PirateDH codes failed with `Incorrect padding`.
- Card metadata: `analysis_cards_from_deck_identity` did not exist.
- Config readiness: sideboard analysis rows and `analysis_only_sideboard_cards` were absent.
- MechPala prepare: modules were absent from semantic metadata and later from explainability annotations.
- Explainability summary initially counted sideboard `first_missing_link="none"` rows as missing.

## GREEN

- Required suite:
  - `python -m pytest -q -p no:cacheprovider tests/test_deckstring_decode.py tests/test_card_metadata.py tests/test_config_readiness.py tests/test_multideck_source_backed_e2e.py tests/test_autonomous_mulligan_policy.py`
  - 65 passed.
- Additional regression suite:
  - `python -m pytest -q -p no:cacheprovider tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py tests/test_preconfig_context_parity.py`
  - 43 passed.
- `git diff --check`: clean.

## Commit

`feat: preserve sideboard identity through readiness` (this commit)

## Self-Review

- Main-deck `card_count_total`, guide coverage denominator, and readiness `total_cards` remain main-deck-only.
- Sideboard modules carry `deck_zone="sideboard"`, `sideboard_owner_card_id="TOY_330"`, and `runtime_eligible=false`.
- Sideboard readiness and explainability use `runtime_surfaces=[]`, `readiness_lane="report_only_supported"`, and `first_missing_link="none"`.
- `TOY_330` receives `sideboard_owner` and `deckbuilding_modifier`; the latter uses the existing mulligan safety exclusion so its printed zero cost cannot become the lowest-curve fallback.
- No `TOY_330t95.json`, `TOY_330t98.json`, or `TOY_330t11.json` runtime file is generated.
- Legacy synthetic explainability rows keep their previous shape unless the audit explicitly provides zone annotations.

## Concerns

None blocking. No runtime writes, HSTuner actions, desktop HearthRanger actions, branches, worktrees, or pushes were performed.

## Fix Round 1

### Status

PASS

Both Important findings from `task-3-quality-review.md` are resolved:

- Runtime-ineligible sideboard rows now form a terminal report-only lane throughout explainability. Their closure lane is `report_only`, lowering status is `report_only_supported`, next source actions are `none`, default-only risk is false, and operator attention is `report_only`.
- Analysis-card collection now aggregates duplicate CardIDs without losing identity. A main-deck record remains the single authoritative runtime-capable row when the same CardID also appears in a sideboard, while separate `sideboard_owner_card_ids` and `sideboard_memberships` retain all sideboard linkage. Repeated sideboard-only CardIDs likewise retain every owner without creating duplicate analysis rows.

The added sideboard linkage fields are passed through metadata, readiness, source-contract audit, and source-to-runtime explainability.

### Files

- `src/hsconfig/card_metadata.py`
- `src/hsconfig/config_readiness.py`
- `src/hsconfig/preconfig_context.py`
- `src/hsconfig/source_contract_audit.py`
- `src/hsconfig/source_to_runtime_explainability.py`
- `tests/test_card_metadata.py`
- `tests/test_config_readiness.py`
- `tests/test_multideck_source_backed_e2e.py`

### RED

- Cross-zone duplicate regression showed the sideboard row overwriting the main-deck record.
- Repeated sideboard-card regression showed last-owner-wins loss.
- Cross-zone readiness regression showed a one-card denominator instead of two authoritative cards.
- MechPala explainability regression showed runtime-ineligible rows ending in `explicit_gap` with source action needed.
- Focused RED result: 4 failed.

### GREEN

- Focused regression command:
  - `python -m pytest -q -p no:cacheprovider tests/test_card_metadata.py tests/test_config_readiness.py tests/test_multideck_source_backed_e2e.py -k 'cross_zone or repeated_sideboard or sideboard_cards_are_visible or multideck_source_backed_prepare and MechPala'`
  - 5 passed, 50 deselected.
- Combined Task 3 suite:
  - `python -m pytest -q -p no:cacheprovider tests/test_deckstring_decode.py tests/test_card_metadata.py tests/test_config_readiness.py tests/test_multideck_source_backed_e2e.py tests/test_autonomous_mulligan_policy.py tests/test_source_contract_audit.py tests/test_source_to_runtime_explainability.py tests/test_preconfig_context_parity.py`
  - 111 passed.
- `git diff --check`: clean.

### Commit

`fix: make sideboard analysis non-lossy` (separate Fix-Round-1 commit)

### Self-Review

- One CardID produces one analysis row.
- Main-deck runtime authority wins cross-zone collisions.
- Sideboard linkage remains visible as a separate, lossless relationship.
- Report-only rows cannot contradict themselves through nested closure or operator-attention fields.
- Main-deck guide metadata remains restricted by `deck_zone="main"`.
- Minor review findings remain deferred as requested.

### Concerns

None blocking. No runtime writes, HSTuner actions, desktop HearthRanger actions, branches, worktrees, or pushes were performed.
