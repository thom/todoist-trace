# todoist-trace

A robust, read-only Python CLI tool to export Todoist activity logs into structured CSV and Markdown files with multi-level project and task hierarchy resolution, local timezone normalization, interval-aware SQLite caching, and live visual progress reporting.

---

## Features

- **Multi-Level Project Tree Resolution**: Automatically traverses project hierarchies of arbitrary depth (e.g., `work-areas / admin / email / vendor-contracts`) to extract the root ancestor and relative project paths. Handles archived projects seamlessly.
- **Recursive Task Ancestry Resolution**: Reconstructs deep parent-child subtask relationships (e.g., `Sprint Planning / Backend / Authentication Service`) by querying and caching task parentage.
- **Local Timezone Normalization**: Automatically converts Todoist UTC activity timestamps into the user's local timezone (or configured IANA timezone, e.g. `Europe/Zurich`), ensuring cross-midnight tasks are attributed to the true local calendar day.
- **Interactive Visual Progress Reporting**:
  - Displays a clean boxed metadata header with active range, calendar day count, timezone, and cache path.
  - Live Unicode block progress bar (`[██████████░░░░░░░░]`), Braille animation spinner, calendar day completion percentage, throughput (`tasks/s`), and remaining time countdown (`ETA MM:SS`).
  - Automatically adapts to terminal width (`shutil.get_terminal_size()`) and collapses to clean milestone logs when piped or running in CI (`NO_COLOR` standard compliant).
- **Hierarchical Markdown Export**:
  - **Nested Headings**: Structured heading levels by project depth (`## Date` -> `### Root Project` -> `#### Sub-project`).
  - **Task Bullet Hierarchies**: Renders parent tasks with indented sub-bullets for completed subtasks.
  - **Flat Headings & Paths**: Optional flat representation with slash-separated headings (`#### admin/email`) and flat bullet paths.
- **RFC 4180 Compliant CSV Export**: Clean, standard CSV output escaping commas, quotes, and newlines.
- **Interval-Aware SQLite Cache Engine**:
  - Automatically caches projects, tasks, completed events, and synchronized date ranges in `~/.todoist-trace/cache.db`.
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
│   └── resolvers.py            # Recursive project tree and task hierarchy resolvers
├── tests/                      # Modular test suite (85 tests)
│   ├── conftest.py             # Shared fixtures and path configuration
│   ├── test_cache.py           # SQLite, interval arithmetic, and auto-migration tests
│   ├── test_cli_config.py      # Argument and configuration precedence tests
│   ├── test_exporters.py       # CSV and Markdown formatting tests
│   ├── test_filters.py         # Category and date filtering tests
│   ├── test_package.py         # Submodule and public export tests
│   ├── test_progress.py        # Progress bars, day percentage, and ETA tests
│   └── test_resolvers.py       # Project and task tree resolution tests
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
  "markdown_style": "nested",
  "task_style": "nested"
}
```

Alternatively, you can provide environment variables in a `.env` file:

```env
TODOIST_API_TOKEN=0123456789abcdef0123456789abcdef01234567
TODOIST_TRACE_FORMAT=markdown
TODOIST_TRACE_CATEGORY=all
TODOIST_TRACE_TIMEZONE=Europe/Zurich
```

---

## Usage

You can execute `todoist-trace` using any of the following entrypoints:

```bash
# Via root launcher
python3 todoist_trace.py [options]

# Via Python module
python3 -m todoist_trace [options]
```

### Visual Terminal Progress

When executing a sync, `todoist-trace` displays a real-time visual progress dashboard:

```text
╭─ todoist-trace ────────────────────────────────────────────────────────╮
│ Range    : 2026-01-01 to 2026-10-02 (275 days)                         │
│ Timezone : Europe/Zurich                                              │
│ Category : all                                                         │
│ Format   : MARKDOWN (nested)                                           │
│ Cache    : ~/.todoist-trace/cache.db (SQLite)                          │
╰────────────────────────────────────────────────────────────────────────╯

[1/4] ✔ Projects: 62 active, 18 archived retrieved
[2/4] ⠹ Syncing activities: 2026-01-01 → 2026-10-02 (275 days)
      ⠸ [████████████████░░░░░░░░░░]  61.5% • Day 169/275 • 1,840 tasks • 142 tasks/s • ETA 00:03
[3/4] ✔ Task hierarchies: 2,450 records resolved in 00:01
[4/4] ✔ Export complete: todoist_trace_export.md (2,450 of 2,450 records matched, MARKDOWN (nested))
```

### Common Commands

#### 1. Export the Last 30 Days to Markdown
```bash
python3 todoist_trace.py -f markdown -s 2026-09-02 -e 2026-10-02 -o my_trace.md
```

#### 2. Export Work Projects to CSV
```bash
python3 todoist_trace.py -c work -f csv -o work_activities.csv
```

#### 3. Export with Flat Project Headings
```bash
python3 todoist_trace.py -f markdown --markdown-style flat -o flat_report.md
```

#### 4. Specify Custom Timezone
```bash
python3 todoist_trace.py -z Europe/Zurich -s 2026-10-01 -e 2026-10-02
```

#### 5. Quiet / Scripted Mode
Suppress visual progress reporting for automated pipelines:
```bash
python3 todoist_trace.py -q -f csv -o automated_export.csv
```

#### 6. Force Refresh Cache
Fetch all records fresh from the Todoist API and update the local SQLite database:
```bash
python3 todoist_trace.py --refresh
```

#### 7. Run Without Local Cache
```bash
python3 todoist_trace.py --no-cache -f markdown -o trace_live.md
```

---

## CLI Options

| Flag | Short | Default | Description |
| :--- | :--- | :--- | :--- |
| `--format` | `-f` | `csv` | Output format: `csv` or `markdown` / `md`. |
| `--start-date` | `-s` | `None` | Start date filter in `YYYY-MM-DD` format (inclusive). |
| `--end-date` | `-e` | `None` | End date filter in `YYYY-MM-DD` format (inclusive). |
| `--timezone` | `-z` | `local` | Timezone for daily overview and exports (e.g. `Europe/Zurich`, `UTC`, or `local`). |
| `--category` | `-c` | `all` | Top-level project filter: `work`, `personal`, or `all`. |
| `--output` | `-o` | Auto | Output file path (default: `todoist_trace_export.csv` or `.md`). |
| `--token` | `-t` | Env/Config | Todoist API token (falls back to `TODOIST_API_TOKEN` env var or config file). |
| `--markdown-style` | | `nested` | Markdown project heading style: `nested` (`#### admin / ##### email`) or `flat` (`#### admin/email`). |
| `--task-style` | | `nested` | Markdown task bullet style: `nested` (bullet hierarchy) or `flat` (slash-separated). |
| `--config` | | Auto | Path to custom config file (`JSON` or `.env`). |
| `--cache-file` | | `~/.todoist-trace/cache.db` | Path to local cache file. |
| `--no-cache` | | `False` | Disable persistent local cache. |
| `--refresh` | | `False` | Force re-fetching all data from the API and refresh cache. |
| `--quiet` | `-q` | `False` | Suppress progress updates and non-error messages. |
| `--no-color` | | `False` | Disable ANSI colors in terminal output. |
| `--plain` | | `False` | Use clean plain-text progress updates (no in-place cursor overwrites). |

---

## Export Formats

### 1. Markdown Export Example

#### Nested Style (`--task-style nested`)
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

#### Flat Style (`--task-style flat`)
```markdown
## 2026-09-30

### work
#### sprint-planning
- Sprint Deliverables / Client Portal
- Sprint Deliverables / Services / Database
- Sprint Deliverables / Services / Auth
```

### 2. CSV Export Example

Conforms strictly to RFC 4180 with standard headers:

```csv
top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id
work,sprint-planning,2026-09-30,10:00:00,Sprint Deliverables / Services / Auth,p2,p1,ev_101
personal,finances/taxes,2026-09-30,14:20:00,"Submit quarterly return, Q3",,proj_99,ev_102
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
    start_date TEXT,
    end_date TEXT
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
