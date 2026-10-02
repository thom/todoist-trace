"""
Unit tests for terminal progress reporting, day-based sync tracking,
progress bars, and quiet mode.
"""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from todoist_trace.api import fetch_completed_activities, fetch_projects
from todoist_trace.cli import parse_args, resolve_settings
from todoist_trace.progress import (
    FancyProgressReporter,
    Style,
    format_duration,
    parse_iso_timestamp,
    render_progress_bar,
    supports_color,
)
from todoist_trace.resolvers import (
    ProjectTreeResolver,
    TaskHierarchyResolver,
    build_trace_records,
)


class TestProgressHelpers:
    """Test progress utility functions."""

    def test_supports_color_respects_flags_and_env(self):
        stream = io.StringIO()
        assert not supports_color(stream, force_no_color=True)

        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            assert not supports_color(stream, force_no_color=False)

        with patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            assert not supports_color(stream, force_no_color=False)

    def test_render_progress_bar_percentage_bounds(self):
        assert render_progress_bar(0.0, width=10) == "░░░░░░░░░░"
        assert render_progress_bar(50.0, width=10) == "█████░░░░░"
        assert render_progress_bar(100.0, width=10) == "██████████"
        assert render_progress_bar(-10.0, width=10) == "░░░░░░░░░░"
        assert render_progress_bar(150.0, width=10) == "██████████"
        assert render_progress_bar(50.0, width=0) == ""

    def test_format_duration(self):
        assert format_duration(0) == "00:00"
        assert format_duration(45) == "00:45"
        assert format_duration(125) == "02:05"
        assert format_duration(3665) == "01:01:05"

    def test_parse_iso_timestamp(self):
        dt = parse_iso_timestamp("2026-10-02T15:30:00Z")
        assert dt is not None
        assert dt.year == 2026
        assert dt.month == 10
        assert dt.day == 2

        assert parse_iso_timestamp(None) is None
        assert parse_iso_timestamp("invalid-date") is None

    def test_style_enabled_and_disabled(self):
        s_on = Style(enabled=True)
        assert "\033[32mhello\033[0m" in s_on.green("hello")
        assert "\033[36mhello\033[0m" in s_on.cyan("hello")
        assert "\033[1mhello\033[0m" in s_on.bold("hello")

        s_off = Style(enabled=False)
        assert s_off.green("hello") == "hello"
        assert s_off.bold("hello") == "hello"


class TestFancyProgressReporter:
    """Test FancyProgressReporter operations across TTY, non-TTY, and quiet modes."""

    def test_quiet_mode_suppresses_all_output(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=True, stream=buf)

        reporter.print_banner("2026-01-01 to 2026-10-02", "Europe/Zurich", "cache.db")
        reporter.start_projects(cached=False)
        reporter.update_projects(10, 5)
        reporter.finish_projects(10, 5)
        reporter.start_sync("2026-01-01T00:00:00Z", "2026-10-02T23:59:59Z")
        reporter.update_sync(500, "2026-05-01T12:00:00Z")
        reporter.finish_sync(500, 1000)
        reporter.start_resolve(100)
        reporter.update_resolve(50, 100)
        reporter.finish_resolve(100)
        reporter.finish_export("out.csv", 100, 100, "csv")

        assert buf.getvalue() == ""

    def test_banner_and_project_reporting_non_tty(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)

        reporter.print_banner(
            date_range_desc="2026-01-01 to 2026-10-02 (275 days)",
            timezone_desc="Europe/Zurich",
            cache_desc="~/.todoist-trace/cache.db (SQLite)",
        )
        output = buf.getvalue()
        assert "todoist-trace" in output
        assert "2026-01-01 to 2026-10-02 (275 days)" in output
        assert "Europe/Zurich" in output

        # Project cached
        buf.seek(0)
        buf.truncate(0)
        reporter.start_projects(cached=True, count=42)
        assert "42 cached projects loaded" in buf.getvalue()

        # Project fetched
        buf.seek(0)
        buf.truncate(0)
        reporter.finish_projects(30, 12)
        assert "42 retrieved (30 active, 12 archived)" in buf.getvalue()

    def test_sync_day_percentage_calculation(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)

        start_iso = "2026-01-01T00:00:00Z"
        end_iso = "2026-10-01T23:59:59Z"
        reporter.start_sync(start_iso, end_iso)

        # Midway event (~May 2026)
        midway_event = "2026-05-15T12:00:00Z"
        reporter.update_sync(600, midway_event)

        output = buf.getvalue()
        assert "Syncing activities: 2026-01-01 → 2026-10-01" in output
        assert "activities synced" in output

        # Finish sync
        reporter.finish_sync(600, 1200, elapsed_sec=2.5)
        assert "Sync complete: 600 new activities synced" in buf.getvalue()

    def test_sync_single_day_range_avoids_division_by_zero(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)

        start_iso = "2026-10-01T00:00:00Z"
        end_iso = "2026-10-01T23:59:59Z"
        reporter.start_sync(start_iso, end_iso)
        reporter.update_sync(500, "2026-10-01T12:00:00Z")
        reporter.finish_sync(500, 500, elapsed_sec=1.0)

        output = buf.getvalue()
        assert "Sync complete: 500 new activities synced" in output

    def test_sync_genesis_unbounded_start(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)

        reporter.start_sync(start_iso=None, end_iso="2026-10-01T23:59:59Z")
        reporter.update_sync(750, "2024-03-01T10:00:00Z")
        reporter.finish_sync(750, 750, elapsed_sec=3.0)

        output = buf.getvalue()
        assert "Syncing activities: genesis → 2026-10-01" in output
        assert "750 new activities synced" in output

    def test_task_resolution_and_export_reporting(self):
        buf = io.StringIO()
        reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)

        reporter.start_resolve(1500)
        reporter.update_resolve(1000, 1500)
        reporter.update_resolve(1500, 1500)
        reporter.finish_resolve(1500)

        assert "Resolving task hierarchies (1,500 records)" in buf.getvalue()
        assert "1,500 records resolved" in buf.getvalue()

        reporter.finish_export("export.md", 1200, 1500, "markdown", style_desc="nested")
        assert "Export complete: export.md (1,200 of 1,500 records matched, MARKDOWN (nested))" in buf.getvalue()

    def test_tty_interactive_mode_rendering(self):
        buf = io.StringIO()
        # Mock isatty to return True
        buf.isatty = lambda: True

        with patch.dict(os.environ, {}, clear=True):
            reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)
            assert reporter.is_tty is True

            reporter.start_sync("2026-01-01T00:00:00Z", "2026-10-01T23:59:59Z")
            reporter.update_sync(250, "2026-06-01T00:00:00Z")

            output = buf.getvalue()
            assert "\r\033[K" in output

        # Antigravity disables in-place overwriting to avoid garbled transcripts
        with patch.dict(os.environ, {"ANTIGRAVITY_AGENT": "1"}, clear=True):
            ag_reporter = FancyProgressReporter(quiet=False, no_color=True, stream=buf)
            assert ag_reporter.is_tty is False


class TestProgressIntegration:
    """Test CLI arguments, API callbacks, and resolver progress callbacks."""

    def test_cli_quiet_and_no_color_flags(self):
        args = parse_args(["-q", "--no-color", "--token", "test_tok"])
        settings = resolve_settings(args)
        assert settings["quiet"] is True
        assert settings["no_color"] is True

    def test_cli_plain_flag(self):
        args = parse_args(["--plain", "--token", "test_tok"])
        settings = resolve_settings(args)
        assert settings["plain"] is True

    @patch("todoist_trace.api.requests.get")
    def test_api_fetch_projects_progress_callback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [{"id": "p1", "name": "Work", "parent_id": None}],
            "next_cursor": None,
        }
        mock_get.return_value = mock_resp

        cb_calls = []
        fetch_projects("test_tok", progress_cb=lambda act, arc: cb_calls.append((act, arc)))

        assert len(cb_calls) > 0
        assert cb_calls[0] == (1, 0)

    @patch("todoist_trace.api.requests.get")
    def test_api_fetch_activities_progress_callback(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"id": "e1", "event_date": "2026-10-01T12:00:00Z"},
                {"id": "e2", "event_date": "2026-09-30T10:00:00Z"},
            ],
            "next_cursor": None,
        }
        mock_get.return_value = mock_resp

        cb_calls = []
        fetch_completed_activities(
            "test_tok",
            progress_cb=lambda count, oldest: cb_calls.append((count, oldest)),
        )

        assert len(cb_calls) == 1
        assert cb_calls[0] == (2, "2026-09-30T10:00:00Z")

    def test_build_trace_records_progress_callback(self):
        events = [
            {"id": f"e{i}", "object_id": f"t{i}", "event_date": "2026-10-01T10:00:00Z", "extra_data": {"content": f"Task {i}"}}
            for i in range(50)
        ]
        p_resolver = ProjectTreeResolver([])
        t_resolver = TaskHierarchyResolver("test_tok")

        calls = []
        records = build_trace_records(
            events,
            p_resolver,
            t_resolver,
            progress_cb=lambda cur, tot: calls.append((cur, tot)),
        )

        assert len(records) == 50
        # Progress callback should be called on multiples of 20 and at completion (20, 40, 50)
        assert len(calls) == 3
        assert calls[-1] == (50, 50)
