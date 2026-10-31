# DONE — completed-work log

Append-only, newest first (see `.claude/standards/documentation.md`).

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
