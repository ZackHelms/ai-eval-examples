# grader-01d — the trial runner (`20-run-trials.ps1`)

**Status:** IMPLEMENTED 2026-11-01 (oversee run, commits `48a9936`..`3f30839`
plus the wrap-up; see `grader-01d.trial-runner.follow-up.md`).
**Requested:** 2026-10-30 (grader-01 phase D, design approved that day);
drafted 2026-10-31 by `/zmh-producer:backlog-plan-gen`.
**Scope:**
- New: `tools/scriptfix/run.py`, `tools/tests/test_run.py`,
  `20-run-trials.ps1`.
- Changed: `tools/scriptfix/__main__.py` (a `run` subcommand),
  `tools/scriptfix/grade.py` (it reads the subject sidecar),
  `tools/tests/test_grade.py`, `tools/tests/test_cli.py`.
- Docs: `.claude/skills/trial-runs.md`, `.claude/skills/scriptfix-grader.md`,
  `CLAUDE.md` (trial-run loop, Playtest SOP), `README.md`.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`). The "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.

## Goal

`.\20-run-trials.ps1 -Case evals\<slug> -Model <id> -Count N` runs N
one-shot headless trials of a case, strictly one at a time:
- each trial runs in a fresh `~\eval-trials\<NN>-run<N>\` holding only
  `prompt.md` and `inputs/`;
- the launcher's three gotchas are built in;
- each run's stream log and a subject sidecar land beside its folder,
  where `30-grade-trials.ps1` already looks;
- the grader records the subject from the sidecar.

`.\20-run-trials.ps1 -SelfTest` checks the launcher itself for about $0.01
before any trial money is spent.

## Context

- The launch command, transcripts and the gotchas behind it, each of which
  cost real runs: `.claude/skills/trial-runs.md` § Launch and § Launcher
  gotchas. That file says it is this script's spec.
- Eval 01's runs 3–12 were launched by hand this way on Claude Code
  2.1.314 (`evals/01-playwright-python-basic/grading/trials.md` § Setup).
  This host now has 2.1.314 at `C:\Users\zmhel\.local\bin\claude.exe`, a
  native exe rather than a `.cmd` shim.
- Where the grader looks for a run (`tools/scriptfix/grade.py`
  `locate_trial`, lines 129–156): `<root>\<NN>-run<N>\inputs\script.py`
  and `<root>\<NN>-run<N>.stream.jsonl`, with `<root>` defaulting to
  `~\eval-trials`.
- Design: `.claude/plans/grader-01.global-rubric-design.md` § Tooling
  layout ("The runner").
- **Out of scope:**
  - **Context bundles.** `--safe-mode` disables CLAUDE.md, skills and
    plugins (`claude --help`), so a context experiment needs a different
    launch. Only `context = none` is supported here, and that's a
    follow-up.
  - The isolated trial environment, the SDK harness, and phases C, E
    and F.

## Implementation guidance (for the overseer)

Tiers under the **balanced** profile (`.claude/skills/task-scoping.md`, 2026-10-31).

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | `run.py` pure parts: run numbers, folder prep, env, allow rules, argv, sidecar + tests | code | sonnet | high | single module, rules spelled out; env and path handling need care |
| 2 | Launch, self-test, `run` CLI + tests with a fake `claude` | code | sonnet | high | process lifecycle on Windows; reuses `replay`'s lessons |
| 3 | The grader reads the sidecar + tests | code | sonnet | high | small, but it changes recorded verdict data; precedence rules given |
| 4 | `20-run-trials.ps1` | script | sonnet | medium | follows `30-grade-trials.ps1`'s pattern; wording is the agent's |
| 5 | The live self-test, once (≈ $0.01) | validation | sonnet | high | a real headless launch; a failure means launcher debugging |
| 6 | Docs | docs | sonnet | medium | pattern named; wording is the agent's |

- **Ordering / dependencies:** 1 → 2 → 3 → 4 → 5 → 6. Parallel-safe: none
  (default sequential).
- **Files owned per task:**
  1. `tools/scriptfix/run.py`, `tools/tests/test_run.py`.
  2. The same two, plus `tools/scriptfix/__main__.py` and
     `tools/tests/test_cli.py`.
  3. `tools/scriptfix/grade.py`, `tools/tests/test_grade.py`.
  4. `20-run-trials.ps1`.
  5. No repo files. If the self-test exposes a launcher bug, the fix goes
     in `tools/scriptfix/run.py`.
  6. `.claude/skills/trial-runs.md`, `.claude/skills/scriptfix-grader.md`,
     `CLAUDE.md` (the trial-run loop paragraph and the Playtest SOP bullet
     only), `README.md`.
- **Validation per task:**
  - Every task: `.\.venv\Scripts\python.exe -m pytest` exits 0. Check
    `$LASTEXITCODE` unpiped and paste the summary line.
  - Task 4: `.\20-run-trials.ps1 -h` prints usage; `--bogus` fails naming
    it; a `-DryRun` on case 01 prints a plan and creates nothing (check
    that `~\eval-trials` has no new folder).
  - Task 5: § Self-test passes.
  - The suite grows by exactly what tasks 1–3 add.
- **Tier audit (required):**
  - Tasks 1–3 fail haiku checklist item 4 (error messages, module
    structure).
  - Task 4 follows a named pattern but has its own help text →
    sonnet-medium.
  - Task 5 is a live run whose failure needs diagnosis → sonnet-high.
  - Task 6 is wording → sonnet-medium.
  - Nothing is cross-package or invariant-bearing enough for opus. The one
    invariant (never overwrite a trial) is a few lines with tests.
- **Decision defaults:**
  - **Never overwrite a trial.** `--runs` naming an existing folder, log or
    sidecar is a usage error (exit 2), and `--count` always starts after
    the highest run found (§ Run numbers).
  - **Stop at the first harness problem**, so a broken launcher doesn't
    burn trials. A harness problem is a non-zero `claude` exit, a timeout,
    or a stream log with no `result` line. Print it and launch nothing
    more.
  - **Precedence, sidecar vs. arguments:**
    - In `grade`, a run's sidecar wins over `--effort/--context/--tools`,
      which stay the defaults for runs without a sidecar (Eval 01's
      runs 1–12).
    - The model always comes from the transcript, as now.
    - A sidecar that doesn't parse, or lacks one of the three string keys,
      makes that run `invalid` (`harness-error`, naming the file).
  - **Supported choices only:** `--tools edit-only`, `--context none`, and
    `--effort default|low|medium|high|xhigh|max` (`default` omits the
    flag). Anything else is rejected by argparse `choices`.
  - **`--model` is required for trials, and passed through verbatim**
    (e.g. `claude-haiku-4-5-20251001`, `claude-haiku-5-5`). The self-test
    defaults to `claude-haiku-5-5`, the cheapest.
  - Names: snake_case; JSON keys exactly as § Sidecar; standard library
    only.
- **Embedded-content QA (required):**
  - Anchors refer to the tree at `2b9eb1b`.
  - `locate_trial` is at `grade.py:129`, `_load` at `grade.py:296`, and
    `grade()`'s `subject={…}` at `grade.py:559–565`, and the `World` test
    helper at `test_grade.py:109`.
  - The env-strip list is `trial-runs.md` gotcha 2 plus three names this
    plan adds (`VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONSTARTUP`) and the
    plugin prefix `ZMH3D_`.
- **Escalation triggers:**
  - `claude` isn't on `PATH`, or isn't logged in for headless use (the
    self-test's result line says so): log under "Blocked — needs you" and
    finish everything else.
  - The self-test still fails after one targeted fix in `run.py`: log it
    with the stream log path. Don't keep spending runs.
  - **Never run a real case trial in this plan.** Trials are the CD's
    playtest (CLAUDE.md § Playtest SOP); only the self-test runs live.
- **Playtest:** after this lands, the CD runs a smoke trial, e.g.
  `.\20-run-trials.ps1 -Case evals\02-docs-journey-a -Model claude-haiku-5-5 -Count 1`
  once phase C has landed (else on Eval 01), then grades it with the
  printed `30-grade-trials.ps1` command. § Validation names what to check.
- **Publish:** none (no publish step in this repo).
- **Commit strategy:** one conventional commit per task. Scopes:
  - `scriptfix` (tasks 1–3, and task 5's fix if any);
  - `scripts` (task 4);
  - `claude` (task 6).

## Steps

1. **Pure parts.** In `run.py`, per § Interfaces, § Run numbers,
   § Environment and § Launch command: `next_runs`, `check_free`,
   `prepare_trial`, `trial_env`, `allow_rule`, `claude_argv` and
   `write_sidecar`. Tests in `test_run.py`, all in `tmp_path`:
   - numbering over folders, logs and `trials.jsonl`;
   - `check_free` rejecting each kind of existing file;
   - `prepare_trial` copying exactly `prompt.md` and `inputs/**`, and
     refusing an existing folder;
   - `trial_env` stripping every listed name case-insensitively, dropping
     `PATH` entries under the repo and the venv, and putting the pwsh
     directory first;
   - `allow_rule` on a Windows path (`C:\Users\a\eval-trials\02-run3\inputs\script.py`
     → `Edit(//c/Users/a/eval-trials/02-run3/inputs/script.py)`) and a
     POSIX one;
   - `claude_argv` with and without `--effort`;
   - the sidecar's JSON.

   Done: pytest green.
2. **Launch, self-test, CLI.** `launch_trial`, `run_trials` and
   `self_test` per § Interfaces and § Self-test, and the `run` subparser
   per § CLI. Tests use a fake `claude`: a Python script in `tmp_path`,
   launched as `claude_cmd=[sys.executable, fake.py]`. It records its
   argv, cwd and env to a JSON file, writes a canned stream-json to
   stdout, and edits the allowed file. Cover:
   - a good trial, with its log, sidecar and summary line;
   - argv and env as seen by the child (no `CLAUDECODE`, and `PATH`
     starting with the pwsh directory);
   - a non-zero exit stopping the batch;
   - a timeout killing the fake, which sleeps;
   - a log with no result line;
   - a self-test pass, and a fail on "The command line is too long";
   - `--dry-run` creating nothing;
   - `run -h` in `test_cli.py`.

   Done: pytest green.
3. **Sidecar in the grader.**
   - `TrialFiles` gains `subject_file`
     (`<root>/<NN>-run<N>.subject.json`).
   - `_load` reads it when present and applies § Decision defaults'
     precedence.
   - `grade()` records each trial's effort, context and tools from it.
   - Tests in `test_grade.py`, using the `World` helper (line 109):
     - a sidecar overrides the arguments;
     - with no sidecar, the arguments are recorded as now;
     - a corrupt sidecar → `invalid`/`harness-error`.

   Done: pytest green, and every existing `test_grade.py` test is
   unchanged.
4. **Entry script.** `20-run-trials.ps1` per § CLI and the Script SOP
   pattern of `30-grade-trials.ps1`:
   - `PositionalBinding = $false`, the help block, unknown arguments
     rejected;
   - the child scope, `$timeoutGiven`-style pass-through of optional
     values;
   - `PYTHONPATH` set and restored;
   - python run unpiped, with its exit code in `$script:exitCode`.

   It always passes `--pwsh (Get-Process -Id $PID).Path`. Done: as in
   § Implementation guidance.
5. **Live self-test.** Run `.\20-run-trials.ps1 -SelfTest` once from the
   oversee session.
   - It prints `SELFTEST=pass`, and the folder and log are under
     `~\eval-trials\selftest-*`. Paste the summary lines.
   - On a fail, read the stream log against `trial-runs.md`'s gotchas,
     make one targeted fix in `run.py` (with a test), commit, and re-run
     once.
   - If `--permission-mode default` is rejected (the 2.1.314 help lists
     `manual`, not `default`, though runs 3–12 used `default`), switch to
     `manual` with a comment saying so.
6. **Docs.**
   - **`trial-runs.md`:**
     - The first paragraph: the script exists now.
     - § Launch: lead with `.\20-run-trials.ps1 -Case … -Model … -Count N`
       and `-SelfTest`, and keep the raw command as "what it runs".
     - § Launcher gotchas stay as the reasons, each noting that the
       script handles it, plus the venv/`PYTHONPATH` strip this plan
       adds.
     - Add one line on the sidecar and the stop-at-first-harness-problem
       rule.
   - **`scriptfix-grader.md` § Run it:** `-Effort/-Context/-Tools` apply
     only to runs without a `<NN>-run<N>.subject.json`.
   - **`CLAUDE.md`:**
     - The trial-run loop paragraph (lines 81–84) names
       `.\20-run-trials.ps1` for the copy-and-run part.
     - The Playtest SOP bullet's "(headless `claude -p` from a trial
       folder outside the repo; `20-run-trials.ps1` once grader-01 phase D
       lands)" becomes "(`.\20-run-trials.ps1`, then
       `.\30-grade-trials.ps1`)".
   - **`README.md` § Setup:** a bullet `.\20-run-trials.ps1 -h`, before
     the `30-grade-trials` bullet.

   Done: `git diff --check` clean, and `git grep -n "once grader-01 phase
   D lands"` finds nothing.

## Interfaces

```python
# run.py
TOOLS = ("edit-only",); CONTEXTS = ("none",)
EFFORTS = ("default", "low", "medium", "high", "xhigh", "max")
DEFAULT_TRIAL_TIMEOUT_S = 1800
SELF_TEST_MODEL = "claude-haiku-5-5"

def next_runs(case_number: str, count: int, trials_root: Path, trials_jsonl: Path) -> list[int]
def check_free(case_number: str, runs: list[int], trials_root: Path) -> None     # ValueError naming the file
def prepare_trial(case_dir: Path, folder: Path) -> Path                          # returns folder/inputs/script.py
def trial_env(environ: Mapping[str, str], *, pwsh_dir: Path, repo_root: Path) -> dict[str, str]
def allow_rule(tool: str, path: Path) -> str
def claude_argv(claude_cmd: list[str], *, prompt: str, model: str, effort: str,
                allowed_file: Path) -> list[str]
def write_sidecar(path: Path, record: dict[str, object]) -> None                # LF JSON

@dataclass(frozen=True)
class TrialRun:
    run: int; folder: Path; log: Path; sidecar: Path
    exit_code: int | None; timed_out: bool; seconds: float

def launch_trial(argv: list[str], *, folder: Path, log: Path, stderr: Path,
                 env: dict[str, str], timeout_s: int) -> tuple[int | None, bool, float]
def run_trials(case_dir: Path, *, model: str, effort: str, runs: list[int] | None,
               count: int | None, trials_root: Path, claude_cmd: list[str],
               pwsh: Path, timeout_s: int, dry_run: bool, out: Out = print) -> int   # exit code
def self_test(*, model: str, trials_root: Path, claude_cmd: list[str], pwsh: Path,
              timeout_s: int, out: Out = print) -> int                                 # 0 pass / 1 fail
```

## Run numbers

- The highest existing run of case `NN` is the max N over:
  - folders `<root>/<NN>-run<N>/`;
  - files `<root>/<NN>-run<N>.stream.jsonl` and
    `<root>/<NN>-run<N>.subject.json`;
  - `run` values in `<case>/grading/trials.jsonl`, if it exists.
- `--count k` gives the next k numbers. Eval 01's next run is 13, since
  its trials go up to 12.
- `--runs <list>` (parsed by `grade.parse_runs`) must pass `check_free`.

## Environment

`trial_env` starts from a copy of the environment, then:
- **Removes** every key, compared case-insensitively, that starts with
  `CLAUDE` or `ZMH3D_`, or is one of: `AI_AGENT`, `NO_COLOR`,
  `PYTHONIOENCODING`, `GIT_ASKPASS`, `GIT_EDITOR`, `GIT_TERMINAL_PROMPT`,
  `GCM_INTERACTIVE`, `COREPACK_ENABLE_AUTO_PIN`,
  `PSExecutionPolicyPreference`, `NoDefaultCurrentDirectoryInExePath`,
  `VIRTUAL_ENV`, `PYTHONPATH`, `PYTHONSTARTUP`. The last three name the
  repo or its venv: the evidence must not, and neither may the
  environment.
- **Rebuilds `PATH`:**
  - drop every entry inside `repo_root` (the repo's `.venv\Scripts`
    included) and the removed `VIRTUAL_ENV`'s `Scripts`/`bin`;
  - prepend `pwsh_dir`, which is `(Get-Process -Id $PID).Path`'s folder
    passed by the wrapper;
  - compare paths case-insensitively on Windows (`os.path.normcase`).
- **Without `--pwsh`,** `shutil.which("pwsh")` is used. A result under
  `\WindowsApps\` is rejected with a message to pass `--pwsh`, because
  that app alias breaks the PowerShell tool ("The command line is too
  long", runs 7–9).

## Launch command

```
<claude> -p <prompt.md text, stripped> --safe-mode --strict-mcp-config --model <model>
  [--effort <effort>]                       # omitted for "default"
  --permission-mode default
  --allowedTools "Edit(<rule path>)" "Write(<rule path>)"
  --output-format stream-json --verbose
```

- **The working directory is the trial folder.**
- **stdin** is `DEVNULL`.
- **stdout** goes to `<root>/<NN>-run<N>.stream.jsonl` and **stderr** to
  `<root>/<NN>-run<N>.stderr.txt`. Both are files opened in binary mode,
  never pipes; the reason is in `trial-runs.md` § Grading replays,
  "Windows processes".
- **The prompt goes as an argv element** (list form, never through a
  shell), as in runs 3–12. `claude.exe` is native, so `CreateProcess`
  quoting is exact.
- **Rule paths** are `//` plus the absolute path with forward slashes and
  a lowercase drive letter (`//c/Users/...`). They are absolute so a
  `cd inputs` can't break them (gotcha 1).
- **On timeout,** kill the tree with `scriptfix.replay._kill_tree`
  (import it; don't copy it).
- **After each trial,** print one line:
  `RUN=<n> EXIT=<code> TIMED_OUT=<bool> COST_USD=<x> IS_ERROR=<bool> DENIALS=<k> LOG=<path>`,
  using `transcript.read_transcript`.
- **After the batch,** print
  `NEXT=.\30-grade-trials.ps1 -Case <case> -Runs <first>-<last>`.

## Sidecar

`<root>/<NN>-run<N>.subject.json`, written after the trial ends:

```json
{
  "run": 13,
  "case": "01-playwright-python-basic",
  "model": "claude-haiku-5-5",
  "effort": "default",
  "context": "none",
  "tools": "edit-only",
  "runner": "0.1.0",
  "started": "2026-11-01T10:00:00",
  "seconds": 74.2,
  "exit_code": 0,
  "timed_out": false
}
```

`runner` is `scriptfix.__version__`. The file is written with
`json.dumps(record, indent=2) + "\n"` and `newline="\n"`.

## Self-test

This is launcher gotcha 4, automated.

- **The folder** is `<root>/selftest-<YYYYMMDD-HHMMSS>/`, containing only
  `inputs/dummy.txt` = `before\n`. Allow rules cover that file only. The
  model defaults to `SELF_TEST_MODEL`.
- **The prompt,** verbatim: `This is a harness check. Do exactly these three
  things and nothing else. 1. With the PowerShell tool, run: Get-Location
  2. With the Bash tool, run: cd inputs && ls 3. With the Edit tool,
  change the word before to after in inputs/dummy.txt. Then reply with
  the three results.`
- **It passes** when all of these hold:
  1. the log has a `result` line with `is_error` false;
  2. a `PowerShell` tool call has a non-error result;
  3. a `Bash` tool call has a non-error result;
  4. no tool result contains `The command line is too long`;
  5. no `Edit`/`Write` denial;
  6. `dummy.txt` reads `after` once stripped.
- **Output:** `SELFTEST=pass`, or `SELFTEST=fail` with one
  `REASON=<check>: <detail>` line per failed check, then the folder and log
  paths. Exit 0 or 1. The folder is kept for inspection.

## CLI

- `python -m scriptfix run --case <dir> --model <id> (--count N | --runs <list>) [--effort default] [--context none] [--tools edit-only] [--trials-root DIR] [--claude PATH] [--pwsh PATH] [--timeout 1800] [--dry-run]`
- `python -m scriptfix run --self-test [--model claude-haiku-5-5] [--trials-root DIR] [--claude PATH] [--pwsh PATH] [--timeout 600]`

Notes:
- `--count` and `--runs` are mutually exclusive, and `--case`/`--model`
  are required unless `--self-test` is given.
- `--claude` defaults to `shutil.which("claude")`; missing is a usage
  error. `--trials-root` defaults to `~/eval-trials`.
- **Exit codes:** 0 ok; 1 a harness problem or a failed self-test; 2 a
  usage error.
- **`--dry-run`** prints the run numbers, folders, argv (the prompt shown
  as `<prompt.md: N chars>`), and the names of the env keys it would
  strip. It creates nothing and launches nothing.

`20-run-trials.ps1`:
- Parameters: `-Case`, `-Model`, `-Count`, `-Runs`, `-Effort`,
  `-TrialsRoot`, `-Timeout`, `-DryRun`, `-SelfTest`, `-h`.
- It maps them one-to-one, passing optional values only when given, plus
  `--pwsh (Get-Process -Id $PID).Path`.
- Examples to include:
  - `-SelfTest`;
  - `-Case evals\01-playwright-python-basic -Model claude-haiku-5-5 -Count 1 -DryRun`;
  - a 10-trial screen.

## Gotchas / bindings

- **The three launcher gotchas** (`trial-runs.md`) are the reason for this
  plan:
  - absolute allow rules;
  - stripping the parent session's variables;
  - the real `pwsh.exe` first on `PATH`.

  Stripping variables does **not** fix the "command line is too long"
  failure; only the `PATH` change does.
- **This run executes inside a Claude Code session.** Every launch,
  including the self-test, must go through `trial_env`; never call
  `claude` with the inherited environment.
- **No trial ever runs the script or touches a site:** the tool profile is
  edit-only, and headless mode denies anything else. The load-test pin
  isn't engaged, but trials still run one at a time.
- **Money:** each trial costs about $0.01–$0.08 (Haiku 5.5 / 4.5 on
  Eval 01). The only live call in this plan is the self-test.
- **Windows processes:**
  - Capture output through files, not pipes.
  - Kill a timed-out tree with `taskkill /T /F` (via `_kill_tree`).
  - Never probe a process with `os.kill(pid, 0)`: on Windows it
    terminates the process.
- **Encoding:** the stream log is bytes straight from `claude`; never
  decode and re-encode it. Sidecars and any text the tooling writes are
  UTF-8 with LF.
- **pwsh:**
  - Inside `& { … }`, `$PSBoundParameters` is the block's own, so read it
    at script scope.
  - Don't pipe python into `Out-Host`.
  - `(Get-Process -Id $PID).Path` is the running `pwsh.exe`.
- **Trial folders live outside the repo** (`~\eval-trials`), and their
  names carry only the number (`<NN>-run<N>`); never the slug.
- **Git:** stage named files only (never `git add -A`). In the oversee
  worktree, run git as plain separate commands (no compound commands that
  name git), and use `git -C <worktree>` in every implementer prompt.
- **Public repo:** no product names or work-internal names in code,
  tests, docs or commit messages.

## Validation

- The project validation procedure: the static pre-pass on changed files,
  then `.\.venv\Scripts\python.exe -m pytest` green.
- `requirements.txt` is unchanged.
- The self-test passed once, live (task 5).
- **The CD's playtest after landing:** one smoke trial (see Playtest
  above). Check that:
  - the trial folder holds only `prompt.md` and `inputs/`;
  - the stream log's `init` line shows the requested model;
  - `permission_denials` lists only what the model tried beyond editing
    the script;
  - the printed `NEXT=` command grades it, recording the sidecar's
    subject.

## Follow-ups

- **Context bundles:** a launch that gives the subject context files
  despite `--safe-mode` (e.g. `--append-system-prompt-file`, or dropping
  safe mode with explicit `--setting-sources`), recording the bundle's
  hash in the sidecar. Do it when the first context experiment is planned.
- Phase F (the pilot) needs this, phase C's cases and phase E's judge.

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/grader-01d.trial-runner.md
```
