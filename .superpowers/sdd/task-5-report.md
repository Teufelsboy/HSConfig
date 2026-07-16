# Task 5 Report: Preserve Darkbishop Effect-Not-Mulligan Canary

## Status

DONE

## Scope completed

- Added one protective E2E canary in `tests/test_shadowpriest_e2e.py`.
- The canary prepares the existing ShadowPriest strong source fixture and proves:
  - `reports/operator_summary.json` reports `semantic_status` as `SOURCE_BACKED_STRONG`.
  - `CustomConfig/shadowpriest/Mulligan.json` contains no `SW_448` entry.
  - `CustomConfig/shadowpriest/SW_448.json` retains the Mind Spike hero-power behavior through `BeforeUseHeroPowerBonus` (or an explicit `hero_power_transform` marker).

## Production-code decision

No production files changed. The existing source-lowering and autonomous Mulligan policy paths already preserve the required distinction: Darkbishop Benedictus remains an emitted start-of-game hero-power effect but is not inferred as an opening-hand keep without explicit source text.

## Verification

Required canary command:

```powershell
python -m pytest tests/test_shadowpriest_e2e.py tests/test_claim_kind_runtime_contract.py -q
```

Result:

```text
55 passed in 15.61s
```

The canary did not fail, so the conditional follow-up run including `tests/test_autonomous_mulligan_policy.py` was not required. `git diff --check` completed without whitespace errors before commit.

## Constraints preserved

- HSConfig remains pre-run only; no replay, winrate, HSTuner, or post-game logic was added.
- `operator_summary.json` remains the normal apply authority.
- `SOURCE_BACKED_STRONG` is tested as source-confidence only, not as a runtime apply gate.
- No source-confidence promotion rules or source schema changed.
- Normal output behavior for `Presume.json`, `Concede.json`, and aggregate `CardBehavior.json` was not changed.

## Commit

`afc1388706857d541a31c83e6e0817bef4d9a657 test: preserve darkbishop effect not mulligan canary`
