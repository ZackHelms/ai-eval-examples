#Requires -Version 7.0

<#
.SYNOPSIS
    Build or rebuild a script-fix case from its recipe.toml, capturing its
    evidence in a neutral folder.

.DESCRIPTION
    Wraps `python -m scriptfix make-case` from the repo's venv. From the case's
    grading\recipe.toml it builds the reference and the input script, then
    replays the input once against the case's target in the capture venv
    ($env:LOCALAPPDATA\pwrun\venv, a folder outside the repo) and records the
    result and trace as the case's evidence, plus capture.toml. A dry run
    builds and checks everything in memory and writes nothing. Captures are
    single, sequential replays against the case's target.

    Unless -DryRun, it first builds or verifies the capture venv with
    .\01-setup-env.ps1 -VenvDir ... -NoActivate (about a minute the first time).

    Optional options are passed through only when given, so the Python CLI's
    defaults stay the single source of truth (see: .venv\Scripts\python.exe
    -m scriptfix make-case -h). Run the script; don't dot-source it (it exits
    with a meaningful code). Needs the venv from .\01-setup-env.ps1.

    Exit codes: 0 ok; 1 the capture was a surprise (nothing written);
    2 usage, recipe, case or setup error.

.PARAMETER Case
    The eval directory, e.g. evals\02-docs-journey-a. A relative path resolves
    against your current directory.

.PARAMETER DryRun
    Build and check without capturing or writing anything, and skip the
    capture-venv setup.

.PARAMETER Timeout
    Seconds before the capture replay is killed (Python default applies).

.PARAMETER Help
    Print this usage and exit. Also: -h, --help, or pwsh's native -?.

.PARAMETER UnknownArgs
    Not for direct use: collects --help and rejects any unrecognized argument.

.EXAMPLE
    .\10-make-case.ps1 -Case evals\02-docs-journey-a -DryRun
    Check the recipe and what would be built, without capturing or writing.

.EXAMPLE
    .\10-make-case.ps1 -Case evals\02-docs-journey-a
    Build the case and capture its evidence.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Case,
    [switch]$DryRun,
    [int]$Timeout,
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

# Exit code 1 means "capture surprise", so every usage error here exits 2.
$scriptName = Split-Path -Leaf $PSCommandPath
function Stop-Usage([string]$Message) {
    [Console]::Error.WriteLine("$Message Run .\$scriptName -h for usage.")
    exit 2
}
if ($UnknownArgs) { Stop-Usage "Unknown argument(s): $UnknownArgs." }
if (-not $Case) { Stop-Usage 'Missing -Case (the eval directory to build).' }

# Resolve against the caller's directory before anything changes directory.
$caseDir = [IO.Path]::GetFullPath($Case, $PWD.Path)
if (-not (Test-Path -LiteralPath $caseDir -PathType Container)) {
    Stop-Usage "-Case is not a directory: $caseDir."
}

# The work runs in a child scope so StrictMode, $ErrorActionPreference and the
# helper variables don't leak into your session. Python's exit code lands in
# $script:exitCode (the block's own output is not captured, so Python's isn't).
# $PSBoundParameters inside the block is the block's own, so capture it here.
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

    # The capture venv lives outside the repo, in a neutral folder.
    $captureVenvDir    = Join-Path $env:LOCALAPPDATA 'pwrun\venv'
    $capturePython     = Join-Path $captureVenvDir ($IsWindows ? 'Scripts\python.exe' : 'bin/python')

    if (-not $DryRun) {
        try {
            & (Join-Path $repoRoot '01-setup-env.ps1') -VenvDir $captureVenvDir -NoActivate
        } catch {
            [Console]::Error.WriteLine("Capture venv setup failed: $($_.Exception.Message)")
            $script:exitCode = 2
            return
        }
    }

    $pyArgs = @('-m', 'scriptfix', 'make-case', '--case', $caseDir, '--python', $capturePython)
    if ($timeoutGiven) { $pyArgs += @('--timeout', "$Timeout") }
    if ($DryRun) { $pyArgs += '--dry-run' }

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
