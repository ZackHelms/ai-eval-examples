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

Dependencies point one way: `grading/` may reference `inputs/` (a check
runs the reference fix against the same evidence); `prompt.md` and
`inputs/` never reference `grading/`. Shared tooling (env setup, local load
targets, capture scripts) lives outside `evals/` and is referenced, not
copied, by evals — `<FILL-IN: shared-tooling location, decided when the
first shared script lands>`.

## Reproducibility

Fixtures (results files, Playwright traces, logs) are captured from a real
run, never hand-edited. Each eval records how its fixtures were produced
(tool versions, target, user/iteration counts) so they can be regenerated
and so a grader can tell a stale fixture from a real failure. Multi-user
captures run only against a local target (CLAUDE.md § Project pins).

## Learnings

`<FILL-IN: repo-specific learnings as they accumulate — trace capture
quirks, placeholder conventions, answer-leak patterns; each entry:
symptom → root cause → the rule that prevents it.>`

## Decisions

Significant or hard-to-reverse choices get an ADR (`.claude/adr/`); keep the
repository map in sync with reality.
