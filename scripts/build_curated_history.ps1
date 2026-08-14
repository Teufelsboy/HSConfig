[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedOldOid,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$EngineMilestoneOid,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$HardeningMilestoneOid,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$GovernanceMilestoneOid,
    [Parameter(Mandatory)][string]$TemporaryIndexPath,
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ImmutableEngineMilestoneOid = 'b736b4c1501494e555dee38fdd5ce9ea24a00c47'
$Subjects = @(
    'feat: establish the HSConfig pre-run contract engine',
    'feat: add the audited twelve-deck contract catalog',
    'fix: harden atomic publication and pre-run authority',
    'chore: establish proprietary repository governance'
)
$CatalogPaths = @(
    'docs/operator/audited-deck-catalog.json',
    'src/hsconfig/resources/audited_build_inputs.json',
    'src/hsconfig/resources/audited_build_resources.json',
    'tests/test_audited_deck_set_acceptance.py',
    'tests/test_build_input_catalog.py'
)
$ObsoleteOperatorPaths = @(
    'docs/operator/autonomous-source-builder-next.md',
    'docs/operator/boarlock-fracking-source-decision.md',
    'docs/operator/git-branch-cleanup-audit-2026-07-17.md',
    'docs/operator/kingslayer-quick-pick-source-decision.md',
    'docs/operator/source-backed-strong-closure.md',
    'docs/operator/source-builder-workflow.md',
    'docs/operator/universal-wild-no-block-contract.md'
)

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

function Resolve-ExistingDirectory {
    param([Parameter(Mandatory)][string]$Path)
    $item = Get-Item -LiteralPath $Path -Force
    if (-not $item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'temporary_index_parent_unsafe'
    }
    return $item.FullName
}

function Test-IsBelow {
    param([string]$Candidate, [string]$Parent)
    $prefix = $Parent.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
    return $Candidate.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Test-CuratedPath {
    param([Parameter(Mandatory)][string]$Path)
    if ($Path -in $ObsoleteOperatorPaths) {
        return $false
    }
    $forbiddenRoots = @(
        '.agents/', '.superpowers/', 'docs/history/', 'docs/research/',
        'docs/superpowers/', 'outputs/', 'tmp/', 'temp/', '.cutover-candidate/'
    )
    if ($Path -in @('.agents', '.superpowers', 'outputs', 'tmp', 'temp', '.cutover-candidate')) {
        return $false
    }
    foreach ($root in $forbiddenRoots) {
        if ($Path.StartsWith($root, [StringComparison]::Ordinal)) {
            return $false
        }
    }
    return $true
}

function Get-PrunePaths {
    param([string]$MilestoneOid, [switch]$ExcludeCatalog)
    $paths = @(Invoke-CheckedNative git @('ls-tree', '-r', '--name-only', $MilestoneOid))
    $prune = [Collections.Generic.List[string]]::new()
    foreach ($path in $paths) {
        if ([string]::IsNullOrWhiteSpace($path) -or $path.Contains("`n") -or $path.Contains("`r")) {
            throw 'milestone_path_invalid'
        }
        if (-not (Test-CuratedPath $path) -or ($ExcludeCatalog -and $CatalogPaths -contains $path)) {
            $prune.Add($path)
        }
    }
    return @($prune | Sort-Object -Unique)
}

function Get-CuratedTreeRows {
    param([string]$Commitish)
    return @(
        Invoke-CheckedNative git @('ls-tree', '-r', $Commitish) |
            Where-Object {
                $parts = $_ -split "`t", 2
                $parts.Count -eq 2 -and (Test-CuratedPath $parts[1])
            }
    )
}

function Write-PruneFile {
    param([string[]]$Paths, [string]$Path)
    [IO.File]::WriteAllLines($Path, $Paths, [Text.UTF8Encoding]::new($false))
}

function New-CuratedTree {
    param([string]$MilestoneOid, [string]$PruneFile)
    Invoke-CheckedNative git @('read-tree', $MilestoneOid) | Out-Null
    if ((Get-Item -LiteralPath $PruneFile).Length -gt 0) {
        Invoke-CheckedNative git @('rm', '-r', '-f', '--cached', '--ignore-unmatch', "--pathspec-from-file=$PruneFile") | Out-Null
    }
    return [string](@(Invoke-CheckedNative git @('write-tree'))[0])
}

if ($EngineMilestoneOid -ne $ImmutableEngineMilestoneOid) {
    throw 'engine_milestone_oid_mismatch'
}
$requestedIndex = [IO.Path]::GetFullPath($TemporaryIndexPath)
$workingRoot = [IO.Path]::GetFullPath((Get-Location).Path)
$workingPrefix = $workingRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($requestedIndex.StartsWith($workingPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'temporary_index_must_be_external'
}
$repoRoot = [IO.Path]::GetFullPath([string](@(Invoke-CheckedNative git @('rev-parse', '--show-toplevel'))[0]))
$gitDirectoryRaw = [string](@(Invoke-CheckedNative git @('rev-parse', '--git-dir'))[0])
$gitDirectory = if ([IO.Path]::IsPathRooted($gitDirectoryRaw)) {
    [IO.Path]::GetFullPath($gitDirectoryRaw)
} else {
    [IO.Path]::GetFullPath((Join-Path $repoRoot $gitDirectoryRaw))
}
$indexParent = Resolve-ExistingDirectory ([IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($TemporaryIndexPath)))
$temporaryIndex = [IO.Path]::GetFullPath((Join-Path $indexParent ([IO.Path]::GetFileName($TemporaryIndexPath))))
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$repoPrefix = $repoRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$gitPrefix = $gitDirectory.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
$tempPrefix = $tempRoot.TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar) + [IO.Path]::DirectorySeparatorChar
if ($temporaryIndex.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    $temporaryIndex.StartsWith($gitPrefix, [StringComparison]::OrdinalIgnoreCase) -or
    -not $temporaryIndex.StartsWith($tempPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'temporary_index_must_be_external'
}
if (Test-Path -LiteralPath $temporaryIndex) {
    throw 'temporary_index_already_exists'
}

$previousIndex = $env:GIT_INDEX_FILE
$pruneFile = "$temporaryIndex.prune"
try {
    foreach ($oid in @($EngineMilestoneOid, $HardeningMilestoneOid, $GovernanceMilestoneOid, $ExpectedOldOid)) {
        Invoke-CheckedNative git @('cat-file', '-e', "$oid^{commit}") | Out-Null
    }
    $headOid = [string](@(Invoke-CheckedNative git @('rev-parse', 'HEAD'))[0])
    if ($headOid -ne $ExpectedOldOid -or $GovernanceMilestoneOid -ne $ExpectedOldOid) {
        throw 'expected_old_oid_mismatch'
    }
    $env:GIT_INDEX_FILE = $temporaryIndex

    Write-PruneFile (Get-PrunePaths $EngineMilestoneOid -ExcludeCatalog) $pruneFile
    $tree1 = New-CuratedTree $EngineMilestoneOid $pruneFile
    $commit1 = ([string](@(Invoke-CheckedNative git @('commit-tree', '-S', $tree1, '-m', $Subjects[0]))[0])).Trim()

    Write-PruneFile (Get-PrunePaths $EngineMilestoneOid) $pruneFile
    $tree2 = New-CuratedTree $EngineMilestoneOid $pruneFile
    $commit2 = ([string](@(Invoke-CheckedNative git @('commit-tree', '-S', $tree2, '-p', $commit1, '-m', $Subjects[1]))[0])).Trim()

    $catalogDelta = @(Invoke-CheckedNative git @('diff-tree', '--no-commit-id', '--name-only', '-r', $tree1, $tree2) | Sort-Object)
    if (($catalogDelta -join "`n") -ne (($CatalogPaths | Sort-Object) -join "`n")) {
        throw 'catalog_tree_delta_mismatch'
    }

    Write-PruneFile (Get-PrunePaths $HardeningMilestoneOid) $pruneFile
    $tree3 = New-CuratedTree $HardeningMilestoneOid $pruneFile
    $commit3 = ([string](@(Invoke-CheckedNative git @('commit-tree', '-S', $tree3, '-p', $commit2, '-m', $Subjects[2]))[0])).Trim()

    Write-PruneFile (Get-PrunePaths $GovernanceMilestoneOid) $pruneFile
    $tree4 = New-CuratedTree $GovernanceMilestoneOid $pruneFile
    $commit4 = ([string](@(Invoke-CheckedNative git @('commit-tree', '-S', $tree4, '-p', $commit3, '-m', $Subjects[3]))[0])).Trim()

    $expectedRows = @(Get-CuratedTreeRows $GovernanceMilestoneOid)
    $actualRows = @(Invoke-CheckedNative git @('ls-tree', '-r', $tree4))
    if (($actualRows -join "`n") -ne ($expectedRows -join "`n")) {
        throw 'final_curated_tree_mismatch'
    }
    $result = [ordered]@{
        schema_version = 1
        old_oid = $ExpectedOldOid
        engine_milestone_oid = $EngineMilestoneOid
        hardening_milestone_oid = $HardeningMilestoneOid
        governance_milestone_oid = $GovernanceMilestoneOid
        tree_oids = @($tree1, $tree2, $tree3, $tree4)
        commit_oids = @($commit1, $commit2, $commit3, $commit4)
        new_tree_oid = $tree4
        new_tip_oid = $commit4
        subjects = $Subjects
    }
    $result | ConvertTo-Json -Depth 6 -Compress
} finally {
    if ($null -eq $previousIndex) {
        Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
    } else {
        $env:GIT_INDEX_FILE = $previousIndex
    }
    foreach ($path in @($pruneFile, $temporaryIndex)) {
        if (Test-Path -LiteralPath $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}
