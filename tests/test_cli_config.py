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

    def test_include_labels_flag_and_config(self, tmp_path, monkeypatch):
        import json

        # Default is False
        args_def = parse_args([])
        assert resolve_settings(args_def)["include_labels"] is False

        # CLI flag overrides to True
        args_flag = parse_args(["--labels"])
        assert resolve_settings(args_flag)["include_labels"] is True

        args_alias = parse_args(["--include-labels"])
        assert resolve_settings(args_alias)["include_labels"] is True

        # Config file support
        cfg_file = tmp_path / "cfg.json"
        cfg_file.write_text(json.dumps({"token": "tok", "include_labels": True}), encoding="utf-8")
        args_cfg = parse_args(["--config", str(cfg_file)])
        assert resolve_settings(args_cfg)["include_labels"] is True

        # Env var support
        monkeypatch.setenv("TODOIST_TRACE_LABELS", "1")
        assert resolve_settings(args_def)["include_labels"] is True

    def test_include_descriptions_flag_and_config(self, tmp_path, monkeypatch):
        import json

        # Default is False
        args_def = parse_args([])
        assert resolve_settings(args_def)["include_descriptions"] is False

        # CLI flag overrides to True
        args_flag = parse_args(["--descriptions"])
        assert resolve_settings(args_flag)["include_descriptions"] is True

        args_alias = parse_args(["--include-descriptions"])
        assert resolve_settings(args_alias)["include_descriptions"] is True

        # Config file support
        cfg_file = tmp_path / "cfg_desc.json"
        cfg_file.write_text(json.dumps({"token": "tok", "include_descriptions": True}), encoding="utf-8")
        args_cfg = parse_args(["--config", str(cfg_file)])
        assert resolve_settings(args_cfg)["include_descriptions"] is True

        # Env var support
        monkeypatch.setenv("TODOIST_TRACE_DESCRIPTIONS", "true")
        assert resolve_settings(args_def)["include_descriptions"] is True


