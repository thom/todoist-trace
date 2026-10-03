"""
Persistent caching implementations for todoist-trace.
Includes SQLite-backed caching (default) and legacy JSON caching with interval-aware
range synchronization and auto-migration.
"""

import json
import sqlite3
import sys
from datetime import datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .config import DEFAULT_CACHE_PATH, DEFAULT_JSON_CACHE_PATH, resolve_timezone


def normalize_start_date(
    dt_str: Optional[str],
    tz: Optional[Union[str, tzinfo]] = None,
) -> Optional[str]:
    """Normalize a date or timestamp string into an ISO UTC start timestamp."""
    if not dt_str:
        return None
    if "T" in dt_str:
        return dt_str
    if tz is None:
        return f"{dt_str}T00:00:00Z"
    try:
        target_tz = resolve_timezone(tz)
        dt_local_date = datetime.strptime(dt_str, "%Y-%m-%d").date()
        dt_local = datetime.combine(dt_local_date, time(0, 0, 0), tzinfo=target_tz)
        return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return f"{dt_str}T00:00:00Z"


def normalize_end_date(
    dt_str: Optional[str],
    tz: Optional[Union[str, tzinfo]] = None,
) -> Optional[str]:
    """Normalize a date or timestamp string into an ISO UTC end timestamp."""
    if not dt_str:
        return None
    if "T" in dt_str:
        return dt_str
    if tz is None:
        return f"{dt_str}T23:59:59Z"
    try:
        target_tz = resolve_timezone(tz)
        dt_local_date = datetime.strptime(dt_str, "%Y-%m-%d").date()
        dt_local = datetime.combine(dt_local_date, time(23, 59, 59), tzinfo=target_tz)
        return dt_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return f"{dt_str}T23:59:59Z"


def _is_contiguous_or_overlapping(end_str: str, start_str: str, tolerance_seconds: int = 1) -> bool:
    """Return True if start_str <= end_str or contiguous within tolerance_seconds (e.g. across midnight)."""
    if start_str <= end_str:
        return True
    try:
        t_end = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
        t_start = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
        return (t_start - t_end) <= timedelta(seconds=tolerance_seconds)
    except Exception:
        return False


def coalesce_intervals(
    intervals: List[Tuple[str, str, bool]]
) -> List[Tuple[str, str, bool]]:
    """
    Coalesce a list of (start_time, end_time, is_genesis) intervals
    into a minimal sorted list of disjoint intervals.
    """
    if not intervals:
        return []

    # Sort primarily by start_time
    sorted_intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    coalesced: List[Tuple[str, str, bool]] = []

    for s, e, g in sorted_intervals:
        if not coalesced:
            coalesced.append((s, e, g))
            continue

        prev_s, prev_e, prev_g = coalesced[-1]
        # Overlapping or directly contiguous (e.g. 23:59:59 to 00:00:00 across midnight)
        if _is_contiguous_or_overlapping(prev_e, s):
            new_e = max(prev_e, e)
            new_g = prev_g or g
            coalesced[-1] = (prev_s, new_e, new_g)
        else:
            coalesced.append((s, e, g))

    return coalesced


def calculate_missing_intervals(
    existing: List[Tuple[str, str, bool]],
    req_start: Optional[str],
    req_end: Optional[str],
    tz: Optional[Union[str, tzinfo]] = None,
) -> List[Tuple[Optional[str], Optional[str]]]:
    """
    Given existing synced intervals and a requested range [req_start, req_end],
    compute the minimal sub-intervals that need to be fetched from the API.
    Returns [] if the requested range is 100% cached or inverted.
    """
    norm_start = normalize_start_date(req_start, tz=tz)
    norm_end = normalize_end_date(req_end, tz=tz) or datetime.now(timezone.utc).isoformat()

    # Guard against inverted date ranges (start > end)
    if norm_start and norm_end and norm_start > norm_end:
        return []

    is_genesis_req = (req_start is None)

    coalesced = coalesce_intervals(existing)
    if not coalesced:
        return [(norm_start, norm_end)]

    missing: List[Tuple[Optional[str], Optional[str]]] = []

    # 1. Handle genesis / unbounded past request
    if is_genesis_req:
        genesis_interval = next((iv for iv in coalesced if iv[2]), None)
        if genesis_interval:
            current_ptr = genesis_interval[1]
        else:
            earliest_known = min(coalesced[0][0], norm_end)
            missing.append((None, earliest_known))
            current_ptr = coalesced[0][1]
    else:
        current_ptr = norm_start

    # 2. Iterate through coalesced intervals to find intermediate gaps
    for s, e, _ in coalesced:
        if _is_contiguous_or_overlapping(current_ptr, s) or s <= current_ptr:
            current_ptr = max(current_ptr, e)
            continue
        if s > norm_end:
            break
        if s > current_ptr:
            gap_end = min(s, norm_end)
            missing.append((current_ptr, gap_end))
            current_ptr = max(current_ptr, e)

    # 3. Handle remaining forward gap up to norm_end
    if current_ptr < norm_end and not _is_contiguous_or_overlapping(current_ptr, norm_end):
        missing.append((current_ptr, norm_end))

    return missing


class TraceCache:
    """Manages persistent caching of projects, tasks, and activity events in JSON format."""

    def __init__(self, cache_file: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        raw_path = cache_file or str(DEFAULT_JSON_CACHE_PATH)
        self.path = Path(raw_path).expanduser()
        self.projects: List[Dict[str, Any]] = []
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.sections: Dict[str, Dict[str, Any]] = {}
        self.labels: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, Dict[str, Any]] = {}
        self.sync_ranges: List[Dict[str, Any]] = []
        self.last_sync: Optional[str] = None
        if self.enabled:
            self.load()

    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.projects = data.get("projects", [])
                self.tasks = data.get("tasks", {})
                self.sections = data.get("sections", {})
                self.labels = data.get("labels", {})
                self.events = data.get("events", {})
                self.sync_ranges = data.get("sync_ranges", [])
                self.last_sync = data.get("last_sync")
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load cache from {self.path}: {e}\n")

    def save(self) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".tmp")
            data = {
                "last_sync": datetime.now(timezone.utc).isoformat(),
                "projects": self.projects,
                "tasks": self.tasks,
                "sections": self.sections,
                "labels": self.labels,
                "events": self.events,
                "sync_ranges": self.sync_ranges,
            }
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_path.replace(self.path)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to save cache to {self.path}: {e}\n")

    def get_latest_event_date(self) -> Optional[str]:
        """Return the ISO event_date of the newest event in cache."""
        if not self.events:
            return None
        return max(
            (str(ev.get("event_date", "")) for ev in self.events.values() if ev.get("event_date")),
            default=None,
        )

    def merge_events(self, new_events: List[Dict[str, Any]]) -> None:
        for ev in new_events:
            ev_id = str(ev.get("id"))
            if ev_id:
                self.events[ev_id] = ev

    def get_all_events(self) -> List[Dict[str, Any]]:
        return sorted(
            self.events.values(),
            key=lambda x: str(x.get("event_date", "")),
            reverse=True,
        )

    def get_events_count(self) -> int:
        return len(self.events)

    def get_sync_ranges(self) -> List[Tuple[str, str, bool]]:
        return [
            (r["start_time"], r["end_time"], bool(r.get("is_genesis", False)))
            for r in self.sync_ranges
            if "start_time" in r and "end_time" in r
        ]

    def record_sync_range(self, start_time: str, end_time: str, is_genesis: bool = False) -> None:
        current = self.get_sync_ranges()
        current.append((start_time, end_time, is_genesis))
        coalesced = coalesce_intervals(current)
        self.sync_ranges = [
            {"start_time": s, "end_time": e, "is_genesis": g}
            for s, e, g in coalesced
        ]

    def get_missing_ranges(
        self,
        req_start: Optional[str],
        req_end: Optional[str],
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> List[Tuple[Optional[str], Optional[str]]]:
        return calculate_missing_intervals(self.get_sync_ranges(), req_start, req_end, tz=tz)

    def is_range_cached(
        self,
        req_start: Optional[str],
        req_end: Optional[str],
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> bool:
        return len(self.get_missing_ranges(req_start, req_end, tz=tz)) == 0

    def get_events_in_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> List[Dict[str, Any]]:
        norm_start = normalize_start_date(start_date, tz=tz)
        norm_end = normalize_end_date(end_date, tz=tz)
        filtered = []
        for ev in self.events.values():
            ev_date = str(ev.get("event_date", ""))
            if norm_start and ev_date < norm_start:
                continue
            if norm_end and ev_date > norm_end:
                continue
            filtered.append(ev)
        return sorted(filtered, key=lambda x: str(x.get("event_date", "")), reverse=True)


class TaskCacheDict(dict):
    """Dictionary that auto-persists inserted tasks to SQLite."""

    def __init__(self, cache_instance: "SQLiteTraceCache", initial: Optional[Dict[str, Dict[str, Any]]] = None):
        super().__init__(initial or {})
        self._cache = cache_instance

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        super().__setitem__(key, value)
        if self._cache and self._cache.enabled and self._cache.conn:
            try:
                with self._cache.conn:
                    self._cache.conn.execute(
                        "INSERT OR REPLACE INTO tasks (id, parent_id, content, payload) VALUES (?, ?, ?, ?)",
                        (
                            str(key),
                            str(value.get("parent_id")) if value.get("parent_id") else None,
                            value.get("content", ""),
                            json.dumps(value),
                        ),
                    )
            except Exception:
                pass


class SectionCacheDict(dict):
    """Dictionary that auto-persists inserted sections to SQLite."""

    def __init__(self, cache_instance: "SQLiteTraceCache", initial: Optional[Dict[str, Dict[str, Any]]] = None):
        super().__init__(initial or {})
        self._cache = cache_instance

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        super().__setitem__(key, value)
        if self._cache and self._cache.enabled and self._cache.conn:
            try:
                with self._cache.conn:
                    self._cache.conn.execute(
                        "INSERT OR REPLACE INTO sections (id, project_id, name, payload) VALUES (?, ?, ?, ?)",
                        (
                            str(key),
                            str(value.get("project_id")) if value.get("project_id") else None,
                            value.get("name", ""),
                            json.dumps(value),
                        ),
                    )
            except Exception:
                pass


class LabelCacheDict(dict):
    """Dictionary that auto-persists inserted labels to SQLite."""

    def __init__(self, cache_instance: "SQLiteTraceCache", initial: Optional[Dict[str, Dict[str, Any]]] = None):
        super().__init__(initial or {})
        self._cache = cache_instance

    def __setitem__(self, key: str, value: Dict[str, Any]) -> None:
        super().__setitem__(key, value)
        if self._cache and self._cache.enabled and self._cache.conn:
            try:
                with self._cache.conn:
                    self._cache.conn.execute(
                        "INSERT OR REPLACE INTO labels (id, name, color, payload) VALUES (?, ?, ?, ?)",
                        (
                            str(key),
                            value.get("name", ""),
                            value.get("color", ""),
                            json.dumps(value),
                        ),
                    )
            except Exception:
                pass


class SQLiteTraceCache:
    """SQLite-backed persistent cache with range-aware synchronization."""

    def __init__(self, cache_file: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        raw_path = cache_file or str(DEFAULT_CACHE_PATH)
        self.path = Path(raw_path).expanduser()
        self._projects: List[Dict[str, Any]] = []
        self._tasks: TaskCacheDict = TaskCacheDict(self)
        self._sections: SectionCacheDict = SectionCacheDict(self)
        self._labels: LabelCacheDict = LabelCacheDict(self)
        self.conn: Optional[sqlite3.Connection] = None
        if self.enabled:
            self._init_db()
            self._auto_migrate_if_needed()
            self._init_sync_ranges_if_needed()
            self._load_metadata()

    def _init_db(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    name TEXT,
                    is_archived INTEGER,
                    is_deleted INTEGER,
                    payload TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sections (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    name TEXT,
                    payload TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS labels (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    color TEXT,
                    payload TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    content TEXT,
                    payload TEXT
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    event_date TEXT,
                    object_id TEXT,
                    parent_project_id TEXT,
                    extra_data TEXT,
                    payload TEXT
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_events_date ON events(event_date)")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_ranges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT NOT NULL,
                    end_time TEXT NOT NULL,
                    is_genesis INTEGER DEFAULT 0
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def _init_sync_ranges_if_needed(self) -> None:
        """Initialize sync_ranges from existing events for upgraded databases."""
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sync_ranges")
        if cur.fetchone()[0] > 0:
            return
        cur.execute("SELECT MIN(event_date), MAX(event_date) FROM events WHERE event_date IS NOT NULL AND event_date != ''")
        row = cur.fetchone()
        if row and row[0] and row[1]:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO sync_ranges (start_time, end_time, is_genesis) VALUES (?, ?, 0)",
                    (row[0], row[1]),
                )

    def _auto_migrate_if_needed(self) -> None:
        """Auto-migrate legacy JSON cache into SQLite if SQLite events table is empty."""
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        count = cur.fetchone()[0]
        if count > 0:
            return

        import todoist_trace
        dynamic_default = getattr(todoist_trace, "DEFAULT_JSON_CACHE_PATH", DEFAULT_JSON_CACHE_PATH)
        json_candidates = [
            Path(dynamic_default),
            DEFAULT_JSON_CACHE_PATH,
            Path(".todoist_cache.json"),
        ]
        for jpath in json_candidates:
            if jpath.is_file():
                try:
                    with open(jpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    json_projects = data.get("projects", [])
                    json_tasks = data.get("tasks", {})
                    json_sections = data.get("sections", {})
                    json_labels = data.get("labels", {})
                    json_events = list(data.get("events", {}).values())

                    if json_projects:
                        self.projects = json_projects
                    if json_sections:
                        self.sections = json_sections
                    if json_labels:
                        self.labels = json_labels
                    if json_tasks:
                        for tid, tinfo in json_tasks.items():
                            self._tasks[tid] = tinfo
                    if json_events:
                        self.merge_events(json_events)

                    print(f"Auto-migrated {len(json_events)} events, {len(json_tasks)} tasks, {len(json_sections)} sections, {len(json_labels)} labels, and {len(json_projects)} projects from {jpath.name} to SQLite cache.")
                    break
                except Exception as e:
                    sys.stderr.write(f"Warning: Failed to auto-migrate from {jpath}: {e}\n")

    def _load_metadata(self) -> None:
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT payload FROM projects")
        self._projects = [json.loads(row[0]) for row in cur.fetchall()]

        cur.execute("SELECT id, payload FROM sections")
        for row in cur.fetchall():
            self._sections[row[0]] = json.loads(row[1])

        cur.execute("SELECT id, payload FROM labels")
        for row in cur.fetchall():
            self._labels[row[0]] = json.loads(row[1])

        cur.execute("SELECT id, payload FROM tasks")
        for row in cur.fetchall():
            self._tasks[row[0]] = json.loads(row[1])

    @property
    def projects(self) -> List[Dict[str, Any]]:
        return self._projects

    @projects.setter
    def projects(self, projs: List[Dict[str, Any]]) -> None:
        self._projects = projs
        if not self.enabled or not self.conn:
            return
        with self.conn:
            self.conn.execute("DELETE FROM projects")
            rows = [
                (
                    str(p.get("id", "")),
                    str(p["parent_id"]) if p.get("parent_id") else None,
                    p.get("name", ""),
                    1 if p.get("is_archived") else 0,
                    1 if p.get("is_deleted") else 0,
                    json.dumps(p),
                )
                for p in projs
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO projects (id, parent_id, name, is_archived, is_deleted, payload) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    @property
    def sections(self) -> Dict[str, Dict[str, Any]]:
        return self._sections

    @sections.setter
    def sections(self, secs: Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]) -> None:
        if isinstance(secs, list):
            sec_dict = {str(s.get("id")): s for s in secs if s.get("id")}
        else:
            sec_dict = dict(secs)
        self._sections = SectionCacheDict(self, sec_dict)
        if not self.enabled or not self.conn:
            return
        with self.conn:
            rows = [
                (
                    str(s.get("id", "")),
                    str(s.get("project_id")) if s.get("project_id") else None,
                    s.get("name", ""),
                    json.dumps(s),
                )
                for s in sec_dict.values()
                if s.get("id")
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO sections (id, project_id, name, payload) VALUES (?, ?, ?, ?)",
                rows,
            )

    @property
    def labels(self) -> Dict[str, Dict[str, Any]]:
        return self._labels

    @labels.setter
    def labels(self, lbls: Union[List[Dict[str, Any]], Dict[str, Dict[str, Any]]]) -> None:
        if isinstance(lbls, list):
            lbl_dict = {str(l.get("id", l.get("name", ""))): l for l in lbls if l.get("id") or l.get("name")}
        else:
            lbl_dict = dict(lbls)
        self._labels = LabelCacheDict(self, lbl_dict)
        if not self.enabled or not self.conn:
            return
        with self.conn:
            rows = [
                (
                    str(l.get("id", l.get("name", ""))),
                    l.get("name", ""),
                    l.get("color", ""),
                    json.dumps(l),
                )
                for l in lbl_dict.values()
                if l.get("id") or l.get("name")
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO labels (id, name, color, payload) VALUES (?, ?, ?, ?)",
                rows,
            )

    @property
    def tasks(self) -> Dict[str, Dict[str, Any]]:
        return self._tasks

    def get_latest_event_date(self) -> Optional[str]:
        if not self.enabled or not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(event_date) FROM events WHERE event_date IS NOT NULL AND event_date != ''")
        row = cur.fetchone()
        return row[0] if row and row[0] else None

    def get_oldest_event_date(self) -> Optional[str]:
        if not self.enabled or not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT MIN(event_date) FROM events WHERE event_date IS NOT NULL AND event_date != ''")
        row = cur.fetchone()
        return row[0] if row and row[0] else None

    def get_date_bounds(self) -> Tuple[Optional[str], Optional[str]]:
        return (self.get_oldest_event_date(), self.get_latest_event_date())

    def get_sync_ranges(self) -> List[Tuple[str, str, bool]]:
        """Return all coalesced synchronized time ranges."""
        if not self.enabled or not self.conn:
            return []
        cur = self.conn.cursor()
        cur.execute("SELECT start_time, end_time, is_genesis FROM sync_ranges ORDER BY start_time ASC")
        rows = [(r[0], r[1], bool(r[2])) for r in cur.fetchall()]
        return coalesce_intervals(rows)

    def record_sync_range(self, start_time: str, end_time: str, is_genesis: bool = False) -> None:
        """Record a newly synchronized time range and coalesce overlapping ranges."""
        if not self.enabled or not self.conn:
            return
        current = self.get_sync_ranges()
        current.append((start_time, end_time, is_genesis))
        coalesced = coalesce_intervals(current)

        with self.conn:
            self.conn.execute("DELETE FROM sync_ranges")
            rows = [(s, e, 1 if g else 0) for s, e, g in coalesced]
            self.conn.executemany(
                "INSERT INTO sync_ranges (start_time, end_time, is_genesis) VALUES (?, ?, ?)",
                rows,
            )

    def get_missing_ranges(
        self,
        req_start: Optional[str],
        req_end: Optional[str],
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> List[Tuple[Optional[str], Optional[str]]]:
        """Compute missing range gaps that must be fetched from the API."""
        return calculate_missing_intervals(self.get_sync_ranges(), req_start, req_end, tz=tz)

    def is_range_cached(
        self,
        req_start: Optional[str],
        req_end: Optional[str],
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> bool:
        """Check if requested range is completely covered by cache."""
        return len(self.get_missing_ranges(req_start, req_end, tz=tz)) == 0

    def get_events_in_range(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve events matching date range directly from SQLite using idx_events_date."""
        if not self.enabled or not self.conn:
            return []
        norm_start = normalize_start_date(start_date, tz=tz)
        norm_end = normalize_end_date(end_date, tz=tz)
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT payload FROM events
            WHERE (? IS NULL OR event_date >= ?)
              AND (? IS NULL OR event_date <= ?)
            ORDER BY event_date DESC
            """,
            (norm_start, norm_start, norm_end, norm_end),
        )
        events = []
        for row in cur.fetchall():
            try:
                events.append(json.loads(row[0]))
            except Exception:
                pass
        return events

    def merge_events(self, new_events: List[Dict[str, Any]]) -> None:
        if not self.enabled or not self.conn or not new_events:
            return
        rows = [
            (
                str(ev.get("id", "")),
                str(ev.get("event_date", "")),
                str(ev.get("object_id", "")),
                str(ev.get("parent_project_id", "")),
                json.dumps(ev.get("extra_data", {})),
                json.dumps(ev),
            )
            for ev in new_events
            if ev.get("id")
        ]
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO events (id, event_date, object_id, parent_project_id, extra_data, payload) VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )

    def get_all_events(self) -> List[Dict[str, Any]]:
        if not self.enabled or not self.conn:
            return []
        cur = self.conn.cursor()
        cur.execute("SELECT payload FROM events ORDER BY event_date DESC")
        events = []
        for row in cur.fetchall():
            try:
                events.append(json.loads(row[0]))
            except Exception:
                pass
        return events

    def get_events_count(self) -> int:
        if not self.enabled or not self.conn:
            return 0
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        return cur.fetchone()[0]

    def save(self) -> None:
        if not self.enabled or not self.conn:
            return
        with self.conn:
            rows = [
                (
                    str(tid),
                    str(tinfo.get("parent_id")) if tinfo.get("parent_id") else None,
                    tinfo.get("content", ""),
                    json.dumps(tinfo),
                )
                for tid, tinfo in self._tasks.items()
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO tasks (id, parent_id, content, payload) VALUES (?, ?, ?, ?)",
                rows,
            )
            sec_rows = [
                (
                    str(sid),
                    str(sinfo.get("project_id")) if sinfo.get("project_id") else None,
                    sinfo.get("name", ""),
                    json.dumps(sinfo),
                )
                for sid, sinfo in self._sections.items()
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO sections (id, project_id, name, payload) VALUES (?, ?, ?, ?)",
                sec_rows,
            )
            lbl_rows = [
                (
                    str(lid),
                    linfo.get("name", ""),
                    linfo.get("color", ""),
                    json.dumps(linfo),
                )
                for lid, linfo in self._labels.items()
            ]
            self.conn.executemany(
                "INSERT OR REPLACE INTO labels (id, name, color, payload) VALUES (?, ?, ?, ?)",
                lbl_rows,
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('last_sync', ?)",
                (datetime.now(timezone.utc).isoformat(),),
            )

    def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None


def create_cache(cache_file: Optional[str] = None, enabled: bool = True):
    """
    Factory creating either SQLiteTraceCache (default, .db/.sqlite)
    or TraceCache (.json) based on file extension.
    """
    raw_path = cache_file or str(DEFAULT_CACHE_PATH)
    path = Path(raw_path).expanduser()
    if path.suffix == ".json":
        return TraceCache(cache_file=str(path), enabled=enabled)
    else:
        return SQLiteTraceCache(cache_file=str(path), enabled=enabled)
