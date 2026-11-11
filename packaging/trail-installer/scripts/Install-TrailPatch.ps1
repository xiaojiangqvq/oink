[CmdletBinding()]
param(
    [string]$UserDataPath = (Join-Path $env:LOCALAPPDATA 'Oink'),
    [switch]$ValidateOnly
)

. (Join-Path $PSScriptRoot 'Patch-Common.ps1')

Assert-PatchAdministrator
$installRoot = Get-OinkInstallRoot
$manifest = Read-PatchManifest $PSScriptRoot
Assert-BaseInstallation $installRoot $manifest
$markerPath = Join-Path $installRoot $script:PatchMarkerName
if (Test-Path -LiteralPath $markerPath) {
    throw 'A personal trail patch is already recorded. Restore it before applying another patch.'
}
$version = (Get-Item -LiteralPath (Join-Path $installRoot 'oink.exe')).VersionInfo.ProductVersion
if ($version -ne '0.3.4') { throw "Unexpected installed executable version: $version" }
if ($ValidateOnly) {
    Write-Output 'Validation passed. No installed files or running processes were changed.'
    return
}

Write-Output 'Closing Oink gracefully. Keep Oink closed until this script finishes.'
Stop-OinkForPatch $installRoot $UserDataPath
$backupPath = New-PrivateBackupDirectory $installRoot
Backup-OinkUserSettings $UserDataPath $backupPath
$entries = @()
foreach ($name in $script:PatchFileNames) {
    $installed = Join-Path $installRoot $name
    $saved = Join-Path $backupPath $name
    $sddl = (Get-Acl -LiteralPath $installed).GetSecurityDescriptorSddlForm(
        [Security.AccessControl.AccessControlSections]::Access -bor
        [Security.AccessControl.AccessControlSections]::Owner -bor
        [Security.AccessControl.AccessControlSections]::Group)
    Copy-Item -LiteralPath $installed -Destination $saved
    $hash = Get-FileSha256 $installed
    if ((Get-FileSha256 $saved) -ne $hash) { throw "Backup failed: $name" }
    $entries += [pscustomobject]@{
        name = $name
        before_sha256 = $hash
        after_sha256 = $manifest.files.$name
        acl_sddl = $sddl
    }
}
$record = [pscustomobject]@{
    schema = 1
    patch_id = $manifest.patch_id
    installed_utc = [DateTime]::UtcNow.ToString('o')
    install_root = $installRoot
    user_data_path = [IO.Path]::GetFullPath($UserDataPath)
    backup_path = $backupPath
    base_source_tree_sha256 = $manifest.base_source_tree_sha256
    source_tree_sha256 = $manifest.source_tree_sha256
    files = $entries
}
Write-JsonFile (Join-Path $backupPath 'backup-record.json') $record
Copy-Item -LiteralPath (Join-Path $installRoot 'installed.json') -Destination (Join-Path $backupPath 'base-installed.json')

try {
    # Record rollback information before touching any payload, including for an
    # interrupted installation. A failed automatic restore leaves this marker.
    Write-JsonFile $markerPath $record
    foreach ($entry in $entries) {
        $source = Join-Path (Join-Path $PSScriptRoot 'payload') $entry.name
        $target = Join-Path $installRoot $entry.name
        Install-VerifiedFileAtomically $source $target $entry.after_sha256 $entry.acl_sddl
    }
    Assert-ProtectedInstall $installRoot
} catch {
    $failure = $_
    Restore-BackupFiles $installRoot $backupPath $record
    if (Test-Path -LiteralPath $markerPath) { Remove-Item -LiteralPath $markerPath -Force }
    throw "Patch failed; original files were restored. Open Oink normally from Start. Cause: $($failure.Exception.Message)"
}

Write-Output "Patch installed. Backup: $backupPath"
Write-Output 'Open Oink from the Start menu in your normal Windows desktop session.'
Write-Output 'The system service, MSI receipt, pairing and layout were preserved. Repeat with this bundle on the other PC; never copy either PC user-settings backup to the other PC.'
