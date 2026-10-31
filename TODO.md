# TODO — the backlog

Claude-maintained (see CLAUDE.md § Backlog SOP). Buckets: **In progress** ·
**Now** · **Needs Zack** · **Next** · **Later** · **Icebox**.

<!-- --- -->

## In progress

*Nothing in progress.*

At most **one** entry lives here, opened **before** a multi-commit task begins
and closed in its last commit (CLAUDE.md § In-progress SOP).

<!-- --- -->

## Now

- **Global rubric + grader v0** (grader-01; the CD's work-scale idea):
  design approved 2026-10-30, `.claude/plans/grader-01.global-rubric-design.md`.
  One plan per phase: A decide (done: ADR-0001, `rubrics/script-fix/`) →
  B deterministic grader + pytest gate + Eval 01 calibration → C cases
  02–06 (neutral-folder capture, `10-make-case.ps1`; case 06 replaces the
  impossible-locator eval) and D trial runner (`20-run-trials.ps1`) →
  E LLM judge → F pilot. Absorbs the former § Next items Eval 01 grader,
  Capture script, Trial runner script and Eval: impossible locator.

<!-- --- -->

## Needs Zack

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

- **Local test site** (the CD's request, 2026-10-30; absorbs "Local load
  target"): a locally hosted web app (on the PC or in a container), more
  complex than playwright.dev, with a variety of elements in different
  parts of the site for Playwright scripts to exercise. Serves varied
  generated cases, timing cases with controllable delays, grader-01 full
  runs at suite scale, and the multi-user runs that may never hit a
  third-party site (CLAUDE.md § Project pins: load-test safety).
  *Depends on:* level-set (b, c) for the multi-user side; the single-user
  side can start sooner.
- **Eval 02 — Playwright + Locust multi-user debug & fix** — the framing
  prompt: *"debug & fix this playwright+python+locust script `$somescript`;
  you can find the results and pwtrace for a 1 user 1 iteration replay in
  `$somedirectory`"*. *Depends on:* local test site, Eval 01 (eval
  anatomy settled).
- **Eval-integrity gate** — a check script that becomes the hard gate:
  every `prompt.md` placeholder resolves under `inputs/`, nothing in
  `prompt.md`/`inputs/` references `grading/` or names the repo's path,
  required files exist, each `case.toml` is valid and each global-rubric
  case's `prompt.md` matches `rubrics/script-fix/prompt.md`. *Depends on:*
  Eval 01 (file contract), grader-01 phase C (case template).
- **Isolated trial environment** — a container/WSL distro holding only
  `prompt.md` + `inputs/`, its own Python + Playwright + Claude Code and
  settings (permissions, no MCP servers); WSL needs `[automount]
  enabled=false` and `[interop] enabled=false` in `/etc/wsl.conf`.
  Makes the answer-key cheating rule moot: there is no answer key to find.

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
  - [ ] `.claude/standards/architecture.md` — learnings (grows over
        time); shared-tooling location done (ADR-0001)
  - [x] `.claude/standards/naming.md` — eval slug numeric prefix
        (ADR-0001)
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
  save the full transcript, hand the result to the grader-01 grader.
  *Depends on:* isolated trial environment, grader-01 phase E.
- **Eval 01 variant: misleading evidence** — deliberately corrupt the
  characters in `results.txt` (as the first capture did by accident) while
  the trace stays correct. Tests whether a model cross-checks the trace or
  runs its fix instead of copying implausible text (Haiku 4.5's first
  trial run did neither). *Depends on:* Eval 01 done.

<!-- --- -->

## Icebox

*Nothing yet.*
