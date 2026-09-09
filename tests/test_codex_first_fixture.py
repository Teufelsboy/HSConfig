from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from hsconfig.deck_identity import normalize_roster, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_review import validate_starter_review
from tests import starter_fixtures


def _build(root: Path, **kwargs):
    builder = getattr(starter_fixtures, "build_codex_first_fixture", None)
    assert callable(builder), "real code-bound Codex-first fixture is missing"
    return builder(root, **kwargs)


@pytest.fixture
def isolated_appdata(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    appdata.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(appdata))


@pytest.mark.parametrize(
    ("deck_kind", "physical_count"), [("shadowpriest", 30), ("uncatalogued_40", 40)]
)
def test_codex_first_fixture_binds_actual_deckstring_and_complete_card_coverage(
    tmp_path, isolated_appdata, deck_kind, physical_count,
):
    fixture = _build(tmp_path / "fixture", deck_kind=deck_kind)
    decoded = decode_deck_code(fixture.deck_code)
    deck = fixture.frozen_inputs.deck.to_value()
    roster = normalize_roster(decoded["cards"])

    assert decoded["unresolved_identity_count"] == 0
    assert decoded["card_count_total"] == physical_count
    assert normalize_roster(deck["deck_identity"]["main_deck"]) == roster
    assert normalize_roster(deck["cards_payload"]["cards"]) == roster
    assert fixture.context.deck_fingerprint == stable_deck_fingerprint(roster)
    assert deck["deck_identity"]["deck_name"] == fixture.deck_name
    assert deck["cards_payload"]["deck_code"] == fixture.deck_code
    digest = sha256(fixture.deck_code.encode("utf-8")).hexdigest()
    assert deck["deck_identity"]["deck_code_hash"] == digest
    assert fixture.frozen_inputs.manifest.compiler_inputs.to_value()["deck_code_sha256"] == f"sha256:{digest}"
    if deck_kind == "uncatalogued_40":
        assert len(roster) == 40
        assert all(count == 1 for _, count in roster)
        assert "REV_018" in dict(roster)
        assert fixture.deck_name != starter_fixtures.SHADOWPRIEST_DECK_NAME
    candidate = validate_starter_candidate(fixture.candidate, context=fixture.context)
    value = candidate.document.to_value()
    assert {row["card_id"] for row in value["card_dispositions"]} == set(dict(roster))
    assert len(value["card_dispositions"]) == len(roster)
    assert value["mulligan"][0]["selector"] in dict(roster)
    assert value["globalvalues"] != fixture.context.document.to_value()["globalvalues_baseline"]["values"]
    review = validate_starter_review(
        fixture.review, context=fixture.context, candidate=candidate,
    )
    assert review.review_status == "approved"
    assert review.confidence == "high"
    assert len(fixture.frozen_inputs.manifest.blobs) == 6


def test_codex_first_fixture_reuses_profile_and_existing_output_identity(
    tmp_path, isolated_appdata,
):
    first = _build(tmp_path / "first", deck_kind="uncatalogued_40")
    profile_path = operator_profile_path()
    before = (profile_path.read_bytes(), path_identity(profile_path))
    output = derive_deck_output_binding(first.profile, first.deck_name).output_root
    output.mkdir()
    output_identity = path_identity(output)

    second = _build(
        tmp_path / "second", deck_kind="uncatalogued_40",
        existing_profile=first.profile, confidence="limited",
    )

    assert second.profile is first.profile
    assert (profile_path.read_bytes(), path_identity(profile_path)) == before
    assert path_identity(output) == output_identity
    assert second.deck_code == first.deck_code
    assert second.context.deck_fingerprint == first.context.deck_fingerprint
    binding = second.frozen_inputs.manifest.operator_bindings.to_value()
    assert binding["deck_output_precondition"] == {
        "state": "existing", "identity": list(output_identity),
    }
    candidate = validate_starter_candidate(second.candidate, context=second.context)
    review = validate_starter_review(second.review, context=second.context, candidate=candidate)
    assert review.confidence == "limited"
