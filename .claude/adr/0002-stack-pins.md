# ADR-0002 — Python 3.12, Playwright 1.64.1 and codegen-recorded scripts

- **Status:** Accepted
- **Date:** 2026-11-01
- **Deciders:** CD (adopted current practice at the first-eval level-set)

## Context

The scaffold left the stack's pins to "the first-eval level-set":
CLAUDE.md § Project pins and § Tech stack, `.claude/standards/coding.md`
§ Language and `.claude/standards/review.md` item 3 each held a
`<FILL-IN>` for them, and `01-setup-env.ps1` pinned Python 3.12 with an
"ADR pending" comment. Eval 01 and the five generated cases were built,
captured and graded with the versions below, so the level-set (DONE.md,
2026-11-01) adopted what is in use instead of choosing anew. No version
changes here.

## Decision

We will keep the stack the evals were built on:

- **Python 3.12**, in a venv at the repo root (`.venv\`), built by
  `.\01-setup-env.ps1` from `requirements.txt`. The script refuses a venv
  of any other minor version. The venv is never committed, and
  Playwright's browsers live in the per-user cache
  (`%LOCALAPPDATA%\ms-playwright`) that every venv shares.
- **`playwright==1.64.1`**, pinned exactly in `requirements.txt`: a trace
  opens only in a viewer at least as new as the Playwright that recorded
  it. `pytest==9.2.0` is pinned the same way for the gate.
- **Targets:** playwright.dev only for 1-user record/codegen and single
  replays. Anything above 1 user × 1 iteration runs against a local test
  site (CLAUDE.md § Project pins). No multi-user runner for now (CD,
  2026-10-31).
- **Scripts are recorded with codegen**, as Eval 01's was:
  `playwright codegen --target python-async --viewport-size "1280,720"
  -o <file> <url>`, with tracing then added around the journey by hand
  (`README.md` § Record, Replay, Create Eval). Generated cases derive from
  a recorded script by recipe (`grading/recipe.toml`,
  `.\10-make-case.ps1`; ADR-0001's case contract).

## Consequences

- The pins are written down once. CLAUDE.md, the coding and review
  standards and `01-setup-env.ps1` point here.
- Fixtures stay reproducible: each case's `grading/capture.toml` records
  the Python and Playwright versions it was captured with.
- A version bump is a superseding ADR: cross-check the release against
  two independent sources first (CLAUDE.md § Project pins), then recapture
  every case whose trace or output would change.
- Not decided here (TODO.md § Later): a lint or type-check pin, whether
  every eval must use the async API, and the browser channel. Today's
  scripts use the async API and Playwright's bundled Chromium, as codegen
  and `01-setup-env.ps1` set them up.
- Revisit when a new eval needs another Python or Playwright release, or
  the local test site needs another browser.
