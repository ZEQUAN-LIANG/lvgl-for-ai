#requires -Version 5.1
<#
.SYNOPSIS
Installs the esptool backend used by the ESP32-C6 host flasher.

.DESCRIPTION
Creates a local virtual environment under host/vendor/esptool and installs
the pinned esptool release.  The host also discovers an esptool already on
PATH or in an ESP-IDF Python environment; this script is only the convenient
default for machines without ESP-IDF.

-Check only reports status; it never downloads or installs anything.
Exit code 0 means esptool is ready; 1 means it is missing.
#>
[CmdletBinding()]
param(
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$EsptoolVersion = '4.8.1'

$ScriptDir = $PSScriptRoot
$HostDir = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..')).Path
$VendorDir = Join-Path $HostDir 'vendor\esptool'
$VenvPython = Join-Path $VendorDir 'Scripts\python.exe'
$EsptoolExe = Join-Path $VendorDir 'Scripts\esptool.exe'

function Get-EsptoolInfo {
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        return $null
    }
    $output = & $VenvPython -m esptool version 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }
    $version = ($output | Select-Object -Last 1 | Out-String).Trim()
    return [pscustomobject]@{
        Python = $VenvPython
        Version = $version
        Exe = if (Test-Path -LiteralPath $EsptoolExe) { $EsptoolExe } else { '' }
    }
}

$uv = Get-Command uv -ErrorAction SilentlyContinue | Select-Object -First 1
$info = Get-EsptoolInfo

if ($Check) {
    Write-Host "host dir : $HostDir"
    Write-Host ("uv       : " + $(if ($uv) { $uv.Source } else { 'MISSING' }))
    if ($info) {
        Write-Host "esptool  : $($info.Version) ($($info.Python))"
        exit 0
    }
    Write-Host 'esptool  : MISSING (run bootstrap.ps1 without -Check)'
    exit 1
}

if (-not $uv) {
    throw 'uv is required to install esptool; install it from https://docs.astral.sh/uv/'
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "creating venv: $VendorDir"
    & $uv.Source venv $VendorDir --python 3.13
    if ($LASTEXITCODE -ne 0) {
        throw 'uv venv failed'
    }
}

Write-Host "installing esptool==$EsptoolVersion"
& $uv.Source pip install --python $VenvPython "esptool==$EsptoolVersion"
if ($LASTEXITCODE -ne 0) {
    throw 'uv pip install failed'
}

$info = Get-EsptoolInfo
if (-not $info) {
    throw 'esptool was installed but does not run'
}

Write-Host "esptool ready: $($info.Version)"
Write-Host "esptool path : $($info.Python)"
exit 0
