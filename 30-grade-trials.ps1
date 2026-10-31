#Requires -Version 7.0

<#
.SYNOPSIS
    Grade saved trials of a script-fix case, or report pass rates per subject.

.DESCRIPTION
    Wraps `python -m scriptfix grade|report` from the repo's venv.

    Grade mode (-Case and -Runs) grades the saved trial runs of one script-fix
    case under rubric script-fix-v0: transcript validity, fair play, static
    checks, then one replay per distinct fix with control replays of the
    reference and the broken input before and after. Verdicts are recorded in
    <case>\grading\trials.jsonl. Replays are single, sequential replays against
    the case's target; Eval 01's replays open headed browser windows. Exits 1
    when a control replay failed and 2 on usage errors.

    Report mode (-Report) prints, per case and subject, passes/valid, rate, the
    95% lower bound, pending and invalid counts and the most common tags. With
    no -Case it covers every eval that has a grading\trials.jsonl.

    Optional options are passed through only when given, so the Python CLI's
    defaults stay the single source of truth (see: .venv\Scripts\python.exe
    -m scriptfix grade -h). Run the script; don't dot-source it (it exits
    with the Python exit code). Needs the venv from .\01-setup-env.ps1.

.PARAMETER Case
    The eval directory, e.g. evals\01-playwright-python-basic. Grade mode takes
    exactly one; with -Report it may be repeated (comma-separated) to limit
    the report.

.PARAMETER Runs
    Runs to grade: 1-12 or 1,3,5-7. Required in grade mode.

.PARAMETER TrialsRoot
    Folder holding the <NN>-run<N>\ trial folders (Python default applies).

.PARAMETER ProjectsRoot
    Claude Code projects folder used to find session transcripts (Python
    default applies).

.PARAMETER Effort
    Subject effort to record.

.PARAMETER Context
    Subject context files to record.

.PARAMETER Tools
    Subject tool profile to record, e.g. interactive.

.PARAMETER Timeout
    Seconds before a replay is killed.

.PARAMETER Report
    Print pass rates instead of grading.

.PARAMETER Help
    Print this usage and exit. Also: -h, --help, or pwsh's native -?.

.PARAMETER UnknownArgs
    Not for direct use: collects --help and rejects any unrecognized argument.

.EXAMPLE
    .\30-grade-trials.ps1 -Case evals\01-playwright-python-basic -Runs 3-12
    Grade runs 3 through 12 of the case and record the verdicts.

.EXAMPLE
    .\30-grade-trials.ps1 -Case evals\01-playwright-python-basic -Runs 1-2 -Tools interactive
    Grade runs 1 and 2, recording them under the interactive tool profile.

.EXAMPLE
    .\30-grade-trials.ps1 -Report
    Print pass rates for every case that has recorded trials.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string[]]$Case,
    [string]$Runs,
    [string]$TrialsRoot,
    [string]$ProjectsRoot,
    [string]$Effort,
    [string]$Context,
    [string]$Tools,
    [int]$Timeout,
    [switch]$Report,
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
if ($UnknownArgs) {
    throw "Unknown argument(s): $UnknownArgs. Run .\$(Split-Path -Leaf $PSCommandPath) -h for usage."
}

$scriptName = Split-Path -Leaf $PSCommandPath
if (-not $Report) {
    if (-not $Case) { throw "Missing -Case (the eval directory to grade). Run .\$scriptName -h for usage." }
    if ($Case.Count -ne 1) { throw "Grade mode takes exactly one -Case (got $($Case.Count)). Run .\$scriptName -h for usage." }
    if (-not $Runs) { throw "Missing -Runs (e.g. 3-12 or 1,3,5-7). Run .\$scriptName -h for usage." }
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
        throw "Venv python not found at $venvPython. Run .\01-setup-env.ps1 first."
    }

    $pyArgs = @('-m', 'scriptfix', ($Report ? 'report' : 'grade'))
    foreach ($c in $Case) { $pyArgs += @('--case', $c) }
    if (-not $Report) { $pyArgs += @('--runs', $Runs) }
    $optional = @(
        @('--trials-root',   $TrialsRoot),
        @('--projects-root', $ProjectsRoot),
        @('--effort',        $Effort),
        @('--context',       $Context),
        @('--tools',         $Tools)
    )
    foreach ($option in $optional) {
        if ($option[1]) { $pyArgs += @($option[0], $option[1]) }
    }
    if ($timeoutGiven) { $pyArgs += @('--timeout', "$Timeout") }

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
