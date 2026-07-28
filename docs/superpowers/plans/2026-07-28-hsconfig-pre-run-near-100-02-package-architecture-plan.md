# HSConfig Package Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace duplicated contract knowledge and path-coupled package logic with one typed registry, one immutable package model, pure quality/status projections, and a thin configure workflow while preserving byte-identical package behavior.

**Architecture:** First centralize runtime-surface and report metadata, then remove correctness-sensitive `assert` statements. Introduce `PackageModel` as an adapter over the existing generated tree and prove byte parity before making it the canonical build product. Migrate quality, operator status, assembly, and configure orchestration only after the model boundary is stable; remove aliases and dead modules last.

**Tech Stack:** Python 3.11/3.12, frozen slotted dataclasses, `StrEnum`, structural `Protocol`, canonical JSON bytes, SHA-256, pytest snapshot/parity tests, Ruff.

## Global Constraints

- Preserve every semantic disposition and count established by Plan 01.
- `reports/operator_summary.json` remains the sole normal apply authority.
- Registry consumers may project policy; they may not redefine it locally.
- Package validation must work through `PackageView`, not require a physical package directory.
- Package artifacts are immutable after `PackageModel` construction.
- Preserve the existing package bytes until a separately reviewed schema change explicitly authorizes a difference.
- Do not delete compatibility reports or legacy modules until adoption tests prove zero production consumers.
- Do not use Python `assert` for production validation.
- Keep gameplay quality `OUT_OF_SCOPE_ASSUMED_EXTERNAL`.

---

### Task 1: Establish the Single VisionAI Registry

**Files:**
- Create: `tests/test_contract_registry.py`
- Create: `tests/test_contract_registry_adoption.py`
- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/acceptance_matrix.py`
- Modify: `src/hsconfig/config_readiness.py`
- Modify: `src/hsconfig/config_quality_contract.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/validate_package.py`
- Modify: `src/hsconfig/strong_promotion_report.py`
- Modify: `src/hsconfig/runtime_surface_ledger.py`
- Modify: `src/hsconfig/contract_preflight.py`
- Modify: `src/hsconfig/contract_spine_sentinel.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class RuntimeSurfaceSpec:
    file_name: str
    classification: Literal[
        "required",
        "optional",
        "conditional_card_surface",
        "forbidden",
    ]
    normal_apply_allowed: bool
    row_schema_id: str
    value_type_id: str
    physical_owner_rule_id: str


@dataclass(frozen=True, slots=True)
class ClaimSurfaceRule:
    claim_kind: str
    allowed_surfaces: tuple[str, ...]
    required_authority_lanes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GlobalValueKeySpec:
    key: str
    value_type_id: str
    key_class: str
    overlay_authority_required: bool


@dataclass(frozen=True, slots=True)
class ReportSpec:
    relative_path: str
    required: bool
    apply_authority: bool
    ownership: str


NORMAL_APPLY_AUTHORITY = "reports/operator_summary.json"
RUNTIME_SURFACE_REGISTRY: Mapping[str, RuntimeSurfaceSpec]
REPORT_REGISTRY: Mapping[str, ReportSpec]
CLAIM_SURFACE_REGISTRY: Mapping[str, ClaimSurfaceRule]
GLOBALVALUES_KEY_REGISTRY: Mapping[str, GlobalValueKeySpec]


def runtime_surface_spec(file_name: str) -> RuntimeSurfaceSpec: ...
def normalize_runtime_surface(file_name: str) -> str: ...
def classify_runtime_surface(file_name: str) -> str: ...
def report_spec(relative_path: str) -> ReportSpec: ...
```

- [ ] **Step 1: Write failing registry invariant tests**

```python
def test_registry_has_one_normal_apply_authority():
    authorities = [
        spec.relative_path
        for spec in REPORT_REGISTRY.values()
        if spec.apply_authority
    ]
    assert authorities == ["reports/operator_summary.json"]


def test_registry_classifies_normal_runtime_surfaces():
    assert classify_runtime_surface("GlobalValues.json") == "required"
    assert classify_runtime_surface("Mulligan.json") == "required"
    assert classify_runtime_surface("SW_448.json") == "conditional_card_surface"
    assert classify_runtime_surface("Combo.json") == "optional"
    assert classify_runtime_surface("Presume.json") == "forbidden"
    assert classify_runtime_surface("Concede.json") == "forbidden"
    assert classify_runtime_surface("CardBehavior.json") == "forbidden"
```

- [ ] **Step 2: Write the failing adoption test**

`tests/test_contract_registry_adoption.py` must parse the listed production modules with `ast` and fail if they define any of:

```text
NORMAL_APPLY_AUTHORITY
REQUIRED_RUNTIME_SURFACES
OPTIONAL_RUNTIME_SURFACES
FORBIDDEN_RUNTIME_SURFACES
REPORT_REGISTRY
CLAIM_SURFACE_REGISTRY
GLOBALVALUES_KEY_REGISTRY
```

outside `visionai_registry.py`. The adoption test also rejects duplicate row-schema, value-type, physical-owner, claim-to-surface, and GlobalValues-key-class literals outside the registry.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_contract_registry.py tests/test_contract_registry_adoption.py -q -p no:cacheprovider
```

Expected: missing new registry types/fields in `hsconfig.visionai_registry`.

- [ ] **Step 4: Implement the canonical registry and compatibility re-exports**

Move values without changing their spelling or meaning. `visionai_registry.py` is the sole definition site; do not create a compatibility registry with a second literal table.

- [ ] **Step 5: Migrate every listed consumer**

Replace local constants and inline string sets with registry lookup. Unknown surface/report names must raise `KeyError` or a typed contract error; they must never silently become optional.

Concrete CardID JSON files are conditionally required only when the package's canonical disposition ledger authorizes a meaningful physical emission. `RuntimeSurfacePlan.expected_files` is derived from that ledger; a bot-delegated or suppressed card does not make its CardID file required.

- [ ] **Step 6: Run GREEN and registry regressions**

```powershell
python -m pytest tests/test_contract_registry.py tests/test_contract_registry_adoption.py tests/test_visionai_registry.py tests/test_apply_gate.py tests/test_output_ownership_manifest.py tests/test_validate_package.py tests/test_contract_preflight.py tests/test_contract_spine_sentinel.py -q -p no:cacheprovider
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/visionai_registry.py src/hsconfig/apply_gate.py src/hsconfig/acceptance_matrix.py src/hsconfig/config_readiness.py src/hsconfig/config_quality_contract.py src/hsconfig/operator_summary.py src/hsconfig/output_ownership_manifest.py src/hsconfig/report_ownership.py src/hsconfig/validate_package.py src/hsconfig/strong_promotion_report.py src/hsconfig/runtime_surface_ledger.py src/hsconfig/contract_preflight.py src/hsconfig/contract_spine_sentinel.py tests/test_contract_registry.py tests/test_contract_registry_adoption.py
git commit -m "refactor: centralize package contract registry"
git push origin main
```

---

### Task 2: Make Contract Validation Safe Under Optimized Python

**Files:**
- Modify: `src/hsconfig/package_builder.py`
- Modify: `src/hsconfig/source_document_builder.py`
- Modify: `src/hsconfig/source_document_model.py`
- Modify: `src/hsconfig/runtime_surface_ledger.py`
- Create: `tests/test_python_optimized_mode.py`
- Modify: `scripts/check_contract_guardrails.py`
- Modify: `tests/test_check_contract_guardrails.py`

**Interfaces:**

```python
class SurfaceLedgerMismatchError(ValueError):
    pass


def require_surface_ledger_parity(
    *,
    expected: Collection[str],
    observed: Collection[str],
) -> None: ...
```

- [ ] **Step 1: Write the optimized-mode regression**

Spawn `sys.executable -O` against a deliberately invalid surface ledger and invalid source-document fixture. Assert non-zero exit and the stable error codes:

```text
runtime_surface_ledger_mismatch
source_document_contract_invalid
```

- [ ] **Step 2: Extend the guardrail test**

Require `scripts/check_contract_guardrails.py` to fail when any production file under `src/hsconfig` contains an `ast.Assert` node.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_python_optimized_mode.py tests/test_check_contract_guardrails.py -q -p no:cacheprovider
```

Expected: optimized invalid cases incorrectly pass or guardrail reports production asserts.

- [ ] **Step 4: Replace all four production assertions**

Use explicit conditionals and `ValueError` subclasses. Error messages must include a stable machine-readable reason before human context.

- [ ] **Step 5: Run GREEN in normal and optimized modes**

```powershell
python -m pytest tests/test_python_optimized_mode.py tests/test_runtime_surface_ledger.py tests/test_source_contract_conformance.py -q -p no:cacheprovider
python -O -m hsconfig.cli contract-spine-sentinel --json
python scripts/check_contract_guardrails.py
```

Expected: all commands exit 0 and the sentinel reports `status=clean`.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/package_builder.py src/hsconfig/source_document_builder.py src/hsconfig/source_document_model.py src/hsconfig/runtime_surface_ledger.py tests/test_python_optimized_mode.py scripts/check_contract_guardrails.py tests/test_check_contract_guardrails.py
git commit -m "fix: preserve contract checks under optimized Python"
git push origin main
```

---

### Task 3: Define Canonical Build Inputs

**Files:**
- Create: `src/hsconfig/build_inputs.py`
- Create: `tests/test_build_inputs.py`
- Modify: `src/hsconfig/audited_deck_catalog.py`
- Modify: `src/hsconfig/card_data_context.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class CanonicalBuildInputs:
    schema_version: int
    generator_version: str
    generator_commit: str
    deck_name: str
    deck_code_sha256: str
    deck_fingerprint: str
    card_snapshot_id: str
    card_snapshot_sha256: str
    policy_profile_id: str
    policy_profile_sha256: str
    as_of_date: str
    source_bundle_sha256s: tuple[str, ...]
    evidence_policy_ids: tuple[str, ...]
    canonical_payload: bytes
    input_sha256: str


def canonicalize_build_inputs(payload: Mapping[str, Any]) -> CanonicalBuildInputs:
    ...
```

- [ ] **Step 1: Write failing canonicalization tests**

Assert normalized ISO date, sorted unique source/policy identifiers, deck fingerprint parity with the decoded catalog, pinned card snapshot digest, generator version/commit presence, canonical UTF-8 JSON bytes, and `input_sha256=sha256(canonical_payload)`. Reject raw deckcodes, absolute paths, wall-clock defaults, unpinned card data, duplicate IDs, and unknown keys.

- [ ] **Step 2: Write synthetic hash-reference tests**

Use synthetic policy/source/card payload digests to prove the schema binds every reference without requiring the not-yet-built production policy and bundles. The final twelve-row catalog is intentionally deferred until after Contract Closure Tasks 2-7.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_build_inputs.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement schema version 1 and canonical builders**

`as_of_date` must be caller-supplied. Card-data paths are resolved only while loading; serialized inputs contain the stable snapshot ID and SHA-256, never a local path. `generator_commit` is captured once by the configure boundary and becomes data, not a later filesystem lookup.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest tests/test_build_inputs.py tests/test_audited_deck_catalog.py tests/test_card_data_context.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/build_inputs.py src/hsconfig/audited_deck_catalog.py src/hsconfig/card_data_context.py tests/test_build_inputs.py
git commit -m "feat: define canonical package build inputs"
git push origin main
```

---

### Task 4: Introduce Immutable Package and Configure-Run Models

**Files:**
- Create: `src/hsconfig/package_model.py`
- Create: `src/hsconfig/package_domain.py`
- Create: `src/hsconfig/configure_run_model.py`
- Create: `src/hsconfig/package_renderer.py`
- Create: `tests/test_package_model.py`
- Create: `tests/test_configure_run_model.py`
- Create: `tests/test_package_renderer.py`
- Read: `src/hsconfig/io.py`
- Read: `src/hsconfig/package_builder.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class PackageArtifact:
    relative_path: str
    content: bytes
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class MulliganRuleModel:
    card_id: str
    selector_kind: str
    selector_canonical_json: bytes
    action: Literal["hold", "discard"]
    condition_canonical_json: bytes
    reason: str
    confidence: str
    source_claim_ids: tuple[str, ...]
    claim_id: str | None = None


@dataclass(frozen=True, slots=True)
class MulliganSuppressionModel:
    card_id: str
    action: Literal["hold", "discard", "none"]
    reason_code: str
    source_claim_ids: tuple[str, ...]
    claim_id: str | None = None


@dataclass(frozen=True, slots=True)
class BotDelegationModel:
    card_id: str
    evidence_lane: Literal["E"]
    policy_id: Literal["BOT_NATIVE_PRE_RUN"]
    reason_code: str


@dataclass(frozen=True, slots=True)
class MulliganPlanModel:
    deck_name: str
    rules: tuple[MulliganRuleModel, ...]
    suppressed: tuple[MulliganSuppressionModel, ...]
    bot_delegated: tuple[BotDelegationModel, ...]
    merged_duplicate_rule_count: int


@dataclass(frozen=True, slots=True)
class RuntimeSurfaceDecision:
    family: Literal["GlobalValues", "Mulligan", "CardID", "Combo"]
    relative_path: str
    owner: str
    decision_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeSurfacePlan:
    surfaces: tuple[RuntimeSurfaceDecision, ...]

    @property
    def expected_files(self) -> tuple[str, ...]: ...


@dataclass(frozen=True, slots=True)
class PackageModel:
    deck_name: str
    deck_fingerprint: str
    mulligan_plan: MulliganPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    disposition_ledger: DispositionLedger
    evidence_contract: LayeredEvidenceContract
    runtime_surface_plan: RuntimeSurfacePlan


@dataclass(frozen=True, slots=True)
class RenderedPackage:
    model: PackageModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str


@dataclass(frozen=True, slots=True)
class ConfigureRunModel:
    deck_name: str
    deck_fingerprint: str
    package: PackageModel
    stage_artifacts: tuple[PackageArtifact, ...]


@dataclass(frozen=True, slots=True)
class RenderedConfigureRun:
    model: ConfigureRunModel
    artifacts: tuple[PackageArtifact, ...]
    content_root_sha256: str


class PackageView(Protocol):
    def file_names(self) -> tuple[str, ...]: ...
    def read_bytes(self, relative_path: str) -> bytes: ...
    def read_json(self, relative_path: str) -> Any: ...
    def exists(self, relative_path: str) -> bool: ...


def load_package_model(package_root: Path) -> PackageModel: ...
def render_package_model(model: PackageModel) -> RenderedPackage: ...
def build_runtime_surface_plan(
    *,
    mulligan_plan: MulliganPlanModel,
    globalvalues_ledger: GlobalValuesDecisionLedger,
    disposition_ledger: DispositionLedger,
    combo_decision_ids: tuple[str, ...],
) -> RuntimeSurfacePlan: ...
def create_configure_run_model(
    *,
    package: PackageModel,
    stage_artifacts: Mapping[str, bytes],
) -> ConfigureRunModel: ...
def render_configure_run_model(model: ConfigureRunModel) -> RenderedConfigureRun: ...
```

- [ ] **Step 1: Write model invariant tests**

`package_domain.py` owns the typed immutable `MulliganPlanModel`, its three typed row models, `GlobalValuesDecisionLedger`, `DispositionLedger`, `LayeredEvidenceContract`, `RuntimeSurfaceDecision`, and `RuntimeSurfacePlan`; Plan 01 constructs those types rather than redefining them. `PackageModel` is the sole typed truth. `render_package_model` derives runtime and report artifacts together from those fields; callers cannot provide independent runtime/report bytes.

`MulliganPlanModel` rejects duplicate rule identities, duplicate delegation rows, a card that is both exactly ruled and delegated, non-canonical selector/condition bytes, and unstable ordering. Its canonical report serializer preserves the public JSON field names while the compiler consumes typed attributes.

`RuntimeSurfacePlan` contains authorization references, never a second copy of runtime payload bytes. It always contains exactly one `GlobalValues/GlobalValues.json` and one `Mulligan/Mulligan.json` decision; contains a sorted conditional CardID decision only for each disposition-authorized physical emission; contains `Combo/Combo.json` only when all referenced combo decisions are authorized; and rejects `Presume`, `Concede`, aggregate `CardBehavior`, duplicate paths, unknown owners, and dangling decision IDs. `expected_files` is derived solely from `surfaces`. `build_runtime_surface_plan` validates every referenced Mulligan, GlobalValues, disposition, and Combo decision before returning the immutable plan.

Cover canonical forward-slash paths, rejection of absolute/parent paths, unique sorted paths, content/size digest verification, deterministic content root, immutable tuples, and JSON reading through a `PackageView`. The content-root record is exactly `path + NUL + decimal_size + NUL + sha256 + LF`.

`ConfigureRunModel` contains the complete immutable revision:

```text
01_manifest/
02_source_documents/ or 02_source_acquisition/
02_source_autopilot/ or 03_source_autopilot/
03_research/
04_package/CustomConfig/
04_package/reports/
configure_summary.json
```

Every applicable stage is present. An unavailable alternative stage is absent and explained by a stable reason in `configure_summary.json`.

- [ ] **Step 2: Write deterministic typed-fixture renderer tests**

Construct a complete `PackageModel` from fixed typed fixtures and render it twice. Assert identical artifact tuples, canonical report JSON, runtime files equal to `RuntimeSurfacePlan.expected_files`, and the same content root. Construct a complete `ConfigureRunModel` from fixed stage artifacts and assert the same invariants for the full stage tree.

```python
assert render_package_model(model) == render_package_model(model)
assert render_configure_run_model(run) == render_configure_run_model(run)
```

This task introduces an unused typed boundary; it does not adapt or reinterpret the legacy dictionary package. Cross-implementation byte parity is deliberately deferred to Task 8, after Plan 01 has implemented the canonical evidence, disposition, Mulligan, and GlobalValues constructors.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_package_model.py tests/test_configure_run_model.py tests/test_package_renderer.py -q -p no:cacheprovider
```

Expected: missing package-model imports.

- [ ] **Step 4: Implement canonical model creation**

Content-root input is the UTF-8 sequence `relative_path + "\0" + str(size) + "\0" + artifact_sha256 + "\n"` for each non-manifest artifact sorted by relative path. Renderers compute size/digest from produced bytes; loaders reject any persisted size/digest or typed-report parity mismatch.

- [ ] **Step 5: Implement strict renderer**

Render only into a nonexistent or empty destination, create parent directories, and verify every written digest plus the final content root before returning. Publication semantics remain out of scope until Plan 03.

- [ ] **Step 6: Run GREEN and repeatability**

```powershell
python -m pytest tests/test_package_model.py tests/test_configure_run_model.py tests/test_package_renderer.py tests/test_package_builder.py -q -p no:cacheprovider
1..10 | ForEach-Object { python -m pytest tests/test_package_renderer.py tests/test_configure_run_model.py -q -p no:cacheprovider; if ($LASTEXITCODE -ne 0) { throw "repeatability_failed" } }
```

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/package_model.py src/hsconfig/package_domain.py src/hsconfig/configure_run_model.py src/hsconfig/package_renderer.py tests/test_package_model.py tests/test_configure_run_model.py tests/test_package_renderer.py
git commit -m "feat: add immutable deterministic package model"
git push origin main
```

---

### Task 5: Resolve and Freeze Content-Bearing Audited Build Contexts

**Files:**
- Create: `src/hsconfig/build_input_catalog.py`
- Create: `src/hsconfig/build_context.py`
- Create: `src/hsconfig/resources/audited_build_inputs.json`
- Create: `tests/test_build_input_catalog.py`
- Create: `tests/test_build_context.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class AuditedBuildInputSet:
    schema_version: int
    builds: tuple[CanonicalBuildInputs, ...]
    content_sha256: str


@dataclass(frozen=True, slots=True)
class ResolvedBuildContext:
    inputs: CanonicalBuildInputs
    deck_cards_canonical_json: bytes
    card_snapshot_canonical_json: bytes
    policy_profile_canonical_json: bytes
    evidence_contract_canonical_json: bytes
    source_bundle_canonical_json: tuple[bytes, ...]
    globalvalues_baseline_canonical_json: bytes


class BuildResourceStore(Protocol):
    def read_by_sha256(self, content_sha256: str) -> bytes:
        ...


def load_audited_build_inputs(path: Path) -> AuditedBuildInputSet:
    ...


def resolve_build_context(
    inputs: CanonicalBuildInputs,
    *,
    resources: BuildResourceStore,
) -> ResolvedBuildContext:
    ...
```

- [ ] **Step 1: Write failing twelve-row and resolver tests**

Require one canonical input per audited deck in catalog order. Resolve every referenced card snapshot, policy, evidence contract, source bundle, and baseline by SHA-256; reject missing content, digest mismatch, wrong deck fingerprint, mutable/non-canonical JSON, network access, filesystem paths outside the explicit resource store, and extra unbound content.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_build_input_catalog.py tests/test_build_context.py -q -p no:cacheprovider
```

- [ ] **Step 3: Freeze the production input set after semantic closure**

Build `audited_build_inputs.json` only from the finalized Plan 01 policies and frozen source/evidence bundles. Recompute every row and outer digest; do not manually enter digest values.

- [ ] **Step 4: Make the compiler content-complete**

`compile_package` accepts only `ResolvedBuildContext`. It performs no network, clock, environment, Git, ambient filesystem, or global catalog lookup. All bytes it may interpret are already present and hash-verified.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest tests/test_build_input_catalog.py tests/test_build_context.py tests/test_pre_run_semantic_closure_e2e.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/build_input_catalog.py src/hsconfig/build_context.py src/hsconfig/resources/audited_build_inputs.json tests/test_build_input_catalog.py tests/test_build_context.py
git commit -m "feat: freeze audited content-bearing build contexts"
git push origin main
```

---

### Task 6: Separate Quality Inputs from Pure Quality Checks

**Files:**
- Create: `src/hsconfig/config_quality_inputs.py`
- Create: `src/hsconfig/config_quality_checks.py`
- Modify: `src/hsconfig/config_quality_contract.py`
- Create: `tests/test_config_quality_inputs.py`
- Create: `tests/test_config_quality_checks.py`
- Modify: `tests/test_config_quality_contract.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ConfigQualityInputs:
    package: PackageView
    semantic_inventory: Mapping[str, Any]
    disposition_ledger: Mapping[str, Any]
    source_closure: Mapping[str, Any]
    globalvalues_ledger: Mapping[str, Any]


def load_config_quality_inputs(package: PackageView) -> ConfigQualityInputs: ...
def evaluate_config_quality(inputs: ConfigQualityInputs) -> dict[str, Any]: ...
def build_config_quality_report(package: Path | PackageView) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write failing pure-check tests**

Construct an in-memory `PackageModel`; test one passing input and individual failures for semantic count drift, unresolved disposition, evidence digest mismatch, unexpected runtime surface, and incomplete GlobalValues decisions.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_config_quality_inputs.py tests/test_config_quality_checks.py -q -p no:cacheprovider
```

Expected: missing imports.

- [ ] **Step 3: Implement the loader and pure evaluator**

The loader performs I/O interpretation only. The evaluator accepts only the frozen input object and returns deterministic data without reading the clock, environment, filesystem, or network.

- [ ] **Step 4: Reduce the existing module to a compatibility facade**

`build_config_quality_report` converts `Path` to a package view when needed, calls the loader and evaluator, and preserves the current output schema.

- [ ] **Step 5: Run GREEN and facade parity**

```powershell
python -m pytest tests/test_config_quality_inputs.py tests/test_config_quality_checks.py tests/test_config_quality_contract.py tests/test_semantic_runtime_negative_boundaries.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/config_quality_inputs.py src/hsconfig/config_quality_checks.py src/hsconfig/config_quality_contract.py tests/test_config_quality_inputs.py tests/test_config_quality_checks.py tests/test_config_quality_contract.py
git commit -m "refactor: make package quality evaluation pure"
git push origin main
```

---

### Task 7: Separate Operator Inputs, Status, and Diagnostics

**Files:**
- Create: `src/hsconfig/operator_summary_inputs.py`
- Create: `src/hsconfig/operator_status.py`
- Create: `src/hsconfig/operator_diagnostics.py`
- Modify: `src/hsconfig/operator_summary.py`
- Create: `tests/test_operator_summary_inputs.py`
- Create: `tests/test_operator_status.py`
- Create: `tests/test_operator_diagnostics.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_apply_authority_boundary.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class OperatorSummaryInputs:
    package: PackageView
    quality_report: Mapping[str, Any]
    validation_report: Mapping[str, Any]
    source_closure: Mapping[str, Any]
    ownership_manifest: Mapping[str, Any]


def determine_operator_status(inputs: OperatorSummaryInputs) -> str: ...
def build_operator_diagnostics(inputs: OperatorSummaryInputs) -> tuple[dict[str, Any], ...]: ...
def build_operator_summary(inputs: OperatorSummaryInputs) -> dict[str, Any]: ...
```

- [ ] **Step 1: Write the status truth-table tests**

Cover `READY_TO_APPLY`, each fail-closed non-ready state, and the explicit gameplay marker. Assert no diagnostic can elevate a non-ready status.

- [ ] **Step 2: Write the sole-authority boundary test**

Scan every generated report and assert that only `reports/operator_summary.json` has `normal_apply_authority=true` in the registry and only its recomputed decision can authorize apply.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_operator_summary_inputs.py tests/test_operator_status.py tests/test_operator_diagnostics.py tests/test_apply_authority_boundary.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement pure projections and slim the facade**

Status must depend on typed inputs, not path existence checks interleaved with rendering. Diagnostics are explanatory only and sorted by stable reason code.

- [ ] **Step 5: Run GREEN and regressions**

```powershell
python -m pytest tests/test_operator_summary_inputs.py tests/test_operator_status.py tests/test_operator_diagnostics.py tests/test_operator_summary.py tests/test_apply_authority_boundary.py tests/test_no_second_gate_contract.py tests/test_apply_gate.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/operator_summary_inputs.py src/hsconfig/operator_status.py src/hsconfig/operator_diagnostics.py src/hsconfig/operator_summary.py tests/test_operator_summary_inputs.py tests/test_operator_status.py tests/test_operator_diagnostics.py tests/test_operator_summary.py tests/test_apply_authority_boundary.py
git commit -m "refactor: isolate operator status authority"
git push origin main
```

---

### Task 8: Compile and Assemble Packages Without Path-Coupled Mutation

**Files:**
- Create: `src/hsconfig/package_compiler.py`
- Create: `src/hsconfig/package_assembler.py`
- Modify: `src/hsconfig/package_builder.py`
- Create: `tests/fixtures/package-byte-contract-v1.json`
- Create: `tests/test_package_compiler.py`
- Create: `tests/test_package_assembler.py`
- Create: `tests/test_package_byte_parity.py`
- Modify: `tests/test_package_builder.py`
- Modify: `tests/test_package_builder_runtime_filter.py`
- Modify: `tests/test_package_derivation_receipt.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class CompiledPackage:
    build_context: ResolvedBuildContext
    deck_name: str
    deck_fingerprint: str
    mulligan_plan: MulliganPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    disposition_ledger: DispositionLedger
    evidence_contract: LayeredEvidenceContract
    runtime_surface_plan: RuntimeSurfacePlan


def compile_package(context: ResolvedBuildContext) -> CompiledPackage: ...
def assemble_package_model(compiled: CompiledPackage) -> PackageModel: ...
def prepare_package_payload(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
    stage_observer: StageObserver | None = None,
    mulligan_source_gaps: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], int]: ...
```

- [ ] **Step 1: Write compiler tests**

Assert compilation produces only typed registry-authorized domain decisions and performs no rendering, filesystem, network, clock, environment, or global lookup.

- [ ] **Step 2: Write assembler tests**

Assert the assembler creates one immutable typed `PackageModel`; the renderer then derives reports and runtime artifacts from that same object, duplicate paths fail, and all ownership/derivation reports describe that exact model.

- [ ] **Step 3: Freeze the post-closure legacy byte contract before refactoring**

While `package_builder.py` still uses the current dictionary pipeline—but after Plan 01 semantic closure—build all twelve audited packages twice in clean temporary roots. Require the two runs to be byte-identical, then write only this reviewed characterization fixture:

```json
{
  "schema_version": 1,
  "decks": {
    "ShadowPriest": {
      "deck_fingerprint": "<canonical fingerprint>",
      "artifacts": [
        {"relative_path": "CustomConfig/GlobalValues/GlobalValues.json", "size": 0, "sha256": "<64 lowercase hex>"}
      ],
      "content_root_sha256": "<64 lowercase hex>"
    }
  }
}
```

The actual fixture contains every file for every audited deck, sorted by deck and relative path; `size` is the real decimal byte length, never the illustrative zero above. It contains no raw private evidence, runtime logs, deckcodes beyond the already public audited catalog, or generated package bytes. Review the fixture diff before changing `package_builder.py`.

`tests/test_package_byte_parity.py` first proves the current builder matches every recorded path/size/digest. After the refactor, the same test proves `compile_package -> assemble_package_model -> render_package_model` matches the exact same contract. No adapter may fabricate evidence, disposition, GlobalValues, or Mulligan ledgers.

- [ ] **Step 4: Run RED**

```powershell
python -m pytest tests/test_package_compiler.py tests/test_package_assembler.py tests/test_package_byte_parity.py -q -p no:cacheprovider
```

- [ ] **Step 5: Extract compile and assemble stages**

Move behavior without changing schema. `package_builder.py` becomes orchestration plus compatibility entrypoints and must not write files directly.

- [ ] **Step 6: Enforce size budgets**

Add an AST-based architecture assertion:

```text
package_builder.py <= 250 physical lines
prepare_package_payload <= 120 logical source lines
```

The test should report measured values and fail above the limit.

- [ ] **Step 7: Run GREEN and byte parity**

```powershell
python -m pytest tests/test_package_compiler.py tests/test_package_assembler.py tests/test_package_builder.py tests/test_package_builder_runtime_filter.py tests/test_package_derivation_receipt.py tests/test_package_byte_parity.py -q -p no:cacheprovider
1..10 | ForEach-Object { python -m pytest tests/test_package_byte_parity.py -q -p no:cacheprovider; if ($LASTEXITCODE -ne 0) { throw "package_byte_parity_repeat_failed" } }
```

- [ ] **Step 8: Commit**

```powershell
git add src/hsconfig/package_compiler.py src/hsconfig/package_assembler.py src/hsconfig/package_builder.py tests/fixtures/package-byte-contract-v1.json tests/test_package_compiler.py tests/test_package_assembler.py tests/test_package_byte_parity.py tests/test_package_builder.py tests/test_package_builder_runtime_filter.py tests/test_package_derivation_receipt.py
git commit -m "refactor: compile packages into immutable models"
git push origin main
```

---

### Task 9: Make Configure a Thin Workflow

**Files:**
- Create: `src/hsconfig/configure_models.py`
- Create: `src/hsconfig/configure_summary.py`
- Create: `src/hsconfig/configure_workflow.py`
- Modify: `src/hsconfig/commands/configure.py`
- Modify: `src/hsconfig/configure_stages.py`
- Create: `tests/test_configure_workflow.py`
- Modify: `tests/test_configure_cli.py`
- Modify: `tests/test_configure_stages.py`
- Modify: `tests/test_configure_handoff_contract.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ConfigureRequest:
    deck_name: str
    deck_code: str
    output_root: Path
    runtime_root: Path | None
    apply_requested: bool
    current_date: date
    source_urls: tuple[str, ...]
    online_source: bool
    auto_source: bool
    cards_json: Path | None
    collectible_cards_json: Path | None
    full_cards_json: Path | None
    source_fixture_url_map_json: Path | None
    source_fetch_timeout_seconds: float
    allow_placeholder: bool


@dataclass(frozen=True, slots=True)
class ConfigureResult:
    status: str
    exit_code: int
    package_model: PackageModel | None
    configure_run_model: ConfigureRunModel | None
    summary: Mapping[str, Any]


def execute_configure(
    request: ConfigureRequest,
    *,
    stage_observer: StageObserver | None = None,
) -> ConfigureResult: ...
```

- [ ] **Step 1: Write workflow boundary tests**

Test a successful in-memory build, each stage failure, deterministic stage ordering, no publication on failure, and stable summary generation. Add a parameterized CLI-to-request mapping test covering every current configure option and assert the original `argparse.Namespace` is byte-for-byte unchanged after execution.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_configure_workflow.py -q -p no:cacheprovider
```

- [ ] **Step 3: Extract request/result parsing and workflow**

The CLI parses arguments into `ConfigureRequest`, calls `execute_configure`, and formats `ConfigureResult`. Filesystem publication remains delegated to the Plan 03 publisher adapter.

- [ ] **Step 4: Enforce module budgets**

Add to the architecture test:

```text
commands/configure.py <= 200 physical lines
configure_workflow.execute_configure <= 160 logical source lines
operator_summary.py <= 350 physical lines
operator_summary.build_operator_summary <= 120 logical source lines
config_quality_contract.py <= 300 physical lines
config_quality_contract.build_config_quality_report <= 40 logical source lines
```

- [ ] **Step 5: Run GREEN and CLI regressions**

```powershell
python -m pytest tests/test_configure_workflow.py tests/test_configure_cli.py tests/test_configure_stages.py tests/test_configure_handoff_contract.py tests/test_configure_auto_source.py tests/test_configure_online_source.py tests/test_autonomous_guide_workflow_e2e.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/configure_models.py src/hsconfig/configure_summary.py src/hsconfig/configure_workflow.py src/hsconfig/commands/configure.py src/hsconfig/configure_stages.py tests/test_configure_workflow.py tests/test_configure_cli.py tests/test_configure_stages.py tests/test_configure_handoff_contract.py
git commit -m "refactor: make configure orchestration explicit"
git push origin main
```

---

### Task 10: Remove Report Aliases and Dead Architecture

**Files:**
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `src/hsconfig/output_ownership_manifest.py`
- Modify: `src/hsconfig/operator_summary.py`
- Modify: `src/hsconfig/config_quality_contract.py`
- Delete after zero-consumer proof: `src/hsconfig/compile_optional_surfaces.py`
- Delete after zero-consumer proof: `src/hsconfig/matrix_closure.py`
- Delete after zero-consumer proof: `src/hsconfig/matrix_visibility.py`
- Delete after zero-consumer proof: `src/hsconfig/source_depth_closure_index.py`
- Create: `tests/test_architecture_contract.py`
- Modify: `tests/test_subtractive_contract_polish.py`

**Canonical report replacements:**

| Remove alias | Canonical owner |
|---|---|
| `reports/global_values_key_profile_report.json` | `reports/globalvalues_profile.json` |
| `reports/global_values_blocked_changes.json` | `reports/global_values_authority_matrix.json` |
| `reports/card_behavior_suppression_report.json` | suppression rows in the canonical card plan report |
| `reports/combo_suppression_report.json` | suppression rows in the canonical Combo plan report |
| `reports/source_evidence_index.json` | canonical guide/source bundle report |

- [ ] **Step 1: Write the failing zero-alias and zero-consumer tests**

Scan production source, tests, documentation, report registry, and a freshly generated package. Permit old alias strings only in an explicit migration assertion that proves absence from output.

- [ ] **Step 2: Write architecture import rules**

`tests/test_architecture_contract.py` must enforce:

```text
commands -> workflow -> compiler/assembler -> model
quality/status -> PackageView
renderer/publisher -> PackageModel
no compiler or quality module imports commands
no registry literal duplication
no production assert
no direct package writes outside renderer/publisher
```

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_architecture_contract.py tests/test_subtractive_contract_polish.py -q -p no:cacheprovider
```

- [ ] **Step 4: Remove aliases, migrate remaining consumers, then delete dead modules**

Before each deletion run:

```powershell
rg -n "compile_optional_surfaces|matrix_closure|matrix_visibility|source_depth_closure_index" src tests scripts docs
```

Delete only when production references are zero and tests have been moved to canonical owners.

- [ ] **Step 5: Run the architecture phase gate**

```powershell
python -m pytest tests/test_architecture_contract.py tests/test_subtractive_contract_polish.py tests/test_package_byte_parity.py tests/test_operator_summary.py tests/test_config_quality_contract.py -q -p no:cacheprovider
python -m ruff check --no-cache src tests scripts
git diff --check
```

Expected: no alias output, no forbidden dependency edge, byte parity green, lint clean.

- [ ] **Step 6: Commit**

```powershell
git add -A src/hsconfig tests
git commit -m "refactor: remove duplicate package architecture"
git push origin main
```

---

## Package Architecture Acceptance Gate

- [ ] Generate all twelve audited package models twice and compare `(relative_path, sha256)` tuples.
- [ ] Confirm the registry defines one normal apply authority and all runtime/report classifications.
- [ ] Confirm `python -O` preserves every correctness gate.
- [ ] Confirm validators operate against an in-memory `PackageView`.
- [ ] Confirm the CLI, compiler, quality checks, renderer, and publisher dependency direction passes the AST architecture test.
- [ ] Confirm no removed alias or dead module appears in production code or a generated package.
- [ ] Run:

```powershell
python -m pytest tests/test_contract_registry.py tests/test_contract_registry_adoption.py tests/test_python_optimized_mode.py tests/test_package_model.py tests/test_package_renderer.py tests/test_package_byte_parity.py tests/test_config_quality_inputs.py tests/test_config_quality_checks.py tests/test_operator_status.py tests/test_architecture_contract.py -q -p no:cacheprovider
python -m pytest tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
python -m ruff check --no-cache src tests scripts
git diff --check
```

Expected: all selected tests pass, Ruff clean, no whitespace errors.
