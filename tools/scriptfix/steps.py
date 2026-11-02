"""Extract the ordered Playwright steps of a script (rubric script-fix-v1, check 2).

A *step* is one classified call: a navigation, action, assertion, wait or
setup call, or a transaction marker around a ``with`` body. Steps come out in
source order, each with its receiver and arguments normalized so that
formatting, quoting and moving a locator into a local variable don't change
them (rubric-v1.md, "Not graded: code style").

The classification tables are module-level so the detectors can reuse them,
and ``classify_module`` is the call classification the journey and the
detectors share: one walk decides both.
"""

from __future__ import annotations

import ast
import copy
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

KIND_NAVIGATION = "navigation"
KIND_ACTION = "action"
KIND_ASSERTION = "assertion"
KIND_WAIT = "wait"
KIND_SETUP = "setup"
KIND_MARKER = "marker"

# The kinds whose order is the journey (journey rule 1).
PATH_KINDS = frozenset({KIND_NAVIGATION, KIND_ACTION, KIND_MARKER})

NAVIGATION = frozenset({"goto", "reload", "go_back", "go_forward"})
ACTIONS = frozenset(
    {
        "click",
        "dblclick",
        "tap",
        "fill",
        "type",
        "press",
        "press_sequentially",
        "check",
        "uncheck",
        "set_checked",
        "select_option",
        "select_text",
        "hover",
        "focus",
        "blur",
        "clear",
        "set_input_files",
        "drag_to",
        "drag_and_drop",
        "dispatch_event",
        "scroll_into_view_if_needed",
    }
)
# Exact names: ``wait_for`` and ``wait_for_timeout`` are distinct entries.
WAITS = frozenset(
    {
        "wait_for_timeout",
        "wait_for_load_state",
        "wait_for_selector",
        "wait_for_url",
        "wait_for_event",
        "wait_for_function",
        "wait_for",
    }
)
SETUP = frozenset(
    {
        "launch",
        "launch_persistent_context",
        "new_context",
        "new_page",
        "close",
        "set_viewport_size",
        "set_default_timeout",
        "set_default_navigation_timeout",
        "set_extra_http_headers",
        "add_init_script",
        "route",
        "grant_permissions",
    }
)
# Setup only on a receiver whose normalized form ends with ``.tracing``;
# ``start``/``stop`` on anything else are ordinary (unclassified) calls.
TRACING_SETUP = frozenset({"start", "stop", "start_chunk", "stop_chunk"})
TRACING_SUFFIX = ".tracing"
# Setup only as ``expect.set_options(...)``.
EXPECT_SETUP = frozenset({"set_options"})
# Setup calls that only change a default timeout: journey rule 4 ignores
# them because the ``longer-timeout`` detector owns them.
TIMEOUT_SETTERS = frozenset(
    {"set_default_timeout", "set_default_navigation_timeout", "set_options"}
)
# Keyword arguments that tune how a step runs rather than what it targets.
OPTION_KWARGS = frozenset(
    {
        "timeout",
        "force",
        "no_wait_after",
        "trial",
        "position",
        "modifiers",
        "delay",
        "button",
        "click_count",
        "strict",
        "wait_until",
        "referer",
    }
)
# Context-manager calls that delimit a transaction (locust-plugins' ``event``).
MARKER_CALLS = ("event",)
ASSERTION_PREFIXES = ("to_", "not_to_")
EXPECT_NAME = "expect"
MAX_SUBSTITUTION_DEPTH = 10
# Built-ins whose result is never a Playwright object; a receiver made by
# calling one (unless the module rebinds the name) excludes the call.
PLAIN_CONSTRUCTORS = frozenset(
    {
        "set",
        "frozenset",
        "list",
        "dict",
        "tuple",
        "str",
        "bytes",
        "bytearray",
        "int",
        "float",
        "bool",
        "range",
        "enumerate",
        "zip",
        "reversed",
        "sorted",
        "map",
        "filter",
    }
)
# Built-ins the normalization rewrites by name (``getattr(x, "n")`` and
# ``dict(k=v)``); like PLAIN_CONSTRUCTORS, only while the module doesn't rebind them.
GETATTR_NAME = "getattr"
_TRACKED_BUILTINS = PLAIN_CONSTRUCTORS | {GETATTR_NAME}
# A module that calls any of these by bare name could rebind a module name
# without a visible assignment, so none of its module names count as constants.
DYNAMIC_NAME_CALLS = frozenset({"globals", "vars", "setattr", "exec", "eval"})
# Matchers with a boolean state keyword: ``to_be_<x>(<x>=False)`` is
# ``not_to_be_<x>()`` and ``<x>=True`` is the default.
STATE_MATCHERS = frozenset({"visible", "checked", "enabled", "editable", "attached"})
# Kinds an unawaited expression statement in an ``async def`` doesn't run:
# in the async API they are coroutines (setup and waits keep their kind).
_COROUTINE_KINDS = frozenset({KIND_NAVIGATION, KIND_ACTION, KIND_ASSERTION})

# A call's (lineno, col_offset, end_lineno, end_col_offset).
CallKey = tuple[int, int, int, int]

_KIND_BY_NAME: dict[str, str] = {
    **{name: KIND_NAVIGATION for name in NAVIGATION},
    **{name: KIND_ACTION for name in ACTIONS},
    **{name: KIND_WAIT for name in WAITS},
    **{name: KIND_SETUP for name in SETUP},
}

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
# Receivers that are provably not Playwright objects: literals and displays.
_LITERAL_RECEIVERS = (
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.JoinedStr,
    *_COMPREHENSIONS,
)
# Type parameters (Python 3.12+) bind names too.
_TYPE_PARAMS = tuple(
    getattr(ast, name) for name in ("TypeVar", "ParamSpec", "TypeVarTuple") if hasattr(ast, name)
)


@dataclass(frozen=True)
class Step:
    """One classified call (or marker boundary) of a script, normalized."""

    kind: str  # one of the KIND_* constants
    name: str  # method or matcher, e.g. "click", "to_be_visible"; markers "start:<label>" / "end"
    target: str  # normalized receiver (assertions: expect()'s first argument)
    values: tuple[str, ...]  # normalized value arguments
    options: tuple[tuple[str, str], ...]  # OPTION_KWARGS present, sorted by name
    line: int  # 1-based line of the call


def call_name(call: ast.Call) -> str | None:
    """Return the called method's name (``func.attr``) or bare function name.

    ``None`` when the callee is neither an attribute nor a name, e.g. ``f()()``.
    """
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def is_expect_ref(node: ast.AST) -> bool:
    """True for the name ``expect`` or an attribute ending in ``.expect``."""
    if isinstance(node, ast.Name):
        return node.id == EXPECT_NAME
    if isinstance(node, ast.Attribute):
        return node.attr == EXPECT_NAME
    return False


def is_expect_call(node: ast.AST) -> bool:
    """True for a call ``expect(...)`` (or ``<x>.expect(...)``)."""
    return isinstance(node, ast.Call) and is_expect_ref(node.func)


def is_assertion_call(call: ast.Call) -> bool:
    """True for ``expect(<x>, ...).<matcher>(...)`` with a ``to_``/``not_to_`` matcher."""
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr.startswith(ASSERTION_PREFIXES)
        and is_expect_call(func.value)
    )


def call_key(call: ast.expr) -> CallKey:
    """A call's position in its module: start and end (``classify_module``'s key).

    The end matters: ``expect(x).to_be_visible()`` and its inner ``expect(x)``
    start at the same place.
    """
    return (call.lineno, call.col_offset, call.end_lineno or 0, call.end_col_offset or 0)


def classify_module(tree: ast.Module) -> dict[CallKey, str]:
    """Map every classified call of ``tree`` to its step kind, keyed by ``call_key``.

    This is the one classification the journey and the detectors share: a
    call is a step for the detectors exactly when ``extract_steps`` makes a
    step of it. The rules, applied with each scope's substitutions:

    - Only method calls (``<receiver>.<name>(...)``) are steps: a bare call
      such as ``type(x)`` or a script's own ``check()`` helper never is, so a
      built-in or helper can't pose as a journey step.
    - A call whose substituted receiver is provably not a Playwright object
      (a literal or display, or a call to an unrebound built-in such as
      ``set()``) isn't a step, so ``seen.clear()`` on a set isn't an action.
      An unknown receiver (a parameter, an attribute, ...) still counts.
    - A matcher (``to_*``/``not_to_*``) is an assertion when its receiver is
      an ``expect(...)`` call, inline or held in a name assigned once from
      one. The bare name ``expect`` is Playwright's only when every binding
      of it in the module is ``from playwright... import expect``.
    - A navigation, action or assertion call that is a whole expression
      statement in an ``async def``, without ``await``, only makes a
      coroutine that never runs: not a step.
    - An action with ``trial=`` anything but ``False`` only runs Playwright's
      actionability checks: not a step.
    - Markers are recognized on ``with`` items only, bare or not.
    - ``getattr(<expr>, "<name>")(...)`` (two arguments, a literal identifier,
      ``getattr`` never rebound) is read as ``<expr>.<name>(...)``.
    - Module constants (``NAME = "text"``, bound once, never ``global``, and
      no ``globals()``/``vars()``/``setattr()``/``exec()``/``eval()`` call in
      the module) substitute into functions that don't bind the name.

    No I/O; ``tree`` isn't modified.
    """
    return _walk(tree).kinds


def extract_steps(source: str) -> list[Step]:
    """Parse ``source`` and return its steps in source order.

    Each step is a call ``classify_module`` classifies (or a marker), built
    in the same walk. Steps nested in a classified call's receiver or
    arguments come before it, since they run first. Raises ``SyntaxError``
    if the source doesn't parse. No I/O.
    """
    return _walk(ast.parse(source)).steps


def _walk(tree: ast.Module) -> _Extractor:
    facts = ModuleFacts.of(tree)
    extractor = _Extractor(facts)
    # A ``global`` declaration anywhere lets a function rebind a module name,
    # so those names are never substituted at module level, and never stand
    # in as constants inside functions.
    module_rebound = [
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Global)
        for name in node.names
    ]
    extractor.constants = {} if facts.dynamic_names else _module_constants(tree, module_rebound)
    extractor.scope(tree.body, module_rebound, is_module=True)
    return extractor


# --- module-wide facts: built-ins and ``expect`` ------------------------------


def _is_playwright_module(module: str | None) -> bool:
    return module is not None and (module == "playwright" or module.startswith("playwright."))


def _module_bindings(tree: ast.Module) -> Iterator[tuple[str, bool]]:
    """Every name binding anywhere in the module, any scope.

    Yields ``(name, plain)``, where ``plain`` is true only for a name bound
    by ``from playwright... import <name>`` without ``as``. A star import
    yields the name ``"*"``.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            yield node.id, False
        elif isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
            yield node.name, False
        elif isinstance(node, ast.arg):
            yield node.arg, False
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.asname or alias.name.split(".")[0], False
        elif isinstance(node, ast.ImportFrom):
            playwright = node.level == 0 and _is_playwright_module(node.module)
            for alias in node.names:
                yield alias.asname or alias.name, playwright and alias.asname is None
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                yield name, False
        elif isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar, *_TYPE_PARAMS)):
            if node.name is not None:  # type: ignore[attr-defined]
                yield node.name, False  # type: ignore[attr-defined]
        elif isinstance(node, ast.MatchMapping) and node.rest is not None:
            yield node.rest, False


@dataclass(frozen=True)
class ModuleFacts:
    """What the classification needs to know about the whole module."""

    # The bare name ``expect`` is Playwright's.
    playwright_expect: bool
    # The PLAIN_CONSTRUCTORS names (and ``getattr``) that may not be the built-ins.
    rebound_builtins: frozenset[str]
    # The module calls one of DYNAMIC_NAME_CALLS by bare name.
    dynamic_names: bool = False

    @classmethod
    def of(cls, tree: ast.Module) -> ModuleFacts:
        bindings = list(_module_bindings(tree))
        # Any star import may bind ``expect`` or a built-in name; a star
        # import from Playwright binds Playwright's ``expect``.
        playwright_expect = all(plain for name, plain in bindings if name in (EXPECT_NAME, "*"))
        if any(name == "*" and not plain for name, plain in bindings):
            rebound = _TRACKED_BUILTINS
        else:
            rebound = _TRACKED_BUILTINS & {name for name, _ in bindings}
        dynamic = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in DYNAMIC_NAME_CALLS
            for node in ast.walk(tree)
        )
        return cls(playwright_expect, frozenset(rebound), dynamic)

    def is_expect_ref(self, node: ast.AST) -> bool:
        """``is_expect_ref``, but a bare ``expect`` only when it's Playwright's."""
        if isinstance(node, ast.Name):
            return node.id == EXPECT_NAME and self.playwright_expect
        return is_expect_ref(node)

    def is_expect_call(self, node: ast.AST) -> bool:
        return isinstance(node, ast.Call) and self.is_expect_ref(node.func)

    def not_playwright(self, receiver: ast.AST) -> bool:
        """True when a (substituted) receiver is provably not a Playwright object."""
        if isinstance(receiver, _LITERAL_RECEIVERS):
            return True
        return (
            isinstance(receiver, ast.Call)
            and isinstance(receiver.func, ast.Name)
            and receiver.func.id in PLAIN_CONSTRUCTORS
            and receiver.func.id not in self.rebound_builtins
        )

    def getattr_name(self, call: ast.Call) -> str | None:
        """The attribute name when ``call`` is ``getattr(<expr>, "<name>")``, else ``None``.

        Only the two-argument form with a string-constant identifier counts,
        and only while the module never rebinds ``getattr``.
        """
        if not (
            isinstance(call.func, ast.Name)
            and call.func.id == GETATTR_NAME
            and GETATTR_NAME not in self.rebound_builtins
            and len(call.args) == 2
            and not call.keywords
            and not isinstance(call.args[0], ast.Starred)
        ):
            return None
        name = call.args[1]
        if isinstance(name, ast.Constant) and isinstance(name.value, str):
            return name.value if name.value.isidentifier() else None
        return None

    def canonical_call(self, call: ast.Call) -> ast.Call:
        """``call``, with ``getattr(<expr>, "<name>")(...)`` read as ``<expr>.<name>(...)``.

        The result keeps the call's position, so ``call_key`` still matches
        the raw call the detectors look up.
        """
        inner = call.func
        if not isinstance(inner, ast.Call):
            return call
        name = self.getattr_name(inner)
        if name is None:
            return call
        attribute = ast.Attribute(value=inner.args[0], attr=name, ctx=ast.Load())
        ast.copy_location(attribute, inner)
        canonical = copy.copy(call)
        canonical.func = attribute
        return canonical

    def literal_keywords(self, value: ast.expr) -> list[tuple[str, ast.expr]] | None:
        """The keywords a ``**`` value spells out, or ``None`` when it may hold others.

        A dict display whose keys are all distinct string constants, or a
        ``dict(k=v, ...)`` call of the unrebound built-in with no positional
        arguments and no ``**``, is exactly those keywords.
        """
        if isinstance(value, ast.Dict):
            keys = value.keys
            names = [
                key.value
                for key in keys
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            ]
            # A ``**`` inside the display has a ``None`` key, which isn't a name.
            if len(names) != len(keys) or len(set(names)) != len(names):
                return None
            return list(zip(names, value.values))
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "dict"
            and "dict" not in self.rebound_builtins
            and not value.args
            and all(keyword.arg is not None for keyword in value.keywords)
        ):
            return [(str(keyword.arg), keyword.value) for keyword in value.keywords]
        return None


# --- substitution of local names -------------------------------------------


def _arg_names(args: ast.arguments) -> list[str]:
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return names


def _comprehension_targets(node: ast.AST) -> frozenset[str]:
    return frozenset(
        name.id
        for generator in node.generators  # type: ignore[attr-defined]
        for name in ast.walk(generator.target)
        if isinstance(name, ast.Name)
    )


def _nonlocal_names(node: ast.AST) -> Iterator[str]:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Nonlocal):
            yield from inner.names


class _BindingCollector(ast.NodeVisitor):
    """Record every binding of every name in one scope.

    ``bindings[name]`` lists one entry per binding: the value expression for a
    plain ``name = <expr>``, ``None`` for any other kind of binding. Nested
    function and class bodies are separate scopes and aren't entered, except
    to find ``nonlocal`` declarations that rebind this scope's names.
    """

    def __init__(self) -> None:
        self.bindings: dict[str, list[ast.expr | None]] = {}

    def other(self, name: str) -> None:
        self.bindings.setdefault(name, []).append(None)

    def visit_Assign(self, node: ast.Assign) -> None:
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            self.bindings.setdefault(node.targets[0].id, []).append(node.value)
        else:
            for target in node.targets:
                self.visit(target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        # ``name: T = <expr>`` is a plain binding; without a value it's another kind.
        if isinstance(node.target, ast.Name) and node.value is not None:
            self.bindings.setdefault(node.target.id, []).append(node.value)
        else:
            self.visit(node.target)
        self.visit(node.annotation)
        if node.value is not None:
            self.visit(node.value)

    def visit_Name(self, node: ast.Name) -> None:
        # Store covers augmented assignment, an annotation without a value,
        # tuple and for targets, ``with ... as``, walrus and type aliases;
        # Del rebinds too.
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self.other(node.id)

    def _visit_definition(self, node: ast.AST, name: str, header: Iterable[ast.AST]) -> None:
        self.other(name)
        for child in header:
            self.visit(child)
        for rebound in _nonlocal_names(node):
            self.other(rebound)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        header = [*node.decorator_list, node.args]
        if node.returns is not None:
            header.append(node.returns)
        self._visit_definition(node, node.name, header)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        header = [*node.decorator_list, node.args]
        if node.returns is not None:
            header.append(node.returns)
        self._visit_definition(node, node.name, header)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        header = [*node.decorator_list, *node.bases, *node.keywords]
        self._visit_definition(node, node.name, header)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        # Defaults are evaluated here; the body is the lambda's own scope.
        self.visit(node.args)

    def _visit_comprehension(self, node: ast.AST) -> None:
        # Comprehension targets live in the comprehension's own scope, but a
        # walrus inside one binds in this scope, so everything else is visited.
        for field in ("elt", "key", "value"):
            child = getattr(node, field, None)
            if child is not None:
                self.visit(child)
        for generator in node.generators:  # type: ignore[attr-defined]
            self.visit(generator.iter)
            for condition in generator.ifs:
                self.visit(condition)

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name is not None:
            self.other(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.other(alias.asname or alias.name.split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.other(alias.asname or alias.name)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self.other(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.other(name)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        if node.name is not None:
            self.other(node.name)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        if node.name is not None:
            self.other(node.name)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        if node.rest is not None:
            self.other(node.rest)
        self.generic_visit(node)


def _substitutable_value(value: ast.expr) -> bool:
    """Whether a plain assignment's value may stand in for its name.

    Awaited values are results, not lazy handles (``page = await
    context.new_page()``); a step call's value is a result too (the sync
    API's ``page = context.new_page()``), and so are ``expect(...)`` and
    lambdas. Only the outermost node is checked. Any name of a tracing call
    counts here whatever its receiver: not substituting is the safe side.
    """
    if isinstance(value, (ast.Await, ast.Lambda)):
        return False
    if isinstance(value, ast.Call):
        if is_expect_call(value) or is_assertion_call(value):
            return False
        name = call_name(value)
        if name is None:
            name = _getattr_callee_name(value)
        if name is not None and (
            name in _KIND_BY_NAME or name in EXPECT_SETUP or name in TRACING_SETUP
        ):
            return False
    return True


def _getattr_callee_name(call: ast.Call) -> str | None:
    """``name`` when ``call`` calls ``getattr(<x>, "<name>")``, else ``None``.

    Reads the shape only (bare ``getattr``, two arguments, a string
    constant) with no rebinding check, unlike ``ModuleFacts.getattr_name``:
    the caller treats a match as "not substitutable", the safe side.
    """
    inner = call.func
    if not (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Name)
        and inner.func.id == GETATTR_NAME
        and len(inner.args) == 2
        and not inner.keywords
        and not isinstance(inner.args[0], ast.Starred)
    ):
        return None
    name = inner.args[1]
    if isinstance(name, ast.Constant) and isinstance(name.value, str):
        return name.value
    return None


def _is_scalar_constant(value: ast.expr | None) -> bool:
    """A str, int or float literal (not bool, bytes, complex or ``None``)."""
    return isinstance(value, ast.Constant) and type(value.value) in (str, int, float)


def _module_constants(tree: ast.Module, global_names: Iterable[str]) -> dict[str, ast.expr]:
    """The module names that stand in for their value inside function scopes.

    A name qualifies iff its only binding in the module body is one plain
    ``NAME = <str/int/float literal>`` and no ``global`` declaration anywhere
    names it. Anything else at module level (calls, containers, a second
    assignment) doesn't substitute into functions.
    """
    collector = _BindingCollector()
    for statement in tree.body:
        collector.visit(statement)
    blocked = frozenset(global_names)
    return {
        name: bindings[0]  # type: ignore[misc]
        for name, bindings in collector.bindings.items()
        if len(bindings) == 1 and name not in blocked and _is_scalar_constant(bindings[0])
    }


def _scope_substitutions(
    body: list[ast.stmt], rebound: Iterable[str], inherited: dict[str, ast.expr]
) -> tuple[dict[str, ast.expr], dict[str, ast.Call], dict[str, ast.expr]]:
    """Map each substitutable name of one scope to its assigned value.

    A name qualifies iff its only binding in the scope is a single plain
    ``name = <expr>`` (or ``name: T = <expr>``) and that value is
    substitutable. ``rebound`` names (parameters, module names declared
    ``global`` elsewhere) are bindings too. ``inherited`` module constants
    stand in as well, unless the scope binds the name itself (its own
    binding wins and follows the rules above).

    The second map holds the names bound that way to an ``expect(...)``
    call. Those stand in only as a matcher's receiver, so ``check =
    expect(loc)`` then ``check.to_be_visible()`` is the inline assertion,
    while ``check`` elsewhere stays a name.

    The third map is ``inherited`` less this scope's own names: what scopes
    nested in this one may still inherit.
    """
    collector = _BindingCollector()
    for name in rebound:
        collector.other(name)
    for statement in body:
        collector.visit(statement)
    inheritable = {
        name: value for name, value in inherited.items() if name not in collector.bindings
    }
    substitutions: dict[str, ast.expr] = dict(inheritable)
    expectations: dict[str, ast.Call] = {}
    for name, bindings in collector.bindings.items():
        if len(bindings) == 1:
            value = bindings[0]
            if value is not None and _substitutable_value(value):
                substitutions[name] = value
            elif isinstance(value, ast.Call) and is_expect_call(value):
                expectations[name] = value
    return substitutions, expectations, inheritable


class _Substituter(ast.NodeTransformer):
    """Replace substitutable names by their values, recursively (bounded)."""

    def __init__(
        self, substitutions: dict[str, ast.expr], shadowed: frozenset[str], depth: int
    ) -> None:
        self.substitutions = substitutions
        self.shadowed = shadowed
        self.depth = depth

    def visit_Name(self, node: ast.Name) -> ast.AST:
        if (
            isinstance(node.ctx, ast.Load)
            and node.id not in self.shadowed
            and node.id in self.substitutions
            and self.depth < MAX_SUBSTITUTION_DEPTH
        ):
            # The value's names resolve where it was assigned, where no
            # lambda or comprehension variable shadows them.
            value = copy.deepcopy(self.substitutions[node.id])
            return _Substituter(self.substitutions, frozenset(), self.depth + 1).visit(value)
        return node

    def _inner(self, names: Iterable[str]) -> _Substituter:
        return _Substituter(self.substitutions, self.shadowed | frozenset(names), self.depth)

    def visit_Lambda(self, node: ast.Lambda) -> ast.AST:
        node.args = self.visit(node.args)
        node.body = self._inner(_arg_names(node.args)).visit(node.body)
        return node

    def _visit_comprehension(self, node: ast.AST) -> ast.AST:
        inner = self._inner(_comprehension_targets(node))
        generators = node.generators  # type: ignore[attr-defined]
        for index, generator in enumerate(generators):
            # The first iterable is evaluated in the enclosing scope.
            generator.iter = (self if index == 0 else inner).visit(generator.iter)
            generator.ifs = [inner.visit(condition) for condition in generator.ifs]
        for field in ("elt", "key", "value"):
            child = getattr(node, field, None)
            if child is not None:
                setattr(node, field, inner.visit(child))
        return node

    visit_ListComp = _visit_comprehension
    visit_SetComp = _visit_comprehension
    visit_DictComp = _visit_comprehension
    visit_GeneratorExp = _visit_comprehension


def _normalize(node: ast.AST, substitutions: dict[str, ast.expr], shadowed: frozenset[str]) -> str:
    # ``ast.unparse`` normalizes quotes and spacing; the copy keeps the
    # source tree intact for the rest of the walk.
    substituted = _Substituter(substitutions, shadowed, 0).visit(copy.deepcopy(node))
    return ast.unparse(substituted)


# --- the source-order walk ---------------------------------------------------


def _position(node: ast.AST) -> tuple[int, int] | None:
    """(line, column) of a node, or of its first positioned descendant."""
    lineno = getattr(node, "lineno", None)
    if lineno is not None:
        return (lineno, getattr(node, "col_offset", 0))
    positions = [p for p in map(_position, ast.iter_child_nodes(node)) if p is not None]
    return min(positions) if positions else None


def _children_in_source_order(node: ast.AST) -> list[ast.AST]:
    # Field order isn't source order everywhere (``Dict`` keys vs values,
    # ``IfExp``), so children are sorted by position; unpositioned children
    # hold no calls and keep their relative order at the end.
    children = list(ast.iter_child_nodes(node))
    far = (float("inf"), float("inf"))
    return [
        child
        for _, _, child in sorted(
            ((_position(child) or far), index, child) for index, child in enumerate(children)
        )
    ]


def _is_trial(call: ast.Call) -> bool:
    """True for a ``trial=`` keyword whose value isn't the literal ``False``."""
    return any(
        keyword.arg == "trial"
        and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
        for keyword in call.keywords
    )


def _canonical_matcher(call: ast.Call) -> ast.Call:
    """``call`` with a literal boolean state keyword folded into the matcher.

    ``to_be_visible(visible=False)`` is ``not_to_be_visible()`` (and the
    ``not_to_…`` form flips back); ``visible=True`` is the default and is
    dropped. Any other value of the keyword, or a matcher without the
    keyword, comes back as it is. ``call.func`` must be an attribute.
    """
    func = call.func
    assert isinstance(func, ast.Attribute)
    negated = func.attr.startswith("not_")
    base = func.attr.removeprefix("not_")
    state = base.removeprefix("to_be_")
    if state == base or state not in STATE_MATCHERS:
        return call
    flags = [keyword for keyword in call.keywords if keyword.arg == state]
    if len(flags) != 1:
        return call
    flag = flags[0].value
    if not (isinstance(flag, ast.Constant) and isinstance(flag.value, bool)):
        return call
    if flag.value is False:
        negated = not negated
    canonical = copy.copy(call)
    canonical.keywords = [keyword for keyword in call.keywords if keyword is not flags[0]]
    canonical.func = ast.Attribute(
        value=func.value, attr=f"{'not_' if negated else ''}{base}", ctx=ast.Load()
    )
    ast.copy_location(canonical.func, func)
    return canonical


def _marker_label(call: ast.Call, normalize: Callable[[ast.AST], str]) -> str:
    """The first positional string constant, else the first argument normalized."""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return normalize(call.args[0]) if call.args else ""


class _Extractor:
    """Walks statements and expressions in source order, collecting steps."""

    def __init__(self, facts: ModuleFacts) -> None:
        self.facts = facts
        self.steps: list[Step] = []
        self.kinds: dict[CallKey, str] = {}
        self.substitutions: dict[str, ast.expr] = {}
        self.expectations: dict[str, ast.Call] = {}
        # Module constants the current scope may still inherit (_module_constants).
        self.constants: dict[str, ast.expr] = {}
        self.shadowed: frozenset[str] = frozenset()
        self.in_async = False  # walking an ``async def``'s own body

    def normalize(self, node: ast.AST) -> str:
        return _normalize(node, self.substitutions, self.shadowed)

    def substitute(self, node: ast.AST) -> ast.AST:
        """A substituted copy of ``node``; the source tree stays intact."""
        return _Substituter(self.substitutions, self.shadowed, 0).visit(copy.deepcopy(node))

    def scope(
        self,
        body: list[ast.stmt],
        rebound: Iterable[str],
        *,
        is_async: bool = False,
        is_module: bool = False,
    ) -> None:
        """Walk one scope's body with that scope's substitutions only.

        Module constants join a nested scope's substitutions unless that
        scope (or one around it) binds the name; the module's own scope
        substitutes its names by its own bindings, and hands the constants on.
        """
        saved = (
            self.substitutions,
            self.expectations,
            self.constants,
            self.shadowed,
            self.in_async,
        )
        inherited = {} if is_module else self.constants
        self.substitutions, self.expectations, inheritable = _scope_substitutions(
            body, rebound, inherited
        )
        if not is_module:
            self.constants = inheritable
        self.shadowed = frozenset()
        self.in_async = is_async
        for statement in body:
            self.visit(statement)
        (
            self.substitutions,
            self.expectations,
            self.constants,
            self.shadowed,
            self.in_async,
        ) = saved

    def visit_shadowed(self, nodes: Iterable[ast.AST], names: Iterable[str]) -> None:
        saved = self.shadowed
        self.shadowed = saved | frozenset(names)
        for node in nodes:
            self.visit(node)
        self.shadowed = saved

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, _FUNCTIONS):
            for child in (*node.decorator_list, node.args):
                self.visit(child)
            if node.returns is not None:
                self.visit(node.returns)
            is_async = isinstance(node, ast.AsyncFunctionDef)
            self.scope(node.body, _arg_names(node.args), is_async=is_async)
        elif isinstance(node, ast.ClassDef):
            for child in (*node.decorator_list, *node.bases, *node.keywords):
                self.visit(child)
            self.scope(node.body, ())
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            self.visit_with(node)
        elif isinstance(node, ast.Lambda):
            self.visit(node.args)
            self.visit_shadowed([node.body], _arg_names(node.args))
        elif isinstance(node, _COMPREHENSIONS):
            self.visit_comprehension(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            # The call is the whole statement: nothing awaits it.
            if not self.visit_call(node.value, unawaited=self.in_async):
                self.visit_children(node.value)
        elif isinstance(node, ast.Call):
            if not self.visit_call(node):
                self.visit_children(node)
        else:
            self.visit_children(node)

    def visit_children(self, node: ast.AST) -> None:
        for child in _children_in_source_order(node):
            self.visit(child)

    def visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        open_markers = 0
        for item in node.items:
            expr = item.context_expr
            if isinstance(expr, ast.Call) and call_name(expr) in MARKER_CALLS:
                label = _marker_label(expr, self.normalize)
                self.kinds[call_key(expr)] = KIND_MARKER
                # Steps in the marker's own arguments run first.
                for argument in expr.args:
                    self.visit(argument)
                for keyword in expr.keywords:
                    self.visit(keyword.value)
                self.steps.append(Step(KIND_MARKER, f"start:{label}", "", (), (), expr.lineno))
                open_markers += 1
            else:
                self.visit(expr)
            if item.optional_vars is not None:
                self.visit(item.optional_vars)
        for statement in node.body:
            self.visit(statement)
        for _ in range(open_markers):
            self.steps.append(Step(KIND_MARKER, "end", "", (), (), node.lineno))

    def visit_comprehension(self, node: ast.AST) -> None:
        names = _comprehension_targets(node)
        generators = node.generators  # type: ignore[attr-defined]
        first_iter = generators[0].iter
        for child in _children_in_source_order(node):
            if isinstance(child, ast.comprehension):
                for part in _children_in_source_order(child):
                    if part is first_iter:
                        self.visit(part)  # evaluated in the enclosing scope
                    else:
                        self.visit_shadowed([part], names)
            else:
                self.visit_shadowed([child], names)

    def classify(self, call: ast.Call, receiver: ast.AST) -> tuple[str | None, ast.Call | None]:
        """The kind of a method call given its substituted receiver (``classify_module``).

        Returns ``(kind, expectation)``: ``expectation`` is an assertion's
        ``expect(...)`` call, ``None`` for any other kind.
        """
        func = call.func
        assert isinstance(func, ast.Attribute)
        if self.facts.not_playwright(receiver):
            return None, None
        name = func.attr
        if name.startswith(ASSERTION_PREFIXES):
            expectation = self.expectation(func.value, receiver)
            if expectation is not None:
                return KIND_ASSERTION, expectation
        if name in _KIND_BY_NAME:
            return _KIND_BY_NAME[name], None
        if name in EXPECT_SETUP and self.facts.is_expect_ref(receiver):
            return KIND_SETUP, None
        if name in TRACING_SETUP and ast.unparse(receiver).endswith(TRACING_SUFFIX):
            return KIND_SETUP, None
        return None, None

    def expectation(self, value: ast.expr, receiver: ast.AST) -> ast.Call | None:
        """The ``expect(...)`` call a matcher's receiver is, inline or by name."""
        if self.facts.is_expect_call(receiver):
            return receiver  # type: ignore[return-value]
        if (
            isinstance(value, ast.Name)
            and value.id not in self.shadowed
            and value.id in self.expectations
        ):
            # Its names resolve where it was assigned, as substituted values' do.
            held = _Substituter(self.substitutions, frozenset(), 0).visit(
                copy.deepcopy(self.expectations[value.id])
            )
            if self.facts.is_expect_call(held):
                return held
        return None

    def visit_call(self, call: ast.Call, *, unawaited: bool = False) -> bool:
        """Append the step for ``call`` if it's classified; return whether it was.

        A classified call's receiver and arguments are searched first: their
        steps run before it. ``unawaited`` marks a call that is a whole
        expression statement of an ``async def``; such a navigation, action
        or assertion is searched but isn't a step, and neither is an action
        with a ``trial=`` other than ``False``.
        """
        call = self.facts.canonical_call(call)
        func = call.func
        if not isinstance(func, ast.Attribute):
            return False
        substituted = self.substitute(func.value)
        kind, expectation = self.classify(call, substituted)
        if kind is None:
            return False
        self.visit_children(call)
        if (unawaited and kind in _COROUTINE_KINDS) or (kind == KIND_ACTION and _is_trial(call)):
            return True
        if expectation is not None:
            target = ast.unparse(expectation.args[0]) if expectation.args else ""
            call = _canonical_matcher(call)
            func = call.func  # the matcher's canonical name
            assert isinstance(func, ast.Attribute)
        else:
            target = ast.unparse(substituted)
        values, options = self.arguments(call)
        self.kinds[call_key(call)] = kind
        self.steps.append(Step(kind, func.attr, target, values, options, call.lineno))
        return True

    def arguments(self, call: ast.Call) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        """Split a call's arguments into normalized values and options.

        A ``**`` whose value spells out its keywords (a dict display with
        string-constant keys, or ``dict(k=v, ...)``) is split like explicit
        keywords; any other ``**<value>`` stays an opaque value.
        """
        values = [self.normalize(arg) for arg in call.args]
        named: list[tuple[str, str]] = []
        unpacked: list[str] = []
        options: list[tuple[str, str]] = []
        keywords: list[tuple[str | None, str]] = []
        for keyword in call.keywords:
            spelled = (
                self.facts.literal_keywords(self.substitute(keyword.value))
                if keyword.arg is None
                else None
            )
            if spelled is None:
                keywords.append((keyword.arg, self.normalize(keyword.value)))
            else:
                # Already substituted (and a nested name can't shadow here).
                keywords.extend((name, ast.unparse(value)) for name, value in spelled)
        for arg, value in keywords:
            if arg is None:
                unpacked.append(f"**{value}")
            elif arg in OPTION_KWARGS:
                options.append((arg, value))
            else:
                named.append((arg, value))
        values.extend(f"{name}={value}" for name, value in sorted(named))
        values.extend(unpacked)
        return tuple(values), tuple(sorted(options))
