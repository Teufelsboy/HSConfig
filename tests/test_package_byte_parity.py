from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tests.helpers.audited_deck_support import captured_source_documents
from tests.helpers.package_byte_contract import (
    AUDITED_DECK_NAMES,
    artifact_rows_for_tree,
    build_fixture_from_roots,
    assert_fixture_matches_canonical_fingerprints,
    assert_fixture_is_metadata_only,
    assert_fixture_schema,
    canonical_as_of_dates,
    canonicalize_source_bytes,
    content_root_sha256,
    load_fixture,
    prepare_audited_packages,
)


FIXTURE_PATH = Path("tests/fixtures/package-byte-contract-v1.json")
PRE_REMOVAL_CANONICAL_OWNER_BASELINE_PATH = Path(
    "tests/fixtures/pre-removal-canonical-owner-sha256-v1.json"
)

CANONICAL_ALIAS_OWNER_PATHS = (
    "reports/globalvalues_profile.json",
    "reports/global_values_authority_matrix.json",
    "reports/card_behavior_plan_report.json",
    "reports/combo_plan_report.json",
    "reports/guide_claim_bundle.json",
)


def test_content_root_uses_the_literal_path_size_digest_stream() -> None:
    """Catches any separator, ordering, or size-format drift in the root hash."""
    rows = [
        {
            "relative_path": "reports/a.md",
            "size": 3,
            "sha256": "a" * 64,
        },
        {
            "relative_path": "CustomConfig/Deck/Card.json",
            "size": 12,
            "sha256": "b" * 64,
        },
    ]

    assert content_root_sha256(rows) == (
        "269a6818b4f05852fd09d463c64d4beb8e44ed2d559c0a1f137c5191cf7cd94f"
    )


def test_fixture_is_complete_metadata_only_twelve_deck_contract() -> None:
    """Catches fixture leaks, incomplete catalog drift, and malformed byte metadata."""
    fixture = load_fixture(FIXTURE_PATH)

    assert_fixture_schema(fixture)
    assert_fixture_is_metadata_only(fixture)
    assert tuple(fixture["decks"]) == AUDITED_DECK_NAMES
    assert "CuteWarrior" in fixture["decks"]
    assert sum(len(deck["artifacts"]) for deck in fixture["decks"].values()) == 878


def test_fixture_validator_rejects_embedded_deck_code_metadata() -> None:
    """Catches a future fixture change that stores material beyond its byte metadata."""
    fixture = deepcopy(load_fixture(FIXTURE_PATH))
    fixture["decks"]["ShadowPriest"]["deck_code"] = "AAEBA-not-allowed"

    with pytest.raises(AssertionError, match="deck_fields_invalid"):
        assert_fixture_schema(fixture)


def test_fixture_privacy_scan_rejects_a_raw_deck_code_marker() -> None:
    """Catches a raw deck-code leak even if it is hidden in a string-valued row."""
    fixture = deepcopy(load_fixture(FIXTURE_PATH))
    fixture["decks"]["ShadowPriest"]["artifacts"][0]["relative_path"] = "AAEBA"

    with pytest.raises(AssertionError, match="private_data_leak"):
        assert_fixture_is_metadata_only(fixture)


def test_write_requires_the_mandatory_two_root_gate_and_keeps_fixture_untouched(
    tmp_path: Path,
) -> None:
    """Catches a write path that can bypass the full A==B raw-byte gate."""
    from scripts.freeze_package_byte_contract import main

    fixture = tmp_path / "reviewed.json"
    original = b'{"reviewed":true}\n'
    fixture.write_bytes(original)

    with pytest.raises(SystemExit, match="verify_twice_required"):
        main(["--fixture", str(fixture), "--write"])

    assert fixture.read_bytes() == original


def test_fixture_rejects_a_valid_looking_but_noncanonical_fingerprint() -> None:
    """Catches a self-consistent builder-derived fingerprint that is not audited."""
    fixture = deepcopy(load_fixture(FIXTURE_PATH))
    fixture["decks"]["ShadowPriest"]["deck_fingerprint"] = "0" * 64

    with pytest.raises(AssertionError, match="canonical_fingerprint_mismatch"):
        assert_fixture_matches_canonical_fingerprints(fixture)


def test_audited_dates_are_derived_per_deck() -> None:
    """Catches replacing per-deck audited dates with a global date constant."""
    dates = canonical_as_of_dates()

    assert tuple(dates) == AUDITED_DECK_NAMES
    assert dates["ShadowPriest"].isoformat() == "2026-07-29"
    assert all(value.isoformat() == "2026-07-29" for value in dates.values())


def test_source_input_canonicalization_erases_crlf_and_lone_cr_drift() -> None:
    """Catches platform line-ending drift before source bytes enter a package build."""
    lf = b'{"source_documents":[]}\n'
    mixed = b'{"source_documents":[]}\r\n'

    assert canonicalize_source_bytes(lf) == canonicalize_source_bytes(mixed)
    assert canonicalize_source_bytes(b"a\rb\r\nc\n") == b"a\nb\nc\n"


def test_cutewarrior_input_matches_the_established_acceptance_diagnostic_source(
    tmp_path: Path,
) -> None:
    """Catches an invented CuteWarrior source-authority expansion."""
    from tests.helpers.package_byte_contract import _materialize_source_documents

    logical_path = _materialize_source_documents("CuteWarrior", root=tmp_path)
    materialized = load_fixture(tmp_path / logical_path)

    assert materialized == captured_source_documents(
        {"deck_name": "CuteWarrior"}
    )


def test_network_fence_blocks_socket_and_imported_network_aliases() -> None:
    """Catches a bypass through source-acquisition or HearthstoneJSON imports."""
    import hsconfig.hearthstonejson as hearthstonejson
    import hsconfig.source_acquisition as source_acquisition
    from tests.helpers.package_byte_contract import (
        _offline_build_inputs,
        _offline_network_and_card_data,
    )

    _deck_cards, offline_cards, card_database = _offline_build_inputs()
    aliases = (
        (lambda: source_acquisition.create_connection(("example.invalid", 443))),
        (lambda: source_acquisition.getaddrinfo("example.invalid", 443)),
        (lambda: hearthstonejson.urlopen("https://example.invalid/")),
    )

    with _offline_network_and_card_data(offline_cards, card_database):
        for call in aliases:
            with pytest.raises(AssertionError, match="network_attempted"):
                call()


def test_current_builder_reproduces_the_frozen_complete_byte_contract(
    tmp_path: Path,
) -> None:
    """Catches any canonical pipeline byte drift against the frozen contract."""
    fixture = load_fixture(FIXTURE_PATH)
    assert_fixture_matches_canonical_fingerprints(fixture)
    generated = prepare_audited_packages(tmp_path / "generated")

    assert tuple(generated) == AUDITED_DECK_NAMES
    for deck_name, package_root in generated.items():
        assert artifact_rows_for_tree(package_root) == fixture["decks"][deck_name][
            "artifacts"
        ]
        assert content_root_sha256(
            artifact_rows_for_tree(package_root)
        ) == fixture["decks"][deck_name]["content_root_sha256"]


def test_fresh_builder_matches_immutable_pre_removal_owner_sha256_baseline(
    tmp_path: Path,
) -> None:
    baseline = load_fixture(PRE_REMOVAL_CANONICAL_OWNER_BASELINE_PATH)
    generated = prepare_audited_packages(tmp_path / "generated")

    assert baseline["schema_version"] == 1
    assert baseline["purpose"] == (
        "immutable pre-removal canonical-owner SHA256 baseline"
    )
    assert tuple(baseline["decks"]) == AUDITED_DECK_NAMES
    assert sum(len(rows) for rows in baseline["decks"].values()) == 60
    for deck_name, package_root in generated.items():
        actual = {
            row["relative_path"]: row
            for row in artifact_rows_for_tree(package_root)
        }
        expected = baseline["decks"][deck_name]

        assert set(expected) == set(CANONICAL_ALIAS_OWNER_PATHS), deck_name
        assert {
            path: actual[path]["sha256"]
            for path in CANONICAL_ALIAS_OWNER_PATHS
        } == expected, deck_name


def test_generator_rejects_a_valid_looking_but_noncanonical_generated_fingerprint(
    tmp_path: Path,
) -> None:
    """Catches a builder report fingerprint drift before fixture construction."""
    generated = prepare_audited_packages(tmp_path / "generated")
    identity_path = generated["ShadowPriest"] / "reports" / "deck_identity.json"
    identity = load_fixture(identity_path)
    identity["deck_fingerprint"] = "0" * 64
    identity_path.write_text(json.dumps(identity, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(AssertionError, match="canonical_fingerprint_mismatch"):
        build_fixture_from_roots(generated)


def test_generator_requires_two_clean_roots_to_agree_before_freezing() -> None:
    """Catches nondeterministic canonical trees before a fixture write is allowed."""
    from scripts.freeze_package_byte_contract import build_contract

    fixture = build_contract(verify_twice=True)

    assert tuple(fixture["decks"]) == AUDITED_DECK_NAMES
    assert sum(len(deck["artifacts"]) for deck in fixture["decks"].values()) == 878


def test_generator_refuses_fixture_overwrite_without_explicit_write(
    tmp_path: Path,
) -> None:
    """Catches accidental replacement of a reviewed characterization fixture."""
    from scripts.freeze_package_byte_contract import main

    fixture = tmp_path / "existing.json"
    fixture.write_text('{"reviewed":true}\n', encoding="utf-8")

    with pytest.raises(SystemExit, match="refusing_to_overwrite"):
        main(["--fixture", str(fixture)])
