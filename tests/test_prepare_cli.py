import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_research_contract_command_writes_contract_only(tmp_path: Path, capsys):
    out = tmp_path / "research"

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    archetype = json.loads((out / "archetype_research.json").read_text(encoding="utf-8"))
    card_roles = json.loads((out / "card_role_map.json").read_text(encoding="utf-8"))
    globalvalue_intent = json.loads((out / "globalvalue_intent.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["research_dir"] == str(out)
    assert archetype["deck_name"] == "ShadowPriest"
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in card_roles["SW_448"]["roles"]
    assert globalvalue_intent["overlays"]["MyHeroPowerValue"] == "increase"
    assert not (out / "CustomConfig").exists()


def test_research_contract_refuses_existing_nonempty_output_directory(tmp_path: Path, capsys):
    out = tmp_path / "package_root"
    out.mkdir()
    sentinel = out / "do_not_delete.txt"
    sentinel.write_text("keep", encoding="utf-8")

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Refusing to overwrite non-empty research output directory" in payload["errors"][0]
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_research_contract_refuses_existing_artifact_named_output_directory(
    tmp_path: Path, capsys
):
    out = tmp_path / "looks_like_research"
    out.mkdir()
    claims = out / "claims.json"
    claims.write_text('{"claims": "keep"}', encoding="utf-8")

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Refusing to overwrite non-empty research output directory" in payload["errors"][0]
    assert claims.read_text(encoding="utf-8") == '{"claims": "keep"}'


def test_prepare_builds_valid_package_with_research_artifacts(tmp_path: Path, capsys):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    research_dir = reports / "research"
    validation = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    card_roles = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["command"] == "prepare"
    assert payload["package"] == str(package)
    assert payload["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert validation["status"] == "passed"
    assert (package / "CustomConfig" / "shadowpriest" / "GlobalValues.json").exists()
    assert (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").exists()
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"


def test_build_and_research_contract_agree_on_shadowpriest_research(tmp_path: Path, capsys):
    research_out = tmp_path / "research_only"
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    assert (
        main(
            [
                "research-contract",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--out",
                str(research_out),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "build",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(runtime),
                "--out",
                str(package),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    research_only = json.loads((research_out / "archetype_research.json").read_text(encoding="utf-8"))
    build_research = json.loads(
        (package / "reports" / "research" / "archetype_research.json").read_text(
            encoding="utf-8"
        )
    )

    assert build_research["confidence"] == research_only["confidence"]
    assert build_research["deck_name"] == research_only["deck_name"]


def test_prepare_gameplan_uses_research_bundle_intent(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--json",
        ]
    )
    capsys.readouterr()

    research_roles = json.loads(
        (package / "reports" / "research" / "card_role_map.json").read_text(encoding="utf-8")
    )
    research_globalvalues = json.loads(
        (package / "reports" / "research" / "globalvalue_intent.json").read_text(
            encoding="utf-8"
        )
    )
    gameplan = json.loads((package / "reports" / "gameplan_contract.json").read_text(encoding="utf-8"))

    assert code == 0
    assert gameplan["cards"]["SW_448"]["confidence"] == research_roles["SW_448"]["confidence"]
    assert set(research_roles["SW_448"]["roles"]) <= set(gameplan["cards"]["SW_448"]["roles"])
    assert set(research_globalvalues["overlays"]).issubset(
        set(gameplan["aggression_profile"]["global_value_overlays"])
    )
