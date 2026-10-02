"""
Main orchestration and CLI entry point for todoist-trace.
"""

import sys
from typing import Optional

from .api import fetch_completed_activities, fetch_projects
from .cache import create_cache
from .cli import parse_args, resolve_settings
from .exporters import export_csv, export_markdown
from .filters import filter_records
from .resolvers import ProjectTreeResolver, TaskHierarchyResolver, build_trace_records


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
    cache = create_cache(
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
    elif cache.enabled and cache.get_events_count() > 0 and not settings.get("refresh"):
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

    # 6. Export records
    out_path = settings["output"]
    out_fmt = settings["format"]
    if out_fmt == "csv":
        export_csv(filtered_records, out_path)
    else:
        export_markdown(
            filtered_records,
            out_path,
            style=settings["markdown_style"],
            task_style=settings["task_style"],
        )

    print(f"\nSuccessfully exported {len(filtered_records)} records to {out_path} ({out_fmt.upper()} format).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
