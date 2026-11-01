#Requires -Version 7.0

<#
.SYNOPSIS
    Run N one-shot headless trials of a case with claude, one at a time, and
    leave the logs where 30-grade-trials.ps1 looks.

.DESCRIPTION
    Wraps `python -m scriptfix run` from the repo's venv. It runs N one-shot
    headless trials of a case strictly one at a time, each in a fresh
    ~\eval-trials\<NN>-run<N>\ folder holding only prompt.md and inputs\, with
    the stream log, the stderr file and the subject sidecar beside that folder.

    It handles the launcher gotchas for you: the permission allow rules use
    absolute paths, the parent session's variables are stripped from claude's
    environment, and the real pwsh.exe (the one running this script) goes first
    on claude's PATH. It never overwrites a trial (new numbers follow the
    highest existing run, and -Runs refuses numbers that exist), and it stops
    at the first harness problem (a non-zero exit, a timeout, no result line).

    Each trial is a real model call and costs money (about $0.01-$0.08 on
    Eval 01), so run -SelfTest first after any launcher change; it is one
    cheap run that takes no case. Only the edit-only tool profile and no
    context files (--safe-mode) are supported. The edit-only profile is the
    seven built-in tools Read, Glob, Grep, Edit, Write, Bash and PowerShell
    (no web tools), with Edit and Write limited to the case's script.

    When the batch finishes it prints the 30-grade-trials.ps1 command that
    grades it.

    Optional options are passed through only when given, so the Python CLI's
    defaults stay the single source of truth (see: .venv\Scripts\python.exe
    -m scriptfix run -h). Run the script; don't dot-source it (it exits with a
    meaningful code). Needs the venv from .\01-setup-env.ps1.

    Exit codes: 0 ok; 1 a harness problem or a failed self-test; 2 usage error.

.PARAMETER Case
    The eval directory, e.g. evals\02-docs-journey-a. A relative path resolves
    against your current directory. Not used with -SelfTest.

.PARAMETER Model
    The model id, passed to claude as given, e.g. claude-haiku-5-5. Required
    for trials; -SelfTest defaults to a cheap model.

.PARAMETER Count
    Run this many new trials, numbered after the highest existing run. Not
    used with -Runs.

.PARAMETER Runs
    Run exactly these numbers, e.g. 13-22 or 1,3,5-7 (none may exist yet). Not
    used with -Count.

.PARAMETER Effort
    claude's effort level (default, low, medium, high, xhigh, max); default
    omits the flag.

.PARAMETER TrialsRoot
    The folder that receives the trial folders and logs. A relative path
    resolves against your current directory. Default: ~\eval-trials.

.PARAMETER Timeout
    Seconds before a trial is killed (Python default applies).

.PARAMETER DryRun
    Print the run numbers, folders, claude command lines and the environment
    names to strip; create and launch nothing, and cost nothing.

.PARAMETER SelfTest
    Run the cheap harness check (about $0.01) instead of a case. It takes no
    -Case, -Count, -Runs or -DryRun.

.PARAMETER Help
    Print this usage and exit. Also: -h, --help, or pwsh's native -?.

.PARAMETER UnknownArgs
    Not for direct use: collects --help and rejects any unrecognized argument.

.EXAMPLE
    .\20-run-trials.ps1 -SelfTest
    Check the launcher itself with one cheap real run.

.EXAMPLE
    .\20-run-trials.ps1 -Case evals\01-playwright-python-basic -Model claude-haiku-5-5 -Count 1 -DryRun
    Show what a single trial would run, without creating or launching anything.

.EXAMPLE
    .\20-run-trials.ps1 -Case evals\02-docs-journey-a -Model claude-haiku-5-5 -Count 10
    Screen a model with 10 trials, one after another.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Case,
    [string]$Model,
    [int]$Count,
    [string]$Runs,
    [string]$Effort,
    [string]$TrialsRoot,
    [int]$Timeout,
    [switch]$DryRun,
    [switch]$SelfTest,
    [Alias('h')]
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments, DontShow)]
    [string[]]$UnknownArgs
)

# Interactive pwsh passes `--help` through as a plain string rather than a
# parameter name, so it arrives in $UnknownArgs; anything else there is a typo.
if ($Help -or $UnknownArgs -contains '--help') {
    Get-Help $PSCommandPath -Detailed
    return
}

# Exit code 1 means "harness problem", so every usage error here exits 2.
$scriptName = Split-Path -Leaf $PSCommandPath
function Stop-Usage([string]$Message) {
    [Console]::Error.WriteLine("$Message Run .\$scriptName -h for usage.")
    exit 2
}
if ($UnknownArgs) { Stop-Usage "Unknown argument(s): $UnknownArgs." }

# Resolve against the caller's directory before anything changes directory.
# Argument-combination checks are left to the Python CLI (it exits 2).
$caseDir = $null
if ($Case) {
    $caseDir = [IO.Path]::GetFullPath($Case, $PWD.Path)
    if (-not (Test-Path -LiteralPath $caseDir -PathType Container)) {
        Stop-Usage "-Case is not a directory: $caseDir."
    }
}
$trialsRootDir = $null
if ($TrialsRoot) { $trialsRootDir = [IO.Path]::GetFullPath($TrialsRoot, $PWD.Path) }

# The work runs in a child scope so StrictMode, $ErrorActionPreference and the
# helper variables don't leak into your session. Python's exit code lands in
# $script:exitCode (the block's own output is not captured, so Python's isn't).
# $PSBoundParameters inside the block is the block's own, so capture it here.
$countGiven = $PSBoundParameters.ContainsKey('Count')
$timeoutGiven = $PSBoundParameters.ContainsKey('Timeout')
$script:exitCode = 0
& {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'

    $repoRoot   = $PSScriptRoot
    $venvPython = Join-Path $repoRoot ($IsWindows ? '.venv\Scripts\python.exe' : '.venv/bin/python')
    if (-not (Test-Path $venvPython)) {
        [Console]::Error.WriteLine("Venv python not found at $venvPython. Run .\01-setup-env.ps1 first.")
        $script:exitCode = 2
        return
    }

    # The running pwsh is the real executable, not the app-execution alias.
    $pyArgs = @('-m', 'scriptfix', 'run', '--pwsh', (Get-Process -Id $PID).Path)
    if ($caseDir) { $pyArgs += @('--case', $caseDir) }
    if ($Model) { $pyArgs += @('--model', $Model) }
    if ($countGiven) { $pyArgs += @('--count', "$Count") }
    if ($Runs) { $pyArgs += @('--runs', $Runs) }
    if ($Effort) { $pyArgs += @('--effort', $Effort) }
    if ($trialsRootDir) { $pyArgs += @('--trials-root', $trialsRootDir) }
    if ($timeoutGiven) { $pyArgs += @('--timeout', "$Timeout") }
    if ($DryRun) { $pyArgs += '--dry-run' }
    if ($SelfTest) { $pyArgs += '--self-test' }

    # `python -m scriptfix` needs tools\ on the path; restore the caller's value
    # afterwards because env changes are process-wide.
    $previousPythonPath = $env:PYTHONPATH
    Push-Location $repoRoot
    try {
        $env:PYTHONPATH = Join-Path $repoRoot 'tools'
        & $venvPython @pyArgs
        $script:exitCode = $LASTEXITCODE
    } finally {
        Pop-Location
        $env:PYTHONPATH = $previousPythonPath
    }
}
exit $exitCode
