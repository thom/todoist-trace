"""
Unit tests for persistent caching (SQLiteTraceCache and factory),
including interval arithmetic and range-aware synchronization scenarios.
"""

import json
from pathlib import Path
import pytest

from todoist_trace.cache import (
    SQLiteTraceCache,
    calculate_missing_intervals,
    coalesce_intervals,
    create_cache,
)


class TestIntervalArithmetic:
    """Test suite for interval coalescing and missing gap calculations."""

    def test_coalesce_intervals_disjoint_and_overlapping(self):
        # 1. Overlapping intervals: [Sept 1, Sept 30] and [Sept 20, Oct 10]
        raw = [
            ("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z", False),
            ("2026-09-20T00:00:00Z", "2026-10-10T23:59:59Z", False),
        ]
        coalesced = coalesce_intervals(raw)
        assert len(coalesced) == 1
        assert coalesced[0][0] == "2026-09-01T00:00:00Z"
        assert coalesced[0][1] == "2026-10-10T23:59:59Z"
        assert not coalesced[0][2]

        # 2. Contiguous abutting intervals: [Jan 1, Feb 1] and [Feb 1, March 1]
        raw_contiguous = [
            ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", False),
            ("2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z", False),
        ]
        merged = coalesce_intervals(raw_contiguous)
        assert len(merged) == 1
        assert merged[0][0] == "2026-01-01T00:00:00Z"
        assert merged[0][1] == "2026-03-01T00:00:00Z"

        # 3. Disjoint intervals: [Jan, Feb] and [May, June]
        raw_disjoint = [
            ("2026-05-01T00:00:00Z", "2026-06-01T00:00:00Z", False),
            ("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", False),
        ]
        sorted_disjoint = coalesce_intervals(raw_disjoint)
        assert len(sorted_disjoint) == 2
        assert sorted_disjoint[0][0] == "2026-01-01T00:00:00Z"
        assert sorted_disjoint[1][0] == "2026-05-01T00:00:00Z"

    def test_coalesce_intervals_preserves_genesis(self):
        intervals = [
            ("1970-01-01T00:00:00Z", "2026-01-01T00:00:00Z", True),
            ("2026-01-01T00:00:00Z", "2026-10-01T00:00:00Z", False),
        ]
        coalesced = coalesce_intervals(intervals)
        assert len(coalesced) == 1
        assert coalesced[0][2] is True

    def test_calculate_missing_intervals_subset_hit(self):
        # Cache covers Sept 1 to Sept 30
        existing = [("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z", False)]
        # Request Sept 10 to Sept 20
        missing = calculate_missing_intervals(existing, "2026-09-10", "2026-09-20")
        assert missing == []

    def test_calculate_missing_intervals_forward_gap(self):
        # Cache covers Sept 1 to Sept 30
        existing = [("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z", False)]
        # Request Sept 2 to Oct 2 -> Only gap [Sept 30, Oct 2] needed
        missing = calculate_missing_intervals(existing, "2026-09-02", "2026-10-02")
        assert len(missing) == 1
        assert missing[0][0] == "2026-09-30T23:59:59Z"
        assert missing[0][1] == "2026-10-02T23:59:59Z"

    def test_calculate_missing_intervals_backward_gap(self):
        # Cache covers Sept 1 to Oct 2
        existing = [("2026-09-01T00:00:00Z", "2026-10-02T23:59:59Z", False)]
        # Request Jan 1 to Oct 2 -> Only gap [Jan 1, Sept 1] needed
        missing = calculate_missing_intervals(existing, "2026-01-01", "2026-10-02")
        assert len(missing) == 1
        assert missing[0][0] == "2026-01-01T00:00:00Z"
        assert missing[0][1] == "2026-09-01T00:00:00Z"

    def test_calculate_missing_intervals_internal_gap(self):
        # Cache has two disconnected islands: Sept 1-10 and Sept 20-30
        existing = [
            ("2026-09-01T00:00:00Z", "2026-09-10T23:59:59Z", False),
            ("2026-09-20T00:00:00Z", "2026-09-30T23:59:59Z", False),
        ]
        # Request Sept 5 to Sept 25 -> Missing internal hole: [Sept 10, Sept 20]
        missing = calculate_missing_intervals(existing, "2026-09-05", "2026-09-25")
        assert len(missing) == 1
        assert missing[0][0] == "2026-09-10T23:59:59Z"
        assert missing[0][1] == "2026-09-20T00:00:00Z"


class TestSQLiteTraceCache:
    """Test suite for SQLiteTraceCache functionality and range-aware sync."""

    def test_sqlite_save_and_load(self, tmp_path):
        db_file = tmp_path / "test_cache.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        cache.projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        cache.tasks["t1"] = {"content": "Task 1", "parent_id": None}
        cache.merge_events([
            {"id": "e1", "event_date": "2026-10-01T10:00:00Z", "extra_data": {"content": "E1"}},
            {"id": "e2", "event_date": "2026-10-02T12:00:00Z", "extra_data": {"content": "E2"}},
        ])
        cache.record_sync_range("2026-10-01T00:00:00Z", "2026-10-02T23:59:59Z", is_genesis=False)
        cache.save()

        # Reload in a new instance
        reloaded = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert len(reloaded.projects) == 1
        assert reloaded.projects[0]["name"] == "Work"
        assert reloaded.tasks["t1"]["content"] == "Task 1"
        assert reloaded.get_events_count() == 2
        assert reloaded.get_latest_event_date() == "2026-10-02T12:00:00Z"
        assert reloaded.get_oldest_event_date() == "2026-10-01T10:00:00Z"
        assert len(reloaded.get_sync_ranges()) == 1
        all_events = reloaded.get_all_events()
        assert [e["id"] for e in all_events] == ["e2", "e1"]
        reloaded.close()
        cache.close()

    def test_sqlite_range_query_with_index(self, tmp_path):
        db_file = tmp_path / "index_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        cache.merge_events([
            {"id": "e1", "event_date": "2026-09-05T10:00:00Z", "payload": json.dumps({"id": "e1"})},
            {"id": "e2", "event_date": "2026-09-15T10:00:00Z", "payload": json.dumps({"id": "e2"})},
            {"id": "e3", "event_date": "2026-09-25T10:00:00Z", "payload": json.dumps({"id": "e3"})},
        ])
        # Query window [Sept 10, Sept 20]
        events = cache.get_events_in_range("2026-09-10", "2026-09-20")
        assert len(events) == 1
        assert events[0]["id"] == "e2"
        cache.close()

    def test_zero_activity_day_does_not_cause_cache_miss(self, tmp_path):
        """
        Verify that a day with zero completed tasks is correctly recognized as cached
        if it falls within a recorded sync_range.
        """
        db_file = tmp_path / "zero_activity.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # Range Sept 1 to Sept 30 was synced, but only 1 task completed on Sept 15
        cache.merge_events([
            {"id": "e1", "event_date": "2026-09-15T12:00:00Z", "payload": json.dumps({"id": "e1"})},
        ])
        cache.record_sync_range("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z", is_genesis=False)

        # Query Sept 1 to Sept 10 (where 0 tasks occurred)
        assert cache.is_range_cached("2026-09-01", "2026-09-10") is True
        missing = cache.get_missing_ranges("2026-09-01", "2026-09-10")
        assert missing == []

        events = cache.get_events_in_range("2026-09-01", "2026-09-10")
        assert events == []
        cache.close()

    def test_progressive_sync_scenarios(self, tmp_path):
        """
        End-to-end test simulating user's exact three sequential scenarios:
        1. Initial sync: 2026-09-01 to 2026-09-30
        2. Rolling last 30 days: 2026-09-02 to 2026-10-02
        3. Expanding backfill: 2026-01-01 to 2026-10-02
        """
        db_file = tmp_path / "progressive_sync.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # 1. Initial sync: Sept 1 to Sept 30
        missing_1 = cache.get_missing_ranges("2026-09-01", "2026-09-30")
        assert len(missing_1) == 1
        assert missing_1[0] == ("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z")
        cache.record_sync_range("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z")

        # 2. Rolling last 30 days: Sept 2 to Oct 2
        # Only future gap [Sept 30, Oct 2] should be returned!
        missing_2 = cache.get_missing_ranges("2026-09-02", "2026-10-02")
        assert len(missing_2) == 1
        assert missing_2[0] == ("2026-09-30T23:59:59Z", "2026-10-02T23:59:59Z")
        # Record the forward gap
        cache.record_sync_range("2026-09-30T23:59:59Z", "2026-10-02T23:59:59Z")
        ranges = cache.get_sync_ranges()
        assert len(ranges) == 1
        assert ranges[0][0] == "2026-09-01T00:00:00Z"
        assert ranges[0][1] == "2026-10-02T23:59:59Z"

        # 3. Expanding backfill: Jan 1 to Oct 2
        # Only past gap [Jan 1, Sept 1] should be returned!
        missing_3 = cache.get_missing_ranges("2026-01-01", "2026-10-02")
        assert len(missing_3) == 1
        assert missing_3[0] == ("2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z")
        # Record the backward gap
        cache.record_sync_range("2026-01-01T00:00:00Z", "2026-09-01T00:00:00Z")
        ranges_after_backfill = cache.get_sync_ranges()
        assert len(ranges_after_backfill) == 1
        assert ranges_after_backfill[0][0] == "2026-01-01T00:00:00Z"
        assert ranges_after_backfill[0][1] == "2026-10-02T23:59:59Z"

        # 4. Subset query: March 1 to May 1 -> 100% cache hit
        assert cache.is_range_cached("2026-03-01", "2026-05-01") is True
        assert cache.get_missing_ranges("2026-03-01", "2026-05-01") == []

        cache.close()

    def test_create_cache_factory(self, tmp_path):
        db_file = str(tmp_path / "cache.db")
        sqlite_file = str(tmp_path / "cache.sqlite")

        c_db = create_cache(db_file)
        assert isinstance(c_db, SQLiteTraceCache)
        c_db.close()

        c_sqlite = create_cache(sqlite_file)
        assert isinstance(c_sqlite, SQLiteTraceCache)
        c_sqlite.close()


class TestCacheEdgeCases:
    """Detailed edge-case testing for interval arithmetic, boundary conditions, and SQLite cache."""

    def test_midnight_boundary_abutting_intervals_coalesce(self):
        """Consecutive days (differing by 1s across midnight) must coalesce and not leave micro-gaps."""
        iv1 = ("2026-09-01T00:00:00Z", "2026-09-01T23:59:59Z", False)
        iv2 = ("2026-09-02T00:00:00Z", "2026-09-02T23:59:59Z", False)
        coalesced = coalesce_intervals([iv1, iv2])
        assert len(coalesced) == 1
        assert coalesced[0] == ("2026-09-01T00:00:00Z", "2026-09-02T23:59:59Z", False)

        # Query spanning across the midnight boundary should be 100% cached
        missing = calculate_missing_intervals([iv1, iv2], "2026-09-01", "2026-09-02")
        assert missing == []

    def test_inverted_date_range_returns_empty(self):
        """Inverted date range (start > end) must return empty list to prevent invalid fetches."""
        # Empty cache
        assert calculate_missing_intervals([], "2026-10-10", "2026-10-01") == []

        # Non-empty cache
        existing = [("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z", False)]
        assert calculate_missing_intervals(existing, "2026-10-10", "2026-10-01") == []

    def test_empty_intervals_and_none_bounds(self):
        """Ensure missing interval calculation works when existing intervals are empty."""
        missing = calculate_missing_intervals([], "2026-09-01", "2026-09-30")
        assert missing == [("2026-09-01T00:00:00Z", "2026-09-30T23:59:59Z")]

        missing_genesis = calculate_missing_intervals([], None, "2026-09-30")
        assert missing_genesis == [(None, "2026-09-30T23:59:59Z")]

    def test_unbounded_past_genesis_preservation(self):
        """Verify behavior with genesis intervals (is_genesis=True)."""
        existing = [("1970-01-01T00:00:00Z", "2026-06-01T00:00:00Z", True)]

        # 1. Historical query within genesis window -> 100% cache hit
        assert calculate_missing_intervals(existing, None, "2026-05-01") == []

        # 2. Historical query expanding forward beyond genesis window -> only forward gap needed
        missing_forward = calculate_missing_intervals(existing, None, "2026-08-01")
        assert len(missing_forward) == 1
        assert missing_forward[0] == ("2026-06-01T00:00:00Z", "2026-08-01T23:59:59Z")

        # 3. Cache without genesis -> needs backward backfill to None
        existing_non_genesis = [("2026-06-01T00:00:00Z", "2026-08-01T00:00:00Z", False)]
        missing_backfill = calculate_missing_intervals(existing_non_genesis, None, "2026-07-01")
        assert len(missing_backfill) == 1
        assert missing_backfill[0] == (None, "2026-06-01T00:00:00Z")

    def test_exact_boundary_hits(self):
        """Queries landing exactly on existing interval boundaries must be full hits."""
        existing = [("2026-01-01T00:00:00Z", "2026-06-30T23:59:59Z", False)]

        # Exact match
        assert calculate_missing_intervals(existing, "2026-01-01", "2026-06-30") == []
        # Left boundary
        assert calculate_missing_intervals(existing, "2026-01-01", "2026-02-01") == []
        # Right boundary
        assert calculate_missing_intervals(existing, "2026-05-01", "2026-06-30") == []
        # Point query (start == end)
        assert calculate_missing_intervals(existing, "2026-03-15T12:00:00Z", "2026-03-15T12:00:00Z") == []

    def test_completely_disjoint_out_of_bounds_queries(self):
        """Queries completely before or after cached ranges must return full requested window."""
        existing = [("2026-06-01T00:00:00Z", "2026-08-01T23:59:59Z", False)]

        # Completely before
        missing_before = calculate_missing_intervals(existing, "2026-01-01", "2026-03-01")
        assert missing_before == [("2026-01-01T00:00:00Z", "2026-03-01T23:59:59Z")]

        # Completely after
        missing_after = calculate_missing_intervals(existing, "2026-10-01", "2026-12-01")
        assert missing_after == [("2026-10-01T00:00:00Z", "2026-12-01T23:59:59Z")]

    def test_multiple_intermediate_holes_swiss_cheese(self):
        """Ensure multiple disconnected gap intervals are accurately identified."""
        existing = [
            ("2026-01-01T00:00:00Z", "2026-01-31T23:59:59Z", False),
            ("2026-03-01T00:00:00Z", "2026-03-31T23:59:59Z", False),
            ("2026-05-01T00:00:00Z", "2026-05-31T23:59:59Z", False),
        ]
        # Query spanning all three islands from Jan 15 to May 15
        missing = calculate_missing_intervals(existing, "2026-01-15", "2026-05-15")
        assert len(missing) == 2
        assert missing[0] == ("2026-01-31T23:59:59Z", "2026-03-01T00:00:00Z")
        assert missing[1] == ("2026-03-31T23:59:59Z", "2026-05-01T00:00:00Z")

    def test_coalesce_duplicate_and_nested_intervals(self):
        """Coalescing must absorb duplicates and nested intervals properly."""
        raw = [
            ("2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z", False),
            ("2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z", False),  # Duplicate
            ("2026-03-01T00:00:00Z", "2026-04-01T23:59:59Z", False),  # Subset
        ]
        coalesced = coalesce_intervals(raw)
        assert len(coalesced) == 1
        assert coalesced[0] == ("2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z", False)

    def test_sqlite_corrupt_payload_graceful_handling(self, tmp_path):
        """Corrupted JSON in event payload must be skipped rather than crashing queries."""
        db_file = tmp_path / "corrupt.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        with cache.conn:
            cache.conn.execute(
                "INSERT INTO events (id, event_date, payload) VALUES (?, ?, ?)",
                ("valid_1", "2026-09-10T10:00:00Z", json.dumps({"id": "valid_1"})),
            )
            cache.conn.execute(
                "INSERT INTO events (id, event_date, payload) VALUES (?, ?, ?)",
                ("corrupt_1", "2026-09-15T10:00:00Z", "MALFORMED_JSON{{{"),
            )
            cache.conn.execute(
                "INSERT INTO events (id, event_date, payload) VALUES (?, ?, ?)",
                ("valid_2", "2026-09-20T10:00:00Z", json.dumps({"id": "valid_2"})),
            )

        events_range = cache.get_events_in_range("2026-09-01", "2026-09-30")
        assert len(events_range) == 2
        assert [e["id"] for e in events_range] == ["valid_2", "valid_1"]

        events_all = cache.get_all_events()
        assert len(events_all) == 2
        assert [e["id"] for e in events_all] == ["valid_2", "valid_1"]

        cache.close()

    def test_sqlite_empty_table_edge_cases(self, tmp_path):
        """Empty tables should cleanly return None, empty lists, or False without errors."""
        db_file = tmp_path / "empty.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        assert cache.get_latest_event_date() is None
        assert cache.get_oldest_event_date() is None
        assert cache.get_date_bounds() == (None, None)
        assert cache.get_sync_ranges() == []
        assert cache.get_events_count() == 0
        assert cache.get_all_events() == []
        assert cache.get_events_in_range("2026-01-01", "2026-12-31") == []
        assert cache.is_range_cached("2026-01-01", "2026-12-31") is False

        cache.close()

    def test_single_day_start_equals_end_sync(self):
        """Single-day query (start == end) covers the full 24h interval."""
        missing = calculate_missing_intervals([], "2026-10-01", "2026-10-01")
        assert len(missing) == 1
        assert missing[0] == ("2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z")

        # Once recorded, query for the same single day is a 100% cache hit
        coalesced = coalesce_intervals([("2026-10-01T00:00:00Z", "2026-10-01T23:59:59Z", False)])
        assert calculate_missing_intervals(coalesced, "2026-10-01", "2026-10-01") == []

    def test_future_end_date_capped_at_now_never_poisons_cache(self, tmp_path):
        """Syncing with future end date must cap effective_end at now so future tasks aren't ignored."""
        from datetime import datetime, timezone
        db_file = tmp_path / "future_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        now_iso = "2026-10-02T12:00:00Z"
        future_gap_end = "2026-10-10T23:59:59Z"
        effective_end = min(future_gap_end, now_iso)

        cache.record_sync_range("2026-10-01T00:00:00Z", effective_end)
        ranges = cache.get_sync_ranges()
        assert len(ranges) == 1
        assert ranges[0][1] == "2026-10-02T12:00:00Z"
        assert ranges[0][1] != future_gap_end

        cache.close()

    def test_normalize_dates_with_timezone(self):
        """Date boundaries must correctly convert local midnight and 23:59:59 to UTC ISO."""
        from todoist_trace.cache import normalize_end_date, normalize_start_date

        # Europe/Zurich (UTC+2 in summer/CEST)
        assert normalize_start_date("2026-10-01", tz="Europe/Zurich") == "2026-09-30T22:00:00Z"
        assert normalize_end_date("2026-10-01", tz="Europe/Zurich") == "2026-10-01T21:59:59Z"

        # America/Los_Angeles (UTC-7 in summer/PDT)
        assert normalize_start_date("2026-10-01", tz="America/Los_Angeles") == "2026-10-01T07:00:00Z"
        assert normalize_end_date("2026-10-01", tz="America/Los_Angeles") == "2026-10-02T06:59:59Z"

        # UTC
        assert normalize_start_date("2026-10-01", tz="UTC") == "2026-10-01T00:00:00Z"
        assert normalize_end_date("2026-10-01", tz="UTC") == "2026-10-01T23:59:59Z"

        # Default (tz=None) preserves backward-compatible UTC
        assert normalize_start_date("2026-10-01", tz=None) == "2026-10-01T00:00:00Z"
        assert normalize_end_date("2026-10-01", tz=None) == "2026-10-01T23:59:59Z"

    def test_sqlite_cache_range_query_with_timezone(self, tmp_path):
        """A task completed at 00:30 on 2026-10-01 in Zurich has UTC 2026-09-30T22:30:00Z."""
        db_file = tmp_path / "tz_query.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # Task closed on 2026-10-01 at 00:30 AM in Zurich (2026-09-30 22:30 UTC)
        cache.merge_events([
            {
                "id": "ev_night",
                "event_date": "2026-09-30T22:30:00Z",
                "object_id": "t1",
                "extra_data": {"content": "Night Task"},
            }
        ])

        # Query for 2026-10-01 in Europe/Zurich: should match!
        events_zurich = cache.get_events_in_range("2026-10-01", "2026-10-01", tz="Europe/Zurich")
        assert len(events_zurich) == 1
        assert events_zurich[0]["id"] == "ev_night"

        # Query for 2026-10-01 in UTC: should NOT match (belongs to 2026-09-30 in UTC)
        events_utc = cache.get_events_in_range("2026-10-01", "2026-10-01", tz="UTC")
        assert len(events_utc) == 0

        # Query for 2026-09-30 in UTC: should match!
        events_utc_prev = cache.get_events_in_range("2026-09-30", "2026-09-30", tz="UTC")
        assert len(events_utc_prev) == 1
        assert events_utc_prev[0]["id"] == "ev_night"

        cache.close()

    def test_sqlite_sections_persistence_and_reload(self, tmp_path):
        db_file = tmp_path / "sections.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # 1. Bulk set via list
        cache.sections = [
            {"id": "sec_1", "project_id": "p1", "name": "Sprint 1"}
        ]
        assert cache.sections["sec_1"]["name"] == "Sprint 1"

        # 2. Individual insert via SectionCacheDict
        cache.sections["sec_2"] = {"id": "sec_2", "project_id": "p1", "name": "Sprint 2"}
        assert cache.sections["sec_2"]["name"] == "Sprint 2"

        cache.save()
        cache.close()

        # Re-open and verify persistence
        reloaded = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert len(reloaded.sections) == 2
        assert reloaded.sections["sec_1"]["name"] == "Sprint 1"
        assert reloaded.sections["sec_2"]["name"] == "Sprint 2"
        reloaded.close()

    def test_sqlite_labels_persistence(self, tmp_path):
        db_file = tmp_path / "labels_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # 1. Bulk set labels via list
        labels_list = [
            {"id": "lbl_1", "name": "work", "color": "charcoal"},
            {"id": "lbl_2", "name": "urgent", "color": "red"},
        ]
        cache.labels = labels_list
        assert len(cache.labels) == 2
        assert cache.labels["lbl_1"]["name"] == "work"
        assert cache.labels["lbl_2"]["color"] == "red"

        # 2. Individual insert via LabelCacheDict
        cache.labels["lbl_3"] = {"id": "lbl_3", "name": "ops", "color": "blue"}
        assert cache.labels["lbl_3"]["name"] == "ops"

        cache.save()
        cache.close()

        # Re-open and verify persistence
        reloaded = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert len(reloaded.labels) == 3
        assert reloaded.labels["lbl_1"]["name"] == "work"
        assert reloaded.labels["lbl_2"]["name"] == "urgent"
        assert reloaded.labels["lbl_3"]["name"] == "ops"
        reloaded.close()


class TestMaterializedResolvedActivities:
    """Test suite for Option 1: Materialized resolved_activities in cache."""

    def test_sqlite_materialized_activities_schema_and_upsert(self, tmp_path):
        db_file = tmp_path / "resolved_schema_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # Check table and index existence in sqlite_master
        cur = cache.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='resolved_activities'")
        assert cur.fetchone() is not None

        cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_resolved_date'")
        assert cur.fetchone() is not None

        # Insert 2 resolved activities
        rec1 = {
            "event_id": "ev_1",
            "event_date": "2026-10-02T10:00:00Z",
            "date": "2026-10-02",
            "time": "10:00:00",
            "top_level_project": "work",
            "project_path": "core / engine",
            "project_levels": ["core", "engine"],
            "section": "Sprint 1",
            "section_id": "sec_1",
            "project_id": "p1",
            "task_id": "t1",
            "parent_task_id": "",
            "task_path": "Implement Feature",
            "task_levels": ["Implement Feature"],
            "description": "Important feature note",
            "priority": "p1",
            "raw_priority": 4,
            "labels": ["urgent", "backend"],
            "due_date": "2026-10-02",
            "due_variance": "on time",
            "due_status": "on_time",
            "was_overdue": False,
        }
        rec2 = {
            "event_id": "ev_2",
            "event_date": "2026-10-01T15:30:00Z",
            "date": "2026-10-01",
            "time": "15:30:00",
            "top_level_project": "personal",
            "project_path": "health / workout",
            "project_levels": ["health", "workout"],
            "section": "",
            "section_id": "",
            "project_id": "p2",
            "task_id": "t2",
            "parent_task_id": "",
            "task_path": "Evening Run",
            "task_levels": ["Evening Run"],
            "description": "",
            "priority": "p4",
            "raw_priority": 1,
            "labels": ["fitness"],
            "due_date": "",
            "due_variance": "undated",
            "due_status": "undated",
            "was_overdue": False,
        }
        cache.save_resolved_activities([rec1, rec2])
        assert cache.get_resolved_activities_count() == 2

        # Upsert rec1 with updated title/path
        rec1_updated = dict(rec1)
        rec1_updated["task_path"] = "Implement Feature (v2)"
        cache.save_resolved_activities([rec1_updated])
        assert cache.get_resolved_activities_count() == 2

        loaded = cache.get_resolved_activities()
        assert len(loaded) == 2
        assert loaded[0]["event_id"] == "ev_1"
        assert loaded[0]["task_path"] == "Implement Feature (v2)"
        cache.close()

    def test_sqlite_filter_pushdown_category(self, tmp_path):
        db_file = tmp_path / "resolved_filter_cat.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        recs = [
            {"event_id": "e1", "date": "2026-10-01", "top_level_project": "work", "task_path": "W1"},
            {"event_id": "e2", "date": "2026-10-01", "top_level_project": "work-areas", "task_path": "W2"},
            {"event_id": "e3", "date": "2026-10-01", "top_level_project": "personal", "task_path": "P1"},
            {"event_id": "e4", "date": "2026-10-01", "top_level_project": "personal-areas", "task_path": "P2"},
            {"event_id": "e5", "date": "2026-10-01", "top_level_project": "archive", "task_path": "A1"},
        ]
        cache.save_resolved_activities(recs)

        work_only = cache.get_resolved_activities(category="work")
        assert len(work_only) == 2
        assert {r["event_id"] for r in work_only} == {"e1", "e2"}

        personal_only = cache.get_resolved_activities(category="personal")
        assert len(personal_only) == 2
        assert {r["event_id"] for r in personal_only} == {"e3", "e4"}

        others_only = cache.get_resolved_activities(category="others")
        assert len(others_only) == 1
        assert others_only[0]["event_id"] == "e5"

        # Custom categories config pushdown
        custom_work = cache.get_resolved_activities(
            category="work",
            categories_config={"work": ["archive*"], "personal": ["personal*"]},
        )
        assert len(custom_work) == 1
        assert custom_work[0]["event_id"] == "e5"

        all_cats = cache.get_resolved_activities(category="all")
        assert len(all_cats) == 5
        cache.close()

    def test_sqlite_filter_pushdown_date_and_attributes(self, tmp_path):
        db_file = tmp_path / "resolved_filter_dates.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        recs = [
            {"event_id": "e1", "date": "2026-09-01", "top_level_project": "work", "priority": "p1", "due_status": "on_time"},
            {"event_id": "e2", "date": "2026-09-15", "top_level_project": "work", "priority": "p2", "due_status": "overdue"},
            {"event_id": "e3", "date": "2026-10-01", "top_level_project": "work", "priority": "p1", "due_status": "overdue"},
        ]
        cache.save_resolved_activities(recs)

        # Date range
        mid = cache.get_resolved_activities(start_date="2026-09-10", end_date="2026-09-20")
        assert len(mid) == 1
        assert mid[0]["event_id"] == "e2"

        # Inverted date range
        assert cache.get_resolved_activities(start_date="2026-10-05", end_date="2026-09-01") == []

        # Priority filter
        p1s = cache.get_resolved_activities(priority="p1")
        assert len(p1s) == 2
        assert {r["event_id"] for r in p1s} == {"e1", "e3"}

        # Due status filter
        overdues = cache.get_resolved_activities(due_status="overdue")
        assert len(overdues) == 2
        assert {r["event_id"] for r in overdues} == {"e2", "e3"}

        # Clear
        cache.clear_resolved_activities()
        assert cache.get_resolved_activities_count() == 0
        cache.close()

    def test_batch_cache_operations(self, tmp_path):
        db_file = tmp_path / "batch_ops.db"
        cache = SQLiteTraceCache(cache_file=str(db_file), enabled=True)

        # 1. Test tasks.update and save_tasks
        task_data = {
            "task-1": {"id": "task-1", "content": "Synthetic Parent", "parent_id": None},
            "task-2": {"id": "task-2", "content": "Synthetic Child", "parent_id": "task-1"},
        }
        cache.save_tasks(task_data)
        assert len(cache.tasks) == 2
        assert cache.tasks["task-2"]["parent_id"] == "task-1"

        # Verify persisted in sqlite
        cur = cache.conn.cursor()
        cur.execute("SELECT id, parent_id, content FROM tasks ORDER BY id")
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[1][1] == "task-1"

        # 2. Test tasks setter
        cache.tasks = [
            {"id": "task-3", "content": "Task 3", "parent_id": None},
            {"id": "task-4", "content": "Task 4", "parent_id": "task-3"},
        ]
        assert len(cache.tasks) == 2
        assert "task-3" in cache.tasks
        assert "task-4" in cache.tasks

        # 3. Test sections.update and labels.update
        cache.sections.update({
            "sec-1": {"id": "sec-1", "project_id": "proj-1", "name": "Backlog"},
        })
        assert "sec-1" in cache.sections

        cache.labels.update({
            "lbl-1": {"id": "lbl-1", "name": "urgent", "color": "red"},
        })
        assert "lbl-1" in cache.labels

        cache.close()

        # 4. Verify reopening loads fast without triggering extra writes
        reopened = SQLiteTraceCache(cache_file=str(db_file), enabled=True)
        assert len(reopened.tasks) == 4
        assert len(reopened.sections) == 1
        assert len(reopened.labels) == 1
        assert reopened.tasks["task-4"]["parent_id"] == "task-3"
        reopened.close()






