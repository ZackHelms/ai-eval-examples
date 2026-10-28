# Documentation Standards

Prefer concise docs; document decisions and rationale, not every detail.

## Where things live

- **`CLAUDE.md`** — the single AI entry point; high-level orientation. The
  only AI context file outside `.claude/`.
- **`.claude/`** — all other AI documentation (standards, skills, agents,
  workflows, ADRs); keep it here unless there's a compelling reason.
- **`README.md`** — the human-facing overview, kept in sync with reality
  (no `docs/` tree yet).
- **ADRs (`.claude/adr/`)** — the *why* behind significant decisions.
- **`evals/`** — the authoritative eval content (each eval self-contained
  per `architecture.md`).
- **`TODO.md`** — the single centralized backlog, Claude-maintained (Backlog
  SOP in `CLAUDE.md`); one or two lines per item with priority bucket,
  links, dependencies. **Never** put how-tos, trial-run scripts, or tuning
  manuals in it — those live in `.claude/notes/`/`.claude/skills/` with a
  one-line pointer from the backlog item.
- **`DONE.md`** — append-only completed-work log, newest first (say *why*
  when a superseded item moves here).
- **`.claude/plans/DONE/`** — archive for implemented plans + their
  `.follow-up.md` (extract open bullets into `TODO.md` first). Optional:
  a `YYYYMMDDHHMM.<slug>.md` prompt log at repo root, append-only, if this
  repo adopts the prompt-file-convention skill.

## Principles

Keep docs synchronized with the code — update the doc in the same change
that invalidates it. Code comments explain *why*; docs explain *how it fits
together*. Avoid duplicating information; link to the authoritative source.
Write for both humans and AI agents: explicit, structured, skimmable.

## When to write an ADR

When a decision is hard to reverse, affects multiple systems, or future-you
will ask "why did we do it this way?" — use `.claude/templates/adr.md`.
