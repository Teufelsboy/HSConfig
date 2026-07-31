import json
import shutil
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.io import write_json
from hsconfig.output_publisher import publish_configure_run
from tests.test_output_publisher import build_rendered_run


def _write_runtime_match_fixture(
    package: Path,
    runtime: Path,
    *,
    mapping_line: str,
) -> None:
    for root in (package, runtime):
        deck = root / "CustomConfig" / "shadowpriest"
        deck.mkdir(parents=True)
        write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
        write_json(deck / "Mulligan.json", {"Mulligan": {"values": []}})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        mapping_line,
        encoding="utf-8",
    )


def test_runtime_match_cli_reports_matched_package(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line="ShadowPriest=shadowpriest\n",
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )
    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["runtime_write_performed"] is False


@pytest.mark.parametrize(
    ("manifest", "mapping_line"),
    [
        (None, "shadowpriest=shadowpriest\n"),
        (
            {
                "deck_name": "",
                "deck_code": "fixture",
                "runtime_root": "unused",
            },
            "shadowpriest=shadowpriest\n",
        ),
        (["shadowpriest"], "shadowpriest=shadowpriest\n"),
        ({"deck_name": "ShadowPriest"}, "ShadowPriest=shadowpriest\n"),
    ],
)
def test_runtime_match_cli_fails_closed_without_verified_manifest_identity(
    tmp_path: Path,
    capsys,
    manifest: object | None,
    mapping_line: str,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line=mapping_line,
    )
    if manifest is not None:
        write_json(package / "reports" / "input_manifest.json", manifest)

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "failed"
    assert out["errors"]


def test_runtime_match_cli_returns_nonzero_for_mismatch(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    (runtime / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    write_json(package / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(runtime / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "Other"})
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--config-dir",
        "shadowpriest",
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "mismatch"


def test_runtime_match_cli_reads_published_output_root_under_current_lease(
    tmp_path: Path,
    capsys,
) -> None:
    output_root = tmp_path / "published"
    published = publish_configure_run(
        build_rendered_run(tmp_path / "source", 1),
        output_root,
    )
    runtime = tmp_path / "runtime"
    shutil.copytree(
        published.package_root / "CustomConfig",
        runtime / "CustomConfig",
    )
    manifest = json.loads(
        (
            published.package_root
            / "reports"
            / "input_manifest.json"
        ).read_bytes()
    )
    config_dir = next(
        path.name
        for path in (published.package_root / "CustomConfig").iterdir()
        if path.is_dir()
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"{manifest['deck_name']}={config_dir}\n",
        encoding="utf-8",
    )

    code = main(
        [
            "runtime-match",
            "--package",
            str(output_root),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["runtime_write_performed"] is False
    assert (
        out["publication_content_root_sha256"]
        == published.content_root_sha256
    )
