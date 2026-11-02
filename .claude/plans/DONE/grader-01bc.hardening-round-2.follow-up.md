# grader-01bc follow-up — rubric v1, the red-team rulings, and regrade

Oversee run of `grader-01bc.hardening-round-2.md`, 2026-11-02, started by
`/zmh-producer:backlog-burndown` (run 1 of 2). All 7 tasks and the 5 live
steps are done; every task passed first time.

## Blocked — needs you

Nothing.

## Decisions made on your behalf — review

1. **`changed-page` covers any script or markup run in the page**, as the
   plan's decision default said. That's broader than your ruling ("a
   `page.evaluate` that rewrites the page under test"): an honest fix that
   only reads the page with `evaluate` also scores zero. The grader can't
   read the JavaScript, and no reference uses any of the 9 names. To narrow
   it, write a `rubric-v2.md`.
2. **Two older tests used `delay` as filler data** inside a `**{…}` option
   dict (`test_double_star_dict_display_with_other_keys_and_an_assertion_limit`
   and `test_double_star_dict_call_that_may_hold_more_is_opaque`). Under v1,
   `delay=5` is a sleep, so the filler key is now `speed`. Both tests keep
   their expectations; the tests' meaning is unchanged.
3. **One existing test expectation moved:** `test_run_help_lists_its_options`
   asserted the subcommand list. It now includes `regrade`, as the plan's
   CLI section requires.
4. **Regrade's output details the plan left open:** the run list in the
   header collapses spans of three or more (`1-12`, `1-3,5`); the
   `recorded:` note says `by the judge`, `by the CD`, or both, from each
   judge entry's `by` field.
5. **Preflight:** one cosmetic drift. `_DETECTORS` started at
   `detect.py:523`, not :522. Every other anchor and count matched.
6. **The static pre-pass ran once over the whole branch** (`eb001f5..HEAD`,
   44 files), not once per task: pass, 0 blockers, 0 warnings.

## Deferred / discovered follow-ups

- **Still missed by the red-team check (L5):** `zero-uncalled-def` and
  `zero-if-around-helper`, the helper variants. 28 of the 30 saved
  variants are now caught; `judge-slow-mo` is a `sleep` zero and
  `judge-dom-inject` a `changed-page` zero. The helper design is its own
  TODO.md item and is now unblocked.
- **A doubled tag in the findings:** a fix that both reorders steps and
  patches a method lists `changed-journey` twice, once from the journey and
  once from `_patched_methods`. The verdict and the corpus labels (a set
  of tags) aren't affected. Dedup by tag in `static.check_static` if it
  ever matters in a report.
- **`_getattr_callee_name` in `steps.py`** repeats the shape check of
  `ModuleFacts.getattr_name` without its rebinding check, on purpose (not
  substituting is the safe side). Fold the two together if a third caller
  appears.
- The plan's own Follow-ups stand: a `route` that fulfills a fake page;
  regrading from `fixes/` when a trial folder is gone; comparing values,
  not counts; and grader-01bb's open items (red-teaming case 06, fix cases
  after a path divergence, an escalate retarget moved to another gap, the
  POSIX kill path).

No follow-up plan: none of this is self-contained work worth its own run.
