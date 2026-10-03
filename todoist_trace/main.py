"""
Main orchestration and CLI entry point for todoist-trace.
Supports git-style subcommands: sync, export, status, and run.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .api import fetch_completed_activities, fetch_labels, fetch_projects, fetch_sections
from .cache import (
    create_cache,
    normalize_end_date,
    normalize_start_date,
)
from .cli import parse_args, resolve_settings
from .exporters import export_csv, export_markdown
from .filters import filter_records
from .progress import FancyProgressReporter
from .resolvers import (
    LabelResolver,
    ProjectTreeResolver,
    SectionResolver,
    TaskHierarchyResolver,
    build_trace_records,
)


def _format_size(size_bytes: int) -> str:
    """Format file size in bytes to human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def run_status(settings: Dict[str, Any], reporter: FancyProgressReporter, cache: Any) -> int:
    """Display local cache statistics, entity counts, and synchronized date ranges."""
    cache_path = Path(cache.path)
    file_size_str = "0 B (not created)"
    if cache_path.is_file():
        file_size_str = _format_size(cache_path.stat().st_size)

    cache_mode = "SQLite" if str(cache_path).endswith((".db", ".sqlite")) else "JSON"
    last_sync = cache.get_last_sync() or "Never"
    events_count = cache.get_events_count()
    projects_count = len(cache.projects)
    sections_count = len(cache.sections)
    labels_count = len(cache.labels)
    tasks_count = len(cache.tasks)
    oldest_event, newest_event = cache.get_date_bounds()
    sync_ranges = cache.get_sync_ranges()

    reporter.print_text(reporter.style.bold("\nTodoist Trace Cache Status"))
    reporter.print_text(reporter.style.dim("─" * 32))
    reporter.print_text(f"  Location:     {cache_path} ({cache_mode})")
    reporter.print_text(f"  File Size:    {file_size_str}")
    reporter.print_text(f"  Cache State:  {'Active' if cache.enabled else 'Disabled'}")
    reporter.print_text(f"  Last Sync:    {last_sync}")
    reporter.print_text("")
    reporter.print_text(reporter.style.bold("Cached Entities:"))
    reporter.print_text(f"  • Projects:   {projects_count}")
    reporter.print_text(f"  • Sections:   {sections_count}")
    reporter.print_text(f"  • Labels:     {labels_count}")
    reporter.print_text(f"  • Tasks:      {tasks_count}")
    if events_count > 0 and oldest_event and newest_event:
        reporter.print_text(f"  • Activities: {events_count} ({oldest_event} → {newest_event})")
    else:
        reporter.print_text(f"  • Activities: {events_count}")

    reporter.print_text("")
    reporter.print_text(reporter.style.bold("Synchronized UTC Ranges:"))
    if sync_ranges:
        for s, e, g in sync_ranges:
            genesis_mark = " (genesis)" if g else ""
            reporter.print_text(f"  • {s}  →  {e}{genesis_mark}")
    else:
        reporter.print_text("  (No ranges recorded)")
    reporter.print_text("")
    return 0


def run_sync(settings: Dict[str, Any], reporter: FancyProgressReporter, cache: Any) -> int:
    """Fetch projects, sections, labels, activities, and task hierarchies into cache."""
    token = settings.get("token")
    if not token:
        sys.stderr.write(
            "Error: Todoist API token not found.\n"
            "Please provide a token via:\n"
            "  - Command line flag: --token <TOKEN>\n"
            "  - Environment variable: export TODOIST_API_TOKEN=<TOKEN>\n"
            "  - Config file: config.json or .env\n"
        )
        return 1

    refresh = settings.get("refresh", False)

    # 1. Fetch or load projects
    if cache.enabled and cache.projects and not refresh:
        reporter.start_projects(cached=True, count=len(cache.projects))
        projects = cache.projects
    else:
        reporter.start_projects(cached=False)
        try:
            projects = fetch_projects(
                token,
                progress_cb=lambda active, archived: reporter.update_projects(active, archived),
            )
            if cache.enabled:
                cache.projects = projects
        except (ValueError, RuntimeError) as e:
            sys.stderr.write(f"Error: {e}\n")
            return 1

        active = [p for p in projects if not p.get("is_archived", False) and not p.get("is_deleted", False)]
        archived = [p for p in projects if p.get("is_archived", False)]
        reporter.finish_projects(len(active), len(archived))

    # 2. Preload sections
    if cache.enabled and hasattr(cache, "sections") and cache.sections and not refresh:
        sections = cache.sections
    else:
        try:
            sections_list = fetch_sections(token)
            if cache.enabled:
                cache.sections = sections_list
            sections = cache.sections if cache.enabled else {s["id"]: s for s in sections_list if s.get("id")}
        except Exception:
            sections = cache.sections if (cache.enabled and hasattr(cache, "sections")) else {}

    # 3. Preload labels
    if cache.enabled and hasattr(cache, "labels") and cache.labels and not refresh:
        labels = cache.labels
    else:
        try:
            labels_list = fetch_labels(token)
            if cache.enabled:
                cache.labels = labels_list
            labels = cache.labels if cache.enabled else {l["id"]: l for l in labels_list if l.get("id")}
        except Exception:
            labels = cache.labels if (cache.enabled and hasattr(cache, "labels")) else {}

    # 4. Fetch completed activities (gap-filling range-aware sync)
    req_start = settings.get("start_date")
    req_end = settings.get("end_date")
    tz = settings.get("tz")

    if cache.enabled and not refresh:
        missing_ranges = cache.get_missing_ranges(req_start, req_end, tz=tz)
    else:
        norm_s = normalize_start_date(req_start, tz=tz)
        norm_e = normalize_end_date(req_end, tz=tz) or datetime.now(timezone.utc).isoformat()
        missing_ranges = [(norm_s, norm_e)]

    new_events = []
    if not missing_ranges:
        reporter.start_sync(None, None, total_cache_count=cache.get_events_count(), fully_cached=True)
    else:
        for gap_start, gap_end in missing_ranges:
            reporter.start_sync(gap_start, gap_end, total_cache_count=cache.get_events_count(), fully_cached=False)
            try:
                fetched = fetch_completed_activities(
                    token,
                    date_from=gap_start,
                    date_to=gap_end,
                    progress_cb=lambda count, oldest: reporter.update_sync(count, oldest),
                )
                new_events.extend(fetched)
                if cache.enabled:
                    cache.merge_events(fetched)
                    is_genesis = (gap_start is None)
                    now_iso = datetime.now(timezone.utc).isoformat()
                    effective_end = min(gap_end, now_iso) if gap_end else now_iso
                    effective_start = gap_start or (fetched[-1]["event_date"] if fetched else "1970-01-01T00:00:00Z")
                    if effective_start < effective_end:
                        cache.record_sync_range(effective_start, effective_end, is_genesis=is_genesis)
                reporter.finish_sync(
                    len(fetched),
                    cache.get_events_count() if cache.enabled else len(new_events),
                )
            except (ValueError, RuntimeError) as e:
                sys.stderr.write(f"Error: {e}\n")
                return 1

    # 5. Resolve task hierarchies for the synced events and commit to cache
    if cache.enabled:
        cache.save()
        events_to_resolve = cache.get_events_in_range(req_start, req_end, tz=tz)
    else:
        events_to_resolve = new_events

    project_resolver = ProjectTreeResolver(projects)
    section_resolver = SectionResolver(
        token=token,
        preloaded_sections=sections,
        cache=cache if cache.enabled else None,
    )
    label_resolver = LabelResolver(preloaded_labels=labels)
    task_resolver = TaskHierarchyResolver(
        token=token,
        cache=cache if cache.enabled else None,
        tz=tz,
    )

    reporter.start_resolve(len(events_to_resolve))
    build_trace_records(
        events_to_resolve,
        project_resolver,
        task_resolver,
        section_resolver=section_resolver,
        label_resolver=label_resolver,
        progress_cb=lambda cur, tot: reporter.update_resolve(cur, tot),
    )
    reporter.finish_resolve(len(events_to_resolve))

    if cache.enabled:
        cache.save()

    reporter.print_text(
        f"\n{reporter.style.green('✔')} Sync complete. Cached: {cache.get_events_count()} events, "
        f"{len(cache.tasks)} tasks, {len(cache.projects)} projects."
    )
    return 0


def run_export(settings: Dict[str, Any], reporter: FancyProgressReporter, cache: Any) -> int:
    """Filter cached records and export to CSV or Markdown (offline-first)."""
    if not cache.enabled:
        sys.stderr.write("Error: Export requires local cache to be enabled.\n")
        return 1

    if cache.get_events_count() == 0:
        sys.stderr.write(
            "Error: Cache database is empty.\n"
            "Run 'todoist-trace sync' to retrieve activity logs from Todoist before exporting.\n"
        )
        return 1

    req_start = settings.get("start_date")
    req_end = settings.get("end_date")
    tz = settings.get("tz")
    events = cache.get_events_in_range(req_start, req_end, tz=tz)

    project_resolver = ProjectTreeResolver(cache.projects)
    section_resolver = SectionResolver(
        token=settings.get("token"),
        preloaded_sections=cache.sections,
        cache=cache,
    )
    label_resolver = LabelResolver(preloaded_labels=cache.labels)
    task_resolver = TaskHierarchyResolver(
        token=settings.get("token"),
        cache=cache,
        tz=tz,
    )

    reporter.start_resolve(len(events))
    all_records = build_trace_records(
        events,
        project_resolver,
        task_resolver,
        section_resolver=section_resolver,
        label_resolver=label_resolver,
        progress_cb=lambda cur, tot: reporter.update_resolve(cur, tot),
    )
    reporter.finish_resolve(len(all_records))

    # Apply category & date filters
    filtered_records = filter_records(
        all_records,
        category=settings["category"],
        start_date=settings["start_date"],
        end_date=settings["end_date"],
    )

    # Export records
    inc_labels = settings.get("include_labels", False)
    inc_desc = settings.get("include_descriptions", False)
    inc_prio = settings.get("include_priorities", False)
    inc_due = settings.get("include_due_dates", False)

    out_path = settings["output"]
    out_fmt = settings["format"]
    if out_fmt == "csv":
        export_csv(
            filtered_records,
            out_path,
            include_labels=inc_labels,
            include_descriptions=inc_desc,
            include_priorities=inc_prio,
            include_due_dates=inc_due,
        )
    else:
        export_markdown(
            filtered_records,
            out_path,
            style=settings["markdown_style"],
            task_style=settings["task_style"],
            include_labels=inc_labels,
            include_descriptions=inc_desc,
            include_priorities=inc_prio,
            include_due_dates=inc_due,
        )

    reporter.finish_export(
        output_path=out_path,
        matched_count=len(filtered_records),
        total_count=len(all_records),
        out_fmt=out_fmt,
        style_desc=settings["markdown_style"] if out_fmt != "csv" else "",
    )

    if not settings.get("quiet") and filtered_records:
        reporter.print_text("\nSample matched records:")
        for r in filtered_records[:3]:
            full_proj = f"{r['top_level_project']}" + (f" / {r['project_path']}" if r['project_path'] else "")
            sec_part = f" [{r['section']}]" if r.get('section') else ""
            extra_parts = []
            if inc_prio and r.get("priority"):
                extra_parts.append(f"[{r['priority']}]")
            if inc_labels and r.get("labels"):
                tags_str = ", ".join(f"@{l.lstrip('@')}" for l in r["labels"])
                extra_parts.append(f"[{tags_str}]")
            if inc_due and r.get("due_date"):
                extra_parts.append(f"[Due: {r['due_date']}]")
            meta_str = (" " + " ".join(extra_parts)) if extra_parts else ""
            reporter.print_text(f"  [{r['date']} {r['time']}] {full_proj}{sec_part} -> {r['task_path']}{meta_str}")

    return 0


def main(argv: Optional[list] = None) -> int:
    """Main CLI entrypoint supporting git-style subcommands."""
    args = parse_args(argv)
    try:
        settings = resolve_settings(args)
    except ValueError as e:
        sys.stderr.write(f"Error: {e}\n")
        return 1

    command = settings.get("command", "run")

    reporter = FancyProgressReporter(
        quiet=settings.get("quiet", False),
        no_color=settings.get("no_color", False),
        plain=settings.get("plain", False),
    )

    cache = create_cache(
        cache_file=settings.get("cache_file"),
        enabled=settings.get("cache_enabled", True),
    )

    if command == "status":
        return run_status(settings, reporter, cache)

    # For sync, export, and run: render sleek banner
    date_range_desc = f"{settings['start_date'] or 'genesis'} to {settings['end_date'] or 'now'}"
    if settings.get("start_date") and settings.get("end_date"):
        try:
            d1 = datetime.fromisoformat(settings["start_date"]).date()
            d2 = datetime.fromisoformat(settings["end_date"]).date()
            span_days = max(1, (d2 - d1).days + 1)
            date_range_desc += f" ({span_days} days)"
        except Exception:
            pass

    cache_mode = "SQLite" if settings.get("cache_file", "").endswith((".db", ".sqlite")) else "JSON"
    cache_desc = f"{settings.get('cache_file')} ({cache_mode})" if settings.get("cache_enabled") else "Disabled"

    fmt_desc = (
        f"{settings.get('format', 'csv').upper()} ({settings.get('markdown_style', 'nested')})"
        if command in ("export", "run")
        else f"SQLite Cache ({cache_mode})"
    )

    reporter.print_banner(
        date_range_desc=date_range_desc,
        timezone_desc=str(settings.get("timezone", "local")),
        category_desc=settings.get("category", "all") if command in ("export", "run") else "all",
        format_desc=fmt_desc,
        cache_desc=cache_desc,
    )

    if command == "sync":
        return run_sync(settings, reporter, cache)
    elif command == "export":
        return run_export(settings, reporter, cache)
    elif command == "run":
        rc = run_sync(settings, reporter, cache)
        if rc != 0:
            return rc
        return run_export(settings, reporter, cache)
    else:
        sys.stderr.write(f"Unknown command: {command}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
