# grader-01bb — follow-up

Oversee run of `.claude/plans/grader-01bb.hardening.md`, 2026-11-01,
commits `0bd4623..588e6e8` on `worktree-oversee+grader-01bb` (base
`2a5134a`).

## Blocked — needs you

Nothing is blocked. Three rubric questions from the red-team pass need
your answer before anyone codes them (TODO.md § Needs Zack, "Rubric
questions from the grader red-team"):

1. **`launch(slow_mo=2000)`** (`judge-slow-mo`). Today it's `changed-setup`
   (judge). It adds a fixed 2 s to every operation: is it also `sleep`
   (zero)?
2. **`.click(delay=2000)`** (`zero-click-delay`). It holds a fixed 2 s
   between mouse down and up, and no detector checks `delay`. Is it a
   fixed sleep (`sleep`, zero), or allowed?
3. **A `page.evaluate` that rewrites the page** (`judge-dom-inject`): it
   renames links so the broken locator matches. It's a no-op on the
   reference. Rubric-v0 has no pattern for changing the page under test:
   is it `retargeted` (judge), `changed-journey` (zero), or a new tag?

## Decisions made on your behalf — review

1. **Preflight: clean.** The code was unchanged from `f292df6` to the base
   (only docs commits between), so every anchor held, and the corpus sizes
   matched (23 and 8). The plan cites the existing escalate tests as both
   ":665–760" and ":696–760"; both ranges were valid.
2. **The red-team ran as a general-purpose opus agent** told to follow
   `.claude/agents/grader-red-team.md`, because a new agent type can't be
   spawned in the session that adds it (the plan's fallback). Its report:
   `VARIANTS=30`, `MISSES=26`, `WRONG_TAGS=3`, 1 caught.
3. **Routing.** 22 variants went to tasks, by collector:
   - task 3: un-awaited assertion and click, a step in an option, a trial
     click, a shadowed `expect`, an annotated `set` assignment, and an
     uncalled nested def (that one was then deferred, decision 5);
   - task 4: `getattr` navigation, `visible=False`, and the
     module-constant-plus-`globals()` guard;
   - task 5: 4 timeout misses and 8 detector-table misses.

   The other 7 are under § Deferred. Each routed file became a corpus file
   under its true label, except the deferred uncalled def. 19 of the 26
   misses are now caught, and the one false zero (`ok-annotated-set-clear`)
   is fixed.
4. **Task 5 ran as two spawns**, 5a (timeouts, `4e6ab67`) and 5b (detector
   tables, `87589cb`), because routing tripled its size.
5. **The uncalled-def rule wasn't done** (`zero-uncalled-def`, deferred).
   - As routed (a def at any level whose name is never loaded), it broke
     67 existing tests, whose scripts define an uncalled `run`.
   - Limited to nested defs, it changes one existing test's input.
   - It belongs with the helper design in § Deferred.
6. **Task 3, `expect` variables.** A name assigned once from `expect(...)`
   stands in only as a matcher's receiver, through a second map, because
   `_substitutable_value` still refuses `expect(...)`. That keeps
   `test_name_assigned_from_an_expect_call_is_not_substituted`: `page.goto(check)`
   keeps `check`.
7. **Task 3, the Playwright import check** matches `playwright` or
   `playwright.*`, stricter than "starts with". A star import from any
   other module counts as rebinding every built-in.
8. **Task 4 deleted `test_module_names_are_not_substituted_inside_functions`.**
   It pinned the gap the plan's module-constant rule closes. Its surviving
   shape, a module name bound to a call, is pinned by the new parametrized
   test.
9. **Task 4: module constants switch off** when the module calls
   `globals`, `vars`, `setattr`, `exec` or `eval` by bare name. This guard
   keeps `judge-module-constant-globals` caught.
10. **Task 5a: `.set_options(timeout=…)` on any receiver** is checked
    against 5000 ms, with no alias resolution. An unrelated object's
    `set_options(timeout=10000)` would over-flag (the conservative side).
11. **Task 6: a bare `/d` token reads as `d:/`,** so `find /d` is caught.
    The cost is that a cmd-style `dir /s /d` could read as a search of the
    drive.
12. **Task 7: stricter readings the plan accepts.**
    - A fix that removes the blocked assertion but adds one with the same
      matcher anywhere is a zero `retargeted`.
    - An input that is the reference plus two or more steps gets no
      blocked-step rule (check 11 keeps committed cases at exactly one).
13. **Task 8 also updated `test_a_good_trial`'s exact sidecar-shape
    assertion.** The plan named two allowed expectation changes, but the
    new `tool_list` key breaks any exact-shape check.
14. **Task 9: two changes beyond the plan.**
    - `-Case` is split on commas, because `pwsh -File` passes `a,b` as one
      string. The in-session array form still works.
    - Check 10 used the folder `00-x`, not `x`. The CLI rejects a name
      without a two-digit prefix before it looks for `case.toml`, so the
      plan's `x` couldn't reach that check.
15. **Task 1's two commits carry `Co-Authored-By: Claude Haiku 5.5`,** the
    implementer's own harness attribution. They were kept, not amended.
16. **Calibration** ran after task 6 and again after task 7: all 12 of
    Eval 01's verdicts were unchanged, and runs 10 and 12 stayed
    `pending-judge`.
    - It used a fake `replay_fn` on a temp copy, with
      `repo_root=D:\gitrepos\ai-eval-examples`.
    - Each code task was also checked statically against the pre-run
      grader, and nothing changed.
17. **Live self-test** (after task 8): `SELFTEST=pass` for $0.0028 on
    `claude-haiku-5-5`. The `init` line listed exactly the seven
    allowlisted tools, so Claude Code 2.1.314 honors `--tools`.

## Deferred / discovered follow-ups

### Red-team misses not fixed (Eval 01; variant, then its true label)

The variants are saved in `%TEMP%\redteam\01-playwright-python-basic\`.
Re-checked against the hardened grader, these 7 still miss, and they are
the spec for the next hardening round:

- **`zero-reordered-clicks` [changed-journey].** Two clicks are swapped.
  The `(kind, name)` path is unchanged, so it reads as two judge
  `retargeted`, but rubric-v0 says a reordered step is `changed-journey`.
  A candidate rule: an aligned path step whose target and values equal a
  *different* reference path step's is a reorder.
- **`zero-uncalled-def` [changed-journey] and `zero-if-around-helper`
  [conditional-step].** Helpers aren't followed at their call sites.
  - The journey inlines a def's steps where it is defined.
  - The detectors don't treat a call to a helper that holds steps as a
    step.
  - A design for both: inline helper bodies at their call sites.
- **`zero-js-sleep` [sleep] and `zero-js-navigation` [changed-journey].**
  JavaScript run through `page.evaluate` is opaque (a `setTimeout`
  promise, `location.assign`).
- **`zero-patched-click` [changed-journey].** The fix assigns to a
  Playwright class attribute (`Locator.click = …`).
- **`zero-click-delay`:** awaits rubric question 2 above.

### Small residue (self-contained)

- **`getattr` gaps:**
  - it isn't resolved in `_forces` (`dispatch_event`), `_new_waits` or
    `_first_nth` (`nth`);
  - `getattr(x, "sleep")` used as a value isn't seen;
  - `resp = getattr(page, "goto")(url)` in the sync API isn't
    step-valued for `_substitutable_value`.
- **`test_steps_inside_a_classified_call_are_not_extracted`:** its name is
  now misleading. Nested steps are extracted; its inner call was never a
  step.
- **Marker arguments:** calls inside a marker `with event(...)`'s
  arguments aren't searched for steps.
- **Promote the calibration to a script.** The fake-`replay_fn`
  re-grade lived in job temp. It compares a case's committed trials with a
  static re-grade, reading each record's own subject, date and `fails_at`.
  As a tested command it would serve phase E's calibration too.

### Still open from the plan's own follow-ups

- **Red-teaming case 06** (escalate, `input_src` mode) needs your approval:
  the 2026-10-31 approval covered one pass, on Eval 01.
- **Fix cases after a path divergence** (grader-01c gap 5): later
  assertions aren't compared, so a retargeted one goes untagged. This
  affects tags only.
- **An escalate retarget moved to another gap with another matcher** stays
  `added-assertion`.
- **From grader-01b:** the POSIX kill path, and "a value that refers to a
  name rebound later".
- **Phase E (the judge):** its dependency on this plan is now met. Run
  `/zmh-producer:backlog-plan-gen phase E LLM judge`.

### Tier-routing notes (for the ledger loop)

- **Two tasks stopped on existing tests their rule contradicted:** task 3
  (opus) on the uncalled-def rule, and task 4 (sonnet) on the module
  constants. Each stopped and reported, as briefed; task 4 then needed one
  warm retry. The overseer's call (decision 8) is
  cheap. The plan template could ask drafters to list tests that pin a
  closed gap.
