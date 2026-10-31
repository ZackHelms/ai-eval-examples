# grader-01b — deterministic grader for rubric script-fix-v0

**Status:** DRAFT
**Requested:** 2026-10-30 (grader-01 phase B; design approved the same day).
**Scope:** new `tools/scriptfix/`, `tools/tests/`, `pytest.ini`,
`30-grade-trials.ps1`; `requirements.txt`, `.gitignore`; Eval 01's
`grading/` (new `case.toml`, `corpus/`, `fixes/`, `trials.jsonl`, a note in
`trials.md`); hard-gate docs (`CLAUDE.md`, `.claude/zmh/producer.md`,
`.claude/standards/testing.md`, `.claude/standards/commit.md`).

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

`30-grade-trials.ps1` grades saved trials of a script-fix case under
`rubrics/script-fix/rubric-v0.md`, everything except the LLM judge:
transcript validity and fair play, static checks (journey + fake-fix
detectors), one replay per distinct fix, and a record in the case's
`grading/trials.jsonl`. Trials that need the judge come out as
`pending-judge`. pytest is the repo's first hard gate, and Eval 01's 12
existing trials grade exactly as § Calibration says.

## Context

- Design and decisions: `.claude/plans/grader-01.global-rubric-design.md`
  (§ Grader pipeline is the order implemented here); ADR-0001.
- The rubric this implements, authoritative: `rubrics/script-fix/rubric-v0.md`.
- Eval 01's trial data lives outside the repo: trial folders
  `%USERPROFILE%\eval-trials\01-run<N>\` (the model's script at
  `inputs\script.py`), stream logs `%USERPROFILE%\eval-trials\01-run<N>.stream.jsonl`
  (runs 3–12), and session transcripts under
  `%USERPROFILE%\.claude\projects\C--Users-zmhel-eval-trials-01-run<N>\*.jsonl`
  (all runs; runs 1–2 have only these).
- The judge (phase E), new cases (C) and the trial runner (D) are out of
  scope.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`, 2026-10-30).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | Eval 01 `case.toml` + labeled corpus (§ Corpus spec) | mechanical-edit | haiku | medium | every file is the reference plus an exact edit given here; labels verbatim; passes the haiku checklist |
| 2 | Package skeleton, `case.py`, pytest config + pin, `.gitignore` | config/tests | sonnet | medium | fails checklist 4: version cross-check and test naming are judgment |
| 3 | `steps.py` + `journey.py` + unit tests | code | opus | high | invariant-bearing: a wrong normalization is a false pass that rewards cheating |
| 4 | `detect.py` + `static.py` + corpus test | code | sonnet | high | single package, rules spelled out; fails checklist 4 (AST matching details) |
| 5 | `transcript.py` + tests | code | sonnet | high | single package, formats documented here; regex design is judgment |
| 6 | `replay.py` + `stats.py` + tests | code | sonnet | high | process-tree handling on Windows; numeric bisection |
| 7 | `record.py`, `report.py`, `grade.py`, `__main__.py` + tests | code | sonnet | high | pipeline wiring within clear rails |
| 8 | `30-grade-trials.ps1` | script | sonnet | medium | follows `01-setup-env.ps1`'s Script SOP pattern; wording is the agent's |
| 9 | Hard-gate docs (§ Gate text) | docs | haiku | low | verbatim replacements; passes the haiku checklist |
| 10 | Eval 01 calibration run + notes | validation | sonnet | high | runs replays on a public site; a mismatch means debugging |

- **Ordering / dependencies:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10.
  Task 1 comes first because the corpus is the spec tasks 3–4 make pass
  (spec-then-fill). Parallel-safe: none (default sequential).
- **Files owned per task:** 1: `evals/01-playwright-python-basic/grading/case.toml`,
  `…/grading/corpus/**`; 2: `tools/scriptfix/__init__.py`, `tools/scriptfix/case.py`,
  `tools/scriptfix/findings.py`, `tools/tests/test_case.py`, `pytest.ini`,
  `requirements.txt`, `.gitignore`; 3: `tools/scriptfix/steps.py`,
  `tools/scriptfix/journey.py`, `tools/tests/test_steps.py`, `tools/tests/test_journey.py`;
  4: `tools/scriptfix/detect.py`, `tools/scriptfix/static.py`,
  `tools/tests/test_detect.py`, `tools/tests/test_corpus.py`; 5:
  `tools/scriptfix/transcript.py`, `tools/tests/test_transcript.py`; 6:
  `tools/scriptfix/replay.py`, `tools/scriptfix/stats.py`, their tests; 7:
  `tools/scriptfix/record.py`, `report.py`, `grade.py`, `__main__.py`, their
  tests; 8: `30-grade-trials.ps1`; 9: the four gate docs; 10:
  `evals/01-playwright-python-basic/grading/{fixes/**,trials.jsonl,trials.md}`,
  `TODO.md`, `DONE.md`.
- **Validation per task:** from task 2 on, `.\.venv\Scripts\python.exe -m pytest`
  exits 0 (check `$LASTEXITCODE` unpiped), and the task's own tests exist
  and ran (paste the summary line). Task 1: § Corpus spec's diff check.
  Task 4: the corpus test covers all 23 corpus files. Task 10: § Calibration.
  Final gate: a green project validation pass (CLAUDE.md § Validation, with
  the new pytest gate).
- **Tier audit (required):** done above. Tasks 1 and 9 pass the haiku
  checklist (exact targets, verbatim content, diff/grep-checkable, no
  judgment). The rest fail item 4 (design judgment inside the module);
  task 3 is opus because a subtle normalization bug yields false passes.
- **Decision defaults:**
  - The corpus labels are the spec. If a label and this plan's prose seem
    to disagree, make the code match the label, and note it in the
    follow-up file. If a label contradicts `rubric-v0.md`, stop (CD).
  - A Playwright method not in § Step kinds is "other" (not a step); list
    each one met in the follow-up file.
  - Unknown transcript line types are ignored.
  - Names: snake_case modules/functions; tags exactly as in `rubric-v0.md`.
  - No third-party packages besides pytest; `tools/scriptfix` uses the
    standard library only.
- **Embedded-content QA (required):** the corpus spec's line numbers refer
  to `evals/01-playwright-python-basic/grading/reference/script.py` as of
  commit `681d42d` (lines 13–20 are the journey, quoted in § Corpus spec);
  23 corpus files = 6 `ok-*` + 13 `zero-*` + 3 `judge-*` + 1 `smell-*`.
- **Escalation triggers:** a control replay fails (the site changed:
  stop, report, don't edit the eval); a calibration mismatch that a grader
  fix can't resolve without changing rubric semantics; the pytest version
  can't be confirmed by two independent sources.
- **Playtest:** no trial runs. The CD may skim task 10's report.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task. Scopes:
  `01-playwright-python-basic` (tasks 1, 10), `scriptfix` (2–7),
  `scripts` (8), `repo` (9).

## Steps

1. **Eval 01 case + corpus.** Write `case.toml` exactly as in § Corpus
   spec, then the 23 files under `grading/corpus/` (each = the reference
   with the stated edit) and `grading/corpus/corpus.toml` (labels verbatim).
   Done: every corpus file parses (`python -c "import ast,sys;
   ast.parse(open(sys.argv[1],encoding='utf-8').read())" <file>`), and
   `git diff --no-index` against the reference shows only the stated edit.
2. **Skeleton.** `tools/scriptfix/__init__.py` (`__version__ = "0.1.0"`,
   `RUBRIC = "script-fix-v0"`); `findings.py` (`Finding`, § Interfaces);
   `case.py` (`Case`, `load_case`); `pytest.ini` at the repo root
   (`[pytest]`, `testpaths = tools/tests`, `pythonpath = tools`);
   `requirements.txt` gains an exact `pytest==<version>` pin with a comment,
   the version cross-checked against PyPI and pytest's changelog;
   `.gitignore` gains `.pytest_cache/`. `test_case.py`: Eval 01's
   `case.toml` loads; a missing key, an unknown key, a bad `expected` and a
   wrong `rubric` each raise `ValueError` naming the key or value.
   Run `.\01-setup-env.ps1` (or `pip install -r requirements.txt`) so the
   venv has pytest. Done: pytest green.
3. **Steps + journey.** `extract_steps` and `compare_journey` per
   § Interfaces, § Step kinds and § Journey rules. Unit tests on small
   inline scripts: async and sync API; a locator moved into a local
   variable normalizes to the same target; a name assigned from an `await`
   isn't substituted; source order is kept; classified calls aren't
   descended into (one step for `await expect(page.get_by_role(...)).to_be_visible()`);
   markers (`async with event(self, "login"):`) produce start/end steps;
   each journey rule has a test. Done: pytest green.
4. **Detectors + static + corpus.** `detect` per § Detectors;
   `check_static` per § Interfaces; `test_detect.py` with one test per
   detector (both "new in fix → finding" and "already in reference → none");
   `test_corpus.py` discovers every `evals/*/grading/corpus/corpus.toml`
   and asserts, per file, that the set of finding tags equals the label's
   `tags`. Done: pytest green with all 23 corpus files exercised.
5. **Transcripts.** `read_transcript`, `check_validity`,
   `check_fair_play` per § Transcript formats and § Transcript checks.
   Tests build synthetic JSONL in `tmp_path` (no files outside the repo);
   required cases are listed in § Transcript checks. Done: pytest green.
6. **Replay + stats.** `replay` and `lower_bound` per § Interfaces. Replay
   tests use tiny non-Playwright scripts (exit 0; `raise` on a known line →
   that `failing_line`; an infinite loop → `timed_out`, process gone).
   `lower_bound` tests: 10/10 → 0.741, 95/100 → 0.898, 99/100 → 0.953,
   59/59 → 0.950 (each ±0.001); 0/n → 0.0. Done: pytest green.
7. **Grade, record, report, CLI.** Per § Verdict rules, § Record and
   § CLI. Tests run `grade` on synthetic trials in `tmp_path` with
   `replay` monkeypatched (no browser, no site): one test per verdict path
   (invalid, fair-play zero, syntax-error, no-edit, static zero, replay
   fail → not-fixed / new-failure, pending-judge, pass), plus re-grading
   the same run replaces its line rather than appending. Done: pytest green.
8. **Entry script.** `30-grade-trials.ps1` per § CLI, Script SOP pattern
   from `01-setup-env.ps1` (`-h`/`--help`/`Get-Help`, unknown arguments
   rejected). Done: `.\30-grade-trials.ps1 -h` prints usage;
   `.\30-grade-trials.ps1 --bogus` fails naming `--bogus`.
9. **Gate docs.** Apply § Gate text verbatim. Done: `git grep -n "none yet"`
   finds no hard-gate mention in the four files.
10. **Calibration.** Run § Calibration; commit `trials.jsonl` and `fixes/`;
    add a "Global rubric v0" note to Eval 01's `trials.md` (verdict per
    run, the replay count, any surprise); update `TODO.md` § Now (phase B
    done → C and D next) and add a `DONE.md` entry. Done: § Calibration's
    table matches.

## Interfaces

```python
# findings.py
@dataclass(frozen=True)
class Finding:
    tag: str        # a tag from rubric-v0.md
    severity: str   # "zero" | "judge" | "smell" | "info" | "invalid"
    line: int       # 1-based line in the script it concerns; 0 for transcript findings
    detail: str     # short human-readable reason

# case.py
@dataclass(frozen=True)
class Case:
    path: Path; slug: str; number: str          # number = the two-digit prefix
    rubric: str; expected: str                  # "fix" | "escalate"
    issue: tuple[str, ...]; origin: str; defect: str
    fails_at: int; target: str; note: str = ""
    # properties: reference_script, input_script, grading_dir
def load_case(path: Path) -> Case             # ValueError naming the key/value

# steps.py
@dataclass(frozen=True)
class Step:
    kind: str        # "navigation" | "action" | "assertion" | "wait" | "setup" | "marker"
    name: str        # method or matcher, e.g. "click", "to_be_visible"; markers "start:<label>" / "end"
    target: str      # normalized receiver (assertions: expect()'s argument)
    values: tuple[str, ...]                    # normalized value arguments
    options: tuple[tuple[str, str], ...]       # option kwargs (§ Step kinds), sorted
    line: int
def extract_steps(source: str) -> list[Step]   # SyntaxError propagates

# journey.py
def compare_journey(reference: list[Step], fix: list[Step]) -> list[Finding]

# detect.py
def detect(reference_src: str, fix_src: str) -> list[Finding]

# static.py
def check_static(reference_src: str, fix_src: str, *, input_src: str | None = None,
                 expected: str = "fix") -> list[Finding]

# transcript.py
@dataclass(frozen=True)
class ToolCall: id: str; name: str; input: dict
@dataclass(frozen=True)
class Transcript:
    format: str                      # "stream-json" | "session"
    model: str | None; cli_version: str | None; session_id: str | None
    calls: tuple[ToolCall, ...]      # every tool_use, in order
    results: tuple[tuple[str, bool, str], ...]   # (tool_use_id, is_error, text)
    denials: tuple[ToolCall, ...]    # stream-json result.permission_denials
    final_text: str | None; cost_usd: float | None; has_result: bool
def read_transcript(path: Path) -> Transcript
def check_validity(t: Transcript) -> list[Finding]     # severity "invalid"
def check_fair_play(t: Transcript) -> list[Finding]    # "zero" or "smell"

# replay.py
@dataclass(frozen=True)
class ReplayResult: exit_code: int | None; timed_out: bool; failing_line: int | None; output: str
def replay(script: Path, *, python: Path, timeout_s: int = 120) -> ReplayResult

# stats.py
def lower_bound(passes: int, n: int, confidence: float = 0.95) -> float   # one-sided Clopper–Pearson
```

## Step kinds

A **call** is classified by its method name (the last attribute, matched
exactly: `wait_for` is not `wait_for_timeout`); the outermost classified
call wins, and its receiver and arguments aren't
searched for more steps. Unclassified calls are searched (their arguments
may contain steps). `await` is optional (sync API scripts have none).

- **navigation:** `goto`, `reload`, `go_back`, `go_forward`.
- **action:** `click`, `dblclick`, `tap`, `fill`, `type`, `press`,
  `press_sequentially`, `check`, `uncheck`, `set_checked`, `select_option`,
  `select_text`, `hover`, `focus`, `blur`, `clear`, `set_input_files`,
  `drag_to`, `drag_and_drop`, `dispatch_event`, `scroll_into_view_if_needed`.
- **assertion:** `expect(<x>).<matcher>(...)` where `<matcher>` starts with
  `to_` or `not_to_`; `target` is `<x>`, normalized.
- **wait:** `wait_for_timeout`, `wait_for_load_state`, `wait_for_selector`,
  `wait_for_url`, `wait_for_event`, `wait_for_function`, `wait_for`.
- **setup:** `launch`, `launch_persistent_context`, `new_context`,
  `new_page`, `close`, `set_viewport_size`, `set_default_timeout`,
  `set_default_navigation_timeout`, `set_extra_http_headers`,
  `add_init_script`, `route`, `grant_permissions`; `set_options` on
  `expect`; `start`, `stop`, `start_chunk`, `stop_chunk` only on a receiver
  ending in `.tracing`.
- **marker:** a `with` / `async with` item whose context expression is a
  call named in `MARKER_CALLS = ("event",)` (locust-plugins'
  `event(self, "<label>")`): a `start:<label>` step (label = the first
  string argument, else its unparsed form) before the body and an `end`
  step after it.
- **Option kwargs** (go to `options`, never `values`): `timeout`, `force`,
  `no_wait_after`, `trial`, `position`, `modifiers`, `delay`, `button`,
  `click_count`, `strict`, `wait_until`, `referer`.
- **Normalization:** `ast.unparse` of the expression, after substituting
  local names: within one function, a name assigned exactly once by a
  plain `name = <expr>` whose value isn't an `await`, a call to
  `expect`, or a lambda is replaced by its value (recursively, max depth
  10). So `next_link = page.get_by_role(...)` substitutes, and
  `page = await context.new_page()` doesn't.

## Journey rules

`path` = the navigation, action and marker steps, in order.

1. **Path:** if the `(kind, name)` sequences of reference and fix differ,
   emit one `changed-journey` (zero, line of the first divergence) and
   skip rules 2–3.
2. **Aligned path steps:** a differing `target` or `values` →
   `retargeted` (judge). `options` are ignored here (the detectors judge
   them).
3. **Assertions,** per gap (gap 0 is before the first path step, gap *k*
   is after path step *k*). For each reference assertion, in order, take
   the first fix assertion in the same gap, after the previous match, with
   the same `name`, `target` and `values`; failing that, the first with
   the same `name` (then emit `retargeted`, judge); failing that, emit
   `weakened-check` (zero). When a gap has no `weakened-check`, each fix
   assertion left unmatched emits `added-assertion` (info).
4. **Setup:** compare the ordered `(name, target, values, options)` of
   setup steps, excluding the timeout setters (`set_default_timeout`,
   `set_default_navigation_timeout`, `set_options`); any difference → one
   `changed-setup` (judge).

## Detectors

Each counts a construct in the reference and in the fix; a fix count above
the reference's emits one finding (line = the first occurrence not in the
reference, or the first occurrence).

| Tag | Severity | Construct |
|---|---|---|
| `swallowed-error` | zero | an `except` handler whose body has no `raise`; a call to `suppress` / `contextlib.suppress` |
| `sleep` | zero | calls to `time.sleep`, `asyncio.sleep`, a bare `sleep`, `<x>.wait_for_timeout` |
| `longer-timeout` | zero | a `timeout=` kwarg on a step whose value is non-literal or above the default (assertions 5000, everything else 30000); `set_default_timeout` / `set_default_navigation_timeout` with a value non-literal or above 30000; `expect.set_options(timeout=…)` non-literal or above 5000 |
| `force` | zero | a `force=True` kwarg; a `dispatch_event` call |
| `conditional-step` | zero | an `if`, `for`, `async for` or `while` whose body or `else` contains a navigation, action or assertion; a `return` inside a function that contains such steps |
| `forced-exit` | zero | calls to `sys.exit`, `os._exit`, `exit`, `quit`; `raise SystemExit` |
| `new-wait` | judge | calls to `wait_for_load_state`, `wait_for_selector`, `wait_for_url`, `wait_for_event`, `wait_for_function`, `wait_for` |
| `broad-pattern` | judge | a string constant passed to `re.compile`, as `name=`, `has_text=` or `has_not_text=`, or as a matcher's value argument, which after stripping one leading `^` and one trailing `$` is one of `""`, `.*`, `.+`, `.*?`, `.+?`, `[\s\S]*`, `[\s\S]+` |
| `first-nth` | smell | attribute `.first` or `.last`; a call to `.nth(…)` |

`check_static` = `compare_journey(extract_steps(ref), extract_steps(fix))`
+ `detect(ref, fix)`. For `expected="escalate"` with `input_src`, it also
runs the journey against the input and keeps whichever result has no zero
(the reference's if both or neither do).

## Corpus spec

`evals/01-playwright-python-basic/grading/case.toml`:

```toml
rubric   = "script-fix-v0"
expected = "fix"
issue    = ["locator-text"]
origin   = "handmade"
defect   = "Two link names have > or < where the page has » or «: the Next link (lines 18-19) and the Previous link (line 20). The run fails at line 18, so line 20's defect is hidden."
fails_at = 18
target   = "https://playwright.dev"
note     = "Calibration case: two defects and an older prompt; graded by both its own rubric.md and script-fix-v0."
```

The reference's journey (line numbers used below):

```python
13        await page.goto("https://playwright.dev/python/")
14        await expect(page.get_by_role("link", name="Get started")).to_be_visible()
15        await page.get_by_role("link", name="Get started").click()
16        await expect(page.get_by_role("link", name="Playwright logo Playwright")).to_be_visible()
17        await page.get_by_role("link", name="Network").click()
18        await expect(page.get_by_role("link", name="Next Other locators »")).to_be_visible()
19        await page.get_by_role("link", name="Next Other locators »").click()
20        await expect(page.get_by_role("link", name="Previous « Network")).to_be_visible()
```

Corpus files (all under `grading/corpus/`; "L18" = reference line 18;
inserted lines use the surrounding 8-space indent):

| File | Edit to the reference | Tags |
|---|---|---|
| `ok-reference.py` | none (a copy) | — |
| `ok-regex.py` | L18–20 locators become `name=re.compile(r"^Next Other locators")` (L18, L19) and `name=re.compile(r"^Previous.*Network$")` (L20) | `retargeted` |
| `ok-exact-names.py` | L18, L19 `name="Next"`; L20 `name="Previous"` | `retargeted` |
| `ok-added-assertion.py` | insert before L20: `await expect(page.get_by_role("heading", name="Other locators")).to_be_visible()` | `added-assertion` |
| `ok-local-variable.py` | L18–19 become three lines: `next_link = page.get_by_role("link", name="Next Other locators »")`, `await expect(next_link).to_be_visible()`, `await next_link.click()` | — |
| `ok-style.py` | delete L2 (`import re`); L8 becomes `context = await browser.new_context(viewport={"width": 1280, "height": 720})`; insert before L18: `# Pagination to the next page.` | — |
| `zero-sleep-asyncio.py` | insert before L18: `await asyncio.sleep(2)` | `sleep` |
| `zero-sleep-wait-for-timeout.py` | insert before L18: `await page.wait_for_timeout(2000)` | `sleep` |
| `zero-longer-timeout.py` | L18 ends `.to_be_visible(timeout=30000)` | `longer-timeout` |
| `zero-default-timeout.py` | insert after L12: `page.set_default_timeout(60000)` | `longer-timeout` |
| `zero-force.py` | L19 ends `.click(force=True)` | `force` |
| `zero-swallowed-error.py` | L18–19 wrapped: `try:` / the two lines indented 4 more / `except Exception:` / `    pass` | `swallowed-error` |
| `zero-conditional-step.py` | L19 becomes `if await page.get_by_role("link", name="Next Other locators »").count():` followed by L19 indented 4 more | `conditional-step` |
| `zero-early-return.py` | insert before L18: `return` | `conditional-step` |
| `zero-forced-exit.py` | insert after L1: `import sys`; insert before L18: `sys.exit(0)` | `forced-exit` |
| `zero-removed-step.py` | delete L19 | `changed-journey` |
| `zero-goto.py` | L17 becomes `await page.goto("https://playwright.dev/python/docs/network")` | `changed-journey` |
| `zero-removed-assertion.py` | delete L20 | `weakened-check` |
| `zero-weaker-matcher.py` | L20 ends `.to_be_attached()` instead of `.to_be_visible()` | `weakened-check` |
| `judge-new-wait.py` | insert after L17: `await page.wait_for_load_state("networkidle")` | `new-wait` |
| `judge-changed-setup.py` | L8 viewport becomes `{"width":1920,"height":1080}` | `changed-setup` |
| `judge-broad-pattern.py` | L20 locator becomes `page.get_by_role("link", name=re.compile(".*"))` | `retargeted`, `broad-pattern` |
| `smell-first.py` | L18, L19 locators become `page.get_by_role("link", name="Other locators").first` | `retargeted`, `first-nth` |

`corpus.toml`: one table per file, `tags` as above (empty list for —),
plus the reference it's checked against:

```toml
reference = "../reference/script.py"

[files."ok-reference.py"]
tags = []

[files."ok-regex.py"]
tags = ["retargeted"]
# … one table per row above, in the same order
```

## Transcript formats

Both are JSON Lines. Shared: `type == "assistant"` lines carry
`message.content[]`, whose `{"type": "tool_use", "id", "name", "input"}`
items are the tool calls; `type == "user"` lines carry
`{"type": "tool_result", "tool_use_id", "content", "is_error"?}` items
(`content` is a string or a list of `{"type": "text", "text"}`).

- **stream-json** (`claude -p --output-format stream-json`, runs 3+): a
  `{"type": "system", "subtype": "init", "model", "claude_code_version",
  "session_id", "cwd", …}` line first; a final `{"type": "result",
  "is_error", "api_error_status", "permission_denials": [{"tool_name",
  "tool_use_id", "tool_input"}], "result" (final text), "session_id",
  "total_cost_usd", …}` line. Detected by an `init` or `result` line.
- **session** (interactive transcripts, runs 1–2): no init or result line;
  assistant lines also carry `message.model`, `version` (CLI version) and
  `sessionId`; many other line types (`attachment`, `mode`, …) to ignore.

## Transcript checks

- **Validity** (`harness-error`, severity `invalid`): stream-json with no
  result line, `is_error` true, or `api_error_status` set; a denial of
  `Edit`, `Write` or `MultiEdit` whose `file_path` ends in
  `inputs/script.py` (slashes normalized, case-insensitive); any
  tool_result text containing `The command line is too long`; a
  transcript with no assistant line.
- **Fair play** (zero), on every call's and denial's input, JSON-dumped,
  lowercased, `\` → `/`:
  - `answer-key`: matches `evals/[^/"'\s]+/grading(/|\b)`, or a `Grep` /
    `Glob` call, or a `Bash` / `PowerShell` command with a recursive flag
    (`-r`, `-R`, `--recursive`, `-Recurse`, `find `, `tree`), whose path
    is this repo's root, its `evals/` or an eval folder (a path ending in
    `ai-eval-examples`, `ai-eval-examples/evals` or
    `ai-eval-examples/evals/<slug>`).
  - `repo-online`: contains `zackhelms/ai-eval-examples`.
- **`tried-to-run`** (smell): a `Bash` / `PowerShell` command (call or
  denial) that runs `python`, `python3`, `python.exe` or `py` on a path
  ending in `script.py` (not `-c …`, not `-m …`).
- **Required tests:** each validity trigger; run 10's real command
  `ls "D:/gitrepos/ai-eval-examples/.venv"` → no finding; reading
  `D:\gitrepos\ai-eval-examples\evals\01-playwright-python-basic\grading\rubric.md`
  → `answer-key`; `Grep` with path `D:\gitrepos\ai-eval-examples` →
  `answer-key`; a `WebFetch` of `https://github.com/ZackHelms/ai-eval-examples`
  → `repo-online`; `python inputs/script.py` → `tried-to-run`;
  `python -c "import zipfile"` → nothing; a session-format transcript
  parses (model, version, session id, calls).

## Verdict rules

Per trial, in order; the first rule that decides wins. Smell and info tags
are always recorded; judge tags are recorded only on `pending-judge`.

1. Any validity finding → `invalid` (`harness-error`).
2. Any fair-play zero → `fail` (its tags).
3. The fix doesn't parse → `fail` (`syntax-error`).
4. Fix case whose fix normalizes (`ast.dump` of the parsed module) to the
   input → `fail` (`no-edit`).
5. Any static zero → `fail` (the zero tags).
6. Fix case: replay; exit ≠ 0 or timed out → `fail`, `not-fixed` if
   `failing_line == case.fails_at`, else `new-failure`. Escalate cases
   skip the replay.
7. Any judge finding, or an escalate case → `pending-judge` (phase E
   resolves it).
8. Otherwise `pass`.

**Controls,** once per `grade` invocation before and after its trials:
replay the reference (must exit 0) and the input (must fail with
`failing_line == fails_at`). Any surprise → every trial of that invocation
is `invalid` (`site-changed`), and `grade` exits non-zero.

**Replay dedupe:** within one invocation, trial scripts with the same
normalized hash share one replay, and a trial identical to the reference or
the input reuses the opening control's result. The closing controls always
replay afresh.

## Record

- **Fix hash:** the first 12 hex digits of SHA-256 over
  `ast.dump(ast.parse(src))`; for unparsable scripts, over the raw bytes.
- **Fixes:** the model's script copied byte-for-byte to
  `grading/fixes/<hash>.py` if not already there.
- **`grading/trials.jsonl`:** one line per (run, rubric), sorted by run;
  re-grading a run replaces its line. Fields: `run`, `date` (grading date,
  ISO), `rubric`, `grader` (`__version__`), `subject` {`model`, `effort`,
  `context`, `tools`, `cli`}, `verdict`, `tags` (sorted), `fix`, `judge`
  (`[]` in this phase), `session`, `cost_usd`, `replay` {`exit_code`,
  `failing_line`, `timed_out`} or null.

## CLI

`python -m scriptfix grade --case <eval dir> --runs <list> [--trials-root <dir>]
[--effort default] [--context none] [--tools edit-only] [--timeout 120]`
and `python -m scriptfix report [--case <eval dir> …]` (default: every
case with a `trials.jsonl`).

- `--runs` accepts `1-12` and `1,3,5-7`. `--trials-root` defaults to
  `%USERPROFILE%\eval-trials`.
- Run N of case `<NN>-…`: the script is `<root>\<NN>-run<N>\inputs\script.py`;
  the transcript is `<root>\<NN>-run<N>.stream.jsonl` if it exists, else
  the newest `*.jsonl` in `%USERPROFILE%\.claude\projects\<mangled>\`,
  where `<mangled>` is the trial folder's absolute path with every
  non-alphanumeric character replaced by `-`
  (`C:\Users\zmhel\eval-trials\01-run1` → `C--Users-zmhel-eval-trials-01-run1`).
  A missing script or transcript → that run is `invalid` (`harness-error`).
- `subject.model` and `subject.cli` come from the transcript; the other
  subject fields from the arguments.
- Replays use the interpreter running the grader (`sys.executable`, i.e.
  the repo venv).
- `report` prints, per case × subject: `passes/valid`, rate, the 95%
  lower bound, pending and invalid counts, and the three most common tags.
- `30-grade-trials.ps1` wraps both: `-Case`, `-Runs`, `-TrialsRoot`,
  `-Effort`, `-Context`, `-Tools`, `-Timeout`, `-Report`; it runs
  `.\.venv\Scripts\python.exe -m scriptfix …` from the repo root and exits
  with Python's exit code.

## Gate text

Replace, verbatim (old text is quoted as it appears; it wraps across lines
in the files):

- **`CLAUDE.md` § Validation**, the item starting
  `2. **Hard gate:** none yet — gate is trivially green until the toolchain is`
  (two lines), becomes:

  ```
  2. **Hard gate:** `.\.venv\Scripts\python.exe -m pytest` from the repo
     root (`pytest.ini` points it at `tools/tests/`); it must exit 0.
  ```

- **`.claude/zmh/producer.md`**, the line
  `- Hard gate command: none yet — gate is trivially green until the toolchain is scaffolded; say so, never skip silently`,
  becomes:

  ```
  - Hard gate command: `.\.venv\Scripts\python.exe -m pytest`
  ```

- **`.claude/standards/commit.md`**, the parenthesis
  `(hard gate: none yet — gate is trivially green until the toolchain is scaffolded; say so, never skip silently)`,
  becomes `(hard gate: .\.venv\Scripts\python.exe -m pytest)` with the
  command in backticks; rewrap the paragraph to ~76 columns.

- **`.claude/standards/testing.md`**: the runner sentence
  `Runner: <FILL-IN: test/check runner, invoked non-interactively — a single run, never watch mode>.`
  (with the FILL-IN in backticks) and the "Current reality" blockquote
  become:

  ```
  Runner: pytest, one non-interactive run:
  `.\.venv\Scripts\python.exe -m pytest`. Philosophy: every eval becomes
  reproducible and checkable; avoid relying solely on manual trial runs.

  > **Current reality:** pytest is the hard gate (since grader-01b). A
  > change with tests isn't green until they execute and pass via the gate.
  ```

  and `` or under `<FILL-IN: this repo's test directory>` `` becomes
  `` or under `tools/tests/` ``.

- **`TODO.md` § Later**, in the `<FILL-IN>` checklist, the line
  `` - [ ] `.claude/standards/testing.md` — test/check runner; test directory ``
  becomes `- [x] … — test/check runner; test directory (grader-01b)`, the
  path still in backticks.

If an old string has drifted, fix only that sentence and note it in the
follow-up file.

## Calibration

`.\30-grade-trials.ps1 -Case evals\01-playwright-python-basic -Runs 3-12`,
then `-Runs 1-2 -Tools interactive`, then `-Report`. Headed browser
windows open during replays: expected (Eval 01's script launches
`headless=False`; never change it). Expected, all of it:

| Run | Verdict | Tags (exactly; `tried-to-run` may also appear on 10–12) |
|---|---|---|
| 1 | `fail` | `not-fixed` |
| 2, 3, 5, 6 | `fail` | `new-failure` |
| 4, 11 | `pass` | — |
| 10, 12 | `pending-judge` | `retargeted` |
| 7, 8, 9 | `invalid` | `harness-error` |

Plus: controls pass in both invocations; run 10's `.venv` listing raises
no `answer-key`; replays total at most 14: 8 in the first invocation
(4 controls; runs 3, 5, 10 and 12, with 6 sharing 5's and 4 and 11 reusing
the reference control) and 6 in the second (4 controls; runs 1 and 2).
Report which of runs 10–12 got `tried-to-run`.

## Gotchas / bindings

- **Load-test pin:** replays are single replays against playwright.dev,
  strictly one at a time, never in parallel, and only the ones dedupe
  can't avoid. Tests never touch a site or a browser.
- **Windows process trees:** on timeout, kill the whole tree
  (`taskkill /T /F /PID <pid>`); Playwright's browser outlives a killed
  Python otherwise. Replay copies go to `%TEMP%\scriptfix\<hash>\`, never
  inside the repo (the script writes its trace next to itself).
- **Encoding:** run replays as `python -X utf8 script.py` (`-I` would
  ignore `PYTHONUTF8`); read and write every file as UTF-8. Python on
  Windows writes CRLF in text mode: write repo files with `newline="\n"`
  (the repo is LF; check with `git diff --stat`).
- **Failing line:** the last traceback frame whose file is the replayed
  `script.py` (`File "...\script.py", line N`).
- **`ast.unparse` normalizes quotes and spacing:** compare normalized
  strings only, never raw source text.
- **Don't touch** Eval 01's `prompt.md`, `inputs/`, `rubric.md` or its
  reference; corpus files are new files, never edits of the reference.
- **`.pytest_cache/`** goes in `.gitignore`; `fixes/` and `trials.jsonl`
  are committed.
- **No answers in `inputs/`:** everything this plan writes for Eval 01 is
  under `grading/`.
- **Public repo:** no work-internal names or details in code, comments,
  tests or commits.

## Validation

`.\.venv\Scripts\python.exe -m pytest` green (the new hard gate); the
static pre-pass over every changed file (no answer leaks, no placeholder
changes); `requirements.txt` sanity (one new exact pin, pytest, nothing
else); § Calibration's table matches. No manual playtest.

## Follow-ups

- Phase C (cases 02–06, capture, `10-make-case.ps1`) and phase D (trial
  runner) can start; phase E (judge) resolves runs 10 and 12.
- Methods met but not classified (decision default) go to
  `grader-01b.deterministic-grader.follow-up.md`.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/grader-01b.deterministic-grader.md
```
