# Architecture Standards

## The one rule that matters

**Every eval is self-contained and answer-hidden: it lives in
`evals/<slug>/` as `prompt.md` + `inputs/` (everything the model under test
sees) + `grading/` (reference fix + rubric — never inside `inputs/`), and
every placeholder in the prompt resolves to a path under `inputs/`.** An
eval can be copied out of the repo on its own and still run; handing a
model `prompt.md` + `inputs/` gives it everything needed to attempt the
task and nothing that gives the answer away.

```
evals/<slug>/
  prompt.md      task text; $placeholders name paths under inputs/
  inputs/        the broken artifact(s) + evidence (results, traces, logs)
  grading/       reference fix + rubric (+ any automated check)
```

A `grading/` holds either its own `rubric.md` (Eval 01) or a `case.toml`
naming a shared rubric under `rubrics/`, e.g. `script-fix-v0`
(ADR-0001, which lists the rest of a script-fix case's files).

Dependencies point one way: `grading/` may reference `inputs/` (a check
runs the reference fix against the same evidence); `prompt.md` and
`inputs/` never reference `grading/`. Shared tooling (env setup, local load
targets, capture scripts) lives outside `evals/` and is referenced, not
copied, by evals: Python packages under `tools/` (tests in
`tools/tests/`), CD-facing entry points as numbered pwsh scripts at the
repo root, shared rubrics and prompts under `rubrics/` (ADR-0001).

## Reproducibility

Fixtures (results files, Playwright traces, logs) are captured from a real
run, never hand-edited. Each eval records how its fixtures were produced
(tool versions, target, user/iteration counts) so they can be regenerated
and so a grader can tell a stale fixture from a real failure. Multi-user
captures run only against a local target (CLAUDE.md § Project pins).

## Learnings

Each entry: symptom → root cause → the rule that prevents it. Add new ones
as they're learned.

- **Corrupted evidence.** Eval 01's first `results.txt` showed `╗`/`½`
  where the page had `»`/`«`, and a model copied them into its fix →
  Python wrote cp1252 and the pwsh console decoded it as cp437 → capture
  with forced UTF-8 (`python -X utf8`), never by redirecting console
  output.
- **Evidence that points at the answer key.** The tracebacks in Eval 01's
  `results.txt` name the repo path (the eval's `inputs\script.py`, the
  repo's `.venv`), and trial run 10 followed one → the evidence was
  captured inside the repo → capture from a neutral folder outside the
  repo, with its own venv, and run trials outside the repo.
- **A defect hidden behind the first.** Eval 01's second broken link
  (line 20) never ran, because the run stopped at line 18, so no evidence
  showed it, and most models missed it → one visible defect per case: cut
  the script after the failing transaction, then capture (ADR-0001's case
  contract).

## Decisions

Significant or hard-to-reverse choices get an ADR (`.claude/adr/`); keep the
repository map in sync with reality.
