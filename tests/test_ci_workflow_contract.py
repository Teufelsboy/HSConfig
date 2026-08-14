from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import venv

import yaml
from yaml.constructor import ConstructorError


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CHECKOUT = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON = "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97"
RUNNER_ENVIRONMENT_STEP = "Initialize runner-scoped environment"
LOCKED_COVERAGE = (
    "python scripts/check_release_gate.py --repo . --outputs outputs "
    "--tree-mode working-pre-cutover --locked-check full-tests-and-coverage --json"
)
PIP_WHEEL_URL = (
    "https://files.pythonhosted.org/packages/5d/95/"
    "6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/"
    "pip-26.1.2-py3-none-any.whl"
)
PIP_WHEEL_SHA256 = (
    "382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab"
)
CHECKOUT_RESIDUE = (
    "build",
    "dist",
    "src/hsconfig.egg-info",
    ".coverage",
    "coverage.json",
    ".pytest_cache",
    ".hypothesis",
)
TASK8_SOURCE_OVERLAY = (
    ".github/workflows/ci.yml",
    ".github/workflows/contract-guardrails.yml",
    ".github/workflows/contract-spine.yml",
    ".github/workflows/full-test-suite.yml",
    "README.md",
    "docs/operator/README.md",
    "pylock.3.11.toml",
    "pylock.3.12.toml",
    "scripts/check_release_gate.py",
    "scripts/refresh_locks.ps1",
    "scripts/lock_wheel_closure.py",
    "tests/test_ci_contract.py",
    "tests/test_ci_workflow_contract.py",
    "tests/test_dependency_lock_contract.py",
    "tests/test_release_gate.py",
)


class _WorkflowLoader(yaml.SafeLoader):
    """Keep GitHub's `on` key as a string while preserving normal booleans."""


_WorkflowLoader.yaml_implicit_resolvers = {
    key: [
        resolver
        for resolver in resolvers
        if not (key in {"o", "O"} and resolver[0] == "tag:yaml.org,2002:bool")
    ]
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def _construct_unique_mapping(
    loader: _WorkflowLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_WorkflowLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _workflow() -> dict[str, object]:
    paths = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    assert [path.name for path in paths] == ["ci.yml"]
    document = yaml.load(paths[0].read_text(encoding="utf-8"), Loader=_WorkflowLoader)
    assert isinstance(document, dict)
    return document


def _runs(job: object) -> list[str]:
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    return [step["run"] for step in steps if isinstance(step, dict) and "run" in step]


def _steps(job: object) -> list[dict[str, object]]:
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return steps


def _named_step(job: object, name: str) -> dict[str, object]:
    matches = [step for step in _steps(job) if step.get("name") == name]
    assert len(matches) == 1
    return matches[0]


def _uses(job: object) -> list[str]:
    assert isinstance(job, dict)
    steps = job.get("steps")
    assert isinstance(steps, list)
    return [step["uses"] for step in steps if isinstance(step, dict) and "uses" in step]


def test_ci_workflow_reuses_the_locked_release_contract_without_pr_execution() -> None:
    """Catches a CI graph that can run unreviewed PR code or bypass the locked gate."""
    workflow = _workflow()

    assert workflow["name"] == "ci"
    assert workflow["on"] == {"push": {"branches": ["main"]}, "workflow_dispatch": None}
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "ci-${{ github.workflow }}-${{ github.ref }}",
        "cancel-in-progress": True,
    }

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    assert set(jobs) == {"contract", "test", "package", "security"}
    assert jobs["contract"].get("needs") is None
    for name in ("test", "package", "security"):
        assert jobs[name]["needs"] == "contract"
    assert all(isinstance(job.get("timeout-minutes"), int) and job["timeout-minutes"] > 0 for job in jobs.values())
    assert all(job.get("env", {}).get("PYTHONDONTWRITEBYTECODE") == "1" for job in jobs.values())

    assert jobs["test"]["runs-on"] == "windows-latest"
    assert "strategy" not in jobs["test"]
    assert _named_step(jobs["test"], "Set up Python")["with"] == {
        "python-version": "3.11"
    }
    assert CHECKOUT in _uses(jobs["test"])
    assert SETUP_PYTHON in _uses(jobs["test"])
    assert LOCKED_COVERAGE in _runs(jobs["test"])

    all_uses = [reference for job in jobs.values() for reference in _uses(job)]
    assert set(all_uses) == {CHECKOUT, SETUP_PYTHON}
    all_runs = [command.lower() for job in jobs.values() for command in _runs(job)]
    assert all("actions/cache" not in command for command in all_runs)
    assert all("upload-artifact" not in command for command in all_runs)
    assert all("download-artifact" not in command for command in all_runs)
    assert all("constraints-ci.txt" not in "\n".join(_runs(job)) for job in jobs.values())


def test_ci_workflow_assigns_each_required_release_boundary_to_its_job() -> None:
    """Catches a four-job workflow that omits a required release boundary."""
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)
    commands = {name: "\n".join(_runs(job)) for name, job in jobs.items()}

    assert "check_contract_guardrails.py" in commands["contract"]
    assert "contract-spine-sentinel --json" in commands["contract"]
    assert "test_audited_deck_set_acceptance.py" in commands["contract"]
    assert "verify_distribution.py --json" in commands["package"]
    assert "verify_twelve_decks.py" in commands["package"]
    assert "test_version_contract.py" in commands["package"]
    assert "python -m pip_audit" in commands["security"]
    assert "run_contract_mutations.py --json" in commands["security"]
    assert 'reconcile_outputs.py --outputs "${{ runner.temp }}/security-outputs" --apply --json' in commands["security"]
    assert "--internal-check publishable_path_scan" in commands["security"]
    assert "--internal-check repository_hygiene" in commands["security"]


def test_non_test_jobs_bootstrap_the_exact_hash_bound_minor_lock_outside_checkout() -> None:
    """Catches resolver-based installs, unverified pip, or checkout-local builds."""
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)

    for name in ("contract", "package", "security"):
        job = jobs[name]
        assert job["env"]["HSCONFIG_PYTHON_MINOR"] == "3.12"
        step = _named_step(job, "Bootstrap locked runtime from committed source")
        assert step["shell"] == "pwsh"
        command = step["run"]
        assert isinstance(command, str)
        assert PIP_WHEEL_URL in command
        assert PIP_WHEEL_SHA256 in command
        assert "Get-FileHash -LiteralPath $pipWheel -Algorithm SHA256" in command
        assert "pylock.$pythonMinor.toml" in command
        assert "@('3.11', '3.12')" in command
        assert "python_minor_mismatch" in command
        assert "sys.version_info.major" in command
        assert "git archive" not in command
        assert "tar -xf" not in command
        assert "$env:RUNNER_TEMP" in command
        assert '$selectedLock = Join-Path $sourceRoot "pylock.$pythonMinor.toml"' in command
        assert "Copy-Item -LiteralPath $selectedLock -Destination $canonicalLock" in command
        assert "pip download --require-virtualenv --no-deps --only-binary=:all:" in command
        assert "--dest $wheelhouse -r $canonicalLock" in command
        assert "--locked-check ci-wheelhouse-audit" in command
        assert "pip install --require-virtualenv --no-index --no-deps $dependencyWheels" in command
        assert "--no-deps --no-build-isolation $sourceRoot" in command
        assert "constraints-ci.txt" not in command
        assert "--no-build-isolation ." not in command
        assert command.index("Get-FileHash") < command.index("--force-reinstall $pipWheel")
        assert "HSCONFIG_CI_SOURCE_ROOT" in command
        assert "HSCONFIG_CI_COMMIT_OID" in command
        assert "HSCONFIG_CI_TREE_OID" in command
        assert "HSCONFIG_CI_SOURCE_INVENTORY" in command
        assert "HSCONFIG_CI_SOURCE_INVENTORY_SHA256" in command
        assert command.count("--locked-check ci-source-revalidate") >= 2
        assert command.index("--locked-check ci-wheelhouse-audit") < command.index(
            "pip install --require-virtualenv --no-index --no-deps $dependencyWheels"
        )
        assert command.index("checkout_identity_changed_after_dependency_install") < command.index(
            "--no-deps --no-build-isolation $sourceRoot"
        )

    test_steps = _steps(jobs["test"])
    assert all(
        step.get("name") != "Bootstrap locked runtime from committed source"
        for step in test_steps
    )
    assert _named_step(
        jobs["test"], "Run full locked tests and full-source coverage"
    )["run"] == LOCKED_COVERAGE


def test_runner_context_is_scoped_to_initialization_steps_that_persist_environment(
    tmp_path: Path,
) -> None:
    """Catches job-level runner expressions that make GitHub reject the workflow."""
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)

    for job_name, job in jobs.items():
        job_environment = job.get("env", {})
        assert isinstance(job_environment, dict)
        assert all(
            "${{ runner." not in str(value)
            for value in job_environment.values()
        )

        steps = _steps(job)
        initializer = steps[0]
        assert initializer["name"] == RUNNER_ENVIRONMENT_STEP
        assert initializer["shell"] == "pwsh"
        step_environment = initializer.get("env")
        assert step_environment == {
            "HSCONFIG_RUNNER_TEMP": "${{ runner.temp }}",
        }

        runner_temp = tmp_path / job_name / "runner-temp"
        runner_temp.mkdir(parents=True)
        expected_environment = {
            "PIP_CACHE_DIR": str(runner_temp / "pip-cache"),
            "TEMP": str(runner_temp),
            "TMP": str(runner_temp),
            "TMPDIR": str(runner_temp),
        }
        if job_name == "test":
            expected_environment["HYPOTHESIS_STORAGE_DIRECTORY"] = (
                str(runner_temp / "hypothesis")
            )

        command = initializer.get("run")
        assert isinstance(command, str)
        github_environment = tmp_path / job_name / "github-env"
        environment = os.environ.copy()
        environment["GITHUB_ENV"] = str(github_environment)
        environment["HSCONFIG_RUNNER_TEMP"] = str(runner_temp)

        completed = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
            cwd=ROOT,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert completed.returncode == 0, completed.stderr
        persisted = dict(
            line.split("=", 1)
            for line in github_environment.read_text(encoding="utf-8").splitlines()
        )
        assert persisted == expected_environment


def test_jobs_check_checkout_residue_after_their_real_work() -> None:
    """Catches CI commands that leave build, coverage, or package metadata behind."""
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)

    for job in jobs.values():
        steps = _steps(job)
        final = steps[-1]
        assert final["name"] == "Verify checkout residue is zero"
        assert final["shell"] == "pwsh"
        assert final["if"] == "always()"
        command = final["run"]
        assert isinstance(command, str)
        assert "hsconfig-ci-source-baseline" in command
        assert "hsconfig-locked-runtime" in command
        assert "pip-cache" in command
        assert "git status --porcelain=v1 --untracked-files=all" in command
        assert "Get-ChildItem -LiteralPath '.' -Recurse -Force -Directory" in command
        assert "'__pycache__'" in command
        assert "'\\.(whl|tar\\.gz)$'" in command
        for relative in CHECKOUT_RESIDUE:
            assert f"'{relative}'" in command

    security_names = [step.get("name") for step in _steps(jobs["security"])]
    assert security_names.index("Bootstrap locked runtime from committed source") < (
        security_names.index("Check repository hygiene through the canonical release bootstrap")
    )
    assert security_names.index(
        "Check repository hygiene through the canonical release bootstrap"
    ) < security_names.index("Verify checkout residue is zero")


def test_every_job_binds_and_materializes_the_event_commit_before_setup_or_download() -> None:
    jobs = _workflow()["jobs"]
    assert isinstance(jobs, dict)

    for job in jobs.values():
        steps = _steps(job)
        assert steps[0]["name"] == RUNNER_ENVIRONMENT_STEP
        assert steps[1]["name"] == "Checkout"
        baseline = steps[2]
        assert baseline["name"] == "Bind and materialize the event commit"
        assert baseline["shell"] == "pwsh"
        command = baseline["run"]
        assert isinstance(command, str)
        assert "--locked-check ci-source-baseline" in command
        assert "$env:GITHUB_SHA" in command
        assert "$env:RUNNER_TEMP" in command
        assert "tar -xf" not in command
        assert steps[3]["name"] == "Set up Python"


def test_security_outputs_and_final_cleanup_stay_in_runner_temp() -> None:
    security = _workflow()["jobs"]["security"]
    commands = "\n".join(_runs(security))

    assert '--outputs "${{ runner.temp }}/security-outputs"' in commands
    assert "--outputs outputs" not in commands
    final = _steps(security)[-1]
    assert final["if"] == "always()"
    assert "hsconfig-ci-source-baseline" in final["run"]
    assert "unsafe_runner_temp_cleanup_target" in final["run"]
    assert "security-outputs" in final["run"]


def test_default_linux_shell_steps_do_not_use_powershell_environment_syntax() -> None:
    jobs = _workflow()["jobs"]

    for name in ("package", "security"):
        for step in _steps(jobs[name]):
            if "run" in step and "shell" not in step:
                assert "$env:" not in step["run"]


def _run_checked(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )


def _cleanup_command() -> str:
    final = _steps(_workflow()["jobs"]["contract"])[-1]
    command = final["run"]
    assert isinstance(command, str)
    return command


def _clean_repository(path: Path) -> None:
    path.mkdir()
    (path / "tracked.txt").write_text("clean\n", encoding="utf-8")
    _run_checked(["git", "init", "-q"], cwd=path)
    _run_checked(["git", "add", "tracked.txt"], cwd=path)
    _run_checked(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=path,
    )


def _create_junction(link: Path, target: Path) -> None:
    environment = os.environ.copy()
    environment.update({"LINK_PATH": str(link), "LINK_TARGET": str(target)})
    _run_checked(
        [
            "pwsh",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "New-Item -ItemType Junction -Path $env:LINK_PATH -Target $env:LINK_TARGET | Out-Null",
        ],
        cwd=target,
        environment=environment,
    )


def _run_cleanup(checkout: Path, runner_temp: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["RUNNER_TEMP"] = str(runner_temp)
    return subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", _cleanup_command()],
        cwd=checkout,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_cleanup_removes_only_a_normal_fixed_child(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _clean_repository(checkout)
    runner_temp = tmp_path / "runner-temp"
    candidate = runner_temp / "pip-cache"
    candidate.mkdir(parents=True)
    (candidate / "payload.txt").write_text("remove", encoding="utf-8")

    completed = _run_cleanup(checkout, runner_temp)

    assert completed.returncode == 0, completed.stderr
    assert not candidate.exists()


def test_cleanup_rejects_an_outside_junction_without_touching_target(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    _clean_repository(checkout)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    candidate = runner_temp / "pip-cache"
    _create_junction(candidate, outside)

    completed = _run_cleanup(checkout, runner_temp)

    assert completed.returncode != 0
    assert candidate.exists()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_cleanup_rejects_an_in_root_redirected_child_without_touching_target(
    tmp_path: Path,
) -> None:
    checkout = tmp_path / "checkout"
    _clean_repository(checkout)
    runner_temp = tmp_path / "runner-temp"
    redirected = runner_temp / "redirected"
    redirected.mkdir(parents=True)
    marker = redirected / "keep.txt"
    marker.write_text("keep", encoding="utf-8")
    candidate = runner_temp / "pip-cache"
    _create_junction(candidate, redirected)

    completed = _run_cleanup(checkout, runner_temp)

    assert completed.returncode != 0
    assert candidate.exists()
    assert marker.read_text(encoding="utf-8") == "keep"


def test_cleanup_uses_platform_case_semantics_for_fixed_children(tmp_path: Path) -> None:
    checkout = tmp_path / "checkout"
    _clean_repository(checkout)
    runner_temp = tmp_path / "runner-temp"
    candidate = runner_temp / "PIP-CACHE"
    candidate.mkdir(parents=True)

    completed = _run_cleanup(checkout, runner_temp)

    assert completed.returncode == 0, completed.stderr
    assert candidate.exists() is (os.name != "nt")


def test_cleanup_inspects_the_lexical_child_before_resolution() -> None:
    command = _cleanup_command()

    assert "$comparison = if ($IsWindows)" in command
    assert "[StringComparison]::OrdinalIgnoreCase" in command
    assert "[StringComparison]::Ordinal" in command
    assert "$item.LinkType" in command
    assert "[IO.FileAttributes]::ReparsePoint" in command
    assert "Remove-Item -LiteralPath $candidate" in command
    assert "Remove-Item -LiteralPath $resolved" not in command


def test_committed_source_install_executes_without_checkout_residue(tmp_path: Path) -> None:
    """Catches project installation that writes build metadata into its checkout."""
    job = _workflow()["jobs"]["contract"]
    step = _named_step(job, "Bootstrap locked runtime from committed source")
    assert step.get("shell") == "pwsh"
    command = step.get("run")
    assert isinstance(command, str)

    repository = tmp_path / "checkout"
    repository.mkdir()
    archive = tmp_path / "checkout.tar"
    _run_checked(
        ["git", "archive", "--format=tar", "-o", str(archive), "HEAD"],
        cwd=ROOT,
    )
    with tarfile.open(archive) as source:
        source.extractall(repository)
    for relative in TASK8_SOURCE_OVERLAY:
        source_path = ROOT / relative
        destination = repository / relative
        if source_path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, destination)
        else:
            destination.unlink(missing_ok=True)
    _run_checked(["git", "init", "-q"], cwd=repository)
    _run_checked(["git", "-c", "core.longpaths=true", "add", "."], cwd=repository)
    _run_checked(
        [
            "git",
            "-c",
            "user.name=CI Contract",
            "-c",
            "user.email=ci-contract@example.invalid",
            "commit",
            "-q",
            "-m",
            "fixture",
        ],
        cwd=repository,
    )

    ambient = tmp_path / "ambient"
    venv.EnvBuilder(with_pip=True, clear=False, symlinks=False).create(ambient)
    runner_temp = tmp_path / "runner-temp"
    runner_temp.mkdir()
    commit_oid = _run_checked(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    github_environment = tmp_path / "github-env"
    baseline_environment = os.environ.copy()
    baseline_environment.update(
        {
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_SHA": commit_oid,
            "GITHUB_ENV": str(github_environment),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    _run_checked(
        [
            sys.executable,
            "scripts/check_release_gate.py",
            "--repo",
            ".",
            "--outputs",
            str(runner_temp / "ci-baseline-outputs"),
            "--tree-mode",
            "working-pre-cutover",
            "--locked-check",
            "ci-source-baseline",
            "--json",
        ],
        cwd=repository,
        environment=baseline_environment,
    )
    baseline_values = dict(
        line.split("=", 1)
        for line in github_environment.read_text(encoding="utf-8").splitlines()
    )
    environment = os.environ.copy()
    current_minor = f"{sys.version_info.major}.{sys.version_info.minor}"
    assert current_minor in {"3.11", "3.12"}
    environment.update(
        {
            "RUNNER_TEMP": str(runner_temp),
            "PIP_CACHE_DIR": str(runner_temp / "pip-cache"),
            "TEMP": str(runner_temp),
            "TMP": str(runner_temp),
            "TMPDIR": str(runner_temp),
            "GITHUB_ENV": str(github_environment),
            "GITHUB_PATH": str(tmp_path / "github-path"),
            "HSCONFIG_PYTHON_MINOR": current_minor,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": str(ambient / ("Scripts" if os.name == "nt" else "bin"))
            + os.pathsep
            + os.environ["PATH"],
        }
    )
    environment.update(baseline_values)
    checkout_lock = repository / f"pylock.{current_minor}.toml"
    _run_checked(
        ["git", "update-index", "--assume-unchanged", checkout_lock.name],
        cwd=repository,
    )
    checkout_lock.write_text("checkout lock must not be read\n", encoding="utf-8")
    before = _run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository,
    ).stdout

    bootstrap_completed = subprocess.run(
        ["pwsh", "-NoProfile", "-NonInteractive", "-Command", command],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert bootstrap_completed.returncode == 0, (
        bootstrap_completed.stdout + bootstrap_completed.stderr
    )

    after = _run_checked(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repository,
    ).stdout
    assert after == before == ""
    assert [relative for relative in CHECKOUT_RESIDUE if (repository / relative).exists()] == []
    locked_environment = runner_temp / "hsconfig-locked-runtime" / "environment"
    locked_python = locked_environment / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    installed = _run_checked(
        [
            str(locked_python),
            "-c",
            "from pathlib import Path; import hsconfig; print(Path(hsconfig.__file__).resolve())",
        ],
        cwd=repository,
    )
    installed_path = Path(installed.stdout.strip())
    assert locked_environment.resolve() in installed_path.parents
    assert repository.resolve() not in installed_path.parents
    overlay = runner_temp / "hsconfig-locked-runtime" / "build-backend"
    assert not list(overlay.rglob("*.pth"))
    overlay_environment = os.environ.copy()
    overlay_environment["PYTHONPATH"] = str(overlay)
    tool_paths = _run_checked(
        [
            str(locked_python),
            "-c",
            "import coverage,setuptools; print(coverage.__file__); print(setuptools.__file__)",
        ],
        cwd=repository,
        environment=overlay_environment,
    ).stdout.splitlines()
    assert len(tool_paths) == 2
    assert all(overlay.resolve() in Path(path).resolve().parents for path in tool_paths)
