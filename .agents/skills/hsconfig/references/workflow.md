# Workflow

Normal flow: deck input -> `hsconfig prepare` -> HearthSim deckstring decode -> exact identity -> card metadata -> guide/static research contract -> guide-backed gameplan -> surface intent -> compilers -> validation -> optional runtime apply.

Use `hsconfig prepare` for package creation. It writes `deckstring_decode_receipt.json`, `card_id_map.json`, `gameplan_contract.json`, `surface_intent.json`, validation reports, and `reports/research/*`.

Use `hsconfig research-contract` only when the research bundle should be inspected before compiling config files. It writes no `CustomConfig` runtime package.

Use `hsconfig build` as a lower-level command when a caller already controls explicit `--cards-json` or `--claims-json` inputs. It still writes `reports/research/*`. Use `--allow-placeholder` only for deterministic fixture or preview tests.

Use `hsconfig validate` before handoff or apply. Use `hsconfig apply` only when the user explicitly asks to write to a HearthRanger runtime; apply copies the deck folder and updates `CustomConfig/deck_config.ini` so the visible deck name maps to the generated config folder.
