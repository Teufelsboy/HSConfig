import json

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_package_has_single_canonical_guide_claim_bundle_or_identical_copy(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "pkg"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
        ]
    )

    assert code == 0
    canonical_path = out / "reports" / "guide_claim_bundle.json"
    duplicate_path = out / "reports" / "research" / "guide_claim_bundle.json"
    assert canonical_path.exists()
    if duplicate_path.exists():
        duplicate = json.loads(duplicate_path.read_text(encoding="utf-8"))
        if "canonical_report" in duplicate:
            assert duplicate["canonical_report"] == "../guide_claim_bundle.json"
            assert duplicate["authority"] == "reports/guide_claim_bundle.json"
        else:
            assert duplicate_path.read_bytes() == canonical_path.read_bytes()
