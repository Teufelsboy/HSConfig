[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pyprojectPath = Join-Path $repositoryRoot 'pyproject.toml'
$pipVersion = '26.1.2'
$pipBootstrapWheelName = 'pip-26.1.2-py3-none-any.whl'
$pipBootstrapWheelUrl = 'https://files.pythonhosted.org/packages/5d/95/6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/pip-26.1.2-py3-none-any.whl'
$pipBootstrapWheelSha256 = '382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab'
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    'hsconfig-lock-refresh-' + [guid]::NewGuid().ToString('N')
)

function Resolve-PythonMinor {
    param([Parameter(Mandatory = $true)][string]$Minor)

    $candidate = $null
    $launcherOutput = $null
    $launcherExitCode = 1
    try {
        $launcherOutput = & py "-$Minor" -c "import sys; print(sys.executable)" 2>$null
        $launcherExitCode = $LASTEXITCODE
    }
    catch {
        $launcherOutput = $null
        $launcherExitCode = 1
    }
    if ($launcherExitCode -eq 0 -and $launcherOutput) {
        $candidate = $launcherOutput.Trim()
    }
    if (-not $candidate) {
        $uvOutput = & uv python find $Minor 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $uvOutput) {
            throw "python_$Minor`_not_found"
        }
        $candidate = $uvOutput.Trim()
    }
    $actualMinor = (& $candidate -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')").Trim()
    if ($LASTEXITCODE -ne 0 -or $actualMinor -ne $Minor) {
        throw "python_minor_mismatch: expected $Minor, got $actualMinor"
    }
    return $candidate
}

function Invoke-Checked {
    param([Parameter(Mandatory = $true)][string]$Executable, [string[]]$Arguments)

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "command_failed: $Executable $($Arguments -join ' ')"
    }
}

function Write-LfUtf8File {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $content = [System.IO.File]::ReadAllText($Source)
    $content = $content -replace "`r`n", "`n"
    $content = $content.TrimEnd("`n") + "`n"
    [System.IO.File]::WriteAllText(
        $Destination,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
}

function Invoke-TrackedOutputTransaction {
    param(
        [Parameter(Mandatory = $true)][hashtable[]]$Artifacts
    )

    $transactionId = [guid]::NewGuid().ToString('N')
    $prepared = @()
    $replaced = @()
    $rollbackFailed = $false
    try {
        foreach ($artifact in $Artifacts) {
            $target = [string]$artifact.Target
            $directory = Split-Path -Parent $target
            $basename = Split-Path -Leaf $target
            $replacement = Join-Path $directory (".$basename.task1-new-$transactionId")
            $backup = Join-Path $directory (".$basename.task1-backup-$transactionId")
            Write-LfUtf8File -Source ([string]$artifact.Source) -Destination $replacement
            if ((Get-Item -LiteralPath $replacement).Length -eq 0) {
                throw "transaction_replacement_empty:$basename"
            }
            $prepared += @{
                Target = $target
                Replacement = $replacement
                Backup = $backup
                OriginalExists = Test-Path -LiteralPath $target
            }
        }
        foreach ($artifact in $prepared) {
            if ($artifact.OriginalExists) {
                [System.IO.File]::Replace(
                    $artifact.Replacement,
                    $artifact.Target,
                    $artifact.Backup,
                    $true
                )
            }
            else {
                [System.IO.File]::Move($artifact.Replacement, $artifact.Target)
            }
            $replaced += $artifact
        }
    }
    catch {
        $transactionError = $_
        for ($index = $replaced.Count - 1; $index -ge 0; $index--) {
            $artifact = $replaced[$index]
            try {
                if ($artifact.OriginalExists -and (Test-Path -LiteralPath $artifact.Backup)) {
                    [System.IO.File]::Replace(
                        $artifact.Backup,
                        $artifact.Target,
                        $null,
                        $true
                    )
                }
                elseif (-not $artifact.OriginalExists -and (Test-Path -LiteralPath $artifact.Target)) {
                    [System.IO.File]::Delete($artifact.Target)
                }
            }
            catch {
                $rollbackFailed = $true
            }
        }
        if ($rollbackFailed) {
            throw "transaction_rollback_failed_after:$($transactionError.Exception.Message)"
        }
        throw $transactionError
    }
    finally {
        foreach ($artifact in $prepared) {
            $cleanupPaths = @($artifact.Replacement)
            if (-not $rollbackFailed) {
                $cleanupPaths += $artifact.Backup
            }
            foreach ($path in $cleanupPaths) {
                if (Test-Path -LiteralPath $path) {
                    [System.IO.File]::Delete($path)
                }
            }
        }
    }
}

try {
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
    $requirementsWriter = Join-Path $temporaryRoot 'write_requirements.py'
    $requirementsWriterContent = @'
from __future__ import annotations

import pathlib
import re
import sys
import tomllib

pyproject_path = pathlib.Path(sys.argv[1])
output_path = pathlib.Path(sys.argv[2])
with pyproject_path.open("rb") as handle:
    data = tomllib.load(handle)
requirements = [
    *data["project"]["dependencies"],
    *data["project"].get("optional-dependencies", {}).get("dev", []),
    *data["build-system"]["requires"],
]
name_pattern = re.compile(r"[<>=!~;[ ]", re.ASCII)
by_name = {}
for requirement in requirements:
    name = name_pattern.split(requirement, maxsplit=1)[0]
    normalized = re.sub(r"[-_.]+", "-", name).lower()
    existing = by_name.get(normalized)
    if existing is not None and existing != requirement:
        raise SystemExit(f"conflicting_requirement_declarations:{normalized}")
    by_name[normalized] = requirement
output_path.write_text(
    "\n".join(by_name[name] for name in sorted(by_name)) + "\n",
    encoding="utf-8",
    newline="\n",
)
'@
    [System.IO.File]::WriteAllText(
        $requirementsWriter,
        $requirementsWriterContent,
        [System.Text.UTF8Encoding]::new($false)
    )

    $lockAugmenter = Join-Path $temporaryRoot 'augment_and_validate_locks.py'
    $lockAugmenterContent = @'
from __future__ import annotations

import json
import pathlib
import re
import sys
import tomllib
import urllib.parse
import urllib.request

lock_paths = [pathlib.Path(value) for value in sys.argv[1:3]]
constraints_path = pathlib.Path(sys.argv[3])
expected_pip = {
    "version": sys.argv[4],
    "name": sys.argv[5],
    "url": sys.argv[6],
    "sha256": sys.argv[7],
}
controlled = {
    "build", "hearthstone", "hypothesis", "pip-audit", "pytest", "pytest-cov",
    "pyyaml", "ruff", "setuptools", "wheel",
}


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def load(path: pathlib.Path) -> dict[str, object]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def archive_is_platform_specific(archive: dict[str, object]) -> bool:
    name = str(archive.get("name", ""))
    return not name.endswith("-py3-none-any.whl")


def source_distribution(name: str, version: str) -> dict[str, str]:
    url = "https://pypi.org/pypi/{}/{}/json".format(
        urllib.parse.quote(name, safe=""), urllib.parse.quote(version, safe="")
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        payload = json.load(response)
    candidates = [
        item for item in payload["urls"]
        if item.get("packagetype") == "sdist" and not item.get("yanked", False)
    ]
    if len(candidates) != 1:
        raise RuntimeError(f"sdist_fallback_not_unique:{name}=={version}")
    candidate = candidates[0]
    digest = candidate.get("digests", {}).get("sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise RuntimeError(f"sdist_hash_missing:{name}=={version}")
    return {"name": candidate["filename"], "url": candidate["url"], "sha256": digest}


def append_sdist(path: pathlib.Path, package_name: str, sdist: dict[str, str]) -> None:
    text = path.read_text(encoding="utf-8")
    block_pattern = re.compile(r"(?ms)^\[\[packages\]\]\n.*?(?=^\[\[packages\]\]|\Z)")
    matched = False

    def replace(match: re.Match[str]) -> str:
        nonlocal matched
        block = match.group(0)
        parsed = tomllib.loads(block)
        package = parsed["packages"][0]
        if package.get("name") != package_name:
            return block
        if "sdist" in package:
            return block
        matched = True
        addition = (
            "\n[packages.sdist]\n"
            f"name = {json.dumps(sdist['name'])}\n"
            f"url = {json.dumps(sdist['url'])}\n\n"
            "[packages.sdist.hashes]\n"
            f"sha256 = {json.dumps(sdist['sha256'])}\n"
        )
        return block.rstrip("\n") + addition

    result = block_pattern.sub(replace, text)
    if not matched:
        raise RuntimeError(f"package_not_found_for_sdist:{package_name}")
    path.write_text(result, encoding="utf-8", newline="\n")


def mapping_and_validate(lock: dict[str, object]) -> dict[str, str]:
    if lock.get("lock-version") != "1.0":
        raise RuntimeError("unsupported_lock_version")
    mapping: dict[str, str] = {}
    for package in lock.get("packages", []):
        if not isinstance(package, dict):
            raise RuntimeError("invalid_package_record")
        name = package.get("name")
        version = package.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            raise RuntimeError("unversioned_package_record")
        normalized = normalize(name)
        if normalized == "hsconfig" or normalized in mapping:
            raise RuntimeError(f"invalid_package_identity:{normalized}")
        if package.get("editable") or any(
            key in package for key in ("directory", "path", "vcs", "git", "source")
        ):
            raise RuntimeError(f"unsafe_package_source:{normalized}")
        archives = [*package.get("wheels", []), *([package["sdist"]] if "sdist" in package else [])]
        if not archives:
            raise RuntimeError(f"missing_archives:{normalized}")
        platform_specific = False
        has_sdist = "sdist" in package
        for archive in archives:
            if not isinstance(archive, dict):
                raise RuntimeError(f"invalid_archive:{normalized}")
            url = archive.get("url")
            digest = archive.get("hashes", {}).get("sha256") if isinstance(archive.get("hashes"), dict) else None
            if not isinstance(url, str) or not url.startswith("https://") or "@" in url:
                raise RuntimeError(f"unsafe_archive_url:{normalized}")
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise RuntimeError(f"missing_archive_hash:{normalized}")
            platform_specific = platform_specific or archive_is_platform_specific(archive)
        if platform_specific and not has_sdist:
            raise RuntimeError(f"missing_sdist_fallback:{normalized}")
        mapping[normalized] = version
    if not controlled <= mapping.keys():
        raise RuntimeError("controlled_requirements_missing:" + ",".join(sorted(controlled - mapping.keys())))
    if "mutmut" in mapping:
        raise RuntimeError("mutmut_forbidden")
    return mapping


def assert_bootstrap_pip(lock: dict[str, object]) -> None:
    records = [
        package for package in lock.get("packages", [])
        if isinstance(package, dict) and package.get("name") == "pip"
    ]
    if len(records) != 1 or records[0].get("version") != expected_pip["version"]:
        raise RuntimeError("bootstrap_pip_version_mismatch")
    wheels = records[0].get("wheels", [])
    expected_wheels = [
        wheel for wheel in wheels
        if isinstance(wheel, dict) and wheel.get("name") == expected_pip["name"]
    ]
    if len(expected_wheels) != 1:
        raise RuntimeError("bootstrap_pip_wheel_missing")
    wheel = expected_wheels[0]
    if wheel.get("url") != expected_pip["url"]:
        raise RuntimeError("bootstrap_pip_url_mismatch")
    hashes = wheel.get("hashes")
    if not isinstance(hashes, dict) or hashes.get("sha256") != expected_pip["sha256"]:
        raise RuntimeError("bootstrap_pip_hash_mismatch")


for lock_path in lock_paths:
    initial = load(lock_path)
    for package in initial.get("packages", []):
        if not isinstance(package, dict) or "sdist" in package:
            continue
        wheels = package.get("wheels", [])
        if any(isinstance(wheel, dict) and archive_is_platform_specific(wheel) for wheel in wheels):
            append_sdist(
                lock_path,
                str(package["name"]),
                source_distribution(str(package["name"]), str(package["version"])),
            )

locks = [load(lock_path) for lock_path in lock_paths]
for lock in locks:
    assert_bootstrap_pip(lock)
mappings = [mapping_and_validate(lock) for lock in locks]
if mappings[0] != mappings[1]:
    raise RuntimeError("interpreter_dependency_version_mismatch")
constraints_path.write_text(
    "".join(f"{name}=={mappings[0][name]}\n" for name in sorted(mappings[0])),
    encoding="utf-8",
    newline="\n",
)
'@
    [System.IO.File]::WriteAllText(
        $lockAugmenter,
        $lockAugmenterContent,
        [System.Text.UTF8Encoding]::new($false)
    )

    $python311 = Resolve-PythonMinor '3.11'
    $python312 = Resolve-PythonMinor '3.12'
    $bootstrapWheel = Join-Path $temporaryRoot $pipBootstrapWheelName
    Invoke-WebRequest -Uri $pipBootstrapWheelUrl -OutFile $bootstrapWheel
    $bootstrapHash = (Get-FileHash -LiteralPath $bootstrapWheel -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($bootstrapHash -ne $pipBootstrapWheelSha256) {
        throw 'bootstrap_pip_hash_mismatch'
    }
    $cases = @(
        @{ Minor = '3.11'; Python = $python311; Lock = (Join-Path $temporaryRoot 'pylock.3.11.toml') },
        @{ Minor = '3.12'; Python = $python312; Lock = (Join-Path $temporaryRoot 'pylock.3.12.toml') }
    )
    foreach ($case in $cases) {
        $venvRoot = Join-Path $temporaryRoot ("venv-" + $case.Minor)
        Invoke-Checked -Executable $case.Python -Arguments @('-m', 'venv', $venvRoot)
        $venvPython = Join-Path $venvRoot 'Scripts\python.exe'
        Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'install', '--no-deps', $bootstrapWheel)
        $actualPip = (& $venvPython -m pip --version)
        if ($LASTEXITCODE -ne 0 -or $actualPip -notmatch "pip $([regex]::Escape($pipVersion)) ") {
            throw "pip_version_mismatch:$($case.Minor)"
        }
        $requirementsPath = Join-Path $temporaryRoot ("requirements-" + $case.Minor + '.txt')
        Invoke-Checked -Executable $venvPython -Arguments @($requirementsWriter, $pyprojectPath, $requirementsPath)
        Invoke-Checked -Executable $venvPython -Arguments @('-m', 'pip', 'lock', '--output', $case.Lock, '--requirement', $requirementsPath, '--no-cache-dir')
    }
    $temporaryConstraints = Join-Path $temporaryRoot 'constraints-ci.txt'
    Invoke-Checked -Executable $python311 -Arguments @(
        $lockAugmenter,
        $cases[0].Lock,
        $cases[1].Lock,
        $temporaryConstraints,
        $pipVersion,
        $pipBootstrapWheelName,
        $pipBootstrapWheelUrl,
        $pipBootstrapWheelSha256
    )
    Invoke-TrackedOutputTransaction -Artifacts @(
        @{ Source = $cases[0].Lock; Target = (Join-Path $repositoryRoot 'pylock.3.11.toml') },
        @{ Source = $cases[1].Lock; Target = (Join-Path $repositoryRoot 'pylock.3.12.toml') },
        @{ Source = $temporaryConstraints; Target = (Join-Path $repositoryRoot 'constraints-ci.txt') }
    )
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
