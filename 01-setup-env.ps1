#Requires -Version 7.0

<#
.SYNOPSIS
    Ensure this repo's Python venv exists, has every prerequisite for the
    current evals, and is active in your pwsh session.

.DESCRIPTION
    Idempotent and safe to re-run any time (a few seconds when nothing changed):
      1. creates .venv\ at the repo root from Python 3.12 if it's missing
         (-Recreate rebuilds it from scratch);
      2. pip-installs requirements.txt when the file changed since the last
         install (-Force reinstalls regardless);
      3. installs the Playwright browser(s) the evals use (no-op when present);
      4. smoke-tests the result: headless Chromium opens about:blank (no network);
      5. activates the venv in your session.

    Run it or dot-source it. Both leave the venv active, because a pwsh script
    runs inside your session's process (unlike bash, where ./script.sh runs in a
    child process and you must `source` it to keep its environment changes):
        .\01-setup-env.ps1
        . .\01-setup-env.ps1
    Leave the venv with `deactivate`.

.PARAMETER Recreate
    Delete .venv\ and rebuild it (e.g. after a Python upgrade, or to drop
    packages that were removed from requirements.txt).

.PARAMETER Force
    Reinstall requirements.txt even if it hasn't changed.

.PARAMETER Help
    Print this usage and exit. Also: -h, --help, or pwsh's native -?.

.PARAMETER UnknownArgs
    Not for direct use: collects --help and rejects any unrecognized argument.

.EXAMPLE
    .\01-setup-env.ps1
    Set up (or verify) the venv and activate it. Run this at the start of a session.

.EXAMPLE
    .\01-setup-env.ps1 -Recreate
    Throw away .venv\ and rebuild it from requirements.txt.
#>
[CmdletBinding()]
param(
    [switch]$Recreate,
    [switch]$Force,
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

# The work runs in a child scope so StrictMode, $ErrorActionPreference and the
# helper variables don't leak into your session when this file is dot-sourced.
& {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'

    $pythonVersion = '3.12'            # repo pin; ADR pending (TODO.md § Needs Zack)
    $browsers      = @('chromium')     # Playwright browsers the current evals use
    $repoRoot      = $PSScriptRoot
    $venvDir       = Join-Path $repoRoot '.venv'
    $binDir        = Join-Path $venvDir ($IsWindows ? 'Scripts' : 'bin')
    $venvPython    = Join-Path $binDir ($IsWindows ? 'python.exe' : 'python')
    $requirements  = Join-Path $repoRoot 'requirements.txt'
    $stampFile     = Join-Path $venvDir '.requirements.sha256'

    function Write-Step([string]$Message) {
        Write-Host "==> $Message" -ForegroundColor Cyan
    }

    # Native executables don't throw on failure; check every exit code.
    function Invoke-Checked([string]$FilePath) {
        & $FilePath @args
        if ($LASTEXITCODE -ne 0) {
            throw "'$FilePath $args' failed with exit code $LASTEXITCODE."
        }
    }

    # Full path of an installed Python $pythonVersion interpreter, or $null.
    # The `py` launcher (Windows) picks among installed versions; the rest cover
    # PATH, where the Microsoft Store's python.exe stub fails the probe and is skipped.
    function Find-BasePython {
        $candidates = @(
            @('py', "-$pythonVersion"),
            @("python$pythonVersion"),
            @('python'),
            @('python3')
        )
        foreach ($candidate in $candidates) {
            $exe = $candidate[0]
            $exeArgs = @($candidate | Select-Object -Skip 1)
            if (-not (Get-Command $exe -CommandType Application -ErrorAction SilentlyContinue)) {
                continue
            }
            $probe = @(& $exe @exeArgs -c 'import sys; print(sys.executable); print(sys.version.split()[0])' 2>$null)
            if ($LASTEXITCODE -eq 0 -and $probe.Count -eq 2 -and $probe[1] -like "$pythonVersion.*") {
                return $probe[0]
            }
        }
        return $null
    }

    if ($Recreate -and (Test-Path $venvDir)) {
        Write-Step "Removing $venvDir (-Recreate)"
        Remove-Item $venvDir -Recurse -Force
    }

    if (-not (Test-Path $venvPython)) {
        $basePython = Find-BasePython
        if (-not $basePython) {
            throw "Python $pythonVersion not found (tried py -$pythonVersion, python$pythonVersion, python, python3). " +
                  "Install it - on Windows: winget install Python.Python.$pythonVersion - then re-run."
        }
        Write-Step "Creating .venv from $basePython"
        Invoke-Checked $basePython -m venv $venvDir
    }

    $venvVersion = & $venvPython -c 'import sys; print(sys.version.split()[0])'
    if ($LASTEXITCODE -ne 0 -or $venvVersion -notlike "$pythonVersion.*") {
        throw ".venv runs Python '$venvVersion' but the repo pins $pythonVersion.x (or .venv is broken). Re-run with -Recreate."
    }

    # pip is slow even when there's nothing to do, so skip it unless
    # requirements.txt changed since the hash recorded at the last install.
    $requirementsHash = (Get-FileHash $requirements -Algorithm SHA256).Hash
    $installedHash = (Test-Path $stampFile) ? (Get-Content $stampFile -Raw).Trim() : ''
    if ($Force -or $requirementsHash -ne $installedHash) {
        Write-Step 'Installing requirements.txt into .venv'
        Invoke-Checked $venvPython -m pip install --disable-pip-version-check -r $requirements
        Set-Content $stampFile $requirementsHash
    } else {
        Write-Step 'requirements.txt unchanged since last install (-Force reinstalls)'
    }

    # Browsers live in Playwright's per-user cache (%LOCALAPPDATA%\ms-playwright
    # on Windows), shared across venvs; this is a quick no-op when present.
    Write-Step "Ensuring Playwright browsers: $($browsers -join ', ')"
    Invoke-Checked $venvPython -m playwright install @browsers

    Write-Step 'Smoke test: headless Chromium opens about:blank'
    $smokeTest = @'
import sys
from importlib.metadata import version
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    browser.new_page().goto('about:blank')
    playwright_version = version('playwright')
    print(f'    python {sys.version.split()[0]} | playwright {playwright_version} | chromium {browser.version}')
    browser.close()
'@
    Invoke-Checked $venvPython -c $smokeTest

    # Activate.ps1 sets $env:PATH/$env:VIRTUAL_ENV (process-wide) and defines
    # global `deactivate`/`prompt` functions, so activation outlives this scope.
    # It predates StrictMode-clean code, so run it with StrictMode off.
    Set-StrictMode -Off
    & (Join-Path $binDir 'Activate.ps1')
    Write-Host "==> Ready: .venv is active. Leave it with: deactivate" -ForegroundColor Green
}
