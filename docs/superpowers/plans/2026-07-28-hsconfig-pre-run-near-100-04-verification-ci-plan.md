# HSConfig Verification and CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the pre-run contract into one reproducible local release gate and one minimal GitHub Actions workflow that prove semantics, determinism, transaction safety, packaging, security, repository hygiene, and version consistency.

**Architecture:** Add a single version source and reviewed Python 3.11/3.12 lock files, then build layered verification suites around pure contract components and transactional boundaries. A machine-readable release-gate script invokes the same narrow commands used by four GitHub Actions jobs: `contract`, `test`, `package`, and `security`.

**Tech Stack:** Python 3.11/3.12, pytest, pytest-cov, Hypothesis, mutmut, Ruff, pip-audit, `pip lock`, `build`, virtual environments, GitHub Actions, PowerShell.

## Global Constraints

- Local verification is the pre-push authority; GitHub Actions independently confirms the pushed OID.
- Do not upload Config packages, logs, replays, generated reports, coverage databases, or runtime evidence as CI artifacts.
- CI triggers are only push to `main`, `workflow_dispatch`, and an optional scheduled security scan.
- CI must not execute untrusted pull-request code.
- Every Action reference uses a full commit SHA and an adjacent version comment.
- Pin or lock all Python dependencies used by the release gate.
- Exclude generated data and declarative fixtures from meaningful coverage claims.
- Critical transactional and apply-authority modules require 100% reachable branch coverage.
- Whole-project branch coverage minimum is 90%; the tracked target is 95%.
- Gameplay quality remains `OUT_OF_SCOPE_ASSUMED_EXTERNAL`.

---

### Task 1: Create One Version Source and Reproducible Dependency Locks

**Files:**
- Create: `src/hsconfig/version.py`
- Modify: `src/hsconfig/__init__.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `pyproject.toml`
- Create: `pylock.toml`
- Create: `constraints-ci.txt`
- Create: `scripts/refresh_locks.ps1`
- Create: `tests/test_version_contract.py`
- Create: `tests/test_dependency_lock_contract.py`

**Interfaces:**

```python
__version__ = "1.0.0"


def version_payload() -> dict[str, str]:
    return {"version": __version__}
```

- [ ] **Step 1: Write failing version consistency tests**

Assert:

```text
hsconfig.version.__version__ == 1.0.0
importlib.metadata.version("hsconfig") == 1.0.0 when installed
hsconfig --version prints exactly hsconfig 1.0.0
pyproject dynamic version resolves from hsconfig.version.__version__
```

- [ ] **Step 2: Write failing lock-contract tests**

Parse `pylock.toml` and require Python-version markers covering 3.11 and 3.12, hashes for every downloadable archive, the project dependencies, and every release-tool dependency. Require every non-project entry in `constraints-ci.txt` to be exactly pinned. Reject editable/local absolute paths and direct unpinned URLs.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_version_contract.py tests/test_dependency_lock_contract.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement dynamic project version and CLI flag**

Use:

```toml
[project]
dynamic = ["version"]

[tool.setuptools.dynamic]
version = {attr = "hsconfig.version.__version__"}
```

Add the parser-level `--version` option without importing package-building code.

- [ ] **Step 5: Generate and review locks**

Use the installed pip lock implementation from controlled requirement inputs. `scripts/refresh_locks.ps1` creates `pylock.toml` and `constraints-ci.txt` in temporary Python 3.11 and 3.12 virtual environments, compares their resolved package/version sets, and fails if the common lock cannot satisfy both interpreters or introduces unhashed packages or absolute paths.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/refresh_locks.ps1
python -m pytest tests/test_dependency_lock_contract.py -q -p no:cacheprovider
```

- [ ] **Step 6: Verify locked fresh installs**

Create disposable Python 3.11 and 3.12 virtual environments, install from their matching lock, then run:

```powershell
hsconfig --version
python -m pytest tests/test_version_contract.py -q -p no:cacheprovider
```

- [ ] **Step 7: Commit**

```powershell
git add src/hsconfig/version.py src/hsconfig/__init__.py src/hsconfig/cli.py pyproject.toml pylock.toml constraints-ci.txt scripts/refresh_locks.ps1 tests/test_version_contract.py tests/test_dependency_lock_contract.py
git commit -m "build: lock dependencies and set version 1.0.0"
git push origin main
```

---

### Task 2: Define Coverage Ownership and Critical 100% Gates

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/check_coverage_contract.py`
- Create: `tests/test_coverage_contract.py`
- Modify tests for uncovered branches in:
  - `src/hsconfig/atomic_io.py`
  - `src/hsconfig/output_publisher.py`
  - `src/hsconfig/current_output.py`
  - `src/hsconfig/runtime_installer.py`
  - `src/hsconfig/runtime_state.py`
  - `src/hsconfig/deck_config_ini.py`
  - `src/hsconfig/apply_gate.py`
  - `src/hsconfig/apply_decision.py`
  - `src/hsconfig/operator_status.py`

**Coverage contract:**

```text
whole project: branch >= 90.00%
critical modules: reachable statements and branches == 100.00%
target reported separately: whole project branch >= 95.00%
```

- [ ] **Step 1: Write the failing coverage-policy parser test**

Require explicit `branch = true`, source restricted to `src/hsconfig`, omission of tests/fixtures/generated resources, a 90% global fail-under, and the exact critical-module list.

- [ ] **Step 2: Run the current suite with branch coverage and capture RED**

```powershell
python -m pytest --cov=src/hsconfig --cov-branch --cov-report=json:coverage.json --cov-report=term-missing -p no:cacheprovider
python scripts/check_coverage_contract.py coverage.json
```

Expected: the checker identifies precise missing critical lines/branches or global coverage below the contract.

- [ ] **Step 3: Add behavior-focused tests for every reachable gap**

Do not use `# pragma: no cover` for normal error paths. Exclude only platform-impossible branches with a written reason tied to a platform-specific companion test.

- [ ] **Step 4: Implement the coverage checker**

Output JSON:

```json
{
  "passed": true,
  "global_branch_percent": 95.0,
  "global_minimum": 90.0,
  "target_met": true,
  "critical_modules": []
}
```

Each critical-module row includes measured statement and branch percentages and any missing line numbers.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest --cov=src/hsconfig --cov-branch --cov-report=json:coverage.json --cov-report=term-missing -p no:cacheprovider
python scripts/check_coverage_contract.py coverage.json
```

Expected: global branch coverage at least 90%; every critical module 100%; target status reported honestly.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml scripts/check_coverage_contract.py tests src/hsconfig
git commit -m "test: enforce critical branch coverage"
git push origin main
```

---

### Task 3: Add Property and Contract Mutation Tests

**Files:**
- Create: `tests/property/test_package_model_properties.py`
- Create: `tests/property/test_path_and_manifest_properties.py`
- Create: `tests/property/test_publication_properties.py`
- Create: `tests/property/test_ini_properties.py`
- Create: `tests/mutation/test_apply_authority_mutations.py`
- Create: `tests/mutation/test_owner_policy_mutations.py`
- Create: `tests/mutation/test_runtime_surface_mutations.py`
- Create: `scripts/run_contract_mutations.py`
- Create: `tests/test_contract_mutation_runner.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write property tests**

Use deterministic Hypothesis profiles in CI. Prove:

- input mapping order cannot change package bytes or tree digest;
- absolute root location cannot change package bytes;
- path traversal and Unicode-confusable separators are rejected;
- manifest tampering is always detected;
- repeated publication is idempotent;
- unrelated INI bytes are preserved;
- concurrent compare-and-swap never overwrites a changed INI.

- [ ] **Step 2: Write three deliberate mutation operators**

The runner creates a disposable source copy and applies one mutation per run:

1. change the sole apply authority report;
2. allow a non-owner runtime row;
3. reclassify a forbidden runtime surface as optional.

Each mutation must name at least one expected killing test and fail if the selected tests exit 0.

- [ ] **Step 3: Run mutation RED against a disabled assertion**

Temporarily point the runner at a no-op mutation in its test fixture; assert the runner reports `survived` and exits non-zero. Remove the fixture mutation after the harness test is green.

- [ ] **Step 4: Implement isolated mutation execution**

Never mutate the working tree. Copy only tracked source/test files to a temporary root, apply the edit there, set `PYTHONPATH`, and run the exact killing tests.

- [ ] **Step 5: Run property and mutation GREEN**

```powershell
python -m pytest tests/property -q -p no:cacheprovider
python scripts/run_contract_mutations.py --json
```

Expected: all properties pass and all three intentional contract mutations are killed.

- [ ] **Step 6: Commit**

```powershell
git add tests/property tests/mutation scripts/run_contract_mutations.py tests/test_contract_mutation_runner.py pyproject.toml
git commit -m "test: prove contract invariants and mutation sensitivity"
git push origin main
```

---

### Task 4: Prove Twelve-Deck Cold-Build and Runtime Determinism

**Files:**
- Create: `src/hsconfig/release_verification.py`
- Create: `scripts/verify_twelve_decks.py`
- Create: `tests/test_release_verification.py`
- Create: `tests/test_twelve_deck_determinism.py`
- Modify: `tests/test_audited_deck_set_acceptance.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class DeckVerification:
    deck_name: str
    first_content_root_sha256: str
    second_content_root_sha256: str
    configure_run_bytes_equal: bool
    runtime_old_or_new_safe: bool


def verify_audited_decks(
    *,
    build_inputs: AuditedBuildInputSet,
    work_root_a: Path,
    work_root_b: Path,
) -> tuple[DeckVerification, ...]: ...
```

- [ ] **Step 1: Write the failing absolute-path independence test**

Build the same deck in two different temporary absolute roots and compare every package path and byte. Assert no serialized text contains either root.

- [ ] **Step 2: Extend to all twelve catalog rows**

For each deck:

1. cold-build twice;
2. compare full trees and manifests;
3. verify semantic inventory/disposition/GlobalValues closure;
4. simulate runtime install into two fresh temporary roots;
5. inject one pre-commit and one post-commit termination;
6. assert recovery is old-or-new safe.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_release_verification.py tests/test_twelve_deck_determinism.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement a bounded verifier**

Use the canonical build-input set order and return deterministic rows. The CLI script loads the audited build-input manifest, pinned card snapshot, policy IDs, and frozen source bundle hashes; it supports `--json`, exits non-zero on any failed row, performs no network or wall-clock lookup, and never writes to real `outputs/` or HearthRanger runtime paths.

- [ ] **Step 5: Run GREEN**

```powershell
python scripts/verify_twelve_decks.py --build-inputs src/hsconfig/resources/audited_build_inputs.json --json
python -m pytest tests/test_release_verification.py tests/test_twelve_deck_determinism.py tests/test_audited_deck_set_acceptance.py -q -p no:cacheprovider
```

Expected: twelve rows; equal digests and runtime safety true for every row.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/release_verification.py scripts/verify_twelve_decks.py tests/test_release_verification.py tests/test_twelve_deck_determinism.py tests/test_audited_deck_set_acceptance.py
git commit -m "test: verify deterministic twelve-deck builds"
git push origin main
```

---

### Task 5: Verify Build Artifacts and Fresh Wheel Installation

**Files:**
- Create: `scripts/verify_distribution.py`
- Create: `tests/test_distribution_contract.py`
- Modify: `pyproject.toml`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class DistributionVerification:
    wheel: Path
    sdist: Path
    version: str
    wheel_smoke_passed: bool
    source_tree_clean: bool
```

- [ ] **Step 1: Write failing distribution-content tests**

Require wheel/sdist to include only runtime package resources and standard metadata. Reject tests, outputs, local caches, `.superpowers`, runtime evidence, absolute paths, and secret-like filenames.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_distribution_contract.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement isolated build verification**

The script:

1. records `git status --porcelain`;
2. builds sdist and wheel in a temporary output root using locked build tools;
3. inspects archive member lists;
4. creates a fresh venv;
5. installs only the wheel plus locked dependencies;
6. runs `hsconfig --version`, `hsconfig --help`, and `contract-spine-sentinel --json`;
7. verifies the source worktree status is unchanged.

- [ ] **Step 4: Run GREEN**

```powershell
python scripts/verify_distribution.py --json
python -m pytest tests/test_distribution_contract.py -q -p no:cacheprovider
```

- [ ] **Step 5: Commit**

```powershell
git add scripts/verify_distribution.py tests/test_distribution_contract.py pyproject.toml
git commit -m "build: verify wheel and source distribution"
git push origin main
```

---

### Task 6: Compute the Machine-Readable Near-100 Scorecard

**Files:**
- Create: `src/hsconfig/near100_scorecard.py`
- Create: `scripts/check_near100_scorecard.py`
- Create: `tests/test_near100_scorecard.py`
- Read: `tests/fixtures/near100/score_metric_contract.json`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ScoreMetric:
    metric_id: str
    numerator: int
    denominator: int
    score: Decimal | None
    minimum: Decimal | None
    status: Literal["pass", "fail", "pending_remote", "not_applicable"]
    evidence_paths: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    non_blocking_reasons: tuple[str, ...]
    scope: str


@dataclass(frozen=True, slots=True)
class Near100Scorecard:
    schema_version: int
    version: str
    metrics: tuple[ScoreMetric, ...]
    open_p0_findings: int
    open_p1_findings: int
    overall_score: Decimal
    passed: bool


def build_near100_scorecard(
    *,
    evidence: Mapping[str, Mapping[str, Any]],
    mode: Literal["pre_cutover", "final"],
) -> Near100Scorecard:
    ...
```

**Required metric contract:**

| Metric ID | Minimum |
|---|---:|
| `static_contract_safety` | 99 |
| `safe_visionai_lowering` | 99 |
| `testability_and_assurance` | 98 |
| `semantic_disposition_closure` | 100 |
| `layered_pre_run_source_coverage` | 98 |
| `architecture_and_maintainability` | 96 |
| `slimness_and_coherence` | 98 |
| `github_repository_polish` | 98 |
| `workspace_hygiene` | 100 |
| `overall_pre_run` | 98 |
| `gameplay_quality` | `not_applicable` |

- [ ] **Step 1: Write failing score truth-table tests**

Require exact metric IDs, explicit numerator/denominator, Decimal computation without floating-point rounding, minimum comparison, evidence paths, blocking/non-blocking reasons, and scope. `gameplay_quality` must be `not_applicable`, `score=None`, and scope `OUT_OF_SCOPE_ASSUMED_EXTERNAL`.

- [ ] **Step 2: Write anti-gaming tests**

Reject missing metrics, zero denominators except gameplay, scores above 100, evidence paths that do not exist, a passing overall score with any failed hard metric, and a passing scorecard with any open P0/P1 finding.

The frozen score contract lists every atomic check ID and its metric owner. Checks have equal weight inside a metric. A metric numerator is passed atomic checks and its denominator is the fixed count of owned check IDs. `layered_pre_run_source_coverage` alone uses semantic obligations: denominator is all 208 card/module rows plus all 316 claim rows; numerator is rows with one final A-E evidence authority and final disposition. Overall is `100 * sum(metric numerator) / sum(metric denominator)` across the nine non-gameplay metrics, using exact Decimal arithmetic. No metric may consume its own status.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_near100_scorecard.py -q -p no:cacheprovider
```

- [ ] **Step 4: Implement evidence-backed scoring**

Metric inputs come only from completed base checks, coverage JSON, semantic closure reports, architecture tests, repository policy tests, and output inventory. The release gate executes all base checks first, then computes the scorecard as the final meta-check; `near100_scorecard` is never an input to itself. No metric is a subjective constant. Store the scorecard as the release gate's machine-readable result, not inside generated Config packages.

In `pre_cutover` mode, `github_repository_polish` is `pending_remote` and excluded from the provisional overall; the scorecard cannot claim final `passed=true`. Plan 05 reruns `final` after settings, ruleset, tag, release, and final-tree verification; only that result may satisfy the overall release contract.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest tests/test_near100_scorecard.py -q -p no:cacheprovider
python scripts/check_near100_scorecard.py --repo . --outputs outputs --mode pre_cutover --json
```

Expected: every local hard metric passes, GitHub polish is `pending_remote`, gameplay is `not_applicable`, open P0/P1 are zero, and the provisional overall is at least 98.

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/near100_scorecard.py scripts/check_near100_scorecard.py tests/test_near100_scorecard.py
git commit -m "test: score the complete pre-run release contract"
git push origin main
```

---

### Task 7: Create the Canonical Local Release Gate

**Files:**
- Create: `src/hsconfig/release_gate.py`
- Create: `scripts/check_release_gate.py`
- Create: `tests/test_release_gate.py`
- Create: `tests/fixtures/release_gate/clean_repository.json`
- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `AGENTS.md`
- Modify: tracked tests with literal local paths, including `tests/test_io_and_models.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ReleaseCheck:
    name: str
    passed: bool
    command: tuple[str, ...]
    details: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ReleaseGateResult:
    passed: bool
    final_release_ready: bool
    version: str
    commit_oid: str
    checks: tuple[ReleaseCheck, ...]


def run_release_gate(
    *,
    repository: Path,
    outputs_root: Path,
    tree_mode: Literal["working-pre-cutover", "candidate", "final"] = "final",
) -> ReleaseGateResult: ...
```

- [ ] **Step 1: Write failing gate-composition tests**

Require these named checks exactly:

```text
ruff
full_tests_and_coverage
contract_spine
twelve_deck_acceptance
contract_mutations
dependency_audit
distribution
twelve_deck_determinism
publishable_path_scan
output_inventory
package_immutability
transaction_fault_matrix
repository_hygiene
version_consistency
near100_scorecard
```

Test fail-closed aggregation, stable JSON, command exit propagation, and refusal to pass a dirty worktree. `working-pre-cutover` permits only the explicitly enumerated historical documentation paths while requiring all behavioral gates; `candidate` validates a detached candidate tree and an explicitly supplied verified outputs root; `final` permits no historical exception and is the default.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_release_gate.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement direct executable orchestration**

Use `subprocess.run` argument arrays with timeouts; never shell-concatenate user-controlled paths. Stream concise progress to stderr and emit exactly one JSON document to stdout under `--json`.

- [ ] **Step 4: Add publishable scans**

Scan tracked files, wheel, sdist, and all twelve current packages for:

- absolute Windows/user paths;
- private runtime evidence names;
- secrets and high-entropy credential patterns;
- backups, staging, caches, obsolete output generations;
- placeholders such as `TBD`, `TODO`, `FIXME`, and `PLACEHOLDER` in public policy/docs.

Permit source-code TODO-like matches only through a reviewed explicit allowlist with file, line, reason, and expiry version.

Before committing, remove every literal local/profile/workspace path from active tracked files. Use repository-relative language in `AGENTS.md`; tests construct synthetic paths from components or `tmp_path`. `working-pre-cutover` excludes only the exact historical plan/research/history directories from publishability scoring, never active code/tests/docs.

- [ ] **Step 5: Run focused GREEN tests**

```powershell
python -m pytest tests/test_release_gate.py tests/test_near100_scorecard.py -q -p no:cacheprovider
```

- [ ] **Step 6: Commit**

```powershell
git add src/hsconfig/release_gate.py scripts/check_release_gate.py tests/test_release_gate.py tests/fixtures/release_gate/clean_repository.json README.md docs/operator/README.md AGENTS.md tests/test_io_and_models.py
git commit -m "feat: add canonical local release gate"
git push origin main
```

- [ ] **Step 7: Run the canonical gate from the clean committed OID**

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
```

Expected: `passed=true`, `final_release_ready=false`, version `1.0.0`, every local/base check true, the provisional score at least 98, and remote GitHub polish pending until Plan 05.

---

### Task 8: Consolidate GitHub Actions Into Four Reproducible Jobs

**Files:**
- Create: `.github/workflows/ci.yml`
- Delete: `.github/workflows/contract-guardrails.yml`
- Delete: `.github/workflows/contract-spine.yml`
- Delete: `.github/workflows/full-test-suite.yml`
- Create: `tests/test_ci_workflow_contract.py`
- Modify: `tests/test_ci_contract.py`

**Required Action pins at implementation start:**

```yaml
actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
```

Re-verify these tags against the official Action repositories immediately before commit; if upstream tags changed, record the verified full SHA and matching version comment in the implementation review.

- [ ] **Step 1: Write the failing workflow contract test**

Parse YAML with the workflow loader preserving the `on` key. Require:

- triggers: `push.branches == ["main"]`, `workflow_dispatch`, optional `schedule`;
- no `pull_request`;
- top-level `permissions: contents: read`;
- top-level concurrency with cancellation;
- exactly `contract`, `test`, `package`, `security`;
- timeout on every job;
- Python 3.11 and 3.12 coverage;
- full SHA Action references;
- no artifact upload Action;
- locked installs;
- canonical local script reuse.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_ci_workflow_contract.py tests/test_ci_contract.py -q -p no:cacheprovider
```

Expected: three legacy workflows and disallowed triggers fail the contract.

- [ ] **Step 3: Implement the single workflow**

Job responsibilities:

| Job | Required execution |
|---|---|
| `contract` | locked install, Ruff, guardrails, optimized sentinel, twelve-deck contract acceptance |
| `test` | Python 3.11/3.12 matrix, full tests, branch coverage, critical coverage check, property tests |
| `package` | locked build, wheel/sdist verification, fresh wheel install, version smoke, deterministic builds |
| `security` | pip-audit from lock, secret/path/artifact scans, contract mutation runner |

Use `PYTHONDONTWRITEBYTECODE=1` and no persistent caches/artifacts.

- [ ] **Step 4: Delete legacy workflows and run GREEN**

```powershell
python -m pytest tests/test_ci_workflow_contract.py tests/test_ci_contract.py -q -p no:cacheprovider
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
```

- [ ] **Step 5: Commit and push**

```powershell
git add .github/workflows/ci.yml tests/test_ci_workflow_contract.py tests/test_ci_contract.py
git rm .github/workflows/contract-guardrails.yml .github/workflows/contract-spine.yml .github/workflows/full-test-suite.yml
git commit -m "ci: consolidate reproducible release verification"
git push origin main
```

- [ ] **Step 6: Verify pushed CI by exact OID**

```powershell
$oid = git rev-parse HEAD
gh run list --repo Teufelsboy/HSConfig --commit $oid --json databaseId,status,conclusion,workflowName
gh run watch --repo Teufelsboy/HSConfig (gh run list --repo Teufelsboy/HSConfig --commit $oid --json databaseId --jq '.[0].databaseId') --exit-status
```

Expected: the single `ci` workflow is terminal success and all four jobs are green.

---

## Verification and CI Acceptance Gate

- [ ] `hsconfig --version` returns `hsconfig 1.0.0` from source and fresh wheel.
- [ ] Python 3.11 and 3.12 installs resolve only reviewed locked dependencies.
- [ ] Global branch coverage is at least 90%; critical modules are 100%.
- [ ] All three contract mutations are killed.
- [ ] All twelve decks cold-build byte-identically under different roots.
- [ ] All twelve temporary runtime simulations are old-or-new safe.
- [ ] Wheel and sdist contain no private, generated, absolute-path, or secret material.
- [ ] The canonical local release gate returns `passed=true`.
- [ ] Exactly one workflow exists and its four jobs are green for the exact OID.
- [ ] Run:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --tree-mode working-pre-cutover --json
python -m ruff check --no-cache src tests scripts
python -m pytest -p no:cacheprovider
python -O -m hsconfig.cli contract-spine-sentinel --json
python -m pip_audit .
git diff --check
```

Expected: every command exits 0; release gate and sentinel are clean.
