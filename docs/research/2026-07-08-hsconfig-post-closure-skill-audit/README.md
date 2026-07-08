# HSConfig Post-Closure Skill Audit, 2026-07-08

This research-deep audit checks whether HSConfig is still narrow, simple,
efficient, and competent after the latest source-depth closure and polish work.

## Verdict

HSConfig is functionally aligned with the intended product boundary:

- It remains a pre-run HearthRanger VisionAI CustomConfig generator.
- The normal path is still `source-manifest -> draft-source-documents -> research-deck -> prepare -> apply`.
- `reports/operator_summary.json` remains the single normal operator gate.
- Normal runtime output remains limited to `GlobalValues.json`, `Mulligan.json`, per-card CardID JSON, and justified `Combo.json`.
- Replay parsing, winrate, post-game tuning, HSTuner candidate promotion, `Presume.json`, and `Concede.json` remain outside the normal path.
- Every deck card is expected to land in a visible source-depth lane or a concrete first missing link.

The main remaining gap is maintainability pressure, not runtime correctness:
`src/hsconfig/cli.py` is still large, and the growing `docs/research` tree should
stay indexed as evidence rather than become operator guidance.

## Eleven-Deck Matrix Truth

The representative deck matrix should not be widened yet.

- 9 decks are `core_source_backed_fixture`.
- 2 decks are intentionally `source_informed_valid_fixture`.
- Kingslayer remains blocked by the Quick Pick mulligan/source condition chain.
- Boarlock remains the highest-priority closure target because it carries the
  deepest blocker stack, including runtime-surface and Fracking mulligan gaps.

## Recommended Next Work

1. Keep the current HSConfig boundary unchanged.
2. Close Boarlock first, then Kingslayer, before adding more representative decks.
3. Keep source-informed apply narrow: guide-claim and mulligan-claim gaps only.
4. Do one targeted maintainability pass later: continue moving command-specific
   orchestration out of `src/hsconfig/cli.py`, and keep research archives indexed.
5. Expand runtime-surface competence only through documented-safe lowering,
   option identity resolution, and claim-specific CardID behavior support.

## Evidence

All six research result files passed the local research schema validator with
100 percent field coverage. The full test suite also passed:

```text
494 passed, 2 skipped
```
