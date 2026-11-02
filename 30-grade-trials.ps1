#Requires -Version 7.0

<#
.SYNOPSIS
    Grade saved trials of a script-fix case and judge them, calibrate the
    judge, or report pass rates per subject.

.DESCRIPTION
    Wraps `python -m scriptfix grade|judge|calibrate|report|regrade` from the repo's
    venv.

    Grade mode (-Case and -Runs) grades the saved trial runs of one script-fix
    case under rubric script-fix-v1: transcript validity, fair play, static
    checks, then one replay per distinct fix with control replays of the
    reference and the broken input before and after. Verdicts are recorded in
    <case>\grading\trials.jsonl. Replays are single, sequential replays against
    the case's target; Eval 01's replays open headed browser windows. Exits 1
    when a control replay failed and 2 on usage errors.

    When grading succeeds, grade mode then judges the case's pending-judge
    trials (what -Judge does), so a run is graded and judged in one go.
    Judging asks the LLM judge questions about the fixes that the static checks
    can't settle; each is a paid Sonnet call (see Judge mode). Pass -NoJudge to
    grade only and judge later with -Judge. The script exits with grade's code
    when that is non-zero, else with judge's.

    Judge mode (-Judge, one -Case, optional -Runs) judges only: no grading and
    no replays. Without -Runs it judges every pending-judge or needs-review
    run. Each question is answered from the case's grading\reviews.toml, else
    its grading\judge.jsonl cache, else one `claude -p` call. The call is a
    paid Sonnet call capped at $0.10; a re-run resumes from the cache. With
    -DryRun it lists the questions and asks nothing, writes nothing.

    Calibrate mode (-Calibrate) asks the judge every labeled corpus item
    (145 calls with the defaults) and records a full pass in the judge's
    calibration.json, which judging requires. Each call is a paid Sonnet call
    capped at $0.10, and a calibration run stops at $6 total by default
    (-MaxTotalUsd). With -DryRun it prints the call count and asks nothing.
    Takes no -Case or -Runs.

    Regrade mode (-Regrade, one -Case and -Runs) re-grades the case's recorded
    trials from their saved fixes and transcripts without a single replay: it
    checks that a grader change left the verdicts alone. Without -Write it
    only checks and writes nothing (exit 1 on a changed verdict, or when a
    run would need a replay). With -Write, and an older rubric in -From, it
    records the runs under the current rubric and leaves every other line
    alone; Python then prints a NEXT= line with the -Judge command for the
    runs that await the judge. Each run keeps its own recorded subject.

    Report mode (-Report) prints, per case and subject, passes/valid, rate, the
    95% lower bound, pending and invalid counts and the most common tags. With
    no -Case it covers every eval that has a grading\trials.jsonl.

    Optional options are passed through only when given, so the Python CLI's
    defaults stay the single source of truth (see: .venv\Scripts\python.exe
    -m scriptfix grade -h, judge -h, calibrate -h, regrade -h). Run the script; don't
    dot-source it (it exits with the Python exit code). Needs the venv from
    .\01-setup-env.ps1.

.PARAMETER Case
    The eval directory, e.g. evals\01-playwright-python-basic. Grade mode and
    -Judge take exactly one; with -Report it may be repeated (comma-separated)
    to limit the report. A relative path resolves against your current folder.

.PARAMETER Runs
    Runs to grade: 1-12 or 1,3,5-7. Required in grade mode; optional with
    -Judge (default: every pending-judge or needs-review run).

.PARAMETER TrialsRoot
    Folder holding the <NN>-run<N>\ trial folders (Python default applies).

.PARAMETER ProjectsRoot
    Claude Code projects folder used to find session transcripts (Python
    default applies).

.PARAMETER Effort
    Subject effort to record for runs without a <NN>-run<N>.subject.json sidecar.

.PARAMETER Context
    Subject context files to record for runs without a <NN>-run<N>.subject.json sidecar.

.PARAMETER Tools
    Subject tool profile to record for runs without a <NN>-run<N>.subject.json sidecar, e.g. interactive.

.PARAMETER Timeout
    Seconds before a replay is killed.

.PARAMETER Report
    Print pass rates instead of grading.

.PARAMETER Regrade
    Re-grade the case's recorded trials without replaying (needs exactly one
    -Case and -Runs). Checks only unless -Write is given.

.PARAMETER From
    With -Regrade, the rubric whose records are re-graded (Python default
    applies: the current rubric, which -Write refuses), e.g. script-fix-v0.

.PARAMETER Write
    With -Regrade, record the runs under the current rubric when the check
    finds no run that needs a replay. Needs an older rubric in -From.

.PARAMETER RepoRoot
    With -Regrade, the repository root the grader uses for its answer-key
    rule (Python default applies). A relative path resolves against your
    current folder.

.PARAMETER Judge
    Judge the case's trials only, without grading or replaying (needs exactly
    one -Case; -Runs is optional). Paid Sonnet calls, $0.10 cap each.

.PARAMETER NoJudge
    In grade mode, skip the judging that normally follows a successful grade.

.PARAMETER Calibrate
    Ask the judge every labeled corpus item and record a full pass. Paid
    Sonnet calls: $0.10 cap each, $6 per run by default. Takes no -Case or
    -Runs.

.PARAMETER DryRun
    With -Judge or -Calibrate, list what would be asked and ask nothing.

.PARAMETER Samples
    With -Calibrate, times to ask each item (Python default applies; fewer
    than the default is never recorded).

.PARAMETER Items
    With -Calibrate, ask only these item ids (comma-separated); the result is
    never recorded.

.PARAMETER MaxTotalUsd
    With -Calibrate, stop once the running cost passes this many dollars
    (Python default applies).

.PARAMETER Claude
    The claude executable that judging and calibrating ask (Python default
    applies: claude on PATH). A relative path resolves against your current
    folder.

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
    .\30-grade-trials.ps1 -Judge -DryRun -Case evals\01-playwright-python-basic -Runs 10,12
    List the judge's questions for runs 10 and 12 without asking any.

.EXAMPLE
    .\30-grade-trials.ps1 -Regrade -Case evals\01-playwright-python-basic -Runs 1-12 -From script-fix-v0
    Check that runs 1-12, recorded under script-fix-v0, still grade the same
    now, without replaying or writing anything.

.EXAMPLE
    .\30-grade-trials.ps1 -Regrade -Write -Case evals\01-playwright-python-basic -Runs 1-12 -From script-fix-v0
    The same, then record the runs under the current rubric.

.EXAMPLE
    .\30-grade-trials.ps1 -Calibrate -DryRun
    Print how many calls a full calibration would make, without making any.

.EXAMPLE
    .\30-grade-trials.ps1 -Report
    Print pass rates for every case that has recorded trials.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string[]]$Case,
    [string[]]$Runs,
    [string]$TrialsRoot,
    [string]$ProjectsRoot,
    [string]$Effort,
    [string]$Context,
    [string]$Tools,
    [int]$Timeout,
    [switch]$Report,
    [switch]$Regrade,
    [string]$From,
    [switch]$Write,
    [string]$RepoRoot,
    [switch]$Judge,
    [switch]$NoJudge,
    [switch]$Calibrate,
    [switch]$DryRun,
    [int]$Samples,
    [string[]]$Items,
    [double]$MaxTotalUsd,
    [string]$Claude,
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

# Exit code 1 means "a control was surprising", so every usage error exits 2.
$scriptName = Split-Path -Leaf $PSCommandPath
function Stop-Usage([string]$Message) {
    [Console]::Error.WriteLine("$Message Run .\$scriptName -h for usage.")
    exit 2
}
if ($UnknownArgs) { Stop-Usage "Unknown argument(s): $UnknownArgs." }
# `pwsh -File` hands a comma list over as one string, so split it here.
if ($Case) { $Case = @($Case -split ',' | Where-Object { $_ }) }
if ($Items) { $Items = @($Items -split ',' | Where-Object { $_ }) }
# In a session `-Runs 10,12` is an array; under `pwsh -File` it is one string.
$runsText = $Runs -join ','

# The mode is whichever of -Report, -Regrade, -Judge and -Calibrate is given;
# none means grade mode. $PSBoundParameters is read here because the work block below
# has its own.
$samplesGiven = $PSBoundParameters.ContainsKey('Samples')
$maxTotalUsdGiven = $PSBoundParameters.ContainsKey('MaxTotalUsd')
$timeoutGiven = $PSBoundParameters.ContainsKey('Timeout')
$modes = @(@($Report, $Regrade, $Judge, $Calibrate) | Where-Object { $_ })
if ($modes.Count -gt 1) { Stop-Usage "Use only one of -Report, -Regrade, -Judge and -Calibrate." }
$gradeMode = $modes.Count -eq 0
if ($NoJudge -and -not $gradeMode) { Stop-Usage "-NoJudge only applies to grade mode (-Case and -Runs)." }
if (($samplesGiven -or $Items -or $maxTotalUsdGiven) -and -not $Calibrate) {
    Stop-Usage "-Samples, -Items and -MaxTotalUsd need -Calibrate."
}
if ($DryRun -and -not ($Judge -or $Calibrate)) { Stop-Usage "-DryRun needs -Judge or -Calibrate." }
if (($From -or $Write -or $RepoRoot) -and -not $Regrade) { Stop-Usage "-From, -Write and -RepoRoot need -Regrade." }
if ($Calibrate -and ($Case -or $Runs)) { Stop-Usage "-Calibrate takes no -Case or -Runs." }
if ($Regrade) {
    if (-not $Case) { Stop-Usage "Missing -Case (the eval directory to re-grade)." }
    if ($Case.Count -ne 1) { Stop-Usage "-Regrade takes exactly one -Case (got $($Case.Count))." }
    if (-not $Runs) { Stop-Usage "Missing -Runs (e.g. 1-12 or 1,3,5-7)." }
}
if ($Judge -and -not $Case) { Stop-Usage "Missing -Case (the eval directory to judge)." }
if ($Judge -and $Case.Count -ne 1) { Stop-Usage "-Judge takes exactly one -Case (got $($Case.Count))." }
if ($gradeMode) {
    if (-not $Case) { Stop-Usage "Missing -Case (the eval directory to grade)." }
    if ($Case.Count -ne 1) { Stop-Usage "Grade mode takes exactly one -Case (got $($Case.Count))." }
    if (-not $Runs) { Stop-Usage "Missing -Runs (e.g. 3-12 or 1,3,5-7)." }
}

# Resolve against the caller's directory before anything changes directory;
# Python runs from the repo root, so it gets absolute paths.
$caseDirs = @()
foreach ($c in $Case) {
    $dir = [IO.Path]::GetFullPath($c, $PWD.Path)
    if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        Stop-Usage "-Case is not a directory: $dir."
    }
    $caseDirs += $dir
}
$trialsRootDir = $null
if ($TrialsRoot) { $trialsRootDir = [IO.Path]::GetFullPath($TrialsRoot, $PWD.Path) }
$projectsRootDir = $null
if ($ProjectsRoot) { $projectsRootDir = [IO.Path]::GetFullPath($ProjectsRoot, $PWD.Path) }
$repoRootDir = $null
if ($RepoRoot) { $repoRootDir = [IO.Path]::GetFullPath($RepoRoot, $PWD.Path) }
$claudePath = $null
if ($Claude) { $claudePath = [IO.Path]::GetFullPath($Claude, $PWD.Path) }

# The work runs in a child scope so StrictMode, $ErrorActionPreference and the
# helper variables don't leak into your session. Python's exit code lands in
# $script:exitCode (the block's own output is not captured, so Python's isn't).
# $PSBoundParameters inside the block is the block's own, so the facts it needs
# were captured above.
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

    $subcommand = $Report ? 'report' : $Regrade ? 'regrade' : $Judge ? 'judge' : $Calibrate ? 'calibrate' : 'grade'
    $pyArgs = @('-m', 'scriptfix', $subcommand)
    foreach ($c in $caseDirs) { $pyArgs += @('--case', $c) }
    # Options in the order given; an empty value means "not given".
    $optional = @()
    if ($gradeMode -or $Regrade -or ($Judge -and $runsText)) { $optional += , @('--runs', $runsText) }
    if ($Regrade) {
        $optional += , @('--from',      $From)
        $optional += , @('--repo-root', $repoRootDir)
    }
    # Options a mode doesn't take are left for Python to reject (exit 2).
    if (-not $Calibrate) {
        $optional += , @('--trials-root',   $trialsRootDir)
        $optional += , @('--projects-root', $projectsRootDir)
    }
    if (-not $Judge -and -not $Calibrate) {
        $optional += , @('--effort',  $Effort)
        $optional += , @('--context', $Context)
        $optional += , @('--tools',   $Tools)
    }
    if ($Judge -or $Calibrate) { $optional += , @('--claude', $claudePath) }
    foreach ($option in $optional) {
        if ($option[1]) { $pyArgs += @($option[0], $option[1]) }
    }
    if ($timeoutGiven -and -not $Judge -and -not $Calibrate) { $pyArgs += @('--timeout', "$Timeout") }
    if ($Calibrate) {
        if ($samplesGiven) { $pyArgs += @('--samples', "$Samples") }
        foreach ($item in $Items) { $pyArgs += @('--items', $item) }
        if ($maxTotalUsdGiven) { $pyArgs += @('--max-total-usd', $MaxTotalUsd.ToString([cultureinfo]::InvariantCulture)) }
    }
    if ($Regrade -and $Write) { $pyArgs += '--write' }
    if ($DryRun) { $pyArgs += '--dry-run' }

    # Grade mode judges what it just graded, the same way `-Judge` would.
    $judgeArgs = $null
    if ($gradeMode -and -not $NoJudge) {
        $judgeArgs = @('-m', 'scriptfix', 'judge', '--case', $caseDirs[0], '--runs', $runsText)
        if ($trialsRootDir)  { $judgeArgs += @('--trials-root', $trialsRootDir) }
        if ($projectsRootDir) { $judgeArgs += @('--projects-root', $projectsRootDir) }
        if ($claudePath)      { $judgeArgs += @('--claude', $claudePath) }
    }

    # `python -m scriptfix` needs tools\ on the path; restore the caller's value
    # afterwards because env changes are process-wide.
    $previousPythonPath = $env:PYTHONPATH
    Push-Location $repoRoot
    try {
        $env:PYTHONPATH = Join-Path $repoRoot 'tools'
        & $venvPython @pyArgs
        $script:exitCode = $LASTEXITCODE
        if ($script:exitCode -eq 0 -and $judgeArgs) {
            & $venvPython @judgeArgs
            $script:exitCode = $LASTEXITCODE
        }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $previousPythonPath
    }
}
exit $exitCode
