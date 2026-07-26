# Task 3 Report: Linked Runtime Owner für Darkbishop Benedictus

Status: `DONE`

## Ergebnis

`SW_448` bleibt die fachliche Source-Entität für den
Hero-Power-Transform-Claim. Die physische VisionAI-Zeile
`BeforeUseHeroPowerBonus` gehört jetzt ausschliesslich dem kuratiert verlinkten
Runtime-Owner `EX1_625t` (Mind Spike).

Das erzeugte ShadowPriest-Paket hat damit diese Form:

- `SW_448.json`: metadata-only, `GameCardId=SW_448`, kein
  `BeforeUseHeroPowerBonus`;
- `EX1_625t.json`: `GameCardId=EX1_625t`, genau die beabsichtigte
  `BeforeUseHeroPowerBonus`-Zeile;
- der bestehende Wert bleibt unverändert `10`;
- sechs aktive Deckkarten-Dateien, eine aktive Linked-Runtime-Datei und ein
  metadata-only Source-Record für `SW_448`.

## Implementierung

### Enge Owner-Auflösung

Neu erstellt wurde `src/hsconfig/runtime_entity_owner.py` mit dem gefrorenen
Wertobjekt `RuntimeEntityOwner` und einer fail-closed Owner-Auflösung.

Für normale CardID-Semantik bleibt die Source-Karte ihr eigener Owner. Für
`hero_power_before_use` wird ausschliesslich der explizite
`hero_power_transform`-Eintrag aus dem bereits vorhandenen kuratierten
Identity-Link verwendet. Eine fehlende oder anders geformte Verknüpfung
liefert keinen Owner.

Es gibt keinen Fallback über Kartenname, lokalisierten Namen, Kartentext,
Collectible-Status, Online-Suche oder Datenbankähnlichkeit. Legacy-Listen mit
Option-Links werden nicht als Owner-Map interpretiert.

### Routing und Kompilierung

Akzeptierte Runtime-Zeilen tragen nun getrennt:

- `source_card_id`;
- `runtime_card_id`;
- `link_kind`.

Der Compiler gruppiert und schreibt CardID-Konfigurationen anhand von
`runtime_card_id`. Dadurch werden Dateiname, `GameCardId` und physischer
Zeilen-Owner gemeinsam auf `EX1_625t` gesetzt. Die Source-ID bleibt in
Berichten und Explainability erhalten.

Kann der erforderliche verlinkte Owner nicht aus der kuratierten Map aufgelöst
werden, wird keine aktive Zeile erzeugt. Die stabile Diagnose lautet:

```text
linked_runtime_entity_unresolved
```

### Readiness, Validation und Ownership

Die Deckkarten-Readiness behandelt `SW_448` als `linked_runtime_source`.
`EX1_625t` wird separat unter `linked_runtime_entities` mit der Kategorie
`linked_runtime_entity` geführt. Die verlinkte Entität wird damit nicht als
fehlende Deckkarte gezählt.

Die strikte Paketvalidierung verlangt für jede akzeptierte Linked-Runtime-
Entität:

- die erforderliche Owner-Datei;
- exakte Gleichheit von Dateiname und `GameCardId`.

Das Ownership-Manifest enthält den expliziten Eintrag:

```json
{
  "path": "CardID/EX1_625t.json",
  "owner_kind": "linked_runtime_entity",
  "source_card_id": "SW_448",
  "runtime_card_id": "EX1_625t",
  "link_kind": "hero_power_transform"
}
```

### Explainability und abhängige Contracts

Die Source-to-Runtime-Projektion zeigt nun ausdrücklich:

```text
SW_448 (hero_power_transform_source)
  -> EX1_625t (hero_power)
  -> EX1_625t.json
```

Sie behauptet damit nicht mehr, Benedictus selbst sei eine Hero Power.
Source-Claim-IDs und bisherige Provenienz bleiben erhalten.

Direkt abhängige Contract-Flächen wurden auf dieselbe Owner-Identität
ausgerichtet:

- Source-Contract-Audit projiziert `EX1_625t.json`;
- Surface-Intent verlangt die verlinkte Runtime-Datei;
- Config-Quality inventarisiert die physische Owner-ID;
- Conformance verwendet für den positiven Hero-Power-Canary exakt den
  bestehenden kuratierten `SW_448 -> EX1_625t`-Link.

Apply-Authority, Runtime-Write-Gates, Source-Authority und Step-1/Step-2-
Grenzen wurden nicht gelockert.

## TDD-Evidenz

### RED

Nach Ergänzung der Task-3-Regressions und vor dem Produktcode:

```text
11 failed, 113 passed
```

Die Fehler belegten insbesondere:

- fehlende Source-/Runtime-Owner-Felder;
- physische Emission unter `SW_448`;
- fehlende fail-closed Suppression;
- fehlende `EX1_625t.json`;
- alte ShadowPriest-Erwartungen mit sieben aktiven Deckkarten-Dateien.

### GREEN

Finale fokussierte Semantic-Ownership-Suite:

```text
193 passed in 22.91s
```

Contract-Spine-, Sentinel-, Doctor- und Conformance-Suite:

```text
96 passed in 7.69s
```

Finale vollständige Repository-Suite:

```text
2389 passed, 11 skipped in 237.57s
```

Nach dem letzten reinen Readability-/Lane-Prioritäts-Self-Review wurden die
direkt betroffenen Readiness-/Explainability-/Shadow-Suiten erneut ausgeführt:

```text
91 passed in 12.49s
```

Ruff auf allen durch Task 3 geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` meldete keine Whitespace-Fehler. Die Windows-Hinweise zur
künftigen LF/CRLF-Normalisierung sind keine Diff-Fehler.

Der repo-weite Ruff-Lauf bleibt ausserhalb des Task-3-Diffs mit drei bereits
vorhandenen Befunden in unberührten Task-1/Task-2-Dateien rot. Der repo-weite
`ruff format --check` ist ebenfalls bestehender Baseline-Altbestand und würde
261 Dateien neu formatieren. Es wurde deshalb kein breiter, fachfremder
Formatierungs- oder Cleanup-Diff erzeugt.

## Generierte Paketprüfung

Die abschliessende Prüfung eines frisch in den Pytest-Tempbereich erzeugten
ShadowPriest-Pakets bestätigte:

| Prüfung | Ergebnis |
| --- | --- |
| `SW_448.json` / `GameCardId` | `SW_448` |
| aktive Hero-Power-Zeile in `SW_448.json` | nein |
| `EX1_625t.json` / `GameCardId` | `EX1_625t` |
| `BeforeUseHeroPowerBonus`-Wert | `10` |
| Router-Source | `SW_448` |
| Router-Owner | `EX1_625t` |
| Link-Art | `hero_power_transform` |
| Source-Readiness | `linked_runtime_source` |
| Owner-Readiness | `linked_runtime_entity` |
| Dateiname/`GameCardId`-Match | ja |
| Explainability-Runtime-Datei | `EX1_625t.json` |
| Ownership-Manifest-Pfad | `CardID/EX1_625t.json` |

Es wurde keine andere Linked-Runtime-Entität verschoben.

## Self-Review

- Nur die vorhandene kuratierte Identity-Link-Authority kann einen
  Source-to-Owner-Wechsel auslösen.
- Fehlende, listenförmige, namensgleiche oder textähnliche Links bleiben
  fail-closed.
- Der Runtime-Wert `10` wurde nicht verändert.
- Dateiname, `GameCardId`, Runtime-Inventar, Surface-Intent, Readiness,
  Explainability und Ownership-Manifest verwenden dieselbe physische Owner-ID.
- `SW_448` bleibt über Claim-IDs, Source-ID und Source-Rolle vollständig
  nachvollziehbar.
- Report-only- und normale self-owned CardID-Zeilen behalten ihr bisheriges
  Verhalten.
- Contract-Spine und Operator-Summary bleiben diagnostic-only bzw. die
  unveränderte einzige Apply-Authority.
- Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
  Evidence-Dateien geschrieben.

Reviewer-Vorabprüfung: kein Blocker vor Commit. Das controller-seitige
diff-basierte Review folgt nach dem Push.

## Commit

Vorgesehener Task-Commit:

```text
fix: assign hero power behavior to linked runtime entity
```

## Fix-Runde 1: Autorisierte Owner und eindeutige Runtime-Ownership

Status: `DONE`

### Review-Befunde und Korrektur

Die erste Review-Runde fand zwei wichtige Fail-closed-Lücken:

1. Der Resolver akzeptierte jede formal passende
   `hero_power_transform`-Map.
2. Mehrere Source-Karten konnten denselben `runtime_card_id` beanspruchen;
   abhängige Flächen verwendeten dabei `setdefault` oder Last-write-wins.

Die Linked-Owner-Auflösung erlaubt jetzt ausschliesslich dieses vollständige
Tupel:

```text
source_card_id=SW_448
semantic_reason=hero_power_before_use
link_kind=hero_power_transform
runtime_card_id=EX1_625t
```

Alle anderen expliziten, Supplement- oder künstlichen Zuordnungen werden
fail-closed verworfen. Direkt geprüft sind insbesondere:

- `EX1_625 -> EX1_625t` aus dem vorhandenen Linked-Entity-Supplement;
- `CARD_HP -> HERO_POWER_HP` als formal gültige künstliche Map.

Der Router erzeugt in beiden Fällen keine Zeile und meldet unverändert:

```text
linked_runtime_entity_unresolved
```

### Zentraler Collision-Schutz

`runtime_entity_owner.py` prüft aktive Verhaltenszeilen nun zentral vor der
weiteren Verarbeitung. Beanspruchen unterschiedliche `source_card_id`-Werte
denselben `runtime_card_id`, werden sämtliche aktiven Zeilen dieses Runtime-
Owners verworfen. Der deterministische Diagnosecode lautet:

```text
linked_runtime_entity_owner_collision
```

Die Diagnose enthält zusätzlich den kollidierenden `runtime_card_id` und die
sortierte Liste der konkurrierenden `source_card_ids`.

Compiler, Config Readiness, Source-to-Runtime Explainability, Surface Intent
und Output Ownership Manifest verwenden dieselbe zentrale Partitionierung.
Damit entstehen weder eine aktive Runtime-Zeile noch stilles First-/Last-write-
Verhalten oder doppelte Ownership-Manifest-Zeilen. Die Diagnose wird auf allen
vier Berichtsflächen identisch als `runtime_entity_owner_collisions`
ausgegeben; der Compiler trägt dieselbe Liste auf dem Ergebnisobjekt.

Der Schutz erkennt aktive Compiler-Zeilen auch dann, wenn ein korrupter Plan
das optionale Feld `meaningful_runtime_surface` weglässt.

### TDD-Evidenz

Vor der Produktionsänderung wurden die beiden neuen Regressionen rot
ausgeführt:

```text
2 failed in 0.31s
```

Die Fehler bestätigten:

- die nicht autorisierte `EX1_625`-Transformation wurde noch geroutet;
- `RUNTIME_SHARED.json` wurde bei zwei konkurrierenden Sources noch
  kompiliert.

Finale fokussierte Owner-/Compiler-/Readiness-/Explainability-/Surface-/
Manifest-Suite:

```text
275 passed in 9.29s
```

Installierter Skill, Contract-Spine-Sentinel und fokussierte
Contract-/Boundary-Guardrails:

```text
HSConfig skill is in sync
contract spine sentinel: clean
798 passed in 49.27s
```

Finale vollständige Repository-Suite nach der letzten Testergänzung:

```text
2392 passed, 11 skipped in 239.59s
```

Ruff auf allen in Fix-Runde 1 geänderten Python-Dateien:

```text
All checks passed!
```

`git diff --check` meldet keine Whitespace-Fehler. Der bekannte
repo-weite Formatierungs-Altbestand bleibt unverändert; ein gezielter
`ruff format --check` würde acht bereits von Task 3 berührte Dateien breiter
neu formatieren und wurde deshalb nicht als fachfremder Rewrite angewendet.

### Self-Review

- Die autorisierte Owner-Identität ist ein exaktes Vier-Felder-Tupel und kein
  struktureller Truthy-Check mehr.
- Der vorhandene Supplement-Eintrag für `EX1_625` verleiht keine
  Runtime-Authority.
- Normale selbst besessene CardID-Zeilen behalten ihr bisheriges Verhalten.
- Mehrere Zeilen derselben Source für denselben Runtime-Owner sind keine
  Kollision; erst unterschiedliche Source-IDs schliessen den Owner.
- Kollisions-IDs und Source-Listen werden unabhängig von Eingabereihenfolge
  sortiert.
- Alle betroffenen Konsumenten unterdrücken denselben kollidierenden Owner und
  tragen dieselbe Diagnose.
- Apply-Authority, Runtime-Write-Gates, Source-Authority und Step-1/Step-2-
  Grenzen wurden nicht verändert.
- Es wurden keine Runtime-, HSTuner-, Hearthstone-, Desktop- oder privaten
  Evidence-Dateien geschrieben.

Commit für Fix-Runde 1:

```text
fix: enforce unique linked runtime ownership
```
