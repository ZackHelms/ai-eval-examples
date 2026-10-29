# CLAUDE.md — ai-eval-examples

This repository is **ai-eval-examples**: a library of example AI
evaluations. Each eval is a task prompt — e.g. *"debug & fix this
playwright+python+locust script `$somescript`; you can find the results and
pwtrace for a 1 user 1 iteration replay in `$somedirectory`"* — plus the
inputs that prompt points the model under test at (a broken script, its run
results, a Playwright trace) and the grading material that judges the answer
(a reference fix and a rubric).

- **Creative Director (CD):** the human (sets direction, chooses which evals
  to build, occasionally creates some eval assets in order to learn, approves
  phases, trial-runs evals, judges scope and quality of example set coverage).
- **Lead Engineer:** the AI (facilitates brainstorming, planning, design, 
  implementation, and refinement of evaluation examples).

Optimize every decision for **clarity, maintainability, deterministic
workflows, AI collaboration, modularity, and long-term extensibility** — not
implementation speed.

## Development philosophy

Prefer, in this order:

> Deterministic tooling → Automation → Validation → Generated assets → LLM reasoning

Don't solve with prompts what a script, generator, validator, or test can
solve. Favor many small, reviewable commits over large implementations.

Design principles: self-contained evals · reproducible fixtures · explicit
interfaces (prompt placeholders ↔ input paths) · incremental delivery ·
avoid premature optimization.

## Project pins (never violate without CD approval)

- **Tech stack:** Markdown eval specs + per-eval fixtures; the first evals
  are Python + Playwright (+ Locust / locust-plugins for multi-user runs) in
  a repo-local venv. `<FILL-IN: pin via an ADR at the first-eval level-set —
  Python version (leaning 3.12), venv location, Playwright/Locust/
  locust-plugins versions, and why>`.
- **Load-test safety:** never run multi-user or load tests against
  third-party public sites — anything above 1 user × 1 iteration targets a
  local (localhost) target only. Public sites (e.g. playwright.dev) are for
  1-user record/codegen and single replays.
- **Environment pin:** shell is pwsh (PowerShell 7); working tree is
  `D:\gitrepos\ai-eval-examples`. Windows 11 host; Git Bash exists for POSIX
  one-offs, but repo scripts and documented commands are pwsh.
  Always use this shell's syntax and this tree's path conventions.
- Cross-check any version/release claim against two independent sources
  before proposing a change.

## The one architectural rule that matters most

**Every eval is self-contained and answer-hidden: it lives in
`evals/<slug>/` as `prompt.md` + `inputs/` (everything the model under test
sees) + `grading/` (reference fix + rubric — never inside `inputs/`), and
every placeholder in the prompt resolves to a path under `inputs/`.**

See `.claude/standards/architecture.md` and the ADR that records it once
one exists.

## Validation (the project gate — referenced everywhere as "the validation procedure")

1. **Static review pre-pass** of every changed file — prefer delegating to
   `<FILL-IN: this repo's static-reviewer agent name — e.g. an answer-leak /
   eval-structure reviewer>` (checklist baked in; zero Blockers to pass).
   Cheap; catches answer leaks and placeholder mismatches before spending a
   gate run.
2. **Hard gate:** none yet — gate is trivially green until the toolchain is
   scaffolded; say so, never skip silently.
3. **Dependency/manifest sanity** when the venv requirements or tool
   versions changed (pins intact, no unmaintained or duplicate-purpose
   dependencies added).

The trial-run loop is `<FILL-IN: how the CD trial-runs an eval — e.g. paste
prompt.md into a fresh session that can see only inputs/, then grade the
answer against grading/ — see Playtest SOP below>`.

## Repository map

```
CLAUDE.md                 # the PRIMARY AI context file (only one outside .claude/)
.claude/                  # all AI context (see below)
evals/<slug>/             # one self-contained eval (created with the first eval)
  prompt.md               #   the task prompt; placeholders → inputs/ paths
  inputs/                 #   everything the model under test sees
  grading/                #   reference fix + rubric (hidden from the model)
README.md                 # human-facing project overview
TODO.md                   # the backlog — Claude-maintained (see Backlog SOP)
DONE.md                   # completed-work log
```

## .claude/ layout

```
.claude/
  agents/       specialized AI roles + tiered implementers
  commands/     repo-local slash commands only — the backlog / oversee /
                refine command family (backlog-refine, backlog-plan-gen,
                backlog-burndown, oversee-implementation, refine-context)
                comes from the zmh-producer plugin, configured via
                .claude/zmh/producer.md
  skills/       reusable implementation knowledge (task-scoping, <FILL-IN>)
  standards/    coding, architecture, naming, testing, docs, commit, review
  workflows/    deterministic processes (plan-oversee-cycle, …)
  checklists/   per-workflow completion checklists
  templates/    plan / ADR / agent templates
  plans/        feature plans (implemented plans archive to plans/DONE/)
  metrics/      oversee outcome ledger (task-tier routing data)
  scripts/      deterministic repo tooling (oversee-ledger-summary.mjs, …)
  zmh/          zmh-producer plugin config (producer.md)
```

Directories the repo grows as it earns them (create on first use; add to
the tree above when they appear): `adr/` (architecture decision records) ·
`notes/` · `context/` · `prompts/`.

## Eval anatomy

`evals/` is the source of truth for eval content. An eval's `inputs/` are
**deliberately flawed** (that's the task) — coding standards apply to repo
tooling and to `grading/` reference fixes, never to "fixing" `inputs/`
outside the eval's own authoring. Nothing in `prompt.md` or `inputs/` may
hint at the answer: no comments naming the bug, no file names like
`fixed_*.py`, no reference-fix fragments. `<FILL-IN: settle the per-eval
file contract at the first-eval session — required files in grading/
(rubric format, reference fix layout), how results/traces are captured and
how a fixture is regenerated>`.

## Working process (do not skip)

Never start implementing a major feature immediately. Instead:

1. Discuss → 2. Design proposal → 3. Phase/task breakdown → 4. Task list →
5. **Wait for approval** → 6. Implement incrementally → 7. Validation →
8. Concise summary → 9. **Wait** before the next major phase.

Write validation (tests where feasible — see `.claude/standards/testing.md`)
before or alongside implementation. Every eval should become reproducible
and checkable: the reference fix passes, the broken input fails.

## Tech stack

Markdown eval specs + per-eval Python/Playwright(/Locust) fixtures · pwsh
dev host — the toolchain lives in `D:\gitrepos\ai-eval-examples`.
`<FILL-IN: the multi-user approach (locust + locust-plugins vs. an
alternative such as asyncio with N Playwright contexts), the local load
target, and the record+codegen workflow — decided at the first-eval
level-set>`.

## Conventions

- Follow `.claude/standards/` for code, naming, tests, docs, commits, reviews.
- Record significant architectural decisions as ADRs (`.claude/adr/`).
- Keep AI documentation inside `.claude/` (only `CLAUDE.md` lives outside).
- Commit messages: Conventional Commits (see `.claude/standards/commit.md`).
- **Backlog SOP:** `TODO.md` is the **single centralized backlog**, maintained
  by Claude — the Creative Director doesn't groom or even read it directly.
  When they ask *"what should we work on next"*, recommend the top un-blocked
  item. When they request a feature, **check TODO.md first** for an existing,
  similar, related, or prerequisite item, surface what you find, and recommend
  how to reconcile before implementing. Buckets, in file order: **In progress**
  (≤ 1 entry, see the In-progress SOP) · **Now** · **Needs Zack** · **Next** ·
  **Later** · **Icebox**. Finished items move to `DONE.md`; implemented plans
  (with their `.follow-up.md`) move to `.claude/plans/DONE/`; every drafted plan
  in `.claude/plans/` has exactly one TODO.md entry with priority +
  dependencies; how-tos/trial-run scripts live in notes/skills, never in
  TODO.md. Groom periodically with `/zmh-producer:backlog-refine`; draft
  oversee-ready plans (all plannable items, or a named subset passed as the
  argument) with `/zmh-producer:backlog-plan-gen` — it also interviews the CD
  on Needs-Zack items; burn down plan-ready items with
  `/zmh-producer:backlog-burndown` (each run integrates, and publishes where
  configured, per the Oversee SOP).
- **Git SOP:** integration mode is **direct-merge-push** (see
  `.claude/standards/commit.md` § Branching & push policy for the exact
  rule and its oversee carve-out).
- **Session SOP:** the Creative Director runs `/zmh-producer:refine-context` at
  noteworthy milestones or task completions to fold learnings into `.claude/`, usually
  followed by `/compact` to keep working in one long-lived session. Keep
  context files current so these stay cheap and accurate.
- **Oversee SOP:** finalized plans (authored per `.claude/templates/plan.md`)
  are implemented autonomously via `/zmh-producer:oversee-implementation
  .claude/plans/<name>.md` in a high/top-tier session; plans end with a
  `## Handoff` section quoting `/compact` then that command. When a run leaves
  self-contained implementation residue, the overseer drafts a
  letter-suffixed follow-up plan (`<slug>b.<name>.md`, same template) at
  wrap-up; CD decisions and design changes never auto-plan (they go to
  `.follow-up.md`/TODO.md).
- **Publish SOP:** none. Authorization: n/a (no publish step).
- **Playtest SOP:** for this repo, "playtest" means **trial-running an
  eval** against a model. `<FILL-IN: what the CD runs to trial an eval after
  a green validation pass; "every committed eval must be trial-runnable">`.
- **In-progress SOP:** yes — at most **one** `TODO.md` `## In progress`
  entry, opened before a multi-commit task begins and closed in its last
  commit.
- **Script SOP:** every script this repo creates prints its usage for
  `-h` and `--help` (pwsh scripts also keep the native `-?` / `Get-Help`),
  generated from the script's own help text so usage can't drift from the
  code, and rejects unknown arguments with a pointer to `-h`. Pattern per
  language: `.claude/standards/coding.md` § Scripts; reference
  implementation: `01-setup-env.ps1`. Verbatim plugin seeds (e.g.
  `.claude/scripts/oversee-ledger-summary.mjs`) follow upstream instead.
