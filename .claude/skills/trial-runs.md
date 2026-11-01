# Skill: Trial-running an eval (headless Claude Code)

How this repo runs a model on an eval (the Playtest SOP): `20-run-trials.ps1`
does it, and this file is the reasons behind the launcher. Learned on
Eval 01's runs 1–12 (2026-10-29/30, Claude Code 2.1.312–2.1.314).

## Launch

- `.\20-run-trials.ps1 -Case evals\<slug> -Model <id> -Count N` runs N new
  trials. `-Runs 3-5` names runs instead; `-DryRun` prints the plan and
  spends nothing.
- `.\20-run-trials.ps1 -SelfTest` is the cheap harness check (gotcha 4).
- Each trial leaves `<NN>-run<N>.stream.jsonl`, `<NN>-run<N>.stderr.txt` and
  `<NN>-run<N>.subject.json` (the sidecar: model, effort, context, tools)
  beside its folder. The grader reads the sidecar.
- It never overwrites a trial: `-Runs` naming an existing one is a usage
  error, and `-Count` starts after the highest run found.
- The first harness problem stops the batch (a non-zero exit, a timeout, or
  no `result` line): it prints a `HARNESS=` line and exits 1. Every batch
  ends with a `NEXT=.\30-grade-trials.ps1 ...` line that grades it.
- `--permission-mode default` still works on 2.1.314 although `--help` no
  longer lists it; the runner keeps it.

What it runs, for reference: it copies `prompt.md` + `inputs/` to
`~\eval-trials\<NN>-run<N>\` (outside the repo; the folder name carries
only the number), then from that folder:

```pwsh
claude -p "<prompt.md text>" --safe-mode --strict-mcp-config --model <model> `
  --permission-mode default `
  --allowedTools "Edit(//c/Users/<you>/eval-trials/<NN>-run<N>/inputs/script.py)" `
                 "Write(//c/Users/<you>/eval-trials/<NN>-run<N>/inputs/script.py)" `
  --output-format stream-json --verbose > ~\eval-trials\<NN>-run<N>.stream.jsonl
```

Add `--effort <level>` for a non-default effort. In headless mode anything
that needs approval is denied automatically and listed in the result
line's `permission_denials`. Read-only commands inside the trial folder run
without approval. So with these rules the model can read and edit, but
can't run the script or fetch the web: that's the subject's tool profile
(`edit-only`). Record it with the result.

## Making a case

Building a case and capturing its evidence is
`.claude/skills/scriptfix-grader.md` § Extending it. The capture runs in
the neutral folder `%TEMP%\pwrun\` with the capture venv
`%LOCALAPPDATA%\pwrun\venv` (built by `.\01-setup-env.ps1 -VenvDir ...
-NoActivate`, which `10-make-case.ps1` runs), so the evidence (paths in
results and traces) never names the repo.

## Launcher gotchas (each one cost runs)

Each gotcha below is handled by the script.

1. **Use absolute allow rules** (`//c/...`). A relative rule
   (`Edit(./inputs/script.py)`) stops matching once the model runs
   `cd inputs`: Eval 01's runs 7 and 9 were denied their edit.
2. **Strip the parent session's variables** when launching from inside a
   Claude Code session, or the trial starts as its child: everything
   `CLAUDE*`, plus `AI_AGENT`, `NO_COLOR`, `PYTHONIOENCODING`,
   `GIT_ASKPASS`, `GIT_EDITOR`, `GIT_TERMINAL_PROMPT`, `GCM_INTERACTIVE`,
   `COREPACK_ENABLE_AUTO_PIN`, `PSExecutionPolicyPreference`,
   `NoDefaultCurrentDirectoryInExePath` and any plugin-injected variables. The
   runner also strips `ZMH3D_*`, `VIRTUAL_ENV`, `PYTHONPATH` and
   `PYTHONSTARTUP`, and drops `PATH` entries inside the repo (its
   `.venv\Scripts` too) and inside the stripped venv: they name the repo,
   and the trial mustn't see it.
3. **Put the real `pwsh.exe` first on `PATH`:**
   `$env:PATH = (Split-Path (Get-Process -Id $PID).Path) + ';' + $env:PATH`.
   Through the per-user app-execution alias under
   `%LOCALAPPDATA%\Microsoft\WindowsApps\`, Claude Code's PowerShell tool
   fails every command with "The command line is too long" (runs 7–9).
   Stripping variables does **not** fix this; only the `PATH` change does.
   A store install's real `pwsh.exe`, under `C:\Program Files\WindowsApps\`,
   is fine. The runner rejects only the alias, and the wrapper always passes
   `--pwsh (Get-Process -Id $PID).Path`.
4. **Test a changed launcher** with `.\20-run-trials.ps1 -SelfTest` before
   spending trials: one PowerShell command, `cd inputs` + one Bash command,
   one Edit of a dummy file. It prints `SELFTEST=pass` or names what failed.
   The first live run passed with Claude Code 2.1.314 and `claude-haiku-5-5`
   for $0.0025.

## Transcripts

- **stream-json log** (headless): an `init` line (`model`,
  `claude_code_version`, `session_id`) and a `result` line (`is_error`,
  `api_error_status`, `permission_denials`, `result` = the final text,
  `total_cost_usd`).
- **Session transcript** (every run, including interactive ones):
  `~\.claude\projects\<mangled>\<session>.jsonl`, where `<mangled>` is the
  trial folder's absolute path with every non-alphanumeric character
  replaced by `-` (`C:\Users\zmhel\eval-trials\01-run1` →
  `C--Users-zmhel-eval-trials-01-run1`). It has no result line; assistant
  lines carry `message.model`, `version` and `sessionId`.
- Haiku 4.5 and 5.5 leave their thinking blocks empty: grade on the visible
  text and the tool calls.
- **Cost per Eval 01 run:** Haiku 4.5 about $0.08, Haiku 5.5 about $0.01.

## Grading replays

- Grade with `.\30-grade-trials.ps1 -Case evals\<slug> -Runs 3-12` (add
  `-Tools interactive` for interactive runs); `-Report` prints pass rates.
  It replays the reference and the input as controls before and after the
  batch, replays each distinct fix once, and records `grading/trials.jsonl`
  and `grading/fixes/`. If a control fails, it records nothing. Eval 01's
  calibration took 14 replays for 12 runs. `python -m scriptfix` itself
  needs `PYTHONPATH=tools`; the script sets it.
- It replays a copy in `%TEMP%\scriptfix\<hash>\`, never in the repo or the
  trial folder (the script writes its trace next to itself).
- `python -X utf8 script.py`. `python -I` ignores `PYTHONUTF8`, and a
  cp1252 console write crashes on `»`.
- One replay at a time; public sites get single replays only (CLAUDE.md
  § Project pins).
- Eval 01's script launches `headless=False`, so browser windows open.
  Don't change the script to stop them.
- **Windows processes:** capture a replay's output through a file, not a
  pipe: Playwright's driver inherits the parent's stderr, so a leftover
  process can hold a pipe open after the script exits. Kill a timed-out
  replay with `taskkill /T /F /PID`, or its browser outlives it. Never
  probe a Windows process with `os.kill(pid, 0)`: it terminates the
  process instead.

## Windows file gotchas

- Python text mode writes CRLF on Windows, but the repo is LF. Write with
  `newline="\n"` (or repair with `sed -i 's/\r$//'`) and check
  `git diff --stat` for whole-file diffs.
- Capture console output as UTF-8 (`python -X utf8`). Redirecting a cp1252
  write through a cp437 console turned Eval 01's `»`/`«` into `╗`/`½`
  (`.claude/standards/architecture.md` § Learnings).

## How many trials

`.claude/notes/20261031-trial-statistics.md`: what 10 or 100 trials can
and can't prove.
