# HSConfig ShadowPriest Semantic Closure Wave Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the ShadowPriest package semantically honest and as complete as the documented HearthRanger VisionAI surfaces allow: bind Darkbishop to the deckwide Mind Spike plan, apply source-authorized GlobalValues posture, require exact-deck evidence for guide mulligans, emit only safe per-card behavior, deduplicate runtime rows, and make readiness/reporting reflect physical runtime truth.

**Architecture:** Keep the existing source-document → lifecycle → gameplan → surface compiler → operator-summary pipeline. Move `hero_power_transform` from the physical Darkbishop CardID surface to `GlobalValues.json`, introduce exact deck-code evidence as the only guide authority for exact mulligan promotion, and preserve fail-closed reporting for state-dependent effects that the current condition grammar cannot express. The implementation must not add a second apply gate or a new gameplay simulator.

**Tech Stack:** Python 3.12+, pytest, existing `hsconfig` package, HearthRanger VisionAI JSON surfaces, JSON/Markdown operator reports, PowerShell verification commands.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the single `main` line. Do not create a branch, linked worktree, pull request, or parallel version.
- Before implementation:
  ```powershell
  git fetch --all --prune --tags
  git status --short --branch
  git rev-list --left-right --count main...origin/main
  python scripts/check_hsconfig_currentness.py --cwd . --json
  ```
- Required starting state: clean `main`, `0 0` divergence from `origin/main`, no open pull request.
- Do not use HSTuner.
- Do not add a new dependency.
- Do not add unsupported VisionAI keys or broaden the runtime-condition grammar without public documentation and an explicit test fixture for the exact syntax.
- Preserve the normal runtime surfaces: `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for an exact ordered sequence.
- `reports/operator_summary.json` remains the only normal apply authority.
- `semantic_handoff_status` remains diagnostic and must not become a second apply gate.
- Runtime writes remain possible only through the existing explicit apply path. This plan does not execute `hsconfig apply` or `hsconfig configure --apply`.
- Generated packages, runtime logs, `Power.log`, `.hdtreplay`, `.hsreplay`, HDT exports, caches, and private evidence must not be committed.
- Preserve exact ShadowPriest identity:
  ```text
  Deck name: ShadowPriest
  Deck code: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
  Deck-code SHA-256: fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2
  Card count: 30
  Unique CardIDs: 16
  ```
- A card file containing only `GameCardId` and `ConfigComment` is valid report-only output, not evidence of a meaningful runtime row.
- Exact guide absence is an honest partial result. Do not fabricate `SOURCE_BACKED_STRONG`, exact mulligan authority, conditions, combo timing, or in-client optimality.
- Every behavior-changing implementation task follows RED → GREEN → focused regression → commit. The fixture-only Task 1 must remain green.
- Before each commit, inspect `git diff --check` and the task-specific diff.
- After every commit, push `main` so GitHub and local state remain one version.

---

## Desired Final Contract

For the exact ShadowPriest deck:

- `SW_448.json` contains metadata only. It must not contain `BeforeUseHeroPowerBonus`, `BeforePlayCardBonus`, `InHandPlayPriority`, or a mulligan keep.
- The linked effect `SW_448 Darkbishop Benedictus -> EX1_625t Mind Spike` authorizes a deckwide `MyHeroPowerValue` overlay through `GlobalValues.json`.
- `hero_power_transform` is routed to `globalvalues`, not `cardid`, in the source-contract matrix and lifecycle.
- An exact-deck `aggro_burn` posture authorizes:
  - `FirstTurnValueWeight = 0.75`
  - `SecondTurnValueWeight = 0.25`
  - an increase to `GlobalMinionAttack`
  - an increase to `GlobalMinionIntrinsicValue`
  - an increase to `MyHeroPowerValue`
- A partial/archetype-only guide does not gain exact mulligan authority.
- If no exact-deck guide exists, the package remains load-safe and explicitly partial; policy-backed mulligan rows may still exist, but are not source-strong.
- Safe static per-card runtime rows are limited to semantics that map directly to documented surfaces:
  - direct or reciprocal hero burn → `BeforePlayCardBonus`
  - deployable location → `BeforePlayCardBonus`
  - persistent damage/cost/summon engine → `OnBoardBonus`
  - damage aura may also retain its supported play bonus
- These cards remain report-only until a documented condition exists:
  - `CFM_637` Patches the Pirate
  - `DRG_056` Parachute Brigand
  - `YOD_032` Frenzied Felwing
  - `SCH_514` Raise Dead
  - `SW_444` Twilight Deceptor card-play timing
  - `NX2_019` Mind Sear target-kill timing
  - `VAC_512` Brain Masseuse liability timing
- Identical runtime signatures are emitted once. Signature:
  ```python
  (card_id, behavior_block, condition, value)
  ```
- `runtime_emitted` is derived only from parsed per-card payloads containing at least one non-metadata `values` row.
- Reports distinguish:
  - metadata enrichment complete,
  - runtime semantic closure,
  - load safety,
  - in-client behavior not proven by a pre-run package.
- A current partial-source build and an exact-source fixture build are both tested. Only the exact-source fixture may become `SOURCE_BACKED_STRONG`.

---

## File Map

### Hero-power and GlobalValues ownership

- Modify: `src/hsconfig/source_contract_matrix.py`
  - Change `hero_power_transform` allowed surface from `cardid` to `globalvalues`.
- Modify: `src/hsconfig/source_document_model.py`
  - Route `hero_power_transform` through the GlobalValues gate and update runtime-lowering metadata.
- Modify: `src/hsconfig/card_behavior_surface_router.py`
  - Treat `hero_power_transform` as a dedicated non-CardID claim and remove its CardID intent mapping.
- Modify: `src/hsconfig/semantic_runtime_gate.py`
  - Remove the static Darkbishop-local `BeforeUseHeroPowerBonus` allowance.
- Modify: `src/hsconfig/globalvalues_authority.py`
  - Add linked-hero-power overlay authority and canonical posture aliases.
- Modify: `src/hsconfig/package_builder.py`
  - Pass deckwide effect identity into GlobalValues authority construction.

### Exact-deck source and mulligan authority

- Modify: `src/hsconfig/source_acquisition.py`
  - Detect an exact deck-code hash match and report `exact_deck_matched`.
- Modify: `src/hsconfig/source_evidence_policy.py`
  - Recognize exact match as strongest guide scope.
- Modify: `src/hsconfig/source_autopilot.py`
  - Preserve exact match through autopilot normalization.
- Modify: `src/hsconfig/source_document_model.py`
  - Require exact public-guide evidence for guide-backed `mulligan_keep`.
- Modify: `tests/fixtures/source_pages/shadowpriest_current_guide.html`
  - Make the strong fixture explicitly contain the exact deck code.
- Create: `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`
  - Represent the current real-world failure mode: archetype advice without the exact deck code.

### Safe card mechanics and deduplication

- Modify: `src/hsconfig/card_intent_taxonomy.py`
  - Add `summon_trigger_board_engine`.
- Modify: `src/hsconfig/static_semantics.py`
  - Emit the specific mechanic for persistent summon-trigger engines.
- Modify: `src/hsconfig/mechanic_support.py`
  - Map the new mechanic to `OnBoardBonus`.
- Modify: `src/hsconfig/semantic_runtime_gate.py`
  - Allow the exact safe static pairs for Papercraft and summon-trigger engines.
- Modify: `src/hsconfig/card_behavior_surface_router.py`
  - Deduplicate identical runtime signatures while merging provenance.

### Physical readiness and operator language

- Modify: `src/hsconfig/config_readiness.py`
  - Require a payload mapping and remove filename-only runtime inference.
- Modify: `src/hsconfig/semantic_audit.py`
  - Separate metadata completeness from runtime semantic closure.
- Modify: `src/hsconfig/package_builder.py`
  - Pass readiness into semantic-audit rendering.
- Modify: `src/hsconfig/operator_summary.py`
  - Add a non-gating configuration-assurance projection.
- Modify: `src/hsconfig/operator_guidance.py`
  - Surface the same assurance scope to the operator.

### Tests and documentation

- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_source_contract_spine_freeze.py`
- Modify: `tests/test_globalvalues_authority.py`
- Modify: `tests/test_compile_globalvalues.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_semantic_runtime_gate.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_source_acquisition.py`
- Modify: `tests/test_source_evidence_policy.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_semantic_audit.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_operator_guidance.py`
- Modify: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Create: `tests/test_shadowpriest_partial_source_acceptance.py`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`

---

### Task 1: Add Exact And Partial Source Fixtures

**Files:**
- Create: `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`
- Modify: `tests/fixtures/source_pages/shadowpriest_current_guide.html`
- Modify: `tests/fixtures/source_documents_shadowpriest_strong.json`

**Interfaces:**
- Consumes: existing `hsconfig.cli.main`, exact ShadowPriest deck code, package report layout.
- Produces: two deterministic source inputs:
  - exact-deck source fixture,
  - archetype-only partial source fixture.

- [ ] **Step 1: Add exact deck identity to the strong HTML fixture**

Add this paragraph to `tests/fixtures/source_pages/shadowpriest_current_guide.html` directly below the `<h1>`:

```html
<p>
  Exact deck code:
  AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
</p>
```

- [ ] **Step 2: Create the archetype-only fixture**

Create `tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta property="article:published_time" content="2026-07-15T00:00:00Z">
    <title>Wild Aggro Shadow Priest Archetype Guide 2026</title>
  </head>
  <body>
    <main>
      <h1>Wild Aggro Shadow Priest Archetype Guide 2026</h1>
      <p>
        Shadow Priest is an aggressive burn archetype that uses cheap minions,
        direct damage, and the Shadow hero power to pressure the enemy hero.
      </p>
      <h2>Mulligan</h2>
      <p>Keep Papercraft Angel and Twilight Deceptor.</p>
      <h2>Hero Power</h2>
      <p>
        Darkbishop Benedictus changes the starting Hero Power to Mind Spike.
        This start-of-game effect is not an opening-hand keep.
      </p>
    </main>
  </body>
</html>
```

- [ ] **Step 3: Change the strong package expectations**

In the first guide document of
`tests/fixtures/source_documents_shadowpriest_strong.json`, add:

```json
"deck_match_scope": "exact_deck_matched",
"deck_match": {
  "deck_code_hash_match": true,
  "deck_code_hash": "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
}
```

This is test metadata for the exact-source branch. Do not add the raw deck
code to generated production reports.

- [ ] **Step 4: Verify both fixtures remain schema-compatible**

Run:

```powershell
pytest tests/test_archetype_source_fixtures.py tests/test_source_document_builder.py tests/test_source_acquisition.py -q
```

Expected: all existing tests pass. Task 1 changes only deterministic test inputs.

- [ ] **Step 5: Commit and push**

```powershell
git diff --check
git add tests/fixtures/source_pages/shadowpriest_current_guide.html tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html tests/fixtures/source_documents_shadowpriest_strong.json
git commit -m "test: add exact and partial ShadowPriest sources"
git push origin main
```

---

### Task 2: Move Darkbishop Hero-Power Semantics To GlobalValues

**Files:**
- Modify: `src/hsconfig/source_contract_matrix.py`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_source_contract_spine_freeze.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_semantic_runtime_gate.py`
- Modify: `tests/test_globalvalues_authority.py`
- Modify: `tests/test_compile_globalvalues.py`

**Interfaces:**
- Consumes:
  - `gameplan_contract["deckwide_effects"]`
  - `hero_power_transform` source claims
  - `build_globalvalues_authority_matrix(aggression_profile=..., claims=...)`
- Produces:
  ```python
  build_globalvalues_authority_matrix(
      *,
      aggression_profile: str,
      claims: list[dict[str, Any]],
      deckwide_effects: list[dict[str, Any]] | None = None,
  ) -> dict[str, Any]
  ```
  with a `MyHeroPowerValue` Step1 overlay only when an exact linked transformed Hero Power exists.

- [ ] **Step 1: Write source-contract routing tests**

Add imports for `source_contract_vocabulary_rows` and then add to
`tests/test_source_contract_spine_freeze.py`:

```python
def test_hero_power_transform_owns_globalvalues_not_cardid():
    policy = source_contract_policy_by_claim_kind()["hero_power_transform"]
    vocabulary = {
        row["claim_kind"]: row for row in source_contract_vocabulary_rows()
    }

    assert policy["allowed_surfaces"] == ("globalvalues",)
    assert policy["runtime_lowerable"] is True
    assert vocabulary["hero_power_transform"]["runtime_files"] == (
        "GlobalValues.json",
    )
```

Import `can_lower_to_cardid` and `can_lower_to_globalvalues` from
`hsconfig.source_document_model`, then add to
`tests/test_claim_kind_runtime_contract.py`:

```python
def test_hero_power_transform_lowers_only_to_globalvalues():
    claim = {
        "claim_kind": "hero_power_transform",
        "cards": ["SW_448"],
        "claim_readiness": "source_backed_static_semantics",
        "source_confidence": "medium",
    }

    assert can_lower_to_globalvalues(claim).allowed is True
    assert can_lower_to_cardid(claim).allowed is False
```

- [ ] **Step 2: Write GlobalValues identity tests**

Add to `tests/test_globalvalues_authority.py`:

```python
def test_linked_hero_power_transform_authorizes_deckwide_value_overlay():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_id": "claim-darkbishop-transform",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "claim_readiness": "source_backed_static_semantics",
                "source_confidence": "medium",
                "source_refs": ["hearthstonejson_static_semantics"],
            }
        ],
        deckwide_effects=[
            {
                "source_card_id": "SW_448",
                "effect": "replace_starting_hero_power",
                "target_card_id": "EX1_625t",
                "target_name": "Mind Spike",
            }
        ],
    )

    hero_power_rows = [
        row
        for row in matrix["allowed_step1_overlays"]
        if row["key"] == "MyHeroPowerValue"
    ]
    assert len(hero_power_rows) == 1
    assert hero_power_rows[0]["operation"] == "increase"
    assert hero_power_rows[0]["claim_id"] == "claim-darkbishop-transform"
    assert hero_power_rows[0]["reason"] == "linked_hero_power_transform"
```

Add the fail-closed companion:

```python
def test_unlinked_hero_power_transform_does_not_authorize_runtime_overlay():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_id": "claim-unlinked-transform",
                "claim_kind": "hero_power_transform",
                "cards": ["UNKNOWN_001"],
                "claim_readiness": "source_backed_static_semantics",
                "source_confidence": "medium",
            }
        ],
        deckwide_effects=[],
    )

    assert [
        row
        for row in matrix["allowed_step1_overlays"]
        if row["key"] == "MyHeroPowerValue"
    ] == []
```

- [ ] **Step 3: Verify RED**

```powershell
pytest tests/test_source_contract_spine_freeze.py tests/test_claim_kind_runtime_contract.py tests/test_globalvalues_authority.py -q
```

Expected: the claim still routes to CardID and the authority builder does not accept `deckwide_effects`.

- [ ] **Step 4: Change source-surface ownership**

In `src/hsconfig/source_contract_matrix.py`, change the `hero_power_transform` policy to:

```python
"hero_power_transform": {
    "lane": "runtime_lowerable",
    "allowed_surfaces": ("globalvalues",),
    "operator_meaning": (
        "Preserve the exact linked hero-power transform through deckwide "
        "GlobalValues posture; it is neither a card-body action nor a mulligan keep."
    ),
},
```

Change its `_POLICY_DETAILS` default suppression reason to:

```python
"claim_kind_not_globalvalues_surface"
```

In `src/hsconfig/source_document_model.py`:

```python
GLOBALVALUES_SURFACE_CLAIM_KINDS = frozenset(
    {"gameplan_posture", "hero_power_transform"}
)
```

Remove `hero_power_transform` from `CARDID_SURFACE_CLAIM_KINDS`. Update `_runtime_lowering()` so:

```python
if claim_kind in {"gameplan_posture", "hero_power_transform"}:
    return "globalvalues_or_contract_only"
```

- [ ] **Step 5: Remove the Darkbishop-local route**

In `src/hsconfig/card_behavior_surface_router.py`:

- Remove `"hero_power_transform": "BeforeUseHeroPowerBonus"` from `INTENT_BLOCKS`.
- Add `"hero_power_transform"` to `_belongs_to_dedicated_non_cardid_surface()`.

In `src/hsconfig/semantic_runtime_gate.py`, remove the `hero_power_transform` entry from `STATIC_ACTION_SURFACES`.

Update `tests/test_card_behavior_router.py`:

```python
def test_hero_power_transform_is_not_a_cardid_action():
    report = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim-darkbishop",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "claim_readiness": "source_backed_static_semantics",
                "source_confidence": "medium",
                "source_refs": ["hearthstonejson_static_semantics"],
            }
        ]
    )

    assert report["rows"] == []
    assert report["suppressed"] == []
```

Remove `hero_power_transform` from the supported static CardID parameter set in `tests/test_semantic_runtime_gate.py`.

- [ ] **Step 6: Implement linked GlobalValues authority**

Change the function signature in `src/hsconfig/globalvalues_authority.py`:

```python
def build_globalvalues_authority_matrix(
    *,
    aggression_profile: str,
    claims: list[dict[str, Any]],
    deckwide_effects: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
```

Add:

```python
def _linked_hero_power_transform_claim(
    claims: list[dict[str, Any]],
    deckwide_effects: list[dict[str, Any]],
) -> dict[str, Any] | None:
    transformed_source_ids = {
        str(effect.get("source_card_id"))
        for effect in deckwide_effects
        if effect.get("effect") == "replace_starting_hero_power"
        and str(effect.get("target_card_id", "")).strip()
    }
    for claim in claims:
        if normalized_claim_kind(claim) != "hero_power_transform":
            continue
        claim_cards = {
            str(card_id)
            for card_id in claim.get("cards", [])
            if str(card_id)
        }
        if claim_cards & transformed_source_ids:
            return claim
    return None
```

After posture rows are built, append or merge:

```python
transform_claim = _linked_hero_power_transform_claim(
    lowerable_claims,
    list(deckwide_effects or []),
)
if transform_claim is not None:
    transform_row = _allowed_row(
        key="MyHeroPowerValue",
        operation="increase",
        value=None,
        reason="linked_hero_power_transform",
        claim_refs=_claim_refs([transform_claim]),
        claim_id=lifecycle_claim_id(transform_claim),
    )
    allowed = _merge_allowed_overlay_rows([*allowed, transform_row])
```

Implement `_merge_allowed_overlay_rows()` so a duplicate key/operation/value keeps one row and merges `claim_refs` in stable order.

- [ ] **Step 7: Thread deckwide effects from package builder**

In `src/hsconfig/package_builder.py`:

```python
global_values_authority_matrix = build_globalvalues_authority_matrix(
    aggression_profile=str(
        gameplan_contract.get("aggression_profile", {}).get("speed", "balanced")
    ),
    claims=globalvalues_authority_claims,
    deckwide_effects=list(gameplan_contract.get("deckwide_effects", [])),
)
```

- [ ] **Step 8: Update the package-level Darkbishop assertions**

In `tests/test_shadowpriest_visionai_semantic_surface_contract.py`, replace
the Darkbishop-local expectation with:

```python
darkbishop = read_card_json(package_root, "SW_448")
globalvalues = read_card_json(package_root, "GlobalValues")

assert set(darkbishop) == {"GameCardId", "ConfigComment"}
assert globalvalues["MyHeroPowerValue"]["values"] == [
    {"condition": "*", "value": "1.15"}
]
```

In `tests/test_shadowpriest_semantic_safety_wave.py`, replace
`test_darkbishop_effect_does_not_become_mulligan_or_body_priority` with:

```python
def test_darkbishop_effect_is_deckwide_not_card_local(package):
    mulligan = _card(package, "Mulligan")
    darkbishop = _card(package, "SW_448")
    globalvalues = _card(package, "GlobalValues")

    selectors = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold"
    ]
    assert "SW_448" not in selectors
    assert set(darkbishop) == {"GameCardId", "ConfigComment"}
    assert globalvalues["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
```

- [ ] **Step 9: Verify GREEN**

```powershell
pytest tests/test_source_contract_spine_freeze.py tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py tests/test_semantic_runtime_gate.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py -q
```

Expected: all pass; `SW_448.json` is metadata-only and `MyHeroPowerValue` becomes `1.15`.

- [ ] **Step 10: Commit and push**

```powershell
git diff --check
git add src/hsconfig/source_contract_matrix.py src/hsconfig/source_document_model.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/semantic_runtime_gate.py src/hsconfig/globalvalues_authority.py src/hsconfig/package_builder.py tests/test_source_contract_spine_freeze.py tests/test_claim_kind_runtime_contract.py tests/test_card_behavior_router.py tests/test_semantic_runtime_gate.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_shadowpriest_visionai_semantic_surface_contract.py tests/test_shadowpriest_semantic_safety_wave.py
git commit -m "fix: bind hero power transform to GlobalValues"
git push origin main
```

---

### Task 3: Require Exact Deck Evidence For Guide Mulligans

**Files:**
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `tests/test_source_acquisition.py`
- Modify: `tests/test_source_evidence_policy.py`
- Modify: `tests/test_source_autopilot.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Create: `tests/test_shadowpriest_partial_source_acceptance.py`

**Interfaces:**
- Consumes:
  - `deck_identity["deck_code_hash"]`
  - normalized source text
  - guide claim `deck_match_scope`
- Produces:
  ```python
  deck_match["deck_code_hash_match"]: bool
  deck_match_scope: "exact_deck_matched" | "archetype_matched" | "card_overlap" | "unknown"
  ```

- [ ] **Step 1: Write exact-match acquisition tests**

Add to `tests/test_source_acquisition.py`:

```python
def test_exact_deck_code_promotes_source_scope_to_exact_match():
    identity = {
        "deck_code_hash": (
            "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
        ),
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus"},
            {"card_id": "TOY_381", "name": "Papercraft Angel"},
        ],
    }
    text = (
        "ShadowPriest guide "
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
        "KgG17oG1cEGAAA="
    )

    match, scope = _deck_match_evidence(
        "ShadowPriest",
        identity,
        "ShadowPriest guide",
        text,
    )

    assert scope == "exact_deck_matched"
    assert match["deck_code_hash_match"] is True
```

Add:

```python
def test_card_overlap_without_exact_code_stays_archetype_matched():
    identity = {
        "deck_code_hash": (
            "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
        ),
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus"},
            {"card_id": "TOY_381", "name": "Papercraft Angel"},
        ],
    }

    match, scope = _deck_match_evidence(
        "ShadowPriest",
        identity,
        "ShadowPriest guide",
        "ShadowPriest uses Darkbishop Benedictus and Papercraft Angel.",
    )

    assert scope == "archetype_matched"
    assert match["deck_code_hash_match"] is False
```

- [ ] **Step 2: Write mulligan surface-gate tests**

Import `can_lower_to_mulligan` from `hsconfig.source_document_model`, then add
to `tests/test_claim_kind_runtime_contract.py`:

```python
def test_archetype_only_public_guide_cannot_lower_exact_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_381"],
        "claim_readiness": "guide_backed",
        "source_confidence": "high",
        "source_family": "guide",
        "deck_match_scope": "archetype_matched",
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == "mulligan_keep_requires_exact_deck_match"
```

Add:

```python
def test_exact_deck_public_guide_can_lower_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_381"],
        "claim_readiness": "guide_backed",
        "source_confidence": "high",
        "source_family": "guide",
        "deck_match_scope": "exact_deck_matched",
    }

    assert can_lower_to_mulligan(claim).allowed is True
```

- [ ] **Step 3: Verify RED**

```powershell
pytest tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py -q
```

- [ ] **Step 4: Implement hash-only exact identity detection**

In `src/hsconfig/source_acquisition.py`, add:

```python
DECK_CODE_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{40,}={0,2})(?![A-Za-z0-9+/=])"
)


def _has_exact_deck_code_match(text: str, expected_hash: str) -> bool:
    normalized_hash = str(expected_hash).removeprefix("sha256:").strip().lower()
    if not normalized_hash:
        return False
    return any(
        hashlib.sha256(candidate.encode("utf-8")).hexdigest() == normalized_hash
        for candidate in DECK_CODE_CANDIDATE_RE.findall(text)
    )
```

Import `hashlib`. In `_deck_match_evidence()`:

```python
deck_code_hash_match = _has_exact_deck_code_match(
    f"{title} {text}",
    str(deck_identity.get("deck_code_hash", "")),
)
if deck_code_hash_match:
    scope = "exact_deck_matched"
elif deck_name_evidenced and len(matched_unique) >= 2:
    scope = "archetype_matched"
elif matched_unique:
    scope = "card_overlap"
else:
    scope = "unknown"
```

Add `"deck_code_hash_match": deck_code_hash_match` to `deck_match`.

In `_source_record_strength()`, treat the exact scope as the strongest current
guide shape:

```python
and deck_match_scope in {"exact_deck_matched", "deck_matched"}
```

- [ ] **Step 5: Preserve exact scope through evidence policy**

In `src/hsconfig/source_evidence_policy.py`, include `exact_deck_matched` wherever current/strong guide scope is accepted:

```python
STRONG_DECK_SCOPES = {
    "exact_deck_matched",
    "deck_matched",
    "deck_or_archetype_matched",
}
```

Use `STRONG_DECK_SCOPES` in `_source_rank_lane()`, `_source_lane()`, and `_promotion_blockers()`.

In `src/hsconfig/source_autopilot.py`:

- Preserve an explicit `exact_deck_matched`.
- Change the quantitative helper to:

```python
def _quantitative_deck_match_scope(
    *,
    deck_name_match: bool,
    card_overlap: int,
    unique_deck_card_count: int,
    deck_code_hash_match: bool = False,
) -> str:
    if deck_code_hash_match:
        return "exact_deck_matched"
    overlap_ratio = (
        card_overlap / unique_deck_card_count
        if unique_deck_card_count
        else 0.0
    )
    if deck_name_match and overlap_ratio >= 0.80:
        return "deck_matched"
    if deck_name_match and card_overlap >= 2:
        return "archetype_matched"
    if card_overlap:
        return "card_overlap"
    return "unknown"
```

- Pass `bool(match.get("deck_code_hash_match"))` at every call site.
- Do not upgrade archetype overlap to exact scope.

- [ ] **Step 6: Gate guide-backed mulligan keeps**

In `src/hsconfig/source_document_model.py`, add:

```python
def _is_public_guide_claim(claim: Mapping[str, Any]) -> bool:
    source_family = _normalized_text(
        claim.get("source_family") or claim.get("source_type")
    )
    return source_family in PUBLIC_GUIDE_SOURCE_FAMILIES
```

Include `exact_deck_matched` in the public-guide scope sets used by
`_source_lane()` and `_strong_promotion_eligible()`, so the exact source keeps
the canonical `deck_matched_public_guide` lane.

In `can_lower_to_mulligan()` before the start-of-game check:

```python
if (
    claim_kind == "mulligan_keep"
    and _is_public_guide_claim(claim)
    and _normalized_text(claim.get("deck_match_scope")) != "exact_deck_matched"
):
    return SurfaceGateDecision(
        False,
        "mulligan_keep_requires_exact_deck_match",
        claim_kind,
        "mulligan",
    )
```

This must not block policy-backed rows generated by `build_policy_backed_mulligan_rules()`.

- [ ] **Step 7: Verify GREEN**

```powershell
pytest tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py -q
```

Expected:

- exact unit fixture: exact scope is preserved,
- archetype unit fixture: scope remains partial,
- archetype-only guide keeps fail the exact Mulligan surface gate.

- [ ] **Step 8: Add exact and partial package acceptance**

In `tests/test_shadowpriest_source_contract_acceptance.py`, assert:

```python
assert acquisition["records"][0]["deck_match_scope"] == "exact_deck_matched"
assert acquisition["records"][0]["deck_match"]["deck_code_hash_match"] is True
```

Create `tests/test_shadowpriest_partial_source_acceptance.py` using the
fixture-map and `_stub_empty_fetches()` pattern from the exact-source test,
but map the source URL to
`tests/fixtures/source_pages/shadowpriest_archetype_only_guide.html`. Assert:

```python
assert acquisition["records"][0]["deck_match_scope"] == "archetype_matched"
assert acquisition["records"][0]["promotion_eligible"] is False
assert operator["technical_status"] == "VALID_PACKAGE"
assert operator["runtime_apply_allowed"] is True
assert operator["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
assert operator["source_status_apply_blocking"] is False
assert operator["semantic_handoff_status"] in {"attention", "insufficient_evidence"}

guide_keep_claims = [
    claim
    for document in source_documents["source_documents"]
    for claim in document.get("claims", [])
    if claim.get("claim_kind") == "mulligan_keep"
]
assert guide_keep_claims
assert all(
    claim["deck_match_scope"] == "archetype_matched"
    for claim in guide_keep_claims
)

holds = {
    row["mulligan"]
    for row in mulligan["Mulligan"]["values"]
    if row["value"] == "hold"
}
assert "SW_448" not in holds
assert operator["mulligan_policy_status"]["status"] != "guide_backed"
```

Run:

```powershell
pytest tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py -q
```

- [ ] **Step 9: Commit and push**

```powershell
git diff --check
git add src/hsconfig/source_acquisition.py src/hsconfig/source_evidence_policy.py src/hsconfig/source_autopilot.py src/hsconfig/source_document_model.py tests/test_source_acquisition.py tests/test_source_evidence_policy.py tests/test_source_autopilot.py tests/test_claim_kind_runtime_contract.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
git commit -m "fix: require exact deck evidence for mulligan guides"
git push origin main
```

---

### Task 4: Apply Source-Authorized Aggro GlobalValues Posture

**Files:**
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `tests/test_globalvalues_authority.py`
- Modify: `tests/test_compile_globalvalues.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Modify: `tests/test_shadowpriest_partial_source_acceptance.py`

**Interfaces:**
- Consumes: `gameplan_posture.stance`.
- Produces canonical posture:
  ```python
  "aggressive_burn_pressure" -> "aggro_burn"
  "aggro_burn_pressure" -> "aggro_burn"
  "aggressive_burn" -> "aggro_burn"
  ```

- [ ] **Step 1: Write posture-alias tests**

Add to `tests/test_globalvalues_authority.py`:

```python
@pytest.mark.parametrize(
    "stance",
    [
        "aggro_burn",
        "aggressive_burn",
        "aggro_burn_pressure",
        "aggressive_burn_pressure",
        "aggro_burn_hero_power_transform",
    ],
)
def test_aggro_burn_posture_aliases_emit_same_step1_overlays(stance):
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_id": "claim-aggro-burn",
                "claim_kind": "gameplan_posture",
                "stance": stance,
                "claim_readiness": "guide_backed",
                "source_confidence": "high",
                "source_refs": ["https://example.test/exact-shadowpriest"],
            }
        ],
        deckwide_effects=[],
    )

    rows = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
    assert rows["FirstTurnValueWeight"]["value"] == "0.75"
    assert rows["SecondTurnValueWeight"]["value"] == "0.25"
    assert rows["GlobalMinionAttack"]["operation"] == "increase"
    assert rows["GlobalMinionIntrinsicValue"]["operation"] == "increase"
    assert rows["MyHeroPowerValue"]["operation"] == "increase"
```

Add a non-aggro fail-closed test:

```python
def test_draw_engine_plan_does_not_silently_become_aggro_numeric_posture():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_id": "claim-draw-engine",
                "claim_kind": "gameplan_posture",
                "stance": "draw_engine_plan",
                "claim_readiness": "guide_backed",
                "source_confidence": "high",
            }
        ],
        deckwide_effects=[],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["key"] == "baseline"
```

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py -q
```

- [ ] **Step 3: Add explicit aliases**

In `src/hsconfig/globalvalues_authority.py`:

```python
POSTURE_ALIASES = {
    "aggressive": "aggro",
    "tempo": "aggro",
    "aggressive_burn": "aggro_burn",
    "aggro_burn_pressure": "aggro_burn",
    "aggressive_burn_pressure": "aggro_burn",
    "aggro_burn_hero_power_transform": "aggro_burn",
}
```

Do not map `draw_engine_plan` or a generic `pressure` token to `aggro_burn`.

- [ ] **Step 4: Assert exact generated values**

In `tests/test_compile_globalvalues.py`, add:

```python
def test_aggro_burn_authority_compiles_exact_turn_weights_and_hero_power_value():
    result = compile_globalvalues(
        baseline={
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1.0"}]},
            "GlobalMinionAttack": {"values": [{"condition": "*", "value": "0.81"}]},
            "GlobalMinionIntrinsicValue": {
                "values": [{"condition": "*", "value": "3.32 + 2"}]
            },
        },
        contract={
            "aggression_profile": {
                "global_value_overlays": {
                    "FirstTurnValueWeight": "set:0.75",
                    "SecondTurnValueWeight": "set:0.25",
                    "GlobalMinionAttack": "increase",
                    "GlobalMinionIntrinsicValue": "increase",
                    "MyHeroPowerValue": "increase",
                }
            },
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "FirstTurnValueWeight",
                        "operation": "set",
                        "value": "0.75",
                        "reason": "aggro_burn_prioritizes_early_damage",
                    },
                    {
                        "key": "SecondTurnValueWeight",
                        "operation": "set",
                        "value": "0.25",
                        "reason": "aggro_burn_prioritizes_early_damage",
                    },
                    {
                        "key": "MyHeroPowerValue",
                        "operation": "increase",
                        "value": None,
                        "reason": "linked_hero_power_transform",
                    },
                ]
            },
        },
    )

    assert result["config"]["FirstTurnValueWeight"]["values"][0]["value"] == "0.75"
    assert result["config"]["SecondTurnValueWeight"]["values"][0]["value"] == "0.25"
    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
```

- [ ] **Step 5: Update package-level posture assertions**

In the exact source acceptance test:

```python
assert globalvalues["FirstTurnValueWeight"]["values"][0]["value"] == "0.75"
assert globalvalues["SecondTurnValueWeight"]["values"][0]["value"] == "0.25"
assert globalvalues["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
```

In the archetype-only partial acceptance test:

```python
assert globalvalues["FirstTurnValueWeight"]["values"][0]["value"] == "0"
assert globalvalues["SecondTurnValueWeight"]["values"][0]["value"] == "1.0"
assert globalvalues["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
```

The partial build keeps baseline turn weights because the live guide claim says `draw_engine_plan`, but it still receives the static linked Mind Spike overlay.

- [ ] **Step 6: Verify GREEN**

```powershell
pytest tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py -q
```

- [ ] **Step 7: Commit and push**

```powershell
git diff --check
git add src/hsconfig/globalvalues_authority.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
git commit -m "feat: compile source-authorized aggro posture"
git push origin main
```

---

### Task 5: Close Only The Safe Persistent Card Mechanics

**Files:**
- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/static_semantics.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Modify: `tests/test_card_intent_taxonomy.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_mechanic_support.py`
- Modify: `tests/test_semantic_runtime_gate.py`

**Interfaces:**
- Consumes: exact static card text.
- Produces:
  ```python
  CardIntentClassification(
      reason="summon_trigger_board_engine",
      value="8",
      band="medium",
  )
  ```
  and `OnBoardBonus` for persistent summon-trigger engines.

- [ ] **Step 1: Write taxonomy tests**

Add to `tests/test_card_intent_taxonomy.py`:

```python
@pytest.mark.parametrize(
    ("card_id", "text"),
    [
        ("WON_065", "After you summon a minion, give it +1 Health."),
        ("TOY_518", "After you summon a Pirate, give it +1 Attack."),
    ],
)
def test_persistent_summon_trigger_engines_get_precise_intent(card_id, text):
    result = classify_card_intent(text, card_identity=card_id)

    assert result.reason == "summon_trigger_board_engine"
    assert result.value == "8"
    assert result.band == "medium"
```

Add a boundary:

```python
def test_one_shot_summon_text_is_not_a_persistent_board_engine():
    result = classify_card_intent(
        "Battlecry: Summon a 1/1 Pirate.",
        card_identity="TEST_001",
    )

    assert result.reason != "summon_trigger_board_engine"
```

- [ ] **Step 2: Write safe-router tests**

Add to `tests/test_card_behavior_router.py`:

```python
@pytest.mark.parametrize(
    ("card_id", "mechanic", "text", "expected_value"),
    [
        ("TOY_381", "aura", "Your Hero Power costs (0).", "8"),
        (
            "WON_065",
            "summon_trigger_board_engine",
            "After you summon a minion, give it +1 Health.",
            "8",
        ),
        (
            "TOY_518",
            "summon_trigger_board_engine",
            "After you summon a Pirate, give it +1 Attack.",
            "8",
        ),
    ],
)
def test_safe_persistent_engines_route_to_on_board_bonus(
    card_id,
    mechanic,
    text,
    expected_value,
):
    report = route_card_behavior_surfaces(
        [
            {
                "claim_id": f"claim-{card_id}",
                "claim_kind": "mechanic_usage",
                "cards": [card_id],
                "mechanic": mechanic,
                "evidence_text_short": text,
                "claim_readiness": "source_backed_static_semantics",
                "source_confidence": "medium",
                "source_refs": ["hearthstonejson_static_semantics"],
            }
        ]
    )

    assert report["suppressed"] == []
    assert len(report["rows"]) == 1
    assert report["rows"][0]["behavior_block"] == "OnBoardBonus"
    assert report["rows"][0]["value"] == expected_value
```

- [ ] **Step 3: Preserve risky report-only boundaries**

Add:

```python
@pytest.mark.parametrize(
    ("card_id", "mechanic", "text"),
    [
        (
            "SCH_514",
            "damage",
            "Deal 3 damage to your hero. Return two friendly minions that died this game.",
        ),
        (
            "YOD_032",
            "damage",
            "Costs (1) less for each damage dealt to your opponent this turn.",
        ),
        (
            "NX2_019",
            "damage",
            "Deal 2 damage to a minion. If it dies, deal 3 damage to the enemy hero.",
        ),
    ],
)
def test_state_dependent_static_cards_remain_report_only(card_id, mechanic, text):
    report = route_card_behavior_surfaces(
        [
            {
                "claim_id": f"claim-{card_id}",
                "claim_kind": "mechanic_usage",
                "cards": [card_id],
                "mechanic": mechanic,
                "evidence_text_short": text,
                "claim_readiness": "source_backed_static_semantics",
                "source_confidence": "medium",
                "source_refs": ["hearthstonejson_static_semantics"],
            }
        ]
    )

    assert report["rows"] == []
    assert report["suppressed"][0]["reason"] == "semantic_surface_not_expressible"
```

- [ ] **Step 4: Verify RED**

```powershell
pytest tests/test_card_intent_taxonomy.py tests/test_card_behavior_router.py tests/test_mechanic_support.py tests/test_semantic_runtime_gate.py -q
```

- [ ] **Step 5: Add the precise semantic reason**

In `src/hsconfig/card_intent_taxonomy.py`, insert before generic `board_tempo`:

```python
if _has_summon_trigger_board_engine(normalized):
    return CardIntentClassification(
        reason="summon_trigger_board_engine",
        value="8",
        band="medium",
        matched_signals=_signals(
            ("after_you_summon", "after you summon" in normalized),
            ("persistent_buff", "give it +" in normalized),
        ),
    )
```

Add:

```python
def _has_summon_trigger_board_engine(text: str) -> bool:
    return (
        "after you summon" in text
        and "give it +" in text
        and "battlecry:" not in text
    )
```

- [ ] **Step 6: Emit the precise mechanic from static semantics**

In `src/hsconfig/static_semantics.py`, when the exact text matches `_has_summon_trigger_board_engine`, add `summon_trigger_board_engine` to semantic/mechanic families in addition to retaining the general `summon` metadata family. The generated source claim used for runtime lowering must set:

```python
"mechanic": "summon_trigger_board_engine"
```

Do not emit a second generic `summon` runtime-candidate claim for the same
text. Keep `summon` only in metadata/evidence so the precise engine claim is
the single surface candidate. Do not rewrite unrelated `summon` claims.

- [ ] **Step 7: Register safe runtime support**

In `src/hsconfig/mechanic_support.py`:

```python
"summon_trigger_board_engine": {
    "support_level": "partial",
    "normal_path_surfaces": ["CARDID.json:OnBoardBonus"],
    "warning_boundary": (
        "The persistent engine can be preserved on board; individual summon "
        "ordering and generated target value remain broader bot evaluation."
    ),
},
```

In `src/hsconfig/semantic_runtime_gate.py`:

```python
"summon_trigger_board_engine": {
    ("OnBoardBonus", "mechanic_usage", "*"),
},
```

Extend `hero_power_cost_aura` with:

```python
("OnBoardBonus", "mechanic_usage", "*"),
```

Keep the existing report-only set for conditional draw, conditional cost reduction, conditional self-damage resource, conditional target-kill burn, automatic summons, liability bodies, and location activation.

- [ ] **Step 8: Add package-level persistent-engine assertions**

In `tests/test_shadowpriest_visionai_semantic_surface_contract.py`, add:

```python
papercraft = read_card_json(package_root, "TOY_381")
chirurgeon = read_card_json(package_root, "WON_065")
distributor = read_card_json(package_root, "TOY_518")

assert [
    (row["condition"], row["value"])
    for row in papercraft["OnBoardBonus"]["values"]
] == [("*", "8")]
assert [
    (row["condition"], row["value"])
    for row in chirurgeon["OnBoardBonus"]["values"]
] == [("*", "8")]
assert [
    (row["condition"], row["value"])
    for row in distributor["OnBoardBonus"]["values"]
] == [("*", "8")]
```

- [ ] **Step 9: Verify GREEN**

```powershell
pytest tests/test_card_intent_taxonomy.py tests/test_card_behavior_router.py tests/test_mechanic_support.py tests/test_semantic_runtime_gate.py -q
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py tests/test_shadowpriest_semantic_safety_wave.py -q
```

- [ ] **Step 10: Commit and push**

```powershell
git diff --check
git add src/hsconfig/card_intent_taxonomy.py src/hsconfig/static_semantics.py src/hsconfig/mechanic_support.py src/hsconfig/semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_card_behavior_router.py tests/test_mechanic_support.py tests/test_semantic_runtime_gate.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
git commit -m "feat: lower safe persistent card engines"
git push origin main
```

---

### Task 6: Deduplicate Runtime Rows And Harden Physical Readiness

**Files:**
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_compile_cardid.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`

**Interfaces:**
- Produces:
  ```python
  _dedupe_runtime_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]
  ```
  keyed by `(card_id, behavior_block, condition, value)`.
- Changes:
  ```python
  build_config_readiness_report(
      *,
      ...,
      emitted_cardid_files: Mapping[str, Any],
  ) -> dict[str, Any]
  ```
  with no filename-only compatibility path.

- [ ] **Step 1: Write row-deduplication tests**

Import `_dedupe_runtime_rows` beside `route_card_behavior_surfaces`, then add
to `tests/test_card_behavior_router.py`:

```python
def test_identical_runtime_signatures_merge_provenance_once():
    claims = [
        {
            "claim_id": "claim-damage",
            "claim_kind": "mechanic_usage",
            "cards": ["GVG_009"],
            "mechanic": "damage",
            "evidence_text_short": "Deal 3 damage to each hero.",
            "claim_readiness": "source_backed_static_semantics",
            "source_confidence": "medium",
            "source_refs": ["card-text"],
        },
        {
            "claim_id": "claim-battlecry",
            "claim_kind": "mechanic_usage",
            "cards": ["GVG_009"],
            "mechanic": "battlecry",
            "evidence_text_short": "Battlecry: Deal 3 damage to each hero.",
            "runtime_block": "BeforePlayCardBonus",
            "runtime_value": "10",
            "claim_readiness": "source_backed_static_semantics",
            "source_confidence": "medium",
            "source_refs": ["mechanic-tag"],
        },
    ]

    report = route_card_behavior_surfaces(claims)
    rows = [
        row
        for row in report["rows"]
        if row["card_id"] == "GVG_009"
        and row["behavior_block"] == "BeforePlayCardBonus"
        and row["condition"] == "*"
        and row["value"] == "10"
    ]

    assert len(rows) == 1
    assert rows[0]["source_claim_ids"] == ["claim-damage", "claim-battlecry"]
    assert rows[0]["source_refs"] == ["card-text", "mechanic-tag"]
    assert rows[0]["merged_runtime_row_count"] == 2
```

Add:

```python
def test_different_runtime_values_do_not_merge():
    rows = [
        {
            "card_id": "GVG_009",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "8",
            "source_claim_ids": ["claim-eight"],
            "source_refs": ["source-eight"],
        },
        {
            "card_id": "GVG_009",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "10",
            "source_claim_ids": ["claim-ten"],
            "source_refs": ["source-ten"],
        },
    ]

    assert len(_dedupe_runtime_rows(rows)) == 2
```

- [ ] **Step 2: Write readiness API rejection tests**

Add `import pytest` and
`from collections.abc import Mapping` to
`tests/test_config_readiness.py`. Add this payload helper:

```python
def _effect_payloads(*filenames: str) -> dict[str, dict]:
    return {
        filename: {
            "GameCardId": filename.removesuffix(".json"),
            "BeforePlayCardBonus": {
                "values": [{"condition": "*", "value": "6"}]
            },
        }
        for filename in filenames
    }
```

Change `_report_for_card()` to accept
`emitted_cardid_files: Mapping[str, object] | None = None` and pass
`emitted_cardid_files or {}` to `build_config_readiness_report()`. Add
`emitted_cardid_files={}` to `_two_card_readiness_report()`.

Replace filename-only success inputs such as
`["CFM_637.json"]` with `_effect_payloads("CFM_637.json")`. Use an explicit
metadata-only payload in tests that prove report-only behavior.

Add:

```python
@pytest.mark.parametrize(
    "emitted_cardid_files",
    [None, ["EX1_001.json"], ("EX1_001.json",), {"EX1_001.json"}],
)
def test_readiness_requires_payload_mapping(emitted_cardid_files):
    with pytest.raises(TypeError, match="emitted_cardid_files must be a mapping"):
        build_config_readiness_report(
            deck_identity=_one_card_identity("EX1_001"),
            claim_coverage=_covered_claims("EX1_001", "guide_backed"),
            gameplan_contract={
                "cards": {
                    "EX1_001": {
                        "card_id": "EX1_001",
                        "name": "EX1_001",
                        "roles": ["pressure"],
                        "source_claim_ids": ["claim-ex1"],
                    }
                }
            },
            mulligan_plan={"rules": []},
            card_behavior_plan={"rows": []},
            combo_plan={"combos": []},
            global_values_authority_matrix={"allowed_step1_overlays": []},
            emitted_cardid_files=emitted_cardid_files,
        )
```

Add:

```python
def test_metadata_only_payload_is_not_runtime_emitted():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("EX1_001"),
        claim_coverage=_covered_claims("EX1_001", "guide_backed"),
        gameplan_contract={
            "cards": {
                "EX1_001": {
                    "card_id": "EX1_001",
                    "name": "EX1_001",
                    "roles": ["pressure"],
                    "source_claim_ids": ["claim-ex1"],
                }
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files={
            "EX1_001.json": {
                "GameCardId": "EX1_001",
                "ConfigComment": "metadata only",
            }
        },
    )

    assert report["summary"]["runtime_emitted"] == 0
```

- [ ] **Step 3: Verify RED**

```powershell
pytest tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_compile_cardid.py -q
```

- [ ] **Step 4: Implement stable deduplication**

In `src/hsconfig/card_behavior_surface_router.py`, change the return to:

```python
return {
    "rows": _dedupe_runtime_rows(rows),
    "suppressed": suppressed,
    "option_resolution": option_resolution,
}
```

Add:

```python
def _dedupe_runtime_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    order: list[tuple[str, str, str, str]] = []
    for row in rows:
        signature = (
            str(row.get("card_id", "")),
            str(row.get("behavior_block", "")),
            str(row.get("condition", "")),
            str(row.get("value", "")),
        )
        existing = merged.get(signature)
        if existing is None:
            copied = dict(row)
            copied["source_claim_ids"] = list(
                dict.fromkeys(str(item) for item in row.get("source_claim_ids", []))
            )
            copied["source_refs"] = list(
                dict.fromkeys(str(item) for item in row.get("source_refs", []))
            )
            copied["merged_runtime_row_count"] = 1
            merged[signature] = copied
            order.append(signature)
            continue
        existing["source_claim_ids"] = list(
            dict.fromkeys(
                [
                    *existing.get("source_claim_ids", []),
                    *[str(item) for item in row.get("source_claim_ids", [])],
                ]
            )
        )
        existing["source_refs"] = list(
            dict.fromkeys(
                [
                    *existing.get("source_refs", []),
                    *[str(item) for item in row.get("source_refs", [])],
                ]
            )
        )
        existing["merged_runtime_row_count"] = int(
            existing.get("merged_runtime_row_count", 1)
        ) + 1
    return [merged[signature] for signature in order]
```

The compiler continues to ignore diagnostic provenance fields when writing runtime JSON.

- [ ] **Step 5: Remove filename-only readiness inference**

In `src/hsconfig/config_readiness.py`:

- Make `emitted_cardid_files` required and typed as `Mapping[str, Any]`.
- Remove the `fallback_cardids` argument.
- Remove the `None` branch and `payloads is None` branch.
- Add:

```python
if not isinstance(emitted_cardid_files, Mapping):
    raise TypeError("emitted_cardid_files must be a mapping of filename to payload")
```

- Add a CardID to `meaningful_cardids` only when `_has_runtime_effect_rows(payload)` is true.
- Update the remaining `build_config_readiness_report()` test callers to pass
  `{}` when no physical CardID file is present and `_effect_payloads(...)`
  when a meaningful physical row is expected.
- Do not change `src/hsconfig/package_builder.py`; it already passes `cardid_behavior_files`.

- [ ] **Step 6: Replace package duplicate-row expectations**

In `tests/test_shadowpriest_semantic_safety_wave.py`, replace multi-row
identical signatures with:

```python
@pytest.mark.parametrize(
    ("card_id", "block_name", "expected_signatures"),
    [
        ("DS1_233", "BeforePlayCardBonus", [("*", "12")]),
        ("GVG_009", "BeforePlayCardBonus", [("*", "10")]),
        ("REV_290", "BeforePlayCardBonus", [("*", "8")]),
        ("SW_446", "OnBoardBonus", [("*", "10")]),
        ("TOY_381", "OnBoardBonus", [("*", "8")]),
        ("WON_065", "OnBoardBonus", [("*", "8")]),
        ("TOY_518", "OnBoardBonus", [("*", "8")]),
        ("VAC_419", "BeforePlayCardBonus", [("*", "10")]),
    ],
)
def test_supported_runtime_rows_are_unique(
    package,
    card_id,
    block_name,
    expected_signatures,
):
    _assert_runtime_rows(_card(package, card_id), block_name, expected_signatures)
```

- [ ] **Step 7: Verify GREEN and physical/report parity**

```powershell
pytest tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_compile_cardid.py tests/test_shadowpriest_semantic_safety_wave.py -q
```

Expected:

- no duplicate physical rows,
- no duplicate reported rows,
- `physical_cardid_runtime_rows == reported_cardid_runtime_rows`,
- metadata-only files never count as `runtime_emitted`.

- [ ] **Step 8: Commit and push**

```powershell
git diff --check
git add src/hsconfig/card_behavior_surface_router.py src/hsconfig/config_readiness.py tests/test_card_behavior_router.py tests/test_config_readiness.py tests/test_compile_cardid.py tests/test_shadowpriest_semantic_safety_wave.py
git commit -m "fix: derive readiness from unique physical rows"
git push origin main
```

---

### Task 7: Make Operator Reports State Assurance Precisely

**Files:**
- Modify: `src/hsconfig/semantic_audit.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `tests/test_semantic_audit.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_operator_guidance.py`

**Interfaces:**
- Produces:
  ```python
  operator_summary["configuration_assurance"] = {
      "load_safety": "proven" | "not_proven",
      "semantic_closure": "closed" | "attention" | "insufficient_evidence",
      "in_client_behavior": "not_proven_by_pre_run_contract",
      "optimality_claim_allowed": False,
  }
  ```
- Does not affect `runtime_apply_allowed`, `runtime_apply_mode`, or `apply_policy`.

- [ ] **Step 1: Write semantic-audit rendering tests**

Add to `tests/test_semantic_audit.py`:

```python
def test_semantic_audit_separates_metadata_from_runtime_closure():
    markdown = render_semantic_audit_markdown(
        {
            "semantic_enrichment_status": "complete",
            "deckwide_effects": [],
            "cards": [],
            "semantic_enrichment_warnings": [],
        },
        config_readiness_report={
            "summary": {
                "total_cards": 16,
                "runtime_emitted": 8,
                "report_only_supported": 7,
                "globalvalues_only": 1,
            }
        },
    )

    assert "Metadata enrichment status: `complete`" in markdown
    assert "Runtime-emitted cards: `8/16`" in markdown
    assert "Report-only supported cards: `7`" in markdown
    assert "GlobalValues-only cards: `1`" in markdown
    assert "\nStatus: `complete`\n" not in markdown
```

Update the existing rendering test:

```python
assert "Metadata enrichment status: `partial`" in markdown
```

Remove its old `assert "Status: `partial`" in markdown` assertion.

- [ ] **Step 2: Write operator-assurance tests**

Add to `tests/test_operator_summary.py`:

```python
def test_load_safe_attention_summary_does_not_claim_optimality():
    summary = build_operator_summary(
        technical_validation={"status": "passed"},
        generated_files=[
            "CustomConfig/shadowpriest/GlobalValues.json",
            "CustomConfig/shadowpriest/Mulligan.json",
        ],
        card_behavior_plan_report={
            "rows": [],
            "suppressed": [
                {"reason": "semantic_surface_not_expressible"}
            ],
        },
    )

    assurance = summary["configuration_assurance"]
    assert assurance["load_safety"] == "proven"
    assert assurance["semantic_closure"] == "attention"
    assert assurance["in_client_behavior"] == "not_proven_by_pre_run_contract"
    assert assurance["optimality_claim_allowed"] is False
    assert summary["runtime_apply_allowed"] is True
```

Extend the existing
`test_source_backed_valid_package_is_ready_to_apply()`:

```python
assurance = summary["configuration_assurance"]
assert assurance == {
    "load_safety": "proven",
    "semantic_closure": "closed",
    "in_client_behavior": "not_proven_by_pre_run_contract",
    "optimality_claim_allowed": False,
    "runtime_gate_impact": "none",
}
assert summary["operator_guidance"]["configuration_assurance"] == assurance
```

- [ ] **Step 3: Verify RED**

```powershell
pytest tests/test_semantic_audit.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

- [ ] **Step 4: Extend semantic audit renderer**

Change:

```python
def render_semantic_audit_markdown(
    report: dict[str, Any],
    *,
    config_readiness_report: dict[str, Any] | None = None,
) -> str:
```

Render:

```markdown
Metadata enrichment status: `<status>`

## Runtime Semantic Closure

- Runtime-emitted cards: `{runtime}/{total}`
- Report-only supported cards: `<report_only>`
- GlobalValues-only cards: `<globalvalues_only>`
```

In `src/hsconfig/package_builder.py`, pass the already-built `config_readiness_report`.

- [ ] **Step 5: Add non-gating assurance projection**

In `src/hsconfig/operator_summary.py`, after `semantic_handoff` is built:

```python
configuration_assurance = {
    "load_safety": "proven" if load_safe_to_install else "not_proven",
    "semantic_closure": str(
        semantic_handoff.get("semantic_handoff_status", "insufficient_evidence")
    ),
    "in_client_behavior": "not_proven_by_pre_run_contract",
    "optimality_claim_allowed": False,
    "runtime_gate_impact": "none",
}
```

Add it to the summary. Do not use it inside `_runtime_apply_contract()`, `evaluate_apply_gate()`, or any write path.

In `src/hsconfig/operator_guidance.py`, project:

```python
"configuration_assurance": summary.get(
    "configuration_assurance",
    {
        "load_safety": "not_proven",
        "semantic_closure": "insufficient_evidence",
        "in_client_behavior": "not_proven_by_pre_run_contract",
        "optimality_claim_allowed": False,
        "runtime_gate_impact": "none",
    },
),
```

- [ ] **Step 6: Verify GREEN and apply-boundary invariants**

```powershell
pytest tests/test_semantic_audit.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_apply_authority_boundary.py tests/test_apply_gate.py tests/test_runtime_apply.py -q
```

- [ ] **Step 7: Commit and push**

```powershell
git diff --check
git add src/hsconfig/semantic_audit.py src/hsconfig/package_builder.py src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py tests/test_semantic_audit.py tests/test_operator_summary.py tests/test_operator_guidance.py
git commit -m "docs: distinguish load safety from semantic assurance"
git push origin main
```

---

### Task 8: Update Operator And Skill Contracts

**Files:**
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_docs_active_path.py`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_skill_sync.py`

**Interfaces:**
- Documents the code contracts from Tasks 2–7.
- Keeps `reports/operator_summary.json` as the single apply authority.

- [ ] **Step 1: Write docs contract tests**

Add exact required phrases to the docs/skill tests:

```python
REQUIRED_SEMANTIC_CLOSURE_PHRASES = (
    "`hero_power_transform` lowers through deckwide `GlobalValues.json`, not the physical start-of-game card.",
    "Guide-backed Mulligan keeps require `exact_deck_matched` evidence.",
    "Archetype-only Mulligan guidance may remain policy context but is not exact-deck authority.",
    "A metadata-only CardID file is not a `runtime_emitted` card.",
    "Load safety does not prove in-client optimality.",
)
```

Assert every phrase in:

- `docs/operator/README.md`,
- `.agents/skills/hsconfig/SKILL.md` or the directly linked reference named by the skill.

- [ ] **Step 2: Verify RED**

```powershell
pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

- [ ] **Step 3: Update source-contract documentation**

In `docs/operator/source-contract-spine.md`, change the `hero_power_transform` row to:

```markdown
| `hero_power_transform` | runtime_lowerable | `GlobalValues.json` | Requires an exact linked transformed Hero Power; never becomes a card-body action or mulligan keep by itself. |
```

In `docs/operator/guide-research-policy.md`, document:

- exact deck-code hash evidence,
- exact versus archetype match,
- exact mulligan authority,
- policy-backed fallback when exact evidence is absent,
- no strong promotion from a 40-card guide for a different 30-card deck.

- [ ] **Step 4: Update GlobalValues and card behavior documentation**

Document:

- linked Mind Spike effect → `MyHeroPowerValue`,
- exact source posture → `0.75 / 0.25`,
- partial `draw_engine_plan` source does not change turn weights,
- Papercraft/Chirurgeon/Distributor → `OnBoardBonus`,
- state-dependent cards stay report-only,
- identical runtime signatures deduplicate,
- filename-only readiness is invalid.

- [ ] **Step 5: Update operator assurance wording**

In `docs/operator/README.md` and `.agents/skills/hsconfig/SKILL.md`, include the exact statement:

```markdown
Load safety does not prove in-client optimality.
```

Document `configuration_assurance` as diagnostic-only with `runtime_gate_impact=none`.

- [ ] **Step 6: Sync the installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 7: Verify GREEN**

```powershell
pytest tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py -q
```

- [ ] **Step 8: Commit and push**

```powershell
git diff --check
git add docs/operator/source-contract-spine.md docs/operator/guide-research-policy.md docs/operator/README.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md .agents/skills/hsconfig/references/globalvalues-policy.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
git commit -m "docs: define semantic closure operator contract"
git push origin main
```

---

### Task 9: Run Full Package And Repository Verification

**Files:**
- Modify only if a test exposes a causal defect in Tasks 2–8.
- Do not add generated package output to git.

**Interfaces:**
- Produces verified code and a read-only package under an ignored output directory.
- Performs no runtime write.

- [ ] **Step 1: Run the focused semantic suite**

```powershell
pytest tests/test_shadowpriest_visionai_semantic_surface_contract.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py tests/test_claim_kind_runtime_contract.py tests/test_source_contract_spine_freeze.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_card_behavior_router.py tests/test_semantic_runtime_gate.py tests/test_config_readiness.py tests/test_semantic_audit.py tests/test_operator_summary.py tests/test_operator_guidance.py -q
```

Expected: all pass.

- [ ] **Step 2: Run contract guardrails**

```powershell
python scripts/check_contract_guardrails.py
```

Expected: contract clean; all focused guardrail groups pass.

- [ ] **Step 3: Run the complete suite**

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
pytest -q -p no:cacheprovider
```

Expected: all tests pass; documented skips only.

- [ ] **Step 4: Generate a fresh read-only ShadowPriest package**

Resolve the exact output path first:

```powershell
$auditOut = 'C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726'
if (-not $auditOut.StartsWith('C:\Users\darbo\Documents\HSConfig\outputs\')) {
    throw "Unexpected output path: $auditOut"
}
```

Run without `--apply`:

```powershell
hsconfig configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726" --online-source --auto-source --json
```

Expected:

- `status=OK`,
- `runtime_write_performed=false`,
- exact deck identity,
- package validation passed.

- [ ] **Step 5: Validate and inspect the package**

```powershell
hsconfig validate --package "C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726\04_package" --json
hsconfig contract-doctor --package "C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726\04_package" --json
python -m hsconfig.cli runtime-match --package "C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Expected:

- validation passes,
- contract doctor reports clean physical/report parity,
- runtime-match performs no write,
- a mismatch is acceptable because this plan does not apply the package.

- [ ] **Step 6: Assert the fresh package invariants**

Run:

```powershell
@'
import json
from pathlib import Path

package = Path(r"C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726\04_package")
deck = package / "CustomConfig" / "shadowpriest"
reports = package / "reports"

darkbishop = json.loads((deck / "SW_448.json").read_text(encoding="utf-8"))
globalvalues = json.loads((deck / "GlobalValues.json").read_text(encoding="utf-8"))
readiness = json.loads(
    (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
)
operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

assert set(darkbishop) == {"GameCardId", "ConfigComment"}
assert globalvalues["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
assert readiness["summary"]["runtime_emitted"] >= 8
assert readiness["summary"]["report_only_supported"] >= 6
assert operator["runtime_apply_allowed"] is True
assert operator["use_config_now_scope"] == "load_safety_only"
assert operator["configuration_assurance"]["optimality_claim_allowed"] is False
assert operator["configuration_assurance"]["in_client_behavior"] == "not_proven_by_pre_run_contract"
print("ShadowPriest semantic closure package invariants passed")
'@ | python -
```

- [ ] **Step 7: Remove the generated audit package**

Verify the resolved path, then remove only that directory:

```powershell
$auditOut = (Resolve-Path -LiteralPath 'C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726').Path
if ($auditOut -ne 'C:\Users\darbo\Documents\HSConfig\outputs\semantic-closure-shadowpriest-20260726') {
    throw "Unexpected resolved output path: $auditOut"
}
Remove-Item -LiteralPath $auditOut -Recurse
```

- [ ] **Step 8: Run final currentness and cleanliness checks**

```powershell
python scripts/sync_installed_skill.py --check
python scripts/check_hsconfig_currentness.py --cwd . --json
git diff --check
git status --short --branch
git rev-list --left-right --count main...origin/main
gh api repos/Teufelsboy/HSConfig/branches --paginate --jq '.[].name'
gh pr list --repo Teufelsboy/HSConfig --state open --json number,title,headRefName
```

Expected:

- installed skill in sync,
- clean `main`,
- `0 0` divergence,
- only branch `main`,
- no open pull requests.

- [ ] **Step 9: Commit any final causal correction and push**

If Step 1–8 required a causal correction:

1. Return the correction to the task that owns the affected files.
2. Repeat that task's exact RED/GREEN and focused regression commands.
3. Stage only the exact paths listed by that task.
4. Use that task's commit message and push command.

If no correction was required, do not create an empty commit.

---

## Final Acceptance Matrix

| Contract | Exact-source fixture | Current partial source |
|---|---:|---:|
| Exact 30-card identity | Required | Required |
| JSON/package validation | Pass | Pass |
| Runtime apply allowed | `true` | `true` |
| Runtime write during implementation | `false` | `false` |
| Darkbishop mulligan keep | Absent | Absent |
| Darkbishop CardID action row | Absent | Absent |
| Linked Mind Spike `MyHeroPowerValue` | `1.15` | `1.15` |
| First/second turn weights | `0.75 / 0.25` for exact `aggro_burn` posture | Baseline unless the acquired claim is canonical and eligible |
| Exact guide-backed Mulligan | Allowed | Forbidden |
| Policy-backed Mulligan fallback | Optional | Allowed and labeled |
| Papercraft `OnBoardBonus` | Present once | Present once |
| Chirurgeon `OnBoardBonus` | Present once | Present once |
| Treasure Distributor `OnBoardBonus` | Present once | Present once |
| Raise Dead/Felwing/Mind Sear conditional action | Report-only | Report-only |
| Duplicate runtime signatures | Zero | Zero |
| Filename-only readiness | Rejected | Rejected |
| `SOURCE_BACKED_STRONG` | Allowed when all strong closure requirements pass | Forbidden |
| Operator optimality claim | `false` | `false` |

## Out Of Scope

- Runtime apply.
- HSTuner.
- Win-rate claims.
- Matchup-specific tuning.
- Low-HP numeric tuning.
- New unsupported condition atoms for graveyard, damage-this-turn, exact lethal, or location activation.
- Exact minion target selection for Mind Sear.
- Exact same-turn sequencing unless an existing complete `combo_sequence` claim proves it.
- Treating a different 40-card guide as exact evidence for the 30-card deck.

## Implementation Completion Criteria

Implementation is complete only when:

1. Tasks 1–9 are checked.
2. Every task-specific test is green.
3. Contract guardrails are green.
4. The complete pytest suite is green.
5. The fresh read-only package passes validation and invariant checks.
6. Runtime-match performed no write.
7. The generated audit package was removed.
8. The installed HSConfig skill matches the repo source.
9. Git is clean on `main`, local and `origin/main` are `0 0`, only `main` exists, and no PR is open.
10. No report or final message claims in-client optimality from pre-run artifacts alone.
