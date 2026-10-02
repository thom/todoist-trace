#!/usr/bin/env python3
"""
todoist-trace: Export Todoist completed activity logs with multi-level project
and task hierarchy resolution.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


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
    3. User config directory (~/.config/todoist-trace/config.json)
    """
    config: Dict[str, Any] = {}

    candidates = []
    if custom_path:
        candidates.append(Path(custom_path))
    else:
        candidates.extend([
            Path("config.json"),
            Path(".env"),
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
                        if "TODOIST_TRACE_START_DATE" in env_data:
                            config["start_date"] = env_data["TODOIST_TRACE_START_DATE"]
                        if "TODOIST_TRACE_END_DATE" in env_data:
                            config["end_date"] = env_data["TODOIST_TRACE_END_DATE"]
                        break
            except Exception as e:
                sys.stderr.write(f"Warning: Failed to load config from {path}: {e}\n")
                continue

    return config


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="todoist-trace",
        description="Export Todoist activity logs into structured CSV or Markdown files with project and task hierarchy resolution.",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["csv", "markdown", "md"],
        default=None,
        help="Output format: csv or markdown / md (default: csv)",
    )
    parser.add_argument(
        "-s", "--start-date",
        type=str,
        default=None,
        help="Start date filter in YYYY-MM-DD format (inclusive)",
    )
    parser.add_argument(
        "-e", "--end-date",
        type=str,
        default=None,
        help="End date filter in YYYY-MM-DD format (inclusive)",
    )
    parser.add_argument(
        "-c", "--category",
        choices=["work", "personal", "all"],
        default=None,
        help="Top-level project filter: work, personal, or all (default: all)",
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output file path (default: todoist_trace_export.csv or .md)",
    )
    parser.add_argument(
        "-t", "--token",
        type=str,
        default=None,
        help="Todoist API token (falls back to TODOIST_API_TOKEN env var or config file)",
    )
    parser.add_argument(
        "--markdown-style",
        choices=["nested", "flat"],
        default=None,
        help="Markdown project heading style: nested (#### admin / ##### email) or flat (#### admin/email) (default: nested)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom config file (JSON or .env)",
    )
    return parser.parse_args(argv)


def resolve_settings(args: argparse.Namespace) -> Dict[str, Any]:
    """
    Resolve final settings by merging CLI arguments, environment variables,
    config file values, and defaults in order of precedence:
    1. CLI argument (if provided)
    2. Environment variable
    3. Config file
    4. Default value
    """
    file_cfg = load_config(args.config)

    # 1. Token
    token = args.token or os.environ.get("TODOIST_API_TOKEN") or file_cfg.get("token")

    # 2. Format
    raw_format = args.format or os.environ.get("TODOIST_TRACE_FORMAT") or file_cfg.get("format") or "csv"
    output_format = "markdown" if raw_format.lower() in ("md", "markdown") else "csv"

    # 3. Category
    category = (args.category or os.environ.get("TODOIST_TRACE_CATEGORY") or file_cfg.get("category") or "all").lower()

    # 4. Markdown Style
    markdown_style = (args.markdown_style or os.environ.get("TODOIST_TRACE_MARKDOWN_STYLE") or file_cfg.get("markdown_style") or "nested").lower()

    # 5. Dates
    start_date = args.start_date or os.environ.get("TODOIST_TRACE_START_DATE") or file_cfg.get("start_date")
    end_date = args.end_date or os.environ.get("TODOIST_TRACE_END_DATE") or file_cfg.get("end_date")

    # 6. Output path
    output = args.output or os.environ.get("TODOIST_TRACE_OUTPUT") or file_cfg.get("output")
    if not output:
        output = "todoist_trace_export.csv" if output_format == "csv" else "todoist_trace_export.md"

    return {
        "token": token,
        "format": output_format,
        "category": category,
        "markdown_style": markdown_style,
        "start_date": start_date,
        "end_date": end_date,
        "output": output,
    }


def fetch_projects(token: str) -> List[Dict[str, Any]]:
    """
    Fetch active and archived projects from the Todoist API.
    Handles cursor pagination across active and archived endpoints.
    """
    headers = {
        "Authorization": f"Bearer {token}",
    }
    all_projects: List[Dict[str, Any]] = []

    # 1. Fetch active projects (paginated)
    url = "https://api.todoist.com/api/v1/projects"
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error communicating with Todoist API: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token. Please check your credentials.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        all_projects.extend(results)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        if not cursor:
            break

    # 2. Fetch archived projects
    archived_url = "https://api.todoist.com/api/v1/projects/archived"
    cursor = None
    while True:
        params = {"cursor": cursor} if cursor else {}
        try:
            resp = requests.get(archived_url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching archived projects: {e}") from e

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for p in results:
                p["is_archived"] = True
            all_projects.extend(results)
            cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not cursor:
                break
        else:
            break

    return all_projects


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    args = parse_args(argv)
    settings = resolve_settings(args)

    if not settings["token"]:
        sys.stderr.write(
            "Error: Todoist API token not found.\n"
            "Please provide a token via:\n"
            "  - Command line flag: --token <TOKEN>\n"
            "  - Environment variable: export TODOIST_API_TOKEN=<TOKEN>\n"
            "  - Config file: config.json or .env\n"
        )
        return 1

    masked_token = settings["token"][:4] + "..." + settings["token"][-4:] if len(settings["token"]) > 8 else "***"
    print(f"Connecting to Todoist API (token: {masked_token})...")
    try:
        projects = fetch_projects(settings["token"])
    except (ValueError, RuntimeError) as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    active = [p for p in projects if not p.get("is_archived", False) and not p.get("is_deleted", False)]
    archived = [p for p in projects if p.get("is_archived", False)]
    print(f"Successfully authenticated! Retrieved {len(projects)} projects ({len(active)} active, {len(archived)} archived).")

    sample_names = [p.get("name", "Unnamed") for p in active[:5]]
    if sample_names:
        print(f"Sample projects: {', '.join(sample_names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

