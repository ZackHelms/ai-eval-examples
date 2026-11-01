# Repo scripts

Deterministic tooling for the repo. Each script's own help text is the
detailed reference; this page says what each one is for and how to call it.

## `check-private-names.ps1`

Checks that no private name (see CLAUDE.md, Project pins, "Generic content
only") reaches a commit.

- **Before each commit:**
  `.claude\scripts\check-private-names.ps1 -Message "<message>"` checks the
  staged change, the staged paths and the message.
- **Full sweep:** `.claude\scripts\check-private-names.ps1 -All` also checks
  every tracked file and path and the whole history.
- **Exit codes:** 0 clean, 1 at least one hit, 2 usage or setup error (for
  example no list).
- **Output:** a hit prints its list number (`name #<n>`), never the name.
  A path that contains a name is shown with that part masked as `<#n>`.
- **The list:** a gitignored, untracked `.claude/private-names.local.txt` in
  the main checkout. The script finds it from any `git worktree` too.
- **Usage:** `-h` prints the full usage.

## `oversee-ledger-summary.mjs`

A verbatim zmh-producer plugin seed. It summarizes the oversee outcome
ledger, `.claude/metrics/oversee-ledger.jsonl`, as a table by category and
model (first-pass rate, retries, escalations, overseer fixes).

```
node .claude/scripts/oversee-ledger-summary.mjs [ledger-path]
```

The header comment in the script documents the row schema.
