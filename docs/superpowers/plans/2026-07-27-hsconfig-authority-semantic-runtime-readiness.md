# HSConfig Authority, Semantic, and Runtime Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the current HSConfig authority gaps, make every emitted VisionAI row traceable to the correct Hearthstone entity and expressible condition, and produce current package evidence for the twelve audited decks without claiming gameplay optimality or writing to the live runtime.

**Architecture:** Preserve the existing deck-to-package pipeline and harden it at four boundaries: source capability consumption, package derivation, semantic lowering, and operator readiness. Unsupported or insufficiently conditioned Hearthstone behavior remains visible in diagnostics but emits no physical VisionAI row; sideboards and linked runtime entities become first-class explainability records; final package authority remains exclusively in `reports/operator_summary.json`.

**Tech Stack:** Python 3.11+, `pytest`, deterministic JSON/SHA-256 receipts, Hearthstone deck-code decoding, existing `hsconfig` CLI/package builders, PowerShell, Git on the sole `main` branch.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the existing `main` branch. Do not create a branch, worktree, pull request, shadow checkout, or second implementation version.
- Audit baseline is commit `0170e48702685d223b5742fd75c6724d8a47ba35`; implementation starts from its descendant commit containing this plan.
- Before every task run `git fetch --all --prune --tags`, `git remote prune origin`, `git status --short --branch`, `git rev-parse HEAD`, and `git rev-parse origin/main`. Stop if the worktree contains changes outside the current task or `main` diverges from `origin/main`.
- Use test-driven development: add the failing regression, confirm the intended failure, implement the smallest coherent change, run the targeted suite, inspect the diff, request two-stage review, then commit and fast-forward-push `main` before beginning the next task.
- Use exactly one writing subagent per task. After implementation, use a specification reviewer and then a code-quality reviewer. Return fixes to the same implementation subagent until both reviews pass.
- Do not invoke HSTuner, parse replays, tune from win rate, or add runtime-analysis responsibilities to HSConfig.
- Do not run `hsconfig apply`, `configure --apply`, or write anything under `C:\Users\darbo\Desktop\HS`.
- Generated acceptance packages must use a uniquely named directory under `$env:TEMP`; remove that directory after inspection. Do not commit `outputs/`, runtime logs, replay files, caches, coverage artifacts, or private evidence.
- Preserve exact main-deck CardIDs/counts, hero DBF IDs, sideboard owner/module identities, full GlobalValues profiling, per-card coverage, strict JSON validation, and row-level provenance.
- `reports/operator_summary.json` remains the sole human-facing apply authority. Matrix rows, fixtures, readiness reports, and historical package summaries remain diagnostic.
- Captured, fixture, manual, legacy, stale, or seed-only source material must never mint a strategic receipt or runtime-apply authority.
- Do not introduce a new VisionAI condition atom in this plan. When a required Hearthstone condition cannot be represented with the existing documented vocabulary, suppress the physical row with a stable reason and keep the intended behavior report-visible.
- Do not change tuning numbers merely to make a test pass. Existing values may survive only when their owner, surface, condition, and authority are correct.
- Use `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` for verification commands.
- Stable failures must expose a machine-readable reason code. Tests assert reason codes and invariant fields, not entire prose messages.
- This plan proves technical and static semantic correctness only. `RUNTIME_SAMPLED`, gameplay improvement, matchup optimality, and win-rate improvement remain out of scope.

---

## Task 1: Bind Linked Runtime Ownership Into Strict Package Authority

**Files:**

- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/package_derivation_receipt.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Test: `tests/test_strict_package_validation.py`
- Test: `tests/test_apply_authority_boundary.py`
- Test: `tests/test_runtime_apply.py`
- Test: `tests/test_runtime_apply_receipts.py`

**Interfaces:**

- Consumes: `reports/card_behavior_plan_report.json` and the existing linked-owner rows with `source_card_id`, `runtime_card_id`, `link_kind`, `behavior_block`, and `meaningful_runtime_surface`.
- Produces: `linked_runtime_owner_projection(report: Mapping[str, Any]) -> list[dict[str, str]]`, derivation receipt schema version `2`, and stable validation codes `linked_runtime_owner_evidence_missing` and `linked_runtime_owner_evidence_invalid`.

- [ ] **Step 1: Add missing/corrupt report regressions**

Add tests that start from the existing valid curated `SW_448 -> EX1_625t` package fixture:

```python
@pytest.fixture
def linked_owner_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {"rows": [{
            "claim_id": "claim_darkbishop",
            "card_id": "SW_448",
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
            "behavior_block": "BeforeUseHeroPowerBonus",
            "meaningful_runtime_surface": True,
        }]},
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )
    return package


@pytest.mark.parametrize("mutation", ["remove", "invalid_json", "non_object"])
def test_linked_owner_package_fails_closed_without_valid_plan_report(
    linked_owner_package: Path,
    mutation: str,
) -> None:
    path = linked_owner_package / "reports" / "card_behavior_plan_report.json"
    if mutation == "remove":
        path.unlink()
    elif mutation == "invalid_json":
        path.write_text("{", encoding="utf-8")
    else:
        path.write_text("[]", encoding="utf-8")

    report = validate_complete_package(linked_owner_package)

    assert report["status"] == "failed"
    assert any(
        code in report["errors"]
        for code in {
            "linked_runtime_owner_evidence_missing",
            "linked_runtime_owner_evidence_invalid",
        }
    )
```

Add equivalent tests proving `evaluate_apply_gate`, `plan_apply_package`, and `apply_package` block before any runtime directory or write receipt is created.

- [ ] **Step 2: Confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_strict_package_validation.py `
  tests/test_apply_authority_boundary.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_apply_receipts.py
```

Expected: the new remove/corrupt-report cases pass the current fail-open validator or fail only after reaching a later boundary.

- [ ] **Step 3: Add one canonical linked-owner projection**

Move relation extraction behind a public helper in `strict_package_validation.py`:

```python
def linked_runtime_owner_projection(
    behavior_plan: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Return the canonical, sorted linked-owner authority projection."""
```

Each returned row must contain exactly:

```python
{
    "source_card_id": source_card_id,
    "runtime_card_id": runtime_card_id,
    "link_kind": link_kind,
    "semantic_surface": semantic_surface,
    "behavior_block": behavior_block,
}
```

Missing, unreadable, or non-object plan reports must add the stable failure code instead of returning `[]`. A valid report with no linked relations remains valid and projects to `[]`.

- [ ] **Step 4: Include the evidence in derivation receipt v2**

Set:

```python
DERIVATION_RECEIPT_SCHEMA_VERSION = 2
```

Add `reports/card_behavior_plan_report.json` to `_AUTHORITATIVE_JSON_PATHS`. Canonicalize only authority-bearing fields by including the sorted `linked_runtime_owner_projection` in the receipt; do not hash timestamps, prose-only diagnostics, or filesystem metadata.

Expected receipt shape:

```python
{
    "schema_version": 2,
    "inputs": {...},
    "linked_runtime_owners": [...],
    "runtime_files": {...},
}
```

Old schema-1 receipts must fail with `package_derivation_receipt_schema_unsupported`; they must not be silently upgraded during apply.

- [ ] **Step 5: Verify every apply surface fails before mutation**

Add assertions that the four paths share the same result:

```python
assert gate["runtime_apply_allowed"] is False
assert gate["reasons"][0]["code"] in {
    "linked_runtime_owner_evidence_missing",
    "linked_runtime_owner_evidence_invalid",
    "package_derivation_mismatch",
}
assert not runtime_target.exists()
assert not write_receipt.exists()
```

- [ ] **Step 6: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_strict_package_validation.py `
  tests/test_apply_authority_boundary.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_apply_receipts.py `
  tests/test_compile_cardid.py
git diff --check
git add src/hsconfig/strict_package_validation.py `
  src/hsconfig/package_derivation_receipt.py `
  src/hsconfig/apply_gate.py `
  src/hsconfig/runtime_apply.py `
  tests/test_strict_package_validation.py `
  tests/test_apply_authority_boundary.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_apply_receipts.py
git commit -m "fix: bind linked runtime ownership into package authority"
```

---

## Task 2: Make Source-Authority Capabilities Scoped, One-Shot, and Atomic

**Files:**

- Modify: `src/hsconfig/internal_source_authority.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/preconfig_context.py`
- Modify: the research entrypoint that currently calls `trusted_source_documents_from_handoff`
- Test: `tests/test_internal_source_authority_handoff.py`
- Test: `tests/test_configure_handoff_contract.py`
- Test: `tests/test_configure_online_source.py`

**Interfaces:**

- Consumes: the acquisition-issued document handoff.
- Produces:

```python
def split_source_documents_handoff(
    handoff: InternalSourceAuthorityHandoff,
) -> tuple[InternalSourceAuthorityHandoff, InternalSourceAuthorityHandoff]:
    """Consume one document capability and issue research/prepare capabilities."""

def trusted_source_documents_from_handoff(
    handoff: InternalSourceAuthorityHandoff | None,
    *,
    consumer: Literal["research", "prepare"],
) -> list[dict[str, Any]] | None:
    """Validate and consume the capability for exactly one named consumer."""
```

- [ ] **Step 1: Add replay, cross-consumer, and failure-atomicity tests**

Cover all of these cases:

```python
research_handoff, prepare_handoff = split_source_documents_handoff(document_handoff)
assert trusted_source_documents_from_handoff(
    research_handoff, consumer="research"
) == documents
with pytest.raises(ValueError, match="source_authority_handoff_replayed"):
    trusted_source_documents_from_handoff(
        research_handoff, consumer="research"
    )
with pytest.raises(ValueError, match="source_authority_consumer_mismatch"):
    trusted_source_documents_from_handoff(
        prepare_handoff, consumer="research"
    )
assert trusted_source_documents_from_handoff(
    prepare_handoff, consumer="prepare"
) == documents
```

Add a cyclic document and a list subclass whose `__deepcopy__` raises `RuntimeError("copy-bomb")`. After each failed operation, assert the original token state and registry membership are unchanged and a retry with a valid payload succeeds.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_internal_source_authority_handoff.py `
  tests/test_configure_handoff_contract.py
```

Expected: document reuse succeeds, consumer mismatch is not represented, and copy failure burns at least one current token.

- [ ] **Step 3: Add prepared-but-unregistered successor tokens**

Add a `consumer` field to the handoff and token MAC payload. Split token creation into:

```python
def _prepare_authority_token(...) -> _AuthorityToken:
    """Construct and sign without registering or mutating predecessor state."""

def _register_authority_token(token: _AuthorityToken) -> None:
    _ACTIVE_ORIGINAL_TOKENS[token.nonce] = token
```

Create `_safe_deepcopy(payload, *, failure_reason)` which catches `Exception` from `deepcopy` and raises `ValueError(failure_reason)` while preserving the original exception as `__cause__`.

- [ ] **Step 4: Commit authority transitions only after fallible work**

For search consumption, document issuance, handoff splitting, and consumer extraction:

1. validate type, stage, token, registry, fingerprints, and consumer;
2. create all deep copies;
3. compute all fingerprints and MACs;
4. prepare successor tokens without registration;
5. perform the final predecessor pop/state transition and successor registration without further copying or canonicalization.

Use stable failures:

- `source_authority_payload_copy_failed`
- `source_authority_handoff_lineage_mismatch`
- `source_authority_consumer_mismatch`
- `source_authority_handoff_replayed`

- [ ] **Step 5: Wire configure to distinct consumers**

Immediately after online acquisition returns the document handoff:

```python
research_handoff, prepare_handoff = split_source_documents_handoff(
    source_authority_handoff
)
```

Pass only `research_handoff` to `research_deck_for_configure` and only `prepare_handoff` to `prepare_package_payload`. The research and preconfiguration entrypoints must request their exact consumer name.

- [ ] **Step 6: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_internal_source_authority_handoff.py `
  tests/test_configure_handoff_contract.py `
  tests/test_configure_online_source.py `
  tests/test_configure_auto_source.py
git diff --check
git add src/hsconfig/internal_source_authority.py `
  src/hsconfig/commands/configure.py `
  src/hsconfig/preconfig_context.py `
  tests/test_internal_source_authority_handoff.py `
  tests/test_configure_handoff_contract.py `
  tests/test_configure_online_source.py
git commit -m "fix: make source authority handoffs scoped and atomic"
```

---

## Task 3: Carry Sideboard Identity Through Metadata and Readiness

**Files:**

- Modify: `src/hsconfig/deckstring_decode.py`
- Modify: `src/hsconfig/preconfig_context.py`
- Modify: `src/hsconfig/card_metadata.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Test: `tests/test_deckstring_decode.py`
- Test: `tests/test_card_metadata.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_multideck_source_backed_e2e.py`

**Interfaces:**

- Consumes: `deck_identity["sideboards"]`.
- Produces: analysis records with `deck_zone: "main" | "sideboard"`, `sideboard_owner_card_id`, and `runtime_eligible: bool`.

- [ ] **Step 1: Add the MechPala regression**

Use the exact audited deck code and assert:

```python
assert decoded["card_count"] == 30
assert decoded["sideboard_count"] == 3
assert decoded["sideboards"][0]["owner_card_id"] == "TOY_330"
assert {
    row["card_id"] for row in decoded["sideboards"][0]["cards"]
} == {"TOY_330t95", "TOY_330t98", "TOY_330t11"}
```

Build preconfiguration context and assert all three module IDs appear in metadata, readiness, and explainability with `deck_zone == "sideboard"`, while the main-deck count remains 30.

Add a characterization test that the exact supplied MechPala and PirateDH strings decode without callers manually adding Base64 padding.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_deckstring_decode.py `
  tests/test_card_metadata.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py
```

Expected: decode identity passes, but sideboard modules are absent from downstream metadata/readiness/explainability.

- [ ] **Step 3: Normalize an analysis-only card collection**

Add:

```python
def analysis_cards_from_deck_identity(
    deck_identity: Mapping[str, Any],
) -> list[dict[str, Any]]:
```

Main-deck rows receive `deck_zone="main"` and `runtime_eligible=True`. Sideboard module rows receive `deck_zone="sideboard"`, their owner, and `runtime_eligible=False` until a separate runtime-owner rule explicitly authorizes them.

Hydrate metadata from this combined collection, but continue compiling ordinary CardID files from the main deck plus separately authorized linked runtime entities. Do not inflate `card_count`, `unique_card_count`, or the main-deck coverage denominator.

- [ ] **Step 4: Make sideboard ownership visible**

Readiness and explainability must include:

```python
{
    "card_id": "TOY_330t95",
    "deck_zone": "sideboard",
    "sideboard_owner_card_id": "TOY_330",
    "runtime_surfaces": [],
    "readiness_lane": "report_only_supported",
    "first_missing_link": "none",
}
```

The owner `TOY_330` must receive the role `sideboard_owner`; its printed zero cost must never qualify it as a lowest-curve mulligan fallback.

- [ ] **Step 5: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_deckstring_decode.py `
  tests/test_card_metadata.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_autonomous_mulligan_policy.py
git diff --check
git add src/hsconfig/deckstring_decode.py `
  src/hsconfig/preconfig_context.py `
  src/hsconfig/card_metadata.py `
  src/hsconfig/config_readiness.py `
  src/hsconfig/source_to_runtime_explainability.py `
  tests/test_deckstring_decode.py `
  tests/test_card_metadata.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py
git commit -m "feat: preserve sideboard identity through readiness"
```

---

## Task 4: Prevent Policy Mulligan From Overriding Explicit Source Gaps

**Files:**

- Modify: `src/hsconfig/autonomous_mulligan_policy.py`
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `src/hsconfig/source_claim_gap_report.py`
- Test: `tests/test_autonomous_mulligan_policy.py`
- Test: `tests/test_boarlock_fracking_source_decision.py`
- Test: `tests/test_kingslayer_quick_pick_source_decision.py`
- Test: `tests/test_archetype_source_fixtures.py`
- Test: `tests/test_multideck_source_backed_e2e.py`

**Interfaces:**

- Consumes: suppressed source Mulligan claims, explicit stop-condition cards, and `sideboard_owner`.
- Produces: `policy_veto_card_ids: Mapping[str, str]`, passed to `build_policy_backed_mulligan_rules(..., excluded_card_reasons=...)`.

- [ ] **Step 1: Add three named regressions**

Assert:

```python
def prepared_mulligan_plan(
    tmp_path: Path,
    deck_name: str,
) -> dict[str, Any]:
    deck = next(
        row for row in load_archetype_matrix()
        if row["deck_name"] == deck_name
    )
    prepared = prepare_fixture_deck(tmp_path / deck_name, deck)
    assert prepared["exit_code"] == 0
    return read_json(
        prepared["out"] / "reports" / "mulligan_plan_report.json"
    )


def hold_cards(plan: Mapping[str, Any]) -> set[str]:
    return {
        str(row["card"])
        for row in plan["rules"]
        if row.get("action") == "hold"
        and row.get("selector_kind", "single_card") != "wildcard"
    }


boarlock_plan = prepared_mulligan_plan(tmp_path, "Boarlock")
kingslayer_plan = prepared_mulligan_plan(tmp_path, "Kingslayer")
mechpala_plan = prepared_mulligan_plan(tmp_path, "MechPala")
assert "WW_092" not in hold_cards(boarlock_plan)
assert "DEEP_014" not in hold_cards(kingslayer_plan)
assert "TOY_330" not in hold_cards(mechpala_plan)
```

Expected suppression reasons:

- `explicit_source_gap_requires_resolution`
- `explicit_source_gap_requires_resolution`
- `sideboard_owner_not_curve_anchor`

Also assert ordinary safe fallback remains available for a deck with no explicit source conflict.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_autonomous_mulligan_policy.py `
  tests/test_boarlock_fracking_source_decision.py `
  tests/test_kingslayer_quick_pick_source_decision.py `
  tests/test_multideck_source_backed_e2e.py
```

- [ ] **Step 3: Build a single policy-veto projection**

In `mulligan_plan.py`, collect every exact card ID that has:

- a suppressed `mulligan_keep` or `mulligan_discard` claim;
- a documented exact-card Mulligan stop condition;
- a `sideboard_owner` role;
- a start-of-game non-hand effect without independent exact Mulligan authority.

Pass the reasons through `excluded_card_reasons`. Do not hardcode deck names in `autonomous_mulligan_policy.py`; card IDs come from normalized claims, gaps, and metadata.

- [ ] **Step 4: Preserve source visibility**

The Mulligan report must show both:

```python
{
    "card": "WW_092",
    "policy_lane": "source_veto",
    "reason": "explicit_source_gap_requires_resolution",
}
```

and the original suppressed source-claim reason. No wildcard rule may reintroduce a hold.

- [ ] **Step 5: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_autonomous_mulligan_policy.py `
  tests/test_boarlock_fracking_source_decision.py `
  tests/test_kingslayer_quick_pick_source_decision.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_multideck_source_backed_e2e.py
git diff --check
git add src/hsconfig/autonomous_mulligan_policy.py `
  src/hsconfig/mulligan_plan.py `
  src/hsconfig/source_claim_gap_report.py `
  tests/test_autonomous_mulligan_policy.py `
  tests/test_boarlock_fracking_source_decision.py `
  tests/test_kingslayer_quick_pick_source_decision.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_multideck_source_backed_e2e.py
git commit -m "fix: honor explicit source gaps in mulligan policy"
```

---

## Task 5: Make GlobalValues Emission Exactly Match Its Authority Matrix

**Files:**

- Modify: `src/hsconfig/compile_globalvalues.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/globalvalues_authority.py`
- Test: `tests/test_compile_globalvalues.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_multideck_source_backed_e2e.py`
- Test: `tests/test_cli.py`

**Interfaces:**

- Consumes: canonical `global_values_authority_matrix["allowed_step1_overlays"]`.
- Produces: exact equality among emitted non-baseline keys, `generated_overlay_keys`, `expected_overlay_keys`, and authorized overlay keys.

- [ ] **Step 1: Add ImbueMage and Boarlock regressions**

For a contract whose matrix contains only:

```python
{"key": "baseline", "overlay": "none", "operation": "none"}
```

assert:

```python
assert "MyHeroPowerValue" not in result["config"]
assert result["profile"]["generated_overlay_keys"] == []
assert result["profile"]["expected_overlay_keys"] == []
```

Add a positive ShadowPriest-style case with an explicit allowed `MyHeroPowerValue` row and assert the key is generated once with its authority reason and claim ID.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_compile_globalvalues.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py
```

- [ ] **Step 3: Remove the hidden aggression-profile candidate path**

When `allowed_step1_overlays` is present, calculate `generated_overlay_candidates` only from allowed matrix rows. Do not update it from `aggression_profile["global_value_overlays"]` or `mechanic_priorities`.

Add an invariant result:

```python
profile["authority_parity"] = {
    "authorized_overlay_keys": authorized_keys,
    "emitted_overlay_keys": emitted_keys,
    "status": "matched" if authorized_keys == emitted_keys else "mismatch",
}
```

Strict package validation must reject `status == "mismatch"`.

- [ ] **Step 4: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_compile_globalvalues.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_cli.py
git diff --check
git add src/hsconfig/compile_globalvalues.py `
  src/hsconfig/package_builder.py `
  src/hsconfig/globalvalues_authority.py `
  tests/test_compile_globalvalues.py `
  tests/test_config_readiness.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_cli.py
git commit -m "fix: enforce globalvalues authority parity"
```

---

## Task 6: Correct Shared ShadowPriest and Summon-Engine Semantics

**Files:**

- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/runtime_entity_owner.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_cardid.py`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Test: `tests/test_configure_online_source.py`
- Test: `tests/test_config_quality_contract.py`

**Interfaces:**

- Consumes: existing intents `reciprocal_hero_burn`, `summon_trigger_board_engine`, and `hero_power_transform`.
- Produces: report-only reciprocal burn, one physical summon-engine row, and exact `SW_448 -> EX1_625t` owner routing.

- [ ] **Step 1: Add exact semantic assertions**

```python
def physical_blocks(
    card_files: Mapping[str, Mapping[str, Any]],
    card_id: str,
) -> list[str]:
    payload = card_files.get(f"{card_id}.json", {})
    return sorted(
        block
        for block in payload
        if is_supported_card_behavior_block(block)
    )


shadow = next(
    row for row in load_archetype_matrix()
    if row["deck_name"] == "ShadowPriest"
)
prepared = prepare_fixture_deck(tmp_path, shadow)
deck_dir = next((prepared["out"] / "CustomConfig").iterdir())
card_files = {
    path.name: read_json(path)
    for path in deck_dir.glob("*.json")
}
assert physical_blocks(card_files, "GVG_009") == []
assert physical_blocks(card_files, "VAC_419") == []
assert physical_blocks(card_files, "TOY_518") == ["OnBoardBonus"]
assert physical_blocks(card_files, "WON_065") == ["OnBoardBonus"]
assert physical_blocks(card_files, "SW_448") == []
assert physical_blocks(card_files, "EX1_625t") == ["BeforeUseHeroPowerBonus"]
```

Also assert each emitted action has one row only and source provenance still names the original source card.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_configure_online_source.py
```

- [ ] **Step 3: Route by semantic intent, not card-specific duplication**

Implement these rules:

- `reciprocal_hero_burn` -> suppression reason `reciprocal_burn_report_only`;
- `summon_trigger_board_engine` -> exactly one `OnBoardBonus` row owned by the persistent minion;
- `hero_power_transform` -> source remains `SW_448`, runtime owner is the exact linked entity `EX1_625t`, link kind is `hero_power_transform`, and the source file receives no Hero Power block.

Deduplicate rows by `(runtime_card_id, behavior_block, condition, value)` before compilation.

- [ ] **Step 4: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_configure_online_source.py `
  tests/test_config_quality_contract.py `
  tests/test_strict_package_validation.py
git diff --check
git add src/hsconfig/card_intent_taxonomy.py `
  src/hsconfig/card_behavior_surface_router.py `
  src/hsconfig/runtime_entity_owner.py `
  src/hsconfig/compile_cardid.py `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_configure_online_source.py `
  tests/test_config_quality_contract.py
git commit -m "fix: align shadow and summon engine runtime ownership"
```

---

## Task 7: Suppress Rows Whose Hearthstone Conditions Cannot Be Expressed

**Files:**

- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/semantic_runtime_gate.py`
- Modify: `src/hsconfig/card_intent_taxonomy.py`
- Modify: `src/hsconfig/config_readiness.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_semantic_runtime_negative_boundaries.py`
- Test: `tests/test_archetype_source_fixtures.py`
- Test: `tests/test_multideck_source_backed_e2e.py`

**Interfaces:**

- Consumes: card type, semantic intent, target scope, runtime block, and existing lowered condition.
- Produces: `semantic_runtime_decision(...) -> SurfaceGateDecision` with stable reasons.

- [ ] **Step 1: Add parameterized negative-boundary cases**

Use the audited cases:

```python
CASES = [
    ("WW_336", "BeforePlayCardBonus", "variable_cost_condition_not_encoded"),
    ("WW_051", "BeforePlayCardBonus", "symmetric_board_condition_not_encoded"),
    ("CATA_479", "BeforePlayCardBonus", "shatter_state_not_encoded"),
    ("CS2_073", "BeforePlayCardBonus", "combo_target_condition_not_encoded"),
    ("DMF_519", "BeforeBattlecryTargetBonus", "combo_count_condition_not_encoded"),
    ("TTN_922", "BeforePlayCardBonus", "hand_position_condition_not_encoded"),
    ("GVG_029", "BeforePlayCardBonus", "symmetric_summon_condition_not_encoded"),
    ("CS2_038", "BeforeBattlecryTargetBonus", "spell_cannot_use_battlecry_target"),
    ("WON_335", "BeforeBattlecryTargetBonus", "spell_cannot_use_battlecry_target"),
    ("TOY_877", "OnBoardBonus", "spell_cannot_own_on_board"),
    ("JAM_028", "BeforePlayCardBonus", "health_cost_condition_not_encoded"),
    ("TTN_954", "OnBoardBonus", "spell_cannot_own_on_board"),
    ("NX2_006", "BeforePhysicalAttackBonus", "trigger_owner_does_not_attack"),
    ("VAC_938", "BeforePhysicalAttackBonus", "buff_target_owner_mismatch"),
    ("VAC_701", "BeforePhysicalAttackBonus", "battlecry_owner_does_not_attack"),
]
```

For every case, assert no physical row is emitted, the original claim remains in `suppressed`, and readiness maps it to `needs_condition_lowering`, `needs_target_scope`, or `semantic_surface_not_expressible`.

- [ ] **Step 2: Add Discolock regressions**

Assert no generic `InHandPlayPriority` exists solely for coverage. Assert `CATA_490`, `TLC_603`, and `VAC_940` do not use Battlecry-target blocks; `RLK_532` and `WON_098` receive no manual-play bonus from discard-payoff text; generic Discover without option identity remains report-only.

- [ ] **Step 3: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_card_behavior_router.py `
  tests/test_semantic_runtime_negative_boundaries.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_multideck_source_backed_e2e.py
```

- [ ] **Step 4: Implement generic semantic gates**

Implement type- and intent-based gates, not a per-deck allowlist:

- spells cannot own `OnBoardBonus`;
- spells cannot use `BeforeBattlecryTargetBonus`;
- attack bonuses require the runtime owner to perform the evaluated attack;
- target bonuses require a compatible explicit target scope;
- Combo, cards-played count, hand position, symmetric-board, variable-cost, Health-cost, Shatter, Imbue, Outcast, Discover, Dredge, and Choose-One behaviors require a fully lowered existing condition or option identity;
- absent representation produces suppression, never an unconditional row.

Keep exact card IDs only in regression fixtures. Production logic uses normalized metadata and semantic intents.

- [ ] **Step 5: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_card_behavior_router.py `
  tests/test_semantic_runtime_negative_boundaries.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_compile_cardid.py `
  tests/test_config_readiness.py
git diff --check
git add src/hsconfig/card_behavior_surface_router.py `
  src/hsconfig/semantic_runtime_gate.py `
  src/hsconfig/card_intent_taxonomy.py `
  src/hsconfig/config_readiness.py `
  tests/test_card_behavior_router.py `
  tests/test_semantic_runtime_negative_boundaries.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_multideck_source_backed_e2e.py
git commit -m "fix: suppress unexpressible hearthstone conditions"
```

---

## Task 8: Make Readiness and Explainability Match Physical Output

**Files:**

- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/config_usefulness.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_config_usefulness.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_multideck_source_backed_e2e.py`

**Interfaces:**

- Consumes: final compiled `Mulligan.json`, `GlobalValues.json`, `Combo.json`, CardID file payloads, sideboard analysis rows, and linked-owner projection.
- Produces: one canonical per-card surface ledger used by readiness, usefulness, explainability, and operator summary.

- [ ] **Step 1: Add the ImbueMage parity regression**

For `FIR_911`, assert:

```python
assert "FIR_911" in compiled_mulligan_holds
assert readiness["cards"]["FIR_911"]["runtime_surfaces"] == ["Mulligan.json"]
assert readiness["cards"]["FIR_911"]["readiness_lane"] == "mulligan_only"
```

Add parity assertions for `EX1_625t`, the source `SW_448`, and all three MechPala sideboard modules.

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_config_readiness.py `
  tests/test_config_usefulness.py `
  tests/test_operator_summary.py `
  tests/test_multideck_source_backed_e2e.py
```

- [ ] **Step 3: Build the ledger from compiled artifacts**

Add:

```python
def build_runtime_surface_ledger(
    *,
    deck_identity: Mapping[str, Any],
    compiled_mulligan: Mapping[str, Any],
    compiled_globalvalues: Mapping[str, Any],
    compiled_combo: Mapping[str, Any] | None,
    compiled_cardid_files: Mapping[str, Mapping[str, Any]],
    linked_runtime_owners: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
```

Do not infer an emitted surface from a plan row when the compiled file lacks the row. Source and linked runtime owner must be separate ledger records joined by `source_card_id` and `runtime_card_id`.

- [ ] **Step 4: Route all summaries through the ledger**

Replace independent surface reconstruction in readiness, usefulness, explainability, and operator summary. Add a package invariant:

```python
assert operator_summary["surface_ledger_sha256"] == readiness["surface_ledger_sha256"]
assert readiness["surface_ledger_sha256"] == explainability["surface_ledger_sha256"]
```

- [ ] **Step 5: Run tests and commit**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_config_readiness.py `
  tests/test_config_usefulness.py `
  tests/test_operator_summary.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_config_quality_contract.py
git diff --check
git add src/hsconfig/config_readiness.py `
  src/hsconfig/config_usefulness.py `
  src/hsconfig/source_to_runtime_explainability.py `
  src/hsconfig/operator_summary.py `
  tests/test_config_readiness.py `
  tests/test_config_usefulness.py `
  tests/test_operator_summary.py `
  tests/test_multideck_source_backed_e2e.py
git commit -m "fix: derive readiness from physical runtime surfaces"
```

---

## Task 9: Reconcile Fixture Matrix With Current Apply Authority

**Files:**

- Modify: `docs/operator/archetype-fixture-matrix.json`
- Modify: `docs/operator/source-backed-strong-closure.md`
- Modify: `docs/operator/supplemental-proof-decks.json`
- Modify: `src/hsconfig/operator_summary.py`
- Test: `tests/test_archetype_fixture_matrix.py`
- Test: `tests/test_multideck_source_backed_e2e.py`
- Test: `tests/test_supplemental_cute_warrior_load_safe.py`
- Test: `tests/test_operator_summary.py`

**Interfaces:**

- Consumes: fixture classification and current provenance result.
- Produces: separate fields `fixture_expected_load_safe` and `fixture_runtime_apply_authority`, where the latter is always `diagnostic_only`.

- [ ] **Step 1: Replace the ambiguous matrix assertion**

Add tests requiring:

```python
assert row["fixture_expected_load_safe"] is True
assert row["fixture_runtime_apply_authority"] == "diagnostic_only"
assert "runtime_apply_allowed" not in row
```

For CuteWarrior, retain:

```python
assert row["proof_scope"] == "supplemental_load_safe_only"
assert row["representative_output_competence"] is False
```

- [ ] **Step 2: Confirm RED**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_archetype_fixture_matrix.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_supplemental_cute_warrior_load_safe.py
```

- [ ] **Step 3: Update documentation and operator wording**

Historical fixture promotion may remain in dated history sections, but the current snapshot must explicitly state that captured fixtures cannot authorize apply. The operator summary must use:

- `load_safe_fixture`
- `diagnostic_source_not_apply_eligible`
- `current_package_operator_gate`

as separate concepts. Never project a fixture matrix boolean into the package apply gate.

- [ ] **Step 4: Run tests and commit**

```powershell
$env:PYTHONDWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_archetype_fixture_matrix.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_supplemental_cute_warrior_load_safe.py `
  tests/test_operator_summary.py
python scripts/check_contract_guardrails.py
git diff --check
git add docs/operator/archetype-fixture-matrix.json `
  docs/operator/source-backed-strong-closure.md `
  docs/operator/supplemental-proof-decks.json `
  src/hsconfig/operator_summary.py `
  tests/test_archetype_fixture_matrix.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_supplemental_cute_warrior_load_safe.py `
  tests/test_operator_summary.py
git commit -m "docs: separate fixture safety from apply authority"
```

---

## Task 10: Prove All Twelve Decks Through One Read-Only Acceptance Matrix

**Files:**

- Create: `tests/test_audited_deck_set_acceptance.py`
- Modify: `docs/operator/README.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`

**Interfaces:**

- Consumes: the eleven-deck archetype matrix plus the CuteWarrior supplemental manifest.
- Produces: a single parameterized read-only acceptance test covering identity, package ownership, semantic invariants, and authority classification for all twelve decks.

- [ ] **Step 1: Create the parameterized acceptance test**

The test must load the existing manifests rather than duplicate deck codes:

```python
from pathlib import Path
from typing import Any

import pytest

from hsconfig.cli import main
from hsconfig.deckstring_decode import decode_deck_code
from tests.helpers.fixture_prepare import prepare_fixture_deck, read_json


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")


def audited_decks() -> list[dict[str, Any]]:
    matrix = read_json(MATRIX_PATH)["decks"]
    supplemental = read_json(SUPPLEMENTAL_PATH)["decks"]
    cute_warrior = next(
        row for row in supplemental if row["deck_name"] == "CuteWarrior"
    )
    return [*matrix, cute_warrior]


@pytest.mark.parametrize(
    "deck",
    audited_decks(),
    ids=lambda row: row["deck_name"],
)
def test_audited_deck_contract_is_current(deck: dict[str, Any], tmp_path: Path) -> None:
    decoded = decode_deck_code(deck["deck_code"])
    assert decoded["card_count"] == 30
    assert decoded["unresolved_cards"] == []

    if deck["deck_name"] == "CuteWarrior":
        out = tmp_path / "CuteWarrior"
        exit_code = main([
            "prepare",
            "--deck-name", deck["deck_name"],
            "--deck-code", deck["deck_code"],
            "--runtime-root", str(tmp_path / "runtime"),
            "--out", str(out),
            "--json",
        ])
        package = {
            "exit_code": exit_code,
            "out": out,
            "operator": read_json(out / "reports" / "operator_summary.json"),
        }
    else:
        package = prepare_fixture_deck(tmp_path, deck)

    assert package["exit_code"] == 0
    summary = package["operator"]
    assert (package["out"] / "package_derivation_receipt.json").is_file()
    assert summary["package_derivation_authority"]["verified"] is True
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_reason"] == "diagnostic_source_not_apply_eligible"
```

For a separately constructed exact live-verified positive fixture, assert the gate can become technically eligible only after all current strict validations pass. Do not use captured fixtures as that positive case.

- [ ] **Step 2: Add deck-specific invariant assertions**

The parameter table must verify:

- ShadowPriest: Mind Spike owns the Hero Power row; reciprocal burn is report-only; the two summon engines own one `OnBoardBonus` each.
- MechPala: three sideboard modules appear in metadata/readiness; `TOY_330` is not a policy keep.
- Kingslayer: `DEEP_014` has no policy keep without exact source; audited wrong-owner attack rows are absent.
- Boarlock: `WW_092` has no policy keep and no static Combo file; no unauthorized `MyHeroPowerValue`.
- Discolock: no generic coverage-only `InHandPlayPriority`; no unauthorized GlobalValues overlay.
- ImbueMage: physical Mulligan rows and readiness surfaces agree.
- Every deck: no spell owns `OnBoardBonus`, no spell uses Battlecry-target surface, every physical row has provenance, and no unsupported condition becomes unconditional.

- [ ] **Step 3: Confirm RED, then update docs/skill**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider tests/test_audited_deck_set_acceptance.py
```

Update the operator documentation and skill references with the now-enforced invariants. State explicitly that the acceptance matrix is read-only and does not prove in-client execution or gameplay optimality.

- [ ] **Step 4: Run acceptance and sync the installed skill**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider `
  tests/test_audited_deck_set_acceptance.py `
  tests/test_multideck_source_backed_e2e.py `
  tests/test_strong_fixture_closure.py
python scripts/sync_installed_skill.py --check
```

If the check reports drift, run the repository’s documented sync command, inspect the copied files, and rerun `--check`. Do not edit the installed skill independently.

- [ ] **Step 5: Commit**

```powershell
git diff --check
git add tests/test_audited_deck_set_acceptance.py `
  docs/operator/README.md `
  .agents/skills/hsconfig/SKILL.md `
  .agents/skills/hsconfig/references/card-behavior-policy.md `
  .agents/skills/hsconfig/references/globalvalues-policy.md `
  .agents/skills/hsconfig/references/visionai-surfaces.md
git commit -m "test: add twelve deck semantic acceptance matrix"
```

---

## Task 11: Final Verification and Package-Only Operator Handoff

**Files:**

- Modify only if verification exposes a documented inconsistency; return fixes to the owning earlier task rather than introducing a broad cleanup commit.
- Inspect: `reports/operator_summary.json` from temporary packages.
- Inspect: `reports/source_to_runtime_explainability.json`.
- Inspect: `reports/per_card_config_readiness_report.json`.
- Inspect: `reports/globalvalues_profile.json`.
- Inspect: `reports/card_behavior_plan_report.json`.
- Inspect: `package_derivation_receipt.json`.

**Interfaces:**

- Consumes: the completed implementation.
- Produces: a clean repository, green full suite, synchronized skill, and a twelve-deck package-readiness report without runtime mutation.

- [ ] **Step 1: Run full verification**

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q -p no:cacheprovider
python scripts/check_contract_guardrails.py
python scripts/sync_installed_skill.py --check
python scripts/check_hsconfig_currentness.py --cwd . --json
git diff --check
```

Required results:

- all tests pass;
- contract guardrails report `status=clean`;
- installed skill reports synchronized;
- currentness reports `branch=main`, `dirty=false`, `ahead_origin_main=0`, and `behind_origin_main=0` after the final commit/push workflow chosen by the user;
- no cache, generated output, or runtime evidence appears in Git status.

- [ ] **Step 2: Build temporary diagnostic packages**

Define and use one temporary root:

```powershell
$acceptanceRoot = Join-Path $env:TEMP ("hsconfig-acceptance-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $acceptanceRoot | Out-Null
$env:HSCONFIG_ACCEPTANCE_ROOT = $acceptanceRoot
python -m pytest -q -p no:cacheprovider tests/test_audited_deck_set_acceptance.py
```

Inspect the generated reports programmatically, then remove only the validated temporary root:

```powershell
$resolvedAcceptance = (Resolve-Path -LiteralPath $acceptanceRoot).Path
$resolvedTemp = (Resolve-Path -LiteralPath $env:TEMP).Path
if (-not $resolvedAcceptance.StartsWith($resolvedTemp, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Acceptance directory escaped TEMP"
}
Remove-Item -LiteralPath $resolvedAcceptance -Recurse -Force
```

- [ ] **Step 3: Verify the live runtime was untouched**

Record hashes before and after verification for:

- `C:\Users\darbo\Desktop\HS\CustomConfig\deck_config.ini`
- `C:\Users\darbo\Desktop\HS\CustomConfig\shadowpriest`
- `C:\Users\darbo\Desktop\HS\CustomConfig\discolock`

Assert the before/after hash maps are identical. Do not repair or replace the active runtime in this task.

- [ ] **Step 4: Produce the operator verdict**

For each deck report:

```text
IDENTITY
PACKAGE_CONTRACT
SOURCE_AUTHORITY
GLOBALVALUES_AUTHORITY
MULLIGAN_AUTHORITY
CARDID_SEMANTICS
COMBO_AUTHORITY
RUNTIME_APPLY_ALLOWED
RUNTIME_SAMPLED
GAMEPLAY_OPTIMALITY
FIRST_BLOCKER
```

`RUNTIME_SAMPLED` and `GAMEPLAY_OPTIMALITY` must remain `NOT_PROVEN` for all twelve decks. A deck may be described as technically apply-eligible only when its own current `operator_summary.json` says so after fresh recomputation.

- [ ] **Step 5: Final review and commit boundary**

Run:

```powershell
git status --short --branch
git log -12 --oneline
```

Have the final reviewer confirm:

- the three authority findings are closed;
- linked-owner evidence is fail-closed and receipt-bound;
- document capabilities are scoped, one-shot, and failure-atomic;
- sideboards are visible without becoming unauthorized runtime rows;
- policy Mulligan does not override exact source gaps;
- emitted GlobalValues exactly match the authority matrix;
- audited wrong-owner, wrong-surface, or unexpressible rows are suppressed;
- readiness is derived from physical output;
- fixtures never authorize apply;
- no runtime write occurred;
- no gameplay-optimality claim appears.

If documentation or tests changed during final reconciliation, commit only that narrow reconciliation:

```powershell
git add docs tests .agents/skills/hsconfig
git commit -m "docs: finalize hsconfig semantic readiness handoff"
```

Do not create an empty final commit.

---

## Explicit Follow-Up Boundary

This implementation ends with current, read-only package evidence. A later runtime-validation task must be opened separately in the repository that owns HearthRanger runtime sampling. That follow-up may begin only after:

- the package-specific `operator_summary.json` authorizes apply;
- the active runtime is snapshotted and hash-checked;
- the user authorizes the runtime write;
- the exact package is applied through the single guarded writer;
- fresh post-apply games provide direct runtime/log evidence.

Until that separate follow-up succeeds, every deck remains `RUNTIME_SAMPLED=NOT_PROVEN` and `GAMEPLAY_OPTIMALITY=NOT_PROVEN`.
