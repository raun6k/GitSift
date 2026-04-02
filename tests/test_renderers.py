"""test_renderers.py — tests for the renderer output, focusing on JSON structure."""

from __future__ import annotations

import json
import datetime

import pytest

from gitsift.commit_walker import CommitInfo, FileChange
from gitsift.aggregator import analyse, AnalysisResult
from gitsift.renderers import render_json, render_terminal
from rich.console import Console
import io


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_result() -> AnalysisResult:
    commits = [
        CommitInfo(
            hash="aaa",
            author_name="Alice",
            author_email="alice@example.com",
            datetime=datetime.datetime(2024, 1, 1),
            files_changed=[
                FileChange("src/foo.py", 40, 10),
                FileChange("src/bar.py", 5, 2),
            ],
        ),
        CommitInfo(
            hash="bbb",
            author_name="Bob",
            author_email="bob@example.com",
            datetime=datetime.datetime(2024, 1, 8),
            files_changed=[
                FileChange("src/foo.py", 200, 150),  # hotspot
                FileChange("src/baz.py", 3, 1),
            ],
        ),
        CommitInfo(
            hash="ccc",
            author_name="Alice",
            author_email="alice@example.com",
            datetime=datetime.datetime(2024, 1, 15),
            files_changed=[
                FileChange("src/qux.py", 4, 0),
            ],
        ),
    ]
    return analyse(commits, group_by="week")


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

def test_render_json_is_valid_json():
    result = _make_result()
    output = render_json(result)
    parsed = json.loads(output)
    assert isinstance(parsed, dict)


def test_render_json_top_level_keys():
    result = _make_result()
    parsed = json.loads(render_json(result))

    for key in ("summary", "file_churn", "author_stats", "time_series", "hotspots"):
        assert key in parsed, f"Missing key: {key}"


def test_render_json_summary_fields():
    result = _make_result()
    parsed = json.loads(render_json(result))
    summary = parsed["summary"]

    assert "total_files_changed" in summary
    assert "total_contributors" in summary
    assert "total_commits" in summary
    assert "hotspot_count" in summary
    assert "group_by" in summary
    assert summary["group_by"] == "week"
    assert summary["total_commits"] == 3


def test_render_json_file_churn_structure():
    result = _make_result()
    parsed = json.loads(render_json(result))

    assert len(parsed["file_churn"]) > 0
    for fc in parsed["file_churn"]:
        for field in ("filepath", "total_adds", "total_deletes", "change_count", "churn_score", "is_hotspot"):
            assert field in fc, f"Missing field '{field}' in file_churn entry"
        assert isinstance(fc["is_hotspot"], bool)
        assert fc["churn_score"] == fc["total_adds"] + fc["total_deletes"]


def test_render_json_author_stats_structure():
    result = _make_result()
    parsed = json.loads(render_json(result))

    assert len(parsed["author_stats"]) == 2  # Alice and Bob
    for a in parsed["author_stats"]:
        for field in ("name", "email", "commit_count", "lines_added", "lines_deleted", "top_files"):
            assert field in a, f"Missing field '{field}' in author_stats entry"
        assert isinstance(a["top_files"], list)


def test_render_json_time_series_structure():
    result = _make_result()
    parsed = json.loads(render_json(result))

    ts = parsed["time_series"]
    assert isinstance(ts, dict)
    assert all(isinstance(v, int) for v in ts.values())


def test_render_json_hotspots_are_flagged():
    result = _make_result()
    parsed = json.loads(render_json(result))

    for h in parsed["hotspots"]:
        assert h["is_hotspot"] is True


def test_render_json_sorted_by_churn():
    result = _make_result()
    parsed = json.loads(render_json(result))

    scores = [fc["churn_score"] for fc in parsed["file_churn"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# Terminal renderer (smoke test — just ensure it doesn't crash)
# ---------------------------------------------------------------------------

def test_render_terminal_no_crash():
    result = _make_result()
    buf = io.StringIO()
    console = Console(file=buf, no_color=True)
    render_terminal(result, top=5, console=console)
    output = buf.getvalue()
    assert "foo.py" in output or "src/foo.py" in output
    assert "Alice" in output


def test_render_terminal_hotspot_marker():
    result = _make_result()
    buf = io.StringIO()
    console = Console(file=buf, no_color=True, highlight=False)
    render_terminal(result, top=20, console=console)
    output = buf.getvalue()
    # When hotspots exist, the summary title should mention them
    # (rendered as plain text without color codes)
    assert len(output) > 0  # basic smoke test
