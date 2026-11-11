[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Install', 'Restore', 'Upgrade')]
    [string]$Action,
    [string]$UserDataPath = (Join-Path $env:LOCALAPPDATA 'Oink'),
    [switch]$ValidateOnly,
    [switch]$Elevated,
    [ValidatePattern('^[0-9]{8}-[0-9]{6}-[a-f0-9]{8}$')]
    [string]$RunId = ((Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0, 8))
)

. (Join-Path $PSScriptRoot 'Patch-Common.ps1')

$logDirectory = Join-Path $PSScriptRoot 'logs'
Assert-NoReparsePath $logDirectory
[void](New-Item -ItemType Directory -Path $logDirectory -Force)
$logPath = Join-Path $logDirectory ($Action + '-' + $RunId + '.log')
$resultPath = Join-Path $logDirectory ($Action + '-' + $RunId + '.json')
$latestPath = Join-Path $logDirectory ($Action + '-latest.json')
foreach ($path in @($logPath, $resultPath, $latestPath)) { Assert-NoReparsePath $path }

function Save-PatchRunResult([int]$Code, [string]$Message) {
    $result = [pscustomobject]@{
        schema = 1
        action = $Action
        run_id = $RunId
        validate_only = [bool]$ValidateOnly
        success = ($Code -eq 0)
        exit_code = $Code
        finished_utc = [DateTime]::UtcNow.ToString('o')
        log_path = $logPath
        message = $Message
    }
    Write-JsonFile $resultPath $result
    Write-JsonFile $latestPath $result
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin -and -not $Elevated) {
    # Preserve the initiating user's profile path across UAC. The deployment
    # script still requires its normal authenticated graceful-shutdown IPC.
    $powershellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if ([Environment]::Is64BitOperatingSystem -and -not [Environment]::Is64BitProcess) {
        $powershellPath = Join-Path $env:SystemRoot 'Sysnative\WindowsPowerShell\v1.0\powershell.exe'
    }
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass',
        '-File', ('"' + $PSCommandPath + '"'),
        '-Action', $Action, '-Elevated', '-RunId', $RunId,
        '-UserDataPath', ('"' + [IO.Path]::GetFullPath($UserDataPath) + '"')
    )
    if ($ValidateOnly) { $arguments += '-ValidateOnly' }
    try {
        Write-Output 'Windows will request Administrator permission. Confirm UAC to continue.'
        $child = Start-Process -FilePath $powershellPath -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -PassThru -Wait
        $code = $child.ExitCode
        if ($null -eq $code) { $code = 1 }
        if (-not (Test-Path -LiteralPath $resultPath)) {
            Save-PatchRunResult $code 'The elevated process ended before it wrote a result. Check the log if present.'
        }
        if ($code -eq 0) {
            Write-Output 'Completed. Open Oink normally from the Start menu.'
        } else {
            Write-Output "Failed or cancelled. Read the result and log in: $logDirectory"
        }
        exit $code
    } catch {
        Save-PatchRunResult 1 ('Windows elevation could not be completed: ' + $_.Exception.Message)
        Write-Output "Windows elevation was cancelled or failed. No patch operation was started. Result: $resultPath"
        exit 1
    }
}

$exitCode = 1
$message = ''
$transcribing = $false
$operationMutex = $null
$mutexHeld = $false
$maintenanceHandle = $null
try {
    Start-Transcript -Path $logPath -NoClobber | Out-Null
    $transcribing = $true
    if (-not $isAdmin) { throw 'The -Elevated flag does not grant permission. Windows Administrator approval is required.' }
    $operationMutex = New-Object Threading.Mutex($false, 'Global\OinkPersonalTrailPatch.Operation')
    try { $mutexHeld = $operationMutex.WaitOne(0) }
    catch [Threading.AbandonedMutexException] { $mutexHeld = $true }
    if (-not $mutexHeld) { throw 'Another Oink personal-patch operation is already running. Wait for it to finish.' }
    if (-not $ValidateOnly) {
        $installRoot = Get-OinkInstallRoot
        Assert-ProtectedInstall $installRoot
        $maintenanceHandle = Open-OinkMaintenanceLock $installRoot
    }
    $arguments = @{ ValidateOnly = [bool]$ValidateOnly }
    if ($Action -eq 'Upgrade') {
        & (Join-Path $PSScriptRoot 'Upgrade-TrailPatch.ps1') -UserDataPath $UserDataPath -ValidateOnly:$ValidateOnly
    } elseif ($Action -eq 'Install') {
        $arguments.UserDataPath = $UserDataPath
        & (Join-Path $PSScriptRoot 'Install-TrailPatch.ps1') @arguments
    } else {
        & (Join-Path $PSScriptRoot 'Restore-OriginalOink.ps1') @arguments
    }
    $exitCode = 0
    $message = if ($ValidateOnly) { 'Validation passed; no application changes were requested.' }
        else { 'Completed. Open Oink normally from the Start menu.' }
    Write-Output $message
} catch {
    $message = $_.Exception.Message
    Write-Output ('FAILED: ' + $message)
    Write-Output $_.ScriptStackTrace
} finally {
    if ($null -ne $maintenanceHandle) { $maintenanceHandle.Dispose() }
    if ($mutexHeld) { $operationMutex.ReleaseMutex() }
    if ($null -ne $operationMutex) { $operationMutex.Dispose() }
    if ($transcribing) { Stop-Transcript | Out-Null }
    Save-PatchRunResult $exitCode $message
}
exit $exitCode
