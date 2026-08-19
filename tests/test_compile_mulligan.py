from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.io import write_json
from hsconfig.package_domain import (
    BotDelegationModel,
    MulliganPlanModel,
    MulliganRuleModel,
)
from hsconfig.validate_package import validate_config_package


def _json(value: object) -> bytes:
    return json.dumps(
        value,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _rule(
    card_id: str,
    *,
    selector_kind: str = "card",
    selector: str | None = None,
    action: str = "hold",
    condition: str = "*",
    claim_id: str | None = None,
) -> MulliganRuleModel:
    claim_id = claim_id or f"{card_id.lower()}-claim"
    return MulliganRuleModel(
        card_id=card_id,
        selector_kind=selector_kind,
        selector_canonical_json=_json(selector or card_id),
        action=action,
        condition_canonical_json=_json(condition),
        reason="exact_authority",
        confidence="source_backed",
        source_claim_ids=(claim_id,),
        claim_id=claim_id,
    )


def _plan(
    *rules: MulliganRuleModel,
    bot_delegated: tuple[BotDelegationModel, ...] = (),
) -> MulliganPlanModel:
    return MulliganPlanModel(
        deck_name="Fixture",
        rules=tuple(sorted(rules, key=lambda row: row.identity)),
        suppressed=(),
        bot_delegated=bot_delegated,
        merged_duplicate_rule_count=0,
    )


def test_compile_mulligan_emits_valid_mulligan_block(
    tmp_path: Path,
) -> None:
    optimized_rule = MulliganRuleModel(
        card_id="EX1_001",
        selector_kind="card",
        selector_canonical_json=_json("EX1_001"),
        action="hold",
        condition_canonical_json=_json("*"),
        reason="exact optimized authority",
        confidence="llm_optimized_start",
        source_claim_ids=(),
        claim_id="starter:sha256:candidate-1:keep-ex1-001",
    )
    result = compile_mulligan(_plan(optimized_rule))

    assert result["GameCardId"] == "Mulligan"
    assert set(result) == {"GameCardId", "ConfigComment", "Mulligan"}
    assert result["Mulligan"]["values"] == [
        {
            "comment": "Fixture: starter:sha256:candidate-1:keep-ex1-001",
            "mulligan": "EX1_001",
            "condition": "*",
            "value": "hold",
        }
    ]

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Mulligan.json", result)
    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_mulligan_accepts_fully_delegated_empty_values(
    tmp_path: Path,
) -> None:
    result = compile_mulligan(
        _plan(
            bot_delegated=(
                BotDelegationModel(
                    card_id="JAM_013",
                    evidence_lane="E",
                    policy_id="BOT_NATIVE_PRE_RUN",
                    reason_code="unsupported_exact_mulligan_authority",
                ),
            )
        )
    )

    assert result["Mulligan"]["values"] == []

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Mulligan.json", result)
    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_mulligan_emits_supported_selectors_in_stable_model_order() -> None:
    config = compile_mulligan(
        _plan(
            _rule(
                "A_DROP",
                selector_kind="drop_n",
                selector="DROP1",
            ),
            _rule(
                "B_COMBO",
                selector_kind="plus_combo",
                selector="CARD_A + CARD_B",
                condition="coin",
            ),
            _rule(
                "C_CARD",
                selector="CARD_C",
                action="discard",
            ),
        )
    )

    rows = config["Mulligan"]["values"]
    assert [row["mulligan"] for row in rows] == [
        "DROP1",
        "CARD_A + CARD_B",
        "CARD_C",
    ]
    assert rows[1]["condition"] == "coin"
    assert rows[2]["value"] == "discard"


def test_compile_mulligan_rejects_wildcard_even_in_a_typed_plan() -> None:
    wildcard = _rule(
        "*",
        selector_kind="wildcard",
        selector="*",
        action="discard",
    )

    with pytest.raises(
        ValueError,
        match="mulligan_wildcard_rule_forbidden",
    ):
        compile_mulligan(_plan(wildcard))


def test_compile_mulligan_rejects_dictionary_compatibility_input() -> None:
    with pytest.raises(TypeError, match="mulligan_plan_model_required"):
        compile_mulligan(  # type: ignore[arg-type]
            {"deck_name": "Legacy", "mulligan_plan": {"rules": []}}
        )
