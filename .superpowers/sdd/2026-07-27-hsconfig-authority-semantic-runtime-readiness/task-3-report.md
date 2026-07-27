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
