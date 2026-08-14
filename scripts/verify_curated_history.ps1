[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$NewTipOid,
    [Parameter(Mandatory)][ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedOldOid,
    [Parameter(Mandatory)][string]$OutputsRoot
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Subjects = @(
    'feat: establish the HSConfig pre-run contract engine',
    'feat: add the audited twelve-deck contract catalog',
    'fix: harden atomic publication and pre-run authority',
    'chore: establish proprietary repository governance'
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

function Test-ReparsePath {
    param([string]$Root, [string]$RelativePath)
    $current = $Root
    foreach ($component in ($RelativePath -split '[\\/]')) {
        $current = Join-Path $current $component
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                return $true
            }
        }
    }
    return $false
}

function Test-CuratedPath {
    param([Parameter(Mandatory)][string]$Path)
    if ($Path -in $ObsoleteOperatorPaths) { return $false }
    foreach ($root in @(
        '.agents/', '.superpowers/', 'docs/history/', 'docs/research/',
        'docs/superpowers/', 'outputs/', 'tmp/', 'temp/', '.cutover-candidate/'
    )) {
        if ($Path.StartsWith($root, [StringComparison]::Ordinal)) { return $false }
    }
    return $Path -notin @('.agents', '.superpowers', 'outputs', 'tmp', 'temp', '.cutover-candidate')
}

$repoRoot = [IO.Path]::GetFullPath([string](@(Invoke-CheckedNative git @('rev-parse', '--show-toplevel'))[0]))
$outputs = [IO.Path]::GetFullPath((Resolve-Path -LiteralPath $OutputsRoot).Path)
if (-not $outputs.StartsWith($repoRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'outputs_root_must_belong_to_repository'
}
$commits = @(Invoke-CheckedNative git @('rev-list', $NewTipOid))
if ($commits.Count -ne 4) {
    throw 'curated_commit_count_mismatch'
}
$ordered = @($commits | Select-Object -Last 1), @($commits | Select-Object -SkipLast 1 | Sort-Object { [array]::IndexOf($commits, $_) } -Descending)
$ordered = @($commits[3], $commits[2], $commits[1], $commits[0])
for ($index = 0; $index -lt 4; $index++) {
    $commit = $ordered[$index]
    $subject = ([string](@(Invoke-CheckedNative git @('show', '-s', '--format=%s', $commit))[0])).Trim()
    if ($subject -ne $Subjects[$index]) {
        throw "curated_subject_mismatch:$index"
    }
    $parentsText = ([string](@(Invoke-CheckedNative git @('show', '-s', '--format=%P', $commit))[0])).Trim()
    $parents = @()
    if ($parentsText) {
        $parents = @($parentsText -split ' ')
    }
    $expectedParentCount = if ($index -eq 0) { 0 } else { 1 }
    if (@($parents).Count -ne $expectedParentCount) {
        throw "curated_parent_shape_mismatch:$index"
    }
    if ($index -gt 0 -and $parents[0] -ne $ordered[$index - 1]) {
        throw "curated_parent_identity_mismatch:$index"
    }
    Invoke-CheckedNative git @('verify-commit', $commit) | Out-Null
}
$newTree = ([string](@(Invoke-CheckedNative git @('rev-parse', "$NewTipOid^{tree}"))[0])).Trim()
$expectedRows = @(
    Invoke-CheckedNative git @('ls-tree', '-r', $ExpectedOldOid) |
        Where-Object {
            $parts = $_ -split "`t", 2
            $parts.Count -eq 2 -and (Test-CuratedPath $parts[1])
        }
)
$actualRows = @(Invoke-CheckedNative git @('ls-tree', '-r', $NewTipOid))
if (($actualRows -join "`n") -ne ($expectedRows -join "`n")) {
    throw 'curated_final_tree_mismatch'
}
$paths = @(Invoke-CheckedNative git @('ls-tree', '-r', '--name-only', $NewTipOid))
foreach ($path in $paths) {
    if ($path -eq '.agents' -or $path.StartsWith('.agents/', [StringComparison]::Ordinal) -or
        $path.StartsWith('.superpowers/', [StringComparison]::Ordinal) -or
        $path.StartsWith('docs/history/', [StringComparison]::Ordinal) -or
        $path.StartsWith('docs/research/', [StringComparison]::Ordinal) -or
        $path.StartsWith('docs/superpowers/', [StringComparison]::Ordinal) -or
        $path.StartsWith('outputs/', [StringComparison]::Ordinal)) {
        throw "curated_disallowed_path:$path"
    }
}

$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$temporaryIndex = Join-Path $tempRoot ("hsconfig-verify-" + [guid]::NewGuid().ToString('N') + '.index')
$candidateRoot = Join-Path $repoRoot '.cutover-candidate'
$candidate = Join-Path $candidateRoot ([guid]::NewGuid().ToString('N'))
try {
    $env:GIT_INDEX_FILE = $temporaryIndex
    Invoke-CheckedNative git @('read-tree', $NewTipOid) | Out-Null
    Invoke-CheckedNative python @(
        (Join-Path $repoRoot 'scripts/check_publishable_tree.py'),
        '--root', $repoRoot, '--mode', 'candidate-index', '--index-file', $temporaryIndex, '--json'
    ) | Out-Null
    Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue

    if (-not (Test-Path -LiteralPath $candidateRoot)) {
        New-Item -ItemType Directory -Path $candidateRoot | Out-Null
    }
    if (Test-ReparsePath $repoRoot '.cutover-candidate') {
        throw 'candidate_root_reparse'
    }
    Invoke-CheckedNative git @('clone', '--quiet', '--no-checkout', '--no-hardlinks', $repoRoot, $candidate) | Out-Null
    $ownerOrigin = ([string](@(Invoke-CheckedNative git @('-C', $repoRoot, 'remote', 'get-url', 'origin'))[0])).Trim()
    Invoke-CheckedNative git @('-C', $candidate, 'remote', 'set-url', 'origin', $ownerOrigin) | Out-Null
    Invoke-CheckedNative git @('-C', $candidate, 'update-ref', '--no-deref', 'HEAD', $NewTipOid) | Out-Null
    Invoke-CheckedNative git @('-C', $candidate, 'read-tree', '--reset', '-u', $NewTipOid) | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $candidate -Recurse -Force) {
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw 'candidate_member_reparse'
        }
    }
    Invoke-CheckedNative python @(
        (Join-Path $candidate 'scripts/check_release_gate.py'),
        '--repo', $candidate, '--outputs', $outputs, '--owner-repo', $repoRoot,
        '--tree-mode', 'candidate', '--internal-check', 'publishable_path_scan', '--json'
    ) | Out-Null
    [ordered]@{
        schema_version = 1
        passed = $true
        new_tip_oid = $NewTipOid
        new_tree_oid = $newTree
        commit_oids = $ordered
    } | ConvertTo-Json -Depth 4 -Compress
} finally {
    Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $temporaryIndex) {
        Remove-Item -LiteralPath $temporaryIndex -Force
    }
    if (Test-Path -LiteralPath $candidate) {
        if (Test-ReparsePath $repoRoot ('.cutover-candidate/' + [IO.Path]::GetFileName($candidate))) {
            throw 'candidate_cleanup_reparse'
        }
        Remove-Item -LiteralPath $candidate -Recurse -Force
    }
    if ((Test-Path -LiteralPath $candidateRoot) -and @(Get-ChildItem -LiteralPath $candidateRoot -Force).Count -eq 0) {
        Remove-Item -LiteralPath $candidateRoot -Force
    }
}
