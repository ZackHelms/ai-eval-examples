# privnames-01 — a private-names check for commits

**Status:** IMPLEMENTED 2026-10-31 (oversee run, commits `ea0abe6`..`94b3bb4`
plus the wrap-up; see `privnames-01.check-script.follow-up.md`).
**Requested:** 2026-10-31 (refine pass; TODO.md § Next "Private-names
check script"). Drafted by `/zmh-producer:backlog-plan-gen`.
**Scope:**
- New: `.claude/scripts/check-private-names.ps1`,
  `.claude/scripts/README.md`, `tools/tests/test_private_names.py`.
- Changed: `.gitignore`, `.claude/standards/commit.md`,
  `.claude/workflows/plan-oversee-cycle.md`.
- A local, untracked list file in the primary checkout.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

Before each commit, one command says whether the staged diff or the
commit message contains a name that must stay out of this public repo
(CLAUDE.md § Project pins, "Generic content only"):
`.claude\scripts\check-private-names.ps1 -Message "<msg>"`.
- With `-All`, it sweeps every tracked file and the whole history.
- The names live only in a gitignored local list, never in a tracked
  file, the script's output or a commit.

## Context

- Since a leak on 2026-10-30, every commit has been preceded by hand
  greps for a short list of names (case-insensitive, whole words). The
  rule is in `.claude/standards/commit.md` § Rules, "Public repo".
- The names are recorded in the CD's auto-memory, in the file
  `generic-content-only.md` (the user memory folder for this project),
  and nowhere in the repo. **This plan must never write them anywhere
  tracked, and never print them.**
- In an oversee worktree, gitignored files from the primary checkout
  aren't present, so the script finds the list through the main checkout.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`, 2026-10-31).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | The script, the `.gitignore` line, pytest tests | script | sonnet | high | git plumbing, worktree lookup and regex; tests drive pwsh against a temp repo |
| 2 | Wiring: the scripts README, `commit.md`, the oversee workflow, the local list | docs | sonnet | medium | wording is the agent's; the local list is written from memory |

- **Ordering / dependencies:** 1 → 2. Parallel-safe: none.
- **Files owned per task:**
  1. `.claude/scripts/check-private-names.ps1`, `.gitignore`,
     `tools/tests/test_private_names.py`.
  2. `.claude/scripts/README.md`, `.claude/standards/commit.md`,
     `.claude/workflows/plan-oversee-cycle.md`, plus the untracked
     `<primary checkout>\.claude\private-names.local.txt`.
- **Validation per task:**
  - Every task: `.\.venv\Scripts\python.exe -m pytest` exits 0. Check
    `$LASTEXITCODE` unpiped and paste the summary line.
  - Task 1: `-h` prints usage, and `--bogus` fails naming it.
  - Task 2: from the primary checkout, after the merge, `-All` prints
    `PRIVATE_NAMES=clean` (the repo is clean today), and
    `git check-ignore .claude/private-names.local.txt` matches.
- **Tier audit (required):**
  - Task 1 fails haiku checklist item 4 (regex and git-command design).
  - Task 2 fails item 4 (wording) and touches a secret-like local file
    (item 6) → sonnet-medium.
- **Decision defaults:**
  - **Never echo a name.** A hit prints its location and the list entry's
    *number* (`name #2`), never the name or the matched text. The match
    is case-insensitive and whole-word (`\b<name>\b`, regex-escaped).
  - **List lookup order:**
    1. `-ListPath` if given;
    2. else `<repo>\.claude\private-names.local.txt`;
    3. else the same path in the main checkout, found with
       `git rev-parse --path-format=absolute --git-common-dir` (its parent
       folder).

    No list found → exit 2 with a message saying where to create it.
    Never pass silently.
  - **The list format:** one name per line; blank lines and `#` comments
    ignored.
  - **Default scope:** the staged diff's added lines (`git diff --cached
    -U0`, lines starting `+` but not `+++`), plus `-Message` text when
    given.
  - **`-All` scope:**
    - every tracked file (`git grep -I -n -i -w -E -f <temp patterns
      file>`, deleted afterwards);
    - every commit message (`git log --all --format=%H%x00%B%x00`);
    - every commit whose diff adds or removes a matching line
      (`git log --all -G <pattern> --format=%h` per name, with
      `--regexp-ignore-case`).

    Report each hit's commit or path:line.
  - **Exit codes:** 0 clean, 1 at least one hit, 2 usage or setup error.
  - **Output:** `PRIVATE_NAMES=clean|hit`, then one
    `HIT <scope> <location> name #<n>` line per hit.
- **Embedded-content QA (required):**
  - `.gitignore` has 7 lines at `2b9eb1b`; this plan appends a comment and
    `.claude/*.local.*`.
  - `commit.md`'s "Public repo" bullet is at lines 31–36.
- **Escalation triggers:** `-All` finds a hit in history. **Do not
  rewrite history.** Report the commit hashes to the CD in the final
  report (`commit.md` explains why a rewrite can't fully unpublish), and
  finish the rest.
- **Playtest:** none.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task, scope `scripts`
  (task 1) and `claude` (task 2).

## Steps

1. **The script.** Write `.claude/scripts/check-private-names.ps1` per
   § Decision defaults and the Script SOP pattern of `30-grade-trials.ps1`:
   - help block, `PositionalBinding = $false`, unknown arguments rejected;
   - `Set-StrictMode`, `$ErrorActionPreference = 'Stop'`, and every git
     exit code checked.

   Parameters: `-Message <string>`, `-All`, `-ListPath <path>`, `-h`.
   Append to `.gitignore`:

   ```
   # Machine-local files (private-name list, local settings): never committed.
   .claude/*.local.*
   ```

   `tools/tests/test_private_names.py` runs the script with `pwsh -NoProfile -File` against a
   temp git repo in `tmp_path` (`git init`, a user config set with `-c`).
   It uses a temp list of made-up names, e.g. `zorblax`, `quuxcorp`. Cover:
   - a staged hit → exit 1, with the name's number and **not** its text in
     the output;
   - a clean stage → exit 0, `PRIVATE_NAMES=clean`;
   - a substring (`zorblaxes`) → no hit (whole word);
   - a case variant (`ZorBlax`) → hit;
   - a `-Message` hit;
   - `-All` finding a name in an old commit's message and in a removed
     line;
   - a missing list → exit 2;
   - a worktree (`git worktree add`) finding the main checkout's list.

   Skip the module (`pytest.skip`) if `pwsh` isn't on `PATH`.

   Done: pytest green.
2. **Wiring.**
   - **`.claude/scripts/README.md`** (new): one line per script, with what
     it automates and how to invoke it. Cover
     `oversee-ledger-summary.mjs` and this one.
   - **`commit.md`'s "Public repo" bullet:** add "run
     `.claude\scripts\check-private-names.ps1 -Message '<message>'` on the
     staged change before committing; exit 0 is clean".
   - **`plan-oversee-cycle.md` § Gotchas:** add "implementers run the
     private-names check before each commit; from a worktree it reads the
     main checkout's list".
   - **The local list:** write
     `<primary checkout>\.claude\private-names.local.txt` with a
     `# Private names: never commit (see CLAUDE.md § Project pins).`
     header, then the names from the memory file `generic-content-only.md`,
     one per line.
     - Check `git status --short` shows nothing new.
     - Never stage it, never paste it into a prompt for an implementer,
       and never print it.
     - The overseer does this step itself, from the primary checkout.

   Done: § Validation per task.

## Gotchas / bindings

- **Don't leak the names you're protecting:**
  - not in tests (use made-up names);
  - not in output;
  - not in commit messages or the follow-up file;
  - not in a spawn prompt.

  If you need to say which name hit, say its list number.
- **`git grep -f` and `-w` with `-E`:** escape each name for ERE before
  writing the temp patterns file, and delete that file in a `finally`.
- **Git Bash vs pwsh:** the script and tests are pwsh. Tests call
  `pwsh -NoProfile -File <script> …` with `cwd` set to the temp repo, and
  read stdout as UTF-8.
- **Worktree isolation:** in an oversee worktree, run git as plain
  separate commands (no compound commands that name git), and use
  `git -C <worktree>` in every implementer prompt. The tests' own `git`
  calls run in `tmp_path` repos, which is fine.
- **Line endings:** the script and tests are LF (`test_line_endings.py`).
- Stage named files only (never `git add -A`); `.gitignore` is one of
  them.

## Validation

- The project validation procedure: the static pre-pass, then
  `.\.venv\Scripts\python.exe -m pytest` green.
- `-All` is clean on the primary checkout after the merge.
- The local list is ignored and untracked.

## Follow-ups

- A git `pre-commit` hook calling the script. Hooks are per-clone, so
  that's the CD's choice; mention it in the report.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/privnames-01.check-script.md
```
