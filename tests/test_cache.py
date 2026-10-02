"""
Unit tests for persistent caching (TraceCache, SQLiteTraceCache, and factory).
"""

import json
from pathlib import Path
import pytest

from todoist_trace.cache import (
    SQLiteTraceCache,
    TraceCache,
    create_cache,
)


class TestTraceCache:
    """Test suite for JSON-backed TraceCache functionality."""

    def test_cache_save_and_load(self, tmp_path):
        cache_file = tmp_path / "test_cache.json"
        cache = TraceCache(cache_file=str(cache_file), enabled=True)

        cache.projects = [{"id": "p1", "name": "Work"}]
        cache.tasks = {"t1": {"content": "Task 1", "parent_id": None}}
        cache.merge_events([
            {"id": "e1", "event_date": "2026-10-01T10:00:00Z", "extra_data": {"content": "E1"}},
            {"id": "e2", "event_date": "2026-10-02T12:00:00Z", "extra_data": {"content": "E2"}},
        ])
        cache.save()

        # Reload in a new instance
        reloaded = TraceCache(cache_file=str(cache_file), enabled=True)
        assert len(reloaded.projects) == 1
        assert reloaded.projects[0]["name"] == "Work"
        assert reloaded.tasks["t1"]["content"] == "Task 1"
        assert len(reloaded.events) == 2
        assert reloaded.get_latest_event_date() == "2026-10-02T12:00:00Z"
        assert [e["id"] for e in reloaded.get_all_events()] == ["e2", "e1"]

    def test_disabled_cache(self, tmp_path):
        cache_file = tmp_path / "disabled_cache.json"
        cache = TraceCache(cache_file=str(cache_file), enabled=False)
        cache.projects = [{"id": "p1"}]
        cache.save()
        assert not cache_file.exists()


class TestSQLiteTraceCache:
    """Test suite for SQLiteTraceCache functionality."""

    def test_sqlite_save_and_load(self, tmp_path):
        db_file = tmp_path / "test_cache.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        cache.projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        cache.tasks["t1"] = {"content": "Task 1", "parent_id": None}
        cache.merge_events([
            {"id": "e1", "event_date": "2026-10-01T10:00:00Z", "extra_data": {"content": "E1"}},
            {"id": "e2", "event_date": "2026-10-02T12:00:00Z", "extra_data": {"content": "E2"}},
        ])
        cache.save()

        # Reload in a new instance
        reloaded = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert len(reloaded.projects) == 1
        assert reloaded.projects[0]["name"] == "Work"
        assert reloaded.tasks["t1"]["content"] == "Task 1"
        assert reloaded.get_events_count() == 2
        assert reloaded.get_latest_event_date() == "2026-10-02T12:00:00Z"
        all_events = reloaded.get_all_events()
        assert [e["id"] for e in all_events] == ["e2", "e1"]
        reloaded.close()
        cache.close()

    def test_sqlite_auto_migration(self, tmp_path, monkeypatch):
        # Create a mock legacy JSON file
        legacy_json = tmp_path / "legacy.json"
        legacy_data = {
            "projects": [{"id": "p_legacy", "name": "Legacy Project"}],
            "tasks": {"t_legacy": {"content": "Legacy Task", "parent_id": None}},
            "events": {
                "e_legacy": {"id": "e_legacy", "event_date": "2026-09-01T10:00:00Z", "extra_data": {"content": "Legacy Task"}},
            },
        }
        legacy_json.write_text(json.dumps(legacy_data), encoding="utf-8")

        import todoist_trace
        monkeypatch.setattr(todoist_trace, "DEFAULT_JSON_CACHE_PATH", legacy_json)

        db_file = tmp_path / "migrated.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        assert len(cache.projects) == 1
        assert cache.projects[0]["id"] == "p_legacy"
        assert "t_legacy" in cache.tasks
        assert cache.get_events_count() == 1
        assert cache.get_latest_event_date() == "2026-09-01T10:00:00Z"
        cache.close()

    def test_create_cache_factory(self, tmp_path):
        json_file = str(tmp_path / "cache.json")
        db_file = str(tmp_path / "cache.db")
        sqlite_file = str(tmp_path / "cache.sqlite")

        c_json = create_cache(json_file)
        assert isinstance(c_json, TraceCache)

        c_db = create_cache(db_file)
        assert isinstance(c_db, SQLiteTraceCache)
        c_db.close()

        c_sqlite = create_cache(sqlite_file)
        assert isinstance(c_sqlite, SQLiteTraceCache)
        c_sqlite.close()
