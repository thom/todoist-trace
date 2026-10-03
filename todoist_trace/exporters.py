"""
Exporters for todoist-trace records.
Supports RFC 4180 CSV export and hierarchical Markdown export (nested or flat).
"""

import csv
import io
from pathlib import Path
from typing import Any, Dict, List


def generate_csv(
    records: List[Dict[str, Any]],
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> str:
    """
    Generate CSV formatted text for trace records according to RFC 4180.
    Headers: top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id
    Optional metadata columns: labels, description, priority, due_date, due_variance
    """
    output = io.StringIO()
    fieldnames = [
        "top_level_project",
        "project_path",
        "section",
        "date",
        "time",
        "task_path",
        "parent_task_id",
        "project_id",
        "event_id",
    ]
    if include_labels:
        fieldnames.append("labels")
    if include_descriptions:
        fieldnames.append("description")
    if include_priorities:
        fieldnames.append("priority")
    if include_due_dates:
        fieldnames.extend(["due_date", "due_variance"])

    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(fieldnames)
    for r in records:
        row = [
            r.get("top_level_project", ""),
            r.get("project_path", ""),
            r.get("section", ""),
            r.get("date", ""),
            r.get("time", ""),
            r.get("task_path", ""),
            r.get("parent_task_id", ""),
            r.get("project_id", ""),
            r.get("event_id", ""),
        ]
        if include_labels:
            raw_lbls = r.get("labels") or []
            row.append(",".join(raw_lbls) if isinstance(raw_lbls, list) else str(raw_lbls))
        if include_descriptions:
            row.append(r.get("description", "") or "")
        if include_priorities:
            row.append(r.get("priority", "p4") or "p4")
        if include_due_dates:
            row.append(r.get("due_date", "") or "")
            row.append(r.get("due_variance", "") or "")

        writer.writerow(row)
    return output.getvalue()


def export_csv(
    records: List[Dict[str, Any]],
    output_path: str,
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> None:
    """Export trace records to a CSV file."""
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_csv(
        records,
        include_labels=include_labels,
        include_descriptions=include_descriptions,
        include_priorities=include_priorities,
        include_due_dates=include_due_dates,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _format_task_metadata(
    r: Dict[str, Any],
    include_labels: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> str:
    """Format inline badges for priority, labels, and due date/variance."""
    parts = []
    if include_priorities:
        prio = r.get("priority")
        if prio:
            parts.append(f"[{prio}]")
    if include_labels:
        lbls = r.get("labels") or []
        if lbls:
            tags = [f"@{lbl.lstrip('@')}" for lbl in lbls]
            parts.append(f"[{', '.join(tags)}]")
    if include_due_dates:
        due = r.get("due_date")
        if due:
            variance = r.get("due_variance")
            done = r.get("date")
            if done and variance:
                parts.append(f"[Due: {due}, Done: {done} ({variance})]")
            elif done:
                parts.append(f"[Due: {due}, Done: {done}]")
            elif variance:
                parts.append(f"[Due: {due} ({variance})]")
            else:
                parts.append(f"[Due: {due}]")

    return (" " + " ".join(parts)) if parts else ""


def _format_description_lines(desc: str, indent: str) -> List[str]:
    """Format multiline task description as indented markdown blockquote lines."""
    if not desc:
        return []
    lines = desc.splitlines()
    desc_lines = []
    for line in lines:
        line_stripped = line.rstrip()
        if line_stripped:
            desc_lines.append(f"{indent}  > {line_stripped}")
        else:
            desc_lines.append(f"{indent}  >")
    return desc_lines


def format_task_bullets(
    records_in_group: List[Dict[str, Any]],
    task_style: str = "nested",
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> List[str]:
    """Format tasks either as nested bullet hierarchy or flat slash paths with optional metadata."""
    if task_style == "flat":
        lines = []
        for r in records_in_group:
            meta = _format_task_metadata(
                r,
                include_labels=include_labels,
                include_priorities=include_priorities,
                include_due_dates=include_due_dates,
            )
            lines.append(f"- {r.get('task_path', '')}{meta}")
            if include_descriptions and r.get("description"):
                lines.extend(_format_description_lines(r["description"], indent=""))
        return lines

    class TaskNode:
        def __init__(self, title: str):
            self.title = title
            self.record: Optional[Dict[str, Any]] = None
            self.children: Dict[str, "TaskNode"] = {}

    root_tasks: Dict[str, TaskNode] = {}
    for r in records_in_group:
        levels = r.get("task_levels")
        if not levels:
            levels = [r.get("task_path", "")]
        curr = root_tasks
        for lvl in levels[:-1]:
            if lvl not in curr:
                curr[lvl] = TaskNode(lvl)
            curr = curr[lvl].children
        leaf_title = levels[-1]
        if leaf_title not in curr:
            curr[leaf_title] = TaskNode(leaf_title)
        curr[leaf_title].record = r

    def render_tree(nodes: Dict[str, TaskNode], depth: int = 0) -> List[str]:
        res = []
        indent = "  " * depth
        for node in nodes.values():
            meta = ""
            if node.record:
                meta = _format_task_metadata(
                    node.record,
                    include_labels=include_labels,
                    include_priorities=include_priorities,
                    include_due_dates=include_due_dates,
                )
            res.append(f"{indent}- {node.title}{meta}")
            if include_descriptions and node.record and node.record.get("description"):
                res.extend(_format_description_lines(node.record["description"], indent=indent))
            if node.children:
                res.extend(render_tree(node.children, depth + 1))
        return res

    return render_tree(root_tasks)


def format_records_with_sections(
    records: List[Dict[str, Any]],
    parent_h_level: int,
    task_style: str = "nested",
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> List[str]:
    """
    Format records, grouping by section if any records have a section.
    Unsectioned tasks appear first without a section header.
    Sectioned tasks appear under header with level min(parent_h_level + 1, 6).
    """
    if not records:
        return []

    has_sections = any(bool(r.get("section")) for r in records)
    if not has_sections:
        return format_task_bullets(
            records,
            task_style=task_style,
            include_labels=include_labels,
            include_descriptions=include_descriptions,
            include_priorities=include_priorities,
            include_due_dates=include_due_dates,
        )

    res: List[str] = []
    unsectioned: List[Dict[str, Any]] = []
    sections_map: Dict[str, List[Dict[str, Any]]] = {}

    for r in records:
        sec = r.get("section")
        if not sec:
            unsectioned.append(r)
        else:
            if sec not in sections_map:
                sections_map[sec] = []
            sections_map[sec].append(r)

    if unsectioned:
        res.extend(format_task_bullets(
            unsectioned,
            task_style=task_style,
            include_labels=include_labels,
            include_descriptions=include_descriptions,
            include_priorities=include_priorities,
            include_due_dates=include_due_dates,
        ))

    sec_h_level = min(parent_h_level + 1, 6)
    hashes = "#" * sec_h_level

    for sec_name, sec_records in sections_map.items():
        if res and res[-1] != "":
            res.append("")
        res.append(f"{hashes} {sec_name}")
        res.extend(format_task_bullets(
            sec_records,
            task_style=task_style,
            include_labels=include_labels,
            include_descriptions=include_descriptions,
            include_priorities=include_priorities,
            include_due_dates=include_due_dates,
        ))

    return res


def generate_markdown(
    records: List[Dict[str, Any]],
    style: str = "nested",
    task_style: str = "nested",
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> str:
    """
    Format trace records into Markdown grouped by date and project hierarchy.
    style: 'nested' (progressive headings) or 'flat' (slash-separated heading)
    task_style: 'nested' (bullet hierarchy) or 'flat' (slash-separated tasks)
    """
    if not records:
        return ""

    # Sort records descending by date, then time
    sorted_records = sorted(
        records,
        key=lambda r: (r.get("date") or "", r.get("time") or ""),
        reverse=True,
    )

    # Group by date -> top_level_project
    dates_map: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for r in sorted_records:
        date_str = r.get("date") or "Undated"
        top_proj = r.get("top_level_project") or "Other"
        if date_str not in dates_map:
            dates_map[date_str] = {}
        if top_proj not in dates_map[date_str]:
            dates_map[date_str][top_proj] = []
        dates_map[date_str][top_proj].append(r)

    lines: List[str] = []

    for date_str, top_projects in dates_map.items():
        lines.append(f"## {date_str}")
        lines.append("")

        for top_proj, proj_records in top_projects.items():
            lines.append(f"### {top_proj}")

            if style == "flat":
                # Group by project_path
                paths_map: Dict[str, List[Dict[str, Any]]] = {}
                for pr in proj_records:
                    p_path = pr.get("project_path") or ""
                    if p_path not in paths_map:
                        paths_map[p_path] = []
                    paths_map[p_path].append(pr)

                # 1. Direct tasks under top_level_project (empty project_path)
                if "" in paths_map:
                    lines.extend(format_records_with_sections(
                        paths_map[""],
                        parent_h_level=3,
                        task_style=task_style,
                        include_labels=include_labels,
                        include_descriptions=include_descriptions,
                        include_priorities=include_priorities,
                        include_due_dates=include_due_dates,
                    ))
                    lines.append("")

                # 2. Sub-projects
                for p_path, recs in paths_map.items():
                    if p_path == "":
                        continue
                    if "" not in paths_map and len(lines) > 0 and lines[-1] == f"### {top_proj}":
                        lines.append("")
                    lines.append(f"#### {p_path}")
                    lines.extend(format_records_with_sections(
                        recs,
                        parent_h_level=4,
                        task_style=task_style,
                        include_labels=include_labels,
                        include_descriptions=include_descriptions,
                        include_priorities=include_priorities,
                        include_due_dates=include_due_dates,
                    ))
                    lines.append("")

            else:  # nested style
                class Node:
                    def __init__(self, name: str = "", depth: int = 0):
                        self.name = name
                        self.depth = depth
                        self.records: List[Dict[str, Any]] = []
                        self.children: Dict[str, "Node"] = {}

                root_node = Node(name=top_proj, depth=0)
                for pr in proj_records:
                    levels = pr.get("project_levels") or []
                    curr = root_node
                    for idx, level_name in enumerate(levels):
                        if level_name not in curr.children:
                            curr.children[level_name] = Node(name=level_name, depth=idx + 1)
                        curr = curr.children[level_name]
                    curr.records.append(pr)

                def render_nested_node(node: Node) -> None:
                    if node.depth == 0 and not node.records and node.children:
                        lines.append("")

                    if node.depth > 0:
                        h_level = min(3 + node.depth, 6)
                        hashes = "#" * h_level
                        lines.append(f"{hashes} {node.name}")
                    else:
                        h_level = 3

                    if node.records:
                        lines.extend(format_records_with_sections(
                            node.records,
                            parent_h_level=h_level,
                            task_style=task_style,
                            include_labels=include_labels,
                            include_descriptions=include_descriptions,
                            include_priorities=include_priorities,
                            include_due_dates=include_due_dates,
                        ))
                        lines.append("")
                    elif node.depth > 0 and node.children:
                        lines.append("")

                    for child in node.children.values():
                        render_nested_node(child)

                render_nested_node(root_node)

    return "\n".join(lines).rstrip() + "\n"


def export_markdown(
    records: List[Dict[str, Any]],
    output_path: str,
    style: str = "nested",
    task_style: str = "nested",
    include_labels: bool = False,
    include_descriptions: bool = False,
    include_priorities: bool = False,
    include_due_dates: bool = False,
) -> None:
    """Export trace records to a Markdown file."""
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_markdown(
        records,
        style=style,
        task_style=task_style,
        include_labels=include_labels,
        include_descriptions=include_descriptions,
        include_priorities=include_priorities,
        include_due_dates=include_due_dates,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
