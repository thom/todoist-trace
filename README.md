# todoist-trace

Interactive HTML dashboard and structured Markdown/CSV exporter to explore your Todoist completed task activity—with full project, section, and subtask hierarchy resolution.

## Features

- **Interactive HTML Dashboard**:
  - Standalone, single-file dashboard with zero external dependencies (works 100% offline, Light/Dark mode).
  - **KPIs & Charts**: Total tasks, active days, daily velocity timeline (clickable by day), on-time completion rate, and project share breakdown.
  - **Multi-Dimensional Filtering**: Dual-calendar date range picker with period presets (Week, Month, Quarter, Year, All Time), search bar, and multi-select filters across categories, parent projects, specific projects, priorities, due statuses, and `@tag` pills.
  - **Three View Modes**: Collapsible Daily Timeline, Project Tree Hierarchy, and Sortable Data Table.
- **Hierarchical Markdown & CSV Exports**:
  - **Markdown**: Nested headings by date, project tree depth, and section (`## Date` → `### Root Project` → `#### Sub-project` → `##### Section`) with hierarchical task bullet trees.
  - **CSV**: RFC 4180 compliant export with optional extended columns (`labels`, `description`, `priority`, `due_date`, `due_variance`).
- **Full Hierarchy Reconstruction**:
  - Resolves deep project trees, active/archived sections, and multi-level parent-child subtasks.
  - Preserves historical parent-child project links across Todoist project archiving via `~/.todoist-trace/hierarchy.json`.
- **Fast Offline SQLite Cache**:
  - Incrementally caches projects, sections, tasks, and completed events in `~/.todoist-trace/cache.db`, coalescing synced date intervals so exports run instantaneously offline.
- **Strictly Read-Only**:
  - Exclusively issues HTTP `GET` requests against the Todoist REST API v1 (`https://developer.todoist.com/api/v1/`). Never modifies or deletes user data.

## Installation

Requires Python 3.10+.

```bash
git clone https://github.com/thom/todoist-trace.git
cd todoist-trace

# Isolated global CLI install (recommended)
pipx install .

# Or editable development install
pip install -e .
```

## Quick Start

1. **Configure your Todoist API token** (via environment variable or `~/.todoist-trace/config.json`):
   ```bash
   export TODOIST_API_TOKEN="0123456789abcdef0123456789abcdef01234567"
   ```

2. **Sync your completed activity history to the local cache**:
   ```bash
   todoist-trace sync -s 2026-01-01
   ```

3. **Export an interactive HTML dashboard, Markdown log, or CSV**:
   ```bash
   # Interactive HTML dashboard with all metadata fields
   todoist-trace export -f html --all-fields -o dashboard.html

   # Hierarchical Markdown log for work projects
   todoist-trace export -f markdown -c work --all-fields -o work_log.md

   # Standard CSV export
   todoist-trace export -f csv --all-fields -o activities.csv
   ```

## Subcommands

| Subcommand | Description | Example |
| :--- | :--- | :--- |
| `sync` | Pull projects, sections, tasks, and completed events into `~/.todoist-trace/cache.db`. | `todoist-trace sync -s 2026-07-01` |
| `export` | Generate HTML, Markdown, or CSV offline from the local SQLite cache. | `todoist-trace export -f html --all-fields -o trace.html` |
| `run` | Run `sync` followed immediately by `export` in a single pass (default when no subcommand is given). | `todoist-trace -s 2026-09-01 -f md -o monthly.md` |
| `hierarchy` | Inspect or assign parent projects for archived projects (`list`, `set`). | `todoist-trace hierarchy list --unassigned` |
| `status` | Display SQLite cache statistics, entity counts, and synchronized UTC intervals. | `todoist-trace status` |

## Configuration

Settings are resolved in order of precedence: **CLI Flags** → **Environment Variables** → **`~/.todoist-trace/config.json`** → **Defaults**.

Example `~/.todoist-trace/config.json`:

```json
{
  "token": "0123456789abcdef0123456789abcdef01234567",
  "format": "html",
  "category": "all",
  "timezone": "Europe/Zurich",
  "categories": {
    "work": ["work", "work-areas"],
    "personal": ["personal", "personal-areas"]
  },
  "include_labels": true,
  "include_descriptions": true,
  "include_priorities": true,
  "include_due_dates": true
}
```

## CLI Options Reference

| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--start-date` | `-s` | `None` | Start date filter in `YYYY-MM-DD` format (inclusive). |
| `--end-date` | `-e` | `None` | End date filter in `YYYY-MM-DD` format (inclusive). |
| `--format` | `-f` | `csv` | Export format: `html`, `markdown` (`md`), or `csv`. |
| `--output` | `-o` | Auto | Output file path (`todoist_trace_export.{html,md,csv}`). |
| `--category` | `-c` | `all` | Category filter: `work`, `personal`, `others`, or `all`. |
| `--timezone` | `-z` | `local` | IANA timezone name (e.g. `Europe/Zurich`, `UTC`) or `local`. |
| `--all-fields` | | `False` | Enable all extended metadata (`--labels`, `--descriptions`, `--priorities`, `--due-dates`). |
| `--refresh` | | `False` | Force re-fetching data from the API and re-resolving cached hierarchies. |
| `--token` | `-t` | Env/Config | Todoist API token (`TODOIST_API_TOKEN`). |
| `--config` | | Auto | Path to custom configuration file (`JSON` or `.env`). |
| `--cache-file` | | `~/.todoist-trace/cache.db` | Path to local SQLite cache database. |
| `--quiet` / `--plain` | `-q` | `False` | Suppress progress output (`-q`) or use plain-text milestone logs (`--plain`). |

## Development

Run the test suite with `pytest`:

```bash
pytest
```

## License

MIT License — see [LICENSE](LICENSE) for details.
