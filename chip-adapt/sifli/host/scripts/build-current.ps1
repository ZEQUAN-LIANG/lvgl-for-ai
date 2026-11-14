#Requires -Version 5.1
<#
.SYNOPSIS
    Build the current SiFli host project or user app.

.DESCRIPTION
    Resolves the project directory from suggest.ps1 unless -ProjectDir is
    given, then runs `cli.py build --json` and prints the important job
    result fields.  The CLI exit code (0 ok, 1 build failed, 2 harness) is
    passed through.

    When the project directory is the exported copy
    `chip-adapt/exports/<app>/project`, the script passes `--app <app>` so the
    host re-exports `user/app/<app>` before building instead of compiling a
    stale exported tree.

.PARAMETER ProjectDir
    Project directory to build.  Defaults to the project_dir suggested by
    the host.  Relative paths are resolved against the current directory.

.PARAMETER DryRun
    Print the CLI command that would run and exit without building.

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\build-current.ps1

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\build-current.ps1 -ProjectDir chip-adapt/exports/sift_watch/project

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\build-current.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$ProjectDir,
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
        (Join-Path $RepoRoot 'chip-adapt\exports')
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

$suggestion = $null
if (-not $ProjectDir) {
    $suggestScript = Join-Path $ScriptDir 'suggest.ps1'
    try {
        $suggestion = & $suggestScript
    }
    catch {
        throw "suggest.ps1 failed: $($_.Exception.Message)"
    }
    if ($suggestion.project_dir) {
        $ProjectDir = [string]$suggestion.project_dir
    }
}

$app = $null
$cliArguments = $null
$description = ''

if ($ProjectDir) {
    $resolvedProject = Resolve-ProjectDirectory -Path $ProjectDir
    $app = Get-ExportedAppName -ResolvedProjectDir $resolvedProject
    if ($app) {
        $cliArguments = @('build', '--app', $app, '--actor', 'ai', '--json')
        $description = "app '$app' (re-export chip-adapt/exports/$app, then scons)"
    }
    else {
        $cliArguments = @('build', '--project-dir', $resolvedProject, '--actor', 'ai', '--json')
        $description = "project $resolvedProject (scons only)"
    }
}
elseif ($suggestion -and $suggestion.app) {
    $app = [string]$suggestion.app
    $cliArguments = @('build', '--app', $app, '--actor', 'ai', '--json')
    $description = "app '$app' (re-export, then scons)"
}
else {
    throw 'no project directory; pass -ProjectDir <path> or build an app once so suggest.ps1 can find it.'
}

if ($DryRun) {
    Write-Host 'DRY RUN: build is not executed.'
    Write-Host "  target:  $description"
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
        $detail = "cli.py build exited with code $($result.ExitCode)"
    }
    [Console]::Error.WriteLine("cli.py build failed: $detail")
    exit $result.ExitCode
}

$jobResult = $job.result
$projectDirOut = ''
$buildDirOut = ''
$durationOut = ''
if ($null -ne $jobResult) {
    $projectDirOut = [string]$jobResult.project_dir
    $buildDirOut = [string]$jobResult.build_dir
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
    project_dir = $projectDirOut
    build_dir   = $buildDirOut
    duration_s  = $durationOut
    error       = [string]$job.error
    exit_code   = $result.ExitCode
}

exit $result.ExitCode
