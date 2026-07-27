# Task 5 Report: Verifizierter Deck-Input vor Runtime Apply

Status: `DONE`

## Ergebnis

`--cards-json` und Placeholder bleiben für Forschung, Fixtures und
Fehlerdiagnose nutzbar. Sie können aber keine Runtime-Apply-Authority mehr
erzeugen, solange ihr normalisierter Roster nicht exakt zum decodierten
Deckcode passt.

Die neue Verifikationsmatrix lautet:

| Input | Status | Diagnose-Build | Runtime Apply |
|---|---|---:|---:|
| aus Deckcode decodierter Roster | `decoded_from_deck_code` | ja | ja |
| exakt passendes `cards-json` | `cards_json_matches_deck_code` | ja | ja |
| abweichendes `cards-json` | `cards_json_unverified` | ja | nein |
| Placeholder ohne verifizierbaren Deckcode | `placeholder_unverified` | ja | nein |
| malformed Deckcode plus gelieferte Karten | `cards_json_unverified` | ja | nein |

## Implementierung

### Deck-Input-Verifikation

Neu erstellt wurde `src/hsconfig/deck_input_verification.py`.

`verify_deck_input()` verwendet den bestehenden
`hsconfig.deckstring_decode.decode_deck_code()`-Pfad und die bestehende
kanonische Deck-Fingerprint-Logik. Es gibt keine zweite Deckstring-
Implementierung.

Roster-Gleichheit ist Multiset-Gleichheit über `(card_id, count)`:

- Eingabereihenfolge und Kartennamen sind irrelevant;
- Duplikatzeilen werden vor dem Vergleich zusammengezählt;
- leere Card IDs werden mit `deck_input_card_id_missing` abgelehnt;
- ungültige Count-Typen werden mit `deck_input_count_invalid` abgelehnt;
- `count <= 0` wird mit `deck_input_count_non_positive` abgelehnt.

Insbesondere werden Boolean- und Float-Counts nicht still zu Integern
konvertiert. Malformed beziehungsweise abgeschnittene Base64-Deckcodes, für
die die verwendete Decoderbibliothek `ValueError` oder `TypeError` liefert,
erzeugen ein unverified Verdict statt eines ungefangenen Fehlers.

### Persistenz und Derivation-Bindung

Die Verifikation entsteht unmittelbar in `load_cards()` und wird in folgende
Authority-Flächen übernommen:

- `reports/input_manifest.json`;
- `reports/operator_summary.json`;
- `package_derivation_receipt.json` über die bereits in Task 4 vorbereitete
  Input-Bindung.

Das Verdict enthält:

```json
{
  "status": "cards_json_unverified",
  "runtime_apply_eligible": false,
  "normalized_roster_sha256": "sha256:<64 lowercase hex>"
}
```

Task 5 ändert den Task-4-Receipt-Algorithmus nicht. Die bereits vorhandene
Receipt-Projektion bindet das nun verpflichtend produzierte Manifestfeld und
den separaten Deck-Input-Authority-Digest.

### Fail-closed Apply-Gate

Das Apply-Gate vertraut weder Manifest noch Operator Summary isoliert. Es:

1. liest Deckcode, Card-Source und `deck_identity.cards`;
2. berechnet das Verdict erneut;
3. verlangt exakte Gleichheit mit Manifest und Operator Summary;
4. verlangt `runtime_apply_eligible is True`.

Ein fehlendes, negatives, widersprüchliches oder veraltetes Verdict blockiert
mit dem stabilen Code:

```text
deck_input_not_verified
```

Diese Prüfung läuft nach strikter Paketvalidierung, aber vor Source-Authority
und Derivation-Authority. `runtime_apply.apply_package()` wertet das Gate aus,
bevor Zielverzeichnis, Snapshot oder Runtime-Mutation vorbereitet werden.

`configure --apply` prüft das gerade erzeugte Operator-Verdict zusätzlich vor
dem Aufruf des allgemeinen Apply-Kommandos. Ein unverified Diagnosepaket wird
weiter vollständig geschrieben; der Prozess endet erst an der Apply-Stufe
non-zero und ruft keinen Runtime-Schreibpfad auf.

## TDD-Evidenz

### RED

Nach Ergänzung der Task-5-Regressions und vor dem Produktcode:

```text
15 failed, 104 passed in 71.34s
```

Die Fehler belegten:

- das Verifikationsmodul und Verdict-Felder fehlten;
- `cards-json`, Placeholder und malformed Inputs konnten ohne ausdrückliches
  negatives Verdict gebaut werden;
- Manifest, Summary und Receipt waren noch nicht vollständig verbunden;
- direkter Runtime Apply erreichte bei fehlendem Verdict die
  Zielvorbereitung;
- `configure --apply` rief bei unverified Input noch den Apply-Pfad auf.

Ein nachgelagertes Self-Review ergänzte vor dem Fix zwei weitere Randfälle:

```text
3 failed, 5 passed
```

Reproduziert wurden ein abgeschnittener Base64-Deckcode mit Decoder-
`TypeError` sowie still akzeptierte Boolean-/Float-Counts.

### GREEN

Gezielte Randfälle:

```text
8 passed, 9 deselected in 6.64s
```

Finale, im Task-Brief vorgeschriebene Deck-Input-Suite:

```text
123 passed in 52.81s
```

Sie umfasst:

- `tests/test_cli.py`;
- `tests/test_deck_identity.py`;
- `tests/test_package_builder.py`;
- `tests/test_apply_gate.py`;
- `tests/test_apply_authority_boundary.py`.

Finale vollständige Repository-Suite:

```text
2436 passed, 11 skipped in 268.15s
```

Contract-Guardrail:

```text
825 passed in 60.79s
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

Ruff auf allen durch Task 5 geänderten Python-Dateien:

```text
All checks passed!
```

Der repo-weite Ruff-Lauf meldet weiterhin drei unberührte F401-
Baselinebefunde in `source_claim_context.py`,
`test_source_builder_matrix_closure.py` und `test_visionai_registry.py`.
Task-5-Dateien sind davon nicht betroffen.

`git diff --check` meldet keine Whitespace-Fehler. Die Windows-Hinweise zur
künftigen LF/CRLF-Normalisierung sind keine Diff-Fehler.

## Legacy-Testmigration

Es wurde kein fehlendes Verdict pauschal toleriert und kein Gate
abgeschwächt.

Handgebaute Tests, die andere Apply-Grenzen prüfen, verwenden über
`tests/helpers/verified_deck_input.py` ein gemeinsames echtes Mini-Deck mit
exakt passendem Roster. Dadurch erreichen sie weiterhin die jeweils
beabsichtigte nachgelagerte Authority-Grenze.

ShadowPriest- und synthetische Semantik-Fixtures verwenden verifizierbare,
zum jeweiligen Deckcode passende Roster, wenn der Test weiterhin ein
apply-fähiges Paket benötigt.

Bewusst abweichende `cards-json`-, Placeholder-, captured-, legacy- und
troubleshooting-Fixtures bleiben diagnostisch. Ihre Erwartungen wurden
explizit auf `cards_json_unverified`, `runtime_apply_allowed=false` und
`blocked` umgestellt, während ihre fachlichen Report- und
Semantikassertionen erhalten blieben.

Die vollständige Suite dokumentierte die Migration in drei Runden:

```text
74 failed, 2358 passed, 11 skipped
5 failed, 2431 passed, 11 skipped
2436 passed, 11 skipped
```

## Self-Review und Bypass-Prüfung

- Ein decodierter Deckcode ist apply-eligible.
- Ein exakt passendes `cards-json` ist apply-eligible, unabhängig von
  Zeilenreihenfolge und Kartennamen.
- Ein abweichendes, Placeholder- oder malformed Input bleibt baubar, ist aber
  apply-ineligible.
- Manifest und Summary müssen dasselbe frisch recomputierte Verdict enthalten.
- Ein gefälschtes positives Verdict mit nachträglich veränderter
  `deck_identity.cards` wird blockiert.
- Ein fehlendes Verdict in einer prebuilt Summary wird blockiert.
- Ein Widerspruch zwischen Manifest und Summary wird blockiert.
- Der normale Apply-CLI-Pfad und der direkte Python-Aufruf verwenden dasselbe
  Gate.
- `configure --apply` blockiert vor dem allgemeinen Apply-Aufruf.
- Ein direkter `apply_package()`-Aufruf blockiert vor
  `_single_config_dir`, Snapshot und Runtime-Erzeugung.
- Fake-Apply-Receipts umgehen die erneute Gate-Prüfung nicht.
- `operator_summary.json` bleibt die einzige human-facing Apply-Authority.
- Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
  Evidence-Dateien gelesen oder geschrieben.

## Restrisiko

Die Deckstring-Bibliothek signalisiert beschädigte Eingaben derzeit mit
`ValueError` und bei einzelnen abgeschnittenen Payloads mit `TypeError`.
Beide beobachteten invalid-code Formen werden fail-closed behandelt. Andere
unerwartete interne Decoderfehler werden bewusst nicht pauschal verschluckt.

## Commit

Vorgesehener Task-Commit:

```text
fix: require verified deck input for runtime apply
```

## Fix-Runde 1: Apply-Planung und No-Block-Verträge

Status: `DONE`

### Direkte Apply-Planung

Das Self-Review zeigte eine zweite Python-Oberfläche: `apply_package()`
reevaluierte das Apply-Gate bereits selbst, `plan_apply_package()` validierte
dagegen nur die Paketstruktur und vertraute anschließend dem optional
übergebenen `apply_gate`.

Der neue Regressionstest ruft `plan_apply_package()` direkt mit einem
nachträglich unverifizierten Deck-Input und einem gefälschten positiven Gate
auf. Wachposten auf `_single_config_dir`, `_validate_config_dir`,
Fake-Receipt-Erzeugung/-Persistenz und Runtime-Snapshot belegen, dass keine
Ziel- oder Receipt-Vorbereitung erreicht werden darf.

RED:

```text
1 failed
AssertionError: target preparation must not run
```

GREEN nach der minimalen Produktionsänderung:

```text
4 passed in 7.79s
```

`plan_apply_package()` ruft nun direkt nach der gemeinsamen strikten
Paketvalidierung `_resolve_allowed_apply_gate()` auf. Damit werden
Operator-Summary, Deck-Input-Verifikation, Source-Authority und
Derivation-Authority erneut ausgewertet. Ein unverifiziertes Paket endet vor
der Zielvorbereitung stabil mit `deck_input_not_verified`. Das frisch
ausgewertete Gate wird in das Fake-Receipt übernommen.

### Wiederhergestellte No-Block- und Load-safe-Verträge

Der vollständige Testdiff `3d61649..781452e` wurde Datei für Datei geprüft.
Die erste Task-5-Migration hatte mehrere ältere Integrationsverträge auf
`INVALID_PACKAGE` beziehungsweise `blocked` umgestellt, obwohl die Tests
eigentlich andere Grenzen belegen sollten.

Betroffen waren insbesondere:

- `universal_wild_no_block_matrix`;
- importierte Plan-Konflikte in `package_builder`;
- vier `prepare_cli`-Verträge;
- `mulligan_richness_e2e`;
- `source_contract_closure_wave`;
- vier Build-/Plan-Override-Verträge in `test_cli.py`;
- die ShadowPriest-Online-Source-Semantik.

Zuerst wurden die ursprünglichen fachlichen Assertions ohne Fixture-Reparatur
wiederhergestellt. Der gemeinsame RED-Lauf belegte die Ursache:

```text
18 failed in 29.43s
```

Alle 18 Fehler gingen auf unverifizierte beziehungsweise nicht passende
Testroster zurück; bei ShadowPriest war zusätzlich die Vollroster-bedingte
Semantikverschiebung sichtbar.

Die Reparatur verwendet nun zentrale Testhelfer:

- reale CardID-/DBF-Paare für normale Fixtures;
- aus dem jeweiligen Roster erzeugte Deckcodes;
- deckcode-verifizierte synthetische `UNRESOLVED_DBF_*`-Karten, wenn ein Test
  bewusst unbekannte zukünftige Kartenmechaniken modelliert;
- rekursives CardID-Remapping für Source-Dokumente;
- dynamisch aus dem aktuellen Roster berechnete Exact-Deck-Fingerprints.

Die synthetischen Roster bleiben dadurch fachlich unbekannt, sind aber
Authority-seitig exakt zum Deckcode passend. Die Universal-No-Block-Hilfe
prüft zusätzlich ausdrücklich:

```text
deck_input_verification.status=cards_json_matches_deck_code
deck_input_verification.runtime_apply_eligible=true
```

GREEN:

```text
18 passed in 29.89s
```

Wiederhergestellt sind unter anderem:

- `technical_status=VALID_PACKAGE`;
- `runtime_load_safe=true`;
- `runtime_apply_mode=load_safe_apply`;
- `runtime_apply_allowed=true`;
- `no_block_failure_mode_summary.hard_block=false`;
- die ursprünglichen `config_usefulness`- und Mulligan-Qualitätsassertions;
- die ursprünglichen Conflict-, Report-only- und Runtime-evidence-Lanes.

### ShadowPriest

Die Online-Source-Fixture verwendet wieder das ursprüngliche gezielte Roster:

```text
SW_448 x1
SW_446 x2
TOY_381 x2
SW_444 x2
SCH_514 x2
GVG_009 x2
```

Dazu gehört der exakt passende Testdeckcode
`AAEBAa0GAbv3AwWRD9fOA6P3A633A8SoBgAA`. Die zwischenzeitliche
Vollroster-Decodierung wurde entfernt.

Die ursprünglichen exakten Assertions sind wieder aktiv und grün:

- `generic_low_confidence_not_strong_evidence` ist der erwartete Blocker;
- abgelehnte Mulligan-Ziele sind exakt `GVG_009`, `SCH_514`, `SW_444` und
  `TOY_381`;
- ihr erster fehlender Link ist exakt `needs_mulligan_claim`;
- Darkbishop bleibt Start-of-game-/Hero-power-Effekt und kein Mulligan-Keep.

### Finale Verifikation

Apply-Authority und Runtime-Planung:

```text
108 passed in 17.79s
```

Explizite No-Block-, Closure- und Mulligan-Suiten:

```text
76 passed in 42.12s
```

CLI-, Prepare-, Configure- und ShadowPriest-Suiten:

```text
126 passed in 84.39s
```

Weitere geänderte Authority-/Validation-Suiten:

```text
49 passed in 16.48s
```

Vollständige Repository-Suite:

```text
2437 passed, 11 skipped in 271.24s
```

Contract-Guardrail:

```text
826 passed in 59.80s
OK: installed skill sync
OK: contract spine sentinel
OK: focused contract boundary tests
```

Ruff auf allen in Fix-Runde 1 geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` ist sauber. Der repo-weite Ruff-Lauf meldet vier
unberührte Baselinebefunde: zusätzlich zu den drei bereits dokumentierten
F401-Befunden einen bestehenden E402-Befund in
`scripts/sync_installed_skill.py`.

Der erneute Assertions-Diff gegen `3d61649` zeigt keine verbliebene
Task-5-Abschwächung der alten No-Block-/Load-safe-Verträge.

### Scope

Es gab keine Task-6-, Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
Evidence-Schreibzugriffe.

Vorgesehener Fix-Commit:

```text
fix: preserve apply planning and no-block contracts
```
