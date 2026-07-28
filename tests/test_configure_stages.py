from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def test_verified_deck_stage_is_deeply_immutable_with_stable_digest() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        stage_digest,
    )

    identity = {
        "deck_name": "ShadowPriest",
        "deck_fingerprint": "abc",
    }
    cards = [
        {
            "card_id": "SW_448",
            "dbf_id": 64443,
            "count": 1,
        }
    ]
    verification = {"status": "verified"}

    stage = build_verified_deck_stage(
        identity=identity,
        cards=cards,
        input_verification=verification,
    )
    identity["deck_name"] = "mutated"
    cards[0]["count"] = 99
    verification["status"] = "mutated"

    assert dict(stage.identity) == {
        "deck_name": "ShadowPriest",
        "deck_fingerprint": "abc",
    }
    assert [dict(card) for card in stage.cards] == [
        {
            "card_id": "SW_448",
            "dbf_id": 64443,
            "count": 1,
        }
    ]
    assert dict(stage.input_verification) == {"status": "verified"}
    assert stage_digest(stage) == (
        "sha256:f04454d0a3b145f867370082792623c500ebb9127e35b211501049ee831c9c57"
    )
    with pytest.raises(TypeError):
        stage.identity["deck_name"] = "mutated"
    with pytest.raises(TypeError):
        stage.cards[0]["count"] = 99
    with pytest.raises(FrozenInstanceError):
        stage.identity = {}


def test_lowered_runtime_stage_is_deeply_immutable_with_stable_digest() -> None:
    from hsconfig.configure_stages import (
        build_lowered_runtime_stage,
        stage_digest,
    )

    runtime_files = {
        "GlobalValues.json": {"A": 1},
        "Mulligan.json": {"B": []},
    }
    warnings = [{"reason": "thin"}]
    source_contract = {"status": "closed"}

    stage = build_lowered_runtime_stage(
        runtime_files=runtime_files,
        warnings=warnings,
        source_contract=source_contract,
    )
    runtime_files["GlobalValues.json"]["A"] = 2
    warnings[0]["reason"] = "mutated"
    source_contract["status"] = "mutated"

    assert {
        filename: dict(payload)
        for filename, payload in stage.runtime_files.items()
    } == {
        "GlobalValues.json": {"A": 1},
        "Mulligan.json": {"B": ()},
    }
    assert [dict(warning) for warning in stage.warnings] == [{"reason": "thin"}]
    assert dict(stage.source_contract) == {"status": "closed"}
    assert stage_digest(stage) == (
        "sha256:9137543001e2452a00cb7005983e832e742a3c2971a3159d058705777912dd10"
    )
    with pytest.raises(TypeError):
        stage.runtime_files["GlobalValues.json"]["A"] = 2
    with pytest.raises(TypeError):
        stage.warnings[0]["reason"] = "mutated"
    with pytest.raises(FrozenInstanceError):
        stage.runtime_files = {}
