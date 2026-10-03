"""
Unit tests for CLI argument parsing and configuration resolution.
"""

from todoist_trace.cache import TraceCache
from todoist_trace.cli import parse_args, resolve_settings


class TestCLIAndSettings:
    """Test CLI parsing and configuration precedence."""

    def test_cli_flags_override_defaults(self):
        args = parse_args([
            "-f", "markdown",
            "-c", "work",
            "-s", "2026-09-01",
            "-e", "2026-09-30",
            "-o", "custom.md",
            "-t", "test_token_123",
            "--markdown-style", "flat",
        ])
        settings = resolve_settings(args)

        assert settings["format"] == "markdown"
        assert settings["category"] == "work"
        assert settings["start_date"] == "2026-09-01"
        assert settings["end_date"] == "2026-09-30"
        assert settings["output"] == "custom.md"
        assert settings["token"] == "test_token_123"
        assert settings["markdown_style"] == "flat"

    def test_md_alias_normalizes_to_markdown(self):
        args = parse_args(["-f", "md"])
        settings = resolve_settings(args)
        assert settings["format"] == "markdown"
        assert settings["output"] == "todoist_trace_export.md"

    def test_default_cache_path_in_dotdir(self):
        args = parse_args([])
        settings = resolve_settings(args)
        assert ".todoist-trace/cache.db" in settings["cache_file"]

    def test_cache_save_creates_parent_directory(self, tmp_path):
        nested_cache_file = tmp_path / "new_dir" / "sub" / "cache.json"
        cache = TraceCache(cache_file=str(nested_cache_file), enabled=True)
        cache.projects = [{"id": "p1"}]
        cache.save()
        assert nested_cache_file.is_file()

    def test_reversed_dates_raise_value_error(self):
        import pytest
        args = parse_args(["-s", "2026-10-10", "-e", "2026-10-01"])
        with pytest.raises(ValueError, match="cannot be after end date"):
            resolve_settings(args)

    def test_same_start_and_end_date_valid(self):
        args = parse_args(["-s", "2026-10-01", "-e", "2026-10-01"])
        settings = resolve_settings(args)
        assert settings["start_date"] == "2026-10-01"
        assert settings["end_date"] == "2026-10-01"

    def test_cli_timezone_flag_and_resolution(self):
        import pytest
        from zoneinfo import ZoneInfo
        from datetime import timezone

        # Explicit IANA timezone
        args_zurich = parse_args(["-z", "Europe/Zurich"])
        settings_zurich = resolve_settings(args_zurich)
        assert settings_zurich["timezone"] == "Europe/Zurich"
        assert settings_zurich["tz"] == ZoneInfo("Europe/Zurich")

        # UTC override
        args_utc = parse_args(["--timezone", "UTC"])
        settings_utc = resolve_settings(args_utc)
        assert settings_utc["timezone"] == "UTC"
        assert settings_utc["tz"] == timezone.utc

        # Default local
        args_default = parse_args([])
        settings_default = resolve_settings(args_default)
        assert settings_default["timezone"] == "local"
        assert settings_default["tz"] is not None

        # Invalid timezone raises ValueError
        args_invalid = parse_args(["--timezone", "NonExistent/Zone"])
        with pytest.raises(ValueError, match="Invalid timezone"):
            resolve_settings(args_invalid)

    def test_extended_metadata_flags_defaults(self):
        args = parse_args([])
        settings = resolve_settings(args)
        assert settings["include_labels"] is False
        assert settings["include_descriptions"] is False
        assert settings["include_priorities"] is False
        assert settings["include_due_dates"] is False
        assert settings["all_fields"] is False

    def test_extended_metadata_individual_cli_flags(self):
        args = parse_args([
            "--labels",
            "--descriptions",
            "--priorities",
            "--due-dates",
        ])
        settings = resolve_settings(args)
        assert settings["include_labels"] is True
        assert settings["include_descriptions"] is True
        assert settings["include_priorities"] is True
        assert settings["include_due_dates"] is True

    def test_extended_metadata_all_fields_flag(self):
        args = parse_args(["--all-fields"])
        settings = resolve_settings(args)
        assert settings["include_labels"] is True
        assert settings["include_descriptions"] is True
        assert settings["include_priorities"] is True
        assert settings["include_due_dates"] is True
        assert settings["all_fields"] is True

    def test_extended_metadata_from_config_file(self, tmp_path):
        import json
        cfg_file = tmp_path / "custom_config.json"
        cfg_data = {
            "token": "tok_cfg",
            "include_labels": True,
            "include_priorities": True,
        }
        cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

        args = parse_args(["--config", str(cfg_file)])
        settings = resolve_settings(args)
        assert settings["include_labels"] is True
        assert settings["include_priorities"] is True
        assert settings["include_descriptions"] is False
        assert settings["include_due_dates"] is False

    def test_extended_metadata_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("TODOIST_TRACE_LABELS", "1")
        monkeypatch.setenv("TODOIST_TRACE_DESCRIPTIONS", "true")

        args = parse_args([])
        settings = resolve_settings(args)
        assert settings["include_labels"] is True
        assert settings["include_descriptions"] is True
        assert settings["include_priorities"] is False
        assert settings["include_due_dates"] is False


class TestSubcommandsAndStages:
    """Test git-style subcommands (sync, export, status, run) and stage runners."""

    def test_sync_subcommand_parsing(self):
        args = parse_args(["sync", "-s", "2026-07-01", "-e", "2026-10-01", "-t", "token123", "--refresh"])
        assert args.command == "sync"
        settings = resolve_settings(args)
        assert settings["command"] == "sync"
        assert settings["start_date"] == "2026-07-01"
        assert settings["end_date"] == "2026-10-01"
        assert settings["token"] == "token123"
        assert settings["refresh"] is True

    def test_export_subcommand_parsing(self):
        args = parse_args(["export", "-f", "markdown", "-c", "work", "--all-fields", "-o", "custom_export.md"])
        assert args.command == "export"
        settings = resolve_settings(args)
        assert settings["command"] == "export"
        assert settings["format"] == "markdown"
        assert settings["category"] == "work"
        assert settings["all_fields"] is True
        assert settings["include_labels"] is True
        assert settings["output"] == "custom_export.md"

    def test_status_subcommand_parsing(self, tmp_path):
        db_path = tmp_path / "test.db"
        args = parse_args(["status", "--cache-file", str(db_path)])
        assert args.command == "status"
        settings = resolve_settings(args)
        assert settings["command"] == "status"
        assert settings["cache_file"] == str(db_path)

    def test_run_subcommand_parsing(self):
        args = parse_args(["run", "-s", "2026-08-01", "-f", "csv", "-t", "tok_run"])
        assert args.command == "run"
        settings = resolve_settings(args)
        assert settings["command"] == "run"
        assert settings["start_date"] == "2026-08-01"
        assert settings["format"] == "csv"
        assert settings["token"] == "tok_run"

    def test_flag_only_invocation_defaults_to_run(self):
        args = parse_args(["-s", "2026-08-01", "-f", "markdown", "-t", "tok_def"])
        assert args.command == "run"
        settings = resolve_settings(args)
        assert settings["command"] == "run"
        assert settings["start_date"] == "2026-08-01"
        assert settings["format"] == "markdown"

    def test_empty_invocation_defaults_to_run(self):
        args = parse_args([])
        assert args.command == "run"
        settings = resolve_settings(args)
        assert settings["command"] == "run"

    def test_run_status_output(self, tmp_path, capsys):
        from todoist_trace.cache import SQLiteTraceCache
        from todoist_trace.main import run_status
        from todoist_trace.progress import FancyProgressReporter

        db_path = tmp_path / "status_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_path), enabled=True)
        cache.projects = [{"id": "p1", "name": "Work"}]
        cache.sections = [{"id": "s1", "name": "Sprint", "project_id": "p1"}]
        cache.labels = [{"id": "l1", "name": "urgent"}]
        cache.merge_events([{"id": "ev1", "event_date": "2026-09-01T10:00:00Z", "object_id": "t1"}])
        cache.tasks["t1"] = {"content": "Task 1", "parent_id": None}
        cache.record_sync_range("2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z", is_genesis=False)
        cache.save()

        reporter = FancyProgressReporter(plain=True)
        ret = run_status({"cache_file": str(db_path)}, reporter, cache)
        assert ret == 0

        captured = capsys.readouterr().out
        assert "Todoist Trace Cache Status" in captured
        assert "Projects:   1" in captured
        assert "Sections:   1" in captured
        assert "Labels:     1" in captured
        assert "Tasks:      1" in captured
        assert "Activities: 1" in captured
        assert "2026-09-01T00:00:00Z" in captured

    def test_run_export_on_empty_cache_returns_error(self, tmp_path, capsys):
        from todoist_trace.cache import SQLiteTraceCache
        from todoist_trace.main import run_export
        from todoist_trace.progress import FancyProgressReporter

        db_path = tmp_path / "empty.db"
        cache = SQLiteTraceCache(cache_file=str(db_path), enabled=True)
        reporter = FancyProgressReporter(quiet=True)
        settings = {
            "cache_file": str(db_path),
            "cache_enabled": True,
            "format": "csv",
            "output": str(tmp_path / "out.csv"),
            "category": "all",
            "start_date": None,
            "end_date": None,
        }
        ret = run_export(settings, reporter, cache)
        assert ret == 1
        err = capsys.readouterr().err
        assert "Cache database is empty" in err

    def test_run_export_offline_from_cache(self, tmp_path):
        from todoist_trace.cache import SQLiteTraceCache
        from todoist_trace.main import run_export
        from todoist_trace.progress import FancyProgressReporter

        db_path = tmp_path / "offline_export.db"
        cache = SQLiteTraceCache(cache_file=str(db_path), enabled=True)
        cache.projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        cache.tasks["t1"] = {"content": "Finish report", "parent_id": None, "priority": 4}
        cache.merge_events([{
            "id": "ev10",
            "event_date": "2026-09-15T14:30:00Z",
            "object_id": "t1",
            "parent_project_id": "p1",
            "extra_data": {"content": "Finish report", "priority": 4},
        }])
        cache.save()

        out_csv = tmp_path / "offline.csv"
        settings = {
            "token": None,  # 100% offline
            "cache_file": str(db_path),
            "cache_enabled": True,
            "format": "csv",
            "output": str(out_csv),
            "category": "all",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "include_priorities": True,
            "include_labels": False,
            "include_descriptions": False,
            "include_due_dates": False,
            "quiet": True,
        }
        reporter = FancyProgressReporter(quiet=True)
        ret = run_export(settings, reporter, cache)
        assert ret == 0
        assert out_csv.is_file()
        content = out_csv.read_text(encoding="utf-8")
        assert "Finish report" in content
        assert "p1" in content

    def test_run_sync_requires_token(self, tmp_path, capsys):
        from todoist_trace.cache import SQLiteTraceCache
        from todoist_trace.main import run_sync
        from todoist_trace.progress import FancyProgressReporter

        db_path = tmp_path / "no_token.db"
        cache = SQLiteTraceCache(cache_file=str(db_path), enabled=True)
        reporter = FancyProgressReporter(quiet=True)
        settings = {"token": None, "cache_file": str(db_path), "cache_enabled": True}
        ret = run_sync(settings, reporter, cache)
        assert ret == 1
        err = capsys.readouterr().err
        assert "Todoist API token not found" in err

    def test_cache_corrupted_auto_backup(self, tmp_path, capsys):
        from todoist_trace.cache import SQLiteTraceCache

        corrupt_db = tmp_path / "corrupted.db"
        corrupt_db.write_text("This is garbage data, not a sqlite database!", encoding="utf-8")

        cache = SQLiteTraceCache(cache_file=str(corrupt_db), enabled=True)
        bak_file = tmp_path / "corrupted.db.bak"
        assert bak_file.is_file()
        assert bak_file.read_text(encoding="utf-8") == "This is garbage data, not a sqlite database!"
        # New database is valid
        assert corrupt_db.is_file()
        assert cache.conn is not None
        cache.close()

    def test_run_export_html(self, tmp_path):
        from todoist_trace.cache import SQLiteTraceCache
        from todoist_trace.main import run_export
        from todoist_trace.progress import FancyProgressReporter

        db_path = tmp_path / "html_test.db"
        cache = SQLiteTraceCache(cache_file=str(db_path), enabled=True)
        cache.projects = [{"id": "p1", "name": "Work", "parent_id": None}]
        cache.tasks["t1"] = {"content": "Build Dashboard", "parent_id": None, "priority": 4}
        cache.merge_events([{
            "id": "ev99",
            "event_date": "2026-09-20T10:00:00Z",
            "object_id": "t1",
            "parent_project_id": "p1",
            "extra_data": {"content": "Build Dashboard", "priority": 4},
        }])
        cache.save()

        out_html = tmp_path / "output.html"
        settings = {
            "token": None,
            "cache_file": str(db_path),
            "cache_enabled": True,
            "format": "html",
            "output": str(out_html),
            "category": "all",
            "start_date": None,
            "end_date": None,
            "quiet": True,
        }
        reporter = FancyProgressReporter(quiet=True)
        ret = run_export(settings, reporter, cache)
        assert ret == 0
        assert cache.get_resolved_activities_count() == 1
        assert out_html.is_file()
        text = out_html.read_text(encoding="utf-8")
        assert "Build Dashboard" in text
        assert "timeline-chart" in text

