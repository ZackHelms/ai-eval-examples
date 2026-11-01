"""Tests for scriptfix.makecase: recipe loading and building the reference and input."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scriptfix.makecase import Edit, Recipe, build_scripts, load_recipe

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_01_REFERENCE = REPO_ROOT / "evals" / "01-playwright-python-basic" / "grading" / "reference" / "script.py"

SOURCE = "def run():\n    one()\n    two()\n    three()\n    four()\n"
SOURCE_REL = "src/script.py"


def make_repo(tmp_path: Path, recipe: str, source: bytes | str = SOURCE) -> tuple[Path, Path]:
    """Build tmp_path/repo with the source and evals/09-demo/grading/recipe.toml.

    Returns (repo_root, case_dir). The recipe text is written as given.
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    data = source.encode("utf-8") if isinstance(source, str) else source
    (repo / SOURCE_REL).write_bytes(data)
    case_dir = repo / "evals" / "09-demo"
    (case_dir / "grading").mkdir(parents=True)
    (case_dir / "grading" / "recipe.toml").write_text(recipe, encoding="utf-8", newline="\n")
    return repo, case_dir


def build(tmp_path: Path, recipe: str, source: bytes | str = SOURCE) -> tuple[str, str]:
    repo, case_dir = make_repo(tmp_path, recipe, source)
    return build_scripts(load_recipe(case_dir), repo)


def header(extra: str = "") -> str:
    return f'source = "{SOURCE_REL}"\n{extra}'


# -- loading -----------------------------------------------------------------


def test_load_recipe_reads_every_field(tmp_path: Path) -> None:
    recipe_text = header(
        "cut = [4, 5]\n"
        "[[edit]]\nline = 1\nold = 'run'\nnew = 'go'\n"
        "[[edit]]\nline = 2\ndelete = true\n"
        "[[edit]]\nline = 3\ninsert = 'extra()'\n"
    )
    _, case_dir = make_repo(tmp_path, recipe_text)
    recipe = load_recipe(case_dir)
    assert recipe == Recipe(
        path=case_dir / "grading" / "recipe.toml",
        source=SOURCE_REL,
        cut=(4, 5),
        edits=(
            Edit(line=1, kind="replace", old="run", new="go"),
            Edit(line=2, kind="delete"),
            Edit(line=3, kind="insert", text="extra()"),
        ),
    )


def test_load_recipe_cut_is_optional_and_edits_default_empty(tmp_path: Path) -> None:
    _, case_dir = make_repo(tmp_path, header())
    recipe = load_recipe(case_dir)
    assert recipe.cut is None
    assert recipe.edits == ()


def test_load_recipe_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="recipe.toml not found"):
        load_recipe(tmp_path / "09-demo")


def test_load_recipe_invalid_toml(tmp_path: Path) -> None:
    _, case_dir = make_repo(tmp_path, "source = \n")
    with pytest.raises(ValueError, match="not valid TOML"):
        load_recipe(case_dir)


# -- edit kinds --------------------------------------------------------------


def test_replace_swaps_the_single_occurrence(tmp_path: Path) -> None:
    reference, broken = build(tmp_path, header("[[edit]]\nline = 3\nold = 'two'\nnew = '2'\n"))
    assert reference == SOURCE
    assert broken == "def run():\n    one()\n    2()\n    three()\n    four()\n"


def test_replace_can_delete_a_substring(tmp_path: Path) -> None:
    _, broken = build(tmp_path, header("[[edit]]\nline = 3\nold = 'wo'\nnew = ''\n"))
    assert broken.splitlines()[2] == "    t()"


def test_delete_removes_the_line(tmp_path: Path) -> None:
    _, broken = build(tmp_path, header("[[edit]]\nline = 3\ndelete = true\n"))
    assert broken == "def run():\n    one()\n    three()\n    four()\n"


def test_insert_goes_before_the_line_with_its_indent(tmp_path: Path) -> None:
    _, broken = build(tmp_path, header("[[edit]]\nline = 3\ninsert = 'extra()'\n"))
    assert broken == "def run():\n    one()\n    extra()\n    two()\n    three()\n    four()\n"


def test_insert_before_an_unindented_line(tmp_path: Path) -> None:
    _, broken = build(tmp_path, header("[[edit]]\nline = 1\ninsert = 'import os'\n"))
    assert broken.startswith("import os\ndef run():\n")


# -- cut ---------------------------------------------------------------------


def test_cut_removes_the_inclusive_range(tmp_path: Path) -> None:
    reference, broken = build(
        tmp_path, header("cut = [3, 4]\n[[edit]]\nline = 3\nold = 'four'\nnew = '4'\n")
    )
    assert reference == "def run():\n    one()\n    four()\n"
    assert broken == "def run():\n    one()\n    4()\n"


def test_cut_of_one_line(tmp_path: Path) -> None:
    reference, _ = build(tmp_path, header("cut = [2, 2]\n[[edit]]\nline = 1\nold = 'run'\nnew = 'go'\n"))
    assert reference == "def run():\n    two()\n    three()\n    four()\n"


def test_edit_lines_are_reference_lines_after_the_cut(tmp_path: Path) -> None:
    # Source line 5 is reference line 3 once lines 2-3 are cut.
    _, broken = build(
        tmp_path, header("cut = [2, 3]\n[[edit]]\nline = 3\nold = 'four'\nnew = '4'\n")
    )
    assert broken == "def run():\n    three()\n    4()\n"


# -- bottom-up application ---------------------------------------------------


def test_edits_apply_bottom_up_so_line_numbers_do_not_shift(tmp_path: Path) -> None:
    # Listed top-down on purpose: applied top-down, the delete on line 2 would
    # shift the later edits onto the wrong lines.
    recipe_text = header(
        "[[edit]]\nline = 2\ndelete = true\n"
        "[[edit]]\nline = 3\ninsert = 'extra()'\n"
        "[[edit]]\nline = 5\nold = 'four'\nnew = '4'\n"
    )
    reference, broken = build(tmp_path, recipe_text)
    assert reference == SOURCE
    assert broken == "def run():\n    extra()\n    two()\n    three()\n    4()\n"


def test_edits_in_any_listed_order_give_the_same_input(tmp_path: Path) -> None:
    top_down = header(
        "[[edit]]\nline = 2\ndelete = true\n[[edit]]\nline = 4\ninsert = 'extra()'\n"
    )
    bottom_up = header(
        "[[edit]]\nline = 4\ninsert = 'extra()'\n[[edit]]\nline = 2\ndelete = true\n"
    )
    assert build(tmp_path / "a", top_down) == build(tmp_path / "b", bottom_up)


# -- line endings ------------------------------------------------------------


def test_lf_input_gives_lf_output(tmp_path: Path) -> None:
    recipe_text = header(
        "cut = [5, 5]\n[[edit]]\nline = 2\ninsert = 'extra()'\n"
        "[[edit]]\nline = 3\nold = 'two'\nnew = '2'\n"
    )
    reference, broken = build(tmp_path, recipe_text)
    assert "\r" not in reference
    assert "\r" not in broken
    assert reference.endswith("\n")
    assert broken.endswith("\n")


def test_crlf_source_keeps_crlf_everywhere(tmp_path: Path) -> None:
    source = SOURCE.replace("\n", "\r\n")
    recipe_text = header("[[edit]]\nline = 3\ninsert = 'extra()'\n[[edit]]\nline = 4\nold = 'three'\nnew = '3'\n")
    reference, broken = build(tmp_path, recipe_text, source)
    assert reference == source
    assert broken == "def run():\r\n    one()\r\n    extra()\r\n    two()\r\n    3()\r\n    four()\r\n"
    assert broken.count("\n") == broken.count("\r\n")


def test_source_without_trailing_newline_keeps_that(tmp_path: Path) -> None:
    reference, broken = build(
        tmp_path, header("[[edit]]\nline = 5\nold = 'four'\nnew = '4'\n"), SOURCE.rstrip("\n")
    )
    assert not reference.endswith("\n")
    assert broken.endswith("    4()")


def test_insert_before_an_unterminated_last_line_still_ends_the_inserted_line(tmp_path: Path) -> None:
    _, broken = build(
        tmp_path, header("[[edit]]\nline = 5\ninsert = 'extra()'\n"), SOURCE.rstrip("\n")
    )
    assert broken.endswith("    extra()\n    four()")


# -- ValueErrors: loading ----------------------------------------------------


def load_error(tmp_path: Path, recipe_text: str, match: str) -> None:
    _, case_dir = make_repo(tmp_path, recipe_text)
    with pytest.raises(ValueError, match=match) as info:
        load_recipe(case_dir)
    assert "recipe.toml" in str(info.value)  # the message names the recipe path


def test_unknown_top_level_key(tmp_path: Path) -> None:
    load_error(tmp_path, header("bogus = 1\n"), "unknown key 'bogus'")


def test_missing_source(tmp_path: Path) -> None:
    load_error(tmp_path, "cut = [1, 2]\n", "missing required key 'source'")


def test_source_must_be_a_string(tmp_path: Path) -> None:
    load_error(tmp_path, "source = 3\n", "'source' must be a non-empty string")


@pytest.mark.parametrize(
    "source", ["/etc/script.py", "\\\\host\\share\\script.py", "C:/work/script.py", "C:\\work\\script.py"]
)
def test_absolute_source(tmp_path: Path, source: str) -> None:
    load_error(tmp_path, f"source = {json.dumps(source)}\n", "'source' must be repo-relative, not absolute")


@pytest.mark.parametrize("source", ["../script.py", "src/../../script.py", "src\\..\\script.py"])
def test_source_with_dotdot(tmp_path: Path, source: str) -> None:
    load_error(tmp_path, f"source = {json.dumps(source)}\n", "'source' must not contain '..'")


@pytest.mark.parametrize("cut", ["3", "[1]", "[1, 2, 3]", "[1, 'a']", "[1, true]", "[1.5, 2]"])
def test_cut_must_be_two_integers(tmp_path: Path, cut: str) -> None:
    load_error(tmp_path, header(f"cut = {cut}\n"), "'cut' must be a list of two integers")


@pytest.mark.parametrize("cut", ["[0, 2]", "[-1, 2]", "[4, 3]"])
def test_cut_bounds(tmp_path: Path, cut: str) -> None:
    load_error(tmp_path, header(f"cut = {cut}\n"), "'cut' needs 1 <= first <= last")


def test_edit_must_be_an_array_of_tables(tmp_path: Path) -> None:
    load_error(tmp_path, header("edit = 3\n"), "'edit' must be an array of tables")
    load_error(tmp_path / "b", header("edit = [3]\n"), r"\[\[edit\]\] #1 must be a table")


def test_edit_missing_line(tmp_path: Path) -> None:
    load_error(tmp_path, header("[[edit]]\ndelete = true\n"), "edit #1 is missing key 'line'")


@pytest.mark.parametrize("line", ["'3'", "true", "2.0"])
def test_edit_line_must_be_an_int(tmp_path: Path, line: str) -> None:
    load_error(tmp_path, header(f"[[edit]]\nline = {line}\ndelete = true\n"), "key 'line' must be an integer")


def test_edit_line_below_one(tmp_path: Path) -> None:
    load_error(tmp_path, header("[[edit]]\nline = 0\ndelete = true\n"), "edit at line 0: 'line' must be at least 1")


def test_edit_unknown_key(tmp_path: Path) -> None:
    load_error(
        tmp_path, header("[[edit]]\nline = 2\ndelete = true\nwhy = 'x'\n"), "edit #1 has unknown key 'why'"
    )


@pytest.mark.parametrize(
    "body",
    [
        "",  # no kind at all
        "old = 'a'\nnew = 'b'\ndelete = true\n",
        "old = 'a'\nnew = 'b'\ninsert = 'x'\n",
        "delete = true\ninsert = 'x'\n",
    ],
)
def test_edit_needs_exactly_one_kind(tmp_path: Path, body: str) -> None:
    load_error(
        tmp_path,
        header(f"[[edit]]\nline = 2\n{body}"),
        "edit at line 2 needs exactly one of 'old' \\+ 'new', 'delete = true' or 'insert'",
    )


@pytest.mark.parametrize("pair", ["old = 'a'", "new = 'b'"])
def test_replace_needs_both_old_and_new(tmp_path: Path, pair: str) -> None:
    missing = "new" if pair.startswith("old") else "old"
    load_error(
        tmp_path, header(f"[[edit]]\nline = 2\n{pair}\n"), f"edit at line 2 has 'old' or 'new' without '{missing}'"
    )


def test_replace_old_must_not_be_empty(tmp_path: Path) -> None:
    load_error(tmp_path, header("[[edit]]\nline = 2\nold = ''\nnew = 'b'\n"), "edit at line 2 key 'old' must not be empty")


def test_delete_false(tmp_path: Path) -> None:
    load_error(tmp_path, header("[[edit]]\nline = 2\ndelete = false\n"), "edit at line 2 has 'delete = false'")


def test_delete_must_be_a_bool(tmp_path: Path) -> None:
    load_error(tmp_path, header("[[edit]]\nline = 2\ndelete = 1\n"), "edit at line 2 key 'delete' must be true")


@pytest.mark.parametrize(
    ("body", "key"),
    [("old = 1\nnew = 'b'\n", "old"), ("old = 'a'\nnew = 2\n", "new"), ("insert = 7\n", "insert")],
)
def test_strings_must_be_strings(tmp_path: Path, body: str, key: str) -> None:
    load_error(tmp_path, header(f"[[edit]]\nline = 2\n{body}"), f"edit at line 2 key '{key}' must be a string")


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ('old = "a\\nb"\nnew = "c"\n', "old"),
        ('old = "a"\nnew = "c\\nd"\n', "new"),
        ('insert = "x\\ny"\n', "insert"),
        ('insert = "x\\ry"\n', "insert"),
    ],
)
def test_multiline_values_are_rejected(tmp_path: Path, body: str, key: str) -> None:
    load_error(
        tmp_path,
        header(f"[[edit]]\nline = 4\n{body}"),
        f"edit at line 4: '{key}' must be a single line",
    )


def test_two_edits_on_one_line(tmp_path: Path) -> None:
    load_error(
        tmp_path,
        header("[[edit]]\nline = 3\ndelete = true\n[[edit]]\nline = 3\ninsert = 'x'\n"),
        "two edits on line 3",
    )


# -- ValueErrors: building ---------------------------------------------------


def build_error(tmp_path: Path, recipe_text: str, match: str, source: bytes | str = SOURCE) -> None:
    repo, case_dir = make_repo(tmp_path, recipe_text, source)
    recipe = load_recipe(case_dir)
    with pytest.raises(ValueError, match=match) as info:
        build_scripts(recipe, repo)
    assert "recipe.toml" in str(info.value)


def test_source_must_exist(tmp_path: Path) -> None:
    repo, case_dir = make_repo(tmp_path, 'source = "src/missing.py"\n')
    with pytest.raises(ValueError, match="'source' does not exist"):
        build_scripts(load_recipe(case_dir), repo)


def test_source_must_be_utf8(tmp_path: Path) -> None:
    build_error(
        tmp_path,
        header("[[edit]]\nline = 1\ndelete = true\n"),
        "'source' is not valid UTF-8",
        source=b"caf\xe9\n",
    )


def test_cut_past_the_end_of_the_source(tmp_path: Path) -> None:
    build_error(tmp_path, header("cut = [4, 6]\n"), r"'cut' \[4, 6\] is past the end of the source \(5 lines\)")


def test_cut_may_end_on_the_last_line(tmp_path: Path) -> None:
    reference, _ = build(tmp_path, header("cut = [4, 5]\n[[edit]]\nline = 1\nold = 'run'\nnew = 'go'\n"))
    assert reference == "def run():\n    one()\n    two()\n"


@pytest.mark.parametrize("line", [6, 100])
def test_edit_line_past_the_reference(tmp_path: Path, line: int) -> None:
    build_error(
        tmp_path,
        header(f"[[edit]]\nline = {line}\ndelete = true\n"),
        f"edit at line {line} is outside the reference \\(5 lines\\)",
    )


def test_edit_bounds_use_the_reference_after_the_cut(tmp_path: Path) -> None:
    # The source has 5 lines but the reference only 3.
    build_error(
        tmp_path,
        header("cut = [2, 3]\n[[edit]]\nline = 4\ndelete = true\n"),
        r"edit at line 4 is outside the reference \(3 lines\)",
    )


def test_old_absent_from_its_line(tmp_path: Path) -> None:
    build_error(
        tmp_path,
        header("[[edit]]\nline = 2\nold = 'two'\nnew = '2'\n"),
        "edit at line 2: 'old' 'two' must occur exactly once on the line, found 0 times",
    )


def test_old_occurring_twice_on_its_line(tmp_path: Path) -> None:
    build_error(
        tmp_path,
        header("[[edit]]\nline = 4\nold = 'e'\nnew = 'E'\n"),
        "edit at line 4: 'old' 'e' must occur exactly once on the line, found 2 times",
    )


def test_input_identical_to_the_reference(tmp_path: Path) -> None:
    build_error(
        tmp_path,
        header("[[edit]]\nline = 2\nold = 'one'\nnew = 'one'\n"),
        "edits leave the input identical to the reference",
    )


def test_no_edits_leaves_the_input_identical(tmp_path: Path) -> None:
    build_error(tmp_path, header(), "edits leave the input identical to the reference")


# -- case 02 on Eval 01's reference ------------------------------------------

CASE_02_RECIPE = """\
# How this case is built: .\\10-make-case.ps1 -Case evals\\02-docs-journey-a
source = "evals/01-playwright-python-basic/grading/reference/script.py"
cut    = [19, 20]

[[edit]]
line = 18
old  = "»"
new  = ">"
"""


def test_case_02_recipe_builds_from_eval_01(tmp_path: Path) -> None:
    case_dir = tmp_path / "02-docs-journey-a"
    (case_dir / "grading").mkdir(parents=True)
    (case_dir / "grading" / "recipe.toml").write_text(CASE_02_RECIPE, encoding="utf-8", newline="\n")

    reference, broken = build_scripts(load_recipe(case_dir), REPO_ROOT)

    eval_01 = EVAL_01_REFERENCE.read_bytes().decode("utf-8").splitlines(keepends=True)
    assert len(eval_01) == 35
    expected_lines = eval_01[:18] + eval_01[20:]
    assert len(expected_lines) == 33
    assert reference == "".join(expected_lines)
    assert "\r" not in reference
    assert reference.endswith("\n")

    broken_lines = broken.splitlines(keepends=True)
    reference_lines = reference.splitlines(keepends=True)
    assert len(broken_lines) == len(reference_lines)
    differing = [n for n, (a, b) in enumerate(zip(reference_lines, broken_lines), start=1) if a != b]
    assert differing == [18]
    assert broken_lines[17] == reference_lines[17].replace("»", ">")
    assert ">" in broken_lines[17]
    assert "»" not in broken_lines[17]
