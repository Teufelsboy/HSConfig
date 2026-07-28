import json
from pathlib import Path

import pytest
from hearthstone.deckstrings import write_deckstring

import hsconfig.audited_deck_catalog as audited_deck_catalog
from hsconfig.audited_deck_catalog import (
    load_audited_deck_catalog,
    load_audited_role_manifest,
)
from hsconfig.deckstring_decode import _parse_deckstring, decode_deck_code
from hsconfig.input_loading import fixture_row_for


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")
SUPPLEMENTAL = Path("docs/operator/supplemental-proof-decks.json")
SOURCE_CANDIDATES = Path("docs/operator/source-candidate-proof-decks.json")
CATALOG = Path("docs/operator/audited-deck-catalog.json")
IDENTITY_FIELDS = {"deck_code", "hs_id", "hdt_deck_id", "matrix_role"}


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_schema_version",
        "wrong_row_count",
        "missing_required_field",
        "empty_required_field",
        "invalid_role",
        "wrong_role_counts",
    ],
)
def test_audited_catalog_rejects_malformed_contract(
    tmp_path: Path,
    mutation: str,
):
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    if mutation == "wrong_schema_version":
        payload["schema_version"] = 2
    elif mutation == "wrong_row_count":
        payload["decks"].pop()
    elif mutation == "missing_required_field":
        payload["decks"][0].pop("hs_id")
    elif mutation == "empty_required_field":
        payload["decks"][0]["deck_code"] = " "
    elif mutation == "invalid_role":
        payload["decks"][0]["matrix_role"] = "visibility_only"
    elif mutation == "wrong_role_counts":
        payload["decks"][0]["matrix_role"] = "supplemental"
    path = tmp_path / "catalog.json"
    _write_json(path, payload)

    with pytest.raises(ValueError):
        load_audited_deck_catalog(path)


@pytest.mark.parametrize(
    "field",
    ["deck_name", "deck_code", "hs_id", "hdt_deck_id"],
)
def test_audited_catalog_rejects_duplicate_identity_fields(
    tmp_path: Path,
    field: str,
):
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    payload["decks"][1][field] = payload["decks"][0][field]
    path = tmp_path / "catalog.json"
    _write_json(path, payload)

    with pytest.raises(ValueError):
        load_audited_deck_catalog(path)


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate_reference",
        "missing_deck_name",
        "empty_deck_name",
        "unknown_audited_reference",
        "visibility_name_typo",
        "visibility_marker_missing",
        "visibility_deck_code_missing",
    ],
)
def test_role_manifest_rejects_unresolved_or_ambiguous_identity(
    tmp_path: Path,
    mutation: str,
):
    catalog_path = tmp_path / "audited-deck-catalog.json"
    manifest_path = tmp_path / "supplemental-proof-decks.json"
    _write_json(
        catalog_path,
        json.loads(CATALOG.read_text(encoding="utf-8")),
    )
    payload = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    if mutation == "duplicate_reference":
        payload["decks"].append(dict(payload["decks"][0]))
    elif mutation == "missing_deck_name":
        payload["decks"][0].pop("deck_name")
    elif mutation == "empty_deck_name":
        payload["decks"][0]["deck_name"] = " "
    elif mutation == "unknown_audited_reference":
        payload["decks"][0]["deck_name"] = "CuteWarriorTypo"
    elif mutation == "visibility_name_typo":
        payload["decks"][1]["deck_name"] = "SecretMageTypo"
    elif mutation == "visibility_marker_missing":
        payload["decks"][1].pop("proof_scope")
    elif mutation == "visibility_deck_code_missing":
        payload["decks"][1].pop("deck_code")
    _write_json(manifest_path, payload)

    with pytest.raises(ValueError):
        load_audited_role_manifest(manifest_path)


@pytest.mark.parametrize(
    ("deck_name", "malformed_deck_code"),
    [
        ("SecretMage", "not-a-deck-code"),
        ("HighlanderPriest", "AAEBA-invalid-base64"),
    ],
)
def test_visibility_only_identity_rejects_nonempty_malformed_deck_code(
    tmp_path: Path,
    deck_name: str,
    malformed_deck_code: str,
):
    catalog_path = tmp_path / "audited-deck-catalog.json"
    manifest_path = tmp_path / "supplemental-proof-decks.json"
    _write_json(
        catalog_path,
        json.loads(CATALOG.read_text(encoding="utf-8")),
    )
    payload = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    row = next(row for row in payload["decks"] if row["deck_name"] == deck_name)
    assert row["proof_scope"] == "supplemental_visibility_only"
    assert row["matrix_policy"] == "not_representative_visibility_only"
    row["deck_code"] = malformed_deck_code
    _write_json(manifest_path, payload)

    with pytest.raises(ValueError, match="audited_role_manifest_invalid"):
        load_audited_role_manifest(manifest_path)


@pytest.mark.parametrize(
    ("deck_name", "decoded_identity"),
    [
        (
            "SecretMage",
            {"card_count_total": 29, "unresolved_card_count": 0},
        ),
        (
            "HighlanderPriest",
            {"card_count_total": 30, "unresolved_card_count": 1},
        ),
    ],
)
def test_visibility_only_identity_requires_thirty_resolved_main_deck_cards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    deck_name: str,
    decoded_identity: dict[str, int],
):
    catalog_path = tmp_path / "audited-deck-catalog.json"
    manifest_path = tmp_path / "supplemental-proof-decks.json"
    _write_json(
        catalog_path,
        json.loads(CATALOG.read_text(encoding="utf-8")),
    )
    payload = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    target_code = next(
        row["deck_code"] for row in payload["decks"] if row["deck_name"] == deck_name
    )
    _write_json(manifest_path, payload)

    def fake_decode(deck_code: str) -> dict[str, int]:
        if deck_code == target_code:
            return decoded_identity
        return {"card_count_total": 30, "unresolved_card_count": 0}

    monkeypatch.setattr(audited_deck_catalog, "decode_deck_code", fake_decode)

    with pytest.raises(ValueError, match="audited_role_manifest_invalid"):
        load_audited_role_manifest(manifest_path)


@pytest.mark.parametrize(
    "identity_surface",
    ["sideboard_card", "sideboard_owner", "hero"],
)
def test_visibility_only_identity_rejects_unresolved_non_main_surface(
    tmp_path: Path,
    identity_surface: str,
):
    catalog_path = tmp_path / "audited-deck-catalog.json"
    manifest_path = tmp_path / "supplemental-proof-decks.json"
    _write_json(
        catalog_path,
        json.loads(CATALOG.read_text(encoding="utf-8")),
    )
    payload = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    highlander = next(
        row for row in payload["decks"] if row["deck_name"] == "HighlanderPriest"
    )
    parsed = _parse_deckstring(highlander["deck_code"])
    heroes = list(parsed["heroes"])
    sideboards = list(parsed["sideboards"])
    if identity_surface == "hero":
        heroes = [999999]
    elif identity_surface == "sideboard_owner":
        card_dbf_id, count, _owner_dbf_id = sideboards[0]
        sideboards[0] = (card_dbf_id, count, 999999)
    else:
        _card_dbf_id, count, owner_dbf_id = sideboards[0]
        sideboards[0] = (999999, count, owner_dbf_id)
    highlander["deck_code"] = write_deckstring(
        list(parsed["cards"]),
        heroes,
        parsed["format"],
        sideboards,
    )
    _write_json(manifest_path, payload)

    with pytest.raises(ValueError, match="audited_role_manifest_invalid"):
        load_audited_role_manifest(manifest_path)


def test_visibility_only_highlander_valid_three_card_sideboard_resolves():
    rows = load_audited_role_manifest(SUPPLEMENTAL)
    highlander = next(row for row in rows if row["deck_name"] == "HighlanderPriest")

    decoded = decode_deck_code(highlander["deck_code"])

    assert decoded["card_count_total"] == 30
    assert decoded["sideboard_count"] == 3
    assert decoded["unresolved_identity_count"] == 0


def test_role_manifests_reference_catalog_without_duplicating_identity():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    supplemental = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    candidates = json.loads(SOURCE_CANDIDATES.read_text(encoding="utf-8"))
    catalog_names = {row["deck_name"] for row in catalog["decks"]}
    representative_names = {
        row["deck_name"]
        for row in catalog["decks"]
        if row["matrix_role"] == "representative"
    }

    for manifest in (matrix, supplemental, candidates):
        assert manifest["identity_catalog"] == "audited-deck-catalog.json"

    assert {row["deck_name"] for row in matrix["decks"]} == representative_names
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in matrix["decks"])

    audited_supplemental = [
        row for row in supplemental["decks"] if row["deck_name"] in catalog_names
    ]
    visibility_only = [
        row for row in supplemental["decks"] if row["deck_name"] not in catalog_names
    ]
    assert [row["deck_name"] for row in audited_supplemental] == ["CuteWarrior"]
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in audited_supplemental)
    assert {row["deck_name"] for row in visibility_only} == {
        "SecretMage",
        "HighlanderPriest",
    }
    for row in visibility_only:
        decoded = decode_deck_code(row["deck_code"])
        assert decoded["card_count_total"] == 30
        assert decoded["unresolved_card_count"] == 0

    assert {row["deck_name"] for row in candidates["decks"]} == catalog_names
    assert all(IDENTITY_FIELDS.isdisjoint(row) for row in candidates["decks"])


def test_fixture_role_loader_resolves_identity_from_catalog():
    shadowpriest = fixture_row_for("ShadowPriest")

    assert shadowpriest is not None
    assert shadowpriest["deck_code"].startswith("AAEBAa0G")
    assert shadowpriest["hs_id"] == "2737726722"
    assert shadowpriest["hdt_deck_id"] == ("c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602")
    assert shadowpriest["matrix_role"] == "representative"
    assert shadowpriest["archetype_bucket"] == ("aggro_burn_hero_power_transform")


def test_representative_matrix_stays_eleven_rows_until_explicitly_widened():
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    names = [row["deck_name"] for row in matrix["decks"]]

    assert len(names) == 11
    assert "CuteWarrior" not in names
    assert {"Kingslayer", "Boarlock"} <= set(names)


def test_supplemental_proof_decks_are_not_representative_matrix_rows():
    supplemental = json.loads(SUPPLEMENTAL.read_text(encoding="utf-8"))
    rows = supplemental["decks"]

    assert rows
    cute = next(row for row in rows if row["deck_name"] == "CuteWarrior")
    assert cute["proof_role"] == "supplemental_load_safe_prepare_proof"
    assert (
        cute["matrix_policy"]
        == "not_representative_until_future_matrix_review_proves_missing_family"
    )
    assert cute["operator_action"] == "keep_supplemental"
