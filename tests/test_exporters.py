"""
Unit tests for CSV and Markdown exporters, including bullet hierarchies.
"""

import re
import shutil
import subprocess
import tempfile

from todoist_trace.exporters import (
    export_csv,
    export_markdown,
    format_task_bullets,
    generate_csv,
    generate_markdown,
)


class TestExporters:
    """Test suite for CSV and Markdown exporters."""

    def test_generate_csv(self, sample_exporter_records):
        csv_out = generate_csv(sample_exporter_records)
        lines = csv_out.strip().split("\n")

        # Verify header
        expected_header = "top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id"
        assert lines[0] == expected_header
        assert len(lines) == 4

        # Verify RFC 4180 escaping on quotes & commas
        assert '"Buy ""groceries"", apples & milk"' in lines[3]
        assert "work-areas,admin/email,,2026-09-15,14:25:00,Reply to vendor requests,,proj_123,ev_002" in lines[1] or lines[2]

    def test_export_csv_file_creation(self, sample_exporter_records, tmp_path):
        out_file = tmp_path / "subdir" / "export.csv"
        export_csv(sample_exporter_records, str(out_file))

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "top_level_project,project_path,section,date" in content
        assert "ev_001" in content

    def test_generate_markdown_hierarchical_headings(self, sample_exporter_records):
        md_out = generate_markdown(sample_exporter_records)

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check progressive headings
        assert "### work-areas" in md_out
        assert "#### admin" in md_out
        assert "##### email" in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check direct task under root project
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_export_markdown_file_creation(self, sample_exporter_records, tmp_path):
        out_file = tmp_path / "nested" / "export.md"
        export_markdown(sample_exporter_records, str(out_file))

        assert out_file.is_file()
        content = out_file.read_text(encoding="utf-8")
        assert "## 2026-09-15" in content
        assert "### work-areas" in content

    def test_empty_records(self, tmp_path):
        assert generate_markdown([]) == ""
        csv_empty = generate_csv([])
        assert csv_empty.strip() == "top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id"

    def test_generate_markdown_task_bullet_hierarchy(self):
        records = [
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:00:00",
                "task_path": "Sprint Deliverables / Services / Auth",
                "task_levels": ["Sprint Deliverables", "Services", "Auth"],
                "parent_task_id": "p2",
                "project_id": "p1",
                "event_id": "e1",
            },
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:05:00",
                "task_path": "Sprint Deliverables / Services / Database",
                "task_levels": ["Sprint Deliverables", "Services", "Database"],
                "parent_task_id": "p2",
                "project_id": "p1",
                "event_id": "e2",
            },
            {
                "top_level_project": "work",
                "project_path": "backend-api",
                "project_levels": ["backend-api"],
                "date": "2026-09-30",
                "time": "10:10:00",
                "task_path": "Sprint Deliverables / Client Portal",
                "task_levels": ["Sprint Deliverables", "Client Portal"],
                "parent_task_id": "p1",
                "project_id": "p1",
                "event_id": "e3",
            },
        ]
        # Always hierarchical outline
        md = generate_markdown(records)
        assert "- Sprint Deliverables\n  - Client Portal\n  - Services\n    - Database\n    - Auth" in md

    def test_daily_overview_with_timezone_converted_records(self):
        """Events resolved in local timezone group under their correct local day heading."""
        from todoist_trace.resolvers import format_event_datetime

        # Two events completed on 2026-10-01 in Europe/Zurich (UTC+2)
        # 1. 00:15 AM local -> 2026-09-30 22:15 UTC
        d1, t1 = format_event_datetime("2026-09-30T22:15:00Z", tz="Europe/Zurich")
        # 2. 23:45 PM local -> 2026-10-01 21:45 UTC
        d2, t2 = format_event_datetime("2026-10-01T21:45:00Z", tz="Europe/Zurich")

        assert d1 == "2026-10-01"
        assert t1 == "00:15:00"
        assert d2 == "2026-10-01"
        assert t2 == "23:45:00"

        records = [
            {
                "top_level_project": "Work",
                "project_path": "",
                "project_levels": [],
                "date": d1,
                "time": t1,
                "task_path": "Early Morning Deliverable",
                "task_levels": ["Early Morning Deliverable"],
                "parent_task_id": "",
                "project_id": "p1",
                "event_id": "e1",
            },
            {
                "top_level_project": "Work",
                "project_path": "",
                "project_levels": [],
                "date": d2,
                "time": t2,
                "task_path": "Late Night Wrapup",
                "task_levels": ["Late Night Wrapup"],
                "parent_task_id": "",
                "project_id": "p1",
                "event_id": "e2",
            },
        ]

        md = generate_markdown(records)
        assert "## 2026-10-01" in md
        assert "## 2026-09-30" not in md
        assert "- Early Morning Deliverable" in md
        assert "- Late Night Wrapup" in md

        csv_out = generate_csv(records)
        assert "Work,,,2026-10-01,00:15:00,Early Morning Deliverable,,p1,e1" in csv_out
        assert "Work,,,2026-10-01,23:45:00,Late Night Wrapup,,p1,e2" in csv_out

    def test_generate_csv_with_populated_section(self):
        records = [
            {
                "top_level_project": "Work",
                "project_path": "backend",
                "section": "Sprint 1",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Implement tools",
                "parent_task_id": "",
                "project_id": "proj_1",
                "event_id": "ev_1",
            }
        ]
        csv_out = generate_csv(records)
        assert "Work,backend,Sprint 1,2026-10-02,14:00:00,Implement tools,,proj_1,ev_1" in csv_out

    def test_generate_markdown_with_sections_nested_style(self):
        records = [
            {
                "top_level_project": "Work",
                "project_path": "Infrastructure",
                "project_levels": ["Infrastructure"],
                "section": "Sprint 1",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Setup server",
                "task_levels": ["Setup server"],
                "parent_task_id": "",
                "project_id": "proj_1",
                "event_id": "ev_1",
            },
            {
                "top_level_project": "Work",
                "project_path": "Infrastructure",
                "project_levels": ["Infrastructure"],
                "section": "",
                "date": "2026-10-02",
                "time": "13:00:00",
                "task_path": "General maintenance",
                "task_levels": ["General maintenance"],
                "parent_task_id": "",
                "project_id": "proj_1",
                "event_id": "ev_2",
            },
        ]
        md = generate_markdown(records)
        assert "### Work" in md
        assert "#### Infrastructure" in md
        # General maintenance is unsectioned and appears directly under Infrastructure
        assert "- General maintenance" in md
        # Section heading at level 5 (parent h4 + 1)
        assert "##### Sprint 1" in md
        assert "- Setup server" in md

    def test_generate_markdown_with_sections_multiple_groups(self):
        records = [
            {
                "top_level_project": "Work",
                "project_path": "Infrastructure",
                "section": "Sprint 1",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Setup server",
                "parent_task_id": "",
                "project_id": "proj_1",
                "event_id": "ev_1",
            },
            {
                "top_level_project": "Work",
                "project_path": "",
                "section": "Quick Hits",
                "date": "2026-10-02",
                "time": "12:00:00",
                "task_path": "Quick task",
                "parent_task_id": "",
                "project_id": "proj_0",
                "event_id": "ev_0",
            },
        ]
        md = generate_markdown(records)
        assert "### Work" in md
        # Quick hits is under top level Work (h3 + 1 = h4)
        assert "#### Quick Hits" in md
        assert "- Quick task" in md
        # Infrastructure is at h4, so its section is at h5
        assert "#### Infrastructure" in md
        assert "##### Sprint 1" in md
        assert "- Setup server" in md

    def test_generate_csv_with_extended_metadata(self):
        records = [
            {
                "top_level_project": "Work",
                "project_path": "Backend",
                "section": "Sprint 1",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Refactor auth",
                "parent_task_id": "",
                "project_id": "p1",
                "event_id": "e1",
                "labels": ["urgent", "security"],
                "description": "Fix token expiration issue\nRequires migration",
                "priority": "p1",
                "due_date": "2026-10-01",
                "due_variance": "+1d overdue",
            }
        ]
        # 1. Default (no extended metadata)
        csv_default = generate_csv(records)
        assert csv_default.startswith("top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id\n")
        assert "labels" not in csv_default.splitlines()[0]

        # 2. Individual flags
        csv_labels = generate_csv(records, include_labels=True)
        assert csv_labels.splitlines()[0] == "top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id,labels"
        assert '"urgent,security"' in csv_labels

        csv_desc = generate_csv(records, include_descriptions=True)
        assert "description" in csv_desc.splitlines()[0]
        assert "Fix token expiration issue" in csv_desc

        csv_prio = generate_csv(records, include_priorities=True)
        assert "priority" in csv_prio.splitlines()[0]
        assert ",p1" in csv_prio

        csv_due = generate_csv(records, include_due_dates=True)
        assert "due_date,due_variance" in csv_due.splitlines()[0]
        assert "2026-10-01,+1d overdue" in csv_due

        # 3. All fields enabled
        csv_all = generate_csv(
            records,
            include_labels=True,
            include_descriptions=True,
            include_priorities=True,
            include_due_dates=True,
        )
        header = csv_all.splitlines()[0]
        assert header == "top_level_project,project_path,section,date,time,task_path,parent_task_id,project_id,event_id,labels,description,priority,due_date,due_variance"

    def test_generate_markdown_with_extended_metadata(self):
        records = [
            {
                "top_level_project": "Work",
                "project_path": "",
                "section": "",
                "date": "2026-10-02",
                "time": "15:00:00",
                "task_path": "Root Task / Leaf Subtask",
                "task_levels": ["Root Task", "Leaf Subtask"],
                "labels": ["urgent", "ops"],
                "description": "Important fix\nLine 2 notes",
                "priority": "p1",
                "due_date": "2026-10-01",
                "due_variance": "+1d overdue",
            }
        ]
        md_out = generate_markdown(
            records,
            include_labels=True,
            include_descriptions=True,
            include_priorities=True,
            include_due_dates=True,
        )
        assert "## 2026-10-02" in md_out
        assert "### Work" in md_out
        assert "- Root Task" in md_out
        assert "  - Leaf Subtask [p1] [@urgent, @ops] [Due: 2026-10-01, Done: 2026-10-02 (+1d overdue)]" in md_out
        assert "    > Important fix" in md_out
        assert "    > Line 2 notes" in md_out

    def test_export_files_with_metadata(self, tmp_path):
        records = [
            {
                "top_level_project": "Personal",
                "project_path": "",
                "section": "",
                "date": "2026-10-02",
                "time": "10:00:00",
                "task_path": "Taxes",
                "labels": ["finance"],
                "priority": "p2",
                "description": "Check deductions",
                "due_date": "2026-10-02",
                "due_variance": "on time",
            }
        ]
        csv_file = tmp_path / "meta.csv"
        md_file = tmp_path / "meta.md"

        export_csv(records, str(csv_file), include_labels=True, include_priorities=True)
        export_markdown(records, str(md_file), include_labels=True, include_descriptions=True)

        assert csv_file.is_file()
        assert md_file.is_file()

        csv_text = csv_file.read_text(encoding="utf-8")
        assert "labels" in csv_text.splitlines()[0]
        assert "finance" in csv_text

        md_text = md_file.read_text(encoding="utf-8")
        assert "[@finance]" in md_text
        assert "> Check deductions" in md_text

    def test_generate_html_structure_and_stats(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "Work",
                "project_path": "backend/auth",
                "section": "Sprint 1",
                "date": "2026-09-30",
                "time": "14:30:00",
                "task_path": "Auth / OAuth Flow",
                "labels": ["security", "urgent"],
                "priority": "p1",
                "description": "Rotate secrets",
                "due_date": "2026-09-29",
                "due_variance": "+1d overdue",
                "due_status": "overdue",
            },
            {
                "top_level_project": "Work",
                "project_path": "frontend",
                "section": "UI",
                "date": "2026-09-30",
                "time": "16:00:00",
                "task_path": "Dashboard UI",
                "labels": ["design"],
                "priority": "p3",
                "description": "",
                "due_date": "2026-09-30",
                "due_variance": "on time",
                "due_status": "on_time",
            },
        ]
        html_out = generate_html(records, title="Custom Test Title")
        assert "<!DOCTYPE html>" in html_out
        assert "Custom Test Title" in html_out
        assert 'id="trace-data"' in html_out
        assert "OAuth Flow" in html_out
        assert "Rotate secrets" in html_out
        assert 'data-theme="dark"' in html_out
        assert "theme-toggle" in html_out
        assert "timeline-chart" in html_out
        assert "project-bars" in html_out
        assert "table-body" in html_out
        assert "btn-toggle-accordions" in html_out
        assert "toggleAllAccordions" in html_out
        assert "tab-pstyle-nested" not in html_out
        assert "tab-pstyle-collapsed" not in html_out
        assert "tab-style-flat" not in html_out
        assert "buildTaskTree" in html_out
        assert "renderTaskTree" in html_out
        assert ".task-tree" in html_out
        assert ".task-children" in html_out

    def test_generate_html_hierarchical_task_support(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "Work",
                "project_path": "",
                "section": "",
                "date": "2026-10-02",
                "time": "11:00:00",
                "task_path": "Roadmap / Core Architecture / Performance Metrics",
                "task_levels": ["Roadmap", "Core Architecture", "Performance Metrics"],
                "labels": ["metrics"],
                "priority": "p2",
                "description": "Benchmark throughput",
                "due_date": "2026-10-02",
                "due_variance": "on time",
                "due_status": "on_time",
            }
        ]
        html_out = generate_html(records, title="Hierarchy Test")
        assert "Performance Metrics" in html_out
        assert "Roadmap" in html_out
        assert "Core Architecture" in html_out
        assert 'buildTaskTree' in html_out
        assert 'renderTaskTree' in html_out

    def test_generate_html_project_hierarchy_support(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "work",
                "project_path": "alpha-service",
                "project_levels": ["alpha-service"],
                "section": "",
                "date": "2026-10-02",
                "time": "10:00:00",
                "task_path": "task-alpha",
                "task_levels": ["task-alpha"],
            },
            {
                "top_level_project": "work-areas",
                "project_path": "admin/triage",
                "project_levels": ["admin", "triage"],
                "section": "daily",
                "date": "2026-10-02",
                "time": "11:00:00",
                "task_path": "task-beta",
                "task_levels": ["task-beta"],
            },
        ]
        html_out = generate_html(records, title="Project Hierarchy Test")
        assert "buildProjectTree" in html_out
        assert "renderProjectNode" in html_out
        assert "renderSubprojectHierarchy" in html_out
        assert "btn-toggle-accordions" in html_out
        assert "toggleAllAccordions" in html_out
        assert "renderCollapsedProjectGroups" not in html_out
        assert "tab-pstyle-nested" not in html_out
        assert "tab-pstyle-collapsed" not in html_out
        assert "setProjectStyle" not in html_out
        assert ".top-project-group" in html_out
        assert ".subproject-group" in html_out
        assert "alpha-service" in html_out
        assert "work-areas" in html_out
        assert "admin" in html_out
        assert "triage" in html_out

    def test_export_html_file_creation(self, tmp_path):
        from todoist_trace.exporters import export_html

        records = [
            {
                "top_level_project": "Personal",
                "project_path": "",
                "section": "",
                "date": "2026-10-01",
                "time": "09:00:00",
                "task_path": "Morning run",
                "labels": ["health"],
                "priority": "p4",
                "description": "5 km pace",
                "due_date": "2026-10-01",
                "due_variance": "on time",
                "due_status": "on_time",
            }
        ]
        html_file = tmp_path / "dashboard.html"
        export_html(records, str(html_file))

        assert html_file.is_file()
        content = html_file.read_text(encoding="utf-8")
        assert "Morning run" in content
        assert "5 km pace" in content
        assert "health" in content

    def test_generate_html_empty_records(self):
        from todoist_trace.exporters import generate_html

        html_out = generate_html([])
        assert "<!DOCTYPE html>" in html_out
        assert 'id="trace-data">[]</script>' in html_out

    def test_generate_html_markdown_support(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "certifications",
                "project_path": "study",
                "project_levels": ["study"],
                "section": "Exam prep",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "[Register for Exam](https://example.com/certification-exam)",
                "task_levels": ["[Register for Exam](https://example.com/certification-exam)"],
                "labels": ["study"],
                "priority": "p1",
                "description": "Prerequisites:\n* Complete **foundations** course\n* Review `sample_questions.pdf`\nSee https://example.com/docs for details.",
                "due_date": "2026-10-05",
                "due_variance": "on time",
                "due_status": "on_time",
            }
        ]
        html_out = generate_html(records, title="Markdown Test")
        assert "function renderMarkdown" in html_out
        assert "renderMarkdown(title, true)" in html_out
        assert "renderMarkdown(t.description)" in html_out
        assert "renderMarkdown(r.description)" in html_out
        assert ".task-desc a" in html_out
        assert ".task-desc code" in html_out
        assert "Register for Exam" in html_out
        assert "https://example.com/certification-exam" in html_out

    def test_generate_html_javascript_syntax_validity(self):
        """Verify embedded JavaScript in the generated HTML dashboard has valid syntax."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "certifications",
                "project_path": "study",
                "project_levels": ["study"],
                "section": "Exam prep",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "[Register for Exam](https://example.com/certification-exam)",
                "task_levels": ["[Register for Exam](https://example.com/certification-exam)"],
                "labels": ["study"],
                "priority": "p1",
                "description": "Prerequisites:\n* Complete **foundations** course\n* Review `sample_questions.pdf`\nSee https://example.com/docs for details.",
                "due_date": "2026-10-05",
                "due_variance": "on time",
                "due_status": "on_time",
            }
        ]
        html_out = generate_html(records, title="Syntax Test")
        scripts = re.findall(
            r"<script(?![^>]*type=\"application/json\")>(.*?)</script>",
            html_out,
            re.DOTALL,
        )
        assert len(scripts) >= 1

        # Node.js syntax and runtime execution check (if node is installed)
        node_bin = shutil.which("node")
        if node_bin:
            # 1. Authoritative syntax check on raw emitted script
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(scripts[0])
                syntax_fpath = f.name
            proc_syntax = subprocess.run(
                [node_bin, "--check", syntax_fpath],
                capture_output=True,
                text=True,
            )
            assert (
                proc_syntax.returncode == 0
            ), f"Node.js syntax check failed:\n{proc_syntax.stderr}"

            # 2. Execution test verifying client-side renderMarkdown behavior
            test_js = (
                """
global.window = { addEventListener: () => {}, matchMedia: () => ({ matches: true }) };
global.document = {
  documentElement: { setAttribute: () => {}, getAttribute: () => "dark" },
  getElementById: () => ({ textContent: "[]", innerHTML: "", value: "all", classList: { add: () => {}, remove: () => {}, toggle: () => {} } }),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.localStorage = { getItem: () => null, setItem: () => {} };
"""
                + scripts[0]
                + """
// Test renderMarkdown function directly
const linkOut = renderMarkdown("[Register for Exam](https://example.com/certification-exam)", true);
if (!linkOut.includes('<a href="https://example.com/certification-exam"') || !linkOut.includes('target="_blank"')) {
  throw new Error("Link rendering failed: " + linkOut);
}

const listOut = renderMarkdown("Prerequisites:\\n* Complete **foundations** course\\n* Review `sample.pdf`", false);
if (!listOut.includes("<ul><li>Complete <strong>foundations</strong> course</li>") || !listOut.includes("<code>sample.pdf</code>")) {
  throw new Error("List rendering failed: " + listOut);
}

const autoOut = renderMarkdown("Visit https://example.com/docs for help.", true);
if (!autoOut.includes('<a href="https://example.com/docs"')) {
  throw new Error("Autolink failed: " + autoOut);
}

const codeUnderscore = renderMarkdown("Variable `user_profile_id` here", true);
if (!codeUnderscore.includes("<code>user_profile_id</code>")) {
  throw new Error("Code underscore failed: " + codeUnderscore);
}

const xssOut = renderMarkdown("[click](javascript:alert(1))", true);
if (xssOut.includes("javascript:")) {
  throw new Error("XSS unsafe scheme not blocked: " + xssOut);
}

const cardP1 = renderTaskItemCard("Task Alpha", { priority: "p1" });
if (!cardP1.includes("badge-p1") || !cardP1.includes("P1")) {
  throw new Error("P1 badge rendering failed: " + cardP1);
}

const cardP4 = renderTaskItemCard("Task Beta", { priority: "p4" });
if (cardP4.includes("badge-p4") || cardP4.includes("P4")) {
  throw new Error("P4 badge should be suppressed: " + cardP4);
}
"""
            )
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(test_js)
                exec_fpath = f.name

            proc_exec = subprocess.run(
                [node_bin, exec_fpath], capture_output=True, text=True
            )
            assert (
                proc_exec.returncode == 0
            ), f"Node.js execution failed:\nSTDOUT: {proc_exec.stdout}\nSTDERR: {proc_exec.stderr}"

    def test_generate_html_vector_icons(self):
        """Verify vector SVG icons are embedded and legacy emojis/bullets are replaced."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "infrastructure",
                "project_path": "services/auth",
                "project_levels": ["services", "auth"],
                "section": "Sprint 1",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Deploy Cluster / Worker Nodes",
                "task_levels": ["Deploy Cluster", "Worker Nodes"],
                "parent_task_id": "parent_001",
                "labels": ["backend"],
                "priority": "p2",
                "description": "Cluster provisioning details",
            }
        ]
        html_out = generate_html(records, title="Vector Icon Test")

        # Verify SVG definitions in ICONS object
        assert "icon-layers" in html_out
        assert "icon-hash" in html_out
        assert "icon-section" in html_out
        assert "icon-check-square" in html_out
        assert "icon-minus-square" in html_out

        # Verify SVG elements
        assert "<svg class=\"icon icon-layers\"" in html_out
        assert "<svg class=\"icon icon-hash\"" in html_out
        assert "<svg class=\"icon icon-section\"" in html_out
        assert "<svg class=\"icon icon-check-square\"" in html_out
        assert "<svg class=\"icon icon-minus-square\"" in html_out

        # Verify absence of legacy emojis and raw bullet glyphs
        assert "📂" not in html_out
        assert "📁" not in html_out
        assert "▤" not in html_out

    def test_priority_p4_suppression_in_markdown_and_html(self):
        """Verify default p4 priority is suppressed in visual output while p1-p3 are rendered."""
        from todoist_trace.exporters import generate_markdown, generate_html

        records = [
            {
                "top_level_project": "operations",
                "project_path": "infra",
                "project_levels": ["infra"],
                "section": "Core",
                "date": "2026-10-02",
                "time": "10:00:00",
                "task_path": "Task Alpha",
                "task_levels": ["Task Alpha"],
                "priority": "p1",
            },
            {
                "top_level_project": "operations",
                "project_path": "infra",
                "project_levels": ["infra"],
                "section": "Core",
                "date": "2026-10-02",
                "time": "10:05:00",
                "task_path": "Task Beta",
                "task_levels": ["Task Beta"],
                "priority": "p4",
            },
        ]

        # Markdown check
        md_out = generate_markdown(records, include_priorities=True)
        assert "[p1]" in md_out
        assert "[p4]" not in md_out

        # HTML template check
        html_out = generate_html(records)
        assert "t.priority && t.priority.toLowerCase() !== 'p4'" in html_out
        assert "r.priority && r.priority.toLowerCase() !== 'p4'" in html_out

    def test_generate_html_date_picker_and_day_toggle(self):
        """Verify presence of date period picker, quick presets, and day expand/collapse toggle."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "platform",
                "project_path": "services",
                "date": "2026-09-28",
                "time": "09:00:00",
                "task_path": "Implement Service Layer",
                "task_levels": ["Implement Service Layer"],
            },
            {
                "top_level_project": "platform",
                "project_path": "services",
                "date": "2026-10-02",
                "time": "14:00:00",
                "task_path": "Deploy Service Layer",
                "task_levels": ["Deploy Service Layer"],
            },
        ]

        html_out = generate_html(records, title="Controls Test")

        # Date range picker inputs and single dropdown
        assert 'id="date-from"' in html_out
        assert 'id="date-to"' in html_out
        assert 'id="btn-clear-date"' in html_out
        assert 'id="date-presets"' in html_out
        assert 'id="date-range-dropdown"' in html_out
        assert 'id="date-range-btn"' in html_out
        assert "setDatePreset" in html_out
        assert "applyCustomDateRange" in html_out
        assert "clearDateRange" in html_out
        assert "onDateRangeChange" in html_out
        assert "initDatePickers" in html_out

        # Calendar period presets
        assert 'data-preset="cur_week"' in html_out
        assert 'data-preset="prev_week"' in html_out
        assert 'data-preset="cur_month"' in html_out
        assert 'data-preset="last_month"' in html_out
        assert 'data-preset="cur_quarter"' in html_out
        assert 'data-preset="last_quarter"' in html_out
        assert 'data-preset="cur_year"' in html_out
        assert 'data-preset="prev_year"' in html_out
        assert 'data-preset="7d"' not in html_out
        assert 'data-preset="30d"' not in html_out
        assert 'data-preset="90d"' not in html_out

        # Day expand / collapse toggle controls
        assert "toggleAllDays" in html_out
        assert "updateDayToggleButton" in html_out
        assert "btn-toggle-accordions" in html_out
        assert "Collapse All Days" in html_out

    def test_generate_html_cascading_project_filters_and_specific_projects(self):
        """Verify 3-tier filtering: Category -> Parent Project -> Specific Project."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "work-areas",
                "project_path": "backend",
                "project_levels": ["backend"],
                "date": "2026-10-01",
                "time": "10:00:00",
                "task_path": "DB Migration",
                "task_levels": ["DB Migration"],
            },
            {
                "top_level_project": "personal",
                "project_path": "fitness",
                "project_levels": ["fitness"],
                "date": "2026-10-01",
                "time": "18:00:00",
                "task_path": "Running",
                "task_levels": ["Running"],
            },
        ]

        html_out = generate_html(records, title="3-Tier Filter Test")

        # Dropdowns
        assert 'id="category-filter"' in html_out
        assert 'id="parent-project-filter"' in html_out
        assert 'id="project-filter"' in html_out
        assert 'value="others"' in html_out
        assert "Others (Unassigned)" in html_out

        # JavaScript functions and config
        assert "updateProjectDropdowns" in html_out
        assert "onCategoryChange" in html_out
        assert "onParentProjectChange" in html_out
        assert "getRecordProject" in html_out
        assert "getRecordCategory" in html_out
        assert "CATEGORY_MAP" in html_out

        # Table header
        assert "Parent Project ⬍" in html_out

    def test_generate_html_configurable_categories(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "custom-work",
                "date": "2026-10-01",
                "task_path": "Custom Work Task",
            },
            {
                "top_level_project": "unassigned-archive",
                "date": "2026-10-01",
                "task_path": "Archive Task",
            },
        ]
        custom_cfg = {
            "work": ["custom-work*"],
            "personal": ["my-personal*"],
            "consulting": ["client-*"],
        }
        html_out = generate_html(records, categories_config=custom_cfg)

        assert 'value="consulting"' in html_out
        assert "Consulting" in html_out
        assert 'value="others"' in html_out
        assert "Others (Unassigned)" in html_out
        assert '"custom-work*"' in html_out
        assert "getRecordCategory" in html_out

    def test_generate_html_projects_view_dates_and_grouping_switcher(self):
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "work",
                "project_path": "alpha-service",
                "project_levels": ["alpha-service"],
                "section": "sprint-1",
                "date": "2026-10-02",
                "time": "14:20:00",
                "task_path": "Deploy API gateway",
                "task_levels": ["Deploy API gateway"],
                "priority": "p2",
            },
            {
                "top_level_project": "personal",
                "project_path": "reading",
                "project_levels": ["reading"],
                "section": "",
                "date": "2026-10-01",
                "time": "20:00:00",
                "task_path": "Read chapter 4",
                "task_levels": ["Read chapter 4"],
                "priority": "p4",
            },
        ]
        html_out = generate_html(records, title="Projects View Test")

        # Project view grouping toolbar and buttons
        assert "projects-view-toolbar" in html_out
        assert 'id="btn-group-project"' in html_out
        assert 'id="btn-group-hierarchy"' in html_out
        assert "setProjectsGrouping" in html_out
        assert "projectsGrouping" in html_out

        # Task completion date badge support in projects view
        assert ".badge-date" in html_out
        assert "badge-date" in html_out
        assert "showDate" in html_out

    def test_generate_html_multiselect_filter_controls(self):
        """Verify presence and markup structure of all 5 multiselect filter popovers."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "alpha-platform",
                "project_path": "gateway",
                "project_levels": ["gateway"],
                "section": "sprint-1",
                "date": "2026-10-02",
                "time": "11:00:00",
                "task_path": "Implement rate limiting",
                "task_levels": ["Implement rate limiting"],
                "priority": "p1",
                "due_status": "overdue",
            },
            {
                "top_level_project": "home-tasks",
                "project_path": "garden",
                "project_levels": ["garden"],
                "section": "",
                "date": "2026-10-02",
                "time": "15:00:00",
                "task_path": "Water seedlings",
                "task_levels": ["Water seedlings"],
                "priority": "p3",
                "due_status": "on_time",
            },
        ]
        html_out = generate_html(records, title="Multiselect Controls Test")

        # 1. Five multiselect containers with proper metadata
        assert 'id="category-filter"' in html_out
        assert 'data-name="Categories"' in html_out
        assert 'data-default="All Categories"' in html_out

        assert 'id="parent-project-filter"' in html_out
        assert 'data-name="Parent Projects"' in html_out
        assert 'data-default="All Parent Projects"' in html_out

        assert 'id="project-filter"' in html_out
        assert 'data-name="Projects"' in html_out
        assert 'data-default="All Projects"' in html_out

        assert 'id="priority-filter"' in html_out
        assert 'data-name="Priorities"' in html_out
        assert 'data-default="All Priorities"' in html_out

        assert 'id="due-filter"' in html_out
        assert 'data-name="Due Statuses"' in html_out
        assert 'data-default="All Due Statuses"' in html_out

        # 2. Action buttons (All & Clear)
        assert "selectAllOptions('category-filter')" in html_out
        assert "clearAllOptions('category-filter')" in html_out
        assert "selectAllOptions('parent-project-filter')" in html_out
        assert "clearAllOptions('parent-project-filter')" in html_out
        assert "selectAllOptions('project-filter')" in html_out
        assert "clearAllOptions('project-filter')" in html_out
        assert "selectAllOptions('priority-filter')" in html_out
        assert "clearAllOptions('priority-filter')" in html_out
        assert "selectAllOptions('due-filter')" in html_out
        assert "clearAllOptions('due-filter')" in html_out

        # 3. Live search filter inputs for parent projects and projects
        assert "filterDropdownOptions('parent-project-filter', this.value)" in html_out
        assert "filterDropdownOptions('project-filter', this.value)" in html_out

        # 4. Priority options
        assert 'value="p1"' in html_out
        assert 'value="p2"' in html_out
        assert 'value="p3"' in html_out
        assert 'value="p4"' in html_out
        assert "P1 (Urgent)" in html_out
        assert "P4 (Normal)" in html_out

        # 5. Due status options
        assert 'value="overdue"' in html_out
        assert 'value="on_time"' in html_out
        assert 'value="early"' in html_out
        assert 'value="undated"' in html_out
        assert "Overdue" in html_out
        assert "On Time" in html_out
        assert "Undated" in html_out

        # 6. CSS classes
        assert ".multiselect {" in html_out
        assert ".multiselect-btn {" in html_out
        assert ".multiselect-menu {" in html_out
        assert ".multiselect-option {" in html_out

    def test_generate_html_multiselect_js_controller_and_cascading(self):
        """Verify JavaScript engine functions for multiselect, cascading, and filter evaluation."""
        from todoist_trace.exporters import generate_html

        records = [
            {
                "top_level_project": "corp-services",
                "project_path": "auth-api",
                "project_levels": ["auth-api"],
                "date": "2026-10-02",
                "time": "10:00:00",
                "task_path": "Rotate token secret",
                "task_levels": ["Rotate token secret"],
                "priority": "p1",
                "due_status": "early",
            }
        ]
        html_out = generate_html(records, title="Multiselect JS Test")

        # Controller functions
        assert "toggleDropdown" in html_out
        assert "closeAllDropdowns" in html_out
        assert "getSelectedValues" in html_out
        assert "updateMultiselectButton" in html_out
        assert "selectAllOptions" in html_out
        assert "clearAllOptions" in html_out
        assert "filterDropdownOptions" in html_out
        assert "handleMultiselectChange" in html_out

        # Cascading and event handlers
        assert "updateProjectDropdowns" in html_out
        assert "onCategoryChange" in html_out
        assert "onParentProjectChange" in html_out
        assert "onProjectChange" in html_out
        assert "onPriorityChange" in html_out
        assert "onDueChange" in html_out

        # Filter and reset logic
        assert "applyFilters" in html_out
        assert "resetFilters" in html_out
        assert "filterByProject" in html_out

        # Node.js syntax and functional execution check if available
        import shutil
        import subprocess
        import tempfile
        import re

        node_bin = shutil.which("node")
        if node_bin:
            scripts = re.findall(
                r"<script(?![^>]*type=\"application/json\")>(.*?)</script>",
                html_out,
                re.DOTALL,
            )
            assert len(scripts) >= 1
            test_js = (
                """
global.window = { addEventListener: () => {}, matchMedia: () => ({ matches: true }) };
global.document = {
  documentElement: { setAttribute: () => {}, getAttribute: () => "dark" },
  getElementById: () => ({ textContent: "", innerHTML: "", value: "all", classList: { add: () => {}, remove: () => {}, toggle: () => {} } }),
  querySelectorAll: () => [],
  addEventListener: () => {}
};
global.localStorage = { getItem: () => null, setItem: () => {} };
"""
                + scripts[0]
                + """
if (typeof toggleDropdown !== 'function') throw new Error('toggleDropdown missing');
if (typeof getSelectedValues !== 'function') throw new Error('getSelectedValues missing');
if (typeof updateMultiselectButton !== 'function') throw new Error('updateMultiselectButton missing');
if (typeof selectAllOptions !== 'function') throw new Error('selectAllOptions missing');
if (typeof clearAllOptions !== 'function') throw new Error('clearAllOptions missing');
if (typeof filterDropdownOptions !== 'function') throw new Error('filterDropdownOptions missing');
if (typeof updateProjectDropdowns !== 'function') throw new Error('updateProjectDropdowns missing');
if (typeof applyFilters !== 'function') throw new Error('applyFilters missing');
if (typeof resetFilters !== 'function') throw new Error('resetFilters missing');
if (typeof filterByProject !== 'function') throw new Error('filterByProject missing');
"""
            )
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(test_js)
                fpath = f.name
            proc = subprocess.run([node_bin, fpath], capture_output=True, text=True)
            assert proc.returncode == 0, f"Node.js check failed: {proc.stderr}"









