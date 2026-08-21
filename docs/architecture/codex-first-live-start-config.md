# Codex-First Live Start Configuration

Status: chat-approved design, written specification awaiting user review
Date: 2026-08-21

[Back to the architecture overview](overview.md)

## Purpose

HSConfig should provide one normal product experience:

> Give Codex a deck name and deck code. The installed HSConfig skill creates
> the best practical evidence-based start configuration, writes it to the
> configured HearthRanger runtime, and verifies the active files.

The user supplies only the deck name and deck code during a normal run. Codex
owns LLM orchestration. HSConfig remains the deterministic authority for deck
identity, document validation, package compilation, publication, guarded
runtime apply, recovery, and runtime matching.

This design replaces the normal three-candidate tournament with one directly
generated candidate plus independent review. It does not add a model client,
provider configuration, API-key handling, a GUI, or post-game tuning.

## Product contract

The normal prompt is intentionally small:

```text
Erstelle die bestmögliche Startconfig.

Deckname: ShadowPriest
Deckcode: AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=
```

The user explicitly enables `live_by_default=true` once in the local HSConfig
operator profile and binds the intended runtime root and output-base root. That
profile is the positive write authorization; the absence of an opt-out phrase
is not authorization by itself. Once enabled, a valid normal invocation needs
no second apply confirmation. An absent, invalid, changed, ambiguous, or
identity-mismatched profile stops with `PROFILE_REQUIRED` before LLM,
publication, or runtime mutation. Explicit preview intent, including `nur
prüfen` or `nicht live schreiben`, always overrides live authorization while
retaining the bound roots needed to build and publish a package.

The normal successful response is also small:

```text
ShadowPriest wurde live erstellt und geprüft.
Kartenabdeckung: vollständig
Review: high
Runtime: LIVE_AND_MATCHED
```

An approved `limited` review replaces `high` on that line and adds one short,
visible limitation. It is never presented as high confidence.

Hashes, content-addressed revision names, receipts, and physical runtime
version directories appear only in technical details or failure diagnostics.

## Product boundary

The product claim is **best practical evidence-based start configuration**.
It is not measured gameplay optimality, a win-rate guarantee, replay analysis,
runtime-log analysis, or post-game tuning. HSConfig remains pre-run only and
stays separate from HSTuner.

The following existing authority boundaries remain unchanged:

- LLM-produced documents are untrusted until HSConfig validates and seals
  them.
- `reports/operator_summary.json` is the sole normal human-facing apply
  authority.
- The apply command recomputes all technical authority before writing.
- Source quality remains visible but does not create a second apply gate for
  the optimized route.
- `runtime-match` proves installation integrity for an exact package. It does
  not prove gameplay quality.

## Component ownership

### Codex and the installed skill

Codex owns:

- interpretation of the one-prompt invocation;
- creation and resumption of the external run directory;
- dispatch of the lead strategist and independent reviewer;
- delivery of exact validation findings to the strategist;
- at most two targeted candidate revisions;
- progress and final user communication;
- evaluation of explicit write-free intent against the local live policy.

The installed skill contains the orchestration instructions and thin helper
entry points. It does not contain credentials and does not call a model API.

### HSConfig repository code

HSConfig owns:

- deck-code decoding and exact identity resolution;
- card, source, date, and GlobalValues snapshot validation;
- starter-context, candidate, and review schemas;
- canonical sealing and digest binding;
- candidate and review validation;
- deterministic lowering to supported runtime surfaces;
- strict package validation and derivation receipts;
- output publication;
- fake apply, guarded apply, recovery, and runtime match;
- validation and run-time rebinding of the explicitly enabled local operator
  profile.

The session record is workflow state only. It is never apply authority.

## One-time local live policy

The positive authorization is a canonical local profile outside the repository,
runtime, outputs, and installed skill:

```text
%LOCALAPPDATA%\HSConfig\operator-profile.json
```

An explicit one-time operator action enables it for one exact runtime and
output-base pair. The planned interface is:

```text
hsconfig live-policy enable --runtime-root <path> --output-base-root <path>
```

The profile is canonical JSON with exactly:

```text
schema_version
live_by_default
runtime_root
runtime_root_identity
output_base_root
output_base_root_identity
content_sha256
```

`schema_version` is 1, `live_by_default` is a JSON boolean, root identities use
the existing closed `PathIdentity` contract, and `content_sha256` is the
standard self-digest. Enablement rejects missing, overlapping, reparse-based,
or unsafe roots. A normal run reads the canonical bytes, verifies the
self-digest, reopens both roots, and never rewrites the profile. Only
`live-policy enable` or `live-policy disable` may change it. Disable preserves
the bound roots and sets `live_by_default=false`, producing preview runs; a
missing profile stops with `PROFILE_REQUIRED`. Installing or updating the skill
does not silently create write authorization.

The output-base root is a shared publication namespace. For each run HSConfig
derives one filesystem-safe child name from the deck display name, binds the
base identity and the child's existing identity or expected absence, and uses
guarded child creation when needed. A profile therefore works for every fully
resolvable deck without pre-registering deck-specific output paths.

## Input and identity contract

The required invocation fields are:

- `deck_name`;
- `deck_code`.

Optional Hearthstone and HDT identifiers may be recorded when they are known
and consistent. They are identity metadata only and never strategy, replay, or
gameplay evidence.

Before an LLM receives the deck, HSConfig must:

1. decode the complete deck code;
2. resolve the hero, main-deck cards, sideboard cards, sideboard owners, and
   linked runtime owners to real CardIDs;
3. reject unresolved, duplicated identity records, identity collisions,
   ambiguous identities, or contradictory identities while preserving legal
   repeated card counts;
4. validate the decoded roster and supported deck structure without assuming
   that every valid deck has exactly 30 cards;
5. bind the display name separately from the deck-code hash, roster
   fingerprint, runtime deck name, and filesystem-safe internal slug.

The visible display name remains the user's deck name. Internal fingerprints
disambiguate same-name deck codes without adding hashes to the normal user
experience.

The normal path does not require an audited deck-catalog entry, a fixed
proof-deck set, or a pre-registered source candidate. Those remain regression
and evidence fixtures only; any fully resolvable supported deck can use the
normal path.

## Frozen input snapshot

Every run freezes its inputs once before candidate generation. The snapshot
binds:

- original and normalized deck identity;
- the decoded roster and counts;
- the exact card-data bytes and digest;
- the exact source-acquisition result and source-document digests;
- the bound current date;
- the complete starting GlobalValues baseline and digest;
- optional external deck identifiers;
- the runtime root, output-base root, and derived deck-output precondition
  selected by the installed local profile.

HSConfig writes a sealed `input_snapshot_manifest.json` before LLM work. It
binds the canonical deck and roster, the exact input-blob digests, the bounded
deck-relevant card and source projections, date, GlobalValues baseline,
operator-profile digest, resolved root identities, runtime grammar version,
and compiler contract ID.

The manifest is canonical UTF-8 JSON with LF, no BOM, duplicate keys, unknown
fields, or non-finite values, and a maximum size of 256 KiB. It has exactly:

```text
schema_version
compiler_inputs
operator_bindings
content_sha256
```

`schema_version` is 1. `content_sha256` is the standard lowercase
`sha256:<64-hex>` self-digest over the canonical document with that field
excluded. `compiler_inputs` has exactly:

```text
deck_code_sha256
roster_fingerprint
bound_date
blobs
runtime_grammar_version
compiler_contract_id
```

The first two values use the same digest grammar, the date is strict
`YYYY-MM-DD`, and both version identifiers are 1 to 128 printable ASCII
identifier characters. `blobs` is a canonical list with exactly one row for
each of `deck`, `full_cards`, `collectible_cards`, `source_acquisition`,
`source_documents`, and `globalvalues_baseline`. Each row has exactly `name`,
`sha256`, `size_bytes`, and `record_count`; sizes are integers from 1 through
134,217,728 bytes and counts are integers from 0 through 1,000,000. Booleans
are never accepted as integers.

`operator_bindings` has exactly:

```text
operator_profile_sha256
runtime_root
runtime_root_identity
output_base_root
output_base_root_identity
deck_output_name
deck_output_precondition
```

Paths are canonical absolute strings accepted by the existing path guards;
root identities use the existing closed `PathIdentity` JSON contract.
`deck_output_name` is one validated filesystem component.
`deck_output_precondition` has exactly `state` and `identity`: `state` is
`absent` with a null identity or `existing` with the captured child identity.
Operator bindings authorize locations only and never influence strategic
generation or deterministic lowering.

All later phases use these exact bytes. The single-candidate compile entry
accepts only the sealed snapshot manifest, its bound blobs, and the sealed
starter documents. Fetch, `latest`, a fresh runtime-baseline read, or an
independent source reconstruction is unreachable on this path. Every
output-affecting snapshot projection is carried into the package and bound by
the derivation receipt. Resume must not repeat successful network acquisition
and must stop when the compiler contract or runtime grammar has changed.

Missing or weak sources remain an explicit informational limitation on the
optimized route. They do not justify invented runtime rules. An unresolved
CardID, unsafe deck structure, or ambiguous owner relationship blocks the run
before candidate generation or live apply.

## External run directory and resume

The controller creates one run directory outside the repository, outputs,
runtime, and installed skill:

```text
%LOCALAPPDATA%\HSConfig\runs\<run-id>\
```

Its closed logical contents are:

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
result/summary.json
result/summary.md
```

Each allowed revision replaces the working candidate. The final sealed
candidate is the only candidate artifact and the only package input; rejected
drafts do not become durable workflow authority.

The session phases are:

```text
INPUT_FROZEN
CANDIDATE_DRAFTED
CANDIDATE_VALIDATED
REVIEW_APPROVED
PACKAGE_VALIDATED
PREPUBLICATION_CHECK_PASSED
PUBLICATION_COMMITTED
APPLY_STARTED
APPLY_COMMITTED
RUNTIME_MATCHED
```

Resume first validates every completed phase against its bound bytes and
digests. It continues at the first incomplete phase. Changed deck identity,
changed frozen inputs, or a mismatched artifact starts a new run or fails
closed; it never silently reuses incompatible work. Candidate revision
invalidates every older candidate-validation and review receipt. Each revised
candidate is resealed, revalidated, and independently reviewed. Review approval
binds the context digest, candidate digest, and candidate revision.

Publication state binds the exact revision path, publication content digest,
and prior-current identity. If another run advances the normal pointer before
this run applies, the older run stops with a publication conflict instead of
republishing or applying stale work.

Immediately before entering the composite live operation, the controller
prepares `apply_invocation.json`. It is canonical UTF-8 JSON with LF, no BOM,
duplicate keys, unknown fields, or non-finite values, a maximum size of 128
KiB, and exactly:

```text
schema_version
apply_attempt_id
run_id
publication_revision
publication_content_root_sha256
operator_profile_sha256
runtime_root
runtime_root_identity
pre_apply_runtime_snapshot
content_sha256
```

`schema_version` is 1. Run and attempt IDs are exactly 32 lowercase hexadecimal
characters. `publication_revision` is exactly
`revisions/sha256-<64-lowercase-hex>`. All SHA fields use lowercase
`sha256:<64-hex>`, `runtime_root` is the canonical absolute path, root identity
uses the existing `PathIdentity` contract, and `content_sha256` is the standard
self-digest.

`pre_apply_runtime_snapshot` has exactly `deck_name`, `mapping_value`,
`deck_config_ini_sha256`, `runtime_state_sha256`,
`last_apply_receipt_sha256`, `runtime_tree_sha256`, `transaction_ids`, and
`content_sha256`. Deck name is safe text from 1 to 128 characters;
`mapping_value` is null or one validated component; each state digest is null
or a standard SHA digest; and `transaction_ids` is a sorted unique list of at
most 128 lowercase 32-hex IDs. Its own self-digest plus the outer self-digest
binds the complete pre-apply state.

The transition protocol is fixed:

1. Atomically write and durably flush the sealed invocation receipt.
2. Atomically compare-and-set the session from `PUBLICATION_COMMITTED` to
   `APPLY_STARTED`, binding the invocation-receipt digest.
3. Only then call `apply_and_match_published(...)`.

The apply-attempt ID is passed unchanged as the runtime transaction ID, so
recovery never has to guess which journal belongs to the run. If resume sees
either the sealed invocation receipt or `APPLY_STARTED` without a confirmed
disposition, it invokes only the controller recovery entry:

```text
hsconfig recover-apply --session <run-directory> --json
```

That entry verifies the receipt self-digest, session/run binding, profile and
root rebinding, publication revision and digest, pre-apply snapshot, and exact
journal transaction ID. It classifies or recovers the existing attempt and
never creates a new journal, staging path, runtime target, or apply. A receipt
without `APPLY_STARTED` is still recovery-only; `APPLY_STARTED` without its
valid receipt is `UNKNOWN_REQUIRES_RECOVERY`. A new apply is impossible until
the previous attempt is terminally classified.

## One-candidate workflow

### Lead strategist

One lead strategist receives only the sealed starter context and the closed
candidate contract. It considers relevant strategic alternatives internally
but emits one proposed configuration.

The candidate must contain:

- one coherent deck-level game plan;
- a non-empty, internally consistent Mulligan strategy;
- the complete validated GlobalValues key set;
- exactly one disposition for every unique physical main-deck CardID;
- only supported card-behavior rules with correct runtime owners;
- exact transformation, sideboard, and linked-owner relationships;
- a combo only when its complete ordered runtime contract is supported;
- an explicit reason for every deliberately unconfigured card;
- no fabricated HearthRanger surface or unsupported behavior.

HSConfig validates the candidate before independent review. A technical error
returns only the exact bounded findings to the same strategist. The strategist
gets at most two targeted revisions in total. Candidate validation and reviewer
requests share this one revision budget; the initial draft does not count as a
revision, and there is no additional hidden retry loop. Exhaustion preserves
the run and stops; the controller does not publish a partial or blank
configuration.

### Independent reviewer

The reviewer receives only:

- the sealed starter context;
- the sealed candidate;
- the successful candidate-validation receipt.

It does not receive the strategist conversation and cannot write runtime
files. It checks:

- alignment with the inferred deck plan;
- Mulligan coherence;
- GlobalValues coherence and unnecessary baseline drift;
- complete card coverage;
- transformations, owners, and sideboards;
- source strength and unsupported assumptions;
- overconfiguration and simpler equivalent choices;
- technical realizability in the supported runtime grammar.

The review result is either `approved` or a closed set of targeted revision
requests. Its confidence is exactly `high` or `limited`;
the product does not invent numeric optimality. An approved review binds the
context digest and candidate digest. The reviewer does not replace the
candidate or silently choose a fallback.

## Durable optimized authority

`LLM_OPTIMIZED_START` remains the configuration mode. Dispatch is never
inferred from filenames alone. `reports/input_manifest.json` carries the
closed field `optimized_start_authority_schema`.

Existing packages in which that field is absent remain legacy five-document
packages. They require the exact existing context, three-candidate, and
decision report set and optimized derivation-receipt schema 3. New compilers
must not emit this implicit legacy form, and its existing validators, apply
behavior, and `high|low` critic-confidence vocabulary remain unchanged.

New packages require
`optimized_start_authority_schema="single_candidate_review_v1"`, optimized
derivation-receipt schema 4, the sealed snapshot manifest, and this exact
three-document starter authority set:

1. `starter_context.json`;
2. `starter_config_candidate.json`;
3. `starter_config_review.json`.

The durable optimized report directory therefore contains exactly these four
authority files:

```text
reports/optimized_start/input_snapshot_manifest.json
reports/optimized_start/starter_context.json
reports/optimized_start/starter_config_candidate.json
reports/optimized_start/starter_config_review.json
```

All three new starter documents use `schema_version=2`. The context has exactly
these top-level fields:

```text
schema_version
input_snapshot_manifest_sha256
deck_identity
cards
deck_shape
supported_runtime_contract
globalvalues_baseline
source_evidence
existing_claims
known_safety_boundaries
content_sha256
```

The candidate has exactly these top-level fields:

```text
schema_version
candidate_id
candidate_revision
starter_context_sha256
deck_fingerprint
strategy_summary
mulligan
globalvalues
card_rules
combo
card_dispositions
rule_rationales
assumptions
content_sha256
```

It fixes `candidate_id="lead"`, `strategy_summary.role="lead_strategist"`,
and `candidate_revision` to 1, 2, or 3. The existing closed nested Mulligan,
GlobalValues, rule, combo, disposition, rationale, assumption, digest, and
identity contracts remain fail-closed.

The review schema has exactly these top-level fields:

```text
schema_version
review_id
review_status
confidence
starter_context_sha256
candidate_id
candidate_revision
candidate_sha256
revision_requests
review_summary
content_sha256
```

The review is canonical JSON no larger than 64 KiB. `review_id` is a 1 to 64
character lowercase ASCII identifier; `review_status` is `approved` or
`revision_requested`; `confidence` is `high` or `limited`; all digest fields
use lowercase `sha256:<64-hex>`; `candidate_id` is `lead`; and
`candidate_revision` is 1, 2, or 3. `review_summary` is safe prose from 1 to
2,000 characters.

`revision_requests` is a canonical JSON list of at most 32 rows. Every row has
exactly `code`, `target`, and `message`. `code` is a 1 to 64 character lowercase
ASCII identifier, `target` is one of `whole_candidate`, `strategy_summary`,
`mulligan`, `globalvalues`, `card_rules`, `combo`, `card_dispositions`,
`rule_rationales`, or `assumptions`, and `message` is safe prose from 1 to 500
characters. An approved review has an empty list; a revision request has at
least one row. No list is treated as a mathematical set, and canonical order
is part of the review digest.

The durable review must have `review_status="approved"`,
`confidence="high"` or `confidence="limited"`, an empty revision-request set,
and exact context, candidate ID, revision, candidate digest, and self-digest
bindings. A limited review remains visibly limited in the final response.

The package derivation receipt binds the full canonical bytes of the snapshot
manifest and all three starter documents. The operator summary and configure
result project the authority-schema value, snapshot digest, candidate digest,
candidate revision, review digest, review status, and confidence. The apply
gate dispatches on the manifest discriminator and re-derives the same binding
before allowing a runtime write.

Existing published five-document optimized packages remain readable and
applicable under their existing schema. New generation does not create
duplicate candidates to impersonate the former three-candidate contract, and
there is no converter for unfinished external sessions. Missing, unknown,
mixed, extra, or downgrade-manipulated authority sets fail closed.

For `reports/input_manifest.json`, this rule is mode-specific. Conservative
packages must not contain `optimized_start_authority_schema`; legacy optimized
packages alone may omit it; every newly generated optimized package must
contain exactly `single_candidate_review_v1`.

## Compilation, publication, and live apply

After review approval, the normal path is:

```text
approved candidate
-> deterministic compilation
-> strict package validation
-> recomputed operator summary and apply facts
-> write-free fake apply
-> atomic publication
-> guarded live apply
-> runtime-match
```

The internal prepublication seam is exact:

1. Render one immutable temporary `04_package` from the frozen compile input.
2. Run strict validation, derivation replay, and operator-summary parity on
   that exact directory.
3. Run the write-free apply planner on that same direct package path.
4. Store its path-bound receipt only as the external
   `prepublication_apply_check.json` with `diagnostic_only=true`.
5. Revalidate the read-only profile, output-base identity, and deck-output
   precondition, then atomically publish only after steps 1 through 4 pass.
6. Revalidate the profile and runtime-root identity immediately before the
   repo-owned composite live operation.
7. The composite operation acquires one publication lease, resolves and leases
   the exact immutable published revision, and requires the normal current
   pointer still to name its publication digest.
8. Lease-aware apply and match functions use that same pinned revision without
   recursively acquiring the publication lock. The operation holds the lease
   through a final current-pointer check and terminal runtime-match result.

The normal route calls one repository-owned public API,
`apply_and_match_published(...)`, with the exact publication digest, runtime
root, and sealed apply-invocation receipt. Direct legacy `apply` and
`runtime-match` commands retain their existing contracts; they are not composed
by an external caller holding a second publication lock.

The prepublication receipt is never written back into the derived package,
never reused by live apply, and never grants apply authority. A failure through
step 4 leaves both `current.json` and runtime state unchanged. Published
revisions are retained long enough to keep the applied revision immutable
through runtime match.

The composite operation follows one lock order: publication lease, immutable
package lease, then runtime apply lock. Its lease-aware internals do not reopen
those locks. This avoids both recursive-lock deadlock and a successful match
for package A while `current.json` names package B.

The normal configured installation is live by default because its local
operator profile already carries explicit `live_by_default=true`
authorization. Profile and root mismatches stop before any output or runtime
write. Explicit preview intent or `live_by_default=false` still performs the
validated publication path but never enters the composite live operation,
never touches the runtime root, and creates no runtime lock, journal, state, or
apply receipt. It reports `PREVIEW_READY`.

Live success requires all of the following for the same exact package:

- apply gate allowed;
- apply receipt status `applied`, `already_current`, or a successfully
  recovered committed state;
- exact active deck mapping;
- exact runtime tree identity and digest;
- `runtime-match` status `matched`.

Before choosing a terminal status, the controller classifies the physical
apply disposition as exactly one of:

- `NOT_COMMITTED`;
- `COMMITTED`;
- `COMMITTED_RECOVERY_PENDING`;
- `UNKNOWN_REQUIRES_RECOVERY`.

The closed raw-result mapping is:

- `applied` -> `COMMITTED`;
- `already_current` -> `COMMITTED` without a new runtime write;
- `recovered` -> `COMMITTED`;
- `committed_receipt_pending` -> `COMMITTED_RECOVERY_PENDING`;
- an exception or crash without sufficient physical evidence ->
  `UNKNOWN_REQUIRES_RECOVERY`.

`committed_receipt_pending` is never success. It enters `recover-apply`, then
requires receipt/state parity and runtime match. The controller never retries
apply while commit disposition is pending or unknown. If recovery proves
`NOT_COMMITTED`, this run returns `FAILED_PRESERVED`; it does not start another
apply attempt implicitly.

The user-facing terminal statuses are:

- `LIVE_AND_MATCHED`;
- `ALREADY_LIVE`;
- `PREVIEW_READY`;
- `PROFILE_REQUIRED`;
- `FAILED_PRESERVED`;
- `APPLIED_BUT_NOT_VERIFIED`.

`FAILED_PRESERVED` is used only when `NOT_COMMITTED` is proven.
`APPLIED_BUT_NOT_VERIFIED` covers a committed or unresolved disposition that
has not completed receipt/state parity and exact runtime match. It is not
success, preserves transaction evidence, does not blindly repeat apply, and
routes through existing recovery and diagnostic boundaries.

## Failure behavior

| Failure point | Required behavior |
| --- | --- |
| Local profile absent, malformed, unsafe, or identity-mismatched | Stop as `PROFILE_REQUIRED` before LLM, output, or runtime writes |
| Profile has `live_by_default=false` or prompt explicitly requests preview | Publish the validated package, but create no runtime lock, journal, state, or receipt |
| Invalid deck or unresolved identity | Stop before LLM generation; no package or runtime write |
| Snapshot, compiler contract, or grammar mismatch | Stop before LLM resume, compilation, publication, or runtime write |
| Candidate validation | Return exact findings; at most two targeted revisions |
| Reviewer rejects after revision budget | Preserve resumable run; no publication or runtime write |
| Unknown, mixed, or downgraded optimized authority schema | Fail closed before derivation or apply |
| Compilation, strict validation, derivation, or fake apply | Keep previous current output and runtime unchanged |
| Normal pointer changed before apply | Stop with publication conflict; do not apply the older run |
| Failure before runtime commit | Keep previous active runtime configuration |
| Crash after `APPLY_STARTED` | Invoke recovery-only classification; never call apply again for that attempt |
| Interrupted or ambiguous runtime commit | Use only the existing transaction recovery contract; never delete or reapply blindly |
| Runtime mismatch after commit | Report `APPLIED_BUT_NOT_VERIFIED`; preserve all evidence and do not claim success |

The final user response contains one concrete cause and the retained safe state.
It does not expose long raw logs unless technical details are requested.

## Naming and presentation

This design does not migrate physical runtime names. Hash-qualified publication
and runtime version directories remain internal because they support immutable
identity, idempotence, conflict detection, recovery, and runtime matching.

Normal product surfaces show only the human deck name. Hashes and internal
version directories are limited to technical details and diagnostics. This is
a presentation rule, not a new runtime naming subsystem.

## Relevant GitHub polish

The repository landing experience receives only product-relevant changes:

1. an outcome-first sentence explaining deck name plus deck code to live
   verified configuration;
2. one copyable normal prompt;
3. one compact successful-result example;
4. one short flow line: `Deck -> Config -> Validate -> Live -> Match`;
5. one concise boundary stating pre-run evidence-based configuration rather
   than gameplay optimality;
6. consistent normal-path wording across the root README, installed skill, and
   operator guide; they must stop presenting three-candidate generation or
   apply-only-on-explicit-live-request behavior as the normal route;
7. correction of stale visible links and alignment of the repository
   description and topics with the one-prompt product.

The polish does not add a website, dashboard, GUI, branding project, large
media set, new contribution process, or retroactive release rewrite. Existing
security, signing, CI, branch protection, tag, and release history remain
unchanged.

## Verification and acceptance

Verification is proportional and consolidated:

- a small focused, parametrized test matrix proves the following boundaries;
- **authorization:** normal runs never change profile bytes; missing profile,
  profile reparse, root overlap, and identity drift stop before output or
  runtime writes; disabled policy and explicit preview publish without any
  runtime lock or artifact; an enabled valid profile needs no per-run
  confirmation;
- **freeze and any deck:** loaders run once, later upstream changes do not
  alter the run, resume performs no repeated successful fetch, a fully
  resolvable uncatalogued deck passes, and an unknown CardID stops before LLM
  work;
- **authority and revisions:** the exact legacy five-document fixture remains
  valid, the exact new schema is valid, mixed/downgraded sets fail, and a
  changed candidate invalidates review and downstream receipts; extra fields,
  wrong types, oversized documents, noncanonical revision requests, and
  self-digest tampering fail closed;
- **prepublication:** injected faults through fake apply preserve pointer and
  runtime bytes and identities, and the diagnostic receipt cannot authorize
  live apply;
- **apply and recovery:** commit-boundary faults produce the correct physical
  disposition, `committed_receipt_pending` cannot report success, and no case
  blindly reapplies; a crash after physical commit but before
  `APPLY_COMMITTED` enters recovery-only; crashes after durable invocation
  receipt, after `APPLY_STARTED`, and after runtime-journal creation all retain
  the same attempt ID, enter recovery-only, and start no second apply;
- **race, match, and idempotence:** pointer switches before apply and between
  apply and match cannot apply or match the wrong package, a post-commit
  runtime mutation reports
  `APPLIED_BUT_NOT_VERIFIED`, and the second identical run is `ALREADY_LIVE`
  without creating another runtime revision;
- documentation contracts verify one consistent normal route;
- broad suites are not repeated after every focused change;
- one final exact-commit CI run is the integrated authority;
- one explicitly authorized manual ShadowPriest canary completes the real path
  through `LIVE_AND_MATCHED` after CI succeeds.

The implementation is complete only when:

1. after one-time live-profile enablement, a normal run needs only deck name
   and deck code;
2. every LLM phase uses the same frozen inputs;
3. exactly one candidate is produced, validated, independently approved, and
   compiled;
4. no additional apply confirmation is requested;
5. failure before commit preserves the previous active configuration;
6. success requires exact runtime match;
7. normal output contains no hash-qualified deck name;
8. repository, embedded skill, and installed skill agree on the workflow;
9. the final exact-commit CI run is fully green;
10. no incomplete own journal or temporary publisher/apply artifact remains
    after acceptance; durable state and receipt evidence remains intact.

## Explicit non-goals

This design does not add:

- a standalone or provider-neutral LLM client;
- model credentials or provider configuration;
- three-candidate generation or candidate ranking;
- replay, win-rate, or post-game analysis;
- HSTuner integration;
- automatic gameplay learning;
- physical SHA-free runtime directories;
- batch or multi-deck operation;
- a GUI, dashboard, or website;
- a broad historical-session migration;
- a retroactive change to the existing `v1.0.0` release.
