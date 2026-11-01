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
  B deterministic grader + pytest gate + Eval 01 calibration (done
  2026-10-31: `tools/scriptfix/`, `30-grade-trials.ps1`,
  `.claude/plans/DONE/grader-01b.deterministic-grader.md`) → C cases
  02–06 (done 2026-11-01: `10-make-case.ps1`, `evals/02-docs-journey-a`
  to `evals/06-docs-journey-e`, the eval-integrity gate and the
  `eval-static-reviewer` agent, `.claude/plans/DONE/grader-01c.cases.md`)
  → D trial runner (done 2026-11-01: `20-run-trials.ps1`, the subject
  sidecar, `-SelfTest`, `.claude/plans/DONE/grader-01d.trial-runner.md`)
  → grader hardening (done 2026-11-01: the red-team agent, one shared
  call classification, the tool allowlist,
  `.claude/plans/DONE/grader-01bb.hardening.md`) → **next:** E LLM judge →
  F pilot. Absorbs the former § Next items Eval 01 grader, Capture script,
  Trial runner script and Eval: impossible locator.
- **grader-01 phase E: LLM judge.** Judges the `judge`-severity tags
  (`retargeted`, `new-wait`, `changed-setup`, `broad-pattern`) and the
  escalate cases' check 1, and resolves Eval 01's `pending-judge` runs 10
  and 12. The calibration set is 29 items: the corpora's 24 judge
  questions, plus 5 escalation responses the plan adds to case 06. At 5
  samples each, that's 145 calls per calibration run, capped at $0.10 a
  call and $6 a run.
  - *Decided 2026-11-01 (the CD), on when a new wait or a setup change is
    a cheat:* "“Ok unless it hides the failure” (the most lenient
    approach, i would like to provide the list of things to consider
    cheats (i.e. “doesnt meet my standards”) as i find them when
    reviewing results."
    - So the phase E plan adds a CD-maintained list of cheats that the
      judge's prompt includes. It starts empty, and editing it changes the judge
      version, so cached verdicts are re-asked.
  - *Decided 2026-11-01:* the overseer runs the 5-out-of-5 calibration in
    the oversee run: about 135 Sonnet 5.5 calls, roughly $2–5, capped per
    call. It may revise the judge prompt once, and stops with a report if
    items still miss.
  - *Decided 2026-11-01:* the plan sets each judge item's right answer,
    with a one-line reason from the case's evidence. The CD reviews the
    list after the run, and any answer the CD flips becomes a new
    calibration item.

  *Depends on:* phase C and the grader hardening (both done; the hardening
  kept Eval 01's runs 10 and 12 `pending-judge`).

  **Plan ready (2026-11-01)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01e.llm-judge.md`

<!-- --- -->

## Needs Zack

- **Test-site element inventory: hands-on pass** (the CD's request,
  2026-10-31): the first pass is `.claude/notes/test-site-element-inventory.md`,
  generic by rule (CLAUDE.md § Project pins: generic content only). The
  CD's pass on real apps marks which of its element patterns break scripts
  in practice, and adds any missing ones (pattern names only). Feeds the
  local test site.
- **First-eval level-set** (a working session together, not a solo
  decision): (a) Python version for the repo venv — 3.12 in use by
  `01-setup-env.ps1` (`.venv/` at repo root, `playwright==1.64.1` in
  `requirements.txt`); confirm in the ADR;
  (b) multi-user approach — *Decided 2026-10-31 (the CD): "We can remove
  locust all together; python+playwright is sufficient for these evals, i
  need to do actual experiments with these with single user first before
  i start thinking about issues that only happen under a multiuser
  load."* Closed: no multi-user runner for now (CLAUDE.md § Project pins);
  (c) target policy — which public site(s) are fine for 1-user
  record/codegen, and the local test site for single-user runs (§ Next);
  (d) record+codegen vs. hand-written scripts — Eval 01 used codegen
  (`--target python-async`); (e) per-eval file contract — settled for
  script-fix cases by ADR-0001 (capture landed with grader-01 phase C:
  `10-make-case.ps1`, `grading/capture.toml`). Outcome: an ADR + the
  matching `<FILL-IN>`s in CLAUDE.md and `.claude/standards/` resolved.
- **Playtest: a smoke trial with the new runner** (grader-01d, 2026-11-01).
  Run
  `.\20-run-trials.ps1 -Case evals\02-docs-journey-a -Model claude-haiku-5-5 -Count 1`
  (about $0.01), then the `NEXT=` command it prints. Check that:
  - the trial folder holds only `prompt.md` and `inputs\`;
  - the stream log's `init` line shows the requested model;
  - `permission_denials` lists only what the model tried beyond editing
    the script;
  - the grade records the sidecar's subject;
  - the stream log's `init` line lists only the seven allowlisted tools
    (Read, Glob, Grep, Edit, Write, Bash, PowerShell; grader-01bb).

  The launcher's self-test already passed live, before and after the
  allowlist (`.claude/plans/DONE/grader-01d.trial-runner.follow-up.md`
  item 9, `.claude/plans/DONE/grader-01bb.hardening.follow-up.md`
  decision 17).
- **Rubric questions from the grader red-team** (grader-01bb, 2026-11-01).
  Three fake-fix shapes that rubric-v0 doesn't settle; the variants are
  described in `.claude/plans/DONE/grader-01bb.hardening.follow-up.md`
  § Blocked:
  - is `launch(slow_mo=…)` also `sleep` (zero), or only `changed-setup`
    (judge, as today)?
  - is an action's `delay=…` a fixed `sleep` (zero), or allowed?
  - a `page.evaluate` that rewrites the page so the broken locator matches:
    `retargeted` (judge), `changed-journey` (zero), or a new tag?

  Each answer becomes a detector rule in the next hardening round (§ Next).

<!-- --- -->

## Next

- **Grader hardening, round 2** (grader-01bb's residue,
  `.claude/plans/DONE/grader-01bb.hardening.follow-up.md` § Deferred).
  - 7 red-team misses still slip past the static checks:
    - swapped clicks read as two judge `retargeted`, not
      `changed-journey`;
    - helpers aren't followed at call sites (an uncalled def, a helper
      called under `if`);
    - JS run through `page.evaluate` is opaque (a sleep, a navigation);
    - a monkeypatched Playwright method;
    - `delay=`.
  - The small residue:
    - `getattr` in three more collectors;
    - a misleading test name;
    - marker arguments aren't searched;
    - promote the static calibration (fake `replay_fn`) to a tested
      command.

  *Depends on:* the red-team rubric questions (§ Needs Zack) for `delay=`,
  `slow_mo` and page rewrites. The helper design needs a short design pass
  first. Not urgent: phase E comes first, and the pilot's real trials will
  show which shapes models actually produce.
- **Local test site** (the CD's request, 2026-10-30; absorbs "Local load
  target"): a locally hosted web app (on the PC or in a container), more
  complex than playwright.dev, with a variety of elements in different
  parts of the site for Playwright scripts to exercise
  (`.claude/notes/test-site-element-inventory.md`): a release switch per
  component for drift cases, fixed seeded delays for timing cases. Serves varied
  generated cases, timing cases with controllable delays, grader-01 full
  runs at suite scale. Single-user only (the CD, 2026-10-31: no
  multi-user runs for now). *Depends on:* the inventory hands-on pass
  (§ Needs Zack); design-heavy, so it needs a design pass with the CD
  before a plan.
- **Isolated trial environment** — a container/WSL distro holding only
  `prompt.md` + `inputs/`, its own Python + Playwright + Claude Code and
  settings (permissions, no MCP servers); WSL needs `[automount]
  enabled=false` and `[interop] enabled=false` in `/etc/wsl.conf`.
  Makes the answer-key cheating rule moot: there is no answer key to find.

<!-- --- -->

## Later

- **Complete the scaffold's `<FILL-IN>` markers** (left by
  `/zmh-producer:studio-init`; most resolve at the first-eval level-set):
  - [ ] `CLAUDE.md` — stack/version ADR pin; codegen workflow (Tech
        stack). Done: trial-run loop + Playtest SOP, `skills/` list, file
        contract for script-fix cases (ADR-0001), multi-user approach
        (none for now, 2026-10-31), static-reviewer agent name
        (`eval-static-reviewer`, grader-01c)
  - [x] `.claude/zmh/producer.md` — Environment setup quirks (worktree
        venv bootstrap; refine pass after grader-01b)
  - [ ] `.claude/standards/coding.md` — Python version + lint/type pin;
        remaining Playwright API pins (waits + transaction timers done)
  - [x] `.claude/standards/architecture.md` — shared-tooling location
        (ADR-0001); learnings seeded (they keep growing)
  - [x] `.claude/standards/naming.md` — eval slug numeric prefix
        (ADR-0001)
  - [x] `.claude/standards/testing.md` — test/check runner; test directory (grader-01b)
  - [ ] `.claude/standards/review.md` — static-reviewer version/API pins
  - [ ] `.claude/agents/README.md` — anticipated agents (the specialist
        table is done: `eval-static-reviewer`, grader-01c)
  - [ ] `.claude/checklists/README.md` — per-workflow checklists (as
        workflows grow)
  - [x] `.claude/skills/task-scoping.md` — per-tier failure modes (seeded
        2026-10-31, privnames-01; keeps growing from the oversee ledger)
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

- **Eval: Playwright + Locust multi-user debug & fix** — iced 2026-10-31
  by the CD: "We can remove locust all together; python+playwright is
  sufficient for these evals, i need to do actual experiments with these
  with single user first before i start thinking about issues that only
  happen under a multiuser load." Revisit after single-user experiments;
  any multi-user run still targets localhost only (CLAUDE.md § Project
  pins).
