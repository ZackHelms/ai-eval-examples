# Testing Standards

Runner: `<FILL-IN: test/check runner, invoked non-interactively — a single
run, never watch mode>`. Philosophy: every eval becomes reproducible and
checkable; avoid relying solely on manual trial runs.

> **Current reality:** the hard gate is "none yet" — trivially green until
> the toolchain is scaffolded (no tests exist); reports say so, never skip
> silently. Once it lands, a change with tests isn't green until they
> execute and pass via the gate.

## What to test

- **Eval integrity first** — cheap and reliable: every `prompt.md`
  placeholder resolves to an existing path under `inputs/`; nothing in
  `prompt.md`/`inputs/` references `grading/`; required files exist.
- **The eval discriminates:** where feasible, an automated check shows the
  original input fails and the reference fix passes against the same
  target.
- Repo tooling (setup, capture scripts) gets tests for its logic; the
  browser/load-runner layer gets thin or no tests.
- Write validation **before or alongside** implementation, not after.

## How to test

- Checks must not hit third-party sites at load; multi-user checks run
  against the local target only.
- Pin anything non-deterministic you can (browser version, seeded data,
  fixed iteration counts); assert on outcomes, not timings.
- Test behavior and edge cases (missing input, wrong path, empty trace),
  not implementation details.

One behavior per test, descriptive names. Tests live beside their subject,
or under `<FILL-IN: this repo's test directory>`. A change is not done
until the validation procedure passes — and the report says explicitly if
tests were not executed.
