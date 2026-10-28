# Agents

Specialized AI roles with non-overlapping responsibilities. Definitions follow
`.claude/templates/agent.md`; frontmatter beyond `name` + `description` is
used only where a pin matters (model, tools, effort).

## Specialists

<FILL-IN: this studio's specialist agents — one row per agent, e.g. an
eval author (drafts prompt/inputs/grading to the eval anatomy), a research
agent (version pins, Playwright/Locust capabilities, two-source rule), and
the static-review agent (answer-leak + eval-structure checks) that IS step 1
of the project validation procedure. Keep the table format:>

| Agent | Owns | Notes |
| --- | --- | --- |
| `<FILL-IN>` | `<FILL-IN: eval domain or validation step>` | `<FILL-IN: model/tools pin, invariant it guards>` |

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
