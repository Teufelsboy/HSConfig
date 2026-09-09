# HSConfig Start-Config Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one deck name and exact deck code into one better-informed, independently reviewed, technically validated start configuration without adding user-facing steps.

**Architecture:** Retain the existing deterministic compiler, source authority, publisher, and guarded writer. Add one captured card dataset, a bounded pre-freeze research continuation, and schema-3 context/decision contracts; dispatch old sealed runs through their original contracts. Enable the new normal route only after its consumers and bundled helper work together.

**Tech Stack:** Existing Python >=3.11, hearthstone deckstrings, strict canonical JSON, pytest, Ruff, Windows, and the embedded Codex skill. No new dependency or model client.

**Spec:** [Approved quality-upgrade design](../specs/2026-09-09-hsconfig-start-config-quality-design.md). Read it and this plan before implementation.

Status: implementation plan; no implementation or acceptance step below has run.
Planning baseline: `dfc5045de65187cc2f1c07bed0c4273d9a6397d6`.

## Global Constraints

- "The user gets no new setup, research command, candidate selection, or provider credentials."
- "Create one candidate and use the existing independent reviewer with at most two targeted revisions."
- "All 38 GlobalValues keys remain profiled."
- "Richer context grants no new runtime-owner or runtime-syntax permission."
- "An unresolved or conflicting required identity stops before candidate creation."
- "Only the canonical acquisition/receipt path can establish `live_verified` or exact strategic guide authority."
- "An empty shortlist is valid and continues with a visible limitation."
- "The page-acquisition deadline starts immediately before its first fetch."
- Research limits: at most two search calls, three pages, 30 seconds total controller acquisition, and 10 seconds per request; no reset on resume.
- Existing sealed live tuple: session/manifest/context/candidate/review = `1/1/2/2/2`, compiler `hsconfig-live-start-v1`.
- New live tuple: `2/2/3/3/3`, compiler `hsconfig-live-start-v2`; runtime grammar remains `visionai-runtime-v1`.
- "Keep human-facing deck names and output aliases free of SHA suffixes; retain internal digests and immutable revision identities for correctness and diagnostics."
- "Neither that status nor local tests proves gameplay improvement or final release readiness."
- Work in this HSConfig checkout, on the existing branch as requested. Do not move work to HSranger, a shadow checkout, or a new worktree.
- Preserve manual edits, strict JSON, exact CardIDs, row provenance, enabled-profile binding, preview, revision limits, and apply recovery.
- No runtime evidence in Git, extra release-catalog decks, release-gate bypass, GitHub push/release/settings changes, or unrelated cleanup.
- No replay parsing, post-game tuning, candidate tournaments, broad crawling, persistent cache framework, multiple-Combo expansion, or new GUI/settings.

## Execution discipline and file ownership

Run the repository freshness procedure before executing Task 1, not as part of writing this plan:

```powershell
git status --short
git fetch --all --prune --tags
git remote prune origin
git branch -vv
git for-each-ref --format='%(refname:short) %(upstream:short) %(upstream:track)' refs/heads
```

Compare each local branch with a matching origin ref. Fast-forward only when non-destructive and clean; do not rewrite this outgoing signed stack, push, or delete local branches. Recheck any overlapping new edits before proceeding.

Use the existing Python environment; no dependency reinstall unless an actual missing dependency is demonstrated. For focused tests:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest --version
```

Each task is one independently reviewable deliverable: write the named failing regression, run its narrow command, implement, run that command green, inspect the diff, and commit only owned files with `git -c core.autocrlf=false commit -S`. Append the exact signed commit to the existing external signing baseline after validating its unchanged prefix and approved signer; preserve the predecessor and original design/plan OIDs. Do not reset that baseline for this new plan. Stop a failed command before committing.

The coordinator alone writes shared controller/session/contract files during execution. Read-only agents may map or review; parallel workers must have disjoint ownership and must not revert each other's changes. Dependency order: Task 1, Task 2, Task 4, Task 3, Task 5, Task 6, Task 7, and Task 8. Task 4 uses the snapshot decoder from Task 2; do not split their acceptance as if those interfaces were unrelated. No new normal deck runs during partial cutover.

| Area | Owner task | Main files |
| --- | --- | --- |
| Closed version routing | 1 | `starter_contract.py`; consumers extended by their owning tasks |
| Single card snapshot and DBF resolution | 2 | new `card_snapshot.py`, `deckstring_decode.py` |
| Manifest-v2 and rich sealed context | 3 | `input_snapshot_manifest.py`, `starter_context.py`, new `starter_card_facts.py` |
| Bounded acquisition and observations | 4 | new `live_start_research.py`, existing source modules |
| Candidate intent, justifications, review facts | 5 | `starter_candidate.py`, `starter_review.py`, `starter_compiler.py` |
| Durable continuation and complete derivation | 6 | `live_start_session.py`, `live_start_controller.py`, package authority consumers |
| Helper/skill cutover and failure output | 7 | `resources/codex_skill_bundle.json`, bundle validator, controller summary |
| Installed acceptance and concise docs | 8 | README/operator docs; external private acceptance evidence |

All source paths in this table are under `src/hsconfig/`.

---

## Task 1: Define closed version dispatch without activating the new route

**Files:** Modify `src/hsconfig/starter_contract.py`; create `tests/test_live_start_contract_versions.py`.

**Interfaces:** Add `live_contract_for_versions(*, session: int, manifest: int, context: int, candidate: int, review: int, compiler: str) -> str`. It returns `legacy_live` or `quality_live`, rejects non-exact types and mixed tuples, and grants no apply authority. Keep existing constants at their current values; add `QUALITY_STARTER_SCHEMA_VERSION = 3` separately.

- [ ] Write this regression, plus parameterized boolean/unknown-version cases:

```python
import pytest
from hsconfig.starter_contract import live_contract_for_versions

def test_quality_tuple_is_explicit_and_mixed_tuple_fails():
    values = dict(session=2, manifest=2, context=3, candidate=3,
                  review=3, compiler="hsconfig-live-start-v2")
    assert live_contract_for_versions(**values) == "quality_live"
    with pytest.raises(ValueError, match="live_start_contract_combination_invalid"):
        live_contract_for_versions(**{**values, "review": 2})
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_live_start_contract_versions.py`. Expected red: missing dispatcher; later malformed tuples must fail for the named contract reason.
- [ ] Implement the exact dispatcher body below using the signature above. New readers use this registry; do not globally replace schema-2 constants or loosen old closed schemas.

```python
versions = (session, manifest, context, candidate, review)
if any(type(value) is not int for value in versions) or type(compiler) is not str:
    raise ValueError("live_start_contract_combination_invalid")
routes = {
    (1, 1, 2, 2, 2, "hsconfig-live-start-v1"): "legacy_live",
    (2, 2, 3, 3, 3, "hsconfig-live-start-v2"): "quality_live",
}
try:
    return routes[(*versions, compiler)]
except KeyError:
    raise ValueError("live_start_contract_combination_invalid") from None
```

- [ ] Run the focused file green and existing `tests/test_starter_contract.py`; verify legacy schema-1 contracts are untouched. Commit `feat: define versioned quality-start contract routing`.

## Task 2: Resolve deck identities from one captured card dataset

**Files:** Create `src/hsconfig/card_snapshot.py`, `tests/test_card_snapshot.py`; modify `src/hsconfig/deckstring_decode.py`, `src/hsconfig/hearthstonejson.py`; reuse `tests/test_deckstring_decode.py`.

**Interfaces:** New `build_card_snapshot(rows: list[dict], *, captured_at: str, upstream_version: str | None = None) -> FrozenJsonDocument` returns the closed fields `full_cards`, `collectible_cards`, `dbf_to_card_id`, `captured_at`, `upstream_version`, `dataset_sha256`. New `decode_deck_code_from_snapshot(deck_code: str, snapshot: FrozenJsonDocument) -> dict` returns the existing decoded payload shape. The old `decode_deck_code(deck_code)` remains unchanged for old contracts.

Add `fetch_card_snapshot(timeout: float = 10.0) -> FrozenJsonDocument` in `hearthstonejson.py`: fetch the full feed once, validate raw identities/types before the old coercive normalizer, and call `build_card_snapshot`. Its stored full rows use normalized `id`/`dbf_id` fields and an additional `source_fields` list recording original field presence, so missing source text is distinguishable from an explicitly empty text. Derive collectible rows from this exact normalized full list. `dataset_sha256` hashes that canonical full projection. Retain an explicit upstream version only if supplied; otherwise null, never an API-version, retrieval-date, or ETag guess. Existing fetch functions/normalization semantics remain unchanged for old callers.

- [ ] Write the following synthetic fixture test and cases for a missing hero, sideboard owner/member, conflicting DBF, and boolean identity/count. Synthetic identifiers are fixture-only.

```python
from hearthstone.deckstrings import FormatType, write_deckstring
from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.deckstring_decode import decode_deck_code_from_snapshot

def test_snapshot_decoder_does_not_consult_installed_cardxml(monkeypatch):
    def unexpected_local_database():
        raise AssertionError("local cardxml consulted")
    monkeypatch.setattr("hsconfig.deckstring_decode.cardxml.load_dbf",
                        unexpected_local_database)
    rows = [
        {"id": "TEST_HERO", "dbfId": 1001, "type": "HERO", "name": "Hero"},
        {"id": "TEST_CARD", "dbfId": 1002, "type": "MINION", "name": "Card",
         "cost": 1, "attack": 1, "health": 2, "collectible": True},
    ]
    snapshot = build_card_snapshot(rows, captured_at="2026-09-09T00:00:00Z")
    code = write_deckstring([(1002, 2)], [1001], FormatType.FT_WILD)
    decoded = decode_deck_code_from_snapshot(code, snapshot)
    assert decoded["hero"]["card_id"] == "TEST_HERO"
    assert [(row["card_id"], row["count"]) for row in decoded["cards"]] == [
        ("TEST_CARD", 2)
    ]
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_card_snapshot.py` red. This unit checks resolution, not playable deck-size legality; controller closure still validates complete decks.
- [ ] Build the index from validated raw source rows, keeping full/collectible views from the same input. Use this core for rows with `id` as nonempty text and `dbfId` as an exact positive integer. Rows without a DBF retain metadata but cannot resolve a required deck identity; never coerce booleans into IDs:

```python
index = {}
for row in rows:
    dbf_key = str(row["dbfId"])
    card_id = row["id"]
    if dbf_key in index and index[dbf_key] != card_id:
        raise ValueError("card_snapshot_identity_conflict")
    index[dbf_key] = card_id
collectible = [row for row in rows if row.get("collectible") is True]
```

Reject conflicting records for a CardID as well; exact duplicate rows may be deduplicated deterministically. Canonicalize with `FrozenJsonDocument`, hash the exact full dataset, and revalidate immutable carriers at use. Do not trust a caller-supplied digest or mapping.

- [ ] Extract the existing deck assembly into `_decode_parsed_deck(parsed: dict, *, resolve: Callable[[int, int], dict], code_length: int) -> dict`. The resolver accepts `(dbf_id, count)` and returns the current card-row shape. Legacy resolution still calls `_card_row`; the new resolver uses the snapshot and raises `card_snapshot_identity_missing` for required missing identities. Preserve `_parse_deckstring`, format handling, receipts, main counts, and HearthSim sideboard-triplet semantics; no similar-name fallback. Preserve canonical one-based `sideboard_index` values. A flat deckstring triplet does not encode a separate original board occurrence: do not invent one or admit duplicate logical-owner aliases. Preserve repeated memberships across valid owners and exact per-member multiplicities.
- [ ] Run the new file green and `tests/test_deckstring_decode.py`. Do not change old expected CardIDs to accommodate the new route. Commit `feat: resolve quality-start decks from one card snapshot`.

## Task 3: Seal richer context and retain old projection semantics

**Files:** Create `src/hsconfig/starter_card_facts.py`, `tests/test_quality_starter_context.py`, `tests/helpers/quality_start.py`; modify `src/hsconfig/input_snapshot_manifest.py`, `src/hsconfig/starter_context.py`, `src/hsconfig/starter_contract.py`. Reuse `tests/starter_fixtures.py` and `tests/test_input_snapshot_manifest.py` helpers without changing their schema-2 defaults.

**Interfaces:** Add `project_card_facts(deck: dict, full_cards: list[dict]) -> dict` and `build_quality_starter_context(inputs: FrozenCompilerInputs) -> StarterContext`. Add optional `quality_inputs: FrozenJsonDocument | None = None` to the frozen carrier and keyword-only `quality_inputs` to its freezer. `None` produces the original manifest-v1 bytes; a validated quality payload produces manifest-v2 with a seventh blob `quality_inputs`, stored as `inputs/quality.json`. No path or authority is accepted from the LLM.

The closed quality payload is `{card_snapshot_sha256, card_snapshot_captured_at, card_snapshot_upstream_version, research_request_sha256, research_result}`. Task 4 defines `research_result`; Task 6 binds the request and installs the file. Its card digest must equal the captured full-card projection; manifest-v2 also recomputes the collectible filter and requires exact equality. Preserve `source_fields` through frozen full/collectible views. This quality payload is not a source-claim document and cannot mint strategic authority.

Schema-3 context retains top-level main `cards` as `{card_id, count}` memberships and adds `card_metadata`, `sideboards`, `linked_entities`, and `research_evidence`. Main facts live in the single deduplicated metadata map, not a second full-card copy. Existing source evidence/claim fields retain their canonical authority semantics.

- [ ] Write a pure projection regression:

```python
from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.starter_card_facts import project_card_facts

def test_sideboard_identity_is_shared_but_membership_is_not_lost():
    deck = {
        "cards": [{"card_id": "TEST_OWNER", "count": 1},
                  {"card_id": "TEST_MEMBER", "count": 1}],
        "sideboards": [{"owner_card_id": "TEST_OWNER", "sideboard_index": 1, "cards": [
            {"card_id": "TEST_MEMBER", "count": 2}]}],
    }
    full = [
        {"id": "TEST_OWNER", "dbfId": 1, "type": "MINION", "name": "Owner",
         "cost": 3, "attack": 2, "health": 4},
        {"id": "TEST_MEMBER", "dbfId": 2, "type": "MINION", "name": "Member",
         "cost": 1, "attack": 1, "health": 2},
    ]
    snapshot = build_card_snapshot(full, captured_at="2026-09-09T00:00:00Z")
    facts = project_card_facts(deck, snapshot.to_value()["full_cards"])
    assert len(facts["card_metadata"]) == 2
    assert facts["card_metadata"]["TEST_MEMBER"]["health"] == 2
    assert facts["sideboards"] == [{"owner_card_id": "TEST_OWNER", "index": 1,
                                    "card_id": "TEST_MEMBER", "count": 2}]
    assert facts["cards"] == deck["cards"]
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_quality_starter_context.py` red.
- [ ] Project exact main memberships and sideboard edges using the existing `card_metadata`/`semantic_enrichment` owner and link logic. Deduplicate metadata by CardID, never memberships. For each relevant record include `dbf_id`, `name`, `text`, `type`, `cost`, `attack`, `health`, `durability`, `races`, `classes`, `spell_school`, `mechanics`, and `play_requirements`; add disjoint `missing_fields` and `inapplicable_fields` lists. Missing/inapplicable values are null, not zero. Preserve genuine numeric zeroes.

```python
sideboards = [
    {"owner_card_id": board["owner_card_id"], "index": board["sideboard_index"],
     "card_id": member["card_id"], "count": member["count"]}
    for board in deck.get("sideboards", [])
    for member in board["cards"]
]
```

Use the existing resolved relation catalog for direct choices/transforms/hero powers/rewards. Include exact linked facts and explicit unresolved/random relations; do not recursively expand generated pools. Classify applicability by card type and source fields, not guessed stats. Normalize CR/LF as the existing card-text fix does; keep other control-character rejection.

- [ ] Implement manifest-v2 closed field/blob/envelope validation and the schema-3 projector. Extend byte/record bounds for the named seventh blob without relaxing existing maxima. `build_single_candidate_starter_context` remains the old projector; readers select from manifest/compiler versions. Dispatch scalar/field validation by schema: URL-bearing research fields must not cause a global relaxation of schema-2 prose validation. Main disposition/shape consumers explicitly join memberships to `card_metadata`.
- [ ] Add sealed round-trip cases for linked facts, missing/inapplicable stats, stale quality digest, malformed counts, excess fields, and CRLF. Reuse captured synthetic compiler inputs to compare old context bytes before/after new projection; exercise old manifest envelope readback unchanged. Never copy an operator run into committed fixtures.
- [ ] Define the reusable fixture `quality_shadowpriest_context(tmp_path, monkeypatch) -> StarterContext` in `tests/helpers/quality_start.py`. Adapt `tests/test_starter_candidate.py::single_candidate_shadowpriest_context`: use `audited_request_with_frozen_input_projections(tmp_path, "ShadowPriest")`, temp-only profile/output roots, the Task-2 consistent full/collectible snapshot, the same captured preconfig updated to those projections, Task-4 empty sealed research with `discovery_outcome=unavailable`, manifest-v2/contract-v2, and `build_quality_starter_context`. Import this fixture explicitly into the new candidate/review test modules. Keep the existing schema-2 fixture unchanged.
- [ ] Run the new file green plus these existing focused regressions:

```powershell
python -m pytest -q -p no:cacheprovider tests/test_starter_context.py::test_schema_two_context_normalizes_source_card_line_breaks_before_sealing tests/test_starter_context.py::test_schema_two_context_never_reobserves_sources_cards_or_baseline tests/test_input_snapshot_manifest.py::test_snapshot_round_trip_binds_three_physical_input_envelopes
```

Commit `feat: add versioned rich card and sideboard context`.

## Task 4: Implement bounded research and sealed observations

**Files:** Create `src/hsconfig/live_start_research.py`, `tests/test_live_start_research.py`; modify `src/hsconfig/source_acquisition.py` and, only where necessary, `src/hsconfig/source_candidate_plan.py`. Reuse `source_claim_compiler.py`, `source_autopilot.py`, and canonical source builders; no second source-authority implementation.

**Interfaces:** All new request/result documents use `FrozenJsonDocument` plus existing canonical sealing/strict loaders, not mutable dictionaries as authority.

- `build_research_request(*, run_id: str, deck_identity: dict, captured_input_sha256: str, queries: tuple[str, ...]) -> FrozenJsonDocument` produces a sealed request with these fields plus `schema_version=1`, limits `2/3/30/10`, and `content_sha256`.
- `validate_research_draft(value: dict, *, request_sha256: str) -> tuple[tuple[str, ...], str]` validates the exact three draft fields from the spec, distinct URLs, and binding.
- `research_timeout(*, deadline_utc: float, now_utc: float) -> float` returns `max(0.0, min(10.0, deadline_utc - now_utc))`; zero means no fetch.
- `build_research_result(*, acquired: dict, discovery_outcome: str, attempts: list[dict], deadline_utc: float | None, card_metadata: dict) -> FrozenJsonDocument` produces the closed fields `schema_version`, `discovery_outcome`, `attempts`, `deadline_utc`, `observations`, `limitations`, and `content_sha256`.

Durable attempt rows are `{url, state, record_sha256, error}` with state `started|completed|failed|interrupted`. Task 6 checkpoints `started` before each fetch and never retries an interrupted URL automatically. Deadline is null only before the first fetch or when no fetch is attempted.

- [ ] Write these tests and parameterized draft cases: extra authority/text/path fields, four URLs, duplicate URLs, malformed URL, wrong request digest, empty result, and each allowed discovery outcome.

```python
from hsconfig.live_start_research import research_timeout, validate_research_draft

def test_empty_shortlist_is_a_valid_limited_continuation():
    digest = "sha256:" + "a" * 64
    draft = {"acquisition_request_sha256": digest, "urls": [],
             "discovery_outcome": "unavailable"}
    assert validate_research_draft(draft, request_sha256=digest) == ((), "unavailable")

def test_deadline_does_not_reset_between_pages():
    assert research_timeout(deadline_utc=130.0, now_utc=100.0) == 10.0
    assert research_timeout(deadline_utc=130.0, now_utc=126.0) == 4.0
    assert research_timeout(deadline_utc=130.0, now_utc=131.0) == 0.0
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_live_start_research.py` red.
- [ ] Implement closed draft validation, deterministic limits, query selection, and result sealing. Normalize/validate public URLs with the existing acquisition restrictions; reject userinfo, non-public destinations, and unsupported schemes. Do not weaken redirect behavior. Queries come from class/format/signature cards and the existing candidate-plan output, trimmed to two; registered URLs consume the same three-page budget.
- [ ] Extend the existing collector with an optional absolute-deadline argument for the quality route. Preserve old defaults. Pass the remaining time into resolution/connect/body-read operations, bound cumulative body size with existing caps, and stop when no time remains. If a transport stage cannot honor the remaining bound, fail that acquisition visibly rather than claiming a hard deadline was enforced.

The current body limit is 400,000 bytes. Detect excess instead of presenting a truncated body as verified full text; report `source_body_too_large`. Add an optional validated `card_snapshot` argument for the quality route and use `decode_deck_code_from_snapshot` when decoding guide deckstrings for exact matching. Old source callers retain the local decoder. Thus a newly resolved card cannot lose exact-guide matching solely because the installed cardxml DB is older.

```python
remaining = research_timeout(deadline_utc=deadline_utc, now_utc=now_utc)
if remaining == 0.0:
    raise TimeoutError("research_budget_exhausted")
```

`now_utc` is sampled immediately before each network stage, not once for the loop. The real collector must still use its normal `fetcher=None` production path: wrapping it with an injected fetcher currently downgrades provenance to `captured_record`. Do not relabel injected transport as `live_http`. Test injected transport as diagnostic evidence; use `tests/helpers/live_acquisition.py` and the existing `_fetch_with_validated_address` seam for synthetic production-route contract tests. Those tests are still not real live research evidence.

- [ ] Compile acquired records with `compile_source_search_records`, retaining the canonical evidence/provenance fields as `commands/source_workflow.py` already does. Feed them through the existing source-document/autopilot path and authority handoffs; do not reconstruct receipts from caller drafts. Build observations deterministically from acquired visible text and exact card-name/ID matches, bounded to 12 observations of at most 600 characters each, across at most three pages. No additional LLM or model client is needed.

Each observation has closed fields `observation_id`, `evidence_id`, `source_url`, `content_sha256`, `retrieved_at`, `source_updated_at`, `supporting_text`, `card_ids`, `applicability`, `limitations`, `conflicts`. Use `exact_list` only from verified exact-deck evidence, `archetype_only` only from established archetype matching, otherwise `card_only` for identifiable card facts. Unknown update dates are null; an observed publication year is not an invented full date. Keep canonical claim conflicts visible; absence of an extracted conflict is not proof that the source contains none. The reviewer judges remaining strategic conflicts.

- [ ] Test unavailable/empty/timeout/HTTP failure separately, plus authority preservation, relevant snippet retention, no off-deck guessed CardID, and no extra source-text instructions in the orchestration draft. Run the new file green and `tests/test_source_acquisition.py` once. Commit `feat: acquire bounded pre-freeze strategy evidence`.

## Task 5: Validate useful intent and give the reviewer concrete decision facts

**Files:** Modify `src/hsconfig/starter_candidate.py`, `src/hsconfig/starter_review.py`, `src/hsconfig/starter_contract.py`, `src/hsconfig/starter_compiler.py`; create `tests/test_quality_starter_candidate.py`, `tests/test_quality_starter_review.py`.

**Interfaces:** Preserve existing candidate validation calls. Extend `validate_starter_review(document, *, context, candidate, validation_receipt: FrozenJsonDocument | None = None) -> ValidatedStarterReview`: schema 3 requires the freshly revalidated matching receipt; schema 2 retains the prior call/validation semantics. Add `changed_globalvalue_keys(baseline: dict, desired: dict) -> tuple[str, ...]` and `build_candidate_review_facts(*, context: StarterContext, candidate: ValidatedStarterCandidate) -> FrozenJsonDocument`. Existing `_globalvalues_semantic_projection` supplies normalized key values.

The schema-3 candidate adds `globalvalues_justifications`. Its keys exactly equal the changed-key set; each value has `{decision, baseline_gap, basis, evidence_refs, assumption}`. `basis=evidence` requires known sealed claim/observation IDs and null assumption; `basis=inference` requires nonempty assumption declared in candidate assumptions. Reject unknown refs, unrelated extra keys, blank reasons, and pseudo-rule-ID workarounds.

- [ ] Write the following numeric-equivalence regression and a complete schema-3 Mulligan-only candidate regression using the existing candidate factory as the source shape, not as approval evidence:

```python
from copy import deepcopy
from hsconfig.starter_candidate import changed_globalvalue_keys

def test_changed_keys_ignore_numeric_spelling():
    baseline = {"FirstTurnValueWeight": {"values": [
        {"condition": "*", "value": "0.5"}]}}
    desired = deepcopy(baseline)
    desired["FirstTurnValueWeight"]["values"][0]["value"] = "0.50"
    assert changed_globalvalue_keys(baseline, desired) == ()
    desired["FirstTurnValueWeight"]["values"][0]["value"] = "0.75"
    assert changed_globalvalue_keys(baseline, desired) == ("FirstTurnValueWeight",)
```

For the Mulligan-only candidate use this concrete test with the Task-3 fixture. Clearing the only rule must still fail with the existing earlier `starter_candidate_mulligan_required`; do not weaken that check just to reach the material-intent gate.

```python
from copy import deepcopy
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_contract import QUALITY_STARTER_CANDIDATE_FIELDS
from hsconfig.starter_document import seal_starter_document
from tests.helpers.quality_start import quality_shadowpriest_context
from tests.test_starter_candidate import candidate_draft

def test_quality_candidate_accepts_only_justified_mulligan(quality_shadowpriest_context):
    context = quality_shadowpriest_context
    draft = candidate_draft(context, candidate_id="lead", role="lead_strategist",
                            schema_version=3)
    draft["globalvalues"] = deepcopy(context.document.to_value()["globalvalues_baseline"]["values"])
    draft["globalvalues_justifications"] = {}
    draft["card_rules"] = []
    draft["combo"] = None
    draft["rule_rationales"].pop("darkbishop-mind-spike")
    for row in draft["card_dispositions"]:
        row["rule_ids"] = ["keep-toy-518"] if row["card_id"] == "TOY_518" else []
        row["disposition"] = "configured" if row["rule_ids"] else "deliberately_unconfigured"
        row["reason"] = "Opening-hand rule." if row["rule_ids"] else "No additional override justified."
    document = seal_starter_document(draft, expected_fields=QUALITY_STARTER_CANDIDATE_FIELDS,
                                    schema_version=3)
    assert validate_starter_candidate(document, context=context).candidate_id == "lead"
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_quality_starter_candidate.py tests/test_quality_starter_review.py` red.
- [ ] Add changed-key calculation and exact map validation. Compare normalized conditions/values; for schema 3, sort condition rows before comparison so order alone is not a semantic change. Do not alter historical schema-2 digest semantics. Implement the intent branch after the existing selector, owner, disposition, rationale, and assumption validators:

```python
has_intent = globalvalues_changed or bool(card_behavior_rows) or combo_decision is not None
if schema_version == QUALITY_STARTER_SCHEMA_VERSION:
    has_intent = has_intent or bool(mulligan_rows)
if not has_intent:
    raise ValueError("starter_candidate_material_runtime_intent_required")
```

The candidate dataclass and lowering retain the same authoritative rule objects. Do not insert a fake GlobalValues drift or relax physical-main ownership. Preserve old Mulligan-only rejection tests under old schema versions.

- [ ] Derive review facts only from freshly validated context/candidate objects: canonical changed-key before/after values, configured/`deliberately_unconfigured` main cards, rules by runtime owner/surface, evidence references, declared assumptions, and existing duplicate/conflict findings. Seal with context/candidate digests. Task 6 emits candidate-validation receipt schema 2 with an embedded `review_facts` document. Add `candidate_validation_receipt_sha256` to schema-3 review fields. The validator recomputes facts and verifies the receipt rather than trusting its embedded values; schema-2 starter reviews retain receipt-schema-1 behavior. Wrong receipt, candidate, revision, or context must reject approval.

Define `QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS` in `starter_contract.py`: the existing candidate-validation receipt field set plus `review_facts`, with receipt `schema_version=2`. Task-5 pure tests seal this closed receipt using `seal_starter_document`; Task 6 makes the session emitter use that same field set. This avoids a circular task dependency or a second receipt format.

Use this changed-key core within the declared helper, after normalizing condition-row order for the quality route:

```python
before = _globalvalues_semantic_projection(baseline)
after = _globalvalues_semantic_projection(desired)
if before.keys() != after.keys():
    raise ValueError("starter_candidate_globalvalues_keys_invalid")
return tuple(sorted(key for key in before if before[key] != after[key]))
```

- [ ] Add focused tests for missing/excess justifications, unknown refs, schema-2 immutability, illegal sideboard-as-main owner, duplicate/conflicting Mulligan, and stale review-facts receipt. Run the new files green and existing `test_schema_two_candidate_retains_numeric_and_owner_fail_closed_boundaries`, `test_candidate_rejects_wholly_baseline_default_only_runtime_intent`, and `test_approved_review_binds_context_candidate_revision_and_digest` by their exact pytest node IDs in the existing candidate/review files. Commit `feat: validate surface-neutral intent and review decision facts`.

## Task 6: Integrate durable discovery, resume, and package derivation

**Files:** Modify `src/hsconfig/live_start_session.py`, `src/hsconfig/live_start_controller.py`, `src/hsconfig/input_snapshot_manifest.py`, `src/hsconfig/package_request.py`, `src/hsconfig/optimized_start_authority.py`, `src/hsconfig/strict_package_validation.py`; create `tests/test_quality_live_start_controller.py`. Update `starter_compiler.py` only for version dispatch required by the complete package path.

**Interfaces:** Add `prepare_quality_live_start(request: LiveStartRequest) -> LiveStartDiscovery | LiveStartResult`, `complete_live_start_research(*, session_root: Path, draft_path: Path) -> LiveStartPreparation | LiveStartResult`, and `LiveStartDiscovery` with `run_root: Path`, `acquisition_request_path: Path`, `acquisition_request_sha256: str`. Normal `prepare_live_start` stays on the old route until Task 7. Resume dispatches from the actual closed session contract, not the current default.

Add session-v2 `DISCOVERY_REQUIRED` and a typed research binding. Before final freeze, the manifest digest is null only in this state, there are no candidate/publication/apply bindings, and immutable seed files contain deck, cards, baseline, bound date, and profile/output identities. Seed files are controller-owned entries in the same run directory; no second run or external arbitrary input path is accepted. Use separate v1/v2 session field/phase/artifact matrices; do not make v1's mandatory manifest nullable. Select the version route from persisted validated session/manifest authority before reading a caller draft.

Use `inputs/deck.json` and `inputs/cards.json` as the immutable early files, reusing their exact bytes at final freeze. Add `inputs/quality_seed.json` for metadata/bindings only, `research/request.json` for the sealed request, and `research/progress.json` for the bounded CAS-updated shortlist/attempt/results journal. Completed research becomes `inputs/quality.json`; the normal source envelope and manifest are then installed. Register these exact paths only in v2's artifact inventory. Do not duplicate the full card dataset into seed/progress files or invent another run store.

- [ ] Build a schema-v2 synthetic session fixture from `_frozen_live_start_inputs`/audited input projections, then exercise real capture/closure code while replacing only external data acquisition. Existing `_prepared_run` patches all of `_capture_live_start_inputs` and therefore does not test this new intake. Add this state sequence assertion after preparation:

```python
assert discovery.acquisition_request_sha256
assert session_value["phase"] == "DISCOVERY_REQUIRED"
assert session_value["input_snapshot_manifest_sha256"] is None
assert session_value["apply_invocation_sha256"] is None
assert session_value["publication_binding"] is None
```

Here `discovery` is the result of `prepare_quality_live_start`; `session_value` is its session's validated serialized value. Add a no-profile case whose acquisition callbacks raise if reached.

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_quality_live_start_controller.py` red.
- [ ] Capture full cards once, use Task 2 to resolve DBFs, derive the collectible view, validate closure, and seal the seed. Preserve existing profile leases, root identities, and no-follow operations. Create session-v2 with a digest-bound acquisition request. The durable transition uses the existing pending-transition/install/readback primitives, not direct `Path.write_text` or a second session store.
- [ ] Implement continuation under the existing session/profile leases: validate request/draft, checkpoint the first deadline and each started URL before network I/O, call Task 4, persist each result, then atomically install the final manifest-v2/context-v3 and enter `INPUT_FROZEN`. Treat a resumed started-without-result URL as interrupted and spent. Do not reset attempts, re-fetch seed data, overwrite old input bindings, or start another lead on resume.

```python
if current.phase == LiveStartPhase.DISCOVERY_REQUIRED:
    return _resume_quality_discovery(current=current, session_root=session_root)
```

Add `_resume_quality_discovery(*, current: LiveStartSession, session_root: Path) -> LiveStartDiscovery | LiveStartPreparation | LiveStartResult` in the controller. Before a draft is accepted it returns the same request; afterward it resumes only unattempted admitted URLs, or finalizes the captured partial result. Reserve the request's at most two search slots durably before first returning it. The skill may dispatch each query once and persist its partial shortlist; resumed requests do not grant new slots. If dispatch completion cannot be established after interruption, retain the spent reservation and continue from saved URLs or empty limited evidence. Report reserved/unknown attempts honestly, not as verified completed searches. No candidate is accessible before `INPUT_FROZEN`.

Partial shortlists are untrusted orchestrator-owned draft files, handled like existing candidate drafts, outside the sealed run inventory. Only the controller updates `research/progress.json`; the skill never edits its CAS journal or sealed request. A supplied draft path grants no write authority to that path or its parent.

- [ ] Complete version-aware document loading, candidate/review validation receipts, lowering, `FrozenApprovedLiveConfigureRequest`, strict derivation, and optimized approval. Remove hard-coded schema-2 assumptions only by dispatching exact validated tuples; never rebuild a legacy context with new functions. Add `quality_inputs` to the v2 file-size inventory, session bindings, package manifest consistency checks, and cleanup ownership inventory. The v1 input inventory and v1 recovery semantics stay byte-compatible.
- [ ] Test these deterministic fault boundaries: after seed install, after request install, after started-attempt checkpoint, after fetched record persistence, after final input installation, and during transition to `INPUT_FROZEN`. For each, resume keeps the same run/input digests and does not increase budgets. Mixed versions, replaced seed/quality files, changed profile binding, and premature finalization fail without runtime mutation. Legacy synthetic approved runs must still pass preview finalize and receipt/derivation readback.
- [ ] Run the new integration file green. Run the existing controller nodes `test_candidate_and_review_share_exact_two_revision_budget`, `test_finalize_requires_approved_review_before_loading_candidate_or_compiling`, and `test_preview_intent_resume_does_not_recompile_or_republish`. Include a quality-route strict package derivation test; do not stop at JSON-reader tests. Commit `feat: integrate resumable quality-start preparation and derivation`.

## Task 7: Cut over the bundled helper and make outcomes actionable

**Files:** Modify `src/hsconfig/resources/codex_skill_bundle.json`, `src/hsconfig/external_skill_bundle.py` only if its closed workflow checks require it, `src/hsconfig/live_start_controller.py`, `tests/test_optimized_skill_workflow.py`; create `tests/test_quality_start_summary.py`. Preserve the exact nine-file bundle inventory.

**Interfaces:** Normal `prepare_live_start(request)` now delegates to the fully tested quality preparation. The internal helper gains only `complete-research --session-root --draft-path`. It serializes `LiveStartDiscovery` as `DISCOVERY_REQUIRED` with request path/digest; that is a pending state, not success or runtime authority. Keep the other phase argument boundaries and `validate_package.py` delegation to `build_config.py`.

- [ ] Extend the existing helper fixtures and add this forwarding regression within `tests/test_optimized_skill_workflow.py`:

```python
def test_complete_research_helper_forwards_only_bound_input(tmp_path, monkeypatch):
    calls = []
    def completed(*, session_root, draft_path):
        calls.append((session_root, draft_path))
        return package_request.FrozenJsonDocument.from_value({"status": "INPUT_FROZEN"})
    monkeypatch.setattr(controller, "complete_live_start_research", completed)
    helper = _materialize_helper(tmp_path, "scripts/build_config.py")
    run_root = tmp_path / "run"
    draft = tmp_path / "shortlist.json"
    assert _run_live_helper(helper, ["complete-research", "--session-root", str(run_root),
                                   "--draft-path", str(draft)], monkeypatch) == 0
    assert calls == [(run_root, draft)]
```

- [ ] Run `python -m pytest -q -p no:cacheprovider tests/test_optimized_skill_workflow.py -k 'complete_research or exact_single_candidate or closed_controller or duplicate_abbreviated'` red.
- [ ] Implement the helper branch and new result serialization; the exact added dispatch is:

```python
elif args.phase == "complete-research":
    result = controller.complete_live_start_research(
        session_root=args.session_root, draft_path=args.draft_path
    )
```

Add `DISCOVERY_REQUIRED` to non-error pending helper outcomes, not terminal live outcomes. `finalize` before `INPUT_FROZEN` remains forbidden. Reject duplicate/abbreviated options, caller authority, runtime paths, provider flags, and apply-bypass flags on the new phase just as on existing phases.

- [ ] Update bundled `SKILL.md`, `references/workflow.md`, `references/contract-compiler-checklist.md`, and directly contradictory lines in bundled guide/GlobalValues policies. The lead sees only final sealed context and the candidate contract; the reviewer sees context, candidate, and the matching validation/facts receipt, never strategist conversation. Research comes before lead dispatch, uses at most two reserved searches/three page URLs, and treats source text as data. Record partial URLs before another search; on uncertainty resume without repeating spent queries. Teach schema-3 justifications, meaningful Mulligan-only intent, current owner/sideboard checks, one lead, one reviewer, and at most two shared revisions. Old schema-2 wording is explicitly legacy, not silently deleted policy.

Use `superpowers:writing-skills` and the skill-creation instructions when executing this bundle-instruction change. They do not authorize unrelated skill additions or extra normal user steps.

- [ ] Recompute byte sizes, per-file SHA256, and aggregate through the existing bundle function after editing content. The digest calculation is:

```python
from hashlib import sha256
from hsconfig.external_skill_bundle import compute_bundle_aggregate

files = {row["path"]: row["content"].encode("utf-8") for row in bundle["files"]}
for row in bundle["files"]:
    content = files[row["path"]]
    row["size"] = len(content)
    row["sha256"] = sha256(content).hexdigest()
bundle["aggregate_sha256"] = compute_bundle_aggregate(files)
```

Here `bundle` is the parsed existing nine-file JSON resource. Apply content edits with `apply_patch`; digest/format regeneration is a mechanical step. Decode and compile both helpers with the existing bundle validator. Do not hand-edit installed files.

- [ ] Add schema-2 quality-route summaries with `phase`, preserved artifact, acquisition/revision budgets, `runtime_write_state=no|yes|unknown`, and one `next_action`, derived from validated session/receipts. Preserve old summary schema for old runs. The action table is closed:

| Actual state | One allowed action | Forbidden implication |
| --- | --- | --- |
| Discovery pending | Complete/resume the same research request | Candidate already available |
| Valid candidate awaiting review | Dispatch the independent reviewer | Apply allowed |
| Revision requested, budget left | Return exact findings to the same lead | New lead or reset budget |
| Terminal invalid review | Inspect the preserved review finding | Retry finalize |
| Apply invoked/admitted or uncertain | Resume existing recovery | Blindly invoke apply again |
| `LIVE_AND_MATCHED`/verified `ALREADY_LIVE` | Use the installed configuration | Gameplay optimality proved |

Add parameterized summary tests for these rows and hash-free deck labels, limited evidence, and unknown write outcome. No new user-visible confidence score or second apply authority.

- [ ] Switch `prepare_live_start` to the new route together with the ready helper. Run the helper selection above green, `tests/test_quality_start_summary.py`, and existing bundle tests `test_embedded_bundle_is_exact_closed_nine_file_contract` and `test_bundle_decoder_compiles_both_python_helpers`. Run one new unmocked-controller helper-to-preview integration through synthetic input transport; it must end at `PREVIEW_READY`, contain actual schema-3 context/candidate/review, and write no runtime files. Synthetic transport/candidate/reviewer inputs are not a real live acceptance claim. Commit `feat: enable the quality-start skill workflow and clear outcomes`.

## Task 8: Install once, accept one real run, and finish concise documentation

**Files:** Modify `README.md`, `docs/operator/README.md`, `docs/operator/guide-research-policy.md`, and `docs/architecture/overview.md` only where the new normal path needs accurate routing. Installed bundle and private run evidence are external artifacts, not Git content. No changes to the fixed twelve-deck catalog.

**Interfaces:** Use existing `external_skill_tree_identity(destination: Path) -> dict`, `install_external_skill(destination: Path, *, expected_predecessor_aggregate_sha256: str | None) -> dict`, and `load_embedded_skill_bundle() -> dict[str, bytes]`. Use the installed helper and the existing enabled profile for the real run; no direct compiler/writer shortcut.

- [ ] Confirm Task 1-7 focused commands actually passed at their committed inputs; do not rerun them solely because this is the last task. Run one affected-file Ruff check with `--no-cache`, one `git diff --check`, and inspect the final scoped diff. If an integration gap remains, run the named missing check, not the whole historical suite. Mandatory release checks remain mandatory only for later release acceptance; do not claim them completed here.
- [ ] Resolve the existing installed `hsconfig` destination from the active configuration and inventory it read-only. Preserve its exact predecessor in the established external rollback area, verify that backup, then call the checked installer with its freshly read aggregate. This Python core uses `destination` resolved and verified immediately before execution:

```python
from hsconfig.external_skill_bundle import (
    external_skill_tree_identity, install_external_skill, load_embedded_skill_bundle,
)

before = external_skill_tree_identity(destination)
install_external_skill(destination,
    expected_predecessor_aggregate_sha256=before["aggregate_sha256"])
for relative, expected_bytes in load_embedded_skill_bundle().items():
    assert (destination / relative).read_bytes() == expected_bytes
```

Verify the exact nine-file inventory as well as bytes and helper imports from this checkout. Do not change/re-enable the operator profile, delete old failed sessions, or remove retained rollback evidence. Skill installation is not live-write authorization.
- [ ] For one authorized normal deck invocation, check current profile/root bindings and preview intent, then run the installed helper. If implementation authorization does not include a deck run, report local acceptance complete and leave this live step explicitly open until a normal deck invocation; this plan alone does not grant runtime authority.
- [ ] Dispatch real Codex search, the real lead, and a separate reviewer through the installed workflow. Validate the selected candidate and matching review receipts, finalize once through guarded apply, and read the exact final runtime-match result. If a real failure occurs, preserve it and use its permitted same-run continuation/recovery; do not keep starting canaries or changing transport provenance to force success.
- [ ] Record a compact acceptance summary outside Git: run ID, exact code/installed-bundle revision, dataset/context/candidate/review bindings, source coverage or fallback reason, main/sideboard coverage, revision count, final installation status, and whether runtime files were written. Do not copy raw pages/logs, private profile paths, or generated evidence into the repository. Only a real matching result satisfies live installation acceptance; it still does not prove gameplay optimality.
- [ ] Update the short public docs to show the actual one-prompt route and one limited-evidence example. Use this honest example structure, replacing nothing with unverified live claims:

```text
Deckname und Deckcode an den HSConfig-Skill geben.
Der Skill recherchiert begrenzt, erstellt einen Kandidaten und lässt ihn unabhängig prüfen.
Bei gültigem aktiviertem Profil: validieren, live anwenden und Dateien abgleichen.
Ohne ausreichende Guide-Evidenz bleiben Annahmen und eingeschränkte Sicherheit sichtbar.
Ein erfolgreicher Datei-Abgleich beweist keine optimale Spielleistung.
```

Keep technical hashes in details, keep names readable, link the architecture/spec, and mark only directly superseded normal-route instructions as legacy. Do not launch a general documentation rewrite or modify GitHub settings, tags, releases, or remote branches.
- [ ] Verify local Markdown links and the final diff, then commit `docs: explain the verified quality-start operator workflow`. Hand off exactly what is proven: local tests, installed parity, and live match separately. If live acceptance is still open, say so; do not label the overall outcome fully live-tested.

## Plan self-review and acceptance map

The following mapping is a planning check, not evidence that implementation passed:

| Approved requirement | Implementing task(s) | Proof boundary |
| --- | --- | --- |
| One prompt, one candidate, independent review, shared two revisions | 5-7 | Helper sequence plus candidate/review receipt binding |
| Actual bounded research and honest fallback | 4, 6, 7 | Transport provenance, intent-first budget, final sealed excerpts |
| Consistent identity/data snapshot | 2, 3, 6 | Decoder avoids local DB; manifest proves collectible derivation |
| Rich facts, sideboards, linked relationships | 3, 5 | Round-trip facts without granting physical-main ownership |
| Mulligan-only and justified changed GlobalValues | 5 | Schema-3 regressions; legacy policy tests retained |
| Old sealed sessions and full version compatibility | 1, 3, 5, 6 | Old readback, lowering, receipt/derivation, preview continuation |
| Clear status/errors, unchanged apply recovery | 6, 7 | State-derived action/write-status tests; existing guarded writer |
| Installed skill parity and one actual live run | 8 | Exact installation readback and real apply/match, separately reported |
| Readable names and GitHub-facing quickstart | 7, 8 | Label tests and scoped documentation/link check |
| Lean checks and no scope expansion | All | Focused task evidence; no repeated broad suite or unrelated changes |

Before execution, no checkbox is complete. After each task, record its actual command/result and signed commit alongside that task, keeping private runtime details external. Final completion requires every applicable acceptance item above, not simply reaching the last task number.
