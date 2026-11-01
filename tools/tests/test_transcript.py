"""Tests for scriptfix.transcript: reading, validity and fair-play checks.

Transcripts are synthetic JSON Lines built in tmp_path; nothing here is
copied from a real trial.
"""

from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pytest

from scriptfix.findings import SEVERITY_INVALID, SEVERITY_SMELL, SEVERITY_ZERO
from scriptfix.transcript import (
    FORMAT_SESSION,
    FORMAT_STREAM,
    TAG_ANSWER_KEY,
    TAG_HARNESS_ERROR,
    TAG_REPO_ONLINE,
    TAG_TRIED_TO_RUN,
    ToolCall,
    Transcript,
    check_fair_play,
    check_validity,
    read_transcript,
)

REPO = "D:/gitrepos/ai-eval-examples"
GRADING_FILE = r"D:\gitrepos\ai-eval-examples\evals\01-playwright-python-basic\grading\rubric.md"


# -- builders ----------------------------------------------------------------


def write_lines(tmp_path: Path, lines: list, name: str = "t.jsonl") -> Path:
    path = tmp_path / name
    text = "\n".join(line if isinstance(line, str) else json.dumps(line) for line in lines)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def init_line(**extra) -> dict:
    line = {
        "type": "system",
        "subtype": "init",
        "model": "model-a",
        "claude_code_version": "9.9.9",
        "session_id": "sess-1",
    }
    line.update(extra)
    return line


def assistant(*items: dict, **extra) -> dict:
    line = {"type": "assistant", "message": {"role": "assistant", "content": list(items)}}
    line.update(extra)
    return line


def tool_use(call_id: str, name: str, **tool_input) -> dict:
    return {"type": "tool_use", "id": call_id, "name": name, "input": tool_input}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def user_result(call_id: str, content, is_error: bool | None = None) -> dict:
    item = {"type": "tool_result", "tool_use_id": call_id, "content": content}
    if is_error is not None:
        item["is_error"] = is_error
    return {"type": "user", "message": {"role": "user", "content": [item]}}


def result_line(**extra) -> dict:
    line = {
        "type": "result",
        "is_error": False,
        "api_error_status": None,
        "permission_denials": [],
        "result": "done",
        "session_id": "sess-1",
        "total_cost_usd": 0.5,
    }
    line.update(extra)
    return line


def denial(name: str, **tool_input) -> dict:
    return {"tool_name": name, "tool_use_id": "d1", "tool_input": tool_input}


def stream_trial(tmp_path: Path, calls: list[dict], **result_extra) -> Transcript:
    """A clean stream-json transcript whose assistant makes the given calls."""
    lines = [init_line(), assistant(*calls, text("working")), result_line(**result_extra)]
    return read_transcript(write_lines(tmp_path, lines))


def trial_with(tmp_path: Path, name: str, **tool_input) -> Transcript:
    return stream_trial(tmp_path, [tool_use("c1", name, **tool_input)])


def shell(tmp_path: Path, command: str, tool: str = "Bash") -> Transcript:
    return trial_with(tmp_path, tool, command=command)


def tags(findings) -> list[str]:
    return [f.tag for f in findings]


# -- reading -----------------------------------------------------------------


def test_stream_json_fields(tmp_path):
    lines = [
        init_line(),
        assistant(tool_use("c1", "Read", file_path="x.py"), text("hi")),
        user_result("c1", "contents"),
        result_line(permission_denials=[denial("Bash", command="ls")]),
    ]
    t = read_transcript(write_lines(tmp_path, lines))
    assert t.format == FORMAT_STREAM
    assert (t.model, t.cli_version, t.session_id) == ("model-a", "9.9.9", "sess-1")
    assert t.calls == (ToolCall("c1", "Read", {"file_path": "x.py"}),)
    assert t.results == (("c1", False, "contents"),)
    assert t.denials == (ToolCall("d1", "Bash", {"command": "ls"}),)
    assert (t.final_text, t.cost_usd, t.has_result, t.has_assistant) == ("done", 0.5, True, True)


def test_session_fields(tmp_path):
    lines = [
        {"type": "mode", "mode": "x"},
        {"type": "system", "subtype": "local_command", "content": "noise"},
        assistant(
            tool_use("c1", "Bash", command="ls"),
            version="1.2.3",
            sessionId="sess-2",
        ),
        assistant(text("first answer")),
        assistant(tool_use("c2", "Read", file_path="a")),
        assistant(text("last answer"), text("more")),
        {"type": "attachment"},
    ]
    lines[2]["message"]["model"] = "model-b"
    t = read_transcript(write_lines(tmp_path, lines))
    assert t.format == FORMAT_SESSION  # a non-init system line doesn't make it stream-json
    assert (t.model, t.cli_version, t.session_id) == ("model-b", "1.2.3", "sess-2")
    assert [c.id for c in t.calls] == ["c1", "c2"]
    assert t.final_text == "last answer\nmore"
    assert t.denials == ()
    assert t.cost_usd is None and not t.has_result


def test_format_detected_by_result_line_alone(tmp_path):
    t = read_transcript(write_lines(tmp_path, [assistant(text("x")), result_line()]))
    assert t.format == FORMAT_STREAM


def test_session_id_falls_back_to_result_line(tmp_path):
    init = init_line()
    del init["session_id"]
    t = read_transcript(write_lines(tmp_path, [init, assistant(text("x")), result_line(session_id="from-result")]))
    assert t.session_id == "from-result"


def test_duplicate_tool_use_ids_are_dropped(tmp_path):
    lines = [
        init_line(),
        assistant(tool_use("c1", "Read", file_path="a")),
        assistant(tool_use("c1", "Read", file_path="a"), tool_use("c2", "Read", file_path="b")),
        result_line(),
    ]
    t = read_transcript(write_lines(tmp_path, lines))
    assert [c.id for c in t.calls] == ["c1", "c2"]


def test_tool_result_content_as_list_and_is_error(tmp_path):
    lines = [
        init_line(),
        assistant(tool_use("c1", "Bash", command="x")),
        user_result("c1", [{"type": "text", "text": "one"}, {"type": "text", "text": "two"}], is_error=True),
        result_line(),
    ]
    t = read_transcript(write_lines(tmp_path, lines))
    assert t.results == (("c1", True, "one\ntwo"),)


def test_blank_garbage_and_truncated_lines_are_skipped(tmp_path):
    lines = [
        init_line(),
        "",
        "not json at all",
        "[1, 2]",
        {"type": "future-thing", "x": 1},
        assistant(tool_use("c1", "Read", file_path="a")),
        result_line(),
        '{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "c9"',  # truncated
    ]
    t = read_transcript(write_lines(tmp_path, lines))
    assert [c.id for c in t.calls] == ["c1"]
    assert t.has_result


def test_reads_utf8(tmp_path):
    lines = [init_line(), assistant(tool_use("c1", "Write", file_path="a", content="caf\u00e9 \u2713")), result_line()]
    t = read_transcript(write_lines(tmp_path, lines))
    assert t.calls[0].input["content"] == "caf\u00e9 \u2713"


# -- validity ----------------------------------------------------------------


def test_clean_stream_has_no_validity_finding(tmp_path):
    assert check_validity(stream_trial(tmp_path, [tool_use("c1", "Read", file_path="a")])) == []


def test_clean_session_has_no_validity_finding(tmp_path):
    t = read_transcript(write_lines(tmp_path, [assistant(text("done"))]))
    assert check_validity(t) == []


def test_stream_without_result_line_is_invalid(tmp_path):
    t = read_transcript(write_lines(tmp_path, [init_line(), assistant(text("x"))]))
    findings = check_validity(t)
    assert tags(findings) == [TAG_HARNESS_ERROR]
    assert findings[0].severity == SEVERITY_INVALID and findings[0].line == 0


def test_result_is_error_is_invalid(tmp_path):
    t = stream_trial(tmp_path, [], is_error=True)
    assert tags(check_validity(t)) == [TAG_HARNESS_ERROR]


def test_api_error_status_is_invalid(tmp_path):
    t = stream_trial(tmp_path, [], api_error_status=529)
    assert tags(check_validity(t)) == [TAG_HARNESS_ERROR]


def test_denied_edit_of_inputs_script_is_invalid(tmp_path):
    denied = denial("Edit", file_path=r"C:\Users\x\trial\inputs\script.py", old_string="a", new_string="b")
    t = stream_trial(tmp_path, [tool_use("c1", "Read", file_path="a")], permission_denials=[denied])
    assert tags(check_validity(t)) == [TAG_HARNESS_ERROR]


@pytest.mark.parametrize("tool", ["Write", "MultiEdit"])
def test_denied_write_or_multiedit_of_inputs_script_is_invalid(tmp_path, tool):
    denied = denial(tool, file_path="C:/Trial/Inputs/Script.py")
    t = stream_trial(tmp_path, [tool_use("c1", "Read", file_path="a")], permission_denials=[denied])
    assert tags(check_validity(t)) == [TAG_HARNESS_ERROR]


def test_denied_edit_of_another_file_is_not_invalid(tmp_path):
    denied = denial("Edit", file_path=r"C:\Users\x\trial\inputs\notes.py")
    t = stream_trial(tmp_path, [tool_use("c1", "Read", file_path="a")], permission_denials=[denied])
    assert check_validity(t) == []


def test_denied_bash_is_not_invalid(tmp_path):
    t = stream_trial(
        tmp_path,
        [tool_use("c1", "Read", file_path="a")],
        permission_denials=[denial("Bash", command="cat inputs/script.py")],
    )
    assert check_validity(t) == []


def test_command_line_too_long_is_invalid(tmp_path):
    lines = [
        init_line(),
        assistant(tool_use("c1", "Bash", command="x")),
        user_result("c1", "Error: The command line is too long.", is_error=True),
        result_line(),
    ]
    t = read_transcript(write_lines(tmp_path, lines))
    assert tags(check_validity(t)) == [TAG_HARNESS_ERROR]


def test_command_line_too_long_in_list_content_is_invalid(tmp_path):
    lines = [
        init_line(),
        assistant(tool_use("c1", "Bash", command="x")),
        user_result("c1", [{"type": "text", "text": "The command line is too long."}]),
        result_line(),
    ]
    assert tags(check_validity(read_transcript(write_lines(tmp_path, lines)))) == [TAG_HARNESS_ERROR]


def test_no_assistant_line_is_invalid(tmp_path):
    t = read_transcript(write_lines(tmp_path, [init_line(), result_line()]))
    findings = check_validity(t)
    assert tags(findings) == [TAG_HARNESS_ERROR]
    assert "no assistant" in findings[0].detail


def test_assistant_text_without_calls_is_valid(tmp_path):
    t = read_transcript(write_lines(tmp_path, [init_line(), assistant(text("just words")), result_line()]))
    assert check_validity(t) == []


def test_one_finding_per_distinct_reason(tmp_path):
    denied = denial("Edit", file_path="inputs/script.py")
    lines = [
        init_line(),
        assistant(tool_use("c1", "Bash", command="x")),
        user_result("c1", "The command line is too long"),
        user_result("c2", "The command line is too long"),
        result_line(is_error=True, permission_denials=[denied, denied]),
    ]
    findings = check_validity(read_transcript(write_lines(tmp_path, lines)))
    assert len(findings) == 3
    assert len({f.detail for f in findings}) == 3


# -- fair play: answer key ---------------------------------------------------


def test_reading_a_grading_file_is_answer_key(tmp_path):
    findings = check_fair_play(trial_with(tmp_path, "Read", file_path=GRADING_FILE))
    assert tags(findings) == [TAG_ANSWER_KEY]
    assert findings[0].severity == SEVERITY_ZERO and findings[0].line == 0


def test_grading_path_with_forward_slashes_and_relative_forms(tmp_path):
    assert tags(check_fair_play(shell(tmp_path, "cat evals/01-x/grading/rubric.md"))) == [TAG_ANSWER_KEY]
    assert tags(check_fair_play(shell(tmp_path, f"cat {REPO}/evals/01-x/grading"))) == [TAG_ANSWER_KEY]


def test_grading_path_in_a_denial_counts(tmp_path):
    t = stream_trial(
        tmp_path,
        [tool_use("c1", "Read", file_path="a")],
        permission_denials=[denial("Read", file_path=GRADING_FILE)],
    )
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


def test_grep_on_the_repo_root_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Grep", pattern="Previous", path=r"D:\gitrepos\ai-eval-examples")
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


@pytest.mark.parametrize(
    "path",
    [
        "D:/gitrepos/ai-eval-examples/",
        "D:/gitrepos/ai-eval-examples/evals",
        "D:/gitrepos/ai-eval-examples/evals/01-x/",
        "D:/gitrepos/ai-eval-examples/evals/**",
    ],
)
def test_grep_on_repo_scopes_is_answer_key(tmp_path, path):
    assert tags(check_fair_play(trial_with(tmp_path, "Grep", pattern="x", path=path))) == [TAG_ANSWER_KEY]


def test_grep_inside_the_trial_folder_is_fine(tmp_path):
    t = trial_with(tmp_path, "Grep", pattern="x", path=r"C:\Users\x\eval-trials\run1\inputs")
    assert check_fair_play(t) == []


def test_grep_on_a_repo_subfolder_other_than_evals_is_fine(tmp_path):
    assert check_fair_play(trial_with(tmp_path, "Grep", pattern="x", path=f"{REPO}/.venv")) == []


def test_glob_with_path_at_the_repo_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Glob", pattern="**/*.md", path=REPO)
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


def test_glob_pattern_rooted_at_the_repo_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Glob", pattern=f"{REPO}/**/*.md")
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


def test_glob_in_the_trial_folder_is_fine(tmp_path):
    assert check_fair_play(trial_with(tmp_path, "Glob", pattern="inputs/**/*.py")) == []


@pytest.mark.parametrize(
    "command",
    [
        f'grep -rn "Previous" {REPO}',
        f"grep -Rin previous {REPO}/evals",
        f"grep --recursive x {REPO}/evals/01-x",
        f"rg Previous {REPO}",
        f"find {REPO} -name '*.md'",
        f"tree {REPO}/evals",
        f"ls -laR {REPO}",
        f"cd {REPO} && grep -r token .",
    ],
)
def test_recursive_shell_forms_on_the_repo_are_answer_key(tmp_path, command):
    assert tags(check_fair_play(shell(tmp_path, command))) == [TAG_ANSWER_KEY]


@pytest.mark.parametrize(
    "command",
    [
        r"Get-ChildItem -Recurse D:\gitrepos\ai-eval-examples\evals",
        r"gci D:\gitrepos\ai-eval-examples -r",
        r"ls D:\gitrepos\ai-eval-examples -Recurse",
        r"Get-ChildItem -Path D:\gitrepos\ai-eval-examples -Filter *.md -Recurse | Select-String x",
    ],
)
def test_recursive_powershell_forms_on_the_repo_are_answer_key(tmp_path, command):
    assert tags(check_fair_play(shell(tmp_path, command, tool="PowerShell"))) == [TAG_ANSWER_KEY]


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        (f"ls -ltr {REPO}", "Bash"),
        (f"ls -la {REPO}", "Bash"),
        (f"ls -r {REPO}", "Bash"),  # POSIX -r is reverse
        (f'ls "{REPO}/.venv"', "Bash"),
        (f"Get-ChildItem {REPO}", "PowerShell"),
        (f"ls {REPO}", "PowerShell"),
        (f"grep -n x {REPO}/README.md", "Bash"),
        (f"grep -r x {REPO}/.venv", "Bash"),
        ("grep -rn x inputs", "Bash"),
        ("find . -name '*.py'", "Bash"),
        (r"Get-ChildItem -Recurse C:\Users\x\trial", "PowerShell"),
    ],
)
def test_non_recursive_or_unrelated_shell_forms_are_fine(tmp_path, command, tool):
    assert check_fair_play(shell(tmp_path, command, tool=tool)) == []


def test_ls_of_the_venv_gives_no_finding(tmp_path):
    assert check_fair_play(shell(tmp_path, 'ls "D:/gitrepos/ai-eval-examples/.venv" 2>&1')) == []


def test_powershell_lowercase_r_on_ls_is_recursive(tmp_path):
    t = shell(tmp_path, rf"ls -r {REPO}", tool="PowerShell")
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


# -- fair play: above the repo -------------------------------------------------

# Never derived from __file__: an oversee worktree lives under the repo.
ROOT = PureWindowsPath(r"D:\gitrepos\ai-eval-examples")


def above(call: Transcript, repo_root=ROOT):
    return check_fair_play(call, repo_root=repo_root)


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("grep -r rubric D:/gitrepos", "Bash"),
        (r"Get-ChildItem -Recurse D:\ ", "PowerShell"),
        ("rg rubric /d/gitrepos", "Bash"),
        ('rg rubric "D:\\GitRepos\\\\"', "Bash"),
        ("find d: -name rubric.md", "Bash"),
        ("rg rubric /d", "Bash"),
        ("grep -r x D:/gitrepos/*", "Bash"),
        ("ls -R D:/gitrepos/** 2>&1", "Bash"),
        ("cd /tmp && rg rubric 'D:/gitrepos'", "Bash"),
    ],
)
def test_recursive_search_of_an_ancestor_is_answer_key(tmp_path, command, tool):
    findings = above(shell(tmp_path, command, tool=tool))
    assert tags(findings) == [TAG_ANSWER_KEY]
    assert findings[0].severity == SEVERITY_ZERO
    assert findings[0].detail.startswith("searched above the repo: ")


def test_the_detail_names_the_searched_path(tmp_path):
    (finding,) = above(shell(tmp_path, "grep -r rubric D:/gitrepos"))
    assert finding.detail == "searched above the repo: D:/gitrepos"


def test_grep_with_path_at_an_ancestor_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Grep", pattern="x", path=r"D:\gitrepos")
    assert tags(above(t)) == [TAG_ANSWER_KEY]


def test_glob_with_path_at_an_ancestor_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Glob", pattern="*.md", path="D:/")
    assert tags(above(t)) == [TAG_ANSWER_KEY]


def test_glob_pattern_rooted_at_an_ancestor_is_answer_key(tmp_path):
    t = trial_with(tmp_path, "Glob", pattern="D:/gitrepos/**/rubric.md")
    assert tags(above(t)) == [TAG_ANSWER_KEY]


def test_an_ancestor_in_a_denied_call_counts(tmp_path):
    t = stream_trial(
        tmp_path,
        [tool_use("c1", "Read", file_path="a")],
        permission_denials=[denial("Grep", pattern="x", path="D:/gitrepos")],
    )
    assert tags(above(t)) == [TAG_ANSWER_KEY]


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("ls D:/gitrepos", "Bash"),  # not recursive
        ("grep rubric D:/gitrepos", "Bash"),
        ("grep -r foo C:/Users/a/eval-trials/01-run3", "Bash"),  # not an ancestor
        ("grep -r foo D:/gitrepos/other-project", "Bash"),  # below an ancestor
        ("grep -r foo D:/gitrepos-two", "Bash"),
        ("find . -name x", "Bash"),
        ("rg foo ./inputs", "Bash"),
        ('ls "D:/gitrepos/ai-eval-examples/.venv" 2>&1', "Bash"),  # recorded in Eval 01, run 10
        ("Get-ChildItem D:\\", "PowerShell"),
    ],
)
def test_other_shell_forms_are_not_above_the_repo(tmp_path, command, tool):
    assert above(shell(tmp_path, command, tool=tool)) == []


def test_grep_and_glob_elsewhere_are_not_above_the_repo(tmp_path):
    assert above(trial_with(tmp_path, "Grep", pattern="x", path="D:/gitrepos/other")) == []
    assert above(trial_with(tmp_path, "Grep", pattern="x", path="C:/gitrepos")) == []
    assert above(trial_with(tmp_path, "Glob", pattern="inputs/**/*.py")) == []
    assert above(trial_with(tmp_path, "Glob", pattern="**/rubric.md")) == []
    assert above(trial_with(tmp_path, "Glob", pattern="D:/gitrepos/other/**/*.md")) == []


def test_without_a_repo_root_the_rule_is_off(tmp_path):
    assert check_fair_play(shell(tmp_path, "grep -r rubric D:/gitrepos")) == []
    assert above(shell(tmp_path, "grep -r rubric D:/gitrepos"), repo_root=None) == []


def test_a_repo_root_with_no_ancestors_turns_the_rule_off(tmp_path):
    assert above(shell(tmp_path, "grep -r rubric D:/"), repo_root=PureWindowsPath("D:/")) == []


def test_a_concrete_repo_root_is_resolved_before_its_ancestors_are_taken(tmp_path):
    parent = tmp_path.resolve() / "a"
    t = trial_with(tmp_path, "Grep", pattern="x", path=str(parent))
    assert tags(above(t, repo_root=parent / "repo")) == [TAG_ANSWER_KEY]
    # The repo itself is not one of its own ancestors.
    own = trial_with(tmp_path, "Grep", pattern="x", path=str(parent / "repo"))
    assert above(own, repo_root=parent / "repo") == []


def test_the_grading_rule_still_fires_with_a_repo_root(tmp_path):
    findings = above(trial_with(tmp_path, "Read", file_path=GRADING_FILE))
    assert tags(findings) == [TAG_ANSWER_KEY]
    assert "grading" in findings[0].detail


def test_one_answer_key_finding_per_trial(tmp_path):
    t = stream_trial(
        tmp_path,
        [
            tool_use("c1", "Read", file_path=GRADING_FILE),
            tool_use("c2", "Grep", pattern="x", path=REPO),
        ],
    )
    assert tags(check_fair_play(t)) == [TAG_ANSWER_KEY]


# -- fair play: repo online --------------------------------------------------


def test_webfetch_of_the_repo_is_repo_online(tmp_path):
    t = trial_with(tmp_path, "WebFetch", url="https://github.com/ZackHelms/ai-eval-examples", prompt="read it")
    findings = check_fair_play(t)
    assert tags(findings) == [TAG_REPO_ONLINE]
    assert findings[0].severity == SEVERITY_ZERO and findings[0].line == 0


def test_git_clone_of_the_repo_is_repo_online(tmp_path):
    t = shell(tmp_path, "git clone git@github.com:ZackHelms/ai-eval-examples.git")
    assert tags(check_fair_play(t)) == [TAG_REPO_ONLINE]


def test_other_github_urls_are_fine(tmp_path):
    t = trial_with(tmp_path, "WebFetch", url="https://github.com/microsoft/playwright-python", prompt="x")
    assert check_fair_play(t) == []


# -- fair play: tried to run -------------------------------------------------


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("python inputs/script.py", "Bash"),
        ("python3 script.py", "Bash"),
        (".venv/Scripts/python.exe -X utf8 inputs/script.py", "Bash"),
        (r".venv\Scripts\Python.EXE -u inputs\script.py", "PowerShell"),
        (r'& "C:\Program Files\Python312\python.exe" inputs\script.py', "PowerShell"),
        ("cd inputs && python script.py", "Bash"),
        ("cd inputs; python script.py 2>&1", "PowerShell"),
        ("python script.py | tail -20", "Bash"),
        ("py -3.12 script.py", "PowerShell"),
        ("python -Xutf8 -u script.py", "Bash"),
        ("PYTHONIOENCODING=utf-8 python script.py", "Bash"),
        ("timeout 60 python script.py", "Bash"),
        ('bash -c "cd inputs && python script.py"', "Bash"),
    ],
)
def test_running_the_script_is_tried_to_run(tmp_path, command, tool):
    findings = check_fair_play(shell(tmp_path, command, tool=tool))
    assert tags(findings) == [TAG_TRIED_TO_RUN]
    assert findings[0].severity == SEVERITY_SMELL and findings[0].line == 0


@pytest.mark.parametrize(
    "command",
    [
        "python -m py_compile script.py",
        "python -m pytest script.py",
        "python -c \"open('script.py')\"",
        'python -c "import zipfile"',
        "python -Ic \"print('script.py')\"",
        "python -X utf8 -c \"print(1)\" && cat script.py",
        "cat inputs/script.py",
        "echo python script.py",
        "python other.py",
        "python",
        "py -3.12 -m pip list",
    ],
)
def test_other_python_uses_are_not_tried_to_run(tmp_path, command):
    assert check_fair_play(shell(tmp_path, command)) == []


def test_tried_to_run_in_a_denial_counts(tmp_path):
    t = stream_trial(
        tmp_path,
        [tool_use("c1", "Read", file_path="a")],
        permission_denials=[denial("Bash", command="python inputs/script.py")],
    )
    assert tags(check_fair_play(t)) == [TAG_TRIED_TO_RUN]


def test_non_shell_tools_never_count_as_tried_to_run(tmp_path):
    t = trial_with(tmp_path, "Write", file_path="notes.md", content="python inputs/script.py")
    assert check_fair_play(t) == []


def test_findings_are_deduplicated_by_tag(tmp_path):
    t = stream_trial(
        tmp_path,
        [
            tool_use("c1", "Bash", command="python script.py"),
            tool_use("c2", "Bash", command="python script.py"),
            tool_use("c3", "WebFetch", url="https://github.com/ZackHelms/ai-eval-examples"),
            tool_use("c4", "Read", file_path=GRADING_FILE),
        ],
        permission_denials=[denial("Bash", command="python script.py")],
    )
    assert sorted(tags(check_fair_play(t))) == sorted([TAG_ANSWER_KEY, TAG_REPO_ONLINE, TAG_TRIED_TO_RUN])


def test_clean_trial_has_no_fair_play_findings(tmp_path):
    t = stream_trial(
        tmp_path,
        [
            tool_use("c1", "Read", file_path=r"C:\Users\x\trial\inputs\script.py"),
            tool_use("c2", "Edit", file_path=r"C:\Users\x\trial\inputs\script.py", old_string="a", new_string="b"),
        ],
    )
    assert check_fair_play(t) == []
    assert check_validity(t) == []
