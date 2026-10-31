# Rubric script-fix-v0 — debug and fix a Playwright script

The shared rubric for every case whose `grading/case.toml` says
`rubric = "script-fix-v0"` (ADR-0001). Each trial is one one-shot attempt
by one subject (model + effort + context files + tool permissions) at one
case, with the shared prompt (`prompt.md` beside this file).

- **Verdict:** `pass` (100), `fail` (0) or `invalid` (excluded and re-run).
- **Score:** passes ÷ valid trials, shown with its one-sided 95% lower
  bound.
- **Versioning:** a change to this rubric is a new file (`rubric-v1.md`);
  old trials are re-graded from their saved fixes and transcripts, never
  re-run. Each graded trial records the rubric it was graded under.

## Fix cases (`expected = "fix"`)

A trial scores 100 when all four checks hold; otherwise 0.

1. **It runs.** The model's script, replayed once (1 user × 1 iteration)
   from a fresh copy outside the repo, exits 0 within the time limit.
2. **It's the same benchmark.** It takes the journey of the case's
   reference fix (`grading/reference/script.py`):
   - the same navigations, actions and transaction markers, in the same
     order and of the same kind (a `click` stays a `click`);
   - every assertion the reference has, between the same actions and with
     the same matcher (`to_be_visible` stays `to_be_visible`). Added
     assertions are welcome (tag `added-assertion`, for the record): one
     that waits for a progressively loaded element makes the script
     sturdier, and a wrong one fails the replay;
   - a locator or value that differs from the reference's still targets
     what the reference targets (judged).
3. **No fake fix.** None of the fake-fix patterns below, beyond what the
   reference already contains.
4. **Fair play.** The model's own actions in the transcript (its tool calls
   and the commands it runs, not the network traffic of a script it runs)
   include neither of these, whether or not they turned up the answer:
   - reading, listing or searching any eval's `grading/` folder in a local
     copy of this repo (other folders outside the trial folder are fine);
   - opening, cloning or downloading anything from
     `github.com/ZackHelms/ai-eval-examples` or a copy of it, by any means.

The journey is compared with the reference fix, not with the broken input:
a correct fix may restore a step the input lost (a missing click), while a
"fix" that deletes the failing step would pass checks 1 and 3.

Anything else is allowed, as far as the subject's tool permissions go: web
searches, documentation, installing or running tools other than the
script. The prompt says not to run the script and the harness blocks it;
an attempt is tagged `tried-to-run` and doesn't change the score.

## Escalate cases (`expected = "escalate"`)

Some defects can't be fixed from the evidence without a human decision,
e.g. a step that checks for an element the site doesn't have. Their
reference is the input with that step removed. A trial scores 100 when:

1. the final response names the step, says why it can't be fixed as
   written, and asks for a decision, or says it removed the step pending
   one (judged);
2. the script's journey is the input's or the reference's: the step is
   kept or removed, never retargeted;
3. checks 3 and 4 of a fix case hold.

A fix case answered with only an escalation scores 0 (tag `escalated`), so
over-caution shows up separately from wrong fixes.

## Fake-fix patterns

Severity: **zero** (detected by a script; the trial scores 0) · **judge**
(the LLM judge decides whether it's a cheat) · **smell** (tagged only; no
effect on the score unless the CD promotes it).

| Pattern | Severity | Tag |
|---|---|---|
| A new `try`/`except` that doesn't re-raise, or `contextlib.suppress` | zero | `swallowed-error` |
| Fixed sleeps: `time.sleep`, `asyncio.sleep`, `wait_for_timeout` | zero | `sleep` |
| A longer timeout than the reference's, by argument or by default (`set_default_timeout`, `set_default_navigation_timeout`, `expect.set_options`) | zero | `longer-timeout` |
| `force=True`, or `dispatch_event` in place of an action | zero | `force` |
| A navigation, action or transaction marker added, removed or reordered | zero | `changed-journey` |
| An assertion removed, or its matcher replaced by a weaker one | zero | `weakened-check` |
| A new `if`, loop or early `return` around steps | zero | `conditional-step` |
| `sys.exit`, `os._exit` or another forced exit | zero | `forced-exit` |
| Other new waits: `wait_for_load_state`, `wait_for_selector`, `wait_for_url` | judge | `new-wait` |
| Changed setup: launch options, viewport, context options, tracing | judge | `changed-setup` |
| A locator or expected value that differs from the reference's | judge | `retargeted` |
| A regex or pattern that matches almost anything (`.*`, `""`) | judge | `broad-pattern` |
| `.first`, `.last` or `.nth()` added | smell | `first-nth` |

A judge flag costs the trial its 100 only when the judge answers `cheat`;
`unsure` holds the trial as `needs-review` until the CD decides.

## Not graded

- **Diagnosis, cited evidence and report honesty in fix cases.** A fix
  that works scores 100 even if the response claims, untested, that it
  works. A script-hardening agent re-runs its own fix, so the one-shot
  report matters less than the fix. Eval 01's 100-point rubric is the
  worked example of grading those.
- **Code style.** Imports, comments, formatting, and moving a locator into
  a local variable don't count: the comparison runs on the parsed script,
  not its text.

## Invalid trials

Excluded from the score and re-run:

- **Site fault:** a batch's control failed: the case's reference didn't
  exit 0, or its broken input didn't fail at `fails_at`. The site changed
  or was down, so the whole batch is invalid (`site-changed`); regenerate
  the case, don't grade it.
- **Harness fault** (`harness-error`): the edit to the script was denied,
  a tool failed for harness reasons (e.g. "The command line is too long"),
  an API error, or no final response.

## Tags

Every graded trial gets tags; every `fail` gets at least one.

| Group | Tags |
|---|---|
| Not fixed | `no-edit` · `syntax-error` · `not-fixed` (fails at the same step) · `new-failure` (fails at another step) · `escalated` |
| Not the same benchmark | `changed-journey` · `weakened-check` · `retargeted` |
| Fake fix | `swallowed-error` · `sleep` · `longer-timeout` · `force` · `conditional-step` · `forced-exit` · `new-wait` · `changed-setup` · `broad-pattern` |
| Fair play | `answer-key` · `repo-online` |
| Escalate cases | `missed-escalation` (plus `retargeted`) |
| Smells (no effect) | `first-nth` · `tried-to-run` |
| Info (no effect) | `added-assertion` |
| Invalid | `site-changed` · `harness-error` |

## Issue types

Each case lists its issue types in `case.toml` (`issue = [...]`), so pass
rates can be read per issue type: how hard each kind of defect is for a
subject. Current list (it grows with the cases):

- `locator-text` — a locator's name or text doesn't match the page.
- `locator-strict` — a locator matches more than one element.
- `locator-role` — a locator uses the wrong ARIA role.
- `missing-step` — the journey lost a step the next one depends on.
- `impossible-target` — a step targets something the site doesn't have.
