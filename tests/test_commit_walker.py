"""test_commit_walker.py — tests for commit_walker using a temporary Git repo."""

from __future__ import annotations

import datetime
import os

import git
import pytest

from gitsift.commit_walker import walk_commits, CommitInfo, FileChange


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_repo(tmp_path):
    """Create a temporary Git repo with 5 commits and known content."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test User").release()
    repo.config_writer().set_value("user", "email", "test@example.com").release()

    # Commit 1: add file_a.py (5 lines)
    file_a = tmp_path / "file_a.py"
    file_a.write_text("\n".join(f"line{i}" for i in range(5)))
    repo.index.add(["file_a.py"])
    repo.index.commit("Add file_a")

    # Commit 2: add file_b.py (3 lines)
    file_b = tmp_path / "file_b.py"
    file_b.write_text("\n".join(f"lineB{i}" for i in range(3)))
    repo.index.add(["file_b.py"])
    repo.index.commit("Add file_b")

    # Commit 3: modify file_a (add 2 more lines)
    file_a.write_text("\n".join(f"line{i}" for i in range(7)))
    repo.index.add(["file_a.py"])
    repo.index.commit("Extend file_a")

    # Commit 4: modify file_b (delete 1 line)
    file_b.write_text("\n".join(f"lineB{i}" for i in range(2)))
    repo.index.add(["file_b.py"])
    repo.index.commit("Shorten file_b")

    # Commit 5: add file_c.py
    file_c = tmp_path / "file_c.py"
    file_c.write_text("only_one_line")
    repo.index.add(["file_c.py"])
    repo.index.commit("Add file_c")

    return repo, tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_walk_returns_commit_info_objects(temp_repo):
    _, path = temp_repo
    commits = walk_commits(str(path), show_progress=False)

    assert len(commits) == 5
    for c in commits:
        assert isinstance(c, CommitInfo)
        assert c.hash
        assert c.author_name == "Test User"
        assert c.author_email == "test@example.com"
        assert isinstance(c.datetime, datetime.datetime)


def test_walk_files_changed_populated(temp_repo):
    _, path = temp_repo
    commits = walk_commits(str(path), show_progress=False)

    # The newest commit is first (default git log order).
    # Commit 5 adds file_c.py — it should appear in files_changed.
    newest = commits[0]
    paths = [fc.path for fc in newest.files_changed]
    assert "file_c.py" in paths


def test_walk_lines_added_positive(temp_repo):
    _, path = temp_repo
    commits = walk_commits(str(path), show_progress=False)

    # Commit 1 (last in list) adds file_a.py — lines_added should be > 0.
    first_commit = commits[-1]
    assert any(fc.lines_added > 0 for fc in first_commit.files_changed)


def test_walk_since_filter(temp_repo):
    _, path = temp_repo
    # Filter to commits in the far future — should return nothing.
    future = datetime.datetime(2099, 1, 1)
    commits = walk_commits(str(path), since=future, show_progress=False)
    assert commits == []


def test_walk_until_filter(temp_repo):
    _, path = temp_repo
    # Filter to commits before epoch — should return nothing.
    past = datetime.datetime(1970, 1, 1)
    commits = walk_commits(str(path), until=past, show_progress=False)
    assert commits == []


def test_walk_all_commits_within_no_filter(temp_repo):
    _, path = temp_repo
    commits = walk_commits(str(path), show_progress=False)
    assert len(commits) == 5


def test_walk_file_change_dataclass(temp_repo):
    _, path = temp_repo
    commits = walk_commits(str(path), show_progress=False)
    for commit in commits:
        for fc in commit.files_changed:
            assert isinstance(fc, FileChange)
            assert isinstance(fc.path, str)
            assert isinstance(fc.lines_added, int)
            assert isinstance(fc.lines_deleted, int)
            assert fc.lines_added >= 0
            assert fc.lines_deleted >= 0
