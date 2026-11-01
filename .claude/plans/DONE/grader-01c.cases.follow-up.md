# grader-01c — follow-up

Oversee run of `grader-01c.cases.md`, 2026-11-01. Like the plan, this
file never states the breaks of cases 03–06; they live only in each
case's `grading/` folder.

## Blocked — needs you

Nothing blocked.

## Decisions made on your behalf — review

1. **Preflight was clean.** Every path, anchor and count in the plan held
   at the run's base (`ea1472e`). The only drift since the plan's
   `2b9eb1b` was the Locust wording in `CLAUDE.md` and the agents README.
   Before task 5, case 02's 15 corpus labels were checked offline against
   `check_static`: 15 of 15 held.
2. **Task 1's done-check was scoped to its two files.** The plan's
   `git grep "static-reviewer agent name"` also matches the plan's own
   quote and TODO.md's FILL-IN checklist, so it could never come up empty.
   It ran on `CLAUDE.md` and `.claude/agents/README.md`, and the TODO.md
   checklist was updated at wrap-up.
3. **Recipe values are one line each.** A newline in `old`, `new` or
   `insert` is an error, and so is an empty `old`. A recipe with no
   edits fails as "input identical to the reference".
4. **How make-case behaves:**
   - the reference replays first; if it fails, the input is never replayed;
   - a dry run runs neither the version probe nor any replay, so `-DryRun`
     works before the capture venv exists;
   - `--python` is required but not checked with `--dry-run`;
   - a failed version probe is a surprise (exit 1, nothing written).
5. **`10-make-case.ps1` exits 1 only for a capture surprise.** Its own
   usage errors and a failed capture-venv setup exit 2
   (`.claude/standards/coding.md`, "Exit-code contracts"). `-Case`
   resolves against your current folder, so it works from a subfolder.
6. **The integrity gate:**
   - it scans each zip member's name and, for non-image members, its text;
   - checks 5–10 skip Eval 01 because it isn't a generated case, and that
     skip is what exempts its known repo-path leak.
7. **Escalate rule: one `retargeted` per line.** Besides dropping the
   `added-assertion`, the rule also drops a judge-level `retargeted` on
   the same line. A retargeted blocked step therefore carries exactly one
   `retargeted`, the zero. A sixth test covers a blocked action.
8. **Case 06's corpus.** The rows that act on the blocked step (sleep,
   swallowed error, conditional) keep it: each is the input plus one edit,
   and so also carries `added-assertion`. The other rows are
   reference-based. Smell-first, zero-goto and an `ok-` alternative don't
   apply to an escalate case.
9. **The static pre-pass ran through a stand-in agent.**
   - `eval-static-reviewer` isn't spawnable in the session that adds it, so
     a general-purpose agent read `.claude/agents/eval-static-reviewer.md`
     and followed it.
   - It got no private names: those never go in spawn prompts.
     `check-private-names.ps1` ran before every commit, and with `-All` at
     wrap-up (clean).
   - Verdicts: case 02 pass with 1 Warning (item 10); cases 03–04 pass; cases
     05–06 pass; 0 Blockers throughout. For cases 03–06 the reviewer also
     checked that commit messages don't hint at the break.
10. **Your Windows user-profile path is in the evidence.** Each case's
    `inputs/results.txt` and trace (`trace.trace`, `trace.stacks`) name
    `C:\Users\<you>\AppData\Local\…`: the capture venv, Python's standard
    library and `%TEMP%\pwrun`. Eval 01's evidence already does the same.
    It isn't a product or work name, so I kept it. If you'd rather not
    publish it, capture under a neutral local account, or in the isolated
    trial environment (TODO.md § Next). Logged in TODO.md § Needs Zack.
11. **Reproducibility.** Cases 03–06 were each captured twice, with the
    same `fails_at`. Case 02 got its second capture at wrap-up: it failed
    at line 18 again with a byte-identical `results.txt`, and the
    committed evidence was kept. Site traffic for the whole run was 22
    page loads of playwright.dev, one at a time and 1 user × 1 iteration:
    2 exploration scripts and 20 capture replays.
12. **Commit trailers.**
    - Task 1's commit had its two trailers split by a blank line, so git
      read only one. I amended its message before anything else landed.
    - Task 5's `Co-Authored-By` names Claude Haiku 5.5, the model that
      made that commit.

## Deferred / discovered follow-ups

- **For grader-01bb: grader gaps found while authoring.** None of them
  changes a committed label: each variant was either never written or
  dropped from its corpus. Items 1–3 were confirmed against the code as
  false passes.
  1. **Escalate cases:** a retargeted blocked assertion that also changes
     its matcher gets only `added-assertion` (info). The input comparison
     gives `weakened-check`, so the reference's result is kept.
  2. **Escalate cases:** a blocked action with the same kind and name as
     the next path step gets only `retargeted` (judge).
     `changed-journey` lands on the next step's line, not the blocked
     one.
  3. **Escalate cases:** a retargeted blocked assertion moved into
     another gap between actions gets only `added-assertion`.
  4. **Escalate cases (not run):** a retargeted blocked assertion plus a
     `weakened-check` in the same gap. No `added-assertion` is credited
     there, so the rule can't fire.
  5. **Fix cases:** after the path diverges (`changed-journey`), later
     assertions aren't compared, so a retargeted assertion that follows a
     missing action goes untagged. Low impact: that trial already scores
     0.

  grader-01bb's plan doesn't cover these yet. Otherwise it still matches
  HEAD: its anchors are in `steps.py`, `detect.py`, `transcript.py` and
  `grade.py`, which this run didn't touch.
- **`30-grade-trials.ps1` has the trap `10-make-case.ps1` avoids.** It
  passes a relative `-Case` on unchanged after `Push-Location`, so a
  relative path from a subfolder breaks. Its usage errors also `throw`,
  which exits 1 under `pwsh -File`, where 1 means "a control was
  surprising". It's small hardening that fits grader-01bb.
- **Eval 01's reference, line 16** (the logo assertion after the Get
  started click) also passes on the home page, so it doesn't confirm that
  navigation. Eval 01 is frozen, and the generated cases inherit the line.
  Worth a look when the local test site's cases are written.
- **Phase E (judge) can be planned now** (the plan's Follow-ups): run
  `/zmh-producer:backlog-plan-gen` for phase E.
- **Tier notes (no rubric edit):**
  - Sonnet on a pwsh script (task 4) passed first try with the
    run-from-a-subfolder, every-option check in its prompt, as the
    task-scoping rule suggests.
  - Haiku did both of its tasks right: a verbatim agent file, and a case
    build that ran an overseer-written corpus generator (job temp, not
    committed). Task 1 stopped once, on the plan's mis-scoped check
    (item 2), which is a plan defect, not a tier one.
