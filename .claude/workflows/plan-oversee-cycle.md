# Workflow: Plan → Oversee Cycle

The Creative Director's outer loop for autonomous feature delivery. It sits
*above* any single session: plans are drafted in one step, implemented by
`/zmh-producer:oversee-implementation` in the next, and each run's closing
lines tell the CD exactly what to type next. This file exists so any session
can orient the CD ("what step am I at?") without re-deriving the process.

**Roles.** The overseer is **not** a `.claude/agents/` sub-agent — it is the
main session itself, given the role by `/zmh-producer:oversee-implementation`
(zmh-producer plugin, marketplace `zmhstudio`, configured via
`.claude/zmh/producer.md`). Sub-agents are the tiered implementers the
overseer spawns. The session model is what matters, not session identity:
after `/compact` a resumed session is effectively fresh.
Convention: a top-tier model drafts plans; a high-tier model oversees —
either via two sessions or one session with `/model` switches.

## Inputs

- A feature, bugfix, or "what's next" request from the CD (TODO.md's top
  un-blocked item when they don't specify).

## The cycle

1. **Start clean.** Resume (or open) a session whose last action was
   `/compact` — the planning/overseeing context comes from disk, not the
   transcript.
2. **Draft the plan.** Ask for a plan for the feature (or the next item from
   TODO.md). The session writes it to `.claude/plans/<name>.md` per
   `.claude/templates/plan.md`, adds the TODO.md entry, commits, and ends its
   final message with the two Handoff lines. Per the template's required tier
   audit, score every task against `.claude/skills/task-scoping.md` before
   finalizing. A large feature set may first get a plan-of-plans with plans
   drafted just-in-time, one at a time.
3. **Run it.** `/compact`, then `/zmh-producer:oversee-implementation
   .claude/plans/<name>.md` (on a high/top-tier model — the command gates
   this). The run isolates itself: worktree (branch
   `worktree-oversee+<slug>`, cut fresh from the default branch) → tasks
   execute and commit there → wrap-up integrates per this repo's Integration
   mode (`.claude/zmh/producer.md` § Integration) and, where configured,
   publishes → the worktree is removed on full success (kept for CD
   inspection on an integration failure). See the
   `/zmh-producer:oversee-implementation` command (zmh-producer plugin) for
   the full mechanics. Wait for the final report. It ends one of two ways:
   - a second line naming a drafted follow-up plan
     (`<slug><letter>.<name>.md`) → `/compact`, run that command, return here;
   - `/compact` only, plus a named recommended next plan → the residue went to
     TODO.md/`.follow-up.md`; the letter chain is done.
4. **Playtest when the report says to** (per this repo's Playtest SOP —
   `.claude/zmh/producer.md` § Reporting or CLAUDE.md § Playtest SOP), and
   feed feel verdicts back.
5. **Loop.** Go to step 2 for the recommended next plan, a new feature, a
   bugfix, or "what should we work on next".

## Required validation

Each overseer run self-gates (the project validation procedure green per task
and at wrap-up — static pre-pass plus the hard gate). The cycle adds one gate
of its own: **the playtest** for anything the report flags as
playtest-affecting — if a run reported red or the playtest fails, resolve
that before starting the next plan.

## Expected artifacts

Per iteration: an implemented plan archived to `.claude/plans/DONE/` with its
`.follow-up.md`, updated TODO.md/DONE.md, the run's commits landed on the
default branch, and per-task ledger rows appended to
`.claude/metrics/oversee-ledger.jsonl` — plus, when residue warranted one,
the next letter-suffixed plan ready to run.

## Completion checklist

None — this loop has no end state; each iteration's gate is the overseer
run's own wrap-up (`/zmh-producer:oversee-implementation` Step 5 —
zmh-producer plugin).
