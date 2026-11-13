#Requires -Version 5.1
<#
.SYNOPSIS
    Flash the current SiFli build, optionally building it first.

.DESCRIPTION
    Resolves build_dir / project_dir / port from suggest.ps1, then runs
    `cli.py flash --json`.  By default it only flashes the suggested
    build_dir; -Build builds first and flashes the fresh output.  The CLI
    exit code (0 ok, 1 build/flash failed, 2 harness) is passed through.

    -DryRun prints the command and never builds or flashes.  A serial port
    is always required; without -Build a flashable build_dir containing
    sftool_param.json is required too.

.PARAMETER Build
    Build before flashing.  The suggested project directory is used; when it
    is the exported `chip-adapt/sifli/<app>/project`, `--app <app>` is passed
    so the host re-exports user/app first.

.PARAMETER Port
    Serial port for sftool.  Defaults to the port suggested by the host.

.PARAMETER DryRun
    Print the resolved paths and CLI command only.  Nothing is built or
    flashed.

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\flash-current.ps1 -DryRun

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\flash-current.ps1

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\flash-current.ps1 -Build -Port COM12
#>
[CmdletBinding()]
param(
    [switch]$Build,
    [string]$Port,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

$ScriptDir = $PSScriptRoot
$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $ScriptDir '..\..\..\..')).Path
$CliPath = Join-Path $RepoRoot 'chip-adapt\sifli\host\cli.py'

if (-not (Test-Path -LiteralPath $CliPath -PathType Leaf)) {
    throw "cli.py not found at $CliPath; run this script from the repository checkout."
}

function ConvertTo-NativeArgument {
    param([AllowEmptyString()][string]$Value)

    if ($null -eq $Value -or $Value.Length -eq 0) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.Append('"')
    $backslashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq [char]'\') {
            $backslashes++
            [void]$builder.Append($character)
        }
        elseif ($character -eq [char]'"') {
            [void]$builder.Append('\', $backslashes + 1)
            [void]$builder.Append('"')
            $backslashes = 0
        }
        else {
            $backslashes = 0
            [void]$builder.Append($character)
        }
    }
    if ($backslashes -gt 0) {
        [void]$builder.Append('\', $backslashes)
    }
    [void]$builder.Append('"')
    return $builder.ToString()
}

function Invoke-SifliCli {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$CliArguments
    )

    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $pythonCommand) {
        throw 'python was not found in PATH; install Python 3.9+ and retry.'
    }
    $pythonPath = $pythonCommand.Path
    if (-not $pythonPath) {
        $pythonPath = $pythonCommand.Source
    }

    $parts = [System.Collections.Generic.List[string]]::new()
    $parts.Add('-I')
    $parts.Add((ConvertTo-NativeArgument $CliPath))
    foreach ($argument in $CliArguments) {
        $parts.Add((ConvertTo-NativeArgument $argument))
    }

    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $pythonPath
    $startInfo.Arguments = [string]::Join(' ', $parts)
    $startInfo.WorkingDirectory = $RepoRoot
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.StandardOutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $startInfo.StandardErrorEncoding = [System.Text.UTF8Encoding]::new($false)

    $process = [System.Diagnostics.Process]::new()
    $process.StartInfo = $startInfo
    try {
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        return [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout   = $stdoutTask.Result
            Stderr   = $stderrTask.Result
        }
    }
    finally {
        $process.Dispose()
    }
}

function Format-SifliCommand {
    param([string[]]$CliArguments)

    $pythonCommand = Get-Command python -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $pythonPath = 'python'
    if ($null -ne $pythonCommand -and $pythonCommand.Path) {
        $pythonPath = $pythonCommand.Path
    }

    $parts = @(
        (ConvertTo-NativeArgument $pythonPath),
        '-I',
        (ConvertTo-NativeArgument $CliPath)
    )
    foreach ($argument in $CliArguments) {
        $parts += ConvertTo-NativeArgument $argument
    }
    return ($parts -join ' ')
}

function Resolve-ProjectDirectory {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "project directory not found: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Get-ExportedAppName {
    param([string]$ResolvedProjectDir)

    $full = [System.IO.Path]::GetFullPath($ResolvedProjectDir).TrimEnd([char[]]@('\', '/'))
    if ((Split-Path -Path $full -Leaf) -ne 'project') {
        return $null
    }
    $appRoot = Split-Path -Path $full -Parent
    $appsRoot = Split-Path -Path $appRoot -Parent
    $expectedRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $RepoRoot 'chip-adapt\sifli')
    ).TrimEnd([char[]]@('\', '/'))

    if (-not [string]::Equals(
        $appsRoot.TrimEnd([char[]]@('\', '/')),
        $expectedRoot,
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        return $null
    }
    return (Split-Path -Path $appRoot -Leaf)
}

$suggestScript = Join-Path $ScriptDir 'suggest.ps1'
try {
    $suggestion = & $suggestScript
}
catch {
    throw "suggest.ps1 failed: $($_.Exception.Message)"
}

$resolvedPort = $Port
if (-not $resolvedPort) {
    $resolvedPort = [string]$suggestion.port
}
if (-not $resolvedPort) {
    throw 'no serial port: pass -Port COMx or connect the board so suggest.ps1 can pick one.'
}

$suggestedBuildDir = [string]$suggestion.build_dir
$suggestedProjectDir = [string]$suggestion.project_dir
$app = $null
$cliArguments = $null
$description = ''

if ($Build) {
    if ($suggestedProjectDir) {
        $resolvedProject = Resolve-ProjectDirectory -Path $suggestedProjectDir
        $app = Get-ExportedAppName -ResolvedProjectDir $resolvedProject
        if ($app) {
            $cliArguments = @(
                'flash', '--build', '--app', $app,
                '--port', $resolvedPort, '--actor', 'ai', '--json'
            )
            $description = "re-export chip-adapt/sifli/$app, build it, then flash"
        }
        else {
            $cliArguments = @(
                'flash', '--build', '--project-dir', $resolvedProject,
                '--port', $resolvedPort, '--actor', 'ai', '--json'
            )
            $description = "build $resolvedProject, then flash"
        }
    }
    elseif ($suggestion.app) {
        $app = [string]$suggestion.app
        $cliArguments = @(
            'flash', '--build', '--app', $app,
            '--port', $resolvedPort, '--actor', 'ai', '--json'
        )
        $description = "re-export app '$app', build it, then flash"
    }
    else {
        throw 'cannot -Build: suggest.ps1 found no project_dir or app.'
    }
}
else {
    if (-not $suggestedBuildDir) {
        throw 'no build_dir suggestion; run build-current.ps1 first or pass -Build.'
    }
    $sftoolParam = Join-Path $suggestedBuildDir 'sftool_param.json'
    if (-not (Test-Path -LiteralPath $sftoolParam -PathType Leaf)) {
        throw "build_dir is not flashable (missing sftool_param.json): $suggestedBuildDir; run build-current.ps1 first."
    }
    $cliArguments = @(
        'flash', '--build-dir', $suggestedBuildDir,
        '--port', $resolvedPort, '--actor', 'ai', '--json'
    )
    $description = "flash existing build dir $suggestedBuildDir"
}

if ($DryRun) {
    Write-Host 'DRY RUN: nothing is built or flashed.'
    Write-Host "  port:      $resolvedPort"
    if ($suggestedBuildDir) {
        Write-Host "  build_dir: $suggestedBuildDir"
    }
    else {
        Write-Host '  build_dir: (will be produced by -Build)'
    }
    Write-Host "  action:    $description"
    Write-Host '  command:'
    Write-Host "  $(Format-SifliCommand -CliArguments $cliArguments)"
    exit 0
}

$result = Invoke-SifliCli -CliArguments $cliArguments

$job = $null
if ($result.Stdout.Trim()) {
    try {
        $job = $result.Stdout | ConvertFrom-Json
    }
    catch {
        $job = $null
    }
}

if ($null -eq $job) {
    $detail = $result.Stderr.Trim()
    if (-not $detail) {
        $detail = "cli.py flash exited with code $($result.ExitCode)"
    }
    [Console]::Error.WriteLine("cli.py flash failed: $detail")
    exit $result.ExitCode
}

$jobResult = $job.result
$portOut = ''
$baudOut = ''
$chipOut = ''
$memoryOut = ''
$buildDirOut = ''
$fileCount = 0
$durationOut = ''
if ($null -ne $jobResult) {
    $portOut = [string]$jobResult.port
    $baudOut = $jobResult.baud
    $chipOut = [string]$jobResult.chip
    $memoryOut = [string]$jobResult.memory
    $buildDirOut = [string]$jobResult.build_dir
    if ($null -ne $jobResult.files) {
        $fileCount = @($jobResult.files).Count
    }
    $durationOut = $jobResult.duration_s
}
$appOut = ''
if ($app) {
    $appOut = $app
}

[pscustomobject][ordered]@{
    status      = [string]$job.status
    id          = [string]$job.id
    app         = $appOut
    port        = $portOut
    baud        = $baudOut
    chip        = $chipOut
    memory      = $memoryOut
    build_dir   = $buildDirOut
    file_count  = $fileCount
    duration_s  = $durationOut
    error       = [string]$job.error
    exit_code   = $result.ExitCode
}

exit $result.ExitCode
