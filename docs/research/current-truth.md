# HSConfig Current Truth Index

Research artifacts are evidence, not operator instructions.

Normal operator path starts at `docs/operator/README.md`.

## Current Active Evidence

| Package | Role | Current implication |
| --- | --- | --- |
| `docs/research/2026-07-09-hsconfig-next-recommendation-mechanic-polish/` | Visibility-only Mechanic Polish | Add non-blocking mechanic visibility for `choose_one`, `board_position`, `generic_spell_target`, `location_activation`, `secret_timing`, and `generated_entity_random_pool`; do not change apply gates. |
| `docs/research/2026-07-09-hsconfig-current-no-block-wild-mechanic-audit/` | No-block Wild mechanic evidence | Valid deck packages should stay load-safe even when mechanic semantics are report-only. |
| `docs/research/2026-07-09-hsconfig-universal-no-block-skill-audit-v2/` | Universal no-block evidence | The no-block promise is implemented through warning visibility, not through broader runtime writes. |

## Superseded Evidence

Older packages remain useful background, but they are not normal operator guidance. When a claim conflicts with `docs/operator/README.md`, `.agents/skills/hsconfig/SKILL.md`, or `docs/operator/universal-wild-no-block-contract.md`, the operator and skill documents win.
