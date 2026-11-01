# TODO — the backlog

Claude-maintained (see CLAUDE.md § Backlog SOP). Buckets: **In progress** ·
**Now** · **Needs Zack** · **Next** · **Later** · **Icebox**.

<!-- --- -->

## In progress

- **grader-01d: the trial runner** — oversee run of
  `.claude/plans/grader-01d.trial-runner.md`, started 2026-11-01 with
  `/zmh-producer:oversee-implementation .claude/plans/grader-01d.trial-runner.md`
  on branch `worktree-oversee+grader-01d`. No commits landed yet.

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
  → **next:** D trial runner (plan-ready, below) and E LLM judge (below;
  independent of each other) → F pilot. Absorbs the former § Next items
  Eval 01 grader, Capture script, Trial runner script and Eval: impossible
  locator.
- **grader-01 phase D: trial runner.** `20-run-trials.ps1` runs N
  headless one-shot trials of a case, one at a time, with the launcher
  gotchas built in. It writes a subject sidecar that the grader reads, and
  `-SelfTest` checks the launcher for about $0.01. Context bundles are
  deferred: `--safe-mode` disables CLAUDE.md. *Depends on:* phase B
  (done); independent of C.

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01d.trial-runner.md`
- **grader-01 phase E: LLM judge.** Judges the `judge`-severity tags
  (`retargeted`, `new-wait`, `changed-setup`, `broad-pattern`) and the
  escalate cases' check 1, and resolves Eval 01's `pending-judge` runs 10
  and 12. The cases' judge items exist now (phase C's corpora).
  *Depends on:* phase C (done). Not planned yet: run
  `/zmh-producer:backlog-plan-gen` for it.

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
- **Your user-profile path in captured evidence** (grader-01c,
  `.claude/plans/DONE/grader-01c.cases.follow-up.md` item 10). Every
  case's `inputs/results.txt` and trace name `C:\Users\<you>\AppData\…`
  (the capture venv, Python's stdlib, `%TEMP%\pwrun`), as Eval 01's
  evidence already did. Options: keep it (it isn't a product or work
  name); capture under a neutral local account; or wait for the isolated
  trial environment (§ Next) and capture there.

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

  **Not in its plan yet:** grader-01c's grader gaps
  (`.claude/plans/DONE/grader-01c.cases.follow-up.md` § Deferred): four
  escalate-rule shapes that slip past the new rule, the untagged
  retarget after a path divergence, and `30-grade-trials.ps1`'s relative
  `-Case` and exit-1 usage errors. The plan's anchors still match HEAD
  (grader-01c didn't touch them). To fold these in, re-draft it first
  with `/zmh-producer:backlog-plan-gen` (recommended); otherwise they
  need a later plan.

  **Plan ready (2026-10-31)** — run:
  `/zmh-producer:oversee-implementation .claude/plans/grader-01bb.hardening.md`
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
