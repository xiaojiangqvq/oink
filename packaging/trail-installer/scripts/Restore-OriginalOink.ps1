[CmdletBinding()]
param([switch]$ValidateOnly)

. (Join-Path $PSScriptRoot 'Patch-Common.ps1')

Assert-PatchAdministrator
$installRoot = Get-OinkInstallRoot
Assert-ProtectedInstall $installRoot
$markerPath = Join-Path $installRoot $script:PatchMarkerName
$record = Read-JsonFile $markerPath
if ($record.schema -ne 1 -or $record.install_root -ine $installRoot) {
    throw 'The installed personal-patch record is invalid.'
}
$backupPath = [IO.Path]::GetFullPath($record.backup_path)
Assert-WithinDirectory $backupPath (Join-Path $installRoot 'custom-trail-backups')
$savedRecord = Read-JsonFile (Join-Path $backupPath 'backup-record.json')
if (($savedRecord | ConvertTo-Json -Depth 20 -Compress) -cne ($record | ConvertTo-Json -Depth 20 -Compress)) {
    throw 'The installed patch record differs from its private backup record.'
}
$names = @($record.files | ForEach-Object name | Sort-Object)
if (Compare-Object $names @($script:PatchFileNames | Sort-Object)) {
    throw 'The backup record contains unexpected files.'
}
if ((Get-FileSha256 (Join-Path $installRoot 'installed.json')) -ne
    (Get-FileSha256 (Join-Path $backupPath 'base-installed.json'))) {
    throw 'The Oink MSI installation changed after patching. Do not roll back over a later installed version.'
}
if (Test-Path -LiteralPath (Join-Path $installRoot 'maintenance\pending.json')) {
    throw 'An Oink update transaction is pending. Complete or recover it before restoring.'
}
foreach ($entry in $record.files) {
    if ($entry.before_sha256 -notmatch '^[0-9a-f]{64}$' -or $entry.after_sha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'The backup record has an invalid hash.'
    }
    if ((Get-FileSha256 (Join-Path $backupPath $entry.name)) -ne $entry.before_sha256) {
        throw "Original backup failed verification: $($entry.name)"
    }
    # An interrupted previous restore may already have restored a subset.
    # Permit only exact original or exact patch bytes, never a later binary.
    if ((Get-FileSha256 (Join-Path $installRoot $entry.name)) -notin @($entry.before_sha256, $entry.after_sha256)) {
        throw "Installed file changed after patching; restoration was refused: $($entry.name)"
    }
}
if ($ValidateOnly) {
    Write-Output 'Restore validation passed. No installed files or running processes were changed.'
    return
}

Stop-OinkForPatch $installRoot $record.user_data_path
Restore-BackupFiles $installRoot $backupPath $record
Assert-ProtectedInstall $installRoot
Remove-Item -LiteralPath $markerPath -Force
Write-Output 'Original Oink files restored. Open Oink normally from the Start menu.'
Write-Output 'Current pairing, settings and layout were kept. Private backup files remain on this PC.'
