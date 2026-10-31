# ADR-0001 — One shared rubric and grader for script-fix cases

- **Status:** Accepted
- **Date:** 2026-10-30
- **Deciders:** both (design by the Lead Engineer, decisions by the CD)

## Context

Eval 01 has its own 100-point rubric, graded by hand. That doesn't scale to
the CD's goal: a large suite of "debug and fix this Playwright script" cases,
each run many times per subject, to rate how hard each kind of defect is
and to tune a script-hardening agent's context files until it succeeds
reliably. Per-case rubrics would also make scores incomparable across
cases.

The design, its statistics and the CD's nine decisions are in
`.claude/plans/grader-01.global-rubric-design.md`. This ADR records the
parts that shape the repo: where the shared rubric and tooling live, and
how a case refers to them.

## Decision

We will grade every script-fix case with one shared, versioned rubric and
one grader:

- **Rubric:** `rubrics/script-fix/rubric-v0.md`, binary per trial
  (100 / 0 / invalid); a subject's score on a case is its pass rate over N
  one-shot trials. A rubric change is a new file (`rubric-v1.md`); old
  trials are re-graded from saved fixes and transcripts.
- **Prompt:** `rubrics/script-fix/prompt.md`, the same wording for every
  case; each case's `prompt.md` is a verbatim copy.
- **Case contract:** a case's `grading/` holds `case.toml`
  (`rubric = "script-fix-v0"`, `expected = "fix" | "escalate"`, `issue`,
  `origin`, `defect`, `fails_at`, `target`), `recipe.toml` (how the case is
  built), `reference/script.py`, `corpus/` (labeled fixes), and the
  grader-written `fixes/<hash>.py` and `trials.jsonl`. The answer-hiding
  rule is unchanged: none of this is in `prompt.md` or `inputs/`.
- **Shared tooling location:** `tools/` at the repo root. The grader is a
  Python package, `tools/scriptfix/` (standard library only), with pytest
  tests in `tools/tests/`; pytest becomes the repo's first hard gate.
  CD-facing entry points are root pwsh scripts per the Script SOP:
  `10-make-case.ps1`, `20-run-trials.ps1`, `30-grade-trials.ps1`.
- **Judge:** the LLM judge is Sonnet 5.5 through `claude -p` with no tools
  and no MCP servers, asked only narrow questions about trials that would
  otherwise pass; verdicts are cached, and `unsure` goes to the CD.
- **Eval 01 stays as it is:** its prompt, inputs, hand rubric and hand
  grades are frozen as the grader's calibration set. Its one-defect,
  shared-prompt successor is case 02.

## Consequences

- Scores are comparable across cases and subjects, and readable per issue
  type. Adding a case means a recipe and a `case.toml`, not a rubric.
- A binary score gives up the partial credit of Eval 01's rubric
  (diagnosis, evidence, honest report); tags record why a trial failed.
- The grader is now load-bearing: a false pass rewards cheating contexts.
  Each case's corpus and the CD's spot-checks guard it.
- Follow-up work: grader-01's phases B–F (TODO.md § Now); the
  eval-integrity gate gains `case.toml` and shared-prompt checks.
- Revisit when cases need graded outcomes beyond fix or escalate, when
  reports need grading after all, or when a deterministic same-target
  check replaces most judge calls (the v1 list in the design).
