# HSConfig Contract Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every audited deck, card/module, claim, source lane, Mulligan decision, and GlobalValues key inside the approved pre-run contract without inventing gameplay behavior.

**Architecture:** Freeze the current 208/316/456 inventory, introduce typed evidence and disposition ledgers, replace heuristic Mulligan fallback with explicit bot delegation, and project all closure reports from one semantic truth. `SOURCE_BACKED_STRONG` remains strict; pre-run completeness is independent.

**Tech Stack:** Python frozen dataclasses, `StrEnum`, JSON policy resources, SHA-256 evidence binding, pytest, existing source-contract and package-builder modules.

## Global Constraints

- Gameplay quality is `OUT_OF_SCOPE_ASSUMED_EXTERNAL`.
- `BOT_NATIVE_PRE_RUN` is the only default policy profile.
- Evidence lanes are exactly A official card data, B exact live guide, C archetype/mechanic guide, D versioned internal policy, and E bot delegation.
- Final card dispositions are exactly `runtime_emitted`, `bot_delegated`, `suppressed_unsupported_surface`, `suppressed_insufficient_authority`, and `analysis_only_sideboard`.
- Keep `SOURCE_BACKED_STRONG` strict and separate from `pre_run_contract_status`.
- Do not convert unknown or builder-missing states into bot delegation.
- Do not add heuristic low-curve, role-rank, deck-name, or archetype-name Mulligan keeps.
- `operator_summary.json` remains the only normal apply authority.

---

### Task 1: Freeze the Audited Semantic Inventory

**Files:**
- Create: `src/hsconfig/semantic_inventory.py`
- Create: `tests/fixtures/near100/current_semantic_inventory.json`
- Create: `tests/fixtures/near100/score_metric_contract.json`
- Create: `tests/test_near100_semantic_inventory.py`
- Read: `docs/operator/audited-deck-catalog.json`
- Read: `tests/fixtures/audited_deck_card_db.json`

**Interfaces:**
- Consumes: canonical audited catalog and the one-time projection from the twelve current integrity-audited packages.
- Produces: `SemanticInventorySummary` and a tracked fixture independent of ignored `outputs/`.

- [ ] **Step 1: Write the failing inventory contract test**

```python
from hsconfig.semantic_inventory import validate_semantic_inventory


def test_near100_inventory_freezes_approved_counts(inventory, audited_catalog):
    summary = validate_semantic_inventory(
        inventory,
        audited_catalog=audited_catalog["decks"],
    )
    assert summary.deck_count == 12
    assert summary.main_slot_count == 360
    assert summary.main_card_identity_count == 205
    assert summary.sideboard_module_count == 3
    assert summary.disposition_row_count == 208
    assert summary.claim_count == 316
    assert summary.globalvalues_decision_count == 456


def test_score_contract_freezes_all_hard_minimums(score_contract):
    assert score_contract["overall_minimum"] == 98
    assert score_contract["gameplay_quality"] == "not_applicable"
    assert score_contract["open_p0_maximum"] == 0
    assert score_contract["open_p1_maximum"] == 0
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
python -m pytest tests/test_near100_semantic_inventory.py -q -p no:cacheprovider
```

Expected: import failure for `hsconfig.semantic_inventory`.

- [ ] **Step 3: Implement the typed summary and strict validator**

```python
@dataclass(frozen=True, slots=True)
class SemanticInventorySummary:
    deck_count: int
    main_slot_count: int
    main_card_identity_count: int
    sideboard_module_count: int
    disposition_row_count: int
    claim_count: int
    globalvalues_decision_count: int


def validate_semantic_inventory(
    inventory: Mapping[str, Any],
    *,
    audited_catalog: Sequence[Mapping[str, Any]],
) -> SemanticInventorySummary:
    rows = tuple(inventory["decks"])
    if inventory["schema_version"] != 1:
        raise ValueError("semantic_inventory_schema_invalid")
    expected_names = tuple(row["deck_name"] for row in audited_catalog)
    if tuple(row["deck_name"] for row in rows) != expected_names:
        raise ValueError("semantic_inventory_catalog_mismatch")
    if len(set(expected_names)) != 12:
        raise ValueError("semantic_inventory_deck_identity_invalid")
    main_cards = tuple(card for row in rows for card in row["main_cards"])
    modules = tuple(card for row in rows for card in row["sideboard_modules"])
    claims = tuple(claim for row in rows for claim in row["claims"])
    decisions = tuple(
        decision for row in rows for decision in row["globalvalues_decisions"]
    )
    return SemanticInventorySummary(
        deck_count=len(rows),
        main_slot_count=sum(int(card["count"]) for card in main_cards),
        main_card_identity_count=len(main_cards),
        sideboard_module_count=len(modules),
        disposition_row_count=len(main_cards) + len(modules),
        claim_count=len(claims),
        globalvalues_decision_count=len(decisions),
    )
```

The validator must decode and recompute each deck fingerprint, require 30 main slots per deck, require unique ordered composite card keys, validate every sideboard module against its owner, require globally unique exact claim IDs, require the exact ordered 38-key baseline for every deck, reject missing/extra/duplicate rows, and verify the fixture's canonical content SHA-256. The fixture lists these derived per-deck counts:

The score fixture freezes the metric IDs and minima `99/99/98/100/98/96/98/98/100`, overall minimum 98, gameplay `not_applicable`, and zero open P0/P1. Plan 04 implements the evidence-backed computation without changing this fixture.

```text
ShadowPriest 16/27/38; CtAPaladin 18/25/38; PirateRogue 16/24/38;
BigShaman 18/32/38; Discolock 17/37/38; TreantDruid 16/21/38;
ImbueMage 17/26/38; MechPala 19/20/38; Kingslayer 18/26/38;
Boarlock 18/31/38; PirateDH 18/27/38; CuteWarrior 17/20/38.
```

- [ ] **Step 4: Run GREEN and identity regressions**

```powershell
python -m pytest tests/test_near100_semantic_inventory.py tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/semantic_inventory.py tests/fixtures/near100/current_semantic_inventory.json tests/fixtures/near100/score_metric_contract.json tests/test_near100_semantic_inventory.py
git commit -m "test: freeze near-100 semantic inventory"
git push origin main
```

### Task 2: Add Typed Evidence Lanes and the Versioned Policy

**Files:**
- Create: `src/hsconfig/evidence_contract.py`
- Create: `src/hsconfig/policies/BOT_NATIVE_PRE_RUN-v1.json`
- Create: `tests/test_evidence_contract.py`
- Modify: `src/hsconfig/package_domain.py`
- Modify: `pyproject.toml`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/source_evidence_policy.py`
- Modify: `src/hsconfig/source_contract_audit.py`

**Interfaces:**
- Consumes: claim, deck identity, verified receipts, packaged policy profile.
- Produces: `EvidenceAuthority` for every claim; no unknown lane.

- [ ] **Step 1: Write failing lane-classification tests**

```python
def test_exact_live_guide_requires_matching_fingerprint_and_receipt():
    authority = classify_evidence_authority(
        claim=exact_claim(),
        deck_identity=deck_identity(),
        verified_source_receipts=matching_receipts(),
        policy_profile=policy_profile(),
    )
    assert authority.lane is EvidenceLane.EXACT_LIVE_GUIDE
    assert authority.runtime_authorized is True


def test_missing_metadata_does_not_become_bot_delegation():
    with pytest.raises(ValueError, match="evidence_lane_unclassified"):
        classify_evidence_authority(
            claim={},
            deck_identity=deck_identity(),
            verified_source_receipts=(),
            policy_profile=policy_profile(),
        )
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_evidence_contract.py -q -p no:cacheprovider
```

Expected: import failure for `hsconfig.evidence_contract`.

- [ ] **Step 3: Implement exact package-domain types and classification**

```python
class EvidenceLane(StrEnum):
    OFFICIAL_CARD_DATA = "A"
    EXACT_LIVE_GUIDE = "B"
    ARCHETYPE_OR_MECHANIC_GUIDE = "C"
    VERSIONED_INTERNAL_POLICY = "D"
    BOT_DELEGATION = "E"


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    policy_id: str
    version: int
    effective_date: str
    content_sha256: str
    rules_canonical_json: bytes


@dataclass(frozen=True, slots=True)
class EvidenceAuthority:
    lane: EvidenceLane
    authority_id: str
    source_identity: str
    as_of_date: str
    claim_kind: str
    content_sha256: str
    exact_deck_fingerprint: str | None
    runtime_authorized: bool
    reason: str


@dataclass(frozen=True, slots=True)
class LayeredEvidenceContract:
    deck_fingerprint: str
    authorities: tuple[EvidenceAuthority, ...]
    exact_guide_authority: bool
    layered_coverage_numerator: int
    layered_coverage_denominator: int
    content_sha256: str


def classify_evidence_authority(
    *,
    claim: Mapping[str, Any],
    deck_identity: Mapping[str, Any],
    verified_source_receipts: Sequence[Mapping[str, Any]],
    policy_profile: Mapping[str, Any],
) -> EvidenceAuthority:
    ...
```

The shown immutable value types live in `package_domain.py`; `evidence_contract.py` owns classification functions and does not redefine them. Implement `classify_evidence_authority` so lane B requires `live_http`, `live_verified`, full text, complete exact evidence, matching deck fingerprint, and a verified receipt. Lane D requires the packaged policy ID, version, and content hash. Lane E is constructed only by disposition compilation.

The policy JSON must contain `policy_id=BOT_NATIVE_PRE_RUN`, `version=1`, an effective date, and explicit rules; it must contain no curve-ranking or generic keep heuristic.

- [ ] **Step 4: Run GREEN and source regressions**

```powershell
python -m pytest tests/test_evidence_contract.py tests/test_source_evidence_policy.py tests/test_source_claim_lifecycle.py tests/test_claim_kind_runtime_contract.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```powershell
git add pyproject.toml src/hsconfig/package_domain.py src/hsconfig/evidence_contract.py src/hsconfig/policies/BOT_NATIVE_PRE_RUN-v1.json src/hsconfig/source_document_model.py src/hsconfig/source_evidence_policy.py src/hsconfig/source_contract_audit.py tests/test_evidence_contract.py
git commit -m "feat: add layered pre-run evidence contract"
git push origin main
```

### Task 3: Close Source Acquisition with Frozen Bundles

**Files:**
- Create: `src/hsconfig/source_acquisition_closure.py`
- Create: `tests/test_source_acquisition_closure.py`
- Modify: `src/hsconfig/source_acquisition.py`
- Modify: `src/hsconfig/source_research_manifest.py`
- Modify: `src/hsconfig/source_bundle.py`
- Modify: `src/hsconfig/commands/source_workflow.py`
- Modify: `src/hsconfig/commands/configure.py`

**Interfaces:**
- Consumes: deck identity, research manifest, acquisition report, source records, policy profile.
- Produces: `AcquisitionClosure` and frozen bundle hash.

- [ ] **Step 1: Write failing positive and negative closure tests**

```python
def test_negative_search_closes_acquisition_without_guide_authority():
    closure = build_acquisition_closure(
        deck_identity=deck_identity(),
        research_manifest=manifest(),
        acquisition_report=negative_report(),
        source_records=(),
        policy_profile=policy_profile(),
    )
    assert closure.status == "closed_negative_search"
    assert closure.negative_search_documented is True
    assert closure.successful_evidence_ids == ()
    assert closure.attempted_urls
    assert closure.failed_attempts
    assert closure.checked_dossier is True
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_source_acquisition_closure.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement immutable closure and frozen source bundle**

```python
@dataclass(frozen=True, slots=True)
class AcquisitionFailure:
    source_identity: str
    reason_code: str
    attempted_at: str


@dataclass(frozen=True, slots=True)
class AcquisitionClosure:
    deck_fingerprint: str
    attempt_id: str
    attempted_at: str
    attempted_urls: tuple[str, ...]
    successful_evidence_ids: tuple[str, ...]
    failed_attempts: tuple[AcquisitionFailure, ...]
    negative_search_documented: bool
    checked_dossier: bool
    policy_id: str | None
    status: Literal["closed_with_evidence", "closed_negative_search", "open"]
    content_sha256: str


def freeze_source_bundle(
    *,
    deck_identity: Mapping[str, Any],
    closure: AcquisitionClosure,
    source_records: Sequence[Mapping[str, Any]],
    policy_profile: Mapping[str, Any],
) -> dict[str, Any]:
    ...


def build_acquisition_closure(
    *,
    deck_identity: Mapping[str, Any],
    research_manifest: Mapping[str, Any],
    acquisition_report: Mapping[str, Any],
    source_records: Sequence[Mapping[str, Any]],
    policy_profile: PolicyProfile,
) -> AcquisitionClosure:
    ...
```

`build_acquisition_closure` derives `negative_search_documented`; callers cannot set it. Negative closure requires a matching deck fingerprint, normalized date, non-empty attempted queries/URLs, recorded outcome for every attempt, checked local dossier, and matching policy ID/hash. Implement `freeze_source_bundle` to exclude absolute paths and raw deck codes and bind each adopted text claim to Evidence ID, source/policy ID, date, claim kind, and SHA-256. Add CuteWarrior to the research manifest aliases.

- [ ] **Step 4: Run GREEN and acquisition regressions**

```powershell
python -m pytest tests/test_source_acquisition_closure.py tests/test_source_acquisition.py tests/test_source_acquisition_strong_closure.py tests/test_source_bundle.py tests/test_source_research_manifest.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/source_acquisition_closure.py src/hsconfig/source_acquisition.py src/hsconfig/source_research_manifest.py src/hsconfig/source_bundle.py src/hsconfig/commands/source_workflow.py src/hsconfig/commands/configure.py tests/test_source_acquisition_closure.py
git commit -m "feat: freeze source acquisition closure"
git push origin main
```

### Task 4: Build the Canonical Disposition Ledger and Dual Closure

**Files:**
- Create: `src/hsconfig/disposition_ledger.py`
- Create: `tests/test_disposition_ledger.py`
- Create: `tests/test_dual_closure.py`
- Modify: `src/hsconfig/source_contract_audit.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/source_to_runtime_explainability.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/package_domain.py`

**Interfaces:**
- Consumes: evidence contract, lifecycle rows, physical emission index, runtime surface ledger, plans.
- Produces: one canonical `DispositionLedger` and `DualClosureStatus`.

- [ ] **Step 1: Write failing precedence and completeness tests**

```python
def test_physical_meaningful_row_wins_disposition_precedence():
    ledger = build_disposition_ledger(**runtime_emitted_inputs())
    assert ledger.cards[0].disposition is CardDisposition.RUNTIME_EMITTED


def test_unknown_builder_state_blocks_complete_closure():
    status = build_dual_closure(
        dispositions=ledger_with_unknown_state(),
        globalvalues_decisions=complete_globalvalues(),
        strategy_source_status="partial",
    )
    assert status.pre_run_contract_status == "incomplete"
    assert "unclassified_card_disposition" in status.unresolved_reasons
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_disposition_ledger.py tests/test_dual_closure.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement exact enums and precedence**

```python
class CardDisposition(StrEnum):
    RUNTIME_EMITTED = "runtime_emitted"
    BOT_DELEGATED = "bot_delegated"
    SUPPRESSED_UNSUPPORTED_SURFACE = "suppressed_unsupported_surface"
    SUPPRESSED_INSUFFICIENT_AUTHORITY = "suppressed_insufficient_authority"
    ANALYSIS_ONLY_SIDEBOARD = "analysis_only_sideboard"


class ClaimDisposition(StrEnum):
    RUNTIME_EMITTED = "runtime_emitted"
    CONTRACT_ONLY = "contract_only"
    BOT_DELEGATED = "bot_delegated"
    SUPPRESSED_UNSUPPORTED_SURFACE = "suppressed_unsupported_surface"
    SUPPRESSED_INSUFFICIENT_AUTHORITY = "suppressed_insufficient_authority"


@dataclass(frozen=True, slots=True)
class CardDispositionRow:
    deck_fingerprint: str
    composite_card_key: str
    zone: Literal["main_deck", "sideboard_module"]
    official_semantics_canonical_json: bytes
    authority_lane: EvidenceLane
    evidence_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    physical_owner: str
    disposition: CardDisposition
    runtime_paths: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class ClaimDispositionRow:
    deck_fingerprint: str
    claim_id: str
    claim_kind: str
    evidence_id: str
    disposition: ClaimDisposition
    runtime_paths: tuple[str, ...]
    reason_code: str


@dataclass(frozen=True, slots=True)
class DispositionLedger:
    deck_fingerprint: str
    cards: tuple[CardDispositionRow, ...]
    claims: tuple[ClaimDispositionRow, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class DualClosureStatus:
    pre_run_contract_status: Literal["complete", "incomplete"]
    strategy_authority_status: Literal["partial", "strong"]
    exact_guide_authority: bool
    unresolved_reasons: tuple[str, ...]


def build_disposition_ledger(
    *,
    evidence_contract: Mapping[str, Any],
    claim_lifecycle_rows: Sequence[Mapping[str, Any]],
    physical_emission_index: Mapping[str, Sequence[str]],
    runtime_surface_ledger: Mapping[str, Any],
) -> DispositionLedger:
    ...


def build_dual_closure(
    *,
    dispositions: DispositionLedger,
    globalvalues_decisions: Sequence[Mapping[str, Any]],
    strategy_source_status: Literal["partial", "strong"],
) -> DualClosureStatus:
    ...
```

The row/ledger value types live in `package_domain.py`; `disposition_ledger.py` owns builders and projections. Physical meaningful emission wins; MechPala modules become analysis-only; unsupported expressibility and insufficient authority remain distinct; bot delegation must be intentional. Every one of the 316 exact claim IDs receives exactly one final `ClaimDispositionRow`. Project existing audit/readiness reports from this ledger.

- [ ] **Step 4: Run GREEN and closure regressions**

```powershell
python -m pytest tests/test_disposition_ledger.py tests/test_dual_closure.py tests/test_source_contract_audit.py tests/test_config_readiness.py tests/test_runtime_surface_ledger.py tests/test_source_to_runtime_explainability.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/package_domain.py src/hsconfig/disposition_ledger.py src/hsconfig/source_contract_audit.py src/hsconfig/config_readiness.py src/hsconfig/source_to_runtime_explainability.py src/hsconfig/package_builder.py tests/test_disposition_ledger.py tests/test_dual_closure.py
git commit -m "feat: add canonical pre-run disposition ledger"
git push origin main
```

### Task 5: Replace Heuristic Mulligan Fallback with Bot Delegation

**Files:**
- Create: `tests/test_mulligan_bot_delegation.py`
- Modify: `src/hsconfig/mulligan_plan.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/compile_mulligan.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `tests/test_mulligan_plan.py`
- Delete after GREEN: `src/hsconfig/autonomous_mulligan_policy.py`
- Delete after GREEN: `tests/test_autonomous_mulligan_policy.py`

**Interfaces:**
- Consumes: lane B exact claims or lane D explicit deterministic policy claims.
- Produces: exact keeps plus visible bot delegation; empty Mulligan values are valid.

- [ ] **Step 1: Write the seven-card delegation regression**

```python
@pytest.mark.parametrize(
    "card_id",
    ["JAM_013", "VAC_939", "EDR_804", "DMF_519", "CS2_146", "BOT_020", "SW_448"],
)
def test_contextual_or_start_of_game_cards_delegate_without_exact_keep(card_id):
    plan = build_mulligan_plan(**plan_inputs_for(card_id))
    assert all(row.card_id != card_id for row in plan.rules)
    assert card_id in {row.card_id for row in plan.bot_delegated}
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_mulligan_bot_delegation.py -q -p no:cacheprovider
```

- [ ] **Step 3: Remove heuristic inputs and implement explicit authority**

Use this final signature:

```python
def build_mulligan_plan(
    *,
    deck_name: str,
    claims: Sequence[Mapping[str, Any]],
    card_roles: Mapping[str, Any],
    deck_cards: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
    policy_profile: PolicyProfile,
    internal_policy_claims: Sequence[Mapping[str, Any]] = (),
    source_claim_lifecycle_rows: Sequence[Mapping[str, Any]] | None = None,
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] = (),
) -> MulliganPlanModel:
```

Remove `allow_policy_backed`, role ranking, deck-name archetype inference, and lowest-curve selection. Compile `{"values": []}` for a fully delegated Mulligan without adding wildcard discard.

Construct the `MulliganPlanModel`, `MulliganRuleModel`, `MulliganSuppressionModel`, and `BotDelegationModel` types defined in Plan 02 Task 4. Every `bot_delegated` value has `card_id: str`, `evidence_lane: Literal["E"]`, `policy_id: Literal["BOT_NATIVE_PRE_RUN"]`, and `reason_code: str`. `compile_mulligan` accepts only `MulliganPlanModel` at the new internal boundary and serializes the existing runtime `{"values": [...]}` shape; the canonical report serializer preserves the existing public field names. Compatibility dictionary parsing is confined to the CLI/input adapter and removed before Plan 02 Task 8 byte parity.

- [ ] **Step 4: Run GREEN and semantic boundary tests**

```powershell
python -m pytest tests/test_mulligan_bot_delegation.py tests/test_mulligan_plan.py tests/test_compile_mulligan.py tests/test_semantic_runtime_negative_boundaries.py -q -p no:cacheprovider
```

Then remove the obsolete policy module and its old test and rerun the same command.

- [ ] **Step 5: Commit**

```powershell
git add -A src/hsconfig/mulligan_plan.py src/hsconfig/package_builder.py src/hsconfig/compile_mulligan.py src/hsconfig/operator_summary.py src/hsconfig/autonomous_mulligan_policy.py tests/test_mulligan_bot_delegation.py tests/test_mulligan_plan.py tests/test_autonomous_mulligan_policy.py
git commit -m "fix: delegate unsupported Mulligan decisions to the bot"
git push origin main
```

### Task 6: Add the Typed GlobalValues Decision Ledger

**Files:**
- Create: `src/hsconfig/globalvalues_decisions.py`
- Create: `tests/test_globalvalues_decisions.py`
- Modify: `src/hsconfig/globalvalues_authority.py`
- Modify: `src/hsconfig/compile_globalvalues.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/package_domain.py`

**Interfaces:**
- Consumes: deck fingerprint, baseline, baseline hash, authority matrix.
- Produces: exactly one typed decision per baseline key.

- [ ] **Step 1: Write failing 38-key and typed-parity tests**

```python
def test_baseline_profile_closes_all_38_keys():
    ledger = build_globalvalues_decision_ledger(**baseline_inputs())
    assert len(ledger.decisions) == 38
    assert {row.kind for row in ledger.decisions} == {
        GlobalValueDecisionKind.COPY_BASELINE
    }
    assert all(row.baseline_value == row.emitted_value for row in ledger.decisions)
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_globalvalues_decisions.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement immutable decisions**

```python
class GlobalValueDecisionKind(StrEnum):
    COPY_BASELINE = "copy_baseline"
    AUTHORIZED_OVERLAY = "authorized_overlay"


@dataclass(frozen=True, slots=True)
class GlobalValueDecision:
    deck_fingerprint: str
    key: str
    kind: GlobalValueDecisionKind
    baseline_canonical_json: bytes
    emitted_canonical_json: bytes
    authority_id: str
    claim_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class GlobalValuesDecisionLedger:
    deck_fingerprint: str
    baseline_sha256: str
    decisions: tuple[GlobalValueDecision, ...]
    content_sha256: str


def build_globalvalues_decision_ledger(
    *,
    deck_fingerprint: str,
    baseline: Mapping[str, Any],
    baseline_sha256: str,
    authority_matrix: Mapping[str, Any],
) -> GlobalValuesDecisionLedger:
    ...
```

The decision/ledger value types live in `package_domain.py`; `globalvalues_decisions.py` owns construction. Require exact canonical-JSON byte equality for `copy_baseline`; require explicit operation, canonical value bytes, and claim authority for overlays. Construction defensively copies mutable input data before canonicalization.

The ledger contains exactly the registry's 38 keys in registry order, rejects duplicate/missing/extra keys, serializes canonical JSON bytes as parsed JSON values in the report, and computes `content_sha256` from the ordered key/kind/value/authority/claim-ID records.

- [ ] **Step 4: Run GREEN and compiler regressions**

```powershell
python -m pytest tests/test_globalvalues_decisions.py tests/test_globalvalues_authority.py tests/test_compile_globalvalues.py tests/test_globalvalues_key_authority.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```powershell
git add src/hsconfig/package_domain.py src/hsconfig/globalvalues_decisions.py src/hsconfig/globalvalues_authority.py src/hsconfig/compile_globalvalues.py src/hsconfig/package_builder.py tests/test_globalvalues_decisions.py
git commit -m "feat: close every GlobalValues decision"
git push origin main
```

### Task 7: Project and Accept the Twelve-Deck Pre-Run Closure

**Files:**
- Create: `tests/test_pre_run_semantic_closure_e2e.py`
- Create: `src/hsconfig/pre_run_metrics.py`
- Create: `tests/test_pre_run_metrics.py`
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/source_evidence_closure.py`
- Modify: `src/hsconfig/source_bundle.py`

**Interfaces:**
- Consumes: evidence, acquisition, disposition, and GlobalValues ledgers.
- Produces: five canonical reports and the operator pre-run projection.

- [ ] **Step 1: Write the failing aggregate acceptance test**

```python
def test_all_twelve_decks_have_complete_pre_run_closure(audited_packages):
    totals = aggregate_pre_run_closure(audited_packages)
    assert totals == {
        "deck_count": 12,
        "main_slot_count": 360,
        "main_card_identity_count": 205,
        "sideboard_module_count": 3,
        "card_disposition_count": 208,
        "final_card_disposition_count": 208,
        "claim_count": 316,
        "final_claim_disposition_count": 316,
        "globalvalues_decision_count": 456,
        "final_globalvalues_decision_count": 456,
        "emission_precision": 1.0,
        "eligible_emission_recall": 1.0,
    }
```

Define metrics in `src/hsconfig/pre_run_metrics.py`:

```python
def emission_precision(ledger: DispositionLedger) -> Fraction:
    return Fraction(authorized_meaningful_emissions, physical_meaningful_emissions)


def eligible_emission_recall(ledger: DispositionLedger) -> Fraction:
    return Fraction(emitted_eligible_rows, eligible_rows)


def aggregate_pre_run_closure(
    packages: Sequence[PackageView],
) -> dict[str, int | float]:
    ...
```

`physical_meaningful_emissions` comes from the verified physical emission index; `authorized_meaningful_emissions` is its subset with owner, surface, row-schema, and authority parity. `eligible_rows` excludes bot-delegated, unsupported, insufficient-authority, and analysis-only rows. A zero denominator is valid only when the corresponding numerator is zero and is represented as `Fraction(1, 1)` with `vacuous=true` in the report.

`ClaimDisposition.CONTRACT_ONLY` is explicitly non-emittable: it represents a fully closed semantic claim whose claim-kind-to-surface registry permits no runtime lowering. The fail-closed `is_emission_eligible(row)` function returns true only for a claim/card row with an allowed surface, sufficient authority, physical owner parity, supported schema, and no bot/suppression/analysis/contract-only disposition.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_pre_run_metrics.py tests/test_pre_run_semantic_closure_e2e.py -q -p no:cacheprovider
```

- [ ] **Step 3: Emit canonical reports and operator fields**

Emit:

```text
reports/layered_evidence_contract.json
reports/source_acquisition_closure.json
reports/disposition_ledger.json
reports/globalvalues_decision_ledger.json
reports/pre_run_closure.json
```

Project these operator fields:

```text
hsconfig_scope=PRE_RUN_CONTRACT
gameplay_strategy_owner=hearthranger_bot
gameplay_quality=OUT_OF_SCOPE_ASSUMED_EXTERNAL
bot_gameplay_assumption=trusted_external
pre_run_contract_status=complete
strategy_authority_status=partial|strong
```

The schema validates `strategy_authority_status` against the two literal values and emits one of them, never the pipe-delimited text. It also reports exact-guide authority as `exact_guide_authority_decks` and `exact_guide_authority_total=12`, plus a computed `layered_pre_run_source_coverage` numerator/denominator. Keep all fields diagnostic; do not add them to `ApplyFacts`.

- [ ] **Step 4: Run GREEN and no-second-gate regressions**

```powershell
python -m pytest tests/test_pre_run_metrics.py tests/test_pre_run_semantic_closure_e2e.py tests/test_audited_deck_set_acceptance.py tests/test_operator_summary.py tests/test_no_second_gate_contract.py tests/test_apply_authority_boundary.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit and run the subplan gate**

```powershell
python -m ruff check --no-cache src tests scripts
python -m pytest tests/test_pre_run_semantic_closure_e2e.py tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
python -m hsconfig.cli contract-spine-sentinel --json
git diff --check
git add src/hsconfig/pre_run_metrics.py src/hsconfig/package_builder.py src/hsconfig/operator_summary.py src/hsconfig/source_evidence_closure.py src/hsconfig/source_bundle.py tests/test_pre_run_metrics.py tests/test_pre_run_semantic_closure_e2e.py
git commit -m "feat: close the audited pre-run semantic contract"
git push origin main
```
