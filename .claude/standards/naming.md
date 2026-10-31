# Naming Conventions

## Evals

- **Eval folders:** `evals/<slug>/`, kebab-case slug naming the task, e.g.
  `evals/playwright-basic-debug/`, with a two-digit prefix in creation
  order: `evals/01-playwright-python-basic/`. Names describe the task or
  the journey, never the defect (`evals/02-docs-journey-a/`); trial
  folders use the number only (`02-run7`).
- **Inside an eval:** `prompt.md`, `inputs/`, `grading/` (see
  `architecture.md`). Input file names must not leak the answer (no
  `broken_*`, `fixed_*`, `bug_*`).
- **Prompt placeholders:** `$camelCase` names (as in `$somescript`,
  `$somedirectory`), each mapped to one path under `inputs/`.

## Code

- **Python:** PEP 8 — `snake_case` modules/functions/locals, `PascalCase`
  classes, `UPPER_SNAKE` constants.
- **pwsh:** `Verb-Noun` function names with approved verbs; `PascalCase`
  parameters.

## Scripts

CD-runnable scripts (repo root) get a **two-digit run-order prefix**
(`NN-<task>.ps1`, matching pwsh, gaps left for later insertions);
Claude-only automation stays unnumbered under `.claude/scripts/`.

## Branches & commits

`claude/<topic>` branches; oversee runs use `worktree-oversee+<slug>`.
Commits: Conventional Commits (`commit.md`).
