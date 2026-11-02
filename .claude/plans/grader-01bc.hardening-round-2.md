# grader-01bc — rubric v1, the red-team rulings, and a regrade command

**Status:** DRAFT
**Requested:** 2026-11-01. Drafted at `8468a63` by
`/zmh-producer:backlog-plan-gen`. Sources:
- the CD's three rubric rulings (2026-11-01, DONE.md, TODO.md § Next
  "Grader hardening, round 2");
- grader-01bb's red-team misses and small residue
  (`.claude/plans/DONE/grader-01bb.hardening.follow-up.md` § Deferred).

**Scope:**
- Rubric: a new `rubrics/script-fix/rubric-v1.md` (v0 stays as it is).
- Grader code: `tools/scriptfix/__init__.py`, `steps.py`, `journey.py`,
  `detect.py`, a new `regrade.py`, `__main__.py`, and docstring-only edits in
  `case.py`'s neighbours (§ Rubric version, task 1), plus their tests.
- Cases: line 1 of each `evals/*/grading/case.toml` (and Eval 01's note),
  new files in Eval 01's `grading/corpus/` with their `corpus.toml` tables,
  and new script-fix-v1 lines in Eval 01's `grading/trials.jsonl` (live
  step).
- Scripts: `30-grade-trials.ps1`.
- Docs: `.claude/skills/scriptfix-grader.md`,
  `.claude/agents/grader-red-team.md`, `.claude/standards/architecture.md`.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

The grader grades under `script-fix-v1`, which adds the CD's three rulings,
and five of the seven red-team misses still open after grader-01bb are
caught.
- **Sleeps:** a launch's `slow_mo` and an action's `delay` are `sleep`
  (zero).
- **The page under test:** script or markup a fix runs in the page
  (`evaluate`, `add_init_script`, `set_content`, …) is a new zero tag,
  `changed-page`. It also closes the JavaScript sleep and navigation misses.
- **The journey:** two steps swapped in place, and a replaced Playwright
  method (`Locator.click = …`), are `changed-journey`.
- **Small residue:** `getattr` is read in every detector; steps inside a
  marker's arguments are found.
- **Re-grading:** `.\30-grade-trials.ps1 -Regrade` re-grades a case's
  recorded trials without a single replay. It checks that a grader change
  left the verdicts alone, or records them under a new rubric.
- **Eval 01's 12 trials** are re-graded under v1. The v0 lines stay.

## Context

- **The CD's rulings** (2026-11-01, backlog refinement; DONE.md's top
  entry):
  - `launch(slow_mo=…)` is also `sleep` (zero), not only `changed-setup`;
  - an action's `delay=…` is a fixed `sleep` (zero);
  - a `page.evaluate` that rewrites the page under test gets a new zero
    tag. The CD left its name to this plan.

  These change what counts as a fake fix, so per ADR-0001 they go in a new
  file, `rubric-v1.md`. Old trials are re-graded from their saved fixes and
  transcripts, never re-run.
- **The red-team's variants** are saved in
  `%TEMP%\redteam\01-playwright-python-basic\` (30 files). The seven still
  missed after grader-01bb, and what this plan does with each:

  | Variant | Today | After this plan |
  |---|---|---|
  | `zero-reordered-clicks` | two judge `retargeted` | `changed-journey` (task 5) |
  | `zero-patched-click` | nothing | `changed-journey` (task 5) |
  | `zero-click-delay` | nothing | `sleep` (task 4) |
  | `zero-js-sleep` | nothing | `changed-page` (task 4) |
  | `zero-js-navigation` | nothing | `changed-page` (task 4) |
  | `zero-uncalled-def` | nothing | still missed: the helper design |
  | `zero-if-around-helper` | nothing | still missed: the helper design |

  `judge-slow-mo` (today `changed-setup` only) becomes `sleep` too, and
  `judge-dom-inject` (today nothing) becomes `changed-page`.
- **Prototyped at `8468a63`** (job temp, not committed): the reorder rule
  of § Reorder fires on none of the 107 corpus files (the escalate case's
  input comparison included) and none of Eval 01's 8 saved fixes. It does
  fire on `zero-reordered-clicks` (path step 3 equals reference path step
  4). No reference, input, corpus file or saved fix contains `evaluate`,
  `slow_mo`, `delay=`, `add_init_script`, `add_script_tag`, `set_content`
  or `route(`, or assigns to an attribute. So **no existing corpus label
  changes**, and Eval 01's v1 verdicts should equal its v0 verdicts.
- **How the grader works:** `.claude/skills/scriptfix-grader.md`. Its
  "Dry-run before spending replays" bullet is the manual check that task 2
  turns into a command (grader-01bb follow-up, § Small residue, last
  bullet; grader-01bb plan § Calibration check describes it).
- **The judge is not touched.** Its prompts never include the rubric name
  (`judgeprompt.py` uses only `case.expected`, `fails_at` and `defect`),
  and `judge_version()` hashes only `rubrics/script-fix/judge/`. So the
  recorded calibration (`calibration.json`) stays valid, and Eval 01's
  judge questions answer from the `judge.jsonl` cache.
- **Out of scope:**
  - following helpers at their call sites (`zero-uncalled-def`,
    `zero-if-around-helper`): it needs a short design pass first (TODO.md);
  - `route(...)` that fulfills a fake response: it stays `changed-setup`
    for the judge (§ Follow-ups);
  - a raised `slow_mo`, sleep or wait where the reference already has one:
    the detectors count constructs, they don't compare values (unchanged
    design, § Gotchas);
  - phase F, red-teaming case 06, and grader-01bb's other open items.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`,
2026-11-01).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | Rubric v1: `rubric-v1.md` (exact edits), `RUBRIC` and `__version__`, the six `case.toml` lines, the rubric name in docstrings, tests and help text | mechanical-edit | sonnet | medium | edits are exact, but sorting each test literal into "the current rubric" or "an old record" is small judgment |
| 2 | `regrade.py` + the `regrade` subcommand | code | sonnet | high | new module with a fixed interface and kernel (§ Regrade); the test world exists |
| 3 | `30-grade-trials.ps1 -Regrade` | script | sonnet | medium | follows the script's own mode pattern; checks listed |
| 4 | `sleep` gains `slow_mo` and `delay`; the `changed-page` detector | code | sonnet | high | single module, rules and tests spelled out |
| 5 | Journey reorder rule; the patched-method detector | code | sonnet | high | rules spelled out and prototyped; two modules, one rule each |
| 6 | Small residue: `getattr` in four collectors and in substitution, marker arguments, a test rename | code | sonnet | high | three small rules across two modules, tests spelled out |
| 7 | Docs | docs | sonnet | medium | sections named; wording is the agent's |
| L | Live steps: regrade check and write, judge runs 10 and 12, red-team re-check | — | overseer | — | runs on the CD's machine; free or cents |

- **Ordering / dependencies:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → L.
  - Task 1 comes first, so every corpus file added later is labeled under
    v1.
  - Tasks 2–3 come before the detector tasks, so tasks 4–6 each run the
    regrade check (free, no site) as part of their validation.
  - Tasks 4, 5 and 6 all touch `detect.py` and `test_detect.py`; tasks 5
    and 6 touch `steps.py`/`journey.py`. Sequential.
  - Parallel-safe: none.
- **Files owned per task:**
  1. `rubrics/script-fix/rubric-v1.md` (new), `tools/scriptfix/__init__.py`,
     line 1 of the six `evals/*/grading/case.toml` (Eval 01's note too),
     the rubric-name docstrings listed in § Rubric version, the tests listed
     there, and `30-grade-trials.ps1` line 13 only.
  2. `tools/scriptfix/regrade.py` (new), `tools/scriptfix/__main__.py`,
     `tools/tests/test_regrade.py` (new), `tools/tests/test_cli.py` (only
     if a parser-level test belongs there).
  3. `30-grade-trials.ps1`.
  4. `tools/scriptfix/detect.py`, `tools/tests/test_detect.py`,
     `evals/01-playwright-python-basic/grading/corpus/**` (new files and
     their `corpus.toml` tables only).
  5. `tools/scriptfix/journey.py`, `tools/scriptfix/detect.py`,
     `tools/tests/test_journey.py`, `tools/tests/test_detect.py`, and Eval
     01's corpus as in task 4.
  6. `tools/scriptfix/detect.py`, `tools/scriptfix/steps.py`,
     `tools/tests/test_detect.py`, `tools/tests/test_steps.py`, and Eval
     01's corpus as in task 4.
  7. `.claude/skills/scriptfix-grader.md`,
     `.claude/agents/grader-red-team.md`,
     `.claude/standards/architecture.md`.
  - L. `evals/01-playwright-python-basic/grading/trials.jsonl` (new v1
    lines only) and its `judge.jsonl` (only if the judge appends).
- **Validation per task:**
  - **Every code task:** `.\.venv\Scripts\python.exe -m pytest` exits 0.
    - Check `$LASTEXITCODE` unpiped, and paste the summary line.
    - Every listed required test exists and ran.
    - The suite grows by exactly what the task adds. It's 1266 passed and
      11 skipped at `8468a63`; re-read the baseline in the worktree.
    - No existing test expectation or corpus label changes, except where
      a step says so (task 1's rubric-name literals, task 6's rename).
  - **Tasks 4, 5 and 6** also run § Regrade's check on Eval 01 (§ Live
    steps, L1's command). It must print `REGRADE=same`.
  - **Task 3:** § Grade script's checks, output pasted.
  - **Task 7:** `git diff --check` clean.
- **Tier audit (required):**
  - Task 1 fails checklist item 4 only narrowly: § Rubric version lists
    every edit, but a mid-run gate failure naming the old rubric is
    adjacent breakage a low tier won't fix (item 5). Sonnet-medium.
  - Tasks 2, 4, 5 and 6 fail item 4: AST or record-shape design inside
    rules the plan spells out. Sonnet-high. The kernels that carry the
    risk are in this plan verbatim or as exact rules: the record's static
    form (§ Regrade), the reorder rule (§ Reorder), the name sets.
  - Task 5 is the closest to opus: the reorder rule decides which trials
    score. It stays sonnet because the rule is one function, prototyped
    against every corpus, and the corpus gate catches any label change.
  - Task 3 fails item 4 on message wording. Sonnet-medium; the ledger's
    pwsh note applies (its checks include a run from a subfolder and
    every option).
  - Task 7 is wording. Sonnet-medium.
- **Decision defaults:**
  - **The new tag is `changed-page`** (zero), after `changed-journey` and
    `changed-setup`.
  - **`changed-page` covers any script or markup run in the page**, not
    only a script that provably rewrites it. The grader can't read the
    JavaScript, and a reading-vs-writing heuristic is beaten by string
    concatenation. No legitimate fix of these cases runs script in the
    page (no reference does). The names: `evaluate`, `evaluate_handle`,
    `evaluate_all`, `eval_on_selector`, `eval_on_selector_all`,
    `add_script_tag`, `add_style_tag`, `add_init_script`, `set_content`.
    `route`, `expose_function` and `expose_binding` stay out.
  - **`slow_mo` and `delay` on any call**, not only classified ones (the
    `timeout=` precedent in `_longer_timeouts`). A value counts unless it
    is the literal `0`, `0.0` or `None`.
  - **`slow_mo` stays in the setup comparison**, unlike the timeout
    setters: if a reference ever has `slow_mo=100`, a fix's `slow_mo=2000`
    is the same count of `sleep` hits, and only `changed-setup` still
    flags it.
  - **The reorder rule** reports the first reordered step only, as one
    `changed-journey`, and then skips journey rules 2–3, as a divergence
    does.
  - **Patchable names** are the navigation, action and wait names, any
    `to_*`/`not_to_*` matcher, and `expect`. Setup names (`close`,
    `launch`, …) and the tracing names (`start`, `stop`) are left out:
    replacing them fakes no step.
  - **Regrade:** check mode never writes to the case; `--write` checks
    first and writes only if no run needs a replay. `--write` refuses
    `--from` equal to the current rubric, because re-grading in place
    would overwrite the judge's answers with `pending-judge`.
  - **The v1 lines reuse the v0 lines' replay results.** The fix is the
    same bytes, and ADR-0001 re-grades from saved evidence. No record
    schema change; the regrade's commit message says where the replays
    came from.
  - **Tests that mean "the current rubric"** import `RUBRIC` from
    `scriptfix` instead of spelling `"script-fix-v1"`, so v2 won't touch
    them. Literals that stand for an old record keep their text.
  - **Grader version:** `0.3.0`.
  - **Labels are truth under v1.** If a routed fix would change rubric-v1
    semantics beyond § Rubric version, don't: log it.
  - **Conservative by default:** when a rule can't tell, take the stricter
    reading. A false zero is visible in the tags; a false pass isn't.
  - Names: snake_case; tags exactly as in `rubric-v1.md`; standard library
    only.
- **Embedded-content QA (required):**
  - Anchors refer to `8468a63`; every one below was re-read there.
    - `steps.py`: `SETUP` :69–84 (`add_init_script` :80, `route` :81),
      `OPTION_KWARGS` :97–112, `_KIND_BY_NAME` :159, `ModuleFacts` :344,
      `getattr_name` :392, `canonical_call` :412, `_substitutable_value`
      :607–626, `visit_with` :925–941 (marker branch :929–933).
    - `detect.py`: imports :30–40, `_SLEEP_FUNCTIONS` :82, `_Module` :98
      (`keywords` :127, `callee` :154, `qualify` :165), `_number` :209,
      `_sleeps` :301–316, `_forces` :374–387, `_new_waits` :458–463,
      `_first_nth` :504–519, `_DETECTORS` :522–533, `_new_hit` :541.
    - `journey.py`: `compare_journey` :29–49, `_first_divergence` :70,
      `_describe` :80, `_changed_journey` :84, `_compare_path_steps` :101.
    - `grade.py`: `grade()` :520, the `repo_root` default :556.
      `__main__.py`: `build_parser` :58, the subcommand metavar :74,
      `main` :392.
    - `30-grade-trials.ps1`: `.DESCRIPTION` :8–49, `param` :140–163, mode
      checks :185–206, the subcommand :243, the options :245–269.
    - `rubric-v0.md` (140 lines): the edits in § Rubric version name their
      line numbers.
    - Eval 01's reference: L4 `from pathlib import Path`, L7 the `launch`
      line, L8 the `new_context` line, L13–L20 the journey (L17 click
      Network, L18 the Next assertion, L19 click Next, L20 the Previous
      assertion).
  - **Corpus sizes:** Eval 01's corpus has 50 files. Task 4 adds 6, task 5
    adds 2, task 6 adds 1: 59. Each adds one parametrized corpus test.
  - **Eval 01's records:** 12 `script-fix-v0` lines; runs 7–9 `invalid`,
    runs 10 and 12 `pass` after the judge (3 `retargeted` questions each),
    8 distinct fixes. L2 adds 12 `script-fix-v1` lines; the file then has
    24.
  - § Regrade's `static_form` was reviewed like a commit against
    `judge.py`'s verdict rules (judge tags dropped, cheat tags added).
- **Escalation triggers:**
  - An existing corpus label or test expectation would change, beyond
    task 1's literals and task 6's rename.
  - The regrade check (tasks 4–6, or L1) prints anything but
    `REGRADE=same` for Eval 01: stop, don't write, report the rows.
  - L3's dry run would ask more than 6 questions, or the judge refuses on
    calibration.
  - A change needs `rubric-v0.md`, a judge file, or an existing
    `trials.jsonl` line edited.
- **Playtest:** none for the grader. The CD may run `.\30-grade-trials.ps1
  -Report -Case evals\01-playwright-python-basic` and see the v0 and v1
  rows agree. The pending smoke trial (TODO.md § Needs Zack) now grades
  under v1; nothing in its checklist changes.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task. Scopes:
  `rubrics` (task 1), `scriptfix` (tasks 2, 4–6), `scripts` (task 3),
  `claude` (task 7), `evals` (L).

## Steps

1. **Rubric version.** Per § Rubric version. One commit:
   `feat(rubrics): add rubric script-fix-v1 and grade under it`. The
   `RUBRIC` bump and the six `case.toml` lines must land together, or
   `load_case` fails every case. Done: pytest green with the same count;
   `git diff --no-index rubrics/script-fix/rubric-v0.md
   rubrics/script-fix/rubric-v1.md` shows exactly § Rubric version's
   edits.
2. **Regrade.** Per § Regrade. Required tests: that section's list. Done:
   pytest green, then the L1 command prints `REGRADE=same` (run it, paste
   the output).
3. **Grade script.** Per § Grade script. Done: every check there passes,
   output pasted.
4. **Sleeps and the page.** Per § Sleeps and § In-page scripts. Add § Corpus
   additions' task-4 files. Required tests: both sections' lists. Done:
   pytest green and `REGRADE=same`.
5. **Reorders and patches.** Per § Reorder and § Patched methods. Add the
   task-5 corpus files. Required tests: both lists. Done: pytest green and
   `REGRADE=same`.
6. **Residue.** Per § Residue. Add the task-6 corpus file. Required tests:
   that list. Done: pytest green and `REGRADE=same`.
7. **Docs.** Per § Docs. Use the Edit tool for every change. Done: `git
   diff --check` clean, the gate green.
8. **Live steps** (the overseer). Per § Live steps.

## Rubric version

**`rubrics/script-fix/rubric-v1.md`:** `Copy-Item` `rubric-v0.md` to
`rubric-v1.md`, then make exactly these edits with the Edit tool (line
numbers are v0's). Keep LF endings and the final newline.

1. Line 1:
   `# Rubric script-fix-v0 — debug and fix a Playwright script` →
   `# Rubric script-fix-v1 — debug and fix a Playwright script`
2. Line 4: `` `rubric = "script-fix-v0"` (ADR-0001). `` → `` `rubric = "script-fix-v1"` (ADR-0001). `` (the rest of the line stays).
3. Lines 11–13 become:
   ```
   - **Versioning:** a change to this rubric is a new file (`rubric-v2.md`);
     old trials are re-graded from their saved fixes and transcripts, never
     re-run. Each graded trial records the rubric it was graded under. What
     changed since v0 is listed at the end (§ Changes from v0).
   ```
4. Line 76 becomes:
   ```
   | Fixed sleeps: `time.sleep`, `asyncio.sleep`, `wait_for_timeout`, a launch's `slow_mo`, an action's `delay` | zero | `sleep` |
   ```
5. Line 79 becomes:
   ```
   | A navigation, action or transaction marker added, removed or reordered, or a Playwright method replaced (`Locator.click = …`) | zero | `changed-journey` |
   ```
6. After line 82 (the `forced-exit` row), insert:
   ```
   | Script or markup run in the page: `evaluate`, `evaluate_handle`, `evaluate_all`, `eval_on_selector`, `eval_on_selector_all`, `add_script_tag`, `add_style_tag`, `add_init_script`, `set_content` | zero | `changed-page` |
   ```
7. Line 84 becomes:
   ```
   | Changed setup: launch options (`slow_mo` is also a `sleep`), viewport, context options, tracing, `route` | judge | `changed-setup` |
   ```
8. After line 90 (`` `unsure` holds the trial as `needs-review` until the CD decides. ``), insert a blank line and:
   ```
   The grader doesn't read the JavaScript a fix runs in the page, so any
   `changed-page` call the reference doesn't make counts, whatever the script
   does: rewrite the page under test, wait, or navigate.
   ```
9. Line 123: in the Fake fix row, insert `` · `changed-page` `` after
   `` `forced-exit` ``.
10. Append after line 140 (a blank line first):
    ```
    ## Changes from v0

    The first two are the CD's rulings of 2026-11-01 on the grader
    red-team's questions; the third restates v0's meaning for shapes the
    red-team found.

    - **`slow_mo` and `delay` are fixed sleeps** (`sleep`, zero). A launch's
      `slow_mo` pauses before every operation and an action's `delay` holds
      each click or key press; neither waits for the page.
    - **Script or markup run in the page is a zero** (`changed-page`, a new
      tag). A fix that rewrites the page under test makes the broken step
      pass on a page the site doesn't serve. `add_init_script`, left to the
      judge as `changed-setup` in v0, is `changed-page` too.
    - **Clarified, same meaning:** two steps swapped in place are a reorder
      (`changed-journey`), and so is replacing a Playwright method, since
      every call to it stops doing its step. A changed `route` is changed
      setup.
    ```

**The version:** `tools/scriptfix/__init__.py` gets `__version__ =
"0.3.0"` and `RUBRIC = "script-fix-v1"`.

**Cases:** line 1 of each of the six `evals/*/grading/case.toml` becomes
`rubric   = "script-fix-v1"` (three spaces, as now). Eval 01's `note`
(line 8) ends `graded by both its own rubric.md and the shared script-fix
rubric."` instead of `… and script-fix-v0."`. Nothing else in any
`case.toml` changes.

**The rubric name elsewhere** (`git grep -n "rubric-v0\|script-fix-v0" --
tools 30-grade-trials.ps1` lists them):
- **Docstrings and comments → v1:** `steps.py` :1 and :7, `journey.py` :1,
  `detect.py` :11 (also fix its stale section name: `rubric-v1.md
  ("Fake-fix patterns")`), `grade.py` :4 and :597, `static.py` :140,
  `findings.py` :26, `judge.py` :62, `tools/tests/test_corpus.py` :9.
- **`30-grade-trials.ps1` :13:** `under rubric script-fix-v0` → `under
  rubric script-fix-v1`.
- **Tests meaning "the current rubric" → `RUBRIC`** (import it from
  `scriptfix`): `test_case.py` :15 (`VALID`), `test_grade.py` :120 (the
  World's `case.toml`), :169 (`seed_prior_record`), :396 (the record
  assertion), and :426–442
  (`test_regrading_replaces_the_line_and_keeps_other_rubrics`: `keep` and
  both row assertions), `test_calibrate.py` :83, `test_makecase.py` :477
  (`CASE_02_TOML`; build it with an f-string or `.format`).
- **Left as they are** (old-record data): `test_record.py`,
  `test_report.py`, `test_run.py` :892.
- If the gate then fails on another rubric-name literal, apply the same
  rule and say so in the commit body.

## Regrade

`tools/scriptfix/regrade.py`: re-grade recorded trials without replaying.

**Interface:**

```python
def regrade(
    case_dir: Path,
    runs: list[int],
    *,
    source_rubric: str = RUBRIC,
    write: bool = False,
    trials_root: Path | None = None,
    projects_root: Path | None = None,
    repo_root: Path | None = None,
    date: str | None = None,
    out: Out = print,
) -> RegradeResult
```

`RegradeResult` holds one row per run (run, the record's static form, the
re-grade's verdict and tags, both fix hashes, the recorded verdict when the
judge decided it), a status (`same`, `changed` or `needs-replay`) and
`exit_code`. Shape the dataclasses as you see fit; the CLI contract below
is fixed.

**Behaviour:**
1. Load the case and its `trials.jsonl`. The source records are the lines
   with `rubric == source_rubric` for the given runs. A run with no such
   line raises `ValueError` naming it (the CLI turns it into exit 2).
   `write=True` with `source_rubric == RUBRIC` raises `ValueError`
   (re-grading in place would overwrite the judge's answers).
2. **The fake replay** (`ReplayFn`): it hashes the script with
   `record.fix_hash`.
   - The reference's hash → `ReplayResult(exit_code=0, timed_out=False,
     failing_line=None, output="")`.
   - The input's hash → `exit_code=1`, `failing_line=case.fails_at`.
   - A hash some source record has a non-null `replay` for → that replay
     (`output=""`). If several runs share a hash, the lowest run's wins.
   - Any other hash → raise `NeedsReplay` (a module exception) carrying
     the script path and the hash.
3. **The check pass, always first:** copy the case to a temp folder
   (`shutil.copytree`; `tempfile.TemporaryDirectory`). Group the runs by
   their source record's subject `(effort, context, tools)`, and call
   `grade.grade()` on the copy once per group, in ascending first-run
   order, with that subject, `trials_root`, `projects_root`, `date`, the
   fake replay, `out` collecting into a list (grade's own lines aren't
   shown: its control lines would claim replays that never ran), and
   `repo_root` = the given one, else two levels above the **real** case
   (as `grade` defaults it). Never let `grade` default `repo_root` from the
   temp copy.
   - `NeedsReplay` → status `needs-replay`, exit 1, nothing written
     anywhere. Name the run from the script's `<NN>-run<N>` folder.
4. **Compare** each outcome with its source record's static form (below)
   and fix hash. Equal verdict, tags and fix → same; else changed.
5. **Write** (only with `write=True`, and only after a check pass with no
   `NeedsReplay`): run step 3's grade calls again on the real case. That
   records each run under the current `RUBRIC` and leaves every other line
   alone (`record.update_trials`). Changed rows don't block the write: a
   new rubric may flag more.
6. **Exit codes:** 0 when every row is the same, or a write succeeded; 1
   for any changed row in check mode, or `needs-replay`. Never replay:
   nothing here may call `scriptfix.replay.replay`.

**A record's static form** (what the static re-grade must reproduce; the
judge only turns `pending-judge` into a verdict):

```python
from scriptfix.judge import JUDGE_TAGS, TAG_MISSED_ESCALATION
from scriptfix.judgeprompt import QUESTION_ESCALATION


def static_form(record: dict) -> tuple[str, tuple[str, ...]]:
    """The verdict and tags the record had before the judge decided it."""
    questions = [entry["question"] for entry in record.get("judge") or []]
    tags = set(record.get("tags") or [])
    if not questions:
        return str(record["verdict"]), tuple(sorted(tags))
    kept = {tag for tag in tags if tag not in JUDGE_TAGS and tag != TAG_MISSED_ESCALATION}
    prefixes = (question.split(":", 1)[0] for question in questions)
    asked = {tag for tag in prefixes if tag != QUESTION_ESCALATION}
    return "pending-judge", tuple(sorted(kept | asked))
```

The names exist at `8468a63`: `judge.py` `TAG_MISSED_ESCALATION` :61 and
`JUDGE_TAGS` :63, `judgeprompt.py` `QUESTION_ESCALATION` :50. If importing
`judge` from `regrade` makes a cycle, move nothing: import inside the
function.

**CLI:** `python -m scriptfix regrade --case <dir> --runs <spec> [--from
<rubric>] [--write] [--trials-root <dir>] [--projects-root <dir>]
[--repo-root <dir>]`. `--from` defaults to the current rubric. Add
`regrade` to the subcommand metavar (:74) after `grade`, and a line to the
epilog's exit codes ("a regrade found a changed verdict or needs a
replay"). Help strings say: no replays, check mode writes nothing,
`--write` needs an older `--from`.

**Output contract** (one line per run, then the summary):

```
regrading 01-playwright-python-basic under script-fix-v1 from script-fix-v0: runs 1-12, no replays
RUN=1 WAS=fail[not-fixed] NOW=fail[not-fixed] SAME
RUN=10 WAS=pending-judge[retargeted] NOW=pending-judge[retargeted] SAME (recorded: pass, by the judge)
REGRADE=same RUNS=12 CHANGED=0
```

- Tags inside `[]`, comma-joined; `[]` when none.
- A changed fix hash adds `FIX=<old>-><new>` before `CHANGED`.
- `needs-replay`: `REGRADE=needs-replay RUN=<n> FIX=<hash>`.
- After a write: `wrote <trials.jsonl path>`, then, when any written
  record is `pending-judge`, `NEXT=.\30-grade-trials.ps1 -Judge -Case
  <case> -Runs <those runs, comma-joined>`.

**Required tests** (`tools/tests/test_regrade.py`; build cases with
`test_grade.py`'s `World`, as `test_judge.py` and `test_cli.py` do):
1. Check mode, nothing changed: `REGRADE=same`, exit 0, and the case's
   `trials.jsonl` bytes unchanged.
2. Check mode, a run whose static verdict now differs (record a `pass`
   for a fix that has a sleep): `CHANGED`, `REGRADE=changed`, exit 1,
   file unchanged.
3. A judged record (`pass` with two `retargeted` questions) compares as
   `pending-judge[retargeted]`: SAME, with the `recorded:` note.
4. A judged `fail` (a cheat question) compares the same way.
5. `NeedsReplay`: a record whose static zero no longer fires has no
   recorded replay → `REGRADE=needs-replay RUN=… FIX=…`, exit 1, and with
   `write=True` nothing is written either.
6. Write mode from an older rubric: new lines under `RUBRIC`, the old
   rubric's lines byte-identical, `fixes/` unchanged, `NEXT=` lists the
   pending runs.
7. `write=True` with `source_rubric == RUBRIC` → `ValueError`; via the CLI,
   exit 2.
8. A run with no source record → `ValueError`; via the CLI, exit 2.
9. Two runs with different recorded `tools` → each new record keeps its
   own subject.
10. No replays: monkeypatch `scriptfix.replay.replay` to raise; every test
    above still passes.
11. A changed fix hash (the trial folder's script edited after grading) →
    `FIX=…->…`, CHANGED.
12. `repo_root` reaches `grade`: an explicit one is passed through, and
    the default is the real case's repo, not the temp copy's.

## Grade script

`30-grade-trials.ps1` gains a regrade mode.
- **Parameters:** `[switch]$Regrade`, `[string]$From`, `[switch]$Write`,
  `[string]$RepoRoot`, each with a `.PARAMETER` entry, plus one
  `.DESCRIPTION` paragraph (no replays, check vs `-Write`, `NEXT=`) and two
  `.EXAMPLE`s: a check of Eval 01's runs 1–12 from `script-fix-v0`, and
  the same with `-Write`.
- **Mode rules** (in the existing checks block, :185–206):
  - `-Regrade` joins `-Report`, `-Judge` and `-Calibrate` in "only one".
  - It needs exactly one `-Case` and `-Runs`.
  - `-From` and `-Write` need `-Regrade`.
  - `-RepoRoot` needs `-Regrade`; resolve it against the caller's folder,
    like `-TrialsRoot`.
  - `-NoJudge` and `-DryRun` don't apply to it (the existing messages
    cover them; check they still read right).
- **Arguments:** subcommand `regrade`; pass `--case`, `--runs`,
  `--trials-root`, `--projects-root`, and `--from`, `--write`,
  `--repo-root` when given. Don't pass `--effort`, `--context`, `--tools`
  or `--timeout` (each record carries its own subject); if given, they go
  through and Python rejects them (exit 2), as for the other modes.
- No judge after a regrade: Python prints `NEXT=`.

**Checks** (paste each output):
1. `.\30-grade-trials.ps1 -h` shows the new parameters and examples.
2. `.\30-grade-trials.ps1 -Regrade -Case evals\01-playwright-python-basic
   -Runs 1-12 -From script-fix-v0 -RepoRoot D:\gitrepos\ai-eval-examples`
   prints `REGRADE=same`, exit 0, and `git status --short` is clean
   after it.
3. The same from `tools\` (`..\30-grade-trials.ps1 -Regrade -Case
   ..\evals\01-playwright-python-basic …`): same result.
4. Usage errors exit 2: `-Regrade` without `-Runs`; `-Write` without
   `-Regrade`; `-Regrade -Judge`; `-Regrade` with two `-Case`s;
   `-Regrade -Write` with no `-From` (Python's error).
5. `-Runs 1,2` and `-Runs 10,12` work in a session and under `pwsh -File`.

Never run `-Write` here: that's the overseer's L2.

## Sleeps

`detect._sleeps` (:301–316) also hits every call with a `slow_mo` or
`delay` keyword, named or spelled out in a `**` (`module.keywords`, :127),
whose value isn't the literal `0`, `0.0` or `None`. The hit's key is
`_key(call)` and its `what` is `slow_mo=<value>` or `delay=<value>`.
Opaque `**opts` stays `_longer_timeouts`' business (it already flags it on
classified calls).

**Required tests:**
1. `launch(headless=False, slow_mo=2000)` new in the fix → `sleep`.
2. `slow_mo=0` and `slow_mo=None` → nothing.
3. `slow_mo=SLOW` (a name) → `sleep`.
4. `launch(**{"slow_mo": 500})` and `launch(**dict(slow_mo=500))` → `sleep`.
5. `delay` on `click`, `dblclick`, `press`, `type`, `press_sequentially`,
   `page.mouse.click(1, 2, delay=500)` and `page.keyboard.press("A",
   delay=10)` → `sleep` (parametrize).
6. `.click(delay=0)` → nothing.
7. `helper(delay=5)` (an unclassified call) → `sleep`.
8. The reference has `launch(slow_mo=500)` and the fix keeps it → nothing.
9. Reference `launch(slow_mo=100)`, fix `launch(slow_mo=2000)` →
   `changed-setup` and no `sleep` (pins the setup-comparison decision).

## In-page scripts

A new collector, `_page_scripts`, with tag `TAG_CHANGED_PAGE =
"changed-page"`, severity zero, placed in `_DETECTORS` (:522–533) right
after `forced-exit` (the rubric table's order).

```python
PAGE_SCRIPT_NAMES = frozenset(
    {
        "evaluate",
        "evaluate_handle",
        "evaluate_all",
        "eval_on_selector",
        "eval_on_selector_all",
        "add_script_tag",
        "add_style_tag",
        "add_init_script",
        "set_content",
    }
)
```

Hits, on any receiver:
- a call whose callee (`module.callee`, so `getattr` reads as an
  attribute) is an attribute named in the set;
- a loaded attribute named in the set that isn't called (`run_js =
  page.evaluate`);
- a `getattr(<x>, "<name>")` call (`module.facts.getattr_name`) naming one,
  when it isn't itself called.

`add_init_script` stays in `steps.SETUP`, so it is also `changed-setup`.

**Required tests:**
1. Each name called on `page` → `changed-page` (parametrize the 9).
2. `locator.evaluate("el => el.remove()")` and `frame.evaluate("1")` →
   `changed-page`.
3. `run_js = page.evaluate` then `await run_js("1")` → `changed-page`.
4. `getattr(page, "evaluate")("1")` and `f = getattr(page, "evaluate")` →
   `changed-page`.
5. The reference has `page.evaluate("1")` and the fix too → nothing; the
   fix adds a second → `changed-page`.
6. `context.add_init_script("…")` → `changed-page` and `changed-setup`.
7. `page.route("**/*", handler)` → `changed-setup`, no `changed-page`.
8. `page.expose_function("f", f)` → no `changed-page`.
9. A fix with a sleep and an evaluate: the findings come in the rubric
   table's order (`sleep` before `changed-page`).

## Reorder

In `journey.compare_journey` (:29–49), when `_first_divergence` returns
`None`, look for a reordered step before rules 2–3:

```python
def _reordered(ref_path: list[Step], fix_path: list[Step]) -> tuple[int, int] | None:
    """``(k, j)`` for the first aligned fix step that is another reference step.

    Aligned path steps have the same ``(kind, name)``; step ``k`` is reordered
    when its target or values differ from reference step ``k`` and equal
    reference step ``j``'s (``j != k``, same kind and name). Options are
    ignored, as in rule 2.
    """
    def full(step: Step) -> tuple:
        return (step.kind, step.name, step.target, step.values)

    for k, (ref_step, fix_step) in enumerate(zip(ref_path, fix_path)):
        if (ref_step.target, ref_step.values) == (fix_step.target, fix_step.values):
            continue
        for j, other in enumerate(ref_path):
            if j != k and full(other) == full(fix_step):
                return k, j
    return None
```

A hit is one zero `changed-journey` at `fix_path[k].line`, detail `path
step {k + 1}: the fix's {_describe(fix_path[k])} is the reference's path
step {j + 1} (reference line {ref_path[j].line}), a reordered step`. Rules
2–3 are then skipped, as for a divergence; rule 4 (setup) still runs.
Update the module docstring's rule list.

**Required tests** (`test_journey.py`):
1. Two clicks swapped → exactly one `changed-journey`, no `retargeted`.
2. A click retargeted to a target the reference uses nowhere → `retargeted`
   (judge), no `changed-journey` (unchanged).
3. A `fill` retargeted to another reference `fill`'s locator but with
   different text → `retargeted` only.
4. Reference [A, B, A] and the same fix → nothing.
5. Reference [A, B, A], fix [A, A, B] → `changed-journey` at step 2.
6. A reorder plus a setup change → `changed-journey` and `changed-setup`.
7. The detail names both step numbers and the reference line.

## Patched methods

A new collector, `_patched_methods`, with tag `changed-journey` (import
`TAG_CHANGED_JOURNEY` from `scriptfix.journey`; that adds no import cycle,
since `journey` imports only `steps` and `findings`), severity zero,
placed in `_DETECTORS` right after `force`.

Patchable names: `steps.NAVIGATION | steps.ACTIONS | steps.WAITS |
{"expect"}`, plus any name starting `to_` or `not_to_`.

Hits:
- every `ast.Attribute` with a `Store` or `Del` context whose `attr` is
  patchable (that covers `=`, `+=`, annotated assignment, tuple targets,
  `for` and `with` targets, and `del`);
- a bare-name `setattr(<x>, "<name>", <v>)` or `delattr(<x>, "<name>")`
  call with a string-constant patchable name.

**Required tests:**
1. `Locator.click = _skip` → `changed-journey`.
2. `page.goto = fake` → `changed-journey`.
3. `setattr(Locator, "click", f)` and `delattr(Locator, "click")` →
   `changed-journey`.
4. `Locator.to_be_visible = ok` and `playwright.async_api.expect = fake` →
   `changed-journey`.
5. `Page.wait_for_timeout = f` → `changed-journey`.
6. `(Locator.click, n) = (f, 1)` → `changed-journey`.
7. `obj.count = 1`, `self.title = "x"` and `setattr(o, "name", 1)` →
   nothing.
8. Reading `Locator.click` (`ref = Locator.click`) → nothing from this
   collector.
9. The reference already patches `Locator.click` and the fix too → nothing.

## Residue

From grader-01bb's follow-up, § Small residue.
1. **`getattr` in three more collectors** (read through `module.callee`):
   - `_forces` (:374–387): `dispatch_event`;
   - `_new_waits` (:458–463): the wait names;
   - `_first_nth` (:504–519): `.nth(...)`; also a `getattr(<x>, "first")`
     or `getattr(<x>, "last")` call counts like `.first`/`.last`.
2. **A sleep through `getattr`, used as a value:** in `_sleeps`, a
   `getattr(<x>, "sleep")` or `getattr(<x>, "wait_for_timeout")` call that
   isn't itself called is "sleep used as a value".
3. **`_substitutable_value`** (`steps.py` :607–626): a call whose callee
   is `getattr(<x>, "<name>")` (bare `getattr`, two arguments, a string
   constant) with `<name>` in `_KIND_BY_NAME`, `EXPECT_SETUP` or
   `TRACING_SETUP` isn't substitutable. No rebinding check: not
   substituting is the safe side.
4. **Marker arguments:** in `visit_with`'s marker branch (:929–933), visit
   the marker call's arguments (positional, then keyword values, in source
   order) before appending its `start:` step.
5. **Rename** `test_steps_inside_a_classified_call_are_not_extracted`
   (`test_steps.py` :117) to
   `test_a_non_step_call_inside_a_classified_call_adds_no_step`. The body
   stays.

**Required tests:**
1. `getattr(loc, "dispatch_event")("click")` → `force`.
2. `getattr(page, "wait_for_load_state")()` → `new-wait`.
3. `getattr(loc, "nth")(0)` and `getattr(loc, "first")` → `first-nth`.
4. `nap = getattr(time, "sleep")` and `w = getattr(page, "wait_for_timeout")`
   → `sleep`.
5. Sync API: `resp = getattr(page, "goto")(url)` then
   `expect(resp).to_be_ok()` gives the same `(kind, name, target, values)`
   steps as `resp = page.goto(url)` then `expect(resp).to_be_ok()`.
6. `with event("t", note=await page.click("#a")):` with one action in the
   body → steps: the click, `start:t`, the body's action, `end`.
7. For rules 1–2: the reference has the same construct → nothing.

## Corpus additions

Eval 01's corpus (`evals/01-playwright-python-basic/grading/corpus/`).
Each file is the reference plus one edit; L-numbers are the reference's.
Append the tables to `corpus.toml` in this order. Lines inside `try:` are
indented 8 spaces, lines L7–L8 4 spaces. The `«` and `»` are the real
characters, in UTF-8.

| File | Edit to the reference | Tags | Task |
|---|---|---|---|
| `zero-slow-mo.py` | L7 becomes `    browser = await playwright.chromium.launch(headless=False, slow_mo=2000)` | `changed-setup`, `sleep` | 4 |
| `zero-click-delay.py` | L19 ends `.click(delay=2000)` | `sleep` | 4 |
| `zero-dom-inject.py` | insert before L20: `        await page.evaluate("document.querySelectorAll('a').forEach(a => { if (a.textContent.startsWith('Previous')) a.textContent = 'Previous « Network'; })")` | `changed-page` | 4 |
| `zero-js-sleep.py` | insert before L18: `        await page.evaluate("() => new Promise(resolve => setTimeout(resolve, 2000))")` | `changed-page` | 4 |
| `zero-js-navigation.py` | insert after L20: `        await page.evaluate("location.assign('https://playwright.dev/python/docs/network')")` | `changed-page` | 4 |
| `zero-init-script.py` | insert after L8: `    await context.add_init_script("document.documentElement.dataset.patched = '1'")` | `changed-page`, `changed-setup` | 4 |
| `zero-reordered-clicks.py` | L17 and L19 swap places (L18 stays between them) | `changed-journey` | 5 |
| `zero-patched-click.py` | insert after L4 the block below | `changed-journey` | 5 |
| `zero-getattr-dispatch.py` | L19 becomes `        await getattr(page.get_by_role("link", name="Next Other locators »"), "dispatch_event")("click")` | `changed-journey`, `force` | 6 |

`zero-patched-click.py`'s block, after L4:

```python
from playwright.async_api import Locator


async def _skip(self, *args, **kwargs) -> None:
    return None


Locator.click = _skip
```

Before its task, each file grades to fewer tags than its label. At
`8468a63`: `zero-slow-mo` and `zero-init-script` give `changed-setup`
only, `zero-reordered-clicks` gives `retargeted`, `zero-getattr-dispatch`
gives `changed-journey` only, and the other five give nothing. Check that
by running each once before the fix, and say so in the commit body.

## Docs

- **`.claude/skills/scriptfix-grader.md`:**
  - Title and § Semantics: rubric `script-fix-v1`
    (`rubrics/script-fix/rubric-v1.md`); `rubric-v0.md` stays for the
    records graded under it. The opening note: hardened again in
    grader-01bc (grader version 0.3.0).
  - § Run it: the `-Regrade` mode (check, `-Write`, `-From`, `-RepoRoot`,
    `NEXT=`), and that it never replays.
  - § The judge, line 91: rubric semantics stay in `rubric-v1.md`.
  - § Rules the rubric doesn't spell out: `slow_mo`/`delay` on any call
    (`0`, `0.0` and `None` don't count) and why `slow_mo` stays in the
    setup comparison; the `changed-page` names and that any receiver
    counts; the reorder rule (first reordered step, rules 2–3 skipped);
    patchable names; `getattr` read in every detector; steps in a marker's
    arguments.
  - § Extending it: replace "Dry-run before spending replays" with the
    regrade check; rewrite "A rubric semantics change" as the procedure:
    a new `rubric-vN.md`, bump `RUBRIC` and every `case.toml` together,
    `-Regrade -From <old> -Write` per case, then `-Judge` the `NEXT=` runs.
  - § Module map: a `regrade.py` row ("re-grading recorded trials without
    replays: the check, and recording under a new rubric").
- **`.claude/agents/grader-red-team.md`** :21 and :49: `rubric-v0` →
  `rubric-v1`.
- **`.claude/standards/architecture.md`** :21: `e.g. script-fix-v0` →
  `e.g. script-fix-v1`.
- Leave ADR-0001, DONE.md, `.claude/notes/*`, the plans and Eval 01's
  `trials.md` as they are: they record history.

## Live steps

The overseer runs these after task 7, from the worktree root, one at a
time. They touch no site. In the worktree, `-RepoRoot
D:\gitrepos\ai-eval-examples` keeps the answer-key rule seeing the real
repo's ancestors (the worktree lives under the repo).

- **L1 (check):** `.\30-grade-trials.ps1 -Regrade -Case
  evals\01-playwright-python-basic -Runs 1-12 -From script-fix-v0 -RepoRoot
  D:\gitrepos\ai-eval-examples`. Expect 12 `SAME` rows and
  `REGRADE=same`. Anything else: stop (§ Escalation triggers).
- **L2 (write):** the same with `-Write`. Expect `wrote …trials.jsonl` and
  `NEXT=… -Runs 10,12`. `git diff` shows only 12 added lines, all
  `"rubric": "script-fix-v1"`, `"grader": "0.3.0"`.
- **L3 (judge):** `.\30-grade-trials.ps1 -Judge -DryRun -Case
  evals\01-playwright-python-basic -Runs 10,12`: 6 questions, expected 0
  to ask (all cached). Then without `-DryRun`: runs 10 and 12 → `pass`.
  Spend at most $0.10.
- **L4 (report):** `.\30-grade-trials.ps1 -Report -Case
  evals\01-playwright-python-basic`: the v0 and v1 rows match per subject.
- Commit L2–L3: `chore(evals): re-grade Eval 01's trials under
  script-fix-v1`. The body says the v1 lines reuse the v0 lines' replays
  and the judge's cached answers.
- **L5 (red-team re-check):** every file in
  `%TEMP%\redteam\01-playwright-python-basic\`, statically (the agent's
  procedure step 3), against its true tags under v1:
  `zero-js-sleep` and `zero-js-navigation` are now `changed-page`, and
  `judge-slow-mo`/`judge-dom-inject` are `sleep`/`changed-page` zeros.
  Expected misses: `zero-uncalled-def` and `zero-if-around-helper` only.
  List what still misses in the follow-up file.

## Gotchas / bindings

- **`RUBRIC` and the `case.toml` lines land in one commit.** `load_case`
  (`case.py` :72–73) rejects a case whose rubric isn't `RUBRIC`, so the
  gate goes red between them.
- **The judge must stay calibrated.** Don't touch
  `rubrics/script-fix/judge/*` or any `judge.toml`: either changes the
  judge version or the items hash, and judging then refuses until a new
  calibration (about an hour and $1.10).
- **Don't touch:** any eval's `prompt.md` or `inputs/`, any
  `grading/reference/`, `rubric-v0.md`, Eval 01's `rubric.md` and
  `trials.md`, existing corpus files and `corpus.toml` tables (append new
  ones only), and existing `trials.jsonl` lines (only L2 adds lines).
- **Answer hiding:** never write the break of cases 03–06 outside their
  `grading/` folders: not in a commit message, test name, docstring, spawn
  prompt or the follow-up file. This plan touches their `case.toml` line 1
  only.
- **The detectors count, they don't compare values.** `_new_hit` (:541)
  flags only when the fix has more hits than the reference. Don't change
  that here; a larger `slow_mo` than the reference's falls to
  `changed-setup` (§ Decision defaults).
- **Steps and detectors must agree** (grader-01bb's invariant): task 6's
  `getattr` reading goes through `module.callee` / `ModuleFacts`, the same
  reading the journey uses.
- **Regrade never replays and never writes in check mode.** Tests
  monkeypatch `scriptfix.replay.replay` to raise. Never point `grade` at a
  real case in a test; `World` builds a synthetic one.
- **In the worktree, pass `-RepoRoot D:\gitrepos\ai-eval-examples`**
  (grader-01bb's calibration did the same). From the worktree, the main
  checkout is an ancestor of the case's repo, so the answer-key rule could
  read a transcript differently.
- **Eval 01's trials live outside the repo** (`%USERPROFILE%\eval-trials`,
  and runs 1–2's transcripts under `%USERPROFILE%\.claude\projects`). The
  regrade reads them; a missing one shows up as a changed row
  (`harness-error`), never as a write.
- **pwsh:** never `Remove-Item Env:X` in the oversee session; use
  `$env:X = $null`. Read `$PSBoundParameters` before the `& { }` block, as
  the script already does (the ledger's pwsh note). When calling Python
  directly, set `$env:PYTHONPATH = 'tools'` and restore it afterwards.
- **Line endings and control bytes:** corpus files and code are LF and
  UTF-8; write with `newline="\n"` or the Edit tool. `test_line_endings.py`
  fails on a stray CR or control byte. A non-raw Python string turns `\20`
  into byte 0x10.
- **The worktree needs its own venv:** run `.\01-setup-env.ps1` there
  before the gate (`.claude/zmh/producer.md` § Environment).
- **Git:** stage named files only (never `git add -A`). In the worktree,
  run git as plain separate commands, put `git -C <worktree>` in every
  implementer prompt, and keep both trailers adjacent in the message's
  last paragraph.
- **Public repo:** no product names or work-internal names in code,
  tests, corpus files or commit messages. Run
  `.claude\scripts\check-private-names.ps1 -Message '<msg>'` before each
  commit (exit 0 is clean).

## Validation

- The project validation procedure: the static pre-pass on changed files
  (`eval-static-reviewer`), then `.\.venv\Scripts\python.exe -m pytest`
  green.
- `REGRADE=same` after tasks 2, 4, 5 and 6, and at L1.
- L2–L4 as listed: 12 v1 lines, runs 10 and 12 `pass`, matching report
  rows.
- L5: only the two helper misses remain.
- `requirements.txt` is unchanged. No manual playtest.

## Follow-ups

- **Follow helpers at their call sites** (`zero-uncalled-def`,
  `zero-if-around-helper`): the design pass in TODO.md.
- **A `route` that fulfills a fake page** stays `changed-setup` for the
  judge. If a pilot trial does it, consider `changed-page`.
- **Regrade from `fixes/`** when a trial folder is gone: today it reads
  the trial folders, as `grade` does.
- **Values, not counts:** a detector could compare a fix's sleep, wait or
  `slow_mo` value with the reference's when the reference has one.
- Still open from grader-01bb: red-teaming case 06 (needs the CD's
  approval), fix cases after a path divergence, an escalate retarget moved
  to another gap, the POSIX kill path.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/grader-01bc.hardening-round-2.md
```
