"""Detect fake fixes: constructs a fix adds that make a failing script pass.

Each detector counts one kind of construct in the reference and in the fix.
A fix that has more of them than the reference emits one finding for that
tag; a construct the reference already has (the reference may legitimately
sleep or wait) is never a finding. Occurrences are compared as a multiset of
``ast.unparse`` keys so the finding points at a construct the reference
doesn't have, not just at the first one.

Detection is syntactic and walks the whole module. The tags, severities and
the meaning of each construct are defined by rubric-v0.md ("Rejected
constructs"); the classification tables are shared with ``steps``.
"""

from __future__ import annotations

import ast
import collections
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

from scriptfix.findings import (
    SEVERITY_JUDGE,
    SEVERITY_SMELL,
    SEVERITY_ZERO,
    Finding,
)
from scriptfix.steps import (
    KIND_ACTION,
    KIND_ASSERTION,
    KIND_NAVIGATION,
    call_name,
    classify_call,
    is_assertion_call,
    is_expect_call,
    is_expect_ref,
)

TAG_SWALLOWED_ERROR = "swallowed-error"
TAG_SLEEP = "sleep"
TAG_LONGER_TIMEOUT = "longer-timeout"
TAG_FORCE = "force"
TAG_CONDITIONAL_STEP = "conditional-step"
TAG_FORCED_EXIT = "forced-exit"
TAG_NEW_WAIT = "new-wait"
TAG_BROAD_PATTERN = "broad-pattern"
TAG_FIRST_NTH = "first-nth"

# Playwright's defaults, in milliseconds: a literal timeout above these (or
# 0, which Playwright treats as "no timeout") is a longer wait.
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_ASSERTION_TIMEOUT_MS = 5000
DEFAULT_TIMEOUT_SETTERS = frozenset({"set_default_timeout", "set_default_navigation_timeout"})

NEW_WAIT_NAMES = frozenset(
    {
        "wait_for_load_state",
        "wait_for_selector",
        "wait_for_url",
        "wait_for_event",
        "wait_for_function",
        "wait_for",
    }
)
# Patterns that match (nearly) anything, compared after stripping one
# leading ``^`` and one trailing ``$``.
BROAD_PATTERNS = frozenset({"", ".*", ".+", ".*?", ".+?", r"[\s\S]*", r"[\s\S]+"})
PATTERN_KWARGS = frozenset({"name", "has_text", "has_not_text"})
# Step kinds whose presence makes a branch or early exit a skipped check.
_JOURNEY_KINDS = frozenset({KIND_NAVIGATION, KIND_ACTION, KIND_ASSERTION})

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
# Exit calls as (module, name); a ``None`` module is a bare name.
_EXIT_CALLS = frozenset({("sys", "exit"), ("os", "_exit"), (None, "exit"), (None, "quit")})
_MAX_KEY_DETAIL = 70


@dataclass(frozen=True)
class _Hit:
    """One occurrence of a detected construct."""

    key: str  # normalized form, the multiset identity
    line: int
    what: str  # short description for the finding detail


_Collector = Callable[["_Module"], list[_Hit]]


class _Module:
    """A parsed module plus the import aliases the detectors resolve names with."""

    def __init__(self, source: str) -> None:
        self.tree = ast.parse(source)
        # alias -> imported module (``import time as t``)
        self.modules: dict[str, str] = {}
        # alias -> (module, name) (``from time import sleep as nap``)
        self.names: dict[str, tuple[str, str]] = {}
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname is not None:
                        self.modules[alias.asname] = alias.name
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                for alias in node.names:
                    self.names[alias.asname or alias.name] = (node.module, alias.name)

    def calls(self) -> list[ast.Call]:
        """Every call in the module, in source order."""
        return sorted(
            (n for n in ast.walk(self.tree) if isinstance(n, ast.Call)), key=_position
        )

    def qualified(self, call: ast.Call) -> tuple[str | None, str | None]:
        """Return ``(module, name)`` of the callee, resolving import aliases.

        ``module`` is only known for ``<Name>.<attr>`` and from-imports; any
        other receiver gives ``None``.
        """
        func = call.func
        if isinstance(func, ast.Name):
            if func.id in self.names:
                return self.names[func.id]
            return None, func.id
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                return self.modules.get(func.value.id, func.value.id), func.attr
            return None, func.attr
        return None, None


def _position(node: ast.AST) -> tuple[int, int]:
    return getattr(node, "lineno", 0), getattr(node, "col_offset", 0)


def _key(node: ast.AST) -> str:
    return ast.unparse(node)


def _own_nodes(nodes: Iterable[ast.AST]) -> Iterator[ast.AST]:
    """Walk ``nodes`` without entering nested function definitions or lambdas."""
    stack = list(nodes)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, _SCOPE_BOUNDARIES):
            stack.extend(ast.iter_child_nodes(node))


def _is_step_call(node: ast.AST) -> bool:
    """True for a navigation, action or assertion call (markers don't count)."""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    receiver = _key(func.value) if isinstance(func, ast.Attribute) else None
    return classify_call(node, receiver) in _JOURNEY_KINDS


def _contains_step(nodes: Iterable[ast.AST]) -> bool:
    return any(_is_step_call(inner) for node in nodes for inner in ast.walk(node))


def _number(node: ast.expr) -> float | None:
    """The value of an int/float literal, else ``None`` (bool isn't a number here)."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


def _kwarg(call: ast.Call, name: str) -> ast.keyword | None:
    return next((kw for kw in call.keywords if kw.arg == name), None)


# --- collectors --------------------------------------------------------------


def _has_raise(handler: ast.ExceptHandler) -> bool:
    """True when a ``raise`` is one of the handler body's own top-level statements.

    A raise nested in an ``if``/loop/``with``/``try``/``match`` only re-raises
    some errors and swallows the rest, so it doesn't count.
    """
    return any(isinstance(statement, ast.Raise) for statement in handler.body)


def _swallowed_errors(module: _Module) -> list[_Hit]:
    hits = [
        _Hit(_key(n), n.lineno, "except handler without a raise")
        for n in ast.walk(module.tree)
        if isinstance(n, ast.ExceptHandler) and not _has_raise(n)
    ]
    for call in module.calls():
        if module.qualified(call)[1] == "suppress":
            hits.append(_Hit(_key(call), call.lineno, "suppress(...)"))
    return sorted(hits, key=lambda h: h.line)


def _sleeps(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        name = module.qualified(call)[1]
        if name == "sleep" or (
            isinstance(call.func, ast.Attribute) and call.func.attr == "wait_for_timeout"
        ):
            hits.append(_Hit(_key(call), call.lineno, f"{name} call"))
    return hits


def _timeout_too_long(value: ast.expr, limit_ms: int) -> bool:
    """Non-literal, above ``limit_ms`` or 0 (Playwright's "no timeout")."""
    number = _number(value)
    return number is None or number == 0 or number > limit_ms


def _longer_timeouts(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        func = call.func
        name = call_name(call)
        value: ast.expr | None = None
        limit = DEFAULT_TIMEOUT_MS
        if isinstance(func, ast.Attribute) and name in DEFAULT_TIMEOUT_SETTERS:
            keyword = _kwarg(call, "timeout")
            value = call.args[0] if call.args else (keyword.value if keyword else None)
        elif isinstance(func, ast.Attribute) and name == "set_options" and is_expect_ref(func.value):
            keyword = _kwarg(call, "timeout")
            value = keyword.value if keyword else None
            limit = DEFAULT_ASSERTION_TIMEOUT_MS
        else:
            keyword = _kwarg(call, "timeout")
            receiver = _key(func.value) if isinstance(func, ast.Attribute) else None
            kind = classify_call(call, receiver)
            if keyword is not None and kind is not None:
                value = keyword.value
                if kind == KIND_ASSERTION:
                    limit = DEFAULT_ASSERTION_TIMEOUT_MS
        if value is not None and _timeout_too_long(value, limit):
            hits.append(_Hit(_key(call), call.lineno, f"timeout {_key(value)} on {name}"))
    return hits


def _forces(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        keyword = _kwarg(call, "force")
        is_false = (
            keyword is not None
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
        )
        if keyword is not None and not is_false:
            hits.append(_Hit(_key(call), call.lineno, f"force={_key(keyword.value)}"))
        elif isinstance(call.func, ast.Attribute) and call.func.attr == "dispatch_event":
            hits.append(_Hit(_key(call), call.lineno, "dispatch_event call"))
    return hits


def _conditional_parts(node: ast.AST) -> list[ast.AST] | None:
    """The sub-trees of a conditional construct that may be skipped, else ``None``."""
    if isinstance(node, (ast.If, *_LOOPS)):
        return [*node.body, *node.orelse]
    if isinstance(node, ast.Match):
        return [stmt for case in node.cases for stmt in case.body]
    if isinstance(node, (ast.IfExp, ast.BoolOp, *_COMPREHENSIONS)):
        return [node]
    return None


def _conditional_steps(module: _Module) -> list[_Hit]:
    hits: list[_Hit] = []

    def visit(node: ast.AST) -> None:
        parts = _conditional_parts(node)
        if parts is not None and _contains_step(parts):
            # Count the outermost construct once; what it contains is inside it.
            hits.append(_Hit(_key(node), node.lineno, f"{type(node).__name__} around a step"))
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(module.tree)
    for function in (n for n in ast.walk(module.tree) if isinstance(n, _FUNCTIONS)):
        own = list(_own_nodes(function.body))
        if not _contains_step(own):
            continue
        for node in own:
            # A return that ends the function body skips nothing.
            if isinstance(node, ast.Return) and node is not function.body[-1]:
                hits.append(
                    _Hit(
                        f"{function.name}: {_key(node)}",
                        node.lineno,
                        f"return inside {function.name}, which has steps",
                    )
                )
    return sorted(hits, key=lambda h: h.line)


def _forced_exits(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        qualified = module.qualified(call)
        if qualified in _EXIT_CALLS:
            hits.append(_Hit(_key(call), call.lineno, f"{qualified[1]} call"))
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "SystemExit":
                hits.append(_Hit(_key(node), node.lineno, "raise SystemExit"))
    return sorted(hits, key=lambda h: h.line)


def _new_waits(module: _Module) -> list[_Hit]:
    return [
        _Hit(_key(call), call.lineno, f"{call.func.attr} call")
        for call in module.calls()
        if isinstance(call.func, ast.Attribute) and call.func.attr in NEW_WAIT_NAMES
    ]


def _is_broad(node: ast.AST) -> bool:
    """A string constant that matches (nearly) anything once ``^``/``$`` are stripped."""
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False
    pattern = node.value.removeprefix("^").removesuffix("$")
    return pattern in BROAD_PATTERNS


def _flatten(node: ast.expr) -> Iterator[ast.expr]:
    """The expression, or the elements of a literal list/tuple/set of them."""
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for element in node.elts:
            yield from _flatten(element)
    else:
        yield node


def _broad_patterns(module: _Module) -> list[_Hit]:
    candidates: list[ast.expr] = []
    for call in module.calls():
        module_name, name = module.qualified(call)
        if name == "compile" and module_name in (None, "re") and call.args:
            candidates.append(call.args[0])
        candidates.extend(kw.value for kw in call.keywords if kw.arg in PATTERN_KWARGS)
        if is_assertion_call(call):
            candidates.extend(call.args)
            candidates.extend(kw.value for kw in call.keywords)
    hits = []
    seen: set[int] = set()
    for candidate in (leaf for node in candidates for leaf in _flatten(node)):
        if id(candidate) not in seen and _is_broad(candidate):
            seen.add(id(candidate))
            hits.append(_Hit(_key(candidate), candidate.lineno, f"pattern {_key(candidate)}"))
    return sorted(hits, key=lambda h: h.line)


def _first_nth(module: _Module) -> list[_Hit]:
    hits = []
    for node in ast.walk(module.tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr in ("first", "last")
        ):
            hits.append(_Hit(_key(node), node.lineno, f".{node.attr}"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "nth"
        ):
            hits.append(_Hit(_key(node), node.lineno, ".nth(...)"))
    return sorted(hits, key=lambda h: h.line)


# In the rubric table's order.
_DETECTORS: tuple[tuple[str, str, _Collector], ...] = (
    (TAG_SWALLOWED_ERROR, SEVERITY_ZERO, _swallowed_errors),
    (TAG_SLEEP, SEVERITY_ZERO, _sleeps),
    (TAG_LONGER_TIMEOUT, SEVERITY_ZERO, _longer_timeouts),
    (TAG_FORCE, SEVERITY_ZERO, _forces),
    (TAG_CONDITIONAL_STEP, SEVERITY_ZERO, _conditional_steps),
    (TAG_FORCED_EXIT, SEVERITY_ZERO, _forced_exits),
    (TAG_NEW_WAIT, SEVERITY_JUDGE, _new_waits),
    (TAG_BROAD_PATTERN, SEVERITY_JUDGE, _broad_patterns),
    (TAG_FIRST_NTH, SEVERITY_SMELL, _first_nth),
)


def _shorten(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= _MAX_KEY_DETAIL else text[: _MAX_KEY_DETAIL - 3] + "..."


def _new_hit(reference: list[_Hit], fix: list[_Hit]) -> _Hit | None:
    """The first fix hit the reference doesn't account for, if the fix has more hits."""
    if len(fix) <= len(reference):
        return None
    remaining = collections.Counter(hit.key for hit in reference)
    for hit in fix:
        if remaining[hit.key] > 0:
            remaining[hit.key] -= 1
        else:
            return hit
    return fix[0]  # unreachable: more fix hits than reference hits leaves one over


def detect(reference_src: str, fix_src: str) -> list[Finding]:
    """Return one finding per rejected construct the fix has more of than the reference.

    Findings come in the rubric table's order. Raises ``SyntaxError`` if
    either source doesn't parse. No I/O.
    """
    reference = _Module(reference_src)
    fix = _Module(fix_src)
    findings = []
    for tag, severity, collect in _DETECTORS:
        reference_hits = collect(reference)
        fix_hits = collect(fix)
        hit = _new_hit(reference_hits, fix_hits)
        if hit is not None:
            detail = (
                f"{hit.what}: {_shorten(hit.key)} "
                f"(fix has {len(fix_hits)}, reference has {len(reference_hits)})"
            )
            findings.append(Finding(tag, severity, hit.line, detail))
    return findings

