# Skill: Task scoping for tiered implementers (cost-aware routing)

> Maintained by the `/zmh-producer:oversee-implementation` wrap-up (damped
> self-edits) and consulted by planning sessions (tier audit). **Hard
> budget: 120 lines.** Additions must compress or replace — if an edit
> would exceed the budget, merge or generalize existing rules first.

## Why

The CD optimizes for **total credit cost, not wall-clock time**. Cost ≈
Σ attempts (model rate × effort × task tokens) + overseer tokens spent
reviewing/correcting. A cheap model that fails cleanly and escalates costs
one wasted attempt; one that *almost* succeeds and needs overseer cleanup
costs more than starting a tier higher. Route by expected first-pass
success, not optimism.

## Profile — the CD's cost/speed dial

**Current profile: balanced.** (`cost` | `balanced` | `speed` — the CD edits
this line; a trailing `profile=<name>` on plan-gen / oversee / burndown wins.)

- **cost** — start each task at the lowest rung that passes its checklist;
  accept escalation churn (slowness lives in retries and spin-ups, not in
  haiku's token speed); decompose fully. Plus **three hard rules** — quota
  ceilings, not preferences, because the expensive failure is a session that
  dies mid-run with work in flight: **never `fable`** (not at drafting, not as
  an escalation target — the ladder tops out at `opus · implementer-xhigh`);
  **one subagent in flight at a time** (no parallel spawns, no backgrounding,
  even where the plan marks tasks parallel-safe); and **burndown `max=1`**, so
  a quota cutoff can only ever interrupt one known run.
- **balanced** — start at the lowest rung expected to pass **first try**:
  haiku for verbatim transcription and any checklist-passing mechanical edit
  (ledger 2026-07, 286 rows: haiku 10/10 first-pass; 12 rows above haiku retro
  haiku-viable, 6 mechanical-edit); other judgment starts at sonnet; escalate
  after one warm retry.
- **speed** — sonnet-high floor, opus for judgment, never haiku; parallelize
  file-disjoint non-committing tasks where the plan allows.

Plans record tiers under the profile current at drafting time (named in the
guidance-table caption); at run time the overseer maps assignments through the
**active** profile (override argument > this line): `speed` floors every
assignment at sonnet-high; `balanced` re-checks each haiku assignment against
its stricter bar; `cost` runs assignments as written apart from its fable cap
— a `fable` assignment inherited from another profile's plan becomes `opus ·
implementer-xhigh` (named in the report), the one **downward** move mapping
ever makes.

Mapping is otherwise upward-only: decomposition happens at drafting time and
can't be recovered later, so a `speed` plan (coarse tasks) run under `cost`
just runs as written. On a mismatch the overseer proceeds, notes it in the
report, and — when the active profile is the cheaper one — recommends
redrafting (`/zmh-producer:backlog-plan-gen <item> profile=cost`) if the
savings matter.

## The ladder

| Rung | When |
| --- | --- |
| haiku · implementer-low | verbatim/near-verbatim transcription: the plan embeds exact content or names an exact in-repo pattern; ≤ ~3 files; machine-checkable done |
| haiku · implementer-medium | mechanical edits with exact file targets and an enumerated gotcha list; zero ambiguity anywhere in the task |
| sonnet · implementer-medium | pattern-following docs/config/tests where the plan names the pattern but wording/details are the agent's |
| sonnet · implementer-high | **default**: single-system (or single-package) code with judgment inside clear rails |
| opus · implementer-high | cross-system/cross-package changes, invariant-bearing code, API design, non-trivial debugging |
| fable · implementer-high/xhigh | novel algorithms, gnarly root-causing — sparingly; **never under the `cost` profile** |

## Haiku-viability checklist (ALL must hold)

1. Exact targets: files named; anchors unambiguous (file:line or unique
   strings that survive drift).
2. A pattern to copy exists in-repo and the task names it — or the content
   is verbatim in the plan.
3. The done-criterion is machine-checkable (a command or checklist).
4. Zero design judgment: nothing to name, no cross-file trade-offs, no
   ambiguity — a low tier resolves ambiguity by guessing.
5. Gotchas enumerated; nothing relies on "obviously you'd also…" — low
   tiers are over-literal and won't fix adjacent breakage or infer
   unstated steps.
6. No secrets, publishing, git-history surgery, or outward-facing actions.

If any item fails: decompose (below) or start at sonnet.

## Decomposition patterns (move judgment into the plan / a higher tier)

- **Spec-then-fill:** the plan (or a high-tier task) writes the
  interface/test/verbatim content; a low-tier task makes it pass or
  transcribes it.
- **Batch same-shape edits:** N repetitive edits = one low-tier task
  with one worked example.
- **Split mixed tasks:** carve the mechanical bulk into a low-tier task;
  keep the judgment kernel at sonnet/opus — worth it only when the
  mechanical part pays for a second agent spin-up.
- Floor: don't decompose below ~15 minutes of work — per-agent overhead
  (spin-up, plan reading, validation) dominates tiny tasks.

## Known per-tier failure modes (ledger-fed)

<FILL-IN: repo-specific tier examples and circuit-breakers — grow from this
repo's oversee ledger. Seed with the two universal ones every originating
studio observed before any local ledger rows exist:
- **haiku:** drifts from unstated repo conventions (name an example file);
  over-literal (checklist item 5); may report success without running the
  validation procedure — the spawn prompt must require pasting its output.
- **sonnet-medium:** fine for docs/tests; on code it under-explores callers.
Promote a rule here only after **2+ ledger observations**; cite the dates.>

## Circuit breaker

Two ledger strikes (needed escalation, or overseer cleanup) for the same
category × tier within 5 runs → stop routing that category to that tier and
record the stop here with the reason. Re-open only via a rubric edit stating
what changed (better decomposition, a new checklist item).

## Ledger duties (overseer wrap-up)

Append one row per task to `.claude/metrics/oversee-ledger.jsonl` (schema
in `.claude/scripts/oversee-ledger-summary.mjs`'s header), including
`haiku_viable_retro` — the post-hoc verdict on whether the task *as
specified* was haiku-viable. This calibrates the checklist even for tasks
that ran at sonnet or above. Run the summarizer; edit this skill only under
the damping rules above (2+ observations, budget, compress-or-replace).
