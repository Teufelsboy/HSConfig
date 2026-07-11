# HSConfig Source Contract Logic Audit

Research artifacts are evidence, not operator instructions.

This package records source-backed implementation evidence for the 2026-07-11
claim-kind runtime contract closure. It is not a runtime artifact and does not
replace `docs/operator/README.md` or `reports/operator_summary.json`.

Key conclusions:

- HearthRanger `Mulligan.json` is an explicit opening-hand keep/discard surface.
- Start-of-game deck effects do not imply that the physical card should be kept
  in the opening hand.
- HearthstoneJSON is useful for card identity and static semantics, not guide
  strategy.
- Runtime lowering must use typed `claim_kind` values rather than broad guide
  text.
