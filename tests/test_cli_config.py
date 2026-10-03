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

