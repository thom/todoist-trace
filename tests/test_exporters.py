"""
Unit tests for CSV and Markdown exporters, including bullet hierarchies.
"""

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

    def test_generate_markdown_nested_style(self, sample_exporter_records):
        md_out = generate_markdown(sample_exporter_records, style="nested")

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

    def test_generate_markdown_flat_style(self, sample_exporter_records):
        md_out = generate_markdown(sample_exporter_records, style="flat")

        # Check date heading
        assert "## 2026-09-15" in md_out

        # Check flat project path heading
        assert "### work-areas" in md_out
        assert "#### admin/email" in md_out
        assert "#### admin\n" not in md_out

        # Check task bullets
        assert "- Check inbox filters / triage / urgent" in md_out
        assert "- Reply to vendor requests" in md_out

        # Check root project without sub-heading
        assert "### personal" in md_out
        assert '- Buy "groceries", apples & milk' in md_out

    def test_export_markdown_file_creation(self, sample_exporter_records, tmp_path):
        out_file = tmp_path / "nested" / "export.md"
        export_markdown(sample_exporter_records, str(out_file), style="nested")

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
        # Nested task style
        md_nested = generate_markdown(records, style="nested", task_style="nested")
        assert "- Sprint Deliverables\n  - Client Portal\n  - Services\n    - Database\n    - Auth" in md_nested

        # Flat task style
        md_flat = generate_markdown(records, style="nested", task_style="flat")
        assert "- Sprint Deliverables / Services / Auth" in md_flat
        assert "- Sprint Deliverables / Services / Database" in md_flat
        assert "- Sprint Deliverables / Client Portal" in md_flat

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

        md = generate_markdown(records, style="nested")
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
                "project_path": "AI Tools",
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
        assert "Work,AI Tools,Sprint 1,2026-10-02,14:00:00,Implement tools,,proj_1,ev_1" in csv_out

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
        md = generate_markdown(records, style="nested")
        assert "### Work" in md
        assert "#### Infrastructure" in md
        # General maintenance is unsectioned and appears directly under Infrastructure
        assert "- General maintenance" in md
        # Section heading at level 5 (parent h4 + 1)
        assert "##### Sprint 1" in md
        assert "- Setup server" in md

    def test_generate_markdown_with_sections_flat_style(self):
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
        md = generate_markdown(records, style="flat")
        assert "### Work" in md
        # Quick hits is under top level Work (h3 + 1 = h4)
        assert "#### Quick Hits" in md
        assert "- Quick task" in md
        # Infrastructure is at h4, so its section is at h5
        assert "#### Infrastructure" in md
        assert "##### Sprint 1" in md
        assert "- Setup server" in md
