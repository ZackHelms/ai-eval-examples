"""Extract the ordered Playwright steps of a script (rubric script-fix-v0, check 2).

A *step* is one classified call: a navigation, action, assertion, wait or
setup call, or a transaction marker around a ``with`` body. Steps come out in
source order, each with its receiver and arguments normalized so that
formatting, quoting and moving a locator into a local variable don't change
them (rubric-v0.md, "Not graded: code style").

The classification tables are module-level so the detectors can reuse them.
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

_KIND_BY_NAME: dict[str, str] = {
    **{name: KIND_NAVIGATION for name in NAVIGATION},
    **{name: KIND_ACTION for name in ACTIONS},
    **{name: KIND_WAIT for name in WAITS},
    **{name: KIND_SETUP for name in SETUP},
}

_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


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


def classify_call(call: ast.Call, receiver: str | None) -> str | None:
    """Return the step kind of ``call``, or ``None`` if it isn't a step.

    Only method calls (``<receiver>.<name>(...)``) are steps: a bare call
    such as ``type(x)`` or a script's own ``check()`` helper never is, so
    a built-in or helper can't pose as a journey step. ``receiver`` is the
    (normalized) unparsed receiver, used only to decide whether
    ``start``/``stop``/... are tracing calls. Markers aren't calls in this
    sense: they are recognized on ``with`` items only, bare or not.
    """
    func = call.func
    if not isinstance(func, ast.Attribute):
        return None
    if is_assertion_call(call):
        return KIND_ASSERTION
    name = func.attr
    if name in _KIND_BY_NAME:
        return _KIND_BY_NAME[name]
    if name in EXPECT_SETUP and is_expect_ref(func.value):
        return KIND_SETUP
    if name in TRACING_SETUP and receiver is not None and receiver.endswith(TRACING_SUFFIX):
        return KIND_SETUP
    return None


def extract_steps(source: str) -> list[Step]:
    """Parse ``source`` and return its steps in source order.

    Raises ``SyntaxError`` if the source doesn't parse. No I/O.
    """
    tree = ast.parse(source)
    extractor = _Extractor()
    # A ``global`` declaration anywhere lets a function rebind a module name,
    # so those names are never substituted at module level.
    module_rebound = [
        name
        for node in ast.walk(tree)
        if isinstance(node, ast.Global)
        for name in node.names
    ]
    extractor.scope(tree.body, module_rebound)
    return extractor.steps


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

    def visit_Name(self, node: ast.Name) -> None:
        # Store covers augmented/annotated assignment, tuple and for targets,
        # ``with ... as``, walrus and type aliases; Del rebinds too.
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
        if name is not None and (
            name in _KIND_BY_NAME or name in EXPECT_SETUP or name in TRACING_SETUP
        ):
            return False
    return True


def _scope_substitutions(body: list[ast.stmt], rebound: Iterable[str]) -> dict[str, ast.expr]:
    """Map each substitutable name of one scope to its assigned value.

    A name qualifies iff its only binding in the scope is a single plain
    ``name = <expr>`` and that value is substitutable. ``rebound`` names
    (parameters, module names declared ``global`` elsewhere) are bindings too.
    """
    collector = _BindingCollector()
    for name in rebound:
        collector.other(name)
    for statement in body:
        collector.visit(statement)
    substitutions: dict[str, ast.expr] = {}
    for name, bindings in collector.bindings.items():
        if len(bindings) == 1:
            value = bindings[0]
            if value is not None and _substitutable_value(value):
                substitutions[name] = value
    return substitutions


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


def _marker_label(call: ast.Call, normalize: Callable[[ast.AST], str]) -> str:
    """The first positional string constant, else the first argument normalized."""
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            return arg.value
    return normalize(call.args[0]) if call.args else ""


class _Extractor:
    """Walks statements and expressions in source order, collecting steps."""

    def __init__(self) -> None:
        self.steps: list[Step] = []
        self.substitutions: dict[str, ast.expr] = {}
        self.shadowed: frozenset[str] = frozenset()

    def normalize(self, node: ast.AST) -> str:
        return _normalize(node, self.substitutions, self.shadowed)

    def scope(self, body: list[ast.stmt], rebound: Iterable[str]) -> None:
        """Walk one scope's body with that scope's substitutions only."""
        saved = (self.substitutions, self.shadowed)
        self.substitutions = _scope_substitutions(body, rebound)
        self.shadowed = frozenset()
        for statement in body:
            self.visit(statement)
        self.substitutions, self.shadowed = saved

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
            self.scope(node.body, _arg_names(node.args))
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
        elif isinstance(node, ast.Call) and self.visit_call(node):
            pass  # a classified call: neither receiver nor arguments are searched
        else:
            for child in _children_in_source_order(node):
                self.visit(child)

    def visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        open_markers = 0
        for item in node.items:
            expr = item.context_expr
            if isinstance(expr, ast.Call) and call_name(expr) in MARKER_CALLS:
                label = _marker_label(expr, self.normalize)
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

    def visit_call(self, call: ast.Call) -> bool:
        """Append the step for ``call`` if it's classified; return whether it was."""
        func = call.func
        receiver = self.normalize(func.value) if isinstance(func, ast.Attribute) else None
        kind = classify_call(call, receiver)
        if kind is None:
            return False
        if kind == KIND_ASSERTION:
            expectation = func.value  # type: ignore[attr-defined]
            target = self.normalize(expectation.args[0]) if expectation.args else ""
        else:
            target = receiver or ""
        values, options = self.arguments(call)
        name = call_name(call) or ""
        self.steps.append(Step(kind, name, target, values, options, call.lineno))
        return True

    def arguments(self, call: ast.Call) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
        """Split a call's arguments into normalized values and options."""
        values = [self.normalize(arg) for arg in call.args]
        named: list[tuple[str, str]] = []
        unpacked: list[str] = []
        options: list[tuple[str, str]] = []
        for keyword in call.keywords:
            value = self.normalize(keyword.value)
            if keyword.arg is None:
                unpacked.append(f"**{value}")
            elif keyword.arg in OPTION_KWARGS:
                options.append((keyword.arg, value))
            else:
                named.append((keyword.arg, value))
        values.extend(f"{name}={value}" for name, value in sorted(named))
        values.extend(unpacked)
        return tuple(values), tuple(sorted(options))
