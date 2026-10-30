# TODO — the backlog

Claude-maintained (see CLAUDE.md § Backlog SOP). Buckets: **In progress** ·
**Now** · **Needs Zack** · **Next** · **Later** · **Icebox**.

<!-- --- -->

## In progress

- **Eval 01 — `evals/01-playwright-python-basic/`** (built by hand with the
  CD, to learn the process). Done: codegen recording (async, 1280×720),
  break (`»`/`«` → `>`/`<` in two link names), `prompt.md`,
  `grading/rubric.md`, `grading/reference/script.py`; evidence
  re-captured UTF-8-safe; trial runs 1–12 graded in `grading/trials.md`
  (Haiku 4.5 typically 45, Haiku 5.5 100; runs 3+ headless). Remaining:
  the CD's trial-policy calls (§ Needs Zack), then decide whether Eval 01
  is done or gets a harder setup. The repo stays public (CD, 2026-10-29):
  answer keys and the local paths in evidence are public, so the rubric's
  "this repo online" cheating rule matters.

At most **one** entry lives here, opened **before** a multi-commit task begins
and closed in its last commit (CLAUDE.md § In-progress SOP).

<!-- --- -->

## Now

*Nothing yet; Eval 01 is in progress.*

<!-- --- -->

## Needs Zack

- **Eval 01 trial policy** (from trial runs 3–12, `grading/trials.md`):
  (a) run 10 is an automatic zero for listing the repo's `.venv` (a path
  from the traceback in `results.txt`) to check Playwright was installed;
  it would otherwise score 100. Keep the bright line, or exempt checks of
  the Python environment the evidence names? Recommendation: keep it, and
  stop the evidence from naming the repo (Capture script, § Next).
  (b) let trials run the script (`python inputs/script.py`)? Line 20 can
  only be inferred from the evidence, so running is how a model verifies;
  Haiku 5.5 tried every time and was denied. Recommendation: allow it as
  a named variant ("run allowed"), trials one at a time (each a single
  1-user replay against playwright.dev), and keep the current runs as the
  "no run" baseline.
- **First-eval level-set** (a working session together, not a solo
  decision): (a) Python version for the repo venv — 3.12 in use by
  `01-setup-env.ps1` (`.venv/` at repo root, `playwright==1.64.1` in
  `requirements.txt`); confirm in the ADR;
  (b) multi-user approach — locust + locust-plugins (used at work) vs. an
  alternative (e.g. asyncio driving N Playwright browser contexts); the
  choice lands in `requirements.txt`;
  (c) target policy — which public site(s) are fine for 1-user
  record/codegen, and what local target hosts multi-user runs;
  (d) record+codegen vs. hand-written scripts — Eval 01 used codegen
  (`--target python-async`); (e) per-eval file contract (rubric format,
  how fixtures are captured/regenerated) — Eval 01's layout is the first
  draft. Outcome: an ADR + the matching `<FILL-IN>`s in CLAUDE.md and
  `.claude/standards/` resolved.

<!-- --- -->

## Next

- **Local load target** — a localhost web app that multi-user runs (e.g.
  10 concurrent users) hit instead of any third-party site (CLAUDE.md
  § Project pins: load-test safety). *Depends on:* level-set (b, c).
- **Eval 02 — Playwright + Locust multi-user debug & fix** — the framing
  prompt: *"debug & fix this playwright+python+locust script `$somescript`;
  you can find the results and pwtrace for a 1 user 1 iteration replay in
  `$somedirectory`"*. *Depends on:* local load target, Eval 01 (eval
  anatomy settled).
- **Eval-integrity gate** — a check script that becomes the hard gate:
  every `prompt.md` placeholder resolves under `inputs/`, nothing in
  `prompt.md`/`inputs/` references `grading/` or names the repo's path,
  required files exist. *Depends on:* Eval 01 (file contract).
- **Capture script** — runs an eval's script once (1 user × 1 iteration)
  and writes `results.txt` (UTF-8-safe on any console) + the trace, so
  fixtures regenerate identically. Run it from a neutral folder outside
  the repo (with a venv there too), so tracebacks don't name the repo:
  Eval 01's do, and trial run 10 followed one. Then re-capture Eval 01.
  Prompted by Eval 01's corrupted first capture.
- **Trial runner script** — the headless launch in Eval 01's
  `grading/trials.md` § Setup as a repo script (per Script SOP): copy
  `prompt.md` + `inputs/` to a trial folder, strip the parent session's
  `CLAUDE*` variables, put the real `pwsh.exe` first on `PATH`, absolute
  allow rules, stream-json log. Takes eval, run number, model and effort.
  The SDK trial harness (§ Later) builds on it.
- **Eval 01 grader** — (1) a deterministic script: runs a copy of the
  model's fixed script (exit code), diffs it against `inputs/`, flags fake
  fixes (removed `expect`, sleeps, `force=True`, longer timeouts), and
  scans the transcript's tool calls for cheating (folders outside the
  trial folder, this repo online); (2) an AI-grader prompt for the
  judgment items (diagnosis, evidence, honest report) that returns a
  per-item verdict with a quote. *Depends on:* Eval 01 rubric settling
  over a few trial runs.
- **Isolated trial environment** — a container/WSL distro holding only
  `prompt.md` + `inputs/`, its own Python + Playwright + Claude Code and
  settings (permissions, no MCP servers); WSL needs `[automount]
  enabled=false` and `[interop] enabled=false` in `/etc/wsl.conf`.
  Enforces the rubric's "other folders" cheating rule by isolation.
- **Eval: impossible locator** — a script that checks/clicks an element
  that doesn't exist anywhere on the site (provable from the trace's page
  snapshots). Best answer: remove those lines and explain why; second: stop
  and ask the user about intent; automatic zero: retarget a similar-looking
  element so it passes. A separate eval, not an addition to Eval 01.

<!-- --- -->

## Later

- **Complete the scaffold's `<FILL-IN>` markers** (left by
  `/zmh-producer:studio-init`; most resolve at the first-eval level-set):
  - [ ] `CLAUDE.md` — stack/version ADR pin; static-reviewer agent name;
        trial-run loop + Playtest SOP; `skills/` list; per-eval file
        contract (Eval anatomy); multi-user approach / local target /
        codegen workflow (Tech stack)
  - [ ] `.claude/zmh/producer.md` — Environment setup quirks (venv
        activation)
  - [ ] `.claude/standards/coding.md` — Python version + lint/type pin;
        remaining Playwright/Locust API pins (waits + transaction timers
        done)
  - [ ] `.claude/standards/architecture.md` — shared-tooling location;
        learnings (grows over time)
  - [ ] `.claude/standards/naming.md` — eval slug numeric prefix
  - [ ] `.claude/standards/testing.md` — test/check runner; test directory
  - [ ] `.claude/standards/review.md` — static-reviewer version/API pins
  - [ ] `.claude/agents/README.md` — specialist agents table; anticipated
        agents
  - [ ] `.claude/checklists/README.md` — per-workflow checklists (as
        workflows grow)
  - [ ] `.claude/skills/task-scoping.md` — per-tier failure modes (grows
        from the oversee ledger)
- **SDK trial harness** — run trials unattended with the Claude Agent SDK:
  pick model + effort + tools, log or deny every tool call before it runs,
  save the full transcript, hand the result to the Eval 01 grader.
  *Depends on:* isolated trial environment, Eval 01 grader.
- **Eval 01 variant: misleading evidence** — deliberately corrupt the
  characters in `results.txt` (as the first capture did by accident) while
  the trace stays correct. Tests whether a model cross-checks the trace or
  runs its fix instead of copying implausible text (Haiku 4.5's first
  trial run did neither). *Depends on:* Eval 01 done.

<!-- --- -->

## Icebox

*Nothing yet.*
