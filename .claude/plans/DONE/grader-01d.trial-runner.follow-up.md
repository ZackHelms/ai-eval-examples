# grader-01d — follow-up

Oversee run of `grader-01d.trial-runner.md`, 2026-11-01.

## Blocked — needs you

Nothing blocked.

## Decisions made on your behalf — review

1. **The pwsh alias rule was narrowed (a preflight correction).** The plan
   rejected any `pwsh` "under `\WindowsApps\`". This host's real pwsh,
   `(Get-Process -Id $PID).Path`, is
   `C:\Program Files\WindowsApps\Microsoft.PowerShell_…\pwsh.exe` (a store
   install), and it's what Eval 01's runs 10–12 used. The alias that
   breaks the PowerShell tool is the per-user one under
   `%LOCALAPPDATA%\Microsoft\WindowsApps\`. So the runner rejects only
   paths containing `\Microsoft\WindowsApps\`, for both `--pwsh` and the
   `shutil.which` fallback. `trial-runs.md` gotcha 3 now says so.
2. **`20-run-trials.ps1` follows `10-make-case.ps1`, not
   `30-grade-trials.ps1`.** Usage errors exit 2 through `Stop-Usage`, and
   `-Case`/`-TrialsRoot` are resolved against your directory before the
   script changes directory. `30-grade-trials.ps1` still has both known
   bugs (grader-01c follow-up; TODO.md lists them under grader-01bb).
3. **Smaller preflight drift:** `CLAUDE.md`'s trial-run loop paragraph
   was at lines 80–83, not 81–84. Task 6's done-check grep was scoped to
   `CLAUDE.md` and `.claude/skills`, so the plan's own quote can't match.
4. **`--permission-mode default` stays.** Claude Code 2.1.314's `--help`
   lists only `acceptEdits, auto, bypassPermissions, manual, dontAsk,
   plan`, but the live self-test's `init` line shows
   `permissionMode: default`. The plan's switch to `manual` wasn't needed;
   the mode is `run.PERMISSION_MODE`.
5. **Run numbering also counts `<NN>-run<N>.stderr.txt`.** The launcher
   writes it beside the log, so a leftover one must never be overwritten
   either. `check_free` checks the folder, the log, the sidecar and the
   stderr file.
6. **What a batch prints and when it stops:**
   - The sidecar is written after every launched trial, a harness problem
     included.
   - The first harness problem prints one `HARNESS=` line and stops (exit 1).
   - `NEXT=` grades every launched run, the broken one included, since
     the grader marks it invalid itself. `-Case` is printed repo-relative
     (`evals\<slug>`) when the case is inside the repo, and `-TrialsRoot`
     is added only for a non-default root.
7. **Usage-error rules (the agents' calls, accepted):**
   - `--self-test` refuses `--case`, `--count`, `--runs` and `--dry-run`.
   - `run_trials` refuses duplicate runs, runs below 1 and a timeout below
     1 before launching anything.
   - The self-test treats a `MultiEdit` denial like an `Edit` or `Write`
     one.
8. **The sidecar in the grader:**
   - Extra keys in a sidecar are ignored, and so is its `model`: the model
     always comes from the transcript.
   - An empty string counts as a valid value.
   - A run with a corrupt sidecar is `invalid` and records the `-Effort`,
     `-Context` and `-Tools` values.
   - The help for `grade --effort/--context/--tools`, and for
     `30-grade-trials.ps1`'s `-Effort`/`-Context`/`-Tools`, now says these
     apply only to runs without a sidecar. The plan didn't list these
     help-text edits, but they follow from the change.
9. **Task 5 was run by the overseer itself.** It is a single command:
   `.\20-run-trials.ps1 -SelfTest`. The self-test passed first time, with
   Claude Code 2.1.314 and `claude-haiku-5-5`, for $0.0025:
   - PowerShell `Get-Location`, Bash `cd inputs && ls` and the Edit all
     succeeded;
   - there were no denials.

   The folder and log are kept at
   `~\eval-trials\selftest-20261101-100532*`.
10. **The static pre-pass passed with 0 Blockers and 2 Warnings**, both
    accepted:
    - **The sidecar names the case slug** (`"case"`) beside the trial
      folders. It's written after the trial ends, the slugs are generic,
      and earlier runs' full stream logs already sit in that folder. The
      trial folder itself holds only `prompt.md` and `inputs/`.
    - **The reviewer's sandbox couldn't run the private-names check.**
      The overseer ran it with `-All` before the merge.
11. **No routing-rule change.** Each lesson from this run has one
    observation, and the damping rules need two:
    - sonnet docs: escape bytes from a heredoc;
    - task 5: a one-command live check that a cheaper tier, or the
      overseer, can run.

## Deferred / discovered follow-ups

1. **The trial's tool list is wider than "edit-only" (your decision).**
   The self-test's `init` line lists every built-in tool the subject has,
   including `Task`, `WebSearch`, `Monitor`, `Cron*`, `RemoteTrigger`,
   `PushNotification`, `SendMessage`, `Skill` and `NotebookEdit`.
   - Headless mode denies only what needs approval, so a tool that needs
     none isn't covered by the allow rules.
   - Eval 01's 10 headless runs used only Read, Grep, Bash, PowerShell and
     Edit, so the gap hasn't been used yet.
   - The option: pass `--disallowedTools` for everything except Read,
     Glob, Grep, Edit, Write, Bash and PowerShell, and record that in the
     tool profile.

   This changes the subject's profile, so it's in TODO.md § Needs Zack.
2. **The gate can't see control characters.** Task 6's first commit had
   four bytes 0x10/0x18 in `trial-runs.md`. A non-raw Python heredoc read
   `\20` and `\30` as octal escapes. Pytest was green, and the overseer
   caught it reading the diff with `cat -A`; the commit was amended
   before the merge.
   - The fix: `test_line_endings.py` could also fail on bytes below 0x20,
     other than tab and LF, in tracked text files.
   - This is small hardening, so it's listed with grader-01bb's other
     not-yet-planned items in TODO.md.
3. **A race only:** if a trial folder appears between `check_free` and the
   launch, `prepare_trial`'s ValueError surfaces as a usage error after
   the earlier trials ran. That is negligible with one runner at a time.
4. **Context bundles** stay the plan's own follow-up: a launch that gives
   context files despite `--safe-mode`, recording the bundle's hash in
   the sidecar. Do it when the first context experiment is planned.

No follow-up plan was drafted: item 2 is too small for a run of its own,
and items 1 and 4 need your decisions.
