# Evidence and Disposition

[Back to the operator guide](../operator/README.md)

Evidence explains a claim; disposition determines whether that claim may lower
to a runtime surface. The two are deliberately separate.

## Evidence rules

- Exact deck-matched public guide statements can support strategic claims only
  when their live provenance and deck fingerprint are verified.
- Supported official static semantics can support deterministic identity,
  role, and mechanical-effect claim families, not inferred strategy.
- Captured snippets, decklists, fixtures, defaults, policy fallbacks, and
  historical research remain diagnostic inputs.
- Raw logs, replays, deck codes, runtime XML, and private runtime packages are
  never public repository evidence.

## Disposition rules

Each decoded card receives an explicit disposition even when no runtime row is
emitted. Wrong-surface or insufficiently supported claims remain visible in
reports. Low confidence or suppression is not bot delegation; `bot_delegated`
is an explicit disposition with zero generated runtime rows.

No evidence record, score, diagnostic, or maintenance artifact can replace
`reports/operator_summary.json` or authorize runtime writes.
