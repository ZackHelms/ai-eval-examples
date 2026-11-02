# Workflow: Plan → Oversee Cycle

The Creative Director's outer loop for autonomous feature delivery. It sits
*above* any single session: plans are drafted in one step, implemented by
`/zmh-producer:oversee-implementation` in the next, and each run's closing
lines tell the CD exactly what to type next. This file exists so any session
can orient the CD ("what step am I at?") without re-deriving the process.

**Roles.** The overseer is **not** a `.claude/agents/` sub-agent — it is the
main session itself, given the role by `/zmh-producer:oversee-implementation`
(zmh-producer plugin, marketplace `zmhstudio`, configured via
`.claude/zmh/producer.md`). Sub-agents are the tiered implementers the
overseer spawns. The session model is what matters, not session identity:
after `/compact` a resumed session is effectively fresh.
Convention: a top-tier model drafts plans; a high-tier model oversees —
either via two sessions or one session with `/model` switches.

## Inputs

- A feature, bugfix, or "what's next" request from the CD (TODO.md's top
  un-blocked item when they don't specify).

## The cycle

1. **Start clean.** Resume (or open) a session whose last action was
   `/compact` — the planning/overseeing context comes from disk, not the
   transcript.
2. **Draft the plan.** Ask for a plan for the feature (or the next item from
   TODO.md). The session writes it to `.claude/plans/<name>.md` per
   `.claude/templates/plan.md`, adds the TODO.md entry, commits, and ends its
   final message with the two Handoff lines. Per the template's required tier
   audit, score every task against `.claude/skills/task-scoping.md` before
   finalizing. A large feature set may first get a plan-of-plans with plans
   drafted just-in-time, one at a time.
3. **Run it.** `/compact`, then `/zmh-producer:oversee-implementation
   .claude/plans/<name>.md` (on a high/top-tier model — the command gates
   this). The run isolates itself: worktree (branch
   `worktree-oversee+<slug>`, cut fresh from the default branch) → tasks
   execute and commit there → wrap-up integrates per this repo's Integration
   mode (`.claude/zmh/producer.md` § Integration) and, where configured,
   publishes → the worktree is removed on full success (kept for CD
   inspection on an integration failure). See the
   `/zmh-producer:oversee-implementation` command (zmh-producer plugin) for
   the full mechanics. Wait for the final report. It ends one of two ways:
   - a second line naming a drafted follow-up plan
     (`<slug><letter>.<name>.md`) → `/compact`, run that command, return here;
   - `/compact` only, plus a named recommended next plan → the residue went to
     TODO.md/`.follow-up.md`; the letter chain is done.
4. **Playtest when the report says to** (per this repo's Playtest SOP —
   `.claude/zmh/producer.md` § Reporting or CLAUDE.md § Playtest SOP), and
   feed feel verdicts back.
5. **Loop.** Go to step 2 for the recommended next plan, a new feature, a
   bugfix, or "what should we work on next".

## Gotchas (this repo)

Learned on grader-01b's run (2026-10-31):

- **A fresh worktree has no `.venv`.** Run `.\01-setup-env.ps1` in it
  first. It builds that worktree's own venv from `requirements.txt` in
  about a minute; the Playwright browsers are shared per user. After the
  merge, run the script again in the primary checkout if
  `requirements.txt` changed, before its gate run.
- **Worktree isolation refuses compound git commands.** It refuses `for`
  loops, `cd x && git …` and `$(git …)` inside a worktree-isolated
  session. Run git as plain, separate commands, and say so in every spawn
  prompt: implementers hit it too.
- **Integrate from the primary checkout.** Git on the primary checkout is
  refused while the session is in the worktree. Call `ExitWorktree` with
  `keep`, merge and push from the primary checkout, then clean up with
  `git worktree remove .claude/worktrees/<name>` and `git branch -d
  <branch>`.

Learned on privnames-01's run (2026-10-31):

- **Implementers run the private-names check before each commit.** From a
  worktree it reads the main checkout's list. A worktree-isolated session
  can't write files in the primary checkout, so the list must already exist
  there before the run: create it from the primary checkout, untracked.
  Spawn prompts never contain the names, only the instruction to run the
  check (`.claude\scripts\check-private-names.ps1 -Message '<message>'`).

Learned on grader-01c's run (2026-11-01):

- **A new agent type can't be spawned in the session that adds it.**
  Agent definitions load at session start. Spawn a general-purpose agent
  told to read the new `.claude/agents/<name>.md` and follow it; the
  static pre-pass on cases 02–06 ran that way.
- **Commit with one `-m` here-string.** `git commit -F -` gets no stdin in
  these shells. Several `-m` options make separate paragraphs, which
  splits the trailer block, and git then reads only the last trailer.
  Spawn prompts say: one `-m` with a single-quoted here-string, the two
  trailer lines adjacent as the last paragraph. Check with
  `git log -1 --format=%B | git interpret-trailers --parse`.
- **The worktree guard refuses Bash commands that name paths outside the
  worktree**, `$TEMP` included. Write temp scripts with the Write tool and
  run them from PowerShell.
- **A done-check that greps for replaced text must name its files.** The
  plan quotes the text it replaces (and TODO.md checklists may too), so a
  repo-wide `git grep` never comes up empty.
- **Hidden breaks stay out of run docs too.** For cases whose breaks are
  hidden, commit messages, follow-ups and DONE.md say what was added,
  never the break: the history and `.claude/` are readable on the trial
  host.

Learned on grader-01d's run (2026-11-01):

- **Docs edits go through the Edit/Write tools, never a script with
  escapes.** A non-raw Python heredoc turned `.\20-run-trials.ps1` into
  `.` + byte 0x10 + `-run-trials.ps1` (`\20` is an octal escape), and the
  gate can't see it. Review doc diffs with `cat -A`, or run
  `git grep -nP "[\x00-\x08\x0b\x0c\x0e-\x1f]" -- <files>`.
- **Append to a file with the Edit tool in the worktree.** The guard
  refuses `cat >> file <<'EOF'` as too complex to verify, even inside the
  worktree.
- **A live check is the overseer's to run.** The plan's one paid call (the
  launcher self-test) was a single command; the overseer ran it and read
  the log, which saved a spawn.

Learned on grader-01bb's run (2026-11-01):

- **The guard reads "git" anywhere in a compound Bash command.** A pipe or
  `;` plus a path holding the letters, such as the session's
  `…\projects\D--gitrepos-…` results folder, is refused even when no git
  runs. Read such files with the Grep/Read tools, or run the command from
  PowerShell.
- **Re-check grader verdicts after every grader task, not only at the
  end.** Run the case's committed fixes through `check_static` twice: once
  with `PYTHONPATH` on the worktree's `tools`, once on the primary
  checkout's (the pre-run grader). Any difference is a changed verdict,
  found while the task's context is warm. The plan's fake-`replay_fn`
  calibration then confirms it end to end.
- **A test that pins the gap a plan closes.** "No existing test changes its
  expectation" collides with a test asserting the old behavior the plan
  replaces. The plan supersedes it: delete it when a new test pins the
  shape that survives, and log the call. Plan drafters can name such tests
  up front.
- **Route a red-team report by collector, and split a task that grows.**
  The routed misses doubled task 5, so it ran as two spawns (timeouts,
  detector tables), each one commit.

Learned on grader-01e's run (2026-11-01):

- **The guard also refuses a computed argument.** A Python call whose
  argument holds a `$VAR` (e.g. `$CLAUDE_JOB_DIR/tmp/x.py`) is refused as
  "a value computed at runtime"; write the literal path. A `cd <path> && …`
  is refused when the path holds the letters "git". Write scratch scripts
  with the Write tool and run them from the worktree with relative paths.
- **A paid live step can run beside a code task that doesn't touch its
  inputs.** The hour-long calibration ran while task 4's implementer
  worked; the spawn prompt named the files the run reads as off limits.
  When the overseer must commit meanwhile (a prompt revision), use
  `git commit -F <msg> -- <path>`: it commits only that path and leaves the
  implementer's staged and unstaged files alone.
- **A usage limit looks like a call error, not a miss.** When the account
  hits its limit, the nested `claude -p` exits 1 with an empty stderr, so
  calibration stops with `CALIBRATION=error`. It doesn't spend the plan's
  one prompt revision: re-run the calibration after the limit resets. A
  halted run's handoff is the In-progress entry, rewritten on the default
  branch from the primary checkout (`ExitWorktree` keep, then edit, commit
  and push there).

## Required validation

Each overseer run self-gates (the project validation procedure green per task
and at wrap-up — static pre-pass plus the hard gate). The cycle adds one gate
of its own: **the playtest** for anything the report flags as
playtest-affecting — if a run reported red or the playtest fails, resolve
that before starting the next plan.

## Expected artifacts

Per iteration: an implemented plan archived to `.claude/plans/DONE/` with its
`.follow-up.md`, updated TODO.md/DONE.md, the run's commits landed on the
default branch, and per-task ledger rows appended to
`.claude/metrics/oversee-ledger.jsonl` — plus, when residue warranted one,
the next letter-suffixed plan ready to run.

## Completion checklist

None — this loop has no end state; each iteration's gate is the overseer
run's own wrap-up (`/zmh-producer:oversee-implementation` Step 5 —
zmh-producer plugin).
