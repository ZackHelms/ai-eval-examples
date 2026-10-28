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

- **Eval 01 — basic 1-user Python + Playwright debug & fix** — record+codegen
  a short script against a public site (e.g.
  https://playwright.dev/python/docs/intro), break it realistically, capture
  the 1 user × 1 iteration results + trace into `inputs/`, write
  `prompt.md` and `grading/`. Worked on together with the CD; establishes
  the per-eval file contract. Env is ready (`01-setup-env.ps1`).
  *Blocked on:* level-set.

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
  (d) record+codegen vs. hand-written scripts; (e) per-eval file contract
  (rubric format, how fixtures are captured/regenerated). Outcome: an ADR +
  the matching `<FILL-IN>`s in CLAUDE.md and `.claude/standards/` resolved.

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
  `prompt.md`/`inputs/` references `grading/`, required files exist.
  *Depends on:* Eval 01 (file contract).

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
        Playwright/Locust API pins
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

<!-- --- -->

## Icebox

*Nothing yet.*
