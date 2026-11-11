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
$previousPatchId = $null
if (Test-Path -LiteralPath $markerPath) {
    $previous = Read-JsonFile $markerPath
    $previousPatchId = $previous.patch_id
    # Validate the previous rollback and new payload before changing anything.
    & (Join-Path $PSScriptRoot 'Restore-OriginalOink.ps1') -ValidateOnly
    if ($previousPatchId -like 'movement-trail-0.3.4-*') {
        Test-LegacyAlwaysMigration $UserDataPath
    }
} else {
    & (Join-Path $PSScriptRoot 'Install-TrailPatch.ps1') -UserDataPath $UserDataPath -ValidateOnly
}
if ($ValidateOnly) {
    Write-Output 'Overwrite installation validation passed. No installed files or processes were changed.'
    return
}
if ($null -ne $previousPatchId) {
    Write-Output 'Restoring the base files before replacing the previous personal version.'
    & (Join-Path $PSScriptRoot 'Restore-OriginalOink.ps1')
}
& (Join-Path $PSScriptRoot 'Install-TrailPatch.ps1') -UserDataPath $UserDataPath
if ($previousPatchId -like 'movement-trail-0.3.4-*') {
    try { Set-LegacyAlwaysMigration $UserDataPath }
    catch {
        throw ('The new enhanced version is installed, but the previous always-on mode could not be migrated. ' +
            'Pairing and layout are preserved. Open Oink and select the always-on trail mode in settings. Details: ' + $_.Exception.Message)
    }
}
Write-Output 'Overwrite installation complete. Pairing, layout and existing preferences are preserved.'
