"""Case recipes: build a script-fix case's reference and broken input from grading/recipe.toml.

A recipe names a source script (repo-relative), an optional cut of it, and a
list of one-line edits. The cut source is the case's reference; the reference
with the edits applied is the case's input. Everything here is pure: the only
I/O is reading the recipe and the source.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

RECIPE_KEYS = ("source", "cut", "edit")
EDIT_KEYS = ("line", "old", "new", "delete", "insert")
KINDS = ("replace", "delete", "insert")


@dataclass(frozen=True)
class Edit:
    line: int  # a line of the reference (after the cut), 1-based
    kind: str  # "replace" | "delete" | "insert"
    old: str = ""  # replace: occurs exactly once on the line
    new: str = ""  # replace
    text: str = ""  # insert (indented like `line`)


@dataclass(frozen=True)
class Recipe:
    path: Path  # the recipe.toml
    source: str  # repo-relative, forward slashes
    cut: tuple[int, int] | None  # source lines [first, last], inclusive
    edits: tuple[Edit, ...]


def _fail(path: Path, message: str) -> ValueError:
    return ValueError(f"{message}: {path}")


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_source_path(source: str, path: Path) -> None:
    windows = PureWindowsPath(source)
    if source.startswith(("/", "\\")) or windows.drive or windows.is_absolute():
        raise _fail(path, f"recipe key 'source' must be repo-relative, not absolute ({source!r})")
    if ".." in re.split(r"[\\/]", source):
        raise _fail(path, f"recipe key 'source' must not contain '..' ({source!r})")


def _single_line(path: Path, label: str, key: str, value: str) -> None:
    if "\n" in value or "\r" in value:
        raise _fail(path, f"recipe {label}: '{key}' must be a single line (no newline)")


def _load_edit(index: int, raw: object, path: Path) -> Edit:
    """Validate one [[edit]] table; the label names its line once that is known."""
    label = f"edit #{index}"
    if not isinstance(raw, dict):
        raise _fail(path, f"recipe [[edit]] #{index} must be a table, got {raw!r}")
    for key in raw:
        if key not in EDIT_KEYS:
            raise _fail(path, f"recipe {label} has unknown key '{key}'")
    if "line" not in raw:
        raise _fail(path, f"recipe {label} is missing key 'line'")
    line = raw["line"]
    if not _is_int(line):
        raise _fail(path, f"recipe {label} key 'line' must be an integer, got {line!r}")
    label = f"edit at line {line}"
    if line < 1:
        raise _fail(path, f"recipe {label}: 'line' must be at least 1")

    replace = "old" in raw or "new" in raw
    delete = "delete" in raw
    insert = "insert" in raw
    if replace + delete + insert != 1:
        raise _fail(
            path,
            f"recipe {label} needs exactly one of 'old' + 'new', 'delete = true' or 'insert'",
        )

    for key in ("old", "new", "insert"):
        if key in raw:
            if not isinstance(raw[key], str):
                raise _fail(path, f"recipe {label} key '{key}' must be a string, got {raw[key]!r}")
            _single_line(path, label, key, raw[key])

    if replace:
        for key in ("old", "new"):
            if key not in raw:
                raise _fail(path, f"recipe {label} has 'old' or 'new' without '{key}'")
        if raw["old"] == "":
            raise _fail(path, f"recipe {label} key 'old' must not be empty")
        return Edit(line=line, kind="replace", old=raw["old"], new=raw["new"])
    if delete:
        value = raw["delete"]
        if not isinstance(value, bool):
            raise _fail(path, f"recipe {label} key 'delete' must be true, got {value!r}")
        if not value:
            raise _fail(path, f"recipe {label} has 'delete = false'; omit the edit instead")
        return Edit(line=line, kind="delete")
    return Edit(line=line, kind="insert", text=raw["insert"])


def load_recipe(case_dir: Path) -> Recipe:
    """Read <case_dir>/grading/recipe.toml; raise ValueError naming the bad key or line."""
    path = Path(case_dir) / "grading" / "recipe.toml"
    if not path.is_file():
        raise ValueError(f"recipe.toml not found: {path}")
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise _fail(path, f"recipe.toml is not valid TOML ({error})") from error

    for key in data:
        if key not in RECIPE_KEYS:
            raise _fail(path, f"recipe has unknown key '{key}'")
    if "source" not in data:
        raise _fail(path, "recipe is missing required key 'source'")
    source = data["source"]
    if not isinstance(source, str) or not source:
        raise _fail(path, f"recipe key 'source' must be a non-empty string, got {source!r}")
    _check_source_path(source, path)

    cut: tuple[int, int] | None = None
    if "cut" in data:
        raw_cut = data["cut"]
        if not isinstance(raw_cut, list) or len(raw_cut) != 2 or not all(map(_is_int, raw_cut)):
            raise _fail(path, f"recipe key 'cut' must be a list of two integers, got {raw_cut!r}")
        first, last = raw_cut
        if not 1 <= first <= last:
            raise _fail(path, f"recipe key 'cut' needs 1 <= first <= last, got {raw_cut!r}")
        cut = (first, last)

    raw_edits = data.get("edit", [])
    if not isinstance(raw_edits, list):
        raise _fail(path, f"recipe key 'edit' must be an array of tables, got {raw_edits!r}")
    edits = tuple(_load_edit(index, raw, path) for index, raw in enumerate(raw_edits, start=1))
    seen: set[int] = set()
    for edit in edits:
        if edit.line in seen:
            raise _fail(path, f"recipe has two edits on line {edit.line}")
        seen.add(edit.line)

    return Recipe(path=path, source=source, cut=cut, edits=edits)


def _split_lines(text: str) -> list[str]:
    """Split on \\n only, keeping each line's ending (\\n or \\r\\n) on the line."""
    return re.findall(r"[^\n]*\n|[^\n]+", text)


def _split_ending(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _read_source(recipe: Recipe, repo_root: Path) -> str:
    source = Path(repo_root) / recipe.source
    if not source.is_file():
        raise _fail(recipe.path, f"recipe key 'source' does not exist ({recipe.source!r})")
    try:
        return source.read_bytes().decode("utf-8")
    except UnicodeDecodeError as error:
        raise _fail(
            recipe.path, f"recipe key 'source' is not valid UTF-8 ({recipe.source!r}: {error})"
        ) from error


def _apply(edit: Edit, lines: list[str], recipe: Recipe) -> None:
    """Apply one edit to `lines` in place (callers go from the highest line down)."""
    index = edit.line - 1
    body, ending = _split_ending(lines[index])
    if edit.kind == "replace":
        count = body.count(edit.old)
        if count != 1:
            raise _fail(
                recipe.path,
                f"recipe edit at line {edit.line}: 'old' {edit.old!r} must occur exactly once"
                f" on the line, found {count} times",
            )
        lines[index] = body.replace(edit.old, edit.new, 1) + ending
    elif edit.kind == "delete":
        del lines[index]
    elif edit.kind == "insert":
        indent = body[: len(body) - len(body.lstrip(" \t"))]
        inserted = (indent + edit.text if edit.text else "") + (ending or "\n")
        lines.insert(index, inserted)
    else:
        raise _fail(recipe.path, f"recipe edit at line {edit.line} has unknown kind {edit.kind!r}")


def build_scripts(recipe: Recipe, repo_root: Path) -> tuple[str, str]:
    """Return (reference, input): the cut source, and that with the edits applied."""
    lines = _split_lines(_read_source(recipe, repo_root))
    if recipe.cut is not None:
        first, last = recipe.cut
        if last > len(lines):
            raise _fail(
                recipe.path,
                f"recipe key 'cut' {[first, last]} is past the end of the source"
                f" ({len(lines)} lines)",
            )
        lines = lines[: first - 1] + lines[last:]
    reference_lines = list(lines)
    for edit in recipe.edits:
        if not 1 <= edit.line <= len(reference_lines):
            raise _fail(
                recipe.path,
                f"recipe edit at line {edit.line} is outside the reference"
                f" ({len(reference_lines)} lines)",
            )
    for edit in sorted(recipe.edits, key=lambda item: item.line, reverse=True):
        _apply(edit, lines, recipe)
    reference, broken = "".join(reference_lines), "".join(lines)
    if broken == reference:
        raise _fail(recipe.path, "recipe edits leave the input identical to the reference")
    return reference, broken
