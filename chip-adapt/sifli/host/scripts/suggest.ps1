#Requires -Version 5.1
<#
.SYNOPSIS
    Read the host's suggested app / project / build / port values.

.DESCRIPTION
    Runs `python -I chip-adapt/sifli/host/cli.py suggest --json` from the
    repository root and emits one PowerShell object with the fields
    app, project_dir, build_dir, port and baud.

    The CLI starts the local broker automatically when it is not running.
    Throws when the host cannot suggest an app, a project directory or a
    build directory; an empty port only means no serial port was detected.

.EXAMPLE
    .\chip-adapt\sifli\host\scripts\suggest.ps1

.EXAMPLE
    $suggestion = .\chip-adapt\sifli\host\scripts\suggest.ps1
    $suggestion.build_dir
#>
[CmdletBinding()]
param()

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

$result = Invoke-SifliCli -CliArguments @('suggest', '--json')
if ($result.ExitCode -ne 0) {
    $detail = $result.Stderr.Trim()
    if (-not $detail) {
        $detail = "cli.py suggest exited with code $($result.ExitCode)"
    }
    throw "cli.py suggest failed: $detail"
}

try {
    $payload = $result.Stdout | ConvertFrom-Json
}
catch {
    throw "cli.py suggest returned invalid JSON: $($_.Exception.Message)"
}
if ($null -eq $payload) {
    throw 'cli.py suggest returned an empty JSON payload.'
}

$app = [string]$payload.app
$projectDir = [string]$payload.project_dir
$buildDir = [string]$payload.build_dir
$port = [string]$payload.port
$baud = 0
if ($null -ne $payload.baud) {
    $baud = [int]$payload.baud
}

if (-not $app -and -not $projectDir -and -not $buildDir) {
    throw 'the host has no app, project_dir or build_dir suggestion; build an app first or pass an explicit path.'
}

[pscustomobject][ordered]@{
    app         = $app
    project_dir = $projectDir
    build_dir   = $buildDir
    port        = $port
    baud        = $baud
}
