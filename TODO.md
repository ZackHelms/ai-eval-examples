# TODO — the backlog

Claude-maintained (see CLAUDE.md § Backlog SOP). Buckets: **In progress** ·
**Now** · **Needs Zack** · **Next** · **Later** · **Icebox**.

<!-- --- -->

## In progress

- **privnames-01: private-names check script** — oversee run of
  `.claude/plans/privnames-01.check-script.md`, started 2026-10-31 by
  `/zmh-producer:oversee-implementation .claude/plans/privnames-01.check-script.md`
  on branch `worktree-oversee+privnames-01`. No commits landed yet.

At most **one** entry lives here, opened **before** a multi-commit task begins
and closed in its last commit (CLAUDE.md § In-progress SOP).

<!-- --- -->

## Now

- **Global rubric + grader v0** (grader-01; the CD's work-scale idea):
  design approved 2026-10-30, `.claude/plans/grader-01.global-rubric-design.md`.
  One plan per phase: A decide (done: ADR-0001, `rubrics/script-fix/`) →
  B deterministic grader + pytest gate + Eval 01 calibration (done
  2026-10-31: `tools/scriptfix/`, `30-grade-trials.ps1`,
  `.claude/plans/DONE/grader-01b.deterministic-grader.md`) → **next:** C
  cases 02–06 and D trial runner, both plan-ready (the two entries below;
  independent of each other) → E LLM judge (resolves Eval 01's
  `pending-judge` runs 10 and 12; plan it once C lands, since it needs
  the cases' judge items) → F pilot. Absorbs the former § Next items Eval
  01 grader, Capture script, Trial runner script and Eval: impossible
  locator.
- **grader-01 phase C: cases 02–06.** Neutral-folder capture,
  `10-make-case.ps1`, five recipe-built cases with labeled corpora (case 06
  replaces the impossible-locator eval and is the first escalate case),
  and the escalate journey rule. Bundled into it:
  - the **eval static reviewer** (from § Needs Zack, AGENT-OPP).
    *Decided 2026-10-31 (the CD): "Approve, in phase C".* Task 1 writes
    `.claude/agents/eval-static-reviewer.md`, so the new cases get
    reviewed in the same run;
  - the **eval-integrity gate** (from § Next): pytest checks over every
    eval.

  *Depends on:* phase B (done).

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01c.cases.md`
- **grader-01 phase D: trial runner.** `20-run-trials.ps1` runs N
  headless one-shot trials of a case, one at a time, with the launcher
  gotchas built in. It writes a subject sidecar that the grader reads, and
  `-SelfTest` checks the launcher for about $0.01. Context bundles are
  deferred: `--safe-mode` disables CLAUDE.md. *Depends on:* phase B
  (done); independent of C.

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01d.trial-runner.md`

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
  script-fix cases by ADR-0001 (capture lands with grader-01 phase C). Outcome: an ADR + the matching `<FILL-IN>`s in CLAUDE.md and
  `.claude/standards/` resolved.

<!-- --- -->

## Next

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
- **Grader hardening + red-team agent** (grader-01b residue,
  `.claude/plans/DONE/grader-01b.deterministic-grader.follow-up.md`
  § Deferred, items 1–4). It merges the former § Needs Zack AGENT-OPP
  "grader red-team".
  - *Decided 2026-10-31 (the CD):* the receiver rule is "Exclude proven
    non-PW". A method isn't a step only when its receiver is provably not
    Playwright (a literal, or a name assigned once from one); unknown
    receivers still count.
  - *Also decided:* the red-team is "Approve, with hardening". The run
    uses it once on Eval 01, and its misses become the run's test cases.

  It also covers `expect` variables, module constants, `**opts` and
  unclassified timeouts, and answer-key searches above the repo.
  *Depends on:* nothing; best before phase F's pilot.

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01bb.hardening.md`
- **Private-names check script** (refine pass, 2026-10-31):
  `.claude/scripts/check-private-names.ps1` scans the staged diff and the
  commit message (or, with `-All`, every tracked file and the whole
  history) against a local, untracked list of names
  (`.claude/*.local.*`, gitignored). It replaces the hand greps run before
  each commit since the 2026-10-30 leak, and works from oversee worktrees
  by reading the list from the main checkout. Per the Script SOP.

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/privnames-01.check-script.md`
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
        codegen workflow (Tech stack). Done: trial-run loop + Playtest
        SOP, `skills/` list, file contract for script-fix cases
        (ADR-0001), multi-user approach (none for now, 2026-10-31)
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

- **Eval: Playwright + Locust multi-user debug & fix** — iced 2026-10-31
  by the CD: "We can remove locust all together; python+playwright is
  sufficient for these evals, i need to do actual experiments with these
  with single user first before i start thinking about issues that only
  happen under a multiuser load." Revisit after single-user experiments;
  any multi-user run still targets localhost only (CLAUDE.md § Project
  pins).
