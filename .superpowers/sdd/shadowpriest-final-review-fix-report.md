# ShadowPriest Final-Review Fix Report

Date: 2026-07-24

## RED

- `test_card_named_guide_title_does_not_override_an_unrelated_claim` failed as expected: a `Mind Blast Priest Guide` source title produced `direct_enemy_hero_burn` instead of `semantic_default`.
- `test_config_quality_does_not_accept_nested_surface_intent_row_as_globalvalues_intent` failed as expected: `nested/GlobalValues.json` left the config-intent self-audit `clean` instead of reporting the real `GlobalValues.json` as unexplained.
- Exact-identity taxonomy tests initially failed as expected because `classify_card_intent` did not yet accept `card_identity`.

## GREEN

- Card identity is now passed separately from prose. Named-card shortcuts use exact normalized card IDs or names; `source_title` is excluded from scoring and surface-intent prose. Actual card-text recognizers remain active.
- `surface_intent` can explain a runtime file only through canonical path-free generated rows with the required rule, card/surface, and required/optional-surface agreement. Malformed rows remain non-blocking diagnostics and appear in projection attention.
- The ShadowPriest fallback test now proves every known card has both a meaningful CardID behavior row and a CardID surface-intent row before absence assertions run.

Focused verification:

- `python -m pytest tests\\test_card_intent_taxonomy.py tests\\test_semantic_intent_score.py -q` -> `22 passed`.
- `python -m pytest tests\\test_config_quality_contract.py tests\\test_contract_preflight.py -q` -> `81 passed`.
- `python -m pytest tests\\test_surface_intent.py tests\\test_shadowpriest_e2e.py -q` -> `12 passed`.
- `python -m compileall -q src\\hsconfig` and `git diff --check` -> passed.

## Files Changed

- `.superpowers/sdd/shadowpriest-final-review-fix-report.md`
- `src/hsconfig/card_intent_taxonomy.py`
- `src/hsconfig/semantic_intent_score.py`
- `src/hsconfig/surface_intent.py`
- `src/hsconfig/config_quality_contract.py`
- `tests/test_card_intent_taxonomy.py`
- `tests/test_semantic_intent_score.py`
- `tests/test_config_quality_contract.py`
- `tests/test_contract_preflight.py`
- `tests/test_shadowpriest_e2e.py`

## Commits

- `222d3ebd93f27fc4851accde2a5e0f5a29e14acf` `fix: harden semantic intent diagnostics`

## Residual Concern

- Full `python -m pytest -q` was attempted but exceeded the 120-second command limit and terminated with a Windows stdout `OSError`; the requested focused suites passed. No runtime writes, apply authority, HSTuner integration, logs/replay parsing, or gameplay/performance assertions were added.
