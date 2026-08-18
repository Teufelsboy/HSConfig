# LLM-Optimized Start Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the installed HSConfig skill generate a meaningful, deterministic, pre-game HearthRanger start configuration by having an LLM create exactly three concrete VisionAI candidates, having an independent LLM critic select one, and compiling the selected immutable candidate through the existing guarded HSConfig package/apply pipeline.

**Architecture:** The repository remains model-agnostic. It creates a bounded starter context, validates fixed-name candidate and critic documents as untrusted input, freezes the selected candidate in `ResolvedPackageRequest`, and lowers it before the existing package compiler renders runtime files. The Codex skill owns strategist and critic orchestration. Existing publication, derivation, apply, and `runtime-match` authorities remain the only write path.

**Tech Stack:** Python 3.11/3.12, frozen dataclasses, canonical JSON and SHA-256, `argparse`, existing HSConfig compiler/domain models, pytest, Ruff, embedded nine-file Codex skill bundle, Windows HearthRanger runtime integration.

**Spec:** `docs/superpowers/specs/2026-08-18-llm-optimized-start-config-design.md`

## Global Constraints

- Work directly in `C:\Users\darbo\Documents\HSConfig` on `main`; do not create a branch, worktree, PR, or shadow checkout.
- Before the first implementation edit, run `git fetch --all --prune --tags`, `git remote prune origin`, confirm the worktree/index state, and reconcile any upstream movement without discarding local commits.
- Exactly one writer owns each task's files. Independent spec and quality reviews are read-only.
- Keep HSConfig pre-run only. Do not add replay parsing, HDT log parsing, win-rate analysis, post-game tuning, or candidate promotion.
- Do not add an OpenAI SDK, model client, network model call, prompt endpoint, or secret to the repository.
- LLM documents are untrusted input. They never choose filesystem paths, output roots, runtime roots, package identities, or apply destinations.
- `hsconfig apply` and `hsconfig configure --apply` remain the only live-write paths. The LLM never writes `CustomConfig` files directly.
- The selected candidate must be lowered before runtime compilation. No task may patch rendered JSON or copy an old practical package.
- The optimized path uses the authority label `LLM_OPTIMIZED_START`; it never claims `GAMEPLAY_OPTIMAL`, measured gameplay quality, or win-rate improvement.
- The conservative non-optimized `configure` path must remain byte-compatible wherever starter mode is absent. Optimized-only reports and receipt changes are conditional.
- Each implementation task uses the listed focused RED/GREEN commands. Do not run the local full repository suite during task loops. The hosted exact-OID CI remains the final full-regression authority.
- Generated candidate bundles and deck packages stay under ignored output/temp locations. No runtime logs, replays, private evidence, or secrets enter Git.

## Resolved Contract Decisions

1. `starter-context` requires `--runtime-root` so the context binds the actual complete GlobalValues baseline. A bundled fallback may be used only when the existing baseline loader explicitly records `bundled_fallback` and its digest; it is never described as live runtime state.
2. The user supplies only `starter_config_decision.json`. The loader reads exactly four fixed sibling filenames from the same directory:

   ```text
   starter_context.json
   candidate-1.json
   candidate-2.json
   candidate-3.json
   starter_config_decision.json
   ```

   Candidate JSON may contain IDs and digests but never paths.
3. Optimized packages conditionally own exactly five immutable evidence reports:

   ```text
   reports/optimized_start/starter_context.json
   reports/optimized_start/candidate-1.json
   reports/optimized_start/candidate-2.json
   reports/optimized_start/candidate-3.json
   reports/optimized_start/starter_config_decision.json
   ```

4. A candidate revision is an integer from 1 through 3: initial candidate plus at most two targeted repair rounds.
5. The three strategy roles are `proactive_tempo`, `balanced`, and `resource_oriented`. Their runtime-intent subtrees must be materially distinct; different prose alone is insufficient.
6. Numeric expressions use the existing safe arithmetic grammar. Their evaluated finite result must be within `[-1000, 1000]` for GlobalValues and `[-10000, 10000]` for per-card/Combo numeric values. Metadata GlobalValues keys remain exact baseline copies.
7. Candidate compilation carries no fabricated guide claim IDs. Optimized rules use an explicit starter authority record and keep `source_claim_ids` empty unless a separate real source claim already exists in the resolved context.
8. A successful optimized candidate has at least one physical Mulligan rule and at least one material runtime-intent change: a changed GlobalValue, an emitted CardID behavior row, or an expressible Combo row.
9. Candidate nested shapes are closed:

   - `strategy_summary`: `{role, summary}`;
   - each Mulligan row: `{rule_id, selector_kind, selector, action, condition}`;
   - `globalvalues`: the exact complete 38-key desired-state object;
   - each card rule: `{rule_id, source_card_id, runtime_card_id, link_kind, behavior_block, condition, value}`;
   - `combo`: `null` or `{rule_id, cards, timing, values, condition}`;
   - each card disposition: `{card_id, disposition, rule_ids, reason}`, where disposition is `configured` or `deliberately_unconfigured`;
   - `rule_rationales`: an exact rule-ID-to-nonempty-string mapping;
   - `assumptions`: a bounded list of nonempty strings.

   `card_dispositions` contains exactly one row for every unique main-deck CardID, never one row per physical copy. For the audited ShadowPriest deck this is exactly 16 disposition rows; their corresponding positive deck counts sum to 30 physical cards.

10. Critic nested shapes are closed:

   - `reviewed_candidates`: three `{candidate_id, candidate_revision, content_sha256}` rows;
   - `ranking`: exactly three candidate IDs;
   - `strengths` and `risks`: bounded nonempty string lists;
   - `rejection_reasons`: exact rejected-ID-to-reason mapping;
   - `critic_identity`: `{kind: "independent_codex_agent", review_id, confidence}`, where confidence is `high` or `low` and is a qualitative critic judgment, not a numeric score.

11. The deterministic pre-critic gate is the read-only command `hsconfig starter-validate-candidate --starter-context-json PATH --candidate-json PATH --json`. All three candidates must pass this command before the critic receives them. A failing candidate may return only to its own strategist, for at most two targeted repair rounds.
12. `configuration_mode` is part of the frozen invocation authority. It defaults to `CONSERVATIVE`; `LLM_OPTIMIZED_START` is valid only with one frozen `ValidatedStarterSelection`. To preserve existing conservative package bytes and readability, conservative manifests keep the legacy shape with no `configuration_mode` field; optimized manifests alone write top-level `"configuration_mode":"LLM_OPTIMIZED_START"`. All downstream dispatch uses one central `configuration_mode_from_manifest` helper: a missing field means legacy `CONSERVATIVE`, either exact known string is accepted, and a present non-string or unknown value fails closed.
13. The real live completion removes only the explicitly requested inactive legacy directories `aggro` and `warrior_pirate`, and only after the new ShadowPriest revision is applied and `runtime-match` is green. The cleanup is quarantined and recoverable; it preserves `default`, every directory referenced by `deck_config.ini`, the active versioned ShadowPriest directory, `deck_config.ini`, `hsconfig_write_history.jsonl`, `.hsconfig`, and every unrelated runtime entry.

---

## Task 1: Add the Complete Optimized Runtime Constraint Registry

**Files:**

- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `src/hsconfig/globalvalues_decisions.py`
- Modify: `src/hsconfig/package_domain.py`
- Modify: `tests/test_contract_registry.py`
- Modify: `tests/test_globalvalues_decisions.py`

- [ ] **Step 1: Write the focused RED contract tests**

Add assertions that:

- optimized GlobalValues constraints contain exactly `GLOBALVALUES_BASELINE_DECISION_KEYS` in canonical order;
- `GameCardId` and `ConfigComment` are `copy_baseline` constraints;
- every remaining key is a safe numeric expression with finite string bounds `-1000` and `1000`;
- card behavior and Combo values use finite bounds `-10000` and `10000`;
- the new decision kind serializes exactly as `llm_optimized_start` and does not require a source claim ID.

Name the two focused additions `test_starter_globalvalue_constraints_cover_exact_baseline_keys` and `test_llm_optimized_globalvalue_decision_kind_is_source_distinct`.

Use this public contract:

```python
@dataclass(frozen=True, slots=True)
class RuntimeValueConstraint:
    value_type_id: str
    minimum: Decimal | None
    maximum: Decimal | None
    copy_baseline_only: bool


def starter_globalvalue_constraint(key: str) -> RuntimeValueConstraint:
    return STARTER_GLOBALVALUE_CONSTRAINTS[key]


STARTER_CARD_VALUE_CONSTRAINT = RuntimeValueConstraint(
    value_type_id="finite_decimal",
    minimum=Decimal("-10000"),
    maximum=Decimal("10000"),
    copy_baseline_only=False,
)
```

- [ ] **Step 2: Run the RED tests**

Run:

```powershell
python -B -m pytest tests/test_contract_registry.py::test_starter_globalvalue_constraints_cover_exact_baseline_keys tests/test_globalvalues_decisions.py::test_llm_optimized_globalvalue_decision_kind_is_source_distinct -q -p no:cacheprovider
```

Expected: FAIL because the complete starter constraint registry and `llm_optimized_start` decision kind do not exist.

- [ ] **Step 3: Implement the registry without changing conservative semantics**

In `visionai_registry.py`, build `STARTER_GLOBALVALUE_CONSTRAINTS` from the exact baseline key tuple, not the existing partial overlay registry. Project `Decimal` bounds to strings when serializing starter context.

In `package_domain.py`, add:

```python
class GlobalValueDecisionKind(StrEnum):
    COPY_BASELINE = "copy_baseline"
    AUTHORIZED_OVERLAY = "authorized_overlay"
    LLM_OPTIMIZED_START = "llm_optimized_start"
```

Update `GlobalValueDecision.__post_init__` so the new kind requires:

- `authority_id` beginning with `starter:`;
- emitted canonical JSON different from baseline when the rule is counted as changed;
- no requirement for a source claim ID.

Do not change the existing source-backed overlay validation.

- [ ] **Step 4: Run the GREEN tests**

Run the same focused command. Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add -- src/hsconfig/visionai_registry.py src/hsconfig/globalvalues_decisions.py src/hsconfig/package_domain.py tests/test_contract_registry.py tests/test_globalvalues_decisions.py
git diff --cached --check
git commit -S -m "feat: define optimized runtime constraints"
```

---

## Task 2: Implement Bounded Canonical Starter Documents

**Files:**

- Create: `src/hsconfig/starter_document.py`
- Create: `src/hsconfig/starter_contract.py`
- Create: `tests/test_starter_contract.py`

- [ ] **Step 1: Write RED tests for byte and schema closure**

Cover the following concrete failures:

- UTF-8 BOM, invalid UTF-8, bare CR, NUL, duplicate JSON key, NaN/Infinity, noncanonical bytes, and oversize input;
- missing/extra top-level field, wrong schema version, stale self digest, and path-like fields in a critic document;
- any sibling name other than the five fixed names;
- candidate revisions outside 1 through 3.

The document limits are:

```python
STARTER_CONTEXT_MAX_BYTES = 512 * 1024
STARTER_CANDIDATE_MAX_BYTES = 256 * 1024
STARTER_DECISION_MAX_BYTES = 64 * 1024
```

The self digest is `sha256:<lowercase hex>` over compact sorted UTF-8 JSON after removing only `content_sha256`.

- [ ] **Step 2: Run the RED test**

```powershell
python -B -m pytest tests/test_starter_contract.py -q -p no:cacheprovider
```

Expected: collection FAIL because `hsconfig.starter_document` and `hsconfig.starter_contract` are missing.

- [ ] **Step 3: Implement the canonical document authority**

Create the shared immutable wrapper:

```python
@dataclass(frozen=True, slots=True)
class StarterDocument:
    document: FrozenJsonDocument
    content_sha256: str

    @property
    def canonical_json(self) -> bytes:
        return self.document.canonical_json

    def to_value(self) -> dict[str, Any]:
        value = self.document.to_value()
        if not isinstance(value, dict):
            raise TypeError("starter_document_root_invalid")
        return value
```

Compose the existing `package_request.FrozenJsonDocument`; do not duplicate its duplicate-key/non-finite/canonical JSON machinery. Implement `seal_starter_document(value: Mapping[str, Any], *, expected_fields: frozenset[str], schema_version: int) -> StarterDocument` and `load_starter_document(path: Path, *, maximum_bytes: int, expected_fields: frozenset[str], schema_version: int) -> StarterDocument` as the only public constructors. `load_starter_document` must read once with a bounded no-follow helper, reject noncanonical source bytes, and never retain the input path as authority.

In `starter_contract.py`, define the five filename constants, exact field sets from the design spec, role enum, and closed scalar/list/object helpers used by later semantic validators.

- [ ] **Step 4: Run the GREEN test and the adjacent strict-JSON test**

```powershell
python -B -m pytest tests/test_starter_contract.py tests/test_package_request.py::test_frozen_documents_are_canonical_and_copy_their_byte_input tests/test_package_request.py::test_frozen_json_rejects_duplicate_object_keys tests/test_package_request.py::test_frozen_json_rejects_nonfinite_numbers -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add -- src/hsconfig/starter_document.py src/hsconfig/starter_contract.py tests/test_starter_contract.py
git diff --cached --check
git commit -S -m "feat: add bounded starter documents"
```

---

## Task 3: Build the Deterministic Starter Context and CLI

**Files:**

- Create: `src/hsconfig/starter_context.py`
- Create: `src/hsconfig/commands/starter_context.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/commands/__init__.py`
- Create: `tests/test_starter_context.py`
- Create: `tests/test_starter_context_cli.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_cli_help.py`

- [ ] **Step 1: Write the ShadowPriest context RED**

Using the existing audited ShadowPriest deck and card fixtures, assert that the context contains:

- deck fingerprint `831b989cf8d076bff87848b4d0d6f382c9d306fddea7619017f0c361bfc92327`;
- HS ID `2737726722` and HDT deck ID `c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602` when present in the audited catalog;
- exactly 16 unique main-deck CardID rows, each with its positive count, whose counts sum to 30 physical cards, plus the exact CardIDs from the supplied deck code;
- cost, type, text, mechanics, deterministic curve/type/mechanic counts, and linked entities;
- the supported runtime registry plus all optimized bounds;
- exactly 38 GlobalValues baseline keys and the baseline receipt/digest;
- the authorized Darkbishop relation `SW_448 -> EX1_625t` with block `BeforeUseHeroPowerBonus`;
- bounded normalized source evidence and explicit gaps, never raw web instructions;
- a stable canonical self digest.

Add a CLI test proving `starter-context` writes only `starter_context.json` beneath its `--out` directory and does not modify the runtime root.

Name the added help node `test_starter_context_help_exposes_bounded_read_only_operands`.

- [ ] **Step 2: Run the RED tests**

```powershell
python -B -m pytest tests/test_starter_context.py tests/test_starter_context_cli.py tests/test_cli_help.py::test_starter_context_help_exposes_bounded_read_only_operands -q -p no:cacheprovider
```

Expected: FAIL because the command and builder are missing.

- [ ] **Step 3: Implement context construction from one resolved snapshot**

Use this core immutable result:

```python
@dataclass(frozen=True, slots=True)
class StarterContext:
    document: StarterDocument
    deck_fingerprint: str
    globalvalues_baseline_sha256: str
```

Expose one constructor with the exact signature `build_starter_context(snapshot: PackageResolutionSnapshot) -> StarterContext`.

The implementation must consume `snapshot.general_preconfig` and its already resolved `globalvalues_baseline`; it must not decode the deck, fetch cards, or load the runtime baseline a second time.

Source evidence projection must omit volatile timestamps, local paths, fetch durations, and raw HTML. Two resolutions of byte-identical source/card/baseline authority must therefore produce the same starter-context digest; any semantic source, card, registry, or baseline change must change it.

The `cards` collection is keyed by unique main-deck CardID. Do not duplicate a row for each physical copy. Preserve `count` as data and assert `len(cards) == 16` and `sum(row["count"] for row in cards) == 30` for the audited ShadowPriest snapshot.

Add the parser surface:

```text
hsconfig starter-context --deck-name NAME --deck-code CODE --runtime-root PATH --out PATH [the existing source/card fixture options] --json
```

`commands/starter_context.py` should call the existing package resolution boundary in conservative mode, build the context from that frozen snapshot, and write compact canonical bytes with `atomic_write_bytes`.

- [ ] **Step 4: Run GREEN and the exact deck adjacency**

```powershell
python -B -m pytest tests/test_starter_context.py tests/test_starter_context_cli.py tests/test_cli.py::test_cli_parser_subcommands_match_main_dispatch_commands tests/test_cli_help.py::test_starter_context_help_exposes_bounded_read_only_operands tests/test_deckstring_decode.py::test_decode_shadowpriest_deck_code_to_exact_cardids tests/test_globalvalues_decisions.py::test_baseline_profile_closes_all_38_keys_in_registry_order -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add -- src/hsconfig/starter_context.py src/hsconfig/commands/starter_context.py src/hsconfig/cli_parser.py src/hsconfig/cli.py src/hsconfig/commands/__init__.py tests/test_starter_context.py tests/test_starter_context_cli.py tests/test_cli.py tests/test_cli_help.py
git diff --cached --check
git commit -S -m "feat: expose deterministic starter context"
```

---

## Task 4: Validate Three Candidates and the Independent Critic Decision

**Files:**

- Create: `src/hsconfig/starter_candidate.py`
- Create: `src/hsconfig/starter_decision.py`
- Create: `src/hsconfig/commands/starter_validate_candidate.py`
- Modify: `src/hsconfig/starter_contract.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `src/hsconfig/commands/__init__.py`
- Create: `tests/test_starter_candidate.py`
- Create: `tests/test_starter_decision.py`
- Create: `tests/test_starter_candidate_cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write candidate RED cases**

Create one valid ShadowPriest candidate builder and mutate one field per parameterized case. Require rejection for:

- wrong context digest or deck fingerprint;
- unknown physical CardID or unauthorized linked runtime owner;
- unsupported surface/block, unsafe condition, non-finite value, or bound violation;
- missing/extra GlobalValues key or changed metadata key;
- wildcard/drop Mulligan selector, missing Mulligan rule, duplicate/conflicting runtime row;
- physical rule on `SW_448` for the transformed hero power instead of authorized runtime owner `EX1_625t`;
- anything other than exactly one disposition for each unique main-deck CardID (16 rows for the audited ShadowPriest deck), including duplicate, missing, extra, or physical-copy-expanded rows;
- inexpressible Combo sequence;
- wholly baseline/default-only runtime intent.

Candidate `strategy_summary` must be this closed object:

```json
{"role":"proactive_tempo","summary":"Prioritize early pressure while preserving a bounded refill line."}
```

Card rules use the exact fields:

```json
{
  "rule_id":"darkbishop-mind-spike",
  "source_card_id":"SW_448",
  "runtime_card_id":"EX1_625t",
  "link_kind":"hero_power_transform",
  "behavior_block":"BeforeUseHeroPowerBonus",
  "condition":"*",
  "value":"12"
}
```

- [ ] **Step 2: Write decision RED cases**

Require exactly three fixed-role candidates; each candidate revision is independently in the inclusive range 1 through 3. Revisions are not globally unique: the normal initial set has revision 1 for all three, and only a repaired candidate increments its own revision. Require unique IDs, unique content digests, and distinct runtime-intent digests. The critic's `reviewed_candidates` and `ranking` must be exact permutations of the same three IDs; `rejection_reasons` must contain exactly the two rejected IDs. Reject stale candidate digests, narrative-only diversity, missing critic identity, and critic-authored candidate mutation.

Add a CLI RED proving that `starter-validate-candidate`:

- accepts only `--starter-context-json`, `--candidate-json`, and `--json` as public operands;
- loads one canonical starter context and one candidate without resolving sources, touching runtime state, or writing files;
- exits zero with one bounded JSON receipt containing `valid=true`, candidate ID/revision/role, context digest, candidate digest, and runtime-intent digest;
- exits nonzero with a stable error for a malformed or context-mismatched candidate.

- [ ] **Step 3: Run the RED tests**

```powershell
python -B -m pytest tests/test_starter_candidate.py tests/test_starter_decision.py tests/test_starter_candidate_cli.py -q -p no:cacheprovider
```

Expected: collection FAIL because the validators are missing.

- [ ] **Step 4: Implement typed validation and fixed-sibling loading**

Use these public immutable results:

```python
@dataclass(frozen=True, slots=True)
class ValidatedStarterCandidate:
    document: StarterDocument
    candidate_id: str
    candidate_revision: int
    strategy_role: str
    runtime_intent_sha256: str
    mulligan_plan: MulliganPlanModel
    globalvalues: FrozenJsonDocument
    card_behavior_rows: tuple[FrozenJsonDocument, ...]
    combo_plan: ComboPlanModel


@dataclass(frozen=True, slots=True)
class ValidatedStarterSelection:
    context: StarterContext
    candidates: tuple[ValidatedStarterCandidate, ...]
    decision: StarterDocument
    selected: ValidatedStarterCandidate
```

Expose exactly `validate_starter_candidate(document: StarterDocument, *, context: StarterContext) -> ValidatedStarterCandidate` and `load_validated_starter_selection(decision_path: Path, *, current_context: StarterContext) -> ValidatedStarterSelection`. Load only the fixed sibling names. Use `normalize_mulligan_selector`, `classify_runtime_condition`, `runtime_entity_owner_relation_is_authorized`, `canonicalize_runtime_rows`, `ComboDecisionModel`, and the optimized constraint registry. Do not build a `GlobalValuesDecisionLedger` here: retain the validated exact 38-key desired state as `FrozenJsonDocument`, and let Task 6 build the one authoritative ledger. Do not create source receipts or promote starter rules to guide claims.

Add the deterministic read-only CLI surface:

```text
hsconfig starter-validate-candidate --starter-context-json PATH --candidate-json PATH --json
```

`commands/starter_validate_candidate.py` loads the bounded context document, reconstructs the typed `StarterContext`, validates exactly one candidate, and prints only the bounded receipt described in Step 2. It must not accept a runtime root, output root, decision path, network/source option, or repair option. Add the parser/dispatch entry and extend `test_cli_parser_subcommands_match_main_dispatch_commands`.

- [ ] **Step 5: Run GREEN plus grammar/identity adjacency**

```powershell
python -B -m pytest tests/test_starter_candidate.py tests/test_starter_decision.py tests/test_starter_candidate_cli.py tests/test_condition_format.py::test_rejects_unknown_strings_and_top_level_pipe tests/test_runtime_row_identity.py::test_same_surface_condition_with_different_values_fails_closed tests/test_globalvalues_decisions.py::test_baseline_profile_closes_all_38_keys_in_registry_order tests/test_combo_domain.py::test_combo_values_must_be_finite_decimal_strings tests/test_cli.py::test_cli_parser_subcommands_match_main_dispatch_commands -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```powershell
git add -- src/hsconfig/starter_candidate.py src/hsconfig/starter_decision.py src/hsconfig/commands/starter_validate_candidate.py src/hsconfig/starter_contract.py src/hsconfig/cli_parser.py src/hsconfig/cli.py src/hsconfig/commands/__init__.py tests/test_starter_candidate.py tests/test_starter_decision.py tests/test_starter_candidate_cli.py tests/test_cli.py
git diff --cached --check
git commit -S -m "feat: validate optimized start selections"
```

---

## Task 5: Freeze Optimized Selection at the Configure/Package Boundary

**Files:**

- Modify: `src/hsconfig/configure_models.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/configure_workflow.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/audited_build_request.py`
- Create: `src/hsconfig/configuration_mode.py`
- Modify: `src/hsconfig/package_request.py`
- Modify: `src/hsconfig/package_compiler.py`
- Modify: `tests/helpers/audited_package_request.py`
- Modify: `tests/test_configure_workflow.py`
- Modify: `tests/test_configure_publication.py`
- Modify: `tests/test_global_branch_coverage.py`
- Modify: `tests/test_package_request.py`
- Modify: `tests/test_package_compiler.py`
- Create: `tests/test_configure_optimized_start.py`

- [ ] **Step 1: Write the CLI/request handshake RED**

Add tests for the exact failures:

- `--optimized-start` without `--starter-decision-json` -> `starter_decision_required`;
- decision path without `--optimized-start` -> `starter_decision_not_enabled`;
- supplied context digest differs from freshly rebuilt resolved context -> `starter_context_mismatch`;
- candidate/decision load failure occurs before publication and leaves previous `current.json` byte-identical;
- the selected candidate bytes remain unchanged if the source files are modified after request resolution.
- every legacy constructor and `ResolvedPackageRequest.from_values` path resolves to `configuration_mode="CONSERVATIVE"` and `starter_selection=None`;
- `LLM_OPTIMIZED_START` without a valid frozen selection and every unknown mode fail closed;
- optimized `reports/input_manifest.json` receives top-level `"configuration_mode":"LLM_OPTIMIZED_START"`; a conservative manifest remains byte-identical to the pinned legacy fixture and therefore omits the field;
- `configuration_mode_from_manifest` reads a missing field as legacy `CONSERVATIVE`, accepts the two exact known string values, and rejects every present non-string or unknown value.

- [ ] **Step 2: Run the RED tests**

```powershell
python -B -m pytest tests/test_configure_optimized_start.py tests/test_package_request.py::test_package_invocation_is_slotted_frozen_and_excludes_transport_fields tests/test_package_compiler.py::test_c4_compiles_complete_immutable_runtime_and_report_inputs tests/test_configure_publication.py::test_failed_configure_leaves_previous_current_byte_identical -q -p no:cacheprovider
```

Expected: FAIL because the request fields and frozen selection do not exist.

- [ ] **Step 3: Extend immutable request types**

Add to `ConfigureRequest`:

```python
optimized_start: bool
starter_decision_json: Path | None
```

Add to `PackageInvocation`:

```python
configuration_mode: Literal["CONSERVATIVE", "LLM_OPTIMIZED_START"] = "CONSERVATIVE"
```

Add to `ResolvedPackageRequest`:

```python
starter_selection: ValidatedStarterSelection | None
```

Use a `TYPE_CHECKING` forward import for the annotation and local runtime imports inside `ResolvedPackageRequest.__post_init__` and `resolve_package_request`; this keeps `starter_document -> package_request.FrozenJsonDocument` acyclic during module import. Do not retain `starter_decision_json` or any sibling path in the resolved compiler request. In `resolve_package_request`, build the normal snapshot and current `StarterContext` first, then load/validate the selection once and freeze the typed result.

Update every production `PackageInvocation(...)` and `ResolvedPackageRequest.from_values(...)` call in `package_request.py` and `audited_build_request.py` to pass the conservative values explicitly. Update the shared audited test helper and the two direct constructor test sites likewise; prove completeness with:

```powershell
rg -n "PackageInvocation\(|ResolvedPackageRequest\.from_values\(" src tests
```

Every listed construction must either pass the explicit conservative pair or be a focused test of the default/failure contract. `ResolvedPackageRequest.__post_init__` requires exact parity: conservative mode has no selection, optimized mode has one valid `ValidatedStarterSelection`, and no third state is accepted.

- [ ] **Step 4: Propagate the configure options without introducing a second stage writer**

Update `configure_request_from_args`, `_request_namespace`, and the namespace passed to `prepare_package_payload`. Invalid optimized input must fail inside the existing temporary build before immutable publication. Do not add a post-publication candidate stage.

Create `configuration_mode.py` with the literal mode type/constants and one public `configuration_mode_from_manifest(manifest: Mapping[str, Any])` function. It returns `CONSERVATIVE` when the legacy field is absent, returns either exact known string when present, and raises `ValueError("configuration_mode_invalid")` for every other present value.

In `package_compiler.py`, add top-level `"configuration_mode":"LLM_OPTIMIZED_START"` to `reports/input_manifest.json` only for an optimized request. A conservative request emits the exact legacy manifest bytes with the field absent. This optimized projection occurs before Task 7 adds receipt/apply dispatch and is covered by the frozen invocation digest. The conservative compatibility regression compares a pinned pre-change package with the new result and requires every artifact, including `reports/input_manifest.json`, to remain byte-identical.

- [ ] **Step 5: Run GREEN and conservative mapping adjacency**

```powershell
python -B -m pytest tests/test_configure_optimized_start.py tests/test_package_request.py::test_package_invocation_is_slotted_frozen_and_excludes_transport_fields tests/test_package_request.py::test_general_resolution_request_detaches_every_nested_mutable_input tests/test_package_request.py::test_frozen_documents_are_canonical_and_copy_their_byte_input tests/test_package_request.py::test_resolved_request_binds_strict_context_to_invocation_deck_code tests/test_configure_workflow.py::test_cli_maps_every_configure_option_and_leaves_namespace_byte_identical tests/test_configure_workflow.py::test_configure_stage_order_is_exact_and_deterministic tests/test_configure_workflow.py::test_each_offline_stage_failure_is_fail_closed_without_runtime_publication tests/test_configure_publication.py::test_failed_configure_leaves_previous_current_byte_identical tests/test_package_compiler.py::test_c4_compiles_complete_immutable_runtime_and_report_inputs tests/test_global_branch_coverage.py::test_package_invocation_rejects_noncanonical_transport_and_mode_values -q -p no:cacheprovider
```

Expected: PASS for request/mapping/failure tests. No optimized success is expected until Task 6.

- [ ] **Step 6: Commit Task 5**

```powershell
git add -- src/hsconfig/configure_models.py src/hsconfig/commands/configure.py src/hsconfig/configure_workflow.py src/hsconfig/cli_parser.py src/hsconfig/audited_build_request.py src/hsconfig/configuration_mode.py src/hsconfig/package_request.py src/hsconfig/package_compiler.py tests/helpers/audited_package_request.py tests/test_configure_workflow.py tests/test_configure_publication.py tests/test_global_branch_coverage.py tests/test_package_request.py tests/test_package_compiler.py tests/test_configure_optimized_start.py
git diff --cached --check
git commit -S -m "feat: freeze optimized configure inputs"
```

---

## Task 6: Lower the Selected Candidate Before Runtime Compilation

**Files:**

- Create: `src/hsconfig/starter_compiler.py`
- Modify: `src/hsconfig/package_compiler.py`
- Modify: `src/hsconfig/package_domain.py`
- Modify: `src/hsconfig/globalvalues_decisions.py`
- Modify: `src/hsconfig/disposition_ledger.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Create: `tests/test_starter_compiler.py`
- Modify: `tests/test_package_compiler.py`
- Modify: `tests/test_compile_mulligan.py`
- Modify: `tests/test_compile_cardid.py`
- Modify: `tests/test_compile_globalvalues.py`

- [ ] **Step 1: Write the direct-lowering RED**

Given one validated selected candidate, assert that `compile_package` produces:

- physical non-empty `Mulligan.json` from candidate rules;
- complete `GlobalValues.json` with the exact 38-key set and selected values;
- only supported per-card files, including `EX1_625t.json` for Darkbishop's transformed hero power;
- `Combo.json` only when candidate Combo is present and expressible;
- no `Presume.json`, `Concede.json`, or aggregate `CardBehavior.json`;
- rule provenance `LLM_OPTIMIZED_START` with empty fabricated source-claim IDs;
- all existing runtime ledgers/dispositions regenerated from the selected candidate;
- all five optimized evidence projections equal the originally frozen canonical bytes.

Add a regression asserting that conservative `compile_package` produces the same canonical projections and runtime values as before Task 6.

- [ ] **Step 2: Run the RED tests**

```powershell
python -B -m pytest tests/test_starter_compiler.py tests/test_package_compiler.py::test_c3_compiles_real_audited_decisions_without_post_request_io tests/test_package_compiler.py::test_c4_compiles_complete_immutable_runtime_and_report_inputs -q -p no:cacheprovider
```

Expected: FAIL because `starter_compiler` and the optimized branch are missing.

- [ ] **Step 3: Implement a neutral lowering result**

Avoid a circular import by returning a neutral result from the new module:

```python
@dataclass(frozen=True, slots=True)
class OptimizedStartLowering:
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    card_behavior_plan: FrozenJsonDocument
    optimized_projections: tuple[tuple[str, StarterDocument], ...]
    authority_id: str
```

Expose `lower_optimized_start(*, request: ResolvedPackageRequest, selection: ValidatedStarterSelection) -> OptimizedStartLowering`. The authority ID is `starter:<selected-candidate-content-sha256>`. The selected candidate contributes only its frozen complete `globalvalues` desired-state document; this function invokes `build_optimized_globalvalues_decision_ledger` exactly once and places that one ledger in the lowering result. No validator, adapter, report builder, or package compiler branch may build a second optimized ledger.

- [ ] **Step 4: Integrate at `compile_package_decisions`**

Extend `PackageDecisionSnapshot` with an optional `optimized_start_lowering`. In `compile_package_decisions`:

```python
if request.starter_selection is None:
    return _compile_conservative_package_decisions(request)
return _compile_optimized_package_decisions(request)
```

The optimized branch may reuse verified deck/card/source context from the conservative base, but it replaces Mulligan, complete GlobalValues desired state, card behavior rows, Combo, and their disposition/explainability inputs before `compile_package` builds runtime files.

Use a dedicated `build_optimized_globalvalues_decision_ledger` that emits `COPY_BASELINE` for unchanged keys and `LLM_OPTIMIZED_START` for changed keys. It consumes the selected candidate's frozen 38-key desired state and the exact context-bound baseline and is the sole optimized GlobalValues ledger authority. Do not route direct candidate values through `build_globalvalues_authority_matrix` or Step1 source overlays.

- [ ] **Step 5: Run GREEN and physical compiler adjacency**

```powershell
python -B -m pytest tests/test_starter_compiler.py tests/test_package_compiler.py::test_c3_compiles_real_audited_decisions_without_post_request_io tests/test_package_compiler.py::test_c3_identical_request_is_equal_and_caller_mutation_cannot_change_it tests/test_package_compiler.py::test_c4_compiles_complete_immutable_runtime_and_report_inputs tests/test_compile_mulligan.py::test_compile_mulligan_emits_valid_mulligan_block tests/test_compile_mulligan.py::test_compile_mulligan_rejects_wildcard_even_in_a_typed_plan tests/test_compile_cardid.py::test_darkbishop_hero_power_behavior_is_owned_by_linked_mind_spike_file tests/test_compile_cardid.py::test_compile_cardid_merges_exact_duplicate_rows_as_final_write_guard tests/test_compile_globalvalues.py::test_compile_globalvalues_preserves_and_profiles_every_key tests/test_combo_domain.py::test_typed_combo_plan_is_the_direct_report_and_runtime_authority -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```powershell
git add -- src/hsconfig/starter_compiler.py src/hsconfig/package_compiler.py src/hsconfig/package_domain.py src/hsconfig/globalvalues_decisions.py src/hsconfig/disposition_ledger.py src/hsconfig/source_to_runtime_explainability.py tests/test_starter_compiler.py tests/test_package_compiler.py tests/test_compile_mulligan.py tests/test_compile_cardid.py tests/test_compile_globalvalues.py
git diff --cached --check
git commit -S -m "feat: compile optimized start candidates"
```

---

## Task 7: Bind Reports, Receipt, Operator Summary, and Apply Authority

**Files:**

- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Modify: `src/hsconfig/package_derivation_receipt.py`
- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/operator_summary_inputs.py`
- Modify: `src/hsconfig/operator_summary_evaluator.py`
- Modify: `src/hsconfig/operator_status.py`
- Modify: `src/hsconfig/apply_decision.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/configure_workflow.py`
- Modify: `tests/test_contract_registry.py`
- Modify: `tests/test_output_ownership_manifest.py`
- Modify: `tests/test_package_derivation_receipt.py`
- Modify: `tests/test_strict_package_validation.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_apply_decision.py`
- Modify: `tests/test_apply_gate.py`
- Modify: `tests/test_configure_optimized_start.py`

- [ ] **Step 1: Write report/receipt tamper REDs**

For an optimized package, mutate each of the five evidence reports independently and assert the derivation receipt becomes invalid. Assert optimized validation requires exactly all five paths and rejects a stray optimized report in conservative mode.

Preserve receipt v2 for conservative packages. Emit receipt v3 only when `reports/input_manifest.json.configuration_mode == "LLM_OPTIMIZED_START"`; v3 includes all five optimized evidence paths in authoritative input digests.

Name the new focused nodes exactly:

- `test_optimized_receipt_binds_exact_five_starter_documents`;
- `test_optimized_receipt_rejects_each_starter_document_tamper`;
- `test_optimized_reports_are_all_or_none_and_conservative_mode_rejects_strays`;
- `test_optimized_report_ownership_is_mode_bound`.

- [ ] **Step 2: Write mode-aware apply REDs**

Assert:

- conservative apply still requires existing source acquisition authority;
- optimized apply ignores absence of exact strategic guide authority only when the starter selection, all five report digests, package derivation, strict package validation, deck identity, and summary parity are valid;
- malformed/stale starter derivation blocks with `optimized_start_derivation_invalid`;
- source limitations remain informational and visible;
- operator summary assurance is exactly `LLM_OPTIMIZED_START`, never `GAMEPLAY_OPTIMAL`;
- configure summary contains status, three candidate IDs, selection rationale, Mulligan summary, changed GlobalValues, per-card rules, Combo summary, risks, and next-report path. A valid `high` critic confidence maps to `selected`; valid `low` maps to `low_confidence`; any rejected/failed path maps to `failed` without publication.

Name the new focused nodes exactly:

- `test_optimized_apply_uses_bound_starter_derivation_without_fabricated_source_authority`;
- `test_apply_gate_allows_valid_llm_optimized_start`;
- `test_operator_summary_reports_llm_optimized_start_without_optimality_claim`;
- `test_optimized_configure_summary_binds_selected_candidate`.

- [ ] **Step 3: Run the RED tests**

```powershell
python -B -m pytest tests/test_package_derivation_receipt.py::test_optimized_receipt_binds_exact_five_starter_documents tests/test_package_derivation_receipt.py::test_optimized_receipt_rejects_each_starter_document_tamper tests/test_strict_package_validation.py::test_optimized_reports_are_all_or_none_and_conservative_mode_rejects_strays tests/test_output_ownership_manifest.py::test_optimized_report_ownership_is_mode_bound tests/test_apply_decision.py::test_optimized_apply_uses_bound_starter_derivation_without_fabricated_source_authority tests/test_apply_gate.py::test_apply_gate_allows_valid_llm_optimized_start tests/test_operator_summary.py::test_operator_summary_reports_llm_optimized_start_without_optimality_claim tests/test_configure_optimized_start.py::test_optimized_configure_summary_binds_selected_candidate -q -p no:cacheprovider
```

Expected: FAIL because optimized authority is not registered or bound.

- [ ] **Step 4: Register conditional package authority**

Register the five exact optimized report paths as conditional diagnostic artifacts owned by the package compiler. Update ownership manifests and strict validation so the set is all-or-none and tied to `configuration_mode`.

Implement receipt dispatch:

```python
def _receipt_schema_for(package: PackageView) -> int:
    manifest = package.read_json("reports/input_manifest.json")
    if configuration_mode_from_manifest(manifest) == "LLM_OPTIMIZED_START":
        return 3
    return 2
```

Both path-based and `PackageView` receipt builders/verifiers must use the same conditional authoritative path set.

All mode dispatch calls the one `configuration_mode_from_manifest` authority from Task 5. A missing field is accepted only as the existing conservative legacy format; a present non-string or unknown value is rejected before choosing a receipt schema, report set, operator authority, or apply gate. Do not infer optimized mode from report presence, a CLI flag, candidate filenames, or source status.

- [ ] **Step 5: Make apply facts explicitly mode-aware**

Add these fields to `ApplyFacts` and its sealed/operator equivalents:

```python
strategy_authority_mode: Literal["source_contract", "llm_optimized_start"]
optimized_start_derivation_validity: bool
```

Common technical facts remain mandatory for both modes. `source_acquisition_eligibility` remains blocking only for `source_contract`; `optimized_start_derivation_validity` is blocking only for `llm_optimized_start`. Preserve source receipt diagnostics and do not relabel LLM rules as live source.

- [ ] **Step 6: Run GREEN and package-authority adjacency**

```powershell
python -B -m pytest tests/test_package_derivation_receipt.py::test_optimized_receipt_binds_exact_five_starter_documents tests/test_package_derivation_receipt.py::test_optimized_receipt_rejects_each_starter_document_tamper tests/test_strict_package_validation.py::test_optimized_reports_are_all_or_none_and_conservative_mode_rejects_strays tests/test_output_ownership_manifest.py::test_optimized_report_ownership_is_mode_bound tests/test_apply_decision.py::test_optimized_apply_uses_bound_starter_derivation_without_fabricated_source_authority tests/test_apply_gate.py::test_apply_gate_allows_valid_llm_optimized_start tests/test_operator_summary.py::test_operator_summary_reports_llm_optimized_start_without_optimality_claim tests/test_configure_optimized_start.py::test_optimized_configure_summary_binds_selected_candidate tests/test_package_derivation_receipt.py::test_empty_canonical_receipts_remain_nonblocking_diagnostics tests/test_output_ownership_manifest.py::test_pre_run_reports_are_diagnostic_and_operator_summary_is_the_only_gate tests/test_apply_gate.py::test_apply_gate_allows_source_backed_ready_package tests/test_apply_gate.py::test_apply_gate_blocks_invalid_package tests/test_operator_summary.py::test_operator_summary_separates_pre_run_assurance_dimensions -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```powershell
git add -- src/hsconfig/visionai_registry.py src/hsconfig/report_ownership.py src/hsconfig/output_ownership_manifest.py src/hsconfig/package_derivation_receipt.py src/hsconfig/strict_package_validation.py src/hsconfig/operator_summary_inputs.py src/hsconfig/operator_summary_evaluator.py src/hsconfig/operator_status.py src/hsconfig/apply_decision.py src/hsconfig/apply_gate.py src/hsconfig/configure_workflow.py tests/test_contract_registry.py tests/test_output_ownership_manifest.py tests/test_package_derivation_receipt.py tests/test_strict_package_validation.py tests/test_operator_summary.py tests/test_apply_decision.py tests/test_apply_gate.py tests/test_configure_optimized_start.py
git diff --cached --check
git commit -S -m "feat: bind optimized package authority"
```

---

## Task 8: Teach the Embedded HSConfig Skill the Three-Candidate Workflow

**Files:**

- Modify: `src/hsconfig/resources/codex_skill_bundle.json`
- Modify: `tests/test_external_skill_bundle.py`
- Create: `tests/test_optimized_skill_workflow.py`
- Modify: `tests/test_distribution_contract.py`
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `tests/test_operator_docs_contract_policy.py`

- [ ] **Step 1: Write the skill-contract RED**

Decode the embedded nine-file bundle and assert the skill instructions require this exact sequence:

1. run `starter-context`;
2. treat `starter_context.json` as immutable;
3. create exactly `candidate-1.json`, `candidate-2.json`, and `candidate-3.json` with the three fixed roles;
4. seal each draft with `seal_starter_document`, write its compact canonical bytes to its fixed filename, then run `hsconfig starter-validate-candidate --starter-context-json starter_context.json --candidate-json <fixed-candidate-name> --json` for each of the three candidates before criticism;
5. dispatch an independent clean-context critic agent;
6. let the critic write only `starter_config_decision.json` and rank all three without a numeric score;
7. allow at most two targeted strategist repair rounds for technical defects;
8. run `configure --optimized-start --starter-decision-json`;
9. validate `LLM_OPTIMIZED_START` and the optimized summary;
10. apply only when the user requested live writing, then run `runtime-match`.

Assert the bundle still contains exactly nine files and no model SDK/import/client call.

Name the added docs node `test_docs_define_optimized_start_as_pre_game_non_optimality_contract`.

- [ ] **Step 2: Run the RED tests**

```powershell
python -B -m pytest tests/test_optimized_skill_workflow.py tests/test_external_skill_bundle.py::test_embedded_bundle_is_exact_closed_nine_file_contract tests/test_external_skill_bundle.py::test_bundle_decoder_compiles_both_python_helpers tests/test_operator_docs_contract_policy.py::test_docs_define_optimized_start_as_pre_game_non_optimality_contract -q -p no:cacheprovider
```

Expected: FAIL because the embedded workflow still defaults to conservative source-only generation.

- [ ] **Step 3: Update the existing bundle files, not the file count**

Change the embedded content for:

- `SKILL.md`;
- `references/workflow.md`;
- `references/contract-compiler-checklist.md`;
- `references/globalvalues-policy.md`;
- `references/card-behavior-policy.md`;
- `scripts/build_config.py` to invoke `starter-context`, the three deterministic candidate validations, and `configure --optimized-start` with the fixed filenames;
- `scripts/validate_package.py` to require the optimized summary/assurance.

Do not add a tenth bundle file. Recompute every modified per-file SHA-256 and the aggregate with `compute_bundle_aggregate`; then patch the exact resulting hashes into the resource. The source resource, sdist, and wheel bytes must remain identical.

The embedded workflow must include a concrete local Python invocation of `seal_starter_document` so agents do not hand-calculate self digests. It then invokes the public `starter-validate-candidate` CLI separately for all three fixed candidate files and records their three zero-exit receipts before dispatching the critic. That flow writes only the three fixed candidate files and later the fixed decision file beneath the caller-owned external starter directory; it is not a runtime write and it never chooses a path from LLM JSON. A failed validator receipt returns only that candidate to its own strategist, with at most two repair attempts, and the critic is not started until all three receipts are valid.

- [ ] **Step 4: Update user/operator docs**

Document the optimized skill path as the normal generation route while preserving conservative CLI mode. Include the fixed filenames, error codes, critic independence, two-repair maximum, `LLM_OPTIMIZED_START` meaning, failure preservation, guarded apply, and runtime-match. State explicitly that the result is a best practical pre-game start config, not measured gameplay optimality.

- [ ] **Step 5: Run GREEN plus distribution parity**

```powershell
python -B -m pytest tests/test_optimized_skill_workflow.py tests/test_external_skill_bundle.py::test_embedded_bundle_is_exact_closed_nine_file_contract tests/test_external_skill_bundle.py::test_bundle_decoder_compiles_both_python_helpers tests/test_operator_docs_contract_policy.py::test_docs_define_optimized_start_as_pre_game_non_optimality_contract tests/test_distribution_contract.py::test_skill_bundle_has_exact_source_sdist_wheel_byte_parity -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

```powershell
git add -- src/hsconfig/resources/codex_skill_bundle.json tests/test_external_skill_bundle.py tests/test_optimized_skill_workflow.py tests/test_distribution_contract.py README.md docs/operator/README.md tests/test_operator_docs_contract_policy.py
git diff --cached --check
git commit -S -m "docs: teach hsconfig optimized orchestration"
```

---

## Task 9: Prove ShadowPriest End to End Without Broad Deck Expansion

**Files:**

- Create: `tests/starter_fixtures.py`
- Create: `tests/test_shadowpriest_optimized_start.py`
- Read-only adjacency: `tests/test_shadowpriest_semantic_safety_wave.py`
- Read-only adjacency: `tests/test_runtime_match_cli.py`

- [ ] **Step 1: Create one deterministic ShadowPriest starter bundle fixture**

Use the exact operator input:

```text
Deck name: ShadowPriest
Deck code: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
HS ID: 2737726722
HDT deck ID: c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602
```

The fixture helper must seal three materially different valid runtime intents and one critic decision. It is test data, not the eventual live candidate authority.

- [ ] **Step 2: Write the single end-to-end RED test file**

Assert:

- context binds the exact deck fingerprint and exactly 16 unique main-deck CardID rows whose positive counts sum to 30;
- `card_dispositions` contains exactly one row for each of those 16 unique CardIDs, not 30 physical-copy rows;
- the critic reviewed exactly three candidates and selected one;
- selected output has non-empty physical Mulligan rows;
- GlobalValues has exactly 38 keys and at least one changed strategic value;
- at least one targeted CardID rule is emitted;
- Darkbishop uses `EX1_625t` ownership correctly;
- all five optimized reports, v3 derivation receipt, ownership manifest, runtime ledger, operator summary, and configure summary agree on candidate/decision digests;
- fake guarded apply succeeds and `runtime-match` returns `matched`;
- a deliberately invalid selected candidate leaves previous published/live state byte-identical.

- [ ] **Step 3: Run the RED test**

```powershell
python -B -m pytest tests/test_shadowpriest_optimized_start.py -q -p no:cacheprovider
```

Expected: FAIL until the full optimized path is connected.

- [ ] **Step 4: Treat Task 9 as verification-only**

Do not edit production code in Task 9. If this integration test exposes a real defect, stop this task, map the failure to the exact owning seam from Tasks 1 through 8, add one focused RED at that seam, implement the smallest general fix there, and create a separate signed fix commit with literal paths. Then restart Task 9 from Step 3. Never add ShadowPriest-specific production branches, values, or hard-coded CardIDs beyond the existing general linked-entity registry.

- [ ] **Step 5: Run GREEN plus the existing ShadowPriest safety adjacency**

```powershell
python -B -m pytest tests/test_shadowpriest_optimized_start.py tests/test_shadowpriest_semantic_safety_wave.py::test_supported_burn_aura_and_hero_power_rows_remain tests/test_shadowpriest_semantic_safety_wave.py::test_shadowpriest_package_identity_and_globalvalues_are_exact tests/test_shadowpriest_semantic_safety_wave.py::test_darkbishop_effect_does_not_become_mulligan_or_body_priority tests/test_runtime_match_cli.py::test_runtime_match_cli_reports_matched_package tests/test_runtime_match_cli.py::test_runtime_match_cli_returns_nonzero_for_mismatch -q -p no:cacheprovider
```

Expected: PASS.

- [ ] **Step 6: Commit Task 9**

```powershell
git add -- tests/starter_fixtures.py tests/test_shadowpriest_optimized_start.py
git diff --cached --check
git commit -S -m "test: prove ShadowPriest optimized start"
```

Before committing, require `git diff --cached --name-only` to list exactly these two test paths. Any production path means Step 4 was not followed and is a hard stop.

---

## Task 10: Final Focused QA, Independent Reviews, Release, and Live ShadowPriest Generation

**Files:**

- No planned production edits
- Append-only ignored implementation evidence report only if the active master plan requires it

- [ ] **Step 1: Run the consolidated focused test set once**

```powershell
python -B -m pytest tests/test_starter_contract.py tests/test_starter_context.py tests/test_starter_context_cli.py tests/test_starter_candidate.py tests/test_starter_candidate_cli.py tests/test_starter_decision.py tests/test_starter_compiler.py tests/test_configure_optimized_start.py tests/test_optimized_skill_workflow.py tests/test_shadowpriest_optimized_start.py tests/test_package_request.py::test_package_invocation_is_slotted_frozen_and_excludes_transport_fields tests/test_package_request.py::test_general_resolution_request_detaches_every_nested_mutable_input tests/test_package_request.py::test_frozen_documents_are_canonical_and_copy_their_byte_input tests/test_package_request.py::test_resolved_request_binds_strict_context_to_invocation_deck_code tests/test_package_compiler.py::test_c3_compiles_real_audited_decisions_without_post_request_io tests/test_package_compiler.py::test_c4_compiles_complete_immutable_runtime_and_report_inputs tests/test_package_derivation_receipt.py::test_optimized_receipt_binds_exact_five_starter_documents tests/test_package_derivation_receipt.py::test_optimized_receipt_rejects_each_starter_document_tamper tests/test_apply_decision.py::test_optimized_apply_uses_bound_starter_derivation_without_fabricated_source_authority tests/test_apply_gate.py::test_apply_gate_allows_valid_llm_optimized_start tests/test_apply_gate.py::test_apply_gate_allows_source_backed_ready_package tests/test_operator_summary.py::test_operator_summary_reports_llm_optimized_start_without_optimality_claim tests/test_external_skill_bundle.py::test_embedded_bundle_is_exact_closed_nine_file_contract tests/test_external_skill_bundle.py::test_bundle_decoder_compiles_both_python_helpers -q -p no:cacheprovider
```

Expected: PASS. This is the only consolidated local set; every existing large test file is represented only by named nodes. Do not run a second overlapping local mega-suite or a local full suite.

- [ ] **Step 2: Run narrow static/distribution QA**

```powershell
python -B -m ruff check --no-cache src/hsconfig/configuration_mode.py src/hsconfig/starter_document.py src/hsconfig/starter_contract.py src/hsconfig/starter_context.py src/hsconfig/starter_candidate.py src/hsconfig/starter_decision.py src/hsconfig/starter_compiler.py src/hsconfig/commands/starter_context.py src/hsconfig/commands/starter_validate_candidate.py tests/test_starter_contract.py tests/test_starter_context.py tests/test_starter_context_cli.py tests/test_starter_candidate.py tests/test_starter_candidate_cli.py tests/test_starter_decision.py tests/test_starter_compiler.py tests/test_configure_optimized_start.py tests/test_optimized_skill_workflow.py tests/test_shadowpriest_optimized_start.py
python -B -m pytest tests/test_distribution_contract.py::test_skill_bundle_has_exact_source_sdist_wheel_byte_parity -q -p no:cacheprovider
git diff --check
git status --short
```

Expected: Ruff PASS, distribution parity PASS, no diff-check errors, and no cache/build/coverage residue.

- [ ] **Step 3: Request two independent read-only reviews**

One reviewer checks spec/acceptance coverage. One reviewer checks security/integrity, especially:

- untrusted JSON bounds and fixed paths;
- context drift and immutable bytes;
- no source-authority masquerading;
- conditional receipt/report closure;
- failure before publication/apply;
- conservative compatibility;
- no model client or post-run scope.

Resolve every Critical/Important finding with focused RED/GREEN evidence before continuing.

- [ ] **Step 4: Verify all commits and push the accepted main tip**

```powershell
git status --porcelain=v1 --untracked-files=all
git log --show-signature -10 --oneline
git push origin main
```

Require a clean worktree, locally valid signatures, and a fast-forward push. Monitor exactly the push `ci.yml` run for the pushed OID; require contract, test/full-source-coverage, package, security, and residue checks to succeed. Do not rerun a deterministic assertion failure unchanged.

- [ ] **Step 5: Transactionally install the released nine-file skill bundle**

After exact-OID CI success, execute this exact Windows transaction from the accepted repository root:

```powershell
$skillRoot = "C:\Users\darbo\.codex\skills\hsconfig"
$beforeRaw = python -B -c 'import json,sys; from pathlib import Path; from hsconfig.external_skill_bundle import external_skill_tree_identity; print(json.dumps(external_skill_tree_identity(Path(sys.argv[1])), sort_keys=True, separators=(",", ":")))' $skillRoot
if ($LASTEXITCODE -ne 0) { throw "installed skill predecessor inspection failed" }
$before = $beforeRaw | ConvertFrom-Json
if (-not $before.present -or $before.files -ne 9 -or -not $before.aggregate_sha256) {
    throw "installed skill predecessor is not the reviewed nine-file tree"
}
$expectedPredecessor = [string]$before.aggregate_sha256

$installRaw = python -B -c 'import json,sys; from pathlib import Path; from hsconfig.external_skill_bundle import install_external_skill; print(json.dumps(install_external_skill(Path(sys.argv[1]), expected_predecessor_aggregate_sha256=sys.argv[2]), sort_keys=True, separators=(",", ":")))' $skillRoot $expectedPredecessor
if ($LASTEXITCODE -ne 0) { throw "transactional skill installation failed" }
$installed = $installRaw | ConvertFrom-Json

$afterRaw = python -B -c 'import json,sys; from pathlib import Path; from hsconfig.external_skill_bundle import external_skill_tree_identity; print(json.dumps(external_skill_tree_identity(Path(sys.argv[1])), sort_keys=True, separators=(",", ":")))' $skillRoot
if ($LASTEXITCODE -ne 0) { throw "installed skill successor inspection failed" }
$after = $afterRaw | ConvertFrom-Json
$bundleAggregate = python -B -c 'from hsconfig.external_skill_bundle import compute_bundle_aggregate,load_embedded_skill_bundle; print(compute_bundle_aggregate(load_embedded_skill_bundle()))'
if ($LASTEXITCODE -ne 0) { throw "embedded bundle aggregate inspection failed" }
if ($installed.status -notin @("installed", "already_current") -or
    $installed.files_installed -ne 9 -or
    $installed.aggregate_sha256 -ne $bundleAggregate -or
    -not $after.present -or $after.files -ne 9 -or $after.directories -ne 2 -or
    -not $after.aggregate_sha256) {
    throw "installed skill successor does not match the embedded bundle contract"
}
```

The exact predecessor aggregate is captured once and passed unchanged to the installer. Any absent, unknown, drifted, or non-nine-file predecessor stops before mutation. The installer's internal exact-byte reread plus the successor identity and embedded aggregate assertions above are all mandatory. Do not manually copy bundle files.

The current task may execute the repository commands directly after verifying installed-byte parity. Record that a new Codex task/app reload is required before future automatic skill discovery can use the newly installed instructions; do not claim the current task hot-reloaded them.

- [ ] **Step 6: Generate the real ShadowPriest candidates with independent agents**

Run the released `starter-context` command against:

```powershell
$systemTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)
$starterRoot = [IO.Path]::GetFullPath((Join-Path -Path $systemTempRoot -ChildPath ("hsconfig-shadowpriest-starter-" + [Guid]::NewGuid().ToString("N"))))
if ([IO.Path]::GetDirectoryName($starterRoot) -ine $systemTempRoot -or
    -not [IO.Path]::GetFileName($starterRoot).StartsWith("hsconfig-shadowpriest-starter-", [StringComparison]::Ordinal)) {
    throw "starter root is not the expected direct system-temp child"
}
New-Item -ItemType Directory -LiteralPath $starterRoot | Out-Null
$starterItem = Get-Item -LiteralPath $starterRoot -Force
if (-not $starterItem.PSIsContainer -or ($starterItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $starterItem.FullName -ine $starterRoot) {
    throw "starter root is not the newly created plain directory"
}
$starterRoot = $starterItem.FullName
python -B -m hsconfig.cli starter-context --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out $starterRoot --online-source --auto-source --json
```

Use three strategist agents to write and seal the three fixed candidates from the same immutable context. Before the critic sees any candidate, run the released deterministic validator for each fixed file:

```powershell
$candidateNames = @("candidate-1.json", "candidate-2.json", "candidate-3.json")
$candidateReceipts = @()
foreach ($candidateName in $candidateNames) {
    $candidatePath = Join-Path $starterRoot $candidateName
    $receiptRaw = python -B -m hsconfig.cli starter-validate-candidate --starter-context-json (Join-Path $starterRoot "starter_context.json") --candidate-json $candidatePath --json
    if ($LASTEXITCODE -ne 0) { throw "candidate validator rejected $candidateName" }
    $receipt = $receiptRaw | ConvertFrom-Json
    if (-not $receipt.valid -or -not $receipt.content_sha256 -or -not $receipt.runtime_intent_sha256) {
        throw "candidate validator returned an incomplete receipt for $candidateName"
    }
    $candidateReceipts += $receipt
}
if ($candidateReceipts.Count -ne 3 -or
    (@($candidateReceipts.candidate_id | Sort-Object -Unique)).Count -ne 3 -or
    (@($candidateReceipts.runtime_intent_sha256 | Sort-Object -Unique)).Count -ne 3) {
    throw "the three validated candidates are not materially distinct"
}
```

If one validator fails, return only that candidate to its own strategist and repeat sealing plus this one validator command. Permit at most two repair rounds per candidate. Start a separate clean-context critic agent only after all three receipts are green and distinct; the critic writes only `starter_config_decision.json` and freely ranks all three without a fixed score.

- [ ] **Step 7: Publish and apply the selected live package**

```powershell
python -B -m hsconfig.cli configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --optimized-start --starter-decision-json (Join-Path $starterRoot "starter_config_decision.json") --runtime-root "C:\Users\darbo\Desktop\HS" --out "outputs\ShadowPriest" --online-source --auto-source --apply --json
```

Require success, `LLM_OPTIMIZED_START`, non-empty Mulligan, complete GlobalValues, meaningful CardID/Combo-or-changed-GlobalValues strategy, the exact deck identifiers, and previous-state preservation on any failure.

- [ ] **Step 8: Verify the exact applied revision read-only**

Resolve `outputs\ShadowPriest\current.json` to its immutable package and run:

```powershell
$current = Get-Content -LiteralPath "outputs\ShadowPriest\current.json" -Raw | ConvertFrom-Json
$package = Join-Path -Path "outputs\ShadowPriest" -ChildPath (Join-Path -Path $current.revision -ChildPath "04_package")
python -B -m hsconfig.cli runtime-match --package $package --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Require `status=matched`. This proves install identity only, not gameplay optimality.

After the package reports have bound all five canonical starter documents and runtime match is green, delete only the exact external `$starterRoot` created in Step 6:

```powershell
$starterBound = [IO.Path]::GetFullPath($starterRoot)
$systemTempBound = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)
$starterDeleteItem = Get-Item -LiteralPath $starterBound -Force
if ($starterBound -ine $starterRoot -or
    [IO.Path]::GetDirectoryName($starterBound) -ine $systemTempBound -or
    -not [IO.Path]::GetFileName($starterBound).StartsWith("hsconfig-shadowpriest-starter-", [StringComparison]::Ordinal) -or
    -not $starterDeleteItem.PSIsContainer -or
    ($starterDeleteItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
    $starterDeleteItem.FullName -ine $starterBound) {
    throw "starter cleanup identity or path boundary changed"
}
Remove-Item -LiteralPath $starterBound -Recurse -Force
if (Test-Path -LiteralPath $starterBound) { throw "starter cleanup failed" }
```

Do not delete any repository output or runtime path during this cleanup.

- [ ] **Step 9: Quarantine and remove only the two inactive legacy CustomConfigs**

This step runs only after Step 8 is `matched`. It is a separate recoverable cleanup, not part of package apply. First bind the complete `[Configs]` reference set and a byte inventory of every non-target entry:

```powershell
$runtimeRoot = [IO.Path]::GetFullPath("C:\Users\darbo\Desktop\HS")
$customRoot = [IO.Path]::GetFullPath((Join-Path $runtimeRoot "CustomConfig"))
$customItem = Get-Item -LiteralPath $customRoot -Force
if (-not $customItem.PSIsContainer -or ($customItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "CustomConfig root is not a plain directory"
}
$customRoot = $customItem.FullName.TrimEnd([IO.Path]::DirectorySeparatorChar)
$iniPath = Join-Path $customRoot "deck_config.ini"
$legacyNames = @("aggro", "warrior_pirate")

$iniAuditScript = @'
import configparser
import json
import sys
from pathlib import Path
from hsconfig.deck_config_ini import read_deck_config

path = Path(sys.argv[1])
raw = path.read_bytes()
parser = configparser.RawConfigParser(interpolation=None, strict=True)
parser.optionxform = str
parser.read_string(raw.decode("utf-8-sig"))
matching_sections = [
    section
    for section in parser.sections()
    if section.casefold() == "configs"
]
if len(matching_sections) != 1:
    raise SystemExit("deck_config_ini_configs_section_missing_or_ambiguous")
configs_section = matching_sections[0]
rows = []
seen = set()
for deck_name, config_dir in parser.items(configs_section, raw=True):
    deck_key = deck_name.strip().casefold()
    if not deck_key or deck_key in seen:
        raise SystemExit("deck_config_ini_ambiguous_mapping")
    seen.add(deck_key)
    snapshot = read_deck_config(path, deck_name=deck_name.strip())
    if snapshot.selected_config_dir != config_dir.strip():
        raise SystemExit("deck_config_ini_mapping_drift")
    rows.append({"deck_name": deck_name.strip(), "config_dir": config_dir.strip()})
print(json.dumps({"mappings": rows}, sort_keys=True, separators=(",", ":")))
'@
$iniAuditRaw = python -B -c $iniAuditScript $iniPath
if ($LASTEXITCODE -ne 0) { throw "deck_config.ini reference audit failed" }
$iniAudit = $iniAuditRaw | ConvertFrom-Json
$shadowRows = @($iniAudit.mappings | Where-Object { $_.deck_name -ieq "ShadowPriest" })
if ($shadowRows.Count -ne 1 -or -not $shadowRows[0].config_dir) {
    throw "active ShadowPriest mapping is not unique"
}
$activeShadowPriest = [string]$shadowRows[0].config_dir
$referenced = @($iniAudit.mappings | ForEach-Object { [string]$_.config_dir })
foreach ($legacyName in $legacyNames) {
    if ($legacyName -ieq "default" -or $legacyName -ieq $activeShadowPriest -or $referenced -icontains $legacyName) {
        throw "legacy cleanup target is protected or still referenced: $legacyName"
    }
}

$inventoryScript = @'
import hashlib
import json
import sys
from pathlib import Path
from hsconfig.package_io import snapshot_bounded_filesystem_package

root = Path(sys.argv[1])
excluded = {name.casefold() for name in sys.argv[2:]}
view = snapshot_bounded_filesystem_package(root)
def keep(path: str) -> bool:
    return path.split("/", 1)[0].casefold() not in excluded
document = {
    "directories": [name for name in view.directory_names if keep(name)],
    "files": [
        {
            "path": name,
            "size": len(view.read_bytes(name)),
            "sha256": hashlib.sha256(view.read_bytes(name)).hexdigest(),
        }
        for name in view.file_names()
        if keep(name)
    ],
}
payload = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
print(hashlib.sha256(payload).hexdigest())
'@
$protectedBefore = python -B -c $inventoryScript $customRoot @legacyNames
if ($LASTEXITCODE -ne 0) { throw "pre-cleanup protected inventory failed" }
```

Validate each existing target as an exact direct child plain directory, move it to one validated external quarantine root, and restore it on any failure before the durable success point:

```powershell
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd([IO.Path]::DirectorySeparatorChar)
$quarantineRoot = [IO.Path]::GetFullPath((Join-Path $tempRoot ("hsconfig-customconfig-quarantine-" + [Guid]::NewGuid().ToString("N"))))
if (-not $quarantineRoot.StartsWith($tempRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw "quarantine root escaped the system temp root"
}
New-Item -ItemType Directory -LiteralPath $quarantineRoot | Out-Null
$quarantineItem = Get-Item -LiteralPath $quarantineRoot -Force
if (-not $quarantineItem.PSIsContainer -or ($quarantineItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "quarantine root is not a plain directory"
}

$moved = [Collections.Generic.List[string]]::new()
try {
    foreach ($legacyName in $legacyNames) {
        $source = [IO.Path]::GetFullPath((Join-Path $customRoot $legacyName))
        if ([IO.Path]::GetDirectoryName($source) -ine $customRoot) {
            throw "legacy target is not a direct CustomConfig child: $legacyName"
        }
        if (-not (Test-Path -LiteralPath $source)) { continue }
        $sourceItem = Get-Item -LiteralPath $source -Force
        if (-not $sourceItem.PSIsContainer -or ($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "legacy target is not a plain directory: $legacyName"
        }
        $destination = Join-Path $quarantineRoot $legacyName
        if (Test-Path -LiteralPath $destination) { throw "quarantine collision: $legacyName" }
        Move-Item -LiteralPath $source -Destination $destination
        $moved.Add($legacyName)
    }

    $protectedAfterMove = python -B -c $inventoryScript $customRoot @legacyNames
    if ($LASTEXITCODE -ne 0 -or $protectedAfterMove -ne $protectedBefore) {
        throw "non-target CustomConfig inventory changed"
    }
    $matchAfterCleanupRaw = python -B -m hsconfig.cli runtime-match --package $package --runtime-root $runtimeRoot --json
    if ($LASTEXITCODE -ne 0) { throw "runtime-match failed after legacy quarantine" }
    $matchAfterCleanup = $matchAfterCleanupRaw | ConvertFrom-Json
    if ($matchAfterCleanup.status -ne "matched") { throw "runtime mismatch after legacy quarantine" }

    $quarantineChildren = @(Get-ChildItem -LiteralPath $quarantineRoot -Force)
    if (@($quarantineChildren | Where-Object { $_.Name -notin $moved }).Count -ne 0) {
        throw "quarantine contains an unowned entry"
    }
    Remove-Item -LiteralPath $quarantineRoot -Recurse -Force
    if (Test-Path -LiteralPath $quarantineRoot) { throw "quarantine cleanup failed" }
} catch {
    $primary = $_
    $restoreErrors = @()
    for ($index = $moved.Count - 1; $index -ge 0; $index--) {
        $legacyName = $moved[$index]
        $backup = Join-Path $quarantineRoot $legacyName
        $restore = Join-Path $customRoot $legacyName
        try {
            if (Test-Path -LiteralPath $restore) { throw "restore collision: $legacyName" }
            Move-Item -LiteralPath $backup -Destination $restore
        } catch {
            $restoreErrors += $_.Exception.Message
        }
    }
    if ($restoreErrors.Count -eq 0 -and (Test-Path -LiteralPath $quarantineRoot)) {
        Remove-Item -LiteralPath $quarantineRoot -Force
    }
    if ($restoreErrors.Count -ne 0) {
        throw "legacy cleanup failed and quarantine was retained for recovery: $($restoreErrors -join '; ')"
    }
    throw $primary
}
```

Execute the final postconditions rather than recording them only in prose:

```powershell
foreach ($legacyName in $legacyNames) {
    $legacyPath = [IO.Path]::GetFullPath((Join-Path $customRoot $legacyName))
    if ([IO.Path]::GetDirectoryName($legacyPath) -ine $customRoot -or (Test-Path -LiteralPath $legacyPath)) {
        throw "legacy CustomConfig still exists or escaped its parent: $legacyName"
    }
}

$requiredConfigDirs = @("default") + @($referenced)
foreach ($configDirValue in $requiredConfigDirs) {
    $configDir = [string]$configDirValue
    if (-not $configDir -or [IO.Path]::IsPathRooted($configDir) -or
        $configDir -in @(".", "..") -or $configDir.Contains("/") -or $configDir.Contains("\") -or
        $configDir.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0) {
        throw "referenced config directory is not one safe path component: $configDir"
    }
    $configPath = [IO.Path]::GetFullPath((Join-Path $customRoot $configDir))
    if ([IO.Path]::GetDirectoryName($configPath) -ine $customRoot) {
        throw "referenced config directory escaped CustomConfig: $configDir"
    }
    $configItem = Get-Item -LiteralPath $configPath -Force
    if (-not $configItem.PSIsContainer -or ($configItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "referenced config directory is missing or unsafe: $configDir"
    }
}

$protectedFinal = python -B -c $inventoryScript $customRoot @legacyNames
if ($LASTEXITCODE -ne 0 -or $protectedFinal -ne $protectedBefore) {
    throw "final non-target CustomConfig inventory changed"
}
if (Test-Path -LiteralPath $quarantineRoot) { throw "final quarantine residue remains" }
$finalMatchRaw = python -B -m hsconfig.cli runtime-match --package $package --runtime-root $runtimeRoot --json
if ($LASTEXITCODE -ne 0) { throw "final runtime-match failed" }
$finalMatch = $finalMatchRaw | ConvertFrom-Json
if ($finalMatch.status -ne "matched") { throw "final runtime state is not matched" }
```

If either legacy directory was already absent, record it as already clean; never broaden the target set.

- [ ] **Step 10: Record the practical outcome**

Report the selected candidate ID/digest, critic decision digest, Mulligan rules, changed GlobalValues, emitted CardID/Combo surfaces, operator-summary verdict, published revision, `runtime-match=matched`, and the exact legacy cleanup result (`aggro`/`warrior_pirate` removed or already absent; protected inventory unchanged). State that gameplay quality remains a pre-game LLM judgment and has not been measured in games.

---

## Completion Checklist

- [ ] Repository contains no model SDK/client and no post-run scope.
- [ ] Exactly three distinct candidates and one independent critic decision are required.
- [ ] Fixed sibling names and bounded canonical documents are enforced.
- [ ] Selected candidate is frozen before compilation and no rendered JSON patch exists.
- [ ] All runtime/report/receipt outputs derive from the same selected bytes.
- [ ] Optimized output cannot succeed with empty Mulligan and wholly default-only strategy.
- [ ] `LLM_OPTIMIZED_START` is distinct from source-backed authority and gameplay optimality.
- [ ] Conservative configure behavior remains compatible.
- [ ] Guarded apply is the only live write and failed optimized runs preserve prior state.
- [ ] Installed skill is transactionally updated only after exact-OID CI success.
- [ ] Real ShadowPriest package is freshly generated, applied, and read-only runtime matched.
- [ ] Only inactive, unreferenced `aggro` and `warrior_pirate` are removed through recoverable quarantine; all protected CustomConfig state remains byte-identical.
