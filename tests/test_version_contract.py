from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tomllib

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_product_version_has_one_source() -> None:
    import hsconfig
    from hsconfig.version import __version__, version_payload

    assert __version__ == "1.0.0"
    assert hsconfig.__version__ == "1.0.0"
    assert version_payload() == {"version": "1.0.0"}


def test_project_uses_the_lightweight_dynamic_version_module() -> None:
    with (REPOSITORY_ROOT / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)

    assert "version" not in metadata["project"]
    assert metadata["project"]["dynamic"] == ["version"]
    assert metadata["tool"]["setuptools"]["dynamic"]["version"] == {
        "attr": "hsconfig.version.__version__"
    }


def test_root_version_option_prints_the_product_version(capsys: pytest.CaptureFixture[str]) -> None:
    from hsconfig.cli import main

    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == "hsconfig 1.0.0\n"


def test_root_version_option_does_not_load_heavy_command_modules(tmp_path: Path) -> None:
    source_root = REPOSITORY_ROOT / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get(
        "PYTHONPATH", ""
    )
    code = "\n".join(
        (
            "import sys",
            "from hsconfig.cli import main",
            "try:",
            "    main(['--version'])",
            "except SystemExit as exc:",
            "    assert exc.code == 0",
            "else:",
            "    raise AssertionError('version option did not exit')",
            "heavy_prefixes = ('hsconfig.package_builder', 'hsconfig.package_compiler', 'hsconfig.package_render', 'hsconfig.commands', 'hsconfig.configure_', 'hsconfig.runtime_', 'hsconfig.apply_')",
            "loaded = sorted(name for name in sys.modules if name.startswith(heavy_prefixes))",
            "assert not loaded, loaded",
        )
    )

    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        cwd=tmp_path,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == "hsconfig 1.0.0\n"
