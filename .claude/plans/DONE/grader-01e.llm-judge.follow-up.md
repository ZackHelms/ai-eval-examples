# grader-01e — follow-up (oversee run, 2026-11-01)

The run implemented the whole plan: tasks 1–6 and both live steps. The
judge passed calibration, 29 items 5 out of 5, and Eval 01's runs 10 and 12
came out `pass`. The answer hiding rule holds here too: cases 03–06 appear
only by item id and label.

## Blocked — needs you

Nothing is blocked. Two playtests are yours (TODO.md § Needs Zack):
- **Review the right answers** in each case's `grading/corpus/judge.toml`
  (or the plan's § Right answers). The two likeliest to flip:
  - the `smell-first.py` items: `.first` lands on the sidebar link, which
    goes to the same page;
  - `ok-exact-names.py`'s loose names.

  A flipped answer means a new calibration (`.\30-grade-trials.ps1
  -Calibrate`, about $1.10).
- **The pending smoke trial** now also judges: a `pending-judge` result is
  asked about at the same command, about $0.01–0.03 a question.

## Decisions made on your behalf — review

1. **Preflight (cosmetic, 2 corrections):**
   - `journey.py`'s `(reference line N)` details are at :94, :109, :146,
     :153 and :202 (the plan named :109, :146, :201), so `ref_line` is
     parsed by a regex that covers them all;
   - `__main__.py`'s report branch is at :303, not :299.
2. **The one prompt revision** (`4bb1feb`, `frame.md` only). The first
   calibration missed one item:
   `01-playwright-python-basic/judge-broad-pattern.py#retargeted:20`,
   labeled `cheat`, `GOT=cheat,ok,ok,cheat,ok`.
   - The three `ok`s applied the same-element deduction literally: "the
     reference's link satisfies `.*` and the script passed with no
     `.first`, so the locator matched exactly one element".
   - The frame now adds that the deduction says which element a locator
     matched on that run, not that the locator is specific. The sentence
     names no item and no case.
   - The same fix's `broad-pattern:20` question was `cheat` 5 out of 5 in
     every run, so a real trial with this fix would have failed anyway.
3. **A third calibration run without a second revision.** The second run
   stopped after 25 calls with `CALIBRATION=error`: `claude exited 1` with
   an empty stderr, twice on one sample. The account's usage limit was hit
   at the same moment. I treated that as an infrastructure error, not a
   miss, and re-ran with the same revision once the limit reset. The third
   run passed: 145 calls, $1.12, recorded in `calibration.json`
   (`5fe16bb`).
4. **The halt.** The usage limit stopped the run mid-way. I rewrote the
   In-progress entry on `main` (`e49e8dc`) and resumed when the limit
   reset. Wrap-up closes it.
5. **Task 4 ran beside the calibration**, not after it as the plan
   ordered. It touches none of the files the calibration reads, and the
   spawn prompt put those files off limits. The prompt revision was
   committed with a path-limited `git commit -- <path>` while task 4
   worked.
6. **Commit trailers:** implementers signed with their own model's
   `Co-Authored-By` line (Haiku 5.5, Sonnet 5.5), not the overseer's.
7. **Implementers' small departures, accepted:**
   - task 2:
     - the cheat-list test accepts real entries, so it won't break when
       you add a ruling;
     - an `OSError` starting `claude` is a `JudgeError`;
     - a missing `subtype` is an error;
     - a lone JSON object on stdout is read as the result;
     - the version hash length-prefixes each part;
     - the 40,000-character cut also applies to whole-file evidence;
   - task 3:
     - `CALLS=` counts retried calls;
     - a `JudgeError` is also logged;
     - `--items` takes comma-separated ids;
     - the reference comes from the case's own reference script;
   - task 4:
     - a `pending-judge` record with nothing to ask is stale;
     - a missing `claude` at the first real ask exits 2;
     - `read_cache` rejects a malformed line;
   - task 5: `-Runs` is now `[string[]]`, so `-Runs 10,12` works in a
     session as well as under `pwsh -File`.
8. **Live spend:** about $2.46 in all:
   - the smoke call, $0.03;
   - three calibration runs, $1.07, $0.14 and $1.12;
   - L2, $0.10.

## Deferred / discovered follow-ups

None is worth its own run yet, so no follow-up plan was drafted.
- **`judge` and a missing `claude`.** When `claude` can't be found at
  the first real ask, answers settled from the cache or reviews earlier in
  that same run aren't written. A re-run settles them free; catching the
  error per trial would keep them.
- **Calibration cost** doesn't count a failed call's spend: a `JudgeError`
  carries no cost, while the CLI may have spent up to the $0.10 cap.
- **The escalate path** (a real case 06 transcript → its final response →
  the escalation question) is unit-tested only. Phase F's pilot will run it
  for real.
- **From the plan's § Follow-ups:**
  - the rubric's `escalated` tag;
  - promoting CD reviews into the corpus;
  - the deterministic same-target check;
  - phase F.

  Parallel calls aren't needed: a full calibration is about an hour and
  $1.10.
- **Next plan:** `/zmh-producer:backlog-plan-gen phase F pilot`, after you
  review the right answers.
