[CmdletBinding()]
param(
    [string]$RepoRoot = (Get-Location).Path,
    [string]$Repository = 'Teufelsboy/HSConfig',
    [Parameter(Mandatory)][string]$GraphStatePath,
    [string]$GraphStateSha256,
    [string]$OutputsRoot,
    [string]$GithubSnapshotPath,
    [string]$JournalPath,
    [ValidatePattern('^[0-9a-f]{40}$')][string]$ExpectedOldOid,
    [ValidatePattern('^[0-9a-f]{40}$')][string]$NewTipOid,
    [switch]$Recover,
    [string]$OperationAdapterPath,
    [string]$AdapterStatePath,
    [ValidateSet(
        'reversible_github_preflight', 'candidate_verification', 'bundle_creation',
        'final_lease_check', 'remote_main_update', 'local_worktree_sync',
        'exact_oid_ci', 'ruleset_activation', 'tag_creation', 'release_creation',
        'final_cache_cleanup', 'canonical_final_product_gate',
        'persisted_commit_decision', 'bundle_directory_deletion',
        'sibling_journal_deletion'
    )][string]$FaultAfter,
    [ValidateSet(
        'reversible_github_preflight', 'candidate_verification', 'bundle_creation',
        'final_lease_check', 'remote_main_update', 'local_worktree_sync',
        'exact_oid_ci', 'ruleset_activation', 'tag_creation', 'release_creation',
        'final_cache_cleanup', 'canonical_final_product_gate',
        'persisted_commit_decision', 'bundle_directory_deletion',
        'sibling_journal_deletion'
    )][string]$HardKillAfter,
    [ValidateSet('git', 'gh', 'python')][string]$AdapterFailCommand,
    [string]$GitPath = 'git',
    [string]$GhPath = 'gh',
    [string]$PythonPath = 'python',
    [ValidateRange(1, 18000)][int]$NativeTimeoutSeconds = 18000
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$script:Decision = 'rollback'
$script:JournalPayload = $null
$script:RollbackFailed = $false
$script:SimulatedHardKill = $false
$CurrentPowerShellPath = [Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
if ([string]::IsNullOrWhiteSpace($CurrentPowerShellPath) -or -not (Test-Path -LiteralPath $CurrentPowerShellPath -PathType Leaf)) {
    throw 'current_powershell_executable_unavailable'
}
$PhaseOrder = @(
    'initialized', 'preflighted', 'candidate_verified', 'bundle_created',
    'lease_verified', 'remote_updated', 'local_synchronized', 'ci_verified',
    'ruleset_active', 'tag_created', 'release_created', 'cache_cleaned',
    'final_verified', 'committed', 'bundle_deleted'
)

function ConvertTo-NativeArgument {
    param([string]$Value)
    if ($Value -notmatch '[\s"]') { return $Value }
    return '"' + (($Value -replace '(\\*)"', '$1$1\"') -replace '(\\+)$', '$1$1') + '"'
}

function Invoke-CheckedNative {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [int]$TimeoutSeconds = $NativeTimeoutSeconds
    )
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $FilePath
    $start.Arguments = (($ArgumentList | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' ')
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $allowedEnvironment = @(
        'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP',
        'USERPROFILE', 'HOME', 'GH_CONFIG_DIR', 'GH_HOST', 'GH_TOKEN',
        'GITHUB_TOKEN', 'GIT_CONFIG_GLOBAL', 'GIT_CONFIG_SYSTEM', 'SSH_AUTH_SOCK',
        'APPDATA', 'LOCALAPPDATA', 'PROGRAMDATA', 'HOMEDRIVE', 'HOMEPATH'
    )
    $start.EnvironmentVariables.Clear()
    foreach ($name in $allowedEnvironment) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if ($null -ne $value) { $start.EnvironmentVariables[$name] = $value }
    }
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw "native_command_failed:${FilePath}:start" }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            try { $process.Kill() } catch { }
            throw "native_command_timeout:${FilePath}"
        }
        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result
        if ($stdout.Length -gt 4194304 -or $stderr.Length -gt 4194304) {
            throw "native_command_output_too_large:${FilePath}"
        }
        if ($process.ExitCode -ne 0) {
            throw "native_command_failed:${FilePath}:exit=$($process.ExitCode)"
        }
        if ([string]::IsNullOrEmpty($stdout)) { return @() }
        return @($stdout.TrimEnd("`r", "`n") -split "`r?`n")
    } finally {
        $process.Dispose()
    }
}

function Get-Sha256Text {
    param([string]$Text)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Text)))).Replace('-', '').ToLowerInvariant()
    } finally { $algorithm.Dispose() }
}

function Get-CanonicalJson {
    param([object]$Value)
    return ($Value | ConvertTo-Json -Depth 20 -Compress)
}

function Read-DuplicateSafeJson {
    param([string]$Path, [switch]$Envelope)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw 'json_state_missing' }
    $size = (Get-Item -LiteralPath $Path -Force).Length
    if ($size -gt 4194304) { throw 'json_state_too_large' }
    $validator = @'
import hashlib,json,sys
class Duplicate(Exception): pass
def closed(pairs):
 d={}
 for k,v in pairs:
  if k in d: raise Duplicate(k)
  d[k]=v
 return d
try:
 raw=open(sys.argv[1],'rb').read().decode('utf-8-sig')
 value=json.loads(raw,object_pairs_hook=closed)
 if sys.argv[2]=='envelope':
  if set(value)!={'schema_version','payload','payload_sha256'} or value['schema_version']!=1: raise ValueError('schema')
  if not isinstance(value['payload'],str) or not isinstance(value['payload_sha256'],str): raise ValueError('type')
  if hashlib.sha256(value['payload'].encode()).hexdigest()!=value['payload_sha256']: raise ValueError('digest')
  payload=json.loads(value['payload'],object_pairs_hook=closed)
  if json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'))!=value['payload']: raise ValueError('canonical')
  value=payload
 print(json.dumps({'ok':True,'value':value},ensure_ascii=False,separators=(',',':')))
except Duplicate:
 print('{"ok":false,"error":"duplicate_json_key"}')
except ValueError as e:
 print(json.dumps({'ok':False,'error':'journal_digest_mismatch' if str(e)=='digest' else 'json_state_invalid'}))
except Exception:
 print('{"ok":false,"error":"json_state_invalid"}')
'@
    $mode = if ($Envelope) { 'envelope' } else { 'plain' }
    $validatorPath = Join-Path ([IO.Path]::GetTempPath()) ("hsconfig-json-validator-" + [guid]::NewGuid().ToString('N') + '.py')
    try {
        [IO.File]::WriteAllText($validatorPath, $validator, [Text.UTF8Encoding]::new($false))
        $row = ((Invoke-CheckedNative $PythonPath @($validatorPath, $Path, $mode)) -join '') | ConvertFrom-Json
        if (-not $row.ok) { throw [string]$row.error }
        return $row.value
    } finally {
        if (Test-Path -LiteralPath $validatorPath) { Remove-Item -LiteralPath $validatorPath -Force }
    }
}

function Write-AtomicCutoverJournal {
    param([hashtable]$Payload, [string]$Path)
    $canonicalObject = [ordered]@{}
    foreach ($key in @($Payload.Keys | Sort-Object)) { $canonicalObject[$key] = $Payload[$key] }
    $canonical = Get-CanonicalJson $canonicalObject
    $envelope = [ordered]@{
        payload = $canonical
        payload_sha256 = Get-Sha256Text $canonical
        schema_version = 1
    }
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    $backup = "$Path.replace-backup"
    try {
        $bytes = [Text.UTF8Encoding]::new($false).GetBytes((Get-CanonicalJson $envelope))
        $stream = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try {
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        if (Test-Path -LiteralPath $Path) {
            if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
            [IO.File]::Replace($temporary, $Path, $backup, $true)
        } else {
            [IO.File]::Move($temporary, $Path)
        }
    } finally {
        if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
        if (Test-Path -LiteralPath $backup) { Remove-Item -LiteralPath $backup -Force }
    }
}

function Set-JournalPhase {
    param([string]$Phase, [string]$Decision = $script:Decision, [hashtable]$Additional)
    if ($null -eq $script:JournalPayload) { throw 'journal_not_initialized' }
    $currentIndex = [array]::IndexOf($PhaseOrder, [string]$script:JournalPayload.phase)
    $nextIndex = [array]::IndexOf($PhaseOrder, $Phase)
    if ($nextIndex -lt $currentIndex -or $nextIndex -gt ($currentIndex + 1)) {
        throw 'journal_phase_transition_invalid'
    }
    $script:JournalPayload.phase = $Phase
    $script:JournalPayload.decision = $Decision
    if ($null -ne $Additional) {
        foreach ($key in $Additional.Keys) { $script:JournalPayload[$key] = $Additional[$key] }
    }
    Write-AtomicCutoverJournal $script:JournalPayload $JournalPath
    $script:Decision = $Decision
}

function Test-Boundary {
    param([string]$Boundary)
    if ($HardKillAfter -eq $Boundary) {
        $script:SimulatedHardKill = $true
        [Environment]::Exit(97)
    }
    if ($FaultAfter -eq $Boundary) { throw "fault_injected:$Boundary" }
}

function Invoke-AdapterOperation {
    param([string]$Operation)
    if ([string]::IsNullOrWhiteSpace($OperationAdapterPath) -or [string]::IsNullOrWhiteSpace($AdapterStatePath)) {
        throw 'operation_adapter_incomplete'
    }
    Invoke-CheckedNative $CurrentPowerShellPath @(
        '-NoProfile', '-NonInteractive', '-File', $OperationAdapterPath,
        '-Operation', $Operation, '-StatePath', $AdapterStatePath
    ) | Out-Null
}

function Invoke-RealOperation {
    param([string]$Operation)
    $governance = Join-Path $RepoRoot 'scripts/github_governance.py'
    switch ($Operation) {
        'github-preflight' {
            if (-not (Test-Path -LiteralPath $GithubSnapshotPath)) {
                Invoke-CheckedNative $PythonPath @($governance, 'snapshot', '--repo', $Repository, '--out', $GithubSnapshotPath, '--json') | Out-Null
            }
            $preflight = ((Invoke-CheckedNative $PythonPath @($governance, 'preflight', '--repo', $Repository, '--snapshot', $GithubSnapshotPath, '--create-inactive-ruleset', '--json')) -join '') | ConvertFrom-Json
            $script:JournalPayload.inactive_ruleset_id = [int]$preflight.ruleset_id
        }
        'candidate-verify' {
            Invoke-CheckedNative powershell @('-NoProfile', '-NonInteractive', '-File', (Join-Path $RepoRoot 'scripts/verify_curated_history.ps1'), '-NewTipOid', $NewTipOid, '-ExpectedOldOid', $ExpectedOldOid, '-OutputsRoot', $OutputsRoot) | Out-Null
            $dry = ((Invoke-CheckedNative powershell @('-NoProfile', '-NonInteractive', '-File', (Join-Path $RepoRoot 'scripts/sync_curated_worktree.ps1'), '-OldOid', $ExpectedOldOid, '-NewTipOid', $NewTipOid, '-DryRun')) -join '') | ConvertFrom-Json
            $script:JournalPayload.deletion_manifest_sha256 = [string]$dry.manifest_sha256
        }
        'bundle-create' {
            $bundle = Join-Path $script:JournalPayload.state_directory 'pre-v1-main.bundle'
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'bundle', 'create', $bundle, 'refs/heads/main') | Out-Null
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'bundle', 'verify', $bundle) | Out-Null
            $hash = (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant()
            [IO.File]::WriteAllText("$bundle.sha256", "$hash  pre-v1-main.bundle`n", [Text.Encoding]::ASCII)
            $script:JournalPayload.bundle_sha256 = $hash
        }
        'lease-check' {
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'fetch', 'origin', 'main', '--prune', '--tags') | Out-Null
            $remote = @(Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'rev-parse', 'origin/main'))[0]
            if ($remote -ne $ExpectedOldOid) { throw 'remote_main_changed_before_cutover' }
        }
        'remote-update' {
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'push', 'origin', "$NewTipOid`:refs/heads/main", "--force-with-lease=refs/heads/main:$ExpectedOldOid") | Out-Null
        }
        'local-sync' {
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'update-ref', 'refs/heads/main', $NewTipOid, $ExpectedOldOid) | Out-Null
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'reset', '--mixed', $NewTipOid) | Out-Null
            Invoke-CheckedNative powershell @('-NoProfile', '-NonInteractive', '-File', (Join-Path $RepoRoot 'scripts/sync_curated_worktree.ps1'), '-OldOid', $ExpectedOldOid, '-NewTipOid', $NewTipOid, '-Apply', '-ExpectedManifestSha256', $script:JournalPayload.deletion_manifest_sha256) | Out-Null
        }
        'ci' {
            $runs = ((Invoke-CheckedNative $GhPath @('run', 'list', '--repo', $Repository, '--commit', $NewTipOid, '--workflow', 'ci.yml', '--json', 'databaseId,headSha,status,conclusion')) -join '') | ConvertFrom-Json
            if (@($runs).Count -ne 1 -or $runs[0].headSha -ne $NewTipOid) { throw 'exact_oid_ci_run_count_invalid' }
            $runId = [string]$runs[0].databaseId
            $deadline = [DateTime]::UtcNow.AddSeconds(18000)
            $pollFailures = 0
            $view = $null
            while ([DateTime]::UtcNow -lt $deadline) {
                try {
                    $view = ((Invoke-CheckedNative $GhPath @('run', 'view', '--repo', $Repository, $runId, '--json', 'headSha,status,conclusion,jobs')) -join '') | ConvertFrom-Json
                    $pollFailures = 0
                } catch {
                    $pollFailures += 1
                    if ($pollFailures -ge 5) { throw 'exact_oid_ci_poll_failed' }
                    Start-Sleep -Seconds 60
                    continue
                }
                if ($view.headSha -ne $NewTipOid) { throw 'exact_oid_ci_head_mismatch' }
                if ($view.status -eq 'completed') { break }
                Start-Sleep -Seconds 60
            }
            if ($null -eq $view -or $view.status -ne 'completed') { throw 'exact_oid_ci_timeout' }
            if ($view.headSha -ne $NewTipOid -or $view.status -ne 'completed' -or $view.conclusion -ne 'success') { throw 'exact_oid_ci_failed' }
            foreach ($name in @('contract', 'test', 'package', 'security')) {
                if (-not @($view.jobs | Where-Object { $_.name -like "$name*" -and $_.conclusion -eq 'success' })) { throw "exact_oid_ci_job_missing:$name" }
            }
        }
        'ruleset-activate' {
            Invoke-CheckedNative $PythonPath @($governance, 'activate', '--repo', $Repository, '--snapshot', $GithubSnapshotPath, '--ruleset-id', [string]$script:JournalPayload.inactive_ruleset_id, '--json') | Out-Null
        }
        'tag-create' {
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'tag', '-s', 'v1.0.0', '-m', 'HSConfig v1.0.0', $NewTipOid) | Out-Null
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'verify-tag', 'v1.0.0') | Out-Null
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'push', 'origin', 'refs/tags/v1.0.0') | Out-Null
        }
        'release-create' {
            Invoke-CheckedNative $GhPath @('release', 'create', 'v1.0.0', '--repo', $Repository, '--title', 'HSConfig v1.0.0', '--notes-file', (Join-Path $RepoRoot 'docs/contracts/v1.0.0-release-notes.md'), '--verify-tag') | Out-Null
        }
        'cache-cleanup' {
            foreach ($name in @('.pytest_cache', '.ruff_cache', 'build', 'dist')) {
                $target = Join-Path $RepoRoot $name
                if (Test-Path -LiteralPath $target) {
                    $item = Get-Item -LiteralPath $target -Force
                    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "cache_reparse:$name" }
                    Remove-Item -LiteralPath $target -Recurse -Force
                }
            }
        }
        'final-gate' {
            Invoke-CheckedNative $PythonPath @((Join-Path $RepoRoot 'scripts/check_release_gate.py'), '--repo', $RepoRoot, '--outputs', $OutputsRoot, '--tree-mode', 'final', '--json') | Out-Null
            Invoke-CheckedNative $PythonPath @((Join-Path $RepoRoot 'scripts/check_near100_scorecard.py'), '--repo', $RepoRoot, '--outputs', $OutputsRoot, '--mode', 'final', '--json') | Out-Null
            Invoke-CheckedNative $PythonPath @($governance, 'verify-final', '--repo', $Repository, '--ruleset-id', [string]$script:JournalPayload.inactive_ruleset_id, '--json') | Out-Null
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'verify-tag', 'v1.0.0') | Out-Null
        }
        'verify-final' { Invoke-RealOperation 'final-gate' }
        'delete-bundle-dir' {
            $stateDirectory = [string]$script:JournalPayload.state_directory
            $expected = @('curated-graph.json', 'github-settings-before.json', 'pre-v1-main.bundle', 'pre-v1-main.bundle.sha256')
            $actual = @(Get-ChildItem -LiteralPath $stateDirectory -Force | ForEach-Object Name | Sort-Object)
            if (($actual -join "`n") -ne (($expected | Sort-Object) -join "`n")) { throw 'bundle_directory_members_mismatch' }
            Remove-Item -LiteralPath $stateDirectory -Recurse -Force
        }
        'delete-journal' { }
        'rollback-release-tag' {
            $releases = ((Invoke-CheckedNative $GhPath @('release', 'list', '--repo', $Repository, '--limit', '100', '--json', 'tagName')) -join '') | ConvertFrom-Json
            if (@($releases | Where-Object tagName -eq 'v1.0.0')) { Invoke-CheckedNative $GhPath @('release', 'delete', 'v1.0.0', '--repo', $Repository, '--cleanup-tag', '--yes') | Out-Null }
            $localTags = @(Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'tag', '--list', 'v1.0.0'))
            if ($localTags) { Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'tag', '-d', 'v1.0.0') | Out-Null }
        }
        'rollback-github' {
            Invoke-CheckedNative $PythonPath @($governance, 'restore', '--repo', $Repository, '--snapshot', $GithubSnapshotPath, '--json') | Out-Null
            Invoke-CheckedNative $PythonPath @($governance, 'verify-snapshot', '--repo', $Repository, '--snapshot', $GithubSnapshotPath, '--json') | Out-Null
        }
        'rollback-remote' {
            $remoteRows = @(Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'ls-remote', 'origin', 'refs/heads/main'))
            $remote = if ($remoteRows) { ($remoteRows[0] -split "`t")[0] } else { '' }
            if ($remote -eq $NewTipOid) { Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'push', 'origin', "$ExpectedOldOid`:refs/heads/main", "--force-with-lease=refs/heads/main:$NewTipOid") | Out-Null }
            elseif ($remote -ne $ExpectedOldOid) { throw 'rollback_remote_main_unexpected' }
        }
        'rollback-local' {
            $local = @(Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'rev-parse', 'HEAD'))[0]
            if ($local -eq $NewTipOid) { Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'update-ref', 'refs/heads/main', $ExpectedOldOid, $NewTipOid) | Out-Null }
            elseif ($local -ne $ExpectedOldOid) { throw 'rollback_local_main_unexpected' }
            Invoke-CheckedNative $GitPath @('-C', $RepoRoot, 'read-tree', '--reset', '-u', $ExpectedOldOid) | Out-Null
        }
        'verify-rollback' {
            Invoke-CheckedNative $PythonPath @($governance, 'verify-snapshot', '--repo', $Repository, '--snapshot', $GithubSnapshotPath, '--json') | Out-Null
        }
        default { throw "unknown_operation:$Operation" }
    }
}

function Invoke-Operation {
    param([string]$Operation)
    if ($OperationAdapterPath) { Invoke-AdapterOperation $Operation }
    else { Invoke-RealOperation $Operation }
}

function Invoke-Rollback {
    $failures = [Collections.Generic.List[string]]::new()
    foreach ($operation in @('rollback-release-tag', 'rollback-github', 'rollback-remote', 'rollback-local', 'verify-rollback')) {
        try { Invoke-Operation $operation }
        catch { $failures.Add("$operation`:$($_.Exception.Message)") }
    }
    $script:Decision = 'rollback'
    $script:JournalPayload.decision = 'rollback'
    try { Write-AtomicCutoverJournal $script:JournalPayload $JournalPath }
    catch { $failures.Add("journal:$($_.Exception.Message)") }
    if ($failures.Count -gt 0) {
        $script:RollbackFailed = $true
        throw ('rollback_incomplete:' + ($failures -join ','))
    }
}

function Invoke-RollForward {
    Invoke-Operation 'verify-final'
    if (Test-Path -LiteralPath ([string]$script:JournalPayload.state_directory)) {
        Invoke-Operation 'delete-bundle-dir'
    }
    if (Test-Path -LiteralPath $JournalPath) { Remove-Item -LiteralPath $JournalPath -Force }
}

function Get-FileSha256 {
    param([string]$Path)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try {
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    } finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

$RepoRoot = [IO.Path]::GetFullPath($RepoRoot)
if (-not $OutputsRoot) { $OutputsRoot = Join-Path $RepoRoot 'outputs' }
$OutputsRoot = [IO.Path]::GetFullPath($OutputsRoot)

if ($Recover) {
    if (-not $JournalPath) { throw 'recover_journal_path_required' }
    $script:JournalPayload = @{}
    $loaded = Read-DuplicateSafeJson $JournalPath -Envelope
    foreach ($property in $loaded.PSObject.Properties) { $script:JournalPayload[$property.Name] = $property.Value }
    $script:Decision = [string]$script:JournalPayload.decision
    $ExpectedOldOid = [string]$script:JournalPayload.old_oid
    $NewTipOid = [string]$script:JournalPayload.new_oid
    if ($script:Decision -eq 'commit') {
        Invoke-RollForward
        exit 0
    }
    if ($script:Decision -ne 'rollback') { throw 'journal_decision_invalid' }
    Invoke-Rollback
    exit 2
}

$graph = Read-DuplicateSafeJson $GraphStatePath
if (-not $ExpectedOldOid) { $ExpectedOldOid = [string]$graph.old_oid }
if (-not $NewTipOid) { $NewTipOid = [string]$graph.new_tip_oid }
if ($ExpectedOldOid -notmatch '^[0-9a-f]{40}$' -or $NewTipOid -notmatch '^[0-9a-f]{40}$') { throw 'graph_oid_invalid' }
$actualGraphHash = Get-FileSha256 $GraphStatePath
if ($GraphStateSha256 -and $GraphStateSha256 -ne $actualGraphHash) { throw 'curated_graph_state_changed' }
$stateDirectory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($GraphStatePath))
if (-not $JournalPath) { $JournalPath = "$stateDirectory.journal.json" }
$expectedName = '^hsconfig-cutover-[0-9a-f]{32}$'
if ([IO.Path]::GetFileName($stateDirectory) -notmatch $expectedName -or
    [IO.Path]::GetFileName($JournalPath) -ne ([IO.Path]::GetFileName($stateDirectory) + '.journal.json')) {
    throw 'cutover_state_identity_invalid'
}
if (-not $GithubSnapshotPath) { $GithubSnapshotPath = Join-Path $stateDirectory 'github-settings-before.json' }

$script:JournalPayload = @{
    schema_version = 1
    decision = 'rollback'
    phase = 'initialized'
    old_oid = $ExpectedOldOid
    new_oid = $NewTipOid
    state_directory = $stateDirectory
    graph_sha256 = $actualGraphHash
    snapshot_sha256 = if (Test-Path -LiteralPath $GithubSnapshotPath) { Get-FileSha256 $GithubSnapshotPath } else { '' }
}
Write-AtomicCutoverJournal $script:JournalPayload $JournalPath

try {
    if ($AdapterFailCommand) {
        $probePath = switch ($AdapterFailCommand) {
            'git' { $GitPath }
            'gh' { $GhPath }
            'python' { $PythonPath }
        }
        Invoke-CheckedNative $probePath @('--task4-native-failure-probe') | Out-Null
        throw "native_failure_probe_unexpected_success:$AdapterFailCommand"
    }
    Invoke-Operation 'github-preflight'
    $script:JournalPayload.snapshot_sha256 = Get-FileSha256 $GithubSnapshotPath
    Set-JournalPhase 'preflighted'
    Test-Boundary 'reversible_github_preflight'

    Invoke-Operation 'candidate-verify'; Set-JournalPhase 'candidate_verified'; Test-Boundary 'candidate_verification'
    Invoke-Operation 'bundle-create'; Set-JournalPhase 'bundle_created'; Test-Boundary 'bundle_creation'
    Invoke-Operation 'lease-check'; Set-JournalPhase 'lease_verified'; Test-Boundary 'final_lease_check'
    Invoke-Operation 'remote-update'; Set-JournalPhase 'remote_updated'; Test-Boundary 'remote_main_update'
    Invoke-Operation 'local-sync'; Set-JournalPhase 'local_synchronized'; Test-Boundary 'local_worktree_sync'
    Invoke-Operation 'ci'; Set-JournalPhase 'ci_verified'; Test-Boundary 'exact_oid_ci'
    Invoke-Operation 'ruleset-activate'; Set-JournalPhase 'ruleset_active'; Test-Boundary 'ruleset_activation'
    Invoke-Operation 'tag-create'; Set-JournalPhase 'tag_created'; Test-Boundary 'tag_creation'
    Invoke-Operation 'release-create'; Set-JournalPhase 'release_created'; Test-Boundary 'release_creation'
    Invoke-Operation 'cache-cleanup'; Set-JournalPhase 'cache_cleaned'; Test-Boundary 'final_cache_cleanup'
    Invoke-Operation 'final-gate'; Set-JournalPhase 'final_verified'; Test-Boundary 'canonical_final_product_gate'

    Set-JournalPhase 'committed' 'commit'
    Test-Boundary 'persisted_commit_decision'
    Invoke-Operation 'delete-bundle-dir'
    Set-JournalPhase 'bundle_deleted' 'commit'
    Test-Boundary 'bundle_directory_deletion'
    Invoke-Operation 'delete-journal'
    Test-Boundary 'sibling_journal_deletion'
    Remove-Item -LiteralPath $JournalPath -Force
} catch {
    $failure = $_
    if ($script:Decision -eq 'rollback') {
        try { Invoke-Rollback } catch { }
    }
    throw $failure
}
