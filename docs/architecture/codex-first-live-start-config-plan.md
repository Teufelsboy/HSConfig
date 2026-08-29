# Codex-First Live Start Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task by task with the
> review checkpoints below.

**Goal:** Make the installed HSConfig skill turn a normal input of only deck
name and deck code into one frozen, independently reviewed, validated,
published, live-applied, and runtime-matched start configuration, subject to
one explicit local live-policy profile.

**Architecture:** Codex remains the only LLM orchestrator. HSConfig adds a
small local profile layer, a frozen compiler-input layer, a versioned
single-candidate authority layer, and a resumable controller around the
existing immutable publisher, package lease, runtime journal, recovery, and
runtime-match primitives. Existing conservative packages and legacy
five-document optimized packages remain readable and applicable; only new
optimized generation emits the schema-4 single-candidate authority.

**Tech Stack:** Python 3.11+, frozen dataclasses, canonical JSON, existing
`package_io` and `atomic_io` Windows-safe filesystem primitives, pytest,
Hypothesis where already used, Ruff, signed Git commits, GitHub Actions.

**Spec:**
[`docs/architecture/codex-first-live-start-config.md`](codex-first-live-start-config.md)

**Approved safety amendment:** The reviewed execution protocol in this plan
supersedes only the specification's earlier apply ordering. The safe order is
`PREPARED session intent -> durable runtime-wide admission -> persisted
one-directory-at-a-time layout binding -> invocation receipt -> APPLY_STARTED
-> one install or targeted recovery`. This amendment
was required by the final crash-window review and is part of the approved plan;
implementers must not restore the earlier receipt-before-admission sequence.

**Focused Task 9 clarification:** The `install_apply_invocation` intent also
persists the exact canonical invocation-document byte size as
`apply_invocation_document_size`. The size is derived internally from the
already sealed `ApplyInvocation`, is carried unchanged through every pending
successor, and is the sole size authority for the invocation-receipt file action
installed by the final runtime-layout CAS. This closes the crash-resume gap in
which the persisted invocation digests alone cannot determine the byte size.
No valid `install_apply_invocation` cursor predates Task 9, so a cursor missing
this required field is invalid; no recapture, guessed size, or legacy upgrade is
permitted.

## Global Constraints

- Work directly on the sole local `main`; do not create a branch, worktree,
  pull request, retag, release, or historical rewrite.
- Fetch and compare upstream before the first implementation edit. Stop if
  local `main` is not a clean descendant of `origin/main` plus the approved
  design and plan commits.
- Use exactly one writer for each file area. Independent reviewers remain
  read-only and review the frozen diff after each commit-sized task.
- Preserve existing manual and unrelated changes. Never reset, checkout, or
  delete user-owned changes.
- Preserve the current conservative route and the existing legacy
  five-document optimized route. Do not migrate published packages or
  unfinished external sessions.
- Do not add an LLM client, model setting, provider abstraction, API key,
  replay reader, win-rate analysis, HSTuner handoff, post-game tuning, GUI,
  dashboard, physical SHA-free runtime directory, or batch-deck mode.
- Keep hash-qualified publication and runtime directories internally. Hide
  them only on normal human-facing surfaces.
- Never infer write permission from silence. Only a valid, identity-rebound
  operator profile with `live_by_default=true` authorizes the normal live
  route; explicit preview language always wins.
- Approval of this implementation plan is not execution-time permission to
  create or change that profile or write the real runtime. The real canary
  requires a separately recorded authorization naming the exact runtime root,
  output-base root, profile creation when absent, ShadowPriest live write, and
  possible active-mapping change.
- Every successful input fetch happens once per run. Resume consumes the
  sealed bytes and never repeats a successful network fetch or rereads a
  mutable GlobalValues baseline.
- The single-candidate compiler path must not call
  `_compile_conservative_package_decisions()` as a source of output-affecting
  state. It consumes only the sealed input snapshot, its six bound blob
  projections, and the three sealed schema-2 starter documents.
- No prepublication diagnostic receipt enters the package or grants apply
  authority. `reports/operator_summary.json` remains the sole normal
  human-facing apply authority.
- Never retry runtime apply while a prior attempt is pending or physically
  ambiguous. The fixed controller admission is durable before the invocation
  receipt or `APPLY_STARTED`; either later state is recovery-only.
- Before runtime admission, a separate fixed output-operation admission is
  durable before the first per-output claim or child mutation. It globally
  fences profile mutation, competing controller output work, every publisher
  for the bound output child, and every generic Runtime writer. Only the owning
  action-scoped admission/layout callbacks may cross it. Live handoff overlaps
  the output and runtime admissions: the runtime record is durably bound in
  `APPLY_STARTED` before the output record may disappear. Preview or pre-
  admission failure may release the output record only after its terminal
  session CAS.
- This rule spans the mutable authorities needed for recovery, not only one
  transaction ID. The overlapping fixed controller admissions under the local
  HSConfig state root prevent a different attempt, a legacy/direct runtime writer,
  a conflicting publication, and a bound profile mutation from invalidating the
  exact runtime, output revision, or profile needed to classify the attempt.
  Process-held session, profile, publication, or runtime locks are not durable
  admission authority after a crash.
- Success means the exact published package is still current, the runtime
  transaction is committed, and the same leased package matches the active
  runtime. Gameplay optimality remains explicitly out of scope.
- Use focused named tests in each task. Do not run a local full suite after
  every change. The final green exact-commit CI run is the integrated authority.
- Sign every implementation commit. Do not push intermediate commits; push
  the complete signed stack once, then monitor exactly one `ci.yml` run for
  that exact OID. If it fails deterministically, never amend or rewrite the
  pushed commit: append one signed focused fix commit, fast-forward push once,
  and monitor exactly one new run for the new OID. Never rerun the same OID.
- Use LF, UTF-8, canonical JSON, no BOM, no duplicate keys, no non-finite
  values, and no unbounded reads.

---

## Locked Module and Type Layout

The implementation uses these new modules. Do not merge them into one large
controller file or invent parallel authority paths.

| Module | Sole responsibility |
| --- | --- |
| `src/hsconfig/operator_profile.py` | Canonical local live policy, root rebinding, and safe deck-output child binding |
| `src/hsconfig/output_operation_admission.py` | Neutral fixed output-operation admission bytes, lock lease, bounded observation, and profile/publication/Runtime writer gates |
| `src/hsconfig/input_snapshot_manifest.py` | Six-blob frozen compiler input, three physical input envelopes, and sealed manifest |
| `src/hsconfig/live_start_session.py` | Closed external run layout, phase state, artifact bindings, and atomic phase CAS |
| `src/hsconfig/starter_review.py` | Schema-2 independent review validation and candidate/context binding |
| `src/hsconfig/optimized_start_authority.py` | Legacy-versus-new authority dispatch and single-candidate approval loading |
| `src/hsconfig/apply_invocation.py` | Canonical pre-apply runtime snapshot and sealed invocation receipt |
| `src/hsconfig/runtime_live_admission.py` | Neutral bounded singleton-admission bytes, atomic no-replace publication, observation, and writer fences |
| `src/hsconfig/published_apply.py` | One publication lease across apply, recovery classification, final current check, and runtime match |
| `src/hsconfig/live_start_faults.py` | Closed private orchestration fault points and no-op hook |
| `src/hsconfig/live_start_controller.py` | Repository-owned prepare, validate, review, finalize, resume, and user-status orchestration |
| `src/hsconfig/commands/live_policy.py` | Thin `live-policy enable|disable` CLI adapter |
| `src/hsconfig/commands/recover_apply.py` | Thin recovery-only CLI adapter |

The public domain surfaces are fixed as follows:

```python
# operator_profile.py
PathIdentity = tuple[int, int, int]

@dataclass(frozen=True, slots=True)
class OperatorProfile:
    schema_version: int
    live_by_default: bool
    runtime_root: Path
    runtime_root_identity: PathIdentity
    output_base_root: Path
    output_base_root_identity: PathIdentity
    content_sha256: str

@dataclass(frozen=True, slots=True)
class OperatorProfileLockToken: ...

@dataclass(frozen=True, slots=True)
class OperatorProfileLease:
    profile: OperatorProfile
    profile_path: Path
    profile_identity: PathIdentity
    profile_parent_identity: PathIdentity
    profile_lock_path: Path
    lock_token: OperatorProfileLockToken

@dataclass(frozen=True, slots=True)
class DeckOutputBinding:
    output_name: str
    output_root: Path
    precondition_state: Literal["absent", "existing"]
    precondition_identity: PathIdentity | None

def operator_profile_path(
    environ: Mapping[str, str] | None = None,
) -> Path: ...

def enable_operator_profile(
    *,
    runtime_root: Path,
    output_base_root: Path,
    expected_predecessor_sha256: str | None,
) -> OperatorProfile: ...

def disable_operator_profile(
    *, expected_predecessor_sha256: str
) -> OperatorProfile: ...

def load_operator_profile() -> OperatorProfile: ...

def revalidate_operator_profile(
    profile: OperatorProfile,
) -> OperatorProfile: ...

@contextmanager
def lease_operator_profile(
    *, expected_profile: OperatorProfile
) -> Iterator[OperatorProfileLease]: ...

def revalidate_operator_profile_lease(
    lease: OperatorProfileLease,
) -> OperatorProfile: ...

def derive_deck_output_binding(
    profile: OperatorProfile, deck_name: str
) -> DeckOutputBinding: ...
```

```python
# output_operation_admission.py
OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION = 1
OUTPUT_OPERATION_ADMISSION_MAX_BYTES = 64 * 1024
OUTPUT_OPERATION_ADMISSION_KIND = "live_start_output_operation_admission"
OUTPUT_OPERATION_ADMISSION_NAME = "output-operation-admission.json"
OUTPUT_OPERATION_ADMISSION_STAGING_NAME = "output-operation-admission.staged"
OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME = (
    ".output-operation-admission.staged.live-start-atomic.tmp"
)

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionLockToken: ...

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionLease:
    state_root: Path
    state_root_identity: PathIdentity
    lock_path: Path
    lock_identity: PathIdentity
    lock_token: OutputOperationAdmissionLockToken

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionEvidence:
    admission_path: Path
    admission_parent_identity: PathIdentity
    admission_identity: PathIdentity
    admission_size: int
    admission_sha256: str
    state: Literal["ACTIVE"]
    run_id: str
    session_root: Path
    session_root_identity: PathIdentity
    expected_session_sha256: str
    operator_profile_path: Path
    operator_profile_parent_identity: PathIdentity
    operator_profile_identity: PathIdentity
    operator_profile_sha256: str
    state_root_identity: PathIdentity
    output_base_root: Path
    output_base_root_identity: PathIdentity
    output_child_path: Path
    output_child_predecessor_state: Literal["absent", "existing"]
    output_child_predecessor_identity: PathIdentity | None
    output_bootstrap_lock_path: Path
    output_bootstrap_lock_identity: PathIdentity
    output_claim_path: Path

@contextmanager
def lease_output_operation_admission(
    *, create_if_missing: bool
) -> Iterator[OutputOperationAdmissionLease]: ...

def observe_output_operation_admission_under_lease(
    lease: OutputOperationAdmissionLease,
) -> OutputOperationAdmissionEvidence | None: ...

def require_output_operation_allows_profile_mutation(
    lease: OutputOperationAdmissionLease,
) -> None: ...

def require_output_operation_allows_publication(
    *,
    lease: OutputOperationAdmissionLease,
    output_root: Path,
    output_root_identity: PathIdentity | None,
    allowed_exact: OutputOperationAdmissionEvidence | None = None,
) -> None: ...

def require_output_operation_allows_runtime_mutation(
    *,
    lease: OutputOperationAdmissionLease,
) -> None: ...
```

The fixed record path is
`%LOCALAPPDATA%\HSConfig\output-operation-admission.json`; the fixed lock is
`%LOCALAPPDATA%\HSConfig\locks\output-operation.lock`. Its only staging and
reserved-temp paths are the two fixed sibling names above. The neutral module
imports no profile, session, publisher, controller, package, or runtime module.
It parses and serializes only primitive canonical paths, identities, digests,
and IDs. Capability-aware create/revalidate/release adapters are added in Task
8 after Task 3 owns their session bearers. Observation is bounded, no-follow,
and read-only across exactly the final, staging, and reserved-temp paths. Any
malformed, unsafe, replaced, unbounded, or orphan staging/temp occupant is a
blocking error, never equivalent to absence.

The generic runtime-mutation gate accepts only an active same-thread lease and
permits a public, direct, or legacy Runtime writer only when all three fixed
paths are absent. A valid final record and every staging/temp, malformed,
unsafe, replaced, or multiply occupied row block globally. It exposes no
`allowed_exact`, Evidence, path, or root-scoped bypass. The owning controller
may cross this fence only inside the action-scoped private callbacks specified
in Tasks 3, 9, and 10; an ordinary loaded dataclass never authorizes a write.

```python
# input_snapshot_manifest.py
@dataclass(frozen=True, slots=True)
class InputBlobBinding:
    name: str
    sha256: str
    size_bytes: int
    record_count: int

@dataclass(frozen=True, slots=True)
class ValidatedInputSnapshotManifest:
    document: StarterDocument
    compiler_inputs: FrozenJsonDocument
    operator_bindings: FrozenJsonDocument
    blobs: tuple[InputBlobBinding, ...]

@dataclass(frozen=True, slots=True)
class FrozenCompilerInputs:
    manifest: ValidatedInputSnapshotManifest
    deck: FrozenJsonDocument
    full_cards: FrozenJsonDocument
    collectible_cards: FrozenJsonDocument
    source_acquisition: FrozenJsonDocument
    source_documents: FrozenJsonDocument
    globalvalues_baseline: FrozenJsonDocument

def freeze_compiler_inputs(...) -> FrozenCompilerInputs: ...
def validate_input_snapshot_manifest_document(
    document: FrozenJsonDocument,
) -> ValidatedInputSnapshotManifest: ...
def load_frozen_compiler_inputs(run_root: Path) -> FrozenCompilerInputs: ...
```

The three physical input envelopes are locked to the specification's closed
run layout:

- `inputs/deck.json` is the canonical normalized `deck` blob;
- `inputs/cards.json` has exactly `full_cards`, `collectible_cards`, and
  `globalvalues_baseline`;
- `inputs/sources.json` has exactly `source_acquisition` and
  `source_documents`.

The six manifest rows hash the canonical bytes of those six named blob values,
not filesystem paths. The session binds the three envelope bytes separately,
so both nested data and physical run artifacts are immutable.

```python
# configuration_mode.py -- the sole alias authority avoids an import cycle
OptimizedStartAuthoritySchema = Literal[
    "legacy_five_doc",
    "single_candidate_review_v1",
]

# optimized_start_authority.py imports and re-exports that alias

@dataclass(frozen=True, slots=True)
class ValidatedSingleStarterApproval:
    snapshot: ValidatedInputSnapshotManifest
    context: StarterContext
    candidate: ValidatedStarterCandidate
    review: ValidatedStarterReview

ValidatedOptimizedStartAuthority = (
    ValidatedStarterSelection | ValidatedSingleStarterApproval
)

def load_optimized_start_authority(
    *, report_root: Path, manifest: Mapping[str, Any]
) -> ValidatedOptimizedStartAuthority: ...
```

```python
# apply_invocation.py
@dataclass(frozen=True, slots=True)
class PreApplyRuntimeSnapshot: ...

@dataclass(frozen=True, slots=True)
class ValidatedSameAttemptJournalDelta: ...

@dataclass(frozen=True, slots=True)
class ApplyInvocation:
    schema_version: int
    apply_attempt_id: str
    run_id: str
    publication_revision: str
    publication_content_root_sha256: str
    output_operation_admission_path: Path
    output_operation_admission_identity: PathIdentity
    output_operation_admission_sha256: str
    output_child_binding_sha256: str
    output_child_path: Path
    output_child_identity: PathIdentity
    operator_profile_sha256: str
    runtime_root: Path
    runtime_root_identity: PathIdentity
    pre_apply_runtime_snapshot: PreApplyRuntimeSnapshot
    content_sha256: str

def build_apply_invocation(...) -> ApplyInvocation: ...
def load_apply_invocation(path: Path) -> ApplyInvocation: ...
def require_same_attempt_pre_apply_snapshot(
    *,
    sealed: PreApplyRuntimeSnapshot,
    current: PreApplyRuntimeSnapshot,
    apply_attempt_id: str,
    validated_delta: ValidatedSameAttemptJournalDelta | None,
) -> None: ...
```

```python
# live_start_session.py
LiveStartTerminalStatus = Literal[
    "LIVE_AND_MATCHED",
    "ALREADY_LIVE",
    "PREVIEW_READY",
    "PROFILE_REQUIRED",
    "FAILED_PRESERVED",
    "APPLIED_BUT_NOT_VERIFIED",
]

@dataclass(frozen=True, slots=True)
class SessionLockToken: ...

@dataclass(frozen=True, slots=True)
class TerminalRetirementAuthorization: ...

@dataclass(frozen=True, slots=True)
class TerminalResolutionStepReceipt: ...

@dataclass(frozen=True, slots=True)
class RuntimeAttemptRecoveryAuthorization: ...

@dataclass(frozen=True, slots=True)
class ApplyRecoveryStepReceipt: ...

RuntimeObservationFamily = Literal[
    "first_install",
    "nonterminal_apply",
    "terminal_resolution",
    "terminal_classification",
]

@dataclass(frozen=True, slots=True)
class RuntimeObservationAuthorization: ...

@dataclass(frozen=True, slots=True)
class RuntimeObservationReceipt: ...

@dataclass(frozen=True, slots=True)
class RuntimeObservationPostcondition: ...

@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapAuthorization: ...

@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapStepReceipt: ...

@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapPhysicalPostcondition: ...

@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapEvidence: ...

@dataclass(frozen=True, slots=True)
class OwnerRetirementEvidence: ...

@dataclass(frozen=True, slots=True)
class RuntimeAdmissionAuthorization: ...

@dataclass(frozen=True, slots=True)
class RuntimeAdmissionStepReceipt: ...

@dataclass(frozen=True, slots=True)
class RuntimeAdmissionPhysicalPostcondition: ...

@dataclass(frozen=True, slots=True)
class TerminalResolutionEvidence: ...

@dataclass(frozen=True, slots=True)
class RuntimeApplyRecoveryEvidence: ...

@dataclass(frozen=True, slots=True)
class SuccessAckStepEvidence: ...

@dataclass(frozen=True, slots=True)
class RuntimeApplyRecoveryPhysicalPostcondition: ...

@dataclass(frozen=True, slots=True)
class TerminalResolutionPhysicalPostcondition: ...

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionPhysicalPostcondition: ...

@dataclass(frozen=True, slots=True)
class OutputChildBootstrapPhysicalPostcondition: ...

TerminalPhysicalStepPostcondition = (
    TerminalResolutionPhysicalPostcondition | SuccessAckStepEvidence
)

RuntimeApplyRecoveryAction = Literal[
    "observe_not_committed",
    "materialize_file_action_staging",
    "retire_unbound_file_action_staging",
    "commit_bound_initial_attempt_record",
    "commit_bound_candidate_planned_attempt_record",
    "commit_bound_prior_owner_planned_attempt_record",
    "advance_controller_transaction_journal_write",
    "promote_legacy_uuid_transaction_temp",
    "retire_legacy_uuid_transaction_temp",
    "bind_created_candidate",
    "bind_candidate_fence",
    "commit_bound_prior_owner_attempt_record",
    "materialize_candidate_tree_entry",
    "verify_candidate_tree",
    "rename_candidate_to_target",
    "bind_renamed_target",
    "write_deck_config_ini",
    "commit_ini_journal",
    "write_runtime_state",
    "commit_state_journal",
    "write_last_apply_receipt",
    "finalize_journal",
    "finalize_attempt_record",
    "commit_owner_retirement_prepared",
    "initialize_owner_cleanup_journal",
    "delete_owner_cleanup_entry",
    "advance_owner_cleanup_journal",
    "retire_owner_target_root",
    "commit_owner_retirement_completed",
    "retire_old_owner_journal",
    "observe_owner_retirement_completed",
    "observe_committed",
    "observe_pending",
    "observe_unknown",
]

RuntimeTerminalObservationAction = Literal[
    "observe_not_committed",
    "observe_pending",
    "observe_unknown",
]

RuntimeLayoutBootstrapAction = Literal[
    "create_or_confirm_runtime_layout_directory",
]

RuntimeLayoutBootstrapAdvance = Literal[
    "directory_bound",
]

NonterminalApplyRecoveryPureTransition = Literal[
    "select_terminal_classification",
    "apply_committed",
    "runtime_matched",
    "recovery_closed",
]

TerminalResolutionPhysicalAction = (
    RuntimeApplyRecoveryAction
    | Literal[
        "retire_unbound_terminal_cleanup_inventory_staging",
        "materialize_terminal_cleanup_inventory_staging",
        "commit_bound_terminal_cleanup_inventory",
        "delete_cleanup_entry",
        "retire_cleanup_journal",
        "retire_cleanup_fence",
        "retire_cleanup_inventory",
        "retire_ack_journal",
        "retire_ack_fence",
    ]
)

TerminalResolutionCleanupStage = Literal[
    "PREPARED",
    "INVENTORY_BOUND",
    "CLEANING",
    "JOURNAL_RETIRED",
    "FENCE_RETIRED",
    "INVENTORY_RETIRED",
    "COMPLETE",
]

@dataclass(frozen=True, slots=True)
class TerminalResolutionCleanupInventory: ...

@dataclass(frozen=True, slots=True)
class TerminalCleanupInventoryPublishStep:
    action: Literal["materialize", "commit"]
    staging: MaterializedStagingBytes | None
    published: PublishedNoReplaceBytes | None
    step_receipt: TerminalResolutionStepReceipt

@dataclass(frozen=True, slots=True)
class TerminalCleanupInventoryRetireStep:
    action: Literal["unbound_staging", "final_sidecar"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

@dataclass(frozen=True, slots=True)
class LiveStartSessionLease:
    session_root: Path
    session_root_identity: PathIdentity
    session_lock_path: Path
    session_lock_identity: PathIdentity
    lock_token: SessionLockToken

OutputOperationAdmissionState = Literal[
    "ACTIVE",
    "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
    "TERMINAL_RELEASE_AUTHORIZED",
]

OutputOperationAdmissionAction = Literal[
    "materialize_output_operation_admission_staging",
    "commit_bound_output_operation_admission",
    "retire_unbound_output_operation_admission_staging",
]

RuntimeAdmissionAction = Literal[
    "materialize_runtime_admission_staging",
    "commit_bound_runtime_admission",
    "retire_unbound_runtime_admission_staging",
    "materialize_invocation_receipt_staging",
    "commit_bound_invocation_receipt",
    "retire_unbound_invocation_receipt_staging",
]

RuntimeAdmissionAdvance = Literal[
    "unbound_staging_retired",
    "staging_bound",
    "admission_primary_applied",
    "invocation_receipt_unbound_staging_retired",
    "invocation_receipt_staging_bound",
    "invocation_receipt_committed",
]

RuntimeAdmissionReleaseDisposition = Literal[
    "old_unlinked",
    "already_absent",
    "valid_foreign_successor",
]

@dataclass(frozen=True, slots=True)
class RuntimeAdmissionReleasePostcondition:
    admission_path: Path
    admission_parent_identity: PathIdentity
    historical_admission_identity: PathIdentity
    historical_admission_sha256: str
    disposition: RuntimeAdmissionReleaseDisposition
    foreign_successor_identity: PathIdentity | None
    foreign_successor_sha256: str | None

OutputOperationAdmissionAdvance = Literal[
    "unbound_staging_retired",
    "staging_bound",
    "admission_active",
]

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionAuthorization: ...

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionStepReceipt: ...

@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionReleaseAuthorization: ...

OutputChildBootstrapAction = Literal[
    "materialize_claim_staging",
    "commit_bound_claim",
    "retire_unbound_claim_staging",
    "bind_existing_child",
    "create_output_child",
    "retire_claim",
    "confirm_claim_absent_and_current_exact",
]

OutputChildBootstrapAdvance = Literal[
    "unbound_claim_staging_retired",
    "claim_staging_bound",
    "claim_bound",
    "child_bound",
    "claim_unlinked",
    "claim_retired",
]

@dataclass(frozen=True, slots=True)
class OutputChildBootstrapAuthorization: ...

@dataclass(frozen=True, slots=True)
class OutputChildBootstrapStepReceipt: ...

@contextmanager
def lease_live_start_session(
    session_root: Path,
) -> Iterator[LiveStartSessionLease]: ...

def prepare_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_prepublication_session: LiveStartSession,
    admission_path: Path,
    admission_staging_path: Path,
    admission_staging_inner_temp_path: Path,
    admission_parent_identity: PathIdentity,
    planned_admission_size: int,
    planned_admission_sha256: str,
    output_base_path: Path,
    output_base_identity: PathIdentity,
    output_child_path: Path,
    predecessor_output_child_identity: PathIdentity | None,
    output_bootstrap_lock_path: Path,
    output_bootstrap_lock_identity: PathIdentity,
) -> LiveStartSession: ...

def authorize_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    action: OutputOperationAdmissionAction,
) -> OutputOperationAdmissionAuthorization: ...

def advance_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    transition: OutputOperationAdmissionAdvance,
    physical_step_receipt: OutputOperationAdmissionStepReceipt,
) -> LiveStartSession: ...

def _authorize_output_operation_admission_release_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
) -> OutputOperationAdmissionReleaseAuthorization: ...

def prepare_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_prepublication_session: LiveStartSession,
    output_base_path: Path,
    output_base_identity: PathIdentity,
    output_child_path: Path,
    predecessor_output_child_identity: PathIdentity | None,
    planned_claim_size: int,
    planned_claim_sha256: str,
    planned_claim_staging_path: Path,
    planned_claim_staging_inner_temp_path: Path,
    output_bootstrap_lock_path: Path,
    output_bootstrap_lock_identity: PathIdentity,
) -> LiveStartSession: ...

def authorize_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    action: OutputChildBootstrapAction,
) -> OutputChildBootstrapAuthorization: ...

def advance_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    transition: OutputChildBootstrapAdvance,
    bootstrap_authorization: OutputChildBootstrapAuthorization | None,
    physical_step_receipt: OutputChildBootstrapStepReceipt | None,
) -> LiveStartSession: ...

def _execute_output_child_bootstrap_physical_step(
    *,
    bootstrap_authorization: OutputChildBootstrapAuthorization,
    action: OutputChildBootstrapAction,
    physical_action: Callable[[], OutputChildBootstrapPhysicalPostcondition],
) -> OutputChildBootstrapStepReceipt: ...

def prepare_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_terminal_session: LiveStartSession,
    operation: Literal[
        "ack_success",
        "release_not_committed",
        "release_committed_mismatch",
        "release_resolved_terminal",
    ],
    runtime_observation_receipt: RuntimeObservationReceipt | None,
) -> LiveStartSession: ...

TerminalRetirementAdvance = Literal[
    "ack_journal_retired",
    "evidence_retired",
    "admission_release_authorized",
]

def advance_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
    transition: TerminalRetirementAdvance,
    terminal_authorization: TerminalRetirementAuthorization | None,
    physical_step_receipt: TerminalResolutionStepReceipt | None,
) -> LiveStartSession: ...

TerminalResolutionAdvance = Literal[
    "cleanup_inventory_unbound_staging_retired",
    "cleanup_inventory_staging_bound",
    "inventory_bound",
    "cleaning_started",
    "cleanup_cursor_advanced",
    "journal_retired",
    "fence_retired",
    "inventory_retired",
    "physical_recovery_advanced",
    "stabilized",
]

def advance_terminal_resolution_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_resolution_session: LiveStartSession,
    transition: TerminalResolutionAdvance,
    resolved_evidence: TerminalResolutionEvidence | None,
    terminal_authorization: TerminalRetirementAuthorization | None,
    physical_step_receipt: TerminalResolutionStepReceipt | None,
) -> LiveStartSession: ...

def publish_terminal_cleanup_inventory_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_prepared_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    inventory: TerminalResolutionCleanupInventory,
    action: Literal["materialize", "commit"],
) -> TerminalCleanupInventoryPublishStep: ...

def retire_terminal_cleanup_inventory_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_resolution_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["unbound_staging", "final_sidecar"],
) -> TerminalCleanupInventoryRetireStep: ...

def authorize_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
) -> TerminalRetirementAuthorization: ...

def _authorize_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_session: LiveStartSession,
    expected_action: (
        RuntimeApplyRecoveryAction | NonterminalApplyRecoveryPureTransition
    ),
) -> RuntimeAttemptRecoveryAuthorization: ...

def _execute_apply_recovery_physical_step(
    *,
    recovery_authorization: RuntimeAttemptRecoveryAuthorization,
    action: RuntimeApplyRecoveryAction,
    physical_action: Callable[[], RuntimeApplyRecoveryPhysicalPostcondition],
) -> ApplyRecoveryStepReceipt: ...

def _execute_terminal_resolution_physical_step(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    action: TerminalResolutionPhysicalAction,
    physical_action: Callable[[], TerminalPhysicalStepPostcondition],
) -> TerminalResolutionStepReceipt: ...

def _execute_output_operation_admission_physical_step(
    *,
    admission_authorization: OutputOperationAdmissionAuthorization,
    action: OutputOperationAdmissionAction,
    physical_action: Callable[
        [], OutputOperationAdmissionPhysicalPostcondition
    ],
) -> OutputOperationAdmissionStepReceipt: ...

_PhysicalResultT = TypeVar("_PhysicalResultT")

def _execute_runtime_admission_physical_step(
    *,
    admission_authorization: RuntimeAdmissionAuthorization,
    action: RuntimeAdmissionAction,
    physical_action: Callable[[], RuntimeAdmissionPhysicalPostcondition],
) -> RuntimeAdmissionStepReceipt: ...

def _execute_runtime_admission_release(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["release_runtime_admission"],
    physical_action: Callable[[], RuntimeAdmissionReleasePostcondition],
) -> RuntimeAdmissionReleasePostcondition: ...

def _execute_output_operation_release(
    *,
    release_authorization: OutputOperationAdmissionReleaseAuthorization,
    physical_action: Callable[[], _PhysicalResultT],
) -> _PhysicalResultT: ...

def prepare_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_committed_session: LiveStartSession,
    layout_evidence: RuntimeLayoutBootstrapEvidence,
) -> LiveStartSession: ...

def _authorize_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    action: RuntimeLayoutBootstrapAction,
) -> RuntimeLayoutBootstrapAuthorization: ...

def _execute_runtime_layout_bootstrap_physical_step(
    *,
    layout_authorization: RuntimeLayoutBootstrapAuthorization,
    action: RuntimeLayoutBootstrapAction,
    physical_action: Callable[
        [], RuntimeLayoutBootstrapPhysicalPostcondition
    ],
) -> RuntimeLayoutBootstrapStepReceipt: ...

def advance_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    transition: RuntimeLayoutBootstrapAdvance,
    physical_step_receipt: RuntimeLayoutBootstrapStepReceipt,
) -> LiveStartSession: ...

def _authorize_runtime_observation_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    observation_family: RuntimeObservationFamily,
    apply_attempt_id: str,
) -> RuntimeObservationAuthorization: ...

def _execute_runtime_observation(
    *,
    observation_authorization: RuntimeObservationAuthorization,
    observation_family: RuntimeObservationFamily,
    read_only_observation: Callable[[], RuntimeObservationPostcondition],
) -> RuntimeObservationReceipt: ...

def prepare_first_runtime_install_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_apply_started_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt,
) -> LiveStartSession: ...

def _authorize_runtime_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_session: LiveStartSession,
    action: RuntimeAdmissionAction,
) -> RuntimeAdmissionAuthorization: ...

def advance_runtime_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_session: LiveStartSession,
    transition: RuntimeAdmissionAdvance,
    physical_step_receipt: RuntimeAdmissionStepReceipt,
) -> LiveStartSession: ...

NonterminalApplyRecoveryAdvance = Literal[
    "physical_recovery_advanced",
    "select_terminal_classification",
    "apply_committed",
    "runtime_matched",
    "recovery_closed",
]

def prepare_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_nonterminal_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt,
) -> LiveStartSession: ...

def advance_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_session: LiveStartSession,
    transition: NonterminalApplyRecoveryAdvance,
    recovery_evidence: RuntimeApplyRecoveryEvidence | None,
    recovery_authorization: RuntimeAttemptRecoveryAuthorization | None,
    physical_step_receipt: ApplyRecoveryStepReceipt | None,
    runtime_observation_receipt: RuntimeObservationReceipt | None,
) -> LiveStartSession: ...
```

`TerminalRetirementAuthorization` and `TerminalResolutionStepReceipt` are
private opaque, nonserializable, originating-thread capabilities. A shallow
copy shares the same private bearer and cannot mint authority. Every physical
helper consumes exactly one stage-bound authorization, performs or confirms at
most one declared physical action, and returns a fresh step receipt bound to
the active session bearer, exact predecessor cursor and digest, operation,
branch, outer and cleanup stages, cursor, action, the matching postcondition-
family digest, and exact physical postcondition. Terminal resolution requires
`TerminalResolutionEvidence`; success acknowledgement requires the separate
nonpersisted `SuccessAckStepEvidence` and forbids terminal-resolution evidence.
The latter binds the predecessor retirement cursor, acknowledgement/owner/
target/admission facts, action, and exact journal/fence postcondition. The
receipt is single-use and is not constructible from a public dataclass,
Boolean, path, or observation.

`advance_terminal_resolution_under_lock()` performs one session-only CAS and no
physical I/O. It accepts only the exact stage/transition combinations defined by
the terminal-resolution matrix. `cleaning_started` and `stabilized` are pure-CAS
edges and consume a fresh `terminal_authorization` plus the exact caller-visible
`resolved_evidence` while `physical_step_receipt` is null.
`cleanup_inventory_unbound_staging_retired`,
`cleanup_inventory_staging_bound`, `inventory_bound`, every cursor increment,
`journal_retired`, `fence_retired`,
`inventory_retired`, and each `physical_recovery_advanced` edge require
`resolved_evidence=null`, consume the matching fresh step receipt, and install
the exact successor evidence only from the private receipt registry while
`terminal_authorization` is null. Missing, both-present, forged, stale, reused,
cross-thread, cross-branch, wrong-action, wrong-stage, or wrong-cursor carriers
fail before CAS. The two inventory helpers return the exact flushed/reread or
absence postcondition together with that receipt; neither performs a session
CAS or reacquires a lock. After an action-before-CAS crash, resume remints an
authorization from the still-persisted predecessor, accepts only the exact
predecessor or that action's exact idempotent postcondition, and emits a new
receipt for the same successor CAS. It never rebinds an already non-null
identity and never derives successor bytes from an observed occupant.

`TerminalCleanupInventoryPublishStep` is action-closed: `materialize` returns
non-null `staging`, null `published`, and one receipt; `commit` returns null
`staging`, non-null `published`, and one receipt. The retirement helper's
`unbound_staging` action is legal only from `RECOVERY_PREPARED` with nested
`PLANNED` residue and cannot touch the final path; `final_sidecar` is legal only
after fence retirement and cannot touch staging. Both return one receipt for
the exact declared successor CAS. Mixed results or stages fail before callback.

**Durable external-file action rule.** Every controller authority-file create
or replace uses one shared persisted `PLANNED -> STAGING_BOUND -> committed`
protocol. `PLANNED` binds the action index/kind, final and deterministic staging
paths, deterministic inner-temp path, already identity-bound parent, exact
predecessor or expected absence, and complete canonical successor bytes with
size/digest before any write. Its staging identity is null. An uninterrupted
materialize callback creates and flushes the exact staging bytes, rereads one
plain no-follow `nlink=1` file with no ADS or reparse metadata, and returns a
receipt whose CAS alone installs the staging identity and `STAGING_BOUND`.
Until that CAS succeeds, a staging or inner-temp occupant is rollback-only: an
owning fresh callback may securely retire it and retry, but may never adopt,
promote, or infer creator provenance from it. A hard exit before the binding
therefore loses work, not authority.

`STAGING_BOUND` makes the staging identity immutable. Its sole commit callback
moves, renames, or links exactly that identity to the final path. Final-only is
valid only when its identity equals the persisted staging identity. On the
POSIX hard-link fallback, final plus staging is one legal intermediate only
when both names have the same bound identity and bytes, the total link count is
two, the inner temp is absent, and the parent is unchanged; the callback
unlinks only staging, flushes the parent, and rereads final as the same identity
with link count one before issuing the commit receipt. The committed CAS copies
that already-bound identity into the action-specific successor and clears the
file-action cursor. A final occupant created directly from `PLANNED`, missing
bound staging/final, different identity, equal-byte replacement, wrong bytes,
unsafe type, changed parent, unexpected link count, unknown sibling, or mixed
row is preserved as tamper. If planned successor bytes equal an exact
predecessor, the action is a preselected no-op confirmation and never replaces
its identity.

This protocol applies uniformly to the fixed output-operation admission,
per-child claim, runtime admission, controller fence and journal, INI, runtime
state, last-apply receipt, prepublication/terminal cleanup inventories, and
owner-retirement authority. Legacy APIs may retain their existing atomic-write
compatibility wrapper, but controller paths never compose materialization and
commit without the intervening durable CAS. The only null-to-exact filesystem
capture outside this rule is an action-specific plain empty directory create
already protected by an exact persisted owning claim; it never authorizes an
authority-file identity, parent, predecessor, target owner, cleanup entry, or
runtime target.

`advance_terminal_retirement_under_lock()` closes the non-resolution
retirement paths with the same carrier discipline. An owning success consumes
one fence-retirement receipt to reach `EVIDENCE_RETIRED`. A non-owning success
consumes one journal-retirement receipt to reach `ACK_JOURNAL_RETIRED`, then a
fresh token and fence-retirement receipt to reach `EVIDENCE_RETIRED`. A stable
non-success path with no physical evidence deletion consumes a fresh token in a
pure CAS to `EVIDENCE_RETIRED`. Every path then consumes a separate fresh token
in the pure CAS to `ADMISSION_RELEASE_AUTHORIZED`. Only the final exact
admission unlink is receipt-free because no session CAS follows it. It still
passes exactly one `release_runtime_admission` callback through
`_execute_runtime_admission_release()`, which validates and consumes the fresh
release-authorized bearer before observation or I/O. Missing, both-present,
wrong-action, stale, reused, or cross-thread carriers fail before callback or
CAS. The callback returns `RuntimeAdmissionReleasePostcondition`, not a bare
status literal. Its path, parent, historical identity, and historical digest
must equal the private bearer registry. `old_unlinked|already_absent` require
jointly null foreign fields; `valid_foreign_successor` requires an exact
identity-distinct foreign identity/digest pair. Wrong historical facts or mixed
nullability fail even when the disposition spelling is valid.

`RuntimeAttemptRecoveryAuthorization` and `ApplyRecoveryStepReceipt` are a
separate private capability family and can never be used as terminal-retirement
carriers. `prepare_nonterminal_apply_recovery_under_lock()` binds one closed
self-digested physical predecessor while the session is exactly nonterminal
`APPLY_STARTED|APPLY_COMMITTED`.
`_authorize_nonterminal_apply_recovery_under_lock()` is the Task-3-owned low
level mint. It validates the active same-thread session bearer, exact persisted
cursor, action index, and exact physical table action or the
`apply_committed|runtime_matched|recovery_closed` pure transition. It explicitly
refuses `select_terminal_classification`, which belongs to the separate
observation-receipt family. It does not
inspect profile, package, admission, or runtime state. Task 10 first validates
those external authorities and only then delegates to this mint; no Task-3
module imports a later module. The family-specific Task-3 executors are the
only bridge from an opaque physical bearer to Task-8 or Task-9 I/O. Before
invoking the supplied callback, an executor validates the private registry
entry, active originating thread and session bearer, exact persisted
predecessor cursor, action, family, and freshness, and atomically marks the
authorization consumed. A validation failure never invokes the callback. The
executor invokes it at most once, accepts only the closed action-specific
postcondition—exact changed path, identity, digest, absence, cursor, or runtime
fact—and only then constructs the sole complete immediate successor and stores
it behind one family-specific, same-thread, single-use receipt. A callback
exception or process death returns no receipt and leaves that authorization
spent; resume may mint a fresh authorization only from the still-persisted
predecessor after validating either that predecessor or the exact permitted
idempotent postcondition. The old bearer and execution frame remain unusable.
The callback never supplies a complete session evidence object. Constructors,
registries, and receipt issuers remain module-private. Wrong-action,
cross-authorization, incomplete, invented, or post-bind identity-substituted
postconditions fail without a receipt.

Each paired recovery helper delegates exactly one callback through the matching
Task-3 executor and advances or confirms at most one table row. The executor
registers the complete action-specific successor behind one opaque receipt and
returns only that receipt. The caller
cannot inspect, reconstruct, replace, or also supply that successor, and
`advance_nonterminal_apply_recovery_under_lock()` consumes that receipt in the
matching same-phase recovery-cursor CAS before another token can be minted.
On those physical edges `recovery_evidence` and
`runtime_observation_receipt` are null; the CAS installs only the privately
registered successor. `apply_committed`, `runtime_matched`, and
`recovery_closed` consume a fresh recovery authorization plus the exact
caller-visible evidence and no receipt. `select_terminal_classification`
instead consumes exactly one `RuntimeObservationReceipt`; its other authority
inputs are null. The receipt's private successor binds exactly one
`observe_not_committed|observe_pending|observe_unknown` action from the same
pair/cursor observation. The CAS performs no filesystem observation or
mutation, increments `action_index` once, changes only `expected_action` and the
required self-digests, and leaves every physical evidence field byte-identical.
`observe_committed` is never a selection target. A callback exception alone
changes no classification.

The recovery cursor stays bound through every legal phase advance. Its
`recovery_stage` is `ACTIVE|CLOSED`. Every initial, physical, classification,
`apply_committed`, and `runtime_matched` successor remains `ACTIVE`.
`recovery_closed` is the sole `ACTIVE -> CLOSED` transition. It requires
`expected_action=null`, stable physical disposition, no successor fields, and
`external_file_action=null`; it changes only `recovery_stage` plus required
self-digests and deliberately retains the rest of the complete recovery object.
Every other recovery transition rejects `CLOSED`. The next
`bind_result_intent_under_lock()` CAS validates that exact closed cursor,
installs the result intent, and atomically clears
`apply_recovery`. A crash between recovery closure and result-intent binding
therefore resumes the same classification without reinstalling or inventing
evidence. Both carrier families reject cross-use.

`RuntimeObservationAuthorization` and `RuntimeObservationReceipt` form a
separate private, nonserializable, originating-thread, single-use family tagged
exactly `first_install|nonterminal_apply|terminal_resolution|
terminal_classification`. Task 10 first validates the active session, profile,
output-operation, package/runtime pair, admission, invocation, attempt, and
family-specific predecessor, then delegates to the Task-3 mint. The Task-3
executor consumes that bearer before invoking one Task-9 read-only callback.
The callback may return only the family-closed postcondition. The executor
privately registers the exact session predecessor digest, pair/admission
context, run/attempt, family, full initial Evidence or exact recovery
digest/index/action plus selected terminal observation, and returns only the
opaque receipt. The three initial prepare CASes and the selection CAS install
only that registry-private successor. Ordinary diagnostic Evidence and
`RuntimeFailureSelection` values are never mutation authority. Constructed,
swapped, stale, cross-family, cross-pair, cross-thread, wrong-admission,
wrong-attempt, runtime-changed, or reused receipts fail before CAS.

`RuntimeObservationPostcondition` is private and family-closed. `first_install`
and `nonterminal_apply` carry exactly one complete
`RuntimeApplyRecoveryEvidence`; `terminal_resolution` carries exactly one
complete `TerminalResolutionEvidence`; `terminal_classification` carries the
exact current recovery digest/index/action, disposition
`select_terminal_observation`, and one exact non-null selected observation.
Every non-family field is null. The Task-9
constructor is reachable only after validating the active pair/admission and
copies their private context binding into the executor registry. The executor
rejects a family mismatch, a diagnostic-only constructor, or a selection whose
recovery facts differ from the authorization predecessor. A diagnostic
`resume_current_action` result never mints an observation receipt.

`RuntimeLayoutBootstrapAuthorization` and its receipt are a fourth private
Task-3 bearer family. After the schema-2 runtime admission is durably committed
but before the invocation receipt or `APPLY_STARTED`, Task 10 persists one
closed `RuntimeLayoutBootstrapEvidence`. It contains the fixed ordered directory
list, one cursor, and one exact `absent|existing` predecessor row per directory.
The sole physical action creates or confirms exactly the current row under its
already-bound parent and returns one postcondition; its receipt CAS binds the
successor identity and advances by exactly one row. Existing rows may be
nonempty but must remain the sealed plain/no-follow directory identity. Absent
rows accept only one newly created or create-before-CAS plain, empty,
non-reparse directory under the sealed parent. This is the plan's only
null-to-exact directory-identity capture and never authorizes a file, target,
cleanup entry, or replacement. The last receipt CAS marks the layout complete;
only then may the invocation-receipt file action be installed. Forged, stale,
reused, cross-thread, skipped, wrong-parent, nonempty newly created, replaced,
ADS, reparse, unsafe, or out-of-order rows fail before another action.

The only file-shaped exception is not an identity-authority capture:
attempt-owned Candidate leaves are explicitly ephemeral content authority.
Under the still-active package/runtime pair, exact bound Candidate root and
destination parent, a resume may confirm one plain regular, `nlink=1`,
ADS-/reparse-free leaf at the exact manifest path when kind, size, SHA-256, and
the unchanged source-manifest authority all match. A safe same-byte replacement
is semantically equivalent before and after that receipt and is not used as an
authority identity. Root, parent, source, kind, bytes, an extra entry, hardlink,
ADS, or reparse drift is tamper. This exception never applies to a fence,
journal, INI, state, receipt, inventory, admission, claim, target root, or any
published tree.

The `first_install` observation receipt replaces the former separate
first-install bearer. Its low-level mint accepts only an active same-thread
session lease and the exact durably persisted `APPLY_STARTED` cursor for that
attempt. Task 10 first
revalidates the active profile and package/runtime pair, retired output-child
binding, invocation, admission, the release-authorized output-operation
handoff, exact old-record absence or permitted foreign successor, the complete
byte-identical runtime-layout binding, unchanged
pre-apply snapshot, and absence of same-attempt fence, journal, candidate,
target, or staged evidence, then delegates to the observation executor. The
bearer never authorizes a monolithic installer callback. Its receipt is consumed exactly once by
`prepare_first_runtime_install_under_lock()`, which performs no runtime I/O and
CASes only the registry-private complete all-same-attempt-surfaces-absent
initial `RuntimeApplyRecoveryEvidence` into the
session. It requires the completed layout binding and copies, rather than
recaptures, every required parent identity into the initial cursor. That
initial evidence selects only
`materialize_file_action_staging` for canonical schema-2 `ACTIVE`, binds its
absent final plus deterministic staging/inner-temp paths, parent identity,
complete planned bytes/size/digest, and null staging identity. Only that
persisted nonterminal cursor can mint the first one-row
file-action authorization. The ordinary install and exact-attempt recovery then
use the same action -> callback -> receipt -> session-CAS loop for every fence,
journal, candidate tree entry, candidate verification, target rename, INI,
state, receipt, and owner-retirement step. A crash after the preparation CAS but
before the first attempt-authority-file byte therefore resumes the same cursor;
the earlier layout identities remain bound and it
cannot safely repeat or skip an opaque installer call. Once the cursor exists,
no `first_install` observation bearer can be minted again. Forged, stale, reused,
cross-thread, wrong-attempt, or pre-`APPLY_STARTED` bearers fail before CAS or
runtime observation.

The output-bootstrap authorization and receipt are a third private Task-3
bearer family. They bind the active session token/thread, exact bootstrap cursor,
output base/child/claim authority, action, and one immediate postcondition.
`authorize_output_child_bootstrap_under_lock()` performs no filesystem I/O;
Task 8's guarded physical helper passes its one callback only through
`_execute_output_child_bootstrap_physical_step()`. Unbound claim staging
retirement consumes its receipt in `unbound_claim_staging_retired`, keeps the
file action logically `PLANNED`, records residue absent, and selects only the
fresh materialize action. `claim_bound`, `child_bound`, `claim_unlinked`, and
`claim_retired` each consume exactly the matching physical receipt while the authorization parameter is null. The final receipt
comes only from `confirm_claim_absent_and_current_exact` under the still-active
bootstrap lease; there is no observation-free retirement CAS. Forged, stale,
reused, wrong-action, cross-thread, both-present, both-absent, or
cross-family carriers fail before observation, mutation, or session CAS.

The output-operation authorization, receipt, and release authorization are a
separate private Task-3 bearer family. Publication authorization is mintable
only from an active same-thread session lease and the exact persisted
`install_output_operation_admission/PREPARED|STAGING_BOUND` cursor. The closed
stage/action matrix permits materialize or unbound-staging retirement only from
`PREPARED` with `external_file_action=PLANNED`, and permits bound commit only
from `STAGING_BOUND` with its exact immutable staging identity. Every other
stage/action pair fails before the callback. Task 8's physical helper
executes one staging-materialize, unbound-staging-retire, or bound-commit
callback and returns one receipt for every action. The cleanup receipt may only
advance `unbound_staging_retired`, preserve `PLANNED`, record residue absent,
and select materialization. Only the materialize receipt may bind
`STAGING_BOUND`; only the following commit receipt may install complete final
evidence and `state=ACTIVE`. The release authorization is mintable only
from an exact persisted `RUNTIME_HANDOFF_RELEASE_AUTHORIZED` or
`TERMINAL_RELEASE_AUTHORIZED` session cursor. This low-level release mint is
module-private and validates only session authority; Task 8's terminal adapter
or Task 10's runtime-handoff adapter must first validate every external held
capability before delegating to it. The bearer authorizes only the verified
unlink, or exact already-absent confirmation, of that one bound record. No
extra CAS is required to record the unlink: the release-authorized cursor is
the durable proof that absence is legitimate. A terminal no-runtime path ends
there; later live-phase CASes preserve the release-authorized binding
byte-identically while the exact runtime admission remains durable. Task 8
passes that receipt-free callback only through
`_execute_output_operation_release()`, so invalid carriers fail before I/O.
The two
release states are mutually exclusive, and forged, copied, stale, cross-thread,
wrong-record, wrong-state, or reused bearers fail before observation or
mutation.

`RuntimeAdmissionAuthorization` and `RuntimeAdmissionStepReceipt` form another
disjoint private Task-3 family for the complete apply-start physical transition.
The mint accepts only the active same-thread session lease and exact
`install_apply_invocation/PREPARED|STAGING_BOUND|PRIMARY_APPLIED` cursor. It
binds exactly one admission or invocation-receipt materialize, unbound-staging
retirement, or bound-staging commit action. The Task-10 physical adapter passes its callback
only through `_execute_runtime_admission_physical_step()` while the profile,
output-operation, package/publication, and runtime pair remain active. The two
receipt CASes are exactly `unbound_staging_retired`, `staging_bound`,
`admission_primary_applied`, `invocation_receipt_unbound_staging_retired`,
`invocation_receipt_staging_bound`, and `invocation_receipt_committed`;
neither caller nor physical adapter may supply or reconstruct successor
evidence. Cross-use with output-operation, bootstrap, first-install, recovery,
or terminal carriers fails before observation or mutation.

```python
# published_apply.py
class PhysicalApplyDisposition(StrEnum):
    NOT_COMMITTED = "NOT_COMMITTED"
    COMMITTED = "COMMITTED"
    COMMITTED_RECOVERY_PENDING = "COMMITTED_RECOVERY_PENDING"
    UNKNOWN_REQUIRES_RECOVERY = "UNKNOWN_REQUIRES_RECOVERY"

@dataclass(frozen=True, slots=True)
class ApplyAndMatchPublishedResult:
    raw_apply_status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ] | None
    physical_disposition: PhysicalApplyDisposition
    runtime_match_status: Literal["not_run", "matched", "mismatch", "unknown"]
    runtime_match_sha256: str | None
    package_root_sha256: str | None
    last_apply_receipt_sha256: str | None
    runtime_state_sha256: str | None
    deck_config_ini_sha256: str | None
    retained_attempt_record_path: Path | None
    retained_attempt_record_identity: PathIdentity | None
    retained_attempt_record_sha256: str | None
    retained_journal_path: Path | None
    retained_journal_identity: PathIdentity | None
    retained_journal_sha256: str | None
    retained_target_owner_journal_path: Path | None
    retained_target_owner_journal_identity: PathIdentity | None
    retained_target_owner_journal_sha256: str | None
    runtime_admission_path: Path | None
    runtime_admission_parent_identity: PathIdentity | None
    runtime_admission_identity: PathIdentity | None
    runtime_admission_sha256: str | None
    terminal_status: Literal[
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    ]
    error_code: str | None

@dataclass(frozen=True, slots=True)
class RecoverApplyNotStarted:
    status: Literal["apply_not_started"]
    run_id: str
    session_root: Path
    session_root_identity: PathIdentity
    persisted_session_sha256: str
    runtime_write_performed: Literal[False]

RecoverApplyResult = ApplyAndMatchPublishedResult | RecoverApplyNotStarted

@dataclass(frozen=True, slots=True)
class AttemptAcknowledgementEvidence:
    apply_attempt_id: str
    retention_owner_run_id: str
    retention_fence_path: Path
    retention_fence_identity: PathIdentity
    retention_fence_sha256: str
    journal_path: Path
    journal_identity: PathIdentity
    journal_sha256: str
    target_owner_journal_path: Path
    target_owner_journal_identity: PathIdentity
    target_owner_journal_sha256: str
    target_path: Path
    target_identity: PathIdentity
    package_root_sha256: str
    runtime_admission_path: Path
    runtime_admission_parent_identity: PathIdentity
    runtime_admission_identity: PathIdentity
    runtime_admission_sha256: str
    journal_owns_target: bool
    acknowledgement_action: Literal[
        "retain_target_owner_delete_fence",
        "delete_nonowning_attempt_and_fence",
    ]

class HeldApplyAndMatchPublished:
    @property
    def updated_session(self) -> LiveStartSession: ...

    @property
    def invocation(self) -> ApplyInvocation: ...

    @property
    def result(self) -> ApplyAndMatchPublishedResult: ...

    @property
    def acknowledgement_evidence(
        self,
    ) -> AttemptAcknowledgementEvidence | None: ...

    @property
    def runtime_admission_evidence(
        self,
    ) -> RuntimeLiveAttemptAdmissionEvidence: ...

    def acknowledge_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession: ...

    def release_admission_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession: ...

    def resolve_and_release_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession: ...

@dataclass(frozen=True, slots=True)
class HeldRecoveredApplyAndMatch:
    held: HeldApplyAndMatchPublished

    @property
    def updated_session(self) -> LiveStartSession:
        return self.held.updated_session

@contextmanager
def apply_and_match_published(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    output_root: Path,
    publication_content_root_sha256: str,
    runtime_root: Path,
    apply_attempt_id: str,
) -> Iterator[HeldApplyAndMatchPublished]: ...

def recover_apply_attempt(
    *, session_root: Path
) -> RecoverApplyResult: ...

@contextmanager
def recover_apply_attempt_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    expected_session: LiveStartSession,
) -> Iterator[HeldRecoveredApplyAndMatch]: ...

def _authorize_nonterminal_runtime_recovery_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeAttemptRecoveryAuthorization: ...

def _observe_runtime_recovery_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observation_family: RuntimeObservationFamily,
    initial_install_plan: RuntimeInstallPlan | None = None,
) -> RuntimeObservationReceipt: ...

def _execute_invocation_receipt_step_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    action: Literal[
        "materialize_invocation_receipt_staging",
        "commit_bound_invocation_receipt",
        "retire_unbound_invocation_receipt_staging",
    ],
    admission_authorization: RuntimeAdmissionAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> RuntimeAdmissionStepReceipt: ...

def _complete_apply_started_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LiveStartSession: ...
```

The `published_apply.py` authorizer is an adapter, not a second bearer mint. It
first validates the active profile, output-operation, paired package/runtime
leases, invocation, admission, action-specific physical predecessor, and the
same persisted session cursor. It then calls Task 3's private
`_authorize_nonterminal_apply_recovery_under_lock()` with that exact cursor and
`expected_action`. It cannot mint `select_terminal_classification`; that edge is
authorized only by `_observe_runtime_recovery_from_context()`. The observation
adapter validates the same capabilities and cursor, mints a family-tagged
Task-3 observation bearer, and passes one read-only Task-9 pair callback through
the Task-3 executor. It returns only the resulting opaque receipt, never a
caller-selected literal or Evidence dataclass. Task-9 helpers issue receipts
only through the two private
Task-3 issuer functions after their one physical row succeeds. This dependency
direction lets Task 3 RED/GREEN real bearer issuance and receipt consumption
without importing Task 9 or Task 10; later tasks integrate the same production
seams rather than constructing dataclasses.

`initial_install_plan` is exact and non-null only for `first_install`; it must
equal the plan already derived under that same package/runtime pair. It is null
for all other families. `nonterminal_apply|terminal_resolution|
terminal_classification` derive their transaction and current recovery facts
only from `expected_session` plus the sealed invocation/admission.

The normal orchestration surface is also fixed. The installed skill calls
these functions; it does not import private compiler, publisher, or installer
helpers directly.

```python
# live_start_controller.py
@dataclass(frozen=True, slots=True)
class LiveStartRequest:
    deck_name: str
    deck_code: str
    preview_requested: bool

@dataclass(frozen=True, slots=True)
class LiveStartResult:
    status: LiveStartTerminalStatus
    run_root: Path | None
    summary: FrozenJsonDocument

@dataclass(frozen=True, slots=True)
class LiveStartPreparation:
    run_root: Path
    starter_context_path: Path
    candidate_revision: Literal[1, 2, 3]
    visible_limitations: tuple[str, ...]

def prepare_live_start(
    request: LiveStartRequest,
) -> LiveStartPreparation | LiveStartResult: ...
def validate_live_start_candidate(
    *, session_root: Path, draft_path: Path
) -> FrozenJsonDocument: ...
def validate_live_start_review(
    *, session_root: Path, draft_path: Path
) -> FrozenJsonDocument: ...
def finalize_live_start(*, session_root: Path) -> LiveStartResult: ...
def resume_live_start(*, session_root: Path) -> LiveStartResult: ...
```

The literal `...` above denotes signature-only planning notation. Production
implementations must contain complete bodies and no incomplete branches.

## Test and Commit Discipline

For every task:

1. Confirm `git status --short` contains only the currently assigned writer's
   files.
2. Add the named focused test first and run only its listed node IDs to capture
   the expected RED failure.
3. Implement the smallest production change that makes those nodes GREEN.
4. Run the listed adjacent existing nodes once.
5. Run Ruff only on the changed Python paths, then `git diff --check`.
6. Ask one independent read-only spec reviewer and one independent read-only
   quality/security reviewer to inspect the frozen diff.
7. Resolve every Critical or Important finding with a focused RED/GREEN case.
8. Revalidate the external signing baseline and its immutable approved
   fingerprints, preflight the fixed signing selector with the non-ref-changing
   probe below, stage only the task's owned files, and run
   `git diff --cached --check`. Commit with that explicit selector. Before any
   ledger append or next task, require `git verify-commit` success, `%G? == G`,
   and `%GF` exact membership in the approved set for the new exact OID.
9. Do not push until the final integration task.

Tasks 6 and 7 are one explicit atomic commit-sized exception because the real
renderer invokes strict validation and derivation replay before it can return a
new-authority package. Task 6 deliberately remains an uncommitted RED/partial
implementation checkpoint; Task 7 supplies the schema-aware validators, reruns
both tasks' focused nodes GREEN, receives one review over their combined diff,
and creates one signed commit for the complete unit.

---

## Execution Baseline Before Task 1

Run these commands before the first implementation edit:

```powershell
$ExpectedRepository = 'Teufelsboy/HSConfig'
$AllowedOriginUrls = @(
  'https://github.com/Teufelsboy/HSConfig.git',
  'git@github.com:Teufelsboy/HSConfig.git',
  'ssh://git@github.com/Teufelsboy/HSConfig.git'
)
$OriginFetchUrls = @(git remote get-url --all origin)
$OriginFetchUrlExit = $LASTEXITCODE
$OriginPushUrls = @(git remote get-url --push --all origin)
$OriginPushUrlExit = $LASTEXITCODE
if (
  $OriginFetchUrlExit -ne 0 -or
  $OriginPushUrlExit -ne 0 -or
  $OriginFetchUrls.Count -ne 1 -or
  $OriginPushUrls.Count -ne 1 -or
  $OriginFetchUrls[0] -cnotin $AllowedOriginUrls -or
  $OriginPushUrls[0] -cnotin $AllowedOriginUrls
) {
  throw 'origin is not exactly bound to Teufelsboy/HSConfig'
}
$ResolvedRepository = (
  gh repo view $ExpectedRepository --json nameWithOwner `
    --jq '.nameWithOwner'
).Trim()
if ($LASTEXITCODE -ne 0 -or $ResolvedRepository -cne $ExpectedRepository) {
  throw 'GitHub repository binding mismatch'
}
git fetch --all --prune --tags
git remote prune origin
git status --short --branch
git branch --show-current
git branch --format='%(refname:short)'
git rev-list --left-right --count origin/main...HEAD
git log -2 --show-signature --format=fuller
```

Require exact repository `Teufelsboy/HSConfig`, one canonical fetch URL, one
canonical push URL, branch `main`, exactly one local branch, a clean worktree
and index, good approved signatures on the design and plan commits, and no
unexpected remote commits. The expected starting relationship is `0 2`:
origin/main plus
the signed design and plan commits. If origin advances, rebase is forbidden;
stop, inspect, and integrate the upstream descendant without rewriting signed
history.

Create one external signing-baseline file at the absolute path named by
`HSCONFIG_SIGNING_BASELINE`. It is canonical UTF-8 JSON without BOM, CR, NUL,
duplicate keys, unknown fields, non-finite values, trailing whitespace, or a
final newline; its maximum size is 64 KiB. It has exactly:

```text
schema_version
base_oid
design_oid
plan_oid
expected_outgoing_oids
approved_signer_fingerprints
content_sha256
```

Schema version is 1. Base, design, plan, and outgoing entries use the fetched
repository's exact lowercase 40- or 64-hex object-ID width.
`expected_outgoing_oids` is an ordered unique list of 2 through 64 OIDs whose
first two entries are exactly design and plan; later entries are every signed
implementation or focused-fix commit in creation order. Base is not outgoing.
The fingerprint list is sorted and unique with 1 through 8 exact printable-
ASCII `%GF` values of 1 through 256 characters. `content_sha256` is the standard
self-digest over canonical bytes with that field excluded.

Initialize the ledger with the signed design and plan OIDs. After each signed
task or focused-fix commit, atomically append only that OID and recompute the
self-digest; never change or reorder base, design, plan, earlier outgoing OIDs,
or approved fingerprints. A signature that merely verifies does not approve a
new signer. Freeze this external file before each pre-push stack gate.

Before Task 1, run the complete bounded `SigningBaselineValidator` from Step
13.5 in validation-only mode against the current exact HEAD and capture
`approved_signer_fingerprints`. Verify the design and plan commits individually
with `git verify-commit`, `%G? == G`, and exact `%GF` membership. Choose exactly
one non-empty explicit selector from `git config --get user.signingkey` and bind
it as `$ApprovedSigningSelector` for the entire task stack. Before the first real
task commit, and again whenever the signing environment changes, run this
non-ref-changing probe:

```powershell
$SigningSelectors = @(git config --get-all user.signingkey)
if (
  $LASTEXITCODE -ne 0 -or
  $SigningSelectors.Count -ne 1 -or
  [string]::IsNullOrWhiteSpace($SigningSelectors[0])
) {
  throw 'exactly one configured signing selector is required'
}
$ApprovedSigningSelector = [string]$SigningSelectors[0]
$ProbeTree = (git rev-parse 'HEAD^{tree}').Trim()
if ($LASTEXITCODE -ne 0) {
  throw 'failed to resolve signing-probe tree'
}
$ProbeOid = (
  'HSConfig approved signing probe' |
    git -c "user.signingkey=$ApprovedSigningSelector" commit-tree -S $ProbeTree
).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ProbeOid)) {
  throw 'approved signing probe failed'
}
git verify-commit $ProbeOid
$ProbeStatus = (git show --no-patch --format='%G?' $ProbeOid).Trim()
$ProbeFingerprint = (git show --no-patch --format='%GF' $ProbeOid).Trim()
if (
  $LASTEXITCODE -ne 0 -or
  $ProbeStatus -cne 'G' -or
  $ProbeFingerprint -cnotin $ApprovedFingerprints
) {
  throw 'configured signer is not approved'
}
```

Every later commit command uses that explicit selector. Immediately after each
real commit, capture its exact OID, run the same `verify-commit`, `%G?`, and `%GF`
checks, and only then atomically append that OID to the external ledger and
revalidate the new canonical baseline. A failed or differently signed real
commit is never appended, pushed, amended, reset, or hidden by a later commit;
stop and require a separately authorized history-repair workflow. This plan's
no-rewrite route proceeds only because the probe and explicit selector prevent
that state before the ref-changing commit.

---

## Task 1: Add the One-Time Live Policy and Safe Output Binding

**Owned files**

- Create: `src/hsconfig/operator_profile.py`
- Create: `src/hsconfig/output_operation_admission.py`
- Create: `src/hsconfig/commands/live_policy.py`
- Create: `tests/test_operator_profile.py`
- Create: `tests/test_output_operation_admission.py`
- Create: `tests/test_live_policy_cli.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_cli_help.py`

### Step 1.1: Write the RED profile-contract matrix

Add these exact tests:

- `test_enable_writes_closed_canonical_profile_and_reloads_it`
- `test_disable_preserves_bound_roots_and_only_changes_live_flag`
- `test_normal_load_is_read_only_and_detects_self_digest_or_identity_drift`
- `test_profile_rejects_missing_overlapping_reparse_or_unsafe_roots`
- `test_profile_roots_are_disjoint_from_the_hsconfig_state_root`
- `test_enable_safely_creates_state_root_but_load_and_disable_never_create`
- `test_deck_output_binding_is_safe_stable_and_identity_bound`
- `test_enable_and_disable_require_absent_or_exact_predecessor_cas`
- `test_operator_profile_lease_is_active_nonforgeable_and_expires_on_exit`
- `test_profile_mutation_waits_for_active_live_authority_lease`
- `test_operator_profile_lease_missing_lock_is_read_only_failure`
- `test_operator_profile_lease_revalidation_detects_byte_identity_or_root_drift`
- `test_output_operation_admission_fixed_path_schema_and_observation_are_closed`
- `test_output_operation_admission_observation_is_read_only_and_never_bootstraps`
- `test_output_operation_admission_lease_is_thread_bound_and_expires`
- `test_runtime_mutation_gate_allows_only_absent_fixed_output_operation_family`
- `test_runtime_mutation_gate_rejects_final_staging_temp_malformed_or_replaced_surface`
- `test_profile_enable_bootstraps_fixed_operation_lock_before_profile_cas`
- `test_profile_mutations_reject_present_malformed_or_replaced_output_operation_admission`
- `test_profile_mutations_reject_output_operation_staging_or_reserved_temp_residue`
- `test_profile_mutation_lock_order_is_profile_then_output_operation`
- `test_absent_profile_enable_is_blocked_by_active_output_operation_admission`

The first test must assert the exact key set:

```python
assert set(document) == {
    "schema_version",
    "live_by_default",
    "runtime_root",
    "runtime_root_identity",
    "output_base_root",
    "output_base_root_identity",
    "content_sha256",
}
assert document["schema_version"] == 1
assert document["live_by_default"] is True
```

The read-only test records profile bytes, identity, and modification time,
calls `load_operator_profile()` and `revalidate_operator_profile()` twice, and
requires all three observations to remain byte-identical.

Run:

```powershell
python -B -m pytest `
  tests/test_operator_profile.py::test_enable_writes_closed_canonical_profile_and_reloads_it `
  tests/test_operator_profile.py::test_disable_preserves_bound_roots_and_only_changes_live_flag `
  tests/test_operator_profile.py::test_normal_load_is_read_only_and_detects_self_digest_or_identity_drift `
  tests/test_operator_profile.py::test_profile_rejects_missing_overlapping_reparse_or_unsafe_roots `
  tests/test_operator_profile.py::test_profile_roots_are_disjoint_from_the_hsconfig_state_root `
  tests/test_operator_profile.py::test_enable_safely_creates_state_root_but_load_and_disable_never_create `
  tests/test_operator_profile.py::test_deck_output_binding_is_safe_stable_and_identity_bound `
  tests/test_operator_profile.py::test_enable_and_disable_require_absent_or_exact_predecessor_cas `
  tests/test_operator_profile.py::test_operator_profile_lease_is_active_nonforgeable_and_expires_on_exit `
  tests/test_operator_profile.py::test_profile_mutation_waits_for_active_live_authority_lease `
  tests/test_operator_profile.py::test_operator_profile_lease_missing_lock_is_read_only_failure `
  tests/test_operator_profile.py::test_operator_profile_lease_revalidation_detects_byte_identity_or_root_drift `
  tests/test_output_operation_admission.py::test_output_operation_admission_fixed_path_schema_and_observation_are_closed `
  tests/test_output_operation_admission.py::test_output_operation_admission_observation_is_read_only_and_never_bootstraps `
  tests/test_output_operation_admission.py::test_output_operation_admission_lease_is_thread_bound_and_expires `
  tests/test_output_operation_admission.py::test_runtime_mutation_gate_allows_only_absent_fixed_output_operation_family `
  tests/test_output_operation_admission.py::test_runtime_mutation_gate_rejects_final_staging_temp_malformed_or_replaced_surface `
  tests/test_operator_profile.py::test_profile_enable_bootstraps_fixed_operation_lock_before_profile_cas `
  tests/test_operator_profile.py::test_profile_mutations_reject_present_malformed_or_replaced_output_operation_admission `
  tests/test_operator_profile.py::test_profile_mutations_reject_output_operation_staging_or_reserved_temp_residue `
  tests/test_operator_profile.py::test_profile_mutation_lock_order_is_profile_then_output_operation `
  tests/test_operator_profile.py::test_absent_profile_enable_is_blocked_by_active_output_operation_admission `
  -q -p no:cacheprovider
```

Expected RED: import failure for `hsconfig.operator_profile` or
`hsconfig.output_operation_admission`.

### Step 1.2: Implement the canonical profile

Use the fixed path `%LOCALAPPDATA%\HSConfig\operator-profile.json`. Require a
pre-existing, plain, non-reparse runtime root and output-base root. Reject
equal roots, either root containing the other, and either root overlapping the
canonical `%LOCALAPPDATA%\HSConfig` state root that owns the profile, runs, and
locks. Serialize identities as three-integer JSON lists and validate them back
to tuples with booleans rejected as integers.

The key constants must be explicit:

```python
OPERATOR_PROFILE_SCHEMA_VERSION = 1
OPERATOR_PROFILE_MAX_BYTES = 64 * 1024
OPERATOR_PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "live_by_default",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "content_sha256",
    }
)
```

Reuse `capture_plain_ancestor_guard`, `hold_plain_directory`, `path_identity`,
`require_plain_directory`, `require_same_identity_resolution`,
`secure_create_directory`, and `atomic_write_bytes`. Only explicit `enable`
may create the plain HSConfig state root under a held and identity-bound
`LOCALAPPDATA` parent for profile authority. Under its new or pre-existing
profile lock, enable may also create the plain `locks` child and fixed empty
output-operation lock before acquiring that lock and before profile CAS. The
only narrower exception is Task 8's neutral publisher-lock bootstrap, which may
converge those same plain lock surfaces and add one deterministic empty output-
bootstrap lock, but no profile or other state. `load` and `disable` never create
a parent, lock, or profile. The profile update lock is
`%LOCALAPPDATA%\HSConfig\operator-profile.lock`; normal reads do not rewrite
either file.

Profile writes are compare-and-set operations. Every enable, disable, or root
rebind first takes the profile lock and then the fixed output-operation lock.
Under those locks it rejects any present, malformed, replaced, or unsafe fixed
output-operation admission, staging file, or reserved temp before the profile
CAS, regardless of the old or requested roots. An absent-profile enable is
subject to the same global check;
the one profile cannot change while a crashed owning output operation still
depends on its sealed bytes. For enable,
`expected_predecessor_sha256=None` means the profile must be absent; an existing
profile requires its exact currently loaded standard digest. Disable always
requires that exact predecessor digest. Under the profile lock, reread bytes,
identity, and digest immediately before replacement. A missing, different, or
concurrently changed predecessor fails without a write. Idempotent enable with
the exact predecessor may return the existing profile only when roots,
identities, and `live_by_default=true` already match.

`lease_operator_profile()` acquires the pre-existing profile lock with
`create_if_missing=False`, then rereads and compares the exact profile path,
parent identity, identity, canonical bytes, self-digest, enabled flag, root paths, and root
identities to `expected_profile`. It mints one nonserializable
`OperatorProfileLockToken` only after that comparison and invalidates the token
on context exit. Lease-aware helpers verify object identity, active-context
state, and the originating thread; callers cannot construct, copy, reuse, or
cross threads with the capability. Profile mutations take the same lock, so an
enable, disable, or root rebind waits until the live or preview operation has
published and reached its durable terminal session state. Normal read-only
loads remain lock-free and never create state.

`revalidate_operator_profile_lease()` performs one bounded no-follow reread
while the lock remains held. It requires the active token, originating thread,
profile path, parent identity, file identity, canonical bytes and self-digest, enabled flag, root
paths, and both current root identities to equal `lease.profile`. It never
creates or rewrites the state root, lock, profile, runtime root, or output root.

Derive the deck child with the existing `slugify_deck_name()` and then enforce
one non-empty filesystem component, no reserved Windows name, no trailing dot
or space, and a 128-character bound. Capture either the existing plain child
identity or expected absence under the held output-base identity. Do not add a
deck hash to this visible child name.

### Step 1.3: Add `live-policy enable|disable`

Append the new parser after existing argument definitions so current
line-bound publishability pins do not move. The parser contract is:

```text
hsconfig live-policy enable --runtime-root ROOT --output-base-root ROOT
  (--expected-absent | --expected-predecessor-sha256 SHA256) --json
hsconfig live-policy disable --expected-predecessor-sha256 SHA256 --json
```

`enable` returns status `enabled`; `disable` returns status `disabled`. Both
return the canonical profile digest and bound roots. Neither returns raw
filesystem identity details unless `--json` is used. A missing profile on
disable fails closed and does not create one.

Add and run:

```powershell
python -B -m pytest `
  tests/test_live_policy_cli.py::test_enable_and_disable_round_trip_through_cli `
  tests/test_live_policy_cli.py::test_disable_never_creates_a_missing_profile `
  tests/test_live_policy_cli.py::test_profile_mutations_require_exact_predecessor_option `
  tests/test_cli_help.py::test_live_policy_help_exposes_only_explicit_profile_mutations `
  -q -p no:cacheprovider
```

Expected RED before the parser/dispatch edit: argparse rejects `live-policy`.

### Step 1.4: Verify and commit

Run the two focused groups above, plus these adjacent filesystem controls:

```powershell
python -B -m pytest `
  tests/test_atomic_io.py::test_atomic_write_optional_expected_parent_identity_rejects_substitution `
  tests/test_atomic_io.py::test_atomic_write_rejects_identity_changes_before_replace `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/operator_profile.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/commands/live_policy.py `
  src/hsconfig/cli_parser.py `
  src/hsconfig/cli.py `
  tests/test_operator_profile.py `
  tests/test_output_operation_admission.py `
  tests/test_live_policy_cli.py `
  tests/test_cli_help.py
git diff --check
```

Commit:

```powershell
git add -- `
  src/hsconfig/operator_profile.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/commands/live_policy.py `
  src/hsconfig/cli_parser.py `
  src/hsconfig/cli.py `
  tests/test_operator_profile.py `
  tests/test_output_operation_admission.py `
  tests/test_live_policy_cli.py `
  tests/test_cli_help.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: add explicit live operator policy"
```

---

## Task 2: Freeze All Compiler Inputs Once

**Owned files**

- Create: `src/hsconfig/input_snapshot_manifest.py`
- Create: `tests/test_input_snapshot_manifest.py`
- Modify: `src/hsconfig/package_request.py`
- Modify: `tests/test_package_request.py`
- Modify: `tests/helpers/audited_package_request.py`

### Step 2.1: Write the RED closed-schema tests

Add these exact tests:

- `test_input_snapshot_manifest_binds_exact_six_blob_projections`
- `test_snapshot_rejects_unknown_duplicate_oversized_or_wrong_typed_values`
- `test_snapshot_round_trip_binds_three_physical_input_envelopes`
- `test_snapshot_loader_observes_each_bound_input_once`
- `test_snapshot_accepts_a_fully_resolvable_uncatalogued_deck`
- `test_snapshot_rejects_an_unknown_card_before_candidate_generation`
- `test_pure_manifest_validation_needs_no_envelopes_or_local_roots`
- `test_physical_envelope_limits_cover_exact_blob_count_and_json_overhead`

The first test must require this order:

```python
assert [row.name for row in snapshot.blobs] == [
    "deck",
    "full_cards",
    "collectible_cards",
    "source_acquisition",
    "source_documents",
    "globalvalues_baseline",
]
```

The type matrix must explicitly reject `True` and `False` for `size_bytes`,
`record_count`, and every schema integer. Include boundary cases at 0,
134217728, 1000000, and their first invalid neighbors.

Run:

```powershell
python -B -m pytest `
  tests/test_input_snapshot_manifest.py::test_input_snapshot_manifest_binds_exact_six_blob_projections `
  tests/test_input_snapshot_manifest.py::test_snapshot_rejects_unknown_duplicate_oversized_or_wrong_typed_values `
  tests/test_input_snapshot_manifest.py::test_snapshot_round_trip_binds_three_physical_input_envelopes `
  tests/test_input_snapshot_manifest.py::test_snapshot_loader_observes_each_bound_input_once `
  tests/test_input_snapshot_manifest.py::test_snapshot_accepts_a_fully_resolvable_uncatalogued_deck `
  tests/test_input_snapshot_manifest.py::test_snapshot_rejects_an_unknown_card_before_candidate_generation `
  tests/test_input_snapshot_manifest.py::test_pure_manifest_validation_needs_no_envelopes_or_local_roots `
  tests/test_input_snapshot_manifest.py::test_physical_envelope_limits_cover_exact_blob_count_and_json_overhead `
  -q -p no:cacheprovider
```

Expected RED: import failure for `hsconfig.input_snapshot_manifest`.

### Step 2.2: Implement the sealed manifest and envelopes

Use these limits and field sets exactly:

```python
INPUT_SNAPSHOT_SCHEMA_VERSION = 1
INPUT_SNAPSHOT_MAX_BYTES = 256 * 1024
INPUT_BLOB_MAX_BYTES = 134_217_728
INPUT_BLOB_MAX_RECORDS = 1_000_000
INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES = 1_048_576
DECK_INPUT_ENVELOPE_MAX_BYTES = (
    INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
CARDS_INPUT_ENVELOPE_MAX_BYTES = (
    3 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
SOURCES_INPUT_ENVELOPE_MAX_BYTES = (
    2 * INPUT_BLOB_MAX_BYTES + INPUT_ENVELOPE_JSON_OVERHEAD_MAX_BYTES
)
INPUT_SNAPSHOT_FIELDS = frozenset(
    {"schema_version", "compiler_inputs", "operator_bindings", "content_sha256"}
)
COMPILER_INPUT_FIELDS = frozenset(
    {
        "deck_code_sha256",
        "roster_fingerprint",
        "bound_date",
        "blobs",
        "runtime_grammar_version",
        "compiler_contract_id",
    }
)
OPERATOR_BINDING_FIELDS = frozenset(
    {
        "operator_profile_sha256",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "deck_output_name",
        "deck_output_precondition",
    }
)
```

Build the normalized deck and all card/source/baseline projections from one
`PackageResolutionSnapshot`; do not make the manifest builder fetch or read a
runtime baseline. The caller supplies already captured bytes. Use
`StarterDocument` sealing for the manifest and `FrozenJsonDocument` for each
blob and envelope.

`validate_input_snapshot_manifest_document()` is the pure package-facing
validator. It checks exact fields, types, blob order, limits, nested bindings,
canonical bytes, and the self-digest without opening envelopes or rebinding a
local path. Package authority, strict validation, receipt replay, and apply
validation use this pure function. `load_frozen_compiler_inputs()` calls it and
then adds physical envelope checks plus operator-root rebinding for an external
run.

`load_frozen_compiler_inputs()` must:

1. read each physical file once with a bounded no-follow read using its exact
   envelope limit above;
2. validate the manifest self-digest and exact field closure;
3. validate the three envelope key sets;
4. recanonicalize and rehash every named blob;
5. compare size and record count;
6. rebind operator paths and identities without rewriting them;
7. return only immutable values.

The envelope-boundary test covers each exact maximum and first invalid byte,
including a cards envelope whose three individually valid blobs would exceed a
smaller two-blob estimate. Envelope overhead never weakens the per-blob or
record-count limits.

Add `frozen_compiler_inputs: FrozenCompilerInputs | None = None` to
`ResolvedPackageRequest`. Conservative and legacy optimized requests leave it
`None`; the new schema will require it in Task 5. Do not change current
`resolve_package_request()` behavior yet.

### Step 2.3: Prove no catalog dependency and no second observation

The uncatalogued-deck test must construct a real resolvable deck identity with
a name absent from the audited catalog. It must not monkeypatch the catalog to
pretend the deck exists. The loader-count test changes the upstream fixtures
after the first freeze and proves the loaded manifest and blob digests remain
unchanged.

Run adjacent controls:

```powershell
python -B -m pytest `
  tests/test_package_request.py::test_general_resolution_request_detaches_every_nested_mutable_input `
  tests/test_package_request.py::test_strict_resolution_context_defensively_copies_all_resource_bytes `
  tests/test_starter_context.py::test_shadowpriest_starter_context_closes_identity_cards_and_runtime_contract `
  -q -p no:cacheprovider
```

### Step 2.4: Verify and commit

```powershell
python -B -m ruff check `
  src/hsconfig/input_snapshot_manifest.py `
  src/hsconfig/package_request.py `
  tests/test_input_snapshot_manifest.py `
  tests/test_package_request.py `
  tests/helpers/audited_package_request.py
git diff --check
git add -- `
  src/hsconfig/input_snapshot_manifest.py `
  src/hsconfig/package_request.py `
  tests/test_input_snapshot_manifest.py `
  tests/test_package_request.py `
  tests/helpers/audited_package_request.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: freeze live start compiler inputs"
```

---

## Task 3: Add the Closed Resumable Session State Machine

**Owned files**

- Create: `src/hsconfig/live_start_session.py`
- Create: `tests/test_live_start_session.py`
- Modify: `src/hsconfig/atomic_io.py`
- Modify: `src/hsconfig/package_io.py`
- Modify: `tests/test_atomic_io.py`
- Modify: `tests/test_package_io.py`

### Step 3.1: Write RED phase and layout tests

Add these exact tests:

- `test_session_has_closed_layout_and_canonical_self_digest`
- `test_session_allows_only_the_declared_phase_transitions`
- `test_session_cas_rejects_stale_bytes_identity_or_digest`
- `test_candidate_revision_invalidates_candidate_review_and_downstream_receipts`
- `test_resume_stops_on_input_compiler_or_grammar_drift`
- `test_session_lock_lives_outside_the_closed_run_directory`
- `test_two_processes_cannot_commit_the_same_session_predecessor`
- `test_validation_receipts_have_exact_closed_phase_bound_schemas`
- `test_resume_revalidates_every_completed_phase_receipt`
- `test_candidate_revision_transition_table_is_closed_and_resume_deterministic`
- `test_preview_intent_is_boolean_immutable_and_resume_bound`
- `test_one_lease_threads_exact_session_cursor_through_every_terminal_cas`
- `test_session_lease_token_is_nonforgeable_thread_bound_and_expires_on_exit`
- `test_session_under_lock_helper_rejects_mixed_wrong_root_or_wrong_lock_token`
- `test_cross_thread_session_capability_fails_before_artifact_read_or_write`
- `test_shallow_copy_shares_bearer_and_expires_without_minting_authority`
- `test_session_embeds_result_intent_and_acknowledgement_status_matrix`
- `test_pending_transition_is_closed_self_digested_and_resumes_exact_physical_change`
- `test_external_file_action_staging_bound_matrix_is_closed`
- `test_unbound_authority_staging_is_delete_only_and_never_promoted`
- `test_unbound_staging_retirement_receipt_advances_cursor_before_retry`
- `test_atomic_materialize_staging_binds_identity_only_after_complete_flush`
- `test_atomic_bound_no_replace_commit_preserves_persisted_staging_identity`
- `test_atomic_bound_no_replace_commit_rejects_parent_or_staging_substitution`
- `test_atomic_bound_no_replace_posix_two_link_intermediate_converges`
- `test_no_replace_commit_is_parent_identity_bound_on_windows_and_posix`
- `test_no_replace_posix_hook_fires_after_exact_link_before_source_unlink`
- `test_atomic_bound_no_replace_maps_posix_link_before_unlink_fault`
- `test_no_replace_posix_hard_kill_after_link_resumes_bound_identity`
- `test_apply_start_capability_separates_admission_and_invocation_receipt_actions`
- `test_cleanup_pending_transition_binds_external_identity_inventory_states`
- `test_pending_transition_rejects_unknown_paths_mixed_artifacts_or_stale_predecessor`
- `test_output_child_binding_and_claim_state_matrix_is_closed`
- `test_output_child_bootstrap_transition_is_intent_first_and_operation_closed`
- `test_output_child_bootstrap_rejects_mixed_nullability_or_unknown_stage`
- `test_output_child_bootstrap_receipt_is_thread_cursor_action_and_single_use_bound`
- `test_output_child_bootstrap_rejects_constructed_stale_or_wrong_action_receipt`
- `test_output_operation_admission_binding_state_and_nullability_are_closed`
- `test_output_operation_admission_publish_is_intent_first_and_receipt_bound`
- `test_output_operation_authorization_stage_action_matrix_is_closed`
- `test_output_operation_release_requires_exact_persisted_authorized_cursor`
- `test_apply_started_atomically_authorizes_output_operation_runtime_handoff`
- `test_output_operation_release_needs_no_absence_recording_cas`
- `test_output_operation_bearers_are_nonforgeable_thread_bound_and_single_use`
- `test_output_child_claim_retirement_is_forbidden_before_publication_committed`
- `test_output_child_claim_retirement_preserves_historical_claim_binding`
- `test_output_claim_retired_requires_confirmation_receipt`
- `test_output_claim_retired_atomically_rebinds_publication_digest`
- `test_output_child_binding_is_immutable_through_admission_and_terminal`
- `test_result_intent_coverage_counts_are_jointly_nullable_until_valid_candidate`
- `test_result_intent_coverage_binds_exact_supported_frozen_roster_without_thirty_cap`
- `test_result_intent_runtime_admission_fields_are_jointly_closed`
- `test_session_runtime_admission_binding_is_jointly_closed`
- `test_attempt_acknowledgement_binds_attempt_record_and_surviving_target_owner`
- `test_attempt_acknowledgement_rejects_delete_owner_action_or_mixed_evidence`
- `test_result_intent_binds_attempt_journal_and_owner_path_identity_and_digest`
- `test_terminal_retirement_has_closed_recovery_evidence_and_release_authorized_stages`
- `test_terminal_resolution_evidence_has_closed_predecessor_successor_matrix`
- `test_terminal_resolution_cleanup_inventory_is_closed_bounded_and_cursor_bound`
- `test_terminal_cleanup_inventory_uses_planned_staging_bound_commit`
- `test_terminal_cleanup_inventory_same_outer_stage_accepts_only_receipt_bound_file_rollovers`
- `test_terminal_cleanup_inventory_retires_unbound_staging_without_promotion`
- `test_terminal_cleanup_inventory_rejects_direct_final_or_changed_bound_identity`
- `test_terminal_resolution_cleanup_has_exact_stage_nullability_and_physical_matrix`
- `test_terminal_resolution_cleanup_cas_allows_only_exact_cursor_successors`
- `test_terminal_resolution_cleanup_rejects_skipped_backward_stale_or_reused_authority`
- `test_terminal_resolution_advance_requires_matching_physical_step_receipt_or_pure_cas_authorization`
- `test_terminal_resolution_step_receipt_is_nonforgeable_thread_bound_and_single_use`
- `test_physical_recovery_receipt_privately_carries_exact_successor_evidence`
- `test_physical_recovery_rejects_caller_supplied_successor_with_receipt`
- `test_physical_executor_consumes_before_callback_and_validates_postcondition`
- `test_physical_executor_exception_spends_authorization_without_callback_retry`
- `test_success_ack_step_evidence_is_separate_nonpersisted_receipt_family`
- `test_crash_after_bound_physical_step_remints_receipt_only_for_exact_postcondition`
- `test_terminal_resolution_rejects_missing_stale_wrong_cursor_cross_action_or_reused_receipt`
- `test_terminal_retirement_advance_closes_ack_journal_and_pure_cas_edges`
- `test_apply_recovery_evidence_has_closed_cursor_and_nullability`
- `test_apply_recovery_temp_and_candidate_fields_are_jointly_closed`
- `test_legacy_uuid_transaction_temp_origin_path_classification_and_nullability_matrix_is_closed`
- `test_transaction_temp_origin_is_exactly_legacy_uuid_or_null`
- `test_controller_journal_unbound_staging_uses_only_external_file_action_retirement`
- `test_controller_journal_unbound_complete_bytes_are_deleted_never_promoted`
- `test_legacy_uuid_temp_cannot_alias_controller_external_file_action`
- `test_apply_recovery_candidate_create_or_confirm_action_matrix_is_closed`
- `test_candidate_identity_receipt_accepts_only_exact_action_postcondition`
- `test_candidate_create_and_candidate_fence_require_distinct_authorizations`
- `test_nonterminal_recovery_advance_requires_matching_receipt_or_pure_cas_authorization`
- `test_terminal_and_nonterminal_recovery_carriers_reject_cross_use`
- `test_apply_recovery_action_matrix_and_rollover_are_exhaustive`
- `test_terminal_classification_selection_is_pure_cas_and_increments_action_index_once`
- `test_terminal_classification_selection_preserves_all_physical_evidence`
- `test_terminal_classification_selection_requires_fresh_exact_single_use_observation_receipt`
- `test_terminal_classification_selection_rejects_missing_receipt_or_observe_committed`
- `test_terminal_classification_selection_rejects_stale_reused_cross_thread_and_stable_cursor`
- `test_terminal_classification_selection_cannot_select_twice`
- `test_runtime_observation_receipt_is_nonforgeable_thread_family_cursor_and_single_use`
- `test_runtime_observation_receipt_privately_binds_initial_evidence_or_selection`
- `test_runtime_observation_receipt_rejects_constructed_swapped_stale_cross_pair_or_reused_values`
- `test_initial_prepare_and_selection_cas_accept_only_matching_observation_receipt`
- `test_apply_recovery_pending_and_unknown_close_before_terminal_result`
- `test_recovery_stage_active_closed_matrix_is_closed`
- `test_recovery_closed_changes_stage_once_and_rejects_noop_or_repeat`
- `test_recovery_closed_retains_exact_closed_apply_recovery_until_result_intent_cas`
- `test_result_intent_cas_atomically_consumes_closed_apply_recovery`
- `test_result_intent_rejects_unclosed_stale_wrong_attempt_or_wrong_digest_recovery_cursor`
- `test_crash_after_recovery_closed_preserves_selected_terminal_classification`
- `test_private_recovery_mint_and_receipt_issuer_bind_real_session_bearer`
- `test_runtime_first_install_observation_receipt_prepares_exact_persisted_recovery_cursor`
- `test_normal_first_install_persists_apply_recovery_before_first_runtime_mutation`
- `test_normal_first_install_executes_exactly_one_physical_row_per_receipt_cas`
- `test_runtime_layout_bootstrap_schema_and_fixed_order_are_closed`
- `test_runtime_layout_bootstrap_create_or_confirm_is_one_receipt_cas_per_directory`
- `test_runtime_layout_bootstrap_crash_after_mkdir_before_cas_binds_only_exact_empty_child`
- `test_runtime_layout_bootstrap_rejects_parent_substitution_reparse_ads_nonempty_new_or_skip`
- `test_invocation_receipt_is_forbidden_until_runtime_layout_complete`
- `test_apply_recovery_new_target_action_graph_is_exhaustive_and_linear`
- `test_candidate_tree_copy_verify_rename_and_journal_rows_are_distinct`
- `test_new_target_ini_is_reachable_only_after_bound_renamed_target`
- `test_owner_retirement_evidence_action_and_nullability_matrix_is_closed`
- `test_owner_retirement_each_entry_delete_and_journal_advance_need_distinct_receipts`
- `test_owner_retirement_completed_precedes_old_owner_unlink`
- `test_owner_retirement_evidence_binds_target_parent_and_complete_manifest_commitment`
- `test_owner_retirement_initialize_cursor_zero_and_target_retired_stages_are_closed`
- `test_owner_retirement_initialize_delete_advance_root_and_completed_need_distinct_receipts`
- `test_owner_retirement_target_retired_precedes_completed_and_old_owner_unlink`
- `test_owner_retirement_binds_completed_tombstone_commitment_at_final_v1_cursor`
- `test_owner_root_receipt_installs_only_prebound_completed_tombstone_intent`
- `test_owner_root_crash_rejects_completed_tombstone_list_or_v1_substitution`
- `test_terminal_resolution_carries_partial_owner_retirement_until_owner_retired`
- `test_release_authorized_is_final_session_stage_before_physical_unlink`
- `test_runtime_admission_release_executor_consumes_before_callback_and_returns_no_receipt`
- `test_runtime_admission_release_executor_binds_path_parent_old_identity_and_digest`
- `test_runtime_admission_release_executor_rejects_forged_stale_reused_wrong_stage_and_cross_thread_before_callback`
- `test_runtime_admission_release_postcondition_nullability_is_closed`
- `test_terminal_retirement_authority_is_persisted_thread_bound_and_single_use`
- `test_atomic_session_cas_hard_exit_reconciles_reserved_temp_without_layout_residue`
- `test_reserved_atomic_temp_discards_partial_but_rejects_reparse_hardlink_ads_or_unknown_name`
- `test_session_and_result_atomic_temp_exceptions_are_exact_and_receipts_use_staging`

The pending-transition tests exercise every operation and stage, including a
hard exit before the primary change, after the primary change, between each
secondary removal class, and before the final phase CAS. The count-nullability
test covers joint null, mixed-null rejection, invented pre-authority counts,
exact integers after same-revision candidate validity, and every later status
row. The roster-bound test uses a fully resolvable supported frozen deck with
more than 30 unique physical main-deck CardIDs, rejects a substituted count of
30 and Boolean counts, and requires exact disposition/count parity.

The phase test uses this exact enum order:

```python
class LiveStartPhase(StrEnum):
    INPUT_FROZEN = "INPUT_FROZEN"
    CANDIDATE_DRAFTED = "CANDIDATE_DRAFTED"
    CANDIDATE_VALIDATED = "CANDIDATE_VALIDATED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    PACKAGE_VALIDATED = "PACKAGE_VALIDATED"
    PREPUBLICATION_CHECK_PASSED = "PREPUBLICATION_CHECK_PASSED"
    PUBLICATION_COMMITTED = "PUBLICATION_COMMITTED"
    APPLY_STARTED = "APPLY_STARTED"
    APPLY_COMMITTED = "APPLY_COMMITTED"
    RUNTIME_MATCHED = "RUNTIME_MATCHED"
```

Run:

```powershell
python -B -m pytest `
  tests/test_live_start_session.py::test_session_has_closed_layout_and_canonical_self_digest `
  tests/test_live_start_session.py::test_session_allows_only_the_declared_phase_transitions `
  tests/test_live_start_session.py::test_session_cas_rejects_stale_bytes_identity_or_digest `
  tests/test_live_start_session.py::test_candidate_revision_invalidates_candidate_review_and_downstream_receipts `
  tests/test_live_start_session.py::test_resume_stops_on_input_compiler_or_grammar_drift `
  tests/test_live_start_session.py::test_session_lock_lives_outside_the_closed_run_directory `
  tests/test_live_start_session.py::test_two_processes_cannot_commit_the_same_session_predecessor `
  tests/test_live_start_session.py::test_validation_receipts_have_exact_closed_phase_bound_schemas `
  tests/test_live_start_session.py::test_resume_revalidates_every_completed_phase_receipt `
  tests/test_live_start_session.py::test_candidate_revision_transition_table_is_closed_and_resume_deterministic `
  tests/test_live_start_session.py::test_preview_intent_is_boolean_immutable_and_resume_bound `
  tests/test_live_start_session.py::test_one_lease_threads_exact_session_cursor_through_every_terminal_cas `
  tests/test_live_start_session.py::test_session_lease_token_is_nonforgeable_thread_bound_and_expires_on_exit `
  tests/test_live_start_session.py::test_session_under_lock_helper_rejects_mixed_wrong_root_or_wrong_lock_token `
  tests/test_live_start_session.py::test_cross_thread_session_capability_fails_before_artifact_read_or_write `
  tests/test_live_start_session.py::test_shallow_copy_shares_bearer_and_expires_without_minting_authority `
  tests/test_live_start_session.py::test_session_embeds_result_intent_and_acknowledgement_status_matrix `
  tests/test_live_start_session.py::test_pending_transition_is_closed_self_digested_and_resumes_exact_physical_change `
  tests/test_live_start_session.py::test_external_file_action_staging_bound_matrix_is_closed `
  tests/test_live_start_session.py::test_unbound_authority_staging_is_delete_only_and_never_promoted `
  tests/test_live_start_session.py::test_unbound_staging_retirement_receipt_advances_cursor_before_retry `
  tests/test_atomic_io.py::test_atomic_materialize_staging_binds_identity_only_after_complete_flush `
  tests/test_atomic_io.py::test_atomic_bound_no_replace_commit_preserves_persisted_staging_identity `
  tests/test_atomic_io.py::test_atomic_bound_no_replace_commit_rejects_parent_or_staging_substitution `
  tests/test_atomic_io.py::test_atomic_bound_no_replace_posix_two_link_intermediate_converges `
  tests/test_package_io.py::test_no_replace_commit_is_parent_identity_bound_on_windows_and_posix `
  tests/test_package_io.py::test_no_replace_posix_hook_fires_after_exact_link_before_source_unlink `
  tests/test_atomic_io.py::test_atomic_bound_no_replace_maps_posix_link_before_unlink_fault `
  tests/test_package_io.py::test_no_replace_posix_hard_kill_after_link_resumes_bound_identity `
  tests/test_live_start_session.py::test_apply_start_capability_separates_admission_and_invocation_receipt_actions `
  tests/test_live_start_session.py::test_cleanup_pending_transition_binds_external_identity_inventory_states `
  tests/test_live_start_session.py::test_pending_transition_rejects_unknown_paths_mixed_artifacts_or_stale_predecessor `
  tests/test_live_start_session.py::test_output_child_binding_and_claim_state_matrix_is_closed `
  tests/test_live_start_session.py::test_output_child_bootstrap_transition_is_intent_first_and_operation_closed `
  tests/test_live_start_session.py::test_output_child_bootstrap_rejects_mixed_nullability_or_unknown_stage `
  tests/test_live_start_session.py::test_output_child_bootstrap_receipt_is_thread_cursor_action_and_single_use_bound `
  tests/test_live_start_session.py::test_output_child_bootstrap_rejects_constructed_stale_or_wrong_action_receipt `
  tests/test_live_start_session.py::test_output_operation_admission_binding_state_and_nullability_are_closed `
  tests/test_live_start_session.py::test_output_operation_admission_publish_is_intent_first_and_receipt_bound `
  tests/test_live_start_session.py::test_output_operation_authorization_stage_action_matrix_is_closed `
  tests/test_live_start_session.py::test_output_operation_release_requires_exact_persisted_authorized_cursor `
  tests/test_live_start_session.py::test_apply_started_atomically_authorizes_output_operation_runtime_handoff `
  tests/test_live_start_session.py::test_output_operation_release_needs_no_absence_recording_cas `
  tests/test_live_start_session.py::test_output_operation_bearers_are_nonforgeable_thread_bound_and_single_use `
  tests/test_live_start_session.py::test_output_child_claim_retirement_is_forbidden_before_publication_committed `
  tests/test_live_start_session.py::test_output_child_claim_retirement_preserves_historical_claim_binding `
  tests/test_live_start_session.py::test_output_claim_retired_requires_confirmation_receipt `
  tests/test_live_start_session.py::test_output_claim_retired_atomically_rebinds_publication_digest `
  tests/test_live_start_session.py::test_output_child_binding_is_immutable_through_admission_and_terminal `
  tests/test_live_start_session.py::test_result_intent_coverage_counts_are_jointly_nullable_until_valid_candidate `
  tests/test_live_start_session.py::test_result_intent_coverage_binds_exact_supported_frozen_roster_without_thirty_cap `
  tests/test_live_start_session.py::test_result_intent_runtime_admission_fields_are_jointly_closed `
  tests/test_live_start_session.py::test_session_runtime_admission_binding_is_jointly_closed `
  tests/test_live_start_session.py::test_attempt_acknowledgement_binds_attempt_record_and_surviving_target_owner `
  tests/test_live_start_session.py::test_attempt_acknowledgement_rejects_delete_owner_action_or_mixed_evidence `
  tests/test_live_start_session.py::test_result_intent_binds_attempt_journal_and_owner_path_identity_and_digest `
  tests/test_live_start_session.py::test_terminal_retirement_has_closed_recovery_evidence_and_release_authorized_stages `
  tests/test_live_start_session.py::test_terminal_resolution_evidence_has_closed_predecessor_successor_matrix `
  tests/test_live_start_session.py::test_terminal_resolution_cleanup_inventory_is_closed_bounded_and_cursor_bound `
  tests/test_live_start_session.py::test_terminal_cleanup_inventory_uses_planned_staging_bound_commit `
  tests/test_live_start_session.py::test_terminal_cleanup_inventory_same_outer_stage_accepts_only_receipt_bound_file_rollovers `
  tests/test_live_start_session.py::test_terminal_cleanup_inventory_retires_unbound_staging_without_promotion `
  tests/test_live_start_session.py::test_terminal_cleanup_inventory_rejects_direct_final_or_changed_bound_identity `
  tests/test_live_start_session.py::test_terminal_resolution_cleanup_has_exact_stage_nullability_and_physical_matrix `
  tests/test_live_start_session.py::test_terminal_resolution_cleanup_cas_allows_only_exact_cursor_successors `
  tests/test_live_start_session.py::test_terminal_resolution_cleanup_rejects_skipped_backward_stale_or_reused_authority `
  tests/test_live_start_session.py::test_terminal_resolution_advance_requires_matching_physical_step_receipt_or_pure_cas_authorization `
  tests/test_live_start_session.py::test_terminal_resolution_step_receipt_is_nonforgeable_thread_bound_and_single_use `
  tests/test_live_start_session.py::test_physical_recovery_receipt_privately_carries_exact_successor_evidence `
  tests/test_live_start_session.py::test_physical_recovery_rejects_caller_supplied_successor_with_receipt `
  tests/test_live_start_session.py::test_physical_executor_consumes_before_callback_and_validates_postcondition `
  tests/test_live_start_session.py::test_physical_executor_exception_spends_authorization_without_callback_retry `
  tests/test_live_start_session.py::test_success_ack_step_evidence_is_separate_nonpersisted_receipt_family `
  tests/test_live_start_session.py::test_crash_after_bound_physical_step_remints_receipt_only_for_exact_postcondition `
  tests/test_live_start_session.py::test_terminal_resolution_rejects_missing_stale_wrong_cursor_cross_action_or_reused_receipt `
  tests/test_live_start_session.py::test_terminal_retirement_advance_closes_ack_journal_and_pure_cas_edges `
  tests/test_live_start_session.py::test_apply_recovery_evidence_has_closed_cursor_and_nullability `
  tests/test_live_start_session.py::test_apply_recovery_temp_and_candidate_fields_are_jointly_closed `
  tests/test_live_start_session.py::test_legacy_uuid_transaction_temp_origin_path_classification_and_nullability_matrix_is_closed `
  tests/test_live_start_session.py::test_transaction_temp_origin_is_exactly_legacy_uuid_or_null `
  tests/test_live_start_session.py::test_controller_journal_unbound_staging_uses_only_external_file_action_retirement `
  tests/test_live_start_session.py::test_controller_journal_unbound_complete_bytes_are_deleted_never_promoted `
  tests/test_live_start_session.py::test_legacy_uuid_temp_cannot_alias_controller_external_file_action `
  tests/test_live_start_session.py::test_apply_recovery_candidate_create_or_confirm_action_matrix_is_closed `
  tests/test_live_start_session.py::test_candidate_identity_receipt_accepts_only_exact_action_postcondition `
  tests/test_live_start_session.py::test_candidate_create_and_candidate_fence_require_distinct_authorizations `
  tests/test_live_start_session.py::test_nonterminal_recovery_advance_requires_matching_receipt_or_pure_cas_authorization `
  tests/test_live_start_session.py::test_terminal_and_nonterminal_recovery_carriers_reject_cross_use `
  tests/test_live_start_session.py::test_apply_recovery_action_matrix_and_rollover_are_exhaustive `
  tests/test_live_start_session.py::test_terminal_classification_selection_is_pure_cas_and_increments_action_index_once `
  tests/test_live_start_session.py::test_terminal_classification_selection_preserves_all_physical_evidence `
  tests/test_live_start_session.py::test_terminal_classification_selection_requires_fresh_exact_single_use_observation_receipt `
  tests/test_live_start_session.py::test_terminal_classification_selection_rejects_missing_receipt_or_observe_committed `
  tests/test_live_start_session.py::test_terminal_classification_selection_rejects_stale_reused_cross_thread_and_stable_cursor `
  tests/test_live_start_session.py::test_terminal_classification_selection_cannot_select_twice `
  tests/test_live_start_session.py::test_runtime_observation_receipt_is_nonforgeable_thread_family_cursor_and_single_use `
  tests/test_live_start_session.py::test_runtime_observation_receipt_privately_binds_initial_evidence_or_selection `
  tests/test_live_start_session.py::test_runtime_observation_receipt_rejects_constructed_swapped_stale_cross_pair_or_reused_values `
  tests/test_live_start_session.py::test_initial_prepare_and_selection_cas_accept_only_matching_observation_receipt `
  tests/test_live_start_session.py::test_apply_recovery_pending_and_unknown_close_before_terminal_result `
  tests/test_live_start_session.py::test_recovery_stage_active_closed_matrix_is_closed `
  tests/test_live_start_session.py::test_recovery_closed_changes_stage_once_and_rejects_noop_or_repeat `
  tests/test_live_start_session.py::test_recovery_closed_retains_exact_closed_apply_recovery_until_result_intent_cas `
  tests/test_live_start_session.py::test_result_intent_cas_atomically_consumes_closed_apply_recovery `
  tests/test_live_start_session.py::test_result_intent_rejects_unclosed_stale_wrong_attempt_or_wrong_digest_recovery_cursor `
  tests/test_live_start_session.py::test_crash_after_recovery_closed_preserves_selected_terminal_classification `
  tests/test_live_start_session.py::test_private_recovery_mint_and_receipt_issuer_bind_real_session_bearer `
  tests/test_live_start_session.py::test_runtime_first_install_observation_receipt_prepares_exact_persisted_recovery_cursor `
  tests/test_live_start_session.py::test_normal_first_install_persists_apply_recovery_before_first_runtime_mutation `
  tests/test_live_start_session.py::test_normal_first_install_executes_exactly_one_physical_row_per_receipt_cas `
  tests/test_live_start_session.py::test_runtime_layout_bootstrap_schema_and_fixed_order_are_closed `
  tests/test_live_start_session.py::test_runtime_layout_bootstrap_create_or_confirm_is_one_receipt_cas_per_directory `
  tests/test_live_start_session.py::test_runtime_layout_bootstrap_crash_after_mkdir_before_cas_binds_only_exact_empty_child `
  tests/test_live_start_session.py::test_runtime_layout_bootstrap_rejects_parent_substitution_reparse_ads_nonempty_new_or_skip `
  tests/test_live_start_session.py::test_invocation_receipt_is_forbidden_until_runtime_layout_complete `
  tests/test_live_start_session.py::test_apply_recovery_new_target_action_graph_is_exhaustive_and_linear `
  tests/test_live_start_session.py::test_candidate_tree_copy_verify_rename_and_journal_rows_are_distinct `
  tests/test_live_start_session.py::test_new_target_ini_is_reachable_only_after_bound_renamed_target `
  tests/test_live_start_session.py::test_owner_retirement_evidence_action_and_nullability_matrix_is_closed `
  tests/test_live_start_session.py::test_owner_retirement_each_entry_delete_and_journal_advance_need_distinct_receipts `
  tests/test_live_start_session.py::test_owner_retirement_completed_precedes_old_owner_unlink `
  tests/test_live_start_session.py::test_owner_retirement_evidence_binds_target_parent_and_complete_manifest_commitment `
  tests/test_live_start_session.py::test_owner_retirement_initialize_cursor_zero_and_target_retired_stages_are_closed `
  tests/test_live_start_session.py::test_owner_retirement_initialize_delete_advance_root_and_completed_need_distinct_receipts `
  tests/test_live_start_session.py::test_owner_retirement_target_retired_precedes_completed_and_old_owner_unlink `
  tests/test_live_start_session.py::test_owner_retirement_binds_completed_tombstone_commitment_at_final_v1_cursor `
  tests/test_live_start_session.py::test_owner_root_receipt_installs_only_prebound_completed_tombstone_intent `
  tests/test_live_start_session.py::test_owner_root_crash_rejects_completed_tombstone_list_or_v1_substitution `
  tests/test_live_start_session.py::test_terminal_resolution_carries_partial_owner_retirement_until_owner_retired `
  tests/test_live_start_session.py::test_release_authorized_is_final_session_stage_before_physical_unlink `
  tests/test_live_start_session.py::test_runtime_admission_release_executor_consumes_before_callback_and_returns_no_receipt `
  tests/test_live_start_session.py::test_runtime_admission_release_executor_binds_path_parent_old_identity_and_digest `
  tests/test_live_start_session.py::test_runtime_admission_release_executor_rejects_forged_stale_reused_wrong_stage_and_cross_thread_before_callback `
  tests/test_live_start_session.py::test_runtime_admission_release_postcondition_nullability_is_closed `
  tests/test_live_start_session.py::test_terminal_retirement_authority_is_persisted_thread_bound_and_single_use `
  tests/test_live_start_session.py::test_atomic_session_cas_hard_exit_reconciles_reserved_temp_without_layout_residue `
  tests/test_atomic_io.py::test_reserved_atomic_temp_discards_partial_but_rejects_reparse_hardlink_ads_or_unknown_name `
  tests/test_live_start_session.py::test_session_and_result_atomic_temp_exceptions_are_exact_and_receipts_use_staging `
  -q -p no:cacheprovider
```

Expected RED: import failure for `hsconfig.live_start_session`.

### Step 3.2: Implement the session document and run layout

Use these exact outer and nested bounds:

```python
LIVE_START_SESSION_SCHEMA_VERSION = 1
LIVE_START_SESSION_MAX_BYTES = 256 * 1024
LIVE_START_RESULT_INTENT_SCHEMA_VERSION = 1
LIVE_START_RESULT_INTENT_MAX_BYTES = 64 * 1024
LIVE_START_RESULT_INTENT_KIND = "live_start_result_intent"
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_SCHEMA_VERSION = 1
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_MAX_BYTES = 32 * 1024
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND = (
    "live_start_attempt_acknowledgement"
)
LIVE_START_TERMINAL_RETIREMENT_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RETIREMENT_MAX_BYTES = 64 * 1024
LIVE_START_TERMINAL_RETIREMENT_KIND = "live_start_terminal_retirement"
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_MAX_BYTES = 64 * 1024
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_KIND = (
    "live_start_terminal_resolution_evidence"
)
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_MAX_BYTES = 64 * 1024
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_KIND = (
    "live_start_runtime_apply_recovery_evidence"
)
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_SCHEMA_VERSION = 1
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_MAX_BYTES = 32 * 1024
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_KIND = (
    "live_start_runtime_layout_bootstrap"
)
LIVE_START_OWNER_RETIREMENT_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_OWNER_RETIREMENT_EVIDENCE_MAX_BYTES = 64 * 1024
LIVE_START_OWNER_RETIREMENT_EVIDENCE_KIND = (
    "live_start_owner_retirement_evidence"
)
LIVE_START_EXTERNAL_FILE_ACTION_SCHEMA_VERSION = 1
LIVE_START_EXTERNAL_FILE_ACTION_MAX_BYTES = 32 * 1024
LIVE_START_EXTERNAL_FILE_ACTION_KIND = "live_start_external_file_action"
LIVE_START_PENDING_TRANSITION_SCHEMA_VERSION = 1
LIVE_START_PENDING_TRANSITION_MAX_BYTES = 64 * 1024
LIVE_START_PENDING_TRANSITION_KIND = "live_start_pending_transition"
LIVE_START_OUTPUT_CHILD_BINDING_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_CHILD_BINDING_MAX_BYTES = 32 * 1024
LIVE_START_OUTPUT_CHILD_BINDING_KIND = "live_start_output_child_binding"
LIVE_START_OUTPUT_CHILD_CLAIM_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES = 16 * 1024
LIVE_START_OUTPUT_CHILD_CLAIM_KIND = "live_start_output_child_claim"
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_MAX_BYTES = 32 * 1024
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_KIND = (
    "live_start_output_operation_admission_binding"
)
LIVE_START_CLEANUP_IDENTITY_INVENTORY_SCHEMA_VERSION = 1
LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES = 64 * 1024 * 1024
LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_ENTRIES = MAX_FILESYSTEM_NODES
LIVE_START_CLEANUP_IDENTITY_INVENTORY_KIND = (
    "live_start_prepublication_cleanup_identity_inventory"
)
LIVE_START_TERMINAL_CLEANUP_INVENTORY_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES = 64 * 1024 * 1024
LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES = MAX_FILESYSTEM_NODES
LIVE_START_TERMINAL_CLEANUP_INVENTORY_KIND = (
    "live_start_terminal_resolution_cleanup_inventory"
)
```

The session JSON has exactly:

```text
schema_version
run_id
deck_name
deck_code_sha256
preview_requested
phase
candidate_revision
revisions_used
input_snapshot_manifest_sha256
artifact_bindings
pending_transition
prepublication_work_binding
output_operation_admission_binding
output_child_binding
publication_binding
apply_invocation_sha256
runtime_admission_binding
runtime_layout_bootstrap
apply_recovery
result_intent
attempt_acknowledgement
terminal_retirement
terminal_status
content_sha256
```

The run root permits exactly these logical artifacts and no others:

```text
session.json
inputs/input_snapshot_manifest.json
inputs/deck.json
inputs/cards.json
inputs/sources.json
starter/starter_context.json
starter/starter_config_candidate.json
starter/starter_config_review.json
receipts/candidate_validation.json
receipts/review_validation.json
receipts/package_validation.json
receipts/prepublication_apply_check.json
receipts/apply_invocation.json
terminal-resolution-cleanup.json
result/summary.json
result/summary.md
```

These are the only durable logical artifacts. During one guarded controller
artifact write, the target directory may additionally contain only that
target's deterministic `<leaf>.staged` sibling and its inner
`.<leaf>.staged.live-start-atomic.tmp`. Both are accepted only by the persisted
`external_file_action` matrix and are never user artifacts. The special
`session.json` CAS may instead use only
`.session.json.live-start-atomic.tmp`, because the replaced session bytes are
the durable cursor itself. While `result_intent` is non-null and
`terminal_status` is null, the result directory may additionally contain only
`result/.summary.json.live-start-atomic.tmp` or
`result/.summary.md.live-start-atomic.tmp`, subject to the closed sequential
result matrix below. These two temps are non-authority, verified-delete-only
surfaces: they are never parsed, adopted, promoted, linked to final, or entered
in `artifact_bindings`. No receipt or other canonical artifact receives this
exception. No random UUID sibling, second reserved sibling, or other transient
name is allowed.

All validation receipt files are canonical, self-digested, run-ID-bound
documents. Their exact kind-specific fields are:

```text
candidate_validation:
  schema_version, receipt_kind, run_id, candidate_revision,
  starter_context_sha256, candidate_sha256, status, findings, content_sha256
review_validation:
  schema_version, receipt_kind, run_id, candidate_revision,
  starter_context_sha256, candidate_sha256, review_sha256, review_status,
  confidence, content_sha256
package_validation:
  schema_version, receipt_kind, run_id, input_snapshot_manifest_sha256,
  starter_context_sha256, candidate_sha256, candidate_revision, review_sha256,
  package_root_sha256, derivation_receipt_sha256, operator_summary_sha256,
  apply_gate_allowed, prepublication_work_root,
  prepublication_work_parent_path, prepublication_work_parent_identity,
  prepublication_work_root_identity, prepublication_work_tree_sha256,
  cleanup_manifest_sha256, cleanup_entry_count, content_sha256
```

`runtime_layout_bootstrap` is null before the runtime admission is committed,
is exact and incomplete while its directory cursor runs, and remains exact and
complete through `APPLY_STARTED`, `apply_recovery`, and terminalization. It is a
closed self-digested object with exactly:

```text
runtime_layout_bootstrap:
  schema_version, binding_kind, run_id, apply_attempt_id, runtime_root,
  runtime_root_identity, stage, next_directory_index, directory_count,
  directories, content_sha256
runtime_layout_directory:
  role, path, expected_parent_identity, predecessor_state,
  predecessor_identity, successor_identity
```

`stage` is `INCOMPLETE|COMPLETE`. The canonical role/path order is exactly
`custom_config`, `transactions`, `staging`, `receipts`,
`state_receipts`, `attempt_retention`, `owner_retirements`. The paths are
respectively `CustomConfig`, `.hsconfig/transactions`, `.hsconfig/staging`,
`.hsconfig/receipts`, `.hsconfig/receipts/<state-key>`,
`.hsconfig/attempt-retention`, and `.hsconfig/owner-retirements` beneath the
sealed runtime root. `.hsconfig` itself and `apply.lock` remain the narrow
lease-bootstrap surfaces. A child may be listed only after its parent is an
already sealed predecessor or an earlier exact successor. Existing predecessors
have exact identities; absent predecessors have null identities. Successor is
null until that row's receipt CAS and exact thereafter. `next_directory_index`
is the first null successor, or equals `directory_count` only at `COMPLETE`.
No aliases, optional rows, Boolean indices, duplicate paths, fourth state, or
identity recapture are allowed.

This cursor is deliberately not another `pending_transition.operation`.
`install_apply_invocation` remains durably `PRIMARY_APPLIED` with the exact
runtime admission present while the separate layout bearer advances. During
that interval the invocation-receipt `external_file_action` is null, and every
other pending operation is forbidden. The final directory receipt CAS both
marks the layout `COMPLETE` and installs the already planned invocation-receipt
file action, closing any unjournaled gap.

Preview and every run that never commits a runtime admission require
`runtime_layout_bootstrap=null`. A live run requires it non-null from its first
layout-intent CAS onward and `COMPLETE` before any invocation-receipt staging,
`APPLY_STARTED`, or `apply_recovery`. The complete object remains byte-identical
for result and resume validation; later directory contents may change only via
their separately authorized child actions, never by rebinding the parent.

`apply_recovery` is null through `APPLY_STARTED` only until the one
first-install preparation CAS. Both an uninterrupted install and a resumed
attempt then carry the same closed self-digested nonterminal cursor until
`recovery_closed`; there is no separate unjournaled ordinary installer path. It
has exactly:

```text
schema_version, recovery_kind, recovery_stage, run_id, apply_attempt_id,
apply_invocation_sha256, runtime_admission_path,
runtime_admission_parent_identity, runtime_admission_identity,
runtime_admission_sha256, package_root_sha256, runtime_root,
runtime_root_identity, install_route, action_index, expected_action,
predecessor_attempt_record_path, predecessor_attempt_record_identity,
predecessor_attempt_record_sha256, predecessor_journal_path,
predecessor_journal_identity, predecessor_journal_sha256,
predecessor_transaction_temp_path,
predecessor_transaction_temp_parent_identity,
predecessor_transaction_temp_identity, predecessor_transaction_temp_size,
predecessor_transaction_temp_sha256,
predecessor_transaction_temp_classification,
predecessor_transaction_temp_origin,
external_file_action,
predecessor_target_owner_journal_path,
predecessor_target_owner_journal_identity,
predecessor_target_owner_journal_sha256,
successor_attempt_record_path, successor_attempt_record_identity,
successor_attempt_record_sha256, successor_journal_path,
successor_journal_identity, successor_journal_sha256,
successor_transaction_temp_path,
successor_transaction_temp_parent_identity,
successor_transaction_temp_identity, successor_transaction_temp_size,
successor_transaction_temp_sha256,
successor_transaction_temp_classification,
successor_transaction_temp_origin,
planned_journal_successor_path, planned_journal_successor_parent_identity,
planned_journal_successor_phase, planned_journal_successor_size,
planned_journal_successor_sha256,
successor_target_owner_journal_path,
successor_target_owner_journal_identity,
successor_target_owner_journal_sha256, candidate_path,
candidate_parent_identity, predecessor_candidate_identity,
successor_candidate_identity, candidate_tree_manifest_sha256,
candidate_tree_entry_count, candidate_tree_cursor,
candidate_tree_next_relative_path, candidate_tree_next_kind,
candidate_tree_next_source_identity, candidate_tree_next_size,
candidate_tree_next_sha256, candidate_tree_next_parent_identity,
candidate_tree_next_successor_identity, candidate_tree_verified_sha256,
renamed_target_path, predecessor_renamed_target_identity,
successor_renamed_target_identity, owner_retirement,
last_apply_receipt_sha256,
runtime_state_sha256, deck_config_ini_sha256, runtime_match_status,
runtime_match_sha256, stable_physical_disposition, content_sha256
```

Every path/identity/digest triplet is jointly null or exact. `recovery_stage` is
exactly `ACTIVE|CLOSED`; every prepared and progressing cursor is `ACTIVE`.
`action_index` is a
non-Boolean bounded integer and increases by exactly one after each consumed
physical step receipt. `expected_action` is exactly one
`RuntimeApplyRecoveryAction` literal and becomes null only after one authorized
classification row establishes one of all four `PhysicalApplyDisposition`
values. Successor fields are null before an action and carry only that action's
immediate successor until its receipt CAS. That CAS increments `action_index`
by one, moves every immediate successor triplet to the corresponding
predecessor triplet, clears every old successor field, and binds exactly the
next table action or a null stable action. `stable_physical_disposition` is null
until exact `NOT_COMMITTED|COMMITTED|COMMITTED_RECOVERY_PENDING|
UNKNOWN_REQUIRES_RECOVERY` classification. The object is permitted only with a
nonterminal admitted attempt in
`APPLY_STARTED|APPLY_COMMITTED|RUNTIME_MATCHED`; it may enter
`RUNTIME_MATCHED` only through its own pure-CAS edge. `recovery_closed` requires
`recovery_stage=ACTIVE`, `expected_action=null`, stable disposition, final action
index, no successor fields, and `external_file_action=null`. It alone CASes
`recovery_stage=CLOSED`, changes the object/session self-digests, and preserves
every physical evidence field. `CLOSED` forbids every recovery action or second
closure. Only the immediately following result-intent CAS may consume and clear
it. Result files, acknowledgement, terminal retirement, and terminal status all
require it already cleared.

`select_terminal_classification` is the only pure-CAS edge that replaces a
persisted physical `expected_action`. Its opaque observation receipt binds that
current action, recovery digest/index, same pair/admission/session context, and
exactly one terminal observation. The successor remains `ACTIVE` and changes only
`action_index = predecessor + 1`, `expected_action`, and canonical self-digests;
all physical, nested cursor, snapshot, Candidate, owner, file-action, identity,
size, and digest fields remain byte-identical. Selection is forbidden from an
already selected observation, a stable disposition, or a `CLOSED` cursor. The
selected `observe_*` action then runs in a later iteration with its own fresh
physical bearer and receipt.

`install_route` is immutable and exactly `new_target|prior_owner`. It is derived
under the active pair before the initial recovery cursor from the deterministic
target path plus exact separate owner evidence. It selects the sole
route-planning attempt-record successor after `ACTIVE`; no post-crash
observation may switch routes. `prior_owner` requires the target and owner
triplets already exact in the initial cursor and forbids candidate-tree fields.
`new_target` requires the target absent and binds the package-tree manifest used
by the later candidate cursor.

The transaction-temp family is a compatibility surface for legacy UUID temps
only and is separately jointly null or exact. It never aliases the final
journal triplet or the controller `external_file_action` staging and inner-temp
paths. Path, parent/file identity, non-Boolean size, raw byte digest, origin, and
classification are jointly null or jointly exact. Origin is exactly
`legacy_uuid`, using only the existing bounded UUID grammar and
`legacy_complete_valid|legacy_redundant_equal|legacy_monotone_successor|
legacy_partial_invalid`. New controller journal creates and replacements use
only the generic final, `<final>.staged`, and
`.<staged-leaf>.live-start-atomic.tmp` paths bound by `external_file_action`;
they never create or recognize a separate controller transaction-temp family.
Multiple UUID temps, a UUID temp mixed with controller staging, unsafe
occupants, parent/path or identity replacement, ADS, reparse points, and hard
links block without mutation.

During one controller journal CAS the recovery evidence also binds the jointly
exact planned journal successor path, parent identity, allowed phase, byte
size, and digest. Those fields are exact only on a controller journal
`external_file_action` row and are null for observation, cleanup, and legacy
UUID promotion. The commitment is derived before the first write from the
sealed journal predecessor and closed allowed successor phase and remains
byte-identical through unbound-staging retirement, rematerialization, and bound
commit. Every fresh materialization canonically serializes the successor from
bound journal fields in memory and must reproduce that size/digest; it never
reconstructs bytes from residue. Before any controller
journal, fence, INI, state, receipt, or inventory create/replace, the same
evidence carries one exact `external_file_action`. Its materialize receipt
rolls only `PLANNED -> STAGING_BOUND`; the existing concrete action name then
means the identity-preserving commit from `STAGING_BOUND` to the declared final
successor. Unbound staging retirement is also one executor, one receipt, and
one CAS: the successor remains logically `PLANNED`, increments the action
index, records staging and inner-temp absent, and selects only the fresh
materialize action. A crash after unlink but before that CAS remints from the
old cursor, confirms the same permitted absence, issues the same cleanup
receipt, and never promotes or adopts residue.
`retire_unbound_file_action_staging` is the sole recovery alternate to a
persisted `materialize_file_action_staging` action. The private mint permits
that alternate only while the nested stage is `PLANNED`; its executor accepts
only verified residue removal or already-absent confirmation, and the receipt
CAS reinstalls `materialize_file_action_staging` as the sole next action. Every
other wrong-action substitution fails before its callback.
Candidate path and
parent are null outside the new-target planned row; predecessor/successor
identity follows the same one-action rollover rule as journal and temp facts.

The candidate-tree fields are jointly null outside `CANDIDATE_BOUND` through
the target-rename binding. They repeat a canonical bounded package-tree
manifest digest/count derived under the active package lease before the first
candidate entry. `candidate_tree_cursor` advances by exactly one after each
directory-create or content-confirmation receipt. The next-entry fields are jointly exact
only for that cursor and carry the source identity/size/digest, destination
relative path/kind, already-bound destination parent, and nullable successor
identity. A directory step creates or confirms one safe empty directory; a file
step copies and flushes one exact source file under the still-active package
lease or, after action-before-CAS, confirms an already present safe leaf solely
by exact manifest content. Candidate children are ephemeral content authority,
not durable identity authority: the current destination identity is a receipt
postcondition and is deliberately discarded after cursor rollover. A safe
same-byte replacement is therefore semantically equivalent; changed bytes,
kind, source/root/parent authority, an extra entry, hardlink, ADS, or reparse is
tamper. No callback copies two entries or updates a journal. After the full
cursor, `verify_candidate_tree` performs one bounded read-only snapshot against
the sealed manifest and binds `candidate_tree_verified_sha256`. The same full
manifest parity is reread inside `rename_candidate_to_target` immediately before
the move and again before `bind_renamed_target` commits target ownership. Only
then may a separate staged v1 action commit `RUNTIME_VERIFIED`. Rename is another
row: it moves or confirms exactly the verified Candidate-root identity to the
absent target, and its receipt binds `successor_renamed_target_identity`; a later
staged v1 commit records that target ownership. Partial trees, extra entries,
changed content/root/parent/source authority, skipped cursors, or a target
appearing before the rename action are tamper.

`owner_retirement` is jointly null unless the newly finalized successor owns a
different target and one authenticated stale owner must be retired. When
present it is a closed self-digested object with exactly:

```text
owner_retirement:
  schema_version, evidence_kind, stage, tombstone_path,
  tombstone_parent_identity, tombstone_identity, tombstone_sha256,
  retired_owner_transaction_id, initial_owner_journal_path,
  initial_owner_journal_identity, initial_owner_journal_sha256,
  current_owner_journal_identity, current_owner_journal_sha256,
  retired_target_path, retired_target_parent_identity,
  retired_target_identity, retired_target_tree_sha256,
  successor_transaction_id, successor_package_root_sha256,
  successor_owner_journal_path, successor_owner_journal_identity,
  successor_owner_journal_sha256, cleanup_manifest_sha256,
  cleanup_entry_count, cleanup_cursor, planned_completed_tombstone_size,
  planned_completed_tombstone_sha256, next_entry_relative_path,
  next_entry_kind, next_entry_identity, next_entry_parent_identity,
  next_entry_size, next_entry_sha256, old_owner_journal_retired,
  content_sha256
```

Stage is exactly `PREPARED_PLANNED|PREPARED|CLEANING|TARGET_RETIRED|
COMPLETED|OWNER_RETIRED`. The outer `external_file_action` is non-null only for
the planned/bound tombstone or old-v1-journal transition selected by the action
table; it never aliases the tombstone's permanent final identity. The initial
owner, target and parent, successor owner, immutable cleanup manifest/count, and
tombstone path/parent never change. `PREPARED_PLANNED` binds the full target-tree
commitment and planned canonical PREPARED-tombstone bytes before any cleanup
mutation. `PREPARED` binds the committed tombstone identity; that tombstone is
the durable carrier of the complete ordered identity-inclusive cleanup list and
starts at cursor zero. `CLEANING` begins only after a distinct initial old-v1
commit sets `cleanup_started=true,cursor=0`; thereafter it binds exactly one
current old-v1 identity and the one immutable next cleanup entry. Entry deletion
and the following old-v1 cursor commit are separate receipt/CAS rows.
The planned COMPLETED-tombstone size/digest are jointly null until the exact
old-v1 cleanup cursor first reaches count. For a zero-entry tree, the
`initialize_owner_cleanup_journal` receipt CAS derives and binds them from the
exact PREPARED tombstone plus its cursor-zero v1 successor. Otherwise the last
`advance_owner_cleanup_journal` receipt CAS derives and binds them from the same
PREPARED tombstone plus its final cursor successor. They remain exact through
every later stage and are copied unchanged into terminal-resolution handoff.
`TARGET_RETIRED` requires cursor equal to count, next-entry fields null, the
final old-v1 identity and both planned COMPLETED commitments exact, and the
exact empty target root receipt-bound absent. Its CAS installs the file intent
only from those already persisted values. `COMPLETED` requires the permanent completed tombstone successor
committed while that final old-v1 remains exact. `OWNER_RETIRED` alone permits
the old journal to be absent while the exact completed tombstone remains. No
monolithic cleanup loop, post-PREPARED live recapture, backward/skipped cursor,
changed cleanup entry, undeclared physical state, or ordinary deletion of the
completed tombstone is legal.

The runtime-metadata adjacency matrix is exhaustive for both nonterminal and
terminal exact-attempt metadata recovery; the separate terminal tree-cleanup
matrix remains authoritative for entry deletion. `confirm` below means a bounded reread of the declared
idempotent successor, not another mutation. Each row is exactly one authorized
action, one opaque family-specific receipt, and one session CAS:

| `expected_action` | Required predecessor | Sole physical action or confirmation | Immediate successor bound by receipt CAS |
| --- | --- | --- | --- |
| `retire_unbound_file_action_staging` | `PLANNED`; final predecessor; staging/temp residue | Verify removal/absence; never promote | New index/digest; still `PLANNED`; select materialize |
| `materialize_file_action_staging` | `PLANNED`; final exact/absent; residue absent; commit preselected | Flush canonical staging | `STAGING_BOUND`; bind staging; select preselected commit |
| `commit_bound_initial_attempt_record` | Bound staging; schema-2 final absent; planned `ACTIVE` | Commit/confirm bound final | Exact `ACTIVE`; install route-plan file intent |
| `commit_bound_candidate_planned_attempt_record` | Bound staging; predecessor `ACTIVE`; target absent | Commit candidate-route fence | Exact `CANDIDATE_PLANNED`; candidate/v1 plan bound |
| `commit_bound_prior_owner_planned_attempt_record` | Bound staging; predecessor `ACTIVE`; prior target/owner exact | Commit prior-owner route fence | Exact `PRIOR_OWNER_PLANNED`; v1 plan bound |
| `advance_controller_transaction_journal_write` | Bound v1 staging; final absent | Commit/confirm prebound v1 | Exact v1 `PREPARED`; next candidate/prior row |
| `advance_controller_transaction_journal_write` | Bound v1 staging; final `PREPARED`; tree complete | Commit/confirm prebound v1 | Exact v1 `RUNTIME_STAGED`; next verify |
| `advance_controller_transaction_journal_write` | Bound v1 staging; final `RUNTIME_STAGED`; tree verified | Commit/confirm prebound v1 | Exact v1 `RUNTIME_VERIFIED`; next rename |
| `promote_legacy_uuid_transaction_temp` | One exact valid legacy UUID temp and absent or exact older final | One guarded temp-to-final replace | Exact selected final; temp absent |
| `retire_legacy_uuid_transaction_temp` | Exact redundant or partial legacy UUID temp plus separately exact final/predecessor | One verified temp unlink | Final unchanged; temp absent |
| `bind_created_candidate` | Planned fence; exact v1; bound path/parent; identity null; absent or exact empty postcondition | Create or confirm one safe empty directory | Bind identity; select `bind_candidate_fence` |
| `bind_candidate_fence` | Planned fence; v1/candidate exact; fence staging bound | Commit fence identity | `CANDIDATE_BOUND`; path/parent/identity repeat; residue absent |
| `commit_bound_prior_owner_attempt_record` | Planned fence; exact v1, target, owner; staging bound | Commit schema-2 fence | Exact `PRIOR_OWNER_BOUND`; residue absent |
| `materialize_candidate_tree_entry` | Bound candidate; v1 `PREPARED`; next entry exact | Create/confirm one safe dir or content-exact file | Bind result; cursor +1; discard leaf identity; select next row |
| `verify_candidate_tree` | Full candidate cursor; exact candidate tree; v1 `RUNTIME_STAGED` | One bounded read-only manifest/tree verification | Bind verified tree digest; install v1 `RUNTIME_VERIFIED` file intent |
| `rename_candidate_to_target` | Verified candidate; v1 `RUNTIME_VERIFIED`; target absent | Rename/confirm exact candidate identity | Bind target; candidate absent; install v1 owner intent |
| `bind_renamed_target` | Exact renamed target; bound v1 staging with same `RUNTIME_VERIFIED` phase and owner fields | Commit v1 identity | Target identity exact; `owns_target=true`; residue absent |
| `write_deck_config_ini` | New target owned; v1 `RUNTIME_VERIFIED`; INI staging bound | Commit/confirm INI | Exact next INI identity/digest/mapping |
| `write_deck_config_ini` | `PRIOR_OWNER_BOUND`; v1 `PREPARED`; INI staging bound | Commit/confirm INI | Exact next INI identity/digest/mapping |
| `commit_ini_journal` | Exact intended INI/target and `STAGING_BOUND` v1 from `PREPARED|RUNTIME_STAGED|RUNTIME_VERIFIED` | Identity-preserving v1 commit | Exact v1 `INI_COMMITTED`; staging/temp absent |
| `write_runtime_state` | v1 `INI_COMMITTED`; intended INI; state staging bound | Commit state identity or confirm bound final | Selected-state identity/bytes/digest exact; residue absent |
| `commit_state_journal` | Exact state plus `STAGING_BOUND` v1 from `INI_COMMITTED` | Identity-preserving v1 commit | Exact v1 `STATE_COMMITTED`; staging/temp absent |
| `write_last_apply_receipt` | Exact state; v1 `STATE_COMMITTED`; receipt staging bound | Commit receipt identity or confirm bound final | Nonpending receipt identity/bytes/digest exact; residue absent |
| `finalize_journal` | Exact receipt plus `STAGING_BOUND` v1 from `STATE_COMMITTED` | Identity-preserving v1 commit | Exact v1 `FINALIZED`; staging/temp absent |
| `finalize_attempt_record` | v1 `FINALIZED`; matching candidate/prior fence staging bound | Commit fence identity | Fence `FINALIZED`; journal/owner evidence exact; residue absent |
| `commit_owner_retirement_prepared` | Planned retirement; owners/target exact; tombstone staging bound | Commit bound tombstone | `PREPARED`; full inventory; cursor zero; install cleanup-v1 intent |
| `initialize_owner_cleanup_journal` | `PREPARED`; old v1 not cleaning; initial v1 staging bound | Commit full-list v1 at cursor zero | `CLEANING`; cursor zero; zero-count binds completion; select entry/root |
| `delete_owner_cleanup_entry` | `CLEANING`; old v1, target, next entry exact | Delete/confirm only that entry | Cursor unchanged; bind absence; install cursor-successor intent |
| `advance_owner_cleanup_journal` | `CLEANING`; entry absent; bound monotone old-v1 staging | Commit/confirm old v1 | Cursor +1; at count bind completed commitment; select entry/root |
| `retire_owner_target_root` | `CLEANING`; full cursor/final v1/completed commitment; root empty or authorized absent | Remove/confirm bound root | `TARGET_RETIRED`; install only prebound completed intent |
| `commit_owner_retirement_completed` | `TARGET_RETIRED`; root absent; final old v1; tombstone staging bound | Commit tombstone | Permanent `COMPLETED`; old v1 exact; residue absent |
| `retire_old_owner_journal` | Exact `COMPLETED` tombstone and exact final old v1 | Unlink only old v1 or confirm authorized absence | `OWNER_RETIRED`; completed tombstone unchanged |
| `observe_owner_retirement_completed` | Exact permanent `COMPLETED|OWNER_RETIRED` tombstone and successor owner | Read-only confirmation | Stable owner succession; no mutation |
| `observe_committed` | Exact finalized fence/journal, INI, state, receipt, package, and parity | Read-only confirmation | Stable `COMMITTED` and exact match facts or a separately bound mismatch |
| `observe_not_committed` | A closed precommit/no-tree or precommit/tree row plus the shared same-attempt snapshot proof | Read-only confirmation | Stable `NOT_COMMITTED`; no runtime metadata mutation |
| `observe_pending` | Exact retained evidence proves commit is in progress but not yet safely classifiable | Read-only confirmation | Stable `COMMITTED_RECOVERY_PENDING`; no mutation |
| `observe_unknown` | Exact admission plus bounded contradictory or incomplete retained evidence | Read-only confirmation | Stable `UNKNOWN_REQUIRES_RECOVERY`; no mutation |

The separate pure-CAS selection matrix is equally exhaustive:

| Persisted physical predecessor | Pair-bound read-only classification | Selected successor | Sole CAS effect |
| --- | --- | --- | --- |
| Exact precommit predecessor; no idempotent successor or final INI; full no-commit proof | safe `NOT_COMMITTED` | `observe_not_committed` | index +1; only action/self-digests change |
| Exact retained evidence proves commit may still be in progress, but the current action cannot safely complete now | recovery pending | `observe_pending` | same pure-CAS rule |
| Bounded observation proves neither stable commit nor no-commit without adopting contradictory evidence | unknown | `observe_unknown` | same pure-CAS rule |
| Exact idempotent successor of the persisted action is visible | resume current action | no selection | remint that exact physical action and consume its normal receipt |
| Intended final INI successor is visible | commit threshold reached | `observe_not_committed` forbidden | finish the current INI receipt/CAS and continue only commit recovery |
| Current action is already `observe_*`, disposition is stable, or recovery is closed | invalid | no selection | no CAS |

A staging file alone is reconciled through its persisted `external_file_action`;
it is never silently treated as a final INI successor. Selection invokes no
additional Task-9 callback during the CAS and changes no physical evidence; its
opaque receipt already binds the immediately preceding pair observation. A
callback exception alone does not select a status.

The closure matrix is separate and exhaustive:

| Recovery predecessor | Session phase | Sole successor |
| --- | --- | --- |
| `ACTIVE`, stable, action/successors/file action null | Required apply/match phase reached | `CLOSED`; only stage and self-digests change |
| `ACTIVE` but unstable, action/file action non-null, or wrong phase | Any | Reject without CAS |
| `CLOSED` | Any | Reject every recovery transition and repeated closure |

Only result-intent binding consumes the exact `CLOSED` cursor. Stable
classification alone never satisfies that precondition.

For controller journal recovery, a token authorizes at most one generic
unbound-staging retirement, staging materialization, bound commit, or read-only
final confirmation. Every such step returns one opaque receipt, and exactly one
session CAS consumes it and increments the action index before another token
exists. A crash before the staging-binding CAS follows the generic delete-only
unbound-residue row; a crash after it follows the bound identity-preserving
commit row. A legacy UUID temp remains a separate compatibility row and cannot
satisfy any controller `external_file_action` precondition. No single token may
both remove residue and write or confirm the final journal.

`external_file_action.action_kind` preselects the exact action-specific commit
literal before materialization. The materialize receipt can select only that
literal; a generic file commit may not infer a fence, journal, INI, state,
receipt, inventory, or tombstone successor from observed bytes. The initial
`ACTIVE` commit atomically installs exactly one route-planning file intent. The
route commit installs exactly one v1 `PREPARED` intent. Each later file commit
installs only the next action named in the matrix. Candidate copy, candidate
verification, target rename, and their adjacent v1 commits are distinct rows.

`write_deck_config_ini` is legal on both closed continuations: the exact
new-target route after candidate verification, rename, and target-owner binding,
and the exact `PRIOR_OWNER_BOUND` route. An ordinary new-target precommit row
classifies `NOT_COMMITTED` only after the persisted, I/O-free
`select_terminal_classification -> observe_not_committed` edge proves that the
intended final INI successor is not visible; it is not the normal installation
rule. Pending and unknown use the same selection edge with their respective
pair-bound observation receipt. Phase skips and multi-row writes under one token are
invalid even when the broad schema-1 monotonic predicate would accept the final
bytes. A committed match rolls through pure session CAS
edges `apply_committed -> runtime_matched -> recovery_closed`; a committed
mismatch or committed-recovery-pending row uses `apply_committed ->
recovery_closed`; `NOT_COMMITTED` and `UNKNOWN_REQUIRES_RECOVERY` use
`recovery_closed` from their current legal phase. That edge retains the exact
recovery evidence with `recovery_stage=CLOSED` until result-intent binding
consumes it. Closing pending or unknown
does not authorize later physical mutation: any later progress uses only the
terminal-resolution authorization family while preserving the historical
result bytes.

The no-authority observer uses a new bounded, no-follow transaction-store
reader that returns finals plus exact controller-reserved and legacy-UUID temps
without promoting, replacing, or deleting anything. Existing
`load_runtime_transaction_journals()` is never called by that observer. A
controller temp is always raw-classified and retired by its own receipt/CAS
before a fresh canonical write token exists—even when its bytes equal the
planned successor or current final. Only that fresh uninterrupted writer may
commit newly serialized bytes. Legacy UUID compatibility uses only its two
separately typed rows. Foreign, substituted, mixed-origin, multiple, or
ambiguous temps stop without mutation.

The session embeds, rather than adds physical files for, these three exact
self-digested terminal objects:

```text
result_intent:
  schema_version, intent_kind, run_id, terminal_status, deck_name,
  candidate_revision, unique_main_deck_cards, configured_cards,
  deliberately_unconfigured_cards, review_confidence, visible_limitations,
  apply_attempt_id, publication_revision, publication_content_root_sha256,
  raw_apply_status, physical_disposition, runtime_match_status,
  runtime_match_sha256, package_root_sha256,
  last_apply_receipt_sha256, runtime_state_sha256, deck_config_ini_sha256,
  retained_attempt_record_path, retained_attempt_record_identity,
  retained_attempt_record_sha256, retained_journal_path,
  retained_journal_identity, retained_journal_sha256,
  retained_target_owner_journal_path, retained_target_owner_journal_identity,
  retained_target_owner_journal_sha256, runtime_admission_path,
  runtime_admission_parent_identity, runtime_admission_identity,
  runtime_admission_sha256, error_code, retained_safe_state, content_sha256
attempt_acknowledgement:
  schema_version, acknowledgement_kind, run_id, apply_attempt_id,
  retention_owner_run_id, retention_fence_path, retention_fence_identity,
  retention_fence_sha256, journal_path, journal_identity, journal_sha256,
  target_owner_journal_path, target_owner_journal_identity,
  target_owner_journal_sha256, target_path, target_identity,
  package_root_sha256, runtime_admission_path,
  runtime_admission_parent_identity, runtime_admission_identity,
  runtime_admission_sha256, journal_owns_target, acknowledgement_action,
  content_sha256
terminal_retirement:
  schema_version, retirement_kind, run_id, apply_attempt_id, operation, stage,
  source_terminal_session_sha256, result_intent_sha256,
  terminal_resolution_evidence, runtime_admission_path,
  runtime_admission_parent_identity, runtime_admission_identity,
  runtime_admission_sha256, retained_attempt_record_path,
  retained_attempt_record_identity, retained_attempt_record_sha256,
  retained_journal_path, retained_journal_identity, retained_journal_sha256,
  retained_target_owner_journal_path, retained_target_owner_journal_identity,
  retained_target_owner_journal_sha256, content_sha256
terminal_resolution_evidence:
  schema_version, resolution_kind, run_id, apply_attempt_id,
  predecessor_attempt_record_path, predecessor_attempt_record_identity,
  predecessor_attempt_record_sha256, predecessor_journal_path,
  predecessor_journal_identity, predecessor_journal_sha256,
  predecessor_transaction_temp_path,
  predecessor_transaction_temp_parent_identity,
  predecessor_transaction_temp_identity, predecessor_transaction_temp_size,
  predecessor_transaction_temp_sha256,
  predecessor_transaction_temp_classification,
  predecessor_transaction_temp_origin,
  external_file_action, owner_retirement,
  predecessor_target_owner_journal_path,
  predecessor_target_owner_journal_identity,
  predecessor_target_owner_journal_sha256,
  allowed_attempt_record_successor_state, allowed_journal_successor_phase,
  successor_attempt_record_path, successor_attempt_record_identity,
  successor_attempt_record_sha256, successor_journal_path,
  successor_journal_identity, successor_journal_sha256,
  successor_transaction_temp_path,
  successor_transaction_temp_parent_identity,
  successor_transaction_temp_identity, successor_transaction_temp_size,
  successor_transaction_temp_sha256,
  successor_transaction_temp_classification,
  successor_transaction_temp_origin,
  planned_journal_successor_path, planned_journal_successor_parent_identity,
  planned_journal_successor_phase, planned_journal_successor_size,
  planned_journal_successor_sha256,
  successor_target_owner_journal_path,
  successor_target_owner_journal_identity,
  successor_target_owner_journal_sha256, candidate_path,
  candidate_parent_identity, predecessor_candidate_identity,
  successor_candidate_identity, resolved_physical_disposition,
  cleanup_stage, cleanup_inventory_path,
  cleanup_inventory_parent_identity, cleanup_inventory_identity,
  cleanup_inventory_size, cleanup_inventory_sha256,
  cleanup_manifest_sha256, cleanup_entry_count, cleanup_cursor, cleanup_roots,
  package_root_sha256, last_apply_receipt_sha256, runtime_state_sha256,
  deck_config_ini_sha256, runtime_match_status, runtime_match_sha256,
  content_sha256
pending_transition:
  schema_version, transition_kind, run_id, operation, stage,
  expected_session_sha256, source_phase, target_phase,
  source_candidate_revision, target_candidate_revision,
  source_revisions_used, target_revisions_used,
  successor_artifact_bindings, actions, next_action_index,
  external_file_action,
  rendered_model_sha256, work_parent_path, work_parent_identity,
  work_root, work_root_identity, work_tree_sha256,
  cleanup_manifest_sha256, cleanup_entry_count, cleanup_inventory_path,
  cleanup_inventory_identity, cleanup_inventory_size,
  cleanup_inventory_sha256, quarantine_path, cleanup_parent_identity,
  quarantine_identity, cleanup_cursor, apply_attempt_id,
  apply_invocation_sha256, apply_invocation_document_size,
  runtime_admission_document_size,
  runtime_admission_document_sha256,
  runtime_admission_path, runtime_admission_staging_path,
  runtime_admission_staging_inner_temp_path,
  runtime_admission_staging_identity, runtime_admission_staging_size,
  runtime_admission_staging_sha256,
  runtime_admission_parent_identity,
  runtime_admission_identity,
  runtime_admission_sha256, output_base_path, output_base_identity,
  output_operation_admission_path,
  output_operation_admission_staging_path,
  output_operation_admission_staging_inner_temp_path,
  output_operation_admission_staging_identity,
  output_operation_admission_staging_size,
  output_operation_admission_staging_sha256,
  output_operation_admission_parent_identity,
  output_operation_admission_planned_size,
  output_operation_admission_planned_sha256,
  output_operation_admission_identity,
  output_operation_admission_sha256,
  output_child_path, output_child_predecessor_state,
  output_child_predecessor_identity,
  planned_output_claim_size, planned_output_claim_sha256, output_claim_path,
  output_claim_staging_path, output_claim_staging_inner_temp_path,
  output_claim_parent_identity, output_claim_staging_identity,
  output_claim_staging_size, output_claim_staging_sha256,
  output_claim_identity, output_claim_sha256,
  created_or_confirmed_output_child_identity, output_bootstrap_lock_path,
  output_bootstrap_lock_identity, content_sha256
runtime_admission_binding:
  admission_path, admission_parent_identity, admission_identity,
  admission_sha256, output_operation_admission_path,
  output_operation_admission_identity, output_operation_admission_sha256,
  output_child_binding_sha256, output_child_path,
  output_child_identity, publication_revision,
  publication_content_root_sha256
output_operation_admission_binding:
  schema_version, binding_kind, state, release_handoff_kind, admission_path,
  admission_parent_identity, admission_identity, admission_size,
  admission_sha256, run_id, session_root, session_root_identity,
  expected_session_sha256, operator_profile_path,
  operator_profile_parent_identity, operator_profile_identity,
  operator_profile_sha256, state_root_identity, output_base_root,
  output_base_root_identity, output_child_path,
  output_child_predecessor_state, output_child_predecessor_identity,
  output_bootstrap_lock_path, output_bootstrap_lock_identity,
  output_claim_path, handoff_runtime_admission_path,
  handoff_runtime_admission_parent_identity,
  handoff_runtime_admission_identity, handoff_runtime_admission_sha256,
  content_sha256
prepublication_work_binding:
  work_parent_path, work_parent_identity, work_root, work_root_identity,
  work_tree_sha256,
  cleanup_manifest_sha256, cleanup_entry_count
output_child_binding:
  schema_version, binding_kind, run_id, output_base_path,
  output_base_identity, output_child_path, output_child_identity,
  predecessor_state, predecessor_output_child_identity, claim_path,
  claim_parent_identity, claim_identity, claim_sha256, claim_state,
  content_sha256
cleanup_identity_inventory:
  schema_version, inventory_kind, run_id, work_parent_path,
  work_parent_identity, work_root, work_root_identity, work_tree_sha256,
  cleanup_manifest_sha256, cleanup_entry_count,
  cleanup_parent_path, cleanup_parent_identity, quarantine_path, entries,
  content_sha256
cleanup_identity_inventory_entry:
  relative_path, entry_kind, identity, expected_parent_identity, size, sha256
terminal_resolution_cleanup_inventory:
  schema_version, inventory_kind, run_id, apply_attempt_id,
  runtime_root_path, runtime_root_identity, cleanup_roots,
  cleanup_manifest_sha256, cleanup_entry_count, entries, content_sha256
terminal_resolution_cleanup_root:
  root_role, source_path, source_identity, expected_parent_identity
terminal_resolution_cleanup_inventory_entry:
  root_role, relative_path, entry_kind, identity,
  expected_parent_identity, size, sha256
external_file_action:
  schema_version, action_kind, action_index, stage, final_path, staging_path,
  inner_temp_path, parent_identity, predecessor_state, predecessor_identity,
  predecessor_size, predecessor_sha256, planned_successor_size,
  planned_successor_sha256, staging_identity, staging_size, staging_sha256,
  commit_mode, content_sha256
```

`terminal_resolution_evidence.owner_retirement` is jointly null or an exact
copy of the current nonterminal owner-retirement cursor. It is null on every
branch without a stale owned target. If an incomplete owner retirement is
terminalized as recovery-pending or unknown, the exact nested object is carried
unchanged into `RECOVERY_PREPARED` and may advance only through the same
action/receipt successors as the nonterminal graph. `RECOVERY_STABILIZED`
requires `owner_retirement.stage=OWNER_RETIRED`, the permanent completed
tombstone exact, the old owner journal absent, the successor owner exact, and no
open external file action. Result intent and historical terminal bytes remain
unchanged during that physical resolution.

Schema version is 1. Candidate validation is durable only with `status=valid`
and an empty findings list. Review validation is durable only for an approved
review and `high|limited` confidence. Package validation is durable only when
strict validation, derivation replay, operator-summary parity, and recomputed
apply facts all passed and `apply_gate_allowed=true`. All SHA values use the
standard prefixed grammar. Each phase transition uses the pending-transition
protocol below before its first physical artifact write or removal. Resume
verifies every prior receipt and completes or safely rolls back that exact
transition before it continues at the first incomplete phase.

The session work binding's prepublication root is one canonical absolute path
under the dedicated local state `work` root. It binds both that fixed parent
path/identity and the child-root identity as exactly three non-Boolean integers.
The package receipt repeats that same parent-and-child binding on success;
neither document may name another tree. It exists so resume can reopen the exact
already-materialized package without recapturing a replaced parent or rebuilding
authority at a new path. The
nested acknowledgement object may separately persist one retained-journal
identity plus its controller fence and exact ownership disposition. The nested
terminal-retirement object is the only durable authorization for a physical
post-terminal action. Neither object reclassifies target ownership.

The cleanup identity inventory is a separate external sidecar, not another run
artifact or authority for what should exist. Its kind is exactly
`live_start_prepublication_cleanup_identity_inventory`; it is canonical,
self-digested, at most 64 MiB, and contains at most `MAX_FILESYSTEM_NODES`
rows. Its entries equal the logical cleanup manifest path-for-path, type-for-
type, size-for-size, and digest-for-digest. They are ordered by descending path
depth and then UTF-8 path bytes, with the work-root row `relative_path="."`
last. Entry kind is `file|directory`; every identity and expected parent
identity is exactly three non-Boolean integers. A file has a non-Boolean size
and standard digest; a directory has both fields null. Inner rows bind the
identity of their actual parent at the one physical snapshot. The root row
binds `work_root_identity`; before quarantine its source authority is the
persisted `work_parent_identity`, and after quarantine its exact delete parent
is the separately bound cleanup-parent identity. Both parents remain explicit;
neither is recaptured on resume.
Unknown or duplicate fields, path aliases, reparse points, hard links,
alternate streams, count mismatch, and every bound overflow fail closed.
The document's `content_sha256` is its self-digest with that field excluded;
the pending transition's `cleanup_inventory_sha256` is the distinct byte digest
of the complete canonical sidecar including `content_sha256`, and
`cleanup_inventory_size` is that same complete byte length.

The terminal-resolution cleanup inventory is a distinct conditional run
artifact, not a second statement of desired runtime content. It exists only for
a `release_resolved_terminal` no-commit cleanup. It is absent for every other
operation and before that cleanup is durably prepared. The inventory is
canonical, self-digested, bounded by the terminal-cleanup constants, and binds
the exact runtime-root path and identity. `cleanup_roots` is an ordered unique
zero-to-two-row list with roles `candidate|target`; each row binds the canonical
source path, source identity, and exact source-parent identity. Its entries are
ordered by root role, descending path depth, and UTF-8 path bytes, with each
root row last. Every entry repeats its root role and binds relative path,
`file|directory`, object identity, actual parent identity, and nullable size and
digest exactly as the prepublication inventory does. Unknown roles, aliases,
duplicates, unsafe nodes, count mismatch, or a row outside its bound root fail
closed. `cleanup_manifest_sha256` binds the canonical ordered logical cleanup
rows; the session separately binds the complete sidecar byte size, byte digest,
file identity, entry count, and monotone cursor.

`terminal-resolution-cleanup.json`, its deterministic `.staged` sibling, and the
staging file's deterministic inner temp are the only conditional additions to
the closed run layout. Staging and inner temp are allowed only while the exact
persisted `external_file_action` below requires them; the final sidecar is
allowed only through its cleanup-retirement stages. It is securely removed at
the prescribed boundary. Absence at any other stage and every other run-root
child remain invalid.

`external_file_action` is null when no controller authority-file action is in
flight. Otherwise it is one canonical, self-digested, operation-closed record
for exactly one file. `action_kind` is one literal from the owning transition's
closed action table; `action_index` equals that table's current cursor. Stage is
exactly `PLANNED|STAGING_BOUND`. Final, staging, inner-temp, parent, predecessor,
planned size/digest, and `commit_mode=create_no_replace|replace_exact` are exact
at both stages. `predecessor_state=absent` requires its identity/size/digest
jointly null; `predecessor_state=exact` requires all three exact. `PLANNED`
requires staging identity/size/digest jointly null. `STAGING_BOUND` requires
them jointly exact, equal to the planned bytes, and immutable. The three paths
are deterministic distinct direct children of the same bound parent. Unknown
fields, aliases, another temp, a wrong-parent path, Boolean integer, unsafe
node, or a second in-flight file action fails closed.

The exact matrix is universal. At `PLANNED`, final remains the sealed
predecessor or absent. Inner-temp/staging residue is delete-only under a fresh
owning executor; its receipt CAS records both absent, increments the action
index, and selects materialization while remaining logically `PLANNED`. It is
never a forward file successor. One uninterrupted materialization produces exact staging,
no inner temp, and one receipt; that receipt alone CASes `STAGING_BOUND`. At
`STAGING_BOUND`, the only legal rows are bound staging alone, final alone with
the same bound identity, or the POSIX two-link intermediate with final and
staging equal to that identity and total link count two. The commit executor
converges to final-only with that same identity and no temp, and its receipt
alone advances the owning cursor. It clears `external_file_action` unless the
closed action table atomically installs the next independently preplanned file
action; only the runtime-admission commit does so for the invocation receipt.
Different
identities, direct final creation from `PLANNED`, same-byte replacement after
binding, disappearance of both bound names, or any extra surface is tamper.
The prepublication and terminal cleanup inventories, journal/fence updates,
INI, state, and receipts use this same nested record rather than inventing
parallel staging contracts.

Both cleanup-inventory families keep `external_file_action` non-null from their
first persisted inventory intent through the identity-preserving final commit.
Their only three file surfaces are `<inventory-final>`,
`<inventory-final>.staged`, and
`.<inventory-final>.staged.live-start-atomic.tmp`. Direct final creation from
`PLANNED`, a separate `.<inventory-leaf>.live-start-atomic.tmp`, or first capture
of an identity observed only at the final path is invalid. `PLANNED` binds exact
paths, parent, create-no-replace mode, absence, planned bytes, size, and digest,
with a null staging triplet; `STAGING_BOUND` carries the immutable staging
triplet; successful commit copies that exact identity into the inventory's final
triplet and clears the nested action only after staging and inner temp are
absent.

`pending_transition` is null outside one physical transition. Its schema
version is 1, its canonical maximum is 64 KiB, and its operation is exactly one
of `install_candidate`, `install_candidate_validation`, `install_review`,
`install_review_validation`, `materialize_prepublication_work`,
`install_package_validation`, `install_prepublication_validation`,
`install_output_operation_admission`,
`bootstrap_output_child`, `retire_output_child_claim`,
`install_apply_invocation`, or
`cleanup_prepublication`. Stage is `PREPARED`, `STAGING_BOUND`,
`PRIMARY_APPLIED`, or `CLEANUP_DELETING`. Outer `STAGING_BOUND` is valid only
for an operation whose primary external-file action is bound at that stage.
After the primary action reaches `PRIMARY_APPLIED`, a nested receipt or
inventory `external_file_action` may independently be `PLANNED` or
`STAGING_BOUND` while the outer stage remains `PRIMARY_APPLIED`; its own receipt
CAS advances only the nested action and session self-digest.
Each action has exactly logical path,
`create|replace|remove|materialize_tree`, predecessor `absent|present`, nullable
predecessor identity/digest, and nullable successor digest. Present requires
identity plus digest; absent requires both null. The action set and monotone
`next_action_index` contain every permitted addition, replacement, and removal.
Every other field is operation-closed. Unknown paths, mixed field sets,
duplicate aliases, fourth physical states, and an object over its bound are
invalid.

For operations other than `cleanup_prepublication`, every
`cleanup_inventory_*` field is null. Cleanup uses an empty `actions` array and
`next_action_index=0`; the cleanup cursor is its only deletion cursor. The
logical cleanup manifest still comes only from the frozen rendered model. The
physical identity inventory is captured exactly once from the complete work
tree after that tree has been verified against the logical manifest, then
persisted before rename. Once present, resume consumes only that sidecar. In the
single `PREPARED`/sidecar-absent crash row it may reproduce the already
committed complete inventory bytes in memory, materialize only deterministic
staging, bind `STAGING_BOUND`, and then commit that exact identity under the
shared rule. Unbound staging is delete-only; no observed file changes inventory
authority. Residual enumeration
outside that row may detect unknown state but cannot authorize it.

Only `install_apply_invocation` may populate the apply/admission fields in
`pending_transition`. Its `PREPARED` row requires exact attempt ID, invocation
self-digest, canonical invocation-document byte size, planned admission-document
byte size/digest, and canonical admission and attempt-owned staging/inner-temp
paths plus exact state-parent identity. The invocation size is an exact non-bool
integer from 1 through `APPLY_INVOCATION_MAX_BYTES`, is derived only as
`len(invocation.canonical_json)` during Prepare, and remains unchanged through
`PREPARED`, `STAGING_BOUND`, `PRIMARY_APPLIED`, every runtime-layout CAS, and
the invocation-receipt subcursor. It is null for every other pending operation.
Its `external_file_action` is `PLANNED` and physical admission and staging
identities/digests remain null. Only a materialization receipt may CAS
`STAGING_BOUND` with the exact staging identity/size/digest. Only the following
identity-preserving no-replace commit receipt may CAS `PRIMARY_APPLIED`, where
the final admission identity equals that persisted staging identity, both
staging surfaces are absent, while the invocation-receipt action and runtime
layout are still null. The next session CAS installs the exact ordered
`runtime_layout_bootstrap`; its seven receipt CASes bind one directory identity
at a time. The last directory receipt marks the layout `COMPLETE` and installs a
fresh nested `external_file_action=PLANNED` for the deterministic
invocation-receipt final/staging/inner-temp paths and planned canonical bytes.
That action takes `planned_successor_size` only from the persisted
`apply_invocation_document_size` and takes `planned_successor_sha256` only from
the already persisted raw-byte digest in `successor_artifact_bindings`; neither
an in-memory invocation, receipt-file observation, nor runtime recapture may
supply or alter either value. A
final-only admission while still `PREPARED` is tamper and is never captured.
Materialize and commit receipts advance only that nested action while the outer
stage remains `PRIMARY_APPLIED`. The final
`APPLY_STARTED` CAS copies those four physical facts plus the
exact active output-operation-admission digest, retired output-child, and
publication bindings into the closed `runtime_admission_binding`, binds
`apply_invocation_sha256`, changes the existing operation binding to
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED`, and clears the transition. All
apply/admission fields are null for every other operation.
`runtime_admission_binding` is null before admission and jointly exact after
claim, including the operation-admission digest, output-child-binding digest,
child path/identity, and publication revision/content root copied from the
exact retired binding.
Mixed nullability, path reconstruction, direct-final capture, or rebound
identity is invalid.

Only `install_output_operation_admission` may populate the
`output_operation_admission_*` pending fields. Its `PREPARED` row binds the
complete canonical fixed-record bytes, byte size/digest, absent target path,
exact state-root parent identity, output/profile/session authority, output
child predecessor, deterministic staging/inner-temp paths, and deterministic
per-child claim path before a physical record or staging surface exists. The per-child claim bytes are planned only from
the resulting `ACTIVE` cursor, avoiding a self-digest cycle. The session remains
`PREPUBLICATION_CHECK_PASSED`, and its durable
`output_operation_admission_binding` is null. Its `external_file_action` starts
`PLANNED`. A materialization receipt alone CASes `STAGING_BOUND` and binds the
exact internal staging identity; unbound staging/temp residue is delete-only
and never promoted. A second receipt from the identity-preserving no-replace
commit alone CASes the complete final identity/digest/evidence into the binding
with `state=ACTIVE`, clears the pending transition, and permits child bootstrap.
Final-only at `PREPARED`, foreign, malformed, replaced, second, wrong-parent,
or post-bind same-byte identity-substituted occupants are tamper. All output-operation fields are null for every
other pending operation.

The active binding is immutable through per-child claim publication,
publication CAS, claim unlink, claim-retired CAS, and prepublication cleanup.
For live apply, the final `APPLY_STARTED` CAS that durably binds the exact
runtime admission also changes only its state to
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED`; the record identity and bytes remain
unchanged. For preview or failure after record creation, the terminal CAS
changes it instead to `TERMINAL_RELEASE_AUTHORIZED`. No other phase or status
may authorize release. The corresponding fresh release bearer verifies the
fixed record or its exact already-absent postcondition and unlinks only that
identity. Because the release-authorized session cursor precedes deletion and
remains durable, no additional CAS is needed to authorize or record the unlink.
A terminal no-runtime path ends there. Later live-phase CASes preserve the
complete release-authorized binding byte-identically, so an absence after a
crash cannot be confused with unauthorized deletion.

The closed binding matrix is exact. `ACTIVE` requires
`release_handoff_kind=null`, every handoff-runtime field null, and the old
physical record exact. `RUNTIME_HANDOFF_RELEASE_AUTHORIZED` requires
`release_handoff_kind=runtime_admission` and all four handoff-runtime fields
exactly equal the durable `runtime_admission_binding` created in the same
`APPLY_STARTED` CAS. `TERMINAL_RELEASE_AUTHORIZED` requires
`release_handoff_kind=terminal_no_runtime`, every handoff-runtime field null,
an exact terminal session, and no runtime admission. Later live-phase CASes may
preserve only the complete `RUNTIME_HANDOFF_RELEASE_AUTHORIZED` binding
byte-identically; no CAS rewrites or clears it after the old record disappears.
A release-authorized row
permits only the old exact record, exact absence, or a canonical identity-
distinct foreign successor that is preserved byte-identically. A same-run or
same-byte identity replacement is tamper, not a foreign successor.

Only `bootstrap_output_child` and `retire_output_child_claim` may populate the
`output_*` fields. Both run under the active session/profile leases, an
identity-bound output-base guard, and the fixed per-output bootstrap lock
derived from the canonical child path. All live, preview, and legacy publisher
wrappers acquire that same lock and inspect the same claim before creating,
opening, reconciling, or publishing the child. Claim creation uses
`PREPARED|STAGING_BOUND|PRIMARY_APPLIED`; the other child/retirement actions use
only `PREPARED|PRIMARY_APPLIED`. `CLEANUP_DELETING` is invalid.

The external claim path is exactly
`<output-base>/.hsconfig-live-start-output-child-<sha256(UTF-8 child
component)>.claim.json`. Its canonical, self-digested document is at most
16 KiB and contains exactly:

```text
schema_version, claim_kind, run_id, session_root, session_root_identity,
expected_session_sha256, output_base_path, output_base_identity,
output_child_path, predecessor_state, predecessor_output_child_identity,
content_sha256
```

Its final path is the path above. Staging is exactly that path with `.staged`
appended, and the inner temp is exactly `.<staging-leaf>.live-start-atomic.tmp`
under the same bound output base. It is published create-only with the shared
staged/no-replace protocol. The complete planned bytes, byte size, digest, all
three paths, and parent identity are bound in the session before any claim or
child write. Unbound staging/temp may be discarded only from that exact
persisted intent and is never promoted. A foreign, malformed, replaced,
differently bound, unsafe, additional, or post-bind same-byte claim/temp blocks before
child, revision, or current-pointer mutation.
`expected_session_sha256` is the exact pre-bootstrap predecessor cursor passed
to `prepare_output_child_bootstrap_under_lock()`, never the digest of the
successor that embeds the claim digest; the protocol therefore has no
self-referential hash cycle.

`bootstrap_output_child/PREPARED` requires `output_child_binding=null`,
`publication_binding=null`, an exact output-base identity, and either an absent
child with null predecessor identity or the exact sealed existing-child
identity. The claim and its reserved temp are absent; claim identity/digest and
created-or-confirmed child identity are null. The deterministic staging and
inner-temp are also absent and `external_file_action.stage=PLANNED`. If unbound
staging/temp is observed, only `retire_unbound_claim_staging` may remove or
confirm its absence; its receipt CASes `unbound_claim_staging_retired`, keeps
the action `PLANNED`, and selects materialization. A fresh
`materialize_claim_staging` token may only create exact staging and its receipt
CASes `STAGING_BOUND`. If that CAS was not durable, any staging/temp is
rollback-only. From `STAGING_BOUND`, a fresh `commit_bound_claim` token may only
commit or confirm the already-bound staging identity. Its receipt alone CASes
the transition to `PRIMARY_APPLIED`, copies that identity to the final claim,
clears staging state, and increments `next_action_index` to one. Final-only at
`PREPARED`, a missing bound identity, or a same-byte replacement after binding
is tamper.

`bootstrap_output_child/PRIMARY_APPLIED` requires that exact active claim and
unchanged child predecessor. Its closed child action is:

| Sealed predecessor | Sole allowed action or confirmation |
| --- | --- |
| Existing exact child | Open and confirm the original identity; never create or rebind it. |
| Absent child, still absent | Create exactly one plain child descriptor-relatively under the bound base. |
| Absent child, plain empty child after create-before-CAS | Only the exact active owning claim authorizes capture of that new-object identity while its guard remains held through CAS. |

A claimless child, nonempty or unsafe child, wrong claim, foreign run, wrong
parent, or any prebound identity change is tamper and is never adopted or
cleaned. The `bind_existing_child|create_output_child` receipt binds the exact
session predecessor, action, base/child/claim paths and identities, predecessor
state, and resulting child identity. Its `child_bound` CAS clears the pending
transition and installs a self-digested `output_child_binding` with
`claim_state=ACTIVE`; phase remains `PREPUBLICATION_CHECK_PASSED` and
`publication_binding` remains null. From then on the child identity is
immutable and every publisher access uses only its still-held guard.

An active claim is a publisher fence. Under the common bootstrap lock, claim
absence permits the ordinary path only when no session binding expects it;
the exact claim plus the matching opaque session/profile capability permits
only its owning controller; the exact claim without that capability blocks;
and malformed, foreign, or replaced authority is tamper. The owning publisher
revalidates the base, child, and claim identities, acquires the child
`.publish.lock` without reacquiring an outer lock, and keeps claim, guards, and
publisher lock through the `PUBLICATION_COMMITTED` session CAS. That CAS binds
the exact child path, identity, output-child-binding digest, revision, content
root, and prior-current identity. A publisher-commit-before-session-CAS crash
is reconciled only under those exact authorities and current-pointer parity.

The claim may be retired only after `PUBLICATION_COMMITTED`.
`retire_output_child_claim/PREPARED` repeats the exact active claim, child, and
publication bindings; before that CAS no unlink is allowed. A fresh
`retire_claim` token may call only `secure_unlink_verified()` on the exact claim
identity and parent. Its receipt CASes `PRIMARY_APPLIED` with the claim absent
and child identity plus physical current publication still exact. A crash after
unlink but before CAS resumes only from that persisted predecessor, exact
absence, and unchanged current revision/content root; a publisher that won
after the process lock was lost therefore causes a typed stop before preview or
apply. From `PRIMARY_APPLIED`, a fresh
`confirm_claim_absent_and_current_exact` token performs that bounded physical
confirmation under the same bootstrap lease and returns the sole receipt for
the final CAS. That whole-session CAS clears the transition, reseals
`output_child_binding` with `claim_state=RETIRED`, and atomically changes
`publication_binding.output_child_binding_sha256` to the new retired digest.
Every other publication and historical claim field remains unchanged. The
ACTIVE and RETIRED digests must differ. `RETIRED` requires
physical claim absence and never authorizes claim recreation or child rebinding.

Only `PUBLICATION_COMMITTED`, null pending transition, a retired claim, and the
same exact active output-operation admission binding may start prepublication
cleanup, preview terminalization, or apply/admission.
`ApplyInvocation`, the external runtime admission, and
`runtime_admission_binding` all repeat the exact output-child-binding digest,
child path/identity, publication revision, and content root. Same-attempt apply
and recovery require that complete equality plus the currently opened child
identity before runtime observation or mutation. All output fields are null on
every unrelated pending operation; all apply/admission fields are null on both
output operations.

Every sibling-artifact transition follows one protocol under the active session
lease:

1. derive exact source/target phase, revision, revision-use count, successor
   binding map, and ordered actions from the current explicit session cursor;
2. CAS the sealed `PREPARED` transition into `session.json` before the first
   physical write, replacement, removal, or work-root creation;
3. perform the one atomic primary action and CAS `PRIMARY_APPLIED`, then advance
   `next_action_index` by CAS after each exact physical action;
4. complete only the listed remaining actions, validating every predecessor
   identity/digest or exact absence immediately before mutation;
5. reread the exact successor set, then replace `artifact_bindings`, phase,
   revision, and `revisions_used` with the target values and clear the intent in
   one final CAS. Revision budget is charged only there and never twice.

The bounded `actions` array applies only to run-root artifacts.
`bootstrap_output_child`, `retire_output_child_claim`, and
`cleanup_prepublication` require it to be empty. The two output operations use
their closed claim/child action cursor above; cleanup instead advances through
the bounded canonical cleanup manifest identified by digest, entry count, and
cursor. That manifest is reconstructed from the frozen rendered model and
historical work binding; it is never embedded unboundedly in the session or
regenerated from a live residual tree.

Candidate or review replacement is the physical commit point for its operation:
it occurs before deleting superseded receipts. If the predecessor primary still
exists after a crash, no secondary removal may have occurred and resume clears
the intent back to the exact predecessor. If the exact successor primary
exists, resume proceeds forward and removes only still-present listed
predecessors. Receipt creation similarly rolls back the intent when the receipt
is absent and completes forward only for the exact sealed successor. A mixed,
replaced, or unknown artifact set is tamper, never a guessed rollback.

Package materialization CASes `PREPARED` before creating its deterministic
per-run work child and binds the rendered-model digest, complete expected tree
digest, cleanup-manifest digest, and bounded entry count derived from frozen
inputs. On resume, an absent child restarts from those same bytes;
an existing child is accepted only when every present entry is an exact subset
of the expected rendered tree, after which missing entries are completed and
the full identity/inventory is bound as `PRIMARY_APPLIED`. Its final same-phase
CAS clears the intent and sets `prepublication_work_binding`; only a subsequent
transition may create and bind `package_validation.json`. That receipt repeats
all seven parent/root/tree/manifest work-binding facts. A validation failure can therefore clean the exact
bound work tree before becoming terminal. Unknown or replaced content is
preserved as tamper. No mutable input or network source is reread.
Invocation keeps its stronger exact-attempt recovery rules in Task 9. Its
transition first binds the planned invocation and admission, then durably
claims that admission before the receipt write. It therefore shares the
intent-before-physical-change invariant without creating an unblocked
recovery-only receipt window.

Its physical matrix is exact. At `PREPARED`, final admission remains absent.
When staging and inner-temp are absent, rollback may clear the intent. Any
unbound staging/temp is delete-only: the executor captures identity only as a
verified deletion guard, and its receipt CAS records absence before rollback or
retry. A crash after deletion and before that CAS remints against the old cursor
and exact absence. At `STAGING_BOUND`, only bound staging, final with that same
identity, or the declared POSIX same-identity two-link intermediate may complete
the no-replace commit and `PRIMARY_APPLIED` receipt CAS. Direct final from
`PREPARED`, partial or substituted staging, foreign final admission, missing
bound identities, or a mixed receipt state is nonterminal tamper.

The complete session has a 256 KiB maximum. Nested `result_intent` schema
version 1 has a 64 KiB canonical-serialization maximum. `PROFILE_REQUIRED` and
a pre-session input/deck failure never create a run or intent; the
session-backed status variants use the matrix below. `raw_apply_status` is null or
`applied|already_current|recovered|committed_receipt_pending`; physical
disposition is null or one of the four closed values; runtime match is exactly
`not_run|matched|mismatch|unknown`. `error_code` is null or one safe ASCII token
of at most 64 characters.

The four `runtime_admission_*` result-intent fields are jointly null for
profile/pre-session failures, preview, and publication-only failures. They are
jointly non-null and exactly equal to the held admission evidence for every
post-claim result, including
proven `NOT_COMMITTED`, committed mismatch, recovery-pending, and unknown. A
mixed row, reconstructed path, recaptured identity, or mismatched digest is
invalid. The held composite or recovery context supplies those values; the
controller never reloads a different singleton as authority.

Session-backed result-intent counts and pre-session in-memory summary counts are
separate closed authorities. The pre-session summary is a canonical,
self-digested `FrozenJsonDocument` of at most 16 KiB with exactly:

```text
schema_version, summary_kind, status, run_root, deck_name, candidate_revision,
unique_main_deck_cards, configured_cards, deliberately_unconfigured_cards,
review_confidence, visible_limitations, error_code, retained_safe_state,
content_sha256
```

Its schema version is 1, kind is `live_start_pre_session_result`, status is
`PROFILE_REQUIRED|FAILED_PRESERVED`, `run_root` and `candidate_revision` are
null, review confidence is null, and the cause, safe-state, text, size, and
self-digest bounds match the session-backed result contract. `deck_name` is a
safe validated name or null only when name syntax itself failed. It creates no
result file.

Pre-session count authority is exactly:

| Pre-session branch | `unique_main_deck_cards` | `configured_cards` | `deliberately_unconfigured_cards` |
| --- | --- | --- | --- |
| No validated supported normalized roster | null | null | null |
| Exact validated supported normalized roster exists, but later acquisition fails before session sealing | exact unique-card integer | null | null |

Profile failure, name/deck syntax failure, ambiguous deck resolution, and any
partially decoded, rejected, provisional, or unsealed roster use the all-null
row. A later acquisition failure may use the integer row only when the exact
supported normalized roster was already completely validated and remains an
immutable in-memory value. A mixed coverage pair, invented zero, Boolean,
partial-roster count, or any configured count is invalid. Both rows render card
coverage as unavailable, never incomplete, complete, or deliberately
unconfigured.

For every session-backed `result_intent`, `unique_main_deck_cards` is a
non-Boolean integer equal to the exact number of unique physical main-deck
CardIDs in the frozen normalized deck blob. It is bounded by the existing
supported deck-structure contract; this result schema does not introduce a
literal 30-card or 30-CardID limit.

For every session-backed `result_intent`, `configured_cards` and
`deliberately_unconfigured_cards` are one jointly nullable pair. Both are null
until the current candidate revision has a bound, self-digested
candidate-validation receipt with `status=valid` and matching run, context,
candidate revision, and candidate digest. Once that authority exists, both
values are non-Boolean integers from zero through `unique_main_deck_cards`, and
their sum equals `unique_main_deck_cards`.

`REVIEW_APPROVED` and every later session phase, including package,
prepublication, preview, publication, apply, recovery, runtime-match, and
post-apply terminal results, require both coverage counts to be non-null. A
session-backed `FAILED_PRESERVED` without valid current-candidate authority
requires the configured/deliberately-unconfigured pair to be jointly null while
retaining the exact frozen unique-card count. A mixed pair, Boolean value,
out-of-range value, wrong frozen-roster count, or non-null coverage without its
exact valid-candidate authority is invalid. The renderer maps the joint-null
pair to card coverage unavailable; it must not invent complete or deliberately
unconfigured coverage.

Deck name is safe text from 1 to 128 characters; candidate revision is 1
through 3; review confidence is null or `high|limited`; and visible limitations
are a canonical sorted unique list of at most 32 context-safe strings of at
most 256 characters. The closed `retained_safe_state` values are
`NO_PUBLICATION_OR_RUNTIME_WRITE`,
`PUBLICATION_RETAINED_RUNTIME_UNCHANGED`,
`PUBLISHED_PREVIEW_RUNTIME_UNCHANGED`, `PREVIOUS_RUNTIME_UNCHANGED`,
`ATTEMPT_EVIDENCE_RETAINED`, and `ACTIVE_RUNTIME_MATCHED`. These facts plus the
error code authorize every human-facing JSON/Markdown field; result rendering
rereads no mutable candidate, review, package, or runtime surface.

The closed status matrix is:

- `PROFILE_REQUIRED`: no session, result intent, or result file exists; return
  one closed pre-session summary with `run_root=None`, the all-null card-count
  row, card coverage unavailable, and the bounded profile cause.
- Pre-session `FAILED_PRESERVED`: invalid deck resolution or input acquisition
  before a session exists returns one closed pre-session summary with
  `run_root=None`, the exact applicable pre-session count row, card coverage
  unavailable, and one bounded cause; no output or runtime path is written.
- `PREVIEW_READY`: phase is `PUBLICATION_COMMITTED`, publication is bound,
  invocation/apply fields are null, match is `not_run`, and no acknowledgement
  exists; runtime remains untouched.
- `LIVE_AND_MATCHED`: phase is `RUNTIME_MATCHED`, raw status is
  `applied|recovered`, disposition is `COMMITTED`, exact match and all runtime
  digests plus retained admission/attempt-record/journal facts are present, and
  the exact acknowledgement object is required.
- `ALREADY_LIVE`: phase is `RUNTIME_MATCHED`, raw status is `already_current`,
  disposition is `COMMITTED`, exact match and all runtime digests are present,
  retained admission/attempt-record/journal facts are present, and the exact
  acknowledgement object is required.
- Prepublication `FAILED_PRESERVED`: any phase through
  `PREPUBLICATION_CHECK_PASSED` is allowed only without an invocation; apply
  fields are null, safe state is `NO_PUBLICATION_OR_RUNTIME_WRITE`, no
  acknowledgement exists, and resume returns the immutable failure.
- Published pre-apply `FAILED_PRESERVED`: phase is `PUBLICATION_COMMITTED`
  without an invocation, safe state is
  `PUBLICATION_RETAINED_RUNTIME_UNCHANGED`, and no acknowledgement exists.
- Post-apply `FAILED_PRESERVED`: phase is `APPLY_STARTED`, disposition is
  positively proven `NOT_COMMITTED`, the exact pre-apply snapshot still holds,
  match is `not_run`, and no acknowledgement exists. The evidence-free fast
  path has no retention record or journal. The closed precommit-cleanup path
  instead binds the exact historical fence, attempt journal, any separate
  target owner, admission, and attempt-owned tree authority before the first
  delete; only `terminal_retirement/release_resolved_terminal` may later make
  that historical evidence physically absent. The result intent and status stay
  byte-identical and already truthfully report `FAILED_PRESERVED`.
- Committed-mismatch `APPLIED_BUT_NOT_VERIFIED`: phase is `APPLY_COMMITTED`, raw
  status is `applied|already_current|recovered`, disposition is `COMMITTED`,
  match is `mismatch|unknown`, no acknowledgement exists, and the owner-bound
  retention record and journal remain byte-identical while admission is
  released only after terminal CAS.
- Pending/unknown `APPLIED_BUT_NOT_VERIFIED`: phase is `APPLY_STARTED`, or
  `APPLY_COMMITTED` only when commit is proven; raw status is
  `committed_receipt_pending` or null, disposition is
  `COMMITTED_RECOVERY_PENDING|UNKNOWN_REQUIRES_RECOVERY`, and no
  acknowledgement exists; any observed retention record/journal is bound and
  preserved as immutable historical evidence together with the blocking
  admission. Exact recovery may diagnose or progress active physical metadata
  only through a persisted terminal-resolution predecessor/successor intent; it
  never rewrites the historical terminal result or deletes evidence without its
  later closed retirement action.

Every status-incompatible field combination is invalid. Success alone permits
the acknowledgement object. Pre-apply failures require
`NO_PUBLICATION_OR_RUNTIME_WRITE` before publication and
`PUBLICATION_RETAINED_RUNTIME_UNCHANGED` after publication; preview requires
`PUBLISHED_PREVIEW_RUNTIME_UNCHANGED`; no-commit requires
`PREVIOUS_RUNTIME_UNCHANGED`; unresolved/committed mismatch requires
`ATTEMPT_EVIDENCE_RETAINED`; and success requires
`ACTIVE_RUNTIME_MATCHED`. The nested self-digest and outer session self-digest
bind the chosen terminal outcome atomically.

The retained attempt-record path/identity/digest triplet is jointly null or
jointly exact.
It is required whenever the controller retention fence exists and forbidden
when `NOT_COMMITTED` was proven with no remaining attempt evidence. The journal
and target-owner-journal triplets follow the same physical evidence. An
`ACTIVE` fence is strictly pre-planning: every planned-journal, observed
journal, candidate, target, and owner field is null. On a new-target route it
must first CAS to `CANDIDATE_PLANNED`, binding the exact candidate parent/path
and planned v1 path/size/digest before v1 creation is permitted. An applicable
existing target owner must first advance the fence to
`PRIOR_OWNER_PLANNED`, binding the exact target/owner triplets and planned v1
path/size/digest while the journal identity is null. Once those exact v1 bytes
are present, the fence advances to `PRIOR_OWNER_BOUND` and binds their identity
and digest. Both rows remain active preservation fences and are not terminal
results. Once any v1 journal is observed, its triplet is mandatory before the
fence becomes `FINALIZED`.
Result validation recomputes the
deterministic fence path from the invocation attempt ID and rejects an unbound,
aliased, recaptured, same-byte-replaced, or action-incompatible record.

| Observed attempt state | Fence triplet | Attempt-journal triplet | Target-owner triplet |
| --- | --- | --- | --- |
| Before controller fence | null | null | null |
| `ACTIVE` before route-planning CAS; v1 forbidden | exact | null | null |
| `CANDIDATE_PLANNED`, v1 and candidate absent | exact | null; exact planned path/size/digest in fence | null |
| `CANDIDATE_PLANNED` with exact v1 and candidate absent | exact | exact and equal to plan | null |
| `CANDIDATE_BOUND` after exact journal and candidate binding | exact | exact and equal to plan | null |
| `PRIOR_OWNER_PLANNED`, v1 absent | exact | null; exact planned path/size/digest in fence | exact separate owner |
| `PRIOR_OWNER_PLANNED`, v1 exact | exact | exact and equal to plan | exact separate owner |
| `PRIOR_OWNER_BOUND` after v1 `PREPARED` on an exact pre-existing target route | exact | exact | exact separate owner |
| `FINALIZED` owning | exact | exact | exact and equal to the owning attempt journal |
| `FINALIZED` non-owning | exact | exact no-op journal | exact separate owner |
| Proven `NOT_COMMITTED` with closed historical cleanup evidence | exact historical binding | exact historical binding when v1 was written | exact only when a separate prior owner applies |
| Proven `NOT_COMMITTED` after closed cleanup | null | null | null |

The admission path/parent-identity/file-identity/digest quartet is likewise jointly null or jointly
exact. When present, validation recomputes the fixed singleton path from the
local HSConfig state root and verifies its historical run/attempt/fence binding even
after authorized release; only the status matrix decides whether physical
presence or exact absence is required at the current recovery cursor.

Preview and both success statuses require an approved `high|limited` review;
success also requires complete card-count coverage and `error_code=null`.
Preview requires `error_code=null`. Every failure status requires one non-null
error code; review confidence may be null only when the failure predates an
approved review.

Session-backed coverage-count nullability is orthogonal to terminal status but
closed by durable authority:

| Durable coverage authority | `configured_cards` | `deliberately_unconfigured_cards` |
| --- | --- | --- |
| No current same-revision valid candidate-validation receipt | null | null |
| Current same-revision valid candidate-validation receipt bound | exact integer | exact integer |
| `REVIEW_APPROVED` or any later phase | required exact integer | required exact integer |

For the integer variant, both values are bounded by the exact frozen unique-card
count and their sum equals that count. Preview, both success statuses,
post-package failures, published failures, and every apply/recovery result are
therefore non-null. Only an early failure before current candidate validity may
use the joint-null variant. A joint-null result renders coverage unavailable,
not incomplete or complete.

The pre-session in-memory variants are governed only by the separate matrix
above; they never enter this session-backed table.

The only allowed pre-terminal commit-intent variant has a non-null valid
`result_intent`, an outer `terminal_status=null`, and an acknowledgement object
only when that intent names a success status. Resume completes the exact result
pair and outer terminal CAS from those already bound nested bytes. An
acknowledgement without a result intent, a status mismatch, or any other
partially populated combination is tamper.

No result intent, result file, acknowledgement object, publication/apply phase
advance, or terminal status may be bound while `pending_transition` is non-null,
except the transition's own declared target-phase CAS that clears it atomically.
Likewise, no result file, acknowledgement, terminal retirement, or terminal
status may be bound while `apply_recovery` is non-null. Result intent is the
single exception: `bind_result_intent_under_lock()` accepts only an exact closed
recovery object, derives and validates the result from it, installs that intent,
and clears the object in the same whole-session CAS. Its own closed pure-CAS
phase edges are the only earlier phase advances; no reload or second
classification is permitted between `recovery_closed` and that consuming CAS.

`attempt_acknowledgement` schema version is 1 and maximum size is 32 KiB. It is
non-null only for a successful result with an exact controller-retention fence
and `FINALIZED` runtime journal. Their canonical paths, three-integer identities,
standard file digests, run/attempt/retention-owner IDs, package digest,
`owns_target` value, and closed action must equal the held context's evidence.
For `owns_target=true`, acknowledgement retains the exact schema-1 owner journal
and removes only the fence. For `owns_target=false`, it removes the exact no-op
journal and then the fence while the separately bound owner remains. The closed
physical matrix is:

| Acknowledgement action | Pre-action | Intermediate | Completed |
| --- | --- | --- | --- |
| `retain_target_owner_delete_fence` | Exact owner and exact fence present | Exact owner present; fence absent before evidence-retired CAS | Exact owner present; fence absent |
| `delete_nonowning_attempt_and_fence` | Exact no-op journal, exact owner, and exact fence present | No-op absent; exact owner and fence present | No-op and fence absent; exact owner present |

Only the post-terminal retirement capability may advance these states. Every
replacement, missing owner, action mismatch, or unbound absence is tamper. The
closed stage/action/successor matrix is exact:

| Persisted retirement stage | Ownership row | One permitted action | Required receipt CAS |
| --- | --- | --- | --- |
| `PREPARED` | owning | Remove or confirm absence of only the exact fence | `EVIDENCE_RETIRED` |
| `PREPARED` | non-owning | Remove or confirm absence of only the exact no-op journal | `ACK_JOURNAL_RETIRED` |
| `ACK_JOURNAL_RETIRED` | non-owning | Remove or confirm absence of only the exact fence | `EVIDENCE_RETIRED` |

After an action-before-CAS crash, a still-persisted `PREPARED` non-owning row
with journal absent and fence present may remint only the journal-action receipt
and CAS `ACK_JOURNAL_RETIRED`. It may not jump directly to
`EVIDENCE_RETIRED`. Journal and fence both absent while non-owning `PREPARED`
is an impossible skipped-action state and fails as tamper. The same rule rejects
an old `PREPARED` cursor for the later fence step. Physical postcondition alone
never authorizes admission release.

For `retain_target_owner_delete_fence`, the fence action returns one receipt and
its CAS reaches `EVIDENCE_RETIRED`. For
`delete_nonowning_attempt_and_fence`, the journal action returns one receipt and
its CAS reaches `ACK_JOURNAL_RETIRED`; only a fresh authorization may then
delete the fence, whose separate receipt CASes `EVIDENCE_RETIRED`. Each
action-before-CAS crash remints only from the persisted predecessor and exact
idempotent postcondition. No single token or helper may delete both rows.

`terminal_retirement` schema version is 1 and maximum size is 64 KiB. Its
operation is exactly `ack_success`, `release_not_committed`,
`release_committed_mismatch`, or `release_resolved_terminal`. Owning
`ack_success` advances only `PREPARED -> EVIDENCE_RETIRED ->
ADMISSION_RELEASE_AUTHORIZED`; non-owning `ack_success` advances only
`PREPARED -> ACK_JOURNAL_RETIRED -> EVIDENCE_RETIRED ->
ADMISSION_RELEASE_AUTHORIZED`. The two stable non-success operations advance
only `PREPARED -> EVIDENCE_RETIRED -> ADMISSION_RELEASE_AUTHORIZED`.
`release_resolved_terminal` advances only
one of these four closed paths:

- commit:
  `RECOVERY_PREPARED -> RECOVERY_STABILIZED -> EVIDENCE_RETIRED ->
  ADMISSION_RELEASE_AUTHORIZED`;
- no-commit with no v1 journal and no attempt-owned tree:
  `RECOVERY_PREPARED -> RECOVERY_FENCE_RETIRED -> RECOVERY_STABILIZED ->
  EVIDENCE_RETIRED -> ADMISSION_RELEASE_AUTHORIZED`;
- no-commit with an exact v1 `PREPARED` journal but no attempt-owned tree:
  `RECOVERY_PREPARED -> RECOVERY_JOURNAL_RETIRED ->
  RECOVERY_FENCE_RETIRED -> RECOVERY_STABILIZED -> EVIDENCE_RETIRED ->
  ADMISSION_RELEASE_AUTHORIZED`;
- no-commit with an attempt-owned candidate or target tree:
  `RECOVERY_PREPARED -> RECOVERY_INVENTORY_BOUND -> RECOVERY_CLEANING ->
  RECOVERY_JOURNAL_RETIRED -> RECOVERY_FENCE_RETIRED ->
  RECOVERY_INVENTORY_RETIRED -> RECOVERY_STABILIZED ->
  EVIDENCE_RETIRED -> ADMISSION_RELEASE_AUTHORIZED`.

It is null before a terminal CAS. A stage from one path is invalid on the other.
Preparing `ack_success|release_not_committed|release_committed_mismatch` requires
`runtime_observation_receipt=null`. Preparing `release_resolved_terminal`
requires one exact, unconsumed `terminal_resolution` observation receipt from
the current terminal session and active pair; the CAS installs only its private
Evidence successor. Caller-supplied terminal Evidence is not an API input.

The held post-terminal method first CASes `PREPARED` against the exact persisted
terminal cursor before deleting any attempt evidence. It CASes
`EVIDENCE_RETIRED` only after the operation-specific evidence postconditions are
true. While the exact old admission still occupies the singleton, it then CASes
`ADMISSION_RELEASE_AUTHORIZED`; only that final durable session cursor permits
unlinking that exact old admission. There is no session CAS after physical
unlink. A crash before unlink resumes from the authorization and removes only
the old identity; a crash after unlink observes absence and is complete. If a
fully canonical, identity-distinct foreign admission has since won the
no-replace path, the old run leaves it byte-identical and treats it only as proof
that the old identity is absent. The same old identity with different bytes,
malformed bytes, or any unbound combination is tamper.

`terminal_resolution_evidence` is null for the first three operations and is
required for `release_resolved_terminal`. Its schema version is 1, kind and
maximum use the constants above, and its historical predecessor triplets equal
the immutable terminal `result_intent`. Before the first post-terminal physical
metadata mutation, `RECOVERY_PREPARED` binds those predecessors plus the only
permitted same-run/same-attempt branch and successor states. Successor triplets
and stable proof fields are null at that stage. Targeted recovery may then make
only the declared transition.

On the commit branch, `physical_recovery_advanced` is a same-outer-stage
`RECOVERY_PREPARED -> RECOVERY_PREPARED` CAS that replaces only the current
successor triplets with one exact immediate monotone successor. Its receipt
binds the complete old and new evidence digests. The changed whole-session
digest is the cursor for the next authorization, so a second physical row
cannot advance under the prior token or receipt. Once the exact canonical
committed successor and all parity facts are present, a pure-CAS
`stabilized` edge consumes a fresh stage token and reaches
`RECOVERY_STABILIZED`. On a no-commit cleanup branch, the only same-outer-stage
CAS operations at `RECOVERY_PREPARED` are receipt-bound retirement of unbound
inventory staging and receipt-bound `PLANNED -> STAGING_BOUND` inventory
materialization. Neither may delete a cleanup entry, advance `cleanup_cursor`,
change a cleanup-root row, or touch journal/fence evidence.

`cleanup_stage` is closed to
`null|PREPARED|INVENTORY_BOUND|CLEANING|JOURNAL_RETIRED|FENCE_RETIRED|INVENTORY_RETIRED|COMPLETE`.
It is null, together with every cleanup field, on every branch without an
attempt-owned tree. On the tree branch the exact matrix is:

| Outer retirement stage | Cleanup authority and permitted physical row |
| --- | --- |
| `RECOVERY_PREPARED` | `PREPARED`; `external_file_action=PLANNED|STAGING_BOUND`; planned paths/parent/bytes/count/roots exact; final identity null; cursor 0; every tree/journal/fence exact and present |
| `RECOVERY_INVENTORY_BOUND` | `INVENTORY_BOUND`; final sidecar exact with the previously bound staging identity; staging/temp absent; cursor 0; no deletion |
| `RECOVERY_CLEANING`, cursor `< count` | `CLEANING`; the current row alone may be exact or already absent after its authorized step; every later row and parent remains exact |
| `RECOVERY_CLEANING`, cursor `== count` | `CLEANING`; both roots absent, exact journal/fence/sidecar present before metadata retirement |
| `RECOVERY_JOURNAL_RETIRED` | `JOURNAL_RETIRED`; roots and journal absent, exact fence and sidecar present |
| `RECOVERY_FENCE_RETIRED` | `FENCE_RETIRED`; roots, journal, and fence absent, exact sidecar present |
| `RECOVERY_INVENTORY_RETIRED` | `INVENTORY_RETIRED`; roots, journal, fence, sidecar, and reserved temp absent |
| `RECOVERY_STABILIZED` | `COMPLETE`; full historical inventory/count/cursor retained as authority, all active cleanup targets absent, stable successor proof exact |

Every mixed nullability, skipped row, early absence outside the one current
idempotent action, stale cursor, or reappearance is invalid.

For a no-commit cleanup with an attempt-owned tree, `RECOVERY_PREPARED` also
binds `cleanup_stage=PREPARED`, the run-local sidecar path and parent identity,
its already computed canonical size/digests/count, the exact cleanup-root rows,
`cleanup_cursor=0`, and a nested `external_file_action=PLANNED`; sidecar and
staging identities are null and no deletion has occurred.
After a crash at this row with the sidecar absent, the helper may boundedly and
no-follow enumerate the still-complete attempt tree only as a candidate for the
already persisted inventory commitment. It first revalidates the prebound root
and parent identities, then rebuilds canonical entry rows including every
current object and parent identity. It may materialize those bytes only when
their complete byte size, byte digest, self-digest, entry count, cleanup-root
rows, and every canonical line reproduce the values committed in
`RECOVERY_PREPARED`. A same-byte file replacement, empty-directory replacement,
parent replacement, missing or extra row, or any digest difference is tamper.
No observed identity replaces, extends, or becomes authority; the observation
is only a candidate whose full canonical bytes must satisfy the pre-crash
commitment.
Materialize those reproduced bytes only to deterministic staging through its
inner temp. The materialization receipt alone keeps the outer stage at
`RECOVERY_PREPARED`, sets the nested action to `STAGING_BOUND`, and binds its
exact triplet. A fresh commit authorization then converges staging-only,
final-only with that same bound identity, or the exact POSIX two-link
intermediate to final-only. Its receipt alone advances to
`RECOVERY_INVENTORY_BOUND`, sets `cleanup_stage=INVENTORY_BOUND`, copies the
staging triplet into the final sidecar triplet, clears `external_file_action`,
and requires staging/temp absent. CAS `RECOVERY_CLEANING` before the first tree
deletion with `cleanup_stage=CLEANING`. Delete exactly the entry at the cursor
using its persisted object and parent identities, then advance the cursor by
one session CAS that remains in `RECOVERY_CLEANING`. After a crash, only that
current row may be either exact or already absent; before advancing, all later
rows and parents must still equal the inventory. Never recapture or adopt a
remaining identity.

At full cursor, require both cleanup roots absent. A freshly minted token may
then delete or confirm absent only the exact v1 journal; its successor CAS is
`RECOVERY_JOURNAL_RETIRED` with `cleanup_stage=JOURNAL_RETIRED`. A new token may
then delete or confirm absent only the exact schema-2 fence; its successor CAS
is `RECOVERY_FENCE_RETIRED` with `cleanup_stage=FENCE_RETIRED`. A third new token
may securely remove or confirm absent only the exact sidecar; its successor CAS
is `RECOVERY_INVENTORY_RETIRED` with
`cleanup_stage=INVENTORY_RETIRED`. The only permitted physical rows are, in
order, all three present, journal absent, journal and fence absent, then all
three absent. Each physical action may crash before its successor CAS; resume
accepts only that action's exact predecessor or exact postcondition. Only from
`RECOVERY_INVENTORY_RETIRED` may the session CAS `RECOVERY_STABILIZED` with
`cleanup_stage=COMPLETE`, the full historical inventory and cursor retained as
authority, jointly null active successor triplets, and unchanged pre-apply
proof. Any premature absence, replacement, skipped stage, or extra entry is
tamper.

For the historical
`fence=ACTIVE|CANDIDATE_PLANNED|PRIOR_OWNER_PLANNED,journal=ABSENT` branch with
no attempt-owned candidate or target and exact raw sealed-snapshot equality,
every cleanup field is jointly null. `PRIOR_OWNER_PLANNED` additionally requires
its exact separate target/owner and planned-journal byte commitment to remain
unchanged. `CANDIDATE_PLANNED` additionally requires its exact candidate parent,
path, planned-journal commitment, and candidate absence. After
`RECOVERY_PREPARED`, delete only that exact fence;
absence is the sole permitted successor and authorizes only the
`RECOVERY_FENCE_RETIRED` CAS; bounded reread then authorizes
`RECOVERY_STABILIZED`. This is the only journal-less no-commit row; it never
creates the planned journal during terminal resolution.

For the historical
`fence=CANDIDATE_PLANNED|PRIOR_OWNER_PLANNED|PRIOR_OWNER_BOUND,
journal=PREPARED` branch with no attempt-owned
candidate, target, or staging tree and an exact same-attempt snapshot projection,
every cleanup field is jointly null. A separately existing target is legal only
when the fence is exactly `PRIOR_OWNER_PLANNED|PRIOR_OWNER_BOUND`, its exact
prior owner and target triplets are bound, and the journal bytes equal the
planned commitment. From
`RECOVERY_PREPARED`, delete or confirm absent only the exact attempt journal and
CAS `RECOVERY_JOURNAL_RETIRED`; the sole inter-record row is
`journal=ABSENT,fence=CANDIDATE_PLANNED|PRIOR_OWNER_PLANNED|
PRIOR_OWNER_BOUND` with the same
historical state.
A fresh token then deletes or confirms absent only
the exact fence and CASes `RECOVERY_FENCE_RETIRED`. The prior owner, if any,
must remain byte-identical throughout. Only then may bounded reread authorize
`RECOVERY_STABILIZED` with `NOT_COMMITTED`.
After bounded reread, `RECOVERY_STABILIZED` binds the exact successor attempt,
journal, owner, package, receipt, state, INI, match, and stable
`NOT_COMMITTED|COMMITTED` facts; a no-commit successor has jointly null active
attempt/journal triplets and exact raw sealed-snapshot equality after its own
journal is absent, while a committed
successor has exact FINALIZED triplets. Every later stage carries both historical and
successor evidence byte-identically. The historical result intent, result files,
acknowledgement, and terminal status never change.

Unknown fields, mixed nullability, backward stages, operation changes, a
successor with changed run/attempt/package/target/owner authority, or a second
retirement object are invalid. Active physical fence/journal bytes may advance
only through this persisted predecessor-to-successor protocol; their historical
terminal evidence remains immutable rather than being mistaken for the current
successor.

The terminal-resolution physical matrix is exhaustive:

| Branch | Eligible historical v1 phase | Stabilized row |
| --- | --- | --- |
| Commit | Every phase from `PREPARED` through `FINALIZED` | Exact `journal=FINALIZED,fence=FINALIZED` plus committed receipt/state/INI/package/match proof |
| No commit with tree | `PREPARED`, `RUNTIME_STAGED`, or `RUNTIME_VERIFIED`, plus exact same-attempt snapshot projection | Full cleanup cursor; tree, journal, fence, inventory absent; raw snapshot equals sealed |
| Candidate planned, v1 exact | Exact planned v1/fence; candidate absent; same-attempt projection exact | Journal/fence absent; cleanup null; raw snapshot sealed |
| Prior planned, v1 exact | v1 `PREPARED`, fence `PRIOR_OWNER_PLANNED`, planned bytes/target/owner exact, no tree, exact same-attempt projection | Journal/fence absent; target/owner exact; raw snapshot equals sealed |
| Prior bound, v1 exact | v1 `PREPARED`, fence `PRIOR_OWNER_BOUND`, target/owner exact, no tree, exact same-attempt projection | Journal/fence absent; target/owner exact; raw snapshot equals sealed |
| No v1, ordinary | Journal absent, fence `ACTIVE`, no attempt tree, raw snapshot equals sealed | Exact journal/fence absence; cleanup null; raw snapshot equals sealed |
| No v1, candidate planned | Journal absent; `CANDIDATE_PLANNED` path/parent/planned bytes exact; candidate absent; raw snapshot sealed | Journal/fence absent; cleanup null; raw snapshot sealed |
| No v1, prior planned | No journal; planned fence; exact target/owner; no tree; raw snapshot sealed | No journal/fence; no cleanup; exact target/owner; raw snapshot sealed |

For the commit branch, accept only a canonical successor under the existing
schema-1 monotonic predicate. Run, attempt, package, target, owner, cleanup
entries, and pre-apply fields stay immutable. The schema-2 fence remains exact
`CANDIDATE_BOUND` on the new-target route or `PRIOR_OWNER_BOUND` on the pre-existing-
target route until journal finalization; `PRIOR_OWNER_PLANNED` may advance only
to its exact bound journal first. `journal=FINALIZED,fence=<that exact
predecessor>` is the sole inter-record window before fence `FINALIZED`.

For the tree-bearing no-commit branch, remove only exact attempt-owned candidate
and target entries through the persisted sidecar and cursor, then remove the
exact v1 journal, the exact schema-2 fence, and the sidecar. Every cleanup
boundary and
`journal=ABSENT,fence=CANDIDATE_PLANNED|CANDIDATE_BOUND` is resumable from the
persisted historical variant. `CANDIDATE_PLANNED` covers create-before-bind;
`CANDIDATE_BOUND` covers an already bound/staged/verified candidate. The
v1/no-tree branch deletes its exact attempt journal before its exact
fence and never invents a tree inventory. The journal-less branch deletes only
its exact fence and likewise never invents a tree inventory.

`INI_COMMITTED`, `STATE_COMMITTED`, and `FINALIZED` can never resolve to
`NOT_COMMITTED`. At a commit-step crash, the current journal must be the
historical predecessor or one exact monotone successor. At a no-commit crash,
the cursor and remaining identities must equal the bound cleanup authority.
Fence finalization waits for journal FINALIZED; fence deletion waits for exact
no-commit journal absence. Any skipped/backward phase, changed immutable field,
mixed branch, unexpected target/staging, or fourth inter-record state remains
admission-blocking without mutation. Tests parameterize every historical phase
and each journal CAS, physical cleanup, journal deletion, and fence CAS/deletion
boundary.

Immediately after terminal CAS, `terminal_retirement=null` is the sole legal
pre-action row for success, proven not-committed, and committed mismatch; the
exact admission and action-specific evidence must still be present. Pending or
unknown also keeps it null until later stable resolution. A released stable row
requires `ADMISSION_RELEASE_AUTHORIZED`; the exact old admission still present,
its absence, or a fully valid foreign no-replace winner are its three closed
physical rows. The first is pending exact unlink, and the latter two are
complete. Earlier stages are recovery-only and block every affected writer.

`TerminalRetirementAuthorization` is a private, nonserializable, originating-
thread, stage-bound, single-use capability minted only after an exact bounded
reread of the persisted terminal session. Its action is also closed and bound:
`RECOVERY_PREPARED` authorizes only the declared monotone commit recovery, the
cleanup sidecar's current nested action—unbound-staging retirement,
materialization, or bound commit—the exact no-tree journal retirement, or the
exact journal-less fence retirement for its selected branch;
`RECOVERY_INVENTORY_BOUND` authorizes only the pure CAS into cleaning;
`RECOVERY_CLEANING` with cursor below count authorizes only the current inventory
entry, and no next token may be minted before the corresponding cursor CAS;
`RECOVERY_CLEANING` at full cursor authorizes only journal retirement;
`RECOVERY_JOURNAL_RETIRED` authorizes only fence retirement;
`RECOVERY_FENCE_RETIRED` authorizes only sidecar retirement when the branch has
one, otherwise only stabilization; and `RECOVERY_INVENTORY_RETIRED` authorizes
only stabilization. For `ack_success`, a `PREPARED` token authorizes only its
closed owning-fence or non-owning-journal action;
`ACK_JOURNAL_RETIRED` authorizes only the non-owning fence action. For stable
non-success and `RECOVERY_STABILIZED`, a fresh token authorizes only the pure
evidence-retired CAS. An `EVIDENCE_RETIRED` token authorizes only the pure CAS to
`ADMISSION_RELEASE_AUTHORIZED`; and a newly minted release-
authorized token may execute only `release_runtime_admission`, which may unlink
the exact historical admission or confirm exact absence/identity-distinct
foreign succession. Each binds the
active session bearer and exact cursor, action, operation, attempt, admission,
historical evidence, and resolved successor evidence. Every physical primitive
passes its sole callback through the matching Task-3 executor, which validates
and consumes the token before the callback observes or mutates at most one
declared persisted row, then returns one opaque
`TerminalResolutionStepReceipt` for exactly the matching
successor CAS. The final runtime-admission release instead returns its closed
disposition directly and has no receipt or successor CAS.
`advance_terminal_resolution_under_lock()` or
`advance_terminal_retirement_under_lock()` consumes that receipt before the
next token can be minted. A pure-CAS edge consumes its fresh token directly and
returns no receipt. Commit recovery is likewise decomposed into at
most one state, receipt, journal, or fence mutation per token followed by one
`physical_recovery_advanced` CAS; no token silently covers a multi-write recovery
loop. Constructed, stale, preterminal, wrong-cursor, cross-action, cross-thread,
reused, or expired authority or receipt fails before observation, mutation, or
CAS.

Use schema version 1, a 32-lowercase-hex run ID, revision 1 through 3,
`revisions_used` 0 through 2, and an exact map of logical artifact path to
standard `sha256:<64-lowercase-hex>` digest. Long-lived artifact bindings do not
store unstable filesystem identities. A transient pending action may bind the
exact predecessor identity needed for its one transition and must clear it in
the final CAS. Every artifact operation also holds
the run-root identity, captures the current child identity immediately before
its one bounded read or guarded replacement, and verifies the recorded digest
within that operation. `publication_binding` is null before publication or has
exactly `output_child_path`, `output_child_identity`,
`output_child_binding_sha256`, `revision`, `content_root_sha256`, and
`prior_current_identity`.
`revision` uses `revisions/sha256-<64-lowercase-hex>` and
`content_root_sha256` uses the standard prefixed digest; comparisons to the
existing raw lease digest use `f"sha256:{lease.content_root_sha256}"`.
`preview_requested` is an exact Boolean copied from the initial request during
session creation. It is immutable thereafter and is the sole preview-intent
authority used by finalize and resume. `terminal_status` is null until one of
the five session-backed terminal states is recorded. All three nested terminal
objects start null and are modified only by
whole-session CAS; there is no
physical write-before-binding receipt window.

The run root is `%LOCALAPPDATA%\HSConfig\runs\<run-id>`. Create it with
`secure_create_directory`; validate every ancestor and reject overlap with the
repository, runtime root, output-base root, output deck root, and installed
skill. The persistent lock lives at
`%LOCALAPPDATA%\HSConfig\locks\live-start-<run-id>.lock`, outside the closed
run contents.

Every session load, validation, artifact write/removal, binding update, and
phase or terminal-status CAS runs for its entire operation under exactly one
`ExclusiveFileLock(session_lock_path)`. Helpers that already receive the held
session lease never reacquire it. Session creation securely creates that lock
under the identity-bound locks root; every later load/resume uses
`create_if_missing=False`, so missing lock authority fails closed. The
two-process test starts from identical
expected bytes and proves exactly one process commits while the other receives
the stable session-conflict error.

`lease_live_start_session()` returns the closed `LiveStartSessionLease` shown
in the locked API layout. Public one-operation helpers may acquire that lease
once and delegate. Multi-step controller paths accept the lease explicitly and
call only `_under_lock` helpers; no raw `session_root` helper may be called from
inside an already-held session lease.

The lease is a lock/identity capability, not a cached session snapshot. Its
private nonserializable `SessionLockToken` is minted only after successful
lock, lock-path, run-root, and session-root identity verification. Private
token state binds the exact lease context, session root and identity,
session-lock path and identity, active-state nonce, and originating thread.
Every `_under_lock` reader, artifact helper, CAS mutator, terminal-cursor
reread, and acknowledgement consumer validates the exact token object, active
context, matching lease fields, and originating thread before any filesystem
observation or mutation. Constructed, mixed-token/lease, wrong-root,
wrong-lock, copied-across-context, cross-thread, or expired use fails closed. A
shallow copy shares the same bearer, creates no new authority, and expires with
it. The token is invalidated in `finally` before the session lock is released.
Every `_under_lock` mutator has this shape:

```python
def update_session_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    update: LiveStartSessionUpdate,
) -> LiveStartSession: ...
```

It verifies current session identity, canonical bytes, and digest against
`expected_session`, performs one CAS, and returns the newly sealed successor
cursor.
The controller must assign and pass that returned value into every following
CAS. Under-lock helpers may not silently reload a new predecessor or mutate a
cursor hidden inside the frozen lease. The full-chain test covers
`PUBLICATION_COMMITTED -> APPLY_STARTED -> APPLY_COMMITTED -> RUNTIME_MATCHED`
and terminal result binding under one token and an explicit cursor at each edge.

Implement `atomic_write_reserved_bytes()` in `atomic_io.py`. It must accept an
expected file identity and expected SHA-256, open the current file without
following links, compare exact bytes, write only the deterministic reserved
sibling `.<leaf>.live-start-atomic.tmp`, flush it, and replace only while the
parent identity remains unchanged. Use this reserved-sibling primitive only for
`session.json`, the two result-intent-derived result leaves, and true legacy
paths that make no cross-process successor-identity claim. Every canonical
receipt is an authority artifact and uses its persisted staged
`external_file_action`.

Lock the neutral Task-3 API as:

```python
@dataclass(frozen=True, slots=True)
class AtomicPublishedBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str

AtomicWriteFaultPoint = Literal[
    "temp_created",
    "temp_partial",
    "temp_full",
    "temp_flushed",
    "before_replace",
    "after_replace",
]
AtomicWriteFaultHook = Callable[[AtomicWriteFaultPoint], None]

def no_atomic_write_fault(_point: AtomicWriteFaultPoint) -> None:
    pass

def atomic_write_reserved_bytes(
    *,
    path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    expected_predecessor_identity: PathIdentity | None,
    expected_predecessor_sha256: str | None,
    maximum_size: int,
    fault_hook: AtomicWriteFaultHook = no_atomic_write_fault,
) -> AtomicPublishedBytes: ...

@dataclass(frozen=True, slots=True)
class PublishedNoReplaceBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str

@dataclass(frozen=True, slots=True)
class MaterializedStagingBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str

STAGING_MATERIALIZE_FAULT_POINT = "after_staging_flush_before_identity_return"
NO_REPLACE_COMMIT_FAULT_POINT = "after_bound_staging_commit_before_return"
NO_REPLACE_POSIX_LINK_FAULT_POINT = (
    "after_bound_staging_posix_link_before_unlink"
)

# package_io.py
SiblingNoReplaceFaultPoint = Literal[
    "after_posix_link_before_source_unlink",
]
SiblingNoReplaceFaultHook = Callable[[SiblingNoReplaceFaultPoint], None]

def no_sibling_no_replace_fault(
    _point: SiblingNoReplaceFaultPoint,
) -> None:
    pass

def secure_commit_sibling_no_replace(
    *,
    source_path: Path,
    target_path: Path,
    expected_source_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    fault_hook: SiblingNoReplaceFaultHook = no_sibling_no_replace_fault,
) -> PathIdentity: ...

# atomic_io.py
def atomic_materialize_staging_bytes(
    *,
    staging_path: Path,
    inner_temp_path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    fault_hook: FaultHook = no_fault,
) -> MaterializedStagingBytes: ...

def atomic_commit_bound_staging_no_replace(
    *,
    path: Path,
    staging_path: Path,
    expected_staging_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
    expected_parent_identity: PathIdentity,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes: ...
```

Task 3 moves the platform-specific no-replace move/
`renameat2(RENAME_NOREPLACE)`/hard-link core into `package_io.py`, then exposes
the two shared staged-authority primitives from `atomic_io.py`. Materialization
writes and flushes only the deterministic inner temp and staging path; it returns
the staging identity only after a complete reread. The no-replace commit accepts
only that persisted identity and an unchanged parent, never chooses a live
identity, and converges the POSIX same-identity two-link intermediate to one
final `nlink=1` name. These APIs and their fault points are green before the
first Task-3 terminal-cleanup inventory helper uses them.

`package_io.py` owns the cycle-free `SiblingNoReplaceFaultHook`; it does not
import `FaultHook`, `LiveStartFaultHook`, `atomic_io.py`, or controller code.
The POSIX hard-link fallback invokes
`after_posix_link_before_source_unlink` only after a no-follow reread proves
the parent unchanged, both sibling names equal to the exact persisted staging
identity and bytes, and the shared identity has total `nlink == 2`, and
immediately before unlinking the staging name. Windows, a successful
`renameat2(RENAME_NOREPLACE)`, final-only resume, and every rejection path never
invoke this point. `atomic_commit_bound_staging_no_replace()` adapts that one
local callback to its caller's generic
`after_bound_staging_posix_link_before_unlink` stage; the separate
`after_bound_staging_commit_before_return` stage fires only after convergence.
A hard kill at the internal POSIX point therefore leaves exactly the permitted
two-name/one-bound-identity state. Resume accepts only that exact state,
securely unlinks the staging name, flushes the unchanged parent, and proves the
final name still has the persisted identity, exact bytes, and `nlink == 1`.
No first identity capture, byte-only adoption, or second mutation is allowed.

Task 3 keeps `atomic_write_reserved_bytes()` private to the special `session.json`
CAS, the closed two-leaf result-intent exception, and true legacy paths that
make no cross-process successor-identity claim. Tasks 8 and 9 do not use it for
controller authority files; they reuse the Task-3 staged primitives and the
intervening session CAS is normative.

Before the closed run-layout check, and only under the active session lease plus
exact session-parent identity, reconcile the one deterministic session-CAS temp.
If durable `session.json` is still the exact predecessor, the temp may be
partial; capture it only as a verified-delete guard, securely remove it, and
retry the CAS from the predecessor without parsing or adopting temp bytes. If
durable `session.json` is the exact self-digested successor, the temp must be
absent or byte-identical and is securely removed. Every other canonical run
artifact uses its persisted `external_file_action`, staged binding, and commit
matrix. An oversized file, directory, reparse point, hard link, ADS, alias,
second temp, unknown name, or successor-plus-different temp is tamper. Real
subprocess-kill tests cover session temp creation, partial/full write, flush,
immediately before replace, and immediately after replace, and separately cover
all staged controller-artifact boundaries.

### Step 3.3: Implement invalidation and revision budget

The initial candidate uses `candidate_revision=1` and consumes no revision.
Each validation failure or reviewer revision request consumes one shared
revision and advances the next allowed candidate revision. Revision 3 is the
last candidate. A third request stops without publication.

Use this closed transition table. A bound rejected candidate or
`revision_requested` review is diagnostic resume evidence, never durable
compile authority.

| Event | Phase transition | Durable discriminator | Resume action |
| --- | --- | --- | --- |
| Initial draft | `INPUT_FROZEN -> CANDIDATE_DRAFTED` | Bound candidate; no receipts | Validate that draft first |
| Technical success | `CANDIDATE_DRAFTED -> CANDIDATE_VALIDATED` | Bound valid receipt | Revalidate and review |
| Technical failure | `CANDIDATE_DRAFTED -> CANDIDATE_DRAFTED` | Rejected candidate; no receipt; one charge | Repeat findings; await next revision |
| Replacement draft | `CANDIDATE_DRAFTED -> CANDIDATE_DRAFTED` | New candidate; superseded artifacts cleared | Validate only the new draft |
| Review approval | `CANDIDATE_VALIDATED -> REVIEW_APPROVED` | Bound approved review and receipt | Revalidate and continue |
| Review revision | `CANDIDATE_VALIDATED -> CANDIDATE_DRAFTED` | Bound request review; no receipt; one charge | Repeat rows; await next revision |
| Budget exhausted | same phase plus `FAILED_PRESERVED` | Current evidence; no downstream authority | Return terminal result only |

Before each CAS, initial/replacement candidate bytes bind the exact context,
candidate ID, and expected revision. Success receipts are flushed, reread, and
bound. Failure/request transitions increment `revisions_used` in the same CAS
that binds their evidence, so resume cannot charge twice. Budget exhaustion
retains current candidate/review evidence but creates no downstream receipt or
publication.

Installing a replacement draft requires the previous physical files to match
their recorded digests under the held run-root identity. Capture current child
identities for each guarded replacement or removal. First bind the exact
pending transition, atomically replace the candidate as its primary commit
point, then remove only the listed superseded candidate-validation, review, and
downstream artifacts. The final session CAS binds the new revision, clears all
superseded bindings, and clears the transition together. `CANDIDATE_DRAFTED`
may therefore contain
either an unvalidated/rejected current draft or a revision-request review; the
exact artifact set disambiguates those two closed variants. Any other file
combination, backward phase edge, revision jump, or missing binding is tamper,
not a resume guess.

### Step 3.4: Verify and commit

Run all focused nodes from Step 3.1 and these CAS adjacency controls:

```powershell
python -B -m pytest `
  tests/test_atomic_io.py::test_atomic_write_optional_expected_parent_identity_rejects_substitution `
  tests/test_atomic_io.py::test_atomic_write_rejects_identity_changes_before_replace `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/package_io.py `
  tests/test_live_start_session.py `
  tests/test_atomic_io.py `
  tests/test_package_io.py
git diff --check
git add -- `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/package_io.py `
  tests/test_live_start_session.py `
  tests/test_atomic_io.py `
  tests/test_package_io.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: add resumable live start sessions"
```

---

## Task 4: Define Schema-2 Context, Lead Candidate, and Independent Review

**Owned files**

- Create: `src/hsconfig/starter_review.py`
- Create: `tests/test_starter_review.py`
- Modify: `src/hsconfig/starter_contract.py`
- Modify: `src/hsconfig/starter_context.py`
- Modify: `src/hsconfig/starter_candidate.py`
- Modify: `src/hsconfig/starter_document.py`
- Modify: `tests/test_starter_contract.py`
- Modify: `tests/test_starter_context.py`
- Modify: `tests/test_starter_candidate.py`

### Step 4.1: Preserve legacy V1 and add versioned constants

First add a RED assertion that the existing constants and legacy fixture still
load unchanged while the new constants are available:

```python
assert LEGACY_STARTER_SCHEMA_VERSION == 1
assert SINGLE_CANDIDATE_STARTER_SCHEMA_VERSION == 2
assert STARTER_SCHEMA_VERSION == LEGACY_STARTER_SCHEMA_VERSION
assert SINGLE_CANDIDATE_REVIEW_REPORT_FILENAMES == (
    "input_snapshot_manifest.json",
    "starter_context.json",
    "starter_config_candidate.json",
    "starter_config_review.json",
)
```

Add versioned field sets; do not alter the legacy V1 sets. Define
`STARTER_REVIEW_FIELDS` exactly as approved and keep legacy critic confidence
`high|low` separate from review confidence `high|limited`.

Run:

```powershell
python -B -m pytest `
  tests/test_starter_contract.py::test_legacy_and_single_candidate_contracts_are_versioned_and_disjoint `
  tests/test_starter_contract.py::test_load_starter_document_rejects_untrusted_noncanonical_bytes `
  -q -p no:cacheprovider
```

Expected RED: the new versioned constants do not exist.

### Step 4.2: Build and validate the schema-2 context

Add `build_single_candidate_starter_context(inputs: FrozenCompilerInputs)` and
make its output exactly match the approved schema-2 top-level fields. It must
project from the frozen blobs only and bind
`input_snapshot_manifest_sha256`. Do not call a fetcher, catalog lookup,
runtime-baseline loader, or `build_starter_context()` internally.

Add and run:

```powershell
python -B -m pytest `
  tests/test_starter_context.py::test_schema_two_context_binds_frozen_snapshot_and_exact_cards `
  tests/test_starter_context.py::test_schema_two_context_never_reobserves_sources_cards_or_baseline `
  tests/test_starter_context.py::test_schema_two_context_rejects_unknown_fields_and_snapshot_drift `
  -q -p no:cacheprovider
```

Expected RED: V2 context validation rejects schema version 2 and the snapshot
digest field.

### Step 4.3: Validate one lead candidate

Dispatch `validate_starter_candidate()` by document schema. The V1 path stays
byte-compatible. The V2 path requires:

```python
candidate_id == "lead"
strategy_summary["role"] == "lead_strategist"
candidate_revision in {1, 2, 3}
```

Retain all current nested Mulligan, exact 38-key GlobalValues, CardID owner,
combo, disposition, rationale, assumption, numeric, condition, and self-digest
checks. Require exactly one disposition for every unique physical main-deck
CardID; repeated deck counts do not create duplicate disposition rows.

Add and run:

```powershell
python -B -m pytest `
  tests/test_starter_candidate.py::test_schema_two_lead_candidate_closes_identity_and_all_runtime_surfaces `
  tests/test_starter_candidate.py::test_schema_two_candidate_requires_exact_unique_physical_card_coverage `
  tests/test_starter_candidate.py::test_schema_two_candidate_rejects_old_roles_ids_and_revision_four `
  tests/test_starter_candidate.py::test_schema_two_candidate_retains_numeric_and_owner_fail_closed_boundaries `
  -q -p no:cacheprovider
```

Expected RED: `lead` and `lead_strategist` are rejected by the legacy role
contract.

### Step 4.4: Implement the review contract

Use these exact limits:

```python
STARTER_REVIEW_MAX_BYTES = 64 * 1024
STARTER_REVIEW_MAX_REQUESTS = 32
STARTER_REVIEW_ID_MAX_CHARS = 64
STARTER_REVIEW_SUMMARY_MAX_CHARS = 2_000
STARTER_REVIEW_REQUEST_CODE_MAX_CHARS = 64
STARTER_REVIEW_REQUEST_MESSAGE_MAX_CHARS = 500
REVIEW_STATUSES = frozenset({"approved", "revision_requested"})
REVIEW_CONFIDENCE = frozenset({"high", "limited"})
REVIEW_TARGETS = frozenset(
    {
        "whole_candidate",
        "strategy_summary",
        "mulligan",
        "globalvalues",
        "card_rules",
        "combo",
        "card_dispositions",
        "rule_rationales",
        "assumptions",
    }
)
```

`validate_starter_review()` reseals context and candidate first, then checks
exact context digest, candidate ID, revision, and candidate digest. Approved
reviews require an empty request list; revision requests require at least one
row. Preserve list order in the digest and reject duplicate JSON keys rather
than treating rows as a set.

Require `review_id` and every request `code` to be 1 through 64 characters in
the closed lowercase ASCII identifier grammar. Require `review_summary` to be
safe prose of 1 through 2,000 characters and every request `message` to be safe
prose of 1 through 500 characters. Every request row has exactly `code`,
`target`, and `message`. Add table-driven boundary cases at empty, maximum, and
maximum-plus-one lengths; reject uppercase, Unicode lookalikes, control/path/
URL transport text, wrong types, unknown row fields, and noncanonical order.

Add and run:

```powershell
python -B -m pytest `
  tests/test_starter_review.py::test_approved_review_binds_context_candidate_revision_and_digest `
  tests/test_starter_review.py::test_limited_approval_remains_valid_and_visible `
  tests/test_starter_review.py::test_revision_request_requires_closed_ordered_rows `
  tests/test_starter_review.py::test_review_rejects_wrong_digest_revision_status_confidence_or_size `
  tests/test_starter_review.py::test_review_rejects_forged_context_or_candidate_dataclass `
  tests/test_starter_review.py::test_review_identifier_summary_and_request_row_boundaries `
  -q -p no:cacheprovider
```

Expected RED: import failure for `hsconfig.starter_review`.

### Step 4.5: Verify legacy adjacency and commit

```powershell
python -B -m pytest `
  tests/test_starter_decision.py::test_valid_selection_accepts_shared_initial_revisions_and_one_repair `
  tests/test_starter_candidate.py::test_runtime_intent_digest_canonicalizes_all_numeric_semantics `
  tests/test_starter_context.py::test_sealed_starter_context_validator_accepts_canonical_shadowpriest `
  tests/test_starter_contract.py::test_fixed_starter_sibling_names_reject_an_unexpected_name `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/starter_contract.py `
  src/hsconfig/starter_context.py `
  src/hsconfig/starter_candidate.py `
  src/hsconfig/starter_document.py `
  src/hsconfig/starter_review.py `
  tests/test_starter_contract.py `
  tests/test_starter_context.py `
  tests/test_starter_candidate.py `
  tests/test_starter_review.py
git diff --check
git add -- `
  src/hsconfig/starter_contract.py `
  src/hsconfig/starter_context.py `
  src/hsconfig/starter_candidate.py `
  src/hsconfig/starter_document.py `
  src/hsconfig/starter_review.py `
  tests/test_starter_contract.py `
  tests/test_starter_context.py `
  tests/test_starter_candidate.py `
  tests/test_starter_review.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: define single candidate review authority"
```

---

## Task 5: Dispatch Legacy and New Optimized Authority Explicitly

**Owned files**

- Create: `src/hsconfig/optimized_start_authority.py`
- Create: `tests/test_optimized_start_authority.py`
- Modify: `src/hsconfig/configuration_mode.py`
- Modify: `src/hsconfig/visionai_registry.py`
- Modify: `src/hsconfig/package_request.py`
- Modify: `src/hsconfig/starter_compiler.py`
- Modify: `tests/starter_fixtures.py`
- Modify: `tests/test_starter_decision.py`
- Modify: `tests/test_package_request.py`

### Step 5.1: Write RED manifest-dispatch tests

Add these exact tests:

- `test_conservative_manifest_forbids_optimized_authority_discriminator`
- `test_legacy_optimized_manifest_omits_discriminator_and_requires_five_docs`
- `test_new_optimized_manifest_requires_exact_single_candidate_discriminator`
- `test_unknown_mixed_extra_and_downgraded_authority_sets_fail_closed`
- `test_legacy_five_document_fixture_loads_byte_unchanged`

The dispatch expectations are exact:

```python
assert optimized_start_authority_schema_from_manifest(
    {"configuration_mode": "LLM_OPTIMIZED_START"}
) == "legacy_five_doc"
assert optimized_start_authority_schema_from_manifest(
    {
        "configuration_mode": "LLM_OPTIMIZED_START",
        "optimized_start_authority_schema": "single_candidate_review_v1",
    }
) == "single_candidate_review_v1"
```

The conservative case must reject the discriminator even when its value is
otherwise valid. Unknown strings, null, booleans, and numbers fail with the
same stable authority-schema error.

Run:

```powershell
python -B -m pytest `
  tests/test_optimized_start_authority.py::test_conservative_manifest_forbids_optimized_authority_discriminator `
  tests/test_optimized_start_authority.py::test_legacy_optimized_manifest_omits_discriminator_and_requires_five_docs `
  tests/test_optimized_start_authority.py::test_new_optimized_manifest_requires_exact_single_candidate_discriminator `
  tests/test_optimized_start_authority.py::test_unknown_mixed_extra_and_downgraded_authority_sets_fail_closed `
  tests/test_optimized_start_authority.py::test_legacy_five_document_fixture_loads_byte_unchanged `
  -q -p no:cacheprovider
```

Expected RED: the discriminator and new report-set resolver do not exist.

### Step 5.2: Implement one manifest authority resolver

Add to `configuration_mode.py`:

```python
OptimizedStartAuthoritySchema = Literal[
    "legacy_five_doc",
    "single_candidate_review_v1",
]
SINGLE_CANDIDATE_REVIEW_V1 = "single_candidate_review_v1"

def optimized_start_authority_schema_from_manifest(
    manifest: Mapping[str, Any],
) -> OptimizedStartAuthoritySchema | None:
    mode = configuration_mode_from_manifest(manifest)
    present = "optimized_start_authority_schema" in manifest
    if mode == CONSERVATIVE:
        if present:
            raise ValueError("optimized_start_authority_schema_forbidden")
        return None
    if not present:
        return "legacy_five_doc"
    if manifest["optimized_start_authority_schema"] != SINGLE_CANDIDATE_REVIEW_V1:
        raise ValueError("optimized_start_authority_schema_invalid")
    return SINGLE_CANDIDATE_REVIEW_V1
```

`configuration_mode.py` is the sole runtime definition of the alias.
`optimized_start_authority.py` imports and re-exports it; it must not define a
second alias or import back from the authority module. This keeps normal
imports acyclic and Ruff-clean without a runtime `TYPE_CHECKING` dependency.

Split `visionai_registry.py` constants without changing the legacy tuple:

```python
LEGACY_OPTIMIZED_START_REPORT_PATHS = (
    "reports/optimized_start/starter_context.json",
    "reports/optimized_start/candidate-1.json",
    "reports/optimized_start/candidate-2.json",
    "reports/optimized_start/candidate-3.json",
    "reports/optimized_start/starter_config_decision.json",
)
SINGLE_CANDIDATE_REVIEW_REPORT_PATHS = (
    "reports/optimized_start/input_snapshot_manifest.json",
    "reports/optimized_start/starter_context.json",
    "reports/optimized_start/starter_config_candidate.json",
    "reports/optimized_start/starter_config_review.json",
)
ALL_OPTIMIZED_START_REPORT_PATHS = frozenset(
    (*LEGACY_OPTIMIZED_START_REPORT_PATHS, *SINGLE_CANDIDATE_REVIEW_REPORT_PATHS)
)
```

Keep `OPTIMIZED_START_REPORT_PATHS` as an alias to the legacy tuple until all
legacy consumers have migrated in Task 7. Add
`optimized_start_report_paths_for_manifest()` as the only new resolver.

### Step 5.3: Load one validated single-candidate approval

`load_optimized_start_authority()` first resolves the schema and exact physical
report set, then delegates either to the unchanged legacy selection loader or
to the new V2 context/candidate/review validators. It must reseal all four new
documents and return `ValidatedSingleStarterApproval` only when:

- snapshot digest equals the context binding;
- context digest equals candidate and review bindings;
- candidate ID is `lead` in both documents;
- candidate revision is identical;
- candidate digest equals the review binding;
- review is approved with an empty request list;
- confidence is `high` or `limited`.

Add and run:

```powershell
python -B -m pytest `
  tests/test_optimized_start_authority.py::test_single_candidate_approval_reseals_every_document `
  tests/test_optimized_start_authority.py::test_single_candidate_approval_rejects_cross_document_rebinding `
  tests/test_optimized_start_authority.py::test_revision_requested_review_is_not_durable_compile_authority `
  -q -p no:cacheprovider
```

Expected RED: the new loader is absent.

### Step 5.4: Extend the immutable request without overloading legacy names

Keep `starter_selection: ValidatedStarterSelection | None` for legacy
compatibility. Add
`starter_approval: ValidatedSingleStarterApproval | None`. Enforce:

- conservative: both are null;
- optimized legacy: selection set, approval null, frozen inputs null;
- optimized new: selection null, approval set, frozen inputs set;
- both or neither on optimized requests: fail closed.

Add a read-only property:

```python
@property
def optimized_start_authority_schema(
    self,
) -> OptimizedStartAuthoritySchema | None:
    if self.starter_selection is not None:
        return "legacy_five_doc"
    if self.starter_approval is not None:
        return "single_candidate_review_v1"
    return None
```

Do not make `resolve_package_request()` fabricate new approvals. The normal
controller constructs the new request directly from frozen values; raw
`configure --optimized-start --starter-decision-json` remains the legacy
expert route.

Run:

```powershell
python -B -m pytest `
  tests/test_package_request.py::test_new_optimized_request_requires_frozen_single_candidate_approval `
  tests/test_package_request.py::test_conservative_and_legacy_requests_keep_existing_constructor_contract `
  tests/test_package_request.py::test_optimized_request_rejects_mixed_authority_objects `
  -q -p no:cacheprovider
```

### Step 5.5: Verify and commit

```powershell
python -B -m pytest `
  tests/test_starter_decision.py::test_valid_selection_accepts_shared_initial_revisions_and_one_repair `
  tests/test_starter_compiler.py::test_lower_optimized_start_builds_one_neutral_frozen_authority `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/optimized_start_authority.py `
  src/hsconfig/configuration_mode.py `
  src/hsconfig/visionai_registry.py `
  src/hsconfig/package_request.py `
  src/hsconfig/starter_compiler.py `
  tests/test_optimized_start_authority.py `
  tests/starter_fixtures.py `
  tests/test_starter_decision.py `
  tests/test_package_request.py
git diff --check
git add -- `
  src/hsconfig/optimized_start_authority.py `
  src/hsconfig/configuration_mode.py `
  src/hsconfig/visionai_registry.py `
  src/hsconfig/package_request.py `
  src/hsconfig/starter_compiler.py `
  tests/test_optimized_start_authority.py `
  tests/starter_fixtures.py `
  tests/test_starter_decision.py `
  tests/test_package_request.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: dispatch optimized authority schemas"
```

---

## Task 6: Compile the New Authority Without Conservative Reconstruction

**Atomic unit with Task 7:** The real renderer always invokes strict package
validation and derivation construction before returning. Therefore Tasks 6 and
7 have one writer, one frozen combined diff, one pair of independent reviews,
and one signed commit at Step 7.6. Task 6 intentionally records the renderer
RED caused by the still-legacy strict/derivation layer and must not be staged or
committed on its own.

**Owned files**

- Modify: `src/hsconfig/starter_compiler.py`
- Modify: `src/hsconfig/package_compiler.py`
- Modify: `src/hsconfig/package_assembler.py`
- Modify: `src/hsconfig/package_render_authority.py`
- Modify: `src/hsconfig/report_ownership.py`
- Modify: `tests/test_starter_compiler.py`
- Modify: `tests/test_package_compiler.py`
- Modify: `tests/test_package_render_authority.py`
- Modify: `tests/test_output_ownership_manifest.py`

### Step 6.1: Write the RED no-conservative-call test

Add these exact tests:

- `test_single_candidate_compiler_never_calls_conservative_compiler`
- `test_single_candidate_compile_uses_only_frozen_blob_and_starter_bytes`
- `test_single_candidate_compile_emits_exact_four_authority_reports`
- `test_single_candidate_authority_accounts_for_every_physical_card`
- `test_single_candidate_compile_is_byte_deterministic_across_temp_roots`

The first test monkeypatches
`package_compiler._compile_conservative_package_decisions` to raise and then
compiles a valid V2 approval successfully. The frozen-input test changes the
source fixtures, clock, runtime baseline, and catalog after request creation
and requires identical compiled bytes.

The physical-card test asserts exactly one `card_dispositions` row for every
unique physical main-deck CardID. It does not require a runtime CardID file for
a deliberately unconfigured card. Runtime files are required only for actual
validated configured rules and must use their correct runtime owners.

Run:

```powershell
python -B -m pytest `
  tests/test_package_compiler.py::test_single_candidate_compiler_never_calls_conservative_compiler `
  tests/test_package_compiler.py::test_single_candidate_compile_uses_only_frozen_blob_and_starter_bytes `
  tests/test_starter_compiler.py::test_single_candidate_compile_emits_exact_four_authority_reports `
  tests/test_starter_compiler.py::test_single_candidate_authority_accounts_for_every_physical_card `
  tests/test_package_render_authority.py::test_single_candidate_compile_is_byte_deterministic_across_temp_roots `
  -q -p no:cacheprovider
```

Expected RED: dispatch either lacks the new authority or reaches the patched
conservative compiler.

### Step 6.2: Add neutral single-candidate lowering

Add a separate type; do not overload the legacy selection field names:

```python
@dataclass(frozen=True, slots=True)
class SingleCandidateStartLowering:
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    card_behavior_plan: FrozenJsonDocument
    optimized_projections: tuple[tuple[str, StarterDocument], ...]
    compiler_state: FrozenJsonDocument
    authority_id: str
```

Implement `lower_single_candidate_start(request, approval)`. Its authority ID
is `starter:<candidate-content-sha256>`. It builds GlobalValues once from the
candidate's complete desired state, groups validated card rows by runtime
CardID, and projects exactly snapshot, context, candidate, and review under
`reports/optimized_start/`.

The `compiler_state` must be built from the V2 context and candidate only. It
contains the exact existing keys consumed by `compile_package()` but derives
them as follows:

- deck identity, cards, linked owners, and card metadata from the frozen
  context;
- source bundle, evidence, claims, and visible gaps from frozen context
  source fields;
- baseline from the frozen context baseline;
- Mulligan, CardID, Combo, disposition, and desired GlobalValues from the
  validated candidate;
- empty or diagnostic-only source authority where sources are weak;
- current policy provenance only when its exact bytes were frozen in the
  input snapshot.

No resolver, fetcher, date function, catalog, or runtime read is reachable.

### Step 6.3: Add a three-way package compiler dispatch

Keep `compile_package_decisions(request)` public and dispatch exactly:

```python
schema = request.optimized_start_authority_schema
if schema is None:
    return _compile_conservative_package_decisions(request)
if schema == "legacy_five_doc":
    return _compile_legacy_optimized_package_decisions(request)
if schema == "single_candidate_review_v1":
    return _compile_single_candidate_review_package_decisions(request)
raise ValueError("optimized_start_authority_schema_invalid")
```

Rename the current `_compile_optimized_package_decisions()` to
`_compile_legacy_optimized_package_decisions()` without changing its output.
The new function consumes `SingleCandidateStartLowering.compiler_state`
directly and must not call the conservative function.

When `compile_package()` builds `reports/input_manifest.json`, add
`optimized_start_authority_schema="single_candidate_review_v1"` only for the
new path. Conservative remains without the field; legacy optimized remains
implicitly absent. Ensure the new four authority projections are owned by
`PACKAGE_COMPILER` and no obsolete candidate path appears.

### Step 6.4: Render both versioned authority sets canonically

In `package_render_authority.py`, replace the legacy-only membership check with
`ALL_OPTIMIZED_START_REPORT_PATHS`. Both schema versions retain their already
sealed canonical bytes. The surrounding package remains generated through the
same immutable authority renderer and manifest.

Run:

```powershell
python -B -m pytest `
  tests/test_package_render_authority.py::test_single_candidate_authority_bytes_are_not_pretty_rendered_again `
  tests/test_output_ownership_manifest.py::test_single_candidate_report_ownership_is_mode_and_schema_bound `
  tests/test_package_compiler.py::test_pre_authority_owner_mapping_is_exact_and_rejects_swaps `
  -q -p no:cacheprovider
```

Expected intermediate RED: the real renderer reaches the still-legacy strict
report-set or derivation-schema check. Do not stub either check and do not make
Task 6 a partial public GREEN path; continue directly into Task 7.

### Step 6.5: Verify legacy controls without committing

```powershell
python -B -m pytest `
  tests/test_starter_compiler.py::test_compile_package_uses_selected_candidate_for_every_runtime_authority `
  tests/test_package_render_authority.py::test_optimized_reports_preserve_all_five_frozen_canonical_bytes `
  tests/test_output_ownership_manifest.py::test_optimized_report_ownership_is_mode_bound `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/starter_compiler.py `
  src/hsconfig/package_compiler.py `
  src/hsconfig/package_assembler.py `
  src/hsconfig/package_render_authority.py `
  src/hsconfig/report_ownership.py `
  tests/test_starter_compiler.py `
  tests/test_package_compiler.py `
  tests/test_package_render_authority.py `
  tests/test_output_ownership_manifest.py
git diff --check
```

Require the legacy controls GREEN, but leave every Task-6 path unstaged. The
new renderer nodes remain the explicit RED handed to Task 7.

---

## Task 7: Bind Schema-4 Derivation, Strict Validation, Summary, and Apply Gate

This is Part B of the atomic Task-6/7 unit. Its final GREEN and commit include
all Task-6 compiler/renderer paths and tests.

**Owned files**

- Modify: `src/hsconfig/package_derivation_receipt.py`
- Modify: `src/hsconfig/strict_package_validation.py`
- Modify: `src/hsconfig/validate_package.py`
- Modify: `src/hsconfig/apply_gate.py`
- Modify: `src/hsconfig/operator_summary_inputs.py`
- Modify: `src/hsconfig/operator_summary_evaluator.py`
- Modify: `src/hsconfig/configure_workflow.py`
- Modify: `tests/test_package_derivation_receipt.py`
- Modify: `tests/test_strict_package_validation.py`
- Modify: `tests/test_validate_package.py`
- Modify: `tests/test_apply_gate.py`
- Modify: `tests/test_operator_summary_inputs.py`
- Modify: `tests/test_operator_summary.py`
- Modify: `tests/test_configure_optimized_start.py`

### Step 7.1: Write RED schema-4 derivation tests

Add these exact tests:

- `test_schema_four_receipt_binds_snapshot_candidate_revision_review_and_confidence`
- `test_schema_four_receipt_rejects_each_authority_document_tamper`
- `test_legacy_schema_three_receipt_remains_valid`
- `test_receipt_schema_is_selected_only_from_manifest_discriminator`

Use this exact new constant:

```python
SINGLE_CANDIDATE_REVIEW_DERIVATION_RECEIPT_SCHEMA_VERSION = 4
```

The new derivation payload projects exactly:

```text
optimized_start_authority_schema
input_snapshot_manifest_sha256
candidate_sha256
candidate_revision
review_sha256
review_status
confidence
```

These are starter self-digests, not the receipt input hashes of the complete
sealed documents. The receipt's authoritative input map still hashes the full
canonical bytes of all four authority files.

Run:

```powershell
python -B -m pytest `
  tests/test_package_derivation_receipt.py::test_schema_four_receipt_binds_snapshot_candidate_revision_review_and_confidence `
  tests/test_package_derivation_receipt.py::test_schema_four_receipt_rejects_each_authority_document_tamper `
  tests/test_package_derivation_receipt.py::test_legacy_schema_three_receipt_remains_valid `
  tests/test_package_derivation_receipt.py::test_receipt_schema_is_selected_only_from_manifest_discriminator `
  -q -p no:cacheprovider
```

Expected RED: optimized packages always select schema 3 and expect five files.

### Step 7.2: Implement schema-aware receipt construction and replay

Update `_receipt_schema_for()` and `_receipt_schema_for_path()` to resolve the
manifest discriminator. Refactor the current selected-candidate/decision
helper into two versioned functions:

```python
def legacy_optimized_start_derivation_digests(...) -> dict[str, str]: ...

def single_candidate_review_derivation(
    ...,
) -> dict[str, str | int]: ...
```

Both path and `PackageView` variants must validate the exact physical report
set before reading documents. Update authoritative input digests to include
the schema-selected paths only. A mixed set cannot be reauthorized by
refreshing the receipt.

### Step 7.3: Make strict validation schema-aware

Change `_optimized_start_report_set_errors()` to accept the parsed manifest,
resolve its exact report tuple, and report stable errors for missing, extra,
mixed, or invalid authority. `validate_package.py` must use the same resolver,
not maintain a second list.

Add and run:

```powershell
python -B -m pytest `
  tests/test_strict_package_validation.py::test_strict_validation_accepts_exact_single_candidate_report_set `
  tests/test_strict_package_validation.py::test_strict_validation_rejects_mixed_downgraded_and_extra_authority `
  tests/test_validate_package.py::test_public_validate_dispatches_new_and_legacy_optimized_authority `
  -q -p no:cacheprovider
```

Expected RED: strict validation expects the old five paths.

### Step 7.4: Recompute schema-4 authority at the apply gate

Update `_package_derivation_reasons()` so expected receipt schema is:

- 2 for conservative;
- 3 for legacy optimized;
- 4 for single-candidate review.

Invalid or inconsistent starter reports return
`optimized_start_derivation_invalid`. A valid report/receipt chain with
missing or wrong summary projections returns
`operator_summary_derivation_inconsistent`. Never accept self-reported summary
fields without recomputing all four authority documents.

Add and run:

```powershell
python -B -m pytest `
  tests/test_apply_gate.py::test_apply_gate_allows_valid_single_candidate_review_package `
  tests/test_apply_gate.py::test_apply_gate_rejects_schema_four_summary_or_receipt_tamper `
  tests/test_apply_gate.py::test_apply_gate_rejects_mixed_or_downgraded_single_candidate_authority `
  tests/test_apply_gate.py::test_apply_gate_allows_valid_llm_optimized_start `
  -q -p no:cacheprovider
```

Expected RED: schema 4 is unsupported or the report-set check fails first.

### Step 7.5: Project the exact new authority in operator and configure summaries

`operator_summary.package_derivation` and
`configure_summary.optimized_start` must each include:

```text
optimized_start_authority_schema
input_snapshot_manifest_sha256
candidate_sha256
candidate_revision
review_sha256
review_status
confidence
```

Keep legacy selected-candidate and decision fields only on the legacy branch.
For new packages, do not emit `candidate_ids`, ranking, selected candidate ID,
critic identity, or `low` confidence. Preserve `limited` literally and expose
one concise limitation in the user-facing projection.

Add and run:

```powershell
python -B -m pytest `
  tests/test_operator_summary_inputs.py::test_replay_projects_exact_single_candidate_derivation `
  tests/test_operator_summary.py::test_operator_summary_keeps_limited_review_visible `
  tests/test_configure_optimized_start.py::test_configure_summary_binds_single_candidate_review_authority `
  tests/test_configure_optimized_start.py::test_legacy_configure_summary_remains_byte_compatible `
  -q -p no:cacheprovider
```

### Step 7.6: Verify and commit

Run every focused group from Steps 6.1, 6.4, 7.1, 7.3, 7.4, and 7.5 once.
Every new compiler, renderer, strict-validation, derivation, summary, and apply
node must now be GREEN through the real renderer. Then run:

```powershell
python -B -m ruff check `
  src/hsconfig/starter_compiler.py `
  src/hsconfig/package_compiler.py `
  src/hsconfig/package_assembler.py `
  src/hsconfig/package_render_authority.py `
  src/hsconfig/report_ownership.py `
  src/hsconfig/package_derivation_receipt.py `
  src/hsconfig/strict_package_validation.py `
  src/hsconfig/validate_package.py `
  src/hsconfig/apply_gate.py `
  src/hsconfig/operator_summary_inputs.py `
  src/hsconfig/operator_summary_evaluator.py `
  src/hsconfig/configure_workflow.py `
  tests/test_starter_compiler.py `
  tests/test_package_compiler.py `
  tests/test_package_render_authority.py `
  tests/test_output_ownership_manifest.py `
  tests/test_package_derivation_receipt.py `
  tests/test_strict_package_validation.py `
  tests/test_validate_package.py `
  tests/test_apply_gate.py `
  tests/test_operator_summary_inputs.py `
  tests/test_operator_summary.py `
  tests/test_configure_optimized_start.py
git diff --check
git add -- `
  src/hsconfig/starter_compiler.py `
  src/hsconfig/package_compiler.py `
  src/hsconfig/package_assembler.py `
  src/hsconfig/package_render_authority.py `
  src/hsconfig/report_ownership.py `
  src/hsconfig/package_derivation_receipt.py `
  src/hsconfig/strict_package_validation.py `
  src/hsconfig/validate_package.py `
  src/hsconfig/apply_gate.py `
  src/hsconfig/operator_summary_inputs.py `
  src/hsconfig/operator_summary_evaluator.py `
  src/hsconfig/configure_workflow.py `
  tests/test_starter_compiler.py `
  tests/test_package_compiler.py `
  tests/test_package_render_authority.py `
  tests/test_output_ownership_manifest.py `
  tests/test_package_derivation_receipt.py `
  tests/test_strict_package_validation.py `
  tests/test_validate_package.py `
  tests/test_apply_gate.py `
  tests/test_operator_summary_inputs.py `
  tests/test_operator_summary.py `
  tests/test_configure_optimized_start.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: compile and bind single candidate authority"
```

---

## Task 8: Gate Publication on Exact Write-Free Prepublication Validation

**Owned files**

- Create: `src/hsconfig/live_start_controller.py`
- Create: `src/hsconfig/live_start_faults.py`
- Create: `tests/test_configure_prepublication_apply.py`
- Modify: `src/hsconfig/configure_run_model.py`
- Modify: `src/hsconfig/configure_run_stage_contract.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/runtime_apply_receipts.py`
- Modify: `src/hsconfig/live_start_session.py`
- Modify: `src/hsconfig/atomic_io.py`
- Modify: `src/hsconfig/output_operation_admission.py`
- Modify: `src/hsconfig/output_publisher.py`
- Modify: `src/hsconfig/package_io.py`
- Modify: `tests/test_configure_publication.py`
- Modify: `tests/test_output_publisher.py`
- Modify: `tests/test_package_io.py`
- Modify: `tests/test_runtime_apply_receipts.py`
- Modify: `tests/test_live_start_session.py`
- Modify: `tests/test_output_operation_admission.py`
- Modify: `tests/test_atomic_io.py`

### Step 8.1: Write the RED ordering and preservation tests

Add these exact tests:

- `test_fake_apply_plans_exact_temporary_package_before_publication`
- `test_prepublication_receipt_is_external_diagnostic_only_and_path_bound`
- `test_fault_through_fake_apply_preserves_current_pointer_and_runtime_bytes`
- `test_profile_or_output_precondition_drift_blocks_publication`
- `test_preview_publishes_but_creates_no_runtime_lock_journal_state_or_receipt`
- `test_validation_receipts_are_durable_before_package_and_prepublication_phase_cas`
- `test_tampered_review_package_or_prepublication_receipt_stops_resume`
- `test_deck_output_identity_is_held_through_publish`
- `test_prepublication_work_tree_is_retained_for_resume_then_identity_cleaned_before_apply_or_terminal`
- `test_crash_after_prepublication_cas_resumes_same_tree_and_receipt_without_rebuild`
- `test_publication_requires_active_profile_and_output_capabilities`
- `test_profile_disable_waits_through_publication_committed_cas`
- `test_publisher_uses_held_child_capability_on_windows_and_posix`
- `test_publish_under_guard_rejects_closed_or_forged_guard_before_write`
- `test_publish_under_guard_requires_active_bootstrap_lease_and_publication_authorization`
- `test_output_publication_authorization_rejects_wrong_kind_cursor_profile_or_claim`
- `test_output_publication_authorization_requires_active_owning_session_lease`
- `test_output_publication_authorization_rejects_stale_cross_thread_or_expired_session_lease`
- `test_publish_under_guard_swap_at_first_mutation_never_touches_replacement`
- `test_legacy_path_publisher_delegates_and_preserves_existing_contract`
- `test_neutral_lock_bootstrap_supports_first_legacy_publish_without_profile`
- `test_neutral_lock_bootstrap_supports_first_legacy_runtime_writer_without_profile`
- `test_output_child_bootstrap_prepared_cas_precedes_absent_child_create`
- `test_output_child_bootstrap_crash_before_identity_cas_never_adopts_or_deletes_child`
- `test_output_child_bootstrap_bound_identity_resumes_and_rejects_replacement`
- `test_publisher_commit_before_publication_cas_reconciles_only_bound_output_identity`
- `test_live_preview_and_legacy_publishers_share_output_child_bootstrap_lock`
- `test_every_publisher_checks_output_child_claim_under_output_base_lock`
- `test_foreign_or_malformed_output_child_claim_blocks_before_mutation`
- `test_absent_output_child_claim_is_durable_before_create`
- `test_existing_output_child_binds_without_create`
- `test_claimless_empty_output_child_is_never_adopted`
- `test_output_child_create_before_cas_resumes_only_under_exact_active_claim`
- `test_output_child_claim_remains_exact_until_publication_committed`
- `test_output_child_claim_retirement_is_intent_first`
- `test_output_child_claim_unlink_before_cas_resumes_from_exact_absence`
- `test_claim_retirement_confirmation_stops_after_foreign_current_change`
- `test_claim_retired_cas_atomically_rebinds_publication_digest`
- `test_output_child_claim_is_never_recreated_after_retired`
- `test_output_operation_admission_is_fixed_absent_cas_and_profile_bound`
- `test_all_publishers_reject_active_malformed_or_replaced_output_operation_admission`
- `test_all_publishers_reject_output_operation_staging_or_reserved_temp_residue`
- `test_output_operation_admission_precedes_per_child_claim_and_survives_claim_retirement`
- `test_output_operation_admission_unlink_requires_persisted_release_authorized_cursor`
- `test_output_operation_terminal_release_adapter_requires_exact_terminal_no_runtime_context`
- `test_output_operation_admission_crashes_resume_without_profile_or_publisher_race`
- `test_output_operation_staging_flush_crash_retires_then_retries_without_promotion`
- `test_output_claim_binds_exact_final_staging_and_inner_temp_paths`
- `test_unbound_staging_and_direct_final_are_delete_only_or_tamper`
- `test_atomic_publish_no_replace_default_hook_and_named_stage_are_compatible`
- `test_atomic_publish_no_replace_never_overwrites_two_process_winner`
- `test_bound_no_replace_posix_two_link_intermediate_converges_by_identity`
- `test_child_directory_guard_opens_relative_to_held_parent`
- `test_child_directory_guard_fails_closed_after_visible_parent_swap`
- `test_receipt_transitions_resume_every_write_before_phase_cas`
- `test_prepublication_cleanup_quarantine_is_forward_resumable_before_terminal`
- `test_cleanup_parent_bootstrap_is_atomic_idempotent_and_identity_bound`
- `test_work_parent_identity_is_bound_in_session_receipt_and_cleanup_inventory`
- `test_cleanup_identity_inventory_is_durable_before_quarantine_rename`
- `test_cleanup_prepared_before_sidecar_reconstructs_only_exact_committed_inventory`
- `test_cleanup_inventory_staged_hard_kills_reconcile_without_unknown_child`
- `test_prepublication_cleanup_inventory_uses_planned_staging_bound_commit`
- `test_prepublication_cleanup_inventory_retires_unbound_staging_without_promotion`
- `test_prepublication_cleanup_inventory_rejects_direct_final_from_planned`
- `test_prepublication_cleanup_inventory_posix_two_link_commit_preserves_identity`
- `test_prepublication_cleanup_inventory_rejects_staging_or_parent_substitution`
- `test_cleanup_resume_rejects_replaced_work_parent_after_prepared_or_inventory_write`
- `test_cleanup_resume_rejects_same_bytes_file_identity_replacement`
- `test_cleanup_resume_rejects_empty_directory_identity_replacement`
- `test_cleanup_fault_after_each_entry_class_and_cursor_resumes_exactly`
- `test_cleanup_substitution_or_unknown_entry_preserves_nonterminal_state`
- `test_cleanup_clears_transition_last_before_apply_or_terminal`

Instrument both output-child predecessor variants with one event list and
require this strict order; the event payload distinguishes `created` from
`confirmed` without changing ordering:

```python
assert events == [
    "rendered",
    "strict_validated",
    "derivation_replayed",
    "operator_summary_recomputed",
    "package_validation_receipt_written",
    "package_validated_cas",
    "fake_apply_planned",
    "diagnostic_receipt_written",
    "prepublication_check_passed_cas",
    "profile_lease_enter",
    "profile_rebound_under_lease",
    "output_precondition_rebound",
    "output_operation_lock_enter",
    "output_child_bootstrap_lock_enter",
    "output_base_identity_lease_enter",
    "output_operation_admission_prepared_cas",
    "output_operation_admission_staging_flushed",
    "output_operation_admission_publish",
    "output_operation_admission_bound_cas",
    "output_child_bootstrap_prepared_cas",
    "output_child_claim_publish",
    "output_child_claim_bound_cas",
    "output_child_created_or_confirmed",
    "output_child_bound_cas",
    "output_deck_identity_lease_enter",
    "published",
    "publication_committed_cas",
    "output_child_claim_retirement_prepared",
    "output_child_claim_unlink",
    "output_child_claim_unlink_cas",
    "output_child_claim_absence_current_confirmed",
    "output_child_claim_retired_cas",
    "output_operation_admission_still_active",
    "output_child_bootstrap_lock_exit",
    "prepublication_cleanup_inventory_staging_flushed",
    "prepublication_cleanup_inventory_staging_bound_cas",
    "prepublication_cleanup_inventory_bound_commit",
    "prepublication_cleanup_inventory_primary_applied_cas",
    "prepublication_quarantine",
    "prepublication_cleanup_inventory_deleted",
    "prepublication_cleanup_complete_cas",
    "output_deck_identity_lease_exit",
    "output_base_identity_lease_exit",
    "profile_lease_still_active",
    "output_operation_lock_still_active",
]
```

That exact event list is the committed-and-matched branch. `NOT_COMMITTED` and
`UNKNOWN_REQUIRES_RECOVERY` omit both committed/matched CAS events but still
require `recovery_closed_session_cas`; committed mismatch and pending follow the
closed phase table. The Session digest at `composite_result_yield` must equal the
direct return digest of the last recovery-closure CAS. No Session reload occurs
between them, and no later CAS may reuse any earlier predecessor cursor.

Run:

```powershell
python -B -m pytest `
  tests/test_configure_prepublication_apply.py::test_fake_apply_plans_exact_temporary_package_before_publication `
  tests/test_configure_prepublication_apply.py::test_prepublication_receipt_is_external_diagnostic_only_and_path_bound `
  tests/test_configure_prepublication_apply.py::test_fault_through_fake_apply_preserves_current_pointer_and_runtime_bytes `
  tests/test_configure_prepublication_apply.py::test_profile_or_output_precondition_drift_blocks_publication `
  tests/test_configure_prepublication_apply.py::test_preview_publishes_but_creates_no_runtime_lock_journal_state_or_receipt `
  tests/test_configure_prepublication_apply.py::test_validation_receipts_are_durable_before_package_and_prepublication_phase_cas `
  tests/test_configure_prepublication_apply.py::test_tampered_review_package_or_prepublication_receipt_stops_resume `
  tests/test_configure_prepublication_apply.py::test_deck_output_identity_is_held_through_publish `
  tests/test_configure_prepublication_apply.py::test_prepublication_work_tree_is_retained_for_resume_then_identity_cleaned_before_apply_or_terminal `
  tests/test_configure_prepublication_apply.py::test_crash_after_prepublication_cas_resumes_same_tree_and_receipt_without_rebuild `
  tests/test_configure_prepublication_apply.py::test_publication_requires_active_profile_and_output_capabilities `
  tests/test_configure_prepublication_apply.py::test_profile_disable_waits_through_publication_committed_cas `
  tests/test_output_publisher.py::test_publisher_uses_held_child_capability_on_windows_and_posix `
  tests/test_output_publisher.py::test_publish_under_guard_rejects_closed_or_forged_guard_before_write `
  tests/test_output_publisher.py::test_publish_under_guard_requires_active_bootstrap_lease_and_publication_authorization `
  tests/test_output_publisher.py::test_output_publication_authorization_rejects_wrong_kind_cursor_profile_or_claim `
  tests/test_output_publisher.py::test_output_publication_authorization_requires_active_owning_session_lease `
  tests/test_output_publisher.py::test_output_publication_authorization_rejects_stale_cross_thread_or_expired_session_lease `
  tests/test_output_publisher.py::test_publish_under_guard_swap_at_first_mutation_never_touches_replacement `
  tests/test_output_publisher.py::test_legacy_path_publisher_delegates_and_preserves_existing_contract `
  tests/test_output_publisher.py::test_neutral_lock_bootstrap_supports_first_legacy_publish_without_profile `
  tests/test_output_publisher.py::test_neutral_lock_bootstrap_supports_first_legacy_runtime_writer_without_profile `
  tests/test_configure_prepublication_apply.py::test_output_child_bootstrap_prepared_cas_precedes_absent_child_create `
  tests/test_configure_prepublication_apply.py::test_output_child_bootstrap_crash_before_identity_cas_never_adopts_or_deletes_child `
  tests/test_configure_prepublication_apply.py::test_output_child_bootstrap_bound_identity_resumes_and_rejects_replacement `
  tests/test_configure_prepublication_apply.py::test_publisher_commit_before_publication_cas_reconciles_only_bound_output_identity `
  tests/test_output_publisher.py::test_live_preview_and_legacy_publishers_share_output_child_bootstrap_lock `
  tests/test_output_publisher.py::test_every_publisher_checks_output_child_claim_under_output_base_lock `
  tests/test_output_publisher.py::test_foreign_or_malformed_output_child_claim_blocks_before_mutation `
  tests/test_configure_prepublication_apply.py::test_absent_output_child_claim_is_durable_before_create `
  tests/test_configure_prepublication_apply.py::test_existing_output_child_binds_without_create `
  tests/test_configure_prepublication_apply.py::test_claimless_empty_output_child_is_never_adopted `
  tests/test_configure_prepublication_apply.py::test_output_child_create_before_cas_resumes_only_under_exact_active_claim `
  tests/test_configure_prepublication_apply.py::test_output_child_claim_remains_exact_until_publication_committed `
  tests/test_configure_prepublication_apply.py::test_output_child_claim_retirement_is_intent_first `
  tests/test_configure_prepublication_apply.py::test_output_child_claim_unlink_before_cas_resumes_from_exact_absence `
  tests/test_configure_prepublication_apply.py::test_claim_retirement_confirmation_stops_after_foreign_current_change `
  tests/test_configure_prepublication_apply.py::test_claim_retired_cas_atomically_rebinds_publication_digest `
  tests/test_configure_prepublication_apply.py::test_output_child_claim_is_never_recreated_after_retired `
  tests/test_output_operation_admission.py::test_output_operation_admission_is_fixed_absent_cas_and_profile_bound `
  tests/test_output_publisher.py::test_all_publishers_reject_active_malformed_or_replaced_output_operation_admission `
  tests/test_output_publisher.py::test_all_publishers_reject_output_operation_staging_or_reserved_temp_residue `
  tests/test_configure_prepublication_apply.py::test_output_operation_admission_precedes_per_child_claim_and_survives_claim_retirement `
  tests/test_configure_prepublication_apply.py::test_output_operation_admission_unlink_requires_persisted_release_authorized_cursor `
  tests/test_configure_prepublication_apply.py::test_output_operation_terminal_release_adapter_requires_exact_terminal_no_runtime_context `
  tests/test_configure_prepublication_apply.py::test_output_operation_admission_crashes_resume_without_profile_or_publisher_race `
  tests/test_configure_prepublication_apply.py::test_output_operation_staging_flush_crash_retires_then_retries_without_promotion `
  tests/test_configure_prepublication_apply.py::test_output_claim_binds_exact_final_staging_and_inner_temp_paths `
  tests/test_output_operation_admission.py::test_unbound_staging_and_direct_final_are_delete_only_or_tamper `
  tests/test_atomic_io.py::test_atomic_publish_no_replace_default_hook_and_named_stage_are_compatible `
  tests/test_atomic_io.py::test_atomic_publish_no_replace_never_overwrites_two_process_winner `
  tests/test_atomic_io.py::test_bound_no_replace_posix_two_link_intermediate_converges_by_identity `
  tests/test_package_io.py::test_child_directory_guard_opens_relative_to_held_parent `
  tests/test_package_io.py::test_child_directory_guard_fails_closed_after_visible_parent_swap `
  tests/test_configure_prepublication_apply.py::test_receipt_transitions_resume_every_write_before_phase_cas `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_quarantine_is_forward_resumable_before_terminal `
  tests/test_package_io.py::test_cleanup_parent_bootstrap_is_atomic_idempotent_and_identity_bound `
  tests/test_configure_prepublication_apply.py::test_work_parent_identity_is_bound_in_session_receipt_and_cleanup_inventory `
  tests/test_configure_prepublication_apply.py::test_cleanup_identity_inventory_is_durable_before_quarantine_rename `
  tests/test_configure_prepublication_apply.py::test_cleanup_prepared_before_sidecar_reconstructs_only_exact_committed_inventory `
  tests/test_configure_prepublication_apply.py::test_cleanup_inventory_staged_hard_kills_reconcile_without_unknown_child `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_inventory_uses_planned_staging_bound_commit `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_inventory_retires_unbound_staging_without_promotion `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_inventory_rejects_direct_final_from_planned `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_inventory_posix_two_link_commit_preserves_identity `
  tests/test_configure_prepublication_apply.py::test_prepublication_cleanup_inventory_rejects_staging_or_parent_substitution `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_replaced_work_parent_after_prepared_or_inventory_write `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_same_bytes_file_identity_replacement `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_empty_directory_identity_replacement `
  tests/test_configure_prepublication_apply.py::test_cleanup_fault_after_each_entry_class_and_cursor_resumes_exactly `
  tests/test_configure_prepublication_apply.py::test_cleanup_substitution_or_unknown_entry_preserves_nonterminal_state `
  tests/test_configure_prepublication_apply.py::test_cleanup_clears_transition_last_before_apply_or_terminal `
  -q -p no:cacheprovider
```

Expected RED: the current configure flow publishes before any fake apply.

### Step 8.2: Build a configure run directly from frozen authority

Create `live_start_faults.py` with a closed `LiveStartFaultPoint` enum, a
`LiveStartFaultHook` callable protocol, and `no_live_start_fault`. It has no CLI,
environment, profile, document, or package selector. Internal implementation
functions accept it explicitly; every public operator wrapper supplies only the
no-op hook. Define all enum values in Task 8, including the later phase points,
so Tasks 9 through 11 only thread the already closed contract:

```text
after_pending_transition_cas
after_transition_primary_artifact
after_transition_secondary_artifact
before_transition_phase_cas
after_prepublication_cas
after_output_operation_admission_prepared
after_output_operation_admission_staging_flush_before_staging_bound_cas
after_output_operation_admission_staging_bound
after_output_operation_admission_bound_commit_before_cas
after_output_operation_admission_bound
after_output_child_bootstrap_prepared
after_output_child_claim_staging_flush_before_staging_bound_cas
after_output_child_claim_staging_bound
after_output_child_claim_bound_commit_before_cas
after_output_child_claim_bound
after_output_child_create_before_cas
after_output_child_bound
after_publication_commit_before_output_child_claim_retirement
after_output_child_claim_retirement_prepared
after_output_child_claim_unlink_before_cas
after_output_child_claim_unlink_cas
after_output_child_claim_confirmation_before_retired_cas
after_output_child_claim_retired
after_output_operation_release_authorized
after_output_operation_admission_unlink
after_prepublication_cleanup_inventory_unbound_staging_retire_before_cas
after_prepublication_cleanup_inventory_staging_flush_before_staging_bound_cas
after_prepublication_cleanup_inventory_staging_bound
after_prepublication_cleanup_inventory_bound_commit_before_primary_applied_cas
after_prepublication_quarantine
after_prepublication_cleanup_entry
after_prepublication_cleanup_inventory_delete
after_prepublication_cleanup_before_cas
after_invocation_prepared_before_admission
after_runtime_admission_staging_flush_before_staging_bound_cas
after_runtime_admission_staging_bound
after_runtime_admission_bound_commit_before_cas
after_runtime_layout_intent
after_runtime_layout_directory_create_before_receipt_cas
after_runtime_layout_directory_bound
after_bound_staging_posix_link_before_unlink
after_authorization_consumed_before_physical_callback
after_generic_file_staging_flush_before_staging_bound_cas
after_generic_file_bound_commit_before_cas
after_admission_bound_before_invocation_write
after_invocation_receipt_staging_flush_before_staging_bound_cas
after_invocation_receipt_bound_commit_before_cas
after_invocation_write_before_apply_started
after_apply_started
after_initial_attempt_record_commit_before_cas
after_route_attempt_record_commit_before_cas
after_runtime_journal_created
after_runtime_candidate_journal_bound_before_candidate_create
after_runtime_candidate_create_before_candidate_identity_receipt_cas
after_candidate_tree_entry_before_cursor_cas
after_candidate_tree_verification_before_cas
after_candidate_to_target_rename_before_cas
after_new_target_ini_write_before_cas
after_prior_owner_planned_before_journal
after_prior_owner_journal_created_before_bound
after_prior_owner_bound_before_ini
after_nonowning_ini_write_before_journal_cas
after_physical_commit_before_installer_return
after_installer_return_before_apply_committed
after_result_intent
after_acknowledgement_intent
after_result_json_temp_created
after_result_json_temp_partial
after_result_json_temp_full
after_result_json_temp_flushed
before_result_json_replace
after_result_json
after_result_markdown_temp_created
after_result_markdown_temp_partial
after_result_markdown_temp_full
after_result_markdown_temp_flushed
before_result_markdown_replace
after_result_markdown
before_terminal_cas
after_terminal_cas_before_ack
after_terminal_retirement_prepared
after_success_ack_journal_delete_before_stage_cas
after_success_ack_journal_retired_cas
after_success_ack_fence_delete_before_evidence_cas
after_success_ack_evidence_retired_cas
after_attempt_evidence_physical_retirement_before_cas
after_attempt_evidence_retired_before_admission_release
after_terminal_recovery_resolution_prepared
after_terminal_recovery_metadata_successor
after_nonterminal_recovery_physical_step_before_cursor_cas
after_nonterminal_recovery_cursor_cas
after_first_install_observation_before_prepare_cas
after_nonterminal_observation_before_prepare_cas
after_terminal_resolution_observation_before_prepare_cas
after_terminal_classification_observation_before_selection_cas
after_terminal_classification_selection_cas
after_recovery_closed_cas_before_result_intent
after_candidate_leaf_copy_before_receipt_cas
after_candidate_tree_verify_before_rename
after_terminal_cleanup_inventory_unbound_staging_retire_before_cas
after_terminal_cleanup_inventory_staging_flush_before_staging_bound_cas
after_terminal_cleanup_inventory_staging_bound
after_terminal_cleanup_inventory_bound_commit_before_inventory_bound_cas
after_terminal_cleanup_inventory_bound
after_terminal_cleanup_started
after_terminal_cleanup_entry_delete_before_cursor_cas
after_terminal_cleanup_cursor_cas
after_terminal_cleanup_journal_delete_before_stage_cas
after_terminal_cleanup_journal_retired_cas
after_terminal_cleanup_fence_delete_before_stage_cas
after_terminal_cleanup_fence_retired_cas
after_terminal_cleanup_sidecar_delete_before_stage_cas
after_terminal_cleanup_inventory_retired_cas
after_terminal_recovery_stabilized
after_admission_release_authorized_before_runtime_admission_unlink
after_runtime_admission_unlink
after_owner_retirement_manifest_bound_before_prepared_staging
after_owner_retirement_prepared_staging_flush_before_bound_cas
after_owner_retirement_prepared_commit_before_cas
after_owner_cleanup_initial_journal_staging_flush_before_bound_cas
after_owner_cleanup_initial_journal_commit_before_cas
after_owner_cleanup_initialized_cursor_zero_cas
after_owner_cleanup_entry_before_receipt_cas
after_owner_cleanup_journal_commit_before_cas
after_owner_completed_tombstone_commitment_cas
after_owner_target_root_delete_before_receipt_cas
after_owner_target_root_retired_cas
after_owner_retirement_completed_staging_flush_before_bound_cas
after_owner_retirement_completed_commit_before_cas
after_owner_journal_delete_before_receipt_cas
```

The seven output-operation hooks bind `PREPARED`, staging flush before its
binding CAS, durable `STAGING_BOUND`, bound-identity commit before its CAS, the
`ACTIVE` binding, the later release-authorized session cursor, and exact record
unlink. The record remains present across all
thirteen output-child hooks and through the final claim-retired CAS. Preview or
failure reaches the release pair only after terminal CAS; live apply reaches it
only after the exact runtime admission is bound in `APPLY_STARTED`.

The thirteen output-child hooks bind these exact settled or action-before-CAS
states: bootstrap `PREPARED`; claim staging flushed; claim `STAGING_BOUND`;
bound claim committed before its receipt CAS; claim bound; child created before
its receipt CAS; child bound with active claim;
publisher committed before retirement preparation; retirement `PREPARED`;
claim absent before its receipt CAS; unlink receipt CAS complete; exact claim-
absence/current confirmation before its CAS; and final retired binding. Every
hook is reachable through the real controller pipeline and a subprocess hard
kill. Resume may capture an identity exactly once only for a completed plain
empty child-create action whose persisted cursor still has a null identity and
whose owning final claim and absent predecessor remain exact. Authority-file
claim publication always uses `STAGING_BOUND`. After the
first identity CAS, every identity is immutable; replacement or recapture is
tamper. Every successful resume leaves no claim staging or inner-temp residue.

The transition-secondary and cleanup-entry hooks run after every individual
action; parameterized tests stop on the nth invocation and cover create,
replace, remove, file delete, directory delete, root delete, cursor advance, and
the final clearing CAS. The terminal-cleanup hooks fire after the inventory
write, its bind CAS, the cleaning CAS, every entry delete before its cursor CAS,
every cursor CAS, and each journal/fence/sidecar delete before its stage CAS.
The runtime-layout hooks fire after the binding intent, after every
create-or-confirm postcondition before its receipt CAS, and after every bound
directory cursor. The first-install hooks then split initial schema-2 commit,
route commit, each candidate entry, candidate verification, target rename, and
New-Target INI at their action-before-CAS boundaries. The four observation
families also fault after their read-only callback/opaque-receipt creation but
before the consuming Session CAS. Candidate leaf recovery
uses only exact safe content authority and full parity is reread before rename.
The classification hooks fire once after the same-pair observation before its
selection CAS and once after that pure CAS before the selected physical
observation. The closure hook proves `ACTIVE -> CLOSED` is durable before result
intent and never a no-op. The owner-retirement
hooks split manifest commitment, both tombstone staging/commit pairs, initial
cursor-zero journal initialization, each entry delete, each old-v1 cursor
commit, the final COMPLETED-tombstone commitment CAS, target-root retirement,
and the final old-owner unlink. A process-kill matrix must show
the same next action and no second durable row for every hook.
The four prior-owner hooks are exclusive to Task 9's controller no-staging
fastpath: they fire after `PRIOR_OWNER_PLANNED` before v1 creation, after exact
v1 creation before `PRIOR_OWNER_BOUND`, after that bound CAS before INI
mutation, and after intended INI bytes are durably visible before the v1
`INI_COMMITTED` CAS. Public legacy installation does not emit or interpret
those hooks.
The success-ack hooks split non-owning journal retirement, its stage CAS,
fence retirement, and its evidence-retired CAS; the owning route skips only
the journal pair. The nonterminal recovery hooks fire after every one-row
physical successor and after its matching recovery-cursor CAS. Parameterized
subprocess kills prove that neither path mints a second token or advances a
second physical row from the predecessor cursor.
It also fires after each of those three stage CASes. Existing lower-level atomic-
I/O fault tests cover a hard exit within each single atomic replace/delete
primitive.

Add to `live_start_controller.py` the internal typed boundary:

```python
@dataclass(frozen=True, slots=True)
class ValidatedPrepublication:
    rendered: RenderedConfigureRun
    work_root: Path
    work_root_identity: PathIdentity
    package_root: Path
    package_validation_receipt: FrozenJsonDocument
    diagnostic_receipt: FrozenJsonDocument
    updated_session: LiveStartSession

def build_frozen_live_configure_run(
    *, request: ResolvedPackageRequest
) -> ConfigureRunModel: ...

@contextmanager
def lease_validated_prepublication(
    *,
    run_model: ConfigureRunModel,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_root: Path,
) -> Iterator[ValidatedPrepublication]: ...
```

Construct stage artifacts from frozen bytes only:

- `01_manifest/input_snapshot_manifest.json`;
- `02_source_documents/source_documents.json`;
- `03_research/starter_context.json`.

Extend `configure_run_stage_contract.py` only as needed to accept this exact
frozen stage shape. Keep the existing source-acquisition/document exclusivity
and legacy stage shapes unchanged.

### Step 8.3: Validate and plan on one temporary package

`lease_validated_prepublication()` must:

1. render the immutable run model entirely in memory, derive its exact tree and
   cleanup manifests, and CAS `materialize_prepublication_work` before writing;
2. materialize or resume its exact expected subset at the deterministic path
   `%LOCALAPPDATA%\HSConfig\work\live-start-<run-id>` or, on resume, reopen the
   exact path/identity already bound by the session work binding;
3. snapshot and verify the entire run against the model, then CAS the exact
   `prepublication_work_binding` and clear materialization intent;
4. validate the direct `04_package` strictly;
5. replay derivation and recompute operator-summary parity;
6. through `install_package_validation`, write/reread the exact canonical
   receipt, bind its digest, and CAS `REVIEW_APPROVED` to `PACKAGE_VALIDATED`;
7. call `plan_apply_package()` on that exact direct package path;
8. add `diagnostic_only=true`, exact package-path and package-digest bindings,
   and a deterministic diagnostic timestamp derived from the frozen bound date,
   never the resume wall clock;
9. through `install_prepublication_validation`, write and reread the receipt at
   `receipts/prepublication_apply_check.json` with the session-root identity;
10. bind its digest, CAS `PACKAGE_VALIDATED` to
    `PREPUBLICATION_CHECK_PASSED`, and clear the transition;
11. yield the immutable object plus exact updated session cursor while the work
    directory remains leased to the caller.

The first materialization revalidates the canonical state-root identity, then
bootstraps the fixed `%LOCALAPPDATA%\HSConfig\work` child once with
`secure_create_directory()` or accepts one concurrent legitimate create. It
captures and binds that parent path/identity before securely creating and
capturing the work-root identity. Both identities are bound in
`prepublication_work_binding`, repeated in `package_validation.json` on success,
and kept through
`PUBLICATION_COMMITTED` or an intentional failure-cleanup decision. A process
exception after work binding or either receipt CAS retains that exact tree for
resume; it is not a `finally` cleanup boundary. Resume under the session lease
opens the work parent only with `create_if_missing=False` under the state-root
guard and requires the same parent path/identity, child path/identity, rendered
snapshot, package digest, cleanup manifest, and completed receipt bytes. It
continues without refetching or minting a new diagnostic timestamp. A missing or
replaced source parent is tamper even if the original child identity was moved
under it. A validation failure never clears the work binding before its exact
cleanup has completed.

After publication CAS, or before making a chosen failure terminal, start the
same-phase `cleanup_prepublication` transition. The shared cleanup parent is
exactly `%LOCALAPPDATA%\HSConfig\cleanup`. Before the first `PREPARED` CAS,
revalidate and hold the canonical state-root identity. If its exact `cleanup`
child is absent, create it once with `secure_create_directory()` relative to
that held parent; if a concurrent legitimate create wins, reread it once.
Otherwise require an existing canonical plain non-reparse directory. Capture
its identity and bind it in `PREPARED`. After that CAS, resume always uses
`create_if_missing=False`; a missing or replaced cleanup parent is tamper. The
shared parent is never removed.

The two run-owned children are fixed as
`%LOCALAPPDATA%\HSConfig\cleanup\live-start-<run-id>.inventory.json` and
`%LOCALAPPDATA%\HSConfig\cleanup\live-start-<run-id>.quarantine`. The inventory
file uses only its deterministic `.staged` sibling and
`.<staged-leaf>.live-start-atomic.tmp`. Its `external_file_action` remains
non-null from the first `PREPARED` CAS until the identity-preserving commit;
direct final creation, a separate `.<inventory-leaf>.live-start-atomic.tmp`, or
first capture of an identity observed only at the final path is invalid. The
cleanup stages then have exactly this physical meaning:

The closed inventory action literals are
`retire_unbound_prepublication_cleanup_inventory_staging`,
`materialize_prepublication_cleanup_inventory_staging`, and
`commit_bound_prepublication_cleanup_inventory`; no generic receipt writer or
reserved-sibling action is admitted for this operation.

| Outer stage | Nested file stage | Required physical state and sole next action |
| --- | --- | --- |
| `PREPARED` | `PLANNED` | Work root exact; final absent; staging/temp absent or one unbound residue; bytes/parent bound; identities null. Retire or materialize. |
| `STAGING_BOUND` | `STAGING_BOUND` | Exact bound staging alone, the same identity at final alone, or the exact POSIX two-link intermediate; commit bound identity. |
| `PRIMARY_APPLIED` | null | Final alone has the bound staging identity and exact bytes; staging/temp and quarantine absent; cursor zero. Rename work to quarantine. |
| `CLEANUP_DELETING` | null | Work root absent; quarantine has exactly `work_root_identity`; inventory exact; cursor between zero and `cleanup_entry_count`. |
| Final clear window | null | Only at full cursor may quarantine and inventory both be absent; the last session CAS clears the transition. |

From `PREPARED/PLANNED`, verified retirement of unbound residue returns one
receipt whose CAS keeps the stage `PREPARED/PLANNED`, increments the action
index, binds both staging surfaces absent, and selects only materialization.
Materialization writes and flushes canonical bytes through the inner temp to
staging; its receipt alone CASes `STAGING_BOUND` and binds the staging triplet.
A fresh commit authorization converges staging-only, final-only with the same
bound identity, or the exact POSIX two-link row to final-only. Its receipt alone
CASes `PRIMARY_APPLIED`, copies the staging triplet into the final inventory
triplet, and clears `external_file_action`. `PRIMARY_APPLIED` may then observe
work absent plus quarantine present with the already bound `work_root_identity`
and advance to `CLEANUP_DELETING`; a cleanup cursor may observe only its current
exact row already absent; and full cursor may observe the exact inventory
already absent. No stage adopts any other successor, replacement, direct-final
write, or mixed predecessor state.

Construct the logical manifest only from the frozen rendered model and require
its digest/count to match `prepublication_work_binding`. While the complete
work tree is still present, snapshot it once, reject unsafe physical state, and
build the exact canonical identity inventory. CAS `PREPARED/PLANNED` before any
inventory write. Materialize only deterministic staging, bind its identity by
receipt CAS, then commit only that bound identity and bind the final triplet by
the separate receipt CAS. Resume never recaptures a remaining child identity as
authority.

If a hard kill leaves exactly `PREPARED`, sidecar absent, and the complete work
tree present, resume first revalidates the persisted work-root and parent
identities, then boundedly/no-follow re-enumerates only as a candidate for the
already committed inventory bytes. Its canonical size, byte digest,
self-digest, count, root/parent rows, logical manifest, and every entry identity
must reproduce the values already stored in `PREPARED` exactly. Only those
identical bytes may be materialized. Same-byte file replacement, empty-
directory replacement, parent replacement, missing or extra entry, or any
digest difference is tamper. The candidate never updates or extends the
persisted commitment.

Close the work-root handle for Windows rename, but retain the exact persisted
work-parent guard and the cleanup-parent guard. Securely rename the exact work root to the absent
quarantine with both expected parent identities, validate the full quarantine
against the sealed identity inventory, then CAS `CLEANUP_DELETING` with
`quarantine_identity == work_root_identity`. Delete only the row at
`cleanup_cursor` with `secure_unlink_verified()` or
`secure_rmdir_verified()`, using that row's exact identity, expected parent
identity, size, and digest, and CAS the incremented cursor after each row. An
already-absent current row after a crash may advance only when every earlier
row is durably complete and the remaining tree still matches the inventory.

After the root row, require quarantine absence, then delete the inventory file
with its exact identity, size, digest, and parent identity. A crash after that
delete is forward-resumable only when the cursor is full and both run-owned
cleanup children are absent; clear the transition last. Inventory absence at a
smaller cursor, any same-byte replacement, empty-directory replacement, extra
entry, changed identity/size/digest, reparse point, hard link, alternate stream,
or unlisted physical combination is tamper and remains nonterminal. Residual
enumeration may detect unknown state but cannot authorize it.

Publication stays committed, but preview terminalization and live apply may not
begin while cleanup is non-null. Cleanup failure preserves a resumable
nonterminal session and never rolls publication back. The historical
`prepublication_work_binding` remains after deletion and authorizes only exact
absence, never recreation.

The fake receipt stays outside the package and is not accepted by
`apply_and_match_published()` later. Extend receipt verification to reject
`diagnostic_only=true` in any real-apply input position.

### Step 8.4: Publish only after root rebinding

Add a lease-aware internal publisher entry and keep the existing public
publisher as its compatibility wrapper:

The fixed operation admission is canonical, self-digested, and has exactly:

```text
schema_version, record_kind, state, run_id, session_root,
session_root_identity, expected_session_sha256, operator_profile_path,
operator_profile_parent_identity, operator_profile_identity,
operator_profile_sha256, state_root_identity, output_base_root,
output_base_root_identity, output_child_path,
output_child_predecessor_state, output_child_predecessor_identity,
output_bootstrap_lock_path, output_bootstrap_lock_identity,
output_claim_path, content_sha256
```

The record is immutable from its no-replace publication through release. It is
not a per-output claim, current pointer, package lease, or runtime admission.
Its path is globally fixed so profile mutation and every publisher can stop on
one bounded observation without searching sessions or output trees.
Its physical `state` is always exactly `ACTIVE`; release authorization exists
only in the session binding and never rewrites the fixed record.
`expected_session_sha256` is the exact predecessor cursor passed to the
intent-first prepare CAS, never the successor that embeds the planned record
digest, so the two self-digests are acyclic.

Task 8 reuses the already-green Task-3 shared two-stage external-file
primitives before either fixed-record or claim publication.
`atomic_materialize_staging_bytes()` writes and flushes only the deterministic
internal staging path and returns its exact identity; the owning receipt/CAS
must bind that identity before `atomic_commit_bound_staging_no_replace()` is
callable. The latter requires the persisted staging identity, flushes the bound
parent, and never materializes bytes, chooses a live identity, performs an
existence-check-plus-replace, or overwrites a winner. Task 8 adds only the
sibling `atomic_commit_bound_staging_replace()` for controller replace actions,
requiring the exact predecessor identity. The legacy compatibility
`atomic_publish_bytes_no_replace()` may compose both stages only for callers
that do not claim cross-process controller provenance; every controller path
uses the intervening durable CAS. Task 9 imports these same primitives for
runtime admission and metadata and does not define a second implementation.

The output-operation staging child is exactly the globally fixed
`output-operation-admission.staged` sibling and its inner reserved temp is
exactly `.output-operation-admission.staged.live-start-atomic.tmp`. Both are
bound in `PREPARED` before either exists. Every profile mutation and publisher
checks the final plus these two fixed paths under the operation lock. At
`PREPARED`, final must remain absent; staging or inner-temp residue is verified
delete-only and a final occupant is tamper. The materialization receipt alone
binds `STAGING_BOUND`. At `STAGING_BOUND`, inner temp is absent and the only
legal rows are the exact bound staging alone, final alone with that same bound
identity, or final plus staging as that same identity with total `nlink=2` on
the POSIX hard-link fallback. The last row is completed only by unlinking
staging, flushing the parent, and rereading final as the same identity with
`nlink=1`. Different identities, bytes, link counts, parents, extra surfaces,
or disappearance of both bound names are tamper. The active-binding CAS
requires final-only and copies the persisted staging identity; it never captures
an identity from final.

A `PREPARED` cursor with final, staging, and inner temp all absent is still
prephysical. Resume may roll it back without blocking a profile change and may
retry only after reacquiring and exactly revalidating the sealed profile/output
preconditions. Once staging or inner-temp bytes exist, their fixed path is a
global fail-closed fence until the owning session retires them under the exact
`PREPARED` authority; no unrelated publisher, generic Runtime writer, or profile
mutation may proceed. Such residue is never promoted. Once `STAGING_BOUND` is
durable, only the exact bound identity may move forward and profile,
publisher, and generic Runtime mutation remain fenced until final commit or
exact rollback.

```python
# atomic_io.py, extending Task 3's shared staged-authority API
def atomic_commit_bound_staging_replace(
    *,
    path: Path,
    staging_path: Path,
    expected_predecessor_identity: PathIdentity,
    expected_staging_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
    expected_parent_identity: PathIdentity,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes: ...

def atomic_publish_bytes_no_replace(
    *,
    path: Path,
    staging_path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes:
    """Legacy compatibility wrapper; controller callers are rejected."""

# output_publisher.py
@dataclass(frozen=True, slots=True)
class OutputChildBootstrapLease: ...

@dataclass(frozen=True, slots=True)
class OutputPublicationAuthorization: ...

@dataclass(frozen=True, slots=True)
class OutputPublicationPermit: ...

# output_publisher.py
@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionPhysicalStep:
    staging: MaterializedStagingBytes | None
    evidence: OutputOperationAdmissionEvidence | None
    step_receipt: OutputOperationAdmissionStepReceipt

OutputOperationAdmissionReleaseDisposition = Literal[
    "old_unlinked",
    "already_absent",
    "valid_foreign_successor",
]

@dataclass(frozen=True, slots=True)
class OutputChildBootstrapPhysicalStep:
    claim_staging: MaterializedStagingBytes | None
    claim_identity: PathIdentity | None
    output_child_identity: PathIdentity | None
    object_was_already_in_exact_postcondition: bool
    step_receipt: OutputChildBootstrapStepReceipt

# output_publisher.py
@contextmanager
def lease_output_child_bootstrap(
    *, output_root: Path
) -> Iterator[OutputChildBootstrapLease]: ...

def authorize_output_publication_under_bootstrap_lease(
    *,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_guard: PlainDirectoryMutationGuard,
    operation_admission: OutputOperationAdmissionEvidence | None,
    session_lease: LiveStartSessionLease | None,
    expected_session: LiveStartSession | None,
    profile_lease: OperatorProfileLease | None,
) -> OutputPublicationAuthorization: ...

@contextmanager
def _begin_output_publication(
    *,
    publication_authorization: OutputPublicationAuthorization,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_guard: PlainDirectoryMutationGuard,
) -> Iterator[OutputPublicationPermit]: ...

def _finish_output_publication(
    *,
    permit: OutputPublicationPermit,
    published_output: PublishedOutput,
) -> None: ...

# output_publisher.py
def publish_output_operation_admission_under_lease(
    *,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_base_guard: PlainDirectoryMutationGuard,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    admission_authorization: OutputOperationAdmissionAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> OutputOperationAdmissionPhysicalStep: ...

def authorize_output_operation_terminal_release_from_context(
    *,
    operation_lease: OutputOperationAdmissionLease,
    session_lease: LiveStartSessionLease,
    expected_terminal_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    expected: OutputOperationAdmissionEvidence,
) -> OutputOperationAdmissionReleaseAuthorization: ...

def release_output_operation_admission_under_lease(
    *,
    operation_lease: OutputOperationAdmissionLease,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    expected: OutputOperationAdmissionEvidence,
    release_authorization: OutputOperationAdmissionReleaseAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> OutputOperationAdmissionReleaseDisposition: ...

def perform_output_child_bootstrap_step_under_guards(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_base_guard: PlainDirectoryMutationGuard,
    bootstrap_authorization: OutputChildBootstrapAuthorization,
    fault_hook: FaultHook = no_fault,
) -> OutputChildBootstrapPhysicalStep: ...

# output_publisher.py
@contextmanager
def publish_configure_run_under_guard(
    rendered: RenderedConfigureRun,
    *,
    output_guard: PlainDirectoryMutationGuard,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    publication_authorization: OutputPublicationAuthorization,
    fault_hook: FaultHook = no_fault,
) -> Iterator[PublishedOutput]: ...
```

As its first executable operation, the context calls
`_begin_output_publication()`; forged, stale, reused, cross-thread, wrong-kind,
or wrong-lease authority fails before the callback can observe or mutate any
output surface. The returned opaque permit spans exactly one publisher context,
and `_finish_output_publication()` consumes it only after the final bounded
readback. An exception abandons it and no second callback is permitted. The
context also validates the active, originating-thread guard token and exact
output-root identity before every child open, create, replace, pointer update,
and final readback. Every layout, lock, journal, staging, revision, and current
direct-child operation is descriptor-relative to that guard or a child guard
derived from it; it never reconstructs and reopens the guarded path for
mutation. Extend `package_io` only with the narrowly required guarded-child
primitives and an opaque guard token minted after handle/identity acquisition,
bound to that context/thread, and invalidated before handle release. Forged,
copied-across-context, cross-thread, or expired guards fail before mutation. The
context holds
the existing `.publish.lock` until the caller records the publication CAS, then
invalidates its private capability before unlock. The public path-based wrapper
acquires its own guard and delegates. Add a real process-level rename/replace
test on Windows and POSIX; a substituted child must never receive output.

Every publisher first enters the fixed `OutputOperationAdmissionLease`.
Ordinary live, preview, and legacy wrappers require the fixed record, staging,
and reserved temp all absent before acquiring the per-output bootstrap lock.
Every public, direct, and legacy Runtime wrapper requires the same three-path
absence before creating `.hsconfig` or acquiring the Runtime lock.
The owning controller enters
the same lease while its session/profile capabilities are active, publishes
and binds the fixed record before any per-output claim, and keeps the lease
through claim retirement and either terminal release or the runtime-admission
handoff. A valid foreign record blocks; malformed, unsafe, replaced, or
unbounded state also blocks rather than being treated as absence. The shared
operation lease closes absence/create and unlink/reclaim races across every
publisher, every profile mutation, and every generic Runtime writer.

`lease_output_child_bootstrap()` uses the deterministic lock
`%LOCALAPPDATA%/HSConfig/locks/output-child-<sha256-canonical-path>.lock` and
binds its parent/file identities plus canonical output path. It is the shared
output-base fence for every path-based live, preview, and legacy publisher.
Task 8 adds one neutral no-follow lock bootstrap that may create only the plain
`%LOCALAPPDATA%/HSConfig` directory, its plain `locks` child, the fixed empty
output-operation lock, and this deterministic empty lock under an identity-
bound `LOCALAPPDATA` parent. It never
creates a profile, run, receipt, admission, output, or runtime artifact and is
owned by `package_io`/`output_publisher`, not `operator_profile`. This is the
only exception to profile-enable's state-root creation rule and lets the first
legacy publisher or public Runtime writer use the same fence without a pre-
existing profile. The Runtime route may create no `.hsconfig`, apply lock,
journal, target, INI, state, receipt, or other Runtime artifact until this
neutral lease is held and its three-path gate has passed.
While held, each wrapper bounded-reads the deterministic claim before any child
open/create, publisher reconciliation, revision cleanup, or current-pointer
write. An absent claim permits an ordinary publisher; an exact active claim
permits only the matching owning session/profile capability; every foreign,
malformed, replaced, or unsafe claim blocks. A closed, forged, cross-thread,
wrong-path, or replaced lease fails before filesystem mutation.

`authorize_output_publication_under_bootstrap_lease()` mints one opaque,
same-thread, context-bound authorization after validating both active leases,
base/child guards, and claim. Its kind is exactly
`ORDINARY_CLAIM_ABSENT|OWNING_ACTIVE_CLAIM`. The ordinary kind requires exact
absence of fixed operation admission, staging, reserved temp, and per-child
claim and requires
`operation_admission`, `session_lease`, `expected_session`, and `profile_lease`
all null. The owning kind requires all four non-null: the exact active fixed
record, an active originating-thread `LiveStartSessionLease`, the byte-identical
persisted expected cursor with matching operation/claim binding, and the active
profile capability, plus exact base/child/claim identities and publication
predecessor. The authorization binds every bearer nonce and expires with the
first enclosing lease. A loaded or constructed session dataclass without its
active session lease cannot mint or use owning authority. Both mutating
publisher surfaces require this bearer and the same active operation/bootstrap
leases; a raw directory guard alone always fails before reconciliation or
mutation. Public, preview, and legacy wrappers mint only the ordinary kind;
the owning controller forwards every already-held capability.

`publish_output_operation_admission_under_lease()` accepts only the fresh
Task-3 publication bearer, the active operation/bootstrap/session/profile
leases, the active exact output-base guard, and the exact operation cursor. As
its first executable operation it delegates the action callback through
`_execute_output_operation_admission_physical_step()`. From `PREPARED` the
callback may only materialize or retire unbound staging. A cleanup receipt may
only advance `unbound_staging_retired`, preserve `PREPARED`, record residue
absent, and select materialization; the materialization receipt alone advances
`staging_bound`. From `STAGING_BOUND` it may only commit
or confirm the persisted staging identity; that receipt alone advances
`admission_active` and binds final evidence. It performs no session CAS itself.
Its private fault adapter maps both staging-materialization and bound-commit
stages to the closed output-operation hooks and exposes no public selector.
The terminal release adapter requires an active exact session/profile/
operation context, a byte-identical persisted terminal cursor with
`TERMINAL_RELEASE_AUTHORIZED`, no runtime-admission binding, and the original
record evidence before it delegates to Task 3's private low-level mint.
`release_output_operation_admission_under_lease()` accepts only the
fresh release bearer from the exact persisted release-authorized cursor. It
passes the sole unlink/absence callback through
`_execute_output_operation_release()` before any physical observation, and
performs no session CAS. Its closed
return distinguishes `old_unlinked`, `already_absent`, and
`valid_foreign_successor`; the last proves only that the old identity is gone
and leaves the canonical successor byte-identical. Neither helper reacquires a
lock, creates a state parent, adopts an identity, or releases a foreign
successor.

`perform_output_child_bootstrap_step_under_guards()` accepts only one fresh
opaque action token and the already-held session, profile, bootstrap, and base
guards. Before any physical observation it delegates exactly one callback
through `_execute_output_child_bootstrap_physical_step()`. That callback may
materialize or retire unbound claim staging, commit bound claim staging,
confirm an existing child, create an absent child, retire the claim, or confirm
final claim absence plus current publication, and returns one
action-specific receipt. It never performs a session CAS or reacquires a lock.
The session helper consumes that receipt before another token may be minted.

Add `publish_validated_prepublication()` to the controller. It receives the
already-held session, `OperatorProfileLease`, and
`OutputOperationAdmissionLease`; it never acquires or releases them. It must
validate every active token and the exact expected profile, then:

- bounded-reread and revalidate the same operator-profile bytes, identity, and
  digest under that already-held lease;
- reopen the runtime and output-base roots and compare identities;
- recalculate the same deck-output name;
- require fixed output-operation admission absence, construct its canonical
  bytes from the sealed session/profile/output precondition, and CAS
  `install_output_operation_admission/PREPARED` before any fixed record,
  per-output claim, child, revision, or current-pointer mutation;
- materialize fixed-record staging under one fresh token, consume its receipt
  in the `STAGING_BOUND` CAS, then commit only that bound identity under a new
  token and consume its receipt in the CAS that installs
  `output_operation_admission_binding.state=ACTIVE`; keep the
  record and operation lease through every following step;
- acquire the exact bootstrap lease and base guard, require the sealed
  existing/absent child precondition and absent deterministic claim, and CAS
  `bootstrap_output_child/PREPARED` with the planned canonical claim bytes and
  the exact active bootstrap-lock path/identity;
- authorize and materialize only that claim's staging, consume its receipt in
  the `claim_staging_bound` CAS, then commit only that bound identity under a
  new token and consume its receipt in `claim_bound`; keep the exact claim
  physically present;
- from that persisted cursor either confirm the original existing identity or
  create one plain absent child, then consume the child receipt in the
  `child_bound` CAS that installs `output_child_binding.claim_state=ACTIVE`;
- capture only the persisted child identity and hold output-base, deck-child,
  claim, and publisher capabilities across the entire publisher context;
- publish the already validated `RenderedConfigureRun` through
  `publish_configure_run_under_guard()` without rebuilding it;
- record and reassign the exact `PUBLICATION_COMMITTED` session cursor before
  allowing the publisher context to release its lock;
- CAS `retire_output_child_claim/PREPARED`, securely unlink only the exact claim
  under a fresh token, consume the receipt in `PRIMARY_APPLIED`, then under the
  same bootstrap lease confirm exact claim absence, child identity, and current
  revision/content root. Only that confirmation receipt may perform the final
  `claim_retired` CAS before cleanup, preview, or apply.

The final claim-retired CAS does not release the fixed output-operation
admission. Task 8 returns the updated cursor while the caller still holds the
operation lease and while the fixed record remains exact. Preview/failure
release belongs to Task 11 after terminal CAS; live handoff belongs to Task 10
after the runtime admission is durably bound in `APPLY_STARTED`.

The publisher may create children inside the held output root but may not
silently rebind to a substituted root. The child-swap race test replaces the
path before and during publication and requires failure without writing into
the replacement on every supported platform.

After publication, write the exact output-child path/identity and binding
digest, revision, content root, and prior-current identity to session state and
transition to `PUBLICATION_COMMITTED`. A crash after child creation but before
its CAS may resume only from the exact active owning claim and the declared
plain-empty new-object postcondition; claimless or unsafe children are never
adopted. After the child-bound CAS, every failure preserves and revalidates the
exact child identity. A failure after publisher commit is reconciled by the
existing publisher only under that identity, claim, and exact current
publication before session CAS. Claim retirement is itself intent-first: a
crash after unlink resumes only from the exact persisted retirement cursor and
claim absence, preserves the historical binding, and never republishes.

### Step 8.5: Preserve legacy configure behavior and commit

Run:

```powershell
python -B -m pytest `
  tests/test_live_start_session.py::test_cleanup_pending_transition_binds_external_identity_inventory_states `
  tests/test_package_io.py::test_cleanup_parent_bootstrap_is_atomic_idempotent_and_identity_bound `
  tests/test_configure_prepublication_apply.py::test_work_parent_identity_is_bound_in_session_receipt_and_cleanup_inventory `
  tests/test_configure_prepublication_apply.py::test_cleanup_identity_inventory_is_durable_before_quarantine_rename `
  tests/test_configure_prepublication_apply.py::test_cleanup_inventory_staged_hard_kills_reconcile_without_unknown_child `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_replaced_work_parent_after_prepared_or_inventory_write `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_same_bytes_file_identity_replacement `
  tests/test_configure_prepublication_apply.py::test_cleanup_resume_rejects_empty_directory_identity_replacement `
  tests/test_configure_prepublication_apply.py::test_cleanup_fault_after_each_entry_class_and_cursor_resumes_exactly `
  tests/test_configure_prepublication_apply.py::test_cleanup_substitution_or_unknown_entry_preserves_nonterminal_state `
  tests/test_configure_prepublication_apply.py::test_cleanup_clears_transition_last_before_apply_or_terminal `
  -q -p no:cacheprovider
python -B -m pytest `
  tests/test_configure_publication.py::test_successful_configure_publishes_one_resolved_current_package `
  tests/test_configure_publication.py::test_failed_configure_leaves_previous_current_byte_identical `
  tests/test_runtime_apply_receipts.py::test_fake_apply_receipt_is_pure_hash_bound_and_verifiable `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/live_start_controller.py `
  src/hsconfig/live_start_faults.py `
  src/hsconfig/configure_run_model.py `
  src/hsconfig/configure_run_stage_contract.py `
  src/hsconfig/runtime_apply.py `
  src/hsconfig/runtime_apply_receipts.py `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/output_publisher.py `
  src/hsconfig/package_io.py `
  tests/test_configure_prepublication_apply.py `
  tests/test_configure_publication.py `
  tests/test_output_publisher.py `
  tests/test_package_io.py `
  tests/test_runtime_apply_receipts.py `
  tests/test_live_start_session.py `
  tests/test_output_operation_admission.py `
  tests/test_atomic_io.py
git diff --check
git add -- `
  src/hsconfig/live_start_controller.py `
  src/hsconfig/live_start_faults.py `
  src/hsconfig/configure_run_model.py `
  src/hsconfig/configure_run_stage_contract.py `
  src/hsconfig/runtime_apply.py `
  src/hsconfig/runtime_apply_receipts.py `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/output_publisher.py `
  src/hsconfig/package_io.py `
  tests/test_configure_prepublication_apply.py `
  tests/test_configure_publication.py `
  tests/test_output_publisher.py `
  tests/test_package_io.py `
  tests/test_runtime_apply_receipts.py `
  tests/test_live_start_session.py `
  tests/test_output_operation_admission.py `
  tests/test_atomic_io.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: gate live publication on write free apply planning"
```

---

## Task 9: Seal Apply Attempts and Make Resume Recovery-Only

**Owned files**

- Create: `src/hsconfig/apply_invocation.py`
- Create: `src/hsconfig/runtime_live_admission.py`
- Create: `tests/test_apply_invocation.py`
- Create: `tests/test_runtime_live_admission.py`
- Modify: `src/hsconfig/live_start_session.py`
- Modify: `src/hsconfig/atomic_io.py`
- Modify: `src/hsconfig/package_io.py`
- Modify: `src/hsconfig/deck_config_ini.py`
- Modify: `src/hsconfig/current_output.py`
- Modify: `src/hsconfig/operator_profile.py`
- Modify: `src/hsconfig/output_publisher.py`
- Modify: `src/hsconfig/runtime_installer.py`
- Modify: `src/hsconfig/runtime_transaction_journal.py`
- Modify: `tests/test_live_start_session.py`
- Modify: `tests/test_atomic_io.py`
- Modify: `tests/test_package_io.py`
- Modify: `tests/test_deck_config_ini.py`
- Modify: `tests/test_current_output.py`
- Modify: `tests/test_operator_profile.py`
- Modify: `tests/test_output_publisher.py`
- Modify: `tests/test_runtime_installer.py`
- Modify: `tests/test_runtime_transaction_journal.py`

### Step 9.1: Write RED invocation-receipt tests

Add these exact tests:

- `test_apply_invocation_has_exact_closed_canonical_schema`
- `test_pre_apply_snapshot_binds_mapping_ini_state_receipt_tree_and_transactions`
- `test_apply_invocation_rejects_wrong_types_unknown_fields_size_or_self_digest`
- `test_apply_invocation_enforces_all_path_digest_text_and_list_boundaries`
- `test_runtime_snapshot_is_read_only_when_runtime_metadata_is_absent`
- `test_attempt_id_is_passed_unchanged_to_runtime_journal`
- `test_same_attempt_snapshot_projection_accepts_only_exact_own_journal_delta`
- `test_same_attempt_snapshot_projection_rejects_extra_missing_or_preexisting_attempt_id`
- `test_same_attempt_snapshot_projection_requires_validated_journal_delta_bearer`
- `test_same_attempt_journal_delta_rejects_fence_journal_or_pair_substitution`
- `test_apply_admission_reserves_one_transaction_slot_before_runtime_mutation`
- `test_prepare_apply_attempt_reserves_one_transaction_slot_before_prepared_cas`
- `test_runtime_admission_binds_exact_output_child_path_identity_and_binding_digest`
- `test_apply_invocation_and_runtime_admission_bind_output_operation_handoff_digest`
- `test_runtime_admission_binds_exact_output_operation_path_identity_and_digest`
- `test_runtime_admission_rejects_output_operation_identity_or_digest_substitution`
- `test_runtime_admission_rejects_replaced_byte_identical_output_child`

The nested snapshot has exactly:

```text
deck_name
mapping_value
deck_config_ini_sha256
runtime_state_sha256
last_apply_receipt_sha256
runtime_tree_sha256
transaction_ids
content_sha256
```

Use these exact constants and field sets:

```python
APPLY_INVOCATION_SCHEMA_VERSION = 1
APPLY_INVOCATION_MAX_BYTES = 128 * 1024
PRE_APPLY_TRANSACTION_IDS_MAX = 128
PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX = 127
PRE_APPLY_DECK_NAME_MAX_CHARS = 128
APPLY_INVOCATION_FIELDS = frozenset(
    {
        "schema_version",
        "apply_attempt_id",
        "run_id",
        "publication_revision",
        "publication_content_root_sha256",
        "output_operation_admission_path",
        "output_operation_admission_identity",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "output_child_path",
        "output_child_identity",
        "operator_profile_sha256",
        "runtime_root",
        "runtime_root_identity",
        "pre_apply_runtime_snapshot",
        "content_sha256",
    }
)
PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS = frozenset(
    {
        "deck_name",
        "mapping_value",
        "deck_config_ini_sha256",
        "runtime_state_sha256",
        "last_apply_receipt_sha256",
        "runtime_tree_sha256",
        "transaction_ids",
        "content_sha256",
    }
)
```

Both documents use a standard `sha256:<64-lowercase-hex>` self-digest. Run
and attempt IDs are exactly 32 lowercase hexadecimal characters.
`publication_revision` is exactly
`revisions/sha256-<64-lowercase-hex>`. Publication, profile,
output-operation-admission, and output-binding SHA fields are standard prefixed
digests. Output-child and runtime paths are
canonical absolute paths, and each identity is exactly three non-Boolean
integers. Deck name is safe text of 1
through 128 characters; mapping is null or one validated runtime component;
each state digest is null or standard; and transaction IDs are sorted, unique,
at most 128, and exactly 32 lowercase hexadecimal characters. Reject duplicate
keys, unknown fields, non-finite values, booleans as integers, relative or
noncanonical paths, and every boundary overflow before runtime mutation.

The sealed snapshot is captured before the controller creates its own schema-1
journal. Admission therefore requires at most
`PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX` transaction IDs and requires the new
`apply_attempt_id` to be absent, reserving exactly one slot within the existing
128-row representation bound. Every no-commit classifier uses only
`require_same_attempt_pre_apply_snapshot()`. The own-journal row requires an
active `ValidatedSameAttemptJournalDelta`, minted only under the exact
package/runtime pair after bounded no-follow validation of the schema-2 fence,
own schema-1 path, parent, identity, digest, transaction ID, allowed precommit
phase, admission, and raw transaction inventory. A public Boolean, ordinary
dataclass, stale pair, foreign attempt, or same-byte replacement cannot mint or
stand in for that bearer. The raw current IDs must then equal exactly
`sorted((*sealed.transaction_ids, apply_attempt_id))`; the helper removes only
the bearer-bound ID, canonically rebuilds the complete snapshot including its
self-digest, and requires the resulting complete bytes to equal the sealed
snapshot. The journal-absent row passes `validated_delta=None` and requires raw
full-snapshot equality. No extra, missing, replaced, or formerly sealed ID is
tolerated.
After authorized own-journal retirement and before `RECOVERY_STABILIZED`, the
unprojected current snapshot must again equal the complete sealed bytes. The
nonterminal classifier and terminal resolver call this same helper; neither
compares all raw fields while silently exempting `content_sha256`.

Run:

```powershell
python -B -m pytest `
  tests/test_apply_invocation.py::test_apply_invocation_has_exact_closed_canonical_schema `
  tests/test_apply_invocation.py::test_pre_apply_snapshot_binds_mapping_ini_state_receipt_tree_and_transactions `
  tests/test_apply_invocation.py::test_apply_invocation_rejects_wrong_types_unknown_fields_size_or_self_digest `
  tests/test_apply_invocation.py::test_apply_invocation_enforces_all_path_digest_text_and_list_boundaries `
  tests/test_apply_invocation.py::test_runtime_snapshot_is_read_only_when_runtime_metadata_is_absent `
  tests/test_apply_invocation.py::test_attempt_id_is_passed_unchanged_to_runtime_journal `
  tests/test_apply_invocation.py::test_same_attempt_snapshot_projection_accepts_only_exact_own_journal_delta `
  tests/test_apply_invocation.py::test_same_attempt_snapshot_projection_rejects_extra_missing_or_preexisting_attempt_id `
  tests/test_apply_invocation.py::test_same_attempt_snapshot_projection_requires_validated_journal_delta_bearer `
  tests/test_runtime_installer.py::test_same_attempt_journal_delta_rejects_fence_journal_or_pair_substitution `
  tests/test_runtime_live_admission.py::test_runtime_live_admission_has_no_installer_controller_or_published_apply_import `
  tests/test_runtime_live_admission.py::test_release_exact_runtime_admission_unlinks_only_bound_old_identity `
  tests/test_runtime_live_admission.py::test_release_exact_runtime_admission_accepts_absence_idempotently `
  tests/test_runtime_live_admission.py::test_release_exact_runtime_admission_preserves_valid_foreign_successor `
  tests/test_runtime_live_admission.py::test_release_exact_runtime_admission_rejects_replaced_malformed_or_same_identity_changed_bytes `
  tests/test_apply_invocation.py::test_apply_admission_reserves_one_transaction_slot_before_runtime_mutation `
  tests/test_live_start_session.py::test_prepare_apply_attempt_reserves_one_transaction_slot_before_prepared_cas `
  tests/test_runtime_installer.py::test_runtime_admission_binds_exact_output_child_path_identity_and_binding_digest `
  tests/test_runtime_installer.py::test_apply_invocation_and_runtime_admission_bind_output_operation_handoff_digest `
  tests/test_runtime_installer.py::test_runtime_admission_binds_exact_output_operation_path_identity_and_digest `
  tests/test_runtime_installer.py::test_runtime_admission_rejects_output_operation_identity_or_digest_substitution `
  tests/test_runtime_installer.py::test_runtime_admission_rejects_replaced_byte_identical_output_child `
  -q -p no:cacheprovider
```

Expected RED: import failure for `hsconfig.apply_invocation`.

### Step 9.2: Capture runtime state without creating it

Implement `capture_pre_apply_runtime_snapshot()` using bounded no-follow reads.
It may read `CustomConfig/deck_config.ini`, `.hsconfig/state.json`, the bound
last-apply receipt, the active mapped runtime tree, and the transaction
directory. It must not call `_ensure_runtime_layout()`, `mkdir()`, an apply
planner, or a recovery function. Missing surfaces become null digests or an
empty transaction list.

Revalidate the operator-profile runtime root and identity before capture. Bind
the canonical deck mapping from the `[Configs]` section only. Require a plain,
non-reparse active tree before hashing it.

### Step 9.3: Claim durable admission before the invocation becomes recovery-only

Add only under-lock primitives to `live_start_session.py`:

```python
def prepare_apply_attempt_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    invocation: ApplyInvocation,
    planned_admission_path: Path,
    planned_admission_staging_path: Path,
    planned_admission_staging_inner_temp_path: Path,
    planned_admission_parent_identity: PathIdentity,
    planned_admission_document_size: int,
    planned_admission_document_sha256: str,
) -> LiveStartSession:
    """CAS the intended invocation/admission; perform no physical write."""

def _complete_apply_started_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> LiveStartSession:
    """Perform only the final I/O-free CAS to APPLY_STARTED."""
```

Before its `PREPARED` CAS, `prepare_apply_attempt_under_lock()` validates the
sealed snapshot, requires no more than
`PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX` existing IDs, and requires the new
attempt ID to be absent. Capacity failure precedes session mutation, admission,
invocation receipt, schema-2 fence, schema-1 journal, and every runtime write;
no later helper may postpone or repeat this admission check.

There is no public standalone `begin_apply_attempt()` and no caller may write
an invocation receipt without already holding the exact durable admission. The
two primitives validate the active originating-thread session token, exact run
root and cursor, and never acquire a session, profile, package, publication, or
runtime lock. Task 10 calls both only while all those capabilities are already
held. Task 3 owns the receipt action/receipt-CAS state machine, but it exposes no
session-only physical receipt writer: Task 10 must execute each invocation-
receipt action through its capability-aware context adapter, then pass only the
opaque `RuntimeAdmissionStepReceipt` to
`advance_runtime_admission_under_lock()`. The module-private
`_complete_apply_started_under_lock()` accepts only the exact cursor whose
nested receipt action is already durably committed and performs one I/O-free
CAS to `APPLY_STARTED`; it cannot materialize, retire, commit, observe, or
reread a receipt. Task 10 fires
`after_admission_bound_before_invocation_write` only after the separately
receipt-bound `PRIMARY_APPLIED` cursor,
`after_invocation_receipt_staging_flush_before_staging_bound_cas` after staging
flush, `after_invocation_receipt_bound_commit_before_cas` after the identity-
preserving commit, and `after_invocation_write_before_apply_started` after the
committed-receipt CAS but before the final I/O-free phase CAS. Public wrappers
always pass `no_live_start_fault`.

The implementation order is fixed:

1. seal the invocation and planned admission bytes in memory, then CAS an
   `install_apply_invocation/PREPARED` transition from the explicit
   `PUBLICATION_COMMITTED` cursor; it binds attempt ID, invocation self-digest,
   exact canonical invocation-document byte size, admission path, exact
   profile-state-parent identity, and planned admission-document byte
   size/digest but performs no physical write; the helper accepts that parent
   identity explicitly and never recaptures it;
2. under the same profile, package/publication, and runtime leases, mint one
   runtime-admission materialize authorization and execute it before any raw
   admission observation. After exact staging is flushed, fault at
   `after_runtime_admission_staging_flush_before_staging_bound_cas`; consume its
   receipt in the `STAGING_BOUND` CAS with exact staging identity/size/digest;
3. mint a new bound-commit authorization, commit only that persisted identity
   by atomic no-replace, fault at
   `after_runtime_admission_bound_commit_before_cas`, and consume its receipt in
   `PRIMARY_APPLIED`, whose final identity equals the old staging identity and
   whose staging/temp are absent; the invocation-receipt action remains null;
4. derive and persist the exact seven-row runtime-layout binding. For each row,
   mint one create-or-confirm authorization, execute only that directory action,
   fault after its postcondition before receipt CAS, then consume the receipt to
   bind the exact identity and next cursor. After the last row the binding is
   `COMPLETE` and the same CAS installs the nested invocation-receipt file action
   as durably `PLANNED`, with its exact size copied from the persisted
   `apply_invocation_document_size` and its raw-byte digest copied from the
   persisted invocation artifact binding;
5. Task 10 validates the still-active session/profile/output-operation/pair and
   both exact final admission records, mints one receipt-materialize bearer,
   and passes it through `_execute_invocation_receipt_step_from_context()`.
   That adapter revalidates the same external context after bearer consumption,
   materializes and flushes only the exact invocation-receipt staging file,
   faults at
   `after_invocation_receipt_staging_flush_before_staging_bound_cas`, and
   returns one opaque receipt. Task 10 consumes it in a session CAS that leaves
   the outer stage `PRIMARY_APPLIED` while binding the nested action
   `STAGING_BOUND`;
6. Task 10 repeats that adapter sequence with a fresh bound-commit bearer. The
   callback identity-preservingly commits only that bound staging identity,
   faults at `after_invocation_receipt_bound_commit_before_cas`, and returns one
   opaque receipt. Task 10 consumes it in a second nested-action CAS, revalidates
   the canonical receipt bytes, self-digest, invocation binding, absent
   staging/temp, and every still-held outer capability, then faults at
   `after_invocation_write_before_apply_started`;
7. Task 10 alone calls `_complete_apply_started_under_lock()` through its
   external-context wrapper. In one final I/O-free CAS, the helper copies the
   exact admission binding into the session, binds the invocation digest,
   advances to `APPLY_STARTED`, clears the transition, and returns that sealed
   cursor;
8. only after that cursor exists may the installer create its schema-2 fence,
   schema-1 journal, staging path, target, state, or receipt.

`resume_pending_apply_invocation_under_lock()` classifies every boundary and
performs only the I/O-free rollback/final-CAS edges. An exact
`PREPARED` transition with no staging, admission, or receipt rolls back to the
byte-identical `PUBLICATION_COMMITTED` predecessor and never blocks or applies.
If any unbound deterministic staging/inner-temp exists, the Task-10 recovery
wrapper validates the outer context and passes one delete-guard callback through
its receipt adapter. It gives the opaque receipt to the Session helper, whose
cleanup CAS records absence and the next materialize action before rollback or
retry. No Session-only function observes or retires the file, and no path
promotes staged-only bytes after a process boundary. A crash after delete and
before the cleanup CAS remints from the old cursor, confirms exact absence in
the same external context, and issues the same opaque cleanup receipt.
Partial, replaced, extra, direct-
final-from-`PREPARED`, or mixed staging is a typed tamper stop. From a durable
`STAGING_BOUND` cursor, only the exact bound staging, exact final with that same
identity, or the declared POSIX same-identity two-link row may continue through
step 3. An exact
receipt with that same admission completes only the missing final CAS; from
the admission claim onward the attempt is globally blocking, and from the
   receipt write onward it is recovery-only. A receipt or `APPLY_STARTED` without
   the exact admission is a typed nonterminal `runtime_admission_missing_or_invalid`
   tamper stop. It creates no held carrier, result intent, or terminal status and
   is never adoption or new-apply authority. No helper deletes the receipt or invents a
replacement admission.

Add and run:

```powershell
python -B -m pytest `
  tests/test_live_start_session.py::test_invocation_prepared_intent_performs_no_physical_write `
  tests/test_live_start_session.py::test_admission_is_durable_before_invocation_receipt `
  tests/test_live_start_session.py::test_invocation_receipt_is_durable_before_apply_started_cas `
  tests/test_live_start_session.py::test_complete_apply_started_is_io_free_and_requires_committed_receipt_cursor `
  tests/test_live_start_session.py::test_public_session_surface_exposes_no_invocation_receipt_mutator `
  tests/test_live_start_session.py::test_invocation_pending_intent_absent_receipt_rolls_back_without_apply `
  tests/test_live_start_session.py::test_staging_only_admission_crash_securely_deletes_then_rolls_back `
  tests/test_live_start_session.py::test_partial_or_replaced_admission_staging_is_preserved_as_tamper `
  tests/test_live_start_session.py::test_admission_without_receipt_reconstructs_exact_same_invocation `
  tests/test_live_start_session.py::test_invocation_pending_exact_receipt_completes_apply_started_recovery_only `
  tests/test_live_start_session.py::test_invocation_or_apply_started_without_admission_is_rejected `
  tests/test_live_start_session.py::test_apply_attempt_primitives_never_reacquire_any_authority_lock `
  tests/test_live_start_session.py::test_resume_completes_pending_invocation_cas_then_recovers_without_apply `
  -q -p no:cacheprovider
```

Expected RED: session state has no admission-before-invocation transition.

### Step 9.4: Thread the caller-owned transaction ID into the installer

Add an optional `transaction_id` keyword to the existing public installer for
backward compatibility, an explicit runtime-lock lease, and a shared
paired controller capability for Task 10:

```python
def install_runtime_package(
    plan: RuntimeInstallPlan,
    *,
    fault_hook: FaultHook = no_fault,
    transaction_id: str | None = None,
) -> RuntimeInstallResult: ...

# current_output.py
@dataclass(frozen=True, slots=True)
class PackageInputLockToken: ...

@dataclass(frozen=True, slots=True)
class PackageInputLease:
    package_root: Path
    publication: OutputPublication | None
    content_root_sha256: str | None
    output_root: Path | None
    snapshot: BoundedFilesystemPackageView | None
    lock_token: PackageInputLockToken

# runtime_installer.py
@dataclass(frozen=True, slots=True)
class RuntimeApplyLockToken: ...

@dataclass(frozen=True, slots=True)
class RuntimeApplyLease:
    runtime_root: Path
    runtime_root_identity: PathIdentity
    apply_lock_path: Path
    apply_lock_identity: PathIdentity
    lock_token: RuntimeApplyLockToken

@dataclass(frozen=True, slots=True)
class ControllerApplyLeasePairToken: ...

@dataclass(frozen=True, slots=True)
class ControllerApplyLeasePair:
    package_lease: PackageInputLease
    runtime_lease: RuntimeApplyLease
    pair_token: ControllerApplyLeasePairToken

@contextmanager
def lease_controller_apply_pair(
    *,
    package_lease: PackageInputLease,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> Iterator[ControllerApplyLeasePair]: ...

# runtime_live_admission.py
RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION = 1
RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES = 64 * 1024
RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND = "live_start_runtime_admission"

@dataclass(frozen=True, slots=True)
class RuntimeLiveAttemptAdmissionEvidence:
    admission_path: Path
    admission_parent_identity: PathIdentity
    admission_identity: PathIdentity
    admission_sha256: str
    run_id: str
    apply_attempt_id: str
    retention_owner_run_id: str
    retention_fence_path: Path
    output_base_root: Path
    output_base_root_identity: PathIdentity
    output_root: Path
    output_root_identity: PathIdentity
    output_operation_admission_path: Path
    output_operation_admission_identity: PathIdentity
    output_operation_admission_sha256: str
    output_child_binding_sha256: str
    publication_revision: str
    publication_content_root_sha256: str
    apply_invocation_sha256: str

def require_live_admission_allows_legacy_root_bootstrap(
    *, runtime_root: Path
) -> None: ...

# runtime_installer.py -- pair-aware adapter over neutral admission primitives
def validate_same_attempt_journal_delta_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_attempt_id: str,
    expected_attempt_record_path: Path,
    expected_attempt_record_identity: PathIdentity,
    expected_attempt_record_sha256: str,
    expected_journal_path: Path,
    expected_journal_identity: PathIdentity,
    expected_journal_sha256: str,
    expected_journal_phase: Literal[
        "PREPARED", "RUNTIME_STAGED", "RUNTIME_VERIFIED"
    ],
) -> ValidatedSameAttemptJournalDelta: ...

# runtime_installer.py -- legacy/public unpaired wrapper only
@contextmanager
def lease_runtime_apply(
    runtime_root: Path,
    *,
    expected_root_identity: PathIdentity,
) -> Iterator[RuntimeApplyLease]: ...

@contextmanager
def _lease_runtime_apply_under_output_operation(
    *,
    output_operation_lease: OutputOperationAdmissionLease,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> Iterator[RuntimeApplyLease]: ...

# published_apply.py -- implemented in Task 10
@dataclass(frozen=True, slots=True)
class RuntimeAdmissionPhysicalStep:
    staging: MaterializedStagingBytes | None
    evidence: RuntimeLiveAttemptAdmissionEvidence | None
    step_receipt: RuntimeAdmissionStepReceipt

def _claim_runtime_live_attempt_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_admission_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    run_id: str,
    transaction_id: str,
    retention_owner_run_id: str,
    session_root: Path,
    session_root_identity: PathIdentity,
    operator_profile_sha256: str,
    admission_parent_identity: PathIdentity,
    output_base_root: Path,
    output_base_root_identity: PathIdentity,
    output_root: Path,
    output_root_identity: PathIdentity,
    output_operation_admission_sha256: str,
    output_child_binding_sha256: str,
    publication_revision: str,
    publication_content_root_sha256: str,
    apply_invocation_sha256: str,
    pre_apply_runtime_snapshot_sha256: str,
    admission_authorization: RuntimeAdmissionAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> RuntimeAdmissionPhysicalStep: ...

def _execute_invocation_receipt_step_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    action: Literal[
        "materialize_invocation_receipt_staging",
        "commit_bound_invocation_receipt",
        "retire_unbound_invocation_receipt_staging",
    ],
    admission_authorization: RuntimeAdmissionAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> RuntimeAdmissionStepReceipt: ...

def _complete_apply_started_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LiveStartSession: ...

def revalidate_runtime_live_attempt_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> None: ...

def _require_same_attempt_live_admission_allows_runtime_mutation_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> None: ...

def _release_runtime_live_attempt_from_pair(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    profile_lease: OperatorProfileLease,
    lease_pair: ControllerApplyLeasePair,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeAdmissionReleasePostcondition: ...

def _release_or_confirm_runtime_live_attempt_without_old_leases(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeAdmissionReleasePostcondition: ...

# Both release adapters use Task 3's pre-I/O consume executor. The paired
# adapter handles the held normal path; the bounded fast path may unlink the
# exact old record or confirm old absence or an identity-distinct canonical
# foreign successor without reacquiring historical external leases.
# Their callback maps the neutral observation field-for-field into Task 3's
# RuntimeAdmissionReleasePostcondition; Task 3 then compares every historical
# field and closed nullability row against the consumed private bearer.

# runtime_live_admission.py
def require_live_admission_allows_publication(
    *,
    output_root: Path,
    output_root_identity: PathIdentity,
) -> None: ...

def require_live_admission_allows_profile_mutation() -> None: ...

def require_live_admission_allows_runtime_mutation(
    *,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
) -> None: ...

RuntimeLiveAttemptReleaseDisposition = Literal[
    "old_unlinked",
    "already_absent",
    "valid_foreign_successor",
]

@dataclass(frozen=True, slots=True)
class RuntimeLiveAttemptReleaseObservation:
    admission_path: Path
    admission_parent_identity: PathIdentity
    historical_admission_identity: PathIdentity
    historical_admission_sha256: str
    disposition: RuntimeLiveAttemptReleaseDisposition
    foreign_successor_identity: PathIdentity | None
    foreign_successor_sha256: str | None

def release_runtime_live_attempt_exact(
    *,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeLiveAttemptReleaseObservation: ...

# runtime_installer.py
def observe_runtime_layout_bootstrap_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    retention_owner_run_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    state_key: str,
) -> RuntimeLayoutBootstrapEvidence: ...

def bootstrap_runtime_layout_directory_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    layout_authorization: RuntimeLayoutBootstrapAuthorization,
) -> RuntimeLayoutBootstrapStepReceipt: ...

def observe_initial_runtime_install_from_pair(
    plan: RuntimeInstallPlan,
    *,
    lease_pair: ControllerApplyLeasePair,
    observation_authorization: RuntimeObservationAuthorization,
    transaction_id: str,
    retention_owner_run_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeObservationReceipt: ...

@dataclass(frozen=True, slots=True)
class RuntimeAttemptEvidenceRetirementStep:
    action: Literal["journal", "fence"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

def _retire_success_attempt_evidence_step_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_retention_fence_path: Path,
    expected_retention_fence_identity: PathIdentity,
    expected_retention_fence_sha256: str,
    expected_journal_path: Path,
    expected_journal_identity: PathIdentity,
    expected_journal_sha256: str,
    expected_target_owner_journal_path: Path,
    expected_target_owner_journal_identity: PathIdentity,
    expected_target_owner_journal_sha256: str,
    expected_target_path: Path,
    expected_target_identity: PathIdentity,
    expected_runtime_admission_path: Path,
    expected_runtime_admission_parent_identity: PathIdentity,
    expected_runtime_admission_identity: PathIdentity,
    expected_runtime_admission_sha256: str,
    action: Literal["journal", "fence"],
) -> RuntimeAttemptEvidenceRetirementStep: ...
```

The functions explicitly labelled `published_apply.py` are locked call shapes
for Task 10, not Task-9 implementation work. Task 9 implements the
neutral admission byte/parser/guard primitives and the runtime-installer lease
pair only. Task 10 owns the session/profile-capability-aware claim,
revalidation, and release adapters, avoiding any reverse import from
`runtime_installer.py` or `runtime_live_admission.py` into `published_apply.py`.

Validate the ID with the existing runtime-journal grammar. The legacy public
path generates `uuid.uuid4().hex` only when no ID was supplied. The controller
pair context receives already-active session, profile, fixed output-operation,
and published `PackageInputLease` capabilities. Its
`output_operation_admission` parameter is always the immutable historical
Evidence already bound in the exact session; the context itself observes the
current fixed paths under `output_operation_lease`. It never treats a
caller-loaded Evidence object as proof that the old record is still present.
Before observing or creating `.hsconfig` or `apply.lock`, and before acquiring
the Runtime lock, it revalidates every same-thread bearer, the exact persisted
session bytes, profile/runtime/output/publication bindings, the already-existing
exact plain runtime-root identity, and exactly one row of this closed entry
matrix:

- **Before handoff:** allow only exact non-preview `PUBLICATION_COMMITTED` or
  the same attempt's
  `install_apply_invocation/PREPARED|STAGING_BOUND|PRIMARY_APPLIED`. Runtime
  admission Evidence is null before a final exists and exact only where that
  persisted transition already binds it. The historical `ACTIVE` output record
  is physically exact; its fixed staging/temp are absent or match only that
  transition's explicitly bound precommit row.
- **After handoff:** allow only the same attempt's
  `APPLY_STARTED|APPLY_COMMITTED|RUNTIME_MATCHED`, nonterminal recovery row, or
  paired terminal-resolution row. Runtime admission Evidence is non-null and
  byte-/identity-exact to the current same-attempt final and the complete session
  binding. The historical output record is either exact old, exactly absent, or
  replaced by one canonical identity-distinct foreign successor; staging/temp
  are absent.

The post-handoff row additionally requires the complete persisted
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED` binding. A pre-handoff old-record absence or
foreign successor, a post-handoff missing/foreign Runtime admission, a same-run
or same-byte old-record replacement, or any stage-incompatible staging/temp
fails before runtime-root bootstrap, lock I/O, observation, or mutation. If the
old record remains present on post-handoff entry, the pair may first finish only
its already-authorized release; it may not observe or mutate the controller
fence, journal, candidate, target, INI, state, or receipt beforehand. A valid
foreign successor is observed and preserved byte-identically.

The sole controller pre-attempt physical exception remains idempotent, no-follow
create-or-confirm of the already bound plain runtime root's `.hsconfig`
directory and empty persistent `apply.lock`. It never creates the runtime root,
any other Runtime surface, or semantic write authority. Only after the selected
matrix row and this narrow bootstrap validate does the context acquire the
runtime lease in the fixed order and mint one opaque shared pair token. The
token binds all five bearer identities, roots, locks, run/session lineage,
entry-cursor digest as mint provenance, context nonce, and originating thread.
It is not invalidated merely because the same active `LiveStartSessionLease`
performs an authorized whole-session CAS and directly reassigns its returned
cursor. Every action-specific adapter nevertheless rereads and validates the
currently persisted, exact directly returned cursor and rejects a stale,
constructed, skipped, or non-descendant cursor before observation or I/O.
Controller claim/install/recovery/match/ack/release accepts only that
`ControllerApplyLeasePair`; a package-only caller or two independently acquired
same-thread leases are not a pair. The context never reacquires any outer lock.
Every component token is invalidated in `finally` before unlock and rejects
forgery, mixed contexts, cross-thread use, or use after exit. A shallow copy
shares the same bearers and expires with them; it never mints authority.

Task 9 adds the package token to the existing `lease_package_input()` context so
the paired API is green in the same task. It preserves direct-package and
published-package read compatibility, but only a published lease may enter the
controller pair. Task 10 then adds the stricter
published-current revalidation required by the live composite; no Task-9 writer
depends on a later token definition.
`_install_locked()` must receive the validated ID instead of generating one.
If a journal with that ID already exists, refuse new installation and require
recovery.

The public/unpaired path first calls Task 8's single neutral lock-bootstrap
helper and then enters `OutputOperationAdmissionLease`. Package-free recovery
requires all three fixed operation paths absent and an already existing exact
runtime root, then calls `_lease_runtime_apply_under_output_operation()`
directly, producing the exact order `output-operation -> runtime`. Public
installation also requires the three-path gate and acquires
`PackageInputLease` beneath it before any runtime-root creation, producing the
fixed order `output-operation -> package -> runtime`.

Only the backward-compatible public unpaired install may handle a missing
caller-selected runtime root. After the output-operation and Package/apply gates
and the exact fake/apply receipt are all valid, Task 10's private
`_authorize_legacy_runtime_root_bootstrap_from_context()` revalidates both active
same-thread leases, calls
`require_live_admission_allows_legacy_root_bootstrap(runtime_root=...)`, binds
the nearest existing plain ancestor plus exact/absent root predecessor, and
mints one opaque, thread-bound, single-use
`LegacyRuntimeRootBootstrapAuthorization`. Malformed or unsafe singleton state
blocks globally; a valid admission for the same canonical root path blocks even
when its recorded old root identity is no longer present; a canonical valid
admission for another root follows the existing root-scoping rule.

Only Task 10's private `_bootstrap_legacy_runtime_root_from_context()` consumes
that authorization. Before its first path observation or directory mutation it
validates the still-active lease objects, Package/apply receipt, canonical path,
predecessor, and ancestor from the private bearer registry, then performs
`require_live_admission_allows_legacy_root_bootstrap()` again as the final
pre-I/O check under the still-held output-operation lease. It create-or-confirms
only the authorized bounded missing directory suffix, one plain no-follow child
at a time, rereads every identity, and returns the exact final root identity. It
rejects missing, forged, copied, stale, reused, cross-thread, wrong-root, wrong-
gate, or wrong-ancestor authorization before `mkdir`; a callback failure spends
the bearer. It also rejects a changed ancestor, raced occupant, reparse point,
ADS, hardlink-like unsafe metadata, non-directory, or identity substitution.
It creates no `.hsconfig` or semantic Runtime artifact. No public export,
controller Pair, recovery path, or ordinary Package lease can mint or call this
compatibility mutation directly.

The public wrapper then passes only that returned identity to
`_lease_runtime_apply_under_output_operation()`. The private helper validates
the already-held operation lease and exact existing root, never reacquires the
operation lease, and only then may securely create or confirm `.hsconfig` and
the persistent empty `apply.lock`. Immediately after acquiring the Runtime lock
and immediately before the first semantic write, it repeats both the output-
operation and Runtime-admission gates. A hard kill after root creation but
before Runtime-lock acquisition leaves at most a plain empty, non-authoritative
Legacy root; a fresh public invocation may recapture it only after repeating the
same gates and safety checks. Within one invocation, the captured root identity
must never change. Controller Pair and every recovery path remain strictly
existing-root-only and cannot call the Legacy bootstrap. No caller may create
`runtime_root`, `.hsconfig`, or `apply.lock` before the applicable gates; no path
may create `transactions`, staging, state, a last-apply receipt, `CustomConfig`,
or a runtime target merely to obtain the Runtime lock. Every acquired lease is
held until the complete Runtime mutation or legacy recovery returns.
`install_runtime_package()`, `recover_runtime_state()`,
`recover_runtime_attempt()`, `runtime_apply.py`, and every broad public wrapper
delegate only through these two orders. A read-only planning lease opened before
mutation is released before the operation lease and is never upgraded in place.
The paired controller path never calls the public/private generic wrapper and
never reacquires the operation lease because its expanded pair entry validates
Task 10's exact capability directly.

Immediately before the first semantic Runtime write, an unpaired wrapper
revalidates the still-held output-operation three-path gate and then the
root-scoped Runtime-admission gate under the Runtime lock. The neutral gate has
no same-attempt exception. Only
`_require_same_attempt_live_admission_allows_runtime_mutation_from_pair()` may
accept an exact final Runtime admission, and it first authenticates the active
same-thread pair token plus exact Evidence from the current controller cursor.

After the fixed runtime admission wins, and before the invocation receipt or
`APPLY_STARTED`, `observe_runtime_layout_bootstrap_from_pair()` derives the
exact seven-row layout binding from the already-held runtime root and state key.
It is read-only: existing rows are sealed with their current plain-directory
identities; absent rows bind null predecessors and the already sealed direct
parent. Task 10 persists those bytes, then calls
`bootstrap_runtime_layout_directory_from_pair()` for exactly the current row.
That adapter first revalidates the active session, profile, output-operation,
pair, and exact final Runtime-admission capabilities against the current row.
It then passes one create-or-confirm callback through Task 3's pre-I/O consume
executor. It uses `secure_create_directory()` only for a persisted absent row,
or confirms the exact existing identity; it never calls
`_ensure_runtime_layout()` or a multi-directory helper. A create-before-CAS
empty child is the sole permitted postcondition for the absent row. Each receipt
CAS binds its identity before the next directory or any child authority file.
The completed binding remains in the session and supplies every parent identity
to the invocation and recovery cursors without recapture. A crash at any row is
globally fenced by the already committed runtime admission.

On the seventh row,
`bootstrap_runtime_layout_directory_from_pair()` must build the planned
invocation-receipt action exclusively from the current sealed session cursor:
the canonical byte size comes from `apply_invocation_document_size`, and the
raw-byte digest comes from `successor_artifact_bindings`. It receives no
`ApplyInvocation`, does not read a receipt or staging file, and does not
recapture runtime state. The final layout receipt CAS rejects any different
size even when the supplied digest and paths are otherwise valid.

Consume Task 3's shared `atomic_materialize_staging_bytes()` and
`atomic_commit_bound_staging_no_replace()` plus Task 8's sole replace extension
while preserving the legacy INI wrapper. Task 9 adds no second staging/commit
implementation or divergent hook contract. Controller code never calls the compatibility
`atomic_publish_bytes_no_replace()` wrapper.

Every controller authority-file action carries the exact generic
`external_file_action` in the session recovery cursor. The deterministic inner
temp and unbound staging are rollback-only after a hard kill: under the
persisted `PLANNED` intent and parent identity, a fresh executor may capture an
occupant only as a verified-delete guard and remove it; it never parses,
promotes, or adopts those bytes. A directory, reparse point, unexpected link,
ADS, parent replacement, second temp, direct final successor, or other name is
tamper. One uninterrupted materialization callback returns complete staging;
its receipt CAS binds `STAGING_BOUND`. Only a later callback can move that
persisted identity to final.

This contract is mandatory for every controller authority file in the plan:

- runtime admission, prepublication and terminal cleanup inventories;
- each schema-2 attempt-retention create/transition/finalization;
- every controller schema-1 journal create/transition/finalization;
- deck-config INI, runtime state, last-apply receipt, and owner-retirement
  create/transition.

Each family uses exact deterministic final/staging/inner-temp names under its
already bound parent. Its bounded enumerator accepts only the universal
`PLANNED` and `STAGING_BOUND` rows and rejects every other residue. Existing
legacy schema-1 UUID temps retain only their separately typed bounded promotion
compatibility path. A controller inner temp or unbound staging already present
at helper entry first completes executor-backed retirement and its receipt CAS;
no fast path may rename, promote, or adopt it. A POSIX final+staging pair is legal
only after `STAGING_BOUND`, only for the same persisted identity with total
`nlink=2`, and is reduced to final-only before the commit receipt is issued.

Real subprocess-kill tests cover every `AtomicWriteFaultPoint` for admission
staging, both cleanup inventories, schema-2 retention, and owner retirement, plus the
admission callback before final no-replace. Resume must end at exactly the old
or new canonical authority with zero reserved-temp residue; public operator
wrappers expose no fault hook.

`_claim_runtime_live_attempt_from_pair()` passes exactly one neutral callback
through `_execute_runtime_admission_physical_step()`. The unbound-cleanup action
verifies and retires only staging/temp and returns the receipt consumed by
`unbound_staging_retired`. The materialize action
adapts `STAGING_MATERIALIZE_FAULT_POINT` to
`after_runtime_admission_staging_flush_before_staging_bound_cas`; the separate
bound-commit action adapts `NO_REPLACE_COMMIT_FAULT_POINT` to
`after_runtime_admission_bound_commit_before_cas`. The latter returns final
evidence only after the singleton is complete, flushed, reread, and its identity
equals the persisted staging identity. Callback hooks are private test
instrumentation, not caller authority.

Before any admission staging retirement, materialization, or bound commit, the
adapter revalidates the active session, profile, output-operation, and pair
capabilities; the exact fixed output-operation final path, parent, identity,
digest, run/session/profile/output bindings; and absence of its fixed staging
and reserved temp. Only the already consumed, action-specific
`RuntimeAdmissionAuthorization` permits that one same-attempt callback to cross
the generic output-operation Runtime gate. A loaded or constructed
`OutputOperationAdmissionEvidence` cannot use this exception, and a stale,
foreign, replaced, wrong-root, or wrong-thread capability invokes no observer
or mutator.
`_execute_invocation_receipt_step_from_context()` is the sole physical adapter
for the later invocation-receipt staging, cleanup, and commit actions. Before
mint, Task 10 validates the active Session/Profile/output-operation/pair and both
exact final records. The adapter passes exactly one receipt callback through
`_execute_runtime_admission_physical_step()`; inside that callback and therefore
after bearer consumption but before observation or I/O, it repeats the same
capability, cursor, invocation, output-record, runtime-admission, and pair
validation. It returns only the opaque receipt. Task 10 immediately consumes
that receipt with `advance_runtime_admission_under_lock()` and directly assigns
the returned cursor. A stale, forged, expired, wrong-thread, wrong-record, or
cross-action context invokes zero receipt observers or mutators.

After the committed-receipt CAS, Task 10 revalidates the same external context
once more and calls `_complete_apply_started_from_context()`. That wrapper fires
`after_invocation_write_before_apply_started` and invokes only Task 3's private,
I/O-free `_complete_apply_started_under_lock()` CAS. The Session module never
imports Profile, output-operation, package, Runtime-pair, or Task-10 modules and
exposes no physical receipt mutation path. Admission actions cannot use receipt
paths or bytes, and receipt actions cannot create, replace, or release the
admission singleton.
The default call supplies no custom hook and must reach both admission and the
existing INI delegation without `NameError` or `TypeError`. The INI wrapper
continues to receive and forward all of its existing string-named stages
unchanged; only the new exact stage above is adapted to the live-start hook.

The process-independent singleton admission is fixed at
`%LOCALAPPDATA%\HSConfig\live-start-active-attempt.json`, outside every
repository, run, output, package, and runtime root. The neutral module
`runtime_live_admission.py` owns its bounded parser, expected-absence create,
exact-identity reread, and exact release. It imports no operator-profile,
publisher, installer, or controller module; those callers pass only primitive
canonical paths, identities, digests, and optional exact evidence. Its
`require_live_admission_allows_legacy_root_bootstrap()` check is the only
root-identity-free entry: it runs under the already-held output-operation and
Package leases, compares the requested canonical path to the fixed record, and
can only reject or prove that the narrow Legacy root bootstrap is presently
unfenced. It creates no path and grants no same-attempt authority. Its
primitive same-attempt comparison accepts only already validated paths,
identities, digests, and parsed evidence. The pair-aware adapter is owned by
`runtime_installer.py`, because only that module can authenticate
`ControllerApplyLeasePairToken` against its private active-pair registry. After
authenticating the pair it may call those neutral primitives. The neutral
module never imports, structurally inspects, or duck-types an installer pair;
the dependency direction cannot reverse.

The singleton's
canonical self-digested document has exactly:

```text
schema_version
record_kind
run_id
apply_attempt_id
retention_owner_run_id
session_root
session_root_identity
operator_profile_sha256
state_root_identity
runtime_root
runtime_root_identity
output_base_root
output_base_root_identity
output_root
output_root_identity
output_operation_admission_path
output_operation_admission_identity
output_operation_admission_sha256
output_child_binding_sha256
publication_revision
publication_content_root_sha256
package_root_sha256
pre_apply_runtime_snapshot_sha256
apply_invocation_sha256
retention_fence_path
content_sha256
```

All identifiers, paths, identities, digests, and field sets use the existing
closed grammars and reject Booleans as integers. The record is immutable from
claim until exact release; it is admission authority, not a target owner,
transaction journal, or replacement for the schema-2 attempt fence. Its parent
is created only by the already-authorized profile setup or identity-guarded
state bootstrap; observation never creates it.

Admission claim and every same-attempt recovery additionally require
the exact immutable output-operation-admission digest across session,
invocation, runtime admission, and the current fixed predecessor during
handoff; after authorized unlink the historical session/invocation/runtime
values remain equal,
`output_child_binding.claim_state=RETIRED`, byte-for-byte equality of the
output-child-binding digest across session, invocation, and admission, equality
of child path/identity and publication revision/content root across all three
documents, the same values in `runtime_admission_binding`, and a currently
opened child with that persisted identity. Mixed nullability or a path-,
identity-, revision-, or digest-mismatch blocks before runtime observation or
mutation. These controller facts are not added to schema-1 journals or durable
target-owner records.

Use Task 3's shared staging-materialize and identity-preserving no-replace commit
primitives; keep `atomic_publish_bytes_no_replace()` only as the legacy INI
compatibility wrapper. The invocation `PREPARED` row binds the deterministic
attempt-owned staging child
`.live-start-active-attempt.<run-id>.<apply-attempt-id>.staged`, its exact inner
temp, the fixed final path, parent identity, and exact final byte size/digest
before any appears. Its `external_file_action` is `PLANNED`. One executor
materializes and flushes staging; its receipt alone persists the identity and
`STAGING_BOUND`. Only a new executor may commit that bound identity to the
absent singleton with Windows no-replace move or POSIX
`renameat2(RENAME_NOREPLACE)`/hard-link fallback and flush the parent. Never use
`os.replace()` or an existence check followed by replacement.

Across a process boundary, `PREPARED` with absent surfaces may roll back;
unbound staging/temp is delete-only and is never promoted; final-only is
tamper. `STAGING_BOUND` accepts only bound-staging-only, final-only with the
same identity, or the POSIX final+staging two-link intermediate with that same
identity. The last is completed by unlinking staging and rereading final at
`nlink=1`. Different identities, partial/wrong bytes, extra surfaces, or missing
bound staging/final are tamper. Thus the final singleton is absent or one
complete canonical file with the identity already persisted before commit. A
present exact same-run/same-attempt admission may enter only targeted
continuation or recovery; no restart freshly captures its final identity.

Retain and rerun Task 8's
`test_atomic_publish_no_replace_default_hook_and_named_stage_are_compatible`
and add
`test_deck_config_ini_preserves_existing_fault_stage_delegation` to
`tests/test_deck_config_ini.py`. The first exercises the production default and
the one exact named inner stage; the second proves every existing INI stage is
unchanged.

Task 8's output-operation family is globally visible as the fixed final record
plus fixed staging and reserved-temp siblings. Runtime-admission final is fixed,
but its precommit staging is attempt-owned and is never treated as a globally
discoverable fence. Every public, direct, or legacy Runtime writer therefore
acquires the output-operation lease before the Runtime lock, allows only all
three operation paths absent, and revalidates that gate immediately before its
first semantic Runtime write. It then applies the root-scoped Runtime-admission
gate. A malformed occupant in either family blocks. During live handoff both
exact final records coexist, and the older output record may disappear only
after the Runtime record is durably bound. Under each writer's mutation locks:

- every generic Runtime writer rejects any output-operation occupant and then
  rejects a valid Runtime admission whose `runtime_root` and identity match;
  neither gate accepts caller-supplied Evidence as an exception;
- the owning composite alone crosses the first gate for admission claim and the
  seven layout rows through fresh action-scoped bearers after revalidating the
  exact session/profile/output-operation/pair context. After the final Runtime
  admission exists, only the private same-attempt pair adapter may continue;
- `publish_configure_run_under_guard()` and its legacy wrapper reject a valid
  admission whose `output_root` and identity match before reconciliation,
  revision cleanup, staging creation, or current-pointer mutation;
- every profile enable/disable/rebind rejects any present fixed admission before
  profile CAS, regardless of old or requested roots. The profile is one global
  singleton; even absent-profile enable against unrelated valid roots must wait
  for the admitted attempt to finish.

Malformed, replaced, noncanonical, or identity-drifted singleton bytes block
all three affected mutation classes. Publication mutation for a proven
unrelated root may proceed after its fixed-operation checks. Generic Runtime
mutation does not receive an unrelated-root exception while any output-
operation path exists; profile mutation is also always globally fenced, and the
expected-absence create admits only one controller attempt globally.
An equal canonical root path with a different current identity is tamper and
blocks; it is never reclassified as an unrelated root.
The checks race safely: admission claim already holds the exact profile,
output-operation, publication/package, and Runtime locks in that order. A
generic installer holds `output-operation -> package -> runtime`; package-free
recovery holds `output-operation -> runtime`; neither takes a reverse edge.
Every different controller attempt and every legacy/direct affected writer
therefore stops before a profile/pointer/revision/fence/journal/staging/target/
state/receipt mutation. Broad legacy recovery may report the singleton but
never adopt, progress, overwrite, or remove it.

All claim, revalidation, and release helpers validate the exact active,
same-thread paired capabilities before reading or mutating admission. The
claim helper is private and is callable only from Task 10 after that composite
has also validated its already-held `session_lease`, explicit PREPARED session
cursor, `profile_lease`, `output_operation_lease`, and exact active
output-operation evidence; its session root/identity arguments are copied
from that active lease and may never be reconstructed from `run_id` or a path.
No public session-only, path-only, or installer API exposes claim. The
normal held release adapter is callable only by the held Task-10 terminal
capability; it revalidates the active profile/pair before delegating the exact
old-record action. After the durable `ADMISSION_RELEASE_AUTHORIZED` CAS, resume
may instead use the bounded lease-free adapter with the active session lease and
persistent admission path, parent, identity, and digest. It neither reacquires
nor depends on the historical profile, output, package, publication, or runtime
lease. Both adapters pass one callback through Task 3's pre-I/O consume
executor. The neutral primitive unlinks only the exact old record, confirms its
absence, or preserves a fully canonical identity-distinct foreign successor;
it never recaptures or creates the parent and never mutates foreign evidence.
An `EVIDENCE_RETIRED` cursor is rejected without observing, unlinking, or
consuming authority. `observe_initial_runtime_install_from_pair()` requires the
already-claimed exact admission and completed layout, and performs one bounded
read-only all-same-attempt-surfaces-absent observation for the planned attempt.
It requires the exact `first_install` observation bearer and passes that
read-only callback through Task 3's executor. It returns only the opaque receipt
whose private successor is the complete initial `RuntimeApplyRecoveryEvidence`;
it creates no fence, journal, candidate, staging, target, state, receipt, or
temp. Task 10 consumes that receipt only in the Session CAS that binds those
registry-private bytes. Every later physical row, including the first schema-2 fence staging
write, goes through `recover_runtime_attempt_from_pair()` with one nonterminal
authorization and one receipt. Missing, replaced, malformed, wrong-run, or
wrong-attempt admission is contradictory evidence, never permission to install.
A crash after admission creation but before invocation receipt or the initial
recovery cursor is positive same-attempt continuation authority: recovery
validates the pending session, profile, historical publication revision,
invocation digest, and unchanged complete pre-apply snapshot, completes or
revalidates every pending layout row, finishes the one planned invocation
receipt, reaches `APPLY_STARTED`, and binds the same initial cursor before any
attempt authority-file write. After that cursor exists, recovery may advance
only the existing attempt and never prepares a second first-install cursor.
Admission remains until the exact terminal session cursor is durable and its
status-closed release succeeds.

Use `RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION = 2`, a 64 KiB canonical maximum,
and record kind `live_start_runtime_attempt_retention`. Reject every unknown
field, mixed state/nullability row, duplicate key, noncanonical path, unsafe ID,
Boolean integer, size overflow, and self-digest mismatch before using a record.

Keep the existing runtime transaction journal schema version 1 byte-for-byte
unchanged. A `FINALIZED` v1 journal with `owns_target=true` remains the durable
target-ownership authority used by existing-owner validation and old-revision
cleanup for every caller. No success acknowledgement may delete that owner.

Legitimate later old-revision cleanup records durable owner succession without
changing schema 1. Before mutating an acknowledged stale owner or its target,
the installer atomically writes
`.hsconfig/owner-retirements/<owner-transaction-id>.json`. The
`runtime_installer.py` module owns this document and these exact constants:

```python
RUNTIME_OWNER_RETIREMENT_SCHEMA_VERSION = 1
RUNTIME_OWNER_RETIREMENT_MAX_BYTES = 4 * MAX_RUNTIME_TRANSACTION_BYTES
RUNTIME_OWNER_RETIREMENT_MAX_ENTRIES = MAX_RUN_FILES
RUNTIME_OWNER_RETIREMENT_KIND = "runtime_owner_retirement"
RUNTIME_OWNER_RETIREMENT_FIELDS = frozenset(
    {
        "schema_version",
        "record_kind",
        "state",
        "retired_owner_transaction_id",
        "initial_owner_journal_path",
        "initial_owner_journal_identity",
        "initial_owner_journal_sha256",
        "retired_target_path",
        "retired_target_parent_identity",
        "retired_target_identity",
        "retired_target_tree_sha256",
        "successor_transaction_id",
        "successor_package_root_sha256",
        "successor_owner_journal_path",
        "successor_owner_journal_identity",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
        "cleanup_entry_count",
        "cleanup_entries",
        "completed_cleanup_cursor",
        "completed_owner_journal_identity",
        "completed_owner_journal_sha256",
        "content_sha256",
    }
)
RUNTIME_OWNER_RETIREMENT_CLEANUP_ENTRY_FIELDS = frozenset(
    {
        "relative_path",
        "entry_kind",
        "identity",
        "expected_parent_identity",
        "size",
        "sha256",
    }
)
```

State is exactly `PREPARED|COMPLETED`; IDs, paths, identities, tree/file/self
digests, sizes, duplicate keys, and canonical bytes use the existing strict
grammars. Each cleanup entry is a canonical strict descendant path. Files carry
exact identity, parent identity, size, and SHA-256 and must be plain regular,
`nlink=1`, no-ADS/no-reparse; directories carry exact identity and parent with
null size/digest and must be plain/no-reparse. Files precede directories in the
existing deepest-first schema-v1 cleanup order. The target root is deliberately
not an entry and is retired by its own action. Count equals list length, and the
manifest digest covers the full ordered identity-inclusive list. PREPARED and
COMPLETED tombstones carry byte-identical `cleanup_entries` and manifest facts.
Both derived v1 bytes and both tombstones are size-checked before the first
Session cursor or physical mutation; overflow stops.

The durable Session `owner_retirement` cursor is created before the first
tombstone byte. It binds the exact initial schema-1 owner, exact target and
parent, already `FINALIZED` successor owner/package, canonical full-tree digest,
cleanup digest/count, first entry if any, and planned canonical PREPARED-
tombstone size/digest. Before that CAS, the complete unchanged target is bounded
once to build the full identity-inclusive list. After a hard kill while the
cursor is still `PREPARED_PLANNED` and the final tombstone is absent, the already
consumed materialization callback may enumerate the still-complete tree only as
a candidate. It must reproduce root/parent, every entry identity, complete
canonical list, count, manifest digest, tombstone size, and planned tombstone
digest exactly; it updates no persisted field. Only those exact bytes may be
staged and committed. Same-byte, empty-directory, parent, or root replacement
changes the commitment and stops. Once PREPARED is committed, re-enumeration is
permanently forbidden and every next-entry authority comes only from the exact
tombstone list.

`initialize_owner_cleanup_journal` is the sole transition from exact old v1
`FINALIZED,owns_target=true,cleanup_started=false` to the fully derived v1
successor `cleanup_started=true,cursor=0`; it commits through the generic staged
file protocol and does not delete an entry or increment the cursor. If the
inventory count is zero, its callback also rereads the exact PREPARED tombstone,
derives the canonical COMPLETED bytes from that list plus the cursor-zero v1
successor, and its receipt CAS binds the resulting size/digest commitment.
While the
tombstone remains PREPARED, each target entry has two later durable rows:
`delete_owner_cleanup_entry` removes or confirms absence of only the exact bound
entry without changing the cursor, then a separately staged
`advance_owner_cleanup_journal` commits only cursor `n+1`. When that successor
first reaches count, the same callback rereads the exact PREPARED tombstone,
derives the canonical COMPLETED bytes from its immutable list plus the exact
final v1 successor, and its receipt CAS binds their size/digest commitment. The
next entry comes from the unchanged PREPARED list. No token loops over two entries, combines a
delete with a journal write, or calls `_prepare_cleanup_journal()` or
`_resume_owned_cleanup()` as a monolithic controller callback. Their pure list
builder may be shared with the legacy wrapper; a legacy path seeing a recognized
controller-owned successor must use this tombstone protocol or fail closed.

After cursor equals count, both planned COMPLETED commitment fields must already
be exact. `retire_owner_target_root` alone securely removes or confirms
authorized absence of the exact empty root under its bound parent. Its bearer,
postcondition, and receipt repeat that commitment plus the exact PREPARED
tombstone and final-v1 triplets. Its receipt CAS reaches `TARGET_RETIRED` and
installs the COMPLETED-tombstone file intent only from the persisted values.
Materialization rereads only that exact PREPARED tombstone, canonically derives
the COMPLETED bytes, and requires their size/digest to equal the commitment.
Only after that staging identity is bound may
`commit_owner_retirement_completed` commit the permanent successor with the full
cursor and exact final old-owner identity/digest. Only then may
`retire_old_owner_journal` delete that exact journal or confirm its authorized
absence; its receipt CAS records `OWNER_RETIRED`. A crash before COMPLETED
resumes only the next persisted row; a crash after COMPLETED but before delete
removes only the bound journal; a crash after delete before CAS confirms only
that absence. Same-byte substitution, backward/skipped cursor, changed entries,
missing successor owner, or undeclared physical state is tamper. COMPLETED is a
permanent authenticated tombstone. An old successful live-start session accepts
only its exact live owner or an exact completed tombstone whose initial owner,
target, parent, successor, list, and cursor proofs match the acknowledgement.

The owner-retirement subtrace is exhaustive:

```text
materialize -> commit_owner_retirement_prepared
materialize -> initialize_owner_cleanup_journal(cursor=0)
[delete_owner_cleanup_entry
 -> materialize -> advance_owner_cleanup_journal] * cleanup entry count
retire_owner_target_root -> TARGET_RETIRED
materialize -> commit_owner_retirement_completed
retire_old_owner_journal
observe_owner_retirement_completed
```

The initial cursor-zero transition is mandatory, including for zero entries.
Every old-v1 successor size/digest is bound before staging. The zero-entry
initialization or last nonzero cursor advance binds the COMPLETED commitment
before root retirement. Entry absence never
advances the durable cursor without the following v1 commit; a v1 cursor never
advances without the preceding exact entry absence. With zero entries the trace
goes from initialized cursor zero directly through root retirement; COMPLETED is
still forbidden until the root-removal receipt CAS reaches `TARGET_RETIRED`.

The owner callbacks return private, action-specific postconditions, never a
Boolean or caller-built successor evidence. Initialization and cursor-advance
postconditions bind predecessor/successor old-v1 identities/digests, manifest
digest, count, cursor, and—only when the successor cursor equals count—the exact
derived COMPLETED-tombstone size/digest. The root-retirement postcondition binds
target path, historical target identity, parent identity, the already persisted
COMPLETED commitment, the exact PREPARED tombstone/final-v1 triplets, and exactly
`removed|already_absent`. Task 3's executor consumes the bearer before each
callback and constructs the sole complete successor behind the opaque receipt.

Controller-owned attempts add a separate canonical schema-2 retention record at
`.hsconfig/attempt-retention/<apply-attempt-id>.json`. It has exactly schema,
record kind, attempt ID, retention-owner run ID,
`ACTIVE|CANDIDATE_PLANNED|CANDIDATE_BOUND|PRIOR_OWNER_PLANNED|
PRIOR_OWNER_BOUND|FINALIZED` state,
attempt-journal path/identity/digest, package digest, target path/identity,
attempt `owns_target`, target-owner-journal path/identity/digest, and
self-digest. It also has exact planned-attempt-journal path, byte-size, and
byte-digest fields plus candidate path, candidate-parent identity, and nullable
candidate identity. `ACTIVE` requires every journal/target/candidate/planned
field null. `CANDIDATE_PLANNED` binds the deterministic candidate path, exact
parent identity, absent predecessor, and planned v1 `PREPARED` bytes before
either file or directory exists. `CANDIDATE_BOUND` additionally binds the exact
v1 journal and plain candidate identities after their separate receipt/CAS
steps. `PRIOR_OWNER_PLANNED`
requires exact deterministic target and separate owner triplets,
`owns_target=false`, candidate/staging absence, and exact planned v1
`PREPARED` path/size/digest; its observed journal identity/digest are null until
that file exists. `PRIOR_OWNER_BOUND` requires an exact v1
`PREPARED` no-op attempt journal, exact deterministic pre-existing target, exact
separate `FINALIZED,owns_target=true` owner journal, package digest, and
`owns_target=false`; its bytes equal the planned commitment and
candidate/staging authority is forbidden. `FINALIZED`
requires all exact applicable evidence. Every non-final state remains an active
fence. The record is not a second target owner and never parses or serializes as
a v1 journal.

Under the paired leases, first claim and reread the exact singleton admission,
complete and bind the runtime-layout cursor, then write and reread schema-2
`ACTIVE` before creating the v1 transaction journal or mutating runtime files.
The `ACTIVE` create and every later schema-2 replace use separate materialize
and identity-preserving commit receipts. A new target progresses through the
closed candidate phases and its owning attempt journal is also its durable
owner. Before its v1 create or candidate `mkdir`, the cursor stages and commits
`ACTIVE -> CANDIDATE_PLANNED` with the exact candidate parent/path, package-tree
manifest, and planned v1 bytes. Create and reread only that v1 file through the
generic staged journal rows, then create at most one plain empty
candidate. `bind_created_candidate` is the sole create-or-confirm row: its
persisted predecessor still says candidate absent, while its callback may either
create the one plain empty child or confirm the exact plain-empty postcondition
left by an action-before-CAS crash. It validates the bound parent and path,
plain-directory type, emptiness, no reparse metadata or ADS, and no additional
surface before returning the candidate identity. A crash after `mkdir` but
before the candidate-identity receipt CAS may bind that new identity only
through the same row; it never writes or rebinds v1. After that receipt CAS a
separate `bind_candidate_fence` action CASes `CANDIDATE_PLANNED ->
CANDIDATE_BOUND`. Only the bounded reread of `CANDIDATE_BOUND` may begin copy or
staging. The candidate manifest is consumed one entry per
`materialize_candidate_tree_entry` receipt/CAS. A file action may confirm an
action-before-CAS leaf only as exact safe manifest content under the held pair;
its identity is not retained as durable authority and a safe same-byte occupant
is equivalent. Wrong bytes, kind, source/root/parent, extra entry, hardlink,
ADS, or reparse stops. After the full cursor, one
`RUNTIME_STAGED` v1 commit records the staged tree, one
`verify_candidate_tree` action binds its exact digest, and one separately staged
v1 commit records `RUNTIME_VERIFIED`. `rename_candidate_to_target` then rereads
full manifest parity and moves or confirms only that bound Candidate-root
identity at the absent target. `bind_renamed_target` rereads full parity again
before ownership. A distinct
staged `bind_renamed_target` v1 commit records target identity and ownership;
only its successor may plan the New-Target INI action. Candidate copy, journal
transition, verification, rename, and target-owner binding never share a token.
Nonempty, unsafe, additional, replaced, or wrong-parent candidates are tamper
and never become authority. For an exact deterministic target that
already exists, the paired
controller installer must not enter the legacy candidate-delete branch. Before
creating any candidate it verifies the target tree from the leased package,
target identity, and a separate exact `FINALIZED,owns_target=true` owner. It
constructs the canonical v1 `PREPARED` no-op bytes in memory and stages then
commits the schema-2 record `ACTIVE -> PRIOR_OWNER_PLANNED`, binding target/owner
plus the exact planned path, size, and digest before the file exists. Only then
may it materialize and commit exactly those no-replace v1 bytes. It separately
stages then commits `PRIOR_OWNER_PLANNED -> PRIOR_OWNER_BOUND` with that journal
identity/digest;
only after bounded reread of the durable bound row
may it write and verify the INI. It then advances the v1 journal directly from
`PREPARED -> INI_COMMITTED` with `owns_target=false` and the bound target
identity, continues normal state/receipt finalization, and finally CASes the
retention record to `FINALIZED`. This path creates no candidate or staging tree
and never calls `_remove_owned_tree(candidate)`. The existing public legacy
wrapper keeps its compatibility behavior but cannot authorize this controller
route. A crash at any boundary is progressed only by targeted recovery for the
same run and attempt; another run cannot create its own admission or evidence
first.

The uninterrupted New-Target action trace and every resumed trace are
byte-for-byte the same ordered action literals below. Each `materialize` is the
generic `materialize_file_action_staging` row and is followed by one separate
listed commit receipt/CAS:

```text
materialize -> commit_bound_initial_attempt_record(ACTIVE)
materialize -> commit_bound_candidate_planned_attempt_record
materialize -> advance_controller_transaction_journal_write(PREPARED)
bind_created_candidate
materialize -> bind_candidate_fence(CANDIDATE_BOUND)
materialize_candidate_tree_entry * exact manifest entry count
materialize -> advance_controller_transaction_journal_write(RUNTIME_STAGED)
verify_candidate_tree
materialize -> advance_controller_transaction_journal_write(RUNTIME_VERIFIED)
rename_candidate_to_target
materialize -> bind_renamed_target
materialize -> write_deck_config_ini
materialize -> commit_ini_journal
materialize -> write_runtime_state
materialize -> commit_state_journal
materialize -> write_last_apply_receipt
materialize -> finalize_journal
materialize -> finalize_attempt_record
[zero or more closed owner-retirement rows]
observe_committed
```

The Prior-Owner trace shares the initial `ACTIVE` commit, then uses
`commit_bound_prior_owner_planned_attempt_record`, v1 `PREPARED`,
`commit_bound_prior_owner_attempt_record`, and the common INI/state/receipt/
finalization suffix without a candidate. A generic materialize action can never
skip its preselected commit literal, and no commit literal can consume a
`PLANNED` rather than `STAGING_BOUND` file action.

`select_terminal_classification` is never part of either uninterrupted success
trace. It is an alternate pure-CAS edge only after a failed or aborted action has
been reread under all held authorities and Task 9 classifies the exact persisted
predecessor.

A crash while `ACTIVE` has no v1 or candidate resumes by staging and committing
the already selected route. It becomes the unchanged-snapshot `NOT_COMMITTED`
row only after `select_terminal_classification -> observe_not_committed` instead
of that legal continuation. `CANDIDATE_PLANNED` with neither child similarly
continues by creating the planned v1 or uses that exact selection edge for the
same no-tree classification. With only exact v1 it may bind/continue or, after
the persisted selection, use journal-then-fence retirement. With one plain
empty unbound candidate it may bind the identity through the closed recovery
action or terminalize only after durable tree-cleanup authority is established.
A crash at `PRIOR_OWNER_PLANNED` with
the journal absent retires only
that exact fence after revalidating the planned bytes are still absent and the
target/owner exact. With the exact planned journal present it may either bind
that identity in `PRIOR_OWNER_BOUND` and continue the same attempt or first
select `observe_not_committed`, terminalize `FAILED_PRESERVED`, and use
journal-then-fence retirement; it never
reobserves or adopts target/owner. A crash after `PRIOR_OWNER_BOUND` but before
INI write may take the corresponding prior-owner no-tree `NOT_COMMITTED` row
only through the pure selection edge and only while the intended final INI
successor is absent; its target
and owner remain byte-identical while only the attempt journal and fence are
retired. A crash after the physical INI write but before the v1 journal CAS is a
commit-recovery row: recovery uses only the prebound target and owner, verifies
the intended INI successor, advances the journal monotonically, and never
cleans the prior target as a no-commit attempt. Replaced owner/target, a
candidate on this route, or any mixed binding blocks before INI, state, receipt,
or cleanup mutation.

Before every installer/recovery old-revision cleanup, bounded enumeration of the
closed attempt-retention directory rejects malformed rows and treats every
other controller fence as a preservation fence for its bound journal, owner,
and target. A later package may install elsewhere, but it cannot mutate or
delete fenced evidence until that fence's own closed retirement does so. While
a matching retention record exists, broad legacy recovery may report but never
adopt, progress, clean, or delete its v1 attempt journal. For positively
proven `NOT_COMMITTED`, targeted recovery may remove an exact non-owning journal
and then the fence only after the shared same-attempt projection proves the
sealed snapshot before journal retirement and raw equality after it; incomplete
or contradictory evidence remains. Once the fence is absent, legacy owner
validation and old-revision cleanup continue to use the retained owning v1
journal exactly as before.

That preterminal cleanup rule does not authorize deleting evidence already
named by a durable terminal pending/unknown result. Terminal-result targeted
recovery keeps the historical result triplets immutable and may progress active
fence/journal bytes only through the persisted
terminal-resolution predecessor/successor contract. A no-commit tree cleanup
must pass through the run-local identity inventory and monotone session cursor;
the journal-less branch uses only its exact direct fence transition. It
releases only singleton admission after stable classification and the later
release-authorization CAS.

Only private `_retire_success_attempt_evidence_step_from_pair()` retires
successful attempt evidence after it verifies the active paired capability, session lease,
exact persisted `terminal_retirement/PREPARED|ACK_JOURNAL_RETIRED` cursor,
the exact stage/action/ownership row above, single-use terminal authorization,
current package and match, singleton admission, retention record,
journal/owner identities and digests, nonpending receipt/state/INI facts, and no
recovery work. One call accepts exactly one closed action, mutates or confirms
at most that one journal or fence row only inside
`_execute_terminal_resolution_physical_step()`, and returns one
opaque receipt. For a new owning attempt the sole action retains the v1 owner
and deletes only the fence. For a non-owning attempt the first action deletes
the exact no-op journal and retains the separately bound owner; only after its
receipt CAS reaches `ACK_JOURNAL_RETIRED` may a fresh token authorize the fence
action. It never deletes admission itself. The held Task-10 capability
revalidates the profile parent, package, runtime, persisted terminal session,
and each post-action state, consumes each receipt through
`advance_terminal_retirement_under_lock()`, then calls the private
paired admission path on the uninterrupted held route only after CASing
`ADMISSION_RELEASE_AUTHORIZED`. It passes the exact release callback through the
Task-3 executor, unlinks only the old exact identity, and makes no later session
CAS. Resume from that durable cursor uses the lease-free release-or-confirm
adapter and does not reacquire historical profile/package/runtime authority. A
crash between those transitions resumes forward only from the exact terminal-retirement
cursor and never reapplies. Legacy callers without a controller fence
preserve their existing behavior but cannot mutate while admission exists.

Add `test_transaction_id_requires_exact_lowercase_hex` to
`tests/test_runtime_transaction_journal.py` and include it in the focused
installer RED/GREEN cycle. It must reject uppercase, wrong-length, non-hex,
boolean, and path-like values before any runtime mutation.

Also add focused installer tests
`test_caller_owned_transaction_id_is_reused_and_never_regenerated`,
`test_existing_exact_transaction_requires_recovery_without_install`, and
`test_recover_runtime_attempt_inspects_only_the_exact_transaction`. Add
`test_recovery_bootstraps_only_metadata_directory_and_empty_apply_lock`,
`test_caller_owned_nonowning_finalized_journal_survives_installer_return`, and
`test_caller_owned_already_current_attempt_retains_noop_journal_until_ack`, and
`test_generic_recovery_never_adopts_or_deletes_controller_retained_journal`, and
`test_acknowledge_runtime_attempt_retires_only_exact_attempt_evidence`. Also add
`test_schema_v1_owner_bytes_remain_exact_and_field_absent`,
`test_schema_v2_attempt_record_is_separate_from_schema_v1_target_owner`,
`test_controller_attempt_record_blocks_broad_recovery_of_matching_v1_transaction`,
`test_new_install_ack_preserves_owner_then_later_identical_install_is_already_current`,
`test_new_install_ack_preserves_owner_then_later_install_cleans_stale_revision`,
`test_already_current_ack_deletes_nonowner_attempt_but_preserves_existing_owner`,
`test_fault_between_owner_finalization_and_attempt_record_finalization_recovers_exactly`,
`test_fault_between_nonowner_delete_and_attempt_record_delete_is_idempotent`,
`test_package_input_lease_token_is_nonforgeable_thread_bound_and_expires`,
`test_runtime_apply_lease_token_is_nonforgeable_thread_bound_and_expires`, and
`test_runtime_lease_consumer_rejects_forged_expired_or_wrong_root_token`. Add
`test_controller_apply_pair_rejects_independently_acquired_or_mixed_leases`,
`test_candidate_planned_fence_then_v1_journal_binds_identity_and_digest_before_finalization`,
`test_controller_prior_owned_target_uses_no_staging_nonowner_path`,
`test_prior_owner_planned_crash_before_v1_create_preserves_owner_and_proves_not_committed`,
`test_prior_owner_planned_crash_after_v1_create_never_adopts_target_or_owner`,
`test_prior_owner_planned_to_bound_is_exact_and_candidate_free`,
`test_prior_owned_target_crash_before_ini_remains_prepared_no_tree`,
`test_prior_owned_target_crash_after_ini_before_journal_recovers_as_commit`,
`test_nonowning_fastpath_rejects_same_byte_target_or_owner_substitution`,
`test_legacy_nonowner_path_remains_compatible`,
`test_same_byte_fence_journal_or_owner_substitution_fails_closed`,
`test_later_changed_install_preserves_committed_mismatch_fenced_evidence`,
`test_owner_retirement_tombstone_has_exact_closed_canonical_schema`,
`test_owner_retirement_rejects_unknown_fields_bounds_self_digest_or_substitution`,
`test_owner_retirement_reserved_temp_hard_kills_reconcile_before_enumeration`,
`test_owner_retirement_crash_matrix_resumes_each_cleanup_cursor_and_owner_delete`,
`test_owner_cleanup_writes_completed_tombstone_before_deleting_old_owner`, and
`test_old_success_accepts_exact_owner_retirement_tombstone_after_later_cleanup`.
Add
`test_owner_retirement_prepared_and_completed_use_external_file_action`,
`test_owner_retirement_uses_one_tombstone_entry_or_journal_action_per_receipt_cas`,
`test_owner_retirement_old_owner_unlink_requires_completed_receipt_cas`,
`test_owner_retirement_prepared_record_carries_complete_identity_inventory`,
`test_owner_retirement_prepared_reconstructs_only_exact_precommitted_candidate`,
`test_owner_retirement_prepared_reconstruction_rejects_same_byte_file_empty_directory_parent_or_root_replacement`,
`test_owner_retirement_initializes_cleanup_started_at_cursor_zero_before_first_delete`,
`test_owner_retirement_advance_journal_only_increments_after_bound_entry_absence`,
`test_owner_retirement_zero_entry_tree_retires_root_before_completed`,
`test_owner_retirement_root_rmdir_action_before_cas_confirms_only_authorized_absence`,
`test_owner_retirement_final_v1_cursor_binds_completed_tombstone_commitment`,
`test_owner_retirement_root_receipt_uses_only_prebound_completed_commitment`,
`test_owner_retirement_root_crash_rejects_tombstone_list_or_final_v1_substitution`,
`test_owner_retirement_terminal_observer_exports_exact_partial_owner_evidence`,
and `test_schema_v1_cleanup_initialization_is_monotone_only_at_finalized_cursor_zero`.
Add
`test_runtime_live_admission_has_closed_bounded_schema_fixed_path_and_absent_cas`,
`test_two_process_claim_race_creates_exactly_one_admission_without_replacement`,
`test_crash_after_admission_before_invocation_receipt_continues_same_attempt_once`,
`test_different_attempt_is_rejected_by_admission_before_fence_journal_or_runtime_write`,
`test_legacy_runtime_writer_rejects_active_controller_admission`,
`test_legacy_runtime_writer_rejects_output_operation_before_runtime_admission_final`,
`test_legacy_runtime_writer_rejects_output_operation_staging_or_reserved_temp`,
`test_legacy_runtime_recovery_rejects_output_operation_before_temp_or_journal_reconciliation`,
`test_legacy_runtime_lock_order_is_output_operation_then_runtime`,
`test_public_runtime_writer_checks_output_operation_then_runtime_admission_before_first_write`,
`test_controller_pair_entry_requires_exact_session_profile_output_operation_and_package_capabilities`,
`test_controller_pair_entry_rejects_forged_stale_cross_thread_or_wrong_cursor_before_runtime_bootstrap`,
`test_controller_pair_entry_creates_only_hsconfig_and_apply_lock_before_apply_intent`,
`test_controller_pair_reentry_after_runtime_handoff_accepts_old_exact_absent_or_valid_foreign_output_record`,
`test_controller_pair_reentry_requires_exact_release_authorized_session_and_runtime_admission`,
`test_controller_pair_reentry_rejects_active_absence_same_byte_replacement_staging_or_foreign_runtime_admission`,
`test_controller_pair_token_accepts_only_persisted_same_lease_cursor_descendants`,
`test_public_installer_lock_order_is_output_operation_then_package_then_runtime`,
`test_public_installer_never_acquires_output_operation_while_holding_package`,
`test_already_gated_runtime_helper_never_reacquires_output_operation`,
`test_blocked_public_installer_creates_no_runtime_root_hsconfig_or_apply_lock`,
`test_legacy_root_bootstrap_gate_rejects_same_path_active_or_malformed_final_admission`,
`test_same_attempt_recovery_revalidates_exact_admission`, and
`test_forged_replaced_wrong_run_or_wrong_attempt_admission_fails_closed`.
The generic Runtime tests instrument the public install and broad recovery
wrappers. Install must prove `output-operation -> package -> runtime`; package-
free recovery proves `output-operation -> runtime`. Both require the neutral
operation lease before `runtime_root`, `.hsconfig`, `apply.lock`, or the Runtime
lock, repeat the three-path check and then Runtime-admission check before the
first mutator, hold all acquired locks to return, and invoke zero mutators for
final, staging, temp, malformed, replaced, or foreign operation state. The Pair
entry tests prove that an ordinary Package lease is insufficient: every outer
capability and the exact allowed session row is authenticated before the narrow
lock bootstrap, and no later action surface is created. The re-entry matrix tests
drop the original process after the authorized output-record unlink, reacquire
all leases and one new Pair from the exact persisted session, and prove that only
the exact same-attempt Runtime admission permits continuation. The Legacy-root
neutral-gate test proves that same-path final, staging, temp, malformed, or
substituted admission state never authorizes a root mutation; Task 10 owns the
public absent-root compatibility adapter and its capability tests.
Add `test_runtime_admission_requires_staging_bound_before_final` and
`test_runtime_file_actions_use_planned_staging_bound_commit_matrix` and
`test_invocation_receipt_uses_apply_start_capability_and_bound_staging` to
`tests/test_runtime_installer.py`; cover materialize, delete-only unbound
residue, bound move/replace, final-only bound confirmation, POSIX two-link
completion, direct-final tamper, and post-bind same-byte substitution. Extend
`test_terminal_physical_helpers_return_receipt_and_reject_reused_authorization`
and `test_controller_first_install_has_no_monolithic_multiwrite_callback`
to instrument the raw observer/mutator and require zero calls for every invalid
bearer before mutation.
Add `test_runtime_live_admission_has_no_installer_controller_or_published_apply_import`
to `tests/test_runtime_live_admission.py`. Also add
`test_release_exact_runtime_admission_unlinks_only_bound_old_identity`,
`test_release_exact_runtime_admission_accepts_absence_idempotently`,
`test_release_exact_runtime_admission_preserves_valid_foreign_successor`, and
`test_release_exact_runtime_admission_rejects_replaced_malformed_or_same_identity_changed_bytes`
to that file. Add
`test_pair_observation_receipt_binds_exact_requested_initial_recovery_evidence`,
`test_runtime_observation_receipt_rejects_wrong_pair_admission_attempt_family_or_runtime_change`,
`test_runtime_observation_receipt_is_single_use_and_cross_thread_bound`,
`test_failure_selection_receipt_rejects_constructed_literal_and_visible_ini_not_committed`,
and `test_runtime_attempt_recovery_family_nullability_rejects_mixed_fields`
to `tests/test_runtime_installer.py`; the first parameterizes first-install,
nonterminal, terminal-resolution, and terminal-classification families and
proves the receipt privately binds the one raw observation. Move
`test_same_attempt_journal_delta_rejects_fence_journal_or_pair_substitution`
to `tests/test_runtime_installer.py`; it covers a genuine, forged, expired,
cross-thread, wrong-root, and substituted pair while the neutral importgraph
test proves there is no reverse dependency.
Add `test_attempt_retention_reserved_temp_hard_kills_reconcile_before_enumeration`
to `tests/test_runtime_installer.py`.
Add `test_terminal_no_commit_inventory_deletes_only_bound_candidate_and_target_entries`,
`test_terminal_no_commit_inventory_rejects_same_bytes_empty_directory_or_parent_replacement`,
`test_terminal_no_commit_metadata_tokens_are_action_bound_single_use_and_ordered`,
`test_terminal_physical_helpers_return_receipt_and_reject_reused_authorization`,
`test_commit_recovery_mutates_one_persisted_row_per_token_and_receipt`,
`test_success_ack_threads_one_receipt_per_deleted_row`,
`test_nonowning_ack_crash_after_journal_before_fence_resumes_from_ack_journal_retired`,
`test_owning_ack_deletes_only_fence_before_evidence_retired`,
`test_terminal_inventory_reconstructs_only_exact_precommitted_bytes_after_prepared_crash`,
`test_terminal_inventory_prepared_rejects_same_byte_entry_or_parent_identity_substitution`,
`test_nonterminal_recovery_authorization_advances_exactly_one_row_per_token`,
`test_nonterminal_recovery_rejects_null_terminal_forged_reused_or_cross_attempt_authority`,
`test_terminal_and_nonterminal_recovery_authorities_are_mutually_exclusive`,
`test_runtime_apply_recovery_matrix_covers_external_file_action_and_every_legacy_row`,
`test_null_authority_runtime_observer_never_promotes_or_deletes_uuid_temps`,
`test_recovery_legacy_temp_actions_mutate_exactly_one_bound_temp_per_receipt`,
`test_controller_journal_observer_reports_staging_only_in_external_file_action`,
`test_controller_journal_observer_never_classifies_new_staging_as_transaction_temp`,
`test_controller_journal_commit_requires_staging_bound_identity`,
`test_controller_journal_posix_link_crash_accepts_only_same_bound_identity`,
`test_terminal_and_nonterminal_legacy_temp_evidence_bind_origin_classification_path_parent_identity_size_and_digest`,
`test_runtime_layout_bootstrap_fixed_order_and_existing_missing_rows`,
`test_runtime_layout_bootstrap_crash_after_each_directory_create_resumes_without_authority_file`,
`test_runtime_layout_bootstrap_rejects_parent_replacement_reparse_ads_and_nonempty_created_child`,
`test_initial_active_and_route_fence_commits_are_distinct_staged_rows`,
`test_new_target_candidate_tree_copy_verify_rename_and_v1_phases_are_one_row_each`,
`test_candidate_leaf_action_before_cas_confirms_only_exact_safe_manifest_content`,
`test_candidate_same_byte_safe_replacement_is_content_equivalent`,
`test_candidate_leaf_rejects_wrong_bytes_source_parent_root_extra_hardlink_ads_or_reparse`,
`test_candidate_manifest_is_reverified_before_rename_and_owner_binding`,
`test_new_target_ini_runs_only_after_target_owner_binding`,
`test_first_install_uninterrupted_and_resumed_action_trace_is_identical`,
`test_candidate_planned_precedes_v1_and_candidate_create`,
`test_created_candidate_is_bound_by_journal_then_fence_receipts`,
`test_candidate_planned_create_or_confirm_matrix_handles_absent_and_exact_empty_rows`,
`test_candidate_create_crash_before_identity_receipt_remints_without_adoption`,
`test_candidate_create_or_confirm_rejects_nonempty_replaced_wrong_parent_and_unsafe_candidate`,
`test_candidate_identity_receipt_cas_precedes_candidate_fence_commit`,
`test_controller_first_install_has_no_monolithic_multiwrite_callback`,
`test_success_ack_receipt_rejects_terminal_resolution_evidence_family`,
`test_nonterminal_recovery_closes_pending_and_unknown_without_physical_mutation`,
`test_failure_selection_matrix_is_exhaustive_for_new_target_and_prior_owner`,
`test_prior_owner_bound_before_ini_can_select_not_committed`,
`test_not_committed_selection_rejects_visible_intended_ini_successor`,
`test_visible_idempotent_successor_resumes_current_action_instead_of_selecting`,
`test_failure_selection_rejects_pair_admission_fence_journal_candidate_owner_or_snapshot_drift`,
`test_pending_and_unknown_selection_preserve_exact_retained_evidence`,
`test_candidate_planned_fence_with_prepared_journal_and_no_tree_resolves_not_committed_in_order`,
`test_precommit_noop_keeps_separately_authenticated_owner`,
`test_no_tree_resolution_rejects_unexpected_tree_or_missing_replaced_owner`, and
`test_active_fence_without_v1_journal_resolves_only_from_unchanged_snapshot`
and `test_no_commit_same_attempt_projection_allows_only_bound_own_transaction_and_restores_full_digest`
to `tests/test_runtime_installer.py`.
Add `test_admission_atomic_no_replace_is_absent_or_complete_at_every_crash_boundary`,
`test_admission_atomic_no_replace_never_overwrites_two_process_winner`,
`test_admission_staging_inner_temp_hard_kills_reconcile_before_no_replace`,
`test_staging_flush_crash_is_cleaned_without_promotion_or_runtime_write`, and
`test_prepared_admission_parent_substitution_fails_without_recapture`.
Add `test_controller_legacy_and_preview_publishers_reject_matching_admission_before_pointer_or_revision_write`
to `tests/test_output_publisher.py`. Add
`test_profile_enable_disable_and_rebind_reject_any_admission_before_cas` and
`test_deleted_profile_cannot_be_reenabled_on_unrelated_root_while_admission_exists`
to `tests/test_operator_profile.py`. Both tests use real process barriers and
prove the current pointer/profile bytes remain byte-identical until the owning
attempt releases admission; a malformed fixed admission blocks rather than
being ignored.

### Step 9.5: Add exact-attempt recovery

Add to `runtime_installer.py`:

```python
RuntimeRecoveryObservationFamily = Literal[
    "nonterminal_apply",
    "terminal_resolution",
]

@dataclass(frozen=True, slots=True)
class RuntimeAttemptRecovery:
    transaction_id: str
    status: Literal[
        "not_committed",
        "committed",
        "recovered",
        "committed_receipt_pending",
        "unknown",
    ]
    package_root_sha256: str | None
    receipt_path: Path | None
    retained_attempt_record_path: Path | None
    retained_attempt_record_identity: PathIdentity | None
    retained_attempt_record_sha256: str | None
    retained_journal_path: Path | None
    retained_journal_identity: PathIdentity | None
    retained_journal_sha256: str | None
    target_owner_journal_path: Path | None
    target_owner_journal_identity: PathIdentity | None
    target_owner_journal_sha256: str | None
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None
    observation_family: RuntimeRecoveryObservationFamily | None
    initial_apply_recovery_evidence: RuntimeApplyRecoveryEvidence | None
    initial_terminal_resolution_evidence: TerminalResolutionEvidence | None
    runtime_observation_receipt: RuntimeObservationReceipt | None
    apply_recovery_step_receipt: ApplyRecoveryStepReceipt | None
    terminal_resolution_step_receipt: TerminalResolutionStepReceipt | None

@dataclass(frozen=True, slots=True)
class RuntimeFailureSelection:
    disposition: Literal[
        "resume_current_action",
        "select_terminal_observation",
    ]
    expected_recovery_sha256: str
    expected_action_index: int
    expected_action: RuntimeApplyRecoveryAction
    selected_observation: RuntimeTerminalObservationAction | None

def classify_runtime_failure_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    expected_recovery: RuntimeApplyRecoveryEvidence,
) -> RuntimeFailureSelection: ...

def observe_runtime_failure_selection_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    expected_recovery: RuntimeApplyRecoveryEvidence,
    observation_authorization: RuntimeObservationAuthorization,
) -> RuntimeObservationReceipt: ...

def recover_runtime_attempt(
    runtime_root: Path,
    *,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_deck_name: str,
) -> RuntimeAttemptRecovery: ...

def recover_runtime_attempt_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_deck_name: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observation_family: RuntimeRecoveryObservationFamily | None = None,
    runtime_observation_authorization: RuntimeObservationAuthorization | None = None,
    nonterminal_recovery_authorization: RuntimeAttemptRecoveryAuthorization | None = None,
    terminal_authorization: TerminalRetirementAuthorization | None = None,
) -> RuntimeAttemptRecovery: ...

# With nonterminal authority this adapter executes or confirms exactly the one
# RuntimeApplyRecoveryAction named by the persisted cursor, including every
# schema-2 route commit, v1 phase commit, candidate entry/verification/rename,
# New-Target INI step, and owner-retirement row. It delegates the callback to
# Task 3's pre-I/O executor and returns exactly one opaque receipt. It never
# calls _install_locked(), _cleanup_old_revision(), or _resume_owned_cleanup()
# as a controller callback.

@dataclass(frozen=True, slots=True)
class RuntimeNoCommitCleanupStep:
    next_cursor: int
    current_entry_was_already_absent: bool
    cleanup_roots_absent: bool
    step_receipt: TerminalResolutionStepReceipt

@dataclass(frozen=True, slots=True)
class RuntimeNoCommitMetadataStep:
    action: Literal["journal", "fence"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

def delete_runtime_no_commit_entry_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    terminal_authorization: TerminalRetirementAuthorization,
    inventory: TerminalResolutionCleanupInventory,
    expected_cursor: int,
) -> RuntimeNoCommitCleanupStep: ...

def retire_runtime_no_commit_metadata_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["journal", "fence"],
) -> RuntimeNoCommitMetadataStep: ...
```

`classify_runtime_failure_from_pair()` is a bounded, read-only diagnostic under
the active pair and exact runtime admission. It never mutates Runtime or Session
state and never reacquires a lock. `resume_current_action` requires
`selected_observation=null`; `select_terminal_observation` requires exactly one
`observe_not_committed|observe_pending|observe_unknown`. The result binds the
exact persisted recovery digest, index, and current action. It validates the
same-attempt snapshot projection, fence, journal, Candidate/prior-owner facts,
and nested file action. An exact idempotent successor selects resume. A complete
precommit no-commit proof with no final intended INI successor may select
`observe_not_committed`; incomplete-but-coherent retained evidence may select
pending, and bounded contradiction may select unknown. Substitution never
normalizes to no-commit. The returned dataclass is observation, not CAS
authority. `observe_runtime_failure_selection_from_pair()` is the sole
authoritative adapter: it requires the exact `terminal_classification`
observation bearer, runs that classifier inside Task 3's pre-consumed callback,
and returns only the opaque receipt. The receipt privately binds the recovery
digest/index/current action and exact selected observation. A visible intended
INI successor can therefore never mint an `observe_not_committed` receipt.

The public observation path acquires or narrowly bootstraps the persistent runtime apply lock,
inspects only the exact retention record, transaction, bound target owner, and
state/receipt/target, and reuses existing journal phase recovery helpers. It
never creates a new attempt record, journal, staging directory, target,
state, last-apply receipt, `CustomConfig`, apply plan, or new transaction ID.
Unrelated journals cannot be adopted as the requested attempt. A missing
`.hsconfig` plus missing exact transaction is positive `not_committed` evidence
after lock bootstrap; it is not an unknown or an excuse to install.

`recover_runtime_attempt_from_pair()` validates the active shared pair and exact
admission and never reacquires a lock. Its observation, nonterminal, and
terminal authorization parameters are mutually exclusive. A controller initial
observation requires exactly one `observation_family` and matching
`runtime_observation_authorization`, passes its bounded raw callback through
Task 3's executor, returns only `runtime_observation_receipt`, and leaves both
ordinary initial-evidence fields and both step-receipt fields null. The
receipt's private successor binds every applicable attempt-record,
journal, controller/legacy temp, planned journal successor, candidate,
target-owner, INI, state, receipt, match, admission, package, run, and attempt
field. It never returns an incomplete projection and the caller never reopens
the store to reconstruct omitted facts. The unpaired public diagnostic may
return ordinary status/Evidence but always has a null observation receipt and
cannot feed a Session CAS. The paired observation uses the bounded raw transaction-
store observer, not `load_runtime_transaction_journals()`, and therefore never
promotes or deletes a UUID temp. With either physical authorization non-null,
the observation family, observation authorization/receipt, and both initial-
evidence fields are null, and exactly the matching step receipt may be non-null.
Every other combination fails before
mutation. One exact nonterminal authorization advances or confirms
at most the one `RuntimeApplyRecoveryAction` row bound by the session. Before
its first raw runtime observation, the helper passes the one callback through
`_execute_apply_recovery_physical_step()`; invalid authority invokes no
observer or mutator and a valid callback returns exactly one
`ApplyRecoveryStepReceipt`; it cannot perform terminal cleanup. One exact
terminal authorization similarly passes its callback through
`_execute_terminal_resolution_physical_step()`, advances or confirms at most one persisted
terminal-resolution row from the same physical adjacency table, and returns exactly one
`TerminalResolutionStepReceipt`; it cannot alter nonterminal recovery. The
controller consumes the corresponding receipt in its one session CAS before it
may mint a new authorization. That CAS increments the action index, promotes
only the receipt-bound successor to predecessor, clears all old successor
fields, and binds the table's sole next action. Both set, a cross-family token,
a phase skip, a stale successor, or a multi-phase recovery loop under one token
fails closed.

For a controller attempt in a pre-commit phase with a candidate or target tree,
ordinary observation and public recovery do not run the existing in-memory tree
cleanup. They return the exact retained evidence so the controller can first
bind a terminal result and the durable cleanup intent. Only
`delete_runtime_no_commit_entry_from_pair()` may delete that tree. It validates
the active paired token, the single-use authorization minted from the exact
persisted `RECOVERY_CLEANING` session cursor, the sealed inventory and cursor,
and every remaining identity before deleting at most the current entry. It
returns the observed successor plus the opaque step receipt; Task 10 consumes
that receipt in the session cursor CAS before
minting authority for another entry. Public/legacy recovery cannot call or
emulate this path. `retire_runtime_no_commit_metadata_from_pair()` consumes one
fresh action-bound token and retires at most the exact journal or exact fence;
it accepts absence only as the idempotent postcondition of that same persisted
stage. Journal and fence retirement occur only after full cursor, or on the
closed no-tree branch, in their separately faulted order while the same leases
remain active. The controller must consume its matching opaque receipt in the
retired-stage CAS before a new token can be minted. Plain Booleans, paths, and
reconstructed observations are never CAS authority.

### Step 9.6: Verify and commit

```powershell
python -B -m pytest `
  tests/test_atomic_io.py::test_atomic_publish_bytes_no_replace_never_exposes_partial_target `
  tests/test_atomic_io.py::test_atomic_publish_no_replace_default_hook_and_named_stage_are_compatible `
  tests/test_package_io.py::test_no_replace_commit_is_parent_identity_bound_on_windows_and_posix `
  tests/test_deck_config_ini.py::test_deck_config_ini_delegates_to_shared_no_replace_commit `
  tests/test_deck_config_ini.py::test_deck_config_ini_preserves_existing_fault_stage_delegation `
  tests/test_runtime_installer.py::test_apply_uses_full_runtime_subtree_digest_and_is_idempotent `
  tests/test_runtime_installer.py::test_caller_owned_transaction_id_is_reused_and_never_regenerated `
  tests/test_runtime_installer.py::test_existing_exact_transaction_requires_recovery_without_install `
  tests/test_runtime_installer.py::test_recover_runtime_attempt_inspects_only_the_exact_transaction `
  tests/test_runtime_installer.py::test_recovery_bootstraps_only_metadata_directory_and_empty_apply_lock `
  tests/test_runtime_installer.py::test_caller_owned_nonowning_finalized_journal_survives_installer_return `
  tests/test_runtime_installer.py::test_caller_owned_already_current_attempt_retains_noop_journal_until_ack `
  tests/test_runtime_installer.py::test_generic_recovery_never_adopts_or_deletes_controller_retained_journal `
  tests/test_runtime_installer.py::test_acknowledge_runtime_attempt_retires_only_exact_attempt_evidence `
  tests/test_runtime_transaction_journal.py::test_transaction_id_requires_exact_lowercase_hex `
  tests/test_runtime_transaction_journal.py::test_schema_v1_owner_bytes_remain_exact_and_field_absent `
  tests/test_runtime_transaction_journal.py::test_schema_v2_attempt_record_is_separate_from_schema_v1_target_owner `
  tests/test_runtime_installer.py::test_controller_attempt_record_blocks_broad_recovery_of_matching_v1_transaction `
  tests/test_runtime_installer.py::test_new_install_ack_preserves_owner_then_later_identical_install_is_already_current `
  tests/test_runtime_installer.py::test_new_install_ack_preserves_owner_then_later_install_cleans_stale_revision `
  tests/test_runtime_installer.py::test_already_current_ack_deletes_nonowner_attempt_but_preserves_existing_owner `
  tests/test_runtime_installer.py::test_fault_between_owner_finalization_and_attempt_record_finalization_recovers_exactly `
  tests/test_runtime_installer.py::test_fault_between_nonowner_delete_and_attempt_record_delete_is_idempotent `
  tests/test_current_output.py::test_package_input_lease_token_is_nonforgeable_thread_bound_and_expires `
  tests/test_runtime_installer.py::test_runtime_apply_lease_token_is_nonforgeable_thread_bound_and_expires `
  tests/test_runtime_installer.py::test_runtime_lease_consumer_rejects_forged_expired_or_wrong_root_token `
  tests/test_runtime_installer.py::test_controller_apply_pair_rejects_independently_acquired_or_mixed_leases `
  tests/test_runtime_installer.py::test_candidate_planned_fence_then_v1_journal_binds_identity_and_digest_before_finalization `
  tests/test_runtime_installer.py::test_controller_prior_owned_target_uses_no_staging_nonowner_path `
  tests/test_runtime_installer.py::test_prior_owner_planned_crash_before_v1_create_preserves_owner_and_proves_not_committed `
  tests/test_runtime_installer.py::test_prior_owner_planned_crash_after_v1_create_never_adopts_target_or_owner `
  tests/test_runtime_installer.py::test_prior_owner_planned_to_bound_is_exact_and_candidate_free `
  tests/test_runtime_installer.py::test_prior_owned_target_crash_before_ini_remains_prepared_no_tree `
  tests/test_runtime_installer.py::test_prior_owned_target_crash_after_ini_before_journal_recovers_as_commit `
  tests/test_runtime_installer.py::test_nonowning_fastpath_rejects_same_byte_target_or_owner_substitution `
  tests/test_runtime_installer.py::test_legacy_nonowner_path_remains_compatible `
  tests/test_runtime_installer.py::test_same_byte_fence_journal_or_owner_substitution_fails_closed `
  tests/test_runtime_installer.py::test_later_changed_install_preserves_committed_mismatch_fenced_evidence `
  tests/test_runtime_installer.py::test_owner_retirement_tombstone_has_exact_closed_canonical_schema `
  tests/test_runtime_installer.py::test_owner_retirement_rejects_unknown_fields_bounds_self_digest_or_substitution `
  tests/test_runtime_installer.py::test_owner_retirement_reserved_temp_hard_kills_reconcile_before_enumeration `
  tests/test_runtime_installer.py::test_owner_retirement_crash_matrix_resumes_each_cleanup_cursor_and_owner_delete `
  tests/test_runtime_installer.py::test_owner_cleanup_writes_completed_tombstone_before_deleting_old_owner `
  tests/test_runtime_installer.py::test_old_success_accepts_exact_owner_retirement_tombstone_after_later_cleanup `
  tests/test_runtime_installer.py::test_owner_retirement_prepared_and_completed_use_external_file_action `
  tests/test_runtime_installer.py::test_owner_retirement_uses_one_tombstone_entry_or_journal_action_per_receipt_cas `
  tests/test_runtime_installer.py::test_owner_retirement_old_owner_unlink_requires_completed_receipt_cas `
  tests/test_runtime_installer.py::test_owner_retirement_prepared_record_carries_complete_identity_inventory `
  tests/test_runtime_installer.py::test_owner_retirement_prepared_reconstructs_only_exact_precommitted_candidate `
  tests/test_runtime_installer.py::test_owner_retirement_prepared_reconstruction_rejects_same_byte_file_empty_directory_parent_or_root_replacement `
  tests/test_runtime_installer.py::test_owner_retirement_initializes_cleanup_started_at_cursor_zero_before_first_delete `
  tests/test_runtime_installer.py::test_owner_retirement_advance_journal_only_increments_after_bound_entry_absence `
  tests/test_runtime_installer.py::test_owner_retirement_zero_entry_tree_retires_root_before_completed `
  tests/test_runtime_installer.py::test_owner_retirement_root_rmdir_action_before_cas_confirms_only_authorized_absence `
  tests/test_runtime_installer.py::test_owner_retirement_final_v1_cursor_binds_completed_tombstone_commitment `
  tests/test_runtime_installer.py::test_owner_retirement_root_receipt_uses_only_prebound_completed_commitment `
  tests/test_runtime_installer.py::test_owner_retirement_root_crash_rejects_tombstone_list_or_final_v1_substitution `
  tests/test_runtime_installer.py::test_owner_retirement_terminal_observer_exports_exact_partial_owner_evidence `
  tests/test_runtime_transaction_journal.py::test_schema_v1_cleanup_initialization_is_monotone_only_at_finalized_cursor_zero `
  tests/test_runtime_live_admission.py::test_runtime_live_admission_has_closed_bounded_schema_fixed_path_and_absent_cas `
  tests/test_runtime_live_admission.py::test_two_process_claim_race_creates_exactly_one_admission_without_replacement `
  tests/test_runtime_live_admission.py::test_crash_after_admission_before_invocation_receipt_continues_same_attempt_once `
  tests/test_runtime_installer.py::test_different_attempt_is_rejected_by_admission_before_fence_journal_or_runtime_write `
  tests/test_runtime_installer.py::test_legacy_runtime_writer_rejects_active_controller_admission `
  tests/test_runtime_installer.py::test_legacy_runtime_writer_rejects_output_operation_before_runtime_admission_final `
  tests/test_runtime_installer.py::test_legacy_runtime_writer_rejects_output_operation_staging_or_reserved_temp `
  tests/test_runtime_installer.py::test_legacy_runtime_recovery_rejects_output_operation_before_temp_or_journal_reconciliation `
  tests/test_runtime_installer.py::test_legacy_runtime_lock_order_is_output_operation_then_runtime `
  tests/test_runtime_installer.py::test_public_runtime_writer_checks_output_operation_then_runtime_admission_before_first_write `
  tests/test_runtime_installer.py::test_controller_pair_entry_requires_exact_session_profile_output_operation_and_package_capabilities `
  tests/test_runtime_installer.py::test_controller_pair_entry_rejects_forged_stale_cross_thread_or_wrong_cursor_before_runtime_bootstrap `
  tests/test_runtime_installer.py::test_controller_pair_entry_creates_only_hsconfig_and_apply_lock_before_apply_intent `
  tests/test_runtime_installer.py::test_controller_pair_reentry_after_runtime_handoff_accepts_old_exact_absent_or_valid_foreign_output_record `
  tests/test_runtime_installer.py::test_controller_pair_reentry_requires_exact_release_authorized_session_and_runtime_admission `
  tests/test_runtime_installer.py::test_controller_pair_reentry_rejects_active_absence_same_byte_replacement_staging_or_foreign_runtime_admission `
  tests/test_runtime_installer.py::test_controller_pair_token_accepts_only_persisted_same_lease_cursor_descendants `
  tests/test_runtime_installer.py::test_public_installer_lock_order_is_output_operation_then_package_then_runtime `
  tests/test_runtime_installer.py::test_public_installer_never_acquires_output_operation_while_holding_package `
  tests/test_runtime_installer.py::test_already_gated_runtime_helper_never_reacquires_output_operation `
  tests/test_runtime_installer.py::test_blocked_public_installer_creates_no_runtime_root_hsconfig_or_apply_lock `
  tests/test_runtime_live_admission.py::test_legacy_root_bootstrap_gate_rejects_same_path_active_or_malformed_final_admission `
  tests/test_runtime_live_admission.py::test_same_attempt_recovery_revalidates_exact_admission `
  tests/test_runtime_live_admission.py::test_forged_replaced_wrong_run_or_wrong_attempt_admission_fails_closed `
  tests/test_runtime_installer.py::test_runtime_admission_requires_staging_bound_before_final `
  tests/test_runtime_installer.py::test_runtime_file_actions_use_planned_staging_bound_commit_matrix `
  tests/test_runtime_installer.py::test_invocation_receipt_uses_apply_start_capability_and_bound_staging `
  tests/test_runtime_live_admission.py::test_runtime_live_admission_has_no_installer_controller_or_published_apply_import `
  tests/test_runtime_installer.py::test_pair_observation_receipt_binds_exact_requested_initial_recovery_evidence `
  tests/test_runtime_installer.py::test_runtime_observation_receipt_rejects_wrong_pair_admission_attempt_family_or_runtime_change `
  tests/test_runtime_installer.py::test_runtime_observation_receipt_is_single_use_and_cross_thread_bound `
  tests/test_runtime_installer.py::test_failure_selection_receipt_rejects_constructed_literal_and_visible_ini_not_committed `
  tests/test_runtime_installer.py::test_runtime_attempt_recovery_family_nullability_rejects_mixed_fields `
  tests/test_runtime_live_admission.py::test_admission_atomic_no_replace_is_absent_or_complete_at_every_crash_boundary `
  tests/test_runtime_live_admission.py::test_admission_atomic_no_replace_never_overwrites_two_process_winner `
  tests/test_runtime_live_admission.py::test_admission_staging_inner_temp_hard_kills_reconcile_before_no_replace `
  tests/test_runtime_live_admission.py::test_staging_flush_crash_is_cleaned_without_promotion_or_runtime_write `
  tests/test_runtime_installer.py::test_attempt_retention_reserved_temp_hard_kills_reconcile_before_enumeration `
  tests/test_runtime_installer.py::test_terminal_no_commit_inventory_deletes_only_bound_candidate_and_target_entries `
  tests/test_runtime_installer.py::test_terminal_no_commit_inventory_rejects_same_bytes_empty_directory_or_parent_replacement `
  tests/test_runtime_installer.py::test_terminal_no_commit_metadata_tokens_are_action_bound_single_use_and_ordered `
  tests/test_runtime_installer.py::test_terminal_physical_helpers_return_receipt_and_reject_reused_authorization `
  tests/test_runtime_installer.py::test_commit_recovery_mutates_one_persisted_row_per_token_and_receipt `
  tests/test_runtime_installer.py::test_success_ack_threads_one_receipt_per_deleted_row `
  tests/test_runtime_installer.py::test_nonowning_ack_crash_after_journal_before_fence_resumes_from_ack_journal_retired `
  tests/test_runtime_installer.py::test_owning_ack_deletes_only_fence_before_evidence_retired `
  tests/test_runtime_installer.py::test_terminal_inventory_reconstructs_only_exact_precommitted_bytes_after_prepared_crash `
  tests/test_runtime_installer.py::test_terminal_inventory_prepared_rejects_same_byte_entry_or_parent_identity_substitution `
  tests/test_runtime_installer.py::test_nonterminal_recovery_authorization_advances_exactly_one_row_per_token `
  tests/test_runtime_installer.py::test_nonterminal_recovery_rejects_null_terminal_forged_reused_or_cross_attempt_authority `
  tests/test_runtime_installer.py::test_terminal_and_nonterminal_recovery_authorities_are_mutually_exclusive `
  tests/test_runtime_installer.py::test_runtime_apply_recovery_matrix_covers_external_file_action_and_every_legacy_row `
  tests/test_runtime_installer.py::test_null_authority_runtime_observer_never_promotes_or_deletes_uuid_temps `
  tests/test_runtime_installer.py::test_recovery_legacy_temp_actions_mutate_exactly_one_bound_temp_per_receipt `
  tests/test_runtime_installer.py::test_controller_journal_observer_reports_staging_only_in_external_file_action `
  tests/test_runtime_installer.py::test_controller_journal_observer_never_classifies_new_staging_as_transaction_temp `
  tests/test_runtime_installer.py::test_controller_journal_commit_requires_staging_bound_identity `
  tests/test_runtime_installer.py::test_controller_journal_posix_link_crash_accepts_only_same_bound_identity `
  tests/test_runtime_installer.py::test_terminal_and_nonterminal_legacy_temp_evidence_bind_origin_classification_path_parent_identity_size_and_digest `
  tests/test_runtime_installer.py::test_runtime_layout_bootstrap_fixed_order_and_existing_missing_rows `
  tests/test_runtime_installer.py::test_runtime_layout_bootstrap_crash_after_each_directory_create_resumes_without_authority_file `
  tests/test_runtime_installer.py::test_runtime_layout_bootstrap_rejects_parent_replacement_reparse_ads_and_nonempty_created_child `
  tests/test_runtime_installer.py::test_initial_active_and_route_fence_commits_are_distinct_staged_rows `
  tests/test_runtime_installer.py::test_new_target_candidate_tree_copy_verify_rename_and_v1_phases_are_one_row_each `
  tests/test_runtime_installer.py::test_candidate_leaf_action_before_cas_confirms_only_exact_safe_manifest_content `
  tests/test_runtime_installer.py::test_candidate_same_byte_safe_replacement_is_content_equivalent `
  tests/test_runtime_installer.py::test_candidate_leaf_rejects_wrong_bytes_source_parent_root_extra_hardlink_ads_or_reparse `
  tests/test_runtime_installer.py::test_candidate_manifest_is_reverified_before_rename_and_owner_binding `
  tests/test_runtime_installer.py::test_new_target_ini_runs_only_after_target_owner_binding `
  tests/test_runtime_installer.py::test_first_install_uninterrupted_and_resumed_action_trace_is_identical `
  tests/test_runtime_installer.py::test_candidate_planned_precedes_v1_and_candidate_create `
  tests/test_runtime_installer.py::test_created_candidate_is_bound_by_journal_then_fence_receipts `
  tests/test_runtime_installer.py::test_candidate_planned_create_or_confirm_matrix_handles_absent_and_exact_empty_rows `
  tests/test_runtime_installer.py::test_candidate_create_crash_before_identity_receipt_remints_without_adoption `
  tests/test_runtime_installer.py::test_candidate_create_or_confirm_rejects_nonempty_replaced_wrong_parent_and_unsafe_candidate `
  tests/test_runtime_installer.py::test_candidate_identity_receipt_cas_precedes_candidate_fence_commit `
  tests/test_runtime_installer.py::test_controller_first_install_has_no_monolithic_multiwrite_callback `
  tests/test_runtime_installer.py::test_success_ack_receipt_rejects_terminal_resolution_evidence_family `
  tests/test_runtime_installer.py::test_nonterminal_recovery_closes_pending_and_unknown_without_physical_mutation `
  tests/test_runtime_installer.py::test_failure_selection_matrix_is_exhaustive_for_new_target_and_prior_owner `
  tests/test_runtime_installer.py::test_prior_owner_bound_before_ini_can_select_not_committed `
  tests/test_runtime_installer.py::test_not_committed_selection_rejects_visible_intended_ini_successor `
  tests/test_runtime_installer.py::test_visible_idempotent_successor_resumes_current_action_instead_of_selecting `
  tests/test_runtime_installer.py::test_failure_selection_rejects_pair_admission_fence_journal_candidate_owner_or_snapshot_drift `
  tests/test_runtime_installer.py::test_pending_and_unknown_selection_preserve_exact_retained_evidence `
  tests/test_runtime_installer.py::test_candidate_planned_fence_with_prepared_journal_and_no_tree_resolves_not_committed_in_order `
  tests/test_runtime_installer.py::test_precommit_noop_keeps_separately_authenticated_owner `
  tests/test_runtime_installer.py::test_no_tree_resolution_rejects_unexpected_tree_or_missing_replaced_owner `
  tests/test_runtime_installer.py::test_active_fence_without_v1_journal_resolves_only_from_unchanged_snapshot `
  tests/test_runtime_installer.py::test_no_commit_same_attempt_projection_allows_only_bound_own_transaction_and_restores_full_digest `
  tests/test_live_start_session.py::test_prepared_admission_parent_substitution_fails_without_recapture `
  tests/test_output_publisher.py::test_controller_legacy_and_preview_publishers_reject_matching_admission_before_pointer_or_revision_write `
  tests/test_operator_profile.py::test_profile_enable_disable_and_rebind_reject_any_admission_before_cas `
  tests/test_operator_profile.py::test_deleted_profile_cannot_be_reenabled_on_unrelated_root_while_admission_exists `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/apply_invocation.py `
  src/hsconfig/runtime_live_admission.py `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/package_io.py `
  src/hsconfig/deck_config_ini.py `
  src/hsconfig/current_output.py `
  src/hsconfig/operator_profile.py `
  src/hsconfig/output_publisher.py `
  src/hsconfig/runtime_installer.py `
  src/hsconfig/runtime_transaction_journal.py `
  tests/test_apply_invocation.py `
  tests/test_runtime_live_admission.py `
  tests/test_live_start_session.py `
  tests/test_atomic_io.py `
  tests/test_package_io.py `
  tests/test_deck_config_ini.py `
  tests/test_current_output.py `
  tests/test_operator_profile.py `
  tests/test_output_publisher.py `
  tests/test_runtime_installer.py `
  tests/test_runtime_transaction_journal.py
git diff --check
git add -- `
  src/hsconfig/apply_invocation.py `
  src/hsconfig/runtime_live_admission.py `
  src/hsconfig/live_start_session.py `
  src/hsconfig/atomic_io.py `
  src/hsconfig/package_io.py `
  src/hsconfig/deck_config_ini.py `
  src/hsconfig/current_output.py `
  src/hsconfig/operator_profile.py `
  src/hsconfig/output_publisher.py `
  src/hsconfig/runtime_installer.py `
  src/hsconfig/runtime_transaction_journal.py `
  tests/test_apply_invocation.py `
  tests/test_runtime_live_admission.py `
  tests/test_live_start_session.py `
  tests/test_atomic_io.py `
  tests/test_package_io.py `
  tests/test_deck_config_ini.py `
  tests/test_current_output.py `
  tests/test_operator_profile.py `
  tests/test_output_publisher.py `
  tests/test_runtime_installer.py `
  tests/test_runtime_transaction_journal.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: bind recoverable runtime apply attempts"
```

---

## Task 10: Compose Published Apply and Runtime Match Under One Lease

**Owned files**

- Create: `src/hsconfig/published_apply.py`
- Create: `src/hsconfig/commands/recover_apply.py`
- Create: `tests/test_apply_and_match_published.py`
- Create: `tests/test_recover_apply_cli.py`
- Modify: `src/hsconfig/current_output.py`
- Modify: `src/hsconfig/runtime_apply.py`
- Modify: `src/hsconfig/runtime_installer.py`
- Modify: `src/hsconfig/runtime_package_match.py`
- Modify: `src/hsconfig/output_operation_admission.py`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `src/hsconfig/cli.py`
- Modify: `tests/test_current_output.py`
- Modify: `tests/test_runtime_apply.py`
- Modify: `tests/test_runtime_package_match.py`
- Modify: `tests/test_output_operation_admission.py`
- Modify: `tests/test_configure_publication.py`

### Step 10.1: Write RED lock-order and race tests

Add these exact tests:

- `test_composite_holds_one_publication_lease_through_apply_and_match`
- `test_composite_passes_invocation_attempt_id_to_runtime_journal`
- `test_pointer_change_before_composite_blocks_without_runtime_write`
- `test_pointer_cannot_switch_between_apply_and_final_match`
- `test_post_commit_runtime_mutation_is_applied_but_not_verified`
- `test_second_identical_composite_is_already_live_without_new_revision`
- `test_composite_never_recursively_acquires_publication_or_runtime_lock`
- `test_runtime_drift_before_locked_apply_blocks_without_install`
- `test_runtime_lock_prevents_mutation_between_apply_and_match`
- `test_crash_after_nonowning_installer_return_recovers_exact_retained_attempt`
- `test_competing_mutation_after_match_waits_until_terminal_session_cas`
- `test_held_context_acknowledges_only_bound_evidence_and_expires_on_exit`
- `test_recovery_context_yields_updated_session_cursor_without_reload`
- `test_normal_context_yields_updated_session_cursor_without_reload`
- `test_held_updated_session_is_exact_recovery_closed_cas_successor`
- `test_normal_and_recovery_holders_share_one_updated_session_authority`
- `test_composite_reassigns_every_physical_and_pure_transition_cursor`
- `test_composite_never_exposes_started_session_after_recovery_begins`
- `test_package_and_runtime_lease_tokens_reject_forged_stale_cross_thread_or_wrong_context`
- `test_composite_requires_active_profile_lease_until_terminal_ack`
- `test_recovery_validates_but_never_reacquires_profile_lease`
- `test_ack_requires_active_session_lease_and_exact_persisted_terminal_cursor`
- `test_ack_rejects_cross_thread_session_capability_without_retiring_evidence`
- `test_ack_rejects_constructed_stale_or_unpersisted_terminal_without_deleting_journal`
- `test_ack_threads_terminal_retirement_successors_without_lock_reacquire_or_result_rewrite`
- `test_published_package_lease_never_recreates_a_missing_publish_lock`
- `test_direct_package_lease_cannot_authorize_published_apply`
- `test_cross_context_package_runtime_pair_is_rejected`
- `test_held_context_expires_with_package_runtime_and_pair_tokens`
- `test_ack_revalidates_exact_current_and_match_before_retiring_attempt_evidence`
- `test_success_ack_evidence_binds_attempt_record_and_durable_target_owner`
- `test_held_acknowledgement_never_deletes_owning_finalized_journal`
- `test_held_terminal_release_requires_exact_persisted_session_and_admission`
- `test_success_ack_retires_attempt_evidence_then_releases_admission_last`
- `test_composite_success_ack_threads_one_receipt_per_deleted_row`
- `test_composite_nonowning_ack_crash_resumes_from_ack_journal_retired`
- `test_composite_owning_ack_deletes_only_fence_before_evidence_retired`
- `test_not_committed_releases_admission_only_after_terminal_cas`
- `test_committed_mismatch_releases_admission_but_retains_fence_and_owner`
- `test_pending_and_unknown_terminal_cannot_release_admission`
- `test_terminal_pending_recovery_releases_admission_without_rewriting_result`
- `test_terminal_pending_recovery_binds_historical_and_monotone_successor_evidence`
- `test_every_terminal_journal_phase_and_fence_transition_recovers_across_faults`
- `test_terminal_no_commit_cleanup_orders_target_journal_then_fence_and_rejects_ini_committed`
- `test_terminal_no_commit_cleanup_resumes_every_inventory_cursor_and_staged_inventory_crash`
- `test_terminal_no_commit_cleanup_cas_and_single_use_token_matrix_is_closed`
- `test_terminal_resolution_threads_step_receipt_after_each_physical_action`
- `test_commit_recovery_threads_one_receipt_and_session_cas_per_persisted_row`
- `test_terminal_candidate_planned_with_prepared_v1_and_no_tree_resolves_failed_preserved_in_order`
- `test_terminal_active_without_v1_journal_resolves_not_committed_without_adoption`
- `test_prior_owned_no_staging_crash_before_ini_is_failed_preserved`
- `test_prior_owned_no_staging_crash_after_ini_is_commit_recovery_not_cleanup`
- `test_terminal_no_commit_cleanup_rejects_same_bytes_or_parent_replacement`
- `test_terminal_inventory_prepared_crash_reconstructs_only_committed_candidate_bytes`
- `test_nonterminal_precommit_tree_terminalizes_failed_preserved_before_cleanup_and_remains_failed_preserved`
- `test_terminal_resolution_rejects_backward_cross_attempt_or_unbound_successor`
- `test_fault_after_terminal_before_admission_release_resumes_without_reapply`
- `test_composite_requires_active_session_lease_and_exact_publication_cursor`
- `test_composite_passes_exact_publication_committed_authority_into_pair_entry`
- `test_pair_entry_rejects_package_only_stale_cross_thread_or_replaced_output_operation_before_lock_io`
- `test_composite_reenters_fresh_pair_after_output_operation_unlink`
- `test_composite_post_handoff_pair_requires_exact_runtime_admission_and_current_session_cursor`
- `test_prepared_intent_precedes_admission_and_admission_precedes_receipt`
- `test_prepared_crash_before_admission_rolls_back_without_runtime_block`
- `test_admission_crash_before_receipt_blocks_competitor_and_continues_once`
- `test_prior_owner_planned_crashes_bind_before_journal_and_never_adopt`
- `test_low_level_retirement_rejects_preterminal_constructed_stale_or_expired_authority`
- `test_low_level_release_rejects_evidence_retired_cursor_before_unlink`
- `test_terminal_retirement_crashes_resume_recovery_evidence_and_release_authorized_stages`
- `test_terminal_release_authorization_precedes_unlink_and_needs_no_later_session_cas`
- `test_old_release_fast_path_never_touches_valid_foreign_successor_admission`
- `test_terminal_fast_path_unlinks_present_old_admission_without_old_leases`
- `test_terminal_fast_path_accepts_absent_old_admission_without_old_leases`
- `test_terminal_fast_path_preserves_valid_foreign_successor_without_old_leases`
- `test_terminal_fast_path_never_reacquires_profile_package_output_or_runtime_pair`
- `test_invalid_terminal_release_bearer_invokes_zero_admission_observers`
- `test_pending_result_binds_fence_journal_and_owner_identities_and_digests`
- `test_old_success_fast_path_accepts_completed_owner_retirement_tombstone`
- `test_composite_recovery_executes_exact_action_table_and_rollover`
- `test_composite_pending_and_unknown_close_recovery_before_terminal_result`
- `test_composite_rejects_128_preexisting_transactions_before_prepared_or_admission`
- `test_apply_pair_revalidates_output_child_binding_before_runtime_observation`
- `test_recovery_rejects_output_child_binding_mismatch_without_runtime_mutation`
- `test_apply_started_first_install_prepares_nonterminal_cursor_before_task9_mutation`
- `test_composite_runtime_layout_bootstrap_precedes_invocation_receipt_and_apply_started`
- `test_composite_fresh_runtime_root_binds_each_parent_before_first_authority_file`
- `test_composite_runs_prepared_package_install_through_one_row_recovery_loop`
- `test_composite_reassigns_returned_session_cursor_and_remints_after_every_cas`
- `test_uninterrupted_first_install_and_crash_resume_share_identical_action_sequence`
- `test_composite_new_target_full_action_trace_has_one_receipt_cas_per_row`
- `test_composite_new_target_ini_is_reached_after_rename_owner_binding`
- `test_composite_owner_retirement_runs_one_persisted_row_per_capability`
- `test_composite_owner_retirement_crash_resume_never_loops_or_deletes_successor`
- `test_composite_owner_retirement_initializes_cursor_zero_then_deletes_one_row_per_capability`
- `test_composite_owner_retirement_retires_root_before_completed_tombstone`
- `test_composite_owner_root_crash_uses_prebound_completed_tombstone_commitment`
- `test_terminal_pending_owner_retirement_resumes_through_terminal_resolution_evidence`
- `test_composite_controller_journal_uses_external_file_action_final_staging_and_inner_temp`
- `test_composite_unbound_controller_staging_retires_then_retries_one_receipt_cas_per_step`
- `test_composite_staging_bound_controller_journal_commits_one_receipt_cas`
- `test_composite_candidate_create_crash_binds_or_preserves_without_adoption`
- `test_composite_candidate_absent_row_continues_same_attempt_without_second_install`
- `test_composite_candidate_present_before_receipt_binds_identity_without_second_install`
- `test_composite_candidate_leaf_crash_accepts_only_exact_safe_content_authority`
- `test_composite_reverifies_candidate_manifest_before_target_owner_binding`
- `test_success_ack_rejects_terminal_resolution_evidence_family`
- `test_composite_threads_exact_observer_evidence_and_receipt_without_reconstruction`
- `test_apply_started_cas_authorizes_output_operation_release_only_after_runtime_admission`
- `test_runtime_handoff_release_authorizer_requires_active_pair_and_exact_admission`
- `test_output_operation_unlink_requires_current_exact_runtime_admission`
- `test_output_operation_release_crash_accepts_old_absent_or_valid_foreign_successor`
- `test_recovery_finishes_output_operation_handoff_before_runtime_observation_or_mutation`
- `test_no_profile_or_publisher_gap_exists_between_output_and_runtime_admissions`
- `test_pre_handoff_layout_and_admission_writes_require_action_scoped_same_attempt_bearers`
- `test_runtime_admission_staging_crash_keeps_output_operation_runtime_writer_fence_active`
- `test_direct_foreign_stale_or_replaced_output_operation_evidence_cannot_bypass_runtime_gate`
- `test_invocation_receipt_context_adapter_revalidates_outer_capabilities_after_bearer_consumption`
- `test_invocation_receipt_context_adapter_runs_one_action_and_one_receipt_cas_per_stage`
- `test_composite_revalidates_outer_capabilities_immediately_before_complete_apply_started`
- `test_session_only_or_cross_action_invocation_receipt_path_invokes_zero_mutators`
- `test_public_install_and_controller_pair_cannot_deadlock_on_package_runtime_locks`
- `test_public_apply_preserves_absent_runtime_root_contract_after_output_operation_gate`
- `test_public_installer_creates_absent_runtime_root_only_after_output_operation_and_package_gates`
- `test_public_installer_fresh_root_hard_kill_resumes_before_any_semantic_runtime_artifact`
- `test_active_output_or_runtime_admission_keeps_absent_runtime_root_absent`
- `test_fresh_runtime_root_parent_or_root_substitution_fails_before_hsconfig_or_runtime_lock`
- `test_controller_pair_still_rejects_absent_profile_bound_runtime_root`
- `test_direct_legacy_root_bootstrap_cannot_bypass_active_runtime_admission`
- `test_legacy_root_bootstrap_rechecks_runtime_admission_immediately_before_first_mkdir`
- `test_legacy_root_bootstrap_authorization_rejects_output_operation_staging_temp_or_malformed_surfaces_before_mkdir`
- `test_legacy_root_bootstrap_authorization_rejects_forged_stale_reused_cross_thread_wrong_root_or_unvalidated_gate`
- `test_controller_and_recovery_never_use_legacy_runtime_root_creation`
- `test_runtime_apply_creates_no_runtime_surface_before_output_operation_gate`
- `test_failed_action_selects_terminal_classification_only_after_fresh_pair_observation`
- `test_composite_terminal_classification_reobserves_under_same_pair_before_receipt`
- `test_composite_initial_observation_receipts_reject_constructed_swapped_or_stale_evidence`
- `test_failure_selection_performs_no_runtime_io`
- `test_crash_after_failure_selection_resumes_only_selected_observation`
- `test_visible_ini_successor_uses_commit_recovery_not_failed_preserved`
- `test_failure_selection_rejects_stale_cross_family_or_reused_bearer`
- `test_callback_exception_alone_does_not_change_session_classification`
- `test_composite_recovery_closed_active_to_closed_then_result_consumes`

The lock instrumentation must assert the order:

```python
assert lock_events == [
    "session_lease_verified",
    "operator_profile_lease_verified",
    "output_operation_lease_verified",
    "output_operation_admission_verified",
    "output_operation_runtime_fence_active",
    "publication_lease_enter",
    "package_lease_verified",
    "controller_pair_outer_capabilities_revalidated",
    "controller_pair_narrow_lock_bootstrap",
    "runtime_apply_lock_enter",
    "controller_apply_lease_pair_minted",
    "pre_apply_snapshot_captured",
    "invocation_admission_intent_prepared",
    "runtime_admission_claim_or_revalidate",
    "runtime_admission_final_bound",
    "runtime_layout_intent_prepared",
    "runtime_layout_directory_receipt_cas_loop",
    "runtime_layout_complete",
    "invocation_receipt_materialize_receipt_cas",
    "invocation_receipt_commit_receipt_cas",
    "invocation_receipt_outer_context_revalidated",
    "apply_started_session_cas",
    "output_operation_release_authorized",
    "output_operation_admission_unlinked_or_absent",
    "runtime_first_install_authorized",
    "runtime_install_or_recovery",
    "apply_committed_session_cas",
    "runtime_match",
    "runtime_matched_session_cas",
    "recovery_closed_session_cas",
    "current_pointer_recheck",
    "composite_result_yield",
    "terminal_session_cas",
    "terminal_session_pre_retirement_revalidate",
    "terminal_retirement_prepared",
    "terminal_retirement_authority_minted",
    "status_closed_attempt_evidence_retired",
    "admission_release_authorized_cas",
    "release_authorization_minted",
    "old_runtime_admission_absent",
    "terminal_session_post_retirement_revalidate",
    "lease_tokens_still_active",
    "runtime_apply_lock_exit",
    "publication_lease_exit",
    "output_operation_lease_exit",
]
```

The trace also instruments a competing unpaired Runtime wrapper. It must acquire
the same output-operation lease before the Runtime lock and remain blocked at
the three-path gate through admission staging, layout bootstrap, invocation
receipt, and `APPLY_STARTED`. The controller crosses that gate only inside the
fresh action-scoped admission/layout callbacks. The final Runtime admission is
exact before output-operation release becomes callable. The returned value of
every Whole-Session CAS is assigned directly as the next `expected_session`;
no public Session reader reloads or replaces that cursor between edges.

Run:

```powershell
python -B -m pytest `
  tests/test_apply_and_match_published.py::test_composite_holds_one_publication_lease_through_apply_and_match `
  tests/test_apply_and_match_published.py::test_composite_passes_invocation_attempt_id_to_runtime_journal `
  tests/test_apply_and_match_published.py::test_pointer_change_before_composite_blocks_without_runtime_write `
  tests/test_apply_and_match_published.py::test_pointer_cannot_switch_between_apply_and_final_match `
  tests/test_apply_and_match_published.py::test_post_commit_runtime_mutation_is_applied_but_not_verified `
  tests/test_apply_and_match_published.py::test_second_identical_composite_is_already_live_without_new_revision `
  tests/test_apply_and_match_published.py::test_composite_never_recursively_acquires_publication_or_runtime_lock `
  tests/test_apply_and_match_published.py::test_runtime_drift_before_locked_apply_blocks_without_install `
  tests/test_apply_and_match_published.py::test_runtime_lock_prevents_mutation_between_apply_and_match `
  tests/test_apply_and_match_published.py::test_crash_after_nonowning_installer_return_recovers_exact_retained_attempt `
  tests/test_apply_and_match_published.py::test_competing_mutation_after_match_waits_until_terminal_session_cas `
  tests/test_apply_and_match_published.py::test_held_context_acknowledges_only_bound_evidence_and_expires_on_exit `
  tests/test_apply_and_match_published.py::test_recovery_context_yields_updated_session_cursor_without_reload `
  tests/test_apply_and_match_published.py::test_normal_context_yields_updated_session_cursor_without_reload `
  tests/test_apply_and_match_published.py::test_held_updated_session_is_exact_recovery_closed_cas_successor `
  tests/test_apply_and_match_published.py::test_normal_and_recovery_holders_share_one_updated_session_authority `
  tests/test_apply_and_match_published.py::test_composite_reassigns_every_physical_and_pure_transition_cursor `
  tests/test_apply_and_match_published.py::test_composite_never_exposes_started_session_after_recovery_begins `
  tests/test_apply_and_match_published.py::test_package_and_runtime_lease_tokens_reject_forged_stale_cross_thread_or_wrong_context `
  tests/test_apply_and_match_published.py::test_composite_requires_active_profile_lease_until_terminal_ack `
  tests/test_apply_and_match_published.py::test_recovery_validates_but_never_reacquires_profile_lease `
  tests/test_apply_and_match_published.py::test_ack_requires_active_session_lease_and_exact_persisted_terminal_cursor `
  tests/test_apply_and_match_published.py::test_ack_rejects_cross_thread_session_capability_without_retiring_evidence `
  tests/test_apply_and_match_published.py::test_ack_rejects_constructed_stale_or_unpersisted_terminal_without_deleting_journal `
  tests/test_apply_and_match_published.py::test_ack_threads_terminal_retirement_successors_without_lock_reacquire_or_result_rewrite `
  tests/test_current_output.py::test_published_package_lease_never_recreates_a_missing_publish_lock `
  tests/test_current_output.py::test_direct_package_lease_cannot_authorize_published_apply `
  tests/test_apply_and_match_published.py::test_cross_context_package_runtime_pair_is_rejected `
  tests/test_apply_and_match_published.py::test_held_context_expires_with_package_runtime_and_pair_tokens `
  tests/test_apply_and_match_published.py::test_ack_revalidates_exact_current_and_match_before_retiring_attempt_evidence `
  tests/test_apply_and_match_published.py::test_success_ack_evidence_binds_attempt_record_and_durable_target_owner `
  tests/test_apply_and_match_published.py::test_held_acknowledgement_never_deletes_owning_finalized_journal `
  tests/test_apply_and_match_published.py::test_held_terminal_release_requires_exact_persisted_session_and_admission `
  tests/test_apply_and_match_published.py::test_success_ack_retires_attempt_evidence_then_releases_admission_last `
  tests/test_apply_and_match_published.py::test_composite_success_ack_threads_one_receipt_per_deleted_row `
  tests/test_apply_and_match_published.py::test_composite_nonowning_ack_crash_resumes_from_ack_journal_retired `
  tests/test_apply_and_match_published.py::test_composite_owning_ack_deletes_only_fence_before_evidence_retired `
  tests/test_apply_and_match_published.py::test_not_committed_releases_admission_only_after_terminal_cas `
  tests/test_apply_and_match_published.py::test_committed_mismatch_releases_admission_but_retains_fence_and_owner `
  tests/test_apply_and_match_published.py::test_pending_and_unknown_terminal_cannot_release_admission `
  tests/test_apply_and_match_published.py::test_terminal_pending_recovery_releases_admission_without_rewriting_result `
  tests/test_apply_and_match_published.py::test_terminal_pending_recovery_binds_historical_and_monotone_successor_evidence `
  tests/test_apply_and_match_published.py::test_every_terminal_journal_phase_and_fence_transition_recovers_across_faults `
  tests/test_apply_and_match_published.py::test_terminal_no_commit_cleanup_orders_target_journal_then_fence_and_rejects_ini_committed `
  tests/test_apply_and_match_published.py::test_terminal_no_commit_cleanup_resumes_every_inventory_cursor_and_staged_inventory_crash `
  tests/test_apply_and_match_published.py::test_terminal_no_commit_cleanup_cas_and_single_use_token_matrix_is_closed `
  tests/test_apply_and_match_published.py::test_terminal_resolution_threads_step_receipt_after_each_physical_action `
  tests/test_apply_and_match_published.py::test_commit_recovery_threads_one_receipt_and_session_cas_per_persisted_row `
  tests/test_apply_and_match_published.py::test_terminal_candidate_planned_with_prepared_v1_and_no_tree_resolves_failed_preserved_in_order `
  tests/test_apply_and_match_published.py::test_terminal_active_without_v1_journal_resolves_not_committed_without_adoption `
  tests/test_apply_and_match_published.py::test_prior_owned_no_staging_crash_before_ini_is_failed_preserved `
  tests/test_apply_and_match_published.py::test_prior_owned_no_staging_crash_after_ini_is_commit_recovery_not_cleanup `
  tests/test_apply_and_match_published.py::test_terminal_no_commit_cleanup_rejects_same_bytes_or_parent_replacement `
  tests/test_apply_and_match_published.py::test_terminal_inventory_prepared_crash_reconstructs_only_committed_candidate_bytes `
  tests/test_apply_and_match_published.py::test_nonterminal_precommit_tree_terminalizes_failed_preserved_before_cleanup_and_remains_failed_preserved `
  tests/test_apply_and_match_published.py::test_terminal_resolution_rejects_backward_cross_attempt_or_unbound_successor `
  tests/test_apply_and_match_published.py::test_fault_after_terminal_before_admission_release_resumes_without_reapply `
  tests/test_apply_and_match_published.py::test_composite_requires_active_session_lease_and_exact_publication_cursor `
  tests/test_apply_and_match_published.py::test_composite_passes_exact_publication_committed_authority_into_pair_entry `
  tests/test_apply_and_match_published.py::test_pair_entry_rejects_package_only_stale_cross_thread_or_replaced_output_operation_before_lock_io `
  tests/test_apply_and_match_published.py::test_composite_reenters_fresh_pair_after_output_operation_unlink `
  tests/test_apply_and_match_published.py::test_composite_post_handoff_pair_requires_exact_runtime_admission_and_current_session_cursor `
  tests/test_apply_and_match_published.py::test_prepared_intent_precedes_admission_and_admission_precedes_receipt `
  tests/test_apply_and_match_published.py::test_prepared_crash_before_admission_rolls_back_without_runtime_block `
  tests/test_apply_and_match_published.py::test_admission_crash_before_receipt_blocks_competitor_and_continues_once `
  tests/test_apply_and_match_published.py::test_prior_owner_planned_crashes_bind_before_journal_and_never_adopt `
  tests/test_apply_and_match_published.py::test_low_level_retirement_rejects_preterminal_constructed_stale_or_expired_authority `
  tests/test_apply_and_match_published.py::test_low_level_release_rejects_evidence_retired_cursor_before_unlink `
  tests/test_apply_and_match_published.py::test_terminal_retirement_crashes_resume_recovery_evidence_and_release_authorized_stages `
  tests/test_apply_and_match_published.py::test_terminal_release_authorization_precedes_unlink_and_needs_no_later_session_cas `
  tests/test_apply_and_match_published.py::test_old_release_fast_path_never_touches_valid_foreign_successor_admission `
  tests/test_apply_and_match_published.py::test_terminal_fast_path_unlinks_present_old_admission_without_old_leases `
  tests/test_apply_and_match_published.py::test_terminal_fast_path_accepts_absent_old_admission_without_old_leases `
  tests/test_apply_and_match_published.py::test_terminal_fast_path_preserves_valid_foreign_successor_without_old_leases `
  tests/test_apply_and_match_published.py::test_terminal_fast_path_never_reacquires_profile_package_output_or_runtime_pair `
  tests/test_apply_and_match_published.py::test_invalid_terminal_release_bearer_invokes_zero_admission_observers `
  tests/test_apply_and_match_published.py::test_pending_result_binds_fence_journal_and_owner_identities_and_digests `
  tests/test_apply_and_match_published.py::test_old_success_fast_path_accepts_completed_owner_retirement_tombstone `
  tests/test_apply_and_match_published.py::test_composite_recovery_executes_exact_action_table_and_rollover `
  tests/test_apply_and_match_published.py::test_composite_pending_and_unknown_close_recovery_before_terminal_result `
  tests/test_apply_and_match_published.py::test_composite_rejects_128_preexisting_transactions_before_prepared_or_admission `
  tests/test_apply_and_match_published.py::test_apply_pair_revalidates_output_child_binding_before_runtime_observation `
  tests/test_apply_and_match_published.py::test_recovery_rejects_output_child_binding_mismatch_without_runtime_mutation `
  tests/test_apply_and_match_published.py::test_apply_started_first_install_prepares_nonterminal_cursor_before_task9_mutation `
  tests/test_apply_and_match_published.py::test_composite_runtime_layout_bootstrap_precedes_invocation_receipt_and_apply_started `
  tests/test_apply_and_match_published.py::test_composite_fresh_runtime_root_binds_each_parent_before_first_authority_file `
  tests/test_apply_and_match_published.py::test_composite_runs_prepared_package_install_through_one_row_recovery_loop `
  tests/test_apply_and_match_published.py::test_composite_reassigns_returned_session_cursor_and_remints_after_every_cas `
  tests/test_apply_and_match_published.py::test_uninterrupted_first_install_and_crash_resume_share_identical_action_sequence `
  tests/test_apply_and_match_published.py::test_composite_new_target_full_action_trace_has_one_receipt_cas_per_row `
  tests/test_apply_and_match_published.py::test_composite_new_target_ini_is_reached_after_rename_owner_binding `
  tests/test_apply_and_match_published.py::test_composite_owner_retirement_runs_one_persisted_row_per_capability `
  tests/test_apply_and_match_published.py::test_composite_owner_retirement_crash_resume_never_loops_or_deletes_successor `
  tests/test_apply_and_match_published.py::test_composite_owner_retirement_initializes_cursor_zero_then_deletes_one_row_per_capability `
  tests/test_apply_and_match_published.py::test_composite_owner_retirement_retires_root_before_completed_tombstone `
  tests/test_apply_and_match_published.py::test_composite_owner_root_crash_uses_prebound_completed_tombstone_commitment `
  tests/test_apply_and_match_published.py::test_terminal_pending_owner_retirement_resumes_through_terminal_resolution_evidence `
  tests/test_apply_and_match_published.py::test_composite_controller_journal_uses_external_file_action_final_staging_and_inner_temp `
  tests/test_apply_and_match_published.py::test_composite_unbound_controller_staging_retires_then_retries_one_receipt_cas_per_step `
  tests/test_apply_and_match_published.py::test_composite_staging_bound_controller_journal_commits_one_receipt_cas `
  tests/test_apply_and_match_published.py::test_composite_candidate_create_crash_binds_or_preserves_without_adoption `
  tests/test_apply_and_match_published.py::test_composite_candidate_absent_row_continues_same_attempt_without_second_install `
  tests/test_apply_and_match_published.py::test_composite_candidate_present_before_receipt_binds_identity_without_second_install `
  tests/test_apply_and_match_published.py::test_composite_candidate_leaf_crash_accepts_only_exact_safe_content_authority `
  tests/test_apply_and_match_published.py::test_composite_reverifies_candidate_manifest_before_target_owner_binding `
  tests/test_apply_and_match_published.py::test_success_ack_rejects_terminal_resolution_evidence_family `
  tests/test_apply_and_match_published.py::test_composite_threads_exact_observer_evidence_and_receipt_without_reconstruction `
  tests/test_apply_and_match_published.py::test_apply_started_cas_authorizes_output_operation_release_only_after_runtime_admission `
  tests/test_apply_and_match_published.py::test_runtime_handoff_release_authorizer_requires_active_pair_and_exact_admission `
  tests/test_apply_and_match_published.py::test_output_operation_unlink_requires_current_exact_runtime_admission `
  tests/test_apply_and_match_published.py::test_output_operation_release_crash_accepts_old_absent_or_valid_foreign_successor `
  tests/test_apply_and_match_published.py::test_recovery_finishes_output_operation_handoff_before_runtime_observation_or_mutation `
  tests/test_apply_and_match_published.py::test_no_profile_or_publisher_gap_exists_between_output_and_runtime_admissions `
  tests/test_apply_and_match_published.py::test_pre_handoff_layout_and_admission_writes_require_action_scoped_same_attempt_bearers `
  tests/test_apply_and_match_published.py::test_runtime_admission_staging_crash_keeps_output_operation_runtime_writer_fence_active `
  tests/test_apply_and_match_published.py::test_direct_foreign_stale_or_replaced_output_operation_evidence_cannot_bypass_runtime_gate `
  tests/test_apply_and_match_published.py::test_invocation_receipt_context_adapter_revalidates_outer_capabilities_after_bearer_consumption `
  tests/test_apply_and_match_published.py::test_invocation_receipt_context_adapter_runs_one_action_and_one_receipt_cas_per_stage `
  tests/test_apply_and_match_published.py::test_composite_revalidates_outer_capabilities_immediately_before_complete_apply_started `
  tests/test_apply_and_match_published.py::test_session_only_or_cross_action_invocation_receipt_path_invokes_zero_mutators `
  tests/test_apply_and_match_published.py::test_public_install_and_controller_pair_cannot_deadlock_on_package_runtime_locks `
  tests/test_runtime_apply.py::test_public_apply_preserves_absent_runtime_root_contract_after_output_operation_gate `
  tests/test_runtime_apply.py::test_public_installer_creates_absent_runtime_root_only_after_output_operation_and_package_gates `
  tests/test_runtime_apply.py::test_public_installer_fresh_root_hard_kill_resumes_before_any_semantic_runtime_artifact `
  tests/test_runtime_apply.py::test_active_output_or_runtime_admission_keeps_absent_runtime_root_absent `
  tests/test_runtime_apply.py::test_fresh_runtime_root_parent_or_root_substitution_fails_before_hsconfig_or_runtime_lock `
  tests/test_apply_and_match_published.py::test_controller_pair_still_rejects_absent_profile_bound_runtime_root `
  tests/test_runtime_apply.py::test_direct_legacy_root_bootstrap_cannot_bypass_active_runtime_admission `
  tests/test_runtime_apply.py::test_legacy_root_bootstrap_rechecks_runtime_admission_immediately_before_first_mkdir `
  tests/test_runtime_apply.py::test_legacy_root_bootstrap_authorization_rejects_output_operation_staging_temp_or_malformed_surfaces_before_mkdir `
  tests/test_runtime_apply.py::test_legacy_root_bootstrap_authorization_rejects_forged_stale_reused_cross_thread_wrong_root_or_unvalidated_gate `
  tests/test_apply_and_match_published.py::test_controller_and_recovery_never_use_legacy_runtime_root_creation `
  tests/test_runtime_apply.py::test_runtime_apply_creates_no_runtime_surface_before_output_operation_gate `
  tests/test_apply_and_match_published.py::test_failed_action_selects_terminal_classification_only_after_fresh_pair_observation `
  tests/test_apply_and_match_published.py::test_composite_terminal_classification_reobserves_under_same_pair_before_receipt `
  tests/test_apply_and_match_published.py::test_composite_initial_observation_receipts_reject_constructed_swapped_or_stale_evidence `
  tests/test_apply_and_match_published.py::test_failure_selection_performs_no_runtime_io `
  tests/test_apply_and_match_published.py::test_crash_after_failure_selection_resumes_only_selected_observation `
  tests/test_apply_and_match_published.py::test_visible_ini_successor_uses_commit_recovery_not_failed_preserved `
  tests/test_apply_and_match_published.py::test_failure_selection_rejects_stale_cross_family_or_reused_bearer `
  tests/test_apply_and_match_published.py::test_callback_exception_alone_does_not_change_session_classification `
  tests/test_apply_and_match_published.py::test_composite_recovery_closed_active_to_closed_then_result_consumes `
  -q -p no:cacheprovider
```

Expected RED: `apply_and_match_published()` does not exist and current
configure explicitly releases its lease before apply.

### Step 10.2: Add lease-aware validation and apply primitives

Use Task 9's actual expiring `PackageInputLease` capability and add:

```python
def revalidate_package_input_lease(lease: PackageInputLease) -> None:
    """Under the already-held publish lock, require current still names this lease."""
```

For published input, `lease_package_input()` acquires the existing
`.publish.lock` with `create_if_missing=False`, exact parent identity, and path
guard; only the publisher bootstraps that lock. It mints the token after lock,
root, current pointer, revision, package snapshot, and manifest verification,
binds it to the context/thread by private object identity, and invalidates it in
`finally` before unlock. Direct-package compatibility also gets an expiring
token, but every live writer additionally requires non-null publication,
output-root, content-root, and snapshot fields.

`revalidate_package_input_lease()` rejects forged, expired, cross-thread,
cross-context, wrong-root, wrong-lock, and direct-package capabilities. It then
calls `resolve_current_publication_unlocked()` and compares output root,
revision, content root, package path, verified manifest, and snapshot while the
lock remains held. It never reacquires or recreates `.publish.lock`.

Add the context authorizer to `published_apply.py` and the lease-aware entry to
`runtime_apply.py`:

```python
@dataclass(frozen=True, slots=True)
class LegacyRuntimeRootBootstrapAuthorization: ...

@dataclass(frozen=True, slots=True)
class LegacyRuntimeRootBootstrapEvidence:
    runtime_root: Path
    predecessor_state: Literal["absent", "existing"]
    predecessor_identity: PathIdentity | None
    successor_identity: PathIdentity
    bound_ancestor_path: Path
    bound_ancestor_identity: PathIdentity
    created_directory_identities: tuple[PathIdentity, ...]

def _authorize_legacy_runtime_root_bootstrap_from_context(
    *,
    output_operation_lease: OutputOperationAdmissionLease,
    package_lease: PackageInputLease,
    runtime_root: Path,
    expected_predecessor_identity: PathIdentity | None,
    bound_ancestor_path: Path,
    bound_ancestor_identity: PathIdentity,
    config_dir: str,
    apply_gate: dict[str, Any],
    fake_apply_receipt: dict[str, Any],
) -> LegacyRuntimeRootBootstrapAuthorization: ...

def _bootstrap_legacy_runtime_root_from_context(
    *,
    authorization: LegacyRuntimeRootBootstrapAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LegacyRuntimeRootBootstrapEvidence: ...

def _observe_runtime_recovery_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observation_family: RuntimeObservationFamily,
    initial_install_plan: RuntimeInstallPlan | None = None,
) -> RuntimeObservationReceipt: ...

def _authorize_output_operation_runtime_handoff_release_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_apply_started_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> OutputOperationAdmissionReleaseAuthorization: ...

@dataclass(frozen=True, slots=True)
class PreparedPackageInstall:
    plan: RuntimeInstallPlan
    runtime_layout_evidence: RuntimeLayoutBootstrapEvidence
    apply_gate: dict[str, Any]

def prepare_package_install_from_lease(
    *,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_gate: dict[str, Any] | None = None,
) -> PreparedPackageInstall: ...
```

The Legacy-root authorization is a private `runtime_apply.py` bearer family.
Its mint recomputes and compares the exact apply gate/fake receipt against the
held Package snapshot, validates both active same-thread leases, performs the
neutral fixed Runtime-admission check, and binds the canonical root,
predecessor, ancestor, lease identities, context nonce, and thread. Only the
private bootstrap consumes it. Consumption validates the registry facts and
reruns the fixed admission check as the last operation before any path
observation or `mkdir`; invalid use invokes zero filesystem callbacks. The
bearer is spent before the first callback and cannot be copied, reused, or
reminted by controller/recovery code. Public exports contain neither helper nor
bearer.

Reuse strict validation, apply-gate recomputation, logical config resolution,
fake-receipt construction/verification, `plan_runtime_install()`, and
`observe_runtime_layout_bootstrap_from_pair()`. The function receives the full
invocation and exact already-claimed held admission, revalidates the shared pair
without reloading or claiming admission internally, uses the unchanged attempt
ID, verifies the expected pre-apply snapshot, and returns the plan plus complete
layout-bootstrap evidence. It performs no runtime mutation and never enters
either publication/package or runtime locks itself.

The context authorizer first validates the active same-thread
session/profile/output-operation/pair capabilities, exact persisted pre-receipt
cursor, invocation/admission/output binding, the still-exact `ACTIVE`
output-operation record, unchanged snapshot, and absence of all same-attempt
physical evidence. It then
persists and completes the layout rows. Only after the layout is complete may
the invocation receipt commit and `APPLY_STARTED` CAS occur.
`_observe_runtime_recovery_from_context()` then validates the later exact
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED` cursor, physical old-record absence or
permitted foreign successor, and all active capabilities before minting the
private `first_install` bearer. It delegates internally to
`observe_initial_runtime_install_from_pair()`, which derives
the complete all-same-attempt-surfaces-absent initial recovery evidence from the
bound directory identities inside the Task-3 executor; the context adapter
returns only its receipt. `prepare_first_runtime_install_under_lock()` consumes that receipt and
installs only its private successor. The bearer cannot be reminted after that
cursor or any same-attempt physical evidence exists. The controller drives every
later physical action through the ordinary paired recovery helper and
receipt-CAS loop.

Every controller apply, recovery, match, current-revalidation, and
acknowledgement entry validates the active package/runtime tokens plus their
shared pair token before reading authority or mutating. A direct-package lease,
expired token, cross-thread call, or independently acquired package/runtime pair fails
before runtime write.

Add `build_runtime_package_match_report_from_pair()` that consumes the
already verified controller pair without acquiring either lock. Add
`recover_runtime_attempt_from_pair()` for the same reason. Preserve the
existing public installer, recovery, and runtime-match commands as wrappers
that acquire their own locks when no composite lease already exists.

Task 10 rewrites the public `runtime_apply.py` mutation boundary rather than
wrapping its current Package-first sequence. Any read-only planning lease closes
before mutation. The writer then performs the neutral output-lock bootstrap,
enters and validates `OutputOperationAdmissionLease`, acquires
`PackageInputLease`, and preserves the existing public absent-root contract only
through Task 10's private authorized Legacy bootstrap. An existing root is revalidated
directly; an absent root is created or confirmed only after the operation,
Package/apply, and fixed Runtime-admission gates, then its returned exact identity
is passed to `_lease_runtime_apply_under_output_operation()`. It creates no
runtime root before those gates and no `.hsconfig`/`apply.lock` before the
operation gate, never reacquires the operation lease under Package, and holds
operation, Package, and Runtime leases through the last mutation. Package-free
recovery omits only the Package lease and remains existing-root-only. The
profile-bound controller Pair is also existing-root-only. The focused Runtime-
apply tests instrument ancestor/root `mkdir`, fixed-gate observation, lock entry,
and Package entry and fail on any `package -> output-operation`, `runtime ->
package`, pre-gate filesystem write, raced root identity, or semantic Runtime
artifact before the Runtime lock.

### Step 10.3: Implement the physical disposition classifier

Map raw installer states exactly:

```python
RAW_DISPOSITIONS = {
    "applied": PhysicalApplyDisposition.COMMITTED,
    "already_current": PhysicalApplyDisposition.COMMITTED,
    "recovered": PhysicalApplyDisposition.COMMITTED,
    "committed_receipt_pending": (
        PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING
    ),
}
```

An exception is not automatically `NOT_COMMITTED`. Classify it only after
targeted recovery inspects the exact attempt. Use `NOT_COMMITTED` only when
targeted recovery positively proves that no runtime commit occurred. Missing,
incomplete, contradictory, or merely absent commit evidence is always
`UNKNOWN_REQUIRES_RECOVERY`; a physically committed but unmatched attempt is
`APPLIED_BUT_NOT_VERIFIED`.

### Step 10.4: Implement `apply_and_match_published()` as a held-lease context

The public context delegates to a private
`_apply_and_match_published(..., fault_hook)` implementation with
`no_live_start_fault`. Only the private controller test harness may pass the
closed hook through; normal callers cannot select fault behavior.

The function must:

1. require caller-held `session_lease` plus explicit `expected_session` at
   `PUBLICATION_COMMITTED`, caller-held `profile_lease`, and the same active
   `output_operation_lease` retained from Task 8; revalidate all opaque active
   originating-thread tokens, exact session/profile bytes, roots, active fixed
   operation admission, publication binding, and preview=false without
   reacquiring any outer lock;
2. acquire `lease_package_input(output_root)` once with no lock creation,
   validate its active published-package token, current digest, exact revision,
   and content root against the session publication binding;
3. revalidate session, profile, fixed output-operation lease/final record, and
   package immediately before entering `lease_controller_apply_pair()` once.
   Pass those exact four predecessor capabilities, the exact
   `PUBLICATION_COMMITTED` cursor, historical operation Evidence,
   `runtime_admission=None`, profile-bound runtime root/identity, and no
   constructed substitutes. The pair entry validates the pre-handoff row before
   any `.hsconfig`, `apply.lock`, or Runtime-lock I/O and retains one shared token
   bound to every bearer and the session lineage;
4. validate the pair and recapture the complete runtime snapshot under
   that lock before any physical admission, receipt, fence, journal, or runtime
   write;
5. seal one `ApplyInvocation` with caller-supplied `apply_attempt_id`, the exact
   session/profile/publication facts, and that snapshot; seal the planned fixed
   admission with its invocation digest and output/publication bindings;
6. call `prepare_apply_attempt_under_lock()` so the session durably binds those
   two planned documents, the attempt-owned staging path, and exactly
   `profile_lease.profile_parent_identity` while all six capabilities remain
   active; no helper recaptures that parent;
7. from the exact PREPARED cursor mint one runtime-admission materialize bearer
   and call `_claim_runtime_live_attempt_from_pair()` with the pair, active
   session/profile/output-operation capabilities, and that bearer. Consume its
   receipt in `staging_bound`; from that exact returned cursor mint a separate
   bound-commit bearer, call the same physical adapter once, and consume its
   receipt in `admission_primary_applied`. These two callbacks are the only
   pre-final exception to the generic output-operation Runtime gate and each
   revalidates the active Session/Profile/operation/pair context after its
   bearer is consumed. Loaded Evidence cannot bypass the gate. While the exact
   final admission fences the runtime, call
   `prepare_package_install_from_lease()` read-only, persist its
   exact runtime-layout binding, and advance each of the seven ordered directory
   rows through one create-or-confirm callback, receipt, and session CAS. Only
   after the layout cursor is `COMPLETE` may Task 10 mint the first invocation-
   receipt action bearer. Run materialize, any unbound-staging retirement, and
   bound commit only through `_execute_invocation_receipt_step_from_context()`,
   consume exactly one opaque receipt/CAS per action, and assign every returned
   cursor directly. After the committed-receipt cursor, revalidate the active
   Session/Profile/output-operation/pair and both final records, then call
   `_complete_apply_started_from_context()` for the sole I/O-free final CAS to
   `APPLY_STARTED`; assign that returned cursor to the single local `cursor`.
   That same CAS binds the runtime admission as the exact handoff successor and
   changes the output-operation binding to
   `RUNTIME_HANDOFF_RELEASE_AUTHORIZED`. Every layout and receipt callback uses
   its own bearer and revalidates both fixed final records. A waiting unpaired
   Runtime writer remains blocked by the operation lease throughout;
8. while runtime admission remains exact, mint a fresh output-operation release
   bearer through the runtime-handoff context adapter from `cursor`,
   the active profile/operation/pair capabilities, and the exact runtime
   admission; securely unlink or confirm exact absence of
   only the old fixed record, and fire the two release hooks. Recovery performs
   this handoff before any attempt-record, journal, candidate, target, or runtime
   metadata observation/mutation when a crash left the record present; the
   already bound layout directories are the only earlier runtime-root changes.
   An identity-distinct valid foreign successor is left
   byte-identical. At every boundary at least one of the two fixed admissions
   is exact;
9. only after output-operation release confirmation call
   `_observe_runtime_recovery_from_context(...,
   observation_family="first_install")` with the current cursor, all active
   capabilities, already prepared plan binding, exact admission, unchanged
   invocation/attempt ID, and completed layout. Consume only its opaque receipt in
   `prepare_first_runtime_install_under_lock()` so the returned session cursor
   durably binds the first recovery action before any runtime authority-file
   write and reassign it to `cursor`. Drive the install through the same one-row
   authorization -> paired callback -> receipt -> session-CAS loop used by
   resume, reassigning `cursor` after every physical receipt CAS. When the deterministic
   target is already exact and separately owned, that loop must take Task 9's
   `PRIOR_OWNER_BOUND` no-staging fastpath; it may not create then delete a
   candidate tree;
10. if a callback fails or the exact postcondition is not immediately usable,
    reread only the same persisted cursor under the held Session lease and call
    the diagnostic `classify_runtime_failure_from_pair()`. `resume_current_action`
    remints only that action. For `select_terminal_observation`, mint a fresh
    `terminal_classification` context observation, which internally runs
    `observe_runtime_failure_selection_from_pair()` under the same pair. Consume
    only its receipt in the I/O-free `select_terminal_classification`
    CAS; reassign
    `cursor`, and executes only the now-persisted `observe_*` on the next loop.
    No exception alone selects status, and a visible intended final INI
    successor always resumes commit recovery rather than no-commit;
11. if physically committed, verify receipt/state/INI parity and build runtime
    match from the same active pair. Reassign `cursor` after the authorized
    `apply_committed` CAS and, only for exact match, after `runtime_matched`;
12. for every stable disposition consume a fresh pure-CAS bearer for
    `recovery_closed`, reassign `cursor`, and require its closed recovery evidence
    still exact for result-intent consumption;
13. revalidate package, admission, session, profile, and the release-authorized
    output-operation binding while the runtime lease
    is still held;
14. yield one nonserializable `HeldApplyAndMatchPublished` while all capabilities
    remain active. It exposes immutable `updated_session=cursor`, invocation, result,
    exact non-null admission evidence, and optional acknowledgement evidence,
    but no raw lease;
15. require the caller to continue from `held.updated_session`, atomically bind
    result intent while consuming the exact closed recovery object, bind optional
    acknowledgement and the result pair, set terminal status, then call the
    status-appropriate acknowledgement or admission-release method inside the
    context. The caller never repeats `APPLY_COMMITTED` or `RUNTIME_MATCHED`;
16. after the caller returns, require every token still active, then invalidate
    and release runtime and package leases; the outer controller releases the
    output-operation, profile, and session leases last.

The context manager never yields a success candidate after either lease has
been released. The normal controller's terminal CAS is therefore inside both
physical authority leases. If the caller faults before terminalization, context
cleanup releases locks but the exact retention fence and journal remain for
recovery. A deterministic competing writer started immediately after match
must block until terminal CAS and acknowledgement complete; it cannot make a
stale `LIVE_AND_MATCHED` result durable.

`HeldApplyAndMatchPublished` is minted only after the session, profile, package,
paired runtime, and exact singleton admission capabilities are active. No post-claim
or post-receipt carrier has nullable admission evidence. Both
`acknowledge_after_terminal()`, `release_admission_after_terminal()`, and the
status-closed `resolve_and_release_after_terminal()` require the caller's
already-held originating-thread session lease and exact session returned by
terminal CAS. Without reacquiring, they bounded-reread
`session.json` and require active token, run root, file identity, canonical
bytes, self-digest, terminal status, result intent, and exact equality with
`expected_terminal_session`. They also require exact admission path, parent
identity, file identity, and digest equality with result intent and revalidate the private
profile/package/runtime capabilities plus the disposition-specific current and
runtime facts. Constructed, stale, unpersisted, wrong-run, cross-thread, or
inactive-token cursors fail before runtime evidence changes.

`updated_session` is exactly the return value of the last successful Whole-
Session CAS inside the composite: the post-`recovery_closed` cursor for the same
run, attempt, and active Session lease. The composite reassigns one local cursor
after every physical receipt CAS, failure-selection CAS, phase CAS, and recovery-
closure CAS; it never reloads a replacement predecessor. There is no public
`started_session` alias. Result, acknowledgement, and admission evidence are all
validated against this one cursor. `HeldRecoveredApplyAndMatch.updated_session`
delegates to `held.updated_session`, so normal and resumed paths cannot expose
two competing session authorities.

The methods are mutually status-closed and callable at most once per held
context. The resolved method is available only for a terminal result whose exact
historical evidence requires `release_resolved_terminal`; it owns the complete
inventory/cursor/metadata sequence below under the already-held leases and
returns every new persisted cursor internally. Each method first calls
`prepare_terminal_retirement_under_lock()`, assigns the
returned `PREPARED` cursor, and mints one stage-bound
`TerminalRetirementAuthorization` from an exact reread. Success acknowledgement
and stable non-success release pass `runtime_observation_receipt=null`.
`release_resolved_terminal` first mints the exact `terminal_resolution`
observation bearer, executes the same-pair callback, and passes only that
receipt; a caller-supplied `TerminalResolutionEvidence` is never accepted.
Success acknowledgement
calls private `_retire_success_attempt_evidence_step_from_pair()` once for the
owning fence or twice for the non-owning journal and fence, preserves every
owning schema-1 journal, and consumes each returned receipt in the exact
`ACK_JOURNAL_RETIRED|EVIDENCE_RETIRED` CAS before minting another token. It then
mints a separate stage-bound token and CASes
`ADMISSION_RELEASE_AUTHORIZED` while the exact old admission remains present.
A third token then unlinks only that old identity and verifies it absent; there
is no later session CAS.
Stable non-success release preserves every fence/journal, uses the same staged
retirement protocol, and deletes only admission. Each method returns the newly
sealed persisted session cursor. It never rewrites result intent, result files,
terminal status, or acknowledgement and is invalid after context exit.

If a crash occurs after release authorization, resume accepts exactly three
physical rows: the old admission remains and only it may be unlinked; the path
is absent and release is complete; or a fully validated identity-distinct
foreign admission occupies the path and is left byte-identical because the old
no-replace occupant must already have been removed. Current package/runtime/
profile parity was required immediately before the authorization CAS; later
valid operations are not retroactively required by the old read-only fast path.
Same old identity with different bytes, malformed successor bytes, or any
partially retired state is tamper.

| Terminal result / physical disposition | Runtime admission action |
| --- | --- |
| `LIVE_AND_MATCHED` or `ALREADY_LIVE` | Successful acknowledgement retires only permitted temporary attempt evidence, preserves the owning v1 journal, and releases admission last. |
| Post-attempt `FAILED_PRESERVED`, proven `NOT_COMMITTED` | Evidence-free path releases admission. Historical-evidence path completes resolved cleanup, then releases admission; no acknowledgement or result rewrite. |
| `APPLIED_BUT_NOT_VERIFIED` with positively proven `COMMITTED` mismatch | Retain schema-2 fence and schema-1 journal byte-identically; release only admission after terminal CAS. |
| `COMMITTED_RECOVERY_PENDING` | Retain admission, fence, and journal; release is unavailable. |
| `UNKNOWN_REQUIRES_RECOVERY` | Retain admission and every exact attempt artifact; release is unavailable. |
| Preview or failure before admission | No admission method is available. |

For a terminal pending/unknown result, targeted `recover-apply` accepts only the
same terminal session, admission, invocation, and attempt. It performs physical
recovery only and never rewrites or reclassifies result intent, result files, or
terminal status. Admission remains blocking until recovery proves stable
`NOT_COMMITTED` or `COMMITTED`. Before its first permitted journal/fence change,
the held recovery capability CASes
`release_resolved_terminal/RECOVERY_PREPARED` with exact predecessor evidence;
after the declared monotone metadata transition it CASes
`RECOVERY_STABILIZED` with exact successor proof. Result intent, result files,
acknowledgement, and terminal status remain byte-identical while the outer
session cursor advances through `EVIDENCE_RETIRED` and
`ADMISSION_RELEASE_AUTHORIZED`; only then may the old admission be unlinked. A
crash at any boundary resumes only that resolution/release and never reapplies.

Status mapping is exact:

- committed + matched + raw `already_current` -> `ALREADY_LIVE`;
- committed + matched otherwise -> `LIVE_AND_MATCHED`;
- proven not committed -> `FAILED_PRESERVED`;
- committed/pending/unknown without exact match ->
  `APPLIED_BUT_NOT_VERIFIED`.

Never return success for `committed_receipt_pending` until recovery completes
receipt/state parity and exact runtime match.

### Step 10.5: Implement exact-attempt recovery as a closed controller path

`recover_apply_attempt(session_root=...)` is a complete public wrapper, not a
thin alias to the broad runtime recovery command. It acquires one existing
session lease, reconstructs the expected profile from sealed bindings, acquires
one profile lease, then acquires the existing fixed output-operation lease
before any publication/package or runtime lock. It delegates to
`recover_apply_attempt_under_lock()` with all three capabilities and the
explicit current session cursor.
`resume_live_start()` already owns the session lease, so it acquires only the
profile and output-operation leases and never calls the public wrapper. The
under-lock context yields
`HeldRecoveredApplyAndMatch`, whose `updated_session` is the exact cursor after
its recovery phase CAS operations and whose `held` member provides the same
active acknowledgement capability as live apply. The wrapper and
`resume_live_start()` use that returned cursor for nested result intent,
result-pair, terminal CAS, optional acknowledgement/release, and final recheck
only while the session is nonterminal; neither reloads the session or reacquires
a lock. For an already terminal pending/unknown result, recovery preserves the
historical result intent, files, acknowledgement, and terminal status. Once the
physical disposition is stable it may advance only the outer
`terminal_retirement` cursor and release admission through that durable intent;
it does not rerun result binding or terminal CAS.

For a nonterminal receipt-bearing `APPLY_STARTED|APPLY_COMMITTED` cursor, the
context mints one `nonterminal_apply` observation bearer and calls the paired
observer inside Task 3's executor. It requires exactly one non-null opaque
observation receipt, keeps both ordinary initial-evidence fields null, and
passes only that receipt to `prepare_nonterminal_apply_recovery_under_lock()`;
the CAS installs only its registry-private successor. It performs no controller
reconstruction or second transaction-store observation. It then loops
only as `exact session cursor -> all held capabilities -> one
RuntimeApplyRecoveryAuthorization for the exact table action -> at most one
physical successor -> one ApplyRecoveryStepReceipt -> one rollover session
CAS`. Each rollover promotes only the immediate successor to predecessor,
increments the index, clears old successor fields, and binds the sole next
action. If a callback fails or cannot safely prove its postcondition, the same
held pair performs `classify_runtime_failure_from_pair()`. An exact idempotent
successor remints the current action; otherwise a fresh
`terminal_classification` observation bearer and same-pair callback produce one
receipt. That receipt alone performs one I/O-free
`select_terminal_classification` CAS and only the selected persisted
`observe_*` action may run next. After stable proof or stable pending/unknown classification, fresh pure-CAS
tokens perform the legal `apply_committed`, optional `runtime_matched`, and
`recovery_closed` edges. Closure retains the exact evidence; only the next
result-intent CAS consumes it. Only then may result files and terminalization occur.
A crash at any physical action-before-CAS boundary remints only against the
persisted old cursor and exact allowed idempotent successor; it never reruns
install or freezes an unclassified provisional UNKNOWN result. A classified
pending/unknown cursor closes recovery first and thereafter can progress only
through terminal resolution without rewriting its historical result.

The under-lock recovery path:

1. validates the closed session, its phase, every completed artifact binding,
   pending transition, invocation/admission bindings, and any invocation
   canonical bytes/self-digest;
2. validates the caller-held profile capability and revalidates its exact
   digest, runtime/output paths, root identities, deck-output binding,
   publication revision, and standard content digest without reacquiring;
3. acquires one publication/package lease and requires the exact historical
   revision still current; compares the raw lease digest to the session
   publication binding using the explicit prefix adapter;
4. revalidates the fixed output-operation lease and historical binding, then
   enters Task 9's exact pre-/post-handoff Pair matrix and acquires one runtime
   lease. `PREPARED` permits only absent admission surfaces or exact rollback-
   only unbound staging/temp while the old output record is exact.
   `STAGING_BOUND` permits only its bound staging, same-identity final, or
   declared POSIX two-link intermediate, again with the old record exact.
   `PRIMARY_APPLIED`, any invocation receipt, and `APPLY_STARTED` require the
   fixed exact same-attempt final Runtime admission. After
   `RUNTIME_HANDOFF_RELEASE_AUTHORIZED`, a fresh Pair is mintable from the exact
   persisted session and Runtime admission even when the historical output
   record is already absent or a valid identity-distinct foreign successor is
   present. A foreign, malformed, replaced, or stage-incompatible Runtime
   admission, or a pre-handoff missing/replaced old record, blocks this recovery
   context. If `APPLY_STARTED` already authorized the handoff, recovery finishes
   only the output-operation release before any attempt-record, journal,
   candidate, target, or runtime-metadata observation or mutation;
5. resumes the invocation transition only through its persisted stage. From
   `PREPARED`, it securely retires any unbound staging/temp through receipt/CAS
   and then either restores the byte-identical `PUBLICATION_COMMITTED`
   predecessor or rematerializes. From `STAGING_BOUND`, it completes only the
   bound admission commit and its `PRIMARY_APPLIED` receipt CAS. From
   `PRIMARY_APPLIED`, it first derives or revalidates the persisted seven-row
   runtime-layout binding and completes exactly one missing directory row per
   authorization/receipt/CAS. Only from a `COMPLETE` runtime-layout binding may
   it advance the nested invocation-receipt action through
   `PLANNED -> STAGING_BOUND -> committed`, then perform the separate
   `APPLY_STARTED` CAS. Only after that exact returned cursor may it release or
   confirm absence of the old output-operation record under the still-held
   runtime admission, mint the `first_install` observation bearer, run the
   complete all-same-attempt-surfaces-absent read-only callback, and consume only
   its receipt in the one Session CAS that binds the initial recovery cursor. It
   then advances the
   same per-file action loop as normal execution; no monolithic installer call
   is repeated or skipped;
6. for any existing receipt or `APPLY_STARTED`, require exact session admission
   binding and invocation digest and never invoke install. While nonterminal,
   prepare the exact `apply_recovery` cursor, mint only the nonterminal
   capability, advance one physical row, consume its receipt in one cursor CAS,
   and repeat until stable. On a failed physical callback, classify the exact
   persisted predecessor under the same pair; either remint that action or
   perform one pure selection CAS and then only the selected `observe_*`. A
   receipt or phase
   with absent, malformed, foreign, or replaced admission raises the typed
   nonterminal tamper stop and cannot yield `HeldRecoveredApplyAndMatch`;
7. if same-attempt admission exists but retention record and journal are both
   absent after a receipt/phase, positively prove `NOT_COMMITTED` only when the
   raw complete current runtime snapshot equals the sealed pre-apply snapshot;
8. if the exact retention record exists, checks its attempt/owner journal,
   previous mapping/INI/state/receipt, target, and package bindings against the
   sealed snapshot. For an already terminal pending/unknown session, before any
   call that may advance those files it mints one `terminal_resolution`
   observation bearer and runs the paired observer inside Task 3's executor. It
   passes only the resulting opaque receipt into the
   `release_resolved_terminal/RECOVERY_PREPARED` CAS, which installs only its
   registry-private Evidence. Both ordinary initial-evidence fields remain null.
   It performs no second observation or reconstruction, then calls only
   `recover_runtime_attempt_from_pair()` with one stage-bound terminal
   authorization for that transaction. That call advances at most one persisted physical row and
   returns one opaque step receipt; the controller passes no reconstructed
   successor and consumes that receipt in the matching
   `physical_recovery_advanced` session CAS, whose private registry installs the
   exact issuer-bound successor, before minting the next token. A
   journal without its required fence is contradictory;
   a nonterminal pre-commit row with an attempt-owned tree is classified before
   deletion: only an exact precommit v1 phase plus the shared exact same-attempt
   snapshot projection and exact attempt-owned tree authority positively proves
   `NOT_COMMITTED`. Bind terminal `FAILED_PRESERVED`, `runtime_match_status=not_run`,
   and `PREVIOUS_RUNTIME_UNCHANGED` with the exact historical evidence, then
   enter the same post-terminal inventory protocol under the still-active
   leases. The status and result files remain byte-identical through cleanup.
   Incomplete or contradictory evidence remains pending/unknown and is not
   cleaned. The path may not call legacy in-memory cleanup before the terminal
   cleanup intent exists;
   the exact `CANDIDATE_PLANNED` fence plus v1 `PREPARED` journal with absent
   candidate/target/staging and an exact same-attempt projection is the ordinary closed
   no-tree `NOT_COMMITTED` branch only after its pure
   `select_terminal_classification -> observe_not_committed` edge.
   `PRIOR_OWNER_PLANNED` with exact target/owner
   and absent planned journal is the fence-only prior-owner branch; with the
   exact planned v1 bytes present it is the journal-then-fence branch and may
   first advance to `PRIOR_OWNER_BOUND` only when continuing the same
   nonterminal attempt. The exact `PRIOR_OWNER_BOUND` fence plus v1 `PREPARED`,
   absent candidate/staging, an exact same-attempt projection, and byte-identical separate
   target/owner is the bound no-staging prior-owner variant, but only while the
   intended final INI successor is absent. All no-commit rows first persist the
   selection and observation, then terminalize `FAILED_PRESERVED` before mutation
   and use no sidecar. The
   journal-absent planned row skips directly to exact fence retirement; every
   journal-present row retires the exact attempt journal, consumes its step
   receipt in the CAS `RECOVERY_JOURNAL_RETIRED`, then retires the exact fence
   and CASes `RECOVERY_FENCE_RETIRED`, then stabilizes. Any separately bound prior owner
   remains exact throughout. If the intended INI successor is already durable
   under `PRIOR_OWNER_BOUND`, it is never this no-commit branch: targeted
   recovery uses the prebound target/owner and one-receipt-per-row protocol to
   advance the v1 journal and prove commit without candidate cleanup;
9. after terminal targeted recovery becomes stable, bounded-rereads every
   successor and CASes `RECOVERY_STABILIZED` with its exact triplets plus
   disposition/receipt/state/INI/package/match proof before evidence retirement;
10. treats any absent, extra, wrong-ID, partial, or contradictory evidence as
   `UNKNOWN_REQUIRES_RECOVERY`, never as proof of no commit;
11. for a proven commit, requires package digest plus receipt/state/INI parity,
    builds runtime match under the same leases, and revalidates current;
12. returns the updated explicit session cursor in the held recovery carrier
    after each CAS and records `APPLY_COMMITTED`, then `RUNTIME_MATCHED` only
    after the corresponding facts are proven.

For a nonterminal session with an exact held admission, the terminal decision
table is exact. Admission absence/malformation/foreign identity never enters it:

| Physical evidence | Session/result |
| --- | --- |
| Positive proof of no commit and exact pre-apply snapshot | Keep phase evidence, set `FAILED_PRESERVED`; never apply or require journal acknowledgement |
| Proven commit plus parity plus exact match/current | CAS through `APPLY_COMMITTED` to `RUNTIME_MATCHED`; success |
| Proven commit without final parity/match | Record `APPLY_COMMITTED` when proven; `APPLIED_BUT_NOT_VERIFIED` |
| Pending, incomplete, missing, extra, or contradictory evidence | Preserve phase/evidence; `APPLIED_BUT_NOT_VERIFIED` with `UNKNOWN_REQUIRES_RECOVERY` |

Before entering this recovery context, `resume_live_start()` normalizes the one
safe pre-claim row: `PUBLICATION_COMMITTED` plus exact
`install_apply_invocation/PREPARED`, absent admission, and absent receipt first
retires only exact unbound staging/temp when present through executor, receipt,
and cleanup CAS, proves both absent, clears the intent to its byte-identical predecessor, and returns to
ordinary finalization.
It is not represented as `HeldRecoveredApplyAndMatch`. The public
`recover_apply_attempt()` returns the closed `RecoverApplyNotStarted` union
variant and `recover-apply` serializes exactly `status=apply_not_started`, run ID,
session root/identity, persisted-session digest, and
`runtime_write_performed=false` without profile, publication, or runtime
mutation for that row. It does not
overload `NOT_COMMITTED` or invent a held recovery capability.

Recovery never creates a profile, session, singleton admission, transaction ID,
publication, or independent apply plan. The one pre-receipt continuation above
may finish its already-bound receipt and bind the initial recovery cursor; every
physical install step is then an authorized row of that same recovery protocol.
No row may prepare a second initial cursor or create a second retention record,
journal, staging tree, or target. Add
focused tests:

- `test_recovery_rebinds_session_receipt_profile_publication_snapshot_and_exact_transaction`;
- `test_prepared_without_admission_rolls_back_before_apply`;
- `test_prepared_staged_only_recovery_cleans_and_returns_apply_not_started`;
- `test_public_recovery_returns_closed_apply_not_started_union_variant`;
- `test_admission_before_receipt_prepares_one_bound_recovery_cursor`;
- `test_recovery_no_journal_requires_exact_snapshot_to_prove_not_committed`;
- `test_recovery_missing_incomplete_or_conflicting_evidence_is_unknown`;
- `test_recovery_commit_requires_receipt_state_ini_match_and_current_parity`;
- `test_nonterminal_recovery_reaches_recovered_match_without_terminal_result_freeze`;
- `test_nonterminal_recovery_threads_one_step_receipt_per_physical_row`;
- `test_nonterminal_recovery_rejects_cross_family_authority`;
- `test_recovery_cas_records_apply_committed_then_runtime_matched`;
- `test_recovery_never_creates_or_starts_a_second_apply`;
- `test_recovery_resume_under_one_session_lease_never_reacquires`;
- `test_receipt_or_apply_started_without_admission_is_nonterminal_tamper_and_never_applies`.

Run:

```powershell
python -B -m pytest `
  tests/test_apply_and_match_published.py::test_recovery_rebinds_session_receipt_profile_publication_snapshot_and_exact_transaction `
  tests/test_apply_and_match_published.py::test_prepared_without_admission_rolls_back_before_apply `
  tests/test_apply_and_match_published.py::test_prepared_staged_only_recovery_cleans_and_returns_apply_not_started `
  tests/test_apply_and_match_published.py::test_public_recovery_returns_closed_apply_not_started_union_variant `
  tests/test_apply_and_match_published.py::test_admission_before_receipt_prepares_one_bound_recovery_cursor `
  tests/test_apply_and_match_published.py::test_recovery_no_journal_requires_exact_snapshot_to_prove_not_committed `
  tests/test_apply_and_match_published.py::test_recovery_missing_incomplete_or_conflicting_evidence_is_unknown `
  tests/test_apply_and_match_published.py::test_recovery_commit_requires_receipt_state_ini_match_and_current_parity `
  tests/test_apply_and_match_published.py::test_nonterminal_recovery_reaches_recovered_match_without_terminal_result_freeze `
  tests/test_apply_and_match_published.py::test_nonterminal_recovery_threads_one_step_receipt_per_physical_row `
  tests/test_apply_and_match_published.py::test_nonterminal_recovery_rejects_cross_family_authority `
  tests/test_apply_and_match_published.py::test_recovery_cas_records_apply_committed_then_runtime_matched `
  tests/test_apply_and_match_published.py::test_recovery_never_creates_or_starts_a_second_apply `
  tests/test_apply_and_match_published.py::test_recovery_resume_under_one_session_lease_never_reacquires `
  tests/test_apply_and_match_published.py::test_receipt_or_apply_started_without_admission_is_nonterminal_tamper_and_never_applies `
  -q -p no:cacheprovider
```

### Step 10.6: Add recovery-only CLI dispatch after the composite exists

Append the parser after existing pinned options:

```text
hsconfig recover-apply --session SESSION_ROOT --json
```

The command loads the session and any sealed pending invocation/admission,
rebinds operator profile plus runtime/output identities, requires the exact
publication revision and content root, and calls only
`recover_apply_attempt()` from `published_apply.py`. It must not call public
`apply_package()` or `install_runtime_package()`. Only the exact
admission-before-receipt row may complete its already-bound receipt and prepare
the one initial nonterminal cursor; every file action then remains strictly
same-attempt recovery-only. The only permitted missing-layout bootstrap is the identity-
guarded `.hsconfig` directory plus persistent empty `apply.lock` defined in
Task 9.

Add and run:

```powershell
python -B -m pytest `
  tests/test_recover_apply_cli.py::test_recover_apply_uses_only_exact_recorded_attempt `
  tests/test_recover_apply_cli.py::test_recover_apply_reports_exact_apply_not_started_shape `
  tests/test_recover_apply_cli.py::test_recover_apply_bootstraps_only_persistent_lock_and_never_creates_attempt_artifacts `
  tests/test_recover_apply_cli.py::test_recover_apply_rejects_receipt_profile_publication_or_runtime_drift `
  -q -p no:cacheprovider
```

Expected RED: argparse rejects the command and no composite-level recovery
dispatcher exists. GREEN requires the Task 9 exact-attempt classifier and the
Task 10 publication/profile rebinding; the CLI therefore cannot be committed
in Task 9 without a forward dependency.

### Step 10.7: Preserve the legacy lease-release contract

Keep
`test_configure_apply_releases_publication_lease_before_consumer` unchanged.
It remains the required deadlock guard for expert legacy `configure --apply`.
Task 10 proves the new held-lease context only in
`test_apply_and_match_published.py`; Task 11 adds the controller integration
test after the controller actually owns that call path. The two routes retain
separate explicit contracts.

### Step 10.8: Verify and commit

```powershell
python -B -m pytest `
  tests/test_current_output.py::test_package_input_lease_blocks_publisher_for_entire_consumer_lifetime `
  tests/test_runtime_apply.py::test_published_apply_preserves_installer_status_and_honest_fields `
  tests/test_runtime_apply.py::test_public_apply_preserves_absent_runtime_root_contract_after_output_operation_gate `
  tests/test_runtime_apply.py::test_direct_legacy_root_bootstrap_cannot_bypass_active_runtime_admission `
  tests/test_runtime_apply.py::test_legacy_root_bootstrap_rechecks_runtime_admission_immediately_before_first_mkdir `
  tests/test_apply_and_match_published.py::test_composite_reenters_fresh_pair_after_output_operation_unlink `
  tests/test_runtime_package_match.py::test_runtime_package_match_auto_resolution_binds_runtime_tree_digest `
  tests/test_configure_publication.py::test_configure_apply_rejects_competing_current_digest `
  tests/test_configure_publication.py::test_configure_apply_releases_publication_lease_before_consumer `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/published_apply.py `
  src/hsconfig/commands/recover_apply.py `
  src/hsconfig/current_output.py `
  src/hsconfig/runtime_apply.py `
  src/hsconfig/runtime_installer.py `
  src/hsconfig/runtime_package_match.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/cli_parser.py `
  src/hsconfig/cli.py `
  tests/test_apply_and_match_published.py `
  tests/test_recover_apply_cli.py `
  tests/test_current_output.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_package_match.py `
  tests/test_configure_publication.py `
  tests/test_output_operation_admission.py
git diff --check
git add -- `
  src/hsconfig/published_apply.py `
  src/hsconfig/commands/recover_apply.py `
  src/hsconfig/current_output.py `
  src/hsconfig/runtime_apply.py `
  src/hsconfig/runtime_installer.py `
  src/hsconfig/runtime_package_match.py `
  src/hsconfig/output_operation_admission.py `
  src/hsconfig/cli_parser.py `
  src/hsconfig/cli.py `
  tests/test_apply_and_match_published.py `
  tests/test_recover_apply_cli.py `
  tests/test_current_output.py `
  tests/test_runtime_apply.py `
  tests/test_runtime_package_match.py `
  tests/test_configure_publication.py `
  tests/test_output_operation_admission.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: compose published apply and runtime match"
```

---

## Task 11: Finish the Codex-First Controller and Installed Skill Workflow

**Owned files**

- Modify: `src/hsconfig/live_start_controller.py`
- Modify: `src/hsconfig/resources/codex_skill_bundle.json`
- Create: `tests/test_live_start_controller.py`
- Modify: `tests/test_optimized_skill_workflow.py`
- Modify: `tests/test_external_skill_bundle.py`
- Modify: `tests/test_contract_preflight.py`
- Modify: `tests/test_distribution_contract.py`

### Step 11.1: Write RED normal-flow tests

Add these exact tests:

- `test_prepare_requires_only_deck_name_and_code_after_profile_enablement`
- `test_missing_or_drifted_profile_stops_before_llm_output_or_runtime_write`
- `test_prepare_freezes_inputs_once_and_resume_performs_no_second_fetch`
- `test_candidate_and_review_share_exact_two_revision_budget`
- `test_finalize_preview_publishes_without_any_runtime_artifact`
- `test_finalize_live_uses_one_composite_and_returns_runtime_match_status`
- `test_finalize_live_adopts_held_updated_session_without_duplicate_phase_cas`
- `test_controller_result_intent_cas_consumes_exact_held_recovery_closed_cursor`
- `test_resume_and_normal_controller_use_identical_held_cursor_contract`
- `test_resume_after_apply_started_calls_recovery_only`
- `test_prepare_always_creates_a_new_run_and_only_resume_reuses_one`
- `test_review_and_package_receipts_gate_each_completed_phase`
- `test_failure_results_have_one_cause_retained_state_and_no_raw_log`
- `test_finalize_holds_one_session_lease_from_invocation_through_terminal_cas`
- `test_result_pair_crash_windows_resume_to_one_terminal_binding`
- `test_result_pair_closed_layout_allows_only_one_sequential_delete_only_temp`
- `test_result_pair_exact_or_partial_temp_is_deleted_never_promoted`
- `test_result_pair_accepts_only_missing_or_byte_exact_final`
- `test_result_pair_rejects_both_temps_markdown_before_json_and_unsafe_occupants`
- `test_result_pair_requires_both_temps_absent_before_terminal_cas`
- `test_terminal_result_artifact_bindings_equal_result_intent_derived_digests`
- `test_terminal_session_acknowledges_only_exact_retained_runtime_journal`
- `test_preview_intent_survives_resume_tamper_and_profile_change_without_live_write`
- `test_nested_result_intent_is_atomic_before_user_result_pair`
- `test_nested_acknowledgement_intent_resumes_before_result_pair`
- `test_no_journal_not_committed_terminal_skips_ack_and_never_reapplies`
- `test_mismatch_pending_and_unknown_retain_owner_journal_without_ack`
- `test_resume_recovery_uses_one_session_lease_and_under_lock_context_only`
- `test_private_fault_hook_reaches_every_named_orchestration_crash_boundary`
- `test_terminal_cleanup_fault_hook_reaches_each_physical_and_session_boundary`
- `test_controller_prepublication_cleanup_threads_each_inventory_receipt_and_cursor`
- `test_controller_terminal_cleanup_threads_each_inventory_receipt_and_cursor`
- `test_cleanup_inventory_fault_hooks_reach_staging_bound_and_commit_boundaries`
- `test_controller_never_advances_terminal_resolution_without_fresh_carrier`
- `test_controller_ack_threads_journal_and_fence_receipts_before_release`
- `test_controller_prior_owner_planned_crashes_resume_without_adoption`
- `test_controller_terminal_inventory_prepared_crash_rebuilds_only_committed_bytes`
- `test_controller_nonterminal_recovery_threads_capability_receipt_and_cursor`
- `test_pre_session_summary_count_matrix_is_closed_without_invented_roster`
- `test_early_failure_renders_card_coverage_unavailable_without_invented_counts`
- `test_candidate_and_review_pending_transitions_resume_without_redispatch`
- `test_profile_disable_waits_until_live_terminal_cas_and_ack`
- `test_profile_disable_before_lease_blocks_publication_and_runtime`
- `test_preview_holds_profile_lease_through_terminal_without_runtime_lock`
- `test_resume_uses_one_session_and_one_profile_lease`
- `test_terminal_ack_retires_attempt_evidence_but_preserves_target_owner`
- `test_resume_after_ack_fault_finishes_retirement_without_reapply`
- `test_prepublication_cleanup_must_finish_before_apply_or_terminal`
- `test_prepublication_work_parent_substitution_stops_resume_before_quarantine_or_apply`
- `test_different_run_cannot_apply_while_prior_runtime_admission_is_unclassified`
- `test_controller_threads_admission_evidence_into_result_intent`
- `test_terminal_status_matrix_releases_or_retains_admission_exactly`
- `test_terminal_pending_recovery_keeps_result_pair_byte_identical`
- `test_terminal_pending_recovery_threads_historical_and_successor_evidence_without_result_rewrite`
- `test_private_fault_hook_covers_every_admission_crash_boundary`
- `test_admission_precedes_receipt_and_apply_started_under_one_composite`
- `test_crash_after_admission_before_receipt_blocks_profile_publisher_and_runtime`
- `test_runtime_admission_staging_hard_kill_blocks_legacy_runtime_writer_via_output_operation`
- `test_terminal_crash_before_release_blocks_profile_and_all_publishers_until_resume`
- `test_completed_release_terminal_fast_path_survives_later_valid_profile_and_current_change`
- `test_terminal_crash_after_release_authorized_before_unlink_uses_leasefree_fast_path`
- `test_controller_prior_owned_no_staging_threads_each_recovery_cursor`
- `test_controller_threads_output_child_binding_through_invocation_and_admission`
- `test_controller_rejects_output_child_replacement_after_binding`
- `test_controller_cannot_apply_while_output_child_claim_is_active`
- `test_controller_resumes_publication_before_retiring_output_child_claim`
- `test_controller_retires_output_child_claim_before_preview_or_apply`
- `test_controller_threads_same_bootstrap_lease_through_claim_retirement`
- `test_controller_claim_retirement_stops_when_current_changed_after_unlink`
- `test_controller_never_installs_before_apply_started_authorization`
- `test_controller_candidate_create_fault_resumes_same_attempt_without_adoption`
- `test_controller_claim_retired_keeps_output_operation_active_until_handoff`
- `test_controller_live_handoff_overlaps_output_and_runtime_admissions`
- `test_controller_preview_terminal_authorizes_then_releases_output_operation`
- `test_controller_preapply_terminal_failure_releases_output_operation_only_after_terminal_cas`
- `test_output_operation_unlink_fault_resumes_without_republication_or_reapply`
- `test_controller_requires_active_session_lease_for_owning_publication_authorization`
- `test_output_operation_prepared_without_physical_surface_rolls_back_before_profile_rebind`

The admission-staging crash test uses real process termination after inner-temp
materialization, after staging flush before `STAGING_BOUND`, after the bound
commit before its Session CAS, and after final-admission CAS. At every boundary
an unpaired install and broad recovery reacquire no outer process state, enter
the neutral output-operation lease, and stop before `.hsconfig`, journal, INI,
state, receipt, target, or snapshot mutation. Only the owning action-scoped
resume may reconcile the staged row and complete the fence handoff.

Use spies at the repository boundaries, not stubs inside the compiler,
publisher, installer, or matcher. The happy path may replace network card and
source acquisition with deterministic captured bytes, but must run the real
snapshot, V2 validators, compiler, renderer, strict validation, derivation,
operator summary, publisher, apply gate, runtime installer, and match code.

The pre-session count-matrix test covers missing and drifted profiles,
name/deck syntax or identity failure, and acquisition failure both before and
after an exact supported normalized roster exists. It requires the exact
applicable matrix row, `candidate_revision=None`, `run_root=None`, no result
files, and no output/runtime write. It rejects invented zero, Boolean,
partial-roster, mixed-null, and configured-card variants. The adjacent renderer
test requires coverage unavailable in both rows.

Run:

```powershell
python -B -m pytest `
  tests/test_live_start_controller.py::test_prepare_requires_only_deck_name_and_code_after_profile_enablement `
  tests/test_live_start_controller.py::test_missing_or_drifted_profile_stops_before_llm_output_or_runtime_write `
  tests/test_live_start_controller.py::test_prepare_freezes_inputs_once_and_resume_performs_no_second_fetch `
  tests/test_live_start_controller.py::test_candidate_and_review_share_exact_two_revision_budget `
  tests/test_live_start_controller.py::test_finalize_preview_publishes_without_any_runtime_artifact `
  tests/test_live_start_controller.py::test_finalize_live_uses_one_composite_and_returns_runtime_match_status `
  tests/test_live_start_controller.py::test_finalize_live_adopts_held_updated_session_without_duplicate_phase_cas `
  tests/test_live_start_controller.py::test_controller_result_intent_cas_consumes_exact_held_recovery_closed_cursor `
  tests/test_live_start_controller.py::test_resume_and_normal_controller_use_identical_held_cursor_contract `
  tests/test_live_start_controller.py::test_resume_after_apply_started_calls_recovery_only `
  tests/test_live_start_controller.py::test_prepare_always_creates_a_new_run_and_only_resume_reuses_one `
  tests/test_live_start_controller.py::test_review_and_package_receipts_gate_each_completed_phase `
  tests/test_live_start_controller.py::test_failure_results_have_one_cause_retained_state_and_no_raw_log `
  tests/test_live_start_controller.py::test_finalize_holds_one_session_lease_from_invocation_through_terminal_cas `
  tests/test_live_start_controller.py::test_result_pair_crash_windows_resume_to_one_terminal_binding `
  tests/test_live_start_controller.py::test_result_pair_closed_layout_allows_only_one_sequential_delete_only_temp `
  tests/test_live_start_controller.py::test_result_pair_exact_or_partial_temp_is_deleted_never_promoted `
  tests/test_live_start_controller.py::test_result_pair_accepts_only_missing_or_byte_exact_final `
  tests/test_live_start_controller.py::test_result_pair_rejects_both_temps_markdown_before_json_and_unsafe_occupants `
  tests/test_live_start_controller.py::test_result_pair_requires_both_temps_absent_before_terminal_cas `
  tests/test_live_start_controller.py::test_terminal_result_artifact_bindings_equal_result_intent_derived_digests `
  tests/test_live_start_controller.py::test_terminal_session_acknowledges_only_exact_retained_runtime_journal `
  tests/test_live_start_controller.py::test_preview_intent_survives_resume_tamper_and_profile_change_without_live_write `
  tests/test_live_start_controller.py::test_nested_result_intent_is_atomic_before_user_result_pair `
  tests/test_live_start_controller.py::test_nested_acknowledgement_intent_resumes_before_result_pair `
  tests/test_live_start_controller.py::test_no_journal_not_committed_terminal_skips_ack_and_never_reapplies `
  tests/test_live_start_controller.py::test_mismatch_pending_and_unknown_retain_owner_journal_without_ack `
  tests/test_live_start_controller.py::test_resume_recovery_uses_one_session_lease_and_under_lock_context_only `
  tests/test_live_start_controller.py::test_private_fault_hook_reaches_every_named_orchestration_crash_boundary `
  tests/test_live_start_controller.py::test_terminal_cleanup_fault_hook_reaches_each_physical_and_session_boundary `
  tests/test_live_start_controller.py::test_controller_prepublication_cleanup_threads_each_inventory_receipt_and_cursor `
  tests/test_live_start_controller.py::test_controller_terminal_cleanup_threads_each_inventory_receipt_and_cursor `
  tests/test_live_start_controller.py::test_cleanup_inventory_fault_hooks_reach_staging_bound_and_commit_boundaries `
  tests/test_live_start_controller.py::test_controller_never_advances_terminal_resolution_without_fresh_carrier `
  tests/test_live_start_controller.py::test_controller_ack_threads_journal_and_fence_receipts_before_release `
  tests/test_live_start_controller.py::test_controller_prior_owner_planned_crashes_resume_without_adoption `
  tests/test_live_start_controller.py::test_controller_terminal_inventory_prepared_crash_rebuilds_only_committed_bytes `
  tests/test_live_start_controller.py::test_controller_nonterminal_recovery_threads_capability_receipt_and_cursor `
  tests/test_live_start_controller.py::test_pre_session_summary_count_matrix_is_closed_without_invented_roster `
  tests/test_live_start_controller.py::test_early_failure_renders_card_coverage_unavailable_without_invented_counts `
  tests/test_live_start_controller.py::test_candidate_and_review_pending_transitions_resume_without_redispatch `
  tests/test_live_start_controller.py::test_profile_disable_waits_until_live_terminal_cas_and_ack `
  tests/test_live_start_controller.py::test_profile_disable_before_lease_blocks_publication_and_runtime `
  tests/test_live_start_controller.py::test_preview_holds_profile_lease_through_terminal_without_runtime_lock `
  tests/test_live_start_controller.py::test_resume_uses_one_session_and_one_profile_lease `
  tests/test_live_start_controller.py::test_terminal_ack_retires_attempt_evidence_but_preserves_target_owner `
  tests/test_live_start_controller.py::test_resume_after_ack_fault_finishes_retirement_without_reapply `
  tests/test_live_start_controller.py::test_prepublication_cleanup_must_finish_before_apply_or_terminal `
  tests/test_live_start_controller.py::test_prepublication_work_parent_substitution_stops_resume_before_quarantine_or_apply `
  tests/test_live_start_controller.py::test_different_run_cannot_apply_while_prior_runtime_admission_is_unclassified `
  tests/test_live_start_controller.py::test_controller_threads_admission_evidence_into_result_intent `
  tests/test_live_start_controller.py::test_terminal_status_matrix_releases_or_retains_admission_exactly `
  tests/test_live_start_controller.py::test_terminal_pending_recovery_keeps_result_pair_byte_identical `
  tests/test_live_start_controller.py::test_terminal_pending_recovery_threads_historical_and_successor_evidence_without_result_rewrite `
  tests/test_live_start_controller.py::test_private_fault_hook_covers_every_admission_crash_boundary `
  tests/test_live_start_controller.py::test_admission_precedes_receipt_and_apply_started_under_one_composite `
  tests/test_live_start_controller.py::test_crash_after_admission_before_receipt_blocks_profile_publisher_and_runtime `
  tests/test_live_start_controller.py::test_runtime_admission_staging_hard_kill_blocks_legacy_runtime_writer_via_output_operation `
  tests/test_live_start_controller.py::test_terminal_crash_before_release_blocks_profile_and_all_publishers_until_resume `
  tests/test_live_start_controller.py::test_completed_release_terminal_fast_path_survives_later_valid_profile_and_current_change `
  tests/test_live_start_controller.py::test_terminal_crash_after_release_authorized_before_unlink_uses_leasefree_fast_path `
  tests/test_live_start_controller.py::test_controller_prior_owned_no_staging_threads_each_recovery_cursor `
  tests/test_live_start_controller.py::test_controller_threads_output_child_binding_through_invocation_and_admission `
  tests/test_live_start_controller.py::test_controller_rejects_output_child_replacement_after_binding `
  tests/test_live_start_controller.py::test_controller_cannot_apply_while_output_child_claim_is_active `
  tests/test_live_start_controller.py::test_controller_resumes_publication_before_retiring_output_child_claim `
  tests/test_live_start_controller.py::test_controller_retires_output_child_claim_before_preview_or_apply `
  tests/test_live_start_controller.py::test_controller_threads_same_bootstrap_lease_through_claim_retirement `
  tests/test_live_start_controller.py::test_controller_claim_retirement_stops_when_current_changed_after_unlink `
  tests/test_live_start_controller.py::test_controller_never_installs_before_apply_started_authorization `
  tests/test_live_start_controller.py::test_controller_candidate_create_fault_resumes_same_attempt_without_adoption `
  tests/test_live_start_controller.py::test_controller_claim_retired_keeps_output_operation_active_until_handoff `
  tests/test_live_start_controller.py::test_controller_live_handoff_overlaps_output_and_runtime_admissions `
  tests/test_live_start_controller.py::test_controller_preview_terminal_authorizes_then_releases_output_operation `
  tests/test_live_start_controller.py::test_controller_preapply_terminal_failure_releases_output_operation_only_after_terminal_cas `
  tests/test_live_start_controller.py::test_output_operation_unlink_fault_resumes_without_republication_or_reapply `
  tests/test_live_start_controller.py::test_controller_requires_active_session_lease_for_owning_publication_authorization `
  tests/test_live_start_controller.py::test_output_operation_prepared_without_physical_surface_rolls_back_before_profile_rebind `
  -q -p no:cacheprovider
```

Expected RED: controller preparation, validation, finalization, and resume are
not yet implemented as one workflow.

### Step 11.2: Implement profile-first preparation

`prepare_live_start()` performs these operations in order:

1. validate only deck name and code syntax;
2. load and rebind the operator profile;
3. derive and bind the deck output child;
4. decode and resolve the complete deck identity;
5. fetch/capture full cards, collectible cards, source acquisition, source
   documents, date, and GlobalValues baseline once into bounded immutable
   values;
6. freeze the three envelopes and six-blob manifest in memory;
7. create a fresh external run/session and durably install those exact frozen
   bytes without rereading an upstream source;
8. build the schema-2 starter context from frozen inputs;
9. copy the exact Boolean `request.preview_requested` into the initial
   self-digested session;
10. transition to `INPUT_FROZEN` and return only the run root, context path,
   expected candidate revision, and bounded visible limitations.

Any profile error returns `PROFILE_REQUIRED` before creating a run directory,
output deck child, runtime lock, or candidate request. Invalid deck resolution
or input acquisition returns bounded in-memory `FAILED_PRESERVED` with
`run_root=None`. Unknown CardID or ambiguous owner errors stop before the
strategist is dispatched; when frozen inputs already exist, that failure is
atomically recorded in the new session.
`prepare_live_start()` never searches for or selects an earlier run, even when
deck name and code are identical. Only explicit
`resume_live_start(session_root=...)` may continue an existing run; ambiguous
automatic run reuse is forbidden. A crash before the sealed session exists has
no resumable run; a crash after session creation consumes only its frozen
bytes and never repeats a successful fetch for that run.
Finalize and resume read preview intent only from the immutable session field.
CLI arguments, current profile mode, environment, and reconstructed request
objects cannot turn a preview run live. A changed profile digest still fails
closed; an unchanged live profile cannot override `preview_requested=true`.

### Step 11.3: Implement candidate and review intake

`validate_live_start_candidate()` reads a caller-owned draft outside the
closed run directory, seals it as the current expected revision, and installs
it only through Task 3's intent-first pending transition under the session
lease before the `INPUT_FROZEN -> CANDIDATE_DRAFTED` CAS.
It then validates the exact bound bytes. On success it writes
`receipts/candidate_validation.json` and advances the session. On technical
failure it retains the rejected sealed candidate as non-authoritative resume
evidence, writes no success receipt, consumes the shared revision exactly once,
and returns exact bounded findings.

On success it installs, rereads, and binds the exact candidate receipt through
another pending transition whose final CAS advances `CANDIDATE_DRAFTED` to
`CANDIDATE_VALIDATED`. The next draft
may replace a rejected candidate or reviewer-rejected candidate only through
the guarded same-phase revision transition in Task 3; it simultaneously clears
all superseded receipts and downstream bindings.

Review installation, review receipt creation, package receipt creation,
prepublication receipt creation, and invocation receipt creation use the same
closed action/cursor protocol. Resume completes an exact successor or restores
an untouched predecessor without asking Codex to regenerate a candidate or
review. Unknown, mixed, or replaced physical states stop as tamper.

`validate_live_start_review()` similarly seals and validates the reviewer
document. Approved review writes the final review and receipt, then advances to
`REVIEW_APPROVED`. A revision request records the exact bounded rows, consumes
one revision, CASes `CANDIDATE_VALIDATED -> CANDIDATE_DRAFTED`, and invalidates
downstream bindings. The bound review is diagnostic resume evidence until the
next candidate replaces it. After two revision requests/failures combined, any
further rejection writes the deterministic `FAILED_PRESERVED` terminal result
without publication.

The approved path uses `install_review_validation` to write, flush, reread, and
bind `receipts/review_validation.json`; its final CAS both clears the pending
transition and advances to `REVIEW_APPROVED`. Finalize refuses to compile when
candidate or review receipt bytes, self-digest, run ID,
revision, context, candidate, review, status, or confidence no longer matches.
Task 8 similarly makes `PACKAGE_VALIDATED` and
`PREPUBLICATION_CHECK_PASSED` contingent on their exact durable receipts.

### Step 11.4: Implement finalization and resume

`finalize_live_start()` requires `REVIEW_APPROVED`, constructs the immutable
new-authority request from frozen bytes, runs Task 8's prepublication seam, and
publishes. It holds the session lease, reconstructs the exact expected profile
from sealed operator bindings, and acquires one `OperatorProfileLease` before
the final publication boundary. If that bound profile is live-disabled or the
sealed session has
`preview_requested=true`, it binds a `PREVIEW_READY` result intent, writes the
result pair, reaches terminal state while the profile and output-operation
leases remain active, CASes the operation binding to
`TERMINAL_RELEASE_AUTHORIZED`, securely releases or confirms absence of the old
fixed record under a fresh bearer minted only by Task 8's terminal-context
adapter, and exits without building an apply
invocation. A post-publication failure without runtime admission follows the
same terminal-then-release order. No release is legal before terminal CAS and
no session CAS follows the unlink.

For live mode it:

1. acquires the existing session lock and keeps it through terminal state;
2. loads `session` once, then passes each returned updated value as the next
   explicit expected-session cursor;
3. acquires one profile lease and then one fixed output-operation lease and
   keeps both through publication, runtime handoff or no-runtime terminal
   release, terminal state, and acknowledgement; profile mutation waits on the
   profile lock and every publisher waits on the operation lock;
4. publishes through Task 8's guarded publisher, assigns
   `PUBLICATION_COMMITTED`, retires the exact output-child claim through its
   two-stage receipt/CAS protocol while leaving the fixed output-operation
   admission `ACTIVE`, and completes prepublication cleanup before any preview
   terminal state or live invocation;
5. creates only one random `apply_attempt_id`; it does not capture or write an
   invocation outside the composite;
6. enters `with apply_and_match_published(session_lease=...,
   expected_session=cursor, profile_lease=...,
   output_operation_lease=..., output_operation_admission=...,
   apply_attempt_id=..., ...) as held:` exactly once. The composite acquires
   publication/runtime leases,
   captures the snapshot, seals PREPARED invocation/admission intent, claims
   admission, writes the receipt, and reaches `APPLY_STARTED` in the fixed
   order, authorizes and completes the gap-free output-operation release, then
   completes the unified install/recovery graph, its legal phase edges, and
   `recovery_closed`; the controller first assigns
   `cursor = held.updated_session`;
7. validates `held.result` only against the already persisted phase, stable
   physical disposition, match binding, attempt, and closed recovery evidence in
   that cursor. It never repeats `APPLY_COMMITTED` or `RUNTIME_MATCHED`;
8. embeds the closed result intent, including exact singleton-admission evidence
   for every admitted live attempt, in one whole-session CAS that consumes and
   clears the exact closed `apply_recovery` object, then reassigns the returned
   cursor;
9. only for `LIVE_AND_MATCHED|ALREADY_LIVE`, builds the nested acknowledgement
   from `held.acknowledgement_evidence`, embeds it in one whole-session CAS, and
   reassigns the returned cursor;
10. writes and binds the closed result pair, calls
    `complete_live_start_under_lock()`, and assigns its returned exact terminal
    session cursor while all four authority leases remain active;
11. performs exactly one status-closed post-terminal action and reassigns every
    returned successor cursor. Each action first CASes
    `terminal_retirement/PREPARED`, then advances only through the closed
    evidence-retired and admission-release-authorized stages before unlinking
    only the old admission:

    - success calls `held.acknowledge_after_terminal(session_lease=...,
      expected_terminal_session=cursor)`, retiring only authorized temporary
      evidence and releasing admission last;
    - evidence-free proven `NOT_COMMITTED` calls
      `held.release_admission_after_terminal(...)` with its exact admission;
    - proven `NOT_COMMITTED` with bound historical attempt evidence calls
      `held.resolve_and_release_after_terminal(session_lease=...,
      expected_terminal_session=cursor)`, threads every returned cleanup/session
      cursor, and never rewrites the already correct `FAILED_PRESERVED` result;
    - positively committed mismatch calls the same release method but preserves
      its fence and journal byte-identically;
    - recovery-pending or unknown calls neither and retains admission as a
      runtime-wide block;

    Every resolved physical step consumes one freshly minted authorization and
    returns one opaque `TerminalResolutionStepReceipt`. The controller passes
    that receipt directly to the one matching session CAS, reassigns the
    returned cursor, and only then mints the next authorization. Pure-CAS
    cleaning-started/stabilized edges instead consume their fresh authorization
    directly. The controller has no path that accepts a Boolean, ordinary
    dataclass, or reconstructed filesystem observation as transition authority;

12. lets the composite invalidate and release runtime then package/publication,
    then releases output-operation, profile, and finally session.

No different run is admitted merely because the first run produced an
`APPLIED_BUT_NOT_VERIFIED` user result. Pending or unknown physical disposition
remains runtime-wide admission-blocking until same-attempt targeted recovery
proves a stable disposition.

The two fixed final admissions fence the mutable authorities required to
perform later recovery. Before `APPLY_STARTED`, the output-operation three-path
family makes every generic publisher—including controller, preview, and
preserved legacy routes—reject before reconciliation or pointer/revision
mutation, makes every profile mutation reject globally before profile CAS, and
makes every generic Runtime install or recovery reject before taking its
Runtime lock or creating Runtime metadata. The owning controller may perform
only its action-scoped admission and layout callbacks while retaining the exact
operation lease. At live handoff the Runtime record is durable before the
output record can disappear and thereafter carries the publisher/profile and
Runtime-writer fences. Thus a crash at admission staging, claim unlink, handoff,
terminal CAS, acknowledgement, or release cannot let another run advance
`current` or rewrite the profile and orphan the owning session. Resume first
finishes the exact durable fence handoff or terminal release, then retires or
retains the attempt according to its closed row.

Each acknowledgement/release return is the newly persisted terminal-retirement
successor cursor. Result intent, result files, acknowledgement, and terminal
status remain byte-identical, but the outer session self-digest advances. Final
controller and recovery rechecks use that cursor directly. Neither path reloads
through a public helper, reacquires the
session/profile lock, or treats a constructed dataclass as retirement authority.

The complete controller lock order is `session -> operator profile -> fixed
output-operation lease -> output-bootstrap lease -> output-base guard ->
deck-output guard -> publisher lock`. After publication and claim-retirement
CASes, publisher and output guards may close; the controller retains the fixed
operation lease. Live or recovery continues with
`package/publication -> runtime`, performs the runtime-admission/`APPLY_STARTED`
handoff, releases the old output record, and terminalizes before releasing
`runtime -> package -> output-operation -> profile -> session`. Preview omits
package/runtime but holds session/profile/output-operation through terminal CAS
and fixed-record release. Ordinary legacy/preview publication starts at the
fixed operation lease, then bootstrap and output guards, and omits
session/profile. Profile mutation takes `profile -> output-operation`; it never
takes a publisher/package/runtime lock. The publisher lock and later package
lock are sequential, never recursive. Admission claim occurs only after the
package and runtime locks are active while the older output-operation record
and lease remain exact. These shared locks plus the overlapping durable records
close every absence/create and unlink/reclaim race without reverse acquisition.

Every ordinary Runtime install uses exactly `output-operation -> package ->
runtime`; package-free recovery uses exactly `output-operation -> runtime`.
They hold every acquired lease through the last mutation and repeat the output-
operation gate and then Runtime-admission gate immediately before the first
write. No path takes `package -> output-operation`, `runtime -> package`, or
`runtime -> output-operation`. A read-only planning package lease, if needed,
closes before the mutation sequence begins. The controller already owns the
earlier operation and package leases and may reacquire neither inside the pair.

The disable/rebind process tests place barriers immediately before publication,
before runtime-lock entry, and before physical commit. At each barrier either
the profile mutation owns the lock first and the run stops before writing, or
the run owns the lease and the mutation waits until its durable terminal state
and acknowledgement. No third interleaving is accepted.

No step reacquires the session lock. Before either user-facing file,
`bind_result_intent_under_lock()` constructs the closed nested object defined
in Task 3 and atomically compare-and-sets the whole sealed session. There is no
separate receipt write and therefore no write-before-binding window. The nested
object is the durable commit intent for all later user-result bytes. A crash
before its CAS triggers exact-attempt recovery; a crash after it must not
reclassify the result.

For a successful outcome only,
`bind_attempt_acknowledgement_under_lock()` constructs the nested object from
the held capability's exact evidence and performs one whole-session CAS. A
crash before that CAS leaves only result intent; resume re-enters exact-attempt
recovery and recomputes the same evidence. A crash after it continues from the
already bound object. There is no physical unbound acknowledgement artifact.

`complete_live_start_under_lock()` builds deterministic canonical
`result/summary.json` and UTF-8 LF `result/summary.md` bytes only from the bound
result intent. Under the held lease it:

1. derives both payloads while holding the exact result-parent identity;
2. boundedly/no-follow classifies the JSON temp; when present as one safe plain
   `nlink=1`, no-ADS file under that parent, securely deletes it without parsing
   or promotion;
3. writes JSON from `result_intent` when final is absent, accepts it unchanged
   only when byte-exact, and otherwise reports tamper;
4. only after exact JSON and absent JSON temp performs the same delete-only
   temp reconciliation and missing-or-exact final handling for Markdown;
5. rereads both finals with bounded no-follow reads and confirms both temps
   absent;
6. adds both digests to `artifact_bindings` and sets `terminal_status` in one
   compare-and-set of `session.json`.

A crash after result-intent binding, the JSON write, the Markdown write, both
readbacks, or the terminal CAS is deterministic. While terminal status is null,
resume derives the exact pair only from bound result intent. Its closed physical
rows are: both finals/temps absent; JSON temp only; exact JSON final with both
temps absent; exact JSON plus Markdown temp only; and both exact finals with both
temps absent. A safe partial or complete temp is always delete-only and final is
then regenerated from intent; it is never promoted. Both temps, Markdown temp
before exact JSON, wrong final bytes, unsafe occupant, parent replacement,
reparse, ADS, hard link, or any extra result child is tamper. Result-final
identities are not durable authority: after replace-before-terminal-CAS, exact
bytes derived from intent are sufficient, while different bytes are never
overwritten. Once terminal status is set, either result mismatch is tamper and
is never rewritten. The parameterized result fault test covers every temp
create/partial/full/flush/replace boundary for preview, committed success, and
failure-preserved summaries.

The retention fence and runtime journal are attempt evidence until the terminal
result is durable. Only `LIVE_AND_MATCHED` and `ALREADY_LIVE` bind the exact
acknowledgement object and retire attempt evidence inside the still-held package
and runtime leases. An owning v1 journal remains as durable target authority;
the terminal-retirement row is prepared, the fence is removed, the evidence-
retired CAS is durable, and admission is released last. A non-owning no-op journal
is removed before its fence while the separately bound owner remains, then
admission is released last. After terminal CAS, the held
capability accepts only the exact action-specific intermediate or completed
state; a missing owner or different occupant is tamper. For
positively proven no-journal `NOT_COMMITTED`, `retained_journal_path` is null,
cleanup is already complete, no acknowledgement object is created, and
terminalization skips ack but releases the exact admission. Committed mismatch also
creates no acknowledgement object, retains fence plus journal byte-identically,
and releases only admission. Pending and unknown retain admission, fence, and
journal as runtime-wide blocking evidence. Missing success evidence before
acknowledgement binding is tamper, never the no-journal branch. If retirement
faults, the result remains terminal and resume finishes only the same closed
action without applying or rewriting.

After admission release, a later legitimate changed-package install may clean a
stale successful owner only through Task 9's durable owner-retirement tombstone.
The old terminal fast path accepts the original live owner or that exact
completed tombstone. A committed-mismatch or unresolved controller fence is a
hard preservation fence: no later installer, recovery, or cleanup may mutate its
bound journal, owner, or target.

`resume_live_start()` validates completed phase artifacts. If a pending
admission/invocation transition, invocation receipt, or `APPLY_STARTED` exists
without terminal disposition, it calls
`recover_apply_attempt_under_lock(session_lease=..., profile_lease=...,
output_operation_lease=..., expected_session=...)` inside the already-held
session/profile/output-operation leases and never
calls the public wrapper or apply. It assigns
`cursor = recovered.held.updated_session`; the delegating
`recovered.updated_session` property must be the same exact object. It uses only
`recovered.held` for terminal facts and optional success acknowledgement. An
exact `PREPARED` transition without staging/admission rolls back. Exact unbound
staging/temp is securely retired through its executor, receipt, and cleanup CAS
before rollback or retry. `STAGING_BOUND` completes only the bound admission
commit; `PRIMARY_APPLIED` completes only the nested staged invocation receipt
and final `APPLY_STARTED` CAS inside the recovery context. A receipt or
`APPLY_STARTED` then remains recovery-only.
Earlier phases continue from their
first incomplete point without repeating successful input acquisition.
Recovery cannot race a live composite in another process.

The earlier `install_output_operation_admission/PREPARED` row has one narrower
prephysical fast path. Under session then output-operation lock, with final,
fixed staging, and reserved temp all absent, resume may roll back that pending
cursor without acquiring the sealed profile. It releases the operation lock
before any later profile acquisition and retries only through the normal
session -> profile -> operation order after all profile/output preconditions
still match. If staging, temp, or final exists, its fixed path already blocks
profile mutation; resume releases the observation lock and reacquires the full
ordered capability set before any cleanup, bind, retry, publication, or result.
Profile drift after a fully absent rollback yields bounded `FAILED_PRESERVED`
with no output/runtime write. No path acquires profile while holding the
operation lock.

An already terminal session takes one bounded retirement check before trying to
reacquire profile/package/runtime authority. For a stable released row, exact
old-admission removal is authorized only when `terminal_retirement` is
`ADMISSION_RELEASE_AUTHORIZED`. At that cursor the old exact admission is
unlinked by `_release_or_confirm_runtime_live_attempt_without_old_leases()` if
present; absence is complete; and a fully canonical identity-distinct foreign
successor is left byte-identical and also proves the old occupant is gone. The
fast path consumes the fresh release token before its first observation and
requires no historical profile, output, publication, package, or runtime lease.
Success owner
authority is either the exact live owner or its exact completed Task-9
retirement tombstone. Pending/unknown without a
retirement intent requires admission presence. Absence without a matching
`ADMISSION_RELEASE_AUTHORIZED` row is tamper. Completed rows return the
immutable historical user result without revalidating a later current pointer
or later profile bytes; this fast path cannot convert a terminal outcome.

The same bounded fast path handles the older output-operation record. A
terminal no-runtime session may release it only from
`TERMINAL_RELEASE_AUTHORIZED`; a live session may release it only from
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED` with the exact runtime admission still
present. Under the existing output-operation lease, the old record is unlinked,
absence is idempotently complete, and an identity-distinct canonical foreign
successor is preserved. `ACTIVE` plus absence, either release state without its
required terminal/runtime handoff, or a same-byte identity replacement is
tamper. A terminal no-runtime release is the last session action. A live
handoff may continue through result and terminal CASes, but every successor
preserves the complete release-authorized operation binding byte-identically;
none records, rewrites, or clears the old-record absence.

When a previously terminal pending/unknown attempt is physically resolved,
recovery preserves the exact bound result intent, JSON/Markdown bytes, and
terminal status. If disposition becomes stable, it first CASes the exact
`release_resolved_terminal/RECOVERY_PREPARED` row against the old terminal cursor
before changing active metadata, then CASes `RECOVERY_STABILIZED` with the exact
successor proof. It may advance the evidence/release-authorization stages and
unlink only the old admission; it never turns an old user result into success.
A crash before or after either resolution CAS, evidence retirement, release
authorization, or unlink resumes only that action. Stable committed mismatch retains its
attempt evidence; pending or unknown remains admission-blocking.

Define one private `LiveStartFaultHook` threaded through private controller,
prepublication, composite, apply-from-lease, installer-adapter, result-intent,
result-pair, terminal-CAS, and acknowledgement helpers. Public operator
wrappers keep their simple signatures and pass `no_live_start_fault`; tests use
one underscored harness, not monkeypatches inside compiler/publisher/installer/
matcher. The sole closed hook-name enum is the exact Task-8 list in its declared
order; Task 11 must import it and may neither redeclare nor reorder a subset.
In particular, the real pipeline invokes
`after_output_operation_admission_prepared`,
`after_output_operation_admission_staging_flush_before_staging_bound_cas`,
`after_output_operation_admission_staging_bound`,
`after_output_operation_admission_bound_commit_before_cas`,
`after_output_operation_admission_bound`,
`after_invocation_prepared_before_admission` immediately after the PREPARED CAS,
`after_admission_bound_before_invocation_write` immediately after the
PRIMARY_APPLIED CAS, `after_output_operation_release_authorized` after the
handoff/terminal cursor, `after_output_operation_admission_unlink` after the
exact release action, and every terminal-retirement hook at its named durable
boundary.

Every Task-11/13 crash test names one of these points and asserts the hook is
reached through the real public pipeline. Production cannot select a hook by
CLI, environment, profile, starter document, or package bytes.

For session-backed `FAILED_PRESERVED` and every
`APPLIED_BUT_NOT_VERIFIED`, the bound result pair contains exactly one bounded
concrete cause plus the retained safe state. `PROFILE_REQUIRED` and a
pre-session deck/input `FAILED_PRESERVED` return the same closed pre-session
summary field set only in memory/stdout with `run_root=None`; they select the
exact Task-3 pre-session count row, render card coverage unavailable, and
create no result files. No form
embeds traceback text or long raw logs. Technical detail stays in sealed
receipts when a run exists and is shown only when explicitly requested.

### Step 11.5: Replace the embedded three-candidate workflow

Keep the embedded bundle at exactly nine files. Modify only the relevant
contents:

- `SKILL.md`;
- `references/workflow.md`;
- `references/contract-compiler-checklist.md`;
- `scripts/build_config.py`;
- `scripts/validate_package.py`.

The helper phases become:

```text
prepare
validate-candidate
validate-review
finalize
resume
```

`prepare` forwards only deck name, deck code, and explicit preview intent to
the controller. `validate-candidate` and `validate-review` accept one external
draft path and the sealed session root. `finalize` and `resume` accept only the
session root. The helper must reject duplicate and abbreviated controlled
options before forwarding.

The skill instructions must require:

- one lead strategist with only sealed context and the candidate contract;
- one independent reviewer with only context, candidate, and validation
  receipt;
- no strategist conversation given to the reviewer;
- at most two shared revisions;
- no provider/model client or credentials;
- exact user-visible confidence `high|limited`;
- live by default only under a valid enabled profile;
- explicit preview overriding live;
- recovery-only after an invocation receipt or `APPLY_STARTED`.

The lead's closed assignment must also require one coherent deck plan, a
non-empty coherent Mulligan, the full validated GlobalValues key set, exactly
one disposition per unique physical main-deck CardID, correct runtime owners,
exact transformation/sideboard/linked-owner relations, combos only when their
complete ordered runtime contract is supported, a reason for every deliberate
non-configuration, and no fabricated surface or unsupported behavior. It must
explicitly instruct the same lead to compare relevant evidence-supported
strategic alternatives internally, select the strongest practical coherent
start configuration, and emit exactly one candidate without exposing rankings
or a candidate tournament. Technical and review findings return only to that
same lead within the shared revision budget.

The reviewer's closed checklist must cover deck-plan alignment, Mulligan
coherence, GlobalValues coherence and unnecessary baseline drift, complete
card dispositions, transformations/owners/sideboards, source strength,
unsupported assumptions, overconfiguration, simpler equivalent rules, and
technical realizability in the supported runtime grammar. It must state that
the reviewer cannot write runtime files, replace the candidate, see strategist
conversation, or silently choose a fallback.

Extend the bundle contract tests to require every one of those lead/reviewer
instructions in the decoded `SKILL.md` or `references/workflow.md`, along with
the best-practical-single-candidate selection language, same-lead revision
language, fixed five helper phases, and no-runtime-write reviewer boundary.

Regenerate the canonical bundle resource, every row size/hash, aggregate hash,
and the exact aggregate pin in `tests/test_external_skill_bundle.py`. Keep all
embedded lines within the thin-router line limit and all nine paths unchanged.

### Step 11.6: Verify bundle and controller, then commit

```powershell
python -B -m pytest `
  tests/test_optimized_skill_workflow.py::test_embedded_skill_defines_exact_single_candidate_review_sequence `
  tests/test_optimized_skill_workflow.py::test_embedded_helper_rejects_duplicate_abbreviated_or_apply_bypass_options `
  tests/test_external_skill_bundle.py::test_embedded_bundle_is_exact_closed_nine_file_contract `
  tests/test_contract_preflight.py::test_contract_preflight_exposes_skill_thin_router_contract `
  tests/test_distribution_contract.py::test_skill_bundle_has_exact_source_sdist_wheel_byte_parity `
  -q -p no:cacheprovider
python -B -m ruff check `
  src/hsconfig/live_start_controller.py `
  tests/test_live_start_controller.py `
  tests/test_optimized_skill_workflow.py `
  tests/test_external_skill_bundle.py `
  tests/test_contract_preflight.py `
  tests/test_distribution_contract.py
git diff --check
git add -- `
  src/hsconfig/live_start_controller.py `
  src/hsconfig/resources/codex_skill_bundle.json `
  tests/test_live_start_controller.py `
  tests/test_optimized_skill_workflow.py `
  tests/test_external_skill_bundle.py `
  tests/test_contract_preflight.py `
  tests/test_distribution_contract.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "feat: orchestrate Codex first live starts"
```

---

## Task 12: Polish Only the Relevant Product Surfaces

**Owned files**

- Modify: `README.md`
- Modify: `docs/operator/README.md`
- Modify: `src/hsconfig/cli_parser.py`
- Modify: `pyproject.toml`
- Modify: `scripts/github_governance.py`
- Modify: `src/hsconfig/publishable_tree.py`
- Modify: `tests/test_readme_contract.py`
- Modify: `tests/test_operator_docs_contract_policy.py`
- Modify: `tests/test_operator_guidance.py`
- Modify: `tests/test_cli_help.py`
- Modify: `tests/test_github_governance.py`
- Modify: `tests/helpers/markdown_contract.py`
- Modify: `tests/test_repository_governance.py`
- Modify: `tests/test_release_gate.py`

### Step 12.1: Write RED one-route documentation tests

Add these exact tests:

- `test_readme_leads_with_deck_name_code_to_live_matched_config`
- `test_readme_has_one_copyable_normal_prompt_and_compact_success`
- `test_operator_guide_has_one_normal_single_candidate_live_route`
- `test_docs_do_not_present_three_candidates_or_per_run_apply_confirmation_as_normal`
- `test_cli_help_presents_codex_first_live_route_and_preserves_expert_commands`

The required flow line is literal:

```text
Deck -> Config -> Validate -> Live -> Match
```

The normal prompt contains only deck name and deck code. The result example
contains human deck name, complete card coverage, review confidence, and
`LIVE_AND_MATCHED`. Do not show content hashes or versioned runtime directories
in that normal example.

Run:

```powershell
python -B -m pytest `
  tests/test_readme_contract.py::test_readme_leads_with_deck_name_code_to_live_matched_config `
  tests/test_readme_contract.py::test_readme_has_one_copyable_normal_prompt_and_compact_success `
  tests/test_operator_docs_contract_policy.py::test_operator_guide_has_one_normal_single_candidate_live_route `
  tests/test_operator_guidance.py::test_docs_do_not_present_three_candidates_or_per_run_apply_confirmation_as_normal `
  tests/test_cli_help.py::test_cli_help_presents_codex_first_live_route_and_preserves_expert_commands `
  -q -p no:cacheprovider
```

Expected RED: current docs and help still name the optimized three-candidate
workflow and explicit `--apply` as the normal route.

### Step 12.2: Apply minimal text polish

Update the root README near the top with exactly:

1. outcome-first one-sentence product description;
2. one copyable normal prompt;
3. one compact successful response;
4. the five-stage flow line;
5. one sentence limiting the claim to best practical evidence-based pre-run
   configuration.

Update the operator guide and CLI help to make the installed Codex skill the
normal route. Keep raw `configure`, `apply`, `runtime-match`, source commands,
and conservative compatibility documented as expert or diagnostic surfaces.
Do not delete the detailed apply authority, source, security, or recovery
documentation.

Set the package description to the same concise product outcome. Normal
display uses the deck name; technical diagnostics may still include hashes.

### Step 12.3: Update GitHub desired metadata without touching governance

Change the desired description to:

```text
Codex-first HearthRanger start-config generator: deck name and deck code to a validated, live-matched VisionAI CustomConfig.
```

Set the exact sorted topics to:

```python
DESIRED_TOPICS = [
    "codex",
    "configuration",
    "hearthranger",
    "hearthstone",
    "python",
    "visionai",
]
```

Add two narrow script commands:

```text
python scripts/github_governance.py product-polish --repo OWNER/REPO --json
python scripts/github_governance.py verify-product-polish --repo OWNER/REPO --json
```

`product-polish` may PATCH only `description` and PUT only `topics`.
`verify-product-polish` is read-only. Neither command creates, edits, enables,
or disables a ruleset; changes Actions, security settings, collaborators,
branches, tags, releases, or visibility; or calls the historic cutover flow.

Add and run:

```powershell
python -B -m pytest `
  tests/test_github_governance.py::test_product_polish_changes_only_description_and_topics `
  tests/test_github_governance.py::test_verify_product_polish_is_read_only_and_exact `
  -q -p no:cacheprovider
```

Expected RED: the desired description/topics are old and the narrow commands
do not exist.

### Step 12.4: Rebind exact documentation-security pins once

After final wording is frozen:

- recompute the root README digest used by
  `tests/helpers/markdown_contract.py` and repository-governance tests;
- update exact approved fixture-option line/hash positions in
  `src/hsconfig/publishable_tree.py` only where the unchanged literal moved;
- update the exact paired assertions in `tests/test_release_gate.py`;
- keep the source-marker exception tuple empty;
- do not weaken absolute-path, unfinished-marker, link, Markdown, or legacy-inventory
  scanners.

Run:

```powershell
python -B -m pytest `
  tests/test_repository_governance.py::test_governance_round14_frozen_policy_is_independent_of_shared_digest `
  tests/test_release_gate.py -k "current_operator and exactly_approved" `
  tests/test_publishable_tree.py::test_repository_working_inventory_is_bound_baseline_or_complete_cutover `
  -q -p no:cacheprovider
python -B scripts/check_publishable_tree.py `
  --root . `
  --mode working-pre-cutover `
  --json
```

Require zero violations and legacy inventory zero.

### Step 12.5: Verify and commit

```powershell
python -B -m ruff check `
  src/hsconfig/cli_parser.py `
  scripts/github_governance.py `
  src/hsconfig/publishable_tree.py `
  tests/test_readme_contract.py `
  tests/test_operator_docs_contract_policy.py `
  tests/test_operator_guidance.py `
  tests/test_cli_help.py `
  tests/test_github_governance.py `
  tests/helpers/markdown_contract.py `
  tests/test_repository_governance.py `
  tests/test_release_gate.py
git diff --check
git add -- `
  README.md `
  docs/operator/README.md `
  src/hsconfig/cli_parser.py `
  pyproject.toml `
  scripts/github_governance.py `
  src/hsconfig/publishable_tree.py `
  tests/test_readme_contract.py `
  tests/test_operator_docs_contract_policy.py `
  tests/test_operator_guidance.py `
  tests/test_cli_help.py `
  tests/test_github_governance.py `
  tests/helpers/markdown_contract.py `
  tests/test_repository_governance.py `
  tests/test_release_gate.py
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "docs: present the one prompt live start workflow"
```

---

## Task 13: Prove the Integrated Route Without Repeating Broad Tests

**Owned files**

- Create: `tests/test_codex_first_live_e2e.py`
- Modify: `tests/starter_fixtures.py`
- Modify: `scripts/run_coverage_gate.py`
- Modify: `tests/test_coverage_contract.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `tests/test_ci_workflow_contract.py`

### Step 13.1: Write one real-pipeline E2E matrix

Add these exact tests:

- `test_supported_non_thirty_resolvable_deck_reaches_preview_with_exact_coverage`
- `test_shadowpriest_reaches_live_and_matched_through_real_downstream_pipeline`
- `test_limited_review_is_visible_but_still_valid`
- `test_second_identical_run_is_already_live_and_does_not_add_runtime_revision`
- `test_later_changed_package_cleans_only_authenticated_old_runtime_revision`
- `test_invalid_candidate_preserves_publication_and_runtime_byte_exact`
- `test_crash_after_invocation_prepared_before_admission_rolls_back_without_block`
- `test_crash_after_admission_before_receipt_blocks_every_affected_writer_and_continues_once`
- `test_crash_after_invocation_receipt_never_reapplies`
- `test_crash_after_apply_started_never_reapplies`
- `test_fresh_runtime_layout_bootstrap_crashes_bind_parents_before_first_attempt_file`
- `test_crash_after_runtime_journal_creation_recovers_same_attempt_without_reapply`
- `test_new_target_first_install_crashes_every_copy_verify_rename_and_ini_boundary`
- `test_candidate_journal_bound_before_create_hard_kill_creates_and_binds_without_reapply`
- `test_candidate_create_before_identity_receipt_cas_hard_kill_resumes_without_adoption`
- `test_controller_journal_staging_hard_kills_use_external_file_action_only`
- `test_prior_owned_no_staging_hard_kills_recover_without_candidate_or_second_apply`
- `test_prior_owner_planned_hard_kills_before_and_after_v1_create`
- `test_crash_after_nonowning_installer_return_before_session_cas_recovers_same_attempt`
- `test_crash_after_physical_commit_before_apply_committed_cas_recovers_without_reapply`
- `test_crash_after_recovery_closed_before_result_intent_preserves_cursor_classification_and_attempt`
- `test_recovery_closed_is_distinct_active_to_closed_cursor_before_result`
- `test_initial_runtime_observation_receipt_crashes_resume_each_family_without_swapped_evidence`
- `test_owner_root_retirement_crash_reuses_prebound_completed_tombstone_commitment`
- `test_failed_runtime_action_selects_exactly_one_terminal_observation_without_reapply`
- `test_prior_owner_pre_ini_failure_is_failed_preserved_but_post_ini_failure_is_commit_recovery`
- `test_hard_kill_after_terminal_classification_selection_resumes_observation_only`
- `test_commit_then_runtime_drift_reports_applied_but_not_verified`
- `test_terminal_crash_before_admission_release_blocks_legacy_preview_controller_publish_and_profile_rebind`
- `test_terminal_retirement_crashes_resume_each_stage_without_reapply`
- `test_success_ack_hard_kills_resume_journal_then_fence_receipts`
- `test_terminal_no_commit_cleanup_crashes_preserve_failed_preserved_and_resume_each_boundary`
- `test_terminal_inventory_prepared_hard_kill_rejects_identity_substitution`
- `test_nonterminal_recovery_hard_kills_advance_one_row_per_capability_without_reapply`
- `test_old_success_resumes_after_later_owner_retirement_tombstone`
- `test_owner_retirement_crashes_each_tombstone_entry_journal_and_unlink_boundary`
- `test_owner_retirement_zero_entry_and_root_rmdir_crashes_reach_completed_without_skip`
- `test_committed_mismatch_fence_survives_later_changed_install`
- `test_output_child_bootstrap_hard_kills_resume_every_claim_and_child_boundary`
- `test_output_operation_admission_fences_profile_publishers_and_runtime_writers_through_runtime_handoff`
- `test_runtime_admission_staging_hard_kills_leave_generic_runtime_writer_blocked`
- `test_controller_and_legacy_install_lock_order_completes_without_deadlock_or_early_runtime_write`
- `test_output_operation_admission_hard_kills_resume_every_create_bind_and_release_boundary`
- `test_crash_after_output_operation_unlink_reenters_fresh_pair_and_recovers_without_reapply`
- `test_legacy_public_apply_fresh_runtime_root_crash_resumes_without_semantic_artifact`
- `test_staged_authority_file_hard_kills_require_bound_identity_before_commit`
- `test_live_handoff_never_has_both_output_and_runtime_admissions_absent`
- `test_preview_releases_output_operation_only_after_terminal_cas`
- `test_valid_foreign_output_operation_successor_is_never_deleted_by_old_resume`
- `test_output_child_claim_retirement_hard_kills_resume_without_republication`
- `test_foreign_publisher_cannot_win_during_output_child_bootstrap_or_publication`
- `test_output_child_replacement_after_bound_never_reaches_admission_or_runtime`
- `test_candidate_leaf_action_before_cas_accepts_safe_content_but_rejects_unsafe_or_wrong_content`
- `test_candidate_tree_is_reverified_after_first_verify_before_owner_binding`
- `test_result_pair_hard_kill_matrix_reaches_one_byte_exact_terminal_pair`

The tests may inject deterministic card/source acquisition only at the
approved external input seam. They must use the real profile, frozen snapshot,
session, V2 validators, compiler, renderer, strict validator, derivation,
operator-summary replay, publisher, apply gate, runtime installer, recovery,
and runtime matcher. Do not monkeypatch any of those downstream components.

The arbitrary-deck case must be absent from the audited catalog, fully
resolvable by its supplied card data, and have more than 30 unique physical
main-deck CardIDs while remaining valid under the supported deck-structure
contract. Its frozen roster, candidate dispositions, result intent, JSON
summary, and Markdown coverage all carry the same exact count without
truncation or a literal-30 rejection. The ShadowPriest case uses the repository
fixture deck and checks optional HS/HDT identity only when present and
consistent.

Each crash-window test asserts the unchanged apply-attempt ID,
exact runtime transaction ID, journal count, composite/install call count,
session phase, physical disposition, and terminal classification. No recovery
case after invocation receipt may create a second journal or initialize a
second recovery cursor. The admission-before-receipt row prepares exactly one
cursor and advances each file action once or idempotently confirms it; the
pre-admission PREPARED row performs no runtime file action. The Runtime-
admission-staging case hard-kills after inner-temp creation, staging flush,
`STAGING_BOUND`, bound final commit before Session CAS, and final-admission CAS.
At every row a fresh legacy install acquires `output-operation -> package ->
runtime` and broad recovery acquires `output-operation -> runtime`; both invoke
zero mutators and leave Runtime bytes and the pre-apply snapshot byte-identical
until exact same-attempt resume completes the handoff. A real two-process
barrier puts the controller after operation-lock acquisition but before package
acquisition while a legacy installer starts; one proceeds, the other waits, no
reverse lock is held, both finish without deadlock, and the blocked process
creates no runtime-root child. Malformed/staging-only state blocks; ordinary
Evidence cannot use the owning exception. The terminal-release race uses real
processes and proves
every generic publisher leaves `current` and
revisions byte-identical and profile mutation leaves profile bytes unchanged;
after owner resume releases admission, the waiting next run may proceed.
The post-handoff crash case kills the owner immediately after the historical
output-operation record is unlinked, discards every process-local lease/token,
and requires a fresh process to enter a new Pair from the exact persisted
`RUNTIME_HANDOFF_RELEASE_AUTHORIZED` cursor and Runtime admission. It reaches
the same terminal classification with the same attempt ID and zero second
apply, while an exact foreign output successor remains byte-identical. The
Legacy fresh-root case starts with the caller-selected runtime root absent,
proves it stays absent through every failing output-operation, Package/apply,
and Runtime-admission gate, kills immediately after the safe empty-root
bootstrap, and resumes through a fresh public call without any pre-lock
`.hsconfig`, journal, fence, INI, state, receipt, or target artifact. Parent/root
substitution and an active same-path admission fail before creation or reuse.
The fresh-layout case begins with only the runtime root plus the narrow
`.hsconfig/apply.lock` bootstrap. It kills after every permitted directory
create and before its receipt CAS, proves the fixed seven-row order, and proves
that no attempt fence, journal, candidate, INI, state, or receipt exists until
all parent identities are bound and `APPLY_STARTED` is durable. The New-Target
case records the entire action trace and kills before and after every schema-2
commit, v1 phase commit, candidate entry, tree verification, target rename,
target-owner binding, and INI commit; uninterrupted and resumed traces must be
identical. Candidate file action-before-CAS accepts only safe exact manifest
content; wrong content or unsafe metadata fails, and full parity is reread after
the first verification immediately before rename and owner binding. The owner-
retirement case kills after commitment, at both tombstone staged commits, around
the initial cursor-zero v1 commit, each entry-delete/old-v1-cursor pair, empty-
root retirement, `TARGET_RETIRED`, `COMPLETED`, and the final old-owner unlink.
For zero entries and for the last nonzero cursor it proves the final-v1 receipt
CAS binds the exact planned COMPLETED size/digest before root removal; a kill
after root removal reuses only that commitment and rejects changed tombstone,
list, or v1 authority. It includes a zero-entry target, proves the successor owner and permanent full-
inventory tombstone survive, and proves no callback advances two durable rows.
The journal-before-candidate row proves
`CANDIDATE_PLANNED + v1 PREPARED + no attempt tree`, remints only the declared
candidate create-or-confirm action, binds that identity by receipt CAS, and
continues the same attempt without a second install. A deliberate terminal
failure from the same historical no-tree row may take the separately persisted
selection/observation then journal/fence `NOT_COMMITTED` retirement path;
ordinary crash resume never chooses it prematurely. The selection crash test
proves one same-pair observation receipt, exactly one I/O-free selection CAS,
observation-only resume, and no second install. First-install, nonterminal,
terminal-resolution, and terminal-classification cases each kill after receipt
creation before its consuming CAS and reject swapped or reconstructed Evidence.
A crash after `recovery_closed` but before result intent retains the same
attempt and disposition with a distinct `CLOSED` cursor until that consuming
CAS; an `ACTIVE` stable cursor remains insufficient. The prior-owned row proves
`PRIOR_OWNER_BOUND + v1 PREPARED`, exact
separate target/owner, and zero candidate/staging entries before INI; a kill
before INI resolves `FAILED_PRESERVED`, while a kill after the INI write before
journal CAS completes commit recovery with no cleanup and no second apply. The
planned-row case kills both before and after exact v1 creation and proves the
prebound journal bytes plus target/owner identities are never recaptured. The
tree-bearing no-commit case faults after every inventory write/CAS,
entry delete/cursor CAS, journal delete/CAS, fence delete/CAS, and sidecar
delete/CAS; every resume retains the same result bytes and status. Success ack
kills after each journal/fence action and before each receipt CAS. Nonterminal
recovery kills after every one-row physical successor and proves the same
attempt reaches recovered match without a second install or premature terminal
result. Candidate-create cases prove one exact planned candidate identity.
Controller journal staging cases kill after inner-temp creation, partial and
complete write, flush, staging commit, `STAGING_BOUND` CAS, POSIX link before
staging unlink, and final commit before receipt CAS. Every `PLANNED` residue is
delete-and-retry and never promoted; every `STAGING_BOUND` completion preserves
only the bound identity and reaches the same exact journal successor. Legacy
UUID promotion is proved only by the separate Task-9 compatibility matrix.
The staged-authority case samples output-operation, claim, runtime-admission,
invocation-receipt, journal, INI, state, receipt, and inventory writes. It proves
unbound staging is delete-only with receipt/CAS, bound staging is the sole final
identity, and the POSIX same-identity two-link intermediate converges without
adoption or a second mutation.
The output-bootstrap tests parametrize all thirteen output-child fault points
plus the seven output-operation points, including both staging-flush boundaries,
and
require one unchanged predecessor or exact
declared successor, prove
that active claims block controller/preview/legacy publishers, and require zero
claim-temp residue plus retired claim authority before preview or apply.
At every sampled operation/publication/live-handoff barrier after physical work
starts, at least the exact output-operation final, its fixed staging/reserved
temp, or the runtime admission is present. Final output and runtime records may
overlap, but a completely unfenced physical state is forbidden. Profile bytes
and `current` remain byte-identical while any of those surfaces is active.
After authorized release there is no old output-operation record or staging
residue, and no resume path republishes or installs a second time.

Run:

```powershell
python -B -m pytest `
  tests/test_codex_first_live_e2e.py::test_supported_non_thirty_resolvable_deck_reaches_preview_with_exact_coverage `
  tests/test_codex_first_live_e2e.py::test_shadowpriest_reaches_live_and_matched_through_real_downstream_pipeline `
  tests/test_codex_first_live_e2e.py::test_limited_review_is_visible_but_still_valid `
  tests/test_codex_first_live_e2e.py::test_second_identical_run_is_already_live_and_does_not_add_runtime_revision `
  tests/test_codex_first_live_e2e.py::test_later_changed_package_cleans_only_authenticated_old_runtime_revision `
  tests/test_codex_first_live_e2e.py::test_invalid_candidate_preserves_publication_and_runtime_byte_exact `
  tests/test_codex_first_live_e2e.py::test_crash_after_invocation_prepared_before_admission_rolls_back_without_block `
  tests/test_codex_first_live_e2e.py::test_crash_after_admission_before_receipt_blocks_every_affected_writer_and_continues_once `
  tests/test_codex_first_live_e2e.py::test_crash_after_invocation_receipt_never_reapplies `
  tests/test_codex_first_live_e2e.py::test_crash_after_apply_started_never_reapplies `
  tests/test_codex_first_live_e2e.py::test_fresh_runtime_layout_bootstrap_crashes_bind_parents_before_first_attempt_file `
  tests/test_codex_first_live_e2e.py::test_crash_after_runtime_journal_creation_recovers_same_attempt_without_reapply `
  tests/test_codex_first_live_e2e.py::test_new_target_first_install_crashes_every_copy_verify_rename_and_ini_boundary `
  tests/test_codex_first_live_e2e.py::test_candidate_journal_bound_before_create_hard_kill_creates_and_binds_without_reapply `
  tests/test_codex_first_live_e2e.py::test_candidate_create_before_identity_receipt_cas_hard_kill_resumes_without_adoption `
  tests/test_codex_first_live_e2e.py::test_controller_journal_staging_hard_kills_use_external_file_action_only `
  tests/test_codex_first_live_e2e.py::test_prior_owned_no_staging_hard_kills_recover_without_candidate_or_second_apply `
  tests/test_codex_first_live_e2e.py::test_prior_owner_planned_hard_kills_before_and_after_v1_create `
  tests/test_codex_first_live_e2e.py::test_crash_after_nonowning_installer_return_before_session_cas_recovers_same_attempt `
  tests/test_codex_first_live_e2e.py::test_crash_after_physical_commit_before_apply_committed_cas_recovers_without_reapply `
  tests/test_codex_first_live_e2e.py::test_crash_after_recovery_closed_before_result_intent_preserves_cursor_classification_and_attempt `
  tests/test_codex_first_live_e2e.py::test_recovery_closed_is_distinct_active_to_closed_cursor_before_result `
  tests/test_codex_first_live_e2e.py::test_initial_runtime_observation_receipt_crashes_resume_each_family_without_swapped_evidence `
  tests/test_codex_first_live_e2e.py::test_owner_root_retirement_crash_reuses_prebound_completed_tombstone_commitment `
  tests/test_codex_first_live_e2e.py::test_failed_runtime_action_selects_exactly_one_terminal_observation_without_reapply `
  tests/test_codex_first_live_e2e.py::test_prior_owner_pre_ini_failure_is_failed_preserved_but_post_ini_failure_is_commit_recovery `
  tests/test_codex_first_live_e2e.py::test_hard_kill_after_terminal_classification_selection_resumes_observation_only `
  tests/test_codex_first_live_e2e.py::test_commit_then_runtime_drift_reports_applied_but_not_verified `
  tests/test_codex_first_live_e2e.py::test_terminal_crash_before_admission_release_blocks_legacy_preview_controller_publish_and_profile_rebind `
  tests/test_codex_first_live_e2e.py::test_terminal_retirement_crashes_resume_each_stage_without_reapply `
  tests/test_codex_first_live_e2e.py::test_success_ack_hard_kills_resume_journal_then_fence_receipts `
  tests/test_codex_first_live_e2e.py::test_terminal_no_commit_cleanup_crashes_preserve_failed_preserved_and_resume_each_boundary `
  tests/test_codex_first_live_e2e.py::test_terminal_inventory_prepared_hard_kill_rejects_identity_substitution `
  tests/test_codex_first_live_e2e.py::test_nonterminal_recovery_hard_kills_advance_one_row_per_capability_without_reapply `
  tests/test_codex_first_live_e2e.py::test_old_success_resumes_after_later_owner_retirement_tombstone `
  tests/test_codex_first_live_e2e.py::test_owner_retirement_crashes_each_tombstone_entry_journal_and_unlink_boundary `
  tests/test_codex_first_live_e2e.py::test_owner_retirement_zero_entry_and_root_rmdir_crashes_reach_completed_without_skip `
  tests/test_codex_first_live_e2e.py::test_committed_mismatch_fence_survives_later_changed_install `
  tests/test_codex_first_live_e2e.py::test_output_child_bootstrap_hard_kills_resume_every_claim_and_child_boundary `
  tests/test_codex_first_live_e2e.py::test_output_operation_admission_fences_profile_publishers_and_runtime_writers_through_runtime_handoff `
  tests/test_codex_first_live_e2e.py::test_runtime_admission_staging_hard_kills_leave_generic_runtime_writer_blocked `
  tests/test_codex_first_live_e2e.py::test_controller_and_legacy_install_lock_order_completes_without_deadlock_or_early_runtime_write `
  tests/test_codex_first_live_e2e.py::test_output_operation_admission_hard_kills_resume_every_create_bind_and_release_boundary `
  tests/test_codex_first_live_e2e.py::test_crash_after_output_operation_unlink_reenters_fresh_pair_and_recovers_without_reapply `
  tests/test_codex_first_live_e2e.py::test_legacy_public_apply_fresh_runtime_root_crash_resumes_without_semantic_artifact `
  tests/test_codex_first_live_e2e.py::test_staged_authority_file_hard_kills_require_bound_identity_before_commit `
  tests/test_codex_first_live_e2e.py::test_live_handoff_never_has_both_output_and_runtime_admissions_absent `
  tests/test_codex_first_live_e2e.py::test_preview_releases_output_operation_only_after_terminal_cas `
  tests/test_codex_first_live_e2e.py::test_valid_foreign_output_operation_successor_is_never_deleted_by_old_resume `
  tests/test_codex_first_live_e2e.py::test_output_child_claim_retirement_hard_kills_resume_without_republication `
  tests/test_codex_first_live_e2e.py::test_foreign_publisher_cannot_win_during_output_child_bootstrap_or_publication `
  tests/test_codex_first_live_e2e.py::test_output_child_replacement_after_bound_never_reaches_admission_or_runtime `
  tests/test_codex_first_live_e2e.py::test_candidate_leaf_action_before_cas_accepts_safe_content_but_rejects_unsafe_or_wrong_content `
  tests/test_codex_first_live_e2e.py::test_candidate_tree_is_reverified_after_first_verify_before_owner_binding `
  tests/test_codex_first_live_e2e.py::test_result_pair_hard_kill_matrix_reaches_one_byte_exact_terminal_pair `
  -q -p no:cacheprovider
```

Expected RED: at least the new public route is absent until Tasks 1 through 12
are complete. If the first run is already GREEN after those tasks, record it as
integration evidence and do not create an artificial failure.

### Step 13.2: Run one consolidated focused acceptance set

Run each named group once. Do not add an entire existing test file to this
command merely because it is adjacent.

```powershell
python -B -m pytest `
  tests/test_operator_profile.py `
  tests/test_input_snapshot_manifest.py `
  tests/test_live_start_session.py `
  tests/test_starter_review.py `
  tests/test_optimized_start_authority.py `
  tests/test_apply_invocation.py `
  tests/test_runtime_live_admission.py `
  tests/test_apply_and_match_published.py `
  tests/test_live_start_controller.py `
  tests/test_codex_first_live_e2e.py `
  tests/test_package_derivation_receipt.py::test_optimized_receipt_binds_exact_five_starter_documents `
  tests/test_apply_gate.py::test_apply_gate_allows_valid_llm_optimized_start `
  tests/test_configure_publication.py::test_failed_configure_leaves_previous_current_byte_identical `
  tests/test_runtime_install_fault_matrix.py::test_process_termination_at_every_persisted_checkpoint_recovers `
  tests/test_current_output.py::test_package_input_lease_blocks_publisher_for_entire_consumer_lifetime `
  tests/test_external_skill_bundle.py::test_embedded_bundle_is_exact_closed_nine_file_contract `
  tests/test_distribution_contract.py::test_skill_bundle_has_exact_source_sdist_wheel_byte_parity `
  -q -p no:cacheprovider
```

This is the only broad-ish local acceptance command. Do not run the local full
suite afterward.

### Step 13.3: Run static gates and independent final reviews

The binding CI must execute the real POSIX hard-link fallback, not merely
collect the three tests in the Windows full-suite job. In the existing
`ubuntu-latest` `package` job, immediately after `Verify distribution and fresh
wheel installation`, add exactly this one focused step; do not add a job or a
matrix:

```yaml
- name: Verify POSIX bound no-replace crash boundary
  run: >-
    python -B -m pytest
    tests/test_package_io.py::test_no_replace_posix_hook_fires_after_exact_link_before_source_unlink
    tests/test_atomic_io.py::test_atomic_bound_no_replace_maps_posix_link_before_unlink_fault
    tests/test_package_io.py::test_no_replace_posix_hard_kill_after_link_resumes_bound_identity
    -q -p no:cacheprovider
```

The three nodes may skip only on a non-POSIX local Task-3 run. In this Ubuntu
step, a non-POSIX platform, unavailable hard-link operation, unreachable hook,
missing real process kill, or incomplete resume is a test failure, never a
skip. Add
`test_package_job_runs_posix_bound_no_replace_crash_boundary_on_ubuntu` to
`tests/test_ci_workflow_contract.py`; it requires the exact package runner,
step name, placement after distribution verification, and exact three-node
command, and rejects any matrix, conditional, `continue-on-error`, or alternate
skip-capable command.

Append exactly these seven new write-authority modules, in this order, after the
existing entries in the ordered `CRITICAL_MODULES` inventory in
`scripts/run_coverage_gate.py` and its mirrored test fixture. Appending keeps
all existing index-addressed coverage controls stable:

```text
src/hsconfig/operator_profile.py
src/hsconfig/output_operation_admission.py
src/hsconfig/live_start_session.py
src/hsconfig/apply_invocation.py
src/hsconfig/runtime_live_admission.py
src/hsconfig/published_apply.py
src/hsconfig/live_start_controller.py
```

All seven must reach 100% statements and branches in final CI. The output-
operation module is critical because it is the global profile/publisher fence;
the controller is
critical because its preview/live authorization branch is the only layer that
decides whether the otherwise valid package may reach the composite runtime
writer. The input and starter modules remain under the global branch threshold
because existing strict/apply boundaries independently revalidate their
output. Add
`test_new_live_write_authority_modules_are_critical` to
`tests/test_coverage_contract.py`; it asserts the exact seven-path order,
uniqueness, and both 100% statement and branch requirements, so the output-
operation module cannot fall through to the aggregate threshold. Run that one
node before the static gates.

```powershell
python -B -m pytest `
  tests/test_ci_workflow_contract.py::test_package_job_runs_posix_bound_no_replace_crash_boundary_on_ubuntu `
  tests/test_coverage_contract.py::test_new_live_write_authority_modules_are_critical `
  -q -p no:cacheprovider
python -B -m ruff check src tests scripts
python -B scripts/check_contract_guardrails.py
python -B -O -m hsconfig.cli contract-spine-sentinel --json
python -B scripts/check_publishable_tree.py `
  --root . `
  --mode working-pre-cutover `
  --json
git diff --check
git status --short
```

Run the repository's existing optimized contract-spine sentinel once. Ask a
fresh independent spec reviewer to map every heading in the approved design to
implementation/tests, and a fresh quality/security reviewer to inspect:

- root/profile/run path races;
- profile-authorization lease linearizability through terminal acknowledgement;
- active package/runtime/session capability expiry and cross-context rejection;
- schema downgrade/mixing;
- frozen-input replay;
- candidate/review revision invalidation;
- fake-receipt authority isolation;
- invocation/session crash windows;
- runtime transaction-ID reuse;
- durable target ownership versus temporary attempt-retention fencing;
- every artifact-before-CAS and prepublication-cleanup crash boundary;
- pure-CAS terminal-classification selection, exact retained evidence, and the
  prohibition on no-commit after the intended final INI successor is visible;
- owner-retirement full inventory commitment, cursor-zero initialization,
  one-entry/one-cursor actions, target-root retirement, and terminal handoff;
- Candidate leaf content-authority exception, unsafe-file rejection, and full
  parity reread before rename/owner binding;
- one exact current Session cursor from recovery closure through atomic
  result-intent consumption, without duplicate phase CASes;
- publication/apply/match lock order;
- physical disposition classification;
- preview non-mutation;
- normal hash-free presentation.
- live-canary authorization evidence names the exact profile, runtime root,
  output-base root, ShadowPriest write, and mapping change; no other approval,
  enabled-profile state, silence, or inference is accepted as that authority.
- the complete outgoing commit stack, not only HEAD, has the approved signer.

No Critical, Important, or Minor finding may remain.

### Step 13.4: Commit final integration and coverage contracts

```powershell
git add -- `
  tests/test_codex_first_live_e2e.py `
  tests/starter_fixtures.py `
  scripts/run_coverage_gate.py `
  tests/test_coverage_contract.py `
  .github/workflows/ci.yml `
  tests/test_ci_workflow_contract.py
git diff --cached --check
git -c "user.signingkey=$ApprovedSigningSelector" commit -S -m "test: prove Codex first live start configuration"
git log -1 --show-signature --format=fuller
git status --short --branch
```

Require a clean worktree, empty index, good signature, and no untracked or
ignored task residue that was created by this implementation.

### Step 13.5: Push once and bind one exact-OID CI run

Refresh immediately before push:

```powershell
$ExpectedRepository = 'Teufelsboy/HSConfig'
$AllowedOriginUrls = @(
  'https://github.com/Teufelsboy/HSConfig.git',
  'git@github.com:Teufelsboy/HSConfig.git',
  'ssh://git@github.com/Teufelsboy/HSConfig.git'
)
$OriginFetchUrls = @(git remote get-url --all origin)
$OriginFetchUrlExit = $LASTEXITCODE
$OriginPushUrls = @(git remote get-url --push --all origin)
$OriginPushUrlExit = $LASTEXITCODE
if (
  $OriginFetchUrlExit -ne 0 -or
  $OriginPushUrlExit -ne 0 -or
  $OriginFetchUrls.Count -ne 1 -or
  $OriginPushUrls.Count -ne 1 -or
  $OriginFetchUrls[0] -cnotin $AllowedOriginUrls -or
  $OriginPushUrls[0] -cnotin $AllowedOriginUrls
) {
  throw 'origin is not exactly bound to Teufelsboy/HSConfig'
}
$Repository = (
  gh repo view $ExpectedRepository --json nameWithOwner `
    --jq '.nameWithOwner'
).Trim()
if ($LASTEXITCODE -ne 0 -or $Repository -cne $ExpectedRepository) {
  throw 'GitHub repository binding mismatch'
}
git fetch --all --prune --tags
git remote prune origin
git status --short --branch
git rev-list --left-right --count origin/main...HEAD
$RemoteTipOid = (git rev-parse 'origin/main^{commit}').Trim()
if ($LASTEXITCODE -ne 0) {
  throw 'failed to resolve fetched remote tip OID'
}
$HeadOid = (git rev-parse 'HEAD^{commit}').Trim()
if ($LASTEXITCODE -ne 0) {
  throw 'failed to resolve head OID'
}
$SigningBaselinePath = [Environment]::GetEnvironmentVariable(
  'HSCONFIG_SIGNING_BASELINE'
)
if (
  [string]::IsNullOrWhiteSpace($SigningBaselinePath) -or
  -not [IO.Path]::IsPathFullyQualified($SigningBaselinePath)
) {
  throw 'missing absolute external signing baseline path'
}
$RepoRoot = (Resolve-Path '.').Path
$env:PYTHONPATH = Join-Path $RepoRoot 'src'
$SigningBaselineValidator = @'
import json
import re
import sys
from hashlib import sha256
from pathlib import Path

from hsconfig.package_io import (
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
)

FIELDS = frozenset(
    {
        "schema_version",
        "base_oid",
        "design_oid",
        "plan_oid",
        "expected_outgoing_oids",
        "approved_signer_fingerprints",
        "content_sha256",
    }
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("signing_baseline_duplicate_key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"signing_baseline_non_finite:{value}")


def canonical(value):
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


path = Path(sys.argv[1])
head_oid = sys.argv[2]
repo_root = Path(sys.argv[3]).resolve(strict=True)
if not path.is_absolute():
    raise ValueError("signing_baseline_path_not_absolute")
resolved_parent = path.parent.resolve(strict=True)
try:
    resolved_parent.relative_to(repo_root)
except ValueError:
    pass
else:
    raise ValueError("signing_baseline_must_be_outside_repository")

guard = capture_plain_ancestor_guard(path)
status = plain_file_status(path)
parent_identity = path_identity(path.parent)
guard.validate()
require_no_alternate_data_streams(
    path,
    expected_identity=path_identity_from_status(status),
    expected_parent_identity=parent_identity,
    directory=False,
    expected_size=status.st_size,
)
raw = read_file_no_follow(
    path,
    expected_status=status,
    maximum_size=64 * 1024,
)
require_no_alternate_data_streams(
    path,
    expected_identity=path_identity_from_status(status),
    expected_parent_identity=parent_identity,
    directory=False,
    expected_size=status.st_size,
)
guard.validate()

if (
    not raw
    or raw.startswith(b"\xef\xbb\xbf")
    or b"\r" in raw
    or b"\x00" in raw
    or raw.endswith(b"\n")
):
    raise ValueError("signing_baseline_bytes_invalid")

document = json.loads(
    raw.decode("utf-8"),
    object_pairs_hook=unique_object,
    parse_constant=reject_constant,
)
if not isinstance(document, dict) or set(document) != FIELDS:
    raise ValueError("signing_baseline_fields_invalid")
if (
    type(document["schema_version"]) is not int
    or document["schema_version"] != 1
):
    raise ValueError("signing_baseline_schema_invalid")

oid_width = len(head_oid)
if oid_width not in {40, 64}:
    raise ValueError("signing_baseline_oid_width_invalid")
oid_pattern = re.compile(rf"[0-9a-f]{{{oid_width}}}\Z")


def require_oid(value):
    if not isinstance(value, str) or oid_pattern.fullmatch(value) is None:
        raise ValueError("signing_baseline_oid_invalid")
    return value


require_oid(head_oid)
base_oid = require_oid(document["base_oid"])
design_oid = require_oid(document["design_oid"])
plan_oid = require_oid(document["plan_oid"])

outgoing = document["expected_outgoing_oids"]
if (
    not isinstance(outgoing, list)
    or not 2 <= len(outgoing) <= 64
    or any(require_oid(value) != value for value in outgoing)
    or len(set(outgoing)) != len(outgoing)
    or outgoing[:2] != [design_oid, plan_oid]
    or base_oid in outgoing
):
    raise ValueError("signing_baseline_outgoing_stack_invalid")

fingerprints = document["approved_signer_fingerprints"]
if (
    not isinstance(fingerprints, list)
    or not 1 <= len(fingerprints) <= 8
    or any(
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or any(
            ord(character) < 0x21 or ord(character) > 0x7E
            for character in value
        )
        for value in fingerprints
    )
    or fingerprints != sorted(set(fingerprints))
):
    raise ValueError("signing_baseline_fingerprints_invalid")

unsigned = dict(document)
declared_digest = unsigned.pop("content_sha256")
expected_digest = "sha256:" + sha256(canonical(unsigned)).hexdigest()
if declared_digest != expected_digest:
    raise ValueError("signing_baseline_content_sha256_invalid")
if raw != canonical(document):
    raise ValueError("signing_baseline_not_canonical")

envelope = {
    "document": document,
    "file_identity": list(path_identity_from_status(status)),
    "file_sha256": "sha256:" + sha256(raw).hexdigest(),
}
sys.stdout.write(json.dumps(envelope, separators=(",", ":"), sort_keys=True))
'@

$SigningBaselineEnvelopeJson = & python -B -c `
  $SigningBaselineValidator `
  $SigningBaselinePath `
  $HeadOid `
  $RepoRoot
if (
  $LASTEXITCODE -ne 0 -or
  [string]::IsNullOrWhiteSpace($SigningBaselineEnvelopeJson)
) {
  throw 'external signing baseline validation failed'
}
$SigningBaselineEnvelope = $SigningBaselineEnvelopeJson |
  ConvertFrom-Json -Depth 6
$SigningBaseline = $SigningBaselineEnvelope.document
$LedgerBaseOid = [string]$SigningBaseline.base_oid
$OutgoingOids = @(git rev-list --reverse "$LedgerBaseOid..$HeadOid")
if ($LASTEXITCODE -ne 0) {
  throw 'failed to enumerate outgoing stack'
}
$ExpectedOids = @($SigningBaseline.expected_outgoing_oids)
$ApprovedFingerprints = @(
  $SigningBaseline.approved_signer_fingerprints
)
if (
  $OutgoingOids.Count -eq 0 -or
  ($OutgoingOids -join "`n") -cne ($ExpectedOids -join "`n")
) {
  throw 'outgoing stack differs from the complete approved outgoing ledger'
}
$IsInitialStackPush = $RemoteTipOid -ceq $LedgerBaseOid
$IsSingleFixPush = (
  $ExpectedOids.Count -ge 3 -and
  $RemoteTipOid -ceq $ExpectedOids[-2] -and
  $HeadOid -ceq $ExpectedOids[-1]
)
if (-not $IsInitialStackPush -and -not $IsSingleFixPush) {
  throw 'remote tip is neither immutable ledger base nor exact prior ledger head'
}
git merge-base --is-ancestor $RemoteTipOid $HeadOid
if ($LASTEXITCODE -ne 0) {
  throw 'audited head is not a fast-forward descendant of remote tip'
}
$SignedStack = foreach ($Oid in $OutgoingOids) {
  git verify-commit $Oid
  if ($LASTEXITCODE -ne 0) {
    throw "invalid or missing signature: $Oid"
  }
  $SignatureStatus = (git show --no-patch --format='%G?' $Oid).Trim()
  $SignerFingerprint = (git show --no-patch --format='%GF' $Oid).Trim()
  if (
    $LASTEXITCODE -ne 0 -or
    $SignatureStatus -cne 'G' -or
    $SignerFingerprint -cnotin $ApprovedFingerprints
  ) {
    throw "unapproved commit signature: $Oid"
  }
  [pscustomobject]@{
    oid = $Oid
    signature_status = $SignatureStatus
    signer_fingerprint = $SignerFingerprint
  }
}
if ($HeadOid -cne $OutgoingOids[-1]) {
  throw 'signed-stack head mismatch'
}
$RunsUri = (
  "repos/$Repository/actions/workflows/ci.yml/runs" +
  "?event=push&branch=main&head_sha=$HeadOid&per_page=100"
)
function Get-BoundPushRuns {
  $EnvelopeJson = gh api -H 'Accept: application/vnd.github+json' $RunsUri
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($EnvelopeJson)) {
    throw 'failed to read exact-OID CI run inventory'
  }
  $Envelope = $EnvelopeJson | ConvertFrom-Json -Depth 20
  if ($Envelope.total_count -gt 100) {
    throw 'exact-OID CI run inventory exceeds its bound'
  }
  $Runs = @($Envelope.workflow_runs)
  if ([int]$Envelope.total_count -ne $Runs.Count) {
    throw 'exact-OID CI run inventory is truncated or inconsistent'
  }
  foreach ($CandidateRun in $Runs) {
    if (
      $CandidateRun.path -cne '.github/workflows/ci.yml' -or
      $CandidateRun.event -cne 'push' -or
      $CandidateRun.head_branch -cne 'main' -or
      $CandidateRun.head_sha -cne $HeadOid
    ) {
      throw 'exact-OID CI inventory returned an out-of-contract run'
    }
  }
  @($Runs)
}
$PrePushRuns = @(Get-BoundPushRuns)
if ($PrePushRuns.Count -ne 0) {
  throw 'audited head already has a push run or rerun before this push'
}
[pscustomobject]@{
  signing_baseline_identity = @($SigningBaselineEnvelope.file_identity)
  signing_baseline_sha256 = $SigningBaselineEnvelope.file_sha256
  base_oid = $LedgerBaseOid
  remote_tip_oid = $RemoteTipOid
  design_oid = $SigningBaseline.design_oid
  plan_oid = $SigningBaseline.plan_oid
  head_oid = $HeadOid
  signed_stack = @($SignedStack)
} | ConvertTo-Json -Depth 5
$PushResult = @(git -c push.followTags=false push `
  --no-follow-tags `
  --recurse-submodules=no `
  --porcelain `
  --force-with-lease="refs/heads/main:$RemoteTipOid" `
  origin `
  "$HeadOid`:refs/heads/main")
if ($LASTEXITCODE -ne 0) {
  throw 'exact-OID push failed'
}
$RefStatusLines = @(
  $PushResult | Where-Object {
    $_ -match "^[ =*!+\-]`t[^`t]+:[^`t]+`t"
  }
)
if ($RefStatusLines.Count -ne 1) {
  throw 'push produced zero or multiple ref updates'
}
$RefFields = @($RefStatusLines[0] -split "`t", 3)
if ($RefFields.Count -ne 3) {
  throw 'push emitted a malformed porcelain ref status'
}
$RefPair = @($RefFields[1] -split ':', 2)
if (
  $RefFields[0] -cne ' ' -or
  $RefPair.Count -ne 2 -or
  $RefPair[1] -cne 'refs/heads/main'
) {
  throw 'push did not perform exactly one new fast-forward main-only update'
}
$RemoteMain = @(git ls-remote --exit-code origin refs/heads/main)
if (
  $LASTEXITCODE -ne 0 -or
  $RemoteMain.Count -ne 1 -or
  (($RemoteMain[0] -split "`t")[0]).Trim() -cne $HeadOid
) {
  throw 'remote main does not equal audited head OID'
}

$MatchingRuns = @()
for ($Poll = 0; $Poll -lt 30; $Poll++) {
  $MatchingRuns = @(Get-BoundPushRuns)
  if ($MatchingRuns.Count -gt 1) {
    throw 'exact-OID CI run inventory is ambiguous'
  }
  if ($MatchingRuns.Count -eq 1) {
    if ($MatchingRuns[0].run_attempt -ne 1) {
      throw 'exact-OID CI authority is a rerun rather than first attempt'
    }
    break
  }
  Start-Sleep -Seconds 10
}
if ($MatchingRuns.Count -ne 1) {
  throw 'exactly one first-attempt exact-OID ci.yml push run is required'
}
$RunId = [long]$MatchingRuns[0].id
gh run watch $RunId --repo $Repository --exit-status
if ($LASTEXITCODE -ne 0) {
  throw 'exact-OID CI run failed'
}
$Run = gh api -H 'Accept: application/vnd.github+json' `
  "repos/$Repository/actions/runs/$RunId" |
  ConvertFrom-Json -Depth 20
if (
  $Run.status -cne 'completed' -or
  $Run.conclusion -cne 'success' -or
  $Run.run_attempt -ne 1 -or
  $Run.event -cne 'push' -or
  $Run.head_branch -cne 'main' -or
  $Run.head_sha -cne $HeadOid -or
  $Run.path -cne '.github/workflows/ci.yml'
) {
  throw 'terminal exact-OID CI metadata mismatch'
}
$JobsEnvelope = gh api -H 'Accept: application/vnd.github+json' `
  "repos/$Repository/actions/runs/$RunId/jobs?filter=latest&per_page=100" |
  ConvertFrom-Json -Depth 30
if ($JobsEnvelope.total_count -gt 100) {
  throw 'CI job inventory exceeds bound'
}
$Jobs = @($JobsEnvelope.jobs)
$RequiredJobs = @('contract', 'test', 'package', 'security')
$ObservedJobNames = @($Jobs.name | Sort-Object)
$ExpectedJobNames = @($RequiredJobs | Sort-Object)
if (($ObservedJobNames -join "`n") -cne ($ExpectedJobNames -join "`n")) {
  throw 'CI job inventory mismatch'
}
foreach ($JobName in $RequiredJobs) {
  $Job = @($Jobs | Where-Object { $_.name -ceq $JobName })
  if ($Job.Count -ne 1 -or $Job[0].conclusion -cne 'success') {
    throw "CI job did not succeed: $JobName"
  }
  $Residue = @(
    $Job[0].steps | Where-Object {
      $_.name -ceq 'Verify checkout residue is zero'
    }
  )
  if ($Residue.Count -ne 1 -or $Residue[0].conclusion -cne 'success') {
    throw "checkout residue gate did not succeed: $JobName"
  }
}
$CoverageStep = @(
  ($Jobs | Where-Object { $_.name -ceq 'test' }).steps |
    Where-Object {
      $_.name -ceq 'Run full locked tests and full-source coverage'
    }
)
if ($CoverageStep.Count -ne 1 -or $CoverageStep[0].conclusion -cne 'success') {
  throw 'full tests and enforced coverage/critical-module gate did not succeed'
}
$PackageJob = @($Jobs | Where-Object { $_.name -ceq 'package' })
if (
  $PackageJob.Count -ne 1 -or
  @($PackageJob[0].labels) -cnotcontains 'ubuntu-latest'
) {
  throw 'POSIX crash boundary did not run on the bound Ubuntu package job'
}
$PosixNoReplaceStep = @(
  $PackageJob[0].steps |
    Where-Object {
      $_.name -ceq 'Verify POSIX bound no-replace crash boundary'
    }
)
if (
  $PosixNoReplaceStep.Count -ne 1 -or
  $PosixNoReplaceStep[0].conclusion -cne 'success'
) {
  throw 'Ubuntu POSIX bound no-replace crash boundary did not succeed'
}
$FinalRemoteMain = @(git ls-remote --exit-code origin refs/heads/main)
if (
  $LASTEXITCODE -ne 0 -or
  $FinalRemoteMain.Count -ne 1 -or
  (($FinalRemoteMain[0] -split "`t")[0]).Trim() -cne $HeadOid
) {
  throw 'terminal remote main no longer equals audited head OID'
}
$FinalMatchingRuns = @(Get-BoundPushRuns)
if ($FinalMatchingRuns.Count -ne 1) {
  throw 'terminal exact-OID CI run inventory is not unique'
}
$FinalRun = $FinalMatchingRuns[0]
if (
  [long]$FinalRun.id -ne $RunId -or
  $FinalRun.status -cne 'completed' -or
  $FinalRun.conclusion -cne 'success' -or
  $FinalRun.run_attempt -ne 1 -or
  $FinalRun.event -cne 'push' -or
  $FinalRun.head_branch -cne 'main' -or
  $FinalRun.head_sha -cne $HeadOid -or
  $FinalRun.path -cne '.github/workflows/ci.yml'
) {
  throw 'terminal exact-one CI authority changed during watch'
}
[pscustomobject]@{
  base_oid = $LedgerBaseOid
  head_oid = $HeadOid
  run_id = $RunId
  run_attempt = $FinalRun.run_attempt
  event = $FinalRun.event
  workflow_path = $FinalRun.path
  jobs = @($RequiredJobs)
  residue_steps = 4
  coverage_and_critical_modules_enforced = $true
  posix_bound_no_replace_crash_boundary_enforced = $true
  posix_runner_label = 'ubuntu-latest'
} | ConvertTo-Json -Depth 5
```

Keep three OIDs distinct: immutable `LedgerBaseOid` from the external baseline,
fresh fetched `RemoteTipOid`, and audited `HeadOid`. The complete signature and
ordered-ledger check always enumerates `LedgerBaseOid..HeadOid`. On the initial
stack push, remote tip must equal the immutable ledger base. On each later
focused-fix push, remote tip must equal the penultimate ledger entry and head
must equal the one newly appended last entry; both require an explicit
fast-forward ancestor check. Require the left/right count before each push to
show only that audited signed suffix ahead. The explicit `--force-with-lease`
is solely the server-side expected-old compare-and-swap; it grants no
non-fast-forward or history-rewrite authority, and the prior ancestor check
remains mandatory. Any remote-tip change fails the push. A porcelain `=` or
up-to-date result is not this run's push authority; require one actual
fast-forward update. Fetch URL, push URL, `gh repo view`, every API request, and
the watch are all bound to exact `Teufelsboy/HSConfig`. Record the pushed exact
OID. Disable configured and command-line follow-tags, prohibit submodule pushes,
and reject every porcelain ref-status inventory except exactly one fast-forward
`HeadOid:refs/heads/main` row. No tag or second ref may be published. Monitor
exactly one
first-attempt run with workflow `.github/workflows/ci.yml`, event `push`, branch
`main`, and `head_sha` equal to that OID.
Do not start a second local full test or a blind CI rerun.

A `workflow_dispatch`, rerun attempt, other branch/SHA, or multiple matching
push runs is not authority and stops investigation before skill,
profile, runtime, canary, or GitHub mutation. After every focused signed fix
commit, atomically append only its exact OID to `expected_outgoing_oids`,
recompute the external baseline self-digest, freeze and revalidate that file,
and rerun the complete immutable-base stack-signature gate before the next one
exact fix push. Earlier
ledger entries and the approved fingerprint set may not change.

The run inventory must be empty immediately before the local push. After the
watch and all job, residue, and coverage checks, reread remote main and the same
bounded run inventory. Acceptance requires remote main still equal to the
audited OID and exactly the original run ID as the sole matching run, then
separately requires that row to remain attempt 1. Filtering out later attempts
before the zero/one cardinality check is forbidden.

Acceptance requires:

- workflow path `.github/workflows/ci.yml`, event `push`, branch `main`, exact
  pushed head SHA, and attempt 1;
- `contract=success`;
- `test=success`;
- `package=success`;
- `security=success`;
- all four checkout-residue steps successful;
- the Ubuntu `package` step `Verify POSIX bound no-replace crash boundary`
  exists exactly once and succeeded;
- coverage gate passed at or above the repository minimum;
- every critical module at 100% statements and branches;
- no scanner, mutation, package, or canonical-output failure.

If CI fails deterministically, diagnose only the exact failures, add focused
RED/GREEN cases, create the smallest new signed fix commit on top, fast-forward
push once, and bind exactly one run for the new OID. Never amend a pushed
commit, force-push, or rerun the same OID. Do not repeat already green local
groups. The last fully green descendant OID is the sole integrated authority;
earlier failed OIDs remain immutable evidence.

### Step 13.6: Install the exact embedded skill after green CI

From the exact green checkout, install the bundle with the existing CAS API:

```powershell
$SkillRoot = Join-Path $env:USERPROFILE '.codex\skills\hsconfig'
$env:PYTHONPATH = Join-Path (Resolve-Path '.').Path 'src'
$InstallScript = "from pathlib import Path;" +
  "from hsconfig.external_skill_bundle import external_skill_tree_identity,install_external_skill;" +
  "p=Path.home()/'.codex'/'skills'/'hsconfig';" +
  "before=external_skill_tree_identity(p);" +
  "expected=before.get('aggregate_sha256') if before.get('present') else None;" +
  "print(install_external_skill(p,expected_predecessor_aggregate_sha256=expected));" +
  "print(external_skill_tree_identity(p))"
python -B -c $InstallScript
```

Require nine files, two directories, the exact committed logical bundle
aggregate, exact SKILL digest, and no installer staging/backup/journal residue.

### Step 13.7: Obtain exact live-canary authorization, then bind the profile and run one real canary

Resolve environment-derived paths read-only so no user-specific absolute path
enters tracked documentation. The mutating command shown next is gated by the
authorization paragraphs immediately below it and must not execute before that
gate succeeds:

```powershell
$RuntimeRoot = Join-Path $env:USERPROFILE 'Desktop\HS'
$OutputBaseRoot = Join-Path (Resolve-Path '.').Path 'outputs'
$env:PYTHONPATH = Join-Path (Resolve-Path '.').Path 'src'
# Run only when the read-only probe proved the profile is absent.
python -B -m hsconfig.cli live-policy enable `
  --runtime-root $RuntimeRoot `
  --output-base-root $OutputBaseRoot `
  --expected-absent `
  --json
```

Before any mutation, resolve `operator_profile_path()`, `$RuntimeRoot`, and
`$OutputBaseRoot`, capture their canonical paths and identities, and inspect the
profile read-only. Design/plan/repository/CI/skill-install approval, silence, or
an enabled profile is not execution permission for this real-runtime canary.

Proceed only when the conversation contains a fresh execution-time
authorization, or an exact previously recorded message still applicable to the
current paths and identities, that explicitly permits all of:

- creating and enabling the exact operator profile when absent;
- binding it to the exact runtime and output-base roots;
- one real ShadowPriest live canary through the installed route;
- creating or replacing its runtime package and changing the active
  `CustomConfig/deck_config.ini` mapping with normal journal/state/receipt/match
  operations.

Record the message reference, exact paths, identities, and authorized effects
outside the repository without copying unnecessary conversation content or
secrets. Do not infer, broaden, or reconstruct consent. If it is absent, stop
before `live-policy enable` and before the live skill route, record
`LIVE_CANARY=NOT_RUN_AUTHORIZATION_REQUIRED`, and do not claim full acceptance.
This is an acceptance-time authority gate, not a new per-run product prompt.

If the profile is absent and authorization permits creation, record that
precondition and use `--expected-absent`. If present, load and revalidate exact
bytes, digest, live flag, roots, and identities; proceed without rewriting only
when it is already enabled and exactly matches both roots. Any disabled,
different, malformed, drifted, or concurrently changed predecessor is a stop
condition. Even a valid enabled profile does not by itself authorize the named
canary mutation.

Before all profile/canary commands, require `hsconfig.__file__` to resolve under the exact
green checkout's `src` directory; do not install or enable from an older
site-packages copy.

Verify the profile once, then use the newly installed skill with this exact
normal input:

```text
Erstelle die bestmögliche Startconfig.

Deckname: ShadowPriest
Deckcode: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
```

Codex must use one lead strategist and one independent reviewer through the
installed helper phases. Do not add another candidate tournament, a second
source fetch, or a per-run apply confirmation. If the resolved optional IDs
are present, require HSid `2737726722` and HDT deck ID
`c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602` to match; otherwise do not fabricate
them.

Require terminal status `LIVE_AND_MATCHED`, exact current publication binding,
allowed apply facts, exact receipt/state/INI parity, runtime match for the same
package, full unique-card disposition coverage, approved `high|limited` review,
no incomplete own session, publisher, or runtime transaction, and exact absence
of the fixed admission after its bound successful acknowledgement. A valid
`ALREADY_LIVE` result remains an honest idempotence result but does not satisfy
this design's real-canary acceptance; preserve it and stop without mutating the
real runtime merely to force a non-idempotent result. Do not interpret either
status as gameplay or win-rate proof.

### Step 13.8: Apply and verify only the approved GitHub polish

After green CI and the live canary:

```powershell
python -B scripts/github_governance.py `
  product-polish `
  --repo Teufelsboy/HSConfig `
  --json
python -B scripts/github_governance.py `
  verify-product-polish `
  --repo Teufelsboy/HSConfig `
  --json
```

Read back description and topics. Also verify that repository visibility,
ruleset, branch inventory, Actions restrictions, security features, tags,
release, assets, and open pull requests are unchanged. Do not run the historic
root cutover, move `v1.0.0`, create another release, or create a website.

### Step 13.9: Record the final acceptance receipt

Record, outside the tracked repository:

- external signing-baseline canonical-byte digest and file identity, fetched
  base OID, design and plan OIDs, and the complete ordered outgoing commit OIDs
  with signature status and approved signer fingerprint for every commit;
- pushed head OID plus CI workflow path, run ID, attempt, event, branch,
  head SHA, URL, and four job conclusions;
- exact coverage-checker `passed`, covered/total/global percentage/minimum,
  every critical-module statement/branch result, all four residue results, and
  the successful named Ubuntu POSIX bound-no-replace crash step;
- installed skill predecessor/successor identities and logical aggregate;
- operator-profile digest and root identities;
- exact live-canary authorization message reference, authorized profile path,
  runtime/output paths and identities, named ShadowPriest write, and mapping
  effect; or `LIVE_CANARY=NOT_RUN_AUTHORIZATION_REQUIRED` when absent;
- run ID and frozen snapshot digest;
- candidate revision/digest and review digest/confidence;
- publication revision and content root;
- apply attempt/transaction ID, runtime-admission parent/file identities and
  digest plus its
  output/profile/runtime bindings, release/retention outcome, final physical
  presence/absence, terminal-retirement operation/stage, any owner-retirement
  tombstone, and physical disposition;
- final runtime-match digest and user-facing status;
- GitHub description/topic readback;
- explicit `GAMEPLAY=OUT_OF_SCOPE_ASSUMED_EXTERNAL`.

The final user response remains concise and human-facing. It shows the deck
name without a SHA suffix, card coverage, review confidence, and one of the six
closed statuses. Technical hashes appear only under optional technical
details.

---

## Requirements-to-Task Traceability

| Approved requirement | Implemented and proven in |
| --- | --- |
| One-time positive live authorization and preview override | Tasks 1, 8, 11, 13 |
| Profile authorization stays linearizable through every write | Tasks 1, 8, 10, 11, 13 |
| Only deck name and deck code on normal runs | Tasks 2, 11, 12, 13 |
| Any fully resolvable supported deck | Tasks 2, 4, 11, 13 |
| Six exact frozen blobs and three physical envelopes | Tasks 2, 3, 11 |
| External closed resumable run state | Tasks 3, 9, 11 |
| One lead candidate and one independent review | Tasks 4, 5, 11 |
| Shared maximum of two targeted revisions | Tasks 3, 4, 11 |
| Legacy five-doc compatibility and new schema-4 authority | Tasks 5, 6, 7 |
| No conservative reconstruction on new compile path | Task 6 |
| Exact four durable optimized authority reports | Tasks 5, 6, 7 |
| Strict validation, receipt, summary, and apply-gate parity | Task 7 |
| Write-free fake apply before publication | Task 8 |
| Preview publishes without runtime artifacts | Tasks 8, 11, 13 |
| Durable output-operation admission fences publication, profile, and generic Runtime mutation from first claim through gap-free runtime or terminal handoff | Tasks 1, 3, 8, 9, 10, 11, 13 |
| Controller pair entry is bound to Session/Profile/output-operation/Package authority and all installers use one acyclic lock order | Tasks 8, 9, 10, 13 |
| Durable admission, then invocation receipt, before `APPLY_STARTED` | Tasks 9, 10, 11, 13 |
| Invocation receipt actions run only through the outer-capability Task-10 adapter before the I/O-free `APPLY_STARTED` CAS | Tasks 3, 9, 10, 13 |
| Fresh runtime layout is bound one directory per receipt/CAS before invocation receipt | Tasks 3, 9, 10, 13 |
| Intent-first artifact transitions and cleanup before terminal/apply | Tasks 3, 8, 9, 11 |
| Recovery-only after receipt or apply start, with every initial/selection observation bound by one opaque same-pair receipt | Tasks 3, 9, 10, 11, 13 |
| Post-handoff runtime admission fences runtime, publication, and profile mutation across crashes | Tasks 9, 10, 11, 13 |
| Post-terminal retirement is intent-first and crash-resumable | Tasks 3, 9, 10, 11, 13 |
| One publication lease through apply and runtime match | Task 10 |
| Target-owner journal survives temporary attempt acknowledgement | Tasks 3, 9, 10, 11, 13 |
| Later owner cleanup uses full inventory, cursor-zero initialization, a prebound COMPLETED commitment, target-root retirement, and preserved evidence | Tasks 3, 9, 10, 11, 13 |
| Candidate leaves use narrow safe content authority and are fully reverified before owner binding | Tasks 3, 9, 10, 13 |
| One exact current session cursor with explicit `ACTIVE -> CLOSED` recovery before result-intent binding | Tasks 3, 10, 11, 13 |
| Closed physical and user status classifications | Tasks 3, 9, 10, 11, 13 |
| No hashes in normal deck presentation | Tasks 1, 12, 13 |
| Installed skill and repository agree | Tasks 11, 12, 13 |
| Minimal GitHub polish only | Tasks 12, 13 |
| Focused tests, one exact CI, one live canary | Task 13 |
| Audited exact OID is the only pushed ref and the only accepted first-attempt CI run | Task 13 |
| No gameplay-optimality claim or HSTuner expansion | Global constraints, Tasks 12 and 13 |

## Final Stop Conditions

Stop implementation and preserve state rather than improvising when any of
these occurs:

- upstream is not the expected clean ancestor;
- an existing profile, run, output, publication, package, runtime root,
  journal, state, or receipt fails identity or canonical-byte validation;
- a new route requires fresh input after the snapshot is sealed;
- candidate/review revision budget is exhausted;
- authority schema is missing, mixed, unknown, or downgraded;
- fake apply, strict validation, derivation, operator parity, or profile/output
  rebinding fails before publication;
- publication current pointer changes before apply;
- the fixed output-operation admission is malformed, unsafe, replaced, or not
  exactly reconcilable with its session/profile/output binding;
- an `ACTIVE` output-operation binding lacks its exact physical record, or an
  owning publisher has no active exact `LiveStartSessionLease`;
- a generic Runtime install or recovery can create `runtime_root`, `.hsconfig`,
  or `apply.lock`, or acquire its Package/Runtime mutation locks, before the
  fixed output-operation gate; the public Legacy installer can create an absent
  runtime root before its Package/apply and fixed Runtime-admission gates, or
  anything except that narrow unpaired path can create/rebind an absent root; an
  installer can acquire `package -> output-operation` or `runtime -> package`,
  recovery can acquire `runtime -> output-operation`, or either can use ordinary
  Evidence as a same-attempt bypass;
- a controller pair can bootstrap or acquire the Runtime lock without active
  exact Session/Profile/output-operation/Package capabilities and an allowed
  persisted session row, or cannot re-enter from the exact post-handoff session
  and Runtime admission after the historical output record was legitimately
  removed;
- an invocation-receipt observer or mutator can run outside the Task-10 context
  adapter, before its action bearer is consumed, or after any outer capability
  or either final admission record fails revalidation;
- output-operation release is requested before either the exact runtime
  admission is durably bound in `APPLY_STARTED` or a no-runtime terminal cursor
  is durable;
- neither the output-operation nor runtime admission is exact at any live
  handoff boundary, or a release cursor sees a same-run/same-byte replacement;
- invocation receipt or `APPLY_STARTED` exists and exact same-attempt recovery
  cannot produce one closed physical disposition;
- a runtime-wide live-attempt admission exists for another run/attempt, is
  malformed, replaced, or cannot be reconciled with its exact owning session;
- admission staging/final bytes are partial, mixed, replace an existing winner,
  or do not match the PREPARED no-replace publication intent;
- a runtime-layout row is out of order, its parent/identity changed, or an
  authority file is observed before all required parents are durably bound;
- the persisted normal-install action lacks exactly one table successor, or a
  candidate copy, verification, rename, INI, journal, or fence step would need
  to advance two physical rows under one authorization;
- an unfinished physical action can neither resume its exact predecessor or
  idempotent postcondition nor take exactly one authorized, I/O-free
  `select_terminal_classification` CAS into one closed observation;
- a first-install, nonterminal, terminal-resolution, or terminal-classification
  Session CAS lacks one exact unconsumed same-pair observation receipt, or an
  ordinary Evidence/selection value would become mutation authority;
- `observe_not_committed` could be selected after the intended final INI
  successor is visible, or selection would change any physical evidence other
  than action index, expected action, and required self-digests;
- a Candidate leaf is unsafe or content-/source-/root-/parent-inexact, or full
  manifest parity is not revalidated immediately before rename and owner bind;
- an owner-retirement full inventory commitment, cursor-zero initialization,
  cleanup entry, old-v1 cursor, planned COMPLETED-tombstone size/digest,
  target-root retirement, successor owner,
  terminal handoff, or final owner-unlink state is missing, replaced, skipped,
  or cannot advance by exactly one persisted receipt/CAS row;
- the held normal or recovered cursor is not the exact post-recovery-closure
  Session successor, or result-intent binding would repeat a phase CAS instead
  of atomically consuming that closed recovery object;
- recovery closure would be a byte-identical no-op, would not CAS
  `recovery_stage=ACTIVE -> CLOSED`, or result intent could consume `ACTIVE`;
- a pending artifact transition or prepublication cleanup cannot be completed
  from its exact bound predecessor/successor evidence;
- a runtime journal cannot be bound to the exact attempt ID;
- controller attempt evidence lacks its exact retention fence or durable target
  owner;
- terminal evidence/admission is absent without an exact durable
  `terminal_retirement` cursor, or later cleanup would touch fenced evidence;
- runtime commit succeeds but final match fails;
- exact-OID CI is not fully green;
- any outgoing commit lacks the approved signer or ordered task-ledger binding;
- installed skill bytes differ from the exact green commit;
- no exact execution authorization exists for the resolved profile creation or
  enablement and named ShadowPriest runtime/package/mapping mutation;
- the real canary would require deleting or adopting unrelated runtime
  evidence;
- GitHub polish would mutate anything beyond description and topics.
