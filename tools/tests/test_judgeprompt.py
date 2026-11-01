"""Tests for scriptfix.judgeprompt: templates, version, evidence excerpt, questions, prompts, answers and the call.

Nothing here calls ``claude``: the subprocess runner is a fake. Questions and
prompts are built from the real corpora through their files; the judge
folder is copied into tmp_path wherever a test edits a template or the cheat
list.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pytest

from scriptfix import __version__, judgeprompt
from scriptfix.case import Case, load_case
from scriptfix.findings import SEVERITY_JUDGE, SEVERITY_ZERO, Finding
from scriptfix.judgeprompt import (
    CUT_MARKER,
    EVIDENCE_LIMIT,
    FACTS_ESCALATE,
    FACTS_FIX,
    JUDGE_DIR,
    SYSTEM_PROMPT,
    Answer,
    JudgeError,
    Question,
    ask_claude,
    build_prompt,
    cheat_entries,
    evidence_excerpt,
    judge_argv,
    judge_version,
    numbered,
    parse_answer,
    prompt_key,
    questions_for,
    render,
    role_of,
)
from scriptfix.report import REPO_ROOT
from scriptfix.run import STRIP_NAMES, session_free_env, stripped_names, trial_env
from scriptfix.static import EXPECTED_ESCALATE, check_static, step_key
from scriptfix.steps import extract_steps

EVAL_01 = REPO_ROOT / "evals" / "01-playwright-python-basic"
EVAL_06 = REPO_ROOT / "evals" / "06-docs-journey-e"


def corpus_file(eval_dir: Path, name: str) -> str:
    return (eval_dir / "grading" / "corpus" / name).read_text(encoding="utf-8")


def reference_of(eval_dir: Path) -> str:
    return (eval_dir / "grading" / "reference" / "script.py").read_text(encoding="utf-8")


def results_of(eval_dir: Path) -> str:
    return (eval_dir / "inputs" / "results.txt").read_text(encoding="utf-8")


def fix_questions(name: str) -> tuple[Case, str, str, list[Question]]:
    """Eval 01's questions for one of its corpus files: (case, reference, fix, questions)."""
    case = load_case(EVAL_01)
    reference, fix = reference_of(EVAL_01), corpus_file(EVAL_01, name)
    questions = questions_for(case, reference, case.input_script.read_text(encoding="utf-8"), fix,
                              check_static(reference, fix))
    return case, reference, fix, questions


def escalate_questions(name: str, response: str = "A response.") -> list[Question]:
    """Case 06's questions for one of its corpus files and a response."""
    case = load_case(EVAL_06)
    reference, fix = reference_of(EVAL_06), corpus_file(EVAL_06, name)
    broken = case.input_script.read_text(encoding="utf-8")
    findings = check_static(reference, fix, input_src=broken, expected=EXPECTED_ESCALATE)
    return questions_for(case, reference, broken, fix, findings, response)


@pytest.fixture
def judge_copy(tmp_path: Path) -> Path:
    target = tmp_path / "judge"
    shutil.copytree(JUDGE_DIR, target)
    return target


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def test_render_fills_every_placeholder() -> None:
    assert render("a {{x}} b {{y}} c {{x}}", {"x": "1", "y": "2"}) == "a 1 b 2 c 1"


def test_render_names_a_missing_value() -> None:
    with pytest.raises(ValueError, match="without a value: y"):
        render("{{x}} {{y}}", {"x": "1"})


def test_render_names_an_unused_value() -> None:
    with pytest.raises(ValueError, match="without a placeholder: z"):
        render("{{x}}", {"x": "1", "z": "2"})


def test_render_inserts_a_value_that_looks_like_a_placeholder_as_it_is() -> None:
    assert render("{{a}} {{b}}", {"a": "{{b}}", "b": "B"}) == "{{b}} B"


# --------------------------------------------------------------------------
# cheat_entries
# --------------------------------------------------------------------------


def test_cheat_entries_are_the_dash_lines_in_order() -> None:
    text = "# Title\n\nprose - with a dash\n- first (the CD)\n -indented\n- second\n-no space\n"
    assert cheat_entries(text) == ["- first (the CD)", "- second"]


def test_the_frame_reads_the_real_cheat_list_or_none_yet() -> None:
    # The CD's list starts empty (the frame then reads "- (none yet)") and
    # grows as results come in; the test holds either way.
    entries = cheat_entries((JUDGE_DIR / "cheats.md").read_text(encoding="utf-8"))
    case, reference, fix, questions = fix_questions("ok-regex.py")
    prompt = build_prompt(case, reference, fix, results_of(EVAL_01), questions[0])
    assert ("\n" + "\n".join(entries or ["- (none yet)"]) + "\n") in prompt


def test_a_cheat_entry_reaches_the_prompt(judge_copy: Path) -> None:
    with (judge_copy / "cheats.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("- never sleep (the CD, 2026-11-20)\n")
    case, reference, fix, questions = fix_questions("ok-regex.py")
    prompt = build_prompt(case, reference, fix, results_of(EVAL_01), questions[0], judge_dir=judge_copy)
    assert "\n- never sleep (the CD, 2026-11-20)\n" in prompt
    assert "(none yet)" not in prompt


# --------------------------------------------------------------------------
# judge_version
# --------------------------------------------------------------------------


def test_judge_version_is_stable_and_shaped() -> None:
    version = judge_version()
    assert version == judge_version()
    assert re.fullmatch(r"j[0-9a-f]{12}", version)


def test_judge_version_ignores_the_graders_version(monkeypatch: pytest.MonkeyPatch) -> None:
    before = judge_version()
    monkeypatch.setattr("scriptfix.__version__", __version__ + ".next")
    assert judge_version() == before


def test_judge_version_changes_with_one_template_byte(judge_copy: Path) -> None:
    before = judge_version(judge_copy)
    with (judge_copy / "broad-pattern.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(" ")
    assert judge_version(judge_copy) != before


def test_judge_version_changes_with_a_cheat_entry(judge_copy: Path) -> None:
    before = judge_version(judge_copy)
    with (judge_copy / "cheats.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("- one more ruling (the CD, 2026-11-20)\n")
    assert judge_version(judge_copy) != before


def test_judge_version_ignores_the_cheat_lists_prose(judge_copy: Path) -> None:
    before = judge_version(judge_copy)
    with (judge_copy / "cheats.md").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\nMore prose, with no dash at the start of a line.\n")
    assert judge_version(judge_copy) == before


def test_judge_version_follows_the_models_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    before = judge_version()
    monkeypatch.setattr(judgeprompt, "JUDGE_EFFORT", "medium")
    assert judge_version() != before


# --------------------------------------------------------------------------
# evidence_excerpt
# --------------------------------------------------------------------------

RESULTS = "\n".join(
    [
        "Traceback (most recent call last):",
        "AssertionError: Locator expected to be visible",
        "Call log:",
        "Aria snapshot:",
        "- banner:",
        '  - link "Home":',
        "    - /url: /",
        "  - text: Welcome",
        "- main:",
        '  - heading "Title" [level=1]',
        "  - paragraph: Some words",
        '  - link "Next":',
        "    - /url: /next",
        "- contentinfo",
        "exit code: 1",
    ]
)


def test_excerpt_with_a_role_keeps_the_head_the_role_and_the_landmarks_in_order() -> None:
    excerpt, note = evidence_excerpt(RESULTS, "link")
    assert excerpt.splitlines() == [
        "Traceback (most recent call last):",
        "AssertionError: Locator expected to be visible",
        "Call log:",
        "Aria snapshot:",
        "- banner:",
        '  - link "Home":',
        "- main:",
        '  - heading "Title" [level=1]',
        '  - link "Next":',
        "- contentinfo",
        "exit code: 1",
    ]
    assert note == (
        "an excerpt: the error and the call log, then the aria snapshot's link, "
        "heading and landmark lines, in document order"
    )


def test_excerpt_without_a_role_drops_the_snapshot() -> None:
    excerpt, note = evidence_excerpt(RESULTS, None)
    assert excerpt.splitlines() == [
        "Traceback (most recent call last):",
        "AssertionError: Locator expected to be visible",
        "Call log:",
        "exit code: 1",
    ]
    assert note == "an excerpt: the error and the call log; the aria snapshot is left out"


def test_excerpt_without_a_snapshot_is_the_whole_text() -> None:
    text = "Error: strict mode violation\n  - a\n  - b\nexit code: 1"
    assert evidence_excerpt(text, "link") == (text, "the whole file")


def test_excerpt_past_the_limit_is_cut_with_a_marker_and_a_note() -> None:
    text = "x" * (EVIDENCE_LIMIT + 50)
    excerpt, note = evidence_excerpt(text, None)
    assert excerpt == "x" * EVIDENCE_LIMIT + "\n" + CUT_MARKER
    assert note == "the whole file; cut at 40000 characters"


def test_excerpt_of_a_long_snapshot_is_cut_too() -> None:
    long_snapshot = RESULTS.replace("- banner:", "\n".join('- link "n"' for _ in range(6000)))
    excerpt, note = evidence_excerpt(long_snapshot, "link")
    assert excerpt.endswith("\n" + CUT_MARKER)
    assert note.endswith("; cut at 40000 characters")


def test_role_of_reads_the_first_get_by_role() -> None:
    assert role_of('await page.get_by_role("link", name="x").click()') == "link"
    assert role_of("page.get_by_role( 'heading' , name='x')") == "heading"
    assert role_of('page.get_by_text("x")') is None


def test_numbered_prefixes_each_line_from_one() -> None:
    assert numbered("a\nb\n") == "1: a\n2: b"


# --------------------------------------------------------------------------
# questions_for
# --------------------------------------------------------------------------


def test_questions_for_a_regex_fix_are_in_line_order_on_the_link_role() -> None:
    _, _, _, questions = fix_questions("ok-regex.py")
    assert [q.id for q in questions] == ["retargeted:18", "retargeted:19", "retargeted:20"]
    assert {q.role for q in questions} == {"link"}
    assert all(q.template == "same-target.md" for q in questions)
    assert questions[0].values["line"] == "18"
    assert questions[0].values["tag"] == "retargeted"
    assert questions[0].values["ref_line"].isdigit()


def test_a_broad_pattern_gives_two_questions_sorted_by_line_then_tag() -> None:
    _, _, _, questions = fix_questions("judge-broad-pattern.py")
    assert [q.id for q in questions] == ["broad-pattern:20", "retargeted:20"]
    assert questions[0].template == "broad-pattern.md"
    assert set(questions[0].values) == {"line", "detail", "fix_line"}


def test_a_setup_change_carries_its_reference_line() -> None:
    _, reference, _, questions = fix_questions("judge-changed-setup.py")
    assert [q.id for q in questions] == ["changed-setup:8"]
    assert questions[0].values["ref_line"] == "8"
    assert questions[0].values["ref_text"] == reference.splitlines()[7].strip()
    assert questions[0].role is None


def test_a_new_wait_has_no_reference_line_and_no_role() -> None:
    _, _, _, questions = fix_questions("judge-new-wait.py")
    assert [q.id for q in questions] == ["new-wait:18"]
    assert set(questions[0].values) == {"line", "detail", "fix_line"}
    assert questions[0].role is None


def test_a_duplicate_finding_is_asked_once() -> None:
    case = load_case(EVAL_01)
    reference, fix = reference_of(EVAL_01), corpus_file(EVAL_01, "judge-new-wait.py")
    finding = next(f for f in check_static(reference, fix) if f.severity == SEVERITY_JUDGE)
    questions = questions_for(case, reference, "", fix, [finding, finding])
    assert len(questions) == 1


def test_an_escalate_case_that_keeps_the_blocked_step_asks_keeps() -> None:
    case = load_case(EVAL_06)
    questions = escalate_questions("ok-input.py", "My response.\n")
    assert [q.id for q in questions] == ["escalation"]
    question = questions[0]
    assert question.template == "escalation.md"
    assert question.values["kept"] == "keeps"
    assert question.values["response"] == "My response."
    input_lines = case.input_script.read_text(encoding="utf-8").splitlines()
    blocked_line = int(question.values["blocked_line"])
    assert question.line == blocked_line
    assert input_lines[blocked_line - 1].strip() == question.values["blocked_text"]


def test_an_escalate_case_that_drops_the_blocked_step_asks_removes() -> None:
    questions = escalate_questions("ok-reference.py")
    assert [q.id for q in questions] == ["escalation"]
    assert questions[0].values["kept"] == "removes"


def test_the_blocked_step_is_the_inputs_extra_step() -> None:
    case = load_case(EVAL_06)
    broken = case.input_script.read_text(encoding="utf-8")
    question = escalate_questions("ok-input.py")[0]
    blocked = next(s for s in extract_steps(broken) if s.line == question.line)
    reference_keys = [step_key(s) for s in extract_steps(reference_of(EVAL_06))]
    assert step_key(blocked) not in reference_keys


def test_questions_for_refuse_a_trial_with_a_zero_finding() -> None:
    case = load_case(EVAL_01)
    reference, fix = reference_of(EVAL_01), corpus_file(EVAL_01, "zero-removed-step.py")
    findings = check_static(reference, fix)
    assert any(f.severity == SEVERITY_ZERO for f in findings)
    with pytest.raises(ValueError, match="zero"):
        questions_for(case, reference, "", fix, findings)


def test_questions_for_an_escalate_case_need_a_response() -> None:
    case = load_case(EVAL_06)
    reference, fix = reference_of(EVAL_06), corpus_file(EVAL_06, "ok-input.py")
    broken = case.input_script.read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="response"):
        questions_for(case, reference, broken, fix, [], None)


def test_questions_for_a_fix_case_refuse_a_response() -> None:
    case = load_case(EVAL_01)
    reference, fix = reference_of(EVAL_01), corpus_file(EVAL_01, "ok-reference.py")
    with pytest.raises(ValueError, match="response"):
        questions_for(case, reference, "", fix, [], "text")


def test_questions_for_a_judge_tag_without_a_template_raise() -> None:
    case = load_case(EVAL_01)
    reference, fix = reference_of(EVAL_01), corpus_file(EVAL_01, "ok-reference.py")
    with pytest.raises(ValueError, match="no judge template"):
        questions_for(case, reference, "", fix, [Finding("mystery", SEVERITY_JUDGE, 3, "x")])


# --------------------------------------------------------------------------
# build_prompt and prompt_key
# --------------------------------------------------------------------------


def test_a_fix_prompt_holds_the_case_both_scripts_the_facts_and_the_question() -> None:
    case, reference, fix, questions = fix_questions("ok-regex.py")
    prompt = build_prompt(case, reference, fix, results_of(EVAL_01), questions[0])
    assert case.defect in prompt
    assert prompt.count("\n18: ") >= 2  # the reference's line 18 and the model's
    assert FACTS_FIX in prompt
    assert FACTS_ESCALATE not in prompt
    question_text = render(
        (JUDGE_DIR / questions[0].template).read_text(encoding="utf-8"), questions[0].values
    )
    assert question_text in prompt
    assert prompt.rstrip().endswith(question_text.rstrip())
    assert "{{" not in prompt
    assert f"at line {case.fails_at} of its input" in prompt


def test_an_escalation_prompt_holds_the_response_and_the_escalate_facts() -> None:
    case = load_case(EVAL_06)
    response = (EVAL_06 / "grading" / "corpus" / "responses" / "ask-kept.md").read_text(encoding="utf-8")
    reference, fix = reference_of(EVAL_06), corpus_file(EVAL_06, "ok-input.py")
    question = escalate_questions("ok-input.py", response)[0]
    prompt = build_prompt(case, reference, fix, results_of(EVAL_06), question)
    assert FACTS_ESCALATE in prompt
    assert FACTS_FIX not in prompt
    assert "<<<RESPONSE\n" + response.strip() + "\nRESPONSE>>>" in prompt
    assert "{{" not in prompt


def test_every_eval_01_item_builds_a_prompt_under_the_limit() -> None:
    case = load_case(EVAL_01)
    items = tomllib.loads((EVAL_01 / "grading" / "corpus" / "judge.toml").read_text(encoding="utf-8"))["item"]
    assert items
    for item in items:
        _, reference, fix, questions = fix_questions(item["file"])
        question = next(q for q in questions if q.id == item["question"])
        prompt = build_prompt(case, reference, fix, results_of(EVAL_01), question)
        assert len(prompt) < 60_000, f"{item['file']} {item['question']}: {len(prompt)} characters"
        assert "{{" not in prompt


def test_prompt_key_is_sixteen_hex_digits_and_follows_the_prompt() -> None:
    key = prompt_key("a prompt")
    assert re.fullmatch(r"[0-9a-f]{16}", key)
    assert key == prompt_key("a prompt")
    assert key != prompt_key("a promPt")


def test_prompt_key_follows_the_system_prompt_and_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    key = prompt_key("a prompt")
    monkeypatch.setattr(judgeprompt, "SYSTEM_PROMPT", SYSTEM_PROMPT + " ")
    assert prompt_key("a prompt") != key
    monkeypatch.undo()
    monkeypatch.setattr(judgeprompt, "JUDGE_MODEL", "another-model")
    assert prompt_key("a prompt") != key


# --------------------------------------------------------------------------
# parse_answer
# --------------------------------------------------------------------------

ANSWER = {"answer": "ok", "quote": "page.get_by_role", "reason": "One match."}


def test_parse_answer_reads_a_plain_object() -> None:
    assert parse_answer(json.dumps(ANSWER)) == Answer("ok", "page.get_by_role", "One match.")


def test_parse_answer_reads_a_fenced_object() -> None:
    assert parse_answer("```json\n" + json.dumps(ANSWER) + "\n```").answer == "ok"


def test_parse_answer_reads_an_object_between_sentences() -> None:
    text = "Here is my answer {not json} for you: " + json.dumps({**ANSWER, "answer": "cheat"}) + " Thanks."
    assert parse_answer(text).answer == "cheat"


def test_parse_answer_allows_braces_inside_the_reason() -> None:
    reason = "It matches {a} and {{b}} but } not {"
    assert parse_answer(json.dumps({**ANSWER, "reason": reason})).reason == reason


def test_parse_answer_skips_an_object_without_an_answer() -> None:
    text = '{"note": 1} ' + json.dumps({**ANSWER, "answer": "unsure"})
    assert parse_answer(text).answer == "unsure"


@pytest.mark.parametrize(
    "text",
    [
        json.dumps({**ANSWER, "answer": "maybe"}),
        json.dumps({"answer": "ok", "reason": "no quote"}),
        json.dumps({**ANSWER, "reason": 3}),
        "no json here",
        "",
        '{"answer": "ok", "quote": ',
    ],
    ids=["bad-answer", "missing-quote", "reason-not-a-string", "no-json", "empty", "truncated"],
)
def test_parse_answer_rejects_what_it_cannot_use(text: str) -> None:
    with pytest.raises(JudgeError):
        parse_answer(text)


# --------------------------------------------------------------------------
# judge_argv and ask_claude
# --------------------------------------------------------------------------


def test_judge_argv_is_the_exact_list() -> None:
    assert judge_argv(["claude"]) == [
        "claude",
        "-p",
        "--safe-mode",
        "--strict-mcp-config",
        "--tools",
        "",
        "--no-session-persistence",
        "--model",
        "claude-sonnet-5-5",
        "--max-budget-usd",
        "0.10",
        "--output-format",
        "json",
        "--system-prompt",
        SYSTEM_PROMPT,
    ]


def test_judge_argv_puts_an_empty_string_then_a_flag_after_tools() -> None:
    argv = judge_argv(["claude", "extra"])
    index = argv.index("--tools")
    assert argv[index + 1] == ""
    assert argv[index + 2].startswith("--")
    assert argv[:2] == ["claude", "extra"]
    assert "--effort" not in argv


def test_judge_argv_adds_the_effort_right_after_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(judgeprompt, "JUDGE_EFFORT", "medium")
    argv = judge_argv(["claude"])
    index = argv.index("--model")
    assert argv[index : index + 4] == ["--model", "claude-sonnet-5-5", "--effort", "medium"]


class FakeRunner:
    """A stand-in for subprocess.run that records its call and returns or raises a canned outcome."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0,
                 raises: Exception | None = None) -> None:
        self.stdout, self.stderr, self.returncode, self.raises = stdout, stderr, returncode, raises
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        self.calls.append((argv, kwargs))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, self.stderr)


def result_line(**overrides: Any) -> bytes:
    body: dict[str, Any] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": json.dumps(ANSWER),
        "total_cost_usd": 0.0123,
    }
    body.update(overrides)
    return json.dumps(body).encode("utf-8")


def test_ask_claude_sends_the_prompt_on_stdin_in_the_work_dir_without_the_session_variables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    runner = FakeRunner(stdout=result_line())
    work = tmp_path / "work"
    ask_claude("the prompt, with é", claude_cmd=["claude"], runner=runner, work_dir=work)
    argv, kwargs = runner.calls[0]
    assert argv == judge_argv(["claude"])
    assert kwargs["input"] == "the prompt, with é".encode("utf-8")
    assert kwargs["capture_output"] is True
    assert kwargs["timeout"] == judgeprompt.JUDGE_TIMEOUT_S
    assert Path(kwargs["cwd"]) == work and work.is_dir()
    assert "CLAUDECODE" not in kwargs["env"]
    assert kwargs["env"]["PATH"] == os.environ["PATH"]


def test_ask_claude_defaults_to_a_neutral_folder_under_the_temp_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    runner = FakeRunner(stdout=result_line())
    ask_claude("p", claude_cmd=["claude"], runner=runner)
    cwd = Path(runner.calls[0][1]["cwd"])
    assert cwd == tmp_path / "scriptfix-judge" and cwd.is_dir()
    assert REPO_ROOT not in cwd.parents and cwd != REPO_ROOT


def test_ask_claude_returns_the_answer_with_its_cost(tmp_path: Path) -> None:
    answer = ask_claude("p", claude_cmd=["claude"], runner=FakeRunner(stdout=result_line()), work_dir=tmp_path)
    assert answer == Answer("ok", "page.get_by_role", "One match.", 0.0123)


def test_ask_claude_leaves_the_cost_empty_when_it_is_not_a_number(tmp_path: Path) -> None:
    runner = FakeRunner(stdout=result_line(total_cost_usd="a lot"))
    assert ask_claude("p", claude_cmd=["claude"], runner=runner, work_dir=tmp_path).cost_usd is None


def test_ask_claude_reads_the_last_result_line_of_a_stream(tmp_path: Path) -> None:
    stream = b'{"type": "system"}\n' + result_line() + b"\n"
    answer = ask_claude("p", claude_cmd=["claude"], runner=FakeRunner(stdout=stream), work_dir=tmp_path)
    assert answer.answer == "ok"


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(stdout=result_line(is_error=True)),
        FakeRunner(stdout=result_line(subtype="error_max_budget_usd")),
        FakeRunner(stdout=result_line(result=None)),
        FakeRunner(stdout=result_line(result="no json at all")),
        FakeRunner(stdout=result_line(result=json.dumps({**ANSWER, "answer": "great"}))),
        FakeRunner(stdout=b"not json"),
        FakeRunner(stdout=b""),
        FakeRunner(stdout=result_line(), stderr=b"boom", returncode=1),
        FakeRunner(raises=subprocess.TimeoutExpired(["claude"], 1)),
        FakeRunner(raises=FileNotFoundError("claude")),
    ],
    ids=[
        "is-error",
        "subtype",
        "result-not-a-string",
        "answer-unparsable",
        "answer-not-allowed",
        "non-json",
        "empty",
        "exit-code",
        "timeout",
        "no-executable",
    ],
)
def test_ask_claude_raises_a_judge_error_instead_of_an_ok(runner: FakeRunner, tmp_path: Path) -> None:
    with pytest.raises(JudgeError):
        ask_claude("p", claude_cmd=["claude"], runner=runner, work_dir=tmp_path)


def test_a_failed_exit_names_the_code_and_the_end_of_stderr(tmp_path: Path) -> None:
    stderr = b"x" * 1000 + b"THE END"
    runner = FakeRunner(stderr=stderr, returncode=3)
    with pytest.raises(JudgeError, match=r"exited 3: x+THE END") as info:
        ask_claude("p", claude_cmd=["claude"], runner=runner, work_dir=tmp_path)
    assert len(str(info.value)) < 400


def test_an_error_subtype_is_named_in_the_message(tmp_path: Path) -> None:
    runner = FakeRunner(stdout=result_line(subtype="error_max_turns"))
    with pytest.raises(JudgeError, match="error_max_turns"):
        ask_claude("p", claude_cmd=["claude"], runner=runner, work_dir=tmp_path)


# --------------------------------------------------------------------------
# session_free_env
# --------------------------------------------------------------------------


def test_session_free_env_strips_what_trial_env_strips(tmp_path: Path) -> None:
    environ = {name: "v" for name in STRIP_NAMES}
    environ.update({"CLAUDECODE": "1", "claude_code_entrypoint": "x", "ZMH3D_HOME": "h"})
    environ.update({"PATH": os.pathsep.join(["a", "b"]), "HOME": "home", "Temp": "t"})
    env = session_free_env(environ)
    assert env == {"PATH": environ["PATH"], "HOME": "home", "Temp": "t"}
    assert set(env) == set(environ) - set(stripped_names(environ))
    trial = trial_env(environ, pwsh_dir=tmp_path / "pwsh", repo_root=tmp_path / "repo")
    assert set(trial) - {"PATH"} == set(env) - {"PATH"}


def test_session_free_env_leaves_its_input_alone() -> None:
    environ = {"CLAUDECODE": "1", "HOME": "h"}
    session_free_env(environ)
    assert environ == {"CLAUDECODE": "1", "HOME": "h"}
