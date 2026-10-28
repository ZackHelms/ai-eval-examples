# Review Standards

Reviews favor long-term health over short-term speed. Many small reviewable
changes beat large ones.

## A change is reviewable when

- The project validation procedure (CLAUDE.md § Validation) is green.
- It does one logical thing, with a clear Conventional Commit message.
- New tooling has tests where feasible (`testing.md`); new evals follow the
  eval anatomy. Docs/ADRs updated if architecture changed.

## What reviewers check

1. **Answer hiding** — nothing in `prompt.md` or `inputs/` reveals the fix
   (comments, file names, leftover reference-fix fragments, git-visible
   history inside `inputs/`); `grading/` is never under `inputs/`
   (`architecture.md`).
2. **Self-containment** — every prompt placeholder resolves under
   `inputs/`; no absolute paths; the eval runs when copied out alone.
3. **Pin compliance** — no load against public sites; `<FILL-IN:
   static-reviewer checklist — Python/Playwright/Locust version and API
   pins once the level-set decides them>`.
4. **Reproducibility** — fixtures are captured, not hand-edited, and say
   how they were produced.
5. **Correctness & edge cases** — the reference fix actually fixes the
   input; the rubric grades the fix, not the wording.
6. **Clarity** — naming, comments explain *why*, matches surrounding style.
7. **Scope** — no unrelated changes; a change to one eval doesn't touch
   another eval's `inputs/` or `grading/`.

## Tone

Be specific and actionable. Distinguish blocking issues from suggestions.
