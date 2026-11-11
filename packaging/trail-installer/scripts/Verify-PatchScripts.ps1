# Exercises manifest validation and rollback helpers using tiny fake PE files.
# This never invokes either deployment script or touches an Oink installation.
[CmdletBinding()]
param()
. (Join-Path $PSScriptRoot 'Patch-Common.ps1')

$fixture = Join-Path ([IO.Path]::GetTempPath()) ('oink-trail-script-check-' + [Guid]::NewGuid().ToString('N'))
$payload = Join-Path $fixture 'payload'
[void](New-Item -ItemType Directory -Path $payload -Force)
$image = New-Object byte[] 256
$image[0] = 0x4D
$image[1] = 0x5A
$image[0x3C] = 0x80
$image[0x80] = 0x50
$image[0x81] = 0x45
$image[0x84] = 0x64
$image[0x85] = 0x86
[IO.File]::WriteAllBytes((Join-Path $payload 'oink.exe'), $image)
[IO.File]::WriteAllBytes((Join-Path $payload 'oink-agent.exe'), $image)
$tree = 'a' * 64
Write-JsonFile (Join-Path $payload 'report-manifest.json') @{ source_tree_sha256 = $tree }
Write-JsonFile (Join-Path $payload 'oink-build.json') @{ source_tree_sha256 = $tree }
$hashes = @{}
foreach ($name in $script:PatchFileNames) { $hashes[$name] = Get-FileSha256 (Join-Path $payload $name) }
$manifest = [ordered]@{
    schema = 1
    kind = 'personal-oink-movement-trail-patch'
    patch_id = 'fixture'
    base_version = '0.3.4'
    base_build = 108
    architecture = 'x64'
    base_source_tree_sha256 = 'b' * 64
    source_tree_sha256 = $tree
    files = $hashes
}
$manifestPath = Join-Path $fixture 'manifest.json'
Write-JsonFile $manifestPath $manifest
[void](Read-PatchManifest $fixture)
Write-Output 'PASS: valid manifest and x64 payload'

function Assert-Rejected([scriptblock]$Action, [string]$Name) {
    $rejected = $false
    try { & $Action } catch { $rejected = $true }
    if (-not $rejected) { throw "Expected rejection: $Name" }
    Write-Output "PASS: rejects $Name"
}

$manifest.architecture = 'arm64'
Write-JsonFile $manifestPath $manifest
Assert-Rejected { Read-PatchManifest $fixture } 'incompatible architecture'
$manifest.architecture = 'x64'
$manifest.files['unexpected.exe'] = 'a' * 64
Write-JsonFile $manifestPath $manifest
Assert-Rejected { Read-PatchManifest $fixture } 'unexpected payload filename'
$manifest.files.Remove('unexpected.exe')
$manifest.files['oink.exe'] = 'c' * 64
Write-JsonFile $manifestPath $manifest
Assert-Rejected { Read-PatchManifest $fixture } 'tampered payload'
$manifest.files['oink.exe'] = Get-FileSha256 (Join-Path $payload 'oink.exe')
$manifest.source_tree_sha256 = 'd' * 64
Write-JsonFile $manifestPath $manifest
Assert-Rejected { Read-PatchManifest $fixture } 'mismatched build metadata'
$manifest.source_tree_sha256 = $tree
Write-JsonFile $manifestPath $manifest
Assert-Rejected { Assert-WithinDirectory (Join-Path $fixture '..\outside') $fixture } 'path traversal'
$jsonHash = Get-FileSha256 $manifestPath
$jsonLock = [IO.File]::Open($manifestPath, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    Assert-Rejected { Write-JsonFile $manifestPath @{ replacement = 'must not commit' } } 'locked JSON replacement'
} finally { $jsonLock.Dispose() }
if ((Get-FileSha256 $manifestPath) -ne $jsonHash) { throw 'Failed JSON replacement damaged the original record.' }
[void](Read-PatchManifest $fixture)
Write-Output 'PASS: failed atomic JSON write preserves complete previous record'

$fakeInstall = Join-Path $fixture 'fake-install'
$fakeBackup = Join-Path $fixture 'fake-backup'
[void](New-Item -ItemType Directory -Path $fakeInstall, $fakeBackup)
$entries = @()
foreach ($name in $script:PatchFileNames) {
    $target = Join-Path $fakeInstall $name
    $backup = Join-Path $fakeBackup $name
    [IO.File]::WriteAllText($target, 'modified fixture')
    [IO.File]::WriteAllText($backup, 'original fixture')
    $entries += [pscustomobject]@{
        name = $name
        before_sha256 = Get-FileSha256 $backup
        acl_sddl = (Get-Acl -LiteralPath $target).GetSecurityDescriptorSddlForm(
            [Security.AccessControl.AccessControlSections]::Access -bor
            [Security.AccessControl.AccessControlSections]::Owner -bor
            [Security.AccessControl.AccessControlSections]::Group)
    }
}
Restore-BackupFiles $fakeInstall $fakeBackup ([pscustomobject]@{ files = $entries })
foreach ($entry in $entries) {
    $installed = Join-Path $fakeInstall $entry.name
    if ((Get-FileSha256 $installed) -ne $entry.before_sha256) {
        throw 'Isolated rollback verification failed.'
    }
    $sddl = (Get-Acl -LiteralPath $installed).GetSecurityDescriptorSddlForm(
        [Security.AccessControl.AccessControlSections]::Access -bor
        [Security.AccessControl.AccessControlSections]::Owner -bor
        [Security.AccessControl.AccessControlSections]::Group)
    if (-not (Test-EquivalentFileAcl $entry.acl_sddl $sddl)) { throw 'Isolated rollback did not preserve the original ACL.' }
}
Write-Output 'PASS: rollback restores all four files and original ACLs in isolated fixture'
$originalInherited = 'O:SYG:SYD:(A;ID;FA;;;SY)(A;ID;FA;;;BA)(A;ID;0x1200a9;;;BU)'
foreach ($flags in @('AI', 'AR', 'ARAI')) {
    if (-not (Test-EquivalentFileAcl $originalInherited ($originalInherited.Replace('D:', ('D:' + $flags))))) {
        throw "Informational DACL inheritance flags incorrectly rejected: $flags"
    }
}
foreach ($changed in @(
    $originalInherited.Replace('O:SY', 'O:BA'),
    $originalInherited.Replace('G:SY', 'G:BA'),
    $originalInherited.Replace('0x1200a9', 'FA'),
    $originalInherited.Replace('D:', 'D:P'),
    $originalInherited.Replace('(A;ID;0x1200a9;;;BU)', '(A;OICI;0x1200a9;;;BU)'),
    $originalInherited.Replace('(A;ID;FA;;;SY)', '(D;ID;FA;;;SY)'),
    'O:SYG:SYD:',
    'O:SYG:SY'
)) {
    if (Test-EquivalentFileAcl $originalInherited $changed) { throw 'A real security-descriptor change was incorrectly accepted.' }
}
if (Test-EquivalentFileAcl 'O:SYG:SYD:' 'O:SYG:SY') { throw 'Empty and absent DACLs must remain different.' }
Write-Output 'PASS: ignores only AI/AR metadata; rejects changed owner/group, access, protection, ACE inheritance/type and empty/absent DACLs'
$candidate = Join-Path $payload 'oink.exe'
$candidateHash = Get-FileSha256 $candidate
$atomicTarget = Join-Path $fakeInstall 'oink.exe'
$originalHash = Get-FileSha256 $atomicTarget
$originalAcl = $entries[0].acl_sddl
Assert-Rejected { Install-VerifiedFileAtomically $candidate $atomicTarget ('d' * 64) $originalAcl } 'invalid staged payload hash'
if ((Get-FileSha256 $atomicTarget) -ne $originalHash) { throw 'A staging failure changed the installed target.' }
$targetLock = [IO.File]::Open($atomicTarget, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
try {
    Assert-Rejected { Install-VerifiedFileAtomically $candidate $atomicTarget $candidateHash $originalAcl } 'locked atomic replacement'
} finally { $targetLock.Dispose() }
if ((Get-FileSha256 $atomicTarget) -ne $originalHash) { throw 'A failed replacement changed the installed target.' }
Install-VerifiedFileAtomically $candidate $atomicTarget $candidateHash $originalAcl
if ((Get-FileSha256 $atomicTarget) -ne $candidateHash) { throw 'The atomic replacement did not install complete candidate bytes.' }
Restore-BackupFiles $fakeInstall $fakeBackup ([pscustomobject]@{ files = $entries })
if ((Get-FileSha256 $atomicTarget) -ne $originalHash) { throw 'Atomic rollback did not restore complete original bytes.' }
$stages = @(Get-ChildItem -LiteralPath $fixture, $fakeInstall -File -Force | Where-Object Name -Match '\.trail-(stage|json)-')
if ($stages.Count) { throw 'A completed or rejected operation failed to clean its exact staging file.' }
Write-Output 'PASS: failed staging/replacement preserves old bytes; commit and rollback preserve complete bytes and clean owned stages'
[IO.File]::WriteAllText((Join-Path $fakeBackup 'oink.exe'), 'corrupt fixture')
Assert-Rejected { Restore-BackupFiles $fakeInstall $fakeBackup ([pscustomobject]@{ files = $entries }) } 'corrupted backup'
$legacyProfile = Join-Path $fixture 'legacy-profile'
[void](New-Item -ItemType Directory -Path $legacyProfile)
$legacySettings = Join-Path $legacyProfile 'settings.json'
Write-JsonFile $legacySettings ([pscustomobject]@{
    schema = 1
    device_options_cbor = 'opaque-owner-envelope-preserved'
    local = [pscustomobject]@{ untouched = [pscustomobject]@{ value = 42 } }
})
Set-LegacyAlwaysMigration $legacyProfile
$migrated = Read-JsonFile $legacySettings
if ($migrated.local.routing.cursor_trail_always -ne $true -or
    $migrated.device_options_cbor -cne 'opaque-owner-envelope-preserved' -or $migrated.local.untouched.value -ne 42) {
    throw 'Legacy always-on migration did not preserve the settings envelope.'
}
$migrated.local.routing.cursor_trail_always = $false
Write-JsonFile $legacySettings $migrated
$beforeMigrationHash = Get-FileSha256 $legacySettings
Set-LegacyAlwaysMigration $legacyProfile
if ((Get-FileSha256 $legacySettings) -ne $beforeMigrationHash) { throw 'Explicit circle-mode preference was overwritten.' }
Write-Output 'PASS: legacy always-mode migration preserves opaque data/unknown fields and existing explicit circle choice'
$maintenance = Join-Path $fakeInstall 'maintenance'
[void](New-Item -ItemType Directory -Path $maintenance)
$maintenanceLock = Open-OinkMaintenanceLock $fakeInstall
try {
    Assert-Rejected { Open-OinkMaintenanceLock $fakeInstall } 'concurrent upstream maintenance lock'
} finally { $maintenanceLock.Dispose() }
$maintenanceLock = Open-OinkMaintenanceLock $fakeInstall
$maintenanceLock.Dispose()
Write-JsonFile (Join-Path $maintenance 'pending.json') @{ fixture = $true }
Assert-Rejected { Open-OinkMaintenanceLock $fakeInstall } 'pending upstream maintenance transaction'
# Rejection must release its handle. A direct exclusive open proves that no
# handle was leaked without deleting the fixture's pending record.
$probe = [IO.File]::Open((Join-Path $maintenance 'maintenance.lock'), [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
$probe.Dispose()
Write-Output 'PASS: shared maintenance locking excludes updates and releases correctly on completion/rejection'
Write-Output "All checks passed. Harmless fixture retained at: $fixture"
