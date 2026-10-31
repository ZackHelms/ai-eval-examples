"""Replay a script in isolation and report how it ended.

The script is copied byte-for-byte into a fresh directory under the system
temp directory, never replayed inside the repo or a trial folder: a
Playwright script writes its trace next to itself. Replays are synchronous
and one at a time on purpose (CLAUDE.md load-test pin: a public site only
ever sees single replays), and are never retried.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

# How long to wait for output after the process tree has been killed.
_DRAIN_TIMEOUT_S = 10

# A traceback frame line: ``  File "<path>", line <n>, in <name>``.
_FRAME = re.compile(r'^\s*File "(?P<path>[^"\n]+)", line (?P<line>\d+)', re.MULTILINE)


@dataclass(frozen=True)
class ReplayResult:
    """How one replay ended.

    ``exit_code`` is None when the replay timed out. ``failing_line`` is the
    line of the last traceback frame inside the replayed script, or None when
    there is no such frame. ``output`` is stdout and stderr merged, whole.
    """

    exit_code: int | None
    timed_out: bool
    failing_line: int | None
    output: str


def _same_file(a: Path, b: Path) -> bool:
    """Whether two paths name the same file (case-insensitive on Windows)."""
    # realpath also expands 8.3 short names, which TEMP can contain.
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def find_failing_line(output: str, script: Path) -> int | None:
    """Return the line of the last traceback frame in ``script``, else None.

    A relative frame path is resolved against the script's directory, since
    that is the replay's working directory.
    """
    found = None
    for match in _FRAME.finditer(output):
        frame = Path(match["path"])
        if not frame.is_absolute():
            frame = script.parent / frame
        if _same_file(frame, script):
            found = int(match["line"])
    return found


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill the process and everything it spawned.

    A killed Python would otherwise leave its browser (a grandchild) running.
    """
    if sys.platform == "win32":
        if process.poll() is not None:
            return  # taskkill walks the tree from a live parent only
        done = subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        if done.returncode != 0:
            # Make sure the replay itself still ends; the tree may linger.
            process.kill()
            detail = done.stdout.decode(errors="replace") + done.stderr.decode(errors="replace")
            raise RuntimeError(f"taskkill failed for pid {process.pid}: {detail.strip()}")
    else:
        os.killpg(process.pid, signal.SIGKILL)


def replay(script: Path, *, python: Path, timeout_s: int = 120) -> ReplayResult:
    """Run ``script`` once with ``python`` in a clean temp copy.

    The copy lives at ``<temp>/scriptfix/<key>/script.py`` where ``<key>`` is
    the first 12 hex digits of the script's SHA-256; the directory is
    recreated first. Runs ``python -X utf8 script.py`` (``-I`` would ignore
    PYTHONUTF8, and ``-X utf8`` is what lets ``»`` print) with the inherited
    environment. On timeout the whole process tree is killed and whatever
    output exists is returned with ``exit_code=None``.
    """
    data = Path(script).read_bytes()
    key = hashlib.sha256(data).hexdigest()[:12]
    workdir = Path(tempfile.gettempdir()) / "scriptfix" / key
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)
    copy = workdir / "script.py"
    copy.write_bytes(data)

    process = subprocess.Popen(
        [str(python), "-X", "utf8", "script.py"],
        cwd=workdir,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=sys.platform != "win32",  # own group, so killpg works
    )
    timed_out = False
    try:
        raw, _ = process.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            _kill_tree(process)
        finally:
            try:
                # communicate keeps the output read before the timeout.
                raw, _ = process.communicate(timeout=_DRAIN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                # An orphan still holds the pipe; give up on the rest.
                process.kill()
                raw = b""
    output = raw.decode("utf-8", errors="replace")
    return ReplayResult(
        exit_code=None if timed_out else process.returncode,
        timed_out=timed_out,
        failing_line=find_failing_line(output, copy),
        output=output,
    )
