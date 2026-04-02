# GitSift

A Python CLI tool that analyzes any local Git repository and generates developer activity reports — code churn metrics, contributor stats, and commit frequency heatmaps.

## Features

- **File churn analysis** — ranks files by total lines added + deleted, flags refactoring hotspots
- **Contributor leaderboard** — commits, lines changed, and most-touched files per author
- **Time-series activity** — commit frequency grouped by day, week, or month
- **Three output modes** — Rich terminal tables, exportable PNG charts, or JSON for CI pipelines

## Installation

```bash
git clone https://github.com/raun6k/GitSift.git
cd GitSift
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage

```bash
# Terminal tables (default)
gitsift --repo /path/to/repo

# Filter by date range
gitsift --repo /path/to/repo --since 2024-01-01 --until 2024-12-31

# Show top 10 results, grouped by month
gitsift --repo /path/to/repo --top 10 --group-by month

# Export PNG charts
gitsift --repo /path/to/repo --charts --output-dir ./charts

# JSON output (pipeable to jq)
gitsift --repo /path/to/repo --json | jq .
```

## Options

| Flag | Default | Description |
|---|---|---|
| `--repo PATH` | `.` | Path to the Git repository |
| `--since DATE` | — | Only include commits on or after this date (YYYY-MM-DD) |
| `--until DATE` | — | Only include commits on or before this date (YYYY-MM-DD) |
| `--top N` | `20` | Number of results per table |
| `--group-by` | `week` | Time-series granularity: `day`, `week`, or `month` |
| `--charts` | — | Generate PNG charts |
| `--output-dir DIR` | `.` | Directory to save charts |
| `--json` | — | Output as JSON instead of tables |
| `--no-progress` | — | Disable the progress bar |

## Tech Stack

- [GitPython](https://gitpython.readthedocs.io/) — programmatic Git access
- [Rich](https://rich.readthedocs.io/) — terminal tables and progress bars
- [matplotlib](https://matplotlib.org/) — PNG chart generation

## Running Tests

```bash
pip install -e ".[dev]"
pytest -v
```
