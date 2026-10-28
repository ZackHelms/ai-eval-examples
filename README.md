# ai-eval-examples

A library of example AI evaluations. Each eval in `evals/<slug>/` is a task
prompt (`prompt.md`), the inputs the model under test sees (`inputs/`), and
the grading material it must not see: a reference fix and rubric
(`grading/`).

## Setup

Prerequisites:

- **PowerShell 7+** (`pwsh`). This is not the Windows PowerShell 5.1
  (`powershell`) that ships with Windows; get pwsh with
  `winget install Microsoft.PowerShell`.
- **Python 3.12.** On Windows: `winget install Python.Python.3.12`.

From the repo root, in pwsh:

```powershell
.\01-setup-env.ps1        # or dot-source it: . .\01-setup-env.ps1
```

The script:

- creates `.venv\` from Python 3.12 (`.venv\` is git-ignored);
- installs the pinned packages in `requirements.txt`, plus Playwright's Chromium;
- smoke-tests them;
- activates the venv in your session, so your prompt gains a `(.venv)` prefix.

Re-run it at the start of a session or after pulling a change to
`requirements.txt`. When nothing changed it finishes in about 2 seconds.

Options:

- `-h` or `--help` prints the full usage.
- `-Recreate` rebuilds the venv from scratch.
- `-Force` reinstalls the packages.
- `deactivate` (a command, not an option) leaves the venv.

Notes:

- **The venv lives in the repo folder but is never committed.** It contains
  absolute paths and platform-specific binaries, so each machine builds its
  own from `requirements.txt`. To add a package, pin it in
  `requirements.txt` and re-run the script.
- **Playwright's browsers are not in `.venv\`.** They download to a per-user
  cache (`%LOCALAPPDATA%\ms-playwright`) that all venvs share.
- **If pwsh says "running scripts is disabled":** allow local scripts with
  `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. If you downloaded
  the repo as a zip instead of cloning it, also run
  `Unblock-File .\01-setup-env.ps1`.

### bash → pwsh cheat sheet

| bash | pwsh |
|---|---|
| `source .venv/bin/activate` | `.\.venv\Scripts\Activate.ps1` (the setup script does this) |
| `source script.sh` / `. script.sh` | `. .\script.ps1` ("dot-sourcing") |
| `./script.sh` runs in a child process | `.\script.ps1` runs in *your* process, so `$env:` changes persist |
| `python3` | `python` inside the venv; `py -3.12` (Windows launcher) outside it |
| `which python` | `Get-Command python` |
| `export FOO=bar` | `$env:FOO = 'bar'` |
| `echo $?` (exit code) | `$LASTEXITCODE` (`$?` is only a true/false success flag) |
| `set -e` | `$ErrorActionPreference = 'Stop'` (doesn't cover native-exe exit codes) |
| `~/.bashrc` | `$PROFILE` |
