# levelset-01 — ADR-0002: the stack pins the first evals were built on

**Status:** DRAFT
**Requested:** 2026-11-01. Drafted at `8468a63` by
`/zmh-producer:backlog-plan-gen`. Source: the CD's first-eval level-set
("adopt current practice", DONE.md 2026-11-01; TODO.md § Next "Level-set
ADR").

**Scope:** a new `.claude/adr/0002-stack-pins.md`; one-line edits to
`CLAUDE.md`, `.claude/standards/coding.md`, `.claude/standards/review.md`
and a comment in `01-setup-env.ps1`. Docs only: no version, code or
behaviour changes.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

The stack the evals already use is written down once, in ADR-0002, and
the scaffold's `<FILL-IN>` markers for it point there. The markers the
level-set didn't decide stay, narrowed to what's still open.

## Context

- **The level-set** (DONE.md, 2026-11-01), as the CD decided it:
  - (a) Python 3.12 in a repo-root `.venv`, `playwright==1.64.1`;
  - (b) no multi-user runner for now (decided 2026-10-31);
  - (c) playwright.dev only for 1-user record/codegen and single replays,
    a local test site for anything more;
  - (d) codegen-recorded scripts, as Eval 01 (`--target python-async`);
  - (e) the file contract is ADR-0001's.
- **What's in use, verified at `8468a63`:**
  - `requirements.txt`: `playwright==1.64.1`, `pytest==9.2.0`, with the
    comment that a trace opens only in a viewer at least as new as its
    recorder;
  - `01-setup-env.ps1` :92 pins `$pythonVersion = '3.12'` and refuses a
    venv of another minor version (:155–156); it installs `chromium` only
    (:93);
  - the repo's `.venv` runs Python 3.12.1 with Playwright 1.64.1, and
    case 02's `grading/capture.toml` records `python = "3.12.1"`,
    `playwright = "1.64.1"`;
  - Eval 01's reference launches `playwright.chromium.launch(headless=False)`
    (bundled Chromium, no channel);
  - `README.md` § Record, Replay, Create Eval holds the codegen command
    Eval 01 was recorded with.
- **The markers** (`git grep -n "FILL-IN\|ADR pending"`):
  - `CLAUDE.md` :39–40 (§ Project pins, the stack pin) and :159–160
    (§ Tech stack, the codegen workflow);
  - `.claude/standards/coding.md` :12–13 (§ Language: the Python version
    and a lint/type pin) and :77–78 (the remaining Playwright API pins);
  - `.claude/standards/review.md` :21–23 (item 3, the version and API
    pins);
  - `01-setup-env.ps1` :92 ("ADR pending").
- **Not decided at the level-set, so not resolved here:** a lint or
  type-check pin, whether every eval must use the async API, and the
  browser channel. `coding.md` :77–78 is left exactly as it is.
- No version changes, so CLAUDE.md's "cross-check any version claim
  against two sources" rule has nothing to check.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`,
2026-11-01).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | Write ADR-0002 verbatim; apply the six exact edits | docs | haiku | low | every byte is in this plan; passes the haiku checklist |

- **Ordering / dependencies:** one task, two commits. Parallel-safe: n/a.
- **Files owned:** `.claude/adr/0002-stack-pins.md` (new), `CLAUDE.md`,
  `.claude/standards/coding.md`, `.claude/standards/review.md`,
  `01-setup-env.ps1` (line 92 only).
- **Validation per task:**
  - `.\.venv\Scripts\python.exe -m pytest` exits 0 with the baseline count
    (1266 passed, 11 skipped at `8468a63`; re-read it in the worktree).
    Check `$LASTEXITCODE` unpiped and paste the summary line.
  - `git grep -n "FILL-IN" -- CLAUDE.md .claude/standards/coding.md
    .claude/standards/review.md` prints exactly three lines: `coding.md`
    :12 (the lint/type pin), `coding.md` :77 (the API pins) and
    `review.md` :23 (the API pins). Paste it.
  - `git grep -n "ADR pending" -- 01-setup-env.ps1` prints nothing.
  - `.\01-setup-env.ps1 -h` still prints its usage.
  - `git diff --check` is clean.
- **Tier audit (required):** all six checklist items hold. The targets
  are exact (file, line and old text), the content is verbatim, the done
  checks are commands, nothing is named or traded off, the gotchas are
  listed, and nothing is secret or outward-facing. Two commits in one
  spawn, because each alone is below the ~15-minute floor.
- **Decision defaults:**
  - **ADR number and name:** `0002-stack-pins.md` (ADR-0001's naming:
    number, then a short noun phrase).
  - **Status `Accepted`, deciders "CD":** the CD decided it in backlog
    refinement; the Lead Engineer only writes it down.
  - **`coding.md` :77–78 stays as it is:** the level-set recorded how
    scripts are recorded (async), not a rule for every eval.
  - **`README.md` is not edited.** Its Record, Replay, Create Eval section
    is the CD's own walkthrough; the ADR cites it.
  - If an edit's old text doesn't match exactly, stop and report it. Don't
    rewrite the surrounding lines.
- **Embedded-content QA (required):** every old text below was copied
  from the file at `8468a63`, and every claim in the ADR was checked
  against § Context's evidence. The FILL-IN count after the edits is 3,
  re-derived: 5 lines today (`CLAUDE.md` :39 and :159, `coding.md` :12
  and :77, `review.md` :21), minus CLAUDE.md's two. Coding.md's :12 and
  review.md's marker are each replaced by a narrower one, so they still
  count. Edit 4 keeps `coding.md`'s line count; edit 5 adds one line to
  `review.md`.
- **Escalation triggers:** none expected. An old text that doesn't match
  is reported, not guessed.
- **Playtest:** none (docs only).
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** two commits.
  1. `docs(adr): record the stack pins as ADR-0002` (the ADR file only).
  2. `docs(claude): point the stack pins at ADR-0002` (the five edited
     files).

## Steps

1. **Write `.claude/adr/0002-stack-pins.md`** exactly as in § ADR-0002
   (LF endings, a final newline). Commit 1.
2. **Apply § Edits** with the Edit tool, one edit per block, old text
   exactly as shown. Run the validation checks. Commit 2.

## ADR-0002

`.claude/adr/0002-stack-pins.md`, verbatim:

```markdown
# ADR-0002 — Python 3.12, Playwright 1.64.1 and codegen-recorded scripts

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** CD (adopted current practice at the first-eval level-set)

## Context

The scaffold left the stack's pins to "the first-eval level-set":
CLAUDE.md § Project pins and § Tech stack, `.claude/standards/coding.md`
§ Language and `.claude/standards/review.md` item 3 each held a
`<FILL-IN>` for them, and `01-setup-env.ps1` pinned Python 3.12 with an
"ADR pending" comment. Eval 01 and the five generated cases were built,
captured and graded with the versions below, so the level-set (DONE.md,
2026-11-01) adopted what is in use instead of choosing anew. No version
changes here.

## Decision

We will keep the stack the evals were built on:

- **Python 3.12**, in a venv at the repo root (`.venv\`), built by
  `.\01-setup-env.ps1` from `requirements.txt`. The script refuses a venv
  of any other minor version. The venv is never committed, and
  Playwright's browsers live in the per-user cache
  (`%LOCALAPPDATA%\ms-playwright`) that every venv shares.
- **`playwright==1.64.1`**, pinned exactly in `requirements.txt`: a trace
  opens only in a viewer at least as new as the Playwright that recorded
  it. `pytest==9.2.0` is pinned the same way for the gate.
- **Targets:** playwright.dev only for 1-user record/codegen and single
  replays. Anything above 1 user × 1 iteration runs against a local test
  site (CLAUDE.md § Project pins). No multi-user runner for now (CD,
  2026-10-31).
- **Scripts are recorded with codegen**, as Eval 01's was:
  `playwright codegen --target python-async --viewport-size "1280,720"
  -o <file> <url>`, with tracing then added around the journey by hand
  (`README.md` § Record, Replay, Create Eval). Generated cases derive from
  a recorded script by recipe (`grading/recipe.toml`,
  `.\10-make-case.ps1`; ADR-0001's case contract).

## Consequences

- The pins are written down once. CLAUDE.md, the coding and review
  standards and `01-setup-env.ps1` point here.
- Fixtures stay reproducible: each case's `grading/capture.toml` records
  the Python and Playwright versions it was captured with.
- A version bump is a superseding ADR: cross-check the release against
  two independent sources first (CLAUDE.md § Project pins), then recapture
  every case whose trace or output would change.
- Not decided here (TODO.md § Later): a lint or type-check pin, whether
  every eval must use the async API, and the browser channel. Today's
  scripts use the async API and Playwright's bundled Chromium, as codegen
  and `01-setup-env.ps1` set them up.
- Revisit when a new eval needs another Python or Playwright release, or
  the local test site needs another browser.
```

## Edits

1. **`CLAUDE.md` § Project pins** (lines 39–40). Old:
   ```
     first). `<FILL-IN: pin via an ADR at the first-eval level-set — Python
     version (leaning 3.12), venv location, Playwright version, and why>`.
   ```
   New:
   ```
     first). Python 3.12 in `.venv\` (built by `.\01-setup-env.ps1`) and
     `playwright==1.64.1`, recorded with codegen: ADR-0002.
   ```
2. **`CLAUDE.md` § Tech stack** (lines 159–160). Old:
   ```
   (CD, 2026-10-31). `<FILL-IN: the record+codegen workflow — decided at the
   first-eval level-set>`.
   ```
   New:
   ```
   (CD, 2026-10-31). Scripts are recorded with `playwright codegen --target
   python-async` against playwright.dev, and cases are derived from them by
   recipe (`.\10-make-case.ps1`): ADR-0002.
   ```
3. **`CLAUDE.md` § .claude/ layout** (line 118). Old:
   ```
     adr/          architecture decision records (ADR-0001: script-fix rubric)
   ```
   New:
   ```
     adr/          architecture decision records (ADR-0001: script-fix rubric;
                   ADR-0002: stack pins)
   ```
4. **`.claude/standards/coding.md` § Language** (lines 12–13). Old:
   ```
   - `<FILL-IN: Python version + lint/type pin, decided at the first-eval
     level-set, e.g. "Python 3.12, type hints on tooling, ruff clean">`.
   ```
   New:
   ```
   - Python 3.12 (ADR-0002). `<FILL-IN: lint/type pin, e.g. "type hints on
     tooling, ruff clean"; the level-set left it open>`.
   ```
5. **`.claude/standards/review.md` item 3** (lines 21–23). Old:
   ```
   3. **Pin compliance** — no load against public sites; `<FILL-IN:
      static-reviewer checklist — Python/Playwright version and API pins once
      the level-set decides them>`.
   ```
   New:
   ```
   3. **Pin compliance** — no load against public sites; Python 3.12 and
      `playwright==1.64.1` change only by a superseding ADR (ADR-0002);
      `<FILL-IN: Playwright API pins (sync vs async, browser channel) once
      decided>`.
   ```
6. **`01-setup-env.ps1`** line 92. Old:
   ```
       $pythonVersion = '3.12'            # repo pin; ADR pending (TODO.md § Needs Zack)
   ```
   New:
   ```
       $pythonVersion = '3.12'            # repo pin (ADR-0002)
   ```

After edit 5, review.md's marker is on line 23 (the validation check's
`review.md :23`), and the file is one line longer. Edit 3 makes
`CLAUDE.md` one line longer too. The Edit tool matches by text, so the
order of the edits doesn't matter; the line numbers above are today's.

## Wrap-up backlog edits (the overseer)

At wrap-up, with the run's DONE.md entry:
- **TODO.md § Next:** the "Level-set ADR" entry moves to DONE.md.
- **TODO.md § Later, "Complete the scaffold's `<FILL-IN>` markers":**
  - the header's parenthesis ends `the level-set's decided half is
    ADR-0002 (levelset-01)` instead of naming the § Next item;
  - the `CLAUDE.md` row becomes `[x]`: `stack/version pin and codegen
    workflow (ADR-0002)`, keeping its "Done:" list;
  - the `coding.md` row: `Python version done (ADR-0002); open: lint/type
    pin and the remaining Playwright API pins (sync vs async, browser
    channel; waits + transaction timers done)`;
  - the `review.md` row: `static-reviewer API pins (the version half is
    done: ADR-0002)`.

## Gotchas / bindings

- **Exact old text only.** The edits replace whole lines; the Edit tool
  must match them byte for byte, including the two-space indents in
  `CLAUDE.md` and the em dash (`—`) in edits 1, 2 and 5.
- **`01-setup-env.ps1`:** change the comment only. The line keeps its
  leading four spaces and the spaces before `#`. Don't touch its help
  block (the Script SOP generates usage from it).
- **LF endings, UTF-8 without BOM:** all five files are LF today. The Edit
  tool keeps them; `test_line_endings.py` fails on a stray CR or control
  byte.
- **Don't touch `README.md`**, any eval, `requirements.txt`, ADR-0001, or
  `coding.md` :77–78.
- **The worktree needs its own venv:** run `.\01-setup-env.ps1` there
  before the gate (`.claude/zmh/producer.md` § Environment).
- **Git:** stage named files only (never `git add -A`). In the worktree,
  run git as plain separate commands, put `git -C <worktree>` in the
  implementer prompt, and keep both trailers adjacent in the message's
  last paragraph.
- **Public repo:** no product or work-internal names. Run
  `.claude\scripts\check-private-names.ps1 -Message '<msg>'` before each
  commit (exit 0 is clean).

## Validation

- The project validation procedure: the static pre-pass on the changed
  files (`eval-static-reviewer`), then `.\.venv\Scripts\python.exe -m
  pytest` green.
- The FILL-IN and "ADR pending" checks in § Implementation guidance.
- No dependency change: `requirements.txt` is untouched.

## Follow-ups

- The three open markers (lint/type pin, the Playwright API pins) stay on
  TODO.md § Later's checklist until the CD decides them.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/levelset-01.adr.md
```
