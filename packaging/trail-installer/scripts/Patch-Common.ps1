Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$script:PatchFileNames = @('oink.exe', 'oink-agent.exe', 'report-manifest.json', 'oink-build.json')
$script:PatchMarkerName = 'custom-trail-installed.json'

function Get-OinkInstallRoot {
    Join-Path ([Environment]::GetFolderPath([Environment+SpecialFolder]::ProgramFiles)) 'Oink'
}

function Assert-PatchAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this script from an Administrator PowerShell window. Use the same Windows account that runs Oink.'
    }
    if (-not [Environment]::Is64BitProcess -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'This personal patch requires x64 Windows and 64-bit PowerShell.'
    }
}

function Assert-NoReparsePath([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    if ($full.StartsWith('\\') -or $full.Substring(2).Contains(':')) {
        throw "A local filesystem path without alternate streams is required: $Path"
    }
    $current = $full
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw "Reparse points are not supported: $current"
            }
        }
        $parent = [IO.Path]::GetDirectoryName($current)
        if ($parent -eq $current) { break }
        $current = $parent
    }
}

function Assert-WithinDirectory([string]$Path, [string]$Directory) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetFullPath($Directory).TrimEnd('\') + '\'
    if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path is outside the expected directory: $Path"
    }
    Assert-NoReparsePath $full
}

function Get-FileSha256([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Read-JsonFile([string]$Path) {
    Get-Content -Raw -LiteralPath $Path -Encoding UTF8 | ConvertFrom-Json
}

function Write-JsonFile([string]$Path, $Value) {
    $text = ($Value | ConvertTo-Json -Depth 100) + [Environment]::NewLine
    $path = [IO.Path]::GetFullPath($Path)
    Assert-NoReparsePath $path
    $directory = [IO.Path]::GetDirectoryName($path)
    $stage = Join-Path $directory ('.' + [IO.Path]::GetFileName($path) + '.trail-json-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    Assert-WithinDirectory $stage $directory
    $created = $false
    try {
        $bytes = (New-Object Text.UTF8Encoding($false)).GetBytes($text)
        $stream = [IO.File]::Open($stage, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        $created = $true
        try {
            $stream.Write($bytes, 0, $bytes.Length)
            $stream.Flush($true)
        } finally { $stream.Dispose() }
        if ([IO.File]::ReadAllText($stage, [Text.Encoding]::UTF8) -cne $text) {
            throw 'Staged JSON verification failed.'
        }
        Assert-NoReparsePath $path
        if (Test-Path -LiteralPath $path) {
            # NullString prevents Windows PowerShell 5 from binding $null as
            # an empty (invalid) backup filename in this .NET overload.
            [IO.File]::Replace($stage, $path, [NullString]::Value)
        } else {
            [IO.File]::Move($stage, $path)
        }
    } finally {
        if ($created -and (Test-Path -LiteralPath $stage)) {
            Assert-WithinDirectory $stage $directory
            Remove-Item -LiteralPath $stage -Force
        }
    }
}

function Assert-ProtectedInstall([string]$InstallRoot) {
    Assert-NoReparsePath $InstallRoot
    if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
        throw 'Oink is not installed in the system Program Files directory.'
    }
    $privileged = @('S-1-5-18', 'S-1-5-32-544', 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464')
    $writeRights = [Security.AccessControl.FileSystemRights]::Write -bor
        [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership
    $paths = @((Split-Path -Parent $InstallRoot), $InstallRoot) +
        @($script:PatchFileNames | ForEach-Object { Join-Path $InstallRoot $_ })
    foreach ($path in $paths) {
        Assert-NoReparsePath $path
        $acl = Get-Acl -LiteralPath $path
        $raw = New-Object Security.AccessControl.RawSecurityDescriptor($acl.GetSecurityDescriptorSddlForm(
            [Security.AccessControl.AccessControlSections]::Access))
        if ($null -eq $raw.DiscretionaryAcl) { throw "The installed path has no protective DACL: $path" }
        if ($privileged -notcontains $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value) {
            throw "The installed path is not owned by a privileged Windows identity: $path"
        }
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
                ($rule.PropagationFlags -band [Security.AccessControl.PropagationFlags]::InheritOnly) -eq 0 -and
                ($rule.FileSystemRights -band $writeRights) -ne 0 -and
                $privileged -notcontains $rule.IdentityReference.Value) {
                throw "The installed path permits writes by a nonprivileged identity: $path"
            }
        }
    }
}

function Assert-BaseInstallation([string]$InstallRoot, $Manifest) {
    Assert-ProtectedInstall $InstallRoot
    $receipt = Read-JsonFile (Join-Path $InstallRoot 'installed.json')
    if ($receipt.product -ne 'Oink' -or $receipt.version -ne '0.3.4' -or
        [int]$receipt.build -ne 108 -or $receipt.architecture -ne 'x64') {
        throw 'This patch supports only the original Oink 0.3.4 build 108 x64 installation. Do not uninstall another version; obtain a matching patch.'
    }
    if ($receipt.source_tree_sha256 -ne $Manifest.base_source_tree_sha256) {
        throw 'The installed source identity differs from the base release used to build this patch.'
    }
    if (Test-Path -LiteralPath (Join-Path $InstallRoot 'maintenance\pending.json')) {
        throw 'An Oink update transaction is pending. Finish or recover that update before applying this patch.'
    }
    $service = Get-CimInstance Win32_Service -Filter "Name='OinkInput'"
    if (-not $service -or $service.State -ne 'Running' -or
        $service.PathName.Trim('"') -ine (Join-Path $InstallRoot 'oink-service.exe')) {
        throw 'The original OinkInput service must be installed at its normal path and running.'
    }
}

function Read-PatchManifest([string]$BundleRoot) {
    Assert-NoReparsePath $BundleRoot
    $manifest = Read-JsonFile (Join-Path $BundleRoot 'manifest.json')
    if ($manifest.schema -ne 1 -or $manifest.kind -ne 'personal-oink-movement-trail-patch' -or
        $manifest.base_version -ne '0.3.4' -or [int]$manifest.base_build -ne 108 -or
        $manifest.architecture -ne 'x64' -or
        $manifest.base_source_tree_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $manifest.source_tree_sha256 -notmatch '^[0-9a-f]{64}$' -or
        $manifest.patch_id -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,100}$') {
        throw 'The bundle manifest is invalid or incompatible.'
    }
    $actualNames = @($manifest.files.PSObject.Properties.Name | Sort-Object)
    if (Compare-Object $actualNames @($script:PatchFileNames | Sort-Object)) {
        throw 'The bundle must contain exactly the four approved payload files.'
    }
    foreach ($name in $script:PatchFileNames) {
        $hash = $manifest.files.$name
        if ($hash -notmatch '^[0-9a-f]{64}$') { throw "Invalid SHA256 for $name" }
        $path = Join-Path (Join-Path $BundleRoot 'payload') $name
        Assert-NoReparsePath $path
        if ((Get-FileSha256 $path) -ne $hash) { throw "Payload SHA256 mismatch: $name" }
    }
    foreach ($name in @('oink.exe', 'oink-agent.exe')) {
        $path = Join-Path (Join-Path $BundleRoot 'payload') $name
        $stream = [IO.File]::OpenRead($path)
        try {
            $reader = New-Object IO.BinaryReader($stream)
            if ($reader.ReadUInt16() -ne 0x5A4D) { throw "Invalid PE image: $name" }
            $stream.Position = 0x3C
            $pe = $reader.ReadUInt32()
            $stream.Position = $pe
            if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) {
                throw "Payload is not a Windows x64 executable: $name"
            }
        } finally { $stream.Dispose() }
    }
    $report = Read-JsonFile (Join-Path $BundleRoot 'payload\report-manifest.json')
    $metadata = Read-JsonFile (Join-Path $BundleRoot 'payload\oink-build.json')
    if ($report.source_tree_sha256 -ne $manifest.source_tree_sha256 -or
        $metadata.source_tree_sha256 -ne $manifest.source_tree_sha256) {
        throw 'The payload metadata does not identify the patched source tree.'
    }
    $manifest
}

function Stop-OinkForPatch([string]$InstallRoot, [string]$UserDataPath) {
    Assert-NoReparsePath $UserDataPath
    if (-not (Test-Path -LiteralPath (Join-Path $UserDataPath 'settings.json'))) {
        throw "The expected Oink user profile is missing: $UserDataPath"
    }
    & (Join-Path $InstallRoot 'oink-agent.exe') --home $UserDataPath stop
    if ($LASTEXITCODE -ne 0) { throw 'Oink did not shut down gracefully. No installed file has been replaced.' }
    # Another logged-in user's session may still have the same executable open.
    # Never force-kill it or replace files beneath that active instance.
    $running = @(Get-CimInstance Win32_Process -Filter "Name='oink.exe'")
    foreach ($process in $running) {
        if (-not $process.ExecutablePath -or $process.ExecutablePath -ieq (Join-Path $InstallRoot 'oink.exe')) {
            throw 'An Oink process is still running, possibly in another user session. Close it before continuing.'
        }
    }
}

function Open-OinkMaintenanceLock([string]$InstallRoot) {
    $directory = Join-Path $InstallRoot 'maintenance'
    Assert-NoReparsePath $directory
    if (-not (Test-Path -LiteralPath $directory -PathType Container)) {
        throw 'The original Oink maintenance directory is missing.'
    }
    $path = Join-Path $directory 'maintenance.lock'
    Assert-NoReparsePath $path
    # The upstream service and installer use this exact exclusive file handle.
    # Keep it for the complete personal upgrade/restore, including graceful stop.
    $handle = [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        foreach ($name in @('pending.json', 'msi-authorization.json')) {
            if (Test-Path -LiteralPath (Join-Path $directory $name)) {
                throw 'An Oink maintenance transaction is pending. Finish or recover it before installing or restoring.'
            }
        }
        return $handle
    } catch {
        $handle.Dispose()
        throw
    }
}

function New-PrivateBackupDirectory([string]$InstallRoot) {
    $parent = Join-Path $InstallRoot 'custom-trail-backups'
    Assert-NoReparsePath $parent
    $privateSddl = 'O:BAG:BAD:P(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)'
    if (-not (Test-Path -LiteralPath $parent)) {
        [void](New-Item -ItemType Directory -Path $parent)
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $acl.SetSecurityDescriptorSddlForm($privateSddl)
        Set-Acl -LiteralPath $parent -AclObject $acl
    } else {
        $acl = Get-Acl -LiteralPath $parent
        $raw = New-Object Security.AccessControl.RawSecurityDescriptor($acl.GetSecurityDescriptorSddlForm(
            [Security.AccessControl.AccessControlSections]::Access))
        if ($null -eq $raw.DiscretionaryAcl) { throw 'The backup directory has no protective DACL.' }
        if ($acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18', 'S-1-5-32-544')) {
            throw 'The backup directory has an unexpected owner.'
        }
        foreach ($rule in $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])) {
            if ($rule.AccessControlType -eq [Security.AccessControl.AccessControlType]::Allow -and
                $rule.IdentityReference.Value -notin @('S-1-5-18', 'S-1-5-32-544')) {
                throw 'The backup directory is not private to SYSTEM and Administrators.'
            }
        }
    }
    $leaf = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $backup = Join-Path $parent $leaf
    [void](New-Item -ItemType Directory -Path $backup)
    $backup
}

function Backup-OinkUserSettings([string]$UserDataPath, [string]$BackupPath) {
    $target = Join-Path $BackupPath 'user-settings'
    [void](New-Item -ItemType Directory -Path $target)
    # Identity, signed group state, preferences and layouts stay on this PC.
    # Skip live IPC tokens, caches, received files, logs and WebView2 data.
    foreach ($item in Get-ChildItem -LiteralPath $UserDataPath -File -Force) {
        if ($item.Name -match '\.lock$' -or $item.Name -in @('ipc.json', 'ui-ipc.json')) { continue }
        Assert-NoReparsePath $item.FullName
        Copy-Item -LiteralPath $item.FullName -Destination (Join-Path $target $item.Name)
    }
    foreach ($name in @('layout-profile-joins', 'layout-profiles-v2', 'audio')) {
        $source = Join-Path $UserDataPath $name
        if (-not (Test-Path -LiteralPath $source -PathType Container)) { continue }
        Assert-NoReparsePath $source
        # Enumerate before copying; never follow a directory junction/symlink.
        $queue = New-Object 'Collections.Generic.Queue[string]'
        $queue.Enqueue($source)
        while ($queue.Count) {
            $directory = $queue.Dequeue()
            foreach ($item in Get-ChildItem -LiteralPath $directory -Force) {
                if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw "Settings backup contains an unexpected reparse point: $($item.FullName)"
                }
                if ($item.PSIsContainer) { $queue.Enqueue($item.FullName) }
            }
        }
        Copy-Item -LiteralPath $source -Destination (Join-Path $target $name) -Recurse
    }
}

function Set-OriginalFileAcl([string]$Path, [string]$Sddl) {
    $acl = New-Object Security.AccessControl.FileSecurity
    $acl.SetSecurityDescriptorSddlForm($Sddl)
    Set-Acl -LiteralPath $Path -AclObject $acl
}

function Test-EquivalentFileAcl([string]$ExpectedSddl, [string]$ActualSddl) {
    $expected = New-Object Security.AccessControl.RawSecurityDescriptor($ExpectedSddl)
    $actual = New-Object Security.AccessControl.RawSecurityDescriptor($ActualSddl)
    # Windows may add AI while applying an unchanged inherited DACL. Ignore
    # only the two DACL inheritance bookkeeping flags; owner, group, DACL
    # presence/protection, ACE order/rights/inheritance and every other field
    # must remain byte-for-byte equal in the parsed security descriptors.
    $ignored = [int][Security.AccessControl.ControlFlags]::DiscretionaryAclAutoInherited -bor
        [int][Security.AccessControl.ControlFlags]::DiscretionaryAclAutoInheritRequired
    foreach ($descriptor in @($expected, $actual)) {
        $descriptor.SetFlags([Security.AccessControl.ControlFlags]([int]$descriptor.ControlFlags -band (-bnot $ignored)))
    }
    if ($expected.BinaryLength -ne $actual.BinaryLength) { return $false }
    $expectedBytes = New-Object byte[] $expected.BinaryLength
    $actualBytes = New-Object byte[] $actual.BinaryLength
    $expected.GetBinaryForm($expectedBytes, 0)
    $actual.GetBinaryForm($actualBytes, 0)
    for ($index = 0; $index -lt $expectedBytes.Length; $index++) {
        if ($expectedBytes[$index] -ne $actualBytes[$index]) { return $false }
    }
    return $true
}

function Install-VerifiedFileAtomically([string]$Source, [string]$Target, [string]$ExpectedSha256, [string]$OriginalSddl) {
    Assert-NoReparsePath $Source
    Assert-NoReparsePath $Target
    if ($ExpectedSha256 -notmatch '^[0-9a-f]{64}$' -or -not (Test-Path -LiteralPath $Target -PathType Leaf)) {
        throw "Atomic replacement requires a valid hash and an existing target: $Target"
    }
    $target = [IO.Path]::GetFullPath($Target)
    $directory = [IO.Path]::GetDirectoryName($target)
    $stage = Join-Path $directory ('.' + [IO.Path]::GetFileName($target) + '.trail-stage-' + [Guid]::NewGuid().ToString('N') + '.tmp')
    Assert-WithinDirectory $stage $directory
    $created = $false
    try {
        # Stage in the protected destination directory, not across volumes.
        # The source stays read-locked while being copied. The old destination
        # is untouched until the complete staged bytes and ACL are verified.
        $input = [IO.File]::Open($Source, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
        try {
            $output = [IO.File]::Open($stage, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
            $created = $true
            try {
                $input.CopyTo($output)
                $output.Flush($true)
            } finally { $output.Dispose() }
        } finally { $input.Dispose() }
        if ((Get-FileSha256 $stage) -ne $ExpectedSha256) { throw "Staged payload hash mismatch: $Source" }
        Set-OriginalFileAcl $stage $OriginalSddl
        Assert-NoReparsePath $target
        [IO.File]::Replace($stage, $target, [NullString]::Value)
        if ((Get-FileSha256 $target) -ne $ExpectedSha256) { throw "Replaced file hash mismatch: $target" }
        $actualSddl = (Get-Acl -LiteralPath $target).GetSecurityDescriptorSddlForm(
            [Security.AccessControl.AccessControlSections]::Access -bor
            [Security.AccessControl.AccessControlSections]::Owner -bor
            [Security.AccessControl.AccessControlSections]::Group)
        if (-not (Test-EquivalentFileAcl $OriginalSddl $actualSddl)) { throw "Replaced file ACL differs from the original: $target" }
    } finally {
        # A successful Replace consumes the stage. Clean only the exact file
        # created by this invocation; an interrupted process may leave harmless
        # staging files, but the installed target stays a complete old/new file.
        if ($created -and (Test-Path -LiteralPath $stage)) {
            Assert-WithinDirectory $stage $directory
            Remove-Item -LiteralPath $stage -Force
        }
    }
}

function Restore-BackupFiles([string]$InstallRoot, [string]$BackupPath, $Record) {
    $errors = @()
    foreach ($entry in $Record.files) {
        try {
            $source = Join-Path $BackupPath $entry.name
            $target = Join-Path $InstallRoot $entry.name
            Assert-NoReparsePath $target
            if ((Get-FileSha256 $source) -ne $entry.before_sha256) { throw 'Backup hash mismatch.' }
            Install-VerifiedFileAtomically $source $target $entry.before_sha256 $entry.acl_sddl
        } catch { $errors += "$($entry.name): $($_.Exception.Message)" }
    }
    if ($errors.Count) { throw ('Some files could not be restored: ' + ($errors -join '; ') + ". Backup: $BackupPath") }
}

function Test-LegacyAlwaysMigration([string]$UserDataPath) {
    $path = Join-Path $UserDataPath 'settings.json'
    Assert-NoReparsePath $path
    $settings = Read-JsonFile $path
    if ($settings.schema -ne 1 -or $null -eq $settings.local -or
        $settings.local -isnot [pscustomobject]) {
        throw 'The existing settings envelope cannot be safely migrated.'
    }
    $routing = $settings.local.PSObject.Properties['routing']
    if ($null -ne $routing -and $routing.Value -isnot [pscustomobject]) {
        throw 'The local routing preferences have an unexpected shape.'
    }
}

function Set-LegacyAlwaysMigration([string]$UserDataPath) {
    Test-LegacyAlwaysMigration $UserDataPath
    $path = Join-Path $UserDataPath 'settings.json'
    $settings = Read-JsonFile $path
    if ($null -eq $settings.local.PSObject.Properties['routing']) {
        $settings.local | Add-Member -NotePropertyName routing -NotePropertyValue ([pscustomobject]@{})
    }
    if ($null -ne $settings.local.routing.PSObject.Properties['cursor_trail_always']) {
        Write-Output 'An explicit trail-mode preference already exists; it was preserved.'
        return
    }
    $settings.local.routing | Add-Member -NotePropertyName cursor_trail_always -NotePropertyValue $true
    Write-JsonFile $path $settings
    Write-Output 'The previous always-on trail preference was preserved in the new selectable mode.'
}
