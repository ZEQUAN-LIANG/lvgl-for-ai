#Requires -Version 5.1
<#
.SYNOPSIS
    Install the SiFli-SDK ARM toolchain, CMake, Ninja and sftool.

.DESCRIPTION
    Wraps chip-adapt/vendor/sifli-sdk/install.ps1.  The SDK installer pulls
    release assets from GitHub, which is often very slow on Chinese networks;
    this wrapper turns on the SDK's own China mirror preset
    (SIFLI_SDK_MIRROR_CHINA=1) by default.  The preset redirects GitHub
    release assets to downloads.sifli.com, switches PyPI to the USTC mirror
    and points uv at its Python download metadata mirror.

    chip-adapt/vendor/ is a read-only vendor download: this script only calls
    the SDK installer and never edits the SDK tree.  When the SDK is missing
    it prints the clone commands from chip-adapt/vendor/README.md.

.PARAMETER NoMirror
    Use the upstream GitHub/PyPI sources instead of the China mirror.  An
    explicit SIFLI_SDK_MIRROR_CHINA environment value is respected when this
    switch is absent.

.PARAMETER DryRun
    Print the SDK installer command and exit without installing.

.PARAMETER Offline
    Forward --offline to the SDK installer.

.PARAMETER Profile
    Forward --profile <name> to the SDK installer.

.PARAMETER Targets
    Forward --targets <names> to the SDK installer.

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/install-toolchain.ps1

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/install-toolchain.ps1 -NoMirror

.EXAMPLE
    powershell -NoProfile -ExecutionPolicy Bypass -File chip-adapt/sifli/host/scripts/install-toolchain.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [switch]$NoMirror,
    [switch]$DryRun,
    [switch]$Offline,
    [string]$Profile,
    [string]$Targets
)

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..\..\..\..')).Path
$SdkDir = Join-Path $RepoRoot 'chip-adapt\vendor\sifli-sdk'
$SdkInstaller = Join-Path $SdkDir 'install.ps1'

if (-not (Test-Path -LiteralPath $SdkInstaller -PathType Leaf)) {
    throw @"
SiFli-SDK not found at $SdkDir.
Download it from the repository root:
  git clone -b release/v2.5 https://gitee.com/SiFli/sifli-sdk.git chip-adapt/vendor/sifli-sdk
  git -C chip-adapt/vendor/sifli-sdk checkout f4042d7e66f144feba9f88ecb7ca0eda8a92c3bc
  git -C chip-adapt/vendor/sifli-sdk submodule update --init tools/SiliconSchema middleware/bluetooth
Checks and downloads are documented in chip-adapt/vendor/README.md.
"@
}

function Test-Truthy {
    param([string]$Value)
    return $Value.Trim().ToLowerInvariant() -in @('1', 'true', 'yes', 'on')
}

$mirrorValue = $env:SIFLI_SDK_MIRROR_CHINA
if ($NoMirror) {
    $mirrorValue = '0'
}
elseif (-not $mirrorValue) {
    $mirrorValue = '1'
}
$env:SIFLI_SDK_MIRROR_CHINA = $mirrorValue

if (Test-Truthy $mirrorValue) {
    Write-Host 'China mirror enabled: downloads.sifli.com + USTC PyPI (disable with -NoMirror).'
}
else {
    Write-Host 'Using upstream sources: GitHub + PyPI.'
}

$installArgs = @()
if ($Offline) { $installArgs += '--offline' }
if ($Profile) { $installArgs += @('--profile', $Profile) }
if ($Targets) { $installArgs += @('--targets', $Targets) }

if ($DryRun) {
    Write-Host 'DRY RUN: SDK installer is not executed.'
    Write-Host "  installer: $SdkInstaller"
    Write-Host "  mirror:    $mirrorValue"
    if ($installArgs.Count -gt 0) {
        Write-Host ("  args:      {0}" -f ($installArgs -join ' '))
    }
    exit 0
}

& $SdkInstaller @installArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Error "SDK install.ps1 exited with code $exitCode." -ErrorAction Continue
    exit $exitCode
}

$ToolsRoot = if ($env:SIFLI_SDK_TOOLS_PATH) {
    $env:SIFLI_SDK_TOOLS_PATH
}
else {
    Join-Path $HOME '.sifli'
}

$gccCandidates = @()
$gccRoot = Join-Path $ToolsRoot 'tools\arm-none-eabi-gcc'
if (Test-Path -LiteralPath $gccRoot) {
    $gccCandidates = Get-ChildItem -LiteralPath $gccRoot -Directory |
        Sort-Object -Property Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'bin\arm-none-eabi-gcc.exe' } |
        Where-Object { Test-Path -LiteralPath $_ }
}
$gcc = $gccCandidates | Select-Object -First 1

$sftoolCandidates = @()
$sftoolRoot = Join-Path $ToolsRoot 'tools\sftool'
if (Test-Path -LiteralPath $sftoolRoot) {
    $sftoolCandidates = Get-ChildItem -LiteralPath $sftoolRoot -Directory |
        Sort-Object -Property Name -Descending |
        ForEach-Object { Join-Path $_.FullName 'sftool.exe' } |
        Where-Object { Test-Path -LiteralPath $_ }
}
$sftool = $sftoolCandidates | Select-Object -First 1

$missing = @()
if (-not $gcc) { $missing += 'arm-none-eabi-gcc' }
if (-not $sftool) { $missing += 'sftool' }
if ($missing.Count -gt 0) {
    Write-Error ("install finished but {0} was not found under {1}." -f ($missing -join ', '), $ToolsRoot) -ErrorAction Continue
    exit 1
}

$gccVersion = (& $gcc --version 2>&1 | Select-Object -First 1)
$sftoolVersion = (& $sftool --version 2>&1 | Select-Object -First 1)

[pscustomobject][ordered]@{
    toolchain_root = $ToolsRoot
    gcc            = $gcc
    gcc_version    = [string]$gccVersion
    sftool         = $sftool
    sftool_version = [string]$sftoolVersion
}

exit 0
