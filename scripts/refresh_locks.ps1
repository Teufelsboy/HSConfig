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

    $wheelClosure = Join-Path $PSScriptRoot 'lock_wheel_closure.py'

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
        $case['VenvPython'] = $venvPython
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
        $wheelClosure,
        '--lock-311', $cases[0].Lock,
        '--lock-312', $cases[1].Lock,
        '--constraints', $temporaryConstraints,
        '--pip-version', $pipVersion,
        '--pip-wheel-name', $pipBootstrapWheelName,
        '--pip-wheel-url', $pipBootstrapWheelUrl,
        '--pip-wheel-sha256', $pipBootstrapWheelSha256
    )
    foreach ($case in $cases) {
        $validationRoot = Join-Path $temporaryRoot ("validate-" + $case.Minor)
        New-Item -ItemType Directory -Path $validationRoot | Out-Null
        $canonicalLock = Join-Path $validationRoot 'pylock.toml'
        Copy-Item -LiteralPath $case.Lock -Destination $canonicalLock
        Invoke-Checked -Executable $case.VenvPython -Arguments @(
            '-m', 'pip', 'install', '--dry-run', '--no-deps',
            '--only-binary=:all:', '--no-build-isolation', '-r', $canonicalLock
        )
    }
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
