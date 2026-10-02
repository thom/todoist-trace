#!/usr/bin/env python3
"""
todoist-trace: Export Todoist completed activity logs with multi-level project
and task hierarchy resolution.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
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
    parser.add_argument(
        "--cache-file",
        type=str,
        default=None,
        help="Path to local cache file (default: .todoist_cache.json)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Disable persistent local cache",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Force re-fetching all data from the API and refresh cache",
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

    # 7. Cache settings
    cache_enabled = not args.no_cache and file_cfg.get("cache_enabled", True)
    cache_file = args.cache_file or file_cfg.get("cache_file") or ".todoist_cache.json"
    refresh = args.refresh

    return {
        "token": token,
        "format": output_format,
        "category": category,
        "markdown_style": markdown_style,
        "start_date": start_date,
        "end_date": end_date,
        "output": output,
        "cache_enabled": cache_enabled,
        "cache_file": cache_file,
        "refresh": refresh,
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


class ProjectTreeResolver:
    """Resolves project hierarchies into root ancestor and relative sub-project path."""

    def __init__(self, projects: List[Dict[str, Any]]):
        self.projects_by_id: Dict[str, Dict[str, Any]] = {
            str(p["id"]): p for p in projects if "id" in p
        }
        self.cache: Dict[str, Dict[str, Any]] = {}

    def resolve(self, project_id: Optional[Any]) -> Dict[str, Any]:
        """
        Recursively resolve project hierarchy.
        Returns:
            {
                "top_level_project": str,
                "project_path": str,
                "project_levels": List[str],
            }
        """
        if not project_id:
            return {
                "top_level_project": "Unknown",
                "project_path": "",
                "project_levels": [],
            }

        pid_str = str(project_id)
        if pid_str in self.cache:
            return self.cache[pid_str]

        chain: List[str] = []
        curr: Optional[str] = pid_str
        visited: set = set()

        while curr and curr in self.projects_by_id and curr not in visited:
            visited.add(curr)
            proj = self.projects_by_id[curr]
            chain.append(proj.get("name", "Unnamed"))
            parent = proj.get("parent_id")
            curr = str(parent) if parent else None

        chain.reverse()

        if not chain:
            res = {
                "top_level_project": "Unknown",
                "project_path": "",
                "project_levels": [],
            }
        else:
            top_level = chain[0]
            levels = chain[1:]
            path = "/".join(levels)
            res = {
                "top_level_project": top_level,
                "project_path": path,
                "project_levels": levels,
            }

        self.cache[pid_str] = res
        return res


class TraceCache:
    """Manages persistent caching of projects, tasks, and activity events."""

    def __init__(self, cache_file: Optional[str] = None, enabled: bool = True):
        self.enabled = enabled
        self.path = Path(cache_file or ".todoist_cache.json")
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


class TaskHierarchyResolver:
    """
    Resolves multi-level task parent-child hierarchies from completed activity events.
    Traces parent tasks upward to build full relative task paths.
    """

    def __init__(
        self,
        token: str,
        preloaded_tasks: Optional[Dict[str, Dict[str, Any]]] = None,
        cache: Optional[TraceCache] = None,
    ):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}
        self.cache = cache
        # Prioritize cache tasks, fallback to preloaded
        self.task_cache: Dict[str, Dict[str, Any]] = {}
        if cache and cache.tasks:
            self.task_cache.update(cache.tasks)
        if preloaded_tasks:
            self.task_cache.update(preloaded_tasks)

    def lookup_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Lookup task content and parent_id, caching results."""
        tid = str(task_id)
        if tid in self.task_cache:
            return self.task_cache[tid]

        url = f"https://api.todoist.com/api/v1/tasks/{tid}"
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                task_info = {
                    "content": data.get("content", f"[Task {tid}]"),
                    "parent_id": str(data["parent_id"]) if data.get("parent_id") else None,
                }
                self.task_cache[tid] = task_info
                if self.cache:
                    self.cache.tasks[tid] = task_info
                return task_info
            elif resp.status_code == 404:
                fallback = {"content": f"[Task {tid}]", "parent_id": None}
                self.task_cache[tid] = fallback
                if self.cache:
                    self.cache.tasks[tid] = fallback
                return fallback
        except requests.exceptions.RequestException:
            pass

        return None


    def resolve(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve an activity event into formatted task hierarchy data.
        Returns:
            {
                "task_path": str,          # e.g. "Root / Subtask / Leaf"
                "task_levels": List[str],  # e.g. ["Root", "Subtask", "Leaf"]
                "parent_task_id": str,
                "project_id": str,
                "event_id": str,
                "date": str,               # YYYY-MM-DD
                "time": str,               # HH:MM:SS
            }
        """
        extra = event.get("extra_data", {})
        current_title = extra.get("content") or f"[Task {event.get('object_id', 'unknown')}]"
        raw_parent_id = extra.get("parent_id") or event.get("parent_item_id")
        parent_task_id = str(raw_parent_id) if raw_parent_id else ""

        event_date_str = str(event.get("event_date", ""))
        date_part = ""
        time_part = ""
        if "T" in event_date_str:
            parts = event_date_str.split("T", 1)
            date_part = parts[0]
            time_part = parts[1].split(".")[0].rstrip("Z")
        elif len(event_date_str) >= 10:
            date_part = event_date_str[:10]

        if not parent_task_id:
            return {
                "task_path": current_title,
                "task_levels": [current_title],
                "parent_task_id": "",
                "project_id": str(event.get("parent_project_id", "")),
                "event_id": str(event.get("id", "")),
                "date": date_part,
                "time": time_part,
            }

        ancestors: List[str] = []
        curr_parent: Optional[str] = parent_task_id
        visited = {str(event.get("object_id", ""))}

        while curr_parent and curr_parent not in visited:
            visited.add(curr_parent)
            parent_info = self.lookup_task(curr_parent)
            if parent_info:
                ancestors.append(parent_info.get("content", f"[Task {curr_parent}]"))
                curr_parent = parent_info.get("parent_id")
            else:
                ancestors.append(f"[Task {curr_parent}]")
                break

        ancestors.reverse()
        full_levels = ancestors + [current_title]
        task_path = " / ".join(full_levels)

        return {
            "task_path": task_path,
            "task_levels": full_levels,
            "parent_task_id": parent_task_id,
            "project_id": str(event.get("parent_project_id", "")),
            "event_id": str(event.get("id", "")),
            "date": date_part,
            "time": time_part,
        }


def fetch_completed_activities(
    token: str,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch completed task activity records using strictly read-only HTTP GET.
    Endpoint: https://api.todoist.com/api/v1/activities
    """
    url = "https://api.todoist.com/api/v1/activities"
    headers = {
        "Authorization": f"Bearer {token}",
    }
    events: List[Dict[str, Any]] = []
    cursor: Optional[str] = None
    page = 0

    while True:
        params: Dict[str, Any] = {
            "object_type": "item",
            "event_type": "completed",
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Network error fetching activity logs: {e}") from e

        if resp.status_code == 401:
            raise ValueError("Invalid Todoist API token.")
        if resp.status_code != 200:
            raise RuntimeError(f"Todoist API returned HTTP {resp.status_code}: {resp.text}")

        data = resp.json()
        results = data.get("results", []) if isinstance(data, dict) else []
        events.extend(results)

        cursor = data.get("next_cursor") if isinstance(data, dict) else None
        page += 1
        if not cursor or (max_pages and page >= max_pages):
            break

    return events


def build_trace_records(
    events: List[Dict[str, Any]],
    project_resolver: ProjectTreeResolver,
    task_resolver: TaskHierarchyResolver,
) -> List[Dict[str, Any]]:
    """Combine activity events with project and task resolvers into unified trace records."""
    records: List[Dict[str, Any]] = []
    for ev in events:
        t_res = task_resolver.resolve(ev)
        p_res = project_resolver.resolve(t_res["project_id"])
        records.append({
            "top_level_project": p_res["top_level_project"],
            "project_path": p_res["project_path"],
            "project_levels": p_res["project_levels"],
            "date": t_res["date"],
            "time": t_res["time"],
            "task_path": t_res["task_path"],
            "task_levels": t_res["task_levels"],
            "parent_task_id": t_res["parent_task_id"],
            "project_id": t_res["project_id"],
            "event_id": t_res["event_id"],
        })
    return records


def filter_records(
    records: List[Dict[str, Any]],
    category: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Filter records by category and date range.
    - category: 'work' (matches 'work' or 'work-areas'), 'personal' (matches 'personal' or 'personal-areas'), or 'all'
    - start_date: 'YYYY-MM-DD' (inclusive)
    - end_date: 'YYYY-MM-DD' (inclusive)
    """
    filtered = []
    cat_lower = (category or "all").lower()

    for r in records:
        top_lower = r.get("top_level_project", "").lower()

        # Category check
        if cat_lower == "work":
            if not (top_lower.startswith("work") or top_lower.startswith("work-areas")):
                continue
        elif cat_lower == "personal":
            if not (top_lower.startswith("personal") or top_lower.startswith("personal-areas")):
                continue

        # Date range check
        rec_date = r.get("date", "")
        if start_date and rec_date < start_date:
            continue
        if end_date and rec_date > end_date:
            continue

        filtered.append(r)

    return filtered


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

    # 1. Initialize Cache
    cache = TraceCache(
        cache_file=settings.get("cache_file"),
        enabled=settings.get("cache_enabled", True),
    )

    # 2. Fetch or load projects
    if cache.enabled and cache.projects and not settings.get("refresh"):
        print(f"Using {len(cache.projects)} cached projects.")
        projects = cache.projects
    else:
        print(f"Connecting to Todoist API (token: {masked_token})...")
        try:
            projects = fetch_projects(settings["token"])
            if cache.enabled:
                cache.projects = projects
        except (ValueError, RuntimeError) as e:
            sys.stderr.write(f"Error: {e}\n")
            return 1

        active = [p for p in projects if not p.get("is_archived", False) and not p.get("is_deleted", False)]
        archived = [p for p in projects if p.get("is_archived", False)]
        print(f"Successfully authenticated! Retrieved {len(projects)} projects ({len(active)} active, {len(archived)} archived).")

    project_resolver = ProjectTreeResolver(projects)

    # 3. Fetch completed activities (incremental if cached)
    date_from = None
    if settings.get("start_date"):
        date_from = f"{settings['start_date']}T00:00:00Z"
    elif cache.enabled and cache.events and not settings.get("refresh"):
        latest_cached = cache.get_latest_event_date()
        if latest_cached:
            date_from = latest_cached
            print(f"Incremental sync: checking for events newer than {latest_cached}...")

    date_to = f"{settings['end_date']}T23:59:59Z" if settings.get("end_date") else None

    print("Fetching completed activities (read-only)...")
    try:
        new_events = fetch_completed_activities(settings["token"], date_from=date_from, date_to=date_to)
        if cache.enabled:
            cache.merge_events(new_events)
            all_events = cache.get_all_events()
            print(f"Retrieved {len(new_events)} new events ({len(all_events)} total events in cache).")
        else:
            all_events = new_events
            print(f"Retrieved {len(all_events)} completed activity events.")
    except (ValueError, RuntimeError) as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    # 4. Resolve tasks
    task_resolver = TaskHierarchyResolver(settings["token"], cache=cache if cache.enabled else None)
    all_records = build_trace_records(all_events, project_resolver, task_resolver)

    # Save updated cache (including newly resolved tasks)
    if cache.enabled:
        cache.save()

    # 5. Apply filters
    filtered_records = filter_records(
        all_records,
        category=settings["category"],
        start_date=settings["start_date"],
        end_date=settings["end_date"],
    )

    print(f"Filters applied (Category: {settings['category']}, Start: {settings['start_date']}, End: {settings['end_date']}):")
    print(f"  {len(filtered_records)} of {len(all_records)} records matched.")

    # Show a few sample filtered records
    print("\nSample matched records:")
    for r in filtered_records[:3]:
        full_proj = f"{r['top_level_project']}" + (f" / {r['project_path']}" if r['project_path'] else "")
        print(f"  [{r['date']} {r['time']}] {full_proj} -> {r['task_path']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


