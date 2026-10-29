# ai-eval-examples

A library of example AI evaluations. Each eval in `evals/<slug>/` is a task
prompt (`prompt.md`), the inputs the model under test sees (`inputs/`), and
the grading material it must not see: a reference fix and rubric
(`grading/`).

## Setup

- **PowerShell 7+** (`pwsh`)
  - Not `powershell` 5.1 that ships with Windows
  - Check version with `$PSVersionTable`
  - Get `pwsh` with `winget install Microsoft.PowerShell`
- **Python 3.12.**
  - On Windows: `winget install Python.Python.3.12`
- `.\01-setup-env.ps1 --help` to see what it does before running it
- `.\01-setup-env.ps1`


## Record, Replay, Create Eval
First one I want to do by hand before asking CC to make more, so I know what is going on.
```pwsh
# mkdir -p recordings > /dev/null
New-Item -ItemType Directory -Force recordings | Out-Null

playwright codegen --target python-async --viewport-size "1280,720" -o recordings\script01.py https://playwright.dev/python/

# Add pwtrace capture starting after browser.new_context() and ending prior to context.close()
# await context.tracing.start(screenshots=True, snapshots=True, sources=True)
# await context.tracing.stop(path="playwright-dev.pwtrace.zip")

# replay
python recordings\script01.py
$LASTEXITCODE

# break it
cp recordings\script01.py recordings\script02.py
python recordings\script02.py
$LASTEXITCODE

# Create eval folder and move scripts
# Eval folder name describes the task not the bug (so we dont give the answer away)
$eval = 'evals\01-playwright-python-basic'
New-Item -ItemType Directory -Force "$eval\inputs", "$eval\grading\reference" | Out-Null
git mv recordings\script02.py "$eval\inputs\script.py"               # broken copy: the model sees this
git mv recordings\script01.py "$eval\grading\reference\script.py"    # working copy: the answer key
Remove-Item recordings -Recurse   # only the two old traces are left; step 2 makes new ones
# Capture results
python "$eval\inputs\script.py" *> "$eval\inputs\results.txt"
"exit code: $LASTEXITCODE" | Add-Content "$eval\inputs\results.txt"

# ? Should I keep the answer key in a separate location or repo ?
# PROMPT:   debug and fix inputs\script.py which failed and produced inputs\results.txt & inputs\script.pwtrace.zip
# Improved: Debug and fix inputs/script.py. It failed when run: its console output and exit code are in inputs/results.txt, and the Playwright trace of that run is inputs/script.pwtrace.zip.



```





## Misc

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

