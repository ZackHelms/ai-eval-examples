# Agents

Specialized AI roles with non-overlapping responsibilities. Definitions follow
`.claude/templates/agent.md`; frontmatter beyond `name` + `description` is
used only where a pin matters (model, tools, effort).

## Specialists

| Agent | Owns | Notes |
| --- | --- | --- |
| `eval-static-reviewer` | step 1 of the validation procedure: answer leaks, evidence, generic content, frozen Eval 01, scope | sonnet; read-only (Read, Grep, Glob, Bash); returns `VERDICT=`/`BLOCKERS=` lines |
| `grader-red-team` | adversarial fake-fix variants against `tools/scriptfix`'s static checks | opus; writes only under `%TEMP%\redteam\`; returns `VARIANTS=`/`MISSES=` lines |

Deliberately **not** created yet (add when the work actually starts, per
`/zmh-producer:refine-context` Step 7): `<FILL-IN: agents this repo anticipates needing
but hasn't built — e.g. a fixture-capture agent, a grader/rubric agent>`.

## Tiered implementers (used by /zmh-producer:oversee-implementation)

`implementer-low` · `implementer-medium` · `implementer-high` ·
`implementer-xhigh` — identical generic plan-task executors differing only in
frontmatter `effort:`. Copied byte-exact into every studio that installs
`zmh-producer` (effort has no per-call override; model does). Routing
rubric: `.claude/skills/task-scoping.md`.

## Ownership rule

Eval domains have exactly one owning agent; anyone proposes, the owner
disposes. The main session (Lead Engineer) coordinates and implements;
role-shaping changes (new agents, ownership moves) are CD decisions.
