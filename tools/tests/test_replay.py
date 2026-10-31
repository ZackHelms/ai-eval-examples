"""Tests for scriptfix.replay: isolation, exit handling, failing line, tree kill.

Only tiny non-Playwright scripts run here: no browser, no network.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

from scriptfix.replay import find_failing_line, replay

PYTHON = Path(sys.executable)


def write_script(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "fixture_script.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8", newline="\n")
    return path


def pid_alive(pid: int) -> bool:
    """Whether a process is running, without signalling it.

    os.kill(pid, 0) terminates the process on Windows instead of probing it.
    """
    if sys.platform == "win32":
        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.restype = ctypes.c_void_p
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False  # no such process (or already gone)
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
            return code.value == still_active
        finally:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
    import os

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A killed grandchild can linger as a zombie until its parent reaps it.
    status = subprocess.run(
        ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True, check=False
    ).stdout.strip()
    return bool(status) and not status.startswith("Z")


def test_exit_zero_captures_output(tmp_path: Path) -> None:
    script = write_script(tmp_path, 'print("done » ok")\n')
    result = replay(script, python=PYTHON, timeout_s=30)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert result.failing_line is None
    assert "done » ok" in result.output


def test_stderr_is_merged_into_output(tmp_path: Path) -> None:
    script = write_script(tmp_path, 'import sys\nprint("err text", file=sys.stderr)\n')
    result = replay(script, python=PYTHON, timeout_s=30)
    assert "err text" in result.output


def test_raise_reports_deepest_script_frame(tmp_path: Path) -> None:
    script = write_script(
        tmp_path,
        """\
        def inner():
            raise RuntimeError("boom")


        def outer():
            inner()


        outer()
        """,
    )
    result = replay(script, python=PYTHON, timeout_s=30)
    assert result.exit_code not in (0, None)
    assert result.timed_out is False
    assert result.failing_line == 2
    assert "RuntimeError: boom" in result.output


def test_failure_inside_stdlib_reports_calling_script_line(tmp_path: Path) -> None:
    script = write_script(
        tmp_path,
        """\
        import json

        print("start")
        json.loads("{")
        """,
    )
    result = replay(script, python=PYTHON, timeout_s=30)
    assert result.exit_code not in (0, None)
    assert result.failing_line == 4


def test_syntax_error_has_no_failing_line_in_traceback_frames(tmp_path: Path) -> None:
    script = write_script(tmp_path, "def broken(:\n    pass\n")
    result = replay(script, python=PYTHON, timeout_s=30)
    assert result.exit_code not in (0, None)
    # A SyntaxError is reported on a File line for the script itself.
    assert result.failing_line == 1


def test_timeout_kills_the_whole_process_tree(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = write_script(
        tmp_path,
        f"""\
        import subprocess
        import sys
        import time

        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(600)"]
        )
        with open({str(pid_file)!r}, "w") as handle:
            handle.write(str(child.pid))
        print("spawned", flush=True)
        while True:
            time.sleep(0.1)
        """,
    )
    result = replay(script, python=PYTHON, timeout_s=2)
    assert result.timed_out is True
    assert result.exit_code is None
    assert "spawned" in result.output
    grandchild = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while pid_alive(grandchild) and time.monotonic() < deadline:
        time.sleep(0.1)
    alive = pid_alive(grandchild)
    if alive:  # don't leak a sleeper if the assertion below fails
        subprocess.run(["taskkill", "/F", "/PID", str(grandchild)], check=False, capture_output=True)
    assert not alive


def test_descendant_holding_stdout_does_not_block_or_blank_the_result(tmp_path: Path) -> None:
    pid_file = tmp_path / "grandchild.pid"
    script = write_script(
        tmp_path,
        f"""\
        import subprocess
        import sys

        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        with open({str(pid_file)!r}, "w") as handle:
            handle.write(str(child.pid))
        print("marker-before-exit", flush=True)
        """,
    )
    started = time.monotonic()
    try:
        result = replay(script, python=PYTHON, timeout_s=60)
        elapsed = time.monotonic() - started
    finally:
        # Don't leak the sleeper (it outlives the script by design).
        if pid_file.exists():
            pid = pid_file.read_text(encoding="utf-8")
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", pid], check=False, capture_output=True
                )
            else:
                subprocess.run(["kill", "-9", pid], check=False, capture_output=True)
    assert result.exit_code == 0
    assert result.timed_out is False
    assert "marker-before-exit" in result.output
    assert elapsed < 10


def test_replay_runs_in_a_temp_copy_and_leaves_the_original_directory_alone(
    tmp_path: Path,
) -> None:
    script = write_script(
        tmp_path,
        """\
        import os
        from pathlib import Path

        Path("trace.zip").write_text("x")
        print(os.getcwd())
        """,
    )
    before = sorted(p.name for p in tmp_path.iterdir())
    result = replay(script, python=PYTHON, timeout_s=30)
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert result.exit_code == 0
    cwd = Path(result.output.strip()).resolve()
    scriptfix_root = (Path(tempfile.gettempdir()) / "scriptfix").resolve()
    assert scriptfix_root in cwd.parents
    assert not tmp_path.resolve() in cwd.parents


def test_each_replay_starts_clean(tmp_path: Path) -> None:
    script = write_script(
        tmp_path,
        """\
        from pathlib import Path

        marker = Path("marker.txt")
        print("seen" if marker.exists() else "fresh")
        marker.write_text("x")
        """,
    )
    assert "fresh" in replay(script, python=PYTHON, timeout_s=30).output
    assert "fresh" in replay(script, python=PYTHON, timeout_s=30).output


def test_find_failing_line_ignores_other_files_and_takes_the_last_match(tmp_path: Path) -> None:
    script = tmp_path / "script.py"
    other = tmp_path / "other.py"
    output = (
        "Traceback (most recent call last):\n"
        f'  File "{script}", line 7, in <module>\n'
        f'  File "{other}", line 99, in helper\n'
        f'  File "{script}", line 3, in inner\n'
        f'  File "{other}", line 5, in leaf\n'
    )
    assert find_failing_line(output, script) == 3
    assert find_failing_line("no frames here", script) is None


def test_find_failing_line_accepts_relative_frames_and_case_differences(tmp_path: Path) -> None:
    script = tmp_path / "script.py"
    script.write_text("", encoding="utf-8")
    assert find_failing_line('  File "script.py", line 4, in <module>\n', script) == 4
    if sys.platform == "win32":
        shouted = str(script).upper()
        assert find_failing_line(f'  File "{shouted}", line 6, in <module>\n', script) == 6
