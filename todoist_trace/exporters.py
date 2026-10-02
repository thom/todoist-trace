"""
Exporters for todoist-trace records.
Supports RFC 4180 CSV export and hierarchical Markdown export (nested or flat).
"""

import csv
import io
from pathlib import Path
from typing import Any, Dict, List


def generate_csv(records: List[Dict[str, Any]]) -> str:
    """
    Generate CSV formatted text for trace records according to RFC 4180.
    Headers: top_level_project,project_path,date,time,task_path,parent_task_id,project_id,event_id
    """
    output = io.StringIO()
    fieldnames = [
        "top_level_project",
        "project_path",
        "date",
        "time",
        "task_path",
        "parent_task_id",
        "project_id",
        "event_id",
    ]
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    writer.writerow(fieldnames)
    for r in records:
        writer.writerow([
            r.get("top_level_project", ""),
            r.get("project_path", ""),
            r.get("date", ""),
            r.get("time", ""),
            r.get("task_path", ""),
            r.get("parent_task_id", ""),
            r.get("project_id", ""),
            r.get("event_id", ""),
        ])
    return output.getvalue()


def export_csv(records: List[Dict[str, Any]], output_path: str) -> None:
    """Export trace records to a CSV file."""
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_csv(records)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def format_task_bullets(records_in_group: List[Dict[str, Any]], task_style: str = "nested") -> List[str]:
    """Format tasks either as nested bullet hierarchy or flat slash paths."""
    if task_style == "flat":
        return [f"- {r.get('task_path', '')}" for r in records_in_group]

    class TaskNode:
        def __init__(self, title: str):
            self.title = title
            self.children: Dict[str, "TaskNode"] = {}

    root_tasks: Dict[str, TaskNode] = {}
    for r in records_in_group:
        levels = r.get("task_levels")
        if not levels:
            levels = [r.get("task_path", "")]
        curr = root_tasks
        for lvl in levels:
            if lvl not in curr:
                curr[lvl] = TaskNode(lvl)
            curr = curr[lvl].children

    def render_tree(nodes: Dict[str, TaskNode], depth: int = 0) -> List[str]:
        res = []
        indent = "  " * depth
        for node in nodes.values():
            res.append(f"{indent}- {node.title}")
            if node.children:
                res.extend(render_tree(node.children, depth + 1))
        return res

    return render_tree(root_tasks)


def generate_markdown(
    records: List[Dict[str, Any]],
    style: str = "nested",
    task_style: str = "nested",
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
                    lines.extend(format_task_bullets(paths_map[""], task_style=task_style))
                    lines.append("")

                # 2. Sub-projects
                for p_path, recs in paths_map.items():
                    if p_path == "":
                        continue
                    if "" not in paths_map and len(lines) > 0 and lines[-1] == f"### {top_proj}":
                        lines.append("")
                    lines.append(f"#### {p_path}")
                    lines.extend(format_task_bullets(recs, task_style=task_style))
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

                    if node.records:
                        lines.extend(format_task_bullets(node.records, task_style=task_style))
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
) -> None:
    """Export trace records to a Markdown file."""
    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = generate_markdown(records, style=style, task_style=task_style)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
