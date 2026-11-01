"""The private-names check script (.claude/scripts/check-private-names.ps1).

Each test runs the real script with `pwsh -File` against a throwaway git repo.
Only made-up names appear here; the script must never echo a name, so every
hit test also asserts the name text is absent from the output.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

if shutil.which("pwsh") is None or shutil.which("git") is None:
    pytest.skip("pwsh and git are required", allow_module_level=True)

SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "check-private-names.ps1"
LIST_REL = Path(".claude") / "private-names.local.txt"
NAME_ONE = "zorblax"
NAME_TWO = "quuxcorp"
GIT_VARS_TO_DROP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
)
GIT_IDENTITY = ["-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false"]


class Result:
    def __init__(self, done: subprocess.CompletedProcess[bytes]) -> None:
        self.code = done.returncode
        self.out = done.stdout.decode("utf-8")
        self.err = done.stderr.decode("utf-8")

    @property
    def everything(self) -> str:
        return self.out + self.err


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """A git environment the host's config and any outer repo can't touch."""
    empty_config = tmp_path / "empty.gitconfig"
    empty_config.write_text("", encoding="utf-8")
    clean = {k: v for k, v in os.environ.items() if k not in GIT_VARS_TO_DROP}
    clean["GIT_CONFIG_NOSYSTEM"] = "1"
    clean["GIT_CONFIG_GLOBAL"] = str(empty_config)
    return clean


class Repo:
    def __init__(self, path: Path, env: dict[str, str]) -> None:
        self.path = path
        self.env = env

    def git(self, *args: str) -> str:
        done = subprocess.run(
            ["git", *GIT_IDENTITY, *args],
            cwd=self.path,
            env=self.env,
            capture_output=True,
            check=True,
        )
        return done.stdout.decode("utf-8")

    def write(self, rel: str, text: str) -> None:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))

    def commit_file(self, rel: str, text: str, message: str) -> None:
        self.write(rel, text)
        self.git("add", rel)
        self.git("commit", "-q", "-m", message)

    def set_list(self, *names: str) -> None:
        self.write(str(LIST_REL), "# a comment\n\n" + "\n".join(names) + "\n")

    def check(self, *args: str, cwd: Path | None = None) -> Result:
        done = subprocess.run(
            ["pwsh", "-NoProfile", "-NonInteractive", "-File", str(SCRIPT), *args],
            cwd=cwd or self.path,
            env=self.env,
            capture_output=True,
        )
        return Result(done)


@pytest.fixture
def repo(tmp_path: Path, env: dict[str, str]) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    made = Repo(path, env)
    made.git("init", "-q")
    made.commit_file("base.txt", "base\n", "chore: base")
    made.set_list(NAME_ONE, NAME_TWO)
    return made


def assert_names_not_echoed(result: Result) -> None:
    lowered = result.everything.lower()
    assert NAME_ONE not in lowered
    assert NAME_TWO not in lowered


def test_staged_hit_reports_the_number_not_the_name(repo: Repo) -> None:
    repo.write("notes.txt", f"line one\nuse {NAME_TWO} here\n")
    repo.git("add", "notes.txt")
    result = repo.check()
    assert result.code == 1
    assert result.out.splitlines()[0] == "PRIVATE_NAMES=hit"
    assert "HIT staged notes.txt:2 name #2" in result.out
    assert_names_not_echoed(result)


def test_clean_stage_exits_zero(repo: Repo) -> None:
    repo.write("notes.txt", "nothing private\n")
    repo.git("add", "notes.txt")
    result = repo.check()
    assert result.code == 0
    assert result.out.strip() == "PRIVATE_NAMES=clean"


def test_nothing_staged_is_clean(repo: Repo) -> None:
    assert repo.check().code == 0


def test_substring_of_a_name_is_not_a_hit(repo: Repo) -> None:
    repo.write("notes.txt", f"{NAME_ONE}es and pre{NAME_TWO}\n")
    repo.git("add", "notes.txt")
    result = repo.check()
    assert result.code == 0
    assert result.out.strip() == "PRIVATE_NAMES=clean"


def test_case_variant_is_a_hit(repo: Repo) -> None:
    repo.write("notes.txt", "see ZorBlax today\n")
    repo.git("add", "notes.txt")
    result = repo.check()
    assert result.code == 1
    assert "HIT staged notes.txt:1 name #1" in result.out
    assert_names_not_echoed(result)


def test_only_added_lines_count_not_removed_ones(repo: Repo) -> None:
    repo.commit_file("notes.txt", f"keep\n{NAME_ONE}\n", "chore: seed")
    repo.write("notes.txt", "keep\n")
    repo.git("add", "notes.txt")
    assert repo.check().code == 0


def test_a_staged_path_named_after_a_name_is_a_hit(repo: Repo) -> None:
    repo.write(f"docs/{NAME_ONE}-notes.txt", "harmless\n")
    repo.git("add", "docs")
    result = repo.check()
    assert result.code == 1
    # The path holds the name, so it is printed masked.
    assert "HIT staged-path docs/<#1>-notes.txt name #1" in result.out
    assert_names_not_echoed(result)


def test_message_hit_and_clean_message(repo: Repo) -> None:
    hit = repo.check("-Message", f"feat: add {NAME_ONE} support")
    assert hit.code == 1
    assert "HIT message -Message name #1" in hit.out
    assert_names_not_echoed(hit)
    clean = repo.check("-Message", "feat: add generic support")
    assert clean.code == 0


def test_all_finds_old_message_and_removed_line(repo: Repo) -> None:
    repo.commit_file("a.txt", "alpha\n", f"chore: import {NAME_ONE} data")
    repo.commit_file("b.txt", f"keep\n{NAME_TWO}\n", "chore: add b")
    repo.commit_file("b.txt", "keep\n", "chore: tidy b")
    result = repo.check("-All")
    assert result.code == 1
    lines = result.out.splitlines()
    assert lines[0] == "PRIVATE_NAMES=hit"
    assert sum(1 for line in lines if line.startswith("HIT commit-message ") and line.endswith("name #1")) == 1
    # One commit added the line and one removed it; both diffs match name #2.
    assert sum(1 for line in lines if line.startswith("HIT commit-diff ") and line.endswith("name #2")) == 2
    assert not any(line.startswith("HIT file ") for line in lines)
    assert_names_not_echoed(result)


def test_all_does_not_flag_a_substring_only_commit(repo: Repo) -> None:
    repo.commit_file("a.txt", f"{NAME_ONE}es\n", f"chore: {NAME_TWO}x")
    result = repo.check("-All")
    assert result.code == 0
    assert result.out.strip() == "PRIVATE_NAMES=clean"


def test_all_finds_tracked_file_lines_and_paths(repo: Repo) -> None:
    repo.commit_file("docs/readme.txt", f"one\ntwo {NAME_ONE}\n", "chore: docs")
    repo.commit_file(f"{NAME_TWO}.cfg", "x\n", "chore: cfg")
    result = repo.check("-All")
    assert result.code == 1
    assert "HIT file docs/readme.txt:2 name #1" in result.out
    assert "HIT path <#2>.cfg name #2" in result.out
    assert_names_not_echoed(result)


def test_all_from_a_subdirectory_still_sweeps_the_whole_repo(repo: Repo) -> None:
    repo.commit_file("top.txt", f"x\n{NAME_ONE}\n", "chore: top")
    sub = repo.path / "sub"
    sub.mkdir()
    result = repo.check("-All", cwd=sub)
    assert result.code == 1
    assert "HIT file top.txt:2 name #1" in result.out
    assert_names_not_echoed(result)


def test_default_scope_from_a_subdirectory_reports_repo_relative_paths(repo: Repo) -> None:
    repo.write("top.txt", f"{NAME_TWO}\n")
    repo.git("add", "top.txt")
    sub = repo.path / "sub"
    sub.mkdir()
    result = repo.check(cwd=sub)
    assert result.code == 1
    assert "HIT staged top.txt:1 name #2" in result.out
    assert_names_not_echoed(result)


def test_all_is_clean_on_a_clean_repo(repo: Repo) -> None:
    result = repo.check("-All")
    assert result.code == 0
    assert result.out.strip() == "PRIVATE_NAMES=clean"


def test_non_ascii_name_in_a_diff_is_matched(repo: Repo) -> None:
    name = "z" + chr(0xF6) + "rblax"  # o-umlaut, kept out of the source text
    repo.set_list(name)
    repo.write("notes.txt", f"ok\nfound {name} here\n")
    repo.git("add", "notes.txt")
    result = repo.check()
    assert result.code == 1
    assert "HIT staged notes.txt:2 name #1" in result.out


def test_missing_list_exits_two_and_says_where_to_create_it(repo: Repo) -> None:
    (repo.path / LIST_REL).unlink()
    result = repo.check()
    assert result.code == 2
    assert "private-names.local.txt" in result.err
    assert "PRIVATE_NAMES" not in result.out


def test_empty_list_exits_two(repo: Repo) -> None:
    repo.write(str(LIST_REL), "# only a comment\n\n   \n")
    result = repo.check()
    assert result.code == 2
    assert "no names" in result.err


def test_explicit_list_path(repo: Repo, tmp_path: Path) -> None:
    (repo.path / LIST_REL).unlink()
    other = tmp_path / "elsewhere.txt"
    other.write_text(f"{NAME_ONE}\n", encoding="utf-8")
    repo.write("notes.txt", f"{NAME_ONE}\n")
    repo.git("add", "notes.txt")
    result = repo.check("-ListPath", str(other))
    assert result.code == 1
    assert "name #1" in result.out
    assert repo.check("-ListPath", str(tmp_path / "nope.txt")).code == 2


def test_not_a_git_repository_exits_two(repo: Repo, tmp_path: Path) -> None:
    bare_dir = tmp_path / "plain"
    bare_dir.mkdir()
    result = repo.check(cwd=bare_dir)
    assert result.code == 2
    assert "git repository" in result.err


def test_worktree_finds_the_main_checkouts_list(repo: Repo, tmp_path: Path) -> None:
    worktree = tmp_path / "wt"
    repo.git("worktree", "add", "-q", "-b", "side", str(worktree))
    assert not (worktree / LIST_REL).exists()
    (worktree / "notes.txt").write_text(f"{NAME_TWO}\n", encoding="utf-8")
    sibling = Repo(worktree, repo.env)
    sibling.git("add", "notes.txt")
    result = sibling.check()
    assert result.code == 1
    assert "HIT staged notes.txt:1 name #2" in result.out
    assert_names_not_echoed(result)


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_and_exits_zero(repo: Repo, flag: str) -> None:
    result = repo.check(flag)
    assert result.code == 0
    assert "check-private-names.ps1" in result.out
    assert "-ListPath" in result.out


def test_unknown_argument_exits_two_naming_it(repo: Repo) -> None:
    result = repo.check("--bogus")
    assert result.code == 2
    assert "--bogus" in result.err
    assert "-h" in result.err
