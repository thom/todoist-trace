"""
Main orchestration and CLI entry point for todoist-trace.
Supports git-style subcommands: sync, export, status, and run.
"""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from .api import (
    fetch_archived_sections,
    fetch_completed_activities,
    fetch_completed_tasks_by_date,
    fetch_labels,
    fetch_projects,
    fetch_sections,
    fetch_tasks,
)
from .cache import (
    create_cache,
    normalize_end_date,
    normalize_start_date,
)
from .cli import parse_args, resolve_settings
from .exporters import export_csv, export_html, export_markdown
from .filters import filter_records
from .hierarchy import HierarchyStore
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

    last_sync = cache.get_last_sync() or "Never"
    events_count = cache.get_events_count()
    projects_count = len(cache.projects)
    sections_count = len(cache.sections)
    labels_count = len(cache.labels)
    tasks_count = len(cache.tasks)
    oldest_event, newest_event = cache.get_date_bounds()
    sync_ranges = cache.get_sync_ranges()

    resolved_count = cache.get_resolved_activities_count()

    reporter.print_text(reporter.style.bold("\nTodoist Trace Cache Status"))
    reporter.print_text(reporter.style.dim("─" * 32))
    reporter.print_text(f"  Location:     {cache_path}")
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
        reporter.print_text(f"  • Activities: {events_count} raw ({oldest_event} → {newest_event})")
    else:
        reporter.print_text(f"  • Activities: {events_count} raw")
    reporter.print_text(f"  • Resolved:   {resolved_count} materialized")

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


def preload_tasks(
    token: Optional[str],
    cache: Any,
    projects: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
    req_start: Optional[str] = None,
    req_end: Optional[str] = None,
    reporter: Optional[FancyProgressReporter] = None,
) -> None:
    """Preload active and completed tasks into cache in batches to resolve subtask hierarchies."""
    if not token or not cache or not getattr(cache, "enabled", False):
        return

    task_batch: Dict[str, Dict[str, Any]] = {}

    def _flush_batch() -> None:
        if task_batch:
            cache.save_tasks(dict(task_batch))
            task_batch.clear()

    # 1. Active tasks
    try:
        active_tasks = fetch_tasks(token)
        for t in active_tasks:
            task_batch[str(t["id"])] = {
                "content": t.get("content", ""),
                "parent_id": str(t["parent_id"]) if t.get("parent_id") else None,
                "description": t.get("description", ""),
                "priority": t.get("priority", 1),
                "labels": t.get("labels", []),
                "due": t.get("due"),
                "project_id": str(t.get("project_id", "")),
                "section_id": str(t.get("section_id", "")) if t.get("section_id") else None,
            }
        if len(task_batch) >= 500:
            _flush_batch()
    except Exception:
        pass

    # 2. Completed tasks across active projects
    if events:
        try:
            valid_dates = [ev.get("event_date", "") for ev in events if ev.get("event_date")]
            sync_start = req_start or (min(valid_dates) if valid_dates else "2020-01-01T00:00:00Z")
            sync_end = req_end or datetime.now(timezone.utc).isoformat()
            try:
                s_dt = datetime.fromisoformat(str(sync_start).replace("Z", "+00:00")) - timedelta(days=2)
                u_dt = datetime.fromisoformat(str(sync_end).replace("Z", "+00:00")) + timedelta(days=2)
                sync_start_str = s_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                sync_end_str = u_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                sync_start_str, sync_end_str = str(sync_start), str(sync_end)

            completed_bulk = fetch_completed_tasks_by_date(token, sync_start_str, sync_end_str)
            for t in completed_bulk:
                task_batch[str(t["id"])] = {
                    "content": t.get("content", ""),
                    "parent_id": str(t["parent_id"]) if t.get("parent_id") else None,
                    "description": t.get("description", ""),
                    "priority": t.get("priority", 1),
                    "labels": t.get("labels", []),
                    "due": t.get("due"),
                    "project_id": str(t.get("project_id", "")),
                    "section_id": str(t.get("section_id", "")) if t.get("section_id") else None,
                }
            if len(task_batch) >= 500:
                _flush_batch()
        except Exception:
            pass

        # 3. Completed tasks across archived projects
        proj_date_spans: Dict[str, List[str]] = {}
        for ev in events:
            pid = str(ev.get("parent_project_id", ""))
            ed = ev.get("event_date")
            if pid and ed:
                if pid not in proj_date_spans:
                    proj_date_spans[pid] = [ed, ed]
                else:
                    if ed < proj_date_spans[pid][0]:
                        proj_date_spans[pid][0] = ed
                    if ed > proj_date_spans[pid][1]:
                        proj_date_spans[pid][1] = ed

        archived_pids = [
            p for p in proj_date_spans
            if any(str(prj.get("id")) == p and prj.get("is_archived") for prj in projects)
        ]

        pids_to_fetch = []
        for apid in archived_pids:
            ev_obj_ids = {
                str(ev.get("object_id"))
                for ev in events
                if str(ev.get("parent_project_id", "")) == apid and ev.get("object_id")
            }
            if ev_obj_ids and hasattr(cache, "tasks") and all(oid in cache.tasks for oid in ev_obj_ids):
                continue
            pids_to_fetch.append(apid)

        if reporter and pids_to_fetch:
            reporter.print_text(
                f"  → Preloading tasks across {len(pids_to_fetch)} archived projects..."
            )

        for apid in pids_to_fetch:
            try:
                span = proj_date_spans[apid]
                try:
                    s_dt = datetime.fromisoformat(span[0].replace("Z", "+00:00")) - timedelta(days=2)
                    u_dt = datetime.fromisoformat(span[1].replace("Z", "+00:00")) + timedelta(days=2)
                    since_str = s_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    until_str = u_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    since_str, until_str = span[0], span[1]

                proj_completed = fetch_completed_tasks_by_date(token, since_str, until_str, project_id=apid)
                for t in proj_completed:
                    task_batch[str(t["id"])] = {
                        "content": t.get("content", ""),
                        "parent_id": str(t["parent_id"]) if t.get("parent_id") else None,
                        "description": t.get("description", ""),
                        "priority": t.get("priority", 1),
                        "labels": t.get("labels", []),
                        "due": t.get("due"),
                        "project_id": str(t.get("project_id", "")),
                        "section_id": str(t.get("section_id", "")) if t.get("section_id") else None,
                    }
                if len(task_batch) >= 500:
                    _flush_batch()
            except Exception:
                continue

    _flush_batch()


def preload_archived_sections(
    token: Optional[str],
    cache: Any,
    events: List[Dict[str, Any]],
) -> None:
    """Preload archived sections for projects referenced by activity events."""
    if not token or not cache or not getattr(cache, "enabled", False) or not hasattr(cache, "sections"):
        return

    pids_with_sections = set()
    for ev in events:
        pid = str(ev.get("parent_project_id", ""))
        ed = ev.get("extra_data")
        if isinstance(ed, str):
            if "section_id" in ed:
                pids_with_sections.add(pid)
        elif isinstance(ed, dict):
            if ed.get("section_id"):
                pids_with_sections.add(pid)

    for pid in pids_with_sections:
        if not pid:
            continue
        try:
            arch_secs = fetch_archived_sections(token, pid)
            for s in arch_secs:
                if s.get("id"):
                    cache.sections[str(s["id"])] = s
        except Exception:
            pass


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

    # 1. Fetch projects
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
    try:
        sections_list = fetch_sections(token)
        if cache.enabled:
            cache.sections = sections_list
        sections = cache.sections if cache.enabled else {s["id"]: s for s in sections_list if s.get("id")}
    except Exception:
        sections = cache.sections if (cache.enabled and hasattr(cache, "sections")) else {}

    # 3. Preload labels
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
    if refresh and cache.enabled:
        cache.clear_resolved_activities()

    if cache.enabled:
        cache.save()
        if not refresh and not new_events and cache.get_resolved_activities_count() >= cache.get_events_count():
            reporter.print_text(
                f"\n{reporter.style.green('✔')} Sync complete. Cache is already up to date: "
                f"{cache.get_events_count()} events, {len(cache.tasks)} tasks, "
                f"{len(cache.projects)} projects, {cache.get_resolved_activities_count()} resolved activities."
            )
            return 0

        if not refresh and new_events and cache.get_resolved_activities_count() > 0:
            events_to_resolve = new_events
        else:
            events_to_resolve = cache.get_events_in_range(req_start, req_end, tz=tz)
    else:
        events_to_resolve = new_events

    # Preload active and completed tasks to resolve subtask hierarchies
    preload_tasks(
        token=token,
        cache=cache,
        projects=projects,
        events=events_to_resolve,
        req_start=req_start,
        req_end=req_end,
        reporter=reporter,
    )
    preload_archived_sections(
        token=token,
        cache=cache,
        events=events_to_resolve,
    )

    hierarchy_store = getattr(cache, "hierarchy_store", None) if cache else None
    project_resolver = ProjectTreeResolver(projects, hierarchy_store=hierarchy_store)
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
    resolved_records = build_trace_records(
        events_to_resolve,
        project_resolver,
        task_resolver,
        section_resolver=section_resolver,
        label_resolver=label_resolver,
        progress_cb=lambda cur, tot: reporter.update_resolve(cur, tot),
    )
    reporter.finish_resolve(len(events_to_resolve))

    if cache.enabled:
        cache.save_resolved_activities(resolved_records)
        cache.save()

    reporter.print_text(
        f"\n{reporter.style.green('✔')} Sync complete. Cached: {cache.get_events_count()} events, "
        f"{len(cache.tasks)} tasks, {len(cache.projects)} projects, "
        f"{cache.get_resolved_activities_count()} resolved activities."
    )
    return 0


def run_export(settings: Dict[str, Any], reporter: FancyProgressReporter, cache: Any) -> int:
    """Filter cached records and export to CSV, Markdown, or HTML (offline-first)."""
    if not cache.enabled:
        sys.stderr.write("Error: Export requires local cache to be enabled.\n")
        return 1

    if cache.get_events_count() == 0:
        sys.stderr.write(
            "Error: Cache database is empty.\n"
            "Run 'todoist-trace sync' to retrieve activity logs from Todoist before exporting.\n"
        )
        return 1

    tz = settings.get("tz")
    refresh = settings.get("refresh", False)

    # Self-healing: materialize resolved activities if cache table is empty, missing events, or refresh requested
    if refresh or cache.get_resolved_activities_count() < cache.get_events_count():
        if refresh:
            cache.clear_resolved_activities()
        token = settings.get("token")
        if token and cache.enabled and (refresh or len(cache.tasks) == 0):
            preload_tasks(token, cache, cache.projects, cache.get_all_events(), reporter=reporter)
            preload_archived_sections(token, cache, cache.get_all_events())

        reporter.print_text("Materializing resolved activities in cache for fast exports...")
        all_events = cache.get_all_events()
        hierarchy_store = getattr(cache, "hierarchy_store", None) if cache else None
        project_resolver = ProjectTreeResolver(cache.projects, hierarchy_store=hierarchy_store)
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

        reporter.start_resolve(len(all_events))
        resolved_records = build_trace_records(
            all_events,
            project_resolver,
            task_resolver,
            section_resolver=section_resolver,
            label_resolver=label_resolver,
            progress_cb=lambda cur, tot: reporter.update_resolve(cur, tot),
        )
        reporter.finish_resolve(len(all_events))
        cache.save_resolved_activities(resolved_records)
        cache.save()

    # Fast indexed read directly from resolved_activities with SQL filter pushdown
    filtered_records = cache.get_resolved_activities(
        category=settings.get("category", "all"),
        start_date=settings.get("start_date"),
        end_date=settings.get("end_date"),
        categories_config=settings.get("categories"),
    )
    total_count = cache.get_resolved_activities_count()

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
    elif out_fmt == "html":
        export_html(
            filtered_records,
            out_path,
            include_labels=inc_labels,
            include_descriptions=inc_desc,
            include_priorities=inc_prio,
            include_due_dates=inc_due,
            categories_config=settings.get("categories"),
        )
    else:
        export_markdown(
            filtered_records,
            out_path,
            include_labels=inc_labels,
            include_descriptions=inc_desc,
            include_priorities=inc_prio,
            include_due_dates=inc_due,
        )

    reporter.finish_export(
        output_path=out_path,
        matched_count=len(filtered_records),
        total_count=total_count,
        out_fmt=out_fmt,
    )

    if not settings.get("quiet") and filtered_records:
        reporter.print_text("\nSample matched records:")
        for r in filtered_records[:3]:
            full_proj = f"{r['top_level_project']}" + (f" / {r['project_path']}" if r['project_path'] else "")
            sec_part = f" [{r['section']}]" if r.get('section') else ""
            extra_parts = []
            if inc_prio and r.get("priority") and r.get("priority", "").lower() != "p4":
                extra_parts.append(f"[{r['priority']}]")
            if inc_labels and r.get("labels"):
                tags_str = ", ".join(f"@{l.lstrip('@')}" for l in r["labels"])
                extra_parts.append(f"[{tags_str}]")
            if inc_due and r.get("due_date"):
                extra_parts.append(f"[Due: {r['due_date']}]")
            meta_str = (" " + " ".join(extra_parts)) if extra_parts else ""
            reporter.print_text(f"  [{r['date']} {r['time']}] {full_proj}{sec_part} -> {r['task_path']}{meta_str}")

    return 0


def run_hierarchy(settings: Dict[str, Any], reporter: FancyProgressReporter, cache: Any) -> int:
    """Inspect or update persistent project hierarchy mappings."""
    hierarchy_store = getattr(cache, "hierarchy_store", None)
    if not hierarchy_store:
        hierarchy_store = HierarchyStore()

    # Seed the store if empty and cache has projects
    if not hierarchy_store.projects and cache and getattr(cache, "projects", None):
        hierarchy_store.record_batch(cache.projects)

    # Build known_projects combining cache and hierarchy_store
    known_projects: Dict[str, Dict[str, Any]] = {}
    if cache and getattr(cache, "projects", None):
        for p in cache.projects:
            pid = str(p.get("id"))
            if pid:
                known_projects[pid] = dict(p)

    for pid, hp in hierarchy_store.projects.items():
        if pid not in known_projects:
            known_projects[pid] = {
                "id": pid,
                "name": hp.get("name", "Unnamed"),
                "parent_id": hp.get("parent_id"),
                "is_archived": hp.get("is_archived", False),
                "is_deleted": hp.get("is_deleted", False),
            }
        else:
            if hp.get("parent_id"):
                known_projects[pid]["parent_id"] = hp["parent_id"]

    all_projects = list(known_projects.values()) if known_projects else list(hierarchy_store.projects.values())

    action = settings.get("hierarchy_action", "list")

    if action == "list":
        unassigned_only = settings.get("hierarchy_unassigned", False)
        show_all = settings.get("hierarchy_all", False)

        if unassigned_only:
            filtered = [
                p for p in all_projects
                if p.get("is_archived") and not hierarchy_store.get_parent_id(p["id"]) and p["id"] not in hierarchy_store.projects
            ]
            title = "Unassigned Archived Projects (not in hierarchy.json)"
        elif show_all:
            filtered = all_projects
            title = "All Project Hierarchy Mappings"
        else:
            # Default: show archived projects
            filtered = [p for p in all_projects if p.get("is_archived")]
            title = "Archived Project Hierarchy Mappings"

        filtered.sort(key=lambda p: p.get("name", "").lower())

        reporter.print_text(reporter.style.bold(f"\n{title}"))
        reporter.print_text(reporter.style.dim("─" * 78))

        if not filtered:
            if unassigned_only:
                reporter.print_text("  All archived projects are listed in hierarchy.json!\n")
            else:
                reporter.print_text("  No projects found.\n")
            return 0

        reporter.print_text(
            f"  {reporter.style.dim('PROJECT ID'):<18}  {reporter.style.dim('STATUS'):<10}  {reporter.style.dim('NAME'):<30}  {reporter.style.dim('PARENT / PATH')}"
        )
        reporter.print_text(reporter.style.dim("  " + "─" * 76))

        unassigned_count = 0
        for p in filtered:
            pid = p["id"]
            name = p.get("name", "Unnamed")
            is_arch = p.get("is_archived", False)
            parent_id = hierarchy_store.get_parent_id(pid) or p.get("parent_id")
            in_store = pid in hierarchy_store.projects

            status_str = reporter.style.dim("Archived") if is_arch else reporter.style.cyan("Active")

            if parent_id:
                top, path, levels = hierarchy_store.resolve_project_chain(pid)
                full_chain = " › ".join([top] + levels[:-1]) if len(levels) > 0 else top
                if not full_chain:
                    full_chain = top
                path_str = reporter.style.green(f"↳ {full_chain}")
            else:
                if is_arch:
                    if in_store:
                        path_str = reporter.style.cyan("(Root in hierarchy.json)")
                    else:
                        unassigned_count += 1
                        path_str = reporter.style.yellow("(Unassigned -> archives)")
                else:
                    path_str = reporter.style.dim("(Root Project)")

            reporter.print_text(f"  {pid:<18}  {status_str:<10}  {name[:30]:<30}  {path_str}")

        reporter.print_text(reporter.style.dim("  " + "─" * 76))
        summary = f"  Total: {len(filtered)} project(s)"
        if unassigned_count > 0:
            summary += f" ({unassigned_count} unassigned)"
        reporter.print_text(summary)
        if unassigned_count > 0:
            reporter.print_text(
                f"\n  {reporter.style.dim('Tip: Assign a parent with:')}\n"
                f"  todoist-trace hierarchy set <project> <parent>\n"
            )
        else:
            reporter.print_text("")
        return 0

    elif action == "set":
        target_arg = settings.get("hierarchy_project")
        parent_arg = settings.get("hierarchy_parent")

        if not target_arg or not parent_arg:
            sys.stderr.write("Error: 'hierarchy set' requires both <project> and <parent> arguments.\n")
            return 1

        # 1. Resolve target project
        target_proj = hierarchy_store.get_project(target_arg)
        if not target_proj:
            candidates = hierarchy_store.find_projects_by_name(target_arg)
            if not candidates and known_projects:
                target_clean = target_arg.strip().lower()
                candidates = [p for p in known_projects.values() if p.get("name", "").strip().lower() == target_clean or p.get("id") == target_arg]
            if len(candidates) == 1:
                target_proj = candidates[0]
            elif len(candidates) > 1:
                sys.stderr.write(f"Error: Ambiguous project name '{target_arg}'. Matches multiple projects:\n")
                for c in candidates:
                    sys.stderr.write(f"  - ID: {c['id']}, Name: {c['name']}\n")
                sys.stderr.write("Please specify by project ID instead.\n")
                return 1
            else:
                sys.stderr.write(f"Error: Project '{target_arg}' not found in hierarchy store or cache.\n")
                return 1

        target_id = target_proj["id"]
        target_name = target_proj.get("name", "Unnamed")
        target_is_archived = target_proj.get("is_archived", True)

        # 2. Resolve parent project
        if parent_arg.lower() in ("root", "none", "null"):
            parent_id = None
            parent_name = "Root"
        else:
            parent_proj = hierarchy_store.get_project(parent_arg)
            if not parent_proj:
                path_resolved_id = hierarchy_store.resolve_path_to_id(parent_arg)
                if path_resolved_id:
                    parent_proj = hierarchy_store.get_project(path_resolved_id)
                else:
                    candidates = hierarchy_store.find_projects_by_name(parent_arg)
                    if not candidates and known_projects:
                        p_clean = parent_arg.strip().lower()
                        candidates = [p for p in known_projects.values() if p.get("name", "").strip().lower() == p_clean or p.get("id") == parent_arg]
                    if len(candidates) == 1:
                        parent_proj = candidates[0]
                    elif len(candidates) > 1:
                        sys.stderr.write(f"Error: Ambiguous parent name '{parent_arg}'. Matches multiple projects:\n")
                        for c in candidates:
                            sys.stderr.write(f"  - ID: {c['id']}, Name: {c['name']}\n")
                        sys.stderr.write("Please specify the full path (e.g. 'work / operations') or project ID.\n")
                        return 1

            if not parent_proj:
                sys.stderr.write(f"Error: Parent project or path '{parent_arg}' not found.\n")
                return 1

            parent_id = parent_proj["id"]
            parent_name = parent_proj.get("name", "Unnamed")

        # 3. Apply assignment
        success = hierarchy_store.set_parent(
            target_id, parent_id, name=target_name, is_archived=target_is_archived
        )
        if not success:
            sys.stderr.write(f"Error: Cannot set parent. Circular reference detected between '{target_name}' and '{parent_name}'.\n")
            return 1

        # 4. Synchronize with cache if active
        if cache and cache.enabled and hasattr(cache, "conn") and cache.conn:
            with cache.conn:
                cache.conn.execute(
                    "UPDATE projects SET parent_id = ? WHERE id = ?",
                    (parent_id, target_id),
                )
            cache.clear_resolved_activities()
            if hasattr(cache, "_load_metadata"):
                cache._load_metadata()

        top, path, levels = hierarchy_store.resolve_project_chain(target_id)
        full_chain = " › ".join([top] + levels) if levels else top

        reporter.print_text(
            f"\n{reporter.style.green('✔')} Successfully assigned project '{reporter.style.bold(target_name)}' "
            f"to parent '{reporter.style.bold(parent_name)}'."
        )
        reporter.print_text(f"  Resolved hierarchy path: {reporter.style.bold(full_chain)}\n")
        return 0

    else:
        sys.stderr.write(f"Error: Unknown hierarchy action: {action}\n")
        return 1


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
        categories_config=settings.get("categories"),
    )

    if command == "status":
        return run_status(settings, reporter, cache)
    elif command == "hierarchy":
        return run_hierarchy(settings, reporter, cache)

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

    cache_desc = str(settings.get("cache_file")) if settings.get("cache_enabled") else "Disabled"

    fmt_desc = None
    cat_desc = None
    if command in ("export", "run"):
        cat_desc = settings.get("category", "all")
        if settings.get("format") == "markdown":
            fmt_desc = "MARKDOWN"
        elif settings.get("format") == "html":
            fmt_desc = "HTML (Interactive Dashboard)"
        else:
            fmt_desc = "CSV"

    reporter.print_banner(
        date_range_desc=date_range_desc,
        timezone_desc=str(settings.get("timezone", "local")),
        category_desc=cat_desc,
        format_desc=fmt_desc,
        cache_desc=cache_desc,
    )

    if command == "sync":
        reporter.set_phase_context(3)
        return run_sync(settings, reporter, cache)
    elif command == "export":
        reporter.set_phase_context(1)
        return run_export(settings, reporter, cache)
    elif command == "run":
        reporter.set_phase_context(4)
        reporter.pipeline_mode = True
        rc = run_sync(settings, reporter, cache)
        if rc != 0:
            return rc
        return run_export(settings, reporter, cache)
    else:
        sys.stderr.write(f"Unknown command: {command}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
