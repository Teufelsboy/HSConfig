# HSConfig Skill Contract Audit Hardening

## Ziel

Den HSConfig-Skill so haerten, dass der normale `hsconfig configure`-Pfad und die niedrigeren `prepare`/`validate`/`apply`-Grenzen dieselbe Runtime-Contract-Logik nutzen: ein Package gehoert zu genau einem Deck, Normalpfad-Surfaces sind zentral definiert, und Operator-Dokumentation sowie Guardrails driften nicht auseinander.

## Befundbasis

- `git fetch --all --prune --tags`, Currentness-Check und `contract-preflight` liefen sauber.
- `scripts/check_contract_guardrails.py` lief sauber.
- Full-Suite lief isoliert sauber: `1893 passed, 11 skipped`.
- Temporaerer ShadowPriest-Smoke mit `configure --apply` gegen Fake-Runtime lief sauber: `VALID_PACKAGE`, `runtime_apply_allowed=true`, ein Deck-Verzeichnis, 18 Runtime-JSONs.
- Reproduziert: Zwei `prepare`-Runs in dasselbe Package koennen mehrere Deck-Verzeichnisse hinterlassen; `validate` und `operator_summary` bleiben aktuell zu optimistisch, waehrend `apply` korrekt blockiert.
- Reproduziert: `CardBehavior.json` wird von `validate` blockiert, aber `evaluate_apply_gate()` kennt es nicht als verbotenes Normalpfad-Surface, wenn eine gefaelschte Summary es auffuehrt.

## Umsetzungsschritte

1. Tests zuerst:
   - `validate_config_package(require_complete_package=True)` muss mehrere Deck-Verzeichnisse ablehnen.
   - `apply_gate` muss `CardBehavior.json` aus Summary und Ist-Dateien wie `Presume.json`/`Concede.json` blockieren.
   - `strong_promotion_report` muss dieselbe Surface-Liste verwenden.
   - `check_hsconfig_currentness.py` braucht direkte Contract-Tests fuer `build_currentness()` und CLI-Exit/JSON.
   - CLI Parser/Dispatch bekommt eine Paritaets-Sentinel.
   - `check_contract_guardrails.py` muss direkte Validate/Apply-Grenztests enthalten.
2. Minimaler Code-Patch:
   - Zentrale Normalpfad-Forbidden-Surface-Konstante in der VisionAI-Registry.
   - `apply_gate` und `strong_promotion_report` auf diese Konstante umstellen.
   - Complete-package-Validation auf genau ein Deck-Verzeichnis ausrichten.
3. Dokumentations-Patch:
   - Operator-Guide currentness sichtbar im Normalpfad machen.
   - Lower-level path wording auf `source-autopilot or draft-source-documents` synchronisieren.
   - Forbidden-Surface-Wording mit aggregate `CardBehavior.json` synchronisieren.
   - Report-Lesereihenfolge angleichen: `acceptance_summary` -> `handoff_contract` -> optionale `source_closure_receipt`.
4. Verifikation:
   - Erst fokussierte neue Tests.
   - Dann Guardrail-Script.
   - Dann Full-Suite.
   - Danach `contract-preflight`, Currentness und finaler sauberer `git status`.

## Nicht-Ziele

- Kein HSTuner.
- Keine Replay-, Winrate-, Log- oder Post-run-Tuning-Logik.
- Keine Runtime-Schreibpfad-Erweiterung.
- Keine generierten Outputs oder Backups committen.
