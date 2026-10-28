# DONE — completed-work log

Append-only, newest first (see `.claude/standards/documentation.md`).

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
