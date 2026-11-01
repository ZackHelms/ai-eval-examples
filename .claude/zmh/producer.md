# zmh-producer config — ai-eval-examples

## Environment
- Shell: pwsh (PowerShell 7)
- Working tree: `D:\gitrepos\ai-eval-examples`
- Setup quirks: run `.\01-setup-env.ps1` in a fresh oversee worktree before
  the gate. It builds that worktree's own `.venv` from `requirements.txt`;
  the Playwright browsers are shared per user. The gate calls
  `.\.venv\Scripts\python.exe` directly, so no activation is needed.

## Backlog (TODO.md)
- Buckets, in file order: In progress · Now · Needs Zack · Next · Later ·
  Icebox
- Needs-Zack bucket name(s): `## Needs Zack`
- Icebox bucket: Icebox
- In-progress SOP: yes, ≤1 entry
- Done log: DONE.md

## Plans
- Plans dir: `.claude/plans/` (archive: `.claude/plans/DONE/`)
- Plan template: `.claude/templates/plan.md`
- Task-scoping skill: `.claude/skills/task-scoping.md`
- Metrics ledger: `.claude/metrics/oversee-ledger.jsonl`

## Validation
- Procedure: CLAUDE.md § Validation
- Hard gate command: `.\.venv\Scripts\python.exe -m pytest`

## Integration (oversee wrap-up)
- Mode: direct-merge-push
- Detail: CLAUDE.md § Git SOP

## Publish
- Step: none
- Authorization: n/a (no publish step)

## Reporting
- Handoff convention: default (two-line `/compact` ending)
