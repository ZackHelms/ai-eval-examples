# DONE — completed-work log

Append-only, newest first (see `.claude/standards/documentation.md`).

- **2026-10-31** — Private-names check (oversee run of
  `.claude/plans/DONE/privnames-01.check-script.md`):
  - `.claude/scripts/check-private-names.ps1 -Message "<msg>"` checks the
    staged change, the staged paths and the message. Add `-All` to also
    sweep every tracked file and the whole history. Names come from a
    gitignored local list (`.claude/*.local.*`), and hits print a list
    number, never the name.
  - It replaces the hand greps before each commit (`commit.md` § Rules),
    and works from oversee worktrees.
  - 23 pytest tests (460 in the gate). `-All` on the repo is clean.
  - The task-scoping skill's per-tier failure modes are seeded, starting
    with sonnet on pwsh scripts.

- **2026-10-31** — Refine pass after grader-01b:
  - a new skill, `.claude/skills/scriptfix-grader.md` (how the grader
    decides, and how to extend it);
  - an LF line-endings test in the pytest gate;
  - the oversee worktree gotchas, in `plan-oversee-cycle.md`;
  - the producer config's setup quirk filled in;
  - an AGENT-OPP stub for a grader red-team.
- **2026-10-31** — grader-01 phase B, the deterministic grader (oversee
  run of `.claude/plans/DONE/grader-01b.deterministic-grader.md`):
  - `tools/scriptfix/` (standard library only) grades script-fix trials
    under rubric `script-fix-v0`: transcript validity and fair play, a
    journey comparison, fake-fix detectors, one replay per distinct fix
    between control replays, and a record in `grading/trials.jsonl` plus
    `grading/fixes/`. Trials that need the judge come out as
    `pending-judge`.
  - `30-grade-trials.ps1` wraps it.
  - pytest 9.2.0 is the hard gate: 432 tests, including Eval 01's
    23-file labeled corpus.
  - Calibration on Eval 01's 12 trials matched exactly in 14 replays:
    runs 4 and 11 pass, 1–3 and 5–6 fail, 10 and 12 wait on the judge,
    and 7–9 are invalid.
- **2026-10-31** — Generic-content pin (CLAUDE.md § Project pins, the
  CD's rule): no real product names, product docs, copied UI or
  work-internal names in this public repo. The test-site element inventory
  landed in `.claude/notes/` under it. The Locust eval lost its "02" so
  it doesn't clash with grader-01's cases. Refine pass:
  `.claude/skills/trial-runs.md` (headless launch, launcher gotchas,
  transcript formats, replays), `.claude/notes/20261031-trial-statistics.md`,
  architecture learnings, a public-repo rule in `commit.md`, and the
  Playtest SOP and trial-run loop filled in.
- **2026-10-30** — grader-01 design approved and phase A done: the CD's
  global-rubric idea became `.claude/plans/grader-01.global-rubric-design.md`
  (binary rubric with fix and escalate cases, fake-fix severities, tags,
  grader pipeline, case template, trial stages and their statistics, a
  pilot on Eval 01 plus five cases). The CD took all nine decisions as
  recommended, except that added assertions are welcome rather than a
  smell. Phase A: ADR-0001, `rubrics/script-fix/rubric-v0.md` + `prompt.md`,
  shared-tooling location and eval-name prefix settled in the standards.
  The local test site joined the backlog, absorbing the local load target.
- **2026-10-30** — Eval 01, `evals/01-playwright-python-basic/`, built by
  hand with the CD to learn the process: codegen recording, a `»`/`«` →
  `>`/`<` break in two link names, prompt, rubric, reference fix, and 12
  trial runs in `grading/trials.md` (Haiku 4.5 typically 45: misses the
  second link and never verifies; Haiku 5.5 100 in 3 of 3). Runs 3+ ran
  headless with `claude -p`. Follow-ups in TODO.md: capture from a neutral
  folder, integrity gate, trial runner, isolation, global rubric.
- **2026-10-28** — Env prerequisites script: `01-setup-env.ps1`
  (run or dot-source) idempotently creates `.venv/` from Python 3.12,
  installs `requirements.txt` (`playwright==1.64.1`) and Chromium,
  smoke-tests a headless launch, and activates the venv; README setup
  section + bash→pwsh cheat sheet. Locust/locust-plugins deferred to the
  level-set.
- **2026-10-28** — Repo bootstrapped by `/zmh-producer:studio-init` from
  the `zmh-producer` plugin's scaffold seed tree, adapted from game-studio
  to eval-library framing (eval anatomy, answer-hiding rule, load-test
  safety pin).
