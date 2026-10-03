"""
Main orchestration and CLI entry point for todoist-trace.
"""

import sys
from datetime import datetime, timezone
from typing import Optional

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

    reporter = FancyProgressReporter(
        quiet=settings.get("quiet", False),
        no_color=settings.get("no_color", False),
        plain=settings.get("plain", False),
    )

    # Render sleek terminal banner
    date_range_desc = f"{settings['start_date'] or 'genesis'} to {settings['end_date'] or 'now'}"
    if settings.get("start_date") and settings.get("end_date"):
        try:
            d1 = datetime.fromisoformat(settings["start_date"]).date()
            d2 = datetime.fromisoformat(settings["end_date"]).date()
            span_days = max(1, (d2 - d1).days + 1)
            date_range_desc += f" ({span_days} days)"
        except Exception:
            pass

    cache_mode = "SQLite" if settings.get("cache_file", "").endswith(".db") else "JSON"
    cache_desc = f"{settings.get('cache_file')} ({cache_mode})" if settings.get("cache_enabled") else "Disabled"

    reporter.print_banner(
        date_range_desc=date_range_desc,
        timezone_desc=str(settings.get("timezone", "local")),
        category_desc=settings.get("category", "all"),
        format_desc=f"{settings.get('format', 'csv').upper()} ({settings.get('markdown_style', 'nested')})",
        cache_desc=cache_desc,
    )

    # 1. Initialize Cache
    cache = create_cache(
        cache_file=settings.get("cache_file"),
        enabled=settings.get("cache_enabled", True),
    )

    # 2. Fetch or load projects
    if cache.enabled and cache.projects and not settings.get("refresh"):
        reporter.start_projects(cached=True, count=len(cache.projects))
        projects = cache.projects
    else:
        reporter.start_projects(cached=False)
        try:
            projects = fetch_projects(
                settings["token"],
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

    # Preload sections
    if cache.enabled and hasattr(cache, "sections") and cache.sections and not settings.get("refresh"):
        sections = cache.sections
    else:
        try:
            sections_list = fetch_sections(settings["token"])
            if cache.enabled:
                cache.sections = sections_list
            sections = cache.sections if cache.enabled else {s["id"]: s for s in sections_list if s.get("id")}
        except Exception:
            sections = cache.sections if (cache.enabled and hasattr(cache, "sections")) else {}

    # Preload labels
    if cache.enabled and hasattr(cache, "labels") and cache.labels and not settings.get("refresh"):
        labels = cache.labels
    else:
        try:
            labels_list = fetch_labels(settings["token"])
            if cache.enabled:
                cache.labels = labels_list
            labels = cache.labels if cache.enabled else {l["id"]: l for l in labels_list if l.get("id")}
        except Exception:
            labels = cache.labels if (cache.enabled and hasattr(cache, "labels")) else {}

    project_resolver = ProjectTreeResolver(projects)
    section_resolver = SectionResolver(
        token=settings["token"],
        preloaded_sections=sections,
        cache=cache if cache.enabled else None,
    )
    label_resolver = LabelResolver(preloaded_labels=labels)

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
        reporter.start_sync(None, None, total_cache_count=cache.get_events_count(), fully_cached=True)
    else:
        for gap_start, gap_end in missing_ranges:
            reporter.start_sync(gap_start, gap_end, total_cache_count=cache.get_events_count(), fully_cached=False)
            try:
                fetched = fetch_completed_activities(
                    settings["token"],
                    date_from=gap_start,
                    date_to=gap_end,
                    progress_cb=lambda count, oldest: reporter.update_sync(count, oldest),
                )
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
                reporter.finish_sync(
                    len(fetched),
                    cache.get_events_count() if cache.enabled else len(new_events),
                )
            except (ValueError, RuntimeError) as e:
                sys.stderr.write(f"Error: {e}\n")
                return 1

    # Load matching events from cache
    if cache.enabled:
        cache.save()
        all_events = cache.get_events_in_range(req_start, req_end, tz=tz)
    else:
        all_events = new_events

    # 4. Resolve tasks and sections
    task_resolver = TaskHierarchyResolver(settings["token"], cache=cache if cache.enabled else None, tz=tz)
    reporter.start_resolve(len(all_events))
    all_records = build_trace_records(
        all_events,
        project_resolver,
        task_resolver,
        section_resolver=section_resolver,
        label_resolver=label_resolver,
        progress_cb=lambda cur, tot: reporter.update_resolve(cur, tot),
    )
    reporter.finish_resolve(len(all_records))

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

    # 6. Export records
    inc_labels = settings.get("include_labels", False)
    inc_desc = settings.get("include_descriptions", False)
    out_path = settings["output"]
    out_fmt = settings["format"]
    if out_fmt == "csv":
        export_csv(filtered_records, out_path, include_labels=inc_labels, include_descriptions=inc_desc)
    else:
        export_markdown(
            filtered_records,
            out_path,
            style=settings["markdown_style"],
            task_style=settings["task_style"],
            include_labels=inc_labels,
            include_descriptions=inc_desc,
        )

    reporter.finish_export(
        output_path=out_path,
        matched_count=len(filtered_records),
        total_count=len(all_records),
        out_fmt=out_fmt,
        style_desc=settings["markdown_style"] if out_fmt != "csv" else "",
    )

    # Show a few sample filtered records (if not quiet)
    if not settings.get("quiet") and filtered_records:
        reporter.print_text("\nSample matched records:")
        for r in filtered_records[:3]:
            full_proj = f"{r['top_level_project']}" + (f" / {r['project_path']}" if r['project_path'] else "")
            sec_part = f" [{r['section']}]" if r.get('section') else ""
            lbl_part = ""
            if inc_labels and r.get("labels"):
                tags_str = ", ".join(f"@{l.lstrip('@')}" for l in r["labels"])
                lbl_part = f" [{tags_str}]"
            reporter.print_text(f"  [{r['date']} {r['time']}] {full_proj}{sec_part} -> {r['task_path']}{lbl_part}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
