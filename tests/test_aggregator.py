"""test_aggregator.py — tests for aggregator using hardcoded CommitInfo data."""

from __future__ import annotations

import datetime

import pytest

from gitsift.commit_walker import CommitInfo, FileChange
from gitsift.aggregator import (
    compute_file_churn,
    compute_author_stats,
    compute_time_series,
    detect_hotspots,
    analyse,
    FileChurn,
    AuthorStats,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dt(year: int, month: int, day: int, hour: int = 0) -> datetime.datetime:
    return datetime.datetime(year, month, day, hour)


def _make_commits() -> list[CommitInfo]:
    """Return a predictable set of commits for testing."""
    return [
        CommitInfo(
            hash="aaa",
            author_name="Alice",
            author_email="alice@example.com",
            datetime=_dt(2024, 1, 1),
            files_changed=[
                FileChange("src/main.py", lines_added=50, lines_deleted=0),
                FileChange("tests/test_main.py", lines_added=20, lines_deleted=0),
            ],
        ),
        CommitInfo(
            hash="bbb",
            author_name="Bob",
            author_email="bob@example.com",
            datetime=_dt(2024, 1, 8),
            files_changed=[
                FileChange("src/main.py", lines_added=10, lines_deleted=5),
                FileChange("src/utils.py", lines_added=30, lines_deleted=0),
            ],
        ),
        CommitInfo(
            hash="ccc",
            author_name="Alice",
            author_email="alice@example.com",
            datetime=_dt(2024, 1, 15),
            files_changed=[
                FileChange("src/main.py", lines_added=5, lines_deleted=20),
            ],
        ),
        CommitInfo(
            hash="ddd",
            author_name="Alice",
            author_email="alice@example.com",
            datetime=_dt(2024, 2, 1),
            files_changed=[
                FileChange("src/main.py", lines_added=100, lines_deleted=80),  # hotspot candidate
            ],
        ),
    ]


# ---------------------------------------------------------------------------
# compute_file_churn
# ---------------------------------------------------------------------------

def test_compute_file_churn_totals():
    commits = _make_commits()
    churn = compute_file_churn(commits)

    # Build a lookup by filepath
    by_path = {fc.filepath: fc for fc in churn}

    assert "src/main.py" in by_path
    mc = by_path["src/main.py"]
    assert mc.total_adds == 50 + 10 + 5 + 100  # 165
    assert mc.total_deletes == 0 + 5 + 20 + 80  # 105
    assert mc.change_count == 4
    assert mc.churn_score == mc.total_adds + mc.total_deletes  # 270

    assert "src/utils.py" in by_path
    uc = by_path["src/utils.py"]
    assert uc.total_adds == 30
    assert uc.total_deletes == 0
    assert uc.change_count == 1


def test_compute_file_churn_sorted_descending():
    commits = _make_commits()
    churn = compute_file_churn(commits)
    scores = [fc.churn_score for fc in churn]
    assert scores == sorted(scores, reverse=True)


def test_compute_file_churn_empty():
    assert compute_file_churn([]) == []


def test_compute_file_churn_no_files():
    commit = CommitInfo("x", "A", "a@b.com", _dt(2024, 1, 1), files_changed=[])
    churn = compute_file_churn([commit])
    assert churn == []


# ---------------------------------------------------------------------------
# detect_hotspots
# ---------------------------------------------------------------------------

def test_detect_hotspots_flags_outlier():
    """A file with vastly higher churn than its peers should be flagged as a hotspot.

    We build 8 "normal" files with ~10–15 churn each and one "hot" file with
    1000 churn. That guarantees hot.py is well above mean + 2*stdev.
    """
    normal_files = [f"normal{i}.py" for i in range(8)]
    commits = [
        CommitInfo(f"c{i}", "X", "x@x.com", _dt(2024, 1, i + 1),
                   [FileChange(normal_files[i], 10, 5)])
        for i in range(8)
    ]
    commits.append(
        CommitInfo("hot", "X", "x@x.com", _dt(2024, 1, 9), [FileChange("hot.py", 600, 400)])
    )
    churn = compute_file_churn(commits)
    hotspots = detect_hotspots(churn)

    hotspot_paths = {h.filepath for h in hotspots}
    assert "hot.py" in hotspot_paths
    assert "normal0.py" not in hotspot_paths


def test_detect_hotspots_marks_is_hotspot():
    """is_hotspot flag must be set on the FileChurn object in-place."""
    # 8 cold files (~7 churn each) + 1 extreme file (2000 churn)
    commits = [
        CommitInfo(f"c{i}", "X", "x@x.com", _dt(2024, 1, i + 1),
                   [FileChange(f"cold{i}.py", 5, 2)])
        for i in range(8)
    ]
    commits.append(
        CommitInfo("hot", "X", "x@x.com", _dt(2024, 1, 9), [FileChange("hot.py", 1200, 800)])
    )
    churn = compute_file_churn(commits)
    detect_hotspots(churn)

    by_path = {fc.filepath: fc for fc in churn}
    assert by_path["hot.py"].is_hotspot is True
    assert by_path["cold0.py"].is_hotspot is False


def test_detect_hotspots_returns_empty_on_single_file():
    churn = [FileChurn("a.py", 10, 5, 1, 15)]
    result = detect_hotspots(churn)
    assert result == []


# ---------------------------------------------------------------------------
# compute_author_stats
# ---------------------------------------------------------------------------

def test_compute_author_stats_counts():
    commits = _make_commits()
    stats = compute_author_stats(commits)

    by_name = {a.name: a for a in stats}
    assert "Alice" in by_name
    assert by_name["Alice"].commit_count == 3
    assert "Bob" in by_name
    assert by_name["Bob"].commit_count == 1


def test_compute_author_stats_sorted():
    commits = _make_commits()
    stats = compute_author_stats(commits)
    counts = [a.commit_count for a in stats]
    assert counts == sorted(counts, reverse=True)


def test_compute_author_stats_lines():
    commits = _make_commits()
    stats = compute_author_stats(commits)
    by_name = {a.name: a for a in stats}

    alice = by_name["Alice"]
    # Commit aaa: main.py(+50) + test_main.py(+20); ccc: main.py(+5); ddd: main.py(+100)
    assert alice.lines_added == 50 + 20 + 5 + 100  # 175
    assert alice.lines_deleted == 0 + 20 + 80  # 100

    bob = by_name["Bob"]
    assert bob.lines_added == 10 + 30  # 40
    assert bob.lines_deleted == 5


def test_compute_author_stats_top_files():
    commits = _make_commits()
    stats = compute_author_stats(commits)
    alice = next(a for a in stats if a.name == "Alice")
    # Alice touched src/main.py 3× — it should be in her top files
    assert "src/main.py" in alice.top_files


# ---------------------------------------------------------------------------
# compute_time_series
# ---------------------------------------------------------------------------

def test_compute_time_series_weekly():
    commits = _make_commits()
    ts = compute_time_series(commits, group_by="week")

    # commits are in weeks 1, 2, 3, 5 of 2024
    assert len(ts) >= 3
    assert all(isinstance(v, int) for v in ts.values())


def test_compute_time_series_monthly():
    commits = _make_commits()
    ts = compute_time_series(commits, group_by="month")

    assert "2024-01" in ts
    assert ts["2024-01"] == 3  # 3 commits in January
    assert "2024-02" in ts
    assert ts["2024-02"] == 1


def test_compute_time_series_daily():
    commits = _make_commits()
    ts = compute_time_series(commits, group_by="day")

    assert "2024-01-01" in ts
    assert ts["2024-01-01"] == 1


def test_compute_time_series_sorted():
    commits = _make_commits()
    ts = compute_time_series(commits, group_by="week")
    keys = list(ts.keys())
    assert keys == sorted(keys)


def test_compute_time_series_empty():
    ts = compute_time_series([])
    assert ts == {}


# ---------------------------------------------------------------------------
# analyse (integration)
# ---------------------------------------------------------------------------

def test_analyse_returns_all_fields():
    from gitsift.aggregator import AnalysisResult
    commits = _make_commits()
    result = analyse(commits, group_by="month")

    assert isinstance(result, AnalysisResult)
    assert result.file_churn
    assert result.author_stats
    assert result.time_series
    assert result.group_by == "month"
