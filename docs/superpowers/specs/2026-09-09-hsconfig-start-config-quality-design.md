# HSConfig start-config quality upgrade

Status: written specification approved by the user; implementation planning authorized.
Date: 2026-09-09
Audit baseline: `3f360924b9be94eb9656fc4e3079077e702b7817`.

## Objective and scope

Give Codex a deck name and exact deck code and receive one carefully reasoned,
independently reviewed start configuration. Preserve the existing enabled live
policy, preview override, guarded apply, and exact runtime match. The user gets
no new setup, research command, candidate selection, or provider credentials.

This is a focused amendment to the [Codex-first design](../../architecture/codex-first-live-start-config.md).
It replaces only the intake, context, decision-justification, compatibility, and
reporting details specified below. Existing publication, authorization, recovery,
source-authority, and release boundaries otherwise remain in force.

The claim is the best practical start configuration supported by available
facts and explicit reasoning, not proven optimal play or improved win rate.
This specification records design intent, not completed implementation or a
request to start a live run. Implementation planning follows written-spec review.

## Findings addressed

| Audit finding | Required change | Acceptance evidence |
| --- | --- | --- |
| Normal preparation acquires no strategic guides. | Add bounded discovery and verified acquisition before final context sealing. | The normal helper route carries acquired evidence into the lead and reviewer context. |
| Relevant card facts are omitted. | Project a compact, richer metadata map from one captured identity/data snapshot. | Stats, requirements, and relevant linked-card facts survive capture, sealing, and readback. |
| Sideboards disappear from the LLM context. | Preserve exact sideboard memberships separately from card metadata and main-deck memberships. | Owner, index, CardID, and count round-trip without becoming extra main-deck cards. |
| Mulligan-only candidates fail the material-intent gate. | Count valid, nonempty Mulligan decisions as runtime intent. | A justified Mulligan-only candidate passes; an empty candidate and conflicting rules still fail. |

These findings concern information quality and a policy restriction. They do not
invalidate the existing digest bindings, independent-review gate, or guarded writer.

## 1. Intake and bounded research

The internal sequence is:

`deck input -> identity/data capture -> DISCOVERY_REQUIRED -> complete-research -> INPUT_FROZEN -> candidate -> independent review -> validate/apply/match`

`prepare` first validates the bound operator profile and captures deck identity,
card data, baseline, and date. It then returns an identity-bound acquisition
request in the new `DISCOVERY_REQUIRED` state instead of prematurely reporting
`INPUT_FROZEN`. The request contains the run identity, deck fingerprint, captured
input digest, at most two search queries, acquisition limits, and its self-digest.
Queries use class, format, and distinctive cards; a user label such as "MyDeck"
does not serve as the only search identity.

Codex uses its available search capability and returns a small untrusted URL
shortlist. Add the internal helper phase `complete-research`, taking the existing
session-root and draft-path arguments. Its closed draft contains only
`acquisition_request_sha256`, `urls`, and `discovery_outcome`. The latter is
`completed`, `unavailable`, or `budget_exhausted`: an orchestration observation,
not source authority. No caller-supplied text, authority labels, destination
paths, or runtime permissions are accepted in this draft.

The controller checks the request binding, validates at most three distinct
public HTTP(S) page URLs, fetches them through the existing source-acquisition
path, and derives evidence and canonical receipts through the existing builders.
Existing public-source network restrictions remain enforced, including on
redirects. A search result or supplied URL alone is never verified evidence.

Limits are at most two search calls and three acquired pages, with a 30-second
total controller page-acquisition budget and a 10-second per-request ceiling.
Search-provider latency and LLM reasoning are not covered by a promise that the
whole run finishes in 30 seconds. No recursive crawling or blind retry loop is
added. The page-acquisition deadline starts immediately before its first fetch.
Consumed attempts and that deadline persist across resumptions; resuming does not
replenish the budget or create another run automatically.

The helper/skill contract explicitly gains this internal continuation; the user
still gives one prompt. Lead and reviewer dispatch occur only after completed
acquisition, validated evidence projection, and final `INPUT_FROZEN` sealing.
An empty shortlist is valid and continues with a visible limitation.

Reuse `source_candidate_plan`, `source_acquisition`, `source_autopilot`, and the
canonical source builders. These components do not already implement generic
web discovery; the new Codex/controller handoff supplies that missing boundary.

## 2. One identity and card-data snapshot

Parse deckstring DBFs, counts, hero, and sideboard relationships before resolving
CardIDs. Resolve them against one captured full card dataset, deriving the
collectible view from that same dataset. Record its content digest, acquisition
date, and upstream version when supplied. Do not mix local library identity data
with separately fetched "latest" full and collectible data in a new run.

An unresolved or conflicting required identity stops before candidate creation.
Never substitute a similarly named card or silently use stale data. Existing
captured data stays fixed during research and resume; this adds within-run reuse,
not a persistent cache framework or automatic fallback to historical snapshots.

Use one deduplicated metadata map keyed by exact CardID, plus separate relations:

- Main-deck memberships retain exact multiplicities and main-card dispositions.
- Sideboard memberships retain owner CardID, sideboard index, member CardID, count,
  and any repeated membership; sharing a card identity does not merge memberships.
- Linked-entity edges retain exact owner, target, and relation kind. Include
  explicitly identified choices, transforms, hero powers, and rewards needed to
  understand the deck, without walking arbitrary or random generated-card pools.

Metadata includes DBF identity, name, current text, type, cost, attack, health,
durability, tribes, classes, spell school, mechanics, and relevant play requirements
when applicable. The same useful facts are available for sideboard and linked
entities. Omit artwork, flavour text, and unrelated localization data.

Unknown and inapplicable fields remain distinguishable; missing decision-relevant
facts are visible limitations, never invented zeroes. Unresolved required identity
is a hard stop. An optional unknown fact may support a limited-confidence decision
only with an explicit assumption and independent review. Unknown/random linked
targets remain visible as unresolved relations, not fabricated exact cards.
Richer context grants no new runtime-owner or runtime-syntax permission.

## 3. Evidence and strategic decisions

Add a closed compact context-evidence collection for useful guide observations
that do not fit existing lowerable claim kinds. Each observation records source
URL, fetched-content identity, retrieval date, source update date when known,
short supporting text, relevant CardIDs, applicability, and limitations/conflicts.
Applicability distinguishes exact-list, archetype-only, and card-only support.

Only the canonical acquisition/receipt path can establish `live_verified` or exact
strategic guide authority. Existing guide gates and diagnostic-source restrictions
are unchanged. Archetype observations and model inference can inform the optimized
candidate but cannot become exact guide claims or `SOURCE_BACKED_STRONG` evidence.
Web content is untrusted data, never orchestration instructions. Retrieval today
does not prove that a guide was updated today or matches the submitted deck.

No useful exact guide, search unavailable, page acquisition failed, and budget
exhausted remain distinct visible outcomes. Continue with current card facts,
applicable weaker evidence, and declared assumptions when the existing optimized
route permits it; expose limited evidence and do not claim that no guide exists.
Failures of identity, document validity, or write authorization still stop.

Create one candidate and use the existing independent reviewer with at most two
targeted revisions. No tournament, second strategy pipeline, or quality-score gate.
The reviewer assesses strategy, Mulligan, relevant interactions, supported runtime
expression, unnecessary overrides, and evidence/assumptions against the sealed facts.

A valid nonempty Mulligan set can establish material runtime intent without a
GlobalValues, CardID, or Combo change. Empty intent remains invalid; count, selector,
conflict, rationale, and complete physical-main-card disposition checks remain.
An exact already-installed package remains `ALREADY_LIVE`, not a reason to invent
changes. Do not claim to detect every semantically default-equivalent rule statically.

All 38 GlobalValues keys remain profiled. Add a versioned
`globalvalues_justifications` map whose keys exactly equal the controller-derived
semantically changed keys. Each entry explains the intended deck decision, why the
baseline is insufficient, and either references sealed evidence or explicitly
declares inference. Unchanged keys require no repetitive explanation. Do not add
reserved pseudo-rule IDs or parse free prose to manufacture evidence bindings.
Existing value ranges and copy-baseline-only restrictions remain authoritative.

Expose controller-derived before/after GlobalValues, configured/delegated main
cards, rule owners and surfaces, support references, assumptions, and duplicate
or conflict findings to the reviewer. These facts are digest-bound diagnostics,
not a second apply authority. Validators establish coverage and consistency;
the independent reviewer still judges the quality of the reasoning.

## 4. Versioning and continuation

Use explicit, closed version combinations rather than accepting arbitrary mixtures:

| Route | Session | Input manifest | Context/candidate/review | Compiler contract |
| --- | --- | --- | --- | --- |
| Existing sealed single-candidate runs | 1 | 1 | 2/2/2 | `hsconfig-live-start-v1` |
| New quality-upgrade runs | 2 | 2 | 3/3/3 | `hsconfig-live-start-v2` |

Legacy schema-1 non-live contracts retain their existing path and are not promoted
into the new live route. The new manifest binds the acquisition result and richer
facts; the new session represents the pre-freeze continuation. Unchanged independent
receipt formats need not be renumbered merely because their enclosing contract changes.

Existing sealed runs retain their original projection, validation, and lowering
semantics through resume, finalize, derivation, and receipt checks. Do not add new
fields, reacquire sources, remap identities, or rewrite historical digests in place.
Dispatch compatibility by the full validated version combination. An unsupported
combination returns an explicit compatibility failure before mutation, never an
automatic regeneration. Pre-freeze resumptions reuse their captured inputs and
remaining budget; finalized or failed historical runs do not restart themselves.

## 5. Output, recovery, and polish

Keep the normal response short: deck name, card coverage, review confidence with
the important limitation, and installation status. Keep human-facing deck names
and output aliases free of SHA suffixes; retain internal digests and immutable
revision identities for correctness and diagnostics.

On failure report the stable error code, current phase, preserved artifact,
remaining revision/acquisition budget where relevant, and runtime-write state
(`no`, `yes`, or `unknown` when genuinely indeterminate). Give one permitted next
action derived from the actual state. Do not recommend finalization for an invalid
terminal review, reset revision budgets, or bypass existing apply-recovery admission.

Technical validation, strategic confidence, source coverage, and installation are
separate facts. Only guarded apply plus exact matching can report `LIVE_AND_MATCHED`.
Neither that status nor local tests proves gameplay improvement or final release
readiness. The operator profile, runtime writer, twelve-deck release catalog,
publication protocol, and canonical release gate are not redesigned here.

Update the embedded and installed skill/helper contract together with the new
continuation before functional acceptance. After that acceptance, polish the
concise quickstart with the verified route, one input example, and honest outcomes.
Remove or mark only directly superseded instructions. GitHub presentation stays
within those documentation changes; pushing, releases, settings, and unrelated
cleanup are not implied by this specification.

## 6. Proportionate acceptance

Use focused regression cases for changed behavior, grouped into this small matrix:

1. Ordinary main deck: current snapshot identity resolution, useful acquired guide
   context, justified changed values, independent review, and complete dispositions.
2. Sideboard/linked deck: exact relations, shared identities, rich entity facts,
   and unchanged runtime-owner restrictions.
3. Thin or unavailable research: empty results, unavailable search, failed page fetch,
   and exhausted budget produce truthful limitations without invented authority.
4. Mulligan-only: valid intent succeeds; empty intent, conflicts, unsupported owners,
   and missing changed-key justifications remain rejected.
5. Compatibility and interruption: old sealed readback/derivation stays unchanged;
   new pending research resumes without refreshed inputs or replenished budgets;
   stale request bindings and mixed versions fail before mutation.

Reuse existing strict validation, review/digest, preview, guarded-apply, and runtime
match checks. Run the affected focused tests and relevant integration checks once
per changed behavior; rerun only after a relevant failure or change. Do not repeat
the full suite as a substitute for specific evidence. Existing mandatory release
checks still apply to any later release; this focused matrix does not replace them.

Finish with one real end-to-end run through the installed skill and actual lead
and reviewer, bounded live sources or explicit fallback, package validation, and
authorized apply/match. Use the existing positively enabled live policy only in an
authorized normal deck invocation; spec approval itself does not start that run.
Keep its private evidence outside Git and the release catalog. A stubbed controller
test is not this proof, and a successful live install is not a gameplay-quality test.

## Exclusions

No provider client, credentials, candidate tournament, replay/log parsing,
post-game tuning, win-rate optimization, persistent cache framework, broad crawler,
arbitrary generated-card recursion, multiple-Combo expansion, new GUI/settings,
unrelated refactor, or extra manual research/review step for normal deck users.
