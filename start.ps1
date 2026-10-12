# Windows PowerShell 5.1. Keep this file ASCII so a BOM is not required.
# start.cmd supplies a process-only execution policy; no system policy is changed.
$script:LaunchArguments = @($args)
Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# Published SHA-256 values, verified against the official release page.
# https://www.python.org/downloads/release/python-3148/
# Pinned on 2026-10-07. Update version AND every hash together.
$script:PythonVersion = '3.14.8'
$script:PythonHashes = @{
    'amd64' = 'a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310'
    'win32' = 'ff153f0044abf190d6483c02d5ade7d9666d6220fc0e2828a5e90e99be047c4c'
    'arm64' = '155be84ccb57c6331cf0e39001c78a1dfac3be62f403f3ff5f2e29b80dda7ebe'
}

function Invoke-QuietProcess {
    param([string] $Executable, [string] $Arguments)
    # Only fixed, internal arguments use this helper. User paths go in FileName.
    $process = New-Object System.Diagnostics.Process
    try {
        $process.StartInfo.FileName = $Executable
        $process.StartInfo.Arguments = $Arguments
        $process.StartInfo.WorkingDirectory = $PSScriptRoot
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardInput = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $process.StartInfo.StandardOutputEncoding = [Text.Encoding]::UTF8
        $process.StartInfo.StandardErrorEncoding = [Text.Encoding]::UTF8
        # A runtime discovery command must not silently invoke an installer.
        $process.StartInfo.EnvironmentVariables['PYTHON_MANAGER_AUTOMATIC_INSTALL'] = 'false'
        foreach ($name in @('PYLAUNCHER_ALLOW_INSTALL', 'PYLAUNCHER_ALWAYS_INSTALL', 'PYLAUNCHER_DRYRUN')) {
            $process.StartInfo.EnvironmentVariables.Remove($name)
        }
        if (-not $process.Start()) { return $null }
        $process.StandardInput.Close()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(10000)) {
            try { $process.Kill() } catch { }
            return $null
        }
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            StdOut = $stdout.GetAwaiter().GetResult()
            StdErr = $stderr.GetAwaiter().GetResult()
        }
    }
    catch { return $null }
    finally { $process.Dispose() }
}

function Test-Python {
    param([string] $Executable)
    $probe = '-I -X utf8 -c "import sys; sys.exit(1) if sys.version_info < (3, 11) or sys.platform != ''win32'' else None; import http.server, ssl, ctypes, json, webbrowser; print(sys.executable)"'
    $result = Invoke-QuietProcess $Executable $probe
    if ($null -eq $result -or $result.ExitCode -ne 0) { return $null }
    $actual = $result.StdOut.Trim()
    if ($actual -and [IO.Path]::IsPathRooted($actual) -and (Test-Path -LiteralPath $actual -PathType Leaf)) {
        return $actual
    }
    return $null
}

function Find-ExistingPython {
    foreach ($name in @('python.exe', 'python3.exe')) {
        foreach ($command in @(Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue)) {
            # Store aliases may open the Store instead of running Python.
            if ($command.Source -match '\\Microsoft\\WindowsApps\\') { continue }
            $python = Test-Python $command.Source
            if ($python) { return $python }
        }
    }
    foreach ($command in @(Get-Command 'py.exe' -CommandType Application -All -ErrorAction SilentlyContinue)) {
        # -0p is a local-only list operation in both Python launcher generations.
        $listing = Invoke-QuietProcess $command.Source '-0p'
        if ($null -eq $listing -or $listing.ExitCode -ne 0) { continue }
        foreach ($line in (($listing.StdOut + [Environment]::NewLine + $listing.StdErr) -split '\r?\n')) {
            if ($line -match '(?i)((?:[a-z]:\\|\\\\).*\\python(?:[0-9.]+)?\.exe)\s*$') {
                $python = Test-Python $Matches[1]
                if ($python) { return $python }
            }
        }
    }
    return $null
}

function Get-WindowsArchitecture {
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    switch ($architecture.ToUpperInvariant()) {
        'AMD64' { return 'amd64' }
        'ARM64' { return 'arm64' }
        'X86' { return 'win32' }
        default { throw 'Unsupported Windows architecture. Install Python 3.11+ from python.org.' }
    }
}

function Get-CachedPython {
    param([string] $Folder, [string] $ExpectedHash)
    $marker = Join-Path $Folder '.verified-sha256'
    if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { return $null }
    if ([IO.File]::ReadAllText($marker).Trim() -cne $ExpectedHash) { return $null }
    return (Test-Python (Join-Path $Folder 'python.exe'))
}

function Install-LocalPython {
    $architecture = Get-WindowsArchitecture
    $expectedHash = $script:PythonHashes[$architecture]
    $runtimeRoot = Join-Path $PSScriptRoot '.runtime'
    $folderName = 'python-' + $script:PythonVersion + '-' + $architecture
    $runtimeFolder = Join-Path $runtimeRoot $folderName
    $cached = Get-CachedPython $runtimeFolder $expectedHash
    if ($cached) { return $cached }

    [IO.Directory]::CreateDirectory($runtimeRoot) | Out-Null
    $lock = $null
    $stage = $null
    $download = $null
    try {
        try {
            $lock = [IO.File]::Open((Join-Path $runtimeRoot 'bootstrap.lock'),
                [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
        }
        catch {
            throw 'Cannot prepare Python. Another launcher may be downloading it, or this folder is not writable. Wait for the other window or extract to a writable local folder.'
        }
        $cached = Get-CachedPython $runtimeFolder $expectedHash
        if ($cached) { return $cached }
        if (Test-Path -LiteralPath $runtimeFolder) {
            throw ('The local Python cache is incomplete. Close other monitor windows, delete only "' +
                $runtimeFolder + '", then restart start.cmd. Existing system Python is not affected.')
        }

        $archiveName = 'python-' + $script:PythonVersion + '-embed-' + $architecture + '.zip'
        $archive = Join-Path $runtimeRoot $archiveName
        $url = 'https://www.python.org/ftp/python/' + $script:PythonVersion + '/' + $archiveName
        $archiveVerified = $false
        if (Test-Path -LiteralPath $archive -PathType Leaf) {
            $archiveVerified = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $expectedHash
        }
        if (-not $archiveVerified) {
            Write-Host ('Downloading official Python ' + $script:PythonVersion + ' (' + $architecture + ', about 12 MB)...')
            Write-Host 'This is a local portable runtime. No installer or administrator access is used.'
            $download = Join-Path $runtimeRoot ('download-' + [Guid]::NewGuid().ToString('N') + '.zip')
            $previousProtocol = [Net.ServicePointManager]::SecurityProtocol
            $previousProgress = $ProgressPreference
            try {
                [Net.ServicePointManager]::SecurityProtocol = $previousProtocol -bor [Net.SecurityProtocolType]::Tls12
                $ProgressPreference = 'SilentlyContinue'
                Invoke-WebRequest -Uri $url -OutFile $download -UseBasicParsing -TimeoutSec 120 -MaximumRedirection 0
            }
            catch {
                throw ('Python download failed: ' + $_.Exception.Message +
                    ' Check Internet/proxy access to https://www.python.org, or install Python 3.11+ manually. ' +
                    'An offline ZIP can be placed at "' + $archive + '". It will be checked before use.')
            }
            finally {
                [Net.ServicePointManager]::SecurityProtocol = $previousProtocol
                $ProgressPreference = $previousProgress
            }
            $actualHash = (Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($actualHash -cne $expectedHash) {
                throw 'Python SHA-256 verification failed. The archive was not extracted or executed. Retry on a trusted connection or install Python from python.org.'
            }
            Move-Item -LiteralPath $download -Destination $archive -Force
            $download = $null
        }

        Write-Host 'Python archive verified. Preparing the local runtime...'
        $stage = Join-Path $runtimeRoot ('build-' + [Guid]::NewGuid().ToString('N'))
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
        # Both staging and final folders have the same depth below the app root.
        # Add the application directory without enabling site or pip.
        $paths = @('python314.zip', '.', '../..', '') -join [Environment]::NewLine
        [IO.File]::WriteAllText((Join-Path $stage 'python314._pth'), $paths, [Text.Encoding]::ASCII)
        if (-not (Test-Python (Join-Path $stage 'python.exe'))) {
            throw 'The downloaded Python could not start. Check Windows updates and antivirus messages, or install Python 3.11+ from python.org.'
        }
        [IO.File]::WriteAllText((Join-Path $stage '.verified-sha256'), $expectedHash, [Text.Encoding]::ASCII)
        [IO.Directory]::Move($stage, $runtimeFolder)
        $stage = $null
        return (Join-Path $runtimeFolder 'python.exe')
    }
    finally {
        if ($download -and (Test-Path -LiteralPath $download)) {
            Remove-Item -LiteralPath $download -Force -ErrorAction SilentlyContinue
        }
        if ($stage -and (Test-Path -LiteralPath $stage)) {
            Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
        }
        if ($null -ne $lock) { $lock.Dispose() }
    }
}

try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'start.ps1 is for Windows 10/11. On another OS, run python3 server.py.'
    }
    Set-Location -LiteralPath $PSScriptRoot
    [IO.Directory]::SetCurrentDirectory($PSScriptRoot)
    foreach ($argument in $script:LaunchArguments) {
        if (@('--demo', '--no-browser', '--check') -cnotcontains $argument) {
            throw 'Supported launcher options: --demo, --no-browser, --check. Settings are in .env and servers.json.'
        }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'server.py') -PathType Leaf)) {
        throw 'server.py is missing. Extract the entire ZIP, then run start.cmd from the extracted folder.'
    }
    $envFile = Join-Path $PSScriptRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot '.env.example') -Destination $envFile
        Write-Host 'Created .env. Set LANGUAGE to ru or en if needed.'
    }
    $serversFile = Join-Path $PSScriptRoot 'servers.json'
    if ($script:LaunchArguments -cnotcontains '--demo' -and
        -not (Test-Path -LiteralPath $serversFile -PathType Leaf)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'servers.json.example') -Destination $serversFile
        Write-Host 'Created servers.json. Set server names and existing OpenSSH Host aliases.'
    }
    Write-Host 'Server Monitor'
    Write-Host 'Checking the local Python runtime...'
    $python = Find-ExistingPython
    if (-not $python) { $python = Install-LocalPython }
    Write-Host ('Python: ' + $python)
    if ($script:LaunchArguments -cnotcontains '--check') {
        Write-Host 'Keep this window open. SSH passwords and key passphrases are entered here.'
        Write-Host 'Press Ctrl+C and wait for "Server Monitor stopped." Then type Y if CMD asks "Terminate batch job (Y/N)?".'
    }
    # Inherit the console handles. Do not pipe, capture, detach, or hide the app.
    # -E/-s/-S isolate stdlib imports while retaining the application directory.
    $appArguments = @($script:LaunchArguments)
    & $python -E -s -S -X utf8 -u -B (Join-Path $PSScriptRoot 'server.py') @appArguments
    $appExitCode = $LASTEXITCODE
    exit $appExitCode
}
catch {
    Write-Host ''
    Write-Host ('ERROR: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host 'See README.md for setup and troubleshooting.'
    exit 1
}
