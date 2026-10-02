"""
Main orchestration and CLI entry point for todoist-trace.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

from .api import fetch_completed_activities, fetch_projects
from .cache import (
    create_cache,
    normalize_end_date,
    normalize_start_date,
)
from .cli import parse_args, resolve_settings
from .exporters import export_csv, export_markdown
from .filters import filter_records
from .resolvers import ProjectTreeResolver, TaskHierarchyResolver, build_trace_records


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint."""
    args = parse_args(argv)
    try:
        settings = resolve_settings(args)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

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

    # 3. Fetch completed activities (gap-filling range-aware sync)
    req_start = settings.get("start_date")
    req_end = settings.get("end_date")
    tz = settings.get("tz")

    if cache.enabled and not settings.get("refresh"):
        missing_ranges = cache.get_missing_ranges(req_start, req_end, tz=tz)
    else:
        norm_s = normalize_start_date(req_start, tz=tz)
        norm_e = normalize_end_date(req_end, tz=tz) or datetime.now(timezone.utc).isoformat()
        missing_ranges = [(norm_s, norm_e)]

    new_events = []
    if not missing_ranges:
        print(f"Requested date range is fully cached in SQLite ({cache.get_events_count()} events in cache). Zero API calls needed.")
    else:
        print("Fetching completed activities (read-only)...")
        for gap_start, gap_end in missing_ranges:
            desc_from = gap_start[:10] if gap_start else "account creation"
            desc_to = gap_end[:10] if gap_end else "present"
            print(f"Syncing missing range: {desc_from} to {desc_to}...")
            try:
                fetched = fetch_completed_activities(settings["token"], date_from=gap_start, date_to=gap_end)
                new_events.extend(fetched)
                if cache.enabled:
                    cache.merge_events(fetched)
                    is_genesis = (gap_start is None)
                    now_iso = datetime.now(timezone.utc).isoformat()
                    # A cache cannot record synchronization beyond the present moment
                    effective_end = min(gap_end, now_iso) if gap_end else now_iso
                    effective_start = gap_start or (fetched[-1]["event_date"] if fetched else "1970-01-01T00:00:00Z")
                    if effective_start < effective_end:
                        cache.record_sync_range(effective_start, effective_end, is_genesis=is_genesis)
                    print(f"Retrieved {len(fetched)} events for range ({cache.get_events_count()} total in cache).")
            except (ValueError, RuntimeError) as e:
                sys.stderr.write(f"Error: {e}\n")
                return 1

    # Load matching events from cache
    if cache.enabled:
        cache.save()
        all_events = cache.get_events_in_range(req_start, req_end, tz=tz)
    else:
        all_events = new_events

    # 4. Resolve tasks
    task_resolver = TaskHierarchyResolver(settings["token"], cache=cache if cache.enabled else None, tz=tz)
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
