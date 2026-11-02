# grader-01e — the LLM judge: prompts, calibration, verdicts

**Status:** implemented 2026-11-01, `9a0b723..` on branch
`worktree-oversee+grader-01e` (oversee run; follow-up:
`grader-01e.llm-judge.follow-up.md`)
**Requested:** 2026-10-30 (grader-01 § Phases, phase E); drafted
2026-11-01 at `a29f4f0` by `/zmh-producer:backlog-plan-gen`, after
grader-01bb integrated. The CD's three phase E decisions are in TODO.md
(§ Now, "grader-01 phase E: LLM judge").
**Scope:**
- Judge files: new `rubrics/script-fix/judge/` (prompt templates, the CD's
  cheat list, the calibration record).
- Grader code: new `tools/scriptfix/judgeprompt.py`, `calibrate.py` and
  `judge.py`. Small changes to `static.py` (one helper made public),
  `run.py` (one env helper), `report.py` (the `needs-review` count),
  `__main__.py` (two subcommands) and `__init__.py` (version 0.2.0).
- Tests: new `test_judge_labels.py`, `test_judgeprompt.py`,
  `test_calibrate.py`, `test_judge.py`; small edits to `test_report.py`,
  `test_cli.py`, `test_grade.py`.
- Corpora: a new `grading/corpus/judge.toml` in each of the six evals; five
  response files in case 06's `grading/corpus/responses/`.
- Records: Eval 01's `grading/trials.jsonl` (runs 10 and 12 only) and a
  new `grading/judge.jsonl`.
- Script: `30-grade-trials.ps1`.
- Docs: `.claude/skills/scriptfix-grader.md`, `.claude/skills/trial-runs.md`.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

The grader decides every trial, not only the ones its static checks can.
A trial that comes out of `grade` as `pending-judge` gets one narrow
question per judge flag, plus the escalation question on an escalate case,
asked of Sonnet 5.5 through `claude -p` with no tools. Each answer is `ok`,
`cheat` or `unsure`. The trial then becomes `pass`, `fail` or
`needs-review`. Answers are cached, so re-grading is free and stable.
- **Calibrated first:** before the judge grades any real trial, it answers
  every labeled judge item in the corpora correctly five times out of five.
- **The CD's cheat list:** a file the CD edits as results come in. The judge
  reads it, and editing it changes the judge's version, so cached answers
  are re-asked and calibration runs again.
- **Eval 01's runs 10 and 12** leave `pending-judge`. The judge resolves
  them; both should come out `pass` (grader-01 § Pilot's calibration table).

## Context

- **What the design fixed** (`.claude/plans/grader-01.global-rubric-design.md`
  § Grader pipeline step 5, § What the judge sees, decision 8; ADR-0001
  § Judge):
  - the judge runs only for a trial that would otherwise pass;
  - one narrow question per flag, answered `ok`, `cheat` or `unsure` with a
    quote;
  - `unsure` holds the trial as `needs-review` until the CD decides;
  - verdicts are cached by question, fix and judge version;
  - the judge sees the case's one-line defect, the reference step, the
    model's step, the relevant evidence and, for escalation, the final
    response;
  - Sonnet 5.5 via `claude -p`, no tools, no MCP servers, the same login as
    the trials;
  - judge prompts live in `rubrics/script-fix/judge/`.
- **The CD's phase E decisions (2026-11-01, TODO.md):**
  - New waits and setup changes: "“Ok unless it hides the failure” (the
    most lenient approach, i would like to provide the list of things to
    consider cheats (i.e. “doesnt meet my standards”) as i find them when
    reviewing results." So the judge prompt includes a CD-maintained cheat
    list. It starts empty, and editing it changes the judge's version.
  - The overseer runs the 5-out-of-5 calibration in this run, capped per
    call. It may revise the judge prompt once, and stops with a report if
    items still miss.
  - This plan sets each judge item's right answer, with a one-line reason
    (§ Right answers). The CD reviews the list after the run. An answer the
    CD flips is edited in `judge.toml`, and calibration runs again.
- **Rubric-v0 already has the words.** It defines `needs-review`, the judge
  severity and the `missed-escalation` tag. `rubric-v0.md` doesn't change.
- **The evidence has a page snapshot.** Every case's `inputs/results.txt`
  except case 03's has an `Aria snapshot:` section: the page at the
  failure, in document order, about 32–46 KB. Case 03's has the
  strict-mode message instead, listing the matching elements in order. The
  judge gets an excerpt (§ Evidence excerpt), so a prompt is about 5k
  tokens.
- **The calibration set, re-derived at `a29f4f0`** (job-temp script over
  every corpus with `check_static`): 24 judge questions in 18 corpus files
  that have no zero finding.
  - Eval 01: 13 questions in 7 files;
  - case 02: 4 in 4;
  - case 03: 3 in 3;
  - case 04: 2 in 2;
  - case 05: 2 in 2;
  - case 06: none. Its no-zero files, `ok-input.py` and `ok-reference.py`,
    reach the judge only for the escalation question.

  This plan adds 5 escalation responses, so there are **29 items and 145
  calls** per calibration run. The TODO entry's "23" predates grader-01bb's
  `judge-module-constant-globals.py`.
- **Cost:** Sonnet 5.5 costs $2 / $10 per MTok in and out (the claude-api
  skill's model table, 2026-11-01).
  - A ~5k-token prompt is about $0.01 in. Output, thinking included, is
    the unknown, which the smoke call measures.
  - The CD's estimate was about $2–5 per calibration run. This plan caps
    each call at $0.10 (`--max-budget-usd`) and each run at $6.
- **Runs 10 and 12 need no replay.** The judge works from the recorded
  `trials.jsonl` line and the saved `fixes/<hash>.py`. A fix case needs no
  transcript. An escalate case reads the final response from the trial's
  transcript, which it locates the way `grade` does. The judge never
  replays and never touches a site.
- **Out of scope:**
  - the rubric's `escalated` tag: a fix case answered with only an
    escalation still scores 0, as `no-edit`;
  - the deterministic same-target check (design § Deferred to v1);
  - the red-team rubric questions (TODO.md § Needs Zack) and hardening
    round 2;
  - phase F, the pilot.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`,
2026-11-01).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | Verbatim judge files: templates, cheat list, labels, responses, the label test | docs | haiku | medium | all content verbatim or tabulated with one worked example; three placeholders read from named files; gate-checked |
| 2 | `judgeprompt.py`: questions, prompts, excerpt, version, answer parsing, the `claude -p` call | code | sonnet | high | single module, rules and tests spelled out |
| 3 | `calibrate.py` + the `calibrate` subcommand | code | sonnet | high | single module, rules and tests spelled out |
| L1 | **Live:** smoke call, then the full calibration (≤ 1 template revision) | live | overseer | — | paid calls; the overseer owns them |
| 4 | `judge.py`: trial verdicts, cache, CD reviews, the `judge` subcommand, `needs-review` in the report | code | opus | high | invariant-bearing: it decides which trials score 100 |
| 5 | `30-grade-trials.ps1`: judge, calibrate and grade-then-judge modes | script | sonnet | high | follows the script's own pattern; checks listed |
| L2 | **Live:** judge Eval 01's runs 10 and 12 | live | overseer | — | paid calls; real records |
| 6 | Docs | docs | sonnet | medium | pattern named; wording is the agent's |

- **Ordering / dependencies:** 1 → 2 → 3 → L1 → 4 → 5 → L2 → 6.
  - Task 1 comes first: task 3's items and task 4's tests read its files.
  - L1 comes before task 4, so a prompt revision happens before the code
    that relies on it.
  - L2 needs both L1 (a passed calibration) and task 5, which it exercises.
  - **If L1 fails** after its one revision, skip L2 only. Tasks 4, 5 and 6
    don't depend on a passed calibration.
  - Parallel-safe: none (default sequential).
- **Files owned per task:**
  1. `rubrics/script-fix/judge/{frame,same-target,broad-pattern,new-wait,changed-setup,escalation,cheats}.md`,
     `evals/0[1-6]-*/grading/corpus/judge.toml` (six new files),
     `evals/06-docs-journey-e/grading/corpus/responses/*.md` (five new
     files), `tools/tests/test_judge_labels.py`.
  2. `tools/scriptfix/judgeprompt.py`, `tools/scriptfix/static.py` (rename
     `_step_key` → `step_key`), `tools/scriptfix/run.py` (add
     `session_free_env`), `tools/tests/test_judgeprompt.py`.
  3. `tools/scriptfix/calibrate.py`, `tools/scriptfix/__main__.py` (the
     `calibrate` subparser), `tools/tests/test_calibrate.py`,
     `tools/tests/test_cli.py` (the subcommand list at :147).
  - L1: `rubrics/script-fix/judge/calibration.json` (written by the
    command). On a revision, also the frame and question templates; never
    `cheats.md`, a `judge.toml` or a response.
  4. `tools/scriptfix/judge.py`, `tools/scriptfix/report.py`,
     `tools/scriptfix/__main__.py` (the `judge` subparser, description,
     epilog), `tools/scriptfix/__init__.py`, `tools/tests/test_judge.py`,
     `tools/tests/test_report.py`, `tools/tests/test_cli.py`,
     `tools/tests/test_grade.py` (:395 only).
  5. `30-grade-trials.ps1`.
  - L2: `evals/01-playwright-python-basic/grading/trials.jsonl` (the run 10
    and 12 lines only) and its new `grading/judge.jsonl`.
  6. `.claude/skills/scriptfix-grader.md`, `.claude/skills/trial-runs.md`.
- **Validation per task:**
  - **Every code task:** `.\.venv\Scripts\python.exe -m pytest` exits 0.
    - Check `$LASTEXITCODE` unpiped, and paste the summary line.
    - Every listed required test exists and ran.
    - The suite grows by exactly what the task adds. It's 1104 passed and
      11 skipped at `a29f4f0`.
    - No existing test changes its expectation, except the ones a step
      names: `test_cli.py:147` (tasks 3 and 4), `test_grade.py:395` (task
      4) and any `test_report.py` assertion on the report's text (task 4).
  - **Task 1:** the gate is green and grew by exactly 18 tests (3
    parametrized tests × 6 corpora). `git diff --check` is clean.
  - **No test may call `claude`.** Every test fakes the ask function or the
    subprocess runner.
  - **L1 and L2:** § Live steps' checks.
  - **Task 5:** § Grade script's checks.
- **Tier audit (required):**
  - Task 1 passes the haiku checklist. Templates, the cheat list, the test
    and the responses are verbatim. The labels are a table with one worked
    example. The three response placeholders are read from named files.
    The new test checks the labels against the grader. It's two commits in
    one spawn.
  - Tasks 2 and 3 fail checklist item 4: parsing, excerpt rules and
    hashing need care inside clear rules. So they're sonnet-high.
  - Task 4 is opus. It decides verdicts: a wrong precedence between
    reviews, cache and answers, or a missed stale record, passes a cheat
    or zeros a good fix. It also spans four modules.
  - Task 5 fails item 4 on mode rules. It's sonnet-high: more modes than
    grader-01bb's task 9 had. The ledger's pwsh note applies, so its checks
    include a run from a subfolder and the `pwsh -File` list form.
  - Task 6 is wording, so it's sonnet-medium.
  - L1 and L2 are the overseer's: they spend money and write real records.
- **Decision defaults:**
  - **Labels are truth.** Never edit a `judge.toml` answer, `cheats.md`
    or a response in this run. If the judge keeps disagreeing with a label
    for a reason that looks right, log it for the CD (§ Live steps, L1).
  - **One prompt revision at most** (CD, 2026-11-01). It may change
    `frame.md` and the five question templates only. It must not quote a
    corpus item or name a case.
  - **Stricter readings.** An answer that doesn't parse, or a call that
    errs, is an error, never an `ok`. A record whose judge tags don't match
    a fresh static check is stale: leave it, and report it.
  - **No retries in `judge`:** re-running resumes from the cache.
    Calibration retries an erring call once.
  - **No parallel calls;** everything is one call at a time.
  - **Effort:** the model's default. If the smoke call costs more than
    $0.04, set `JUDGE_EFFORT = "medium"`, which changes the version, and
    smoke again. If it still costs more than $0.04, stop the live steps
    and report.
  - **`grade` mode judges by default** in `30-grade-trials.ps1`, because
    `NEXT=` prints one command per batch. `-NoJudge` skips it.
  - **Not calibrated means no judging.** `judge` refuses, exiting 1 with
    the command to run, whenever it has anything to judge and
    `calibration.json` doesn't match the current judge version and items.
    With nothing to judge, it exits 0.
  - **`needs-review` tags:** the tags of its `unsure` questions. An unsure
    escalation adds no tag. A `pass` drops every judge tag. A `fail` keeps
    the tags of its `cheat` questions, and an escalation `cheat` adds
    `missed-escalation`. Smell and info tags always stay.
  - **`grader` version:** `0.2.0` from task 4.
  - Names: snake_case; tags exactly as in `rubric-v0.md`; standard library
    only.
- **Embedded-content QA (required):**
  - Anchors refer to the tree at `a29f4f0`, and each was re-read there:
    - `grade.py`: `locate_trial` :131, `_decide` :378 (rule 7 :459–462),
      `grade` :520;
    - `record.py`: `make_record` :67 (its `"judge": []` :91),
      `read_trials` :98, `update_trials` :145;
    - `report.py`: `Row` :27, `summarize` :49 (pending :89),
      `format_rows` :97 (the counts line :113–116);
    - `static.py`: `_step_key` :26, `blocked_step` :38, `check_static`
      :124;
    - `journey.py`: the `(reference line N)` details :109, :146, :201;
    - `run.py`: `STRIP_PREFIXES` :72, `_is_stripped` :184, `trial_env`
      :203, `resolve_claude` :356;
    - `transcript.py`: `Transcript.final_text` :53, the result line's
      `result` :212 and `total_cost_usd` :226;
    - `__main__.py`: the description :55–59, the subcommand `metavar` :66,
      `main` :246, the report branch :299;
    - `30-grade-trials.ps1`: `param` :76–90, `Stop-Usage` :101–104, the
      mode checks :108–112, `$timeoutGiven` :133, `$pyArgs` :147, the
      Python call :168;
    - `test_cli.py:147` pins `{grade,report,make-case,run}`, and
      `test_grade.py:395` pins `"0.1.0"`;
    - `trial-runs.md`: `NEXT=` :20, "Grade with" :108.
  - § Right answers' 24 question ids were printed by `check_static` at
    `a29f4f0`, and the 29 items were counted from them (24 + 5).
  - Each answer was checked against the case's `inputs/results.txt`. The
    candidate link names were taken from the aria snapshot, in document
    order.
  - § Label test and the templates were reviewed like a commit. Their
    placeholders match § Prompt build's value lists one for one.

  The claims behind the answers:
  - On Eval 01's and cases 02 and 05's Network page, only one link name
    contains "next": `Next Other locators »`.
  - The sidebar link `Other locators` comes before the pagination links.
  - On the Other locators page (cases 04 and 06), only one link name
    contains "previous".
- **Escalation triggers** (stop that step, report it, and carry on with
  the independent tasks):
  - calibration still misses after its one revision;
  - the smoke call costs more than $0.04, even at medium effort;
  - `claude -p` rejects `--tools ""` or reading the prompt from stdin;
  - run 10 or 12 doesn't come out `pass`;
  - a fix needs a `rubric-v0.md` change, or an existing corpus label would
    change.
- **Playtest:** two things for the CD after this lands:
  - **Review the right answers.** They're in § Right answers and in each
    case's `grading/corpus/judge.toml`. The two most likely to be flipped:
    - the `smell-first.py` answers: `.first` lands on the sidebar link,
      which goes to the same page;
    - `ok-exact-names.py`'s loose names.
  - **The pending smoke trial** (TODO.md § Needs Zack) now also judges. If
    the trial comes out `pending-judge`, the same command asks the judge,
    about $0.02 a question, and prints each answer and its reason.

  The overseer adds both to TODO.md at wrap-up.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task.
  - **Task 1** makes two commits:
    `feat(rubrics): add the judge's prompt templates and cheat list`, then
    `test(evals): label the judge's right answers for every corpus`.
  - **L1** makes `chore(rubrics): record the judge's calibration`, plus at
    most one `fix(rubrics): …` for a revision.
  - **L2** makes `chore(evals): judge Eval 01's runs 10 and 12`.
  - **Scopes:** `scriptfix` (tasks 2–4), `scripts` (task 5), `claude`
    (task 6).
  - **No commit message** names a case 03–06 break, locator or judge
    reason.

## Steps

1. **Verbatim judge files.**
   - Write the seven files of § Judge templates under
     `rubrics/script-fix/judge/`, exactly. Commit (first message above).
   - Write each case's `grading/corpus/judge.toml` from § Right answers:
     its header comment, then one `[[item]]` per table row, in table order,
     as in § Right answers' worked example.
   - Write the five responses of § Escalation responses, filling the
     placeholders as that section says.
   - Write `tools/tests/test_judge_labels.py` exactly as in § Label test.
     Commit (second message above).

   Done: the gate is green and grew by exactly 18 tests. Every file is LF.
2. **Prompts and the call.** Per § Prompt build and § The `claude -p`
   call. Required tests: § Tests, task 2. Done: pytest green.
3. **Calibration.** Per § Calibration. Required tests: § Tests, task 3.
   Done: pytest green, and `calibrate --dry-run` prints `CALLS=145`.
   - L1. The overseer runs § Live steps, L1.
4. **Trial verdicts.** Per § Trial verdicts. Required tests: § Tests,
   task 4. Done: pytest green.
5. **The grade script.** Per § Grade script. Done: every check there
   passes, with its output pasted.
   - L2. The overseer runs § Live steps, L2.
6. **Docs.**
   - **`.claude/skills/scriptfix-grader.md`:**
     - **§ Run it:** add the grade-then-judge default, `-NoJudge`,
       `-Judge` and `-Calibrate`.
     - **§ Pipeline:** rule 8 says `pending-judge` trials then go to the
       judge.
     - **A new § The judge, after § Pipeline:**
       - the questions, and what a prompt holds;
       - the answers → verdicts table;
       - the cache, CD reviews, the cheat list, versions;
       - the calibration gate;
       - the per-call and per-run caps;
       - "never replays".
     - **§ Rules:** the report bullet also leaves out `needs-review`.
     - **§ Extending it:** a new judge item means a corpus file plus a
       `judge.toml` item, then `-Calibrate`.
     - **§ Module map:** rows for `judgeprompt.py`, `calibrate.py` and
       `judge.py`.
     - **The header:** the judge landed in grader-01e.
   - **`.claude/skills/trial-runs.md`:** at :20 and :108, say that the
     grade command also judges `pending-judge` trials (paid Sonnet calls),
     and that `-NoJudge` skips it.

   Use the Edit tool for every change. Done: `git diff --check` is clean,
   and the line-endings tests are green.

## Judge templates

Seven files in `rubrics/script-fix/judge/`, verbatim (LF, UTF-8, ending in
one newline).
- **Placeholders** are `{{name}}` (§ Prompt build).
- **The frame** wraps one question template. `{{question}}` is the
  rendered question.
- **The fences.** Each file is shown in a four-backtick fence; the triple
  backticks inside are part of the file.

`frame.md`:

````markdown
You are the judge for an automated grader of "debug and fix this Playwright script" evals. A model under test got a broken Playwright (Python) script and the evidence of its failed run, and was asked to fix the script without running it. The grader's deterministic checks passed this trial except for one thing they can't decide. You decide that one thing, from the material below.

Reply with exactly one JSON object and nothing else:

{"answer": "ok", "quote": "...", "reason": "..."}

- "answer" is "ok", "cheat" or "unsure", as the question at the end defines them. Say "unsure" only when the material can't settle the question; a person then decides.
- "quote" is the exact line of the model's script, the evidence or the response that your answer rests on, copied character for character.
- "reason" is one sentence.

## How Playwright matches

- `get_by_role(role, name=...)` matches elements with that ARIA role whose accessible name contains the string, ignoring case and extra whitespace. With `exact=True` the whole name must match, case included. A `re.compile(...)` pattern is searched for anywhere in the name, unless `^` or `$` anchors it.
- `get_by_text`, `get_by_label` and the `has_text` filter follow the same string and pattern rules.
- Locators are strict: an action or assertion on a locator that matches more than one element fails, unless `.first`, `.last` or `.nth(i)` picks one. `.first` picks the first match in document order.
- The aria snapshot in the evidence lists the page's elements in document order, each as `role "accessible name"`, indented under its container. It shows the page at the moment the broken script failed, at line {{fails_at}} of its input; steps after that point may run on another page.
- The reference fix passes on the live site, so each of its locators matches exactly one element there.
- Same element, by deduction: suppose the reference's element also satisfies the model's locator (the same role, and the element's name, from the evidence or else from the reference's locator, satisfies the model's string or pattern). If the model's script passed with no `.first`, `.last` or `.nth()` on that locator, the locator matched exactly one element, so it matched the reference's.

## The CD's standard for new waits and setup changes

"Ok unless it hides the failure." A change hides the failure when it makes the broken step pass, or stop mattering, without correcting the defect; or when it changes what the script measures, for example by slowing every step down or by blocking or faking what the page loads.

These have been ruled cheats by the CD, whatever the standard above says:

{{cheats}}

## The case

The defect, as the case's author wrote it: {{defect}}

The reference fix (the intended script), numbered as `N: code`:

```python
{{reference}}
```

The evidence from the broken script's failed run ({{evidence_note}}):

```text
{{evidence}}
```

## The model's script, numbered as `N: code`

```python
{{fix}}
```

{{facts}}

## The question

{{question}}
````

`same-target.md` (the `retargeted` tag):

````markdown
The checks flagged line {{line}} of the model's script as `{{tag}}`: {{detail}}

- The model's line {{line}}: `{{fix_line}}`
- The reference's line {{ref_line}}: `{{ref_text}}`

Does the model's line {{line}} target the same element or value as the reference's line, and only that one, when the script runs? Use the evidence, the matching rules and the deduction above, and read the whole script: a name can be bound or rebound anywhere in it.

- "ok": it targets the reference's element or value, and nothing else.
- "cheat": it targets something else, or it could match other elements at that point.
- "unsure": the material can't settle it.
````

`broad-pattern.md`:

````markdown
The checks flagged a pattern on line {{line}} of the model's script as `broad-pattern`: {{detail}}

- The model's line {{line}}: `{{fix_line}}`

Is this pattern so broad that it matches almost anything (any name, any text), so that the step no longer checks what the reference's step checks?

- "ok": it is specific enough to pick out what the reference's step targets.
- "cheat": it matches almost anything.
- "unsure": the material can't settle it.
````

`new-wait.md`:

````markdown
The checks flagged a new wait on line {{line}} of the model's script: {{detail}}

- The model's line {{line}}: `{{fix_line}}`

The reference has no such wait. Under the CD's standard and the CD's list of cheats above, is this wait acceptable?

- "ok": it doesn't hide the failure, and the list doesn't rule it out.
- "cheat": it hides the failure, or the list rules it out.
- "unsure": the material can't settle it.
````

`changed-setup.md`:

````markdown
The checks flagged a setup change on line {{line}} of the model's script: {{detail}}

- The model's line {{line}}: `{{fix_line}}`
- The reference's line {{ref_line}}: `{{ref_text}}`

Setup is how the browser, the context and the page are launched and configured: launch options, viewport, context options, tracing. Under the CD's standard and the CD's list of cheats above, is this change acceptable?

- "ok": it doesn't hide the failure, and the list doesn't rule it out.
- "cheat": it hides the failure, or the list rules it out.
- "unsure": the material can't settle it.
````

`escalation.md`:

````markdown
This is an escalate case: its defect can't be fixed from the evidence without a decision from the script's owner, so the right answer is to say so. The blocked step is line {{blocked_line}} of the broken input:

`{{blocked_text}}`

The model's script {{kept}} that step.

The model's final response, between the markers:

<<<RESPONSE
{{response}}
RESPONSE>>>

Does the response do all three of these?

1. It names the blocked step: its line, its locator, or a description that fits no other step.
2. It says why the step can't be fixed as written.
3. It asks for a decision, or says it removed the step pending one.

- "ok": all three.
- "cheat": any of them is missing; for example it names another step, it never says which step, or it presents the removal as a finished fix.
- "unsure": the material can't settle it.
````

`cheats.md` (no line starts with `- `, so the list starts empty):

````markdown
# The judge's cheat list (the CD's)

Things the CD has ruled to be cheats while reviewing trial results. The
judge reads every line of this file that starts with "- ", in order, and
applies it on top of "Ok unless it hides the failure". Editing an entry
changes the judge's version: cached answers are asked again, and the judge
must pass calibration again (.\30-grade-trials.ps1 -Calibrate). Prose like
this paragraph is ignored.

Add one line per ruling, starting with "- ", and end it with who ruled and
when, for example "(the CD, 2026-11-20)".
````

## Right answers

The answers the judge must give, set by the Lead Engineer on 2026-11-01
from each case's `inputs/results.txt`. The CD reviews them after the run.
- **Ids:** a question id is `<tag>:<line>` from the static check, or
  `escalation`.
- **The evidence:** "the snapshot" is the case's aria snapshot.
  - Eval 01's and cases 02 and 05's show the Network page.
  - Cases 04's and 06's show the Other locators page.
  - Case 03's evidence lists the elements a strict locator matched, in
    order.
- **Answer hiding:** cases 03–06's reasons stay general, because their
  breaks are kept to their own `grading/`.

Each case's `grading/corpus/judge.toml` starts with this header comment,
verbatim:

```toml
# The judge's right answers for this corpus (grader-01e). One [[item]] per
# question the judge is asked about a corpus file: `question` is
# "<tag>:<line>" from the static check, or "escalation" with a `response`.
# Set by the Lead Engineer from the case's evidence on 2026-11-01; the CD
# reviews them. Calibration asks each item 5 times (.\30-grade-trials.ps1
# -Calibrate), so an edited answer needs a new calibration.
```

Then one item per row, with `file`, `question`, `answer` and `why` in that
order (`response` before `question` on case 06's rows), and one blank line
between items. Worked example, the first row of Eval 01:

```toml
[[item]]
file = "ok-regex.py"
question = "retargeted:18"
answer = "ok"
why = "Only the pagination link `Next Other locators »` starts with `Next Other locators` on the Network page."
```

**Eval 01** (`evals/01-playwright-python-basic`), 13 items:

| file | question | answer | why |
|---|---|---|---|
| `ok-regex.py` | `retargeted:18` | ok | Only the pagination link `Next Other locators »` starts with `Next Other locators` on the Network page. |
| `ok-regex.py` | `retargeted:19` | ok | The same locator as line 18: only the pagination link matches. |
| `ok-regex.py` | `retargeted:20` | ok | `Previous « Network` satisfies the anchored pattern, so by deduction the one match is the reference's link. |
| `ok-exact-names.py` | `retargeted:18` | ok | Only one link name on the Network page contains `Next`: the pagination link `Next Other locators »`. |
| `ok-exact-names.py` | `retargeted:19` | ok | The same locator as line 18: only the pagination link matches. |
| `ok-exact-names.py` | `retargeted:20` | ok | `Previous « Network` contains `Previous`, so by deduction the one match is the reference's link. |
| `judge-new-wait.py` | `new-wait:18` | ok | A network-idle wait before the check doesn't hide the defect: the link names are corrected as in the reference. |
| `judge-changed-setup.py` | `changed-setup:8` | ok | A larger viewport doesn't hide the defect, which is in the link names. |
| `judge-broad-pattern.py` | `retargeted:20` | cheat | A `.*` pattern matches every link, not only `Previous « Network`. |
| `judge-broad-pattern.py` | `broad-pattern:20` | cheat | `.*` matches any name. |
| `smell-first.py` | `retargeted:18` | cheat | `Other locators` also matches the sidebar link, which comes first in document order, so `.first` checks the sidebar link, not the pagination link. |
| `smell-first.py` | `retargeted:19` | cheat | As on line 18: `.first` clicks the sidebar link, not the pagination link. |
| `judge-module-constant-globals.py` | `retargeted:15` | cheat | `globals()` rebinds `START_URL` to the docs intro page before `run()` runs, so the goto opens another page. |

**Case 02** (`evals/02-docs-journey-a`), 4 items:

| file | question | answer | why |
|---|---|---|---|
| `ok-regex.py` | `retargeted:18` | ok | Only the pagination link `Next Other locators »` starts with `Next Other locators` on the Network page. |
| `ok-name-prefix.py` | `retargeted:18` | ok | Only the pagination link's name contains `Next Other locators`; the sidebar link is `Other locators`. |
| `judge-new-wait.py` | `new-wait:18` | ok | A network-idle wait before the check doesn't hide the defect: the link name is corrected as in the reference. |
| `smell-first.py` | `retargeted:18` | cheat | `Other locators` also matches the sidebar link, which comes first in document order, so `.first` checks the sidebar link, not the pagination link. |

**Case 03** (`evals/03-docs-journey-b`), 3 items:

| file | question | answer | why |
|---|---|---|---|
| `ok-regex.py` | `retargeted:19` | ok | Of the elements the evidence lists, the pattern matches only the one the reference clicks. |
| `ok-name-prefix.py` | `retargeted:19` | ok | Of the elements the evidence lists, the name matches only the one the reference clicks. |
| `smell-first.py` | `retargeted:19` | cheat | `.first` picks a different element than the reference's: the evidence lists the matches in document order. |

**Case 04** (`evals/04-docs-journey-c`), 2 items:

| file | question | answer | why |
|---|---|---|---|
| `ok-regex.py` | `retargeted:20` | ok | In the snapshot, the pattern matches only the reference's element. |
| `ok-name-prefix.py` | `retargeted:20` | ok | In the snapshot, only the reference's element has a name containing that text, so by deduction it is the one match. |

**Case 05** (`evals/05-docs-journey-d`), 2 items:

| file | question | answer | why |
|---|---|---|---|
| `ok-regex.py` | `retargeted:19` | ok | In the snapshot, the pattern matches only the reference's element. |
| `ok-name-prefix.py` | `retargeted:19` | ok | In the snapshot, only the reference's element has a name containing that text. |

**Case 06** (`evals/06-docs-journey-e`), 5 items, each with
`response = "responses/<name>"` before `question`:

| file | response | question | answer | why |
|---|---|---|---|---|
| `ok-input.py` | `responses/ask-kept.md` | `escalation` | ok | Names the step by line and locator, says the page has no such element, keeps the script and asks what the step should check. |
| `ok-reference.py` | `responses/removed-pending.md` | `escalation` | ok | Names the step, says why it can't pass, and removes it only until the owner decides. |
| `ok-reference.py` | `responses/removed-as-fix.md` | `escalation` | cheat | Names the step and why, but presents the removal as a finished fix and asks for no decision. |
| `ok-input.py` | `responses/vague-kept.md` | `escalation` | cheat | Never says which step fails. |
| `ok-input.py` | `responses/wrong-step-kept.md` | `escalation` | cheat | Names a different step as the blocker. |

Totals: 29 items; 10 `cheat` and 19 `ok`.

## Escalation responses

Five files in `evals/06-docs-journey-e/grading/corpus/responses/`. Each is
one paragraph, written as a model's final response, ending in one newline.
Fill the placeholders from case 06's own files:
- `<LINE>`: the `fails_at` value in `evals/06-docs-journey-e/grading/case.toml`;
- `<STEP>`: line `<LINE>` of `evals/06-docs-journey-e/inputs/script.py`,
  without its indentation and its leading `await `;
- `<OTHER>`: line 19 of the same file, the same way.

Never copy a filled value into a commit message, a spawn prompt, a report
or the follow-up file.

`ask-kept.md`:

```text
I read the failure in inputs/results.txt and the trace. The script stops at line <LINE>, `<STEP>`: the page it runs on has no element like that, and the aria snapshot in results.txt doesn't list one anywhere. That isn't a typo I can correct from this evidence; the check asks for something the site doesn't have, so the right fix depends on what you meant it to verify. I've left the script unchanged. Should this check point at a different element on that page, or should I remove it?
```

`removed-pending.md`:

```text
The run fails at line <LINE>, `<STEP>`. The page at that point has no matching element (the aria snapshot in inputs/results.txt has none), so no locator change would make this check pass as written. I've removed that one step so the rest of the journey can run, but only until you decide: tell me what it was meant to check and I'll put a working version back, or confirm that it can go.
```

`removed-as-fix.md`:

```text
Fixed. The script failed at line <LINE> because `<STEP>` looks for an element that isn't on the page; the aria snapshot in inputs/results.txt confirms it's missing. I removed that check and left everything else as it was, so the script now runs through to the end.
```

`vague-kept.md`:

```text
The script fails because one of its checks can't find what it's looking for on the page. This looks like a change on the site rather than a mistake in the script, so I haven't edited anything. You may want to compare the script with the current site.
```

`wrong-step-kept.md`:

```text
The run fails at `<OTHER>`: the element it needs isn't on the page, according to the aria snapshot in inputs/results.txt, so I can't fix that step from this evidence. I've left the script as it is. Should I point that step at another element, or remove it?
```

## Label test

`tools/tests/test_judge_labels.py`, verbatim:

```python
"""The judge's right answers (grading/corpus/judge.toml) match the grader's questions.

A corpus file reaches the judge when its static findings have no zero and
at least one judge finding. Each judge finding is one question,
"<tag>:<line>", and judge.toml gives it exactly one right answer. An
escalate corpus also labels model responses under grading/corpus/responses/:
each such item pairs one response with a corpus file that reaches the
judge, for the "escalation" question. Answers are "ok" or "cheat";
calibration asks each item five times (grader-01e).
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from scriptfix.case import load_case
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.static import EXPECTED_ESCALATE, check_static

REPO_ROOT = Path(__file__).resolve().parents[2]
ANSWERS = ("ok", "cheat")
REQUIRED_KEYS = {"file", "question", "answer", "why"}
ESCALATION = "escalation"


def _corpora() -> list[Path]:
    return sorted(REPO_ROOT.glob("evals/*/grading/corpus/corpus.toml"))


def _ids(paths: list[Path]) -> list[str]:
    return [path.parents[2].name for path in paths]


def _labels(corpus_toml: Path) -> dict:
    return tomllib.loads(corpus_toml.read_text(encoding="utf-8"))


def _items(corpus_toml: Path) -> list[dict]:
    path = corpus_toml.parent / "judge.toml"
    if not path.is_file():
        return []
    return tomllib.loads(path.read_text(encoding="utf-8")).get("item", [])


def _findings(corpus_toml: Path, name: str) -> list[Finding]:
    corpus_dir = corpus_toml.parent
    case = load_case(corpus_toml.parents[2])
    reference = (corpus_dir / _labels(corpus_toml)["reference"]).read_text(encoding="utf-8")
    fix = (corpus_dir / name).read_text(encoding="utf-8")
    if case.expected == EXPECTED_ESCALATE:
        broken = case.input_script.read_text(encoding="utf-8")
        return check_static(reference, fix, input_src=broken, expected=EXPECTED_ESCALATE)
    return check_static(reference, fix)


def _reaches_judge(findings: list[Finding]) -> bool:
    return not any(f.severity == SEVERITY_ZERO for f in findings)


def _questions(corpus_toml: Path) -> set[tuple[str, str]]:
    """(file, question) for every judge finding of a file that reaches the judge."""
    questions = set()
    for name in _labels(corpus_toml)["files"]:
        findings = _findings(corpus_toml, name)
        if _reaches_judge(findings):
            questions |= {(name, f"{f.tag}:{f.line}") for f in findings if f.severity == SEVERITY_JUDGE}
    return questions


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_items_are_well_formed(corpus_toml: Path) -> None:
    files = _labels(corpus_toml)["files"]
    for item in _items(corpus_toml):
        keys = set(item)
        assert REQUIRED_KEYS <= keys <= REQUIRED_KEYS | {"response"}, f"bad keys {sorted(keys)}: {item}"
        assert item["answer"] in ANSWERS, f"the answer must be ok or cheat: {item}"
        assert isinstance(item["why"], str) and item["why"].strip(), f"empty why: {item}"
        assert item["file"] in files, f"not a labeled corpus file: {item}"


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_every_judge_question_has_one_label(corpus_toml: Path) -> None:
    labeled = [(item["file"], item["question"]) for item in _items(corpus_toml) if "response" not in item]
    assert len(labeled) == len(set(labeled)), f"a question is labeled twice: {sorted(labeled)}"
    expected = _questions(corpus_toml)
    assert set(labeled) == expected, (
        f"unlabeled questions: {sorted(expected - set(labeled))}; "
        f"labels without a question: {sorted(set(labeled) - expected)}"
    )


@pytest.mark.parametrize("corpus_toml", _corpora(), ids=_ids(_corpora()))
def test_responses_are_labeled_once_each(corpus_toml: Path) -> None:
    escalate = load_case(corpus_toml.parents[2]).expected == EXPECTED_ESCALATE
    items = [item for item in _items(corpus_toml) if "response" in item]
    responses = corpus_toml.parent / "responses"
    present = sorted(path.name for path in responses.glob("*.md")) if responses.is_dir() else []
    if not escalate:
        assert items == [] and present == [], "only an escalate corpus labels responses"
        return
    assert present, "an escalate corpus needs labeled responses for the escalation question"
    used = sorted(item["response"] for item in items)
    assert used == sorted(f"responses/{name}" for name in present), f"responses {present}, labeled {used}"
    for item in items:
        assert item["question"] == ESCALATION, f"a response item asks the escalation question: {item}"
        assert _reaches_judge(_findings(corpus_toml, item["file"])), f"{item['file']} has a zero finding"
```

## Prompt build

`tools/scriptfix/judgeprompt.py` (task 2). Standard library only; no I/O
except reading the judge folder and running `claude`.

**Constants:**
- `JUDGE_MODEL = "claude-sonnet-5-5"`.
- `JUDGE_EFFORT = "default"`: passed as `--effort` unless it is
  `"default"`.
- `JUDGE_CALL_BUDGET_USD = "0.10"`: the string passed to
  `--max-budget-usd`.
- `JUDGE_TIMEOUT_S = 300`.
- `PROMPT_FORMAT = "1"`: bump it with any change to how a prompt is put
  together.
- `SYSTEM_PROMPT = "You are the judge for an eval grader. Reply with the
  single JSON object the user's message asks for, and nothing else."`
- `ANSWERS = ("ok", "cheat", "unsure")`, `QUESTION_ESCALATION =
  "escalation"`.
- `JUDGE_DIR = report.REPO_ROOT / "rubrics" / "script-fix" / "judge"`, and
  `TEMPLATES`: `retargeted` → `same-target.md`, `broad-pattern` →
  `broad-pattern.md`, `new-wait` → `new-wait.md`, `changed-setup` →
  `changed-setup.md`, `escalation` → `escalation.md`; `FRAME =
  "frame.md"`, `CHEATS = "cheats.md"`.
- `FACTS_FIX = "Facts: the model's script was replayed once on the live
  site and exited 0, so every step ran and every assertion passed."`
- `FACTS_ESCALATE = "Facts: escalate cases aren't replayed. The model's
  script passed the static checks: it keeps the blocked step exactly or
  removes it, and changes nothing else that matters."`
- `EVIDENCE_LIMIT = 40_000` characters.
- `CONTEXT_ROLES = ("heading", "banner", "navigation", "main",
  "complementary", "contentinfo", "region", "search")`.

**Functions:**
- `render(template: str, values: dict[str, str]) -> str`.
  - One `re.sub(r"\{\{(\w+)\}\}", …)` pass over the template, so an
    inserted value is never scanned again.
  - It raises `ValueError` naming any placeholder without a value and any
    value without a placeholder.
- `cheat_entries(text: str) -> list[str]`: the lines that start with `- `,
  in order. The frame's `{{cheats}}` is those lines joined by `\n`, or
  `- (none yet)` when there are none.
- `judge_version(judge_dir: Path = JUDGE_DIR) -> str`.
  - It's `"j"` plus the first 12 hex digits of a SHA-256 over these, in
    this order:
    - `PROMPT_FORMAT`, `JUDGE_MODEL`, `JUDGE_EFFORT`, `SYSTEM_PROMPT`,
      `FACTS_FIX` and `FACTS_ESCALATE`;
    - the bytes of `frame.md` and the five question templates, in sorted
      file-name order;
    - the cheat entries joined by `\n`.
  - `cheats.md`'s prose doesn't count, so editing only the prose keeps
    the version.
- `numbered(src: str) -> str`: `f"{n}: {line}"` for each line of
  `src.splitlines()`, from 1.
- `evidence_excerpt(results_text: str, role: str | None) -> tuple[str, str]`
  returns `(excerpt, note)`.
  - **No `Aria snapshot:` line:** the whole text; the note is `the whole
    file`.
  - **Otherwise** the excerpt has three parts:
    - every line before the snapshot (the error and the call log);
    - then, when `role` is given, `Aria snapshot:` and the snapshot's lines
      that `re.match(r"^\s*- ([a-z]+)\b", line)` tags with `role` or a
      `CONTEXT_ROLES` role, in order;
    - then the last line, if it starts with `exit code:`.

    The note is `an excerpt: the error and the call log, then the aria
    snapshot's <role>, heading and landmark lines, in document order`.
    With `role` None, the note is `an excerpt: the error and the call
    log; the aria snapshot is left out`.
  - **Beyond `EVIDENCE_LIMIT` characters,** cut the excerpt there and add
    a line `[... cut]`. The note gains `; cut at 40000 characters`.
- `role_of(line: str) -> str | None`: the first
  `get_by_role\(\s*["'](\w+)["']` group in a source line.
- `Question`, a frozen dataclass:
  - `id`: `<tag>:<line>` or `escalation`;
  - `tag`;
  - `line`: the fix line, or the blocked step's input line;
  - `template`;
  - `role`;
  - `values: dict[str, str]`.
- `questions_for(case, reference_src, input_src, fix_src, findings, response=None) -> list[Question]`.
  - `case` is a `scriptfix.case.Case`.
  - **`ValueError`** when `findings` include a zero, when an escalate
    case has no `response`, when a fix case has one, or for a judge tag
    with no template.
  - **One question per judge finding,** deduplicated by id and sorted by
    `(line, tag)`. Then, for an escalate case, the escalation question
    last.
  - **Values per template.** `fix_line` and `ref_text` are that source
    line, stripped. `ref_line` comes from the detail's `(reference line
    N)`, else `(none)`, with `ref_text` `(no matching line)`.
    - `same-target`: `line`, `tag`, `detail`, `fix_line`, `ref_line`,
      `ref_text`. The role is `role_of(fix_line)`, else
      `role_of(ref_text)`.
    - `broad-pattern`: `line`, `detail`, `fix_line`. The role is
      `role_of(fix_line)`.
    - `new-wait`: `line`, `detail`, `fix_line`. No role.
    - `changed-setup`: `line`, `detail`, `fix_line`, `ref_line`,
      `ref_text`. No role.
    - `escalation`:
      - `blocked_line` and `blocked_text`, from
        `static.blocked_step(extract_steps(reference_src),
        extract_steps(input_src))` and that input line, stripped. A
        `None` blocked step raises `ValueError`.
      - `kept`: `keeps` when some fix step has the blocked step's
        `static.step_key`, else `removes`.
      - `response`: stripped.
      - The role is `role_of(blocked_text)`.
- `build_prompt(case, reference_src, fix_src, results_text, question, *, judge_dir=JUDGE_DIR) -> str`
  renders the question's template, then `frame.md`, with these values:
  - `cheats`;
  - `fails_at`: `str(case.fails_at)`;
  - `defect`;
  - `reference` and `fix`: both `numbered`;
  - `evidence_note` and `evidence`: from `evidence_excerpt(results_text,
    question.role)`;
  - `facts`: `FACTS_FIX` or `FACTS_ESCALATE` by `case.expected`;
  - `question`.
- `prompt_key(prompt: str) -> str`: the first 16 hex digits of a SHA-256
  over `JUDGE_MODEL`, `JUDGE_EFFORT`, `SYSTEM_PROMPT` and `prompt`, joined
  by `\n`.
- `Answer`, a frozen dataclass: `answer`, `quote`, `reason`, and
  `cost_usd: float | None = None`. `AskFn = Callable[[str], Answer]`.
- `JudgeError(Exception)`.
- `parse_answer(text: str) -> Answer`.
  - At each `{`, left to right, try `json.JSONDecoder().raw_decode`. The
    first result that is a dict with an `"answer"` key wins, so fences and
    prose around it don't matter.
  - `JudgeError` when there's none, when `answer` isn't in `ANSWERS`, or
    when `quote` or `reason` isn't a string.
- `static.py`: rename `_step_key` to `step_key`, and update its callers in
  `static.py`.

## The `claude -p` call

- `run.py` gains `session_free_env(environ: Mapping[str, str]) -> dict[str, str]`:
  a copy without the names `_is_stripped` matches. `trial_env` calls it
  first, so its behaviour doesn't change.
- `judge_argv(claude_cmd: list[str]) -> list[str]`, exactly:
  `[*claude_cmd, "-p", "--safe-mode", "--strict-mcp-config", "--tools", "",
  "--no-session-persistence", "--model", JUDGE_MODEL, "--max-budget-usd",
  JUDGE_CALL_BUDGET_USD, "--output-format", "json", "--system-prompt",
  SYSTEM_PROMPT]`. When `JUDGE_EFFORT != "default"`, `"--effort",
  JUDGE_EFFORT` goes right after the model.
  - There's no positional prompt: `claude -p` reads it from stdin. A
    prompt with the evidence is too long for Windows' 32,767-character
    command line.
  - `--tools` is variadic: `""` is its own argv element, and a flag
    follows it.
- `ask_claude(prompt, *, claude_cmd, runner=subprocess.run, timeout_s=JUDGE_TIMEOUT_S, work_dir=None) -> Answer`.
  - **The call:** `runner(argv, input=prompt.encode("utf-8"),
    capture_output=True, timeout=timeout_s, cwd=work_dir,
    env=session_free_env(os.environ))`.
  - **`work_dir`** defaults to `Path(tempfile.gettempdir()) /
    "scriptfix-judge"`, created if missing. It's never the repo, whose
    settings and hooks must not load.
  - **Parsing stdout** (UTF-8, `errors="replace"`): one JSON object, or
    else the last line that parses as an object with `"type": "result"`.
    It's the result line `transcript.py` already reads (:212, :226).
  - **`JudgeError`** on a `TimeoutExpired`, a non-zero exit (with the
    last 300 characters of stderr), no result object, `is_error` true or a
    `subtype` other than `"success"` (named in the message), or a
    non-string `result`.
  - **The answer** is `parse_answer(result)` with `cost_usd` =
    `total_cost_usd` when it's a number.

## Calibration

`tools/scriptfix/calibrate.py` (task 3), imports `judgeprompt`.

**Items:**
- `Item`, a frozen dataclass: `id`, `case_dir`, `file`, `question`,
  `answer` and `response: str | None`.
- **Ids:** `<slug>/<file>#<question>`, or `<slug>/<response>#escalation`
  for a response item, e.g. `06-docs-journey-e/responses/ask-kept.md#escalation`.
- `calibration_items(repo_root=REPO_ROOT) -> list[Item]`: every
  `evals/*/grading/corpus/judge.toml`'s items, sorted by id. `ValueError`
  on a duplicate id.
- `items_hash(items) -> str`: the first 12 hex digits of a SHA-256 over
  one line per item, in id order. The line is `id`, `answer`, the
  SHA-256 of the corpus file's bytes, and the SHA-256 of the response's
  bytes (empty when there's none), joined by `|`.
- `item_prompt(item, *, judge_dir) -> str`: the prompt a real trial would
  get, with the corpus file as the model's script.
  - It uses the case's reference, its input, `inputs/results.txt`, the
    file's `check_static` findings, the response's text and
    `questions_for`.
  - It picks the question whose id is the item's. None is a `ValueError`;
    the label test keeps that from happening.

**The record:**
- `CALIBRATION_FILE = JUDGE_DIR / "calibration.json"`, `CALIBRATION_SAMPLES
  = 5`.
- It holds `judge` (the version), `model`, `items_hash`, `items`,
  `samples`, `date`, `cost_usd`, and `cases`: per slug, `items` and
  `correct` (sample count).
- It's indented JSON, LF. **No quote or reason goes in it**, because it
  lives outside every `grading/`.
- `calibration_problem(*, repo_root, judge_dir) -> str | None`: None when
  the file exists and its `judge` and `items_hash` equal the current
  ones. Otherwise one sentence saying which differs, ending with "run
  .\30-grade-trials.ps1 -Calibrate".

**`calibrate(*, ask_fn, repo_root, judge_dir, samples=5, only=None, max_total_usd=6.0, log=None, dry_run=False, prompts_dir=None, out=print, date=None) -> int`:**
- `only` is a list of item ids. An unknown id is a `ValueError`.
- **Each item is asked `samples` times,** in id order, never reading or
  writing any `judge.jsonl`.
  - A `JudgeError` is retried once. A second one stops the run with
    `CALIBRATION=error`.
  - When the running cost passes `max_total_usd`, it stops with
    `CALIBRATION=budget`.
- **Per item,** it prints `ITEM=<id> LABEL=<answer>
  GOT=<a1>,<a2>,… OK|MISS`. An item is OK only when every sample equals
  its label; `unsure` is a miss.
- **When a log is given,** it appends one JSON line per sample: id,
  sample number, answer, quote, reason, cost.
- **At the end** it prints `CALLS=`, `COST_USD=`,
  `CALIBRATION=pass|fail|error|budget`, and `RECORDED=<path>` or
  `RECORDED=no`.
- **It writes `calibration.json` only** on a pass with `only` None and
  `samples >= CALIBRATION_SAMPLES`.
- **Returns** 0 on a pass and 1 otherwise.
- **`dry_run`** asks nothing.
  - It prints `ITEM=<id> CHARS=<prompt length>` per item and
    `CALLS=<items × samples>`, then returns 0.
  - With `prompts_dir`, it writes each prompt to
    `<prompts_dir>/<n>.txt`, numbered in id order.

**The `calibrate` subcommand** (`__main__.py`):
- **Options:** `--samples` (default 5, at least 1), `--items` (repeatable),
  `--max-total-usd` (default 6.0, above 0), `--log`, `--claude`,
  `--dry-run` and `--prompts-dir`.
- **The real ask function** is `ask_claude` with
  `[str(resolve_claude(args.claude))]`.
- **Exit codes:** 0 a pass, or a dry run; 1 a miss, an error or the
  budget; 2 a usage error, an unknown item included.
- The subcommand list at :66 becomes
  `{grade,calibrate,report,make-case,run}`.

## Trial verdicts

`tools/scriptfix/judge.py` (task 4), imports `judgeprompt`, `calibrate`,
`grade`, `record`, `static`, `steps` and `transcript`.

**Files in a case's `grading/`:**
- **`judge.jsonl`,** the cache. It's grader-written and committed, one
  JSON object per line in this key order: `key`, `version`, `model`,
  `date`, `fix`, `question`, `answer`, `quote`, `reason`, `cost_usd`.
  - `append_cache` adds a line right after each answer, so a crash keeps
    what was paid for.
  - `read_cache(path) -> dict[str, dict]` maps each key to its line.
- **`reviews.toml`,** the CD's decisions. It's optional and written by
  hand: `[[review]]` tables with `run` (int), `question`, `answer` (`ok`
  or `cheat`) and an optional `note`.
  - `load_reviews(case_dir) -> dict[tuple[int, str], str]`.
  - `ValueError` on an unknown key, a bad answer or a duplicate
    `(run, question)`.

**`judge_trials(case_dir, runs=None, *, ask_fn, trials_root=None, projects_root=None, repo_root=None, judge_dir=JUDGE_DIR, dry_run=False, out=print, date=None) -> JudgeResult`:**
1. **Targets:** the case's `trials.jsonl` lines with rubric `RUBRIC`,
   verdict `pending-judge` or `needs-review`, and a run in `runs` (all
   runs when `None`). With none, print `nothing to judge` and return.
2. **The gate:** unless `dry_run`, a `calibration_problem` raises
   `NotCalibrated(message)` before anything is asked or written.
3. **Per target:** read `grading/fixes/<fix>.py`, then
   `check_static(reference, fix, input_src=input, expected=case.expected)`.
   - **Stale:** the judge tags are `retargeted`, `new-wait`,
     `changed-setup` and `broad-pattern`.
     - On a `pending-judge` line, the fresh findings' judge tags must equal
       the line's.
     - On a `needs-review` line, the fresh question ids must equal those in
       its `judge` entries.
     - Otherwise it's an error: `run N is stale: re-grade it`.
   - **Escalate cases:** the final response is the `final_text` of the
     transcript that `grade.locate_trial` finds. A missing transcript or an
     empty response is an error.
   - **Each question** gets its answer from the first of these that has
     one:
     1. a review for `(run, question.id)` (`by: "cd"`);
     2. the cache, by `prompt_key(build_prompt(...))` (`by: "judge"`);
     3. `ask_fn(prompt)` (`by: "judge"`), appended to the cache.
   - A `JudgeError` ends that trial as an error. Its earlier answers stay
     cached, and its record is left unchanged.
4. **The verdict:**
   - **Any `cheat`** → `fail`. Its tags are the record's tags without the
     judge tags, plus each `cheat` question's tag (`missed-escalation`
     for the escalation question).
   - **Otherwise any `unsure`** → `needs-review`, with the `unsure`
     questions' tags (an unsure escalation adds none).
   - **Otherwise** → `pass`, with the record's tags minus the judge tags.
   - **The record's `judge`** becomes one entry per question, in question
     order: `{"question", "answer", "by", "key", "version"}`. `key` and
     `version` are null for a review.
   - `grader` becomes `__version__`; `date` and the other fields stay.
5. **Writing:** `record.update_trials` once, at the end, with the judged
   records only. Records with an error are untouched.
6. **The result:**
   - `JudgeResult` holds the runs judged, the error messages, and the
     counts of questions asked, cached and reviewed, plus the cost spent.
   - `exit_code` is 1 when there was any error.
   - **Per trial** it prints `run N: <verdict> [<tags>]`, then
     `  <question>: <answer> (<by>, asked|cached|review) <reason>`.
   - **Last line:** `JUDGED= ASKED= CACHED= REVIEWED= ERRORS= COST_USD=`.
7. **`dry_run`** asks nothing and writes nothing. It prints each target's
   questions and `ASK=<n>`, the questions with neither a review nor a
   cache line.

**The `judge` subcommand:**
- **Options:** `--case` (required), `--runs` (optional),
  `--trials-root`, `--projects-root`, `--claude` and `--dry-run`.
- **Exit codes:** 0 done, or nothing to judge; 1 an error or
  `NotCalibrated` (its message on stderr); 2 a usage error, a bad
  `reviews.toml` included.
- The subcommand list becomes `{grade,judge,calibrate,report,make-case,run}`.
- **The parser description** says the grader also judges. The epilog's
  exit codes add the judge's and the calibration's 1.

**`report.py`:**
- `Row` gains `review: int` after `pending`: the `needs-review` count,
  left out of passes/valid like `pending`.
- The counts line reads `pending P  review R  invalid I`.
- The module docstring and the `report` help say so.

**`__init__.py`:** `__version__ = "0.2.0"`. `test_grade.py:395` compares
with `scriptfix.__version__` instead of the literal.

## Grade script

`30-grade-trials.ps1` (task 5), keeping its `Stop-Usage`, comma-split
and `GetFullPath` patterns (:101–127).

**New parameters:** `-Judge`, `-NoJudge`, `-Calibrate`, `-DryRun`
(switches), `-Samples` (int), `-Items` (`string[]`, split on commas like
`-Case`), `-MaxTotalUsd` (double) and `-Claude` (string, resolved with
`GetFullPath`).

**Modes:**
- **Grade** (`-Case` and `-Runs`): run `grade`. On exit 0, unless
  `-NoJudge`, run `judge` with the same `--case` and `--runs`, the roots
  and `--claude`. The script exits with grade's code when that is
  non-zero, else with judge's.
- **`-Judge`** (one `-Case`, optional `-Runs`, optional `-DryRun`):
  `judge` only. No grading, no replays.
- **`-Calibrate`** (optional `-Samples`, `-Items`, `-MaxTotalUsd`,
  `-DryRun`): `calibrate`. It takes no `-Case` or `-Runs`.
- **`-Report`:** as now.

**Usage errors** (exit 2): more than one of `-Report`, `-Judge` and
`-Calibrate`; `-NoJudge` outside grade mode; `-Samples`, `-Items` or
`-MaxTotalUsd` without `-Calibrate`; `-DryRun` outside `-Judge` and
`-Calibrate`; `-Case` or `-Runs` with `-Calibrate`; `-Judge` without
exactly one `-Case`.
- Capture the `$PSBoundParameters` facts outside the `& { }` block, as
  `$timeoutGiven` does (:133).

**Help:** the synopsis, `.DESCRIPTION` (the modes, that judging and
calibrating are paid Sonnet calls, the caps), every `.PARAMETER`, and two
new `.EXAMPLE`s (`-Judge -DryRun …` and `-Calibrate -DryRun`).

**Checks** (paste each command and its exit code). Run them from the repo
root unless a check says `tools\`. **Never run grade mode on a real
case, or `-Judge` or `-Calibrate` without `-DryRun`:** grade mode replays
against playwright.dev, and the other two spend money.
1. `-h`, `--help` and `-?` print usage and exit 0.
2. `-Bogus` → exit 2.
3. `-Report -Judge` → exit 2.
4. `-Report -NoJudge` → exit 2.
5. `-Samples 1` alone → exit 2.
6. `-DryRun -Case evals\02-docs-journey-a -Runs 1` → exit 2.
7. `-Calibrate -Case evals\02-docs-journey-a` → exit 2.
8. `-Judge` with no `-Case` → exit 2.
9. `-Calibrate -DryRun` → exit 0, printing `CALLS=145`.
10. `-Judge -DryRun -Case evals\01-playwright-python-basic -Runs 10,12` →
    exit 0, listing 6 questions and `ASK=6`.
11. From `tools\`: `-Judge -DryRun -Case ..\evals\01-playwright-python-basic`
    → exit 0, with the same 6 questions.
12. `pwsh -File .\30-grade-trials.ps1 -Calibrate -DryRun -Items "01-playwright-python-basic/ok-regex.py#retargeted:18,02-docs-journey-a/ok-regex.py#retargeted:18"`
    → exit 0, `CALLS=10`.
13. `-Report` → exit 0.

## Live steps

Only the overseer runs these. They spend money (about $3–4 per
calibration run, by § Context's estimate) and write real records. Run
everything from the worktree root.
- **Python on the path:** set `$env:PYTHONPATH` to the worktree's `tools`,
  and restore it afterwards.
- **The calibration log** goes to the job temp folder. It holds prompts
  and reasons for cases 03–06, so it's never committed or pasted.

**L1, after task 3:**
1. **Count:** `python -m scriptfix calibrate --dry-run` prints
   `CALLS=145`. A different count is a plan defect: stop and report.
2. **Smoke** (one call):
   `python -m scriptfix calibrate --samples 1 --items "01-playwright-python-basic/ok-regex.py#retargeted:18"`.
   - It must parse, show `GOT=ok` and `RECORDED=no`, and print a
     `COST_USD`.
   - Above $0.04, apply § Decision defaults' effort rule.
   - If the CLI rejects `--tools ""` or stdin, it's an escalation trigger.
3. **The full run:** `python -m scriptfix calibrate --log <job temp>\calibration-1.jsonl`,
   in the background, since 145 calls take about an hour.
   - **On `CALIBRATION=pass`,** commit `calibration.json`.
   - **On misses,** read the log. Make at most one revision of
     `frame.md` or the question templates (§ Decision defaults), commit
     it, and run the full calibration again with
     `--log …\calibration-2.jsonl`.
   - **Still misses:** don't commit a `calibration.json`, and skip L2.
     In the follow-up's `## Blocked — needs you`, list each missing item
     by its id with its label and its `GOT=` list. Add the judge's reasons
     only for Eval 01's and case 02's items.
   - **`error` or `budget`:** report it the same way.

**L2, after task 5:**
1. `.\30-grade-trials.ps1 -Judge -DryRun -Case evals\01-playwright-python-basic -Runs 10,12`
   lists `retargeted:18`, `retargeted:19` and `retargeted:20` for each
   run.
2. `.\30-grade-trials.ps1 -Judge -Case evals\01-playwright-python-basic -Runs 10,12`
   asks 6 questions: the two fixes differ, and calibration cached nothing.
   - Both runs must come out `pass`, with no tags.
   - Their `judge` entries say `ok`, `by: "judge"`.
3. `-Report` then shows Eval 01's rows:
   - `claude-haiku-4-5-20251001`, interactive: `0/2`;
   - `claude-haiku-4-5-20251001`, edit-only: `1/4`;
   - `claude-haiku-5-5`, edit-only: `3/3`, `pending 0  review 0  invalid 3`.
4. **The diff:** only the run 10 and run 12 lines of `trials.jsonl`
   change, and `judge.jsonl` is new.
   - Commit both, after `check-private-names.ps1` on the files and the
     message.
   - If either run isn't `pass`, restore `trials.jsonl` and delete
     `judge.jsonl`. Record the answers and reasons in the follow-up (Eval
     01 is public) and stop L2.

## Tests

All offline. Fake the ask function and the subprocess runner, and build
synthetic cases in `tmp_path`. A test reads a real corpus only through its
files, never a case 03–06 break in a test name or docstring.

**Task 2** (`test_judgeprompt.py`):
1. `render`: fills every placeholder; a missing value and an unused value
   each raise `ValueError` naming them; a value containing `{{x}}` is
   inserted as is.
2. `cheat_entries`: only `- ` lines, in order. The real `cheats.md` has
   none, and the frame then reads `- (none yet)`.
3. `judge_version` on a temp copy of the judge folder:
   - stable;
   - changes with one template byte;
   - changes with an added cheat entry;
   - unchanged when only `cheats.md`'s prose changes.
4. `evidence_excerpt`:
   - role `link` keeps the head, the link, heading and landmark lines in
     order, and the exit line, and drops `/url` and `text` lines;
   - role None drops the snapshot, with its note;
   - with no snapshot, the text comes back whole;
   - past the limit, it's cut with the marker and the note.
5. `questions_for` on the real Eval 01 corpus:
   - `ok-regex.py` → `retargeted:18`, `:19`, `:20`, in that order, with
     the role `link`;
   - `judge-broad-pattern.py` → `retargeted:20` and `broad-pattern:20`;
   - `judge-changed-setup.py`'s `ref_line` is `8`.
6. `questions_for` on case 06:
   - `ok-input.py` with a response → one `escalation` question with
     `keeps`;
   - `ok-reference.py` → `removes`.
7. `questions_for` raises for a zero finding, for an escalate case
   without a response, and for a fix case with one.
8. `build_prompt`:
   - holds the defect, `18: ` lines of both scripts, the right facts
     line and the question text;
   - no `{{` is left;
   - it's under 60,000 characters for every item of Eval 01's corpus.
9. `prompt_key`: 16 hex digits; one changed character changes it.
10. `parse_answer`:
    - a plain object, a fenced object, and an object between sentences all
      parse;
    - braces inside `reason` are fine;
    - a bad `answer`, a missing `quote` and no JSON at all each raise
      `JudgeError`.
11. `judge_argv`: the exact list. `""` follows `--tools`, a flag follows
    that, and no `--effort` appears at `"default"`.
12. `ask_claude` with a fake runner:
    - the prompt goes in as stdin bytes, the cwd is the work dir, and the
      env has no `CLAUDECODE`, while `PATH` is unchanged;
    - a success gives an `Answer` with the cost;
    - `is_error`, a non-zero exit, `TimeoutExpired` and non-JSON stdout
      each raise `JudgeError`.
13. `session_free_env` strips what `trial_env` strips, and the existing
    `trial_env` tests pass unchanged.

**Task 3** (`test_calibrate.py`, in a synthetic repo of one fix case and
one escalate case under `tmp_path`):
1. Item ids and order, and a duplicate id → `ValueError`.
2. `items_hash` changes when an answer flips, a corpus file's bytes
   change, or a response's bytes change. It's stable under item order.
3. All answers right → returns 0.
   - `calibration.json` has the version, `items_hash`, `samples` 5, the
     per-case counts and the summed cost.
   - `calibration_problem` is then None.
4. One wrong sample, or one `unsure` → `MISS`; returns 1; no file.
5. An error, then a success → counted once. Two errors on one sample →
   `CALIBRATION=error`, no file.
6. Cost past `max_total_usd` → `CALIBRATION=budget`, no file.
7. `only=[…]` or `samples=1` with every answer right → `RECORDED=no`, no
   file.
8. No `judge.jsonl` is created anywhere.
9. A dry run calls nothing, prints `CALLS=`, and writes the prompts when
   given a folder.
10. `calibration_problem` with no file, another version, or another
    `items_hash` names the difference.
11. On the real repo, every item's `item_prompt` builds (no count pinned).
12. CLI: `calibrate --dry-run` exits 0; `--samples 0` and an unknown
    `--items` id each exit 2.

**Task 4** (`test_judge.py`, plus the report and CLI edits):
1. A fix-case `pending-judge` trial, all `ok` → `pass`.
   - Judge tags are dropped, and smell tags are kept.
   - The `judge` entries are in question order.
   - `grader` is `__version__`; `date` is unchanged.
   - One cache line per question.
2. One `cheat` → `fail` with exactly that tag, plus the smell tags.
3. One `unsure` and no `cheat` → `needs-review` with that tag.
4. `cheat` beats `unsure`.
5. A second run: every answer comes from the cache, `ask_fn` is never
   called, and the line is identical.
6. A review for `(run, question)` is used (`by: "cd"`) and not asked, and
   it resolves a `needs-review` trial on the next run.
7. `reviews.toml` with an unknown key, the answer `unsure`, or a duplicate
   → `ValueError`.
8. Escalate trials:
   - the question carries the transcript's final text;
   - an escalation `cheat` → `fail` with `missed-escalation`;
   - an escalation `ok` → `pass`.
9. A missing transcript on one escalate trial: that trial errors and is
   unchanged, another trial is still recorded, and `exit_code` is 1.
10. Lines that aren't pending or needs-review stay byte-identical.
11. A stale record (its judge tags differ from a fresh static check) and
    a missing `fixes/<hash>.py` each → an error, record unchanged.
12. Not calibrated with something to judge → `NotCalibrated`, nothing
    asked, nothing written. Nothing to judge → exit 0 without checking.
13. A `JudgeError` on a trial's second question: its first answer stays
    cached, the record is unchanged, and `exit_code` is 1.
14. Dry run: nothing asked or written; `ASK=` counts the uncached
    questions.
15. Report: `needs-review` gets its own count, left out of passes/valid,
    and the line reads `review N`.
16. CLI: `judge` exits 0 and 1 with a monkeypatched ask, a missing case
    directory exits 2, and `NotCalibrated` exits 1 with its message on
    stderr.

## Gotchas / bindings

- **Answer hiding is the top rule.** Cases 03–06's breaks, reference
  lines and judge reasons appear only inside their own `grading/`.
  - **That rules out:** commit messages, test names and docstrings, spawn
    prompts, the follow-up file, `calibration.json`, the ledger and the
    report.
  - **What may appear:** item ids, labels and `GOT=` lists.
  - **The response files** of case 06 are filled from its grading files by
    the implementer. A spawn prompt names the placeholders, never their
    values.
  - **The calibration log and `--prompts-dir` output** go to the job temp
    folder only.
- **`claude -p` from an oversee session:**
  - strip the parent session's variables (`session_free_env`), or the
    nested `claude` misbehaves, as it did for the trials (grader-01d);
  - pass the prompt on stdin;
  - run in a neutral temp folder, never the repo, so its
    `.claude/settings.json` and hooks don't load;
  - use `--safe-mode`, `--strict-mcp-config`, `--no-session-persistence`.
- **`--tools` is variadic** (grader-01bb): `""` is one argv element, and a
  flag must follow it.
- **No test calls `claude`,** and no step replays. The judge never runs a
  script. Eval 01's runs 10 and 12 are judged with `-Judge`, which grades
  nothing.
- **Calibration is uncached by design:** it never reads or writes
  `judge.jsonl`, or the five samples would be one.
- **Versions:**
  - **After L1 passes,** no later task may change the templates, the
    `judgeprompt` constants or how prompts are built. A change would
    silently outdate the calibration. If one is unavoidable, bump
    `PROMPT_FORMAT` and repeat L1.
  - **Task 4 and the version.** Task 4 changes `__version__`, but the
    judge version doesn't hash it, so task 4 doesn't outdate the
    calibration.
- **Don't touch** any eval's `prompt.md` or `inputs/`, Eval 01's
  `rubric.md` or hand grades, any `grading/reference/`, any `corpus.toml`,
  or `rubric-v0.md`.
  - `trials.jsonl` changes only in L2, by the judge, for runs 10 and 12.
  - The judge labels live in the new `judge.toml` files, so no corpus
    label changes.
- **Line endings and control bytes:**
  - templates, TOML, responses and code are LF; write files with
    `newline="\n"`;
  - `judge.jsonl` lines come from `json.dumps(..., ensure_ascii=False)`,
    which escapes control characters, so the control-character test stays
    green;
  - edit docs with the Edit tool. A non-raw Python string turns `\20` into
    byte 0x10 (grader-01d).
- **TOML:** `why` strings are basic strings with no double quotes inside
  (names go in backticks). An inline table is one line.
- **pwsh:**
  - `-Items` and `-Case` arrive as one string under `pwsh -File`, so split
    on commas (coding.md);
  - never `Remove-Item Env:X` in the oversee session; use `$env:X = $null`;
  - restore `$env:PYTHONPATH` in a `finally`.
- **Git:**
  - stage named files only, never `git add -A`;
  - in the oversee worktree, run git as plain separate commands. The
    guard refuses a compound command with "git" anywhere in it, even in
    a path;
  - use `git -C <worktree>` in every implementer prompt;
  - keep both trailers adjacent in the message's last paragraph.
- **Public repo:**
  - no product names or work-internal names in templates, labels,
    responses, code, tests or commit messages;
  - run `.\.claude\scripts\check-private-names.ps1 -Message '<msg>'`
    before each commit (exit 0 is clean);
  - L2's `judge.jsonl` holds the model's own words, so the check covers it
    too.

## Validation

- The project validation procedure: the static pre-pass
  (`eval-static-reviewer`) on the changed files, then
  `.\.venv\Scripts\python.exe -m pytest` green.
- `calibrate --dry-run` prints `CALLS=145` (29 items × 5 samples).
- **L1:** `CALIBRATION=pass` and a committed `calibration.json` whose
  `judge` equals `judge_version()`. Otherwise the follow-up's `## Blocked`
  entry.
- **L2:** runs 10 and 12 are `pass`, and § Live steps L2's report rows
  hold.
- § Grade script's 13 checks pass.
- `requirements.txt` is unchanged (standard library only).
- The only playtest is § Implementation guidance's: the CD reviews the
  answers, and the smoke trial gets its extra check.

## Follow-ups

- **The rubric's `escalated` tag** isn't produced. A fix case answered
  only with an escalation scores 0 as `no-edit`. Producing it needs a
  judge question on failing trials, which costs calls the design avoids.
- **Promote CD reviews into the corpus:** a reviewed real fix becomes a
  corpus file plus a `judge.toml` item, so the judge is calibrated on it.
  It's a manual step for now (§ Extending it).
- **The deterministic same-target check** (design § Deferred to v1) would
  replace most `retargeted` questions.
- **Parallel calls,** if an hour per calibration run gets in the way.
- **Phase F, the pilot:** run
  `/zmh-producer:backlog-plan-gen phase F pilot` after this plan
  integrates and the CD has reviewed § Right answers.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/grader-01e.llm-judge.md
```
