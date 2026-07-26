# HSConfig Post-Audit Authority Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the audit-proven authority gaps so strategic VisionAI rows require verified live guide evidence, linked entities own the correct runtime files, and runtime apply is deterministically hash-bound to a verified deck-derived package.

**Architecture:** Preserve the existing source-to-runtime pipeline and add narrow fail-closed boundaries at the points where evidence becomes authority. Strategic claim lowering receives exact deck identity plus verified source receipts; source acquisition records immutable provenance; linked runtime entities are resolved before CardID compilation; the completed package receives a deterministic derivation receipt; and the apply gate revalidates that receipt, the deck input, and the package before any write can be authorized.

**Tech Stack:** Python 3.11+, `pytest`, Hearthstone deck-code decoding, deterministic JSON/SHA-256 receipts, existing `hsconfig` CLI and package validators, PowerShell, Git on the sole `main` branch.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Work directly on the existing `main` branch. Do not create a branch, worktree, pull request, shadow checkout, or second implementation version.
- Functional audit baseline is commit `05beb35fe1f9b368a321dd7917ac80cd9cebc906`. The implementation may start from the descendant commit that adds this design and plan.
- Before every task, require `git status --short --branch` to show a clean `main` synchronized with `origin/main`.
- Implement with test-driven development: add the failing regression first, confirm the intended failure, make the smallest production change, run the targeted green suite, review the diff, commit, and push before starting the next task.
- Use one writing agent per task. After each task, use an independent read-only reviewer for specification compliance and code quality before committing.
- Do not perform any runtime apply, do not invoke HSTuner, and do not write to `C:\Users\darbo\Desktop\HS`.
- Generate acceptance packages only in a uniquely named temporary directory outside the repository. Delete them after inspection.
- Do not commit runtime evidence, logs, generated output packages, caches, coverage files, or private data.
- Preserve `operator_summary.json` as the sole human-facing apply authority. Its authority must be derived from verified inputs and package content, not accepted as a self-assertion.
- Preserve the established VisionAI condition vocabulary. Do not introduce new condition atoms or change tuning values unless a failing semantic contract proves that an existing value is invalid.
- Do not claim gameplay optimality or in-client behavior. This plan proves contract correctness, semantic ownership, deterministic derivation, and fail-closed write authorization.
- Use `PYTHONDONTWRITEBYTECODE=1` for all test and CLI verification commands.
- Every JSON digest must be calculated from canonical UTF-8 JSON with sorted keys and compact separators. Never hash pretty-printed output or filesystem metadata.
- Error results must be stable machine-readable codes plus concise human-readable details. Tests must assert the code, not fragile full prose.
- Keep backward compatibility only where it remains fail-closed. Legacy or fixture evidence may still build diagnostic packages, but it must not mint strategic receipts or authorize runtime apply.
- The governing design is `docs/superpowers/specs/2026-07-26-hsconfig-post-audit-authority-hardening-design.md`.

---

## Task 1: Make Strategic Combo Lowering Receipt-Bound

**Purpose:** Eliminate the reproduced path where `source_backed_static_semantics` can emit a strategic Combo row and satisfy Strong closure without exact, verified guide evidence.

**Files:**

- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/combo_plan.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/source_contract_conformance.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/strong_closure_profiles.py`
- Test: `tests/test_surface_authority_split.py`
- Test: `tests/test_combo_plan.py`
- Test: `tests/test_operator_summary.py`
- Test: `tests/test_archetype_source_fixtures.py`
- Test: `tests/test_semantic_runtime_negative_boundaries.py`

### Step 1.1: Write the failing strategic-authority regressions

- [ ] Add a regression in `tests/test_surface_authority_split.py` that constructs a `combo_sequence` claim with:

```python
claim = {
    "claim_id": "combo-static-bypass",
    "claim_kind": "combo_sequence",
    "source_lane": "source_backed_static_semantics",
    "source_card_ids": ["EX1_001", "EX1_002"],
    "runtime_lowering": {
        "surface": "Combo",
        "sequence": ["EX1_001", "EX1_002"],
    },
}
```

- [ ] Assert that `can_lower_to_combo(claim)` returns a blocked decision whose reason code is `combo_requires_public_guide_source`.
- [ ] Add a second regression proving that a correctly signed receipt for a different deck fingerprint remains blocked with `combo_exact_deck_fingerprint_mismatch`.
- [ ] Add a positive regression using the existing exact guide-claim fixture, exact deck identity, and its verified source receipt. Assert that the Combo surface is lowerable.
- [ ] Add `tests/test_combo_plan.py` coverage proving the static claim cannot produce `EX1_001>>EX1_002` in the compiled plan.
- [ ] Add `tests/test_operator_summary.py` coverage proving a static `combo_sequence` lane cannot satisfy Strong closure, even when all structural package files exist.

### Step 1.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q tests/test_surface_authority_split.py tests/test_combo_plan.py tests/test_operator_summary.py
```

- [ ] Confirm the new static Combo and Strong-closure assertions fail because current code accepts generic runtime lowerability.
- [ ] If a different test fails first, fix the test fixture so it reaches the intended authorization boundary. Do not weaken the expected blocked result.

### Step 1.3: Introduce one strategic authorization contract

- [ ] Change the public Combo authorization signature in `src/hsconfig/source_document_model.py` to:

```python
def can_lower_to_combo(
    claim: Mapping[str, Any],
    *,
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Iterable[Mapping[str, Any]] | None = None,
) -> SurfaceGateDecision:
```

- [ ] Reuse the existing canonical claim fingerprint and `_has_verified_source_receipt` machinery already used by Mulligan and GlobalValues.
- [ ] Mirror the existing Mulligan and GlobalValues source checks for `combo_sequence`: canonical public-guide identity, `exact_deck_matched`, full-text visibility, `deck_matched_public_guide`, promotion eligibility, target fingerprint, complete canonical exact-deck evidence, matching evidence fingerprint, and a matching verified source receipt.
- [ ] Use the existing helpers and the following receipt check rather than a Combo-specific signature implementation:

```python
target_fingerprint = _normalized_text(
    (deck_identity or {}).get("deck_fingerprint")
)
deck_match = claim.get("deck_match")
exact_evidence = (
    deck_match.get("exact_deck_evidence")
    if isinstance(deck_match, Mapping)
    else None
)
if not canonical_exact_deck_evidence(
    exact_evidence,
    target_fingerprint=target_fingerprint,
):
    return SurfaceGateDecision(
        False,
        "combo_requires_complete_exact_deck_evidence",
        claim_kind,
        "combo",
    )
if not _has_verified_source_receipt(
    claim,
    target_fingerprint=target_fingerprint,
    verified_source_receipts=verified_source_receipts,
):
    return SurfaceGateDecision(
        False,
        "combo_requires_verified_source_receipt",
        claim_kind,
        "combo",
    )
```

- [ ] Use surface-specific stable reasons following the existing naming pattern: `combo_requires_public_guide_source`, `combo_requires_exact_deck_match`, `combo_requires_target_deck_fingerprint`, `combo_requires_verified_exact_deck_evidence`, `combo_exact_deck_fingerprint_mismatch`, `combo_requires_complete_exact_deck_evidence`, `combo_requires_verified_source_receipt`, `combo_requires_promotion_eligible_source`, `combo_requires_full_text_source`, and `combo_requires_deck_matched_public_guide_lane`.

- [ ] Keep non-strategic Combo metadata diagnostic-only. Do not silently reinterpret static semantics as an exact guide claim.

### Step 1.4: Carry authorization context through compilation

- [ ] Update `build_combo_plan` in `src/hsconfig/combo_plan.py`:

```python
def build_combo_plan(
    *,
    deck_cards: set[str],
    claims: list[dict[str, Any]],
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
```

- [ ] Pass the same `deck_identity` and `verified_source_receipts` into every `can_lower_to_combo` call.
- [ ] Update `surface_gate_decision` so its Combo branch forwards `context["deck_identity"]` and `context["verified_source_receipts"]`, exactly as its Mulligan and GlobalValues branches already do.
- [ ] Update all callers in `package_builder.py` and `source_contract_conformance.py`.
- [ ] Remove any call path that invokes `can_lower_to_combo(claim)` after the package already has deck identity and receipts available.
- [ ] Keep the optional defaults only for read-only diagnostics and unit isolation; absent context must block strategic emission.

### Step 1.5: Make Strong closure claim-kind aware

- [ ] Add a single helper in `src/hsconfig/strong_closure_profiles.py`:

```python
def lane_can_satisfy_strong_closure(
    *,
    claim_kind: str,
    source_lane: str,
    strategic_receipt_verified: bool,
) -> bool:
    strategic_claim_kinds = {
        "combo_sequence",
        "mulligan_keep",
        "mulligan_discard",
        "targeting_rule",
        "gameplan_posture",
        "globalvalue_numeric_tuning",
    }
    if claim_kind in strategic_claim_kinds:
        return (
            source_lane == "deck_matched_public_guide"
            and strategic_receipt_verified
        )
    return source_lane in {
        "deck_matched_public_guide",
        "source_backed_static_semantics",
    }
```

- [ ] Remove strategic kinds from the `strong_static_claim` set in `qualify_source_claim`; retain static Strong eligibility only for deterministic identity, role, and mechanical claim families.
- [ ] Route `operator_summary.py` through this helper instead of treating a source lane as globally Strong-capable.
- [ ] Preserve static-semantic Strong credit for deterministic identity or mechanical claims that do not encode strategic order.
- [ ] Include the rejected claim ID and stable reason code in summary diagnostics without copying raw source text.

### Step 1.6: Run the complete targeted authority suite

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_surface_authority_split.py `
  tests/test_combo_plan.py `
  tests/test_operator_summary.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_semantic_runtime_negative_boundaries.py `
  tests/test_source_contract_conformance.py
```

- [ ] Confirm the original reproduction is blocked and the exact receipt-backed Combo path remains green.
- [ ] Run:

```powershell
git diff --check
git diff -- src/hsconfig tests
```

- [ ] Ask the specification reviewer to verify:
  - static strategic evidence cannot emit Combo;
  - exact verified evidence still can;
  - Strong closure is claim-kind aware;
  - no unrelated surface semantics changed.

### Step 1.7: Commit and synchronize

- [ ] Run:

```powershell
git add -- `
  src/hsconfig/source_document_model.py `
  src/hsconfig/combo_plan.py `
  src/hsconfig/package_builder.py `
  src/hsconfig/source_contract_conformance.py `
  src/hsconfig/operator_summary.py `
  src/hsconfig/strong_closure_profiles.py `
  tests/test_surface_authority_split.py `
  tests/test_combo_plan.py `
  tests/test_operator_summary.py `
  tests/test_archetype_source_fixtures.py `
  tests/test_semantic_runtime_negative_boundaries.py
git diff --cached --check
git commit -m "fix: bind strategic combo lowering to verified receipts"
git push origin main
```

- [ ] Verify `git status --short --branch` is clean and `git rev-parse HEAD` equals `git rev-parse origin/main`.

---

## Task 2: Bind Exact Source Receipts to Acquisition Provenance

**Purpose:** Distinguish live HTTP acquisition from fixtures, captured records, manual evidence, and legacy claim JSON so only verified live content can mint production strategic authority.

**Files:**

- Create: `src/hsconfig/source_acquisition_provenance.py`
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/source_autopilot.py`
- Modify: `src/hsconfig/source_document_drafter.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/input_loading.py`
- Test: `tests/test_source_acquisition.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_drafter.py`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Test: `tests/test_shadowpriest_source_contract_acceptance.py`
- Test: `tests/test_source_acquisition_strong_closure.py`

### Step 2.1: Add provenance classification tests

- [ ] Create parameterized tests in `tests/test_source_acquisition.py` for this exact classification:

| Input path | `mode` | `authority` |
|---|---|---|
| successful direct HTTP fetch | `live_http` | `live_verified` |
| checked-in captured response | `captured_record` | `captured_unverified` |
| operator-supplied evidence file | `manual_evidence` | `manual_unverified` |
| repository fixture map | `fixture_map` | `fixture_only` |
| legacy claims JSON | `legacy_claims_json` | `legacy_unverified` |

- [ ] Assert every provenance object includes a canonical `sha256:` content digest.
- [ ] Assert the same content and mode produce byte-identical canonical provenance.
- [ ] Assert changing a single content byte changes `content_sha256`.
- [ ] Add an autopilot regression: a fixture can produce diagnostic claims, but its strategic receipt list is empty.
- [ ] Add a live-source positive test: verified live provenance plus exact fingerprint mints one strategic receipt.
- [ ] Add a captured-record regression: identical content to the live response still cannot mint a strategic receipt.
- [ ] Add a forged-import regression: a manual, fixture, captured, or legacy JSON row containing caller-supplied `{"mode": "live_http", "authority": "live_verified"}` is reclassified by its loader and cannot mint a strategic receipt.

### Step 2.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_source_acquisition.py `
  tests/test_source_autopilot.py `
  tests/test_source_document_drafter.py `
  tests/test_source_acquisition_strong_closure.py
```

- [ ] Confirm the new tests fail because acquisition mode and content digest are not preserved through the current receipt path.

### Step 2.3: Implement the provenance value object

- [ ] Add `src/hsconfig/source_acquisition_provenance.py` with these public constants and functions:

```python
LIVE_HTTP = "live_http"
CAPTURED_RECORD = "captured_record"
MANUAL_EVIDENCE = "manual_evidence"
FIXTURE_MAP = "fixture_map"
LEGACY_CLAIMS_JSON = "legacy_claims_json"

LIVE_VERIFIED = "live_verified"

def build_acquisition_provenance(
    *,
    mode: str,
    content: bytes | str,
) -> dict[str, str]:
    raw = content if isinstance(content, bytes) else content.encode("utf-8")
    authority_by_mode = {
        LIVE_HTTP: LIVE_VERIFIED,
        CAPTURED_RECORD: "captured_unverified",
        MANUAL_EVIDENCE: "manual_unverified",
        FIXTURE_MAP: "fixture_only",
        LEGACY_CLAIMS_JSON: "legacy_unverified",
    }
    return {
        "mode": mode,
        "content_sha256": f"sha256:{hashlib.sha256(raw).hexdigest()}",
        "authority": authority_by_mode[mode],
    }

def strategic_source_provenance_is_verified(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("mode") == LIVE_HTTP
        and value.get("authority") == LIVE_VERIFIED
        and isinstance(value.get("content_sha256"), str)
        and value["content_sha256"].startswith("sha256:")
    )
```

- [ ] Reject unknown modes with `ValueError`; do not default them to live or verified.
- [ ] Keep provenance free of URLs with query secrets, raw HTML, or user-specific filesystem paths.

### Step 2.4: Propagate provenance without reconstruction

- [ ] Construct provenance at the first byte-acquisition boundary in `source_acquisition.py`.
- [ ] Carry the exact object through `commands/source_workflow.py`, `source_autopilot.py`, `source_document_drafter.py`, and `source_document_builder.py`.
- [ ] Do not infer provenance later from the presence of a citation, source title, URL, candidate ID, or fixture name.
- [ ] Classify `--claims-json`, `--source-evidence`, and fixture-map inputs explicitly in `input_loading.py`.
- [ ] Treat imported provenance fields as untrusted data: overwrite their authority classification from the actual loader path. Only the successful direct-HTTP acquisition boundary may assign `live_verified`.
- [ ] Add provenance to the canonical source document and to each strategic receipt payload.

### Step 2.5: Gate receipt minting

- [ ] In `source_document_model.py`, require:

```python
if not strategic_source_provenance_is_verified(
    claim.get("acquisition_provenance")
):
    return None
```

- [ ] Apply this check before signing or appending a strategic receipt.
- [ ] Preserve non-strategic claim parsing and diagnostic reporting for all supported provenance modes.
- [ ] Add the stable diagnostic code `strategic_provenance_not_live_verified`.
- [ ] Ensure fixture-based integration tests expect diagnostic closure, not production Strong closure.

### Step 2.6: Run targeted and compatibility tests

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_source_acquisition.py `
  tests/test_source_autopilot.py `
  tests/test_source_document_drafter.py `
  tests/test_source_document_builder.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_shadowpriest_source_contract_acceptance.py `
  tests/test_source_acquisition_strong_closure.py `
  tests/test_surface_authority_split.py
```

- [ ] Review serialized fixtures. Update expected metadata only where the new provenance fields are part of the public contract.
- [ ] Ask the reviewer to attempt receipt minting with each unverified mode and verify that all attempts fail closed.

### Step 2.7: Commit and synchronize

- [ ] Stage only the provenance implementation, adjusted contract fixtures, and tests.
- [ ] Run:

```powershell
git diff --cached --check
git commit -m "fix: bind strategic receipts to live acquisition provenance"
git push origin main
git status --short --branch
```

- [ ] Verify local `main` and `origin/main` are identical.

---

## Task 3: Put Darkbishop Benedictus Hero-Power Behavior on the Linked Runtime Entity

**Purpose:** Make the physical VisionAI file owner match Hearthstone semantics: `SW_448` is the deck card that transforms the hero power, while `EX1_625t` is Mind Spike and owns `BeforeUseHeroPowerBonus`.

**Files:**

- Create: `src/hsconfig/runtime_entity_owner.py`
- Modify: `src/hsconfig/card_behavior_surface_router.py`
- Modify: `src/hsconfig/compile_cardid.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Test: `tests/test_card_behavior_router.py`
- Test: `tests/test_compile_cardid.py`
- Test: `tests/test_config_readiness.py`
- Test: `tests/test_strict_package_validation.py`
- Test: `tests/test_source_to_runtime_explainability.py`
- Test: `tests/test_output_ownership_manifest.py`
- Test: `tests/test_shadowpriest_semantic_safety_wave.py`
- Test: `tests/test_shadowpriest_visionai_semantic_surface_contract.py`

### Step 3.1: Add semantic ownership regressions

- [ ] Add a router test using the existing curated link:

```python
identity_links = {
    "SW_448": {
        "hero_power_transform": "EX1_625t",
    }
}
```

- [ ] Assert `BeforeUseHeroPowerBonus` resolves to `EX1_625t`.
- [ ] Assert no active `BeforeUseHeroPowerBonus` row is emitted into `SW_448.json`.
- [ ] Assert `SW_448` remains represented in explainability as the source card that caused the linked runtime row.
- [ ] Assert a missing or non-curated link blocks linked runtime emission with `linked_runtime_entity_unresolved`.
- [ ] Assert an arbitrary same-name or text-matched entity is never selected.
- [ ] Update ShadowPriest contract expectations from seven active deck-card files to:
  - six active deck-card files;
  - one active linked runtime file, `EX1_625t.json`;
  - one metadata-only `SW_448.json` record.

### Step 3.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_shadowpriest_semantic_safety_wave.py `
  tests/test_shadowpriest_visionai_semantic_surface_contract.py
```

- [ ] Confirm current compilation places the hero-power row under `SW_448`.

### Step 3.3: Add a narrow runtime-owner resolver

- [ ] Implement `src/hsconfig/runtime_entity_owner.py`:

```python
@dataclass(frozen=True)
class RuntimeEntityOwner:
    source_card_id: str
    runtime_card_id: str
    link_kind: str

def resolve_runtime_entity_owner(
    *,
    source_card_id: str,
    semantic_reason: str,
    identity_links: Mapping[str, Mapping[str, str]],
) -> RuntimeEntityOwner | None:
    if semantic_reason != "hero_power_before_use":
        return RuntimeEntityOwner(
            source_card_id=source_card_id,
            runtime_card_id=source_card_id,
            link_kind="self",
        )
    runtime_card_id = identity_links.get(source_card_id, {}).get(
        "hero_power_transform"
    )
    if not runtime_card_id:
        return None
    return RuntimeEntityOwner(
        source_card_id=source_card_id,
        runtime_card_id=runtime_card_id,
        link_kind="hero_power_transform",
    )
```

- [ ] Keep the resolver dependent only on the curated identity-link supplement already in the repository.
- [ ] Do not add online fuzzy matching, localized-name matching, collectible-card guessing, or database search fallback.

### Step 3.4: Route and compile using the physical owner

- [ ] In `card_behavior_surface_router.py`, attach both `source_card_id` and `runtime_card_id` to the routed behavior.
- [ ] In `compile_cardid.py`, use `runtime_card_id` for:
  - the output filename;
  - `GameCardId`;
  - the owning runtime row.
- [ ] Preserve `source_card_id` in report metadata and explainability only.
- [ ] Ensure `SW_448.json` is metadata-only and contains no active behavior row.
- [ ] Ensure `EX1_625t.json` contains the single intended hero-power row:

```json
{
  "GameCardId": "EX1_625t",
  "BeforeUseHeroPowerBonus": {
    "*": 10
  }
}
```

- [ ] Keep the existing baseline value `10`; this task corrects ownership, not tuning.

### Step 3.5: Separate linked-entity readiness from deck-card readiness

- [ ] Update `config_readiness.py` so a linked entity:
  - is required when an accepted routed behavior references it;
  - is not counted as a missing deck card;
  - receives its own `linked_runtime_entity` readiness category.
- [ ] Update `strict_package_validation.py` to require filename and `GameCardId` equality for linked runtime files exactly as for deck-card runtime files.
- [ ] Update `output_ownership_manifest.py` with:

```python
{
    "path": "CardID/EX1_625t.json",
    "owner_kind": "linked_runtime_entity",
    "source_card_id": "SW_448",
    "runtime_card_id": "EX1_625t",
    "link_kind": "hero_power_transform",
}
```

- [ ] Update source-to-runtime explainability to report the source-to-owner transition without implying that Benedictus itself is a hero power.

### Step 3.6: Run the semantic ownership suite

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_config_readiness.py `
  tests/test_strict_package_validation.py `
  tests/test_source_to_runtime_explainability.py `
  tests/test_output_ownership_manifest.py `
  tests/test_shadowpriest_semantic_safety_wave.py `
  tests/test_shadowpriest_visionai_semantic_surface_contract.py
```

- [ ] Ask the reviewer to inspect the generated in-test package and confirm:
  - filename and `GameCardId` agree;
  - the row belongs to `EX1_625t`;
  - `SW_448` remains traceable;
  - no other linked entity moved.

### Step 3.7: Commit and synchronize

- [ ] Run:

```powershell
git add -- src/hsconfig tests
git diff --cached --check
git commit -m "fix: assign hero power behavior to linked runtime entity"
git push origin main
```

- [ ] Confirm clean, synchronized `main` before continuing.

---

## Task 4: Make Package Authority Deterministic and Mutation-Evident

**Purpose:** Prevent a handcrafted `operator_summary.json` from declaring a package valid by binding the summary and apply gate to a deterministic derivation receipt over authoritative inputs and runtime outputs.

**Files:**

- Create: `src/hsconfig/package_derivation_receipt.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_apply_authority_boundary.py`
- Test: `tests/test_runtime_apply.py`
- Test: `tests/test_runtime_apply_receipts.py`
- Test: `tests/test_strict_package_validation.py`
- Test: `tests/test_output_ownership_manifest.py`

### Step 4.1: Add derivation and tamper regressions

- [ ] Add `tests/test_apply_authority_boundary.py` cases proving apply is blocked when:
  - `operator_summary.json` is manually changed to `VALID_PACKAGE`;
  - one runtime JSON value changes after package build;
  - one runtime JSON file is added after package build;
  - one authoritative input digest changes;
  - the receipt is missing;
  - the receipt schema version is unknown;
  - strict package validation fails even if receipt verification is forced true in the fixture.
- [ ] Add a positive test for an untouched package built by `package_builder`.
- [ ] Add deterministic receipt tests: build the same logical package in two different temporary roots and assert identical receipt content and digest.
- [ ] Add a non-circularity test proving the receipt does not hash itself or the operator summary that embeds its digest.

### Step 4.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_apply_gate.py `
  tests/test_apply_authority_boundary.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_apply_receipts.py
```

- [ ] Confirm the forged-summary fixture currently crosses the apply authority boundary.

### Step 4.3: Implement canonical derivation receipts

- [ ] Add `src/hsconfig/package_derivation_receipt.py` with:

```python
DERIVATION_RECEIPT_SCHEMA_VERSION = 1

def build_package_derivation_receipt(
    package_root: Path,
) -> dict[str, Any]:
    return {
        "schema_version": DERIVATION_RECEIPT_SCHEMA_VERSION,
        "inputs": _authoritative_input_digests(package_root),
        "runtime_files": _runtime_file_digests(package_root),
    }

def verify_package_derivation_receipt(
    package_root: Path,
    receipt: Mapping[str, Any],
) -> tuple[bool, list[dict[str, str]]]:
    expected = build_package_derivation_receipt(package_root)
    if receipt != expected:
        return False, [{
            "code": "package_derivation_mismatch",
            "detail": "Authoritative package content differs from its receipt.",
        }]
    return True, []
```

- [ ] Hash these authoritative inputs:
  - input manifest;
  - deck identity and deck fingerprint;
  - deck-input verification;
  - verified source receipts;
  - GlobalValues baseline/profile selection;
  - output ownership manifest.
- [ ] Hash every active runtime JSON file under the canonical runtime directories, keyed by normalized repository-relative path.
- [ ] Sort all paths ordinally using forward slashes.
- [ ] Exclude:
  - `package_derivation_receipt.json`;
  - `operator_summary.json`;
  - human-readable reports;
  - timestamps;
  - absolute paths.
- [ ] Serialize the receipt once and calculate its public digest from the same canonical JSON bytes.

### Step 4.4: Build summary authority from the receipt

- [ ] Write `package_derivation_receipt.json` only after all authoritative package files are finalized.
- [ ] Add to `operator_summary.json`:

```json
{
  "package_derivation": {
    "schema_version": 1,
    "receipt_path": "package_derivation_receipt.json",
    "receipt_sha256": "sha256:64-lowercase-hex-digits",
    "verified": true
  }
}
```

- [ ] Derive `technical_status = "VALID_PACKAGE"` only if:
  - strict package validation passed;
  - deck input is apply-eligible;
  - required strategic receipts are verified;
  - the just-built derivation receipt verifies.
- [ ] Do not expose a builder parameter that directly sets `technical_status`.

### Step 4.5: Recompute authority at apply time

- [ ] Change `apply_gate.py` ordering to:

```text
load package
-> strict structural and semantic validation
-> deck-input apply eligibility
-> source authority checks
-> derivation receipt digest check
-> derivation receipt content recomputation
-> operator-summary consistency check
-> runtime write authorization
```

- [ ] Return a blocked decision before `runtime_apply.py` receives a write request if any step fails.
- [ ] Use stable codes:
  - `package_derivation_receipt_missing`
  - `package_derivation_receipt_digest_mismatch`
  - `package_derivation_mismatch`
  - `operator_summary_derivation_inconsistent`
- [ ] Keep `operator_summary.json` the sole human-facing authority document while refusing to trust it without recomputation.

### Step 4.6: Run the full apply-boundary suite

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_apply_gate.py `
  tests/test_apply_authority_boundary.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_apply_receipts.py `
  tests/test_strict_package_validation.py `
  tests/test_output_ownership_manifest.py `
  tests/test_property_no_block_apply_gate.py
```

- [ ] Review that every negative test stops before any filesystem write mock is called.
- [ ] Ask the independent reviewer to hand-edit each authority-bearing file in a copied test package and confirm fail-closed behavior.

### Step 4.7: Commit and synchronize

- [ ] Run:

```powershell
git add -- src/hsconfig tests
git diff --cached --check
git commit -m "fix: bind apply authority to package derivation receipt"
git push origin main
```

- [ ] Confirm clean and synchronized `main`.

---

## Task 5: Verify Deck Inputs Before Granting Apply Eligibility

**Purpose:** Preserve useful `--cards-json` and placeholder diagnostics while preventing them from bypassing the decoded deck roster required for runtime apply.

**Files:**

- Create: `src/hsconfig/deck_input_verification.py`
- Modify: `src/hsconfig/input_loading.py`
- Modify: `src/hsconfig/deck_identity.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/commands/configure.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_apply_gate.py`
- Test: `tests/test_apply_authority_boundary.py`
- Test: `tests/test_deck_identity.py`
- Test: `tests/test_package_builder.py`

### Step 5.1: Define the input-verification matrix in tests

- [ ] Add parameterized tests for:

| Input state | Status | Diagnostic build | Runtime apply |
|---|---|---:|---:|
| roster decoded from deck code | `decoded_from_deck_code` | yes | yes |
| `cards-json` exactly matches decoded deck code | `cards_json_matches_deck_code` | yes | yes |
| `cards-json` differs from deck code | `cards_json_unverified` | yes | no |
| no deck code and placeholder cards | `placeholder_unverified` | yes | no |
| malformed deck code plus supplied cards | `cards_json_unverified` | yes | no |

- [ ] Define roster equality as normalized multiset equality of `(card_id, count)`, not input order or card name.
- [ ] Assert duplicate entries are combined before comparison.
- [ ] Assert non-positive counts and missing card IDs are invalid, not merely mismatched.
- [ ] Add CLI coverage showing `configure` can finish a diagnostic package for unverified cards, but `configure --apply` exits non-zero before invoking runtime write code.

### Step 5.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_cli.py `
  tests/test_deck_identity.py `
  tests/test_apply_gate.py `
  tests/test_apply_authority_boundary.py `
  tests/test_package_builder.py
```

- [ ] Confirm current `--cards-json` or placeholder input can reach a package state that lacks an explicit apply-ineligible verdict.

### Step 5.3: Implement deck-input verification

- [ ] Add `src/hsconfig/deck_input_verification.py`:

```python
DECODED_FROM_DECK_CODE = "decoded_from_deck_code"
CARDS_JSON_MATCHES_DECK_CODE = "cards_json_matches_deck_code"
CARDS_JSON_UNVERIFIED = "cards_json_unverified"
PLACEHOLDER_UNVERIFIED = "placeholder_unverified"

def verify_deck_input(
    *,
    deck_code: str | None,
    cards: Sequence[Mapping[str, Any]],
    source: str,
) -> dict[str, Any]:
    normalized_cards = normalize_roster(cards)
    decoded_cards = try_decode_roster(deck_code)
    if source == "deckstring" and decoded_cards == normalized_cards:
        status = DECODED_FROM_DECK_CODE
    elif source == "cards_json" and decoded_cards == normalized_cards:
        status = CARDS_JSON_MATCHES_DECK_CODE
    elif source == "placeholder":
        status = PLACEHOLDER_UNVERIFIED
    else:
        status = CARDS_JSON_UNVERIFIED
    return {
        "status": status,
        "runtime_apply_eligible": status in {
            DECODED_FROM_DECK_CODE,
            CARDS_JSON_MATCHES_DECK_CODE,
        },
        "normalized_roster_sha256": roster_digest(normalized_cards),
    }
```

- [ ] Implement `try_decode_roster` as a private wrapper around the existing `hsconfig.deckstring_decode.decode_deck_code`; return a normalized decoded roster on success and `None` on the decoder's documented invalid-code exception.
- [ ] Reuse the repository deck decoder and canonical deck fingerprint code; do not create a second decoding implementation.
- [ ] Ensure invalid roster shape returns a stable validation error before hashing.

### Step 5.4: Persist and enforce the verdict

- [ ] Build deck-input verification immediately after input loading.
- [ ] Include it in:
  - package input manifest;
  - package derivation receipt;
  - operator summary;
  - apply-gate checks.
- [ ] Show diagnostic-only status clearly in the operator summary:

```json
{
  "deck_input_verification": {
    "status": "cards_json_unverified",
    "runtime_apply_eligible": false
  }
}
```

- [ ] Block runtime apply with `deck_input_not_verified` before any destination path or write operation is prepared.
- [ ] Preserve non-apply generation for research, fixture, and troubleshooting workflows.

### Step 5.5: Run the complete deck-input suite

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_cli.py `
  tests/test_deck_identity.py `
  tests/test_package_builder.py `
  tests/test_apply_gate.py `
  tests/test_apply_authority_boundary.py
```

- [ ] Ask the reviewer to verify that no CLI alias, direct Python call, or prebuilt summary bypasses `runtime_apply_eligible`.

### Step 5.6: Commit and synchronize

- [ ] Run:

```powershell
git add -- src/hsconfig tests
git diff --cached --check
git commit -m "fix: require verified deck input for runtime apply"
git push origin main
```

- [ ] Confirm clean, synchronized `main`.

---

## Task 6: Bound Exact-Evidence Cardinality and Propagate the Operator Date

**Purpose:** Remove the unbounded integer parse and make source freshness deterministic by carrying `--current-date` through the complete guide/source build.

**Files:**

- Modify: `src/hsconfig/source_exact_evidence.py`
- Modify: `src/hsconfig/preconfig_context.py`
- Modify: `src/hsconfig/guide_claim_builder.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/commands/configure.py`
- Test: `tests/test_claim_kind_runtime_contract.py`
- Test: `tests/test_source_autopilot.py`
- Test: `tests/test_source_document_drafter.py`
- Test: `tests/test_guide_claim_builder.py`
- Test: `tests/test_configure_auto_source.py`

### Step 6.1: Add exact-evidence boundary tests

- [ ] Add tests for:
  - `candidate_count = 0`;
  - `candidate_count = 1`;
  - `candidate_count = 256`;
  - `candidate_count = 257`;
  - a 5,000-digit count with `sys.set_int_max_str_digits(0)`;
  - decoded evidence count greater than candidate count;
  - candidate hashes count different from candidate count;
  - duplicate candidate hashes;
  - a non-decimal count.
- [ ] Assert the parser accepts only `0..256`, while canonical exact evidence additionally requires `1 <= decoded_candidate_count <= candidate_count`.
- [ ] Assert logical inconsistencies return `exact_evidence_cardinality_mismatch`.
- [ ] Add a date-propagation test using `--current-date 2030-01-15`; assert every source freshness decision and generated guide claim uses that date rather than the machine clock.

### Step 6.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_guide_claim_builder.py `
  tests/test_configure_auto_source.py
```

- [ ] Confirm the 5,000-digit count reaches integer conversion in the current implementation and the explicit current date is lost before the final guide/source build.

### Step 6.3: Bound parsing before integer conversion

- [ ] In `source_exact_evidence.py`, add:

```python
MAX_EXACT_SOURCE_CANDIDATES = 256
MAX_EXACT_SOURCE_COUNT_DIGITS = len(
    str(MAX_EXACT_SOURCE_CANDIDATES)
)

def parse_exact_source_count(value: Any) -> int:
    text = str(value).strip()
    if not text.isdecimal():
        raise ExactEvidenceError("exact_evidence_count_invalid")
    if len(text) > MAX_EXACT_SOURCE_COUNT_DIGITS:
        raise ExactEvidenceError("exact_evidence_count_out_of_range")
    count = int(text)
    if count > MAX_EXACT_SOURCE_CANDIDATES:
        raise ExactEvidenceError("exact_evidence_count_out_of_range")
    return count
```

- [ ] Reject leading signs, exponent notation, whitespace-only strings, floats, and booleans.
- [ ] Validate:

```python
decoded_count <= candidate_count
len(candidate_hashes) == candidate_count
len(set(candidate_hashes)) == len(candidate_hashes)
```

- [ ] Calculate the canonical evidence digest only after these validations pass.

### Step 6.4: Thread `current_date` through every source-build layer

- [ ] Normalize the CLI value once to a `date`.
- [ ] Extend signatures in `preconfig_context.py`, `guide_claim_builder.py`, and `package_builder.py` with:

```python
current_date: date | None = None
```

- [ ] Pass the normalized value through all calls to guide claim building, source freshness evaluation, and source-document drafting.
- [ ] Resolve `date.today()` only at the outermost boundary when `current_date is None`.
- [ ] Do not serialize a timestamp when the contract only needs a date.

### Step 6.5: Run boundary and propagation suites

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_source_autopilot.py `
  tests/test_source_document_drafter.py `
  tests/test_guide_claim_builder.py `
  tests/test_configure_auto_source.py
```

- [ ] Ask the reviewer to trace one CLI `current_date` value to the final source freshness field and confirm no intermediate call drops it.

### Step 6.6: Commit and synchronize

- [ ] Run:

```powershell
git add -- src/hsconfig tests
git diff --cached --check
git commit -m "fix: bound exact evidence and preserve operator date"
git push origin main
```

- [ ] Confirm clean, synchronized `main`.

---

## Task 7: Align Operator Documentation and the Installed Skill

**Purpose:** Make the public contract accurately describe strategic evidence authority, linked runtime ownership, deck-input eligibility, derivation receipts, and the remaining limits of static verification.

**Files:**

- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `docs/operator/guide-research-policy.md`
- Modify: `docs/operator/source-contract-spine.md`
- Modify: `.agents/skills/hsconfig/SKILL.md`
- Modify: `.agents/skills/hsconfig/references/card-behavior-policy.md`
- Modify: `.agents/skills/hsconfig/references/contract-compiler-checklist.md`
- Modify: `.agents/skills/hsconfig/references/globalvalues-policy.md`
- Modify: `.agents/skills/hsconfig/references/guide-research-policy.md`
- Modify: `.agents/skills/hsconfig/references/visionai-surfaces.md`
- Modify: `.agents/skills/hsconfig/references/workflow.md`
- Test: `tests/test_operator_docs_contract_policy.py`
- Test: `tests/test_skill_files.py`
- Test: `tests/test_source_contract_spine_freeze.py`
- Test: `tests/test_contract_spine_sentinel_cli.py`

### Step 7.1: Add documentation contract assertions

- [ ] Add tests requiring the operator docs and repository skill to state:
  - static semantics cannot authorize strategic Combo order;
  - only `live_http` plus `live_verified` provenance can mint strategic receipts;
  - captured, fixture, manual, and legacy sources are diagnostic-only for strategic authority;
  - linked runtime entities may own physical CardID files;
  - `SW_448` causes the transform while `EX1_625t` owns Mind Spike behavior;
  - unverified deck inputs cannot authorize apply;
  - the apply gate recomputes package derivation;
  - offline tests do not prove gameplay optimality or in-client behavior.
- [ ] Assert the skill uses `operator_summary.json` as the human-facing verdict and does not instruct operators to infer apply readiness from individual reports.

### Step 7.2: Confirm RED

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_operator_docs_contract_policy.py `
  tests/test_skill_files.py `
  tests/test_source_contract_spine_freeze.py `
  tests/test_contract_spine_sentinel_cli.py
```

- [ ] Confirm the new contract language is absent or inconsistent before editing documentation.

### Step 7.3: Update the canonical operator path

- [ ] Update `README.md` only as a concise entry point.
- [ ] Put operational detail in `docs/operator/README.md`.
- [ ] Update `guide-research-policy.md` with the provenance authority matrix.
- [ ] Update `source-contract-spine.md` with the claim-kind-specific Strong rule.
- [ ] Update the runtime-apply section in `docs/operator/README.md` with the exact gate order and blocked reason codes.
- [ ] Include one concrete linked-owner example:

```text
Source card: SW_448 (Darkbishop Benedictus)
Link: hero_power_transform
Runtime owner: EX1_625t (Mind Spike)
Physical row: CardID/EX1_625t.json
```

- [ ] State explicitly that the numeric bonus is a configuration policy value, not a proof of optimal play.

### Step 7.4: Update and synchronize the skill

- [ ] Mirror only operator-facing instructions into `.agents/skills/hsconfig`.
- [ ] Keep the skill a thin router to repository commands and canonical docs; do not duplicate implementation logic.
- [ ] Run the repository sync command:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python scripts/sync_installed_skill.py
```

- [ ] Inspect both the tracked skill diff and installed skill result.
- [ ] Do not stage the external installed-skill copy.

### Step 7.5: Run documentation and skill verification

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_operator_docs_contract_policy.py `
  tests/test_skill_files.py `
  tests/test_source_contract_spine_freeze.py `
  tests/test_contract_spine_sentinel_cli.py
python scripts/sync_installed_skill.py --check
```

- [ ] Ask the reviewer to compare every documented authority claim to its implemented gate and test.

### Step 7.6: Commit and synchronize

- [ ] Run:

```powershell
git add -- README.md docs/operator .agents/skills/hsconfig tests
git diff --cached --check
git commit -m "docs: align operator authority and linked entity contracts"
git push origin main
```

- [ ] Confirm clean, synchronized `main`.

---

## Task 8: Run the Full Read-Only Acceptance and Close the Audit

**Purpose:** Prove the integrated hardening works without touching the live HearthRanger runtime, then leave exactly one clean synchronized repository state.

**Files:**

- Modify only if a verification-discovered defect requires a focused test and fix.
- Do not commit generated packages or logs.

### Step 8.1: Establish the final verification baseline

- [ ] Run:

```powershell
git status --short --branch
git branch --format="%(refname:short)"
git rev-parse HEAD
git rev-parse origin/main
```

- [ ] Require:
  - branch is `main`;
  - only branch is `main`;
  - worktree is clean;
  - local and remote commit IDs match.

### Step 8.2: Run focused security and semantic guardrails

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q `
  tests/test_surface_authority_split.py `
  tests/test_combo_plan.py `
  tests/test_source_acquisition.py `
  tests/test_source_acquisition_strong_closure.py `
  tests/test_card_behavior_router.py `
  tests/test_compile_cardid.py `
  tests/test_apply_authority_boundary.py `
  tests/test_apply_gate.py `
  tests/test_deck_identity.py `
  tests/test_claim_kind_runtime_contract.py `
  tests/test_configure_auto_source.py `
  tests/test_operator_docs_contract_policy.py `
  tests/test_skill_files.py
```

- [ ] Require zero failures.

### Step 8.3: Run the full repository suite

- [ ] Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE = "1"
python -m pytest -q
```

- [ ] Record the final passed/skipped counts in the implementation handoff.
- [ ] Do not describe skipped runtime-dependent tests as passed.

### Step 8.4: Build fresh packages in a safe temporary root

- [ ] Create a unique temporary directory with PowerShell:

```powershell
$auditTempRoot = Join-Path `
  ([System.IO.Path]::GetTempPath()) `
  ("hsconfig-post-audit-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $auditTempRoot | Out-Null
```

- [ ] Resolve the exact deck code and source inputs from the repository’s existing ShadowPriest acceptance fixture. Do not use or copy the stale ignored `outputs/ShadowPriest` package.
- [ ] Build:
  - one exact, verified test package using a mocked successful HTTP response through the normal acquisition boundary;
  - one fixture-backed diagnostic package.
- [ ] Use the normal `hsconfig configure` command surface with `--output-root $auditTempRoot`.
- [ ] Do not pass `--apply`.

### Step 8.5: Inspect exact-package invariants

- [ ] Verify with CLI and direct JSON inspection:
  - package validation passes;
  - preflight passes;
  - deck input is apply-eligible;
  - the package derivation receipt verifies;
  - strategic Combo exists only when the exact receipt is present;
  - `CardID/EX1_625t.json` owns `BeforeUseHeroPowerBonus`;
  - `CardID/SW_448.json` has no active hero-power row;
  - source-to-runtime explainability links `SW_448` to `EX1_625t`;
  - filename and `GameCardId` match for every runtime file.
- [ ] Invoke the apply gate in dry, read-only decision mode only if such an existing mode is available. Otherwise rely on the apply-gate unit/integration suite and do not call the writer.

### Step 8.6: Inspect diagnostic-package invariants

- [ ] Verify:
  - fixture provenance is `fixture_map` plus `fixture_only`;
  - no strategic receipt is minted;
  - no strategic Combo row is emitted from static semantics;
  - the operator summary does not report production Strong closure;
  - runtime apply is ineligible.

### Step 8.7: Clean temporary artifacts safely

- [ ] Resolve and validate the temporary path:

```powershell
$resolvedAuditTemp = (Resolve-Path -LiteralPath $auditTempRoot).Path
$resolvedSystemTemp = (Resolve-Path -LiteralPath ([System.IO.Path]::GetTempPath())).Path
if (-not $resolvedAuditTemp.StartsWith(
    $resolvedSystemTemp,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Refusing to remove a path outside the system temp directory."
}
Remove-Item -LiteralPath $resolvedAuditTemp -Recurse -Force
```

- [ ] Confirm no new files exist under repository `outputs/`, no runtime folder changed, and no cache artifact is staged.

### Step 8.8: Independent final review

- [ ] Give the final reviewer:
  - the design document;
  - this plan;
  - the full diff from the pre-plan functional baseline;
  - targeted and full-suite results;
  - exact- and diagnostic-package invariant summaries.
- [ ] Require the reviewer to answer:
  1. Can static or unverified evidence still authorize a strategic row?
  2. Can a linked behavior be written to the wrong physical entity?
  3. Can a forged or stale summary cross the apply gate?
  4. Can unverified card input authorize apply?
  5. Can oversized or inconsistent evidence counts be canonicalized?
  6. Can an explicit operator date be dropped?
- [ ] If any answer is “yes” or uncertain, add a failing regression, implement the smallest fix, rerun the affected suite and full suite, then commit and push that fix on `main`.

### Step 8.9: Final Git hygiene

- [ ] Run:

```powershell
git diff --check
git status --short --branch
git branch --format="%(refname:short)"
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
git log -1 --oneline
```

- [ ] Require:
  - no unstaged, staged, or untracked implementation artifacts;
  - exactly one local branch, `main`;
  - `HEAD == origin/main`;
  - no open implementation branch or pull request was created.

## Completion Contract

Implementation is complete only when all of the following are true:

- [ ] Strategic Combo lowering requires an exact guide claim, the exact deck fingerprint, verified live acquisition provenance, and a matching signed receipt.
- [ ] Static semantics, fixtures, captured content, manual evidence, and legacy claim JSON cannot mint strategic authority.
- [ ] Strong closure is claim-kind aware and does not credit static Combo order.
- [ ] `EX1_625t` physically owns the Mind Spike hero-power behavior; `SW_448` remains the traceable source card and contains no active hero-power row.
- [ ] Every active package has a deterministic derivation receipt and the apply gate recomputes it.
- [ ] A summary-only forgery, stale receipt, incomplete package, or package whose authoritative content no longer matches its receipt cannot cross the apply gate.
- [ ] Only decoded deck input or `cards-json` that exactly matches the decoded deck code is apply-eligible.
- [ ] Exact-evidence counts are bounded to `0..256` before integer conversion and are logically consistent with decoded candidates and hashes.
- [ ] An explicit `--current-date` reaches every source freshness and guide-claim decision.
- [ ] Operator docs and the installed skill state the same authority boundaries as the implementation.
- [ ] Targeted tests, contract guardrails, and the complete suite pass.
- [ ] No runtime write or HSTuner action occurred.
- [ ] Temporary packages are deleted.
- [ ] Local `main` is clean and identical to `origin/main`.

## Recommended Execution Mode

Use `superpowers:subagent-driven-development` in this task:

1. Dispatch one implementation subagent for the current task only.
2. Dispatch a specification-compliance reviewer after the implementation subagent finishes.
3. Dispatch a code-quality reviewer only after specification compliance passes.
4. Apply reviewer fixes before committing.
5. Commit and push the reviewed task directly to `main`.
6. Confirm a clean synchronized repository.
7. Continue with the next task using fresh subagents.

Do not execute multiple write tasks in parallel. Tasks 1 through 6 change overlapping authority and package-builder paths and must be completed sequentially. Read-only reviews and test inspection may run in parallel when they do not race with file writes.
