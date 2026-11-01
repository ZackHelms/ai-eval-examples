# privnames-01 — follow-up

Oversee run of `privnames-01.check-script.md`, 2026-10-31.

## Blocked — needs you

Nothing blocked.

## Decisions made on your behalf — review

1. **Preflight was clean.** `.gitignore` had 7 lines, the `commit.md`
   "Public repo" bullet was at lines 31–36, and `plan-oversee-cycle.md`
   § Gotchas was at line 55, all as the plan said.
2. **Usage errors exit 2, not `throw`.** The Script SOP's pattern throws
   on unknown arguments, but under `pwsh -File` an uncaught throw exits 1,
   which here means "hit". The script prints the error and exits 2 itself.
   The pattern is now in `.claude/standards/coding.md` § Scripts.
3. **Paths count too.** The default scope also checks the staged paths,
   and `-All` checks every tracked path. Any path or location in a HIT line
   has a name masked as `<#n>`, so a path can't echo one.
4. **One matcher.** `git grep` (substring, no `-w`) and `git log -G` only
   find candidates. The .NET `\b<name>\b` case-insensitive matcher
   confirms and numbers every hit, so all scopes agree on what a word is.
5. **`-All` adds to the default scope** (staged change, staged paths,
   `-Message`) instead of replacing it.
6. **The repo is the current directory's repo**, and every git call runs
   from its toplevel. The first version ran `git grep`/`git ls-files`
   from the current directory, so `-All` from a subdirectory missed files.
   Review caught it; it was fixed with two tests.
7. **Where the names came from.** The memory file `generic-content-only.md`
   describes the names but doesn't list them. I took the list from the
   whole-word pattern this session used for its hand greps before earlier
   commits: 4 names. **Check that the list is complete**; add any missing
   name to `.claude/private-names.local.txt` in the primary checkout.
8. **The list was written after the merge.** A worktree-isolated session
   can't write files in the primary checkout. The pre-merge checks used a
   temporary copy in the job's temp folder (deleted at wrap-up). The new
   workflow gotcha says to create the list before a run.
9. **Errors never echo input.** Git's stderr is suppressed, a failed git
   call reports only its step and exit code, and an unexpected exception
   prints only its type and line.

## Deferred / discovered follow-ups

- **A git `pre-commit` hook** calling the script (the plan's Follow-ups).
  Hooks are per-clone, so it's your choice. A two-line
  `.git/hooks/pre-commit` running
  `pwsh -NoProfile -File .claude/scripts/check-private-names.ps1` would
  check every staged change. It can't see the message; that would be a
  `commit-msg` hook.
- **A stray temp file.** If `-All` is cut off mid-run (for example a
  pipeline that stops early), its temp patterns file
  (`%TEMP%\pnames-*.txt`, the escaped names) can survive. It's local-only;
  passing the patterns as `-e` options instead of a file would avoid it.
- **Tier note (candidate, one observation):** task 1 (sonnet-high,
  script) passed its gate first time but missed the cwd scoping of
  `git grep`/`git ls-files`. The overseer's diff review caught it, not a
  test. A plan with a repo-wide git sweep should say "run git from the
  toplevel". That's now a coding standard, so no rubric edit.
