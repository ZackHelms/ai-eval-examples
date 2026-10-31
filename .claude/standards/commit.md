# Commit Standards

Use **Conventional Commits**:

```
<type>(<optional scope>): <imperative summary>

<optional body: what & why, not how>
```

## Types

`feat` · `fix` · `refactor` · `test` · `docs` · `chore` · `build` · `ci` ·
`perf` · `style`

## Scopes (suggested)

`repo`, `claude`, `scripts`, `evals`, or an eval slug for a change confined
to one eval (e.g. `feat(playwright-basic-debug): add rubric`).

## Rules

- Imperative mood ("add", not "added"). Summary ≤ ~72 chars.
- One logical change per commit; keep commits small and reviewable.
- Run the project validation procedure (hard gate:
  `.\.venv\Scripts\python.exe -m pytest`) before committing — don't
  commit red. **Check the real exit code**, read **immediately after**
  the gating command: a pipeline reports the *last* command's status, not
  the gate's — run gates unpiped, or capture to a log and test
  `$LASTEXITCODE` before committing.
- **Public repo:** before committing, check the staged diff and the
  message for names that must stay out (CLAUDE.md § Project pins: generic
  content only). A pushed leak can't be fully unpublished: after a history
  rewrite, GitHub still serves the old commits by SHA and lists them in the
  repo's Activity log. Only deleting the repo, or a GitHub Support request,
  removes them.
- Never stage with a blanket `add -A`/`add .` — stage named files, and
  review `git status`/`git diff --cached` before committing.
- Reference an ADR when a commit implements a recorded decision.

## Branching & push policy (SOP)

**`direct-merge-push`:** commit *and push* directly to the default branch —
no PRs, ever. Carve-out: oversee runs isolate in a worktree
(`worktree-oversee+<slug>`) for validation, then merge into the default
branch and push at wrap-up — still no PR.

## Examples

```
feat(<eval-slug>): add <eval or eval part>
fix(scripts): correct <bug>
docs(adr): record <decision> (ADR-NNNN)
chore(repo): scaffold <toolchain> per ADR-NNNN
```
