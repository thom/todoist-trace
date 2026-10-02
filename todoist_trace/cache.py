"""
Persistent caching implementations for todoist-trace.
Includes SQLite-backed caching (default) and legacy JSON caching with auto-migration.
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import DEFAULT_CACHE_PATH, DEFAULT_JSON_CACHE_PATH


class TraceCache:
    """Manages persistent caching of projects, tasks, and activity events in JSON format."""

    def __init__(self, cache_file: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        raw_path = cache_file or str(DEFAULT_JSON_CACHE_PATH)
        self.path = Path(raw_path).expanduser()
        self.projects: List[Dict[str, Any]] = []
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.events: Dict[str, Dict[str, Any]] = {}
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
                self.events = data.get("events", {})
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
                "events": self.events,
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


class SQLiteTraceCache:
    """SQLite-backed persistent cache for projects, tasks, and activity events."""

    def __init__(self, cache_file: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        raw_path = cache_file or str(DEFAULT_CACHE_PATH)
        self.path = Path(raw_path).expanduser()
        self._projects: List[Dict[str, Any]] = []
        self._tasks: TaskCacheDict = TaskCacheDict(self)
        self.conn: Optional[sqlite3.Connection] = None
        if self.enabled:
            self._init_db()
            self._auto_migrate_if_needed()
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
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

    def _auto_migrate_if_needed(self) -> None:
        """Auto-migrate legacy JSON cache into SQLite if SQLite events table is empty."""
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM events")
        count = cur.fetchone()[0]
        if count > 0:
            return  # Already populated

        # Check for candidate JSON files: ~/.todoist-trace/cache.json, then .todoist_cache.json
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
                    json_events = list(data.get("events", {}).values())

                    if json_projects:
                        self.projects = json_projects
                    if json_tasks:
                        for tid, tinfo in json_tasks.items():
                            self._tasks[tid] = tinfo
                    if json_events:
                        self.merge_events(json_events)

                    print(f"Auto-migrated {len(json_events)} events, {len(json_tasks)} tasks, and {len(json_projects)} projects from {jpath.name} to SQLite cache.")
                    break
                except Exception as e:
                    sys.stderr.write(f"Warning: Failed to auto-migrate from {jpath}: {e}\n")

    def _load_metadata(self) -> None:
        if not self.conn:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT payload FROM projects")
        self._projects = [json.loads(row[0]) for row in cur.fetchall()]

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
    def tasks(self) -> Dict[str, Dict[str, Any]]:
        return self._tasks

    def get_latest_event_date(self) -> Optional[str]:
        if not self.enabled or not self.conn:
            return None
        cur = self.conn.cursor()
        cur.execute("SELECT MAX(event_date) FROM events WHERE event_date IS NOT NULL AND event_date != ''")
        row = cur.fetchone()
        return row[0] if row and row[0] else None

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
        return [json.loads(row[0]) for row in cur.fetchall()]

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
