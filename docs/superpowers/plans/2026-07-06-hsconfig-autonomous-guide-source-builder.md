# HSConfig Autonomous Guide Source Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make HSConfig stronger at the one job it owns: from deck name and deck code, build a guide-aligned HearthRanger VisionAI CustomConfig package with meaningful Mulligan, GlobalValues, CardID behavior, and Combo inputs before games are played. The workflow stays lean and deck-neutral, but it becomes less generic, less conservative, and much clearer about whether the package is technically valid and semantically strong.

**Architecture:** Add a small autonomous guide-source control plane around the existing config compiler. A new builder normalizes researched guide/card/archetype claims into `guide_sources.json`, `candidate_archetypes.json`, and `guide_builder_receipt.json`. `prepare` and package reports consume those facts, emit `operator_summary.json`, and keep runtime JSON protected by stricter condition and syntax guards. HSConfig still does not parse games, analyze winrate, run HSTuner, or do post-game candidate promotion.

**Tech Stack:** Python 3.11+, existing `hearthstone` dependency, standard library JSON/URL/date tooling, pytest. Do not add web scraping or browser dependencies in this wave. Codex/skill-level research can use web tools; the package normalizes and compiles researched inputs.

## Global Constraints

- Keep the repo small. Do not copy HSTuner replay, HDT, Power.log, winrate, or patch-promotion logic into HSConfig.
- Do not commit raw runtime logs, HDT files, Power.log, HSReplay exports, or local HearthRanger runtime evidence.
- `prepare` may write reports and generated config packages. It must not claim games were played or that runtime behavior improved.
- `apply` may write only through the existing runtime writer path.
- Treat the HearthRanger VisionAI JSON surface as a guarded output format. Unsupported or ambiguous conditions are report-only and must not reach runtime JSON.
- Preserve all existing generated CustomConfig keys unless a task explicitly changes the compiler surface.
- The package can be aggressive in config intent, but it must be explicit about evidence level: source-backed, static-card-semantics-backed, low-confidence fallback, or blocked.
- Each task below should land with tests before implementation changes where practical.

---

## Task 1: Add Operator Summary And Readiness Gate

**Purpose:** Stop using one optimistic readiness label for very different states. Technical JSON validity and semantic guide strength need separate statuses.

**Files to inspect first:**

- `src/hsconfig/cli.py`
- `src/hsconfig/prepare.py` or the current prepare orchestration module if named differently
- `src/hsconfig/reports.py`
- `tests/test_prepare_cli.py`
- `tests/test_package_reports.py`

**Implementation steps:**

- [ ] Create `src/hsconfig/operator_summary.py`.
- [ ] Add a small public function:

```python
def build_operator_summary(
    *,
    deck_name: str,
    deck_code: str,
    technical_validation: dict,
    guide_source_depth: dict | None,
    unsupported_conditions: list[dict] | None,
    globalvalue_authority: dict | None,
    generated_files: list[str],
) -> dict:
    ...
```

- [ ] The returned JSON must contain these top-level keys:

```json
{
  "schema_version": 1,
  "deck": {
    "name": "ShadowPriest",
    "deck_code_hash": "sha256:..."
  },
  "technical_status": "VALID_PACKAGE",
  "semantic_status": "SOURCE_BACKED_STRONG",
  "next_action": "READY_TO_APPLY_OR_HANDOFF",
  "apply_policy": "ALLOWED",
  "primary_blockers": [],
  "warnings": [],
  "generated_files": []
}
```

- [ ] Implement status mapping:
  - `technical_status`: `VALID_PACKAGE`, `INVALID_PACKAGE`.
  - `semantic_status`: `SOURCE_BACKED_STRONG`, `STATIC_SEMANTICS_USABLE`, `NEEDS_MORE_RESEARCH`, `INSUFFICIENT_FOR_STRONG_CONFIG`.
  - `next_action`: `READY_TO_APPLY_OR_HANDOFF`, `READY_WITH_WARNINGS`, `RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG`, `FIX_PACKAGE_BEFORE_APPLY`.
  - `apply_policy`: `ALLOWED`, `ALLOWED_WITH_WARNINGS`, `BLOCKED`.
- [ ] `INVALID_PACKAGE` always maps to `FIX_PACKAGE_BEFORE_APPLY` and `BLOCKED`.
- [ ] `NEEDS_MORE_RESEARCH` does not make JSON invalid, but it must not be reported as a strong guide package.
- [ ] Wire `prepare` to write `operator_summary.json` into the same report/output folder that already receives acceptance/readiness artifacts.
- [ ] Keep existing old readiness labels in older reports only if tests or compatibility require them, but make `operator_summary.json` the operator-facing source.

**Tests first:**

- [ ] Add `tests/test_operator_summary.py`.
- [ ] Cover:
  - valid package + strong guide sources -> `READY_TO_APPLY_OR_HANDOFF`, `ALLOWED`.
  - valid package + no guide depth -> `RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG`, `ALLOWED_WITH_WARNINGS` or `BLOCKED` depending current package policy.
  - invalid package -> `FIX_PACKAGE_BEFORE_APPLY`, `BLOCKED`.
  - unsupported runtime conditions appear as warnings or blockers according to severity.
- [ ] Add a CLI-level assertion that `prepare` writes `operator_summary.json`.

**Verification:**

```powershell
python -m pytest tests/test_operator_summary.py tests/test_prepare_cli.py -q
```

**Expected outcome:** `prepare` always gives the operator a direct machine-readable answer: what is technically valid, how strong the guide evidence is, and what the next action is.

**Commit message:** `Add operator summary readiness gate`

---

## Task 2: Introduce Guide Source Builder Contract

**Purpose:** Create a normalized input layer for guide and archetype research, without letting researched prose write runtime JSON directly.

**Files to inspect first:**

- `src/hsconfig/guide_claim_builder.py`
- `src/hsconfig/guide_sources.py`
- `src/hsconfig/research_contract.py`
- `src/hsconfig/card_roles.py`
- `tests/test_guide_claim_builder.py`
- `tests/test_research_contract.py`

**Implementation steps:**

- [ ] Create `src/hsconfig/guide_source_builder.py`.
- [ ] Define these functions:

```python
def build_deck_fingerprint(deck_identity: dict, cards: list[dict]) -> dict:
    ...

def build_candidate_archetypes(
    *, deck_name: str, deck_identity: dict, card_roles: list[dict], source_documents: list[dict]
) -> dict:
    ...

def build_guide_sources(
    *, deck_name: str, deck_identity: dict, card_roles: list[dict], source_documents: list[dict]
) -> dict:
    ...

def build_guide_builder_receipt(
    *, deck_name: str, deck_identity: dict, source_documents: list[dict], guide_sources: dict
) -> dict:
    ...
```

- [ ] The builder must accept already-researched source documents in this shape:

```json
{
  "source_id": "shadowpriest-guide-001",
  "source_url": "https://...",
  "source_title": "Guide title",
  "source_family": "guide",
  "retrieved_at": "2026-07-06T00:00:00Z",
  "deck_name": "ShadowPriest",
  "archetype": "aggro_burn",
  "claims": [
    {
      "claim_kind": "mulligan_keep",
      "cards": ["CS3_028"],
      "condition": {"coin": true},
      "confidence": "source_backed",
      "reason": "Keep with coin when curve needs burst"
    }
  ]
}
```

- [ ] Support zero source documents by emitting a static-semantics fallback receipt:

```json
{
  "source_depth_status": "static_semantics_only",
  "source_count": 0,
  "static_card_semantics_used": true
}
```

- [ ] Support source documents by emitting:

```json
{
  "source_depth_status": "source_backed",
  "source_count": 2,
  "claim_count": 37,
  "stale_source_count": 0
}
```

- [ ] Do not fetch search engine results inside this module. The skill/Codex research pass can discover URLs and produce source documents; this module normalizes them.
- [ ] Use `source_url`, `retrieved_at`, and `source_family` for freshness and provenance scoring. Keep scoring simple:
  - source-backed current guide: strongest
  - official/static card semantics: usable
  - old or unmatched guide: warning
  - no source and weak static roles: needs more research
- [ ] Ensure output has no raw long prose. Store short reasons and citations only.

**Tests first:**

- [ ] Add `tests/test_guide_source_builder.py`.
- [ ] Cover:
  - source-backed guide produces `source_depth_status=source_backed`.
  - empty source docs produce `static_semantics_only`.
  - stale guide is represented as warning, not silently accepted.
  - unmatched deck/archetype source is kept but downgraded.
  - every claim has stable `claim_id`.

**Verification:**

```powershell
python -m pytest tests/test_guide_source_builder.py tests/test_guide_claim_builder.py -q
```

**Expected outcome:** HSConfig has a small, explicit research normalization boundary.

**Commit message:** `Add guide source builder contract`

---

## Task 3: Add Research-Deck CLI Command

**Purpose:** Give the skill a repeatable command for turning a deck and researched source documents into package inputs.

**Files to inspect first:**

- `src/hsconfig/cli.py`
- `src/hsconfig/deckstring_decode.py`
- `src/hsconfig/hearthstonejson.py`
- `tests/test_cli.py`

**Implementation steps:**

- [ ] Add CLI command:

```powershell
hsconfig research-deck `
  --deck-name ShadowPriest `
  --deck-code "<deck code>" `
  --out out\ShadowPriest\research `
  --source-documents-json source_documents.json `
  --json
```

- [ ] Make `--source-documents-json` optional. If omitted, output static-semantics fallback research.
- [ ] Write these artifacts:
  - `deck_fingerprint.json`
  - `candidate_archetypes.json`
  - `guide_sources.json`
  - `guide_builder_receipt.json`
- [ ] JSON stdout must include:

```json
{
  "status": "OK",
  "deck_name": "ShadowPriest",
  "source_depth_status": "source_backed",
  "written_files": []
}
```

- [ ] If source input is malformed, fail with non-zero exit and a concise JSON error when `--json` is set.
- [ ] Keep this command offline/deterministic. It normalizes research; it does not browse.

**Tests first:**

- [ ] Add `tests/test_research_deck_cli.py`.
- [ ] Cover command success with no source docs.
- [ ] Cover command success with two source docs and at least two claims.
- [ ] Cover malformed JSON error.
- [ ] Cover output file existence and schema-critical keys.

**Verification:**

```powershell
python -m pytest tests/test_research_deck_cli.py tests/test_cli.py -q
```

**Expected outcome:** A repeatable pre-prepare step exists for autonomous deck research normalization.

**Commit message:** `Add research-deck command`

---

## Task 4: Wire Guide Builder Into Prepare Without Runtime Bloat

**Purpose:** Let `prepare` consume generated guide sources and report source depth without making the runtime compiler depend on web or long research prose.

**Files to inspect first:**

- `src/hsconfig/cli.py`
- `src/hsconfig/prepare.py`
- `src/hsconfig/guide_sources.py`
- `src/hsconfig/package_writer.py`
- `tests/test_prepare_cli.py`

**Implementation steps:**

- [ ] Add `prepare` arguments:
  - `--guide-sources-json <path>` if not already present.
  - `--source-documents-json <path>` as a convenience input.
  - `--auto-research-fallback` defaulting to enabled if no guide source is supplied.
- [ ] If `--guide-sources-json` exists, use it directly.
- [ ] If only `--source-documents-json` exists, run the guide source builder in-memory and write generated research artifacts under the package report folder.
- [ ] If neither exists and fallback is enabled, run static-semantics fallback and mark semantic status accordingly.
- [ ] If fallback is disabled and no guide source exists, `operator_summary.json` must say `RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG`.
- [ ] Runtime JSON generation should consume normalized guide claims only. It must not store full guide prose.
- [ ] Report written research artifacts in `operator_summary.generated_files`.

**Tests first:**

- [ ] Extend `tests/test_prepare_cli.py`.
- [ ] Cover:
  - prepare with `--source-documents-json` writes guide builder artifacts.
  - prepare without source docs writes fallback artifacts and semantic warning.
  - prepare with malformed source docs fails before writing runtime JSON.

**Verification:**

```powershell
python -m pytest tests/test_prepare_cli.py tests/test_operator_summary.py tests/test_guide_source_builder.py -q
```

**Expected outcome:** The normal path can be `research-deck -> prepare`, but `prepare` can still run from a deck alone with an honest semantic status.

**Commit message:** `Wire guide research into prepare`

---

## Task 5: Fix Mulligan Rule Identity And Conditional Keeps

**Purpose:** Support multiple guide-backed keep/discard rules for the same card. Current card-level de-duplication loses useful conditional mulligan guidance.

**Files to inspect first:**

- `src/hsconfig/mulligan_plan.py`
- `src/hsconfig/compile_mulligan.py`
- `src/hsconfig/condition_format.py`
- `tests/test_mulligan_plan.py`
- `tests/test_compile_mulligan.py`

**Implementation steps:**

- [ ] Remove card-only de-duplication in `build_mulligan_plan`.
- [ ] Replace with rule identity:

```python
def mulligan_rule_key(rule: dict) -> tuple:
    return (
        rule.get("card"),
        rule.get("action"),
        rule.get("condition", "*"),
        tuple(sorted(rule.get("source_claim_ids", []))),
    )
```

- [ ] Preserve multiple rules for the same card when conditions differ.
- [ ] Add explicit action precedence:
  - exact source-backed discard with condition wins over fallback keep for that condition.
  - exact source-backed keep wins over generic wildcard discard.
  - wildcard discard remains last.
- [ ] Add support for these normalized condition fields before runtime lowering:
  - `coin`
  - `nocoin`
  - `opponent_class`
  - `hand_contains`
  - `hand_contains_any`
  - `combo_partner`
  - `runtime_condition`
- [ ] Store unsupported condition rules in `mulligan_plan["suppressed_rules"]` and do not compile them into runtime JSON.
- [ ] Keep runtime output stable for simple existing claims.

**Tests first:**

- [ ] Update `tests/test_mulligan_plan.py`.
- [ ] Add cases:
  - same card has coin keep and no-coin discard.
  - same card has matchup-specific keep and generic discard.
  - unsupported free-form condition is suppressed.
  - fallback wildcard discard still exists when concrete keeps exist.
- [ ] Update `tests/test_compile_mulligan.py` if compiler expects a flat rule list only.

**Verification:**

```powershell
python -m pytest tests/test_mulligan_plan.py tests/test_compile_mulligan.py -q
```

**Expected outcome:** Mulligan output can become guide-shaped instead of "one default hold plus wildcard discard".

**Commit message:** `Support conditional mulligan rules`

---

## Task 6: Harden Runtime Condition Grammar

**Purpose:** Prevent invalid HearthRanger conditions from reaching runtime JSON while allowing documented simple VisionAI expressions.

**Files to inspect first:**

- `src/hsconfig/condition_format.py`
- `src/hsconfig/compile_mulligan.py`
- `src/hsconfig/compile_card_behavior.py`
- `tests/test_condition_format.py`

**Implementation steps:**

- [ ] Extend `condition_format.py` with a narrow classifier:

```python
@dataclass(frozen=True)
class LoweredCondition:
    value: str
    status: str
    reason: str | None = None
```

- [ ] Keep the old public function if callers depend on it, but route it through the classifier.
- [ ] Allow these runtime forms:
  - `*`
  - `coin`
  - `nocoin`
  - `my_hand(count()) == <int>`
  - `my_hand(count(),cardid=<CARDID>) > 0`
  - `opp_hero(count(),<class>=true) > 0`
  - `my_target(count(),hero=true) > 0`
  - `my_discover(count(),cardid=<CARDID>) > 0`
  - `AND` / `OR` joins of allowed atoms
  - filter pipe `|` only inside supported filter argument lists, not as top-level selector
- [ ] Convert structured condition dicts to allowed atoms where possible.
- [ ] Any unknown string condition gets `status=unsupported` unless it matches the allowlist.
- [ ] Surfaces must treat unsupported conditions as report-only, not runtime JSON.
- [ ] Include the unsupported condition reason in `operator_summary.warnings` or package reports.

**Tests first:**

- [ ] Add or extend `tests/test_condition_format.py`.
- [ ] Cover each allowed atom.
- [ ] Cover `AND` and `OR`.
- [ ] Cover top-level `|` rejection.
- [ ] Cover arbitrary prose rejection.
- [ ] Cover dict-to-runtime conversion for coin/no-coin/opponent class/hand contains.

**Verification:**

```powershell
python -m pytest tests/test_condition_format.py tests/test_mulligan_plan.py tests/test_compile_card_behavior.py -q
```

**Expected outcome:** More conditional logic is possible, but load-error risk stays controlled.

**Commit message:** `Guard runtime condition grammar`

---

## Task 7: Expand GlobalValues Authority Without Wild Swings

**Purpose:** Let Step 1 adjust GlobalValues more intelligently from deck posture and source-backed intent, without turning every key up or down.

**Files to inspect first:**

- `src/hsconfig/globalvalues_authority.py`
- `src/hsconfig/compile_globalvalues.py`
- `src/hsconfig/gameplan.py`
- `tests/test_globalvalues_authority.py`
- `tests/test_compile_globalvalues.py`

**Implementation steps:**

- [ ] Replace single aggressive posture handling with a posture overlay matrix.
- [ ] Support these posture names:
  - `aggro_burn`
  - `token_board`
  - `weapon_pressure`
  - `hero_power_pressure`
  - `combo_setup`
  - `deathrattle_recruit`
  - `control_value`
- [ ] Each posture overlay must declare:

```json
{
  "posture": "aggro_burn",
  "allowed_keys": {
    "FirstTurnValueWeight": {"operation": "set", "value": 0.75, "reason": "..."},
    "SecondTurnValueWeight": {"operation": "set", "value": 0.25, "reason": "..."}
  },
  "blocked_keys": {
    "SomeRuntimeOnlyKey": "requires post-game evidence"
  }
}
```

- [ ] Keep full-key preservation: all Default CustomConfig keys still exist in output if that is current behavior.
- [ ] Add support for source-backed claim kind if current claim schema supports it. If not, derive posture from existing `gameplan_posture` and `card_role_map`.
- [ ] Add `globalvalue_authority_matrix.json` fields:
  - `key`
  - `source`
  - `operation`
  - `value`
  - `authority`
  - `reason`
  - `blocked_reason`
- [ ] Make blocked keys visible in `operator_summary`.
- [ ] Do not add post-game numeric tuning in this repo.

**Tests first:**

- [ ] Extend `tests/test_globalvalues_authority.py`.
- [ ] Add one test per main posture category where at least one key differs.
- [ ] Add test that unknown posture keeps baseline.
- [ ] Add test that runtime-only/tuning-only keys remain blocked.
- [ ] Add compiler test that output still preserves the complete key set.

**Verification:**

```powershell
python -m pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py -q
```

**Expected outcome:** GlobalValues are deck-shaped and assertive where Step 1 can justify it, but never random mass edits.

**Commit message:** `Expand GlobalValues authority matrix`

---

## Task 8: Preserve Sideboards And Add Identity Graph Reports

**Purpose:** Make deck identity more reliable for modern deckstrings and future generated/sideboard-aware semantics.

**Files to inspect first:**

- `src/hsconfig/deckstring_decode.py`
- `src/hsconfig/deck_identity.py`
- `src/hsconfig/hearthstonejson.py`
- `tests/test_deckstring_decode.py`
- `tests/test_deck_identity.py`

**Implementation steps:**

- [ ] Preserve deckstring sideboards from decoded deckstrings instead of discarding them.
- [ ] Add output fields:

```json
{
  "main_deck": [],
  "sideboards": [],
  "card_count": 30,
  "sideboard_count": 0,
  "format": "wild"
}
```

- [ ] Add `src/hsconfig/identity_graph.py`.
- [ ] Produce `identity_graph_report.json` during `research-deck` and `prepare` report generation.
- [ ] Report should contain:
  - deck name
  - deck code hash
  - main deck card multiset
  - sideboard card multiset
  - HearthstoneJSON card build/retrieval receipt if available
  - inferred hero class
  - inferred starting hero power when reliably known
  - missing identity fields
- [ ] Add a separate `identity_gap_report.json` when required facts are missing.
- [ ] Do not attempt full generated-token closure in this task. Mark generated/token closure as `not_in_scope_for_step1_identity_graph`.
- [ ] For HearthstoneJSON, add a receipt wrapper that records:
  - URL or local source used
  - retrieved timestamp
  - card count
  - build number or version if the payload contains it

**Tests first:**

- [ ] Extend `tests/test_deckstring_decode.py` with a fixture containing sideboards if available.
- [ ] Add `tests/test_identity_graph.py`.
- [ ] Mock HearthstoneJSON retrieval receipt; do not call the network in tests.
- [ ] Cover missing hero power as gap, not exception.

**Verification:**

```powershell
python -m pytest tests/test_deckstring_decode.py tests/test_deck_identity.py tests/test_identity_graph.py -q
```

**Expected outcome:** Every generated config has a clearer identity spine, and sideboard information is not silently lost.

**Commit message:** `Add identity graph reports`

---

## Task 9: Update Skill And Operator Docs

**Purpose:** Make the human and Codex workflow match the new architecture: research normalization first, then prepare, then apply/handoff.

**Files to inspect first:**

- `README.md`
- `docs/operator/README.md`
- `docs/design.md`
- `docs/superpowers/plans/`
- `C:\Users\darbo\.codex\skills\hsconfig\SKILL.md`

**Implementation steps:**

- [ ] Update `README.md` to show the short path:

```powershell
hsconfig research-deck --deck-name ... --deck-code ... --out ...
hsconfig prepare --deck-name ... --deck-code ... --guide-sources-json ... --out ...
hsconfig apply --package ...
```

- [ ] Update operator docs to explain:
  - HSConfig owns pre-game config generation only.
  - HSTuner owns post-game log analysis and tuning loops.
  - `operator_summary.json` is the main readiness file.
  - `semantic_status` is not the same as runtime validity.
- [ ] Update the installed `hsconfig` skill instructions so Codex:
  - performs guide/source research before `prepare` when online access is available.
  - writes or normalizes source documents through `research-deck`.
  - treats `NEEDS_MORE_RESEARCH` as a signal to improve source inputs rather than pretending the config is optimal.
  - does not ask for human approval before applying if the package is technically valid and the user requested autonomous operation.
- [ ] Remove stale docs language that implies only default Mulligan or only in-hand priority is expected.
- [ ] Do not add large generated example outputs to docs.

**Tests first:**

- [ ] Add or extend docs tests if the repo has them, likely `tests/test_docs.py` or `tests/test_skill_docs.py`.
- [ ] Add `rg` checks in test or verification for banned active-doc phrases:
  - "default-only mulligan"
  - "guide source as merely optional"
  - "post-game tuning owned by HSConfig"

**Verification:**

```powershell
python -m pytest tests/test_skill_docs.py tests/test_docs.py -q
rg -n "default-only mulligan|post-game tuning owned by HSConfig|guide source as merely optional" README.md docs C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

The `rg` command should return no active-doc matches.

**Expected outcome:** The skill and docs instruct the same lean but strong workflow.

**Commit message:** `Document autonomous guide workflow`

---

## Task 10: Add Multi-Deck E2E Matrix Tests

**Purpose:** Prove the workflow is deck-neutral across multiple archetypes, not only ShadowPriest.

**Files to inspect first:**

- Existing E2E tests under `tests/`
- Any fixture folder under `tests/fixtures/`
- `src/hsconfig/cli.py`

**Deck matrix for tests:**

Use a small representative subset in fast tests:

```json
[
  {
    "deck_name": "ShadowPriest",
    "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="
  },
  {
    "deck_name": "BigShaman",
    "deck_code": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="
  },
  {
    "deck_name": "PirateRogue",
    "deck_code": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA=="
  }
]
```

**Implementation steps:**

- [ ] Add `tests/test_autonomous_guide_workflow_e2e.py`.
- [ ] For each deck:
  - run the research builder in process or through CLI helper.
  - run prepare into a temp directory.
  - assert `operator_summary.json` exists.
  - assert `technical_status=VALID_PACKAGE`.
  - assert runtime package contains `GlobalValues.json`, `Mulligan.json`, and at least one per-card behavior file when the current compiler supports it.
  - assert unsupported conditions are reported and not present in runtime JSON.
- [ ] Use temp dirs only; do not write HearthRanger runtime folders.
- [ ] Mark expensive network-independent full matrix as normal pytest if runtime is acceptable. If it is slow, keep the three-deck subset and add a separate optional script for the full user-provided deck list.
- [ ] Add `scripts/run_deck_matrix.py` only if the repo already has scripts and this improves operator QA. Keep it read/write only under an explicit output directory.

**Verification:**

```powershell
python -m pytest tests/test_autonomous_guide_workflow_e2e.py -q
python -m pytest -q
```

**Expected outcome:** The workflow has a compact regression proof across aggro, big/recruit, and pirate/weapon archetypes.

**Commit message:** `Add autonomous guide workflow matrix tests`

---

## Task 11: Run A Sharp ShadowPriest Dry Package Proof

**Purpose:** Produce one current proof package for the recurring ShadowPriest case, without committing local runtime-private evidence.

**Input deck:**

```text
Deckname: ShadowPriest
Deckcode: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
HSid: 2737726722
HDT-DeckId: c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602
```

**Implementation steps:**

- [ ] Run `research-deck` into a local ignored output folder:

```powershell
hsconfig research-deck `
  --deck-name ShadowPriest `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --out tmp\proof\shadowpriest\research `
  --json
```

- [ ] Run `prepare` into a local ignored output folder:

```powershell
hsconfig prepare `
  --deck-name ShadowPriest `
  --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" `
  --guide-sources-json tmp\proof\shadowpriest\research\guide_sources.json `
  --out tmp\proof\shadowpriest\package `
  --json
```

- [ ] Inspect:
  - `tmp\proof\shadowpriest\package\operator_summary.json`
  - `tmp\proof\shadowpriest\package\GlobalValues.json`
  - `tmp\proof\shadowpriest\package\Mulligan.json`
  - per-card behavior files.
- [ ] Do not commit the proof output unless tests intentionally use a small sanitized fixture.
- [ ] If a sanitized fixture is useful, store only the minimal `operator_summary.json` and a tiny synthetic guide source fixture under `tests/fixtures/`.

**Verification:**

```powershell
python -m pytest -q
git status --short
```

**Expected outcome:** A fresh ShadowPriest package can be built with the new path, and the repo remains clean except intended code/docs/test changes.

**Commit message:** `Validate ShadowPriest guide package flow`

---

## Task 12: Final Review And GitHub Update

**Purpose:** Finish only after tests, docs, and git state are consistent.

**Implementation steps:**

- [ ] Run focused tests from each changed area:

```powershell
python -m pytest `
  tests/test_operator_summary.py `
  tests/test_guide_source_builder.py `
  tests/test_research_deck_cli.py `
  tests/test_mulligan_plan.py `
  tests/test_condition_format.py `
  tests/test_globalvalues_authority.py `
  tests/test_identity_graph.py `
  tests/test_autonomous_guide_workflow_e2e.py `
  -q
```

- [ ] Run full suite:

```powershell
python -m pytest -q
```

- [ ] Run active-doc scan:

```powershell
rg -n "default-only mulligan|post-game tuning owned by HSConfig|guide source as merely optional" README.md docs src tests C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

Expected: no matches except test strings that intentionally assert these phrases are absent.

- [ ] Check generated or temp files:

```powershell
git status --short
```

- [ ] Review diff:

```powershell
git diff --stat
git diff -- README.md docs src tests C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
```

- [ ] Commit logically. If tasks were committed individually, final commit may only contain docs or verification notes. If not, use:

```powershell
git add README.md docs src tests C:\Users\darbo\.codex\skills\hsconfig\SKILL.md
git commit -m "Add autonomous guide source workflow"
```

- [ ] Push:

```powershell
git push origin main
```

**Expected outcome:** `origin/main` contains a lean HSConfig workflow that can build stronger Step-1 CustomConfig packages from deck input plus normalized guide research.

---

## Final Acceptance Criteria

- `hsconfig research-deck` exists and writes normalized research artifacts.
- `hsconfig prepare` writes `operator_summary.json`.
- `operator_summary.json` separates `technical_status`, `semantic_status`, `next_action`, and `apply_policy`.
- Mulligan generation supports multiple conditional rules per card.
- Runtime condition grammar is guarded by an allowlist; unsupported conditions never reach runtime JSON.
- GlobalValues use a posture/key authority matrix instead of one generic aggressive adjustment.
- Deck identity preserves sideboards and writes identity graph/gap reports.
- Docs and the installed `hsconfig` skill describe the same workflow.
- Multi-deck E2E tests prove the workflow is deck-neutral.
- Full test suite passes.
- No raw runtime evidence or temp proof outputs are committed.
