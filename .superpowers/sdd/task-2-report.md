# Task 2 Report

## Status

DONE_WITH_CONCERNS

## Files Changed

- `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/fields.yaml`
- `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/outline.yaml`
- `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Kingslayer_Quick_Pick_Mulligan_Closure.json`
- `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Boarlock_Fracking_Mulligan_Closure.json`
- `.superpowers/sdd/task-2-report.md`

## Sources Checked

### Kingslayer Quick Pick closure

- `https://www.hsguru.com/deck/36080717`
  - Exact public deck page for the provided Kingslayer fixture deck. Confirms `Quick Pick` is in the list but does not expose an explicit public mulligan instruction in the accessible page body.
- `https://www.reddit.com/r/wildhearthstone/comments/1p8sp6f/legend_1478_kingsbane_rogue/`
  - Current public Kingsbane post with explicit mulligan advice, but for a different Kingsbane list without `Quick Pick`.
- `https://us.forums.blizzard.com/en/hearthstone/t/is-weapon-rogue-actually-good/139684`
  - Public weapon rogue discussion with explicit `Quick Pick` mulligan language: "If you don't find either a quick pick or the 1-mana tutor spell, you can go next." Useful as adjacent evidence only, not as source-backed promotion for the provided Kingslayer deck.

### Boarlock Fracking closure

- `https://www.hsguru.com/deck/39985498`
  - Exact public deck page for the provided Boarlock fixture deck. Confirms `Fracking` is in the list but does not expose an explicit public mulligan instruction in the accessible page body.
- `https://www.reddit.com/r/wildhearthstone/comments/1oy5brn/mulligan_advice_for_boarlock/`
  - Public Boarlock mulligan thread. It discusses combo pieces, early clears, and card draw, but no accessible comment explicitly says keep or discard `Fracking`.
- `https://us.forums.blizzard.com/en/hearthstone/t/sludgelock-is-a-top-100-deck/133621`
  - Public warlock guide/discussion with explicit `Fracking` mulligan language: "Fracking is almost always a good keep, unless you have miracle salesman already." Useful as adjacent evidence only, not as source-backed promotion for the provided Boarlock deck.

## Validation Outputs

### Required validator run: Kingslayer JSON

Command:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py `
  -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml `
  -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Kingslayer_Quick_Pick_Mulligan_Closure.json
```

Output summary:

- Exit code: `0`
- Validator result: `PASS`
- Coverage line: `Coverage: 100.0% (0/0)`
- Extra fields line present for the 11 JSON keys

### Required validator run: Boarlock JSON

Command:

```powershell
python C:\Users\darbo\.codex\skills\research\validate_json.py `
  -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml `
  -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Boarlock_Fracking_Mulligan_Closure.json
```

Output summary:

- Exit code: `0`
- Validator result: `PASS`
- Coverage line: `Coverage: 100.0% (0/0)`
- Extra fields line present for the 11 JSON keys

### Additional parse check

Command:

```powershell
python -c "import json, yaml, pathlib; base=pathlib.Path(r'docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure'); yaml.safe_load((base/'fields.yaml').read_text(encoding='utf-8')); yaml.safe_load((base/'outline.yaml').read_text(encoding='utf-8')); json.loads((base/'results'/'Kingslayer_Quick_Pick_Mulligan_Closure.json').read_text(encoding='utf-8')); json.loads((base/'results'/'Boarlock_Fracking_Mulligan_Closure.json').read_text(encoding='utf-8')); print('YAML_JSON_PARSE_OK')"
```

Output:

- `YAML_JSON_PARSE_OK`

## Commit Hash

`2591633`

## Self-Review

- Scope stayed inside Task 2 only.
- No replay, winrate, runtime log, candidate promotion, or post-run tuning logic was added.
- No normal-path `Presume.json` or `Concede.json` content was introduced.
- Both research items stayed conservative: `promotion_allowed` is `false` because no public source explicitly supports a card-level keep/discard for the target card in the provided fixture deck.
- I did not raise confidence without source evidence.
- Concern: the brief required a flat `fields.yaml`, but the current `validate_json.py` implementation only extracts schema fields from `field_categories`. That means the required validator passes as `0/0` coverage rather than truly checking field presence. I left the file exactly as specified in the brief and documented the validation weakness instead of changing the schema.

## Final Status

DONE_WITH_CONCERNS

## Fix Report

- Files changed: `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/fields.yaml`, `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Kingslayer_Quick_Pick_Mulligan_Closure.json`, `docs/research/2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure/results/Boarlock_Fracking_Mulligan_Closure.json`, `.superpowers/sdd/task-2-report.md`
- Validation outputs:
  - `python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Kingslayer_Quick_Pick_Mulligan_Closure.json`
  - `Coverage: 100.0% (10/10)`
  - `python C:\Users\darbo\.codex\skills\research\validate_json.py -f docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\fields.yaml -j docs\research\2026-07-08-hsconfig-kingslayer-boarlock-mulligan-closure\results\Boarlock_Fracking_Mulligan_Closure.json`
  - `Coverage: 100.0% (10/10)`
- Commit hash: pending until commit
- Self-review: Schema now matches the research validator shape used by existing packages, so coverage is measured against 10 defined fields instead of 0/0. Blocked evidence text is now neutral and no longer presents adjacent-archetype quotes as source-backed support. No replay, winrate, runtime-log, candidate-promotion, or post-run tuning logic was added.
