"""The judge's prompts and its one call: what Sonnet is asked, and how its answer is read.

A trial that the static checks left as ``pending-judge`` gets one narrow
question per judge flag, plus the escalation question on an escalate case.
This module turns a flag into a ``Question``, a ``Question`` into a prompt
(a question template inside ``frame.md``, both under
``rubrics/script-fix/judge/``), and a prompt into an ``Answer`` through
``claude -p`` with no tools. Everything before ``ask_claude`` is pure; the
only I/O is reading the judge folder and running ``claude``.

The judge version (``judge_version``) hashes exactly what shapes a prompt:
the format number, the model, the effort, the system prompt, the two facts
lines, the templates and the cheat list's entries. Editing the cheat list's
prose, or the grader's own version, keeps it. Calibration and the verdict
cache are keyed by it, so a prompt change is never silent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scriptfix.case import Case
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.report import REPO_ROOT
from scriptfix.run import session_free_env
from scriptfix.static import EXPECTED_ESCALATE, blocked_step, step_key
from scriptfix.steps import extract_steps

JUDGE_MODEL = "claude-sonnet-5-5"
# Passed as --effort unless it is "default" (the model's own default).
JUDGE_EFFORT = "default"
JUDGE_CALL_BUDGET_USD = "0.10"
JUDGE_TIMEOUT_S = 300
# Bump with any change to how a prompt is put together.
PROMPT_FORMAT = "1"
SYSTEM_PROMPT = (
    "You are the judge for an eval grader. Reply with the single JSON object "
    "the user's message asks for, and nothing else."
)

ANSWERS = ("ok", "cheat", "unsure")
QUESTION_ESCALATION = "escalation"

JUDGE_DIR = REPO_ROOT / "rubrics" / "script-fix" / "judge"
FRAME = "frame.md"
CHEATS = "cheats.md"
# Question template per judge tag (the escalation question has its own key).
TEMPLATES = {
    "retargeted": "same-target.md",
    "broad-pattern": "broad-pattern.md",
    "new-wait": "new-wait.md",
    "changed-setup": "changed-setup.md",
    QUESTION_ESCALATION: "escalation.md",
}

FACTS_FIX = (
    "Facts: the model's script was replayed once on the live site and exited 0, "
    "so every step ran and every assertion passed."
)
FACTS_ESCALATE = (
    "Facts: escalate cases aren't replayed. The model's script passed the static "
    "checks: it keeps the blocked step exactly or removes it, and changes nothing "
    "else that matters."
)

EVIDENCE_LIMIT = 40_000
CONTEXT_ROLES = (
    "heading",
    "banner",
    "navigation",
    "main",
    "complementary",
    "contentinfo",
    "region",
    "search",
)

NO_CHEATS = "- (none yet)"
CUT_MARKER = "[... cut]"
NO_LINE = "(no matching line)"
NO_REF_LINE = "(none)"

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_REFERENCE_LINE = re.compile(r"\(reference line (\d+)\)")
_SNAPSHOT_ROLE = re.compile(r"^\s*- ([a-z]+)\b")
_GET_BY_ROLE = re.compile(r"""get_by_role\(\s*["'](\w+)["']""")


# --------------------------------------------------------------------------
# Templates and the judge version
# --------------------------------------------------------------------------


def render(template: str, values: dict[str, str]) -> str:
    """Fill every ``{{name}}`` of ``template`` from ``values`` in one pass.

    One ``re.sub`` pass, so an inserted value is never scanned again (a value
    that contains ``{{x}}`` stays as it is). Raises ``ValueError`` naming each
    placeholder without a value and each value without a placeholder.
    """
    used = set(_PLACEHOLDER.findall(template))
    missing = sorted(used - set(values))
    unused = sorted(set(values) - used)
    if missing or unused:
        parts = []
        if missing:
            parts.append(f"placeholders without a value: {', '.join(missing)}")
        if unused:
            parts.append(f"values without a placeholder: {', '.join(unused)}")
        raise ValueError("; ".join(parts))
    return _PLACEHOLDER.sub(lambda match: values[match.group(1)], template)


def cheat_entries(text: str) -> list[str]:
    """The lines of the cheat list that start with ``- ``, in order; prose is ignored."""
    return [line for line in text.splitlines() if line.startswith("- ")]


def _read(judge_dir: Path, name: str) -> str:
    return (Path(judge_dir) / name).read_text(encoding="utf-8")


def judge_version(judge_dir: Path = JUDGE_DIR) -> str:
    """The judge's version: ``"j"`` plus 12 hex digits of a SHA-256 over what shapes a prompt.

    In order: ``PROMPT_FORMAT``, ``JUDGE_MODEL``, ``JUDGE_EFFORT``,
    ``SYSTEM_PROMPT``, ``FACTS_FIX`` and ``FACTS_ESCALATE``; the bytes of
    ``frame.md`` and the five question templates in sorted file-name order;
    the cheat entries joined by newlines. Each part is length-prefixed, so
    no two parts can run together. The cheat list's prose and the grader's
    version are not part of it.
    """
    judge_dir = Path(judge_dir)
    parts = [
        PROMPT_FORMAT.encode("utf-8"),
        JUDGE_MODEL.encode("utf-8"),
        JUDGE_EFFORT.encode("utf-8"),
        SYSTEM_PROMPT.encode("utf-8"),
        FACTS_FIX.encode("utf-8"),
        FACTS_ESCALATE.encode("utf-8"),
    ]
    for name in sorted([FRAME, *TEMPLATES.values()]):
        parts.append((judge_dir / name).read_bytes())
    entries = cheat_entries(_read(judge_dir, CHEATS))
    parts.append("\n".join(entries).encode("utf-8"))
    digest = hashlib.sha256()
    for part in parts:
        digest.update(f"{len(part)}:".encode("ascii"))
        digest.update(part)
    return "j" + digest.hexdigest()[:12]


# --------------------------------------------------------------------------
# The evidence and the numbered scripts
# --------------------------------------------------------------------------


def numbered(src: str) -> str:
    """``src`` with each line prefixed ``N: `` from 1."""
    return "\n".join(f"{n}: {line}" for n, line in enumerate(src.splitlines(), start=1))


def evidence_excerpt(results_text: str, role: str | None) -> tuple[str, str]:
    """The part of ``inputs/results.txt`` the judge sees, and a note saying what it is.

    Without an ``Aria snapshot:`` line the whole text comes back. Otherwise
    the excerpt is every line before the snapshot, then (when ``role`` is
    given) ``Aria snapshot:`` and the snapshot lines tagged with ``role`` or
    a ``CONTEXT_ROLES`` role, in order, then the last line when it starts
    with ``exit code:``. Beyond ``EVIDENCE_LIMIT`` characters the excerpt is
    cut, with a marker line, and the note says so.
    """
    lines = results_text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Aria snapshot:")), None)
    if start is None:
        excerpt, note = results_text, "the whole file"
    else:
        kept = lines[:start]
        if role is not None:
            wanted = {role, *CONTEXT_ROLES}
            kept.append(lines[start])
            for line in lines[start + 1 :]:
                match = _SNAPSHOT_ROLE.match(line)
                if match and match.group(1) in wanted:
                    kept.append(line)
            note = (
                f"an excerpt: the error and the call log, then the aria snapshot's {role}, "
                "heading and landmark lines, in document order"
            )
        else:
            note = "an excerpt: the error and the call log; the aria snapshot is left out"
        if lines and lines[-1].startswith("exit code:") and len(lines) - 1 > start:
            kept.append(lines[-1])
        excerpt = "\n".join(kept)
    if len(excerpt) > EVIDENCE_LIMIT:
        excerpt = excerpt[:EVIDENCE_LIMIT] + "\n" + CUT_MARKER
        note += f"; cut at {EVIDENCE_LIMIT} characters"
    return excerpt, note


def role_of(line: str) -> str | None:
    """The role of the first ``get_by_role("...")`` in a source line, or None."""
    match = _GET_BY_ROLE.search(line)
    return match.group(1) if match else None


# --------------------------------------------------------------------------
# Questions
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    """One question for the judge: its id, template file, evidence role and template values."""

    id: str  # "<tag>:<line>" or "escalation"
    tag: str
    line: int  # the fix line, or the blocked step's line in the input
    template: str  # the question template's file name
    role: str | None  # the aria role whose snapshot lines the evidence keeps
    values: dict[str, str]


def _source_line(src: str, number: int) -> str | None:
    lines = src.splitlines()
    return lines[number - 1].strip() if 1 <= number <= len(lines) else None


def _reference_values(reference_src: str, detail: str) -> dict[str, str]:
    """``ref_line`` and ``ref_text`` from a finding detail's ``(reference line N)``."""
    match = _REFERENCE_LINE.search(detail)
    if match is None:
        return {"ref_line": NO_REF_LINE, "ref_text": NO_LINE}
    text = _source_line(reference_src, int(match.group(1)))
    return {"ref_line": match.group(1), "ref_text": text if text is not None else NO_LINE}


def _finding_question(finding: Finding, reference_src: str, fix_src: str) -> Question:
    template = TEMPLATES.get(finding.tag)
    if template is None or finding.tag == QUESTION_ESCALATION:
        raise ValueError(f"no judge template for the tag '{finding.tag}' (line {finding.line})")
    fix_line = _source_line(fix_src, finding.line) or NO_LINE
    values = {"line": str(finding.line), "detail": finding.detail, "fix_line": fix_line}
    role = None
    if finding.tag == "retargeted":
        values["tag"] = finding.tag
        values.update(_reference_values(reference_src, finding.detail))
        role = role_of(fix_line) or role_of(values["ref_text"])
    elif finding.tag == "broad-pattern":
        role = role_of(fix_line)
    elif finding.tag == "changed-setup":
        values.update(_reference_values(reference_src, finding.detail))
    return Question(f"{finding.tag}:{finding.line}", finding.tag, finding.line, template, role, values)


def _escalation_question(
    reference_src: str, input_src: str, fix_src: str, response: str
) -> Question:
    blocked = blocked_step(extract_steps(reference_src), extract_steps(input_src))
    if blocked is None:
        raise ValueError("the escalate case's input is not the reference plus one blocked step")
    blocked_text = _source_line(input_src, blocked.line) or NO_LINE
    keeps = any(step_key(step) == step_key(blocked) for step in extract_steps(fix_src))
    values = {
        "blocked_line": str(blocked.line),
        "blocked_text": blocked_text,
        "kept": "keeps" if keeps else "removes",
        "response": response.strip(),
    }
    return Question(
        QUESTION_ESCALATION,
        QUESTION_ESCALATION,
        blocked.line,
        TEMPLATES[QUESTION_ESCALATION],
        role_of(blocked_text),
        values,
    )


def questions_for(
    case: Case,
    reference_src: str,
    input_src: str,
    fix_src: str,
    findings: list[Finding],
    response: str | None = None,
) -> list[Question]:
    """The judge's questions for one fix: one per judge finding, then the escalation question.

    Judge findings are deduplicated by question id and sorted by ``(line,
    tag)``. An escalate case adds the escalation question last, about the
    blocked step (found from ``reference_src`` and ``input_src``) and
    ``response``, the model's final text. Raises ``ValueError`` when
    ``findings`` hold a zero (the judge never sees such a trial), when an
    escalate case has no ``response``, when a fix case has one, for a judge
    tag with no template, and when the blocked step can't be found.
    """
    if any(finding.severity == SEVERITY_ZERO for finding in findings):
        raise ValueError("a trial with a zero finding never reaches the judge")
    escalate = case.expected == EXPECTED_ESCALATE
    if escalate and response is None:
        raise ValueError("an escalate case needs the model's final response")
    if not escalate and response is not None:
        raise ValueError("only an escalate case takes a response")
    questions: dict[str, Question] = {}
    for finding in findings:
        if finding.severity != SEVERITY_JUDGE:
            continue
        question = _finding_question(finding, reference_src, fix_src)
        questions.setdefault(question.id, question)
    ordered = sorted(questions.values(), key=lambda question: (question.line, question.tag))
    if escalate:
        assert response is not None
        ordered.append(_escalation_question(reference_src, input_src, fix_src, response))
    return ordered


# --------------------------------------------------------------------------
# The prompt
# --------------------------------------------------------------------------


def build_prompt(
    case: Case,
    reference_src: str,
    fix_src: str,
    results_text: str,
    question: Question,
    *,
    judge_dir: Path = JUDGE_DIR,
) -> str:
    """The whole prompt for one question: the question template inside ``frame.md``."""
    judge_dir = Path(judge_dir)
    entries = cheat_entries(_read(judge_dir, CHEATS))
    evidence, note = evidence_excerpt(results_text, question.role)
    rendered = render(_read(judge_dir, question.template), question.values)
    facts = FACTS_ESCALATE if case.expected == EXPECTED_ESCALATE else FACTS_FIX
    return render(
        _read(judge_dir, FRAME),
        {
            "cheats": "\n".join(entries) if entries else NO_CHEATS,
            "fails_at": str(case.fails_at),
            "defect": case.defect,
            "reference": numbered(reference_src),
            "evidence_note": note,
            "evidence": evidence,
            "fix": numbered(fix_src),
            "facts": facts,
            "question": rendered,
        },
    )


def prompt_key(prompt: str) -> str:
    """The cache key of a prompt: 16 hex digits of a SHA-256 over model, effort, system prompt and prompt."""
    text = "\n".join([JUDGE_MODEL, JUDGE_EFFORT, SYSTEM_PROMPT, prompt])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------
# Answers
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Answer:
    """The judge's answer to one question."""

    answer: str  # one of ANSWERS
    quote: str
    reason: str
    cost_usd: float | None = None


AskFn = Callable[[str], Answer]


class JudgeError(Exception):
    """A call or an answer the grader can't use. Never read as an ``ok``."""


def parse_answer(text: str) -> Answer:
    """The first JSON object in ``text`` that has an ``"answer"`` key, as an ``Answer``.

    Every ``{`` is tried left to right with ``raw_decode``, so a fence or
    prose around the object doesn't matter. Raises ``JudgeError`` when there
    is no such object, when ``answer`` isn't one of ``ANSWERS`` or when
    ``quote`` or ``reason`` isn't a string.
    """
    decoder = json.JSONDecoder()
    found = None
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except ValueError:
            continue
        if isinstance(value, dict) and "answer" in value:
            found = value
            break
    if found is None:
        raise JudgeError("the judge's reply holds no JSON object with an answer")
    if found["answer"] not in ANSWERS:
        raise JudgeError(f"the judge's answer {found['answer']!r} is not one of {ANSWERS}")
    for key in ("quote", "reason"):
        if not isinstance(found.get(key), str):
            raise JudgeError(f"the judge's {key} is missing or not a string")
    return Answer(found["answer"], found["quote"], found["reason"])


# --------------------------------------------------------------------------
# claude -p
# --------------------------------------------------------------------------


def judge_argv(claude_cmd: list[str]) -> list[str]:
    """The ``claude`` argument list for one judge call; the prompt goes in on stdin.

    ``--tools`` is variadic: its ``""`` is an argv element of its own and a
    flag follows it. No positional prompt: a prompt with the evidence is
    longer than Windows' command line allows.
    """
    argv = [
        *claude_cmd,
        "-p",
        "--safe-mode",
        "--strict-mcp-config",
        "--tools",
        "",
        "--no-session-persistence",
        "--model",
        JUDGE_MODEL,
    ]
    if JUDGE_EFFORT != "default":
        argv += ["--effort", JUDGE_EFFORT]
    argv += [
        "--max-budget-usd",
        JUDGE_CALL_BUDGET_USD,
        "--output-format",
        "json",
        "--system-prompt",
        SYSTEM_PROMPT,
    ]
    return argv


def _result_object(stdout: str) -> dict:
    """The one JSON object ``claude`` printed, else the last result line of a stream."""
    try:
        whole = json.loads(stdout)
    except ValueError:
        whole = None
    if isinstance(whole, dict):
        return whole
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "result":
            return value
    raise JudgeError("claude printed no result object")


def ask_claude(
    prompt: str,
    *,
    claude_cmd: list[str],
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout_s: int = JUDGE_TIMEOUT_S,
    work_dir: Path | None = None,
) -> Answer:
    """Ask Sonnet one question through ``claude -p`` and return its parsed answer.

    The prompt goes in on stdin as UTF-8. ``claude`` runs in ``work_dir``
    (default: a ``scriptfix-judge`` folder under the system temp folder,
    created if missing; never the repo, whose settings and hooks must not
    load) with the parent session's variables stripped. Raises ``JudgeError``
    for a timeout, a failed start, a non-zero exit, a missing result object,
    ``is_error``, a ``subtype`` other than ``"success"``, a non-string
    ``result`` and an unparsable answer. ``runner`` is the injection point.
    """
    directory = (
        Path(work_dir) if work_dir is not None else Path(tempfile.gettempdir()) / "scriptfix-judge"
    )
    directory.mkdir(parents=True, exist_ok=True)
    try:
        completed = runner(
            judge_argv(claude_cmd),
            input=prompt.encode("utf-8"),
            capture_output=True,
            timeout=timeout_s,
            cwd=directory,
            env=session_free_env(os.environ),
        )
    except subprocess.TimeoutExpired as exc:
        raise JudgeError(f"claude timed out after {timeout_s} s") from exc
    except OSError as exc:
        raise JudgeError(f"claude could not be started: {exc}") from exc
    if completed.returncode != 0:
        stderr = _text(completed.stderr)
        raise JudgeError(f"claude exited {completed.returncode}: {stderr[-300:].strip()}")
    result = _result_object(_text(completed.stdout))
    if result.get("is_error") is True:
        raise JudgeError(f"claude reported an error: {_text(result.get('result'))[:200]}")
    if result.get("subtype") != "success":
        raise JudgeError(f"claude's result subtype is {result.get('subtype')!r}, not 'success'")
    reply = result.get("result")
    if not isinstance(reply, str):
        raise JudgeError("claude's result is not a string")
    answer = parse_answer(reply)
    cost = result.get("total_cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        return Answer(answer.answer, answer.quote, answer.reason, float(cost))
    return answer


def _text(value: object) -> str:
    """Process output as text: bytes decode as UTF-8 (``errors="replace"``), None is empty."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""
