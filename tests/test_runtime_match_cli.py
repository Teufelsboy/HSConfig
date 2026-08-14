import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.io import write_json
from hsconfig.output_publisher import publish_configure_run
from hsconfig.runtime_installer import plan_runtime_install
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


def _versioned_config_dir(package: Path, logical: str) -> str:
    directory = package / "CustomConfig" / logical
    records = b"".join(
        (
            f"{path.name}\0{path.stat().st_size}\0"
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}\n"
        ).encode("utf-8")
        for path in sorted(directory.iterdir())
        if path.is_file()
    )
    return f"{logical}--sha256-{hashlib.sha256(records).hexdigest()}"


def test_runtime_match_cli_reports_matched_package(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line="[configs]\nShadowPriest=shadowpriest\n",
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )
    code = main(
        [
            "runtime-match",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--config-dir",
            "shadowpriest",
            "--json",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["runtime_write_performed"] is False


def test_runtime_match_cli_auto_resolves_active_versioned_config(
    tmp_path: Path,
    capsys,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    logical = "shadowpriest"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line="",
    )
    versioned = _versioned_config_dir(package, logical)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "[configs]\n" f"ShadowPriest = {versioned}\n",
        encoding="utf-8",
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )
    shutil.copytree(
        package / "CustomConfig" / logical,
        runtime / "CustomConfig" / versioned,
    )
    write_json(
        runtime / "CustomConfig" / logical / "GlobalValues.json",
        {"GameCardId": "Legacy"},
    )

    code = main(
        [
            "runtime-match",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["logical_config_dir"] == logical
    assert out["runtime_config_dir"] == versioned


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
    runtime.mkdir()
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime,
    )
    source_config = (
        published.package_root / "CustomConfig" / plan.logical_config_dir
    )
    target_config = runtime / "CustomConfig" / plan.versioned_config_dir
    target_config.parent.mkdir()
    shutil.copytree(source_config, target_config)
    manifest = json.loads(
        (
            published.package_root
            / "reports"
            / "input_manifest.json"
        ).read_bytes()
    )
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        f"[configs]\n{manifest['deck_name']}={plan.versioned_config_dir}\n",
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
