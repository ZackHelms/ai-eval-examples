# Coding Standards

Applies to repo tooling (setup, capture, and check scripts) and to
`evals/*/grading/` reference fixes. Stack: Markdown eval specs + per-eval
Python/Playwright(/Locust) fixtures, pwsh repo scripts.

**Never applies to `evals/*/inputs/`** — those are deliberately flawed;
"cleaning them up" outside the eval's own authoring destroys the eval.

## Language

- `<FILL-IN: Python version + lint/type pin, decided at the first-eval
  level-set, e.g. "Python 3.12, type hints on tooling, ruff clean">`.
- No implicit escape hatches (bare `except:`, swallowed errors, untyped
  catch-alls) without a comment justifying the one safe boundary.
- Prefer pure functions in tooling; return new values rather than mutate
  inputs.

## Scripts

- pwsh scripts: `Set-StrictMode -Version Latest` and
  `$ErrorActionPreference = 'Stop'` at the top; check native exit codes
  (`$LASTEXITCODE`) explicitly. A script meant to be dot-sourced runs its
  body in `& { … }` so those settings don't leak into the caller's session.
- **Usage (CLAUDE.md § Script SOP):** `-h` and `--help` print usage from
  the script's own help text; unknown arguments fail, naming the argument
  and pointing at `-h`.
  - **pwsh:** comment-based help (`.SYNOPSIS`, `.DESCRIPTION`, one
    `.PARAMETER` per parameter, `.EXAMPLE`s) +
    `[Alias('h')][switch]$Help` + a
    `[Parameter(ValueFromRemainingArguments, DontShow)][string[]]$UnknownArgs`
    catch-all, because interactive pwsh passes `--help` as a plain string,
    not a parameter name. On `$Help -or $UnknownArgs -contains '--help'`,
    run `Get-Help $PSCommandPath -Detailed` and `return`; on any other
    `$UnknownArgs`, `throw`. Keep a blank line between `#Requires` and the
    `<# … #>` help block: a comment touching the block hides it from
    `Get-Help`. Reference: `01-setup-env.ps1`.
  - **Python:** `argparse` (it provides `-h`/`--help` and rejects unknown
    arguments by default); put the usage text in `description`/`help=`.

## Platform pins (the static reviewer flags these)

- No multi-user/load runs against third-party public sites — anything
  above 1 user × 1 iteration targets localhost (CLAUDE.md § Project pins).
- `<FILL-IN: Playwright/Locust API pins — e.g. sync vs async API, locust-
  plugins user class, browser channel; one bullet per pin, quotable
  verbatim by the static reviewer.>`

## Eval hygiene

- Reference fixes are the **minimal** correct fix to the broken input —
  they show what a good answer looks like, not a rewrite.
- No hard-coded absolute paths in prompts, inputs, or tooling; resolve
  relative to the eval folder or repo root.
- Tunables (user counts, iterations, timeouts, target URLs) are named,
  documented constants or CLI parameters, never loose literals.

## Errors & comments

Throw/raise with actionable messages naming the offending value. Validate
external data at the boundary, trust it internally; never silently continue
on corrupted state. Comments explain *why* (invariants, rationale, units),
not *what* — and never inside `inputs/` in a way that hints at the bug.
