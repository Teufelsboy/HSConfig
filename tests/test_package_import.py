def test_package_imports():
    import hsconfig
    from hsconfig.version import __version__

    assert __version__ == "1.0.0"
    assert hsconfig.__version__ == __version__


def test_python_m_hsconfig_help_works():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "hsconfig", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage: hsconfig" in result.stdout
