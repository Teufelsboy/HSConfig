# HSConfig ShadowPriest Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the audited ShadowPriest source-authority, Mulligan, VisionAI semantic-surface, runtime-row, validation-parity, and assurance defects from current `main`.

**Architecture:** Preserve the existing contract spine and fix the defects in dependency order: exact source identity first, surface authorization second, static card lowering third, physical-row truth fourth, and operator reporting last. All runtime-producing paths consume the same canonical decisions, while rejected evidence remains visible in diagnostic reports.

**Tech Stack:** Python 3.11+, pytest, JSON contract artifacts, HearthRanger VisionAI CustomConfig, PowerShell, GitHub `main`.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`, except for the existing
  `scripts/sync_installed_skill.py` path in Task 7 and validated temporary
  package directories in Task 8.
- Baseline commit for this plan is `349547f2f3008e0a215f7e406a8b8dcc8f47524c`.
- Work directly on the single `main` branch. Do not create a branch, worktree, pull request, or shadow checkout.
- Finish every task with clean `main == origin/main`; push each reviewed task commit before starting the next task.
- Do not use HSTuner.
- Do not run `apply`, `write-runtime`, direct runtime copies, or any command that writes `C:\Users\darbo\Desktop\HS`.
- Temporary generated packages are read-only evidence and must be outside the repository and deleted after verification.
- `reports/operator_summary.json` remains the sole normal runtime-apply authority.
- Normal output surfaces remain `GlobalValues.json`, `Mulligan.json`, per-card `<CARDID>.json`, and `Combo.json` only for a timing-complete source-backed combo.
- Do not add `Presume.json`, `Concede.json`, `CardBehavior.json`, new VisionAI keys, or unproven condition atoms.
- Do not claim in-client behavior, gameplay improvement, win-rate improvement, or optimality from pre-run contracts.
- Follow TDD for every behavioral change: observe the focused RED failure, implement the minimum causal change, then observe GREEN.
- Use `python -m pytest -p no:cacheprovider` and set `PYTHONDONTWRITEBYTECODE=1` for the complete suite.
- Preserve the approved design in `docs/superpowers/specs/2026-07-26-hsconfig-shadowpriest-semantic-closure-design.md`.

## Current Audit Baseline

The implementation starts from these reproduced facts:

- Git is clean on `main`, local and `origin/main` are `0 0`, and there are no open pull requests.
- The complete suite is red: `8 failed, 2132 passed, 11 skipped`.
- The failures are in exact-source promotion, source-document propagation, and strong-source acceptance.
- The saved `outputs/ShadowPriest/04_package` fails current strict validation.
- Saved package and live runtime differ semantically in 12 of 18 JSON files.
- A fresh exact-source package validates but is only `SOURCE_BACKED_PARTIAL` because exact evidence is dropped during drafting.
- A fresh package emits 6 active cards, 10 report-only cards, 11 physical rows, and 3 duplicate signatures.
- The approved physical target is 7 active cards, 9 report-only cards, 7 physical rows, and zero duplicate/conflicting signatures.
- No post-sync HearthRanger logs prove the current live package loaded or improved gameplay.

## Locked File And Interface Map

### Exact source identity

- `src/hsconfig/source_acquisition.py` owns decoded deckstring comparison and redacted exact-deck evidence.
- `src/hsconfig/source_autopilot.py` copies canonical evidence into evidence rows.
- `src/hsconfig/source_document_drafter.py` preserves consensus evidence on the drafted document.
- `src/hsconfig/source_document_builder.py` remains the final fingerprint revalidation boundary.

### Mulligan authorization

- `src/hsconfig/source_document_model.py` owns the shared surface decision.
- `src/hsconfig/source_claim_lifecycle.py` exposes accepted and rejected surface decisions.
- `src/hsconfig/mulligan_plan.py` renders allowed rules and visible suppression reasons.
- `src/hsconfig/package_builder.py` uses accepted claims for runtime and accepted plus rejected claims for the Mulligan diagnostic plan.

### Card semantics

- `src/hsconfig/card_intent_taxonomy.py` classifies card intent.
- `src/hsconfig/static_semantics.py` builds official-static claims.
- `src/hsconfig/mechanic_support.py` documents supported surfaces.
- `src/hsconfig/semantic_runtime_gate.py` enforces expressibility.

### Physical runtime truth

- New `src/hsconfig/runtime_row_identity.py` owns canonical runtime-row identity, duplicate merging, and conflict detection.
- `src/hsconfig/card_behavior_surface_router.py` and `src/hsconfig/compile_cardid.py` consume canonical rows.
- `src/hsconfig/config_readiness.py` derives readiness from parsed physical payloads.

### Strict package validation

- New `src/hsconfig/strict_package_validation.py` owns the single strict validation entry point.
- `validate`, `apply`, package build, and package preflight call that entry point.

### Assurance

- `src/hsconfig/operator_summary.py` builds `configuration_assurance`.
- `src/hsconfig/operator_guidance.py` and `src/hsconfig/semantic_audit.py` project it without changing apply authority.
- Operator docs and the installed HSConfig skill describe the same boundary.

---

### Task 1: Restore Exact Source Evidence And Make The Source Suite Green

**Files:**

- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_document_drafter.py`
- Modify: `tests/test_source_document_drafter.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/test_multideck_source_backed_e2e.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Modify: `tests/test_source_autopilot_cli.py`
- Modify: `tests/test_source_backed_strong_harvester_closure.py`

**Interfaces:**

- Consumes: `source["deck_match"]["exact_deck_evidence"]` created by source acquisition.
- Produces: document-level `deck_match.exact_deck_evidence` containing only hashes, fingerprint, counts, and `matched`; never the raw source deckstring.
- Invariant: a drafted document remains exact only when every row grouped into that document carries the same matched fingerprint.
- Invariant: `source_document_builder._document_has_exact_deck_evidence()` remains the final verifier against `deck_identity["deck_fingerprint"]`.

- [ ] **Step 1: Add a drafter regression for exact evidence preservation**

Add to `tests/test_source_document_drafter.py`:

```python
def test_drafter_preserves_consensus_exact_deck_evidence():
    fingerprint = "sha256:exact-shadowpriest"
    row = {
        "source_url": "https://example.test/shadowpriest-exact",
        "source_title": "Exact ShadowPriest Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
        "deck_name": "ShadowPriest",
        "archetype": "shadowpriest",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "deck_match_scope": "exact_deck_matched",
        "source_visibility": "full_text",
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": fingerprint,
                "candidate_deck_code_hashes": ["sha256:source-code"],
            }
        },
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_381"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Papercraft Angel.",
        "source_confidence": "high",
    }

    result = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "deck_fingerprint": fingerprint,
            "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel"}],
        },
        evidence_rows=[row],
    )

    document = result["source_documents"][0]
    assert document["deck_match"] == row["deck_match"]
    assert "deck_code" not in str(document)
```

- [ ] **Step 2: Add a conflicting-evidence regression**

Add:

```python
def test_drafter_downgrades_conflicting_exact_evidence():
    rows = []
    for fingerprint in ("sha256:first", "sha256:second"):
        rows.append(
            {
                "source_url": "https://example.test/shared-guide",
                "source_title": "Shared Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "source_lane": "deck_matched_public_guide",
                "source_rank_lane": "guide_current_deck_match",
                "deck_match_scope": "exact_deck_matched",
                "source_visibility": "full_text",
                "deck_match": {
                    "exact_deck_evidence": {
                        "matched": True,
                        "matched_deck_fingerprint": fingerprint,
                    }
                },
                "claim_kind": "mulligan_keep",
                "cards": ["TOY_381"],
                "scope": "card",
                "stance": "keep",
                "source_confidence": "high",
            }
        )

    result = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel"}],
        },
        evidence_rows=rows,
    )

    document = result["source_documents"][0]
    assert document["deck_match_scope"] == "archetype_matched"
    assert document["source_lane"] == "archetype_matched_public_guide"
    assert "deck_match" not in document
```

- [ ] **Step 3: Run the focused tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_source_document_drafter.py tests/test_shadowpriest_source_contract_acceptance.py
```

Expected: the new drafter preservation test fails because `deck_match` is absent; the exact ShadowPriest acceptance test remains partial instead of strong.

- [ ] **Step 4: Copy only canonical exact evidence into autopilot rows**

In `source_autopilot._source_base()`, after constructing `base`, add:

```python
    exact_evidence = match.get("exact_deck_evidence", {})
    if (
        deck_match_scope == "exact_deck_matched"
        and isinstance(exact_evidence, Mapping)
        and exact_evidence.get("matched") is True
    ):
        base["deck_match"] = {
            "exact_deck_evidence": {
                "candidate_count": int(exact_evidence.get("candidate_count", 0)),
                "decoded_candidate_count": int(
                    exact_evidence.get("decoded_candidate_count", 0)
                ),
                "matched": True,
                "matched_deck_fingerprint": _text(
                    exact_evidence.get("matched_deck_fingerprint", "")
                ),
                "candidate_deck_code_hashes": sorted(
                    _text(value)
                    for value in _as_list(
                        exact_evidence.get("candidate_deck_code_hashes", [])
                    )
                    if _text(value)
                ),
            }
        }
```

The persisted structure must contain no raw deckstring.

- [ ] **Step 5: Preserve only consensus evidence in drafted documents**

Add these helpers to `source_document_drafter.py`:

```python
def _exact_deck_match_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    deck_match = row.get("deck_match")
    if not isinstance(deck_match, dict):
        return None
    exact = deck_match.get("exact_deck_evidence")
    if not isinstance(exact, dict) or exact.get("matched") is not True:
        return None
    fingerprint = str(exact.get("matched_deck_fingerprint", "")).strip()
    if not fingerprint:
        return None
    return {"exact_deck_evidence": dict(exact)}


def _merge_document_deck_match(
    document: dict[str, Any],
    row: dict[str, Any],
) -> None:
    if document.get("_deck_match_conflict") is True:
        return
    candidate = _exact_deck_match_from_row(row)
    if candidate is None:
        if document.get("deck_match_scope") == "exact_deck_matched":
            document.pop("deck_match", None)
            document["deck_match_scope"] = "archetype_matched"
            document["source_lane"] = "archetype_matched_public_guide"
            document["_deck_match_conflict"] = True
        return
    existing = document.get("deck_match")
    if existing is None:
        document["deck_match"] = candidate
        return
    if existing != candidate:
        document.pop("deck_match", None)
        document["deck_match_scope"] = "archetype_matched"
        document["source_lane"] = "archetype_matched_public_guide"
        document["_deck_match_conflict"] = True
```

Call `_merge_document_deck_match(document, row)` for every row immediately
after assigning the result of `grouped.setdefault(key, document_seed)`. Before
returning `documents`, remove the internal marker from every document:

```python
for document in documents:
    document.pop("_deck_match_conflict", None)
```

- [ ] **Step 6: Correct legacy tests to the canonical scope contract**

In tests that expect a public guide to promote, replace the legacy input:

```python
"deck_match_scope": "deck_or_archetype_matched"
```

with exact, builder-verifiable evidence:

```python
"deck_match_scope": "exact_deck_matched",
"deck_match": {
    "exact_deck_evidence": {
        "matched": True,
        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
    }
},
```

Tests for non-promoting or archetype-only sources must use:

```python
"deck_match_scope": "archetype_matched",
"source_lane": "archetype_matched_public_guide",
```

and assert they do not become `SOURCE_BACKED_STRONG`.

- [ ] **Step 7: Run the previously failing source group**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_claim_kind_runtime_contract.py tests/test_configure_auto_source.py tests/test_multideck_source_backed_e2e.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_source_autopilot_cli.py tests/test_source_backed_strong_harvester_closure.py tests/test_source_document_drafter.py
```

Expected: all pass.

- [ ] **Step 8: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/source_autopilot.py src/hsconfig/source_document_drafter.py tests/test_source_document_drafter.py tests/test_claim_kind_runtime_contract.py tests/test_configure_auto_source.py tests/test_multideck_source_backed_e2e.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_source_autopilot_cli.py tests/test_source_backed_strong_harvester_closure.py
git add src/hsconfig/source_autopilot.py src/hsconfig/source_document_drafter.py tests/test_source_document_drafter.py tests/test_claim_kind_runtime_contract.py tests/test_configure_auto_source.py tests/test_multideck_source_backed_e2e.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_source_autopilot_cli.py tests/test_source_backed_strong_harvester_closure.py
git commit -m "fix: preserve exact source identity through drafting"
git push origin main
git status --short --branch
```

Expected: clean `main...origin/main`.

---

### Task 2: Enforce Exact Public-Guide Mulligan Authority

**Files:**

- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/source_claim_lifecycle.py`
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_claim_kind_runtime_contract.py`
- Modify: `tests/test_source_claim_lifecycle.py`
- Modify: `tests/test_mulligan_plan.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Create: `tests/test_shadowpriest_partial_source_acceptance.py`

**Interfaces:**

- Produces:

```python
def select_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
    *,
    context: Mapping[str, Any] | None = None,
    card_roles: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return accepted_claims and rejected_claims with lifecycle reasons."""
```

- `runtime_claims_for_surface()` remains backward compatible and returns only `accepted_claims`.
- Public-guide Mulligan claims require exact scope, promotion eligibility, full text, and `deck_matched_public_guide`.
- Policy-backed autonomous Mulligan remains a separate fallback and never counts as guide evidence.

- [ ] **Step 1: Write the four authority-gate tests**

Add a parameterized test to `tests/test_claim_kind_runtime_contract.py`:

```python
@pytest.mark.parametrize(
    ("override", "reason"),
    [
        (
            {"deck_match_scope": "archetype_matched"},
            "mulligan_requires_exact_deck_match",
        ),
        (
            {"promotion_eligible": False},
            "mulligan_requires_promotion_eligible_source",
        ),
        (
            {"source_visibility": "snippet_only"},
            "mulligan_requires_full_text_source",
        ),
        (
            {"source_lane": "archetype_matched_public_guide"},
            "mulligan_requires_deck_matched_public_guide_lane",
        ),
    ],
)
def test_public_guide_mulligan_requires_exact_authority(override, reason):
    claim = {
        "claim_kind": "mulligan_keep",
        "source_family": "guide",
        "cards": ["TOY_381"],
        "deck_match_scope": "exact_deck_matched",
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "claim_readiness": "guide_backed",
        **override,
    }

    decision = can_lower_to_mulligan(claim)

    assert decision.allowed is False
    assert decision.reason == reason
```

Add a positive test with all four exact fields and assert `allowed`.

- [ ] **Step 2: Write lifecycle visibility tests**

Add to `tests/test_source_claim_lifecycle.py`:

```python
def test_surface_selection_keeps_rejected_mulligan_claim_visible():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "claim-archetype-guide",
                "claim_kind": "mulligan_keep",
                "source_family": "guide",
                "cards": ["TOY_381"],
                "deck_match_scope": "archetype_matched",
                "promotion_eligible": True,
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "claim_readiness": "guide_backed",
            }
        ]
    )

    selection = select_claims_for_surface(rows, "mulligan")

    assert selection["accepted_claims"] == []
    assert selection["rejected_claims"][0]["_claim_lifecycle"] == {
        "claim_id": "claim-archetype-guide",
        "surface": "mulligan",
        "policy_lane": "runtime_lowerable",
        "surface_gate_allowed": False,
        "surface_gate_reason": "mulligan_requires_exact_deck_match",
    }
```

- [ ] **Step 3: Write partial-source end-to-end acceptance**

Create `tests/test_shadowpriest_partial_source_acceptance.py` with a configure fixture using:

```python
source_url = "https://example.test/shadowpriest-archetype"
```

and `tests/fixtures/source_pages/shadowpriest_source_url_map.json`. Assert:

```python
assert operator["source_backed_status"] != "SOURCE_BACKED_STRONG"
assert global_profile["changed_keys"] == []
assert mulligan_plan["quality"]["source_backed_keep_rule_count"] == 0
assert {
    row["reason"] for row in mulligan_plan["suppressed_rules"]
} >= {"mulligan_requires_exact_deck_match"}
assert all(
    row.get("source_type") == "policy_backed_autonomous_mulligan"
    for row in mulligan_plan["rules"]
    if row["action"] == "hold"
)
```

- [ ] **Step 4: Run the new tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_claim_kind_runtime_contract.py tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_shadowpriest_partial_source_acceptance.py
```

Expected: archetype-only guide claims are currently accepted or disappear without a suppression row.

- [ ] **Step 5: Add the exact-guide gate**

In `source_document_model.py`, before the Darkbishop check in `can_lower_to_mulligan()`, add:

```python
    source_family = _normalized_text(claim.get("source_family"))
    public_guide = source_family in {"guide", "mulligan_guide"}
    if public_guide:
        if _normalized_text(claim.get("deck_match_scope")) != "exact_deck_matched":
            return SurfaceGateDecision(
                False,
                "mulligan_requires_exact_deck_match",
                claim_kind,
                "mulligan",
            )
        if not _bool_value(claim.get("promotion_eligible")):
            return SurfaceGateDecision(
                False,
                "mulligan_requires_promotion_eligible_source",
                claim_kind,
                "mulligan",
            )
        if _normalized_text(claim.get("source_visibility")) != "full_text":
            return SurfaceGateDecision(
                False,
                "mulligan_requires_full_text_source",
                claim_kind,
                "mulligan",
            )
        if _normalized_text(claim.get("source_lane")) != "deck_matched_public_guide":
            return SurfaceGateDecision(
                False,
                "mulligan_requires_deck_matched_public_guide_lane",
                claim_kind,
                "mulligan",
            )
```

- [ ] **Step 6: Preserve accepted and rejected lifecycle decisions**

Implement `select_claims_for_surface()` in `source_claim_lifecycle.py`. Each non-quarantined, runtime-eligible claim receives:

```python
claim["_claim_lifecycle"] = {
    "claim_id": row.get("claim_id"),
    "surface": surface,
    "policy_lane": row.get("policy_lane"),
    "surface_gate_allowed": decision.allowed,
    "surface_gate_reason": decision.reason,
}
```

Append it to `accepted_claims` or `rejected_claims`. Rewrite `runtime_claims_for_surface()` as:

```python
def runtime_claims_for_surface(
    rows,
    surface,
    *,
    context=None,
    card_roles=None,
):
    return select_claims_for_surface(
        rows,
        surface,
        context=context,
        card_roles=card_roles,
    )["accepted_claims"]
```

- [ ] **Step 7: Route rejected Mulligan claims into the report only**

In `package_builder.py`, use:

```python
mulligan_selection = select_claims_for_surface(
    initial_lifecycle_rows,
    "mulligan",
    card_roles=card_roles,
)
mulligan_runtime_claims = mulligan_selection["accepted_claims"]
mulligan_report_claims = [
    *mulligan_runtime_claims,
    *mulligan_selection["rejected_claims"],
]
```

Pass `mulligan_report_claims` to `build_mulligan_plan()`. In `mulligan_plan.py`, if `_claim_lifecycle.surface_gate_allowed` is false, emit the stored reason to `suppressed_rules` and do not compile a rule.

- [ ] **Step 8: Run exact, partial, and policy fallback tests**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_claim_kind_runtime_contract.py tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py tests/test_autonomous_mulligan_policy.py
```

Expected: all pass; exact public-guide rules may lower, archetype-only rules are visible but suppressed, and policy fallback remains labeled.

- [ ] **Step 9: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/source_document_model.py src/hsconfig/source_claim_lifecycle.py src/hsconfig/mulligan_plan.py src/hsconfig/package_builder.py tests/test_claim_kind_runtime_contract.py tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
git add src/hsconfig/source_document_model.py src/hsconfig/source_claim_lifecycle.py src/hsconfig/mulligan_plan.py src/hsconfig/package_builder.py tests/test_claim_kind_runtime_contract.py tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py
git commit -m "fix: require exact authority for guide mulligan"
git push origin main
git status --short --branch
```

---

### Task 3: Implement The Seven-Active/Nine-Report-Only Card Contract

**Files:**

- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/static_semantics.py`
- Modify: `src/hsconfig/mechanic_support.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Modify: `tests/test_card_intent_taxonomy.py`
- Modify: `tests/test_static_semantics.py`
- Modify: `tests/test_semantic_runtime_gate.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`
- Modify: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

**Interfaces:**

- Adds semantic family `summon_trigger_board_engine`.
- `summon_trigger_board_engine` lowers only to `OnBoardBonus`.
- `reciprocal_hero_burn` is report-only without a proven health condition.
- `damage_aura_amplifier` lowers only to `OnBoardBonus`.
- Safe physical target:

```python
SAFE_SHADOWPRIEST_ROWS = {
    ("DS1_233", "BeforePlayCardBonus", "*", "12"),
    ("REV_290", "BeforePlayCardBonus", "*", "8"),
    ("SW_446", "OnBoardBonus", "*", "10"),
    ("SW_448", "BeforeUseHeroPowerBonus", "*", "10"),
    ("TOY_381", "OnBoardBonus", "*", "8"),
    ("TOY_518", "OnBoardBonus", "*", "8"),
    ("WON_065", "OnBoardBonus", "*", "8"),
}
```

- Report-only target:

```python
REPORT_ONLY_SHADOWPRIEST = {
    "CFM_637",
    "DRG_056",
    "GVG_009",
    "NX2_019",
    "SCH_514",
    "SW_444",
    "VAC_419",
    "VAC_512",
    "YOD_032",
}
```

- [ ] **Step 1: Write intent and static-source tests**

Add parameterized tests for:

```python
[
    ("TOY_518", "After you summon a Pirate, give it +1 Attack."),
    ("WON_065", "After you summon a minion, give it +1 Health."),
]
```

Assert
`classify_card_intent(text, card_identity=card_id).reason == "summon_trigger_board_engine"`,
value `8`, and the static claim uses `runtime_block == "OnBoardBonus"`.

- [ ] **Step 2: Write semantic-gate tests**

Add:

```python
def test_summon_trigger_engine_allows_only_on_board_value():
    allowed = decide_semantic_runtime(
        semantic_reason="summon_trigger_board_engine",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="OnBoardBonus",
        claim_kind="mechanic_usage",
    )
    rejected = decide_semantic_runtime(
        semantic_reason="summon_trigger_board_engine",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert allowed.allowed is True
    assert rejected == SemanticRuntimeDecision(
        False,
        "semantic_surface_not_expressible",
    )
```

Add parameterized tests proving `reciprocal_hero_burn` wildcard rows are rejected for both official-static and exact-guide lanes, and `damage_aura_amplifier` accepts only `OnBoardBonus`.

- [ ] **Step 3: Run focused tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py
```

- [ ] **Step 4: Add the trigger-engine semantic family**

Before generic summon handling in `card_intent_taxonomy.py`, add:

```python
if (
    _has_any(normalized, ("after you summon", "whenever you summon"))
    and _has_any(normalized, ("give it +", "give that minion +"))
) or identity_reason == "summon_trigger_board_engine":
    return CardIntentClassification(
        reason="summon_trigger_board_engine",
        value="8",
        band="medium",
        matched_signals=_signals(
            ("after_you_summon", "after you summon" in normalized),
            ("pirate_trigger", "pirate" in normalized),
            ("persistent_buff_engine", "give it +" in normalized),
        ),
    )
```

Map `TOY_518`, Treasure Distributor, `WON_065`, and both apostrophe spellings of Ship's Chirurgeon to that reason. Detect the same phrase family in `static_semantics.py`.

- [ ] **Step 5: Lock the supported runtime surfaces**

In `mechanic_support.py`, register:

```python
"summon_trigger_board_engine": {
    "support_level": "partial",
    "normal_path_surfaces": ["CARDID.json:OnBoardBonus"],
    "warning_boundary": (
        "Board value is representable; exact summon sequencing and "
        "trigger eligibility remain broader bot evaluation."
    ),
},
```

In `semantic_runtime_gate.py`:

- move `reciprocal_hero_burn` to the report-only set;
- remove its static action surface;
- allow `damage_aura_amplifier` only on `OnBoardBonus`;
- allow `summon_trigger_board_engine` only on `OnBoardBonus`;
- evaluate recognized semantic reasons before the general guide-lane allowance.

- [ ] **Step 6: Lock the ShadowPriest package expectations**

In `tests/test_shadowpriest_semantic_safety_wave.py`, assert:

```python
assert physical_signatures == SAFE_SHADOWPRIEST_ROWS
assert len(physical_signatures) == 7
assert runtime_emitted_card_ids == {
    "DS1_233",
    "REV_290",
    "SW_446",
    "SW_448",
    "TOY_381",
    "TOY_518",
    "WON_065",
}
assert report_only_card_ids == REPORT_ONLY_SHADOWPRIEST
```

Also assert:

- no `InHandPlayPriority`;
- no Shadowbomber or Twilight `BeforeBattlecryTargetBonus`;
- no Darkbishop `BeforePlayCardBonus`;
- no Darkbishop Mulligan keep;
- each report-only CardID payload contains only `GameCardId` and `ConfigComment`.

- [ ] **Step 7: Run the complete card semantic group**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
```

Expected: all pass.

- [ ] **Step 8: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/card_intent_taxonomy.py src/hsconfig/static_semantics.py src/hsconfig/mechanic_support.py src/hsconfig/semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
git add src/hsconfig/card_intent_taxonomy.py src/hsconfig/static_semantics.py src/hsconfig/mechanic_support.py src/hsconfig/semantic_runtime_gate.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
git commit -m "fix: lower only safe ShadowPriest card semantics"
git push origin main
git status --short --branch
```

---

### Task 4: Canonicalize Runtime Rows And Derive Readiness From Physical JSON

**Files:**

- Create: `src/hsconfig/runtime_row_identity.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/config_readiness.py`
- Create: `tests/test_runtime_row_identity.py`
- Modify: `tests/test_card_behavior_router.py`
- Modify: `tests/test_compile_cardid.py`
- Modify: `tests/test_config_readiness.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`

**Interfaces:**

```python
RuntimeRowKey = tuple[str, str, str]
RuntimeRowSignature = tuple[str, str, str, str]
```

The module exposes `runtime_row_key(card_id, behavior_block, row)`,
`runtime_row_signature(card_id, behavior_block, row)`, and
`canonicalize_runtime_rows(rows)`. The canonicalizer returns `rows`,
`merged_duplicate_count`, `merged_provenance`, and `conflicts`.

- Exact duplicate signatures merge provenance.
- Same `(card_id, behavior_block, condition)` with different values is a conflict and emits no runtime row.
- Readiness parses physical CardID JSON; filename presence alone never counts as `runtime_emitted`.

- [ ] **Step 1: Write duplicate and conflict tests**

Create `tests/test_runtime_row_identity.py`:

```python
def test_exact_duplicate_rows_merge_provenance():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-a",
            },
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-b",
            },
        ]
    )

    assert len(result["rows"]) == 1
    assert result["merged_duplicate_count"] == 1
    assert result["rows"][0]["source_claim_ids"] == ["claim-a", "claim-b"]
    assert result["conflicts"] == []


def test_same_surface_condition_with_different_values_fails_closed():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "6",
                "claim_id": "claim-a",
            },
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-b",
            },
        ]
    )

    assert result["rows"] == []
    assert result["conflicts"][0]["key"] == [
        "REV_290",
        "BeforePlayCardBonus",
        "*",
    ]
    assert result["conflicts"][0]["values"] == ["6", "8"]
```

- [ ] **Step 2: Run the new module test and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_runtime_row_identity.py
```

Expected: import failure because the module does not exist.

- [ ] **Step 3: Implement canonical identity**

Create `runtime_row_identity.py` with normalized string identity:

```python
def runtime_row_key(card_id, behavior_block, row):
    return (
        str(card_id).strip(),
        str(behavior_block).strip(),
        str(row.get("condition", "*")).strip() or "*",
    )


def runtime_row_signature(card_id, behavior_block, row):
    return (*runtime_row_key(card_id, behavior_block, row), str(row["value"]).strip())
```

Implement `canonicalize_runtime_rows()` in two passes:

1. group rows by `RuntimeRowKey`;
2. if a group contains multiple values, add one conflict and emit none;
3. otherwise merge identical signatures and stable-sort unique `claim_id`, `source_claim_ids`, and `merged_claim_ids`;
4. sort output rows by signature.

- [ ] **Step 4: Canonicalize before routing and physical compile**

Make `card_behavior_surface_router.py` return only canonical rows and include:

```python
"merged_duplicate_runtime_row_count": result["merged_duplicate_count"],
"runtime_row_conflicts": result["conflicts"],
```

Make `compile_cardid.py` run the same canonicalizer as a final physical-write guard. If conflicts exist, omit the conflicting key and expose the conflicts in the compile result.

- [ ] **Step 5: Make readiness parse physical payloads**

In `config_readiness.py`, count a card as `runtime_emitted` only when its parsed payload contains at least one supported behavior block with a non-empty `values` list. A payload containing only:

```python
{"GameCardId", "ConfigComment"}
```

is `report_only_supported`.

Add report fields:

```python
"physical_cardid_runtime_rows": physical_count,
"reported_cardid_runtime_rows": reported_count,
"unreported_runtime_rows": unreported,
"reported_rows_missing_runtime": missing,
```

- [ ] **Step 6: Add physical/report parity tests**

Assert:

```python
assert readiness["summary"]["runtime_emitted"] == 7
assert readiness["summary"]["report_only_supported"] == 9
assert trace["physical_cardid_runtime_rows"] == 7
assert trace["reported_cardid_runtime_rows"] == 7
assert trace["unreported_runtime_rows"] == []
assert trace["reported_rows_missing_runtime"] == []
assert duplicate_signatures == []
assert conflicting_signatures == []
```

- [ ] **Step 7: Run runtime-row and readiness tests**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py
```

Expected: all pass.

- [ ] **Step 8: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/runtime_row_identity.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_readiness.py tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py
git add src/hsconfig/runtime_row_identity.py src/hsconfig/card_behavior_surface_router.py src/hsconfig/compile_cardid.py src/hsconfig/config_readiness.py tests/test_runtime_row_identity.py tests/test_card_behavior_router.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_shadowpriest_semantic_safety_wave.py
git commit -m "fix: canonicalize physical VisionAI runtime rows"
git push origin main
git status --short --branch
```

---

### Task 5: Unify Strict Validation For Build, Validate, Apply, And Preflight

**Files:**

- Create: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/commands/apply.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/contract_preflight.py`
- Create: `tests/test_strict_package_validation.py`
- Modify: `tests/test_contract_preflight.py`
- Modify: `tests/test_apply_gate.py`
- Modify: `tests/test_runtime_apply.py`

**Interfaces:**

```python
def validate_complete_package(package: str | Path) -> dict[str, Any]:
    """Run the strict complete-package contract used by every caller."""
```

- It loads `reports/globalvalues_baseline.json`.
- It loads the optional profile through the existing package I/O helper.
- It calls `validate_config_package()` with `require_complete_package=True` and `require_globalvalues_profile=True`.
- Preflight remains diagnostic and never becomes an apply authority.

- [ ] **Step 1: Write strict-helper parity tests**

Create tests proving that:

1. a valid fixture package passes all four paths;
2. missing `globalvalues_baseline.json` fails all four paths;
3. missing `globalvalues_profile.json` fails all four paths;
4. a profile with non-empty `missing_overlay_keys` fails all four paths.

The core assertion is:

```python
assert build_result["status"] == "failed"
assert validate_result["status"] == "failed"
assert apply_result["status"] in {"failed", "blocked"}
assert preflight["validation_status"] == "failed"
assert preflight["package_contract_current"] is False
```

- [ ] **Step 2: Run parity tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_strict_package_validation.py tests/test_contract_preflight.py tests/test_apply_gate.py tests/test_runtime_apply.py
```

Expected: package preflight disagrees with normal validate/apply on the GlobalValues contract.

- [ ] **Step 3: Implement the shared strict helper**

Create `strict_package_validation.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.validate_package import validate_config_package


def validate_complete_package(package: str | Path) -> dict[str, Any]:
    package_path = Path(package)
    baseline = read_required_baseline(package_path)
    profile = read_optional_profile(package_path)
    return validate_config_package(
        package_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
```

- [ ] **Step 4: Replace all strict call sites**

Use `validate_complete_package(package)` in:

- `commands/apply.validate_payload`;
- `commands/apply.apply_payload`;
- `package_builder` after writing baseline and profile reports;
- `contract_preflight.build_package_contract_preflight`.

Keep existing exception-to-diagnostic conversion in preflight.

- [ ] **Step 5: Run validation and apply-boundary regressions**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_strict_package_validation.py tests/test_contract_preflight.py tests/test_apply_gate.py tests/test_apply_authority_boundary.py tests/test_runtime_apply.py
```

Expected: all pass.

- [ ] **Step 6: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/strict_package_validation.py src/hsconfig/commands/apply.py src/hsconfig/package_builder.py src/hsconfig/contract_preflight.py tests/test_strict_package_validation.py tests/test_contract_preflight.py tests/test_apply_gate.py tests/test_runtime_apply.py
git add src/hsconfig/strict_package_validation.py src/hsconfig/commands/apply.py src/hsconfig/package_builder.py src/hsconfig/contract_preflight.py tests/test_strict_package_validation.py tests/test_contract_preflight.py tests/test_apply_gate.py tests/test_runtime_apply.py
git commit -m "fix: unify strict package validation"
git push origin main
git status --short --branch
```

---

### Task 6: Add Explicit Configuration Assurance Without Changing Apply Authority

**Files:**

- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/operator_guidance.py`
- Modify: `src/hsconfig/semantic_audit.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_operator_guidance.py`
- Modify: `tests/test_semantic_audit.py`
- Modify: `tests/test_apply_authority_boundary.py`

**Interfaces:**

Every new operator summary contains:

```python
"configuration_assurance": {
    "load_safety": "validated" | "not_validated",
    "source_authority": "exact" | "archetype_only" | "partial" | "unknown",
    "semantic_closure": "closed" | "attention" | "insufficient_evidence",
    "in_client_behavior": "not_proven_by_pre_run_contract",
    "optimality_claim_allowed": False,
    "runtime_gate_impact": "none",
}
```

The block is diagnostic. Existing `runtime_apply_allowed`, `runtime_apply_mode`, and `reports/operator_summary.json` authority remain unchanged.

- [ ] **Step 1: Write assurance contract tests**

Add:

```python
def test_operator_summary_separates_pre_run_assurance_dimensions():
    summary = _strong_candidate_with_lane_counts(
        {"deck_matched_public_guide": 3}
    )

    assert summary["configuration_assurance"] == {
        "load_safety": "validated",
        "source_authority": "exact",
        "semantic_closure": "closed",
        "in_client_behavior": "not_proven_by_pre_run_contract",
        "optimality_claim_allowed": False,
        "runtime_gate_impact": "none",
}
```

Add a second case using:

```python
summary = _strong_candidate_with_lane_counts(
    {"archetype_matched_public_guide": 3}
)
assert summary["configuration_assurance"]["source_authority"] == "archetype_only"
assert summary["configuration_assurance"]["optimality_claim_allowed"] is False
```

- [ ] **Step 2: Prove assurance does not change the gate**

In `tests/test_apply_authority_boundary.py`, import `ast`, parse
`src/hsconfig/apply_gate.py`, and assert that the active gate does not read the
diagnostic block:

```python
def test_apply_gate_does_not_consume_configuration_assurance():
    tree = ast.parse(_read("src/hsconfig/apply_gate.py"))
    names = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "configuration_assurance" not in names
    assert "technical_status" in names
    assert "runtime_apply_allowed" in names
```

Existing behavior tests must continue to prove that changing
`technical_status` or `runtime_apply_allowed` blocks apply.

- [ ] **Step 3: Run operator tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_apply_authority_boundary.py
```

- [ ] **Step 4: Build the assurance projection**

Add a focused helper in `operator_summary.py`:

```python
def _configuration_assurance(
    *,
    technical_status: str,
    source_backed_status: str,
    source_lanes: list[str],
    semantic_handoff_status: str,
) -> dict[str, Any]:
    if "deck_matched_public_guide" in source_lanes:
        source_authority = "exact"
    elif "archetype_matched_public_guide" in source_lanes:
        source_authority = "archetype_only"
    elif source_backed_status == "SOURCE_BACKED_PARTIAL":
        source_authority = "partial"
    else:
        source_authority = "unknown"
    return {
        "load_safety": (
            "validated" if technical_status == "VALID_PACKAGE" else "not_validated"
        ),
        "source_authority": source_authority,
        "semantic_closure": semantic_handoff_status,
        "in_client_behavior": "not_proven_by_pre_run_contract",
        "optimality_claim_allowed": False,
        "runtime_gate_impact": "none",
    }
```

Attach it after the existing semantic-handoff projection.

- [ ] **Step 5: Project assurance into guidance and Markdown**

`operator_guidance.py` must retain `first_report_to_open` and include the unchanged assurance block. `semantic_audit.py` must render:

```markdown
## Configuration Assurance

- Load safety: `<value>`
- Source authority: `<value>`
- Semantic closure: `<value>`
- In-client behavior: `not_proven_by_pre_run_contract`
- Optimality claim allowed: `false`
- Runtime gate impact: `none`
```

- [ ] **Step 6: Run operator and apply-boundary regressions**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_apply_gate.py tests/test_apply_authority_boundary.py tests/test_runtime_apply.py
```

Expected: all pass.

- [ ] **Step 7: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/semantic_audit.py src/hsconfig/package_builder.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_apply_authority_boundary.py
git add src/hsconfig/operator_summary.py src/hsconfig/operator_guidance.py src/hsconfig/semantic_audit.py src/hsconfig/package_builder.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_apply_authority_boundary.py
git commit -m "feat: report configuration assurance dimensions"
git push origin main
git status --short --branch
```

---

### Task 7: Synchronize Operator Documentation And The Installed HSConfig Skill

**Files:**

- Modify: `docs/operator/README.md`
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `tests/test_docs_active_path.py`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Modify: `tests/test_skill_files.py`
- Modify: `tests/test_skill_sync.py`

**Interfaces:**

Docs and skill references must contain the same six durable statements:

```python
REQUIRED_SEMANTIC_CLOSURE_PHRASES = (
    "`exact_deck_matched` requires a decoded canonical deck fingerprint match.",
    "Guide-backed Mulligan claims require `exact_deck_matched`.",
    "`hero_power_transform` does not authorize aggressive GlobalValues by itself.",
    "A metadata-only CardID file is not `runtime_emitted`.",
    "Load safety does not prove in-client optimality.",
    "`configuration_assurance` is diagnostic and has `runtime_gate_impact=none`.",
)
```

- [ ] **Step 1: Add docs and skill contract tests**

Assert all six phrases appear in the operator active path and in the installed skill or a directly linked reference.

- [ ] **Step 2: Run docs tests and observe RED**

Run:

```powershell
python -m pytest -p no:cacheprovider -q tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
```

- [ ] **Step 3: Document source and Mulligan authority**

Document:

- decoded canonical deck fingerprint equality;
- exact versus archetype-only scope;
- four-part exact public-guide Mulligan gate;
- policy-backed fallback labeling;
- visible suppression reasons;
- the 40-card-guide versus 30-card-target boundary.

- [ ] **Step 4: Document Darkbishop, GlobalValues, and card surfaces**

Document:

- `SW_448 -> EX1_625t` owns one Hero Power bonus;
- no Darkbishop body priority or inferred Mulligan keep;
- only a separate exact `gameplan_posture` claim authorizes aggressive GlobalValues;
- `summon_trigger_board_engine -> OnBoardBonus`;
- reciprocal burn and state-dependent mechanics remain report-only;
- metadata-only CardID files are not runtime-emitted.

- [ ] **Step 5: Document physical-row and assurance truth**

Document:

- runtime key `(card_id, behavior_block, condition)`;
- full signature `(card_id, behavior_block, condition, value)`;
- duplicate provenance merge;
- conflicting values fail closed;
- physical/report row parity;
- the exact six `configuration_assurance` fields;
- `runtime_gate_impact=none`.

- [ ] **Step 6: Synchronize and verify the installed skill**

Run:

```powershell
python scripts/sync_installed_skill.py
python scripts/sync_installed_skill.py --check
python -m pytest -p no:cacheprovider -q tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
```

Expected:

```text
HSConfig skill is in sync
```

- [ ] **Step 7: Review, commit, and push**

Run:

```powershell
git diff --check
git diff -- docs/operator .agents/skills/hsconfig tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
git add docs/operator/README.md docs/operator/source-contract-spine.md docs/operator/guide-research-policy.md .agents/skills/hsconfig/SKILL.md .agents/skills/hsconfig/references/guide-research-policy.md .agents/skills/hsconfig/references/globalvalues-policy.md .agents/skills/hsconfig/references/card-behavior-policy.md tests/test_docs_active_path.py tests/test_operator_docs_contract_policy.py tests/test_skill_files.py tests/test_skill_sync.py
git commit -m "docs: define audited ShadowPriest closure contract"
git push origin main
git status --short --branch
```

---

### Task 8: Prove Exact And Archetype-Only Packages Read-Only

**Files:**

- Modify only the owner file from Tasks 1–7 if verification identifies a causal defect.
- Do not commit generated package output.

**Interfaces:**

- Produces full test evidence and two temporary packages.
- Performs no runtime write.
- Finishes with clean, synchronized, single-branch Git state.

- [ ] **Step 1: Run the focused remediation suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -p no:cacheprovider -q tests/test_source_document_drafter.py tests/test_claim_kind_runtime_contract.py tests/test_source_claim_lifecycle.py tests/test_mulligan_plan.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_shadowpriest_partial_source_acceptance.py tests/test_card_intent_taxonomy.py tests/test_static_semantics.py tests/test_semantic_runtime_gate.py tests/test_card_behavior_router.py tests/test_runtime_row_identity.py tests/test_compile_cardid.py tests/test_config_readiness.py tests/test_strict_package_validation.py tests/test_contract_preflight.py tests/test_operator_summary.py tests/test_operator_guidance.py tests/test_semantic_audit.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_visionai_semantic_surface_contract.py
```

Expected: all pass.

- [ ] **Step 2: Run contract and skill guardrails**

Run:

```powershell
python scripts/check_contract_guardrails.py
python scripts/sync_installed_skill.py --check
```

Expected: guardrails pass and skill is in sync.

- [ ] **Step 3: Run the complete suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
python -m pytest -q -p no:cacheprovider
```

Expected: zero failures; only documented skips.

- [ ] **Step 4: Reserve exact validated temp paths**

Run:

```powershell
$exactOut = 'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-remediation-exact-20260726'
$partialOut = 'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-remediation-archetype-20260726'
$tempRoot = [System.IO.Path]::GetFullPath('C:\Users\darbo\AppData\Local\Temp')
foreach ($target in @($exactOut, $partialOut)) {
    $resolved = [System.IO.Path]::GetFullPath($target)
    if (-not $resolved.StartsWith(
        $tempRoot + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Unexpected output path: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        throw "Output already exists: $resolved"
    }
}
```

- [ ] **Step 5: Generate the exact fixture without apply**

Run:

```powershell
python -m hsconfig.cli configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "$exactOut" --online-source --auto-source --source-url "https://example.test/shadowpriest-exact" --source-fixture-url-map-json "tests\fixtures\source_pages\shadowpriest_source_url_map.json" --current-date "2026-07-26" --json
python -m hsconfig.cli validate --package "$exactOut\04_package" --json
python -m hsconfig.cli contract-preflight --package "$exactOut\04_package" --json
python -m hsconfig.cli runtime-match --package "$exactOut\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Expected:

- configure succeeds;
- strict validation passes;
- `package_contract_current=true`;
- source authority is exact;
- `runtime_write_performed=false`;
- runtime-match may report differences but performs no write.

- [ ] **Step 6: Generate the archetype-only fixture without apply**

Run:

```powershell
python -m hsconfig.cli configure --deck-name "ShadowPriest" --deck-code "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=" --runtime-root "C:\Users\darbo\Desktop\HS" --out "$partialOut" --online-source --auto-source --source-url "https://example.test/shadowpriest-archetype" --source-fixture-url-map-json "tests\fixtures\source_pages\shadowpriest_source_url_map.json" --current-date "2026-07-26" --json
python -m hsconfig.cli validate --package "$partialOut\04_package" --json
python -m hsconfig.cli contract-preflight --package "$partialOut\04_package" --json
python -m hsconfig.cli runtime-match --package "$partialOut\04_package" --runtime-root "C:\Users\darbo\Desktop\HS" --json
```

Expected:

- configure and validation pass;
- source authority is archetype-only or partial;
- `SOURCE_BACKED_STRONG` is absent;
- source-backed Mulligan keep count is zero;
- policy fallback holds, if any, are labeled;
- aggressive GlobalValues `changed_keys` is empty;
- `runtime_write_performed=false`.

- [ ] **Step 7: Assert physical seven/nine invariants for both packages**

Run this script for both package paths:

```powershell
$invariant = @'
import json
import sys
from pathlib import Path

package = Path(sys.argv[1])
deck = package / "CustomConfig" / "shadowpriest"
reports = package / "reports"
expected = {
    ("DS1_233", "BeforePlayCardBonus", "*", "12"),
    ("REV_290", "BeforePlayCardBonus", "*", "8"),
    ("SW_446", "OnBoardBonus", "*", "10"),
    ("SW_448", "BeforeUseHeroPowerBonus", "*", "10"),
    ("TOY_381", "OnBoardBonus", "*", "8"),
    ("TOY_518", "OnBoardBonus", "*", "8"),
    ("WON_065", "OnBoardBonus", "*", "8"),
}
report_only = {
    "CFM_637",
    "DRG_056",
    "GVG_009",
    "NX2_019",
    "SCH_514",
    "SW_444",
    "VAC_419",
    "VAC_512",
    "YOD_032",
}
signatures = []
for path in sorted(deck.glob("*.json")):
    if path.name in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
        continue
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    card_id = str(payload["GameCardId"])
    for block, block_payload in payload.items():
        if block in {"GameCardId", "ConfigComment"}:
            continue
        for row in block_payload.get("values", []):
            signatures.append(
                (
                    card_id,
                    block,
                    str(row.get("condition", "*")),
                    str(row["value"]),
                )
            )
    if card_id in report_only:
        assert set(payload) == {"GameCardId", "ConfigComment"}, card_id

assert set(signatures) == expected
assert len(signatures) == len(expected)
readiness = json.loads(
    (reports / "per_card_config_readiness_report.json").read_text(
        encoding="utf-8"
    )
)
operator = json.loads(
    (reports / "operator_summary.json").read_text(encoding="utf-8")
)
assert readiness["summary"]["runtime_emitted"] == 7
assert readiness["summary"]["report_only_supported"] == 9
assert operator["configuration_assurance"]["optimality_claim_allowed"] is False
assert operator["configuration_assurance"]["runtime_gate_impact"] == "none"
print(f"Seven/nine invariant passed: {package}")
'@
$invariant | python - "$exactOut\04_package"
$invariant | python - "$partialOut\04_package"
```

- [ ] **Step 8: Assert the archetype-only authority boundary**

Run:

```powershell
@'
import json
import sys
from pathlib import Path

package = Path(sys.argv[1])
reports = package / "reports"
operator = json.loads(
    (reports / "operator_summary.json").read_text(encoding="utf-8")
)
profile = json.loads(
    (reports / "globalvalues_profile.json").read_text(encoding="utf-8")
)
mulligan = json.loads(
    (reports / "mulligan_plan_report.json").read_text(encoding="utf-8")
)
assert operator["configuration_assurance"]["source_authority"] in {
    "archetype_only",
    "partial",
}
assert operator["source_backed_status"] != "SOURCE_BACKED_STRONG"
assert profile["changed_keys"] == []
assert mulligan["quality"]["source_backed_keep_rule_count"] == 0
for row in mulligan["rules"]:
    if row["action"] == "hold":
        assert row["source_type"] == "policy_backed_autonomous_mulligan"
print(f"Archetype-only authority invariant passed: {package}")
'@ | python - "$partialOut\04_package"
```

- [ ] **Step 9: Remove only the two validated temp directories**

Run:

```powershell
$allowed = @(
    'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-remediation-exact-20260726',
    'C:\Users\darbo\AppData\Local\Temp\hsconfig-shadowpriest-remediation-archetype-20260726'
)
foreach ($target in @($exactOut, $partialOut)) {
    $resolved = [System.IO.Path]::GetFullPath($target)
    if ($resolved -notin $allowed) {
        throw "Unexpected removal target: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        [System.IO.Directory]::Delete($resolved, $true)
    }
    if (Test-Path -LiteralPath $resolved) {
        throw "Temporary output still exists: $resolved"
    }
}
```

- [ ] **Step 10: Run final one-version checks**

Run:

```powershell
python scripts/sync_installed_skill.py --check
python scripts/check_hsconfig_currentness.py --cwd . --json
git diff --check
git status --short --branch
git rev-list --left-right --count origin/main...main
git branch --format='%(refname:short)'
git ls-remote --heads origin
gh pr list --repo Teufelsboy/HSConfig --state open --json number,title,headRefName,baseRefName,url
```

Expected:

- installed skill in sync;
- clean `main`;
- `origin/main...main` is `0 0`;
- only branch `main`;
- no open pull requests;
- both temporary directories absent.

- [ ] **Step 11: Repair verification failures at their owning task**

If verification fails:

1. identify the earliest owning task;
2. add or tighten that task's failing test;
3. observe RED;
4. make the minimum causal correction only in that task's files;
5. observe the focused GREEN result;
6. rerun Tasks 8 Steps 1–10;
7. commit with the owning task's message and push `main`.

Do not make an omnibus verification-fix commit and do not create an empty commit.

---

## Final Acceptance Matrix

| Contract | Exact-source fixture | Archetype-only fixture |
|---|---:|---:|
| Canonical target identity | Pass | Pass |
| Guide scope | `exact_deck_matched` | `archetype_matched` or partial |
| Strict validation | Pass | Pass |
| Preflight parity | Pass | Pass |
| Runtime write | `false` | `false` |
| Guide-backed Mulligan | Allowed | Forbidden |
| Policy-backed fallback | Optional and labeled | Optional and labeled |
| Darkbishop Mulligan keep | Absent | Absent |
| Darkbishop body priority | Absent | Absent |
| Darkbishop Hero Power row | Present once | Present once |
| Aggressive GlobalValues | Only with exact `gameplan_posture` | Baseline |
| Active CardID cards | 7 | 7 |
| Report-only cards | 9 | 9 |
| Physical CardID rows | 7 | 7 |
| Duplicate signatures | 0 | 0 |
| Conflicting values | 0 | 0 |
| Physical/report parity | Exact | Exact |
| `SOURCE_BACKED_STRONG` | Allowed only with complete exact closure | Forbidden |
| `optimality_claim_allowed` | `false` | `false` |
| Apply performed by this plan | Never | Never |

## Out Of Scope

- Applying either generated package.
- Writing or copying anything into the HearthRanger runtime.
- HSTuner.
- Gameplay, win-rate, matchup, or optimality claims.
- Numeric low-health or opponent-specific tuning.
- New condition atoms for graveyard state, damage this turn, current cost, exact lethal, target death, or location activation.
- New VisionAI keys or surfaces.
- Moving `hero_power_transform` away from CardID-linked ownership.
- Treating a different 40-card guide as exact evidence for the 30-card target.

## Completion Criteria

Implementation is complete only when:

1. Tasks 1–8 are checked.
2. Every behavioral task observed its focused RED test before implementation.
3. Every focused suite passes.
4. The complete suite has zero failures.
5. Contract guardrails pass.
6. The installed HSConfig skill is synchronized.
7. Exact and archetype-only packages pass strict validation.
8. Validate, apply, build, and preflight share the same strict package contract.
9. Runtime-match performs no write.
10. The exact seven-active/nine-report-only physical contract holds.
11. Duplicate and conflicting physical rows are zero.
12. Exact-guide Mulligan authority works and archetype-only guide authority is visibly suppressed.
13. `configuration_assurance` explicitly denies in-client proof and optimality.
14. Temporary packages are deleted.
15. Git is clean on the sole `main` branch, local and origin are `0 0`, and no pull request is open.
