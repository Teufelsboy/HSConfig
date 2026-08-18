# LLM-Optimized Start Configuration Design

**Date:** 2026-08-18

**Status:** User-approved design
**Scope:** HSConfig pre-run generation only

## 1. Purpose

HSConfig currently optimizes for exact identity, source provenance, structural
validity, and safe runtime installation. It deliberately refuses to infer
strategy from a deck's curve, roles, or synergies when an exact live-verified
guide claim is unavailable. That contract produces safe packages, but it can
also produce empty or strategically thin Mulligan and behavior surfaces.

The new capability must generate the best practical configuration HSConfig can
construct before the first game. It must use an LLM to build concrete VisionAI
rules, compare three alternative candidates, select one candidate through an
independent LLM critic, and then derive a complete normal HSConfig package from
the selected candidate.

The product term is **LLM-optimized start configuration**. It is not a claim of
mathematically proven optimality or measured win-rate improvement.

## 2. Goals

- Accept the normal deck name and exact deck code input.
- Resolve the exact deck fingerprint and CardID roster before strategy work.
- Use current guide evidence, card text, curve, card roles, deck synergies, and
  comparable archetype knowledge as LLM context.
- Produce three materially different complete configuration candidates.
- Let an independent LLM critic rank the candidates holistically without a
  fixed numeric scoring formula.
- Let the LLM directly choose supported VisionAI surfaces, conditions, and
  concrete values.
- Compile the selected candidate before package assembly so that every ledger,
  report, digest, receipt, and runtime file is derived from the same candidate.
- Preserve the existing guarded validation, apply, publication, and
  `runtime-match` boundaries.
- Avoid empty or silently default-only output being presented as an optimized
  success.
- Keep the normal skill interaction limited to deck name, deck code, runtime
  root, and whether live installation is requested.

## 3. Non-goals

- Replay parsing, post-game tuning, win-rate analysis, or candidate promotion
  after games.
- A guarantee that the selected configuration has the highest possible win
  rate.
- Allowing an LLM to write runtime files directly.
- Allowing post-assembly edits to `CustomConfig` JSON.
- Adding an OpenAI SDK or model client dependency to the HSConfig repository.
- Replacing exact deck and CardID identity validation.
- Generating unsupported legacy surfaces such as `Presume.json`,
  `Concede.json`, or aggregate `CardBehavior.json`.

## 4. Product Contract Change

The current pre-run contract states that missing strategic evidence cannot be
inferred from mana curve, card role, deck name, or generic gameplan text. The
optimized path intentionally changes that rule.

For the optimized path:

- exact source evidence remains first-class context;
- the LLM may infer missing strategy from the exact 30-card roster, card text,
  curve, synergies, and comparable archetypes;
- inferred rules are recorded as LLM-authored strategy, not falsely promoted
  to exact guide evidence;
- source disagreement is visible in the decision report but does not
  automatically block a technically valid candidate;
- load safety and runtime identity remain deterministic gates;
- strategic quality is the LLM strategist and critic's responsibility.

The existing conservative `hsconfig configure` behavior remains available for
backward compatibility.

## 5. Architecture

```text
Deck name + deck code + optional source URLs
                     |
                     v
        Exact deck and CardID resolution
                     |
                     v
             starter_context.json
                     |
                     v
       LLM strategist: three candidates
                     |
                     v
 candidate-1.json / candidate-2.json / candidate-3.json
                     |
                     v
           Independent LLM critic
                     |
                     v
       starter_config_decision.json
                     |
                     v
    Deterministic candidate contract validator
                     |
                     v
       Existing package compiler and renderer
                     |
                     v
 Validate -> publish revision -> apply -> runtime-match
```

The Codex skill owns LLM orchestration. The repository owns deterministic
context construction, candidate validation, package derivation, and runtime
installation. No model invocation occurs inside the repository.

## 6. Components

### 6.1 Starter Context Builder

The repository exposes a read-only starter-context command. It produces a
bounded canonical document containing:

- deck name, deck code digest, canonical deck fingerprint, and format;
- exact 30-card roster with CardID, count, cost, type, text, mechanics, and
  resolved linked runtime entities;
- mana curve and deterministic deck-shape facts;
- supported VisionAI surface registry, condition grammar, data types, and
  allowed value constraints;
- current GlobalValues baseline and required complete key set;
- normalized current guide and archetype evidence with provenance;
- known safety canaries, including Darkbishop Benedictus `SW_448` and the
  transformed hero-power owner `EX1_625t`;
- existing source-backed claims and explicit evidence gaps.

The context builder does not generate strategy and does not write runtime
files.

### 6.2 LLM Strategist

The installed HSConfig skill uses the starter context to create exactly three
materially different candidates:

1. proactive/tempo candidate;
2. balanced candidate;
3. resource-oriented candidate.

The archetype labels guide diversity; they do not force an unsuitable plan.
For a clearly aggressive deck, all three candidates may remain aggressive but
must differ in Mulligan breadth, resource preservation, or priority choices.

The strategist may directly choose:

- physical Mulligan hold and discard rows;
- every GlobalValues value;
- supported per-card VisionAI surfaces, conditions, and values;
- `Combo.json` only when the chosen order is expressible by the supported
  runtime grammar.

Every physical rule must carry a stable rule identifier and a concise
rationale. The rationale records the strategist's reasoning; it is not used as
technical apply authority.

### 6.3 Independent LLM Critic

The critic receives the starter context and all three immutable candidate
documents. It ranks them holistically. It is not constrained by a fixed score
or weighting table.

The decision must include:

- ordered candidate identifiers;
- selected candidate identifier;
- concise selection rationale;
- principal strengths;
- principal risks and uncertain assumptions;
- reasons each rejected candidate was inferior;
- confirmation that all three candidates were considered.

The critic cannot edit a candidate. A requested revision returns to the
strategist as a new immutable candidate revision. At most two targeted repair
rounds are allowed for schema or technical defects.

### 6.4 Candidate Contract Validator

The deterministic validator does not second-guess strategic quality. It checks
that the selected candidate is safe to compile:

- exact schema version and closed document shape;
- candidate and decision digests match the documents the critic reviewed;
- selected candidate belongs to the exact target deck fingerprint;
- every physical CardID belongs to the deck or is an explicitly supported
  linked runtime entity;
- every VisionAI surface and condition is registered and type-correct;
- concrete values satisfy registry-defined finite bounds and expression rules;
- GlobalValues contains the exact complete key set;
- Mulligan selectors resolve to physical deck cards and contain no accidental
  wildcard catch-all;
- duplicate and conflicting physical rows are rejected;
- Darkbishop and linked hero-power identity remain distinct;
- `Combo.json`, if present, has a complete ordered and expressible sequence;
- every deck card has a visible emitted or deliberately unconfigured
  disposition;
- optimized output is not wholly default-only.

A normal 30-card optimized candidate must contain at least one physical
Mulligan rule and at least one meaningful strategic rule outside the baseline
GlobalValues document. Failure is visible and blocks publication; the pipeline
must not silently fall back to an empty "optimized" package.

### 6.5 Package Compiler Integration

The selected candidate enters before normal runtime rendering. The package
compiler must derive all of the following from that exact candidate:

- `GlobalValues.json`;
- `Mulligan.json`;
- per-card `<CARDID>.json` files;
- optional `Combo.json`;
- runtime surface ledger;
- surface intent and disposition ledgers;
- source-to-runtime explainability;
- operator summary;
- output ownership manifest;
- package derivation receipt;
- validation and configuration-assurance reports.

No supported path may copy an old package and patch JSON afterward.

## 7. Data Contracts

### 7.1 `starter_context.json`

Required top-level fields:

- `schema_version`
- `deck_identity`
- `cards`
- `deck_shape`
- `supported_runtime_contract`
- `globalvalues_baseline`
- `source_evidence`
- `existing_claims`
- `known_safety_boundaries`
- `content_sha256`

The document is canonical JSON, UTF-8 without BOM, closed-schema, and
digest-bound.

### 7.2 Candidate document

Required top-level fields:

- `schema_version`
- `candidate_id`
- `candidate_revision`
- `starter_context_sha256`
- `deck_fingerprint`
- `strategy_summary`
- `mulligan`
- `globalvalues`
- `card_rules`
- `combo`
- `card_dispositions`
- `rule_rationales`
- `assumptions`
- `content_sha256`

Candidate documents contain complete concrete desired runtime state, not
patches against a previous package.

### 7.3 `starter_config_decision.json`

Required top-level fields:

- `schema_version`
- `starter_context_sha256`
- `reviewed_candidates` with candidate identifier and exact digest;
- `ranking`
- `selected_candidate_id`
- `selection_rationale`
- `strengths`
- `risks`
- `rejection_reasons`
- `critic_identity`
- `content_sha256`

The decision must bind exactly three distinct candidate digests.

## 8. Command and Skill Flow

The normal Codex skill interaction remains:

```text
Deck name + deck code -> optimized package -> optional live apply
```

Internally, the skill uses two repository phases:

```powershell
hsconfig starter-context `
  --deck-name "<DeckName>" `
  --deck-code "<DeckCode>" `
  --out "outputs/<DeckName>" `
  --online-source `
  --json

hsconfig configure `
  --deck-name "<DeckName>" `
  --deck-code "<DeckCode>" `
  --optimized-start `
  --starter-decision-json "<decision-path>" `
  --runtime-root "<HearthRangerRoot>" `
  --out "outputs/<DeckName>" `
  --apply `
  --json
```

The skill creates the three candidate and one decision documents between these
commands. Direct CLI users may supply the same documents. The repository never
silently invokes a model or reads an unbound ambient response.

`--optimized-start` without a decision document fails closed with
`starter_decision_required`. Supplying a decision document without
`--optimized-start` fails with `starter_decision_not_enabled`.

## 9. User-Facing Result

The final configure summary adds an `optimized_start_summary` containing:

- status: `selected`, `low_confidence`, or `failed`;
- selected candidate identifier;
- three reviewed candidate identifiers;
- selection rationale;
- Mulligan holds and discards;
- changed GlobalValues;
- emitted per-card strategic rules;
- optional combo summary;
- principal risks;
- next report to open.

`reports/operator_summary.json` remains the sole normal apply verdict. It gains
the selected candidate and decision digests as derivation inputs. The
configuration-assurance wording is `LLM_OPTIMIZED_START`, never
`GAMEPLAY_OPTIMAL`.

## 10. Error Handling

- Deck decoding or CardID resolution failure stops before LLM generation.
- Missing live source evidence does not force empty output; it is exposed as a
  source limitation in the starter context.
- Malformed LLM JSON may be repaired at most twice.
- Candidate digest, deck fingerprint, or closed-schema mismatch rejects only
  that candidate revision.
- The critic must review exactly three valid candidate revisions. If fewer than
  three survive, the strategist replaces invalid candidates before selection.
- A technically invalid selected candidate cannot be substituted silently.
- If the selected candidate fails package derivation or fake apply, nothing is
  published or written to runtime.
- A failed optimized run leaves the previous immutable `current.json` revision
  and live HearthRanger mapping untouched.
- Runtime writes remain atomic and are independently checked with
  `runtime-match`.

## 11. Testing Strategy

Implementation follows focused TDD rather than broad per-deck test expansion.

Required focused tests:

1. starter-context exact deck, CardID, source, and registry binding;
2. closed candidate and decision schemas;
3. exactly three distinct digest-bound candidates;
4. wrong deck, unknown CardID, unsupported surface, invalid condition,
   non-finite/out-of-range value, incomplete GlobalValues, wildcard Mulligan,
   and conflicting-row rejection;
5. Darkbishop `SW_448` versus `EX1_625t` linked-runtime identity;
6. direct candidate compilation regenerates ledgers, summaries, manifests, and
   derivation receipts from the candidate bytes;
7. no post-assembly JSON mutation path;
8. optimized-start failure preserves the previous revision and live mapping;
9. ShadowPriest end-to-end fixture produces a non-empty Mulligan, complete
   GlobalValues, meaningful targeted card rules, a critic decision over three
   candidates, a valid package, and a successful fake apply;
10. runtime-match succeeds after a guarded real-apply fixture.

Normal repository release and CI gates remain responsible for full regression
coverage. Generating one deck does not run the complete repository suite.

## 12. Security and Integrity

- LLM output is untrusted input.
- Candidate and decision files are bounded in size, UTF-8 strict, duplicate-key
  rejecting, canonicalized, and digest-bound.
- Source text embedded in the starter context is data, never an instruction to
  bypass the schema or apply gate.
- No secrets, runtime logs, replays, or private HearthRanger evidence enter the
  candidate context.
- The LLM cannot choose filesystem paths, output roots, repository identities,
  or runtime destinations.
- Existing candidate publication, package ownership, atomic apply, and runtime
  identity protections remain unchanged.

## 13. Compatibility and Migration

- Existing `hsconfig configure` remains conservative and source-contract
  driven.
- The installed HSConfig skill defaults to the optimized-start workflow for
  normal deck generation after this feature is released.
- Existing package formats remain readable; optimized packages add new reports
  and derivation inputs without changing the physical VisionAI JSON grammar.
- Existing manually modified practical packages are not promoted. They must be
  regenerated through the optimized pipeline to acquire consistent reports and
  receipts.
- The current ShadowPriest practical profile becomes the first migration case,
  not an authority fixture. Its deck identity and intended aggressive shape may
  be reused, but the new strategist must independently generate and select the
  final candidate.

## 14. Acceptance Criteria

The feature is accepted when:

- the skill needs only deck name, deck code, runtime root, and apply intent;
- it produces and critic-reviews exactly three materially distinct candidates;
- the critic freely selects one candidate and explains the selection;
- the selected LLM candidate contains concrete direct VisionAI rules and passes
  all deterministic technical gates;
- the final package is freshly derived from the selected candidate with no
  stale report or receipt mismatch;
- a normal optimized deck is never reported successful with empty Mulligan and
  wholly default-only strategy output;
- `hsconfig apply` is the only live write path;
- `runtime-match` reports `matched` after apply;
- the conservative non-optimized path remains backward compatible;
- the output is described as an LLM-optimized start configuration and makes no
  measured gameplay or win-rate claim.
