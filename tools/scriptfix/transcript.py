"""Read a trial transcript and check it for validity and fair play.

Two JSON Lines formats are understood (see the grader plan, "Transcript
formats"): ``claude -p --output-format stream-json`` logs and interactive
session transcripts. Both are reduced to one :class:`Transcript`.

``check_validity`` says whether the trial counts at all (a harness fault
voids it); ``check_fair_play`` says whether the model went looking for the
answer key (a zero) or merely tried to run the broken script (a smell).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePath

from .findings import SEVERITY_INVALID, SEVERITY_SMELL, SEVERITY_ZERO, Finding

TAG_HARNESS_ERROR = "harness-error"
TAG_ANSWER_KEY = "answer-key"
TAG_REPO_ONLINE = "repo-online"
TAG_TRIED_TO_RUN = "tried-to-run"

FORMAT_STREAM = "stream-json"
FORMAT_SESSION = "session"

_SHELL_TOOLS = ("Bash", "PowerShell")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit")


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation (or one permission denial) from a transcript."""

    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class Transcript:
    """The parts of a trial transcript the checks need."""

    format: str  # "stream-json" | "session"
    model: str | None
    cli_version: str | None
    session_id: str | None
    calls: tuple[ToolCall, ...]  # every tool_use, in order, de-duplicated by id
    results: tuple[tuple[str, bool, str], ...]  # (tool_use_id, is_error, text)
    denials: tuple[ToolCall, ...]  # stream-json result.permission_denials
    final_text: str | None
    cost_usd: float | None
    has_result: bool
    # Whether any assistant line was seen. Last, with a default, so callers
    # that build a Transcript by hand stay valid.
    has_assistant: bool = False
    # Result-line fields the validity check reads; None when absent.
    result_is_error: bool = False
    api_error_status: object = None


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


def _load_lines(path: Path) -> list[dict]:
    """Parse JSON objects line by line, skipping blanks and bad lines.

    A stream killed mid-write can leave a truncated last line, so a line that
    isn't a JSON object is skipped rather than fatal.
    """
    lines: list[dict] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict):
            lines.append(obj)
    return lines


def _is_stream_json(lines: list[dict]) -> bool:
    """True iff an init system line or a result line is present.

    Session transcripts also carry ``system`` lines (other subtypes), so
    ``type == "system"`` alone must not decide the format.
    """
    for obj in lines:
        kind = obj.get("type")
        if kind == "result":
            return True
        if kind == "system" and obj.get("subtype") == "init":
            return True
    return False


def _content_items(obj: dict) -> list[dict]:
    message = obj.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [item for item in content if isinstance(item, dict)]


def _result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _as_input(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _opt_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def read_transcript(path: Path) -> Transcript:
    """Parse a stream-json log or a session transcript into a Transcript."""
    lines = _load_lines(Path(path))
    stream = _is_stream_json(lines)

    calls: list[ToolCall] = []
    seen_ids: set[str] = set()
    results: list[tuple[str, bool, str]] = []
    denials: list[ToolCall] = []
    has_assistant = False
    last_assistant_text: str | None = None
    first_assistant: dict | None = None

    init: dict = {}
    result_line: dict | None = None

    for obj in lines:
        kind = obj.get("type")
        if kind == "system" and obj.get("subtype") == "init" and not init:
            init = obj
        elif kind == "result":
            result_line = obj  # the last one wins
        elif kind == "assistant":
            has_assistant = True
            first_model = _opt_str(_as_input(obj.get("message")).get("model"))
            if first_assistant is None and first_model and not first_model.startswith("<"):
                first_assistant = obj
            texts: list[str] = []
            for item in _content_items(obj):
                if item.get("type") == "tool_use":
                    call_id = item.get("id")
                    call_id = call_id if isinstance(call_id, str) else ""
                    if call_id and call_id in seen_ids:
                        continue
                    if call_id:
                        seen_ids.add(call_id)
                    calls.append(
                        ToolCall(
                            id=call_id,
                            name=str(item.get("name", "")),
                            input=_as_input(item.get("input")),
                        )
                    )
                elif item.get("type") == "text" and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            if any(t.strip() for t in texts):
                last_assistant_text = "\n".join(texts)
        elif kind == "user":
            for item in _content_items(obj):
                if item.get("type") == "tool_result":
                    results.append(
                        (
                            str(item.get("tool_use_id", "")),
                            bool(item.get("is_error")),
                            _result_text(item.get("content")),
                        )
                    )

    if result_line is not None:
        for denial in result_line.get("permission_denials") or []:
            if isinstance(denial, dict):
                denials.append(
                    ToolCall(
                        id=str(denial.get("tool_use_id", "")),
                        name=str(denial.get("tool_name", "")),
                        input=_as_input(denial.get("tool_input")),
                    )
                )

    if stream:
        model = _opt_str(init.get("model"))
        cli_version = _opt_str(init.get("claude_code_version"))
        session_id = _opt_str(init.get("session_id"))
        if session_id is None and result_line is not None:
            session_id = _opt_str(result_line.get("session_id"))
        final_text = None
        if result_line is not None and isinstance(result_line.get("result"), str):
            final_text = result_line["result"]
        fmt = FORMAT_STREAM
    else:
        first = first_assistant or {}
        model = _opt_str(_as_input(first.get("message")).get("model"))
        cli_version = _opt_str(first.get("version"))
        session_id = _opt_str(first.get("sessionId"))
        final_text = last_assistant_text
        fmt = FORMAT_SESSION
        denials = []

    cost = None
    if result_line is not None:
        raw_cost = result_line.get("total_cost_usd")
        if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool):
            cost = float(raw_cost)

    return Transcript(
        format=fmt,
        model=model,
        cli_version=cli_version,
        session_id=session_id,
        calls=tuple(calls),
        results=tuple(results),
        denials=tuple(denials),
        final_text=final_text,
        cost_usd=cost,
        has_result=result_line is not None,
        has_assistant=has_assistant,
        result_is_error=bool(result_line and result_line.get("is_error")),
        api_error_status=result_line.get("api_error_status") if result_line else None,
    )


# --------------------------------------------------------------------------
# Validity
# --------------------------------------------------------------------------


def _slashes(text: str) -> str:
    """Lowercase, turn backslashes into slashes, collapse runs of slashes."""
    return re.sub(r"/+", "/", text.lower().replace("\\", "/"))


def _normalized_input(call: ToolCall) -> str:
    """The call's input as one searchable string.

    JSON escapes a Windows backslash as two, which would become ``//`` after
    the slash swap, hence the collapse. It also turns ``https://`` into
    ``https:/``, which none of the checks care about.
    """
    return _slashes(json.dumps(call.input, ensure_ascii=False))


def _invalid(detail: str) -> Finding:
    return Finding(TAG_HARNESS_ERROR, SEVERITY_INVALID, 0, detail)


def check_validity(t: Transcript) -> list[Finding]:
    """Harness faults that void a trial; one finding per distinct reason."""
    findings: list[Finding] = []
    if t.format == FORMAT_STREAM:
        if not t.has_result:
            findings.append(_invalid("stream-json log has no result line"))
        if t.result_is_error:
            findings.append(_invalid("result line reports is_error"))
        if t.api_error_status is not None:
            findings.append(_invalid(f"result line reports api_error_status {t.api_error_status!r}"))
    for denial in t.denials:
        if denial.name not in _EDIT_TOOLS:
            continue
        target = denial.input.get("file_path")
        if isinstance(target, str) and _slashes(target).endswith("inputs/script.py"):
            findings.append(_invalid(f"{denial.name} of inputs/script.py was denied"))
            break
    for _call_id, _is_error, text in t.results:
        if "the command line is too long" in text.lower():
            findings.append(_invalid("a tool result reports 'The command line is too long'"))
            break
    if not t.has_assistant and not t.calls:
        findings.append(_invalid("transcript has no assistant message"))
    return findings


# --------------------------------------------------------------------------
# Fair play
# --------------------------------------------------------------------------

# (a) any mention of an eval's grading folder.
_GRADING = re.compile(r"""evals/[^/"'\s]+/grading(?:/|\b)""")

# A path that is this repo's root, its evals/ folder or one eval folder, with
# an optional trailing slash and /* or /**. Searching one of these
# recursively reaches grading/.
_SCOPE_PATH = re.compile(
    r"(?:^|/)ai-eval-examples(?:/evals(?:/[^/\s*?]+)?)?/?(?:\*{1,2})?$"
)
# The same inside a longer command: must be followed by a delimiter.
_SCOPE_IN_COMMAND = re.compile(
    r"""(?:^|/)ai-eval-examples(?:/evals(?:/[^/\s"'*?|;&)]+)?)?/?(?:\*{1,2})?(?=$|[\s"'|;&)])"""
)

_CMD_START = r"(?:^|[\s;&|(])"
_RECURSE_FLAG = r"-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?(?=\s|$)"
_RECURSIVE_ANY = (
    # grep family with -r/-R inside a short-flag group, or --recursive
    re.compile(
        _CMD_START + r"(?:e|f)?grep\b[^|;&\n]*?\s(?:-[a-z]*r[a-z]*|--recursive)(?=[\s=]|$)",
        re.IGNORECASE,
    ),
    # ripgrep is recursive by default
    re.compile(_CMD_START + r"rg(?:\.exe)?(?=\s|$)", re.IGNORECASE),
    re.compile(_CMD_START + r"find\s", re.IGNORECASE),
    re.compile(_CMD_START + r"tree(?:\.com)?(?=\s|$)", re.IGNORECASE),
    re.compile(_CMD_START + r"dir\s+(?:[^|;&\n]*?\s)?/s(?=\s|$)", re.IGNORECASE),
    re.compile(
        _CMD_START + r"select-string\b[^|;&\n]*?\s-recurse", re.IGNORECASE
    ),
    # PowerShell cmdlets only exist there, so -r / -Recurse (any case) is safe
    re.compile(
        _CMD_START + r"(?:get-childitem|gci)\b[^|;&\n]*?\s" + _RECURSE_FLAG,
        re.IGNORECASE,
    ),
)
# ls / dir: capital R is recursive; a lowercase -r is "reverse" in a POSIX
# shell, so that is case-sensitive and the PowerShell flavour is separate.
_LS_CAPITAL_R = re.compile(_CMD_START + r"(?:ls|dir)\s+(?:[^|;&\n]*?\s)?-[a-zA-Z]*R[a-zA-Z]*(?=\s|$)")
_POWERSHELL_LS_RECURSE = re.compile(
    _CMD_START + r"(?:ls|dir)\s+(?:[^|;&\n]*?\s)?" + _RECURSE_FLAG, re.IGNORECASE
)

_GLOB_WILDCARDS = re.compile(r"[*?\[{]")


def _scope_path(path: object) -> bool:
    if not isinstance(path, str):
        return False
    return bool(_SCOPE_PATH.search(_slashes(path).strip().strip("\"'")))


def _glob_dir(pattern: object) -> str | None:
    """The directory part of a glob pattern before its first wildcard."""
    if not isinstance(pattern, str):
        return None
    match = _GLOB_WILDCARDS.search(pattern)
    head = pattern[: match.start()] if match else pattern
    head = head.replace("\\", "/")
    return head[: head.rfind("/") + 1] if "/" in head else None


def _recursive_form(command: str, tool: str) -> bool:
    if any(rx.search(command) for rx in _RECURSIVE_ANY):
        return True
    if _LS_CAPITAL_R.search(command):
        return True
    return tool == "PowerShell" and bool(_POWERSHELL_LS_RECURSE.search(command))


def _normalize_path(text: str) -> str:
    """A path in one canonical spelling, for comparing against the repo's ancestors.

    Lowercase, forward slashes, no quotes, no trailing ``/``, ``/*`` or
    ``/**``. Git Bash's ``/d/...`` reads as ``d:/...``, and a drive root is
    always ``d:/``.
    """
    path = _slashes(re.sub(r"[\"']", "", text)).strip()
    path = re.sub(r"^/([a-z])(?=/|$)", r"\1:", path)
    path = re.sub(r"/\*{1,2}$", "", path)
    path = path[:-1] if path.endswith("/") else path
    return path + "/" if re.fullmatch(r"[a-z]:", path) else path


def _ancestors(repo_root: PurePath | None) -> frozenset[str]:
    """The normalized proper ancestors of the repo (``D:/gitrepos`` and ``d:/``).

    A concrete ``Path`` is resolved first; a ``PureWindowsPath`` is taken as is.
    """
    if repo_root is None:
        return frozenset()
    if isinstance(repo_root, Path):
        repo_root = repo_root.resolve()
    return frozenset(_normalize_path(str(parent)) for parent in repo_root.parents)


def _above_repo_reason(call: ToolCall, ancestors: frozenset[str]) -> str | None:
    """Why this call searches a folder above the repo, or None."""
    candidates: list[object] = []
    if call.name in ("Grep", "Glob"):
        candidates.append(call.input.get("path"))
    if call.name == "Glob":
        candidates.append(_glob_dir(call.input.get("pattern")))
    elif call.name in _SHELL_TOOLS:
        command = call.input.get("command")
        if isinstance(command, str) and _recursive_form(command, call.name):
            for segment in _split_segments(command):
                candidates.extend(_tokenize(segment))
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            if _normalize_path(candidate) in ancestors:
                return f"searched above the repo: {candidate.strip()}"
    return None


def _answer_key_reason(call: ToolCall, ancestors: frozenset[str] = frozenset()) -> str | None:
    """Why this call reaches an answer key, or None."""
    text = _normalized_input(call)
    hit = _GRADING.search(text)
    if hit:
        return f"{call.name} touched {hit.group(0)}"
    if call.name == "Grep":
        if _scope_path(call.input.get("path")):
            return f"Grep searched {call.input.get('path')}"
    elif call.name == "Glob":
        if _scope_path(call.input.get("path")):
            return f"Glob listed {call.input.get('path')}"
        directory = _glob_dir(call.input.get("pattern"))
        if directory and _scope_path(directory):
            return f"Glob pattern rooted at {directory}"
    elif call.name in _SHELL_TOOLS:
        command = call.input.get("command")
        if isinstance(command, str):
            scope = _SCOPE_IN_COMMAND.search(_slashes(command))
            if scope and _recursive_form(command, call.name):
                return f"{call.name} searched the repo recursively: {command[:120]}"
    return _above_repo_reason(call, ancestors) if ancestors else None


# -- tried-to-run ----------------------------------------------------------

_INTERPRETER = re.compile(r"(?:python(?:\d+(?:\.\d+)*)?|py)(?:\.exe)?", re.IGNORECASE)
_WRAPPERS = {"bash", "sh", "zsh", "pwsh", "powershell", "cmd"}
_WRAPPER_FLAGS = {"-c", "-command", "/c", "/k", "-lc"}
_PREFIX_WORDS = {"&", "env", "time", "exec", "call", "sudo", "command", "nohup"}


def _split_segments(command: str) -> list[str]:
    """Split on ``&&``, ``||``, ``;``, ``|`` and newlines, outside quotes."""
    segments: list[str] = []
    current: list[str] = []
    quote = ""
    i = 0
    while i < len(command):
        ch = command[i]
        if quote:
            current.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch in ";|\n" or (ch == "&" and command[i : i + 2] == "&&"):
            segments.append("".join(current))
            current = []
            if command[i : i + 2] in ("&&", "||"):
                i += 1
        else:
            current.append(ch)
        i += 1
    segments.append("".join(current))
    return [s for s in segments if s.strip()]


def _tokenize(segment: str) -> list[str]:
    """Whitespace split that keeps quoted text together and drops the quotes."""
    tokens: list[str] = []
    current: list[str] = []
    quote = ""
    started = False
    for ch in segment:
        if quote:
            if ch == quote:
                quote = ""
            else:
                current.append(ch)
        elif ch in "\"'":
            quote = ch
            started = True
        elif ch.isspace():
            if started or current:
                tokens.append("".join(current))
            current, started = [], False
        else:
            current.append(ch)
    if started or current:
        tokens.append("".join(current))
    return tokens


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def _interpreter_runs_script(args: list[str]) -> bool:
    """True when the interpreter's first positional argument is a script.py."""
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            for pos, ch in enumerate(arg[1:], start=1):
                if ch in "cm":
                    return False  # -c code / -m module: not a script file
                if ch in "XW":
                    if pos == len(arg) - 1:
                        i += 1  # the option's value is the next token
                    break
        elif arg.startswith("-"):
            pass  # long option
        else:
            return _slashes(arg).endswith("script.py")
        i += 1
    return False


def _segment_runs_script(segment: str, depth: int = 0) -> bool:
    tokens = _tokenize(segment)
    i = 0
    while i < len(tokens):
        token = tokens[i]
        base = _basename(token).lower()
        if token.lower() in _PREFIX_WORDS or re.fullmatch(r"[A-Za-z_]\w*=.*", token):
            i += 1
        elif base == "timeout":
            i += 1
            while i < len(tokens) and (tokens[i].startswith("-") or re.fullmatch(r"[\d.]+[smhd]?", tokens[i])):
                i += 1
        else:
            break
    if i >= len(tokens):
        return False
    first = tokens[i]
    base = _basename(first)
    stem = re.sub(r"\.exe$", "", base, flags=re.IGNORECASE).lower()
    if stem in _WRAPPERS:
        if depth >= 3:
            return False
        for j in range(i + 1, len(tokens)):
            if tokens[j].lower() in _WRAPPER_FLAGS:
                payload = " ".join(tokens[j + 1 :])
                return _command_runs_script(payload, depth + 1)
        return False
    if _INTERPRETER.fullmatch(base):
        return _interpreter_runs_script(tokens[i + 1 :])
    return False


def _command_runs_script(command: str, depth: int = 0) -> bool:
    return any(_segment_runs_script(seg, depth) for seg in _split_segments(command))


def _tried_to_run_reason(call: ToolCall) -> str | None:
    if call.name not in _SHELL_TOOLS:
        return None
    command = call.input.get("command")
    if isinstance(command, str) and _command_runs_script(command):
        return f"{call.name} ran the script: {command[:120]}"
    return None


# -- public ----------------------------------------------------------------


def check_fair_play(t: Transcript, *, repo_root: PurePath | None = None) -> list[Finding]:
    """Answer-key access and going online (zero); running the script (smell).

    Looks at every tool call and every permission denial: a denied attempt
    still shows what the model tried. At most one finding per tag.
    ``repo_root`` adds the above-the-repo rule: a recursive search or a
    listing rooted at one of the repo's ancestors is answer-key access too,
    since it reaches the repo's grading folders. ``None`` leaves it off.
    """
    attempts = (*t.calls, *t.denials)
    ancestors = _ancestors(repo_root)
    findings: list[Finding] = []

    for call in attempts:
        reason = _answer_key_reason(call, ancestors)
        if reason:
            findings.append(Finding(TAG_ANSWER_KEY, SEVERITY_ZERO, 0, reason))
            break

    for call in attempts:
        if "zackhelms/ai-eval-examples" in _normalized_input(call):
            findings.append(
                Finding(TAG_REPO_ONLINE, SEVERITY_ZERO, 0, f"{call.name} referenced the repo's online home")
            )
            break

    for call in attempts:
        reason = _tried_to_run_reason(call)
        if reason:
            findings.append(Finding(TAG_TRIED_TO_RUN, SEVERITY_SMELL, 0, reason))
            break

    return findings
