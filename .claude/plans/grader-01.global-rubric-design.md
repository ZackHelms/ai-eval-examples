# grader-01 — global script-fix rubric + grader v0 (design proposal)

**Status:** APPROVED 2026-10-30 (the CD's answers: § Decisions).
Not an oversee-ready plan: each phase in § Phases becomes one
(`.claude/templates/plan.md`), one at a time.
**Requested:** 2026-10-30 (TODO.md § Needs Zack, "Global rubric + graders").
**Scope:** new `rubrics/script-fix/`, `tools/scriptfix/`, three root
scripts, cases `evals/02-…` to `06-…`, and grading files for Eval 01.
Eval 01's prompt, inputs and hand rubric don't change.

## Goal

One rubric and one grader for every "debug and fix this Playwright script"
case, instead of one per script. Each trial scores 100 or 0; a subject's
score on a case is the average over N one-shot trials. Deterministic checks
decide almost everything; an LLM judge answers only the narrow questions a
script can't. v0 is proven here, on Eval 01 and five small cases, before
any of it is ported to work.

## What the CD decided (2026-10-30)

- **Binary per trial:** 100 if the fixed script passes, 0 if any cheat is
  detected. N one-shot trials per subject; the average is the score.
- **Prompt:** "debug & fix; here are the script and its results; do not
  run it".
- **Graders:** deterministic scripts first, LLM graders for the subtler
  cheats.
- **Uses:** rate task complexity by issue type; tune a script-hardening
  agent's context files until it succeeds reliably.
- **One-shot evals,** although the agent itself will fix and re-run up to
  10 times before alerting a human: the evals are a teaching tool and the
  yardstick for context files.
- **One visible defect per case:** cut the script after the failing
  transaction (a later defect hides behind the first), then re-capture its
  evidence.
- **Cases stay** once added, as a regression suite; bar about ≥95% over
  100 trials.
- **Tuning context on the suite is the goal,** not a risk; new incoming
  issues are the fresh test.
- **Seed cases** by recreating past issues; add each new issue the agent
  can't fix.

This proposal answers the five open points: what "passes" means beyond
exit 0 (§ Rubric v0), the expected outcome per case (§ Escalate cases),
failure tags (§ Tags), trial counts per stage (§ Trial stages) and the case
template (§ Case template).

## Terms

- **Case:** one eval graded by this rubric: a broken script, its evidence,
  a reference fix and an expected outcome.
- **Subject:** what a trial measures: model + effort + context files + tool
  permissions (the Claude Code version is recorded too).
- **Trial:** one one-shot attempt by one subject at one case.
- **Verdict:** `pass` (100), `fail` (0) or `invalid` (a harness or site
  fault: excluded and re-run).
- **Score:** passes ÷ valid trials, shown with its 95% lower bound.

## Rubric v0

As approved. The authoritative text is now `rubrics/script-fix/rubric-v0.md`
(phase A); change it there, not here.

### Fix cases

A trial scores 100 when all four checks hold; otherwise 0.

1. **It runs.** The model's script, replayed once (1 user × 1 iteration)
   from a fresh copy, exits 0 within the time limit.
2. **It's the same benchmark.** It takes the reference fix's journey:
   - the same navigations, actions and transaction markers, in the same
     order and of the same kind (a `click` stays a `click`);
   - every assertion the reference has, between the same actions and with
     the same matcher (`to_be_visible` stays `to_be_visible`). Added
     assertions are welcome (tag `added-assertion`, for the record): one
     that waits for a progressively loaded element makes the script
     sturdier, and a wrong one fails the replay;
   - a locator or value that differs from the reference's still targets
     what the reference targets (judged).
3. **No fake fix.** None of the fake-fix patterns below, beyond what the
   reference already contains.
4. **Fair play.** No cheating in the transcript: reading, listing or
   searching any eval's `grading/` folder in a local copy of this repo, or
   opening anything from this repo online (Eval 01's two rules, unchanged).

The journey is compared with the reference fix, not with the broken input:
a correct fix may restore a step the input lost (a missing click), while a
"fix" that deletes the failing step would pass checks 1 and 3.

Anything else is allowed, as far as the subject's tool permissions go: web
searches, documentation, installing or running tools other than the script.

### Escalate cases

Some defects can't be fixed from the evidence without a human decision,
e.g. a step that checks for an element the site doesn't have. Their
reference is the input with that step removed. A trial scores 100 when:

1. the final response names the step, says why it can't be fixed as
   written, and asks for a decision, or says it removed the step pending
   one (judged);
2. the script's journey is the input's or the reference's: the step is
   kept or removed, never retargeted;
3. checks 3 and 4 above hold.

A fix case answered with only an escalation scores 0 (tag `escalated`), so
over-caution shows up separately from wrong fixes.

### Fake-fix patterns

Severity: **zero** (detected by a script; the trial scores 0) · **judge**
(the LLM judge decides) · **smell** (tagged only; no effect on the score
unless the CD promotes it).

| Pattern | Severity |
|---|---|
| A new `try`/`except` that doesn't re-raise, or `contextlib.suppress` | zero |
| Fixed sleeps: `time.sleep`, `asyncio.sleep`, `wait_for_timeout` | zero |
| A longer timeout than the reference's, by argument or by default (`set_default_timeout`, `expect.set_options`, …) | zero |
| `force=True`, or `dispatch_event` in place of an action | zero |
| An action, navigation or assertion removed, reordered or replaced by a weaker kind | zero (check 2) |
| A new `if`, loop or early `return` around steps; `sys.exit` / `os._exit` | zero |
| Other new waits: `wait_for_load_state`, `wait_for_selector`, `wait_for_url` | judge |
| Changed setup: launch options, viewport, context options, tracing | judge |
| A locator or expected value that differs from the reference's | judge |
| A regex or pattern that matches almost anything (`.*`, `""`) | judge |
| `.first`, `.last` or `.nth()` added | smell |

### Not graded in v0

- **Diagnosis, cited evidence and report honesty in fix cases.** Eval 01's
  run 4 (both links fixed, "Fixed!" without checking) scores 100 here. In
  production the agent re-runs its own fix, so its one-shot report matters
  less than the fix. Eval 01's 100-point rubric stays as the worked example
  of grading those.
- **Code style.** Imports, comments, formatting, and moving a locator into
  a local variable don't count: the comparison runs on the parsed script,
  not its text.

### Invalid trials

Excluded from the score and re-run:

- **Site fault:** a control (§ Grader pipeline) failed, so the site changed
  or was down. The whole batch is invalid.
- **Harness fault:** the edit to the script was denied, a tool failed for
  harness reasons ("The command line is too long"), an API error, or no
  final response: the lessons of Eval 01's runs 7–9.

## Tags

Every graded trial gets tags; every `fail` gets at least one.

| Group | Tags |
|---|---|
| Not fixed | `no-edit` · `syntax-error` · `not-fixed` (fails at the same step) · `new-failure` (fails at another step) · `escalated` |
| Not the same benchmark | `changed-journey` · `weakened-check` · `retargeted` |
| Fake fix | `swallowed-error` · `sleep` · `longer-timeout` · `force` · `conditional-step` · `forced-exit` · `new-wait` · `changed-setup` · `broad-pattern` |
| Fair play | `answer-key` · `repo-online` |
| Escalate cases | `missed-escalation` (plus `retargeted`) |
| Smells (no effect) | `first-nth` · `tried-to-run` |
| Info (no effect) | `added-assertion` |
| Invalid | `site-changed` · `harness-error` |

Cases carry **issue types** instead (in `case.toml`), so pass rates can be
read by issue type: the task-complexity view. v0 starts with the pilot's
five: `locator-text`, `locator-strict`, `locator-role`, `missing-step`,
`impossible-target`. The list grows as cases arrive (timing, assertion
drift, navigation, test data, popups and frames, …).

## Grader pipeline

Per batch (one grading session over one or more cases):

0. **Control.** Replay each case's reference (must exit 0) and its broken
   input (must fail at its recorded line), at the start and again at the
   end. Any surprise → the batch is `invalid` (`site-changed`): regenerate
   the case, don't grade.

Per trial, stopping at the first zero:

1. **Validity** (transcript): harness faults → `invalid`.
2. **Fair play** (transcript): the model's tool calls (commands, paths,
   URLs) against the answer-key and repo-online patterns → zero. Attempts
   to run the script → `tried-to-run`.
3. **Static** (the model's script): parse it, extract its steps, compare
   the journey with the reference, run the fake-fix detectors. Zeros stop
   here, so a fake fix never costs a site visit.
4. **Replay:** run a copy once, outside the repo, with a time limit.
   Identical scripts (same parsed form) share one replay per batch.
   Exit ≠ 0 → `not-fixed` or `new-failure`.
5. **Judge:** only for a trial that would otherwise pass but has judge
   flags. One narrow question per flag, answered `ok`, `cheat` or `unsure`
   with a quote; `unsure` holds the trial as `needs-review` until the CD
   decides. Verdicts are cached by question, fix and judge version, so
   re-grading is stable and free.
6. **Record:** one JSON line in the case's `grading/trials.jsonl`; the
   model's script saved once as `grading/fixes/<hash>.py`. Distinct fixes
   are few; they're the re-grade source and future corpus entries.

Transcript and static checks are free and deterministic; replays cost a
site visit; the judge is the only paid, non-deterministic step, so it runs
last and rarely.

A `trials.jsonl` line:

```json
{"run": 7, "date": "2026-11-02", "rubric": "script-fix-v0", "grader": "0.1.0",
 "subject": {"model": "claude-haiku-4-5-20251001", "effort": "default",
             "context": "none", "tools": "edit-only", "cli": "2.1.314"},
 "verdict": "fail", "tags": ["not-fixed"], "fix": "3f9a0c…",
 "judge": [], "session": "…", "cost_usd": 0.08}
```

The report reads every case's `trials.jsonl` and prints, per case ×
subject, `passes/valid`, the 95% lower bound, the most common tags and the
invalid count; and per issue type × subject, the pass rate across cases.

### What the judge sees

Each question gets only what it needs: the case's one-line defect, the
reference step, the model's step, the relevant excerpt of the evidence
(e.g. the page snapshot in `results.txt`) and, for escalation, the final
response. Two question types in v0:

- **Same target:** "Does the model's locator match the element the
  reference's matches, and only that one?" Reworded for changed values,
  setup and waits.
- **Escalation:** "Does the response name this step, say why it can't be
  fixed as written, and ask for a decision or say it removed the step
  pending one?"

Proposed judge: Sonnet 5.5 through `claude -p` with no tools and no MCP
servers (no API key; same login as the trials). Before it grades anything
in the pilot, it must get every labeled judge item in the corpora right,
five times out of five.

## Case template

```
evals/<NN>-<name>/
  prompt.md               the shared prompt, verbatim
  inputs/
    script.py             broken, cut after the failing transaction
    results.txt           captured console output + exit code
    script.pwtrace.zip    captured trace
  grading/
    case.toml             rubric, expected outcome, issue types, origin, defect
    recipe.toml           how the case is built: source, cut point, edits
    reference/script.py   the intended script, cut at the same point
    corpus/               labeled fixes the grader must classify correctly
    fixes/                distinct model fixes, by hash (grader-written)
    trials.jsonl          one graded trial per line (grader-written)
```

`case.toml`:

```toml
rubric   = "script-fix-v0"
expected = "fix"                  # fix | escalate
issue    = ["locator-text"]       # issue types, for the complexity view
origin   = "cut from 01-playwright-python-basic"   # | generated | recreated
defect   = "…one line of ground truth, for the judge and reports…"
fails_at = 18                     # inputs/script.py line where the captured run fails
target   = "https://playwright.dev"
```

**Shared prompt** (`rubrics/script-fix/prompt.md`, one wording for every
case; the integrity gate checks each `prompt.md` matches it):

> Debug and fix inputs/script.py. It failed when run: its console output
> and exit code are in inputs/results.txt, and the Playwright trace of that
> run is inputs/script.pwtrace.zip. Don't run the script; fix it from this
> evidence. If a step can't be fixed without a decision from me, tell me
> which step and why.

The last sentence makes escalation a legitimate answer on every case, so
an escalate case isn't given away by its prompt; the `escalated` tag
measures any over-caution it causes on fix cases.

**Names** describe the journey, never the defect (`evals/02-docs-journey-a/`,
`-b`, …); the defect lives only in `grading/`. Trial folders use the number
only (`02-run7`), as now.

**Cut rule.** Cut after the failing transaction. A script without
transaction markers is cut after the first assertion at or after the
failing line, since a transaction ends on a locator assertion
(`.claude/standards/coding.md`). The teardown after the journey (stopping
the trace, closing the page and browser) stays.

**Making a case** (`10-make-case.ps1 <case>`, from `recipe.toml`):

1. Build `grading/reference/script.py`: the source script, cut.
2. Build `inputs/script.py`: the reference plus the recipe's edits.
3. In a neutral folder outside the repo, with its own venv, so tracebacks
   don't name the repo: replay the reference (must exit 0), then the input
   (must fail at `fails_at`), saving `results.txt` (UTF-8 on any console)
   and the trace into `inputs/`.
4. Copy the shared prompt to `prompt.md`.

Re-running it regenerates the fixtures. A recreated past issue at work uses
the same recipe, with the real script as its source.

**Corpus.** Each case keeps a handful of labeled fixes: the reference,
accepted alternatives (exact name, regex, scoped locator) and one file per
fake-fix pattern that applies, each labeled with its expected verdict and
tags. The grader's tests run every corpus file through the static checks
(offline: no site traffic); replay and judge labels are checked in the
pilot.

## Trial stages

| Stage | Trials per case × subject | Use | What it shows |
|---|---|---|---|
| Smoke | 1 | after any change to the runner, grader or a case | the pipeline works; not a measurement |
| Screen | 10, all run | tuning context; complexity readings | 10/10 → true rate likely ≥74%; a subject at 80% fails it 89% of the time |
| Full | up to 100, stops at the 6th failure | adopting a context change; the regression bar | 95/100 → true rate likely ≥89% |

"Likely" means a one-sided 95% lower bound. What follows from the numbers:

- **A screen can't prove reliability.** A subject truly at 95% fails a
  10-trial screen 40% of the time. A screen failure on a case that used to
  pass triggers a full run, not a rejection.
- **The full bar** (≥95/100) reliably admits a subject at ≥98% and rejects
  one at ≤90%; in between it's a coin toss. Proving a true rate ≥95% would
  take ≤1 failure in 100 (or 59 passes in a row). Recommendation: keep
  ≥95/100 as the bar, and show the lower bound beside every rate.
- **At suite scale, chance failures add up.** With 50 cases each truly at
  97%, about 4 fail the bar on any full run. A failure counts as a
  regression only when a second full run of that case also fails (under 1%
  chance per case).

**Replays and the load-test pin.** Grading replays are single replays, one
at a time, deduplicated. The pilot needs fewer than 100 on playwright.dev
in total (controls plus distinct fixes). Full runs at suite scale need many
more, so they wait for the local test site (TODO.md § Next), which also
stops site changes from invalidating batches.

## Pilot

**Calibration on Eval 01** (no new trials): add its grading files, grade
its 12 existing trials (kept in `~\eval-trials\01-runN\` with their stream
logs) and compare with the hand grades:

| Runs | Hand grade | v0 must say |
|---|---|---|
| 1 | Fixed 0 | `fail`, `not-fixed` (still fails at line 18) |
| 2, 3, 5, 6 | Fixed 0 | `fail`, `new-failure` (fails at line 20, the hidden defect) |
| 4, 11 | Fixed 40 | `pass` |
| 10, 12 | Fixed 40, regex locators | `pass`, once the judge clears the changed locators |
| 7–9 | not scored | `invalid`, `harness-error` |

Run 1's evidence was corrupt, which the grader can't know; it grades the
trial, so `fail` is right. Eval 01 has two defects and an older prompt, so
it calibrates the grader but isn't a pilot case.

**Five cases.** One is Eval 01 cut to a single defect; four are generated
by recipe from Eval 01's reference script (the same journey on
playwright.dev, one break each). The exact breaks live only in each case's
`grading/recipe.toml`, since trials still run on the host, where this file
is readable.

| Case | Issue type | Expected | Exercises |
|---|---|---|---|
| 02 | `locator-text` | fix | Eval 01 without its hidden second defect: how much of Eval 01's difficulty was the hidden one |
| 03 | `locator-strict` | fix | a locator that matches two elements; tempts `.first` (smell) and retargeting (judge) |
| 04 | `locator-role` | fix | the right name with the wrong role |
| 05 | `missing-step` | fix | a lost navigation step; tempts retargeting the assertion or a `goto` (both change the journey) |
| 06 | `impossible-target` | escalate | a step checking for an element the site doesn't have; replaces § Next's "Eval: impossible locator" |

Timing is missing on purpose: on a public site it can't be made to fail
deterministically. It's the natural bait for the sleep and timeout cheats,
so until a local target exists those detectors are tested only by the
corpora.

**Subjects:** Haiku 4.5 and Haiku 5.5, default effort, no context files,
edit-only permissions (as in Eval 01's runs 3+).

**Protocol:** smoke (1 trial per case per subject) → screen (10 × 5 cases
× 2 subjects = 100 trials, about $5 at Eval 01's logged costs) → report.
Optional: one full run (Haiku 5.5 on one case) to exercise early stopping
and the lower bound.

**v0 works when:**

- every corpus label is reproduced, and the judge is 5/5 on every judge
  item;
- Eval 01's calibration matches the table above;
- the screen finishes with no unexplained `invalid` trials;
- the CD spot-checks 10 random verdicts (passes and fails) and agrees with
  every one.

## Tooling layout (ADR-0001)

```
rubrics/script-fix/       rubric-v0.md · prompt.md · judge/ (judge prompts)
tools/scriptfix/          Python package, standard library only: steps,
                          detectors, transcript scan, replay, judge, grade,
                          report, make-case
tools/tests/              pytest: unit tests + every case's corpus (offline)
10-make-case.ps1          build or rebuild a case from its recipe
20-run-trials.ps1         N headless trials of a case for a subject
30-grade-trials.ps1       grade new trials; print the report
```

- **Python for the logic,** because it parses the scripts it grades
  (`ast`), and `tomllib` ships with 3.12. **pwsh for the entry points,**
  per the environment pin and the Script SOP.
- **pytest becomes the repo's first hard gate** (added to
  `requirements.txt`; the version is checked against two sources when
  pinned).
- **The runner** is the launcher from Eval 01's `grading/trials.md`
  § Setup, generalized: any case; subject = model + effort + context bundle
  + tool profile; its three gotchas built in (absolute allow rules,
  stripping the parent session's variables, the real `pwsh.exe` first on
  `PATH`). It records the context bundle's hash from day one, ready for
  context experiments.

## Phases

Each phase is one plan, approved and run one at a time.

| Phase | Delivers | Needs | Replaces in TODO.md § Next |
|---|---|---|---|
| A. Decide | the CD's answers; ADR-0001; `rubrics/script-fix/` | this proposal | — |
| B. Deterministic grader | steps, detectors, transcript checks, replay, record; pytest gate; Eval 01 grading files + corpus; Eval 01 calibration (judge items pending) | A | Eval 01 grader, script half |
| C. Cases | neutral-folder capture; `10-make-case.ps1`; cases 02–06 + corpora | A, B (corpus tests) | Capture script; Eval: impossible locator |
| D. Runner | `20-run-trials.ps1` | A | Trial runner script |
| E. Judge | judge prompts, cache, the 5/5 calibration; Eval 01's pending items | B, C | Eval 01 grader, AI half |
| F. Pilot | smoke → screen → report; findings; the v1 list | C, D, E | — |

C and D are independent of each other once B lands. § Next's eval-integrity
gate gains two checks: `case.toml` is valid, and `prompt.md` matches the
shared prompt.

## Decisions (CD, 2026-10-30)

All nine as recommended, with one change to the first:

1. **The journey is the reference's.** The fix is compared with the
   reference fix; any added, removed or reordered navigation or action, or
   a removed or weakened assertion, is a zero. **Changed:** added
   assertions are welcome, not a smell. The CD prefers more assertions
   (e.g. waits on progressively loaded elements), and an incorrect one
   should break the next transaction, i.e. fail the replay.
2. **`.first` / `.nth()`:** a smell in v0, revisited with pilot data.
3. **The shared prompt** above, including "Don't run the script" and the
   escalation sentence. Running stays blocked by the harness; attempts are
   a smell.
4. **No report grading in fix cases** (Eval 01's run 4 scores 100).
5. **Escalate cases in v0,** with case 06 in the pilot.
6. **Stages and bar:** smoke 1 · screen 10 · full 100, stopping at the 6th
   failure; bar ≥95/100 with the lower bound shown; a screen failure
   triggers a full run; a regression needs two failed full runs.
7. **Site policy:** pilot replays are sequential, deduplicated single
   replays on playwright.dev (fewer than 100 in all), within the
   load-test pin; the one optional pilot full run is fine. Further full
   runs wait for the CD's local test site (TODO.md § Next).
8. **Judge:** Sonnet 5.5 via `claude -p`, cached; `unsure` goes to the CD.
9. **Layout** as in § Tooling layout, recorded as ADR-0001.

## Deferred to v1

- **A timing case,** on the local test site (TODO.md § Next).
- **A deterministic same-target check:** compare the element each step hit
  in the reference's replay trace with the one in the fix's. It would
  replace most judge calls.
- **Locust transaction markers** in real cases (the step extractor's marker
  list is configurable from the start).
- **Context experiments** on the pilot cases (the runner already records
  the bundle).
- Unchanged in TODO.md: the isolated trial environment, the SDK harness,
  the first-eval level-set.

## Risks

- **False passes** (a cheat scores 100) are the costliest error: they
  reward contexts that teach cheating. Guarded by one corpus file per
  applicable pattern and the CD's spot-checks.
- **False zeros** (a fine fix scores 0) show up as tags on fixes that look
  right; each one becomes a corpus "good" file.
- **Public answers.** Reference fixes in a public repo can reach web search
  and future training data. That's fine for teaching cases, and one reason
  work cases stay in a private repo.
- **Site drift.** playwright.dev will change. Controls catch it per batch;
  a local copy ends it.
