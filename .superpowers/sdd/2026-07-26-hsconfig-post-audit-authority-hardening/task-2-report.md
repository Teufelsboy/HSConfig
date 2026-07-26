# Task 2 Report: Acquisition-Provenienz für strategische Receipts

Status: `DONE`

## Ergebnis

Strategische Source-Receipts sind jetzt an eine kanonische Acquisition-
Provenienz gebunden. Nur Inhalte, die an der erfolgreichen direkten
HTTP-Acquisition-Grenze als `live_http` erfasst wurden, erhalten
`authority=live_verified` und können bei passender Exact-Deck-Evidence ein
kanonisches strategisches Receipt erzeugen.

Importierte, manuelle, fixture-basierte und Legacy-Quellen bleiben vollständig
diagnostisch:

| Eingangspfad | mode | authority |
| --- | --- | --- |
| erfolgreicher direkter HTTP-Fetch | `live_http` | `live_verified` |
| importierter/captured Record | `captured_record` | `captured_unverified` |
| Operator-Evidence bzw. Guide-Datei | `manual_evidence` | `manual_unverified` |
| Repository-Fixture-Map | `fixture_map` | `fixture_only` |
| Legacy-Claims-JSON | `legacy_claims_json` | `legacy_unverified` |

Alle Provenienzobjekte enthalten ausschliesslich `mode`, `authority` und einen
kanonischen `sha256:`-Digest der am Eingang gelesenen Bytes. URLs mit
Query-Secrets, Roh-HTML und lokale Benutzerpfade werden nicht in die Provenienz
übernommen.

## Implementierung

### Provenienz-Wertobjekt

Neu erstellt wurde `src/hsconfig/source_acquisition_provenance.py` mit:

- den fünf kanonischen Acquisition-Modi;
- den zugehörigen Authority-Klassifikationen;
- `build_acquisition_provenance()`;
- einer strikten kanonischen Digest-/Authority-Prüfung;
- `strategic_source_provenance_is_verified()`;
- dem stabilen Diagnosecode
  `strategic_provenance_not_live_verified`.

Unbekannte Modi schlagen mit `ValueError` fehl. Ein beliebiger String, ein
verkürzter Digest oder eine inkonsistente Kombination aus Modus und Authority
wird nicht als verifiziert akzeptiert.

### Trust Boundaries und Loader

`src/hsconfig/input_loading.py` überschreibt importierte Provenienzfelder
entsprechend dem tatsächlichen Loader:

- `--claims-json` -> `legacy_claims_json`;
- `--guide-sources-json` und `--source-evidence-json` ->
  `manual_evidence`;
- `--source-documents-json` und `--source-search-results-json` ->
  `captured_record`.

Damit kann ein importiertes JSON mit selbstdeklarierter
`{"mode":"live_http","authority":"live_verified"}`-Struktur keine
Produktionsautorität erlangen. Der Digest wird aus den tatsächlichen
Dateibytes neu berechnet.

Die Fixture-Map wird in `source_acquire_payload()` explizit als
`fixture_map` klassifiziert. Nur der normale Fetch-Pfad verwendet
`live_http`.

### Objektidentische Propagation

Die am Byte-Eingang erzeugte Provenienz wird ohne Rekonstruktion durch folgende
Kette getragen:

1. `source_acquisition.py`
2. `source_claim_compiler.py`
3. `commands/source_workflow.py`
4. `source_autopilot.py`
5. `source_document_drafter.py`
6. `commands/configure.py`
7. `preconfig_context.py`
8. `source_document_builder.py`
9. `source_document_model.py`

Für den realen `configure --online-source --auto-source`-Ablauf wurde ein
interner In-Memory-Handoff ergänzt. Dadurch erreicht dasselbe
Provenienzobjekt den finalen Package-Builder. Die parallel geschriebenen
JSON-Artefakte bleiben weiterhin exportierbare Diagnoseartefakte; ein späterer
erneuter Dateiimport wird korrekt als `captured_record` klassifiziert.

Dasselbe In-Memory-Prinzip bewahrt bei Operator-Evidence die bereits
unverifizierte `manual_evidence`-Klassifikation. Es gibt keinen CLI-Schalter,
mit dem ein Operator den internen Trusted-Handoff setzen kann.

### Receipt-Minting und Surface-Gates

Der Builder prüft die Provenienz vor Exact-Evidence-Prüfung, Signing und
Append:

- unverified Provenienz -> kein Receipt;
- verified Live-Provenienz plus unpassende/fehlende Exact-Evidence ->
  kein Receipt;
- verified Live-Provenienz plus vollständige passende Exact-Evidence ->
  kanonisches Receipt mit exakt derselben Provenienz.

Mulligan-, GlobalValues- und Combo-Gates verlangen zusätzlich:

- eine verified Live-Provenienz am Claim;
- Claim-ID und kanonische Claim-Signatur;
- passenden Ziel-Deck-Fingerprint;
- exakt dieselbe Provenienz im Receipt.

Fehlende Live-Provenienz wird mit
`strategic_provenance_not_live_verified` diagnostiziert. Autopilot nennt als
nächste Aktion `acquire_strategic_source_via_live_http`.

Nichtstrategische Claim-Extraktion, statische Semantik und Diagnoseberichte
bleiben für alle fünf Provenienzmodi erhalten. Fixture- und Captured-Tests
erwarten keine falsche Strong-Closure und keine strategischen Receipts mehr.

### Conformance

`source_contract_conformance.py` konstruiert keine `live_verified`-Dictionaries
mehr. Positive Conformance-Proben beziehen ihre Provenienz über einen
erfolgreichen `collect_public_source_records()`-Durchlauf. Damit bleibt
`source_acquisition.py` die einzige Komponente, die Live-Authority zuweist.

## Geänderte Produktionsdateien

- `src/hsconfig/source_acquisition_provenance.py` (neu)
- `src/hsconfig/source_acquisition.py`
- `src/hsconfig/source_claim_compiler.py`
- `src/hsconfig/source_autopilot.py`
- `src/hsconfig/source_document_drafter.py`
- `src/hsconfig/source_document_builder.py`
- `src/hsconfig/source_document_model.py`
- `src/hsconfig/input_loading.py`
- `src/hsconfig/preconfig_context.py`
- `src/hsconfig/commands/source_workflow.py`
- `src/hsconfig/commands/configure.py`
- `src/hsconfig/source_contract_conformance.py`

## Test- und Fixture-Migration

Die Task-Tests wurden um folgende Grenzen erweitert:

- exakte Klassifikationsmatrix aller fünf Modi;
- deterministischer kanonischer Digest;
- Single-Byte-Digeständerung;
- unbekannter Modus fail-closed;
- erfolgreicher direkter HTTP-Fetch;
- Live-vs-Captured bei identischem Inhalt;
- forged Live-Metadaten in Claims-, Source-Evidence-, Guide-, Source-Document-
  und Source-Search-Loadern;
- Fixture-Map-Reklassifikation;
- objektidentische Propagation Record -> Evidence -> Document -> Claim ->
  Receipt;
- leerer Receipt-Satz und stabile Diagnose für alle unverifizierten Modi;
- positiver Exact-Fingerprint-Live-Fall;
- realer `configure`-End-to-End-Fall bis zum finalen
  `guide_claim_bundle.json`.

Abhängige Legacy-Tests wurden fachlich migriert:

- Fixture-Maps und importierte Source-Document-Dateien gelten als
  diagnostic-only;
- importierte strategische Mulligan-/Combo-/Posture-Claims erzeugen keine
  Produktionsreceipts;
- Policy- und statische nichtstrategische Fallbacks bleiben load-safe;
- positive reine Downstream-Unitfixtures modellieren explizit die bereits
  erfolgreiche Live-Acquisition-Grenze.

Insgesamt wurden neben den Kern-Tasktests die direkt abhängigen
Authority-, CLI-, ShadowPriest-, Archetype-, Matrix-, Lifecycle-, Audit- und
Contract-Spine-Tests aktualisiert. Es wurden keine Runtime-Dateien,
HSTuner-Dateien oder Desktop-Konfigurationen geschrieben.

## TDD-Evidenz

### Baseline

Vor den neuen Tests:

```text
110 passed
```

### RED

Nach Ergänzung der Provenienz- und Forgery-Regressions, vor Produktcode:

```text
15 failed, 110 passed
```

Die Fehler belegten die fehlenden Punkte:

- kein Provenienzmodul;
- keine Acquisition-Klassifikation am Fetch;
- importierte forged Live-Felder blieben vertrauenswürdig;
- Provenienz ging zwischen Record, Autopilot, Source-Dokument und Receipt
  verloren;
- Fixtures konnten weiterhin strategische Receipts erzeugen.

Die unabhängige Review deckte später zusätzlich den fehlenden finalen
Live-Handoff im realen Configure-Ablauf auf. Der neue End-to-End-Test war vor
dem Fix erwartungsgemäss rot:

```text
1 failed
assert receipts
```

### GREEN

Erste fokussierte Provenienz-Suite:

```text
125 passed
```

Finale Task-2-Kompatibilitätssuite:

```text
278 passed in 7.60s
```

Finale vollständige Repository-Suite:

```text
2373 passed, 11 skipped in 235.45s
```

Ruff auf allen geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` meldete keine Whitespace-Fehler. Die Windows-Hinweise zur
künftigen LF/CRLF-Normalisierung sind keine Diff-Fehler.

## Unabhängige Review

Die erste read-only Review verifizierte, dass alle vier unverifizierten
Quellklassen fail-closed bleiben, fand aber zwei echte Blocker:

1. Live-Provenienz wurde nach Autopilot serialisiert und vor dem finalen Builder
   als Captured reimportiert.
2. Production-Conformance konstruierte Live-Provenienz ausserhalb der
   Acquisition-Grenze.

Beide Befunde wurden behoben und erneut geprüft. Ergebnis der Re-Review:

```text
38 passed
keine verbleibenden Task-2-Blocker
```

Die Review bestätigte ausserdem:

- finaler Live-Configure-Pfad mintet Receipts;
- alle forged Importpfade bleiben unverifiziert;
- Fixture-, Manual-, Captured- und Legacy-Modi minten keine strategischen
  Receipts;
- Claim-ID, Signatur, Fingerprint und Provenienz sind beim Receipt-Verbrauch
  gebunden;
- keine sensitiven Rohdaten werden in der Provenienz gespeichert.

## Scope-Entscheidung und Restrisiko

`targeting_rule` ist bereits als strategisch für Receipt- und Strong-Credit
klassifiziert. Der bestehende CardID-Behavior-Router kann einen solchen Claim
jedoch unabhängig vom Task-1/Task-2-Receipt-Kontext als runtime-lowerable
behandeln. Die Review reproduzierte, dass ein Captured-Targeting-Claim kein
Receipt und keinen Strong-Credit erhält, aber weiterhin eine CardID-Zeile
erzeugen kann.

Dieser Punkt ist kein Task-2-Blocker: Der explizite Task-2-Scope bindet
Receipt-Minting und receipt-backed Strong-Authority an Acquisition-Provenienz.
Eine Änderung der CardID-Targeting-Autorisierung wäre eine separate
Surface-Policy-Erweiterung mit neuem Receipt-Kontext im Behavior-Router und
eigenen Kompatibilitätstests. Sie wurde hier bewusst nicht stillschweigend
eingeführt.

## Commit

Vorgesehener Task-Commit:

```text
fix: bind strategic receipts to live acquisition provenance
```

## Fix-Runde 1

Status: `DONE`

### Behobene Review-Befunde

1. Ein beliebig injizierter Top-Level-`fetcher` kann keine
   `live_http`-/`live_verified`-Provenienz mehr erzeugen. Nur der interne
   Direkt-HTTP-Pfad mit `fetcher=None` darf Live-Authority zuweisen. Tests
   ersetzen bei positiven Live-Fällen ausschliesslich die tieferliegende
   Netzwerkfunktion `_fetch_with_validated_address`.
2. Alle vergleichbaren strategischen Positiv-Fixtures für Mulligan, Combo und
   GlobalValues beziehen Live-Provenienz über den gemeinsamen Test-Helper
   `tests/helpers/live_acquisition.py`. Manuelle Live-Dictionaries und direkte
   Authority-Erzeugung in diesen Downstream-Fixtures wurden entfernt.
   Production-Conformance verwendet jetzt ausdrücklich `fixture_map`, bleibt
   diagnostic-only und erzeugt keine strategischen Receipts.
3. Der kanonische Provenienz-Verifier verlangt exakt die Schlüssel
   `{mode, content_sha256, authority}`. Strategische Receipts erhalten ein neu
   normalisiertes Drei-Feld-Objekt. Zusätzliche Felder wie `raw_html`,
   `local_path` oder eine URL mit Query-Secret verhindern das Receipt-Minting
   vollständig und gelangen nicht in Receipts.

### TDD RED

Vor dem Produktcode-Fix:

```powershell
python -m pytest -q `
  tests/test_source_acquisition.py::test_injected_fetcher_cannot_assign_live_authority `
  tests/test_source_acquisition.py::test_canonical_provenance_rejects_additional_fields `
  tests/test_source_document_drafter.py::test_strategic_receipt_rejects_noncanonical_provenance_fields `
  tests/test_source_contract_conformance.py::test_conformance_strategic_examples_remain_diagnostic_only `
  --tb=short --show-capture=no
```

Ergebnis:

```text
9 failed in 0.65s
```

Die neun Fehler deckten exakt die drei Review-Befunde ab: zwei unerlaubte
Live-Upgrades durch injizierte Fetcher, drei akzeptierte Provenienzobjekte mit
Zusatzfeldern, drei dadurch erzeugte strategische Receipts und eine
Conformance-Probe mit unerlaubter Live-Authority.

### GREEN und Regression

Die neue Regression-Suite wurde nach dem minimalen Produktcode-Fix grün:

```text
9 passed in 0.43s
```

Fokussierte Provenienz-/Receipt-/Conformance-/Combo-/Mulligan-/
GlobalValues-Prüfung:

```text
399 passed in 19.58s
```

Nach der Migration des zugehörigen Contract-Spine-Sentinels:

```text
192 passed in 7.77s
```

Der erste vollständige Lauf fand genau eine veraltete Sentinel-Erwartung:

```text
1 failed, 2381 passed, 11 skipped in 242.99s
```

Der Sentinel erwartete noch strategische Emission aus der nun bewusst
unautorisierten Conformance-Fixture. Nach Ausrichtung auf die
diagnostic-only-Sperre war die vollständige Repository-Suite grün:

```text
2382 passed, 11 skipped in 238.30s
```

Ruff auf allen geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` war sauber; es erschienen nur die bestehenden
Windows-Hinweise zur künftigen LF/CRLF-Normalisierung.

### Self-Review

- Repository-weite Suche bestätigt: Verbleibende `live_http`-/
  `live_verified`-Literale in Tests sind Output-Assertions, Negativ-/Forgery-
  Fälle oder direkte Unit-Tests des Provenienz-Wertobjekts. Strategische
  Downstream-Positiv-Fixtures minten keine Authority selbst.
- Die neue Trust-Grenze ist fail-closed: Ein injizierter Fetcher wird bei
  angefordertem Live-Modus als `captured_record` klassifiziert; explizit
  schwächere Modi bleiben schwächer.
- Der kanonische Verifier akzeptiert weder unbekannte noch zusätzliche Felder.
  Der Receipt-Builder gibt nur die drei kanonischen String-Felder weiter.
- Conformance und Contract-Spine bleiben diagnostic-only und melden die
  fehlende Live-Provenienz, ohne Apply-Gates oder Runtime-Schreibrechte zu
  lockern.
- Keine Runtime-, HSTuner- oder Desktop-Dateien wurden geschrieben.

Vorgesehener Fix-Commit:

```text
fix: seal live acquisition provenance boundary
```
