#Requires -Version 7.0

<#
.SYNOPSIS
    Check that no private name appears in the staged change, a commit message
    or (with -All) anywhere in the tracked files and history.

.DESCRIPTION
    The repo is public (CLAUDE.md, Project pins section, "Generic content only"), so
    certain names must never reach a commit. Run this before each commit:

        .claude\scripts\check-private-names.ps1 -Message "<commit message>"

    The names live in a gitignored local list, one name per line; blank lines
    and lines starting with # are ignored. Matching is whole-word and
    case-insensitive: the .NET regex \b<escaped name>\b, so "zorblaxes" does
    not hit the name "zorblax". Names are numbered from 1, counting names only.

    The list is found, in order: -ListPath; <repo>\.claude\private-names.local.txt;
    the same path in the main checkout (the parent folder of
    `git rev-parse --git-common-dir`), so a `git worktree add` worktree reads
    the main checkout's list. No list, or a list with no names, is an error:
    the check never passes silently.

    Default scope: the staged diff's added lines, the staged paths, and the
    -Message text when given. -All adds every tracked file and path
    (`git grep`), every commit message and every commit whose diff adds or
    removes a matching line, on all refs. The repo is the current directory's
    repo, not the script's folder.

    Output is `PRIVATE_NAMES=clean` or `PRIVATE_NAMES=hit`, then one line per
    hit: `HIT <scope> <location> name #<n>`. A name is never printed, only its
    list number. Scopes: staged, staged-path, message, file, path,
    commit-message, commit-diff. Locations: path:line, path, -Message, or a
    short commit hash. A path that itself contains a name is shown with that
    part masked as <#n>.

    Exit codes: 0 clean, 1 at least one hit, 2 usage or setup error (unknown
    argument, no list, empty list, not a git repository, a git command
    failed). A hit in history is reported, never rewritten: see
    .claude\standards\commit.md. Run the script; don't dot-source it (it exits
    with the result code). Needs git and pwsh 7.

.PARAMETER Message
    A commit message to check as well (use the message you are about to commit).

.PARAMETER All
    Also sweep every tracked file and path, every commit message, and every
    commit diff on all refs.

.PARAMETER ListPath
    Use this private-names list instead of looking one up.

.PARAMETER Help
    Print this usage and exit. Also: -h, --help, or pwsh's native -?.

.PARAMETER UnknownArgs
    Not for direct use: collects --help and rejects any unrecognized argument.

.EXAMPLE
    .\.claude\scripts\check-private-names.ps1 -Message "feat(x): add y"
    Check the staged change and the message; exit 0 means clean.

.EXAMPLE
    .\.claude\scripts\check-private-names.ps1 -All
    Sweep every tracked file and the whole history.

.EXAMPLE
    .\.claude\scripts\check-private-names.ps1 -ListPath D:\somewhere\names.txt
    Check the staged change against an explicit list.
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [string]$Message,
    [switch]$All,
    [string]$ListPath,
    [Alias('h')]
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments, DontShow)]
    [string[]]$UnknownArgs
)

$scriptName = Split-Path -Leaf $PSCommandPath

# Interactive pwsh passes `--help` through as a plain string rather than a
# parameter name, so it arrives in $UnknownArgs; anything else there is a typo.
if ($Help -or $UnknownArgs -contains '--help') {
    Get-Help $PSCommandPath -Detailed
    exit 0
}
if ($UnknownArgs) {
    # Not `throw`: under `pwsh -File` an uncaught throw exits 1, which means "hit".
    [Console]::Error.WriteLine("Unknown argument(s): $UnknownArgs. Run .\$scriptName -h for usage.")
    exit 2
}

# The work runs in a child scope so StrictMode, $ErrorActionPreference and the
# helper functions don't leak into your session. $PSBoundParameters inside the
# block is the block's own, so capture it here.
$messageGiven = $PSBoundParameters.ContainsKey('Message')
$script:exitCode = 2
& {
    Set-StrictMode -Version Latest
    $ErrorActionPreference = 'Stop'

    $listRelPath = '.claude/private-names.local.txt'
    $utf8        = [Text.UTF8Encoding]::new($false)

    # Setup and usage failures: the message must never contain a name.
    function Fail([string]$text) {
        throw [System.ApplicationException]::new($text)
    }

    # Runs git, hides its stderr (it could echo a pattern), and checks the exit
    # code. $Label names the step in the error; the arguments are never printed.
    # Once $top is known every call runs from the repo root: `git grep` and
    # `git ls-files` otherwise cover only the current subdirectory, and print
    # paths relative to it.
    $top = $null
    function Invoke-Git([string]$Label, [string[]]$GitArgs, [int[]]$OkCodes = @(0)) {
        $root = $top ? @('-C', $top) : @()
        $out = & git @root -c core.quotepath=off @GitArgs 2>$null
        $code = $LASTEXITCODE
        if ($code -notin $OkCodes) { Fail "git failed ($Label, exit $code)." }
        if ($null -ne $out) { $out }
    }

    # ERE-escape a name for `git grep -E` / `git log -G`.
    function ConvertTo-EreLiteral([string]$name) {
        [regex]::Replace($name, '([\\.^$*+?()\[\]{}|])', '\$1')
    }

    # Parse a -U0 patch into changed lines: Side (+ or -), Path, Line, Text.
    # Hunk-header counts decide what is content, so an added line that starts
    # with "++" is not mistaken for a file header.
    function Read-Patch([string[]]$lines) {
        $oldPath = $null; $newPath = $null
        $oldLeft = 0; $newLeft = 0; $oldLine = 0; $newLine = 0
        foreach ($l in $lines) {
            if ($oldLeft -gt 0 -or $newLeft -gt 0) {
                if ($l.StartsWith('-') -and $oldLeft -gt 0) {
                    $oldLeft--
                    [pscustomobject]@{ Side = '-'; Path = ($newPath ?? $oldPath); Line = $oldLine; Text = $l.Substring(1) }
                    $oldLine++
                    continue
                }
                if ($l.StartsWith('+') -and $newLeft -gt 0) {
                    $newLeft--
                    [pscustomobject]@{ Side = '+'; Path = ($newPath ?? $oldPath); Line = $newLine; Text = $l.Substring(1) }
                    $newLine++
                    continue
                }
                if ($l.StartsWith('\')) { continue }
            }
            $m = [regex]::Match($l, '^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@')
            if ($m.Success) {
                $oldLine = [int]$m.Groups[1].Value
                $oldLeft = $m.Groups[2].Success ? [int]$m.Groups[2].Value : 1
                $newLine = [int]$m.Groups[3].Value
                $newLeft = $m.Groups[4].Success ? [int]$m.Groups[4].Value : 1
            } elseif ($l.StartsWith('diff ')) {
                $oldPath = $null; $newPath = $null
            } elseif ($l.StartsWith('--- ')) {
                $p = $l.Substring(4).TrimEnd("`t")
                $oldPath = ($p -eq '/dev/null') ? $null : ($p -replace '^a/', '')
            } elseif ($l.StartsWith('+++ ')) {
                $p = $l.Substring(4).TrimEnd("`t")
                $newPath = ($p -eq '/dev/null') ? $null : ($p -replace '^b/', '')
            }
        }
    }

    $diffFlags = @('--no-color', '--no-ext-diff', '--no-textconv', '--no-renames',
                   '--src-prefix=a/', '--dst-prefix=b/', '-U0')

    $previousConsoleEncoding = [Console]::OutputEncoding
    $previousOutputEncoding  = $global:OutputEncoding
    $grepPatternFile = $null
    try {
        # Decode git's UTF-8 output correctly. Setting the console encoding can
        # fail when there is no console attached; the pipe decoding then
        # already follows the host's default.
        try { [Console]::OutputEncoding = $utf8 } catch { }
        $global:OutputEncoding = $utf8

        # --- The repo and the list -----------------------------------------
        $top = (@(& git rev-parse --show-toplevel 2>$null) | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0 -or -not $top) {
            Fail "Not inside a git repository. Run .\$scriptName -h for usage."
        }
        $commonDir = (@(Invoke-Git 'rev-parse common dir' @('rev-parse', '--path-format=absolute', '--git-common-dir')) | Select-Object -First 1)
        $mainTop   = Split-Path -Parent $commonDir
        $mainList  = Join-Path $mainTop $listRelPath

        $list = $null
        if ($ListPath) {
            if (-not (Test-Path -LiteralPath $ListPath -PathType Leaf)) {
                Fail "The -ListPath file was not found: $ListPath"
            }
            $list = $ListPath
        } else {
            foreach ($candidate in @((Join-Path $top $listRelPath), $mainList)) {
                if (Test-Path -LiteralPath $candidate -PathType Leaf) { $list = $candidate; break }
            }
        }
        if (-not $list) {
            Fail ("No private-names list found. Create $mainList (one name per line; " +
                  "blank lines and # comments are ignored), or pass -ListPath.")
        }

        $names = @([IO.File]::ReadAllLines($list, $utf8) |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ -and -not $_.StartsWith('#') })
        if ($names.Count -eq 0) {
            Fail "The private-names list at $list has no names (blank lines and # comments don't count)."
        }

        # One matcher for every scope: whole-word, case-insensitive. git is only
        # used to find candidates; this confirms and numbers each hit.
        $matchers = @($names | ForEach-Object {
            [regex]::new('\b' + [regex]::Escape($_) + '\b', [Text.RegularExpressions.RegexOptions]::IgnoreCase)
        })

        $hits = [System.Collections.Generic.List[string]]::new()
        $seen = [System.Collections.Generic.HashSet[string]]::new()
        function Add-Hit([string]$scope, [string]$location, [int]$number) {
            # A path can itself contain a name (that is a leak too), so mask any
            # occurrence, even inside a longer word, as <#n> before printing.
            for ($i = 0; $i -lt $names.Count; $i++) {
                $location = [regex]::Replace($location, [regex]::Escape($names[$i]), "<#$($i + 1)>",
                    [Text.RegularExpressions.RegexOptions]::IgnoreCase)
            }
            $line = "HIT $scope $location name #$number"
            if ($seen.Add($line)) { $hits.Add($line) }
        }
        # Report which names occur in $text, one hit per name.
        function Test-Text([string]$scope, [string]$location, [string]$text) {
            for ($i = 0; $i -lt $matchers.Count; $i++) {
                if ($matchers[$i].IsMatch($text)) { Add-Hit $scope $location ($i + 1) }
            }
        }

        # --- Default scope: staged diff, staged paths, -Message -------------
        $staged = @(Read-Patch @(Invoke-Git 'diff --cached' (@('diff', '--cached') + $diffFlags)))
        foreach ($c in ($staged | Where-Object { $_.Side -eq '+' })) {
            Test-Text 'staged' "$($c.Path):$($c.Line)" $c.Text
        }
        $stagedNames = (@(Invoke-Git 'diff --cached --name-only' @('diff', '--cached', '--name-only', '-z', '--no-renames', '--diff-filter=d')) -join "`n") -split "`0"
        foreach ($p in $stagedNames) {
            if ($p) { Test-Text 'staged-path' $p $p }
        }
        if ($messageGiven -and $Message) { Test-Text 'message' '-Message' $Message }

        # --- -All: tracked files, tracked paths, history --------------------
        if ($All) {
            $grepPatternFile = Join-Path ([IO.Path]::GetTempPath()) ("pnames-" + [guid]::NewGuid().ToString('N') + '.txt')
            [IO.File]::WriteAllText($grepPatternFile, (($names | ForEach-Object { ConvertTo-EreLiteral $_ }) -join "`n") + "`n", $utf8)

            # Candidates are substring matches (no -w) so git can't miss what
            # the .NET matcher would accept; exit 1 just means no candidates.
            $grepLines = @(Invoke-Git 'grep' @('grep', '--no-color', '-I', '-n', '-i', '-E', '-f', $grepPatternFile) @(0, 1))
            foreach ($gl in $grepLines) {
                $m = [regex]::Match($gl, '^(?<path>.+?):(?<line>\d+):(?<text>.*)$')
                if ($m.Success) { Test-Text 'file' "$($m.Groups['path'].Value):$($m.Groups['line'].Value)" $m.Groups['text'].Value }
            }

            $trackedPaths = (@(Invoke-Git 'ls-files' @('ls-files', '-z')) -join "`n") -split "`0"
            foreach ($p in $trackedPaths) {
                if ($p) { Test-Text 'path' $p $p }
            }

            # Commit messages: records start with \x01, hash and body split by \x02.
            $log = (@(Invoke-Git 'log messages' @('log', '--all', '--format=%x01%h%x02%B')) -join "`n")
            foreach ($record in ($log -split "`u{01}")) {
                if (-not $record) { continue }
                $parts = $record -split "`u{02}", 2
                if ($parts.Count -eq 2) { Test-Text 'commit-message' $parts[0].Trim() $parts[1] }
            }

            # Commit diffs: -G finds candidate commits; the matcher confirms
            # against the changed lines of each.
            $diffCache = @{}
            for ($i = 0; $i -lt $names.Count; $i++) {
                $candidates = @(Invoke-Git 'log -G' @('log', '--all', '-G', (ConvertTo-EreLiteral $names[$i]), '--regexp-ignore-case', '--format=%h', '--'))
                foreach ($hash in $candidates) {
                    if (-not $hash) { continue }
                    if (-not $diffCache.ContainsKey($hash)) {
                        $diffCache[$hash] = @(Read-Patch @(Invoke-Git 'show' (@('show', '--format=') + $diffFlags + @($hash))))
                    }
                    foreach ($c in $diffCache[$hash]) {
                        if ($matchers[$i].IsMatch($c.Text)) { Add-Hit 'commit-diff' $hash ($i + 1); break }
                    }
                }
            }
        }

        if ($hits.Count -eq 0) {
            'PRIVATE_NAMES=clean'
            $script:exitCode = 0
        } else {
            'PRIVATE_NAMES=hit'
            $hits
            $script:exitCode = 1
        }
    } catch [System.ApplicationException] {
        [Console]::Error.WriteLine($_.Exception.Message)
        $script:exitCode = 2
    } catch {
        # Only the exception type and line are shown: its text could echo input.
        [Console]::Error.WriteLine("Unexpected error ($($_.Exception.GetType().Name)) at line $($_.InvocationInfo.ScriptLineNumber). Run .\$scriptName -h for usage.")
        $script:exitCode = 2
    } finally {
        if ($grepPatternFile -and (Test-Path -LiteralPath $grepPatternFile)) {
            Remove-Item -LiteralPath $grepPatternFile -Force
        }
        try { [Console]::OutputEncoding = $previousConsoleEncoding } catch { }
        $global:OutputEncoding = $previousOutputEncoding
    }
}
exit $exitCode
