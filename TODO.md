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
  `.claude/plans/DONE/grader-01bb.hardening.md`) → E LLM judge (done
  2026-11-01: `tools/scriptfix/judge.py`, the calibrated judge in
  `rubrics/script-fix/judge/`, `.claude/plans/DONE/grader-01e.llm-judge.md`)
  → **next:** F pilot. Absorbs the former § Next items Eval 01 grader,
  Capture script, Trial runner script and Eval: impossible locator.
- **grader-01 phase F: pilot.** Run the six cases against real models with
  the full pipeline (trials, grade, judge, report).
  *Depends on:* the CD's review of the judge's right answers (§ Needs
  Zack). Next: `/zmh-producer:backlog-plan-gen phase F pilot`.

<!-- --- -->

## Needs Zack

- **Playtest: review the judge's right answers** (grader-01e, 2026-11-01).
  The Lead Engineer set them; the judge passed calibration against them,
  29 items 5 out of 5. They're in each case's `grading/corpus/judge.toml`,
  each with a one-line `why`. The two likeliest to flip:
  - the `smell-first.py` items (`cheat`): `.first` lands on the sidebar
    link, which goes to the same page;
  - `ok-exact-names.py`'s loose names (`ok`).

  To flip one, edit its `answer` and `why`, then run
  `.\30-grade-trials.ps1 -Calibrate` (about an hour, about $1.10). Also add
  any cheat rulings to `rubrics/script-fix/judge/cheats.md` as you find
  them. Unblocks phase F.
- **Test-site element inventory: hands-on pass** (the CD's request,
  2026-10-31): the first pass is `.claude/notes/test-site-element-inventory.md`,
  generic by rule (CLAUDE.md § Project pins: generic content only). The
  CD's pass on real apps marks which of its element patterns break scripts
  in practice, and adds any missing ones (pattern names only). Feeds the
  local test site.
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
    (Read, Glob, Grep, Edit, Write, Bash, PowerShell; grader-01bb);
  - if the grade comes out `pending-judge`, the same `NEXT=` command then
    asks the judge (about $0.01–0.03 a question) and prints each answer and
    its reason (grader-01e; `-NoJudge` skips it).

  The launcher's self-test already passed live, before and after the
  allowlist (`.claude/plans/DONE/grader-01d.trial-runner.follow-up.md`
  item 9, `.claude/plans/DONE/grader-01bb.hardening.follow-up.md`
  decision 17).

<!-- --- -->

## Next

- **Grader hardening, round 2** (grader-01bb's residue,
  `.claude/plans/DONE/grader-01bb.hardening.follow-up.md` § Deferred).
  - **The CD's rubric rulings** (*Decided 2026-11-01*, DONE.md):
    - `launch(slow_mo=…)` and an action's `delay=…` are fixed `sleep`s
      (zero);
    - a `page.evaluate` that rewrites the page under test gets a new zero
      tag (its name is the plan's call).

    Both change the rubric's patterns, so the round opens with
    `rubric-v1.md` (ADR-0001: a rubric change is a new file, and old trials
    are re-graded from their saved fixes).
  - 7 red-team misses still slip past the static checks:
    - swapped clicks read as two judge `retargeted`, not
      `changed-journey`;
    - helpers aren't followed at call sites (an uncalled def, a helper
      called under `if`);
    - JS run through `page.evaluate` is opaque (a sleep, a navigation);
    - a monkeypatched Playwright method;
    - `delay=` (now ruled a `sleep`).
  - The small residue:
    - `getattr` in three more collectors;
    - a misleading test name;
    - marker arguments aren't searched;
    - promote the static calibration (fake `replay_fn`) to a tested
      command.

  *Plannable now:* rubric-v1, the three rulings and the small residue. The
  helper design needs a short design pass first. It can land before or
  after the phase F pilot (trials re-grade from their saved fixes); the
  pilot's real trials will show which other shapes models actually
  produce.
- **Level-set ADR** (the CD adopted current practice, *Decided
  2026-11-01*, DONE.md). Write ADR-0002 recording: Python 3.12 in a
  repo-root `.venv` built by `01-setup-env.ps1`, with
  `playwright==1.64.1`; the target policy (playwright.dev for 1-user
  record/codegen and single replays only, a local test site for anything
  more); codegen-recorded scripts. It records what's in use, so no version
  changes. Then resolve the matching markers: `CLAUDE.md` (the stack pin
  and the codegen workflow), the Python half of `coding.md`'s language
  pin, the version half of `review.md`'s pin check, and
  `01-setup-env.ps1`'s "ADR pending" comment. Docs-only and small:
  `/zmh-producer:backlog-plan-gen level-set ADR`, or one sitting.
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
  `/zmh-producer:studio-init`; the level-set's decided half is the
  Level-set ADR item in § Next):
  - [ ] `CLAUDE.md` — stack/version ADR pin; codegen workflow (Tech
        stack): both → the Level-set ADR. Done: trial-run loop + Playtest
        SOP, `skills/` list, file contract for script-fix cases
        (ADR-0001), multi-user approach (none for now, 2026-10-31),
        static-reviewer agent name (`eval-static-reviewer`, grader-01c)
  - [x] `.claude/zmh/producer.md` — Environment setup quirks (worktree
        venv bootstrap; refine pass after grader-01b)
  - [ ] `.claude/standards/coding.md` — Python version (→ the Level-set
        ADR); lint/type pin and the remaining Playwright API pins (sync vs
        async, browser channel; waits + transaction timers done), which
        the level-set didn't decide
  - [x] `.claude/standards/architecture.md` — shared-tooling location
        (ADR-0001); learnings seeded (they keep growing)
  - [x] `.claude/standards/naming.md` — eval slug numeric prefix
        (ADR-0001)
  - [x] `.claude/standards/testing.md` — test/check runner; test directory (grader-01b)
  - [ ] `.claude/standards/review.md` — static-reviewer version/API pins
        (the version half → the Level-set ADR)
  - [ ] `.claude/agents/README.md` — anticipated agents (the specialist
        table is done: `eval-static-reviewer`, grader-01c)
  - [ ] `.claude/checklists/README.md` — per-workflow checklists (as
        workflows grow)
  - [x] `.claude/skills/task-scoping.md` — per-tier failure modes (seeded
        2026-10-31, privnames-01; keeps growing from the oversee ledger)
- **SDK trial harness** — run trials unattended with the Claude Agent SDK:
  pick model + effort + tools, log or deny every tool call before it runs,
  save the full transcript, hand the result to the grader-01 grader.
  *Depends on:* the isolated trial environment (grader-01 phase E is done).
- **Eval 01 variant: misleading evidence** — deliberately corrupt the
  characters in `results.txt` (as the first capture did by accident) while
  the trace stays correct. Tests whether a model cross-checks the trace or
  runs its fix instead of copying implausible text (Haiku 4.5's first
  trial run did neither). Unblocked (Eval 01 is complete); it stays in
  Later behind the phase F pilot, whose numbers it would be compared
  against.

<!-- --- -->

## Icebox

- **Eval: Playwright + Locust multi-user debug & fix** — iced 2026-10-31
  by the CD: "We can remove locust all together; python+playwright is
  sufficient for these evals, i need to do actual experiments with these
  with single user first before i start thinking about issues that only
  happen under a multiuser load." Revisit after single-user experiments;
  any multi-user run still targets localhost only (CLAUDE.md § Project
  pins).
