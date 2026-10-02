"""
Configuration loader and path resolution for todoist-trace.
Handles discovery of user dotfiles (~/.todoist-trace/) and local overrides.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_APP_DIR = Path.home() / ".todoist-trace"
DEFAULT_CONFIG_PATH = DEFAULT_APP_DIR / "config.json"
DEFAULT_CACHE_PATH = DEFAULT_APP_DIR / "cache.db"
DEFAULT_JSON_CACHE_PATH = DEFAULT_APP_DIR / "cache.json"


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
                        if "TODOIST_TRACE_MARKDOWN_STYLE" in env_data:
                            config["markdown_style"] = env_data["TODOIST_TRACE_MARKDOWN_STYLE"]
                        if "TODOIST_TRACE_TASK_STYLE" in env_data:
                            config["task_style"] = env_data["TODOIST_TRACE_TASK_STYLE"]
                        if "TODOIST_TRACE_START_DATE" in env_data:
                            config["start_date"] = env_data["TODOIST_TRACE_START_DATE"]
                        if "TODOIST_TRACE_END_DATE" in env_data:
                            config["end_date"] = env_data["TODOIST_TRACE_END_DATE"]
                        break
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to load config from {path}: {e}\n")
                continue

    return config
