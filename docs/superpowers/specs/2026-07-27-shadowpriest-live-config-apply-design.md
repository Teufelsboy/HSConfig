# ShadowPriest Live-Verified Configure and Guarded Apply Design

**Date:** 2026-07-27
**Repository:** `Teufelsboy/HSConfig` checkout
**Deck:** ShadowPriest
**Deck code:** `AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=`
**Hearthstone deck ID:** `2737726722`
**HDT deck ID:** `c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602`

## Objective

Create a fresh ShadowPriest HSConfig package from current public source
evidence, validate its complete package and semantic contract, and install it
into the active HearthRanger runtime only when the freshly recomputed normal
operator gate explicitly permits apply.

The run proves package validity and installation integrity. It does not prove
in-client behavior, win rate, or gameplay optimality.

## Execution boundary

- Use the normal `hsconfig configure` route for source acquisition and package
  generation.
- Use a new dated output directory; do not overwrite an existing ShadowPriest
  output.
- Fetch repository state and require a clean `main` that is not behind
  `origin/main` before generation.
- Acquire public sources through the live online source path.
- Keep captured, fixture, manual, or legacy provenance visible as diagnostics;
  it does not independently authorize or prevent apply.
- Do not invoke HSTuner, analyze replays, inspect win rate, or tune after
  games.
- Write runtime files only through the explicit `hsconfig apply` command.
- Stop without a runtime write whenever the package gate is blocked.

## Two-phase workflow

### Phase 1: Configure and inspect without a runtime write

1. Run repository currentness and contract preflight.
2. Run `hsconfig configure` with:
   - the exact deck name and deck code;
   - the standard HearthRanger runtime root;
   - a new dated output directory;
   - `--online-source`;
   - `--auto-source`;
   - no `--apply`.
3. Read `configure_summary.json.acceptance_summary` first.
4. Read `configure_summary.json.handoff_contract` and source-closure diagnostics
   only as supporting evidence.
5. Treat `04_package/reports/operator_summary.json` as the sole normal apply
   authority.
6. Run strict package validation and package-mode contract preflight.

Phase 1 succeeds only when the package is technically valid and all identity,
package-derivation receipt, physical-output, and semantic checks are internally
consistent.

Canonical receipt count and exact-source closure are diagnostics. Empty exact
source evidence must remain visible, but it does not create a second apply
authority. The operator decision is read only from reports/operator_summary.json;
the apply command independently recomputes package integrity and parity.
Source-quality fields remain observation-only through final review.

### Phase 2: Guarded runtime apply

Before apply:

1. Resolve the active ShadowPriest runtime targets beneath the configured
   HearthRanger root.
2. Record a deterministic pre-apply hash inventory without modifying the
   runtime.
3. Re-read the freshly generated `operator_summary.json`.

Apply is permitted only when the current package reports all of the following:

- `technical_status=VALID_PACKAGE`;
- `runtime_load_safe=true`;
- `runtime_apply_mode=load_safe_apply`;
- `runtime_apply_allowed=true`;
- exact deck identity and target fingerprint match;
- package derivation verifies;
- no blocking package or semantic integrity reason remains.

If any condition fails, Phase 2 ends before `hsconfig apply`.

When every condition passes:

1. Run the explicit guarded `hsconfig apply` command.
2. Require the apply receipt to report
   `runtime_package_match.status=matched`.
3. Run the separate read-only `runtime-match` command against the installed
   package.
4. Record a post-apply hash inventory and reconcile it with the package and
   receipt.

The guarded writer owns rollback if install-integrity verification fails.

## ShadowPriest semantic acceptance

The fresh package must preserve these boundaries:

- Decode to exactly 30 deck cards with zero unresolved identities.
- `SW_448` Darkbishop Benedictus is a start-of-game hero-power-transform
  source, not an inferred opening-hand keep.
- `SW_448` may appear in `Mulligan.json` only when a current exact-deck source
  contains explicit Mulligan or opening-hand evidence.
- The hero-power-transform runtime row is physically owned by `EX1_625t`
  through the curated `hero_power_transform` link.
- The physical `EX1_625t.json` row and its source claim, lifecycle, receipt,
  and linked-owner evidence must reconcile.
- GlobalValues output must exactly match its authority matrix and canonical
  baseline, with no unauthorized overlay.
- Every CardID and Mulligan row must be supported, physically emitted, and
  represented in the runtime-surface ledger.
- Combo output is allowed only for an exact ordered combo claim backed by a
  matching live-verified strategic receipt. Otherwise Combo remains absent
  with a visible reason.
- Unsupported structured condition atoms, wrong-owner rows, and wrong-surface
  claims are suppressed rather than partially emitted.

The supplied Hearthstone and HDT deck IDs are operator identity metadata. They
are checked against available local/runtime metadata when such a supported
surface exists; they are not passed through invented CLI flags.

## Failure handling

- Repository behind or dirty: stop before generation.
- Live source unavailable, inexact, or not verified: retain and report the
  diagnostic package-quality evidence; it does not replace the operator
  decision.
- Exact deck or package-derivation receipt mismatch: validation failure and no
  apply.
- Package contract or physical ledger mismatch: validation failure and no
  apply.
- Operator gate blocked: no runtime write, even when the package is otherwise
  load-safe.
- Apply-time runtime mismatch: require guarded rollback and report the failed
  receipt.
- No failure may be converted into a manual copy or an alternate write path.

## Verification and deliverables

The run produces:

- a new dated ShadowPriest output directory;
- source acquisition and receipt artifacts;
- the validated `04_package`;
- a concise operator verdict derived from `operator_summary.json`;
- pre/post runtime hash evidence only when Phase 2 is authorized;
- an apply receipt and read-only runtime-match result only when apply occurs.

Final reporting must distinguish:

- package validity;
- source/apply authority;
- runtime installation integrity;
- in-client behavior;
- gameplay optimality.

`RUNTIME_SAMPLED` and `GAMEPLAY_OPTIMALITY` remain `NOT_PROVEN` after this
pre-run workflow, including after a successful runtime match.
