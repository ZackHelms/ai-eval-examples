# Plans

Feature/phase plans, authored per `.claude/templates/plan.md`. Drafted by
`/zmh-producer:backlog-plan-gen` (or a planning session by hand); run by
`/zmh-producer:oversee-implementation .claude/plans/<name>.md`, per the
config at `.claude/zmh/producer.md`.

## Naming

`<slug>.<what>.md` — a short project-unique slug plus a short description,
e.g. `combatmusic-01.dark-themes.md`. A follow-up plan that continues a
finished one appends a letter to the slug: `<slug>b.<name>.md`.

## Lifecycle

`DRAFT` → `APPROVED` → `IMPLEMENTED <date> (commit range)` (or `PARTIAL`) —
tracked in the plan's own `**Status:**` line. Every drafted plan has exactly
one `TODO.md` entry with priority + dependencies; how-tos and playtest
scripts never live in the plan itself — point at a note or skill instead.

Implemented plans (with their `.follow-up.md`, if any) archive to
`.claude/plans/DONE/` rather than being deleted — they're the record of what
was built and why, and self-contained residue may spawn a letter-suffixed
follow-up plan at oversee wrap-up.
