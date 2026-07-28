# HSConfig Repository and v1.0.0 Cutover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present HSConfig as a concise, public-but-proprietary v1.0.0 product repository with only active documentation, four signed root-history commits, one signed tag, one asset-free release, one protected `main`, and no local or GitHub residue.

**Architecture:** Polish and verify the active tree before any destructive operation. Build the four-commit replacement graph directly with a temporary Git index and `git commit-tree -S`, never a temporary branch. Protect the old remote OID with a short-lived external bundle. Execute every operation from the first reversible GitHub preflight mutation through the canonical final product gate inside one guarded cutover orchestrator with an atomically persisted phase/decision journal and a common recovery path. Perform one OID-bound force-with-lease update, verify exact tree/OID/CI, activate the preflighted GitHub policy, create the signed tag and release, pass final hygiene/inventory/score gates, persist the commit decision, and only then delete the bundle.

**Tech Stack:** Git plumbing (`read-tree`, `write-tree`, `commit-tree -S`, `update-ref`), GitHub CLI/API, PowerShell, SHA-256, pytest policy tests, the canonical release gate.

## Global Constraints

- Work only in `C:\Users\darbo\Documents\HSConfig`.
- Use only branch `main`; create no local or remote side branch and no pull request.
- Complete Tasks 1-5 and pass the release gate before constructing replacement history.
- Do not rewrite `main` without a clean worktree and exact local/remote OID equality.
- Create the temporary source-history bundle outside the repository and hash it.
- Perform exactly one bound update using the recorded value:
  `--force-with-lease=refs/heads/main:$oldOid`.
- Never use unbound `--force`.
- Do not change GitHub settings concurrently with the history push.
- The final tag is one signed annotated `v1.0.0` tag.
- The final GitHub Release is non-draft, non-prerelease, and has no uploaded assets.
- Outputs are local, ignored, untracked, unarchived, and not release assets.
- Public visibility is not secrecy; proprietary wording grants no Open Source license.
- Legal wording is implementation text, not a legal-effect guarantee.
- “No residue” means no reachable old repository refs, GitHub Release or Actions artifacts, extra branches/tags/releases/PRs, or known workspace/product residue. It does not claim deletion of GitHub event history, GitHub Actions logs, external forks/caches, or unreachable Git objects/reflogs.
- Set `$ErrorActionPreference = "Stop"` and run every `git`, `gh`, `python`, and other native command through one `Invoke-CheckedNative` wrapper that throws on any non-zero exit. Raw command snippets below specify arguments and ordering; the orchestrator never invokes them unchecked.

---

### Task 1: Establish Proprietary Product Metadata

**Files:**
- Create: `LICENSE`
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `SECURITY.md`
- Create: `tests/test_repository_governance.py`
- Create: `tests/test_readme_contract.py`

**Required license status:**

```text
Copyright (c) 2026 Teufelsboy. All rights reserved.

This source code is publicly viewable but proprietary. No license is granted
to use, copy, modify, distribute, sublicense, or create derivative works from
this software except with prior written permission from the copyright owner.
```

Add a plain statement that GitHub's platform terms continue to govern platform access and that public visibility does not make the code confidential.

- [ ] **Step 1: Write failing governance tests**

Require:

- `LICENSE` exists and says proprietary and All Rights Reserved;
- `pyproject.toml` contains `LicenseRef-Proprietary`;
- README shows `Publicly visible — proprietary — All Rights Reserved`;
- owner/year are consistent;
- CONTRIBUTING rejects external code contributions and directs bug reports to Issues;
- SECURITY provides a real private GitHub vulnerability-reporting URL;
- no file describes the project as Open Source.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_repository_governance.py tests/test_readme_contract.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement the metadata**

In `pyproject.toml` use:

```toml
license = "LicenseRef-Proprietary"
authors = [{name = "Teufelsboy"}]
classifiers = [
  "License :: Other/Proprietary License",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
]
```

The README order is:

1. one-sentence product description;
2. proprietary status;
3. scope and non-goals;
4. installation;
5. one normal `configure` command;
6. verification command;
7. links to operator, architecture, contract, security, and contribution docs.

- [ ] **Step 4: Use a concrete private reporting path**

Link SECURITY to:

```text
https://github.com/Teufelsboy/HSConfig/security/advisories/new
```

State that raw logs, replays, deckcodes outside the curated catalog, runtime XML, and unredacted packages must not be filed publicly.

- [ ] **Step 5: Run GREEN**

```powershell
python -m pytest tests/test_repository_governance.py tests/test_readme_contract.py -q -p no:cacheprovider
python -m build
```

- [ ] **Step 6: Commit and obtain owner review of rights wording**

```powershell
git add LICENSE pyproject.toml README.md CONTRIBUTING.md SECURITY.md tests/test_repository_governance.py tests/test_readme_contract.py
git commit -S -m "docs: establish proprietary product metadata"
git push origin main
```

Record the approval in the implementation report before the history cutover. Do not encode a legal-effect assertion in code or tests.

---

### Task 2: Curate the Active Documentation Tree

**Files:**
- Create: `docs/architecture/overview.md`
- Create: `docs/architecture/transaction-model.md`
- Create: `docs/contracts/pre-run-contract.md`
- Create: `docs/contracts/evidence-and-disposition.md`
- Create: `docs/contracts/release-gate.md`
- Create: `docs/contracts/v1.0.0-release-notes.md`
- Modify: `docs/operator/README.md`
- Modify active files under: `docs/operator/`
- Modify: `AGENTS.md`
- Modify tracked tests containing literal local absolute paths, including `tests/test_io_and_models.py`
- Create: `scripts/check_publishable_tree.py`
- Create: `tests/test_publishable_tree.py`
- Delete from final curated tree through the cutover manifest:
  - `docs/superpowers/`
  - `docs/research/`
  - `docs/history/`
  - obsolete operator documents without a current README link

**Final allowed top-level tree:**

```text
.github/
docs/architecture/
docs/contracts/
docs/operator/
scripts/
src/
tests/
.gitignore
AGENTS.md
CONTRIBUTING.md
constraints-ci.txt
LICENSE
pylock.toml
README.md
SECURITY.md
pyproject.toml
```

- [ ] **Step 1: Write the failing publishable-tree test**

Require only the allowed top-level entries and fail for:

```text
.superpowers
docs/superpowers
docs/research
docs/history
outputs
build
dist
.pytest_cache
.ruff_cache
.codex-qa-*
*.bak
*.backup
Power.log
*.hdtreplay
*.hsreplay
```

- [ ] **Step 2: Write documentation link and authority tests**

Every public doc link must resolve. Only the operator README may define the normal command path, and every secondary doc links back to it. No historical document may be reachable in the curated tree.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest tests/test_publishable_tree.py tests/test_operator_docs_contract_policy.py tests/test_contract_spine_sentinel_docs.py -q -p no:cacheprovider
```

- [ ] **Step 4: Write concise active architecture and contract docs**

Project the approved design and implemented behavior into the five named files. Do not copy implementation-plan narration, review scores, brainstorming, personal paths, or future tense. Document actual interfaces, invariants, commands, and failure semantics only.

- [ ] **Step 5: Scrub tracked local absolute paths**

Replace the repository-specific absolute path in `AGENTS.md` with a repository-root-relative rule. Convert tests that need Windows-path behavior to construct synthetic components at runtime or use `tmp_path`; no tracked file may contain a literal user/profile/workspace path. The scan allowlist may contain only a test identifier and reason, never a real or synthetic absolute path literal.

- [ ] **Step 6: Build the final path allowlist**

`scripts/check_publishable_tree.py` supports:

```powershell
python scripts/check_publishable_tree.py --root . --mode working-pre-cutover --json
python scripts/check_publishable_tree.py --root . --mode candidate-index --index-file $temporaryIndex --json
python scripts/check_publishable_tree.py --root . --mode final --json
```

`working-pre-cutover` allows only the named historical documentation paths while still rejecting secrets/evidence/artifacts. Candidate-index mode validates the curated candidate before any ref update. Final mode permits no historical exception.

- [ ] **Step 7: Run GREEN**

```powershell
python -m pytest tests/test_publishable_tree.py tests/test_operator_docs_contract_policy.py tests/test_contract_spine_sentinel_docs.py -q -p no:cacheprovider
python scripts/check_publishable_tree.py --root . --mode working-pre-cutover --json
```

- [ ] **Step 8: Commit active docs**

```powershell
git add docs/architecture docs/contracts docs/operator AGENTS.md tests scripts/check_publishable_tree.py
git commit -S -m "docs: curate active product documentation"
git push origin main
```

Historical directories remain present until the replacement history is built; only `working-pre-cutover` permits that exact reviewed exception. Candidate-index and final gates never permit it.

---

### Task 3: Add Minimal GitHub Community and Issue Surfaces

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug.yml`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/CODEOWNERS`
- Create: `.github/dependabot.yml` only if it can disable version-update PRs; otherwise do not create it
- Create: `tests/test_github_metadata.py`

**Bug form requirements:**

```text
name: Redacted bug report
labels: ["bug"]
required version field
required sanitized reproduction field
required expected/actual behavior fields
required sensitive-data confirmation checkbox
no free-form file upload request
```

- [ ] **Step 1: Write failing metadata tests**

Parse every YAML file and require:

- blank issues disabled;
- security contact link points to the private advisory URL;
- bug form warns against deckcodes, logs, replays, runtime XML, and unredacted packages;
- CODEOWNERS assigns `*` to `@Teufelsboy`;
- no feature-request or contribution template;
- no Dependabot configuration that opens automatic version PRs.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_github_metadata.py -q -p no:cacheprovider
```

- [ ] **Step 3: Implement minimal metadata**

Use `.github/ISSUE_TEMPLATE/config.yml`:

```yaml
blank_issues_enabled: false
contact_links:
  - name: Private security report
    url: https://github.com/Teufelsboy/HSConfig/security/advisories/new
    about: Report vulnerabilities privately without runtime evidence.
```

- [ ] **Step 4: Run GREEN and YAML parse**

```powershell
python -m pytest tests/test_github_metadata.py -q -p no:cacheprovider
python -c "import pathlib,yaml; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in pathlib.Path('.github').rglob('*.yml')]"
```

- [ ] **Step 5: Commit**

```powershell
git add .github/ISSUE_TEMPLATE .github/CODEOWNERS tests/test_github_metadata.py
git commit -S -m "chore: add minimal repository community files"
git push origin main
```

---

### Task 4: Freeze the Exact Curated-Tree Manifest

**Files:**
- Create: `scripts/build_curated_history.ps1`
- Create: `scripts/verify_curated_history.ps1`
- Create: `scripts/sync_curated_worktree.ps1`
- Create: `scripts/cutover_v1.ps1`
- Create: `scripts/github_governance.py`
- Create: `tests/test_curated_history_script.py`
- Create: `tests/test_cutover_recovery.py`
- Create: `tests/test_github_governance.py`
- Create during execution and remove before final cutover: `.curated-paths`
- Read: all tracked files

**Four final commit subjects:**

```text
feat: establish the HSConfig pre-run contract engine
feat: add the audited twelve-deck contract catalog
fix: harden atomic publication and pre-run authority
chore: establish proprietary repository governance
```

- [ ] **Step 1: Write script safety tests**

Parse the PowerShell AST and require:

- no `git checkout`, `git switch`, `git branch`, or `git push --force`;
- a caller-supplied expected old OID;
- a caller-supplied temporary index path outside `.git`;
- `git commit-tree -S` for all four commits;
- parent count `0,1,1,1`;
- no `git update-ref refs/heads/main` before validation;
- exact subject assertions;
- cleanup in `finally`.

Also require a fault-injection matrix for the guarded cutover orchestrator. Inject failure after each of these boundaries:

- reversible GitHub preflight;
- candidate verification;
- bundle creation;
- final lease check;
- remote `main` update;
- local ref/worktree synchronization;
- exact-OID CI;
- ruleset activation;
- tag creation;
- release creation.
- final cache cleanup;
- canonical final product gate;
- persisted commit decision;
- bundle-directory deletion.
- final sibling-journal deletion.

For every injected failure before the persisted `commit` decision, prove that `scripts/cutover_v1.ps1 -Recover` or the in-process `finally` handler:

- restores the complete GitHub snapshot and verifies parity;
- deletes a partially created release and local/remote `v1.0.0` tag when present;
- restores remote `main` with the exact `$newTip` lease when it advanced;
- restores local `main`, index, and worktree to `$oldOid`;
- leaves the external bundle verified and in place when bundle creation had completed; expects no bundle before that boundary;
- leaves no inactive/active cutover ruleset that was absent from the snapshot;
- returns a non-zero exit status and does not retry the cutover.

For failure after the atomically persisted `commit` decision, prove the opposite recovery direction: verify the already final repository/settings/tag/release state, finish the idempotent bundle-directory cleanup, and preserve the final release. A hard kill immediately before and immediately after the decision write must deterministically choose rollback and roll-forward respectively.

Exercise actual non-zero exits from fake `git`, `gh`, and `python` executables in addition to injected PowerShell exceptions. A native failure must enter the same compensation path.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest tests/test_curated_history_script.py tests/test_cutover_recovery.py tests/test_github_governance.py -q -p no:cacheprovider
```

`tests/test_github_governance.py` uses a fake API transport to require exact request methods, endpoints, payloads, response verification, snapshot completeness, inactive-before-cutover ruleset state, final activation, and reverse-order compensation.

`tests/test_cutover_recovery.py` uses fake Git/GitHub/process adapters. It runs the full failure matrix and asserts the same restored end state regardless of the failing boundary.

The PowerShell implementation centralizes native execution:

```powershell
function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )
    $output = @(& $FilePath @ArgumentList 2>&1)
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "native_command_failed:${FilePath}:exit=$exitCode"
    }
    return $output
}
```

Do not interpolate captured command output into exceptions because it may contain sensitive API or signing diagnostics. Recovery catches each compensation failure, attempts all remaining independent safe compensations, then verifies the complete target state. If parity is not restored, it leaves the journal at `decision="rollback"` and exits non-zero so a later explicit `-Recover` can retry.

- [ ] **Step 3: Build cumulative trees from recorded milestone blobs**

Record these exact source OIDs during the preceding plans:

1. `engine_milestone_oid`: after Master Sequence step 5, before transactional publication Tasks 2-8;
2. `hardening_milestone_oid`: after Plan 04 and its green CI;
3. `governance_milestone_oid`: clean current `HEAD` after Tasks 1-4 of this plan.

The script constructs trees without changing the working index:

1. read `engine_milestone_oid`, prune non-curated paths and the explicit catalog resource/test list;
2. read `engine_milestone_oid`, prune only non-curated paths, thereby adding the catalog;
3. read `hardening_milestone_oid`, prune non-curated paths, thereby applying actual hardening blobs including modifications to existing files;
4. read `governance_milestone_oid`, prune non-curated paths, thereby applying final governance/docs.

This uses historical blob states for modified files; it does not pretend that final path-only groups can reconstruct earlier code. Each tree is cumulative, and the fourth tree exactly equals the final curated path manifest.

`scripts/cutover_v1.ps1` is the sole operator entry point after the first GitHub mutation. It implements the sequence documented in Tasks 5-8 plus Task 9 Steps 1-3 as one `try/catch/finally` transaction. Its recovery mode reconstructs state from the immutable graph file, the snapshotted GitHub inventory, the bundle when present, the atomically written cutover journal, and current local/remote refs; it does not depend on shell-local variables surviving.

Before preflight, create the journal as a sibling of, never a child of, the deletable state directory: `<temp>/hsconfig-cutover-<32hex>.journal.json` beside `<temp>/hsconfig-cutover-<32hex>/`. It contains immutable old/new OIDs, graph/snapshot identities, the exact state-directory path, and `decision="rollback"`. Every phase transition is a same-directory write-through temporary file followed by atomic replace; the envelope includes canonical payload bytes plus `payload_sha256`, and the loader rejects a digest mismatch or impossible phase transition. Only after Task 9 Step 3 passes does the orchestrator atomically persist `decision="commit"`. Until that durable decision, every terminating error invokes rollback. After it, `-Recover -JournalPath <absolute path>` verifies and rolls forward through external-state cleanup without removing the release. The journal remains present throughout recursive bundle-directory deletion and is removed only after that directory is proven absent. `Invoke-CheckedNative` captures output where needed, checks `$LASTEXITCODE` after every native invocation, and throws a structured phase error on non-zero.

- [ ] **Step 4: Use a temporary index, not a branch**

Core plumbing:

```powershell
$env:GIT_INDEX_FILE = $temporaryIndex
git read-tree $engineMilestoneOid
git rm -r --cached --ignore-unmatch --pathspec-from-file=$prunePathFile
$tree1 = git write-tree
$commit1 = (git commit-tree -S $tree1 -m "feat: establish the HSConfig pre-run contract engine").Trim()
```

For commits 2-4, `git read-tree` the required milestone OID, apply the exact prune manifest, write the tree, and use `git commit-tree -S $treeN -p $previousCommit -m $subject`. Commit signatures make commit OIDs non-reproducible; require deterministic tree OIDs, create the signed graph exactly once, then record and verify its commit OIDs.

- [ ] **Step 5: Validate the detached graph before any ref change**

`verify_curated_history.ps1` must check:

- exactly four commits from new tip to root;
- exact subjects and parent shape;
- all commits have valid signatures;
- final tree equals the working curated-tree hash;
- no disallowed path;
- no absolute local path, secret, private evidence, or generated output;
- the candidate index passes `check_publishable_tree --mode candidate-index`;
- a detached candidate under ignored `.cutover-candidate/` inside this repository passes `scripts/check_release_gate.py --tree-mode candidate` against the already verified real `outputs/` root.

The candidate is detached, creates no branch, remains inside the mandated repository workspace, and is removed after verification.

- [ ] **Step 6: Implement exact local worktree synchronization**

`sync_curated_worktree.ps1` computes `old tracked paths - new tracked paths`, then for every file requires:

- resolved path remains below the repository root;
- no path component is a reparse point;
- current `git hash-object` equals the blob at `oldOid:path`;
- the path is absent from `newTip`.

Only then may it remove that exact file with `Remove-Item -LiteralPath`; it prunes explicitly enumerated empty directories afterward. Any modified, unknown, or reparse path fails closed. Its dry-run deletion manifest is reviewed before the push.

- [ ] **Step 7: Run GREEN safety tests**

```powershell
python -m pytest tests/test_curated_history_script.py tests/test_cutover_recovery.py tests/test_github_governance.py -q -p no:cacheprovider
```

- [ ] **Step 8: Commit the construction tooling**

```powershell
git add scripts/build_curated_history.ps1 scripts/verify_curated_history.ps1 scripts/sync_curated_worktree.ps1 scripts/cutover_v1.ps1 scripts/github_governance.py tests/test_curated_history_script.py tests/test_cutover_recovery.py tests/test_github_governance.py
git commit -S -m "build: add guarded curated-history tooling"
git push origin main
```

- [ ] **Step 9: Record governance milestone and create the one signed graph**

```powershell
$governanceMilestoneOid = git rev-parse HEAD
$cutoverStateDir = Join-Path $env:TEMP ("hsconfig-cutover-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $cutoverStateDir | Out-Null
$graphStatePath = Join-Path $cutoverStateDir "curated-graph.json"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build_curated_history.ps1 -ExpectedOldOid $governanceMilestoneOid -EngineMilestoneOid $engineMilestoneOid -HardeningMilestoneOid $hardeningMilestoneOid -GovernanceMilestoneOid $governanceMilestoneOid -Json |
    Set-Content -LiteralPath $graphStatePath -Encoding utf8
$graphState = Get-Content -LiteralPath $graphStatePath -Raw | ConvertFrom-Json
$newTip = $graphState.new_tip_oid
$graphStateSha256 = (Get-FileHash -Algorithm SHA256 $graphStatePath).Hash.ToLowerInvariant()
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_curated_worktree.ps1 -OldOid $governanceMilestoneOid -NewTipOid $newTip -DryRun
```

This is the only `commit-tree -S` run. It creates unreachable Git objects but changes no ref. All later tasks load the hashed graph state and only verify/push those exact OIDs.

---

### Task 5: Pass the Irreversible Cutover Safety Gate

**Files:**
- Modify: none
- Create outside repository: cutover journal, GitHub settings snapshot, temporary Git bundle, and SHA-256 sidecar

- [ ] **Step 1: Verify clean sole-main state**

```powershell
git fetch origin main --prune --tags
$oldOid = git rev-parse HEAD
$remoteOid = git rev-parse origin/main
if ($oldOid -ne $remoteOid) { throw "local_remote_oid_mismatch" }
if (git status --porcelain) { throw "worktree_not_clean" }
if ((git branch --format="%(refname:short)") -ne "main") { throw "local_branch_inventory_invalid" }
$remoteBranches = @(git ls-remote --heads origin | ForEach-Object { ($_ -split "`t")[1] })
if (($remoteBranches -join ",") -ne "refs/heads/main") { throw "remote_branch_inventory_invalid" }
if ((gh pr list --repo Teufelsboy/HSConfig --state open --json number | ConvertFrom-Json).Count -ne 0) { throw "open_pr_exists" }
```

- [ ] **Step 2: Verify tag and release inventories before cutover**

Require no existing `v1.0.0` tag/release and record any unrelated tag or release as a blocker:

```powershell
git tag --list
gh release list --repo Teufelsboy/HSConfig --limit 100 --json tagName
gh api "repos/Teufelsboy/HSConfig/actions/artifacts?per_page=1" --jq .total_count
```

Expected: tag and release inventories empty and Actions artifact `total_count` equals zero. Any pre-existing Actions artifact is a cutover blocker; the implementation does not silently delete unknown remote artifacts.

- [ ] **Step 3: Snapshot and preflight every GitHub mutation**

The operator starts the guarded interval once:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/cutover_v1.ps1 -RepoRoot (Resolve-Path .) -Repository Teufelsboy/HSConfig -GraphStatePath $graphStatePath -GraphStateSha256 $graphStateSha256 -OutputsRoot (Resolve-Path outputs)
```

Inside that orchestrator, Step 3 begins with:

```powershell
$cutoverJournalPath = "$cutoverStateDir.journal.json"
# Write-AtomicCutoverJournal validates the previous phase, canonicalizes the
# payload, embeds payload_sha256, flushes, and atomically replaces the journal.
Write-AtomicCutoverJournal -Path $cutoverJournalPath -Decision rollback -Phase prepared -StateDirectory $cutoverStateDir -OldOid $oldOid -NewTip $newTip -GraphSha256 $graphStateSha256
$githubSnapshotPath = Join-Path $cutoverStateDir "github-settings-before.json"
python scripts/github_governance.py snapshot --repo Teufelsboy/HSConfig --out $githubSnapshotPath
$githubSnapshotSha256 = (Get-FileHash -Algorithm SHA256 $githubSnapshotPath).Hash.ToLowerInvariant()
Write-AtomicCutoverJournal -Path $cutoverJournalPath -Decision rollback -Phase snapshotted -SnapshotSha256 $githubSnapshotSha256
$githubPreflight = python scripts/github_governance.py preflight --repo Teufelsboy/HSConfig --snapshot $githubSnapshotPath --create-inactive-ruleset --json | ConvertFrom-Json
$inactiveRulesetId = $githubPreflight.ruleset_id
Write-AtomicCutoverJournal -Path $cutoverJournalPath -Decision rollback -Phase preflighted -InactiveRulesetId $inactiveRulesetId
```

The script uses and verifies these exact surfaces:

```text
GET/PATCH /repos/Teufelsboy/HSConfig
GET/PUT /repos/Teufelsboy/HSConfig/topics
GET/PUT/DELETE /repos/Teufelsboy/HSConfig/vulnerability-alerts
GET/PUT/DELETE /repos/Teufelsboy/HSConfig/automated-security-fixes
GET/PUT/DELETE /repos/Teufelsboy/HSConfig/private-vulnerability-reporting
GET/PATCH /repos/Teufelsboy/HSConfig security_and_analysis
GET/PUT /repos/Teufelsboy/HSConfig/actions/permissions
GET/PUT /repos/Teufelsboy/HSConfig/actions/permissions/selected-actions
GET /repos/Teufelsboy/HSConfig/collaborators?affiliation=direct
GET/POST /repos/Teufelsboy/HSConfig/rulesets
GET/PATCH/DELETE /repos/Teufelsboy/HSConfig/rulesets/{ruleset_id}
```

The tested desired payloads are:

```json
{
  "repository": {
    "description": "Deterministic pre-run HearthRanger VisionAI CustomConfig generator with audited contracts.",
    "has_issues": true,
    "has_projects": false,
    "has_wiki": false,
    "has_discussions": false,
    "allow_squash_merge": true,
    "allow_merge_commit": false,
    "allow_rebase_merge": false,
    "allow_auto_merge": false,
    "delete_branch_on_merge": true,
    "web_commit_signoff_required": false,
    "security_and_analysis": {
      "secret_scanning": {"status": "enabled"},
      "secret_scanning_push_protection": {"status": "enabled"}
    }
  },
  "topics": ["hearthstone", "hearthranger", "visionai", "configuration", "python"],
  "actions_permissions": {
    "enabled": true,
    "allowed_actions": "selected"
  },
  "selected_actions": {
    "github_owned_allowed": true,
    "verified_allowed": false,
    "patterns_allowed": []
  },
  "ruleset": {
    "name": "main-linear-signed",
    "target": "branch",
    "enforcement": "disabled",
    "bypass_actors": [],
    "conditions": {
      "ref_name": {
        "include": ["refs/heads/main"],
        "exclude": []
      }
    },
    "rules": [
      {"type": "deletion"},
      {"type": "non_fast_forward"},
      {"type": "required_linear_history"},
      {"type": "required_signatures"}
    ]
  }
}
```

Preflight applies the desired reversible repository/security/Actions settings, explicitly disables automated security-fix PRs, requires no direct write/admin collaborator other than `Teufelsboy`, creates the exact final ruleset payload with `enforcement=disabled`, then reads every field back. Reverse-order restoration uses PUT or DELETE according to each snapshotted boolean state, restores automated security fixes with PUT when previously enabled, and deletes the newly created ruleset by item ID. On any failure it verifies full snapshot parity before aborting. No platform limitation may be waived while still claiming the final gate.

This is the mutation boundary. From this command through Task 9 Step 3, the implementation runs only inside `scripts/cutover_v1.ps1`; the remaining command blocks specify its ordered internal behavior and are not independent operator commands. The orchestrator wraps the whole interval in one common `try/catch/finally`. Any error before the durable `commit` decision—whether candidate verification, bundle handling, push, local synchronization, CI, settings activation, tag, release, cleanup, score, or final inventory—runs the same idempotent rollback routine. If the process is killed before `finally`, the next invocation must be `scripts/cutover_v1.ps1 -Recover`; recovery reads and validates the journal and discovers any cutover-created ruleset by comparing the current ruleset inventory with the snapshot.

- [ ] **Step 4: Build and verify the candidate tree before the cutover**

```powershell
$graphState = Get-Content -LiteralPath $graphStatePath -Raw | ConvertFrom-Json
if ((Get-FileHash -Algorithm SHA256 $graphStatePath).Hash.ToLowerInvariant() -ne $graphStateSha256) { throw "curated_graph_state_changed" }
$newTip = $graphState.new_tip_oid
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_curated_history.ps1 -NewTipOid $newTip -ExpectedOldOid $oldOid -OutputsRoot (Resolve-Path outputs)
python scripts/check_publishable_tree.py --root . --mode working-pre-cutover --json
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_curated_worktree.ps1 -OldOid $oldOid -NewTipOid $newTip -DryRun
```

Expected: current behavior gates pass in `working-pre-cutover`; the candidate index/tree passes the final publishable-tree and full release gates against the verified outputs root; the publishable-tree JSON supplies the tracked-file inventory/hash, and that inventory plus the exact local-deletion manifest are reviewed without creating an unmanaged temp file.

- [ ] **Step 5: Create the short-lived external bundle**

```powershell
$bundleDir = $cutoverStateDir
$bundlePath = Join-Path $bundleDir "pre-v1-main.bundle"
git bundle create $bundlePath refs/heads/main
git bundle verify $bundlePath
$bundleHash = (Get-FileHash -Algorithm SHA256 $bundlePath).Hash.ToLowerInvariant()
Set-Content -Encoding ascii -Path "$bundlePath.sha256" -Value "$bundleHash  pre-v1-main.bundle"
```

Verify the resolved bundle path begins with the resolved system temp path and is outside the repository before creating or later deleting it.

- [ ] **Step 6: Record immutable cutover inputs**

Record in the operator transcript:

```text
old local/remote OID
old tree OID
bundle absolute path
bundle SHA-256
curated new tip OID
curated new tree OID
four commit OIDs and signature status
engine, hardening, and governance milestone OIDs
reviewed local-deletion manifest hash
GitHub settings snapshot SHA-256
inactive ruleset ID and verified payload SHA-256
cutover journal path, envelope hash, phase, and rollback decision
```

No push occurs unless all values are present and the rights wording approval from Task 1 is recorded.

---

### Task 6: Construct and Push the Four-Commit Root History

**Files:**
- Modify remote: `refs/heads/main`
- Modify local: `refs/heads/main`
- Create no branch

- [ ] **Step 1: Reverify the already constructed candidate graph**

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/verify_curated_history.ps1 -NewTipOid $newTip -ExpectedOldOid $oldOid -OutputsRoot (Resolve-Path outputs)
```

- [ ] **Step 2: Reconfirm the lease immediately before push**

```powershell
git fetch origin main --prune
if ((git rev-parse origin/main) -ne $oldOid) { throw "remote_main_changed_before_cutover" }
```

- [ ] **Step 3: Perform the only history update**

```powershell
git push origin "$newTip`:refs/heads/main" "--force-with-lease=refs/heads/main:$oldOid"
```

Do not combine settings mutations or tag creation with this command.

- [ ] **Step 4: Verify exact remote OID before changing local main**

```powershell
$pushedOid = (git ls-remote origin refs/heads/main).Split("`t")[0]
if ($pushedOid -ne $newTip) { throw "remote_main_cutover_oid_mismatch" }
git update-ref refs/heads/main $newTip $oldOid
git reset --mixed $newTip
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/sync_curated_worktree.ps1 -OldOid $oldOid -NewTipOid $newTip -Apply -ExpectedManifestSha256 $reviewedDeletionManifestSha256
```

`git reset --mixed` refreshes the index without overwriting working files. The synchronization script then removes only old tracked files proven unchanged and absent from the new tree. Any mismatch stops before tag, settings, or release.

- [ ] **Step 5: Verify local/remote tree and branch inventories**

```powershell
git fetch origin main --prune
if ((git rev-parse HEAD) -ne $newTip) { throw "local_tip_mismatch" }
if ((git rev-parse origin/main) -ne $newTip) { throw "remote_tip_mismatch" }
if ((git rev-parse HEAD^{tree}) -ne $graphState.new_tree_oid) { throw "local_tree_mismatch" }
git branch --format="%(refname:short)"
git ls-remote --heads origin
git log --show-signature --format=fuller --reverse
```

Expected: only `main`; exactly four signed commits with approved subjects.

- [ ] **Step 6: Wait for exact-OID CI**

```powershell
$deadline = [DateTime]::UtcNow.AddMinutes(10)
do {
    $runs = @(gh run list --repo Teufelsboy/HSConfig --commit $newTip --workflow ci.yml --json databaseId,headSha,status,conclusion | ConvertFrom-Json)
    if ($runs.Count -eq 1) { break }
    Start-Sleep -Seconds 5
} while ([DateTime]::UtcNow -lt $deadline)
if ($runs.Count -ne 1) { throw "exact_oid_ci_run_count_invalid" }
$runId = $runs[0].databaseId
gh run watch --repo Teufelsboy/HSConfig $runId --exit-status
gh run view --repo Teufelsboy/HSConfig $runId --json headSha,status,conclusion,jobs
```

Require exact `headSha=$newTip`, terminal success, and jobs `contract`, `test`, `package`, and `security` all successful.

The following is the common compensation contract, not a CI-only special case. Any failure after the preflight mutation and before the journal contains a valid durable `decision="commit"` first removes any partially created release/tag, compensates every GitHub mutation, and then—when `main` advanced—suspends the single successful-path update rule for one explicit emergency rollback:

```powershell
$releaseTags = @((gh release list --repo Teufelsboy/HSConfig --limit 100 --json tagName | ConvertFrom-Json).tagName)
if ($releaseTags -contains "v1.0.0") {
    gh release delete v1.0.0 --repo Teufelsboy/HSConfig --cleanup-tag --yes
} elseif (git ls-remote --tags origin refs/tags/v1.0.0) {
    git push origin ":refs/tags/v1.0.0"
}
if (git tag --list v1.0.0) { git tag -d v1.0.0 }
python scripts/github_governance.py restore --repo Teufelsboy/HSConfig --snapshot $githubSnapshotPath --json
python scripts/github_governance.py verify-snapshot --repo Teufelsboy/HSConfig --snapshot $githubSnapshotPath --json
$currentRemote = (git ls-remote origin refs/heads/main).Split("`t")[0]
if ($currentRemote -eq $newTip) {
    git push origin "$oldOid`:refs/heads/main" "--force-with-lease=refs/heads/main:$newTip"
} elseif ($currentRemote -ne $oldOid) {
    throw "rollback_remote_main_unexpected"
}
$currentLocal = git rev-parse HEAD
if ($currentLocal -eq $newTip) {
    git update-ref refs/heads/main $oldOid $newTip
} elseif ($currentLocal -ne $oldOid) {
    throw "rollback_local_main_unexpected"
}
git read-tree --reset -u $oldOid
git fetch origin main --prune
if ((git rev-parse origin/main) -ne $oldOid) { throw "emergency_rollback_failed" }
if ((git rev-parse HEAD^{tree}) -ne (git rev-parse "$oldOid^{tree}")) { throw "local_rollback_tree_mismatch" }
if (git status --porcelain) { throw "local_rollback_worktree_dirty" }
if (git tag --list v1.0.0) { throw "rollback_local_tag_residue" }
if (git ls-remote --tags origin refs/tags/v1.0.0) { throw "rollback_remote_tag_residue" }
if ((gh release list --repo Teufelsboy/HSConfig --limit 100 --json tagName | ConvertFrom-Json).tagName -contains "v1.0.0") { throw "rollback_release_residue" }
```

Every command is made idempotent by first inspecting current state; the compact block above shows the required end state. Retain the bundle and end the implementation as failed. Do not attempt a second curated cutover in the same run.

---

### Task 7: Prepare Release Material and Verify Remote Capabilities

**Files:**
- Create: `docs/contracts/v1.0.0-release-notes.md` in the final governance commit before Task 6
- Modify no Git ref or release in this task

**Release notes content:**

```markdown
# HSConfig v1.0.0

First stable pre-run release of the guide-aligned HearthRanger VisionAI
configuration generator.

- Audited twelve-deck contract catalog
- Deterministic, full-tree-manifest packages
- Atomic current-output publication
- Crash-safe runtime activation
- Reproducible local and GitHub verification

Gameplay quality is outside the release contract and assumed external.
The repository is publicly visible proprietary software; all rights reserved.
```

- [ ] **Step 1: Confirm the release-note file is already in the curated tree**

```powershell
git show HEAD:docs/contracts/v1.0.0-release-notes.md
```

If missing, the cutover input was invalid. Do not add a fifth commit; restore and rebuild the approved four-tree graph.

- [ ] **Step 2: Verify signing capability without creating a tag**

```powershell
git config --get user.signingkey
git log --show-signature -4 --format="%H %G?"
```

- [ ] **Step 3: Read effective GitHub capabilities before mutation**

```powershell
gh auth status
gh api repos/Teufelsboy/HSConfig
gh api repos/Teufelsboy/HSConfig/actions/permissions
```

- [ ] **Step 4: Reconfirm empty tag/release inventories**

```powershell
git tag --list
gh release list --repo Teufelsboy/HSConfig --limit 100 --json tagName,isDraft,isPrerelease
```

Expected: signing is configured, all four commits verify, required repository-admin APIs are readable, and tag/release inventories remain empty.

---

### Task 8: Harden GitHub Settings, Then Publish v1.0.0

**Files:**
- Modify GitHub repository settings through `gh api`
- Create no repository commit

- [ ] **Step 1: Reverify the snapshotted/preflighted GitHub state**

```powershell
if ((Get-FileHash -Algorithm SHA256 $githubSnapshotPath).Hash.ToLowerInvariant() -ne $githubSnapshotSha256) { throw "github_snapshot_changed" }
python scripts/github_governance.py verify-preflight --repo Teufelsboy/HSConfig --snapshot $githubSnapshotPath --json
```

- [ ] **Step 2: Verify public presentation and topics**

```powershell
gh api repos/Teufelsboy/HSConfig
gh api repos/Teufelsboy/HSConfig/topics
```

- [ ] **Step 3: Enable available security features**

Use `github_governance.py verify-preflight` to require vulnerability alerts, Private Vulnerability Reporting, secret scanning, and push protection enabled, with Dependabot security updates/automated security-fix pull requests disabled. Any unavailable feature fails the final gate; it cannot be accepted away.

- [ ] **Step 4: Restrict Actions**

Require Actions enabled, `allowed_actions=selected`, GitHub-owned Actions allowed, verified-creator and pattern allowances empty, and workflow SHA pinning enforced by the repository CI policy test.

- [ ] **Step 5: Create the post-cutover `main` ruleset**

Activate the exact inactive ruleset created during preflight:

- deletion blocked;
- non-fast-forward updates blocked;
- linear history required;
- signed commits required after all four root commits verify; tag creation follows the verified ruleset;
- no bypass actor;
- no pull-request requirement;
- no pre-merge status-check requirement.

Before activation, require the direct-collaborator inventory to contain no write/admin actor other than `Teufelsboy`; repository access control, not a ruleset bypass, limits writers. Run:

```powershell
python scripts/github_governance.py activate --repo Teufelsboy/HSConfig --snapshot $githubSnapshotPath --ruleset-id $inactiveRulesetId --json
```

Save the returned JSON in the operator transcript, not the repository.

- [ ] **Step 6: Verify effective settings**

```powershell
gh api repos/Teufelsboy/HSConfig
gh api repos/Teufelsboy/HSConfig/topics
gh api repos/Teufelsboy/HSConfig/actions/permissions
gh api repos/Teufelsboy/HSConfig/rulesets
gh api repos/Teufelsboy/HSConfig/private-vulnerability-reporting
gh api repos/Teufelsboy/HSConfig/vulnerability-alerts --include
```

Confirm public visibility, description, topics, issue-only community posture, security features, Action policy, and the one active ruleset.

If any Step 1-9 action fails before the durable commit decision, invoke the common compensation contract from Task 6, including deletion of a partially created tag/release, full GitHub snapshot restoration, and source-history rollback when `main` advanced. Do not leave partial settings or release artifacts. Task 8 completion alone never writes the commit decision; the canonical final gates in Task 9 must still pass.

- [ ] **Step 7: Create and verify the single signed tag**

```powershell
git tag -s v1.0.0 -m "HSConfig v1.0.0" $newTip
git verify-tag v1.0.0
if ((git rev-parse 'v1.0.0^{commit}') -ne $newTip) { throw "local_tag_target_mismatch" }
git push origin refs/tags/v1.0.0
$peeledTagRows = @(git ls-remote origin 'refs/tags/v1.0.0^{}')
if ($peeledTagRows.Count -ne 1) { throw "remote_peeled_tag_count_invalid" }
$remoteTagCommit = ($peeledTagRows[0] -split "`t")[0]
if ($remoteTagCommit -ne $newTip) { throw "remote_tag_target_mismatch" }
```

- [ ] **Step 8: Create one asset-free release page**

```powershell
gh release create v1.0.0 --repo Teufelsboy/HSConfig --title "HSConfig v1.0.0" --notes-file docs/contracts/v1.0.0-release-notes.md --verify-tag
```

- [ ] **Step 9: Verify release uniqueness and zero assets**

```powershell
git tag --list
gh release list --repo Teufelsboy/HSConfig --limit 100 --json tagName,isDraft,isPrerelease
gh release view v1.0.0 --repo Teufelsboy/HSConfig --json tagName,targetCommitish,isDraft,isPrerelease,assets,url
```

Expected: one tag, one non-draft/non-prerelease release, target resolves to `$newTip`, and `assets` is empty.

---

### Task 9: Remove Residue and Destroy the Temporary Bundle

**Files:**
- Delete local caches/process residue
- Delete external temporary bundle only after all verification passes

- [ ] **Step 1: Reconcile the twelve local outputs**

```powershell
python scripts/reconcile_outputs.py --outputs outputs --catalog docs/operator/audited-deck-catalog.json --check --json
```

Expected: exactly twelve current outputs, twelve revisions, zero staging/invalid.

- [ ] **Step 2: Enumerate exact cleanup targets**

```powershell
Get-Item -Force .pytest_cache,.ruff_cache,build,dist,.superpowers -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
Get-Item -Force .codex-qa-* -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
python scripts/reconcile_outputs.py --outputs outputs --catalog docs/operator/audited-deck-catalog.json --check --json
```

Output cleanup is ownership-aware and occurs only through `reconcile_outputs.py`; do not delete output paths by name pattern. For each cache/process target, use `Path.GetRelativePath` against the resolved repository root, reject rooted/`..` results and reparse points, then use native PowerShell `Remove-Item -LiteralPath` on that exact verified target.

- [ ] **Step 3: Run the final product verification**

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --json
python scripts/check_near100_scorecard.py --repo . --outputs outputs --mode final --json
git status --porcelain
git branch --format="%(refname:short)"
git ls-remote --heads origin
git tag --list
gh pr list --repo Teufelsboy/HSConfig --state open --json number
gh release view v1.0.0 --repo Teufelsboy/HSConfig --json assets,tagName,isDraft,isPrerelease
gh api "repos/Teufelsboy/HSConfig/actions/artifacts?per_page=1" --jq .total_count
```

Expected: release gate and final scorecard true, all hard metrics at minimum, overall at least 98, gameplay `not_applicable`, clean worktree, only `main`, no PR, one tag/release, zero Release assets, and zero GitHub Actions artifacts. CI logs are not downloadable product artifacts and remain outside the residue claim.

Only after every check above passes, persist the transaction decision:

```powershell
Write-AtomicCutoverJournal -Path $cutoverJournalPath -Decision commit -Phase final_verified -FinalOid $newTip -ReleaseTag v1.0.0
```

This atomic, digest-verified journal replacement is the commit point. A failure or hard kill before it rolls back; a failure or hard kill after it makes `-Recover` reverify the final state and roll forward through Steps 4-6.

- [ ] **Step 4: Verify the external bundle immediately before deletion**

```powershell
git bundle verify $bundlePath
if ((Get-FileHash -Algorithm SHA256 $bundlePath).Hash.ToLowerInvariant() -ne $bundleHash) { throw "bundle_hash_changed" }
```

- [ ] **Step 5: Delete only the verified bundle directory**

Resolve `$bundleDir` and the sibling `$cutoverJournalPath`. Use `[IO.Path]::GetRelativePath($resolvedTempRoot, ...)` for both, reject rooted paths or results equal to `..`/beginning `..\`, reject every reparse point, require the exact paired names `hsconfig-cutover-<32 lowercase hex>/` and `hsconfig-cutover-<same 32 lowercase hex>.journal.json`, and require the directory's exact four-file contents `curated-graph.json`, `github-settings-before.json`, `pre-v1-main.bundle`, and `pre-v1-main.bundle.sha256`. Reverify the graph-state, settings-snapshot, journal envelope/payload hashes, journal-to-directory identity, and durable `decision="commit"`, then:

```powershell
Remove-Item -LiteralPath $bundleDir -Recurse -Force
if (Test-Path -LiteralPath $bundleDir) { throw "bundle_cleanup_failed" }
Remove-Item -LiteralPath $cutoverJournalPath -Force
if (Test-Path -LiteralPath $cutoverJournalPath) { throw "journal_cleanup_failed" }
```

The journal is deliberately outside the recursively deleted directory and is the final file removed. If a hard kill occurs while deleting `$bundleDir`, `-Recover -JournalPath $cutoverJournalPath` reads the durable commit decision and resumes roll-forward cleanup. If the journal is absent, recovery accepts success only when its exact paired state directory is also absent; a missing journal beside a partially present directory fails closed as external corruption.

- [ ] **Step 6: Produce the final cutover receipt**

Report:

- old and new OIDs/tree OIDs;
- four commit signature results;
- v1.0.0 tag signature;
- exact CI run and four job conclusions;
- release URL and zero asset count;
- branch/tag/release inventories;
- effective settings/ruleset/security results;
- zero GitHub Actions artifact count;
- twelve-output inventory;
- clean-worktree result;
- durable journal commit decision;
- bundle deletion confirmation.

Do not store the receipt in the repository unless a later versioned governance requirement explicitly adds it.

---

## Repository and v1.0.0 Acceptance Gate

- [ ] Final reachable `main` has exactly four linear signed commits with approved subjects.
- [ ] Final tree contains only active product paths and no plan/research/history directories.
- [ ] Repository is public and visibly proprietary with consistent owner/year.
- [ ] README is concise, clickable, version-correct, and operational.
- [ ] Issues expose only the redacted bug form; sensitive reports use Private Vulnerability Reporting.
- [ ] One signed annotated tag `v1.0.0` exists.
- [ ] One matching non-draft release exists with no assets.
- [ ] GitHub Actions artifact inventory is empty.
- [ ] Local and remote branch inventories equal `[main]`; no PR is open.
- [ ] `main` ruleset blocks deletion/force-push, requires linear history, and enforces proven signing without requiring PRs.
- [ ] Security and Actions settings are verified effective, not merely requested.
- [ ] Exactly twelve local current outputs exist, with no backups/staging/caches.
- [ ] Temporary history bundle is verified, then deleted.
- [ ] Run:

```powershell
python scripts/check_release_gate.py --repo . --outputs outputs --json
git log --show-signature --reverse --format=fuller
git status --porcelain
git branch --format="%(refname:short)"
git ls-remote --heads origin
git tag --verify v1.0.0
gh release view v1.0.0 --repo Teufelsboy/HSConfig --json url,assets,tagName,isDraft,isPrerelease
gh api repos/Teufelsboy/HSConfig/rulesets
```

Expected: all local gates pass and all remote invariants match this plan.
