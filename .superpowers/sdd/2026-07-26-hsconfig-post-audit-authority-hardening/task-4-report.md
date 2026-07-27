# Task 4 Report: Deterministische Package-Derivation-Authority

Status: `DONE`

## Ergebnis

Ein handgeschriebenes oder nachträglich veraltetes
`reports/operator_summary.json` kann ein Paket nicht mehr selbst zu
`VALID_PACKAGE` autorisieren.

Der Paketbau erzeugt jetzt eine kanonische
`package_derivation_receipt.json`. Sie bindet die autoritativen Eingaben und
alle aktiven Runtime-JSON-Dateien an einen öffentlichen SHA-256-Digest. Die
Operator Summary enthält nur den Verweis auf diese Quittung. Das Apply-Gate
vertraut diesem Verweis nicht blind, sondern wiederholt vor jeder
Runtime-Autorisierung:

1. strikte Paketvalidierung;
2. vorhandene Deck-Input-Eligibility-Prüfung;
3. vorhandene strategische Source-Receipt-Prüfung;
4. Receipt-Schema- und Digest-Prüfung;
5. vollständige Receipt-Neuberechnung;
6. Konsistenzprüfung mit der Operator Summary;
7. Parität zwischen tatsächlichen und deklarierten Runtime-Dateien.

Erst danach darf `technical_status=VALID_PACKAGE` die bestehende
`load_safe_apply`-Entscheidung auslösen.

## Implementierung

### Kanonische Derivation Receipt

Neu erstellt wurde `src/hsconfig/package_derivation_receipt.py`.

Die Quittung verwendet `schema_version=1` und hasht:

- `reports/input_manifest.json`;
- `reports/deck_identity.json`;
- `reports/deck_fingerprint.json`;
- eine vorhandene Deck-Input-Verifikation;
- kanonische Source Receipts aus `reports/guide_claim_bundle.json`;
- `reports/globalvalues_baseline.json`;
- `reports/globalvalues_profile.json`;
- `reports/output_ownership_manifest.json`;
- jede aktive JSON-Datei unter `CustomConfig/`, mit normalisiertem
  Forward-Slash-Pfad.

JSON wird deterministisch mit sortierten Schlüsseln, kompakten Trennzeichen
und UTF-8 serialisiert. Source-Receipt-Sequenzen und Pfade werden ordinal
sortiert. Volatile Zeitfelder und absolute Pfadwerte werden aus der
Authority-Projektion entfernt.

Der öffentliche Digest wird aus exakt denselben kanonischen Bytes berechnet,
die in `package_derivation_receipt.json` geschrieben werden.

Die Quittung ist nicht zirkulär:

- sie hasht sich nicht selbst;
- sie hasht `reports/operator_summary.json` nicht;
- Human-Reports sind keine Ableitungsinputs.

### Paketbau und Configure-Nachbearbeitung

`package_builder.py` finalisiert zuerst Runtime-Dateien und das
Output-Ownership-Manifest. Danach schreibt es die Quittung und übergibt deren
Metadaten an `build_operator_summary()`.

Ein bestehendes Receipt aus einem früheren Build wird vor dem Neuaufbau
entfernt. Das Ownership-Manifest klassifiziert die neue Root-Datei als
`integrity_receipt` mit `can_block_apply=true`, ohne sie zu einer zweiten
human-facing Gate-Datei zu machen.

Der `configure`-Workflow ergänzt nach `prepare` noch `source_bundle.json` und
erneuert dabei das Output-Ownership-Manifest. Diese autoritative
Nachbearbeitung aktualisiert nun ebenfalls Quittung und Summary-Bindung.
Damit bleibt auch das endgültige `04_package` konsistent und ein Fake Apply
funktioniert nur mit der finalen Paketform.

### Operator Summary

Die Summary enthält:

```json
{
  "package_derivation": {
    "schema_version": 1,
    "receipt_path": "package_derivation_receipt.json",
    "receipt_sha256": "sha256:<64 lowercase hex>",
    "verified": true
  }
}
```

Die technische Statusableitung verwendet den gemeinsamen strikten
Validierungsvertrag. Für offizielle Builder-Ausgaben ist
`VALID_PACKAGE` zusätzlich an eine syntaktisch gültige, verifizierte
Derivation-Bindung gekoppelt.

Direkte Summary-Konstruktion bleibt für isolierte Diagnostik kompatibel. Sie
erhält dadurch aber keine Apply-Authority: Das Apply-Gate lehnt jedes reale
Paket ohne Quittung und exakte Summary-Bindung ab.

### Apply-Gate und Runtime-Schreibgrenze

Das Apply-Gate recomputiert die Authority aus dem Paketinhalt. Stabile
Fail-Closed-Codes sind:

```text
package_derivation_receipt_missing
package_derivation_receipt_digest_mismatch
package_derivation_mismatch
operator_summary_derivation_inconsistent
```

Eine unbekannte Receipt-Version wird zusätzlich stabil als
`package_derivation_receipt_schema_unsupported` ausgewiesen. Eine
fehlgeschlagene strikte Validierung liefert
`strict_package_validation_failed`.

`runtime_apply.py` und `apply_gate.py` verwenden denselben
`strict_validation_passed()`-Vertrag. Negative Runtime-Tests belegen, dass bei
einem Authority-Fehler die Snapshot-/Write-Grenze nicht erreicht und kein
Runtime-Verzeichnis erzeugt wird.

### Task-5-Grenze

Task 4 erfindet keine Deck-Input-Verifikation vorweg. Wenn die künftige
Verifikation als Report oder Manifestfeld vorhanden ist, wird sie gehasht und
ihre `runtime_apply_eligible`-Entscheidung wird geprüft. Ist sie noch nicht
vorhanden, bleibt das bisherige Paketformat kompatibel. Die eigentliche
Deck-Input-Verifikationslogik bleibt Aufgabe 5.

## TDD-Evidenz

### Baseline

Vor den neuen Regressionen:

```text
89 passed in 10.76s
```

### RED

Nach Ergänzung der Task-4-Regressions und vor dem Produktcode:

```text
12 failed, 89 passed in 12.67s
```

Die Fehler belegten:

- eine gefälschte `VALID_PACKAGE`-Summary überschritt das Apply-Gate;
- Runtime-Wertänderungen und neue Runtime-Dateien waren nicht
  ableitungsgebunden;
- Änderungen an Deck Identity/Fingerprint waren nicht gebunden;
- Receipt, Schema- und Digest-Prüfungen fehlten;
- eine erzwungen erfolgreiche Receipt-Verifikation konnte die fehlende
  strikte Gate-Validierung überstimmen;
- Runtime Apply erreichte die Schreibvorbereitung trotz Authority-Tamper.

Der separat eingeführte gemeinsame Strict-Result-Vertrag war vor der
Implementierung ebenfalls rot:

```text
4 failed, 5 deselected
```

### GREEN

Erste fokussierte Task-4-Green-Runde:

```text
101 passed in 16.50s
```

Finale, im Task-Brief vorgeschriebene Apply-Boundary-Suite:

```text
140 passed in 24.42s
```

Sie umfasst:

- `tests/test_apply_gate.py`;
- `tests/test_apply_authority_boundary.py`;
- `tests/test_runtime_apply.py`;
- `tests/test_runtime_apply_receipts.py`;
- `tests/test_strict_package_validation.py`;
- `tests/test_output_ownership_manifest.py`;
- `tests/test_property_no_block_apply_gate.py`.

Direkt betroffene Configure-, Acceptance-, Source-Claim- und
Subtractive-Contract-Suite:

```text
65 passed in 20.41s
```

Finale vollständige Repository-Suite:

```text
2410 passed, 11 skipped in 255.72s
```

Ruff auf allen durch Task 4 geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` meldet keine Whitespace-Fehler. Die Windows-Hinweise zur
künftigen LF/CRLF-Normalisierung sind keine Diff-Fehler.

## Legacy-Testanpassungen

Es wurden keine Tests durch ein schwächeres Gate grün gemacht.

Drei Acceptance-Matrix-Fälle erwarteten noch, dass eine veraltete
`VALID_PACKAGE`-Summary fehlende oder ungültige GlobalValues-Authority
überstimmt. Diese Erwartungen wurden auf das neue fail-closed Verhalten
umgestellt.

Zwei handgebaute Minimalpakete testen weiterhin bewusst nicht-blockierende
Source-Konflikte beziehungsweise den Legacy-No-op-Flag. Ihre Fixtures wurden
zu strikt validen, Receipt-gebundenen Paketen aufgewertet, damit weiterhin
genau die beabsichtigte Semantikgrenze geprüft wird.

Der vorhandene Configure-Fake-Apply-Test deckte eine echte Produktionslücke
auf: Das nach `prepare` neu geschriebene Ownership-Manifest machte die
Quittung veraltet. Die Produktionslogik wurde korrigiert; der Test wurde
nicht abgeschwächt.

## Self-Review

- Ein unverändertes Builder-Paket verifiziert und darf weiterhin
  `load_safe_apply` erreichen.
- Eine handgeschriebene Summary ohne Receipt-Metadaten wird blockiert.
- Änderungen an Runtime JSON, Runtime-Dateimenge, Deck Identity/Fingerprint,
  Source Receipts und Ownership-Manifest werden durch Neuberechnung erkannt.
- Receipt-Änderungen ohne passenden Summary-Digest werden erkannt.
- Unbekannte Receipt-Schemas werden blockiert.
- Receipt und Summary sind gegenseitig nicht zirkulär.
- Logisch identische Pakete in unterschiedlichen Temp-Roots erzeugen
  identische Receipt-Inhalte und Digests.
- Explizit deklarierte Standort- und volatile Zeitfelder verändern die
  Quittung nicht; andere semantische Werte bleiben vollständig gebunden.
- `operator_summary.json` bleibt die einzige human-facing Apply-Authority.
- Die Quittung ist eine maschinenprüfbare Integritätsabhängigkeit, kein
  zweites menschliches Gate.
- Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
  Evidence-Dateien geschrieben.

## Unabhängiges Review

Verdikt: `PASS`, keine P1-, P2- oder P3-Befunde.

Der Reviewer reproduzierte:

```text
140 passed in 25.20s
configure warning fake-apply: 1 passed in 8.22s
11/11 isolierte Authority-Mutationen fail-closed
```

In separaten Paketkopien wurden nacheinander verändert:

- Runtime-JSON-Inhalt;
- Deck Identity;
- Deck Fingerprint;
- Input Manifest;
- kanonisches Source Receipt;
- Output-Ownership-Manifest;
- Receipt-Inhalt;
- Receipt-Digest;
- Summary-Derivation-Metadaten;
- gefälschte `VALID_PACKAGE`-Summary;
- kombinierte Authority-Metadaten.

Alle elf Fälle lieferten `gate_allowed=false`. Die Runtime-Snapshot-/Write-
Grenze wurde nie erreicht und es wurde kein Runtime-Verzeichnis erzeugt.
Beobachtete Codes waren je nach Schicht
`package_derivation_mismatch`,
`package_derivation_receipt_digest_mismatch` und
`operator_summary_derivation_inconsistent`.

Der Reviewer bestätigte zusätzlich:

- korrekte Gate-Reihenfolge;
- deterministische Canonicalization und Non-Circularity;
- Configure-Rebinding nach dem Ownership-Rewrite;
- keine Workspace-Änderungen durch das Review;
- sauberes `git diff --check`.

Als bewusste Kompatibilitätsgrenze bleibt direkte, isolierte
`build_operator_summary()`-Diagnostik ohne Receipt möglich. Daraus entsteht
keine Autorisierung, weil das Apply-Gate fehlende Derivation-Metadaten
fail-closed ablehnt. Die Task-5-Eligibility-Schnittstelle bleibt wie verlangt
optional, bis Task 5 sie produziert.

## Commit

Vorgesehener Task-Commit:

```text
fix: bind apply authority to package derivation receipt
```

## Fix-Runde 1: Authority-Edge-Cases

Ein nachgelagertes Controller-Review identifizierte drei Important Findings:

1. Python-Gleichheit akzeptierte `true`, `1` und `1.0` an einzelnen
   Schema-/Boolean-Grenzen als gleichwertig.
2. Die offizielle Builder-Summary leitete `VALID_PACKAGE` aus strikter
   Validierung plus formal gültigen Receipt-Metadaten ab, ohne die
   builderseitig tatsächlich neu berechneten Deck-, Source- und
   Receipt-Ergebnisse zu konsumieren.
3. Die Root-Unabhängigkeit entfernte rekursiv jeden absolut-pfadartig
   aussehenden String. Dadurch konnten semantische Werte wie `/Alpha` und
   `/Beta` fälschlich aus der Authority-Projektion verschwinden.

### TDD RED

Vor der Produktionsänderung wurden acht neue Regressionen ausgeführt:

```text
8 failed, 19 deselected in 8.33s
```

Die Fehler reproduzierten exakt:

- `summary.package_derivation.schema_version=true` wurde erlaubt;
- Receipt plus Summary mit `schema_version=true` beziehungsweise `1.0`
  verifizierten nach Aktualisierung des Digests;
- `verified=1` wurde wie `verified=true` behandelt;
- `/Alpha -> /Beta` in Deck Identity veränderte die Quittung nicht;
- die Builder-Summary meldete bei vorhandener negativer Deck-Eligibility,
  ungültiger Source-Authority und einem post-Receipt-Mismatch weiterhin
  `VALID_PACKAGE`, während das Apply-Gate bereits blockierte.

### Typstrenge

Receipt-Verifier, Apply-Gate und Summary-Status verwenden nun dasselbe
typstrenge Schema-Prädikat:

```python
type(value) is int and value == 1
```

Das Summary-Feld `verified` muss mit `is True` exakt ein Boolean sein.
Dictionary-Gleichheit kann diese Grenzen damit nicht mehr über
`True == 1 == 1.0` umgehen.

### Builderseitige Authority für die Human Summary

Nach dem Schreiben der Quittung berechnet der Builder einen internen
Authority-Kontext aus dem tatsächlichen Paket:

- gemeinsames Ergebnis der strikten Paketvalidierung;
- gemeinsame optionale Deck-Input-Eligibility;
- gemeinsame erforderliche Source-Authority;
- vollständige Receipt-Neuberechnung;
- Digest der tatsächlich gelesenen Receipt-Datei.

`operator_summary._technical_status()` verlangt bei offiziellen
Builder-Ausgaben alle vier Ergebnisse exakt `True` und gleicht den
tatsächlichen Receipt-Digest mit den Summary-Metadaten ab. Dadurch kann die
human-facing Summary nicht mehr `VALID_PACKAGE` melden, wenn dieselben
Task-4-Bedingungen das Apply-Gate blockieren.

Direkte isolierte Summary-Diagnostik ohne Package-Derivation bleibt
kompatibel. Sie erhält weiterhin keine Apply-Authority, weil ein reales
Paket ohne Receipt-/Summary-Bindung am Gate blockiert.

Task 5 wurde nicht vorweggenommen: Fehlt eine Deck-Input-Verifikation, bleibt
das aktuelle Format kompatibel. Nur ein bereits vorhandenes negatives
`runtime_apply_eligible`-Verdict blockiert.

### Feldbasierte Root-Unabhängigkeit

Die rekursive wertbasierte Pfaderkennung wurde entfernt. Ausgeschlossen
werden nur noch explizit deklarierte Top-Level-Felder pro autoritativem
Dokument:

- bekannte Standortfelder des Input Manifests;
- bekannte volatile Zeitfelder der jeweiligen Report-Schemas.

Alle übrigen Strings werden unabhängig von ihrer Form gehasht. Insbesondere
ist ein Deckname `/Alpha` semantische Authority; eine Änderung auf `/Beta`
verändert die Receipt und blockiert Apply mit
`package_derivation_mismatch`.

### GREEN und vollständige Verifikation

Neue Edge-Case-Regressionen:

```text
8 passed, 19 deselected in 8.39s
```

Erweiterte Task-4-Apply-Boundary-Suite:

```text
148 passed in 26.56s
```

Betroffene Builder-, Summary-, Configure- und Acceptance-Suite:

```text
169 passed in 14.88s
```

Vollständige Repository-Suite:

```text
2418 passed, 11 skipped in 263.75s
```

Ruff auf allen geänderten Python-Dateien und `git diff --check` waren sauber.
Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
Evidence-Dateien geschrieben.

Vorgesehener Fix-Commit:

```text
fix: close derivation authority edge cases
```

## Fix-Runde 2: Finale Strict-Authority

Ein zweites Controller-Review identifizierte eine verbleibende
Authority-Divergenz: Der Builder führte die strikte Paketvalidierung früh aus
und übergab diesen gespeicherten Report nach der Receipt-Erstellung an
`build_package_authority_context()`. Eine danach erfolgte strict-relevante,
aber nicht receipt-gebundene Änderung konnte deshalb vom Apply-Gate erkannt
werden, während die gerade erzeugte Human Summary weiterhin
`VALID_PACKAGE` meldete.

### TDD RED

Der neue reale Builder-Pfad-Test mutiert direkt nach der Receipt-Erstellung
`reports/card_behavior_plan_report.json`. Er ergänzt eine
strict-relevante linked-runtime-Zeile ohne die erforderliche Runtime-Owner-
Datei.

Vor der Produktionsänderung war der Test erwartungsgemäss rot:

```text
1 failed in 6.72s
```

Die Summary meldete dabei fälschlich `VALID_PACKAGE`; das Apply-Gate
blockierte dasselbe finale Paket bereits mit
`strict_package_validation_failed`.

### Minimale Korrektur

`build_package_authority_context()` akzeptiert keinen extern erzeugten
`strict_validation_report` mehr. Die Funktion führt unmittelbar auf dem
finalen Package selbst `validate_complete_package(package)` aus und
verwendet nur dieses frische Ergebnis für
`strict_validation_passed`.

Der Builder-Aufruf übergibt damit nur noch den Package-Pfad. Es gibt keinen
ignorierten, veralteten oder als Authority missverständlichen
Strict-Report-Parameter mehr.

Task 5 wurde nicht vorweggenommen. Deck-Input-Eligibility und alle übrigen
Task-4-Grenzen blieben unverändert.

### GREEN und Verifikation

Neuer gezielter Builder-Regressionstest:

```text
1 passed in 13.87s
```

Erweiterte Task-4-Apply-Boundary-Suite:

```text
149 passed in 27.02s
```

Betroffene Builder-, Summary-, Configure- und Acceptance-Suite:

```text
169 passed in 14.91s
```

Vollständige Repository-Suite:

```text
2419 passed, 11 skipped in 265.42s
```

Ruff auf allen geänderten Python-Dateien meldete `All checks passed!`.
`git diff --check` war sauber; die Windows-Hinweise zur künftigen
LF/CRLF-Normalisierung sind keine Diff-Fehler.

Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
Evidence-Dateien geschrieben.

Vorgesehener Fix-Commit:

```text
fix: recompute final strict package authority
```
