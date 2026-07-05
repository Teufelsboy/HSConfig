# Workflow

Build flow: deck input -> HearthSim deckstring decode -> exact identity -> card metadata -> guide claims -> guide-backed gameplan -> surface intent -> compilers -> validation -> optional runtime apply.

Use `hsconfig build` for package creation. By default it decodes the deck code and writes `deckstring_decode_receipt.json` plus `card_id_map.json` under `reports/`. Pass `--claims-json` when guide research has source-backed claims. Use `--cards-json` only as an expert override and `--allow-placeholder` only for fixture/test previews.

Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when the user explicitly asks to write to a HearthRanger runtime; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.
