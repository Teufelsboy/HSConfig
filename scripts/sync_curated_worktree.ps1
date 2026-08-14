[CmdletBinding(DefaultParameterSetName = 'Dry')]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$OldOid,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$NewTipOid,
    [Parameter(Mandatory, ParameterSetName = 'Dry')][switch]$DryRun,
    [Parameter(Mandatory, ParameterSetName = 'Apply')][switch]$Apply,
    [Parameter(Mandatory, ParameterSetName = 'Apply')][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedManifestSha256
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @ArgumentList 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "native_command_failed:${FilePath}:exit=$exitCode"
    }
    return $output
}

function Test-IsBelow {
    param([string]$Candidate, [string]$Parent)
    $prefix = $Parent.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    return $Candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Assert-SafePath {
    param([string]$RepositoryRoot, [string]$RelativePath)
    if ([IO.Path]::IsPathRooted($RelativePath) -or $RelativePath.Contains("`0") -or $RelativePath.Contains("`r") -or $RelativePath.Contains("`n")) {
        throw 'worktree_path_invalid'
    }
    $full = [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $RelativePath))
    if (-not (Test-IsBelow $full $RepositoryRoot)) {
        throw 'worktree_path_escape'
    }
    $current = $RepositoryRoot
    foreach ($component in ($RelativePath -split '/')) {
        $current = Join-Path $current $component
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'worktree_path_reparse'
            }
        }
    }
    return $full
}

function Get-TreePaths {
    param([string]$Oid)
    $rows = @(Invoke-CheckedNative git @('ls-tree', '-r', '--name-only', $Oid))
    $set = [Collections.Generic.HashSet[string]]::new([StringComparer]::Ordinal)
    foreach ($row in $rows) {
        if ([string]::IsNullOrWhiteSpace($row) -or -not $set.Add($row)) {
            throw 'tree_path_inventory_invalid'
        }
    }
    return ,$set
}

$repositoryRoot = [IO.Path]::GetFullPath([string](@(Invoke-CheckedNative git @('rev-parse', '--show-toplevel'))[0]))
Invoke-CheckedNative git @('cat-file', '-e', "$OldOid^{commit}") | Out-Null
Invoke-CheckedNative git @('cat-file', '-e', "$NewTipOid^{commit}") | Out-Null
$oldPaths = Get-TreePaths $OldOid
$newPaths = Get-TreePaths $NewTipOid
$deletions = @($oldPaths | Where-Object { -not $newPaths.Contains($_) } | Sort-Object)
$resolved = [Collections.Generic.List[string]]::new()
foreach ($path in $deletions) {
    $full = Assert-SafePath $repositoryRoot $path
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw ("worktree_path_missing:{0}:resolved={1}:root={2}" -f $path, $full, $repositoryRoot)
    }
    $oldBlob = ([string](@(Invoke-CheckedNative git @('rev-parse', "$OldOid`:$path"))[0])).Trim()
    $currentBlob = ([string](@(Invoke-CheckedNative git @('hash-object', '--path', $path, '--', $full))[0])).Trim()
    if ($currentBlob -ne $oldBlob) {
        throw "worktree_path_modified:$path"
    }
    $resolved.Add($full)
}

$manifestBytes = [Text.Encoding]::UTF8.GetBytes(($deletions -join "`0"))
$sha = [Security.Cryptography.SHA256]::Create()
try {
    $manifestHash = ([BitConverter]::ToString($sha.ComputeHash($manifestBytes))).Replace('-', '').ToLowerInvariant()
} finally {
    $sha.Dispose()
}

if ($Apply) {
    if ($manifestHash -ne $ExpectedManifestSha256) {
        throw 'deletion_manifest_sha256_mismatch'
    }
    for ($index = 0; $index -lt $deletions.Count; $index++) {
        $full = Assert-SafePath $repositoryRoot $deletions[$index]
        $currentBlob = ([string](@(Invoke-CheckedNative git @('hash-object', '--path', $deletions[$index], '--', $full))[0])).Trim()
        $oldBlob = ([string](@(Invoke-CheckedNative git @('rev-parse', "$OldOid`:$($deletions[$index])"))[0])).Trim()
        if ($currentBlob -ne $oldBlob) {
            throw "worktree_path_modified:$($deletions[$index])"
        }
        Remove-Item -LiteralPath $full -Force
    }
    $directories = @($resolved | ForEach-Object { Split-Path -Parent $_ } | Sort-Object Length -Descending -Unique)
    foreach ($directory in $directories) {
        if ($directory -eq $repositoryRoot -or -not (Test-IsBelow $directory $repositoryRoot)) {
            continue
        }
        $item = Get-Item -LiteralPath $directory -Force -ErrorAction SilentlyContinue
        if ($null -ne $item -and -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            if (@(Get-ChildItem -LiteralPath $directory -Force).Count -eq 0) {
                Remove-Item -LiteralPath $directory -Force
            }
        }
    }
}

[ordered]@{
    schema_version = 1
    old_oid = $OldOid
    new_tip_oid = $NewTipOid
    manifest_sha256 = $manifestHash
    paths = @($deletions)
    applied = [bool]$Apply
} | ConvertTo-Json -Depth 4 -Compress
