"""
Configuration loader and path resolution for todoist-trace.
Handles discovery of user dotfiles (~/.todoist-trace/) and local overrides.
"""

import json
import os
import sys
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo


def resolve_timezone(tz_name: Optional[Union[str, tzinfo]] = None) -> tzinfo:
    """
    Resolve a timezone identifier into a tzinfo object.
    Supports:
    - None or 'local' (case-insensitive): system local timezone
    - 'UTC' (case-insensitive): timezone.utc
    - IANA timezone string (e.g. 'Europe/Zurich', 'America/New_York')
    - Existing tzinfo instance: returned as-is
    Raises ValueError for invalid timezone names.
    """
    if tz_name is None or (isinstance(tz_name, str) and (not tz_name.strip() or tz_name.strip().lower() == "local")):
        return datetime.now().astimezone().tzinfo or timezone.utc
    if isinstance(tz_name, tzinfo):
        return tz_name
    cleaned = tz_name.strip()
    if cleaned.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(cleaned)
    except Exception:
        raise ValueError(
            f"Invalid timezone: {tz_name!r}. Please specify a valid IANA timezone name (e.g. 'Europe/Zurich', 'UTC') or 'local'."
        )


DEFAULT_APP_DIR = Path.home() / ".todoist-trace"
DEFAULT_CONFIG_PATH = DEFAULT_APP_DIR / "config.json"
DEFAULT_CACHE_PATH = DEFAULT_APP_DIR / "cache.db"
DEFAULT_JSON_CACHE_PATH = DEFAULT_APP_DIR / "cache.json"
DEFAULT_HIERARCHY_PATH = DEFAULT_APP_DIR / "project_hierarchy.json"


def load_env_file(path: Path) -> Dict[str, str]:
    """Parse a simple .env file into a key-value dictionary."""
    data: Dict[str, str] = {}
    if not path.is_file():
        return data

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    data[key] = val
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to read env file {path}: {e}\n")
    return data


def load_config(custom_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load configuration from candidate files in order of precedence:
    1. Explicit custom path (--config)
    2. Local directory (config.json or .env)
    3. User home dotdir (~/.todoist-trace/config.json)
    4. User XDG config directory (~/.config/todoist-trace/config.json)
    """
    config: Dict[str, Any] = {}

    candidates: List[Path] = []
    if custom_path:
        candidates.append(Path(custom_path).expanduser())
    else:
        candidates.extend([
            Path("config.json"),
            Path(".env"),
            DEFAULT_CONFIG_PATH,
            Path.home() / ".config" / "todoist-trace" / "config.json",
        ])

    for path in candidates:
        if path.is_file():
            try:
                if path.suffix == ".json" or "json" in path.name:
                    with open(path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        break
                elif path.name == ".env" or path.suffix == ".env":
                    env_data = load_env_file(path)
                    if env_data:
                        # Map env keys to internal config keys
                        if "TODOIST_API_TOKEN" in env_data:
                            config["token"] = env_data["TODOIST_API_TOKEN"]
                        if "TODOIST_TRACE_FORMAT" in env_data:
                            config["format"] = env_data["TODOIST_TRACE_FORMAT"]
                        if "TODOIST_TRACE_CATEGORY" in env_data:
                            config["category"] = env_data["TODOIST_TRACE_CATEGORY"]
                        if "TODOIST_TRACE_OUTPUT" in env_data:
                            config["output"] = env_data["TODOIST_TRACE_OUTPUT"]
                        if "TODOIST_TRACE_START_DATE" in env_data:
                            config["start_date"] = env_data["TODOIST_TRACE_START_DATE"]
                        if "TODOIST_TRACE_END_DATE" in env_data:
                            config["end_date"] = env_data["TODOIST_TRACE_END_DATE"]
                        break
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to load config from {path}: {e}\n")
                continue

    return config
