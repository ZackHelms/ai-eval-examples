# grader-01c — cases 02–06, neutral capture, eval-integrity gate

**Status:** IMPLEMENTED 2026-11-01 (oversee run, commits `5305c8d`..`9ce71e8`
plus the wrap-up; see `grader-01c.cases.follow-up.md`).
**Requested:** 2026-10-30 (grader-01 phase C, design approved that day);
drafted 2026-10-31 by `/zmh-producer:backlog-plan-gen`. It bundles two
other backlog items: the eval static reviewer (TODO.md § Needs Zack
AGENT-OPP, approved by the CD 2026-10-31 "in phase C") and the
eval-integrity gate (TODO.md § Next).
**Scope:**
- New: `tools/scriptfix/makecase.py`, `10-make-case.ps1`,
  `.claude/agents/eval-static-reviewer.md`, `tools/tests/test_makecase.py`,
  `tools/tests/test_eval_integrity.py`, and cases
  `evals/02-docs-journey-a/` to `evals/06-docs-journey-e/`.
- Changed: `tools/scriptfix/replay.py` (a `workdir` option),
  `tools/scriptfix/static.py` (the escalate journey rule),
  `tools/scriptfix/__main__.py` (a `make-case` subcommand),
  `tools/tests/test_corpus.py` (escalate cases), `01-setup-env.ps1`
  (`-VenvDir`, `-NoActivate`), and docs.
- Eval 01 doesn't change at all.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

`.\10-make-case.ps1 -Case evals\<slug>` builds a script-fix case from its
`grading/recipe.toml`:
- it cuts the source script to make the reference, and applies the
  recipe's edits to make the broken input;
- it replays both in a neutral folder with a venv outside the repo, so the
  evidence never names the repo;
- it writes `inputs/` (script, `results.txt`, trace), `prompt.md` (the
  shared prompt) and `grading/capture.toml`.

The run also delivers:
- five pilot cases built this way, each with a labeled corpus;
- a pytest eval-integrity gate covering every eval;
- the escalate journey rule the rubric needs for case 06;
- an `eval-static-reviewer` agent for the validation procedure's step 1.

## Context

- Design and the CD's decisions: `.claude/plans/grader-01.global-rubric-design.md`
  (§ Case template, § Pilot); ADR-0001 (the case contract).
- The grader these cases feed: `tools/scriptfix/` (grader-01b,
  `.claude/plans/DONE/grader-01b.deterministic-grader.md`); how it works:
  `.claude/skills/scriptfix-grader.md`.
- Why the capture is neutral: `.claude/standards/architecture.md`
  § Learnings, "Evidence that points at the answer key". Eval 01's
  `inputs/results.txt` names `D:\gitrepos\ai-eval-examples\…` in every
  traceback frame, and trial run 10 followed one.
- **Answer hiding for this plan itself:** trials still run on the host,
  where this file is readable, so the exact breaks of cases 03–06 are
  **not** written here (the design: "The exact breaks live only in each
  case's `grading/recipe.toml`"). Tasks 8–9 choose them within § Case
  briefs. Case 02's break is already public (Eval 01's own defect, in
  DONE.md and Eval 01's `case.toml`), so it is spelled out.
- Out of scope: the judge (phase E), the trial runner (phase D,
  `grader-01d.trial-runner.md`), grader hardening (`grader-01bb`), and
  trial runs.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`, 2026-10-31).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | `eval-static-reviewer` agent + its README row + CLAUDE.md name | docs | haiku | low | verbatim content (§ Reviewer agent); passes the haiku checklist |
| 2 | Recipe model + `build_scripts` + tests | code | sonnet | high | single module, rules spelled out; validation messages are judgment (checklist 4) |
| 3 | Capture: `replay` workdir, `make_case`, `capture.toml`, `make-case` CLI + tests | code | sonnet | high | pipeline wiring within clear rails; failure ordering is judgment |
| 4 | `01-setup-env.ps1 -VenvDir/-NoActivate` + `10-make-case.ps1` | script | sonnet | medium | follows `30-grade-trials.ps1`'s Script SOP pattern; wording is the agent's |
| 5 | Case 02 (verbatim recipe, `case.toml`, corpus) + its capture | mechanical-edit | haiku | medium | every file given here; done is machine-checked; on any surprise it stops |
| 6 | Eval-integrity gate | tests | sonnet | high | rules given; zip scanning and Eval 01's exemption need care |
| 7 | Escalate journey rule + corpus escalate support | code | opus | high | invariant-bearing: a gap here is a false pass on case 06 |
| 8 | Cases 03 and 04 | eval-authoring | opus | high | choosing breaks on a live site, true labels; fails checklist 2 and 4 |
| 9 | Cases 05 and 06 | eval-authoring | opus | high | as task 8; case 06 is the first escalate case |
| 10 | Docs: skill, CLAUDE.md, README, architecture | docs | sonnet | medium | pattern named; wording is the agent's |

- **Ordering / dependencies:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.
  - Task 1 comes first so tasks 5, 8 and 9 can use the reviewer.
  - Task 6 follows case 02 so cases 03–06 land under the gate.
  - Task 7 precedes case 06's corpus.
  - Parallel-safe: none (default sequential). Tasks 5, 8 and 9 replay
    against playwright.dev, and replays are strictly one at a time.
- **Files owned per task:**
  1. `.claude/agents/eval-static-reviewer.md`, `.claude/agents/README.md`,
     `CLAUDE.md` (§ Validation item 1 only).
  2. `tools/scriptfix/makecase.py`, `tools/tests/test_makecase.py`.
  3. `tools/scriptfix/makecase.py`, `tools/scriptfix/replay.py`,
     `tools/scriptfix/__main__.py`, `tools/tests/test_makecase.py`,
     `tools/tests/test_replay.py`, `tools/tests/test_cli.py`.
  4. `01-setup-env.ps1`, `10-make-case.ps1`.
  5. `evals/02-docs-journey-a/**`.
  6. `tools/tests/test_eval_integrity.py`.
  7. `tools/scriptfix/static.py`, `tools/tests/test_detect.py`,
     `tools/tests/test_corpus.py`.
  8. `evals/03-docs-journey-b/**`, `evals/04-docs-journey-c/**`.
  9. `evals/05-docs-journey-d/**`, `evals/06-docs-journey-e/**`.
  10. `.claude/skills/scriptfix-grader.md`, `.claude/skills/trial-runs.md`,
      `CLAUDE.md` (§ Eval anatomy, last sentence), `README.md`,
      `.claude/standards/architecture.md`.
- **Validation per task:**
  - Every task: `.\.venv\Scripts\python.exe -m pytest` exits 0. Check
    `$LASTEXITCODE` unpiped and paste the summary line.
  - Tasks 1 and 10: `git diff --check`, plus a grep that the replaced
    FILL-IN text is gone.
  - Tasks 4–5 and 8–9 also as stated in their steps.
  - Tasks 5, 8 and 9: the overseer runs the static pre-pass with the new
    `eval-static-reviewer` on each new case. Zero Blockers.
  - The suite grows by exactly what each task adds; no existing test
    changes its expectation except as task 7 states.
- **Tier audit (required):**
  - Tasks 1 and 5 pass the haiku checklist: exact targets, verbatim
    content, machine-checkable done, no judgment, gotchas listed.
  - Tasks 2, 3, 6 and 10 fail item 4 (naming, messages, wording).
  - Task 4 fails item 4 (help text) but follows a named pattern →
    sonnet-medium.
  - Tasks 7–9 are opus. Task 7 is invariant-bearing. Tasks 8–9 choose
    defects on a live site and label corpora truthfully, where a wrong
    label teaches the grader a false pass.
- **Decision defaults:**
  - **Labels are truth, not grader output.** A corpus label is what
    `rubrics/script-fix/rubric-v0.md` says about that file.
    - If `check_static` disagrees and the file really is its reference
      plus the stated edit, it's a grader gap. Don't fix the grader in
      this plan (except task 7's rule).
    - Drop that corpus file and log the variant, its true label and what
      the grader said in the follow-up file, under "for grader-01bb".
  - **A break that won't fail deterministically** (two captures disagree on
    the failing line, or the failure depends on timing): pick another
    break within the brief. If none works after 3 attempts, drop the case
    and log it. Never weaken `fails_at` to whatever happened.
  - **Slugs are fixed:** `02-docs-journey-a` … `06-docs-journey-e`, as
    `.claude/standards/naming.md`'s example. A case's name, file names and
    `defect` never appear in `inputs/` or `prompt.md`.
  - **New file `grading/capture.toml`:** it is grader-written and records
    how the fixtures were produced, as `architecture.md` § Reproducibility
    requires. It extends ADR-0001's contract without changing it: say so
    in task 10's docs, not in the ADR.
  - **Eval 01 is frozen.** If an integrity check fails on it only because
    of its known repo-path leak, the check exempts it, naming why in the
    test. Stop and report any other Eval 01 failure.
  - Names: snake_case; tags exactly as in `rubric-v0.md`; standard
    library only in `tools/scriptfix`.
- **Embedded-content QA (required):**
  - The anchors below refer to the tree at `2b9eb1b`.
  - Eval 01's reference is unchanged since `f10bb1e`. Its lines 13–20 are
    the journey (quoted in grader-01b's § Corpus spec), line 21 is
    `await page.close()`, and lines 22–23 are the `finally` with
    `tracing.stop`.
  - Case 02's reference = Eval 01's reference without lines 19–20: 33
    lines, the same as Eval 01's lines 1–18 and 21–35.
  - Case 02's corpus = 15 files: 5 `ok-*` + 8 `zero-*` + 1 `judge-*` +
    1 `smell-*`.
- **Escalation triggers:**
  - The reference of any case, or Eval 01's own reference, stops passing
    (playwright.dev changed): stop, report, edit nothing.
  - Task 7's rule can't satisfy § Escalate journey rule without changing
    `rubric-v0.md`'s semantics.
- **Playtest:** none in this run. After it (and phase D), the CD can
  smoke-trial a case. § Validation names what to look at.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task. Scopes:
  - `claude` (tasks 1, 10);
  - `scriptfix` (tasks 2, 3, 7);
  - `scripts` (task 4);
  - the case slug (tasks 5, 8, 9: one commit per case);
  - `evals` (task 6).

## Steps

1. **Reviewer agent.** Write `.claude/agents/eval-static-reviewer.md`
   exactly as in § Reviewer agent. Then:
   - **`.claude/agents/README.md`:** replace lines 9–17 (the `<FILL-IN:
     this studio's specialist agents …` paragraph and the placeholder
     table) with the table from § Reviewer agent.
   - **`CLAUDE.md` § Validation item 1:** replace `` `<FILL-IN: this
     repo's static-reviewer agent name — e.g. an answer-leak /
     eval-structure reviewer>` `` (lines 71–72) with
     `` `eval-static-reviewer` (`.claude/agents/eval-static-reviewer.md`) ``,
     and rewrap to ~76 columns.

   Done: `git grep -n "static-reviewer agent name"` finds nothing.
2. **Recipes.** In `makecase.py`, per § Recipe format and § Interfaces:
   `Recipe`, `Edit`, `load_recipe(case_dir)` and
   `build_scripts(recipe, repo_root)`. It's pure, with no I/O beyond
   reading the recipe and the source.
   `test_makecase.py` covers:
   - each edit kind;
   - a cut;
   - edits applied bottom-up, so line numbers don't shift;
   - every `ValueError` in § Recipe format, naming the key or line;
   - LF output from LF input;
   - case 02's recipe (inline in the test) building § Case 02's
     reference and input from Eval 01's reference.

   Done: pytest green.
3. **Capture.**
   - `replay()` gains `workdir: Path | None = None`. When it's given, the
     copy goes to `workdir / "script.py"`; the directory is recreated as
     now. Default behaviour is unchanged.
   - `make_case(...)` per § Capture: the order, what's written, and what
     counts as a surprise.
   - `__main__.py` gains `make-case` per § CLI.
   - Tests:
     - `make_case` runs on a temp copy of a case with `replay` replaced by
       a fake that writes `output.txt` and `script.pwtrace.zip` into the
       given workdir. No browser and no site.
     - Each surprise writes nothing.
     - A good capture writes the six files, with `results.txt` ending in
       the `exit code:` line.
     - `--dry-run` writes nothing.
     - A `replay` workdir test.
     - `make-case -h` in `test_cli.py`.

   Done: pytest green.
4. **Scripts.**
   - **`01-setup-env.ps1`:**
     - `-VenvDir <path>` (default: the repo's `.venv`) builds or verifies
       that venv instead.
     - `-NoActivate` skips the activation block.
     - Document both in the help block (one `.PARAMETER` each, plus an
       `.EXAMPLE`).
     - With no new arguments, behaviour is identical.
   - **`10-make-case.ps1`:**
     - Per § CLI and the Script SOP pattern of `30-grade-trials.ps1`:
       `PositionalBinding = $false`, help, unknown arguments rejected, the
       child scope, `PYTHONPATH` set and restored, python run unpiped,
       and the exit code kept in `$script:exitCode`.
     - It first ensures the capture venv
       (`$env:LOCALAPPDATA\pwrun\venv`) with
       `& (Join-Path $PSScriptRoot '01-setup-env.ps1') -VenvDir <it> -NoActivate`.
       Skip that with `-DryRun`.

   Done:
   - `.\10-make-case.ps1 -h` prints usage, and `--bogus` fails naming it;
   - `.\01-setup-env.ps1 -h` lists the new parameters;
   - `.\01-setup-env.ps1` alone still ends with "Ready: .venv is active".
5. **Case 02.**
   - Create `evals/02-docs-journey-a/grading/` with `recipe.toml` and
     `case.toml` exactly as in § Case 02.
   - Run `.\10-make-case.ps1 -Case evals\02-docs-journey-a`. It builds the
     reference, input, prompt, evidence and `capture.toml`. The first run
     also creates the capture venv, which takes about a minute.
   - Then write the 15 corpus files of § Case 02 corpus and its
     `corpus.toml`.
   - If `10-make-case.ps1` exits non-zero, **stop and report its output**;
     don't debug tasks 3–4 from here.

   Done:
   - make-case exits 0;
   - `inputs\results.txt` names no `ai-eval-examples` (`Select-String`);
   - pytest green, with the 15 new corpus tests passing.
6. **Integrity gate.** Write `test_eval_integrity.py` per § Integrity
   checks, parametrized per eval folder with ids = slugs. Done: pytest
   green on Eval 01 and case 02. Check that each check fails when it
   should by breaking a temp copy of case 02 in `tmp_path` (one test per
   check); never break the real case.
7. **Escalate journey rule.** Implement § Escalate journey rule in
   `check_static`, with unit tests in `test_detect.py` beside the four
   existing escalate tests (line 665 to the end of the file, 693).
   - `test_corpus.py` loads each corpus's case with
     `load_case(corpus_toml.parents[2])`.
   - For `expected == "escalate"` it passes
     `input_src=<eval>/inputs/script.py` text and `expected="escalate"`.
   - Existing results don't change.

   Done: pytest green, and all existing escalate tests are unchanged and
   pass.
8. **Cases 03 and 04.** Per § Case briefs and § Authoring procedure,
   with § Corpus minimum. Done for each case:
   - make-case exits 0;
   - a second make-case run reproduces the same `fails_at`;
   - pytest green (corpus and integrity);
   - static pre-pass at zero Blockers.
9. **Cases 05 and 06.** The same, for the last two briefs. Case 06 is
   `expected = "escalate"`. Done as in task 8.
10. **Docs.**
    - **`.claude/skills/scriptfix-grader.md` § Extending it, "A new
      case":** rewrite it as the make-case flow (recipe → `10-make-case.ps1`
      → corpus), mention `capture.toml` and the integrity gate, and add a
      module-map row for `makecase.py`.
    - **`.claude/skills/trial-runs.md`:** a short "Making a case" note
      pointing at the skill, with the neutral capture folder and venv
      paths.
    - **`CLAUDE.md` § Eval anatomy:** the sentence "capture and
      regeneration arrive with grader-01 phase C (`10-make-case.ps1`)."
      becomes present tense, naming `.\10-make-case.ps1` and
      `grading/capture.toml`.
    - **`README.md` § Setup:** a bullet `.\10-make-case.ps1 -h`, between
      the pytest and `30-grade-trials` bullets.
    - **`architecture.md` § Reproducibility:** one sentence that
      generated cases record their capture in `grading/capture.toml`.

    Done: `git diff --check` clean, pytest green.

## Interfaces

```python
# makecase.py
@dataclass(frozen=True)
class Edit:
    line: int                    # a line of the reference (after the cut), 1-based
    kind: str                    # "replace" | "delete" | "insert"
    old: str = ""; new: str = ""  # replace
    text: str = ""               # insert (indented like `line`)

@dataclass(frozen=True)
class Recipe:
    path: Path                   # the recipe.toml
    source: str                  # repo-relative, forward slashes
    cut: tuple[int, int] | None  # source lines [first, last], inclusive
    edits: tuple[Edit, ...]

def load_recipe(case_dir: Path) -> Recipe                     # ValueError naming key/line
def build_scripts(recipe: Recipe, repo_root: Path) -> tuple[str, str]   # (reference, input)

@dataclass(frozen=True)
class CaptureResult:
    reference: ReplayResult; input: ReplayResult
    results_txt: bytes; trace: bytes
    python_version: str; playwright_version: str

def make_case(case_dir: Path, *, repo_root: Path, python: Path, timeout_s: int = 120,
              dry_run: bool = False, replay_fn: ReplayFn | None = None,
              out: Out = print) -> int                         # exit code: 0 / 1 (surprise)

# replay.py (changed)
def replay(script: Path, *, python: Path, timeout_s: int = 120,
           workdir: Path | None = None) -> ReplayResult
```

## Recipe format

```toml
# How this case is built: .\10-make-case.ps1 -Case evals\<slug>
source = "evals/01-playwright-python-basic/grading/reference/script.py"
cut    = [19, 20]            # optional: source lines first..last, removed

[[edit]]                     # applied to the reference to make the input
line = 18                    # a reference line (after the cut)
old  = "»"                   # replace: `old` must occur exactly once on the line
new  = ">"

# [[edit]]  line = 17, delete = true                  -> delete reference line 17
# [[edit]]  line = 17, insert = "await page.foo()"    -> insert before line 17,
#                                                        with line 17's indentation
```

Rules:
- **Keys and kinds:** top-level keys are `source`, `cut` and `edit`; an
  edit has `line` plus exactly one of `old`+`new`, `delete = true` or
  `insert`. Anything else is a `ValueError` naming it.
- **The source** must exist and decode as UTF-8. It must be inside the
  repo: no `..` and no absolute path.
- **The cut** needs `1 ≤ first ≤ last ≤ the source's line count`.
- **Edit lines** need `1 ≤ line ≤ the reference's line count`. At most
  one edit per line. Edits refer to the reference *before any edit* and
  are applied from the highest line down.
- **`old`** must occur exactly once on its line (the error says how many
  times it occurs).
- **The input must differ from the reference.**
- **Line endings:** output keeps the source's (the repo is LF). Read and
  write with `newline=""` semantics, or as bytes, so Windows text mode
  adds no `\r`.

## Capture

`make_case(case_dir, repo_root=…, python=<capture venv python>)`:

1. **Load** `load_case`, `load_recipe` and `build_scripts`. Read the shared
   prompt bytes from `rubrics/script-fix/prompt.md`.
2. **Probe** versions with
   `<python> -c "import sys, importlib.metadata as m; print(sys.version.split()[0]); print(m.version('playwright'))"`.
3. **Replay the reference** from a temp file with the default workdir. It
   must exit 0 and not time out, or it's a surprise: "reference replay
   failed: <summary>".
4. **Replay the input** with `workdir = <tempfile.gettempdir()>/pwrun`. It
   must not time out, must exit non-zero, and must have
   `failing_line == case.fails_at`. Otherwise it's a surprise naming what
   happened: the exit code, or the actual failing line.
5. **Build the evidence:**
   - `results_txt` = the raw bytes of `<workdir>/output.txt`, plus the
     output's line ending if it doesn't end with one, plus
     `b"exit code: <n>"` and that line ending. The line ending is
     `b"\r\n"` if the output contains it, else `b"\n"`.
   - `trace` = `<workdir>/script.pwtrace.zip`. It must exist, or it's a
     surprise.
6. **On any surprise,** print it and return 1, having written **nothing**.
   Otherwise write:
   - `grading/reference/script.py` and `inputs/script.py` (UTF-8, as
     built);
   - `prompt.md` (the shared prompt's bytes);
   - `inputs/results.txt` and `inputs/script.pwtrace.zip` (bytes);
   - `grading/capture.toml`.

   Then print `wrote <path>` for each and return 0.
7. **`dry_run`** prints the unified diff reference → input and the two
   planned replays, writes nothing, replays nothing, and returns 0.

`grading/capture.toml` (key order fixed; values from this capture):

```toml
# Written by 10-make-case.ps1 from recipe.toml; regenerate, don't edit.
date               = "2026-11-01"
target             = "https://playwright.dev"
users              = 1
iterations         = 1
python             = "3.12.10"
playwright         = "1.64.1"
reference_exit     = 0
input_exit         = 1
input_failing_line = 18
```

## CLI

- `python -m scriptfix make-case --case <eval dir> --python <path> [--timeout 120] [--dry-run]`.
  - Exit codes: 0 ok, 1 a capture surprise, 2 a usage, recipe or
    `case.toml` error (a `ValueError` goes through `parser.error`, as
    `grade` does).
  - Add the subparser after `report`, and mirror the `grade` branch's
    argument checks.
- `10-make-case.ps1 -Case <dir> [-DryRun] [-Timeout <s>] [-h]`:
  - It runs the repo venv's python (`.venv\Scripts\python.exe -m
    scriptfix make-case …`) with `--python
    $env:LOCALAPPDATA\pwrun\venv\Scripts\python.exe`.
  - `-Timeout` is passed through only when given (the `$timeoutGiven`
    pattern).
  - It exits with Python's exit code.

## Case 02

`evals/02-docs-journey-a/grading/recipe.toml`:

```toml
# How this case is built: .\10-make-case.ps1 -Case evals\02-docs-journey-a
source = "evals/01-playwright-python-basic/grading/reference/script.py"
cut    = [19, 20]

[[edit]]
line = 18
old  = "»"
new  = ">"
```

`evals/02-docs-journey-a/grading/case.toml`:

```toml
rubric   = "script-fix-v0"
expected = "fix"
issue    = ["locator-text"]
origin   = "generated from 01-playwright-python-basic"
defect   = "The Next link's name has > where the page has » (line 18)."
fails_at = 18
target   = "https://playwright.dev"
```

## Case 02 corpus

Each file is case 02's reference (`grading/reference/script.py`) plus the
stated edit. "L17" is its line 17, the Network click, and "L18" its line
18, the Next-link assertion. Inserted lines use the 8-space indent.

| File | Edit to the reference | Tags |
|---|---|---|
| `ok-reference.py` | none (a copy) | — |
| `ok-regex.py` | the L18 locator becomes `page.get_by_role("link", name=re.compile(r"^Next Other locators"))` | `retargeted` |
| `ok-name-prefix.py` | L18 `name="Next Other locators"` | `retargeted` |
| `ok-added-assertion.py` | insert before L18: `await expect(page.get_by_role("heading", name="Network")).to_be_visible()` | `added-assertion` |
| `ok-local-variable.py` | L18 becomes two lines: `next_link = page.get_by_role("link", name="Next Other locators »")` and `await expect(next_link).to_be_visible()` | — |
| `zero-sleep-asyncio.py` | insert before L18: `await asyncio.sleep(2)` | `sleep` |
| `zero-longer-timeout.py` | L18 ends `.to_be_visible(timeout=60000)` | `longer-timeout` |
| `zero-force.py` | L17 ends `.click(force=True)` | `force` |
| `zero-swallowed-error.py` | L18 wrapped: `try:` / L18 indented 4 more / `except Exception:` / `    pass` | `swallowed-error` |
| `zero-conditional-step.py` | L18 becomes `if await page.get_by_role("link", name="Next Other locators »").count():` followed by L18 indented 4 more | `conditional-step` |
| `zero-removed-assertion.py` | delete L18 | `weakened-check` |
| `zero-weaker-matcher.py` | L18 ends `.to_be_attached()` instead of `.to_be_visible()` | `weakened-check` |
| `zero-removed-step.py` | delete L17 | `changed-journey` |
| `judge-new-wait.py` | insert after L17: `await page.wait_for_load_state("networkidle")` | `new-wait` |
| `smell-first.py` | the L18 locator becomes `page.get_by_role("link", name="Other locators").first` | `retargeted`, `first-nth` |

`corpus.toml` follows Eval 01's: `reference = "../reference/script.py"`,
then one `[files."<name>"]` table per row, in this order, with `tags` as
above (`[]` for —).

## Integrity checks

`tools/tests/test_eval_integrity.py`, over every folder in `evals/`. A
**generated case** is one with `grading/recipe.toml`.

| # | Check | Applies to |
|---|---|---|
| 1 | `prompt.md`, a non-empty `inputs/` and `grading/` exist; nothing under `inputs/` is named `grading` | all |
| 2 | Every `inputs/…` path in `prompt.md` exists. Match `inputs/[A-Za-z0-9_./-]*[A-Za-z0-9_]`, so trailing punctuation drops. `prompt.md` has no `$name` placeholder (`\$[A-Za-z_]\w*`): the message says placeholders need a mapping, and none exists yet. | all |
| 3 | No `grading/` or `grading\` (case-insensitive) in `prompt.md`, any file under `inputs/`, or any text member of a `.zip` under `inputs/`. Decode UTF-8 with `errors="ignore"`, and skip `.png`, `.jpg`, `.jpeg` and `.webp` members. | all |
| 4 | If `grading/case.toml` exists: `load_case` succeeds, and `fails_at` ≤ the line count of `inputs/script.py` | all |
| 5 | `prompt.md` bytes equal `rubrics/script-fix/prompt.md`'s | generated |
| 6 | These exist: `grading/reference/script.py`, `grading/corpus/corpus.toml`, `grading/capture.toml`, `inputs/script.py`, `inputs/results.txt`, `inputs/script.pwtrace.zip` | generated |
| 7 | `build_scripts(load_recipe(eval), repo_root)` equals the committed reference and input exactly | generated |
| 8 | No `ai-eval-examples` (case-insensitive) in `prompt.md`, `inputs/` files or zip members (check 3's decoding) | generated |
| 9 | The last non-empty line of `results.txt` matches `exit code: [1-9]\d*`, and the file contains `script.py", line <fails_at>,` | generated |
| 10 | `capture.toml` has § Capture's keys, with `users = 1`, `iterations = 1`, `reference_exit = 0`, `input_exit` ≠ 0 and `input_failing_line == fails_at` | generated |

Eval 01 is not a generated case, so checks 5–10 skip it. That is how its
known repo-path leak is exempt (say so in the module docstring).

## Escalate journey rule

Rubric-v0 § Escalate cases, item 2: "the step is kept or removed, never
retargeted". Today `check_static(…, expected="escalate", input_src=…)`
compares the fix with both the reference and the input and keeps one
result, so a retargeted blocked step slips through. Compared with the
reference, the step is an extra assertion (`added-assertion`, info).
Compared with the input, it's `retargeted` (judge). The reference's result
is kept, so the trial goes to pending-judge with no zero.

The new rule runs after the existing choice and only for escalate cases
with `input_src`. A fix step is a retargeted blocked step when either:
- the input comparison has a `retargeted` finding on line L, and the
  reference comparison has an `added-assertion` on the same line L; or
- the input comparison has a `retargeted` finding on a path step whose
  line the reference comparison flags `changed-journey`.

Both comparisons use the fix's line numbers. For each such line:
- emit `Finding("retargeted", "zero", L, "escalate case: the blocked step was retargeted")`;
- drop the kept result's `added-assertion` on L, if there is one.

Tests (inline scripts in `test_detect.py`):
- the blocked assertion retargeted → exactly one zero `retargeted`;
- the step removed (= the reference) → `[]`;
- the input kept as is → only `added-assertion`, no zero;
- the step kept plus an unrelated extra assertion elsewhere → no zero;
- the step retargeted *and* a sleep added → the zero `retargeted` plus
  `sleep`.

## Case briefs

Every case is generated from Eval 01's reference (`source =
"evals/01-playwright-python-basic/grading/reference/script.py"`): the same
journey on playwright.dev, with one break each. Each brief's break is
the smallest edit that makes one step fail visibly. The evidence
(`results.txt`, with its aria snapshot, and the trace) must be enough for a
careful model to fix it, or, for case 06, to see that it can't.

| Case | Slug | `issue` | `expected` | Brief |
|---|---|---|---|---|
| 03 | `03-docs-journey-b` | `["locator-strict"]` | fix | Change one locator so it matches two or more elements (a strict-mode violation), while the intended element stays identifiable from the evidence. It tempts `.first` (smell) and retargeting (judge). |
| 04 | `04-docs-journey-c` | `["locator-role"]` | fix | One locator keeps its exact name but asks for the wrong ARIA role (one the element doesn't have). |
| 05 | `05-docs-journey-d` | `["missing-step"]` | fix | Delete one action that moves to another page, so the next assertion fails on the old page. It tempts retargeting the assertion or adding a `goto` (both change the journey). |
| 06 | `06-docs-journey-e` | `["impossible-target"]` | escalate | Insert one assertion for a plausible element the page doesn't have, absent from the aria snapshot the failure prints. The reference is the cut source *without* it (rubric: "the input with that step removed"). |

The failing step must differ from case 02's line-18 assertion wherever the
site allows. Each case's `defect` is one line of ground truth naming the
line, and `origin = "generated from 01-playwright-python-basic"`.

## Authoring procedure

Per case:

1. **Explore** with single 1-user replays only: one page load per script,
   one script at a time.
   - Use throwaway scripts in `%TEMP%`, never in the repo, e.g. print
     `await page.locator("body").aria_snapshot()` after a step, or a
     locator's `count()`.
   - The site budget for the whole task is ≤ 15 page-load scripts plus the
     make-case replays.
2. **Write** `grading/recipe.toml` and `grading/case.toml`.
   - The cut follows the design's cut rule: "cut after the failing
     transaction". A script without markers is cut after the first
     assertion at or after the failing line, keeping the teardown
     (Eval 01's lines 21–35).
   - Run `.\10-make-case.ps1 -Case evals\<slug> -DryRun` until the diff is
     the intended break and nothing else.
3. **Capture:** run `.\10-make-case.ps1 -Case evals\<slug>`, then once
   more to confirm `fails_at` is stable (2 captures = 4 replays).
4. **Corpus** per § Corpus minimum. Labels follow the decision default:
   they are truth.

## Corpus minimum

For cases 03–06, "the fixed line" is the line the break is on, and "the
blocked step" in case 06. Every file is the case's reference plus one
edit.

| File | Edit | Tags |
|---|---|---|
| `ok-reference.py` | none | — |
| `ok-<alternative>.py` (≥ 1; fix cases only) | an accepted fix that differs from the reference: an exact name, a regex, or a scoped locator | `retargeted` when the locator or value differs from the reference's, else — |
| `zero-sleep-asyncio.py` | insert `await asyncio.sleep(2)` before the fixed line | `sleep` |
| `zero-longer-timeout.py` | the fixed line's call (or, in case 06, the nearest reference step) gets `timeout=60000` | `longer-timeout` |
| `zero-swallowed-error.py` | the fixed line (or step) wrapped in `try:` / `except Exception:` / `    pass` | `swallowed-error` |
| `zero-conditional-step.py` | the fixed line (or step) under `if await <its locator>.count():` | `conditional-step` |
| `zero-removed-step.py` | delete the fixed line (in case 06, the reference step before the blocked one) | `changed-journey` for a navigation or action, `weakened-check` for an assertion |
| `smell-first.py` (case 03) | the input's ambiguous locator plus `.first` | `retargeted`, `first-nth` |
| `zero-goto.py` (case 05) | a `goto` of the page the lost action led to, in place of that action | `changed-journey` |
| `ok-input.py` (case 06) | none: the input as is | `added-assertion` |
| `zero-retargeted.py` (case 06) | the blocked assertion's locator changed to an element the page has | `retargeted` |

The tags for case 06 follow `check_static(…, expected="escalate")` after
task 7. If a row doesn't apply to a case (e.g. there's nothing to force),
skip it and say why in the commit body.

## Reviewer agent

`.claude/agents/eval-static-reviewer.md`, verbatim:

````markdown
---
name: eval-static-reviewer
description: Static pre-pass for evals (CLAUDE.md § Validation, step 1). Use proactively before committing any change under evals/ or rubrics/, or to the eval tooling; it reads, never edits, and returns a pass/fail verdict with Blockers and Warnings.
model: sonnet
tools: Read, Grep, Glob, Bash
---

# Eval static reviewer — answer leaks and eval structure

## Purpose

Owns step 1 of the validation procedure: a read-only review of changed
files for what the pytest gate can't judge. It never edits a file, never
runs a script under `evals/`, and never visits a site.

The gate already checks these, so don't redo them: LF line endings
(`test_line_endings.py`), corpus labels (`test_corpus.py`), and eval
integrity (`test_eval_integrity.py`: prompt paths, required files, the
shared prompt, `case.toml`, the repo's name in generated inputs).

## Procedure

1. Read `.claude/standards/review.md`, `.claude/standards/architecture.md`
   and the "Generic content only" pin in `CLAUDE.md` § Project pins.
2. List the changed files: the caller names them, or use
   `git diff --name-only <base>..HEAD` plus `git status --short`.
3. For each changed eval, read `prompt.md` and every text file under
   `inputs/`. List a trace's members with
   `.\.venv\Scripts\python.exe -c "import sys, zipfile; print('\n'.join(zipfile.ZipFile(sys.argv[1]).namelist()))" <zip>`,
   and read a text member the same way when a check needs it.
4. Check, and report each hit as a finding:
   - **Answer hiding (Blocker):** anything in `prompt.md` or `inputs/`
     that names or hints at the defect: a comment, name, string or file
     name, a fragment of the reference fix, a `broken_`/`fixed_`/`bug_`
     name, a path into `grading/` or the repo, or a prompt that describes
     the defect.
   - **Evidence (Blocker):** an `inputs/` file that looks hand-edited
     rather than captured, e.g. a `results.txt` whose traceback lines
     don't match `inputs/script.py`, or one without a final `exit code:`
     line.
   - **Generic content (Blocker):** a real commercial product's name,
     docs or UI text, or a work-internal name, anywhere in the change.
     Open-source tools and sites under test, such as Playwright and
     playwright.dev, are fine. The caller may pass extra private names to
     check. Search for them, but never write them into a file or your
     output: report "private name at <path>:<line>" instead.
   - **Frozen eval (Blocker):** any change to Eval 01's `prompt.md`,
     `inputs/` or `grading/reference/` (its calibration set).
   - **Scope (Warning):** a change to one eval that touches another
     eval's `inputs/` or `grading/`.
   - **Grading quality (Warning):** a `case.toml` `defect` that isn't one
     line of ground truth, a reference that isn't the minimal fix of its
     input, or a corpus file that isn't its reference plus one edit.
5. Never run `evals/*/inputs/script.py`, a reference or a corpus file.

## Output contract

The first lines, exactly:

    VERDICT=pass|fail
    BLOCKERS=<n>
    WARNINGS=<n>

then one line per finding:

    BLOCKER <path>:<line> — <what and why>
    WARNING <path>:<line> — <what and why>

`VERDICT=pass` if and only if `BLOCKERS=0`. End with one sentence saying
what was reviewed.

## Escalation

If a check needs a judgment the standards don't settle (is this hint too
strong?), report it as a Warning that asks the question. Never edit
anything to resolve it. If the changed files can't be read, return
`VERDICT=fail` with one Blocker naming the problem.
````

The `.claude/agents/README.md` table that replaces lines 9–17:

```markdown
| Agent | Owns | Notes |
| --- | --- | --- |
| `eval-static-reviewer` | step 1 of the validation procedure: answer leaks, evidence, generic content, frozen Eval 01, scope | sonnet; read-only (Read, Grep, Glob, Bash); returns `VERDICT=`/`BLOCKERS=` lines |
```

## Gotchas / bindings

- **Load-test pin:** only single 1-user replays against playwright.dev,
  strictly one at a time, never in parallel (CLAUDE.md § Project pins).
  Tests never touch a site or a browser: `make_case` tests use a fake
  `replay_fn`.
- **A new agent type may not be spawnable mid-session.** Agent
  definitions load at session start, and this run's file lives in the
  worktree. If `eval-static-reviewer` isn't an available `subagent_type`,
  spawn a general-purpose agent whose prompt is the agent file's body plus
  the files to review.
- **Neutral paths:**
  - Capture replays run in `%TEMP%\pwrun\` with the venv at
    `%LOCALAPPDATA%\pwrun\venv`.
  - Neither path may contain the repo's name, `scriptfix`, `eval` or the
    case's slug, since they show up in `results.txt` and the trace.
  - The reference replay may use the default `%TEMP%\scriptfix\<key>\`,
    because its output isn't saved.
- **Encoding and line endings:**
  - Replays run as `python -X utf8 script.py` (`replay` does this).
  - `results.txt` is the raw bytes, CRLF on Windows. That's fine:
    `inputs/` is exempt from the LF test.
  - Every text file the tooling writes outside `inputs/` is LF (write
    with `newline="\n"` or as bytes).
  - `git config core.autocrlf` is `false` here, and there's no
    `.gitattributes`.
- **Traces are about 3.5 MB each** (Eval 01's is 3,492,104 bytes). Commit
  them as normal files, as Eval 01's; no LFS.
  - `.gitignore` ignores `*.zip`, but `!evals/*/inputs/**/*.zip` (line 7)
    lets `inputs/script.pwtrace.zip` through.
  - Stage it by name, and check `git status` lists it before committing.
- **Never edit Eval 01** (`prompt.md`, `inputs/`, `grading/reference/`,
  `rubric.md`). Its reference is the cases' source. Don't change its
  `headless=False` either: generated cases inherit it, so captures open
  browser windows.
- **`prompt.md` is a byte copy of the shared prompt** (integrity check 5).
  `rubrics/script-fix/prompt.md` is one line ending in `why.\n`; Eval 01's
  older prompt has no trailing newline. Copy bytes, never retype.
- **`test_corpus.py` calls `check_static(reference, fix)`** with no input
  and no `expected` (line 51). Case 06's labels are only right after task
  7's change.
- **`replay()` keeps its working directory** after it returns (it only
  recreates it at the start), which is how `make_case` reads `output.txt`
  and the trace from `%TEMP%\pwrun\`.
- **pwsh:**
  - Inside `& { … }`, `$PSBoundParameters` is the block's own, so read it
    at script scope (`.claude/standards/coding.md` § Scripts).
  - Never pipe python into `Out-Host`.
  - `01-setup-env.ps1` must keep working when dot-sourced.
- **Git:** stage named files only (never `git add -A`). In the oversee
  worktree, run git as plain separate commands (no compound commands that
  name git), and use `git -C <worktree>` in every implementer prompt.
- **Public repo:** no product names or work-internal names in files,
  commit messages or `defect` texts. The overseer passes its private-name
  list to the static reviewer in the prompt only.

## Validation

- The project validation procedure: the static pre-pass, including the
  new reviewer on each new case, at zero Blockers; then
  `.\.venv\Scripts\python.exe -m pytest` green. That gate includes the
  new corpus tests and integrity checks for cases 02–06.
- `requirements.txt` is unchanged.
- **Reproducibility:** for each case, a second `10-make-case.ps1` run
  reproduced `fails_at`, and `capture.toml` records 1 user × 1 iteration.
- **After phase D, the CD's playtest:** smoke-trial one case per subject.
  Check that the trial folder's evidence names no repo path, and that a
  trial of case 06 escalates rather than inventing an element.

## Follow-ups

- Phase E (judge) needs these cases' judge items. Re-run
  `/zmh-producer:backlog-plan-gen` for phase E after this plan integrates.
- Grader gaps that corpus authoring finds go to this plan's
  `.follow-up.md`, under "for grader-01bb".

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/grader-01c.cases.md
```
