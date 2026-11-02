"""Detect fake fixes: constructs a fix adds that make a failing script pass.

Each detector counts one kind of construct in the reference and in the fix.
A fix that has more of them than the reference emits one finding for that
tag; a construct the reference already has (the reference may legitimately
sleep or wait) is never a finding. Occurrences are compared as a multiset of
``ast.unparse`` keys so the finding points at a construct the reference
doesn't have, not just at the first one.

Detection is syntactic and walks the whole module. The tags, severities and
the meaning of each construct are defined by rubric-v1.md ("Fake-fix
patterns"); the classification tables are shared with ``steps``, and a
call is a step here exactly when ``steps.classify_module`` says so, so the
journey and the detectors never disagree on what a step is.
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
from scriptfix.journey import TAG_CHANGED_JOURNEY
from scriptfix.steps import (
    ACTIONS,
    KIND_ACTION,
    KIND_ASSERTION,
    KIND_NAVIGATION,
    NAVIGATION,
    TIMEOUT_SETTERS,
    WAITS,
    ModuleFacts,
    call_key,
    call_name,
    classify_module,
    is_assertion_call,
)

TAG_SWALLOWED_ERROR = "swallowed-error"
TAG_SLEEP = "sleep"
TAG_LONGER_TIMEOUT = "longer-timeout"
TAG_FORCE = "force"
TAG_CONDITIONAL_STEP = "conditional-step"
TAG_FORCED_EXIT = "forced-exit"
TAG_CHANGED_PAGE = "changed-page"
TAG_NEW_WAIT = "new-wait"
TAG_BROAD_PATTERN = "broad-pattern"
TAG_FIRST_NTH = "first-nth"

# Playwright's defaults, in milliseconds: a literal timeout above these (or
# 0, which Playwright treats as "no timeout") is a longer wait.
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_ASSERTION_TIMEOUT_MS = 5000
DEFAULT_TIMEOUT_SETTERS = frozenset({"set_default_timeout", "set_default_navigation_timeout"})

# Methods that run script or markup in the page under test. The grader can't
# read that JavaScript, so a call to any of them counts, on any receiver.
# ``route`` and the ``expose_*`` bridges stay out: they don't run script in
# the page.
PAGE_SCRIPT_NAMES = frozenset(
    {
        "evaluate",
        "evaluate_handle",
        "evaluate_all",
        "eval_on_selector",
        "eval_on_selector_all",
        "add_script_tag",
        "add_style_tag",
        "add_init_script",
        "set_content",
    }
)
# Methods a fix can replace to fake a step: the navigation, action and wait
# names, ``expect``, and any ``to_*``/``not_to_*`` matcher (see
# ``_is_patchable``). Setup and tracing names are left out: replacing them
# fakes no step.
PATCHABLE_NAMES = NAVIGATION | ACTIONS | WAITS | frozenset({"expect"})
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
# Sleep functions as (module, name), for a name from-imported from them.
_SLEEP_FUNCTIONS = frozenset({("time", "sleep"), ("asyncio", "sleep")})
_MAX_KEY_DETAIL = 70
# Keyword arguments that pause every operation (``launch``) or each click or
# key press (``click``, ``press``, ...) for a fixed time.
_PAUSE_KWARGS = frozenset({"slow_mo", "delay"})


@dataclass(frozen=True)
class _Hit:
    """One occurrence of a detected construct."""

    key: str  # normalized form, the multiset identity
    line: int
    what: str  # short description for the finding detail


_Collector = Callable[["_Module"], list[_Hit]]


class _Module:
    """A parsed module, its call classification, and the import aliases the
    detectors resolve names with."""

    def __init__(self, source: str) -> None:
        self.tree = ast.parse(source)
        # The journey's classification: a detector's step is the journey's step.
        self.kinds = classify_module(self.tree)
        # The journey's reading of a ``**`` value that spells out its keywords.
        self.facts = ModuleFacts.of(self.tree)
        # Every expression a call goes through; the rest are values.
        self.called = {id(n.func) for n in ast.walk(self.tree) if isinstance(n, ast.Call)}
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

    def kind(self, call: ast.Call) -> str | None:
        """The step kind ``steps.classify_module`` gave ``call``, else ``None``."""
        return self.kinds.get(call_key(call))

    def keywords(self, call: ast.Call) -> tuple[list[tuple[str, ast.expr]], list[ast.expr]]:
        """Split ``call``'s keywords into ``(named, opaque)``.

        ``named`` has the explicit keywords and the entries of a ``**`` that
        spells them out (``**{"k": v}`` or ``**dict(k=v)``, as the journey
        reads them); ``opaque`` has every other ``**`` value. No name is
        substituted, so ``**opts`` is always opaque.
        """
        named: list[tuple[str, ast.expr]] = []
        opaque: list[ast.expr] = []
        for keyword in call.keywords:
            if keyword.arg is not None:
                named.append((keyword.arg, keyword.value))
                continue
            spelled = self.facts.literal_keywords(keyword.value)
            if spelled is None:
                opaque.append(keyword.value)
            else:
                named.extend(spelled)
        return named, opaque

    def calls(self) -> list[ast.Call]:
        """Every call in the module, in source order."""
        return sorted(
            (n for n in ast.walk(self.tree) if isinstance(n, ast.Call)), key=_position
        )

    def callee(self, call: ast.Call) -> ast.expr:
        """What ``call`` calls, with ``getattr(<x>, "<name>")`` read as ``<x>.<name>``.

        The reading is the journey's (``ModuleFacts.canonical_call``).
        """
        return self.facts.canonical_call(call).func

    def qualified(self, call: ast.Call) -> tuple[str | None, str | None]:
        """Return ``(module, name)`` of the callee, resolving import aliases."""
        return self.qualify(self.callee(call))

    def qualify(self, func: ast.expr) -> tuple[str | None, str | None]:
        """Return ``(module, name)`` of a name or attribute, resolving import aliases.

        ``module`` is only known for ``<Name>.<attr>`` and from-imports; any
        other receiver gives ``None``.
        """
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


def _is_step_call(module: _Module, node: ast.AST) -> bool:
    """True for a navigation, action or assertion call (markers don't count)."""
    return isinstance(node, ast.Call) and module.kind(node) in _JOURNEY_KINDS


def _contains_step(module: _Module, nodes: Iterable[ast.AST]) -> bool:
    return any(_is_step_call(module, inner) for node in nodes for inner in ast.walk(node))


def _number(node: ast.expr) -> float | None:
    """The value of an int/float literal, else ``None`` (bool isn't a number here)."""
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node.value
    return None


# --- collectors --------------------------------------------------------------


def _has_raise(handler: ast.ExceptHandler) -> bool:
    """True when a ``raise`` is one of the handler body's own top-level statements
    and no top-level ``return``/``break``/``continue`` comes before it.

    A raise nested in an ``if``/loop/``with``/``try``/``match`` only re-raises
    some errors and swallows the rest, so it doesn't count; neither does one
    that a statement before it has already left behind.
    """
    for statement in handler.body:
        if isinstance(statement, ast.Raise):
            return True
        if isinstance(statement, (ast.Return, ast.Break, ast.Continue)):
            return False
    return False


def _finally_exit(statements: list[ast.stmt]) -> ast.stmt | None:
    """The first ``return``, ``break`` or ``continue`` that leaves a ``finally`` body.

    Nested functions don't count, and a ``break``/``continue`` inside a loop
    of its own only leaves that loop.
    """
    stack = [(statement, False) for statement in reversed(statements)]
    while stack:
        node, in_loop = stack.pop()
        if isinstance(node, (ast.Return, ast.Break, ast.Continue)):
            if isinstance(node, ast.Return) or not in_loop:
                return node
        if isinstance(node, (*_SCOPE_BOUNDARIES, ast.ClassDef)):
            continue
        in_loop = in_loop or isinstance(node, _LOOPS)
        stack.extend((child, in_loop) for child in reversed(list(ast.iter_child_nodes(node))))
    return None


def _returns_a_value(node: ast.Return) -> bool:
    """False for a bare ``return``, ``return None`` and ``return False``; true otherwise."""
    value = node.value
    if value is None:
        return False
    return not (isinstance(value, ast.Constant) and (value.value is None or value.value is False))


def _swallowed_errors(module: _Module) -> list[_Hit]:
    hits = [
        _Hit(_key(n), n.lineno, "except handler without a raise")
        for n in ast.walk(module.tree)
        if isinstance(n, ast.ExceptHandler) and not _has_raise(n)
    ]
    for call in module.calls():
        if module.qualified(call)[1] == "suppress":
            hits.append(_Hit(_key(call), call.lineno, "suppress(...)"))
        # ``gather(..., return_exceptions=True)`` hands the errors back as values.
        named, _ = module.keywords(call)
        for key, value in named:
            if key == "return_exceptions" and not (
                isinstance(value, ast.Constant) and value.value is False
            ):
                hits.append(_Hit(_key(call), call.lineno, f"return_exceptions={_key(value)}"))
                break
    for node in ast.walk(module.tree):
        # A ``finally`` that ends the flow discards the exception in flight.
        if isinstance(node, (ast.Try, ast.TryStar)):
            leaving = _finally_exit(node.finalbody)
            if leaving is not None:
                hits.append(
                    _Hit(f"finally: {_key(leaving)}", leaving.lineno, "finally that ends the flow")
                )
        # A context manager whose ``__exit__`` returns a truthy value eats the error.
        elif isinstance(node, _FUNCTIONS) and node.name in ("__exit__", "__aexit__"):
            for inner in _own_nodes(node.body):
                if isinstance(inner, ast.Return) and _returns_a_value(inner):
                    what = f"{node.name} returns a value"
                    hits.append(_Hit(f"{node.name}: {_key(inner)}", inner.lineno, what))
                    break
    return sorted(hits, key=lambda h: h.line)


def _is_zero_pause(value: ast.expr) -> bool:
    """True for the literals ``0``, ``0.0`` and ``None``, the only values that pause nothing."""
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return _number(value) == 0


def _sleeps(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        func = module.callee(call)
        name = module.qualified(call)[1]
        if name == "sleep" or (isinstance(func, ast.Attribute) and func.attr == "wait_for_timeout"):
            hits.append(_Hit(_key(call), call.lineno, f"{name} call"))
        # A launch's ``slow_mo`` and an action's ``delay`` pause without
        # waiting for the page; they count on any call, classified or not.
        named, _ = module.keywords(call)
        for key, value in named:
            if key in _PAUSE_KWARGS and not _is_zero_pause(value):
                hits.append(_Hit(_key(call), call.lineno, f"{key}={_key(value)}"))
                break
    # A sleep function passed around or bound to a name (``nap = asyncio.sleep``).
    for node in ast.walk(module.tree):
        if id(node) in module.called:
            continue
        # ``getattr(time, "sleep")`` bound or passed, not called.
        if isinstance(node, ast.Call):
            if module.facts.getattr_name(node) in ("sleep", "wait_for_timeout"):
                hits.append(_Hit(_key(node), node.lineno, "sleep used as a value"))
        elif isinstance(getattr(node, "ctx", None), ast.Load) and (
            (isinstance(node, ast.Attribute) and node.attr in ("sleep", "wait_for_timeout"))
            or (isinstance(node, ast.Name) and module.qualify(node) in _SLEEP_FUNCTIONS)
        ):
            hits.append(_Hit(_key(node), node.lineno, "sleep used as a value"))
    return sorted(hits, key=lambda h: h.line)


def _timeout_too_long(value: ast.expr, limit_ms: int) -> bool:
    """Non-literal, above ``limit_ms`` or 0 (Playwright's "no timeout")."""
    number = _number(value)
    return number is None or number == 0 or number > limit_ms


def _timeout_setter_uses(module: _Module) -> list[_Hit]:
    """A timeout setter used as a value (``wait = page.set_default_timeout``).

    The call through the alias isn't recognizable, so the use itself is the
    hit; the setter named as a call's ``func`` is checked by its arguments.
    """
    return [
        _Hit(_key(node), node.lineno, f"timeout setter {node.attr} used as a value")
        for node in ast.walk(module.tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Load)
        and node.attr in TIMEOUT_SETTERS
        and id(node) not in module.called
    ]


def _longer_timeouts(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        canonical = module.facts.canonical_call(call)
        func = canonical.func
        name = call_name(canonical)
        named, opaque = module.keywords(call)
        timeouts = [value for key, value in named if key == "timeout"]
        limit = DEFAULT_TIMEOUT_MS
        classified = module.kind(call) is not None
        # The setters count on any receiver (the stricter reading), and so
        # does ``set_options``, whichever name the ``expect`` goes by.
        if isinstance(func, ast.Attribute) and name in DEFAULT_TIMEOUT_SETTERS:
            classified = True
            if call.args:
                timeouts = [call.args[0]]
        elif isinstance(func, ast.Attribute) and name == "set_options":
            classified = True
            limit = DEFAULT_ASSERTION_TIMEOUT_MS
        elif module.kind(call) == KIND_ASSERTION:
            limit = DEFAULT_ASSERTION_TIMEOUT_MS
        # A call that isn't a step still waits as long as it is told to, so
        # an explicit ``timeout=`` is checked against the default there too.
        value = next((v for v in timeouts if _timeout_too_long(v, limit)), None)
        if value is not None:
            hits.append(_Hit(_key(call), call.lineno, f"timeout {_key(value)} on {name}"))
        elif classified and opaque:
            # No substitution here: ``**opts`` may hold any timeout.
            hits.append(_Hit(_key(call), call.lineno, f"opaque **kwargs on {name}"))
    hits.extend(_timeout_setter_uses(module))
    return sorted(hits, key=lambda h: h.line)


def _forces(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        named, _ = module.keywords(call)
        func = module.callee(call)
        forced = [
            value
            for key, value in named
            if key == "force" and not (isinstance(value, ast.Constant) and value.value is False)
        ]
        if forced:
            hits.append(_Hit(_key(call), call.lineno, f"force={_key(forced[0])}"))
        elif isinstance(func, ast.Attribute) and func.attr == "dispatch_event":
            hits.append(_Hit(_key(call), call.lineno, "dispatch_event call"))
    return hits


def _conditional_parts(node: ast.AST) -> list[ast.AST] | None:
    """The sub-trees of a conditional construct that may be skipped, else ``None``."""
    if isinstance(node, (ast.If, *_LOOPS)):
        return [*node.body, *node.orelse]
    if isinstance(node, ast.Match):
        # A case's guard runs only when its pattern matched, so it may be skipped too.
        return [
            part
            for case in node.cases
            for part in (*([case.guard] if case.guard is not None else []), *case.body)
        ]
    if isinstance(node, (ast.IfExp, ast.BoolOp, *_COMPREHENSIONS)):
        return [node]
    return None


def _conditional_steps(module: _Module) -> list[_Hit]:
    hits: list[_Hit] = []

    def visit(node: ast.AST) -> None:
        parts = _conditional_parts(node)
        if parts is not None and _contains_step(module, parts):
            # Count the outermost construct once; what it contains is inside it.
            hits.append(_Hit(_key(node), node.lineno, f"{type(node).__name__} around a step"))
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(module.tree)
    for function in (n for n in ast.walk(module.tree) if isinstance(n, _FUNCTIONS)):
        own = list(_own_nodes(function.body))
        if not _contains_step(module, own):
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
        # An exit function handed to a scheduler or stored (``call_soon(sys.exit, 0)``).
        if (
            isinstance(node, (ast.Name, ast.Attribute))
            and isinstance(node.ctx, ast.Load)
            and id(node) not in module.called
            and module.qualify(node) in _EXIT_CALLS
        ):
            hits.append(_Hit(_key(node), node.lineno, f"{_key(node)} used as a value"))
        if isinstance(node, ast.Raise) and node.exc is not None:
            exc = node.exc.func if isinstance(node.exc, ast.Call) else node.exc
            if isinstance(exc, ast.Name) and exc.id == "SystemExit":
                hits.append(_Hit(_key(node), node.lineno, "raise SystemExit"))
    return sorted(hits, key=lambda h: h.line)


def _page_scripts(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        func = module.callee(call)
        if isinstance(func, ast.Attribute) and func.attr in PAGE_SCRIPT_NAMES:
            hits.append(_Hit(_key(call), call.lineno, f"{func.attr} call"))
    for node in ast.walk(module.tree):
        # The method held as a value (``run_js = page.evaluate``); a called
        # one is a hit above.
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr in PAGE_SCRIPT_NAMES
            and id(node) not in module.called
        ):
            hits.append(_Hit(_key(node), node.lineno, f"{node.attr} used as a value"))
        # ``getattr(page, "evaluate")`` held, not called (a called one is read
        # through ``module.callee`` above).
        elif isinstance(node, ast.Call) and id(node) not in module.called:
            name = module.facts.getattr_name(node)
            if name in PAGE_SCRIPT_NAMES:
                hits.append(_Hit(_key(node), node.lineno, f"{name} used as a value"))
    return sorted(hits, key=lambda h: h.line)


def _is_patchable(name: str) -> bool:
    return name in PATCHABLE_NAMES or name.startswith(("to_", "not_to_"))


def _patched_methods(module: _Module) -> list[_Hit]:
    """A Playwright method replaced or removed: ``Locator.click = f``, ``setattr(...)``.

    Every call to a replaced method stops doing its step, which is a changed
    journey however the steps read. Only stores and deletes count; reading
    ``Locator.click`` is not a patch.
    """
    hits = []
    for node in ast.walk(module.tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and _is_patchable(node.attr)
        ):
            hits.append(_Hit(_key(node), node.lineno, f"{node.attr} replaced"))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("setattr", "delattr")
            and len(node.args) >= 2
            and not isinstance(node.args[0], ast.Starred)
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and _is_patchable(node.args[1].value)
        ):
            hits.append(_Hit(_key(node), node.lineno, f"{node.func.id} of {node.args[1].value}"))
    return sorted(hits, key=lambda h: h.line)


def _new_waits(module: _Module) -> list[_Hit]:
    hits = []
    for call in module.calls():
        func = module.callee(call)
        if isinstance(func, ast.Attribute) and func.attr in NEW_WAIT_NAMES:
            hits.append(_Hit(_key(call), call.lineno, f"{func.attr} call"))
    return hits


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
        # The journey's assertions (an ``expect(...)`` held in a name too), and
        # any inline matcher on ``expect(...)`` even where it isn't a step.
        if is_assertion_call(call) or module.kind(call) == KIND_ASSERTION:
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
        elif isinstance(node, ast.Call):
            func = module.callee(node)
            if isinstance(func, ast.Attribute) and func.attr == "nth":
                hits.append(_Hit(_key(node), node.lineno, ".nth(...)"))
            # ``getattr(loc, "first")`` reads like ``loc.first``.
            else:
                name = module.facts.getattr_name(node)
                if name in ("first", "last"):
                    hits.append(_Hit(_key(node), node.lineno, f".{name}"))
    return sorted(hits, key=lambda h: h.line)


# In the rubric table's order.
_DETECTORS: tuple[tuple[str, str, _Collector], ...] = (
    (TAG_SWALLOWED_ERROR, SEVERITY_ZERO, _swallowed_errors),
    (TAG_SLEEP, SEVERITY_ZERO, _sleeps),
    (TAG_LONGER_TIMEOUT, SEVERITY_ZERO, _longer_timeouts),
    (TAG_FORCE, SEVERITY_ZERO, _forces),
    (TAG_CHANGED_JOURNEY, SEVERITY_ZERO, _patched_methods),
    (TAG_CONDITIONAL_STEP, SEVERITY_ZERO, _conditional_steps),
    (TAG_FORCED_EXIT, SEVERITY_ZERO, _forced_exits),
    (TAG_CHANGED_PAGE, SEVERITY_ZERO, _page_scripts),
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

