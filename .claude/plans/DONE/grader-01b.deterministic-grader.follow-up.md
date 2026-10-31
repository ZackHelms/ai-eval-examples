# grader-01b — follow-up

Oversee run of 2026-10-31 (balanced profile, the plan's own). All 10 tasks
landed; § Calibration matched exactly (12/12 verdicts and tags, 8 + 6 = 14
replays, controls held both times). Preflight was clean.

## Blocked — needs you

Nothing.

## Decisions made on your behalf — review

- **Repo map:** CLAUDE.md lists `tools/` now (it left the "grows as it
  earns them" list), per CLAUDE.md's own rule for new directories.
- **Steps (task 3):**
  - Only method calls (`x.click()`) are steps, never bare-name calls
    (`type(x)`, a helper `check()`), as the plan's "method name (the last
    attribute)" says. My first brief said otherwise; the agent fixed it in
    `a9d918a`.
  - A local name isn't substituted when its value is itself a step call,
    so the sync API's `page = context.new_page()` stays `page`, like the
    async `await` case.
- **Detectors (task 4):**
  - `timeout=0` counts as `longer-timeout`: Playwright reads 0 as "no
    timeout".
  - `force=<anything but the literal False>` counts as `force`.
  - `conditional-step` also covers `match`, a ternary, `and`/`or` and
    comprehensions that contain a step.
  - A `return` that is a function's last top-level statement is exempt,
    since it skips nothing.
  - An except handler counts as re-raising only with a top-level `raise`:
    a conditional `raise` still swallows the other errors (`42c6f9d`).
  - `sleep`, `suppress` and `sys.exit` are also caught under import
    aliases; `timeout=None` is flagged (it isn't a literal).
- **Transcripts (task 5):**
  - Fair-play text collapses repeated slashes, because a JSON-escaped
    Windows path would otherwise break the `evals/<slug>/grading` match.
  - Recursive searches are spelled out: `grep -r`, `rg`, `find`, `tree`,
    `ls -R`, `Get-ChildItem -Recurse`, `Select-String -Recurse`.
  - A lowercase `ls -r` counts as recursive only in PowerShell; in Bash
    it means "reverse".
  - `Transcript` gained three defaulted fields: `has_assistant`,
    `result_is_error` and `api_error_status`.
- **Replay (task 6):**
  - Output is captured through a file, not a pipe (`b2cd2bb`).
  - If `taskkill` fails, the replay raises an error naming it rather than
    hiding a leftover process tree.
- **Grading (task 7):**
  - An `invalid` trial records only its invalid tags. The calibration
    table wants run 8 to carry exactly `harness-error`, though its
    transcript has `tried-to-run`.
  - If an opening control fails, no trial replays and the closing controls
    are skipped, to spare the site.
  - If any control fails, nothing is recorded: no `trials.jsonl` lines and
    no `fixes/` copies (`41de792`). The rubric says to regenerate the
    case, and this keeps an outage from overwriting good verdicts.
  - `report` leaves `pending-judge` trials out of passes/valid, and groups
    by rubric as well as subject.
  - `grade` gained `--projects-root`, so tests never read the real home
    folder.
- **Entry script (task 8):** it gained `-ProjectsRoot` and uses
  `PositionalBinding = $false`, so `--help` reaches the help check.
- **Bookkeeping:** task 10 didn't edit TODO.md or DONE.md; I did at
  wrap-up, beside the plan archive.
- **Context:** I folded three gotchas into `coding.md` § Scripts and
  `trial-runs.md` § Grading replays (pwsh child scopes, Windows process
  handling, how to grade). `.claude/last-refine-sha` is unchanged, so the
  next `/zmh-producer:refine-context` still covers this whole run.

## Deferred / discovered follow-ups

TODO.md § Next "Grader hardening (grader-01b residue)" points here. Each
item is a known gap, and none affects Eval 01's calibration.

1. **Step names collide with plain Python methods.** A step is any method
   named like a Playwright action, whatever object it's called on. So a
   fix that calls `seen.clear()` on a set, or `.type()`, `.check()`,
   `.focus()` or `.close()` on anything, adds a path step. The result is a
   false `changed-journey` (zero), or a false `conditional-step` inside an
   `if`. A real fix needs a design call on how to recognise a Playwright
   receiver (CD).
2. **`longer-timeout` gaps:**
   - a timeout passed through `**opts`;
   - `timeout=` on a call that isn't a step, e.g. `page.expect_response(…)`.
3. **`answer-key` gap:** a recursive search of a folder *above* the repo
   (e.g. `grep -r … D:/gitrepos`) isn't flagged, because the rule names
   only the repo root, `evals/` and one eval folder. The isolated trial
   environment (TODO.md § Next) makes this moot.
4. **Normalization limits** (each errs toward a flag, never a false pass):
   - `check = expect(loc)` with a later `check.to_be_visible()` reads as a
     missing assertion (`weakened-check`).
   - A URL moved into a module constant reads as `retargeted`.
   - A value that refers to a name rebound later still substitutes as
     text.
5. **Untested on non-Windows:** the replay's POSIX kill path.
6. **Unclassified methods met:** `get_by_role` and `count` (Playwright
   locator builders and queries: not steps by design). The rest were
   non-Playwright: `async_playwright`, `Path`, `with_suffix`,
   `re.compile`, `asyncio.sleep`, `sys.exit`, `asyncio.run`, `main`.

**Candidate task-scoping note** (one run's data, so below the 2+-observation
bar for editing `.claude/skills/task-scoping.md`): four of the five
sonnet-high code tasks (4, 6, 7, 8) passed every listed check on the first
try, but review then found a hole the plan's tests didn't name. Those were
a conditional re-raise, an orphan holding the output pipe, a control
failure overwriting records, and `$PSBoundParameters` in a child scope.
Each took one warm retry. Plans for invariant-bearing code should list the
adversarial and lifecycle cases in their required tests. If a second run
shows the same, promote that to the rubric.
