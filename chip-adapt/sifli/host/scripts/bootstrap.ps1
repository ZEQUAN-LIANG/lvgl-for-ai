#requires -Version 5.1
<#
.SYNOPSIS
Checks and bootstraps the Windows dependencies of the SiFli serial host.

.DESCRIPTION
Checks Python, the vendored pyserial package, the vendored xterm.js assets,
uv, the SiFli SDK uv lock environment, the ARM toolchain and sftool.

-Check only reports status; it never downloads or installs anything.
Without -Check, missing pyserial (including its license), xterm.js assets and
the SDK lock venv are repaired.  Missing Python, uv, SDK sources or sftool are
reported with a manual hint because they are environment-level installs.

Exit code 0 means every required component is ready; 1 means at least one
MISSING row remains.

.PARAMETER Check
Only check.  Do not download, install, or modify any file.
#>
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$ScriptDir = $PSScriptRoot
$HostDir = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..')).Path
$SifliDir = (Resolve-Path -LiteralPath (Join-Path $HostDir '..')).Path
$ChipAdaptDir = Split-Path -Path $SifliDir -Parent
$RepoRoot = Split-Path -Path $ChipAdaptDir -Parent
$ToolsRoot = if ($env:SIFLI_SDK_TOOLS_PATH) {
    $env:SIFLI_SDK_TOOLS_PATH
} else {
    Join-Path $HOME '.sifli'
}

$VendorDir = Join-Path $HostDir 'vendor'
$PyserialLicense = Join-Path $VendorDir 'pyserial-3.5.LICENSE.txt'
$PyserialLicenseUrl = 'https://raw.githubusercontent.com/pyserial/pyserial/v3.5/LICENSE.txt'
$XtermDir = Join-Path $HostDir 'web\vendor\xterm'
$SdkDir = Join-Path $ChipAdaptDir 'vendor\sifli-sdk'
$LockDir = Join-Path $SdkDir 'tools\locks\default'
$VenvDir = Join-Path $LockDir '.venv'
$VenvScons = Join-Path $VenvDir 'Scripts\scons.exe'

$XtermFiles = @(
    @{
        Name = 'xterm.js'
        Url = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js'
        Marker = 'Terminal'
        MinSize = 100000
    },
    @{
        Name = 'xterm.css'
        Url = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css'
        Marker = '.xterm'
        MinSize = 1000
    },
    @{
        Name = 'LICENSE'
        Url = 'https://cdn.jsdelivr.net/npm/xterm@5.3.0/LICENSE'
        Marker = 'Permission is hereby granted'
        MinSize = 500
    }
)

function Add-Check {
    param(
        [Parameter(Mandatory = $true)] $List,
        [Parameter(Mandatory = $true)] [string] $Name,
        [Parameter(Mandatory = $true)] [string] $Status,
        [Parameter(Mandatory = $true)] [string] $Detail,
        [string] $Fix = ''
    )
    [void]$List.Add([pscustomobject]@{
        Name = $Name
        Status = $Status
        Detail = $Detail
        Fix = $Fix
    })
}

function Get-PythonInfo {
    $cmd = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $cmd -or $cmd.CommandType -ne 'Application') {
        return $null
    }
    $out = & $cmd.Path -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    $version = ($out | Out-String).Trim()
    return [pscustomobject]@{
        Path = $cmd.Path
        Version = $version
    }
}

function Test-PythonVersion {
    param([string] $Version)
    $parts = $Version.Split('.')
    if ($parts.Count -lt 2) {
        return $false
    }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    return ($major -gt 3) -or ($major -eq 3 -and $minor -ge 9)
}

function Get-PyserialInfo {
    param([string] $PythonPath)
    if (-not $PythonPath) {
        return $null
    }
    if (-not (Test-Path -LiteralPath (Join-Path $VendorDir 'serial\__init__.py'))) {
        return $null
    }
    $code = "import sys; sys.path.insert(0, sys.argv[1]); import serial; print(serial.__version__)"
    $out = & $PythonPath -I -B -c $code $VendorDir 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    $version = ($out | Out-String).Trim()
    if ($version -ne '3.5') {
        return $null
    }
    return $version
}

function Get-XtermState {
    $missing = New-Object System.Collections.ArrayList
    $bad = New-Object System.Collections.ArrayList
    foreach ($file in $XtermFiles) {
        $path = Join-Path $XtermDir $file.Name
        if (-not (Test-Path -LiteralPath $path)) {
            [void]$missing.Add($file.Name)
            continue
        }
        $item = Get-Item -LiteralPath $path
        if ($item.Length -eq 0) {
            [void]$missing.Add($file.Name)
            continue
        }
        if ($item.Length -lt $file.MinSize) {
            [void]$bad.Add($file.Name)
            continue
        }
        if (-not (Select-String -LiteralPath $path -Pattern $file.Marker -SimpleMatch -Quiet)) {
            [void]$bad.Add($file.Name)
        }
    }
    return [pscustomobject]@{
        Missing = $missing
        Bad = $bad
    }
}

function Get-UvInfo {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $cmd) {
        return $null
    }
    $out = & $cmd.Path --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($out | Out-String).Trim()
}

function Get-VenvSconsInfo {
    if (-not (Test-Path -LiteralPath $VenvScons)) {
        return $null
    }
    $out = & $VenvScons --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    $text = ($out | Out-String)
    $match = [regex]::Match($text, 'SCons:\s*v([0-9]+\.[0-9]+\.[0-9]+)')
    if ($match.Success) {
        return $match.Groups[1].Value
    }
    return 'unknown'
}

function Find-Sftool {
    $candidates = @()
    if ($env:SFTOOL_BIN) {
        $candidates += $env:SFTOOL_BIN
    }
    $versioned = Join-Path $ToolsRoot 'tools\sftool'
    if (Test-Path -LiteralPath $versioned) {
        $candidates += Get-ChildItem -LiteralPath $versioned -Filter 'sftool.exe' -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $_.FullName }
    }
    $candidates += Join-Path $ToolsRoot 'sftool\sftool.exe'
    $onPath = Get-Command sftool -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $onPath) {
        $candidates += $onPath.Path
    }
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }
    return $null
}

function Get-SftoolInfo {
    $sftool = Find-Sftool
    if (-not $sftool) {
        return $null
    }
    $out = & $sftool --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    return ($out | Out-String).Trim()
}

function Invoke-Checks {
    $results = New-Object System.Collections.ArrayList

    $python = Get-PythonInfo
    if ($null -eq $python) {
        Add-Check $results 'Python' 'MISSING' 'python not found on PATH; install Python 3.9+ first'
    } elseif (-not (Test-PythonVersion $python.Version)) {
        Add-Check $results 'Python' 'MISSING' ("found {0} at {1}; Python 3.9+ required" -f $python.Version, $python.Path)
    } else {
        Add-Check $results 'Python' 'OK' ("{0} ({1})" -f $python.Version, $python.Path)
    }

    $pythonUsable = ($null -ne $python) -and (Test-PythonVersion $python.Version)
    if (-not $pythonUsable) {
        Add-Check $results 'pyserial (vendor)' 'SKIP' 'needs Python'
    } else {
        $serial = Get-PyserialInfo $python.Path
        if ($null -eq $serial) {
            Add-Check $results 'pyserial (vendor)' 'MISSING' ("not importable from {0}; re-run without -Check to install pyserial 3.5" -f $VendorDir) 'pyserial'
        } elseif (Test-Path -LiteralPath $PyserialLicense) {
            Add-Check $results 'pyserial (vendor)' 'OK' ("serial {0} ({1})" -f $serial, $VendorDir)
        } else {
            Add-Check $results 'pyserial (vendor)' 'WARN' ("serial {0}; license file missing: {1}; re-run without -Check to download" -f $serial, $PyserialLicense) 'pyserial-license'
        }
    }

    $xterm = Get-XtermState
    if ($xterm.Bad.Count -gt 0) {
        $detail = "unexpected content in: {0}; remove those files manually and re-run" -f ($xterm.Bad -join ', ')
        if ($xterm.Missing.Count -gt 0) {
            $detail += "; also missing: {0}" -f ($xterm.Missing -join ', ')
        }
        Add-Check $results 'xterm.js (vendor)' 'MISSING' $detail
    } elseif ($xterm.Missing.Count -gt 0) {
        Add-Check $results 'xterm.js (vendor)' 'MISSING' ("missing: {0}; re-run without -Check to download" -f ($xterm.Missing -join ', ')) 'xterm'
    } else {
        Add-Check $results 'xterm.js (vendor)' 'OK' ("xterm.js 5.3.0 assets ({0})" -f $XtermDir)
    }

    $uv = Get-UvInfo
    if ($null -eq $uv) {
        Add-Check $results 'uv' 'MISSING' 'uv not found on PATH; install it from https://docs.astral.sh/uv/getting-started/installation/'
    } else {
        Add-Check $results 'uv' 'OK' $uv
    }

    $sdkOk = Test-Path -LiteralPath (Join-Path $LockDir 'uv.lock')
    if ($sdkOk) {
        Add-Check $results 'SiFli SDK' 'OK' $SdkDir
    } else {
        Add-Check $results 'SiFli SDK' 'MISSING' ("uv.lock not found under {0}; follow chip-adapt/vendor/README.md" -f $SdkDir)
    }

    if (-not $sdkOk) {
        Add-Check $results 'SDK lock venv' 'SKIP' 'needs SiFli SDK'
    } else {
        $scons = Get-VenvSconsInfo
        if ($null -ne $scons) {
            Add-Check $results 'SDK lock venv' 'OK' ("scons {0} ({1})" -f $scons, $VenvDir)
        } elseif ($null -eq $uv) {
            Add-Check $results 'SDK lock venv' 'MISSING' 'scons venv missing and uv is not available to create it'
        } else {
            Add-Check $results 'SDK lock venv' 'MISSING' ("scons venv missing at {0}; re-run without -Check (uv sync)" -f $VenvDir) 'venv'
        }
    }

    $gcc = Get-ChildItem -LiteralPath (Join-Path $ToolsRoot 'tools\arm-none-eabi-gcc') -Filter 'arm-none-eabi-gcc.exe' -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $gcc) {
        Add-Check $results 'ARM toolchain' 'MISSING' ("arm-none-eabi-gcc not found under {0}; run the SDK install.ps1 or set SIFLI_SDK_TOOLS_PATH (see chip-adapt/vendor/README.md)" -f $ToolsRoot)
    } else {
        Add-Check $results 'ARM toolchain' 'OK' $gcc.FullName
    }

    $sftool = Find-Sftool
    $sftoolInfo = Get-SftoolInfo
    if ($null -eq $sftoolInfo) {
        Add-Check $results 'sftool' 'MISSING' ("not runnable under {0}; install sftool 0.2.5 with the SDK installer (see chip-adapt/vendor/README.md)" -f (Join-Path $ToolsRoot 'tools\sftool'))
    } else {
        Add-Check $results 'sftool' 'OK' ("{0} ({1})" -f $sftoolInfo, $sftool)
    }

    return $results
}

function Invoke-PyserialRepair {
    param([string] $PythonPath)
    Write-Host ("fix: python -m pip install --target {0} --no-deps pyserial==3.5" -f $VendorDir)
    New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $PythonPath -m pip install --target $VendorDir --no-deps pyserial==3.5 2>&1 |
        ForEach-Object { Write-Host $_ }
    $pipExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($pipExit -ne 0) {
        Write-Host ("fix: pyserial install failed (exit {0})" -f $pipExit) -ForegroundColor Red
        return $false
    }
    foreach ($name in @('bin', 'pyserial-3.5.dist-info')) {
        $path = Join-Path $VendorDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host ("fix: removing pip artifact {0}" -f $path)
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
    if (-not (Test-Path -LiteralPath $PyserialLicense)) {
        [void](Invoke-PyserialLicenseRepair)
    }
    return $true
}

function Save-VerifiedDownload {
    param(
        [Parameter(Mandatory = $true)] [string] $Url,
        [Parameter(Mandatory = $true)] [string] $Destination,
        [Parameter(Mandatory = $true)] [string] $Marker,
        [Parameter(Mandatory = $true)] [int] $MinSize
    )
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        Write-Host ("fix: download {0}" -f $Url)
        $downloaded = $false
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $curl) {
            & $curl.Path -L --fail --silent --show-error --max-time 120 -o $tmp $Url
            if ($LASTEXITCODE -eq 0) {
                $downloaded = $true
            }
        }
        if (-not $downloaded) {
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
            try {
                Invoke-WebRequest -Uri $Url -OutFile $tmp -UseBasicParsing -TimeoutSec 120
                $downloaded = $true
            } catch {
                Write-Host ("fix: Invoke-WebRequest failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
            }
        }
        if (-not $downloaded) {
            throw ("download failed: {0}" -f $Url)
        }
        $size = (Get-Item -LiteralPath $tmp).Length
        if ($size -lt $MinSize) {
            throw ("downloaded file is too small ({0} bytes): {1}" -f $size, $Url)
        }
        if (-not (Select-String -LiteralPath $tmp -Pattern $Marker -SimpleMatch -Quiet)) {
            throw ("downloaded file does not contain expected marker '{0}': {1}" -f $Marker, $Url)
        }
        Move-Item -LiteralPath $tmp -Destination $Destination -Force
        Write-Host ("fix: wrote {0}" -f $Destination)
        return $true
    } catch {
        Write-Host ("fix: {0}" -f $_.Exception.Message) -ForegroundColor Red
        return $false
    } finally {
        if (Test-Path -LiteralPath $tmp) {
            Remove-Item -LiteralPath $tmp -Force
        }
    }
}

function Invoke-PyserialLicenseRepair {
    New-Item -ItemType Directory -Force -Path $VendorDir | Out-Null
    return (Save-VerifiedDownload -Url $PyserialLicenseUrl -Destination $PyserialLicense -Marker 'Copyright (c) 2001-2020 Chris Liechti' -MinSize 500)
}

function Invoke-XtermRepair {
    New-Item -ItemType Directory -Force -Path $XtermDir | Out-Null
    $allOk = $true
    foreach ($file in $XtermFiles) {
        $dest = Join-Path $XtermDir $file.Name
        if (Test-Path -LiteralPath $dest) {
            if ((Get-Item -LiteralPath $dest).Length -gt 0) {
                continue
            }
        }
        if (-not (Save-VerifiedDownload -Url $file.Url -Destination $dest -Marker $file.Marker -MinSize $file.MinSize)) {
            $allOk = $false
        }
    }
    return $allOk
}

function Invoke-VenvRepair {
    param([string] $UvPath)
    Write-Host ("fix: uv sync --project {0} --no-dev" -f $LockDir)
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $UvPath sync --project $LockDir --no-dev 2>&1 |
        ForEach-Object { Write-Host $_ }
    $uvExit = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($uvExit -ne 0) {
        Write-Host ("fix: uv sync failed (exit {0})" -f $uvExit) -ForegroundColor Red
        return $false
    }
    return (Test-Path -LiteralPath $VenvScons)
}

function Show-Results {
    param($Results)
    Write-Host ''
    Write-Host ('{0,-20} {1,-9} {2}' -f 'Component', 'Status', 'Detail')
    Write-Host ('{0,-20} {1,-9} {2}' -f '---------', '------', '------')
    foreach ($result in @($Results)) {
        $color = 'White'
        if ($result.Status -eq 'OK') {
            $color = 'Green'
        } elseif ($result.Status -eq 'MISSING') {
            $color = 'Red'
        } elseif ($result.Status -eq 'WARN') {
            $color = 'Yellow'
        } elseif ($result.Status -eq 'SKIP') {
            $color = 'DarkYellow'
        }
        Write-Host ('{0,-20} {1,-9} {2}' -f $result.Name, $result.Status, $result.Detail) -ForegroundColor $color
    }
}

$mode = 'bootstrap'
if ($Check) {
    $mode = 'check only'
}

Write-Host ''
Write-Host ("SiFli host environment ({0})" -f $mode)
Write-Host ("repo: {0}" -f $RepoRoot)

$results = Invoke-Checks

if (-not $Check) {
    $pythonForRepair = Get-PythonInfo
    $uvForRepair = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1
    $uvPath = $null
    if ($null -ne $uvForRepair) {
        $uvPath = $uvForRepair.Path
    }

    $attemptedRepair = $false
    foreach ($result in @($results)) {
        if ($result.Status -eq 'OK' -or -not $result.Fix) {
            continue
        }
        $attemptedRepair = $true
        switch ($result.Fix) {
            'pyserial' {
                if ($null -ne $pythonForRepair) {
                    [void](Invoke-PyserialRepair $pythonForRepair.Path)
                }
            }
            'pyserial-license' {
                [void](Invoke-PyserialLicenseRepair)
            }
            'xterm' {
                [void](Invoke-XtermRepair)
            }
            'venv' {
                if ($null -ne $uvPath) {
                    [void](Invoke-VenvRepair $uvPath)
                }
            }
        }
    }

    if ($attemptedRepair) {
        $results = Invoke-Checks
    }
}

Show-Results $results

$okCount = @($results | Where-Object { $_.Status -eq 'OK' }).Count
$missingCount = @($results | Where-Object { $_.Status -eq 'MISSING' }).Count
$warnCount = @($results | Where-Object { $_.Status -eq 'WARN' }).Count
$skipCount = @($results | Where-Object { $_.Status -eq 'SKIP' }).Count

Write-Host ''
Write-Host ("summary: {0} ok, {1} missing, {2} warnings, {3} skipped" -f $okCount, $missingCount, $warnCount, $skipCount)
if ($missingCount -gt 0) {
    Write-Host 'not ready: resolve the MISSING rows above.' -ForegroundColor Red
}
Write-Host 'next: python -I chip-adapt/sifli/host/server.py --open'

if ($missingCount -gt 0) {
    exit 1
}
exit 0
