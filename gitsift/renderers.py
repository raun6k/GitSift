"""renderers.py — output the analysis as Rich terminal tables, PNG charts, or JSON."""

from __future__ import annotations

import json
import os
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich import box

from gitsift.aggregator import AnalysisResult, FileChurn, AuthorStats


# ---------------------------------------------------------------------------
# Terminal renderer (Rich)
# ---------------------------------------------------------------------------

def render_terminal(result: AnalysisResult, top: int = 20, console: Optional[Console] = None) -> None:
    """Print Rich-formatted tables to *console* (defaults to stdout)."""
    if console is None:
        console = Console()

    _render_churn_table(result, top, console)
    console.print()
    _render_author_table(result, top, console)
    console.print()
    _render_time_series_table(result, top, console)


def _render_churn_table(result: AnalysisResult, top: int, console: Console) -> None:
    title = f"Top {top} Churned Files"
    if result.hotspots:
        title += f"  [bold red]({len(result.hotspots)} hotspot{'s' if len(result.hotspots) != 1 else ''})[/bold red]"

    table = Table(title=title, box=box.ROUNDED, show_lines=False, highlight=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("File", style="cyan", no_wrap=False, min_width=30)
    table.add_column("+Lines", style="green", justify="right")
    table.add_column("-Lines", style="red", justify="right")
    table.add_column("Changes", justify="right")
    table.add_column("Churn", justify="right", style="yellow")
    table.add_column("", width=4)  # hotspot marker

    for i, fc in enumerate(result.file_churn[:top], 1):
        marker = "[bold red]🔥[/bold red]" if fc.is_hotspot else ""
        row_style = "bold" if fc.is_hotspot else ""
        table.add_row(
            str(i),
            fc.filepath,
            f"{fc.total_adds:,}",
            f"{fc.total_deletes:,}",
            f"{fc.change_count:,}",
            f"{fc.churn_score:,}",
            marker,
            style=row_style,
        )

    console.print(table)


def _render_author_table(result: AnalysisResult, top: int, console: Console) -> None:
    table = Table(title=f"Top {top} Contributors", box=box.ROUNDED, show_lines=False, highlight=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Author", style="cyan", min_width=20)
    table.add_column("Email", style="dim", min_width=20)
    table.add_column("Commits", justify="right", style="yellow")
    table.add_column("+Lines", justify="right", style="green")
    table.add_column("-Lines", justify="right", style="red")
    table.add_column("Top Files", style="dim")

    for i, a in enumerate(result.author_stats[:top], 1):
        top_files_str = ", ".join(os.path.basename(f) for f in a.top_files[:3])
        table.add_row(
            str(i),
            a.name,
            a.email,
            f"{a.commit_count:,}",
            f"{a.lines_added:,}",
            f"{a.lines_deleted:,}",
            top_files_str,
        )

    console.print(table)


def _render_time_series_table(result: AnalysisResult, top: int, console: Console) -> None:
    label = result.group_by.capitalize() + "ly" if result.group_by != "month" else "Monthly"
    table = Table(
        title=f"{label} Commit Activity (last {top} periods)",
        box=box.ROUNDED,
        show_lines=False,
    )
    table.add_column("Period", style="cyan", min_width=12)
    table.add_column("Commits", justify="right", style="yellow")
    table.add_column("Bar", min_width=30)

    items = list(result.time_series.items())[-top:]
    if not items:
        return
    max_count = max(count for _, count in items) or 1

    for period, count in items:
        bar_len = int((count / max_count) * 30)
        bar = "█" * bar_len
        table.add_row(period, str(count), f"[green]{bar}[/green]")

    console.print(table)


# ---------------------------------------------------------------------------
# Chart renderer (matplotlib)
# ---------------------------------------------------------------------------

def render_charts(result: AnalysisResult, top: int = 20, output_dir: str = ".") -> list[str]:
    """Generate PNG charts and save them to *output_dir*.

    Returns a list of file paths that were written.
    """
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker
    import numpy as np

    os.makedirs(output_dir, exist_ok=True)
    paths: list[str] = []

    # --- Bar chart: top churned files ---
    churn_data = result.file_churn[:top]
    if churn_data:
        labels = [os.path.basename(f.filepath) or f.filepath for f in churn_data]
        adds = [f.total_adds for f in churn_data]
        deletes = [f.total_deletes for f in churn_data]

        y = range(len(labels))
        fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.4)))
        ax.barh(list(y), adds, color="#2ecc71", label="Lines added")
        ax.barh(list(y), [-d for d in deletes], color="#e74c3c", label="Lines deleted")
        ax.set_yticks(list(y))
        ax.set_yticklabels(labels, fontsize=8)
        ax.invert_yaxis()
        ax.axvline(0, color="black", linewidth=0.8)
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, _: f"{abs(int(x)):,}"))
        ax.set_title(f"Top {top} Churned Files", fontsize=13, fontweight="bold")
        ax.set_xlabel("Lines changed")
        ax.legend()
        fig.tight_layout()
        chart_path = os.path.join(output_dir, "churn_chart.png")
        fig.savefig(chart_path, dpi=150)
        plt.close(fig)
        paths.append(chart_path)

    # --- Heatmap: commits by day-of-week × hour ---
    # We need raw commit datetimes; reconstruct from time_series isn't enough,
    # so we pass only the AnalysisResult which already holds time_series.
    # The heatmap requires per-commit datetime data stored on the result — we
    # attach it as an optional attribute in cli.py.
    commit_datetimes: list = getattr(result, "_commit_datetimes", [])
    if commit_datetimes:
        grid = np.zeros((7, 24), dtype=int)
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for dt in commit_datetimes:
            grid[dt.weekday()][dt.hour] += 1

        fig, ax = plt.subplots(figsize=(14, 4))
        im = ax.imshow(grid, aspect="auto", cmap="YlOrRd")
        ax.set_xticks(range(24))
        ax.set_xticklabels([f"{h:02d}" for h in range(24)], fontsize=7)
        ax.set_yticks(range(7))
        ax.set_yticklabels(days)
        ax.set_xlabel("Hour of day (UTC)")
        ax.set_ylabel("Day of week")
        ax.set_title("Commit Frequency Heatmap (day-of-week × hour)", fontsize=13, fontweight="bold")
        plt.colorbar(im, ax=ax, label="Commits")
        fig.tight_layout()
        heatmap_path = os.path.join(output_dir, "commit_heatmap.png")
        fig.savefig(heatmap_path, dpi=150)
        plt.close(fig)
        paths.append(heatmap_path)

    return paths


# ---------------------------------------------------------------------------
# JSON renderer
# ---------------------------------------------------------------------------

def render_json(result: AnalysisResult) -> str:
    """Serialise *result* to a JSON string and return it."""

    def _fc_to_dict(fc: FileChurn) -> dict:
        return {
            "filepath": fc.filepath,
            "total_adds": fc.total_adds,
            "total_deletes": fc.total_deletes,
            "change_count": fc.change_count,
            "churn_score": fc.churn_score,
            "is_hotspot": fc.is_hotspot,
        }

    def _author_to_dict(a: AuthorStats) -> dict:
        return {
            "name": a.name,
            "email": a.email,
            "commit_count": a.commit_count,
            "lines_added": a.lines_added,
            "lines_deleted": a.lines_deleted,
            "top_files": a.top_files,
        }

    payload = {
        "summary": {
            "total_files_changed": len(result.file_churn),
            "total_contributors": len(result.author_stats),
            "total_commits": sum(result.time_series.values()),
            "hotspot_count": len(result.hotspots),
            "group_by": result.group_by,
        },
        "file_churn": [_fc_to_dict(fc) for fc in result.file_churn],
        "author_stats": [_author_to_dict(a) for a in result.author_stats],
        "time_series": result.time_series,
        "hotspots": [_fc_to_dict(fc) for fc in result.hotspots],
    }

    return json.dumps(payload, indent=2)
