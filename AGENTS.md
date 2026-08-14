# HSConfig Agent Rules

Work in `C:\Users\darbo\Documents\HSConfig` for `Teufelsboy/HSConfig`.

HSConfig is a lean deck-to-HearthRanger-config generator. Keep it separate from HSTuner.

Before implementing plans, generating deck packages, or applying runtime-facing changes, refresh repository state first:

- run `git fetch --all --prune --tags`
- run `git remote prune origin`
- compare the current branch with its upstream
- check every local branch that has a matching `origin/<branch>` ref
- fast-forward matching local/remote branch refs only when the update is non-destructive
- push a local branch only when the remote can be fast-forwarded cleanly and the user explicitly asked to bring all branches current
- never pull, rebase, reset, or overwrite across a dirty worktree until local changes are understood and protected
- never delete local-only branches as part of freshness work unless the user explicitly asks for branch cleanup

Do not add replay parsing, HDT parsing, winrate validation, candidate promotion, or post-run tuning to this repo.

Generated runtime packages belong under `outputs/` and are ignored by git.

Every implementation change must preserve:

- exact deck and CardID identity
- full `GlobalValues.json` key profiling
- every card covered in the gameplan contract
- strict JSON validation
- row-level provenance for generated config rows
