# todoist-trace

A robust, read-only Python CLI tool to export Todoist activity logs into structured CSV and Markdown files with multi-level project and task hierarchy resolution, local timezone normalization, interval-aware SQLite caching, and live visual progress reporting.

---

## Features

- **Multi-Level Project Tree Resolution**: Automatically traverses project hierarchies of arbitrary depth (e.g., `work-areas / admin / email / vendor-contracts`) to extract the root ancestor and relative project paths. Handles archived projects seamlessly.
- **Project Section Resolution**: Automatically resolves Todoist section IDs to section names (e.g. `Sprint Deliverables`, `Sprint 1`), grouping tasks under section subheadings in Markdown and providing a dedicated `section` column in CSV exports.
- **Recursive Task Ancestry Resolution**: Reconstructs deep parent-child subtask relationships (e.g., `Sprint Planning / Backend / Authentication Service`) by querying and caching task parentage.
- **Local Timezone Normalization**: Automatically converts Todoist UTC activity timestamps into the user's local timezone (or configured IANA timezone, e.g. `Europe/Zurich`), ensuring cross-midnight tasks are attributed to the true local calendar day.
- **Interactive Visual Progress Reporting**:
  - Displays a clean boxed metadata header with active range, calendar day count, timezone, and cache path.
  - Live Unicode block progress bar (`[██████████░░░░░░░░]`), Braille animation spinner, calendar day completion percentage, throughput (`tasks/s`), and remaining time countdown (`ETA MM:SS`).
  - Automatically adapts to terminal width (`shutil.get_terminal_size()`) and collapses to clean milestone logs when piped or running in CI (`NO_COLOR` standard compliant).
- **Hierarchical Markdown Export**:
  - **Nested Headings**: Structured heading levels by project depth and section (`## Date` -> `### Root Project` -> `#### Sub-project` -> `##### Section`).
  - **Flat Headings & Paths**: Optional flat representation with slash-separated headings (`#### admin/email`) and flat bullet paths.
- **Interactive HTML Dashboard Export**:
  - Standalone, self-contained single-page dashboard with zero external dependencies (works 100% offline).
  - KPI metric cards (total tasks, active days, tasks/day velocity, on-time completion rate, top projects).
  - Interactive SVG charts (daily activity velocity timeline with clickable day filtering, project share breakdown).
  - Multi-dimensional filters (search box, category, project, priority, due status, @tag filter).
  - Three distinct view modes: Collapsible Daily Timeline, Project Tree Hierarchy, and Sortable Data Table.
  - Built-in Dark and Light mode toggle with auto-detection and persistence.
- **RFC 4180 Compliant CSV Export**: Clean, standard CSV output escaping commas, quotes, and newlines (`top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id`).
- **Interval-Aware SQLite Cache Engine**:
  - Automatically caches projects, sections, tasks, completed events, and synchronized date ranges in `~/.todoist-trace/cache.db`.
  - Coalesces contiguous intervals across runs, avoiding redundant API calls while tracking zero-activity days permanently.
  - B-tree indexing on `event_date` for sub-millisecond date range queries.
  - Automatic migration from legacy `cache.json` without data loss.
- **Strict Read-Only & Non-Destructive Policy**:
  - Exclusively issues HTTP `GET` requests (`https://developer.todoist.com/api/v1/`).
  - Never mutates, updates, creates, completes, or deletes any tasks, projects, or user data.

---

## Architecture

The project is structured as a modular package with dedicated subsystems:

```text
todoist-trace/
├── todoist_trace/              # Core package
│   ├── __init__.py             # Public package exports
│   ├── __main__.py             # python -m todoist_trace entrypoint
│   ├── api.py                  # Read-only Todoist REST API v1 client with progress hooks
│   ├── cache.py                # Interval-aware SQLite and JSON cache engines
│   ├── cli.py                  # CLI argument parsing and precedence resolution
│   ├── config.py               # Dotfile (~/.todoist-trace/) & .env loader, timezone resolver
│   ├── exporters.py            # RFC 4180 CSV & hierarchical Markdown generators
│   ├── filters.py              # Category and date range filtering logic
│   ├── main.py                 # Pipeline execution and orchestration
│   ├── progress.py             # Visual terminal progress reporter, day tracking, ETA
│   └── resolvers.py            # Recursive project tree, section, and task hierarchy resolvers
├── tests/                      # Modular test suite (109 tests)
│   ├── conftest.py             # Shared fixtures and path configuration
│   ├── test_api.py             # Read-only REST API client and section endpoint tests
│   ├── test_cache.py           # SQLite, interval arithmetic, and auto-migration tests
│   ├── test_cli_config.py      # Argument and configuration precedence tests
│   ├── test_exporters.py       # CSV and Markdown formatting tests
│   ├── test_filters.py         # Category and date filtering tests
│   ├── test_package.py         # Submodule and public export tests
│   ├── test_progress.py        # Progress bars, day percentage, and ETA tests
│   └── test_resolvers.py       # Project, section, and task tree resolution tests
├── todoist_trace.py            # Root CLI launcher script (backward compatible)
├── pytest.ini                  # Pytest configuration
├── AGENTS.md                   # Repository conventions and guidelines
├── LICENSE                     # MIT License
└── README.md                   # Project documentation
```

---

## Installation

### Prerequisites

- Python 3.10+
- `pip`

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/thom/todoist-trace.git
   cd todoist-trace
   ```

2. Install dependencies:
   ```bash
   pip install requests pytest
   ```

---

## Configuration

`todoist-trace` resolves configuration settings in the following order of precedence:

1. **CLI Flag** (e.g. `--token <TOKEN>`)
2. **Environment Variable** (e.g. `export TODOIST_API_TOKEN=<TOKEN>`)
3. **Configuration File** (`~/.todoist-trace/config.json`, `.env`, or `--config <PATH>`)
4. **Default Setting**

### Configuration File (`~/.todoist-trace/config.json`)

Create `~/.todoist-trace/config.json` to store your API token and preferred defaults:

```json
{
  "token": "0123456789abcdef0123456789abcdef01234567",
  "format": "markdown",
  "category": "all",
  "timezone": "Europe/Zurich",
  "include_labels": true,
  "include_descriptions": true,
  "include_priorities": true,
  "include_due_dates": true
}
```

Alternatively, you can provide environment variables in a `.env` file:

```env
TODOIST_API_TOKEN=0123456789abcdef0123456789abcdef01234567
TODOIST_TRACE_FORMAT=markdown
TODOIST_TRACE_CATEGORY=all
TODOIST_TRACE_TIMEZONE=Europe/Zurich
TODOIST_TRACE_LABELS=true
TODOIST_TRACE_DESCRIPTIONS=true
TODOIST_TRACE_PRIORITIES=true
TODOIST_TRACE_DUE_DATES=true
```

---

## Usage & Git-Style Subcommands

`todoist-trace` supports a two-stage Git-style operation:
1. **`sync`**: Pulls 100% of available metadata (projects, sections, labels, completed activities, task hierarchies, descriptions, priorities, due dates) from the Todoist API into a persistent local SQLite database (`~/.todoist-trace/cache.db`).
2. **`export`**: Operates **100% offline** on the local SQLite cache to filter, slice, and generate Markdown or CSV reports instantaneously without hitting API rate limits.
3. **`status`**: Shows cache statistics, entity counts, covered date ranges, and last sync timestamp.
4. **`run`** (default): Runs `sync` followed immediately by `export` in a single pass (maintains seamless backward compatibility when invoked directly with options).

```bash
# General invocation syntax:
todoist-trace <subcommand> [options]

# Or via Python module / launcher script:
python3 todoist_trace.py <subcommand> [options]
python3 -m todoist_trace <subcommand> [options]
```

### Visual Terminal Progress

When executing a sync or export, `todoist-trace` displays a real-time visual progress dashboard:

```text
╭─ todoist-trace ────────────────────────────────────────────────────────╮
│ Range    : 2026-07-01 to 2026-10-03 (95 days)                          │
│ Timezone : Europe/Zurich                                              │
│ Category : all                                                         │
│ Format   : MARKDOWN (nested)                                           │
│ Cache    : ~/.todoist-trace/cache.db (SQLite)                          │
╰────────────────────────────────────────────────────────────────────────╯

[1/4] ✔ Projects: 48 active, 12 archived retrieved
[2/4] ⠹ Syncing activities: 2026-07-01 → 2026-10-03 (95 days)
      ⠸ [████████████████░░░░░░░░░░]  100.0% • Day 95/95 • 992 tasks • 142 tasks/s
[3/4] ✔ Task hierarchies: 992 records resolved in 00:01
[4/4] ✔ Export complete: todoist_trace_export.md (992 of 992 records matched, MARKDOWN (nested))
```

### Subcommands & Common Commands

#### 1. Synchronize Data (`sync`)
Retrieves all metadata from the Todoist API and stores it in the local SQLite cache:

```bash
# Sync activities from a specific date to today:
python3 todoist_trace.py sync -s 2026-07-01

# Sync a specific date range:
python3 todoist_trace.py sync -s 2026-07-01 -e 2026-09-30

# Force re-fetching all data and refresh cache:
python3 todoist_trace.py sync --refresh
```

#### 2. Export Offline from Cache (`export`)
Runs offline directly from your local SQLite cache. Slices by category, date range, or format without needing network access or an API token:

```bash
# Export the last 30 days to Markdown with all extended metadata:
python3 todoist_trace.py export -f markdown -s 2026-09-02 -e 2026-10-02 --all-fields -o my_trace.md

# Export work projects to CSV:
python3 todoist_trace.py export -c work -f csv -o work_activities.csv

# Generate interactive HTML dashboard with charts and filters:
python3 todoist_trace.py export -f html --all-fields -o activity_dashboard.html
```

#### 3. Check Cache Status (`status`)
Inspects your local cache database, showing file size, entity counts, date boundaries, and synced UTC intervals:

```bash
python3 todoist_trace.py status
```

Output example:
```text
Todoist Trace Cache Status
────────────────────────────────
  Location:     ~/.todoist-trace/cache.db (SQLite)
  File Size:    1.24 MB
  Cache State:  Active
  Last Sync:    2026-10-03T08:15:23Z

Cached Entities:
  • Projects:   48
  • Sections:   12
  • Labels:     35
  • Tasks:      842
  • Activities: 992 (2026-07-01T00:00:00Z → 2026-10-03T08:15:23Z)

Synchronized UTC Ranges:
  • 2026-07-01T00:00:00Z  →  2026-10-03T08:15:23Z
```

#### 4. Single-Pass Execution (`run` or flag-only)
Combines `sync` and `export` in a single step (ideal for one-shot runs or cron jobs):

```bash
# Explicit run subcommand:
python3 todoist_trace.py run -s 2026-09-01 -f markdown -o monthly.md

# Direct flag-only invocation (automatically defaults to 'run'):
python3 todoist_trace.py -s 2026-09-01 -f markdown -o monthly.md
```

---

## CLI Options

### Common Options (All Commands)
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--config` | | Auto | Path to custom config file (`JSON` or `.env`). |
| `--cache-file` | | `~/.todoist-trace/cache.db` | Path to local cache file. |
| `--quiet` | `-q` | `False` | Suppress progress updates and non-error messages. |
| `--no-color` | | `False` | Disable ANSI colors in terminal output. |
| `--plain` | | `False` | Use clean plain-text progress updates (no in-place cursor overwrites). |

### Date & Time Options (`sync`, `export`, `run`)
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--start-date` | `-s` | `None` | Start date filter in `YYYY-MM-DD` format (inclusive). |
| `--end-date` | `-e` | `None` | End date filter in `YYYY-MM-DD` format (inclusive). |
| `--timezone` | `-z` | `local` | Timezone for daily overview and exports (e.g. `Europe/Zurich`, `UTC`, or `local`). |

### Sync Options (`sync`, `run`)
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--token` | `-t` | Env/Config | Todoist API token (falls back to `TODOIST_API_TOKEN` env var or config file). |
| `--refresh` | | `False` | Force re-fetching all data from the API and refresh cache. |
| `--no-cache` | | `False` | Disable persistent local cache. |

### Export Options (`export`, `run`)
| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--format` | `-f` | `csv` | Output format: `csv`, `markdown` / `md`, or `html`. |
| `--output` | `-o` | Auto | Output file path (default: `todoist_trace_export.csv`, `.md`, or `.html`). |
| `--category` | `-c` | `all` | Top-level project filter: `work`, `personal`, or `all`. |
| `--labels` / `--include-labels` | | `False` | Include task labels in exports. |
| `--descriptions` / `--include-descriptions` | | `False` | Include task descriptions/notes in exports. |
| `--priorities` / `--include-priorities` | | `False` | Include task priorities (`p1`-`p4`) in exports. |
| `--due-dates` / `--include-due-dates` | | `False` | Include original due dates and completion variance in exports. |
| `--all-fields` | | `False` | Shorthand enabling all extended metadata fields. |

---

## Export Formats

### 1. Markdown Export Example

#### Hierarchical Task Outline
```markdown
## 2026-09-30

### work
#### sprint-planning
- Sprint Deliverables
  - Client Portal
  - Services
    - Database
    - Auth
```

#### Extended Metadata (`--all-fields`)
```markdown
## 2026-09-30

### work
#### sprint-planning
- Sprint Deliverables
  - Client Portal [p2] [@frontend]
  - Services
    - Database [p1] [@infra] [Due: 2026-09-30, Done: 2026-09-30 (on time)]
      > Run migration scripts before deploy
    - Auth [p1] [@security, @urgent] [Due: 2026-09-29, Done: 2026-09-30 (+1d overdue)]
      > Refresh tokens and rotate signing secret
```

### 2. CSV Export Example

Conforms strictly to RFC 4180 with standard headers:

```csv
top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id
work,sprint-planning,Sprint 1,2026-09-30,10:00:00,Sprint Deliverables / Services / Auth,p2,p1,ev_101
personal,finances/taxes,,2026-09-30,14:20:00,"Submit quarterly return, Q3",,proj_99,ev_102
```

When extended metadata fields are enabled (e.g. `--all-fields`), corresponding metadata columns are appended:

```csv
top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id,labels,description,priority,due_date,due_variance
work,sprint-planning,Sprint 1,2026-09-30,10:00:00,Sprint Deliverables / Services / Auth,p2,p1,ev_101,"security,urgent","Refresh tokens and rotate signing secret",p1,2026-09-29,+1d overdue
```

---

## Database Schema (`~/.todoist-trace/cache.db`)

The SQLite cache uses indexed relational tables with JSON payload storage and synchronized range tracking:

```sql
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    name TEXT,
    is_archived INTEGER,
    is_deleted INTEGER,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    project_id TEXT,
    name TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS labels (
    id TEXT PRIMARY KEY,
    name TEXT,
    color TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    parent_id TEXT,
    content TEXT,
    payload TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    event_date TEXT,
    object_id TEXT,
    parent_project_id TEXT,
    extra_data TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date);

CREATE TABLE IF NOT EXISTS sync_ranges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    is_genesis INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

---

## Running Tests

Execute the full test suite with `pytest`:

```bash
pytest -v
```

Run tests for an individual subsystem:

```bash
pytest -v tests/test_progress.py
pytest -v tests/test_cache.py
pytest -v tests/test_resolvers.py
pytest -v tests/test_cli_config.py
pytest -v tests/test_exporters.py
```

---

## License

MIT License - see [LICENSE](LICENSE) for details.
