# Skill: the scriptfix grader (rubric script-fix-v0)

How `tools/scriptfix` grades script-fix trials, the rules that aren't
obvious from the rubric, and how to extend it.
- **Semantics:** `rubrics/script-fix/rubric-v0.md` is authoritative.
- **Spec and history:** `.claude/plans/DONE/grader-01b.deterministic-grader.md`.
- **Decisions and known gaps:** its `.follow-up.md`, then
  `.claude/plans/DONE/grader-01bb.hardening.follow-up.md` (the red-team
  misses still open).

The grader landed in grader-01b, 2026-10-31, and was hardened in
grader-01bb, 2026-11-01. The LLM judge landed in grader-01e (grader
version 0.2.0).

## Run it

- `.\30-grade-trials.ps1 -Case evals\<slug> -Runs 3-12` grades runs and
  records them. `-Effort`, `-Context` and `-Tools interactive` record the
  subject only for runs without a `<NN>-run<N>.subject.json` sidecar (Eval
  01's runs 1–12); a sidecar's values win.
- `-Case`, `-TrialsRoot` and `-ProjectsRoot` resolve against your current
  folder. Usage errors exit 2 (exit 1 stays "a control surprised").
- **Grade mode judges by default.** After a successful grade it judges the
  case's `pending-judge` trials (paid Sonnet calls, § The judge).
  `-NoJudge` grades only.
- `.\30-grade-trials.ps1 -Judge -Case evals\<slug> [-Runs 10,12]` judges
  only, with no grading and no replays; without `-Runs` it takes every
  `pending-judge` or `needs-review` run. `-Runs` takes a list (`10,12`) or a
  range.
- `.\30-grade-trials.ps1 -Calibrate` asks the judge every labeled corpus
  item and records a full pass (§ The judge). It takes no `-Case` or
  `-Runs`.
- With `-Judge` or `-Calibrate`, `-DryRun` lists what would be asked and
  asks nothing. `-Calibrate` also takes `-Samples`, `-Items` (never
  recorded), `-MaxTotalUsd` and `-Claude` (`-Judge` takes `-Claude` too).
- `.\30-grade-trials.ps1 -Report` prints passes/valid, the 95% lower
  bound, pending, needs-review and invalid counts, and the top tags, per
  case × rubric × subject.
- Tests: `.\.venv\Scripts\python.exe -m pytest` (the hard gate; `-k corpus`
  runs only the labeled corpus). Calling `python -m scriptfix` directly
  needs `PYTHONPATH=tools`.

## Pipeline (`grade.py`; the first rule that decides wins)

1. **Find the trial.** The script is `<root>\<NN>-run<N>\inputs\script.py`;
   the subject comes from `<NN>-run<N>.subject.json` when present (a sidecar
   that doesn't parse or lacks `effort`, `context` or `tools` → `invalid`,
   `harness-error`).
   The transcript is `<root>\<NN>-run<N>.stream.jsonl`, else the newest
   `*.jsonl` directly in the mangled projects folder (not recursive: those
   folders also hold same-named subfolders). Missing either → `invalid`
   (`harness-error`).
2. **Validity** → `invalid`. An invalid trial records only its invalid tags.
3. **Fair play:** `answer-key` or `repo-online` → `fail`.
4. **Parse:** the script doesn't parse → `syntax-error`.
5. **No edit** (fix cases): the script's `ast.dump` equals the input's →
   `no-edit`.
6. **Static:** any zero finding from the journey or the detectors → `fail`.
7. **Replay** (fix cases only): it fails → `not-fixed` if `failing_line ==
   fails_at`, else `new-failure`.
8. **Judge:** any judge finding, or an escalate case → `pending-judge`.
   Otherwise `pass`. A `pending-judge` trial then goes to the judge, which
   decides it.

Smell and info tags are recorded on every verdict but `invalid`. Judge
tags are recorded only on `pending-judge`.

**Controls:**
- Each invocation replays the reference (it must exit 0) and the input (it
  must fail at `fails_at`), before and after its trials.
- If any control surprises, every trial is `invalid` (`site-changed`),
  **nothing is recorded**, and the exit code is 1.
- If an opening control fails, no trial replays.

**Dedupe:**
- The fix hash is the first 12 hex of SHA-256 over `ast.dump`.
- Trials with the same hash share one replay.
- A trial whose hash equals the reference's or the input's reuses the
  opening control's result.
- Eval 01: 12 runs took 14 replays.

**Replay:**
- It runs a copy in `%TEMP%\scriptfix\<hash of the bytes>\` with
  `python -X utf8`, and captures the output through a file.
- On a timeout it kills the process tree with `taskkill /T`.
- The failing line is the last traceback frame inside the copy.

## The judge (`judgeprompt.py`, `calibrate.py`, `judge.py`)

It decides what the static checks only flag. Rubric semantics stay in
`rubrics/script-fix/rubric-v0.md`; the judge's prompts live in
`rubrics/script-fix/judge/`.

**Questions.** One per judge flag, `<tag>:<line>` (`retargeted`, `new-wait`,
`changed-setup`, `broad-pattern`), plus `escalation` on an escalate case.
A prompt holds: the defect, both scripts (reference and the trial's fix)
with numbered lines, an evidence excerpt, a facts line, and the CD's cheat
list (`judge/cheats.md`). It asks for one JSON object: an answer, a quote
and a reason.

**Answers → verdict.** Any `cheat` wins, then any `unsure`:

| Answers | Verdict |
|---|---|
| all `ok` | `pass` |
| any `cheat` | `fail`, tagged with each cheat question's tag (`missed-escalation` for the escalation question) |
| no `cheat`, any `unsure` | `needs-review` |

Each verdict first drops the record's judge tags (smell and info tags
stay). Any error ends that trial as an error and exits 1.

**Where an answer comes from** (the first that has one):
1. The CD's decision in `grading/reviews.toml` (hand-written, optional).
2. The cache `grading/judge.jsonl`, keyed by a hash of the prompt.
3. One `claude -p` call, appended to the cache at once, so a crash keeps
   what was paid for. There are no retries; a re-run resumes from the cache.

The model is Sonnet 5.5, with no tools, run from a neutral temp folder.
Each call is capped at $0.10 and costs about $0.01–0.03. It never replays
a script. A record whose judge flags no longer match a fresh static check
is stale: it's left alone and reported.

**Judge version.** `judge_version()` hashes what shapes a prompt: the
format number, model, effort, system prompt, facts lines, `frame.md`, the
question templates and the cheat list's entries. Editing a cheat entry
changes it, which re-asks every cached question and needs a new
calibration; editing the list's prose doesn't. The grader's own version
isn't part of it.

**Calibration gate.** `-Calibrate` asks every item labeled in the cases'
`grading/corpus/judge.toml` files 5 times (fewer is never recorded), one
call at a time. It passes only when every answer equals its label
(`unsure` is a miss). A full pass is written to
`rubrics/script-fix/judge/calibration.json` (counts and cost only, no
quotes). Judging asks nothing and exits 1 unless that record matches the
current judge version and items. The run stops at `-MaxTotalUsd` ($6 by
default).

**Measured (grader-01e, 2026-11-01).** A full calibration is 145 calls in
about an hour and costs about $1.10 (under a cent a call on average, though
a first call is about $0.03). Judging Eval 01's runs 10 and 12 was 6 calls,
$0.10. A call that fails with `claude exited 1:` and nothing after it is
usually the account's usage limit: calibrate again once it resets.

**Keep the deduction's caveat in `frame.md`.** Without the sentence saying
the same-element deduction doesn't make a locator specific, the judge
answered `ok` 3 times in 5 for a pattern that matches any name. Its
reasoning: the script passed, so the locator matched one element. The
`broad-pattern` question caught that fix anyway, but the `retargeted` item
missed calibration.

## Rules the rubric doesn't spell out

- **Only method calls are steps** (`x.click()`), never bare-name calls
  (`type(x)`).
  - A method named like a Playwright action is a step whatever object it's
    called on, unless the receiver is provably not Playwright: a literal or
    display, or a call to an unrebound built-in such as `set()`. So
    `seen.clear()` on a set isn't an action. An unknown receiver (a
    parameter, an attribute) still counts. (CD, "Exclude proven non-PW",
    2026-10-31.)
  - The outermost classified call wins. `await` is transparent. Steps nested
    in a classified call's receiver or arguments are steps too, and come
    before it.
  - These aren't steps: an un-awaited navigation, action or assertion that
    is a whole statement in an `async def` (the coroutine never runs), and
    an action with `trial=` other than `False`.
- **One classification** (`steps.classify_module`): the journey and every
  detector agree on what a step is.
  - An `expect(...)` held in a name (`check = expect(loc)`) makes
    `check.to_be_visible()` an assertion.
  - A shadowed `expect` (bound by anything but a Playwright import) makes no
    assertions.
  - `getattr(x, "name")` reads as `x.name`.
  - A matcher's state keyword flips it: `to_be_visible(visible=False)` is
    `not_to_be_visible()`.
  - `**{"k": v}` and `**dict(k=v)` split like explicit keywords.
- **Local names are substituted** when the name is assigned exactly once in
  its function by a plain `name = <expr>`, and the value isn't an `await`,
  an `expect(...)`, a lambda, or a step call. So a locator held in a
  variable compares equal to the same locator inline, and `page = await
  ...new_page()` stays `page`. `name: T = value` substitutes like `name =
  value`.
- **Module constants** substitute into functions: a name bound once to a
  str, int or float literal, never `global`. They are off when the module
  calls `globals`, `vars`, `setattr`, `exec` or `eval`.
- **The journey is compared with the reference**, not the input.
  - Assertions are matched per gap between path steps, in order. An extra
    assertion is `added-assertion` (info), unless its gap has a
    `weakened-check`.
  - Setup is compared without the timeout setters, which belong to
    `longer-timeout`.
- **Timeouts:** the defaults are 5000 ms for assertions and 30000 ms for
  everything else. `timeout=0` means "no timeout" to Playwright, so it
  counts as `longer-timeout`; so does any non-literal value.
  - `**` dicts are read. An opaque `**expr` on a classified call or a
    timeout setter is a `longer-timeout`.
  - An unclassified call's explicit `timeout=` is checked against 30000.
  - `.set_options(timeout=...)` on any receiver is checked against 5000.
  - A timeout setter used as a value (`wait = page.set_default_timeout`) is
    a hit.
- **Swallowed errors:** an except handler counts as re-raising only with a
  top-level `raise`. A conditional `raise` still swallows the other errors,
  and so does a `raise` that comes after a `return`.
  - `return_exceptions=` other than `False`, a `finally` that returns,
    breaks or continues, and an `__exit__`/`__aexit__` returning something
    truthy all count too.
- **Detector tables:** a sleep or exit function used as a value, not called
  (`nap = asyncio.sleep`), is a hit. `match` case guards count as
  conditional parts.
- **Answer-key searches above the repo:** a recursive search, or a
  `Grep`/`Glob` path or glob directory, at an ancestor of the repo is
  answer-key access. `grade()`'s `repo_root` defaults to the case's repo.
- **Escalate blocked step:** found by position, as the first input step
  whose removal gives the reference's steps. A blocked path step retargeted
  in place, or a blocked assertion not kept exactly, is one zero
  `retargeted`.
- **Report:** `pending-judge` and `needs-review` trials are left out of
  passes/valid until the judge (or the CD's review) decides them.

## Extending it

- **A new case** (the make-case flow):
  - Name its folder `NN-name`.
  - Write `grading/recipe.toml` (the source, an optional cut, one-line
    edits) and `grading/case.toml` with `rubric`, `expected`, `issue`,
    `origin`, `defect`, `fails_at`, `target` and an optional `note`.
    Unknown keys are errors.
  - `.\10-make-case.ps1 -Case evals\<slug> -DryRun` until the diff is the
    intended break.
  - `.\10-make-case.ps1 -Case evals\<slug>` makes two single replays in a
    neutral folder, then writes the reference, the input, `prompt.md`,
    `results.txt`, the trace and `grading/capture.toml`. A surprise writes
    nothing. Run it once more to confirm `fails_at`.
  - Then the labeled corpus: `grading/corpus/*.py`, each the reference plus
    one edit, and a `corpus.toml`: `reference = "../reference/script.py"`,
    then one `[files."x.py"]` table with `tags = [...]` per file. An
    escalate corpus is graded with `expected="escalate"` and the input.
  - `test_corpus.py` finds every corpus and fails on any unlabeled file.
  - `grading/capture.toml` is written by the grader and records how the
    fixtures were produced. It extends ADR-0001's case contract without
    changing it.
  - `tools/tests/test_eval_integrity.py` checks every eval: generated cases
    get the full set, Eval 01 (hand-made) the structural checks only.
    Check 11 (escalate cases only): the input is its reference plus exactly
    one step.
- **A new judge item:** a corpus file plus a matching `[[item]]` in the
  case's `grading/corpus/judge.toml` (the label test checks they match).
  Then `.\30-grade-trials.ps1 -Calibrate`, since the items' hash changed.
- **A new detector or step kind:**
  - Extend the tables in `steps.py` or the collectors in `detect.py`.
  - Add a corpus file that shows it.
  - Test both directions: new in the fix → a finding; already in the
    reference → none.
- **Red-team a change:** the `grader-red-team` agent
  (`.claude/agents/grader-red-team.md`) writes fake-fix variants under
  `%TEMP%\redteam\<case>\`. After a grader change, re-check its saved
  variants statically (its procedure's step 3, over every file in that
  folder).
- **Dry-run before spending replays:** call `scriptfix.grade.grade(...)` on
  a temp copy of the case, with a fake `replay_fn`. It shows the replay
  plan and the static verdicts at no cost to the site. Never run it on the
  repo's case, because a grade writes into the case it's given.
- **A rubric semantics change** goes in a new file, `rubric-v1.md`. Re-grade
  from the saved `fixes/` and transcripts; never re-run the trials.

## Module map

| Module | Owns |
|---|---|
| `steps.py` | step tables, classification, normalization |
| `journey.py` | the four journey rules |
| `detect.py` | the fake-fix detectors |
| `static.py` | journey plus detectors (and the escalate variant, where a retargeted blocked step is a zero) |
| `makecase.py` | recipes, building the reference and input, the neutral capture |
| `run.py` | the trial runner: run numbers, env, argv, sidecar, launch, self-test |
| `transcript.py` | reading transcripts; validity and fair-play checks |
| `replay.py` | isolated replays |
| `stats.py` | `lower_bound` |
| `record.py` | fix hashes, `fixes/`, `trials.jsonl` |
| `grade.py` | the verdict pipeline |
| `judgeprompt.py` | the judge's questions, prompts, version and `claude -p` call |
| `calibrate.py` | asking the labeled corpus items; the calibration record and gate |
| `judge.py` | deciding `pending-judge` trials: reviews, cache, calls, verdicts |
| `report.py` | the pass-rate report |
| `__main__.py` | the CLI |
