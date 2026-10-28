# <plan-slug> — <one-line title>

**Status:** DRAFT | APPROVED | IMPLEMENTED <date> (commit range) | PARTIAL
**Requested:** <YYYY-MM-DD>.
**Scope:** <dirs/systems/packages this plan touches>.

> CD note: this template exists to make plans executable by
> `/zmh-producer:oversee-implementation` (zmh-producer plugin, configured via
> `.claude/zmh/producer.md`) — the "Implementation guidance" section is what
> the overseer reads to assign models/effort and to make decisions without
> asking.
> Planning sessions: end your final message with the two Handoff lines below
> so they sit on screen at plan-approval time — `/compact` first, because the
> overseer re-reads the plan and its references from disk, making the
> planning transcript pure token cost.

## Goal

What done looks like, in one short paragraph.

## Context

Why this change is being made — the problem, what prompted it, intended outcome.

## Implementation guidance (for the overseer)

| # | Task | Category | Model | Effort | Rationale |
| - | ---- | -------- | ----- | ------ | --------- |
| 1 | <task> | docs | haiku | low | verbatim content/exact pattern; passes the haiku-viability checklist |
| 2 | <task> | mechanical-edit | sonnet | high | mechanical; exact targets below |
| 3 | <task> | cross-system | opus | high | cross-system design judgment |

- **Ordering / dependencies:** <1 → 2 → 3; 4 is independent>. Parallel-safe:
  <none | tasks N+M (file-disjoint, only one commits)>. Default is sequential —
  subagents share the working tree, and under the `cost` profile the overseer
  runs one subagent at a time regardless of what this line marks parallel-safe.
- **Files owned per task:** <task 1: evals/<slug>/**; task 2:
  .claude/scripts/**> — no two concurrent tasks touch the
  same files.
- **Validation per task:** <check + expected result>; final gate is a green
  project validation pass (CLAUDE.md § Validation).
- **Tier audit (required):** before finalizing, score every task against
  `.claude/skills/task-scoping.md` — split part-mechanical tasks per its
  decomposition patterns; any task assigned above haiku states which
  checklist item fails. Assign tiers under the skill's current profile (note
  it in the table caption); the overseer re-maps at run time if the active
  profile differs. **Under `cost`, `fable` is not available** — decompose the
  hard kernel or cap it at `opus`/`xhigh`; a `fable` row drafted under another
  profile is demoted at run time, so a plan meant to be run under `cost`
  should not depend on one. Fine-grained scoping trades planning tokens for
  cheaper execution; the ledger verifies the trade.
- **Decision defaults:** <"if X is ambiguous, prefer Y"> — pre-empt
  escalations; the overseer decides and logs, it does not ask.
- **Embedded-content QA (required):** verbatim code blocks and derived counts
  (expected test totals, file counts) in this plan get static-review scrutiny
  before the plan is finalized — re-derive every count as baseline + added −
  removed, and review verbatim code as if it were a commit. Prefer interfaces
  + done-criteria over long verbatim blocks; when a count could drift, state
  the invariant ("suite grows by exactly what this task adds") instead of a
  literal.
- **Escalation triggers:** <the few things that justify stopping for the CD —
  credentials, permissions, irreversible/outward-facing actions, steps
  requiring a manual playtest verdict, not listed here>.
- **Playtest:** <note whether the CD should playtest after this plan lands,
  and what to look at | "no playtest impact">.
- **Publish:** <omit = the overseer publishes during its wrap-up per this
  repo's Publish SOP | "do not publish" = overseer only prompts for it in
  the report — see `.claude/zmh/producer.md` § Publish for what applies here>.
- **Commit strategy:** one conventional commit per step, scope `<scope>`.

## Steps

1. <step — files, exact changes, done-criteria>
2. …

## Gotchas / bindings

- <every known trap, constraint, or binding decision the implementer must
  honor — this list is the highest-value section for a mid-tier implementer>

## Validation

How to verify end-to-end (the project validation procedure incl. the hard
gate, checks, dry-runs; say what a manual playtest must confirm beyond
gate-green, if any).

## Follow-ups

Known deferred items (the overseer adds discovered ones to
`<plan>.follow-up.md`; self-contained implementation residue may instead
become an overseer-drafted follow-up plan — `<slug><letter>.<name>.md`, this
same template and grounding bar — per the
`/zmh-producer:oversee-implementation` wrap-up. CD decisions and design
changes never auto-plan).

## Handoff

```
/compact
/zmh-producer:oversee-implementation .claude/plans/<name>.md
```
