# HSConfig Agent Rules

Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.

HSConfig is a lean deck-to-HearthRanger-config generator. Keep it separate from HSTuner.

Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.

Generated runtime packages belong under `outputs/` and are ignored by git.

Every implementation change must preserve:

- exact deck and CardID identity
- full `GlobalValues.json` key profiling
- every card covered in the gameplan contract
- strict JSON validation
- row-level provenance for generated config rows
