# HSConfig Transactional Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish exactly one current package per deck and activate runtime configuration without partial visibility, persistent Config backups, immutable-package mutation, or loss of the previously valid state under injected interruption.

**Architecture:** Use content-addressed immutable revision directories plus one atomically replaced `current.json` pointer for outputs. Runtime activation installs a content-addressed immutable runtime directory first, verifies it, then atomically replaces the single DeckConfig INI mapping as the commit point. Locks serialize writers; state and receipts live outside immutable packages; startup reconciliation removes only proven orphan staging and incomplete unreferenced revisions.

**Tech Stack:** Python 3.11/3.12, `os.replace`, file and directory fsync where supported, SHA-256 full-tree manifests, Windows `msvcrt` and POSIX `fcntl` advisory locks, compare-and-swap digests, pytest fault injection, PowerShell process-interruption tests.

## Global Constraints

- The publisher accepts only a validated `RenderedConfigureRun` derived from its typed `ConfigureRunModel`/`PackageModel`.
- The runtime installer accepts only the manifest-verified package resolved from `current.json`.
- Keep exactly one current output generation per audited deck after successful reconciliation.
- A failed publication must leave the previous current output resolvable and byte-valid.
- Before the INI commit point, failure leaves the previous config active and byte-valid. After the commit point, the new verified config remains active and recovery completes state/receipt; post-commit failure never rolls back to old.
- Do not delete the active target before the replacement is durable.
- Do not mutate a package by writing fake-apply, apply, or failure receipts inside it.
- Do not create persistent runtime Config backups.
- Treat `KeyboardInterrupt`, `SystemExit`, and injected `BaseException` as recovery-relevant after mutation begins.
- "Unknown" means a path that cannot be proven publisher-owned at cleanup
  time from a valid ownership record, containment, and unchanged identity.
  Never remove such a path.
- The portable race guarantee covers cooperative publishers serialized by the
  shared lock plus crash/fault recovery. Hostile same-user mutation by a
  non-cooperating process is outside the contract; Windows adds handle-bound
  final-entry hardening, while POSIX `dir_fd` binds containment and parent
  identity but cannot portably make every validated name mutation hostile-CAS.
- `operator_summary.json` remains the sole normal apply authority.

---

### Task 1: Add Durable Atomic I/O and Exclusive Locks

**Files:**
- Create: `src/hsconfig/atomic_io.py`
- Create: `tests/test_atomic_io.py`
- Create: `tests/test_atomic_io_process_lock.py`

**Interfaces:**

```python
FaultHook = Callable[[str], None]


def no_fault(stage: str) -> None: ...


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    fault_hook: FaultHook = no_fault,
) -> None: ...


def atomic_write_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    fault_hook: FaultHook = no_fault,
) -> None: ...


def flush_file(path: Path) -> None: ...


class ExclusiveFileLock:
    def __init__(self, path: Path, *, timeout_seconds: float = 30.0) -> None: ...
    def __enter__(self) -> ExclusiveFileLock: ...
    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...
```

- [x] **Step 1: Write failing atomic-replace tests**

Parameterize injected failure at:

```text
before_temp_write
after_temp_write
after_temp_flush
before_replace
after_replace
after_parent_flush
```

Before the commit point, the old bytes must remain. After the commit point, either old or complete new bytes are acceptable, never truncation or mixed JSON.

- [x] **Step 2: Write cross-process lock tests**

Start one child process holding a lock and assert a second process times out with `LockTimeoutError`. After the holder exits, assert the next acquisition succeeds. Do not rely only on threads.

- [x] **Step 3: Run RED**

```powershell
python -m pytest tests/test_atomic_io.py tests/test_atomic_io_process_lock.py -q -p no:cacheprovider
```

Expected: missing `hsconfig.atomic_io`.

- [x] **Step 4: Implement durable same-directory replacement**

Write a uniquely named sibling temp file with exclusive creation, flush content, call `os.fsync`, `os.replace`, then best-effort flush the parent directory. On Windows, explicitly document and test the directory-flush limitation; file replacement correctness remains mandatory.

- [x] **Step 5: Implement platform lock adapters**

Use `msvcrt.locking` on Windows and `fcntl.flock` on POSIX behind the same class. The lock file may persist as an empty coordination inode; it is not a backup or package artifact.

- [x] **Step 6: Run GREEN**

```powershell
python -m pytest tests/test_atomic_io.py tests/test_atomic_io_process_lock.py -q -p no:cacheprovider
```

- [x] **Step 7: Commit**

```powershell
git add src/hsconfig/atomic_io.py tests/test_atomic_io.py tests/test_atomic_io_process_lock.py
git commit -m "feat: add durable atomic I/O primitives"
git push origin main
```

---

### Task 2: Define and Verify Full Configure-Run Manifests

**Files:**
- Create: `src/hsconfig/run_manifest.py`
- Create: `src/hsconfig/strict_run_validation.py`
- Create: `tests/test_run_manifest.py`
- Modify: `src/hsconfig/configure_run_model.py`
- Modify: `tests/test_configure_run_model.py`
- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `tests/test_strict_package_validation.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ManifestEntry:
    relative_path: str
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class TreeManifest:
    schema_version: int
    deck_name: str
    deck_fingerprint: str
    entries: tuple[ManifestEntry, ...]
    content_root_sha256: str


def build_tree_manifest(rendered: RenderedConfigureRun) -> TreeManifest: ...
def write_tree_manifest(manifest: TreeManifest) -> bytes: ...
def verify_tree_manifest(revision: PackageView) -> TreeManifest: ...
```

- [x] **Step 1: Write failing manifest tests**

Cover stable order, path/size/content binding, extra-file rejection, missing-file rejection, single-byte tamper rejection, manifest self-exclusion from its entry list, and deterministic `content_root_sha256`.

- [x] **Step 2: Run RED**

```powershell
python -m pytest tests/test_run_manifest.py -q -p no:cacheprovider
```

- [x] **Step 3: Implement schema version 1**

Store the canonical manifest at revision root `package_manifest.json`. Its entries cover every other publishable configure-run artifact, including all stages and `04_package`. Compute the content root from `path + NUL + decimal_size + NUL + sha256 + LF`, exactly matching `ConfigureRunModel`; the manifest is excluded from its own entries.

- [x] **Step 4: Integrate manifest assembly and strict validation**

The configure-run renderer adds exactly one root manifest. Strict run validation verifies it before package semantic checks and emits `run_manifest_invalid` on any mismatch; package validation then evaluates the verified `04_package` view.

- [x] **Step 5: Run GREEN and tamper regressions**

```powershell
python -m pytest tests/test_run_manifest.py tests/test_configure_run_model.py tests/test_strict_package_validation.py tests/test_validate_package.py -q -p no:cacheprovider
```

- [x] **Step 6: Commit**

```powershell
git add src/hsconfig/run_manifest.py src/hsconfig/strict_run_validation.py src/hsconfig/configure_run_model.py src/hsconfig/strict_package_validation.py tests/test_run_manifest.py tests/test_configure_run_model.py tests/test_strict_package_validation.py
git commit -m "feat: bind packages with full-tree manifests"
git push origin main
```

---

### Task 3: Publish Content-Addressed Outputs Atomically

**Files:**
- Create: `src/hsconfig/output_publisher.py`
- Create: `src/hsconfig/current_output.py`
- Create: `tests/test_output_publisher.py`
- Create: `tests/test_current_output.py`
- Create: `tests/test_output_publication_fault_matrix.py`
- Modify: `src/hsconfig/atomic_io.py`
- Modify: `src/hsconfig/package_io.py`
- Modify: `tests/test_atomic_io.py`
- Modify: `tests/test_atomic_io_process_lock.py`

**Stable output layout:**

```text
outputs/
  ShadowPriest/
    .publish.lock
    .publisher/
      transactions/
    current.json
    revisions/
      sha256-<content_root_sha256>/
        package_manifest.json
        01_manifest/
        02_source_documents/ or 02_source_acquisition/
        02_source_autopilot/ or 03_source_autopilot/
        03_research/
        04_package/
          CustomConfig/
          reports/
        configure_summary.json
```

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class PublishedOutput:
    output_root: Path
    revision_root: Path
    package_root: Path
    content_root_sha256: str
    reused_existing_revision: bool


@dataclass(frozen=True, slots=True)
class OutputPublication:
    schema_version: int
    deck_name: str
    deck_fingerprint: str
    revision: str
    content_root_sha256: str


def publish_configure_run(
    rendered: RenderedConfigureRun,
    output_root: Path,
    *,
    fault_hook: FaultHook = no_fault,
) -> PublishedOutput: ...


def resolve_current_package(output_root: Path) -> Path: ...
def reconcile_output(output_root: Path) -> PublishedOutput | None: ...
```

- [x] **Step 1: Write failing happy-path and idempotency tests**

Assert first publish creates one revision and a valid pointer; publishing identical bytes reuses it; publishing changed bytes commits a new current revision and removes the old unreferenced revision only after pointer verification.

- [x] **Step 2: Write the output fault matrix**

Inject at:

```text
after_lock
after_staging_render
after_staging_verify
after_revision_rename
before_pointer_replace
after_pointer_replace
before_old_revision_cleanup
during_old_revision_cleanup
```

For every checkpoint, run both an injected exception and a subprocess hard termination. After a new process runs `reconcile_output`, exactly one complete current package must resolve. If the pointer was not committed, the old package remains current.

- [x] **Step 3: Run RED**

```powershell
python -m pytest tests/test_output_publisher.py tests/test_current_output.py tests/test_output_publication_fault_matrix.py -q -p no:cacheprovider
```

- [x] **Step 4: Implement staged publication**

Within the deck output lock:

1. reconcile existing state;
2. atomically write a publisher transaction/ownership record under `.publisher/transactions/`;
3. exclusively create the recorded `revisions/.staging-<uuid>` and render the complete configure run;
4. verify manifest and content root;
5. atomically rename staging to `revisions/sha256-<content_root_sha256>`;
6. atomically replace `current.json`;
7. resolve and reverify current;
8. remove only non-current publisher-owned revision directories.

The external ownership record contains schema, transaction ID, deck fingerprint, staging path, revision path, full content root, recorded identities, and phase. There is an unavoidable window after exclusive staging-directory creation and before its identity is durably recorded. A crash in that window leaves the path unknown: reconciliation retains it, fails closed, and keeps the old current pointer resolvable. Unknown, missing-record, damaged-record, identity-unrecorded, identity-changed, or reparse-point staging/revision paths are reported and left untouched; ownership metadata is not an extra file inside the manifested revision.

The portable publication guarantee covers HSConfig-cooperating publishers
serialized by the shared lock plus crash/fault recovery. Windows additionally
binds final child create, rename, unlink, and rmdir mutations to open handles
and denies delete sharing for the live lock inode. On POSIX, `dir_fd`
operations bind containment and parent-directory identity, but hostile
same-user substitution of a final directory entry between validation and the
name-based mutation is outside the contract. Platform-specific tests must not
claim a stronger cross-platform guarantee.

- [x] **Step 5: Implement strict resolver and reconciliation**

Reject pointer traversal, deck mismatch, digest mismatch, multiple current claims, and a missing manifest. Reconciliation may delete `.staging-*` and unreferenced revisions only after valid recorded ownership identity, containment, unchanged-identity, and current-pointer verification.

`resolve_current_package` holds the same publish lock while it snapshots and
verifies the selected revision. Its returned `Path` is intentionally a
point-in-time result: Task 4 callers that need a longer lifetime must consume
the verified snapshot within their operation rather than assume the path
cannot be retired after the resolver releases the lock.

- [x] **Step 6: Run GREEN**

```powershell
python -m pytest tests/test_output_publisher.py tests/test_current_output.py tests/test_output_publication_fault_matrix.py tests/test_output_inventory.py -q -p no:cacheprovider
```

- [x] **Step 7: Commit**

```powershell
git add src/hsconfig/output_publisher.py src/hsconfig/current_output.py src/hsconfig/atomic_io.py src/hsconfig/package_io.py tests/test_output_publisher.py tests/test_current_output.py tests/test_output_publication_fault_matrix.py tests/test_atomic_io.py tests/test_atomic_io_process_lock.py
git commit -m "feat: publish one atomic current output"
git push origin main
```

---

### Task 4: Route Configure Through the Publisher

**Files:**
- Modify: `docs/superpowers/plans/2026-07-28-hsconfig-pre-run-near-100-03-transactional-publication-plan.md`
- Modify: `src/hsconfig/configure_models.py`
- Modify: `src/hsconfig/configure_workflow.py`
- Modify: `src/hsconfig/current_output.py`
- Modify: `src/hsconfig/commands/apply.py`
- Modify: `src/hsconfig/commands/runtime_match.py`
- Modify: `src/hsconfig/package_io.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `scripts/report_output_inventory.py`
- Create: `tests/test_configure_publication.py`
- Modify: `tests/test_configure_cli.py`
- Modify: `tests/test_configure_workflow.py`
- Modify: `tests/test_configure_auto_source.py`
- Modify: `tests/test_configure_online_source.py`
- Modify: `tests/test_apply_authority_boundary.py`
- Modify: `tests/test_audited_deck_set_acceptance.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_real_deck_usage_loop.py`
- Modify: `tests/test_shadowpriest_partial_source_acceptance.py`
- Modify: `tests/test_shadowpriest_semantic_safety_wave.py`
- Modify: `tests/test_shadowpriest_source_contract_acceptance.py`
- Modify: `tests/test_source_acquisition_strong_closure.py`
- Modify: `tests/test_source_closure_optimizer_matrix.py`
- Modify: `tests/test_universal_wild_no_block_matrix.py`
- Test: `tests/test_configure_run_model.py`
- Test: `tests/test_configure_stages.py`
- Test: `tests/test_autonomous_guide_workflow_e2e.py`
- Modify: `tests/test_current_output.py`
- Modify: `tests/test_output_inventory.py`
- Modify: `tests/test_output_publisher.py`
- Modify: `tests/test_package_publication.py`
- Modify: `tests/test_runtime_apply.py`
- Modify: `tests/test_runtime_match_cli.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class ConfigureResult:
    status: str
    exit_code: int
    package_model: PackageModel | None
    configure_run_model: ConfigureRunModel | None
    summary: Mapping[str, Any]
    published_output: PublishedOutput | None = None
```

- [x] **Step 1: Write failing CLI publication tests**

Assert successful configure returns the resolved current package path, failed configure leaves prior current unchanged, and apply/runtime-match accept the deck output root by resolving `current.json`.

- [x] **Step 2: Run RED**

```powershell
python -m pytest tests/test_configure_publication.py tests/test_configure_cli.py tests/test_runtime_match_cli.py -q -p no:cacheprovider
```

- [x] **Step 3: Replace direct stage-directory publication**

Temporary semantic stages may live under a process-owned temporary root while being built. The renderer derives one `RenderedConfigureRun` from the typed configure/package models and all applicable stage artifacts; only that fully validated render crosses into `publish_configure_run`. Failed pre-publication stages remove only their owned temporary roots.

- [x] **Step 4: Preserve machine-readable summaries**

Add:

```json
{
  "output_root": "outputs/ShadowPriest",
  "published_revision": "revisions/sha256-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "published_package": "revisions/sha256-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef/04_package",
  "publication_content_root_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "reused_existing_revision": false
}
```

These five fields exist only in the transient CLI/result payload after publication; they are never persisted in the manifest-covered `configure_summary.json`. The persisted summary contains only canonical build-input, stage-status, and semantic-result data known before rendering, with no content-root, revision, reuse, absolute, or staging field.

Output publication and optional runtime activation are separate transactions.
A build or publication failure before the `current.json` commit point leaves
the previous current output selected. Once a validated revision is published,
that output commit is not rolled back merely because the later optional runtime
apply fails. Runtime activation retains its own boundary: failure before the
DeckConfig INI commit leaves the prior runtime config selected; after the INI
commit the new verified runtime config remains selected while recovery repairs
advisory state and receipts. `test_configure_apply_failure_keeps_new_publication_current`
locks this controller contract.

- [x] **Step 5: Run GREEN and E2E**

```powershell
python -m pytest tests/test_configure_publication.py tests/test_configure_cli.py tests/test_configure_workflow.py tests/test_configure_auto_source.py tests/test_configure_online_source.py tests/test_configure_run_model.py tests/test_configure_stages.py tests/test_current_output.py tests/test_output_inventory.py tests/test_output_publisher.py tests/test_runtime_apply.py tests/test_runtime_match_cli.py tests/test_autonomous_guide_workflow_e2e.py -q -p no:cacheprovider
```

- [x] **Step 6: Commit (controller-only)**

```powershell
git add docs/superpowers/plans/2026-07-28-hsconfig-pre-run-near-100-03-transactional-publication-plan.md src/hsconfig/configure_models.py src/hsconfig/configure_workflow.py src/hsconfig/current_output.py src/hsconfig/commands/apply.py src/hsconfig/commands/runtime_match.py src/hsconfig/package_io.py src/hsconfig/runtime_apply.py scripts/report_output_inventory.py tests/test_apply_authority_boundary.py tests/test_audited_deck_set_acceptance.py tests/test_cli.py tests/test_configure_publication.py tests/test_configure_cli.py tests/test_configure_workflow.py tests/test_configure_auto_source.py tests/test_configure_online_source.py tests/test_current_output.py tests/test_output_inventory.py tests/test_output_publisher.py tests/test_package_publication.py tests/test_real_deck_usage_loop.py tests/test_runtime_apply.py tests/test_runtime_match_cli.py tests/test_shadowpriest_partial_source_acceptance.py tests/test_shadowpriest_semantic_safety_wave.py tests/test_shadowpriest_source_contract_acceptance.py tests/test_source_acquisition_strong_closure.py tests/test_source_closure_optimizer_matrix.py tests/test_universal_wild_no_block_matrix.py
git commit -m "refactor: route configure through current output"
git push origin main
```

---

### Task 5: Model Runtime State and DeckConfig INI Compare-and-Swap

**Files:**
- Create: `src/hsconfig/runtime_state.py`
- Create: `src/hsconfig/deck_config_ini.py`
- Create: `tests/test_runtime_state.py`
- Create: `tests/test_deck_config_ini.py`
- Read: `src/hsconfig/runtime_apply.py`
- Read: `src/hsconfig/runtime_package_match.py`

**Runtime-owned layout:**

```text
<runtime-root>/
  CustomConfig/
    <logical-name>--sha256-<full-64-hex-digest>/
  .hsconfig/
    apply.lock
    state.json
    receipts/
    transactions/
```

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class DeckConfigSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    sha256: str | None
    selected_config_dir: str | None


@dataclass(frozen=True, slots=True)
class RuntimeDeckState:
    state_key: str
    deck_name: str
    config_dir: str
    package_root_sha256: str
    ini_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeState:
    schema_version: int
    decks: tuple[RuntimeDeckState, ...]


def read_deck_config(path: Path, *, deck_name: str) -> DeckConfigSnapshot: ...
def render_deck_config(snapshot: DeckConfigSnapshot, *, deck_name: str, config_dir: str) -> bytes: ...
def replace_deck_config_if_unchanged(
    snapshot: DeckConfigSnapshot,
    content: bytes,
    *,
    fault_hook: FaultHook = no_fault,
) -> str: ...
def read_runtime_state(runtime_root: Path) -> RuntimeState | None: ...
```

- [x] **Step 1: Write failing INI preservation tests**

Use realistic comments, unrelated sections, whitespace, newline styles, and Unicode. Assert only the named deck mapping changes and the original encoding/newline convention remains stable.

- [x] **Step 2: Write compare-and-swap tests**

Modify the INI after snapshot and assert replacement fails with `deck_config_ini_concurrent_change` without overwriting the concurrent edit.

- [x] **Step 3: Run RED**

```powershell
python -m pytest tests/test_runtime_state.py tests/test_deck_config_ini.py -q -p no:cacheprovider
```

- [x] **Step 4: Implement snapshot/render/CAS**

The INI parser must preserve untouched bytes. Atomic replacement uses Task 1. Runtime state is advisory recovery metadata and may never override the actual verified INI selection. A first install is represented as `existed=False`, `content=None`, and `sha256=None`.

The compare-and-swap guarantee covers HSConfig-cooperating writers serialized by `.hsconfig/apply.lock`; portable filesystems cannot provide a content-CAS against arbitrary non-cooperating editors. Tests and docs state this boundary explicitly. Immediately before replacement, recheck the snapshot; immediately after replacement, re-read and verify. For a missing INI, publish complete bytes with atomic create-if-absent (`os.link`/platform equivalent from a fully flushed temp file), never a visible empty placeholder. An external non-cooperating writer is detected where observable but is outside the claimed serialization guarantee.

On POSIX, use `renameat2(RENAME_NOREPLACE)` when available. The portable
fallback creates a directory-descriptor-bound hard link from the fully flushed,
identity-verified owned temp and then unlinks only that proven source name.
Target creation is the no-overwrite commit point. A hard kill in the very small
link-to-unlink window can leave the complete target and its owned temp as two
links to the same inode; it cannot expose partial target bytes or overwrite a
concurrent target, and subsequent validation must fail closed on unexpected
link count until the owned residue is reconciled.

- [x] **Step 5: Run GREEN**

```powershell
python -m pytest tests/test_runtime_state.py tests/test_deck_config_ini.py -q -p no:cacheprovider
```

- [x] **Step 6: Commit**

```powershell
git add src/hsconfig/runtime_state.py src/hsconfig/deck_config_ini.py tests/test_runtime_state.py tests/test_deck_config_ini.py
git commit -m "feat: add runtime state and INI compare-and-swap"
git push origin main
```

---

### Task 6: Install Runtime Configuration With One Commit Point

**Files:**
- Create: `src/hsconfig/runtime_installer.py`
- Create: `src/hsconfig/runtime_transaction_journal.py`
- Create: `tests/test_runtime_installer.py`
- Create: `tests/test_runtime_transaction_journal.py`
- Create: `tests/test_runtime_install_fault_matrix.py`
- Modify: `src/hsconfig/runtime_package_match.py`
- Modify: `tests/test_runtime_package_match.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class RuntimeInstallPlan:
    deck_name: str
    logical_config_dir: str
    versioned_config_dir: str
    package_root_sha256: str
    source_revision_root: Path
    source_package_root: Path
    runtime_root: Path
    ini_snapshot: DeckConfigSnapshot


@dataclass(frozen=True, slots=True)
class RuntimeInstallResult:
    status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ]
    config_dir: str
    package_root_sha256: str
    previous_config_dir: str | None
    receipt_path: Path | None


class RuntimeTransactionPhase(StrEnum):
    PREPARED = "prepared"
    RUNTIME_STAGED = "runtime_staged"
    RUNTIME_VERIFIED = "runtime_verified"
    INI_COMMITTED = "ini_committed"
    STATE_COMMITTED = "state_committed"
    FINALIZED = "finalized"


@dataclass(frozen=True, slots=True)
class RuntimeTransactionJournal:
    schema_version: int
    transaction_id: str
    deck_name: str
    source_manifest_sha256: str
    candidate_path: str
    target_path: str
    previous_config_dir: str | None
    next_config_dir: str
    previous_ini_sha256: str | None
    next_ini_sha256: str
    phase: RuntimeTransactionPhase


def plan_runtime_install(
    *,
    published_output: PublishedOutput,
    runtime_root: Path,
) -> RuntimeInstallPlan: ...


def install_runtime_package(
    plan: RuntimeInstallPlan,
    *,
    fault_hook: FaultHook = no_fault,
) -> RuntimeInstallResult: ...


def recover_runtime_state(runtime_root: Path) -> RuntimeState | None: ...
```

- [x] **Step 1: Write the happy-path/idempotency tests**

Assert the runtime directory is `<logical-name>--sha256-<full-64-hex-digest>`, copied files match the revision manifest's `04_package/CustomConfig` entries, INI switches only after verification, repeated apply is `already_current`, and only a bounded per-deck receipt lives under `.hsconfig/receipts/`.

- [x] **Step 2: Write the failure matrix**

Inject at:

```text
after_lock
after_runtime_staging_copy
after_runtime_staging_verify
after_runtime_revision_rename
before_ini_compare_and_swap
after_ini_compare_and_swap
before_state_write
after_state_write
before_receipt_write
during_receipt_write
before_old_revision_cleanup
during_old_revision_cleanup
```

Use a subprocess harness that terminates the worker with `os._exit` or `Terminate-Process` at every persisted checkpoint, not only Python exceptions. Start a fresh process and run recovery. Before INI commit, old config must remain selected. After INI commit, new config must be complete and selected. No state may select a missing or unverified directory. Receipt failure after verified state commit returns or recovers as `committed_receipt_pending`.

- [x] **Step 3: Run RED**

```powershell
python -m pytest tests/test_runtime_installer.py tests/test_runtime_install_fault_matrix.py -q -p no:cacheprovider
```

- [x] **Step 4: Implement install order**

Within `.hsconfig/apply.lock`:

1. recover incomplete owned transaction journals and re-read current INI;
2. validate package and sole apply authority;
3. atomically write a `prepared` transaction journal before creating staging;
4. exclusively create staging and record its ownership outside the VisionAI directory;
5. copy runtime files and advance the journal;
6. verify file set/full SHA-256 against the revision manifest and advance the journal;
7. if the full-digest target already exists, verify every file and reuse it while removing only the owned identical staging path; any mismatch or unproven ownership is `runtime_digest_target_conflict`;
8. otherwise atomically rename to the full 64-character SHA-256 runtime directory;
9. compare-and-swap the INI mapping and advance to `ini_committed`;
10. re-read INI, verify its hash, and verify runtime/package match;
11. atomically update the matching deck entry in multi-deck state and advance to `state_committed`;
12. atomically write or repair the bounded per-deck `last_apply_receipt.json`;
13. mark the journal `finalized`;
14. remove only unselected paths proven owned by finalized journals.

Recovery enumerates journals in stable order. The actual INI mapping is authoritative: a pre-commit journal cleans its unselected owned path; an `ini_committed` journal verifies the selected revision before completing state; a `state_committed` journal repairs a missing receipt. Ownership metadata stays under `.hsconfig/transactions`, never inside a VisionAI config directory that HearthRanger may scan.

Journal replacement uses only bounded reserved sibling names of the form
`.<transaction-id>.json.<nonce>.tmp`. Recovery accepts a canonical temp only
when its embedded transaction ID matches the filename and it is an initial
`prepared` record or a monotonic successor of the canonical final journal.
Canonical equal/older residue is removed with its captured identity; conflicting
canonical candidates fail closed. Truncated or invalid reserved regular temps
remain byte- and identity-unchanged and do not hide otherwise valid journals or
block a later update, while unknown names, reparse points, hardlinks, and excess
inventory still invalidate the store.

- [x] **Step 5: Handle `BaseException` safely**

Use `try/finally` to release locks and best-effort recovery after mutation begins. Do not catch and suppress `KeyboardInterrupt` or `SystemExit`; restore/verify state, attach notes where possible, then re-raise.

- [x] **Step 6: Run GREEN and process interruption tests**

```powershell
python -m pytest tests/test_runtime_installer.py tests/test_runtime_transaction_journal.py tests/test_runtime_install_fault_matrix.py tests/test_runtime_package_match.py -q -p no:cacheprovider
```

- [x] **Step 7: Commit**

```powershell
git add src/hsconfig/runtime_installer.py src/hsconfig/runtime_transaction_journal.py src/hsconfig/runtime_package_match.py tests/test_runtime_installer.py tests/test_runtime_transaction_journal.py tests/test_runtime_install_fault_matrix.py tests/test_runtime_package_match.py
git commit -m "feat: activate runtime packages transactionally"
git push origin main
```

---

### Task 7: Replace Legacy Runtime Apply and Package-Mutating Receipts

**Files:**
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/runtime_apply_receipts.py`
- Modify: `src/hsconfig/commands/apply.py`
- Modify: `tests/test_runtime_apply.py`
- Modify: `tests/test_runtime_apply_receipts.py`
- Modify: `tests/test_apply_decision.py`
- Modify: `tests/test_apply_gate.py`
- Create: `tests/test_package_immutability_after_apply.py`

**Interfaces:**

```python
def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
) -> dict[str, Any]: ...


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    apply_gate: dict[str, Any] | None = None,
    allow_source_informed: bool = False,
    write_history: bool = True,
) -> dict[str, Any]: ...
```

These remain compatibility facades over the publisher resolver and runtime installer.

- [x] **Step 1: Write the immutable-package test**

Hash every package file before plan/apply/failure injection and assert the complete `(path, size, sha256)` inventory is identical afterward.

- [x] **Step 2: Write the no-backup test**

After success and each injected failure, recursively assert no runtime path matches:

```text
*backup*
*.bak
*rollback_snapshot*
```

The test must distinguish allowed content-addressed inactive revisions from forbidden backup copies.

- [x] **Step 3: Run RED**

```powershell
python -m pytest tests/test_package_immutability_after_apply.py tests/test_runtime_apply.py tests/test_runtime_apply_receipts.py -q -p no:cacheprovider
```

Expected: current apply writes receipts into the package and creates rollback snapshots.

- [x] **Step 4: Convert legacy entrypoints to facades**

Remove target-directory deletion, `shutil.copytree` activation, in-place INI writes, package receipt writes, and rollback snapshot helpers. Map typed installer results to the existing CLI payload where compatibility is useful.

- [x] **Step 5: Move receipts outside packages**

Fake/plan receipts are pure returned objects. Actual apply/failure state is atomically represented by one bounded `last_apply_receipt.json` per stable deck state key under `<runtime-root>/.hsconfig/receipts/`; no append-only receipt growth is allowed.

- [x] **Step 6: Run GREEN and apply authority regressions**

```powershell
python -m pytest tests/test_package_immutability_after_apply.py tests/test_runtime_apply.py tests/test_runtime_apply_receipts.py tests/test_apply_decision.py tests/test_apply_gate.py tests/test_apply_authority_boundary.py -q -p no:cacheprovider
```

- [x] **Step 7: Commit**

```powershell
git add src/hsconfig/runtime_apply.py src/hsconfig/runtime_apply_receipts.py src/hsconfig/commands/apply.py tests/test_runtime_apply.py tests/test_runtime_apply_receipts.py tests/test_apply_decision.py tests/test_apply_gate.py tests/test_package_immutability_after_apply.py
git commit -m "refactor: remove mutable runtime apply path"
git push origin main
```

---

### Task 8: Reconcile the Twelve Audited Outputs

**Files:**
- Create: `scripts/reconcile_outputs.py`
- Create: `tests/test_reconcile_outputs.py`
- Modify: `scripts/report_output_inventory.py`
- Modify: `tests/test_output_inventory.py`
- Modify: `.gitignore`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class OutputInventory:
    audited_decks: int
    current_outputs: int
    revision_count: int
    staging_count: int
    unreferenced_revision_count: int
    backup_count: int
    rollback_count: int
    orphan_transaction_count: int
    orphan_receipt_count: int
    temporary_file_count: int
    invalid_count: int


def reconcile_audited_outputs(
    *,
    outputs_root: Path,
    catalog_path: Path,
) -> OutputInventory: ...
```

- [x] **Step 1: Write failing inventory tests**

Cover exactly twelve catalog decks, one valid pointer each, one revision each, no unknown deck roots, no staging, no invalid manifest, and no legacy timestamped package tree.

- [x] **Step 2: Run RED**

```powershell
python -m pytest tests/test_reconcile_outputs.py tests/test_output_inventory.py -q -p no:cacheprovider
```

- [x] **Step 3: Implement conservative reconciliation**

The script must support `--check` and `--apply`. `--apply` rebuilds all twelve revisions from the canonical audited build-input set; it may not adopt older package bytes. It removes obsolete output roots only after all twelve new current pointers and complete configure-run manifests verify, using an explicit old-output deletion manifest. It must never create a Config backup.

- [x] **Step 4: Rebuild or migrate all twelve outputs**

Use the audited catalog, canonical build inputs, pinned card snapshot, and frozen evidence. Do not change semantics during regeneration. After all twelve pointers verify, delete only the paths in the reviewed old-output deletion manifest and process-owned staging.

- [x] **Step 5: Verify exactly-one output state**

```powershell
python scripts/reconcile_outputs.py --outputs outputs --catalog docs/operator/audited-deck-catalog.json --check --json
python scripts/report_output_inventory.py outputs
```

Expected:

```json
{
  "audited_decks": 12,
  "current_outputs": 12,
  "revision_count": 12,
  "staging_count": 0,
  "unreferenced_revision_count": 0,
  "backup_count": 0,
  "rollback_count": 0,
  "orphan_transaction_count": 0,
  "orphan_receipt_count": 0,
  "temporary_file_count": 0,
  "invalid_count": 0
}
```

- [x] **Step 6: Run the transactional phase gate**

```powershell
python -m pytest tests/test_atomic_io.py tests/test_atomic_io_process_lock.py tests/test_run_manifest.py tests/test_output_publication_fault_matrix.py tests/test_configure_publication.py tests/test_deck_config_ini.py tests/test_runtime_install_fault_matrix.py tests/test_package_immutability_after_apply.py tests/test_reconcile_outputs.py -q -p no:cacheprovider
python -m ruff check --no-cache src tests scripts
git diff --check
git status --short
```

- [x] **Step 7: Commit tracked code only**

```powershell
git add src tests scripts .gitignore
git commit -m "feat: enforce one reconciled output per deck"
git push origin main
```

Generated `outputs/` must remain ignored and untracked.

---

## Transactional Publication Acceptance Gate

- [x] Kill a child process at every documented fault stage and recover from a fresh process.
- [x] Confirm current output always resolves to one full-tree-manifest-valid package.
- [x] Confirm runtime INI always selects either the old complete revision or the new complete revision.
- [x] Confirm no package bytes change during plan, apply, success receipt, or failure receipt.
- [x] Confirm no backup, rollback-snapshot, staging, or obsolete revision remains after reconciliation.
- [x] Confirm twelve audited deck roots, twelve current pointers, and twelve revisions.
- [x] Confirm two concurrent configure processes serialize safely.
- [x] Confirm two concurrent HSConfig apply processes serialize safely and concurrent INI edits from HSConfig-cooperating writers fail closed under the documented lock/CAS protocol; explicitly state that non-cooperating external writers are outside this guarantee.
- [x] Run:

```powershell
python -m pytest tests/test_output_publication_fault_matrix.py tests/test_runtime_install_fault_matrix.py tests/test_package_immutability_after_apply.py tests/test_reconcile_outputs.py -q -p no:cacheprovider
python scripts/reconcile_outputs.py --outputs outputs --catalog docs/operator/audited-deck-catalog.json --check --json
python -m ruff check --no-cache src tests scripts
git diff --check
```

Expected: all selected tests pass; all twelve outputs/revisions are current and every residue/invalid counter is zero; Ruff and diff checks are clean.
