# HSConfig Pre-Run Near-100 Design

Date: 2026-07-28

Status: approved design

Repository: `Teufelsboy/HSConfig`

Target release: `v1.0.0`

## 1. Objective

Bring HSConfig as close as reasonably possible to a complete, reproducible,
safe, maintainable, and professionally published pre-run configuration system.
The target is an evidence-backed score of approximately 98-99/100 inside the
explicit pre-run contract.

The design does not attempt to prove or improve gameplay quality. The user
accepts the HearthRanger bot as an externally perfect gameplay decision-maker.
HSConfig therefore adds only technically necessary, safely expressible, and
properly authorized configuration. Unsupported or context-dependent gameplay
decisions are delegated to the bot instead of being approximated.

The final state must be:

- technically load-safe and fail-closed;
- deterministic and reproducible;
- crash-safe for output publication and runtime activation;
- complete in its disposition of every deck, card, claim, key, and runtime
  surface;
- limited to one current generated output per audited deck;
- free of stale builds, caches, backups, historical output waves, and internal
  agent artifacts;
- published from a single `main` branch;
- publicly visible but explicitly proprietary;
- represented by one canonical `v1.0.0` release;
- supported by a small, curated, linear root history.

## 2. Explicit Scope

### 2.1 In scope

- Deck and card identity for the twelve audited decks.
- Linked-entity and sideboard identity and ownership.
- Official card semantics needed for safe pre-run classification.
- Layered source and policy provenance.
- Mulligan, GlobalValues, per-card CardID behavior, and source-backed Combo
  lowering.
- Complete card, claim, key, and surface disposition.
- Deterministic package construction and publication.
- Strict package validation and apply authority.
- Crash-safe Runtime installation and `deck_config.ini` activation.
- Operator reports and machine-readable quality scorecards.
- Architecture decomposition, testability, reproducible CI, packaging, and
  command-line polish.
- Repository slimming, governance, security settings, history curation, and
  `v1.0.0` publication.

### 2.2 Out of scope

- Gameplay optimization, win-rate optimization, or proof of perfect play.
- Replay-driven tuning.
- Runtime game sampling as a release requirement.
- HSTuner.
- Claims that an offline validator proves actual in-client gameplay quality.
- Fabricated VisionAI surfaces, conditions, targeting, priorities, timing, or
  numeric tuning.
- Persistent Config package backups.
- Config packages as GitHub Release assets.
- Multiple supported release lines.
- Any additional local or remote branch, or pull-request-based development.

### 2.3 Authoritative scope markers

Every final package and scorecard must expose the following meaning without
ambiguous wording:

```text
hsconfig_scope = PRE_RUN_CONTRACT
gameplay_strategy_owner = hearthranger_bot
gameplay_quality = OUT_OF_SCOPE_ASSUMED_EXTERNAL
bot_gameplay_assumption = trusted_external
```

`operator_summary.json` remains the only normal apply authority. Diagnostic
reports, source strength, semantic closure, and scorecards do not create a
second apply gate.

## 3. Chosen Approach

Use a controlled contract-closure program that retains the existing safe core
and replaces its risky or oversized boundaries in dependency order.

The design rejects two alternatives:

1. A report-only cleanup would make the current gaps look better without
   fixing crash safety, reproducibility, or architecture.
2. A full rewrite would discard more than 3,000 passing tests and many hard-won
   semantic boundary cases.

The selected approach:

- preserves strict fail-closed semantics;
- closes every identity and decision through explicit emission, suppression,
  or bot delegation;
- introduces immutable typed build data;
- makes output and runtime activation transactional;
- reduces duplicated authorities and oversized orchestration;
- makes release scoring executable and evidence-backed;
- completes the work with a curated proprietary `v1.0.0` repository.

## 4. Near-100 Score Contract

### 4.1 Score principles

Scores are produced from a machine-readable release scorecard. Every scored
row has:

- a stable metric identifier;
- a numerator and denominator where applicable;
- a status;
- evidence paths or command receipts;
- blocking and non-blocking reasons;
- an explicit scope statement.

No score is raised merely because a field was renamed, a warning was hidden,
or a runtime row was emitted. Missing gameplay evidence cannot reduce or
increase a pre-run score because gameplay is outside the contract.

### 4.2 Target scorecard

| Area | Target |
|---|---:|
| Static load and contract safety | 99 |
| Safe VisionAI lowering | 99 |
| Testability and assurance | 98-99 |
| Card and surface disposition | 100 |
| Layered pre-run source coverage | 98-100 |
| Architecture and maintainability | 96-98 |
| Slimness and coherence | 98-99 |
| GitHub and repository polish | 98-99 |
| Local version and artifact hygiene | 100 |
| Pre-run overall state | approximately 98.5 |
| Gameplay quality | N/A |

An exact 100 is not claimed. Offline software cannot fully prove hardware
power-loss durability, third-party bot internals, or every future filesystem
behavior.

### 4.3 Source score split

The old broad `strategic_source_coverage` concept becomes three distinct
surfaces:

- `layered_pre_run_source_coverage`, scored with a 98-100 target;
- `exact_guide_authority`, shown honestly as `X/12` and not included in the
  weighted score;
- `gameplay_quality`, shown as `N/A`.

`SOURCE_BACKED_STRONG` retains its current strict meaning. It is not weakened
to make the score reachable.

### 4.4 Hard release gates

The release cannot pass unless:

- no P0 or P1 finding remains open;
- all twelve deck identities and fingerprints are exact;
- all 360 main-deck slots are represented;
- all 205 deck-specific main-card identities are resolved;
- all three expected MechPala sideboard modules have the correct owner;
- all 208 card or module rows have a final disposition;
- all 316 current structured claims have a final disposition;
- all 456 deck-specific GlobalValues decisions are classified;
- emission precision is 100%;
- eligible emission recall is 100%;
- no invented condition, target, owner, timing, or priority exists;
- no generic unresolved semantic remainder exists;
- no publishable package contains an absolute temporary or user path;
- exactly twelve current output roots exist, one per audited deck;
- no report claims that HSConfig proved gameplay quality.

## 5. Evidence and Semantic Closure

### 5.1 Evidence lanes

Every claim uses exactly one visible authority lane:

| Lane | Evidence | Allowed use |
|---|---|---|
| A | Official card data from a pinned snapshot | Identity, text, type, linked entities, deterministic mechanics |
| B | Live-verified exact guide with the same deck fingerprint | Exact Mulligan, posture, and strategic runtime claims |
| C | Public full-text archetype or mechanic guide | Context and review, not exact deck authority |
| D | Versioned and reviewed internal policy | Explicitly policy-backed behavior, never guide authority |
| E | Bot delegation | Intentional decision to emit no runtime row |

A negative source search may close source acquisition but does not count as a
guide.

### 5.2 Dual closure

Source strength and pre-run completeness remain independent:

```text
pre_run_contract_status = complete
strategy_authority_status = partial | strong
```

A deck may have a complete pre-run contract while remaining
`SOURCE_BACKED_PARTIAL`. This is honest when every unsupported decision is
explicitly delegated or suppressed.

### 5.3 Final card dispositions

Every card or module row has exactly one final disposition:

1. `runtime_emitted`
2. `bot_delegated`
3. `suppressed_unsupported_surface`
4. `suppressed_insufficient_authority`
5. `analysis_only_sideboard`

Each row records:

- card identity;
- deck identity and zone;
- official card semantics;
- authority lane;
- claim references;
- final disposition;
- stable reason;
- physical owner where relevant.

The following are not valid final states:

- `generic_low_confidence`;
- an unclassified `first_missing_link`;
- a generic `needs_runtime_surface`;
- a metadata-only file presented as complete gameplay behavior.

Known mechanics such as Dredge, Tradeable, Outcast, Secret timing, Imbue,
Starship, Magnetic, Location activation, Choose One, and conditional targeting
remain visible. If they cannot be expressed safely, they are delegated or
suppressed.

### 5.4 Mulligan contract

Mulligan follows minimal intervention:

- exact live-verified guide claims may lower;
- internal policy keeps may lower only when deterministic, unconditional, and
  context-free;
- a condition-dependent card may not become an unconditional `*` keep;
- uncertain opening-hand decisions are delegated to the bot;
- an intentionally empty `Mulligan.json` is valid;
- start-of-game effects do not imply an opening-hand keep;
- Darkbishop Benedictus remains outside Mulligan without explicit opening-hand
  evidence.

Current contextual keeps, including Jam Session, Eat! The! Imp!, Divination,
Prize Plunderer, Southsea Deckhand, and Skaterbot, require reclassification.

### 5.5 GlobalValues contract

For each of twelve decks and 38 keys:

- every decision is typed;
- every `copy_baseline` value has exact baseline parity;
- an unchanged baseline is a complete decision;
- numeric overlays require their defined authority;
- no numeric value is changed to improve a score;
- posture-dependent keys remain unchanged without the required posture claim.

### 5.6 Lowering metrics

Two metrics prevent score gaming:

- `emission_precision`: all emitted rows are authorized, correctly owned,
  correctly typed, and physically/report-wise identical;
- `eligible_emission_recall`: every claim classified in advance as fully
  authorized and expressible is emitted.

Both must equal 100%.

Additional invariants:

- no suppressed condition reappears as an unconditional row;
- no conflicting runtime keys;
- duplicate-preserving typed parity across model, report, and physical files;
- `Combo.json` only for a complete, ordered, sufficiently authorized combo;
- no normal `Presume.json`, `Concede.json`, or aggregate
  `CardBehavior.json`.

### 5.7 Source acquisition closure

Every deck has:

- a documented acquisition attempt;
- a checked archetype or mechanic dossier where available;
- otherwise a versioned internal policy and a documented negative search;
- Evidence IDs for every adopted textual claim;
- source or policy identity, date, claim kind, and content hash;
- exact guide authority reported separately.

Live acquisition and deterministic build are separate. A build consumes only
frozen, hashed source bundles.

## 6. Target Architecture

### 6.1 Data flow

```text
CanonicalBuildInputs
  -> LayeredEvidenceContract
  -> ImmutablePackageModel
  -> DeterministicStagingRenderer
  -> FullTreeValidatorAndManifest
  -> AtomicOutputPublisher
  -> CurrentPackageResolver
  -> GuardedApplyAuthority
  -> ContentAddressedRuntimeInstaller
  -> AtomicDeckConfigCommit
```

### 6.2 Canonical build inputs

The immutable input contract contains:

- schema version;
- generator version and Git commit;
- deck name and canonical deck fingerprint;
- pinned card-database snapshot hash;
- active policy profile;
- normalized `as_of_date`;
- frozen source bundle hashes;
- versioned internal policy identifiers.

The default policy profile is `BOT_NATIVE_PRE_RUN`.

### 6.3 Immutable PackageModel

One typed, immutable model is the only render source for:

- `GlobalValues.json`;
- `Mulligan.json`;
- CardID files;
- optional `Combo.json`;
- surface and disposition ledgers;
- operator summary;
- manifests and contract reports.

Runtime roots, apply receipts, temporary paths, and mutable execution metadata
are not part of the package model.

### 6.4 Component boundaries

The target components are:

- `build_inputs`: canonicalizes and hashes inputs;
- `evidence_contract`: normalizes claims and authority;
- `package_model`: immutable domain truth;
- `surface_compilers`: pure lowering per runtime surface;
- `renderer`: deterministic file projection;
- `manifest`: complete tree hashes;
- `publisher`: output transaction;
- `current_output`: pointer resolution;
- `runtime_installer`: runtime candidate and commit;
- `recovery`: deterministic reconciliation;
- `operator_projection`: reports from the same model.

`configure` becomes thin orchestration. It does not mutate the CLI argument
namespace and does not construct overlapping report truths.

## 7. Single Registry and Authority

`visionai_registry` becomes the only source for:

- required and optional runtime surfaces;
- row schemas and value types;
- physical owner rules;
- claim-kind-to-surface policy;
- GlobalValues key classes;
- the normal operator authority path.

Builder, validator, ledger, acceptance, quality, and reports derive their
surface sets from this registry.

The design removes:

- duplicate surface constants;
- repeated authority path literals;
- the duplicate GlobalValues profile report;
- production modules with no production consumer unless intentionally
  integrated;
- safety-critical `assert` statements.

Safety-critical parity and invariant failures use explicit validation errors
that remain active under `python -O`.

## 8. Deterministic Package Rendering

### 8.1 Publishable file rules

Publishable files use:

- canonical JSON key order;
- stable row and file order;
- UTF-8;
- exactly `\n` line endings;
- no absolute paths;
- no local user names;
- no temporary directories;
- no random identifiers;
- no uncontrolled wall-clock timestamps;
- no file modification times in semantic hashes;
- no runtime root paths.

### 8.2 Full-tree manifest

`package_manifest.json` records every publishable file:

- normalized relative path;
- byte length;
- SHA-256.

The package root hash is computed from the sorted sequence of path, size, and
file hash. Unmanifested publishable files are forbidden.

Two cold builds from identical inputs, performed under different absolute
working and temporary paths, must produce byte-identical trees and root hashes.

## 9. Atomic Output Publication

### 9.1 Stable structure

Each deck has one stable output root:

```text
outputs/<Deck>/
  current.json
  revisions/
    sha256-<root-hash>/
      01_manifest/
      02_.../
      03_research/
      04_package/
      configure_summary.json
```

In the stable end state, each deck has exactly one revision.

### 9.2 Publication transaction

1. Acquire a per-deck lock.
2. Reconcile any prior interrupted transaction.
3. Render into a same-volume transaction directory.
4. Strictly validate the full candidate tree.
5. Compute and verify its root hash.
6. Move it to `revisions/<root-hash>`.
7. Write and flush `current.json.tmp`.
8. Atomically replace `current.json`.
9. Delete all unreferenced HSConfig-owned revisions.
10. Remove transaction residue and release the lock.

Properties:

- failure before pointer replacement leaves the old package active;
- failure after pointer replacement leaves the new complete package active;
- an identical input and hash is an idempotent no-op;
- recovery never guesses from modification times;
- ambiguous or corrupt state is fail-closed;
- failed builds never damage the current output.

All package consumers use one central current-output resolver.

## 10. Crash-Safe Runtime Apply Without Persistent Backups

### 10.1 Runtime strategy

The active Runtime Config directory is never deleted before a replacement is
ready.

The installer:

1. Acquires an exclusive runtime lock.
2. Reconciles any prior interrupted transaction.
3. Revalidates package, operator authority, identity, manifest, and physical
   surfaces.
4. Copies the candidate to an inactive, content-addressed Runtime directory.
5. Verifies the copied tree against the package manifest and flushes it.
6. Re-reads `deck_config.ini` and compares it with its preflight hash.
7. Writes and flushes a complete temporary INI.
8. Atomically replaces `deck_config.ini`.
9. Re-reads the mapping and verifies the active Runtime hash.
10. Writes the runtime state ledger atomically.
11. Deletes the now-unreferenced, clearly HSConfig-owned old Runtime Config.
12. Releases the lock.

The INI replacement is the only logical commit point.

### 10.2 Runtime guarantees

- Before INI commit, the old Config is active.
- After INI commit, the fully verified new Config is active.
- No persistent `.hsconfig_backups` directory is created.
- A crash may leave an inactive candidate or an unreferenced old Config, but
  never requires guessing which Config is active.
- Recovery treats the INI mapping as commit truth.
- Cleanup deletes only paths whose ownership is cryptographically and
  structurally proven.
- Foreign Runtime Configs are never deleted by name pattern alone.
- An identical active package is a verified no-op.

Apply receipts live outside the immutable package. A receipt failure after INI
commit is represented as `committed_receipt_pending`; status reconstructs the
result from the INI, state ledger, and Runtime hash.

### 10.3 Failure matrix

| Failure | Visible state | Recovery |
|---|---|---|
| Render or validation fails | old output active | remove staging |
| Crash before pointer replace | old output active | remove unreferenced revision |
| Crash after pointer replace | new output active | remove old revision |
| Concurrent output build | one publisher proceeds | per-deck lock |
| Runtime copy or hash fails | old Runtime active | remove candidate |
| External INI change | external or old INI remains | compare-and-swap blocks |
| Crash before INI replace | old Runtime active | remove inactive candidate |
| Crash after INI replace | new Runtime active | remove old owned Config |
| Receipt write fails | new Runtime active | reconstruct receipt |
| Corrupt or ambiguous state | no mutation | fail closed |

## 11. Test and Verification Design

### 11.1 Test classes

The implementation adds:

1. Characterization tests before every architectural extraction.
2. Unit and contract tests for each new component.
3. Property and invariance tests for order, path, and hash independence.
4. Double cold builds of all twelve decks under different absolute paths.
5. Fault injection before and after every mutation point.
6. `KeyboardInterrupt`, `SystemExit`, and receipt-failure simulations.
7. Per-deck and Runtime concurrency tests.
8. Corrupt pointer, manifest, ledger, and recovery-state tests.
9. `python -O` regression tests.
10. Wheel and sdist builds.
11. Installation from the wheel into a fresh environment.
12. `hsconfig --version` and CLI smoke tests.
13. Documentation link, policy, absolute-path, secret, and artifact scans.
14. Full twelve-deck acceptance and contract-spine tests.
15. Targeted mutation tests for apply authority, owner policy, and runtime
    surface policy.

### 11.2 Coverage gates

- `atomic_io`, `publisher`, `runtime_installer`, `recovery`, and critical apply
  authority paths have 100% meaningfully reachable branch coverage.
- The whole project has at least 90% branch coverage, with a target of 95%.
- Generated data, fixtures, and declarative tables do not inflate coverage.
- Every intentional mutation of a critical contract causes at least one test
  failure.

### 11.3 Release verification

The final release gate proves:

- Ruff clean;
- complete test suite green;
- contract spine clean;
- all twelve acceptance rows green;
- dependency audit clean;
- wheel and sdist build clean;
- isolated wheel install clean;
- CLI version and smoke tests clean;
- all twelve double builds byte-identical;
- all twelve temporary-root Runtime installation simulations old-or-new safe;
- no absolute local paths in publishable artifacts;
- exactly one output generation per deck;
- no package mutation during apply;
- no backup, staging, cache, or old generation residue.

## 12. Reproducible CI

One directly executable local release gate is canonical. GitHub Actions runs
the same commands after a push to `main`.

CI uses four clear jobs:

- `contract`;
- `test`;
- `package`;
- `security`.

Every job has:

- minimum permissions;
- full commit-SHA Action pins with version comments;
- a timeout;
- concurrency and cancellation of superseded runs;
- locked or constrained dependency resolution;
- no untrusted pull-request execution;
- no Config, log, replay, or report artifact upload.

Workflow triggers are limited to:

- pushes to `main`;
- `workflow_dispatch`;
- an optional scheduled security scan.

There are no `pull_request` or `codex/**` triggers.

The sole-main workflow cannot use server-side pre-merge checks for a commit
that has not yet reached `main`. This accepted risk is mitigated by:

- an identical hard local release gate;
- signed linear commits;
- owner-only updates;
- immediate post-push CI;
- a protected `main` after the one-time history cutover.

Dependencies use a reviewed standard lock or constraints file. Project
metadata has one version source, and `hsconfig --version` reports `1.0.0`.

## 13. Repository and Governance

### 13.1 Public proprietary model

The repository remains publicly visible and is explicitly not Open Source.

It contains:

- a `LICENSE` file with an All-Rights-Reserved proprietary notice;
- the same short status in the README;
- `LicenseRef-Proprietary` package metadata;
- consistent owner and copyright year;
- a contribution policy that external code contributions are not accepted;
- a real private security reporting path.

The rights wording requires owner or legal review before publication. The
software implementation does not make a legal-effect guarantee.

Public visibility still permits the platform behaviors granted by GitHub's
terms. The proprietary notice does not make visible content secret.

### 13.2 Curated active tree

The final root contains only active product surfaces:

```text
.github/
docs/architecture/
docs/contracts/
docs/operator/
scripts/
src/
tests/
AGENTS.md
CONTRIBUTING.md
LICENSE
README.md
SECURITY.md
pyproject.toml
pylock.toml or constraints-ci.txt
```

The curated root excludes:

- `.superpowers/`;
- historical implementation plans;
- review diffs and agent reports;
- obsolete research snapshots;
- `outputs/`;
- build, test, and linter caches;
- personal absolute paths;
- Runtime logs, replays, and private evidence;
- duplicated generated documentation without an active consumer.

Public, intentionally curated catalog and fixture deckcodes are allowed.
Private user deckcodes and Runtime or replay evidence are not.

### 13.3 GitHub presentation and security

The final repository has:

- a concise description;
- focused topics;
- a proprietary license statement;
- a short clickable README quickstart;
- supported Python versions;
- working operator, security, and development links;
- Private Vulnerability Reporting;
- Dependency Graph and Dependabot Alerts;
- Secret Scanning;
- Push Protection when available;
- Action policies restricted to GitHub-owned or explicitly selected actions;
- repository-level SHA-pinning policy;
- unused Wiki, Projects, and Discussions disabled;
- Issues only with a redacted bug-report form and a sensitive-data warning;
- no automatic Dependabot pull requests.

## 14. Curated Root History and v1.0.0

### 14.1 Final visible history

The final `main` history has four to at most six linear, signed commits. The
preferred four are:

1. `feat: establish the HSConfig pre-run contract engine`
2. `feat: add the audited twelve-deck contract catalog`
3. `fix: harden atomic publication and pre-run authority`
4. `chore: establish proprietary repository governance`

It then has:

- exactly one signed annotated tag, `v1.0.0`;
- exactly one matching GitHub Release page with concise release notes;
- no added Release assets or Config archives.

### 14.2 Rewrite safety gate

Before rewriting `main`, all of the following are mandatory:

- clean worktree;
- local `HEAD` exactly equals fetched `origin/main`;
- local and remote branch inventory equals `[main]`;
- no open pull requests;
- expected tag and release inventory confirmed;
- old remote OID recorded explicitly;
- final curated tree fully tested;
- tracked-file manifest reviewed;
- path, secret, deckcode-policy, and artifact scans clean;
- proprietary rights text approved;
- a temporary local Git bundle of the old source ref created outside the
  repository and hashed.

The Git bundle is not a Config backup or product artifact. It is short-lived
rollback protection for the destructive history operation. It is deleted only
after the new remote OID, tree hash, CI, tag, settings, and branch inventory
are confirmed.

### 14.3 Cutover

The cutover:

- creates no additional local or remote branch at any time;
- constructs the curated commit graph without a temporary named branch;
- performs one OID-bound
  `--force-with-lease=refs/heads/main:<OLD_OID>` update;
- never uses an unbound `--force`;
- does not mutate GitHub settings concurrently with the push;
- verifies the exact new remote OID before any cleanup.

Old commits may remain available in existing clones, forks, caches, or by
known object IDs. This design curates the reachable `main` history; it does
not claim universal erasure.

### 14.4 Post-cutover rules

After the new history and CI are confirmed, `main` receives a ruleset that:

- blocks branch deletion;
- blocks force pushes;
- requires linear history;
- requires signed commits after the signing chain is proven;
- limits updates to the owner or a precisely defined bypass actor;
- does not require pull requests;
- does not require pre-merge status checks that contradict sole-main.

Local and remote branch inventories must both equal `[main]`.

## 15. Output Retention and Local Hygiene

The final local output roots are:

- `outputs/ShadowPriest/`
- `outputs/CtAPaladin/`
- `outputs/PirateRogue/`
- `outputs/BigShaman/`
- `outputs/Discolock/`
- `outputs/TreantDruid/`
- `outputs/ImbueMage/`
- `outputs/MechPala/`
- `outputs/Kingslayer/`
- `outputs/Boarlock/`
- `outputs/PirateDH/`
- `outputs/CuteWarrior/`

Each has exactly one current generation.

Outputs remain ignored and untracked. They are not backed up, released, or
archived. Recovery consists of rebuilding them deterministically from
`v1.0.0`, the canonical deck catalog, pinned card data, frozen evidence, and
versioned policy.

The final local workspace has no:

- dated or audit-named output variants;
- old ShadowPriest output waves;
- `.hsconfig_backups`;
- unreferenced output generations;
- transaction staging directories;
- `.pytest_cache`;
- `.ruff_cache`;
- `build`;
- `.codex-qa-*`;
- local `.superpowers` residue.

## 16. Implementation Sequencing Constraints

The later implementation plan must preserve this dependency order:

1. Freeze the score contract, current acceptance fixtures, and characterizing
   tests.
2. Add atomic file, lock, and fault-injection primitives.
3. Establish canonical inputs, single registry, and immutable PackageModel.
4. Implement layered evidence and complete card, claim, key, and surface
   dispositions.
5. Implement deterministic rendering and the full-tree manifest.
6. Introduce atomic output publication and current-output resolution.
7. Introduce content-addressed Runtime installation and atomic INI commit.
8. Remove legacy backup, direct-delete, in-place-write, duplicate-authority,
   and duplicate-report paths only after replacement tests pass.
9. Rebuild and verify all twelve outputs, then remove all older generations
   and local residue.
10. Consolidate CI, packaging, documentation, governance, and GitHub metadata.
11. Execute the curated root-history cutover.
12. Publish and verify `v1.0.0`, activate final rulesets, and perform the
    complete near-100 audit.

No phase may claim completion from fixtures, reports, or CI alone when its
contract requires physical package or temporary-root Runtime verification.

## 17. Final Acceptance Contract

The design is complete only when all of the following hold simultaneously:

- static contract score at least 99;
- safe lowering score at least 99;
- testability score at least 98;
- card and surface disposition score 100;
- layered pre-run source coverage at least 98;
- architecture score at least 96;
- slimness score at least 98;
- GitHub polish score at least 98;
- local hygiene score 100;
- overall pre-run score at least 98;
- gameplay shown only as `N/A`;
- full release gate green;
- all twelve packages strict-valid and byte-reproducible;
- all critical fault-injection and recovery tests green;
- one current output generation per deck;
- no persistent backups or stale artifacts;
- one local branch and one remote branch, both `main`;
- no open pull requests;
- exactly one canonical `v1.0.0` tag and matching Release page;
- final local `main` equals `origin/main`;
- worktree clean.

This design favors complete, explicit, conservative pre-run contracts over
unverified gameplay configuration. Near 100 means that HSConfig knows exactly
what it owns, what it emits, what it suppresses, and what it delegates.
