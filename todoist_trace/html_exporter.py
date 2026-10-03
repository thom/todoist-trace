"""
Interactive HTML dashboard exporter for todoist-trace records.
Generates a standalone, self-contained single-page application with:
- Stats KPI cards (total tasks, active days, on-time rates, velocity)
- Dynamic interactive SVG charts (daily activity timeline, hourly distribution, project share)
- Instant client-side search and multi-dimensional filters (project, section, priority, due status, labels)
- Multiple view modes: Timeline (daily collapsible tree), Projects hierarchy, and Sortable Data Table
- Light and Dark mode with auto-detection and persistence
- Zero external dependencies: 100% offline-ready and self-contained
"""

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_html(
    records: List[Dict[str, Any]],
    include_labels: bool = True,
    include_descriptions: bool = True,
    include_priorities: bool = True,
    include_due_dates: bool = True,
    title: str = "Todoist Trace - Activity Dashboard",
) -> str:
    """Generate a self-contained, interactive HTML dashboard."""
    # Sanitize JSON payload for embedding inside <script>
    json_data = json.dumps(records).replace("</", "<\\/")

    # Pre-calculate initial summary stats for SSR fallback
    total_records = len(records)
    unique_dates = len({r.get("date") for r in records if r.get("date")})
    unique_projects = len({r.get("top_level_project") for r in records if r.get("top_level_project")})

    return f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    /* CSS Reset & Semantic Variables */
    *, *::before, *::after {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    :root[data-theme="dark"] {{
      --bg: #090d16;
      --bg-card: #111827;
      --bg-card-subtle: #162032;
      --bg-hover: #1e293b;
      --border: #1f293d;
      --border-subtle: #1b2436;
      --text: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-light: rgba(99, 102, 241, 0.15);
      --p1-bg: rgba(239, 68, 68, 0.15);
      --p1-border: rgba(239, 68, 68, 0.4);
      --p1-text: #f87171;
      --p2-bg: rgba(249, 115, 22, 0.15);
      --p2-border: rgba(249, 115, 22, 0.4);
      --p2-text: #fb923c;
      --p3-bg: rgba(59, 130, 246, 0.15);
      --p3-border: rgba(59, 130, 246, 0.4);
      --p3-text: #60a5fa;
      --p4-bg: rgba(148, 163, 184, 0.1);
      --p4-border: rgba(148, 163, 184, 0.25);
      --p4-text: #94a3b8;
      --status-overdue-bg: rgba(239, 68, 68, 0.15);
      --status-overdue-text: #f87171;
      --status-ontime-bg: rgba(34, 197, 94, 0.15);
      --status-ontime-text: #4ade80;
      --status-early-bg: rgba(20, 184, 166, 0.15);
      --status-early-text: #2dd4bf;
      --shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
    }}

    :root[data-theme="light"] {{
      --bg: #f8fafc;
      --bg-card: #ffffff;
      --bg-card-subtle: #f1f5f9;
      --bg-hover: #e2e8f0;
      --border: #e2e8f0;
      --border-subtle: #cbd5e1;
      --text: #0f172a;
      --text-muted: #475569;
      --text-dim: #94a3b8;
      --accent: #4f46e5;
      --accent-hover: #4338ca;
      --accent-light: rgba(79, 70, 229, 0.1);
      --p1-bg: #fee2e2;
      --p1-border: #fca5a5;
      --p1-text: #b91c1c;
      --p2-bg: #ffedd5;
      --p2-border: #fdba74;
      --p2-text: #c2410c;
      --p3-bg: #dbeafe;
      --p3-border: #93c5fd;
      --p3-text: #1d4ed8;
      --p4-bg: #f1f5f9;
      --p4-border: #cbd5e1;
      --p4-text: #475569;
      --status-overdue-bg: #fee2e2;
      --status-overdue-text: #b91c1c;
      --status-ontime-bg: #dcfce7;
      --status-ontime-text: #15803d;
      --status-early-bg: #ccfbf1;
      --status-early-text: #0f766e;
      --shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.08);
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, Helvetica, Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.5;
      transition: background-color 0.2s ease, color 0.2s ease;
      min-height: 100vh;
      padding-bottom: 60px;
    }}

    /* Container */
    .container {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 0 20px;
    }}

    /* Top Navigation Header */
    header.topbar {{
      position: sticky;
      top: 0;
      z-index: 50;
      background-color: var(--bg);
      border-bottom: 1px solid var(--border);
      backdrop-filter: blur(12px);
      padding: 14px 0;
      margin-bottom: 24px;
    }}

    .topbar-content {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .brand-icon {{
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: linear-gradient(135deg, var(--accent), #ec4899);
      display: flex;
      align-items: center;
      justify-content: center;
      color: #ffffff;
      font-weight: 700;
      font-size: 16px;
      box-shadow: 0 2px 8px rgba(99, 102, 241, 0.4);
    }}

    .brand-title {{
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}

    .brand-badge {{
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.05em;
      padding: 2px 8px;
      border-radius: 20px;
      background-color: var(--accent-light);
      color: var(--accent);
      border: 1px solid var(--accent);
    }}

    .topbar-actions {{
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    /* Buttons */
    .btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 6px 14px;
      font-size: 13px;
      font-weight: 500;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s ease;
      border: 1px solid var(--border);
      background-color: var(--bg-card);
      color: var(--text);
    }}

    .btn:hover {{
      background-color: var(--bg-hover);
    }}

    .btn-primary {{
      background-color: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
    }}

    .btn-primary:hover {{
      background-color: var(--accent-hover);
    }}

    .btn-icon {{
      padding: 6px 10px;
    }}

    /* KPI Summary Cards Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}

    .kpi-card {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      box-shadow: var(--shadow);
      transition: transform 0.15s ease;
    }}

    .kpi-card:hover {{
      transform: translateY(-2px);
    }}

    .kpi-label {{
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }}

    .kpi-value {{
      font-size: 26px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text);
    }}

    .kpi-subtext {{
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 4px;
    }}

    /* Visualizations Section */
    .charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}

    @media (max-width: 900px) {{
      .charts-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .chart-card {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      box-shadow: var(--shadow);
    }}

    .chart-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
    }}

    .chart-title {{
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
    }}

    .chart-subtitle {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .chart-container {{
      width: 100%;
      height: 180px;
      position: relative;
    }}

    /* Search & Filter Controls */
    .filter-bar {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
      box-shadow: var(--shadow);
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}

    .filter-row {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}

    .search-input-wrap {{
      position: relative;
      flex: 1;
      min-width: 240px;
    }}

    .search-input {{
      width: 100%;
      padding: 8px 12px 8px 36px;
      font-size: 14px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
      transition: border-color 0.15s ease;
    }}

    .search-input:focus {{
      border-color: var(--accent);
    }}

    .search-icon {{
      position: absolute;
      left: 12px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-dim);
      font-size: 14px;
    }}

    .filter-select {{
      padding: 8px 14px;
      font-size: 13px;
      border-radius: 8px;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text);
      outline: none;
      cursor: pointer;
    }}

    .filter-pills {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}

    .pill {{
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 500;
      border-radius: 16px;
      cursor: pointer;
      border: 1px solid var(--border);
      background-color: var(--bg-card-subtle);
      color: var(--text-muted);
      transition: all 0.15s ease;
      user-select: none;
    }}

    .pill:hover {{
      background-color: var(--bg-hover);
      color: var(--text);
    }}

    .pill.active {{
      background-color: var(--accent);
      border-color: var(--accent);
      color: #ffffff;
    }}

    /* View Switcher Tabs */
    .view-switcher {{
      display: inline-flex;
      border-radius: 8px;
      background-color: var(--bg-card-subtle);
      border: 1px solid var(--border);
      padding: 2px;
    }}

    .view-tab {{
      padding: 5px 12px;
      font-size: 12px;
      font-weight: 600;
      border-radius: 6px;
      cursor: pointer;
      color: var(--text-muted);
      background: transparent;
      border: none;
      transition: all 0.15s ease;
    }}

    .view-tab.active {{
      background-color: var(--bg-card);
      color: var(--text);
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
    }}

    /* Filter Counter Banner */
    .filter-status {{
      font-size: 13px;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    /* View Content Containers */
    .view-section {{
      display: none;
    }}

    .view-section.active {{
      display: block;
    }}

    /* Day / Timeline View Accordions */
    .day-group {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      margin-bottom: 16px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .day-header {{
      padding: 14px 20px;
      background-color: var(--bg-card-subtle);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      cursor: pointer;
      user-select: none;
    }}

    .day-title {{
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .day-count-badge {{
      font-size: 12px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 12px;
      background-color: var(--accent-light);
      color: var(--accent);
    }}

    .day-toggle-icon {{
      font-size: 12px;
      color: var(--text-dim);
      transition: transform 0.2s ease;
    }}

    .day-group.collapsed .day-toggle-icon {{
      transform: rotate(-90deg);
    }}

    .day-group.collapsed .day-content {{
      display: none;
    }}

    .day-content {{
      padding: 16px 20px;
    }}

    /* Top-Level Project Group */
    .top-project-group {{
      margin-bottom: 16px;
      background-color: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 10px;
      padding: 14px 16px;
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
    }}

    .top-project-group:last-child {{
      margin-bottom: 0;
    }}

    .top-project-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .top-project-icon {{
      font-size: 15px;
      line-height: 1;
      margin-right: 2px;
    }}

    .top-project-title {{
      font-size: 14px;
      font-weight: 700;
      color: var(--text);
      letter-spacing: -0.01em;
    }}

    .top-project-count-badge {{
      font-size: 11px;
      font-weight: 600;
      color: var(--text-dim);
      background-color: var(--bg-hover);
      padding: 2px 8px;
      border-radius: 10px;
      border: 1px solid var(--border-subtle);
    }}

    .top-project-content {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}

    /* Sub-Project Group */
    .subproject-group {{
      margin-top: 4px;
      margin-bottom: 6px;
      padding-left: 12px;
      border-left: 2px solid var(--accent);
    }}

    .subproject-group.depth-1 {{
      margin-left: 14px;
      border-left: 2px dashed var(--accent-light);
    }}

    .subproject-group.depth-2 {{
      margin-left: 14px;
      border-left: 2px dotted var(--text-dim);
    }}

    .subproject-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }}

    .subproject-icon {{
      font-size: 13px;
      line-height: 1;
      margin-right: 2px;
    }}

    .subproject-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--accent);
    }}

    .subproject-count-badge {{
      font-size: 10px;
      font-weight: 500;
      color: var(--text-dim);
      background-color: var(--bg-hover);
      padding: 1px 6px;
      border-radius: 8px;
    }}

    .subproject-content {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    /* Section Group inside Project */
    .project-section-group {{
      margin-top: 8px;
      margin-bottom: 4px;
    }}

    .project-section-header {{
      display: flex;
      align-items: center;
      gap: 6px;
      margin-bottom: 6px;
    }}

    .section-tag {{
      font-size: 11px;
      font-weight: 600;
      padding: 1px 7px;
      border-radius: 4px;
      background-color: var(--bg-hover);
      color: var(--text-muted);
    }}

    /* Hierarchical Task Tree */
    .task-tree {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .task-tree-node {{
      position: relative;
    }}

    .task-children {{
      margin-left: 20px;
      padding-left: 14px;
      border-left: 2px dashed var(--border);
      margin-top: 6px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}

    .task-node-card.is-parent {{
      background-color: var(--bg-card-subtle);
      border: 1px solid var(--border);
      border-left: 3px solid var(--accent);
      padding: 6px 12px;
      border-radius: 6px;
    }}

    .task-parent-icon {{
      color: var(--accent);
      font-weight: 700;
      font-size: 13px;
      margin-right: 4px;
    }}

    .task-parent-title {{
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }}

    .badge-parent {{
      background-color: var(--bg-hover);
      color: var(--text-dim);
      font-size: 10px;
      padding: 1px 6px;
      border-radius: 4px;
    }}

    .task-item.is-subtask {{
      border-left: 2px solid var(--accent-light);
    }}

    /* Task Item Row */
    .task-item {{
      padding: 8px 12px;
      border-radius: 8px;
      margin-bottom: 2px;
      background-color: var(--bg-card);
      border: 1px solid var(--border-subtle);
      transition: background-color 0.15s ease;
    }}

    .task-item:hover {{
      background-color: var(--bg-card-subtle);
    }}

    .task-main-row {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
    }}

    .task-title-group {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      flex: 1;
    }}

    .task-bullet {{
      color: var(--accent);
      margin-top: 2px;
    }}

    .task-content {{
      font-size: 14px;
      font-weight: 500;
      color: var(--text);
    }}

    .task-meta-group {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}

    .task-time {{
      font-size: 12px;
      font-family: monospace;
      color: var(--text-dim);
    }}

    /* Badges */
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 4px;
      border: 1px solid transparent;
    }}

    .badge-p1 {{ background-color: var(--p1-bg); border-color: var(--p1-border); color: var(--p1-text); }}
    .badge-p2 {{ background-color: var(--p2-bg); border-color: var(--p2-border); color: var(--p2-text); }}
    .badge-p3 {{ background-color: var(--p3-bg); border-color: var(--p3-border); color: var(--p3-text); }}
    .badge-p4 {{ background-color: var(--p4-bg); border-color: var(--p4-border); color: var(--p4-text); }}

    .badge-overdue {{ background-color: var(--status-overdue-bg); color: var(--status-overdue-text); }}
    .badge-ontime {{ background-color: var(--status-ontime-bg); color: var(--status-ontime-text); }}
    .badge-early {{ background-color: var(--status-early-bg); color: var(--status-early-text); }}

    .badge-label {{
      background-color: var(--bg-hover);
      color: var(--text-muted);
      cursor: pointer;
    }}
    .badge-label:hover {{
      color: var(--accent);
    }}

    .task-desc {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 6px;
      margin-left: 20px;
      padding-left: 10px;
      border-left: 2px solid var(--border);
      line-height: 1.5;
    }}
    .task-desc a,
    .task-content a,
    .task-parent-title a,
    .data-table td a {{
      color: var(--accent);
      text-decoration: underline;
      text-underline-offset: 2px;
      word-break: break-word;
    }}
    .task-desc a:hover,
    .task-content a:hover,
    .task-parent-title a:hover,
    .data-table td a:hover {{
      text-decoration: none;
      filter: brightness(1.2);
    }}
    .task-desc code,
    .task-content code,
    .data-table td code {{
      background-color: var(--bg-hover);
      color: var(--text);
      padding: 1px 5px;
      border-radius: 4px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.9em;
      border: 1px solid var(--border);
    }}
    .task-desc ul, .task-desc ol {{
      margin: 4px 0 4px 18px;
      padding-left: 0;
    }}
    .task-desc li {{
      margin-bottom: 2px;
    }}

    /* Table View */
    .table-container {{
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow-x: auto;
      box-shadow: var(--shadow);
    }}

    table.data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }}

    table.data-table th {{
      background-color: var(--bg-card-subtle);
      padding: 12px 14px;
      font-weight: 600;
      color: var(--text-muted);
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }}

    table.data-table th:hover {{
      color: var(--text);
    }}

    table.data-table td {{
      padding: 10px 14px;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: top;
    }}

    table.data-table tr:hover td {{
      background-color: var(--bg-card-subtle);
    }}

    /* Tooltip */
    .chart-tooltip {{
      position: absolute;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      box-shadow: var(--shadow);
      pointer-events: none;
      opacity: 0;
      transition: opacity 0.15s ease;
      z-index: 100;
    }}

    /* Empty state */
    .empty-state {{
      text-align: center;
      padding: 48px 20px;
      background-color: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 12px;
      color: var(--text-muted);
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <div class="container topbar-content">
      <div class="brand">
        <div class="brand-icon">✓</div>
        <div class="brand-title">todoist-trace</div>
        <div class="brand-badge">Activity Dashboard</div>
      </div>
      <div class="topbar-actions">
        <div class="view-switcher">
          <button class="view-tab active" data-view="timeline" onclick="switchView('timeline')">Timeline</button>
          <button class="view-tab" data-view="projects" onclick="switchView('projects')">Projects</button>
          <button class="view-tab" data-view="table" onclick="switchView('table')">Table</button>
        </div>
        <button class="btn btn-icon" id="theme-toggle" onclick="toggleTheme()" title="Toggle Dark / Light Mode">
          <span id="theme-icon">☀️</span>
        </button>
      </div>
    </div>
  </header>

  <main class="container">
    <!-- KPI Header Cards -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Completed Tasks</div>
        <div class="kpi-value" id="kpi-total-tasks">{total_records:,}</div>
        <div class="kpi-subtext" id="kpi-sub-tasks">Across all synced records</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Active Days</div>
        <div class="kpi-value" id="kpi-active-days">{unique_dates}</div>
        <div class="kpi-subtext" id="kpi-velocity">- tasks / active day</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">On-Time Rate</div>
        <div class="kpi-value" id="kpi-ontime-rate">-%</div>
        <div class="kpi-subtext" id="kpi-ontime-sub">Based on due dates</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Top Category</div>
        <div class="kpi-value" id="kpi-top-project">-</div>
        <div class="kpi-subtext" id="kpi-top-proj-sub">- tasks</div>
      </div>
    </div>

    <!-- Charts Row -->
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">Daily Activity Velocity</div>
            <div class="chart-subtitle">Tasks completed per day (click bar to filter day)</div>
          </div>
        </div>
        <div class="chart-container" id="timeline-chart-wrap">
          <svg id="timeline-chart" width="100%" height="100%"></svg>
          <div class="chart-tooltip" id="chart-tooltip"></div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">Project Share</div>
            <div class="chart-subtitle">Top projects distribution</div>
          </div>
        </div>
        <div class="chart-container" id="project-chart-wrap" style="height: 180px; overflow-y: auto;">
          <div id="project-bars" style="display: flex; flex-direction: column; gap: 8px;"></div>
        </div>
      </div>
    </div>

    <!-- Filter & Search Controls -->
    <div class="filter-bar">
      <div class="filter-row">
        <div class="search-input-wrap">
          <span class="search-icon">🔍</span>
          <input type="text" id="search-box" class="search-input" placeholder="Search tasks, descriptions, projects, or @tags..." oninput="onSearchChange()">
        </div>
        <select id="category-filter" class="filter-select" onchange="applyFilters()">
          <option value="all">All Categories</option>
          <option value="work">Work</option>
          <option value="personal">Personal</option>
        </select>
        <select id="project-filter" class="filter-select" onchange="applyFilters()">
          <option value="all">All Projects</option>
        </select>
        <select id="priority-filter" class="filter-select" onchange="applyFilters()">
          <option value="all">All Priorities</option>
          <option value="p1">P1 (Urgent)</option>
          <option value="p2">P2 (High)</option>
          <option value="p3">P3 (Medium)</option>
          <option value="p4">P4 (Normal)</option>
        </select>
        <select id="due-filter" class="filter-select" onchange="applyFilters()">
          <option value="all">All Due Statuses</option>
          <option value="overdue">Overdue</option>
          <option value="on_time">On Time</option>
          <option value="early">Early</option>
          <option value="undated">Undated</option>
        </select>
        <button class="btn" onclick="resetFilters()">Reset Filters</button>
      </div>

      <div class="filter-status">
        <span id="filter-counter">Showing {total_records} of {total_records} tasks</span>
        <div style="display: flex; align-items: center; gap: 16px; flex-wrap: wrap;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 12px; color: var(--text-dim);">Projects:</span>
            <div class="view-switcher">
              <button class="view-tab active" id="tab-pstyle-nested" onclick="setProjectStyle('nested')">⊞ Nested</button>
              <button class="view-tab" id="tab-pstyle-collapsed" onclick="setProjectStyle('collapsed')">≡ Collapsed Path</button>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-size: 12px; color: var(--text-dim);">Tasks:</span>
            <div class="view-switcher">
              <button class="view-tab active" id="tab-style-nested" onclick="setTaskStyle('nested')">⊞ Nested Bullets</button>
              <button class="view-tab" id="tab-style-flat" onclick="setTaskStyle('flat')">≡ Flat Path</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Timeline View Container -->
    <div id="view-timeline" class="view-section active">
      <div id="timeline-container"></div>
    </div>

    <!-- Projects View Container -->
    <div id="view-projects" class="view-section">
      <div id="projects-container"></div>
    </div>

    <!-- Data Table View Container -->
    <div id="view-table" class="view-section">
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th onclick="sortTable('date')">Date & Time ⬍</th>
              <th onclick="sortTable('top_level_project')">Category ⬍</th>
              <th onclick="sortTable('project_path')">Project / Section ⬍</th>
              <th onclick="sortTable('task_path')">Task Hierarchy ⬍</th>
              <th onclick="sortTable('priority')">Priority ⬍</th>
              <th>Labels</th>
              <th onclick="sortTable('due_date')">Due Date ⬍</th>
            </tr>
          </thead>
          <tbody id="table-body"></tbody>
        </table>
      </div>
    </div>
  </main>

  <!-- Embedded JSON Payload -->
  <script type="application/json" id="trace-data">{json_data}</script>

  <!-- Client-Side Dashboard Engine -->
  <script>
    let rawRecords = [];
    try {{
      rawRecords = JSON.parse(document.getElementById('trace-data').textContent);
    }} catch (e) {{
      console.error('Failed to parse trace records JSON', e);
    }}

    let filteredRecords = [...rawRecords];
    let currentSortColumn = 'date';
    let currentSortAsc = false;
    let activeDayFilter = null;

    // Theme Management
    function initTheme() {{
      const saved = localStorage.getItem('todoist-trace-theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      const theme = saved || (prefersDark ? 'dark' : 'light');
      setTheme(theme);
    }}

    function setTheme(theme) {{
      document.documentElement.setAttribute('data-theme', theme);
      localStorage.setItem('todoist-trace-theme', theme);
      const icon = document.getElementById('theme-icon');
      if (icon) icon.textContent = theme === 'dark' ? '☀️' : '🌙';
      renderTimelineChart();
    }}

    function toggleTheme() {{
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      setTheme(current === 'dark' ? 'light' : 'dark');
    }}

    // Project Style Management (Nested Hierarchy vs Collapsed Path)
    let currentProjectStyle = localStorage.getItem('todoist-trace-project-style') || 'nested';

    function initProjectStyle() {{
      setProjectStyle(currentProjectStyle, false);
    }}

    function setProjectStyle(style, shouldReRender = true) {{
      currentProjectStyle = style;
      localStorage.setItem('todoist-trace-project-style', style);
      const btnNested = document.getElementById('tab-pstyle-nested');
      const btnCollapsed = document.getElementById('tab-pstyle-collapsed');
      if (btnNested && btnCollapsed) {{
        btnNested.classList.toggle('active', style === 'nested');
        btnCollapsed.classList.toggle('active', style === 'collapsed');
      }}
      if (shouldReRender) {{
        renderTimelineView();
        renderProjectsView();
        renderTableView();
      }}
    }}

    // Task Style Management (Nested Bullets vs Flat Path)
    let currentTaskStyle = localStorage.getItem('todoist-trace-task-style') || 'nested';

    function initTaskStyle() {{
      setTaskStyle(currentTaskStyle, false);
    }}

    function setTaskStyle(style, shouldReRender = true) {{
      currentTaskStyle = style;
      localStorage.setItem('todoist-trace-task-style', style);
      const btnNested = document.getElementById('tab-style-nested');
      const btnFlat = document.getElementById('tab-style-flat');
      if (btnNested && btnFlat) {{
        btnNested.classList.toggle('active', style === 'nested');
        btnFlat.classList.toggle('active', style === 'flat');
      }}
      if (shouldReRender) {{
        renderTimelineView();
        renderProjectsView();
        renderTableView();
      }}
    }}

    // View Switching
    function switchView(viewName) {{
      document.querySelectorAll('.view-tab').forEach(t => {{
        t.classList.toggle('active', t.getAttribute('data-view') === viewName);
      }});
      document.querySelectorAll('.view-section').forEach(s => {{
        s.classList.toggle('active', s.id === `view-${{viewName}}`);
      }});
    }}

    // Filter Options Initialization
    function initFilterDropdowns() {{
      const projSelect = document.getElementById('project-filter');
      const projects = [...new Set(rawRecords.map(r => r.top_level_project).filter(Boolean))].sort();
      projects.forEach(p => {{
        const opt = document.createElement('option');
        opt.value = p;
        opt.textContent = p;
        projSelect.appendChild(opt);
      }});
    }}

    // Apply Active Filters
    function applyFilters() {{
      const query = (document.getElementById('search-box').value || '').toLowerCase().trim();
      const cat = document.getElementById('category-filter').value;
      const proj = document.getElementById('project-filter').value;
      const prio = document.getElementById('priority-filter').value;
      const due = document.getElementById('due-filter').value;

      filteredRecords = rawRecords.filter(r => {{
        if (cat !== 'all' && (r.top_level_project || '').toLowerCase() !== cat) return false;
        if (proj !== 'all' && r.top_level_project !== proj) return false;
        if (prio !== 'all' && (r.priority || '').toLowerCase() !== prio) return false;
        if (due !== 'all' && (r.due_status || '') !== due) return false;
        if (activeDayFilter && r.date !== activeDayFilter) return false;

        if (query) {{
          const haystack = [
            r.task_path,
            r.description,
            r.top_level_project,
            r.project_path,
            r.section,
            (r.labels || []).join(' '),
          ].filter(Boolean).join(' ').toLowerCase();
          if (!haystack.includes(query)) return false;
        }}
        return true;
      }});

      updateKPIs();
      renderTimelineView();
      renderProjectsView();
      renderTableView();
      renderTimelineChart();
      renderProjectBars();

      const counter = document.getElementById('filter-counter');
      if (counter) {{
        counter.textContent = `Showing ${{filteredRecords.length.toLocaleString()}} of ${{rawRecords.length.toLocaleString()}} tasks${{activeDayFilter ? ` (Filtered to day ${{activeDayFilter}})` : ''}}`;
      }}
    }}

    function onSearchChange() {{
      applyFilters();
    }}

    function resetFilters() {{
      document.getElementById('search-box').value = '';
      document.getElementById('category-filter').value = 'all';
      document.getElementById('project-filter').value = 'all';
      document.getElementById('priority-filter').value = 'all';
      document.getElementById('due-filter').value = 'all';
      activeDayFilter = null;
      applyFilters();
    }}

    // Update KPI Header Cards
    function updateKPIs() {{
      const total = filteredRecords.length;
      document.getElementById('kpi-total-tasks').textContent = total.toLocaleString();

      const dates = [...new Set(filteredRecords.map(r => r.date).filter(Boolean))];
      const activeDays = dates.length;
      document.getElementById('kpi-active-days').textContent = activeDays;
      const avg = activeDays ? (total / activeDays).toFixed(1) : '0';
      document.getElementById('kpi-velocity').textContent = `${{avg}} tasks / active day`;

      // On-time percentage
      const datedTasks = filteredRecords.filter(r => r.due_status && r.due_status !== 'undated');
      if (datedTasks.length > 0) {{
        const onTimeOrEarly = datedTasks.filter(r => r.due_status === 'on_time' || r.due_status === 'early').length;
        const pct = Math.round((onTimeOrEarly / datedTasks.length) * 100);
        document.getElementById('kpi-ontime-rate').textContent = `${{pct}}%`;
        document.getElementById('kpi-ontime-sub').textContent = `${{onTimeOrEarly}} of ${{datedTasks.length}} dated tasks on time`;
      }} else {{
        document.getElementById('kpi-ontime-rate').textContent = 'N/A';
        document.getElementById('kpi-ontime-sub').textContent = 'No dated tasks';
      }}

      // Top Project
      const projCounts = {{}};
      filteredRecords.forEach(r => {{
        const p = r.top_level_project || 'Uncategorized';
        projCounts[p] = (projCounts[p] || 0) + 1;
      }});
      let topProj = '-';
      let topCount = 0;
      for (const [p, c] of Object.entries(projCounts)) {{
        if (c > topCount) {{
          topProj = p;
          topCount = c;
        }}
      }}
      document.getElementById('kpi-top-project').textContent = topProj;
      document.getElementById('kpi-top-proj-sub').textContent = topCount ? `${{topCount.toLocaleString()}} tasks (${{Math.round(topCount / total * 100)}}%)` : '-';
    }}

    // Render Timeline View (Grouped by Date)
    function renderTimelineView() {{
      const container = document.getElementById('timeline-container');
      if (!container) return;

      if (filteredRecords.length === 0) {{
        container.innerHTML = '<div class="empty-state">No matching tasks found. Adjust search or filters.</div>';
        return;
      }}

      // Group by date
      const byDate = {{}};
      filteredRecords.forEach(r => {{
        const d = r.date || 'Undated';
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(r);
      }});

      const sortedDates = Object.keys(byDate).sort().reverse();
      let html = '';

      sortedDates.forEach(dateStr => {{
        const dayRecords = byDate[dateStr];
        html += `
          <div class="day-group" data-date="${{dateStr}}">
            <div class="day-header" onclick="toggleDayAccordion(this)">
              <div class="day-title">
                <span>${{dateStr}}</span>
                <span class="day-count-badge">${{dayRecords.length}} tasks</span>
              </div>
              <span class="day-toggle-icon">▼</span>
            </div>
            <div class="day-content">
        `;

        // Split by top-level project first
        const byTopProj = {{}};
        dayRecords.forEach(r => {{
          const tp = r.top_level_project || 'Uncategorized';
          if (!byTopProj[tp]) byTopProj[tp] = [];
          byTopProj[tp].push(r);
        }});

        const sortedTopProjs = Object.keys(byTopProj).sort();
        sortedTopProjs.forEach(topProj => {{
          const topRecords = byTopProj[topProj];

          html += `
            <div class="top-project-group">
              <div class="top-project-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span class="top-project-icon">📂</span>
                  <span class="top-project-title">${{escapeHtml(topProj)}}</span>
                </div>
                <span class="top-project-count-badge">${{topRecords.length}} task${{topRecords.length === 1 ? '' : 's'}}</span>
              </div>
              <div class="top-project-content">
                ${{renderSubprojectHierarchy(topRecords)}}
              </div>
            </div>
          `;
        }});

        html += `
            </div>
          </div>
        `;
      }});

      container.innerHTML = html;
    }}

    function toggleDayAccordion(el) {{
      const group = el.closest('.day-group');
      if (group) group.classList.toggle('collapsed');
    }}

    // Hierarchical Task Tree Resolution
    function buildTaskTree(records) {{
      const root = {{}};

      records.forEach(r => {{
        let levels = r.task_levels;
        if (!levels || levels.length === 0) {{
          if (r.task_path) {{
            levels = r.task_path.split(' / ').map(s => s.trim()).filter(Boolean);
          }}
          if (!levels || levels.length === 0) {{
            levels = ['Unnamed Task'];
          }}
        }}

        let curr = root;
        for (let i = 0; i < levels.length - 1; i++) {{
          const lvl = levels[i];
          if (!curr[lvl]) {{
            curr[lvl] = {{
              title: lvl,
              records: [],
              children: {{}}
            }};
          }}
          curr = curr[lvl].children;
        }}

        const leafTitle = levels[levels.length - 1];
        if (!curr[leafTitle]) {{
          curr[leafTitle] = {{
            title: leafTitle,
            records: [r],
            children: {{}}
          }};
        }} else {{
          curr[leafTitle].records.push(r);
        }}
      }});

      return root;
    }}

    function countTotalLeaves(node) {{
      let count = (node.records || []).length;
      for (const child of Object.values(node.children || {{}})) {{
        count += countTotalLeaves(child);
      }}
      return count;
    }}

    function renderTaskItemCard(title, t, isSubtask = false) {{
      let prioBadge = '';
      if (t.priority) {{
        prioBadge = `<span class="badge badge-${{t.priority.toLowerCase()}}">${{t.priority.toUpperCase()}}</span>`;
      }}

      let dueBadge = '';
      if (t.due_status && t.due_status !== 'undated') {{
        dueBadge = `<span class="badge badge-${{t.due_status}}">${{escapeHtml(t.due_variance || t.due_status)}}</span>`;
      }}

      let labelsBadges = '';
      if (t.labels && t.labels.length > 0) {{
        labelsBadges = t.labels.map(l => `<span class="badge badge-label" onclick="filterByTag('${{escapeHtml(l)}}')">@${{escapeHtml(l.replace(/^@/, ''))}}</span>`).join(' ');
      }}

      let descHtml = '';
      if (t.description) {{
        descHtml = `<div class="task-desc">${{renderMarkdown(t.description)}}</div>`;
      }}

      const bullet = isSubtask
        ? '<span class="task-bullet" style="color: var(--accent); font-weight: 700;">↳ •</span>'
        : '<span class="task-bullet">•</span>';

      return `
        <div class="task-item ${{isSubtask ? 'is-subtask' : ''}}">
          <div class="task-main-row">
            <div class="task-title-group">
              ${{bullet}}
              <span class="task-content" style="${{isSubtask ? 'font-size: 13px;' : ''}}">${{renderMarkdown(title, true)}}</span>
            </div>
            <div class="task-meta-group">
              ${{prioBadge}}
              ${{dueBadge}}
              ${{labelsBadges}}
              <span class="task-time">${{escapeHtml(t.time || '')}}</span>
            </div>
          </div>
          ${{descHtml}}
        </div>
      `;
    }}

    function renderFlatTaskItem(t) {{
      return renderTaskItemCard(t.task_path || 'Unnamed Task', t, false);
    }}

    function renderTaskItem(t) {{
      return renderFlatTaskItem(t);
    }}

    function renderTaskTree(nodes, depth = 0) {{
      let html = '<div class="task-tree">';
      for (const node of Object.values(nodes)) {{
        const hasChildren = Object.keys(node.children).length > 0;
        const hasRecords = node.records && node.records.length > 0;

        html += '<div class="task-tree-node">';

        if (hasRecords) {{
          node.records.forEach(r => {{
            html += renderTaskItemCard(node.title, r, depth > 0);
          }});
        }} else {{
          const subtaskCount = countTotalLeaves(node);
          html += `
            <div class="task-node-card is-parent">
              <div style="display: flex; align-items: center; justify-content: space-between;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="task-parent-icon">📁</span>
                  <span class="task-parent-title">${{renderMarkdown(node.title, true)}}</span>
                </div>
                <span class="badge-parent">${{subtaskCount}} subtask${{subtaskCount === 1 ? '' : 's'}}</span>
              </div>
            </div>
          `;
        }}

        if (hasChildren) {{
          html += `
            <div class="task-children">
              ${{renderTaskTree(node.children, depth + 1)}}
            </div>
          `;
        }}

        html += '</div>';
      }}
      html += '</div>';
      return html;
    }}

    // Hierarchical Project Tree Resolution
    function buildProjectTree(records) {{
      const root = {{
        name: '',
        records: [],
        children: {{}}
      }};

      records.forEach(r => {{
        let levels = r.project_levels;
        if (!levels || levels.length === 0) {{
          if (r.project_path) {{
            levels = r.project_path.split('/').map(s => s.trim()).filter(Boolean);
          }}
        }}

        if (!levels || levels.length === 0) {{
          root.records.push(r);
          return;
        }}

        let curr = root;
        for (let i = 0; i < levels.length; i++) {{
          const lvl = levels[i];
          if (!curr.children[lvl]) {{
            curr.children[lvl] = {{
              name: lvl,
              records: [],
              children: {{}}
            }};
          }}
          curr = curr.children[lvl];
        }}
        curr.records.push(r);
      }});

      return root;
    }}

    function countTotalProjectTasks(node) {{
      let count = (node.records || []).length;
      for (const child of Object.values(node.children || {{}})) {{
        count += countTotalProjectTasks(child);
      }}
      return count;
    }}

    function renderTasksWithSections(records) {{
      if (!records || records.length === 0) return '';

      const hasSections = records.some(r => Boolean(r.section));
      if (!hasSections) {{
        if (currentTaskStyle === 'nested') {{
          const tree = buildTaskTree(records);
          return renderTaskTree(tree, 0);
        }} else {{
          return records.map(renderFlatTaskItem).join('');
        }}
      }}

      // Group by section: empty/unsectioned first
      const sectionMap = {{}};
      records.forEach(r => {{
        const sec = r.section || '';
        if (!sectionMap[sec]) sectionMap[sec] = [];
        sectionMap[sec].push(r);
      }});

      let html = '';
      if (sectionMap['']) {{
        if (currentTaskStyle === 'nested') {{
          const tree = buildTaskTree(sectionMap['']);
          html += renderTaskTree(tree, 0);
        }} else {{
          html += sectionMap[''].map(renderFlatTaskItem).join('');
        }}
      }}

      for (const [sec, recs] of Object.entries(sectionMap)) {{
        if (sec === '') continue;
        html += `
          <div class="project-section-group">
            <div class="project-section-header">
              <span class="section-tag">§ ${{escapeHtml(sec)}}</span>
              <span style="font-size: 11px; color: var(--text-dim);">${{recs.length}} tasks</span>
            </div>
            ${{currentTaskStyle === 'nested' ? renderTaskTree(buildTaskTree(recs), 0) : recs.map(renderFlatTaskItem).join('')}}
          </div>
        `;
      }}

      return html;
    }}

    function renderProjectNode(node, depth = 0) {{
      let html = '';

      // Render direct tasks under this node
      if (node.records && node.records.length > 0) {{
        if (depth === 0 && Object.keys(node.children).length > 0) {{
          html += `
            <div style="font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 4px;">
              (Direct Tasks)
            </div>
          `;
        }}
        html += renderTasksWithSections(node.records);
      }}

      // Render child subprojects
      const sortedChildNames = Object.keys(node.children).sort();
      for (const childName of sortedChildNames) {{
        const child = node.children[childName];
        const totalChildTasks = countTotalProjectTasks(child);

        html += `
          <div class="subproject-group depth-${{depth}}">
            <div class="subproject-header">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="subproject-icon">📁</span>
                <span class="subproject-title">${{escapeHtml(child.name)}}</span>
              </div>
              <span class="subproject-count-badge">${{totalChildTasks}} task${{totalChildTasks === 1 ? '' : 's'}}</span>
            </div>
            <div class="subproject-content">
              ${{renderProjectNode(child, depth + 1)}}
            </div>
          </div>
        `;
      }}

      return html;
    }}

    function renderCollapsedProjectGroups(records) {{
      const pathMap = {{}};
      records.forEach(r => {{
        const p = r.project_path || '';
        if (!pathMap[p]) pathMap[p] = [];
        pathMap[p].push(r);
      }});

      let html = '';
      if (pathMap['']) {{
        if (Object.keys(pathMap).length > 1) {{
          html += `
            <div style="font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 4px;">
              (Direct Tasks)
            </div>
          `;
        }}
        html += renderTasksWithSections(pathMap['']);
      }}

      const sortedPaths = Object.keys(pathMap).filter(Boolean).sort();
      for (const path of sortedPaths) {{
        const recs = pathMap[path];
        const displayPath = path.replace(/\\s*\\/\\s*/g, ' › ');
        html += `
          <div class="subproject-group depth-0">
            <div class="subproject-header">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span class="subproject-icon">📁</span>
                <span class="subproject-title">${{escapeHtml(displayPath)}}</span>
              </div>
              <span class="subproject-count-badge">${{recs.length}} task${{recs.length === 1 ? '' : 's'}}</span>
            </div>
            <div class="subproject-content">
              ${{renderTasksWithSections(recs)}}
            </div>
          </div>
        `;
      }}

      return html;
    }}

    function renderSubprojectHierarchy(topRecords) {{
      if (currentProjectStyle === 'collapsed') {{
        return renderCollapsedProjectGroups(topRecords);
      }} else {{
        const projectTree = buildProjectTree(topRecords);
        return renderProjectNode(projectTree, 0);
      }}
    }}

    function filterByTag(tag) {{
      document.getElementById('search-box').value = `@${{tag.replace(/^@/, '')}}`;
      applyFilters();
    }}

    // Render Projects View
    function renderProjectsView() {{
      const container = document.getElementById('projects-container');
      if (!container) return;

      if (filteredRecords.length === 0) {{
        container.innerHTML = '<div class="empty-state">No matching tasks found.</div>';
        return;
      }}

      // Group by top-level project
      const byProject = {{}};
      filteredRecords.forEach(r => {{
        const p = r.top_level_project || 'Uncategorized';
        if (!byProject[p]) byProject[p] = [];
        byProject[p].push(r);
      }});

      const sortedTopProjs = Object.keys(byProject).sort();

      let html = '';
      for (const proj of sortedTopProjs) {{
        const tasks = byProject[proj];

        html += `
          <div class="day-group">
            <div class="day-header" onclick="toggleDayAccordion(this)">
              <div class="day-title">
                <span class="top-project-icon" style="margin-right: 4px;">📂</span>
                <span style="font-weight: 700;">${{escapeHtml(proj)}}</span>
                <span class="day-count-badge">${{tasks.length}} tasks</span>
              </div>
              <span class="day-toggle-icon">▼</span>
            </div>
            <div class="day-content" style="padding: 10px 14px;">
              ${{renderSubprojectHierarchy(tasks)}}
            </div>
          </div>
        `;
      }}
      container.innerHTML = html;
    }}

    // Render Table View
    function renderTableView() {{
      const tbody = document.getElementById('table-body');
      if (!tbody) return;

      if (filteredRecords.length === 0) {{
        tbody.innerHTML = '<tr><td colspan="7" class="empty-state">No records found</td></tr>';
        return;
      }}

      // Apply current sort
      const sorted = [...filteredRecords].sort((a, b) => {{
        const valA = (a[currentSortColumn] || '').toString();
        const valB = (b[currentSortColumn] || '').toString();
        return currentSortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }});

      let rows = '';
      sorted.slice(0, 250).forEach(r => {{
        const tags = (r.labels || []).map(l => `@${{l.replace(/^@/, '')}}`).join(', ');

        let taskCellContent = '';
        if (currentTaskStyle === 'nested' && r.task_levels && r.task_levels.length > 1) {{
          const ancestors = r.task_levels.slice(0, -1).map(l => renderMarkdown(l, true)).join(' › ');
          const leaf = renderMarkdown(r.task_levels[r.task_levels.length - 1], true);
          taskCellContent = `
            <div style="font-size: 11px; color: var(--text-dim); margin-bottom: 2px;">${{ancestors}}</div>
            <strong>${{leaf}}</strong>
          `;
        }} else {{
          taskCellContent = `<strong>${{renderMarkdown(r.task_path || '-', true)}}</strong>`;
        }}

        const projDisplay = (r.project_levels && r.project_levels.length > 0)
          ? r.project_levels.join(' › ')
          : (r.project_path || '-');

        rows += `
          <tr>
            <td style="font-family: monospace;">${{escapeHtml(r.date)}} ${{escapeHtml(r.time || '')}}</td>
            <td><span class="badge" style="background:var(--bg-hover);">${{escapeHtml(r.top_level_project || '-')}}</span></td>
            <td>${{escapeHtml(projDisplay)}}${{r.section ? ` <span class="section-tag">${{escapeHtml(r.section)}}</span>` : ''}}</td>
            <td>
              ${{taskCellContent}}
              ${{r.description ? `<div style="font-size:11px; color:var(--text-muted); margin-top:3px;">${{renderMarkdown(r.description)}}</div>` : ''}}
            </td>
            <td>${{r.priority ? `<span class="badge badge-${{r.priority.toLowerCase()}}">${{r.priority.toUpperCase()}}</span>` : '-'}}</td>
            <td>${{escapeHtml(tags || '-')}}</td>
            <td>${{r.due_status && r.due_status !== 'undated' ? `<span class="badge badge-${{r.due_status}}">${{escapeHtml(r.due_variance || r.due_date)}}</span>` : '-'}}</td>
          </tr>
        `;
      }});

      tbody.innerHTML = rows;
    }}

    function sortTable(column) {{
      if (currentSortColumn === column) {{
        currentSortAsc = !currentSortAsc;
      }} else {{
        currentSortColumn = column;
        currentSortAsc = false;
      }}
      renderTableView();
    }}

    // Interactive SVG Velocity Chart
    function renderTimelineChart() {{
      const svg = document.getElementById('timeline-chart');
      const tooltip = document.getElementById('chart-tooltip');
      if (!svg) return;

      const dateCounts = {{}};
      rawRecords.forEach(r => {{
        if (r.date) dateCounts[r.date] = (dateCounts[r.date] || 0) + 1;
      }});

      const dates = Object.keys(dateCounts).sort();
      if (dates.length === 0) {{
        svg.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="var(--text-muted)" font-size="12">No activity data</text>';
        return;
      }}

      const maxVal = Math.max(...Object.values(dateCounts), 1);
      const width = svg.clientWidth || 600;
      const height = svg.clientHeight || 180;
      const padLeft = 30;
      const padBottom = 25;
      const padTop = 15;
      const padRight = 15;
      const chartW = width - padLeft - padRight;
      const chartH = height - padTop - padBottom;

      const barWidth = Math.max(3, (chartW / dates.length) - 2);

      let svgContent = '';
      // Grid line
      svgContent += `<line x1="${{padLeft}}" y1="${{height - padBottom}}" x2="${{width - padRight}}" y2="${{height - padBottom}}" stroke="var(--border)" stroke-width="1" />`;

      dates.forEach((d, idx) => {{
        const count = dateCounts[d];
        const h = (count / maxVal) * chartH;
        const x = padLeft + (idx * (chartW / dates.length));
        const y = height - padBottom - h;
        const isSelected = activeDayFilter === d;

        svgContent += `
          <rect x="${{x}}" y="${{y}}" width="${{barWidth}}" height="${{h}}"
                rx="2"
                fill="${{isSelected ? '#ec4899' : 'var(--accent)'}}"
                opacity="${{isSelected ? '1' : '0.85'}}"
                style="cursor: pointer; transition: opacity 0.15s ease;"
                onmouseover="showChartTooltip(event, '${{d}}', ${{count}})"
                onmouseout="hideChartTooltip()"
                onclick="filterByDay('${{d}}')" />
        `;
      }});

      svg.innerHTML = svgContent;
    }}

    function showChartTooltip(evt, date, count) {{
      const tooltip = document.getElementById('chart-tooltip');
      if (!tooltip) return;
      tooltip.innerHTML = `<strong>${{date}}</strong>: ${{count}} tasks`;
      tooltip.style.left = `${{evt.pageX + 10}}px`;
      tooltip.style.top = `${{evt.pageY - 25}}px`;
      tooltip.style.opacity = '1';
    }}

    function hideChartTooltip() {{
      const tooltip = document.getElementById('chart-tooltip');
      if (tooltip) tooltip.style.opacity = '0';
    }}

    function filterByDay(date) {{
      if (activeDayFilter === date) {{
        activeDayFilter = null;
      }} else {{
        activeDayFilter = date;
      }}
      applyFilters();
    }}

    // Project Share Bars
    function renderProjectBars() {{
      const container = document.getElementById('project-bars');
      if (!container) return;

      const projCounts = {{}};
      filteredRecords.forEach(r => {{
        const p = r.top_level_project || 'Uncategorized';
        projCounts[p] = (projCounts[p] || 0) + 1;
      }});

      const total = filteredRecords.length || 1;
      const sorted = Object.entries(projCounts).sort((a, b) => b[1] - a[1]);

      let html = '';
      sorted.slice(0, 6).forEach(([proj, count]) => {{
        const pct = Math.round((count / total) * 100);
        html += `
          <div>
            <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 2px;">
              <span style="font-weight: 600; cursor: pointer; color: var(--accent);" onclick="filterByProject('${{escapeHtml(proj)}}')">${{escapeHtml(proj)}}</span>
              <span style="color: var(--text-muted);">${{count}} (${{pct}}%)</span>
            </div>
            <div style="width: 100%; height: 6px; background-color: var(--bg-hover); border-radius: 3px; overflow: hidden;">
              <div style="width: ${{pct}}%; height: 100%; background: linear-gradient(90deg, var(--accent), #a855f7); border-radius: 3px;"></div>
            </div>
          </div>
        `;
      }});

      container.innerHTML = html;
    }}

    function filterByProject(proj) {{
      document.getElementById('project-filter').value = proj;
      applyFilters();
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    function renderMarkdown(str, inlineOnly = false) {{
      if (!str) return '';
      let text = String(str);

      // 1. Escape HTML entities
      text = escapeHtml(text);

      // 2. Protect inline code `...`
      const tokens = [];
      text = text.replace(/`([^`]+)`/g, (match, code) => {{
        tokens.push(`<code>${{code}}</code>`);
        return `__MD_TOKEN_${{tokens.length - 1}}__`;
      }});

      // 3. Markdown links: [text](url)
      text = text.replace(/\\[([^\\]]+)\\]\\(([^)]+)\\)/g, (match, linkText, url) => {{
        const trimmedUrl = url.trim();
        const lowerUrl = trimmedUrl.toLowerCase();
        if (lowerUrl.startsWith('javascript:') || lowerUrl.startsWith('data:') || lowerUrl.startsWith('vbscript:')) {{
          return linkText;
        }}
        tokens.push(`<a href="${{trimmedUrl}}" target="_blank" rel="noopener noreferrer">${{linkText}}</a>`);
        return `__MD_TOKEN_${{tokens.length - 1}}__`;
      }});

      // 4. Autolink bare URLs: https://... or http://...
      text = text.replace(/(^|[\\s(])(https?:\\/\\/[^\\s)<>"]+)/g, (match, prefix, rawUrl) => {{
        let url = rawUrl;
        let trailingPunct = '';
        const punctMatch = url.match(/[.,;:!?]+$/);
        if (punctMatch) {{
          trailingPunct = punctMatch[0];
          url = url.slice(0, -trailingPunct.length);
        }}
        tokens.push(`<a href="${{url}}" target="_blank" rel="noopener noreferrer">${{url}}</a>`);
        return `${{prefix}}__MD_TOKEN_${{tokens.length - 1}}__${{trailingPunct}}`;
      }});

      // 5. Bold, Italic & Strikethrough
      text = text.replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>');
      text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');
      text = text.replace(/\\*([^*]+)\\*/g, '<em>$1</em>');
      text = text.replace(/(^|[^\\w])_([^_]+)_(?![\\w])/g, '$1<em>$2</em>');
      text = text.replace(/~~(.+?)~~/g, '<del>$1</del>');

      // 6. Restore protected tokens
      text = text.replace(/__MD_TOKEN_(\\d+)__/g, (match, index) => {{
        return tokens[parseInt(index, 10)] || match;
      }});

      if (inlineOnly) {{
        return text.replace(/\\n+/g, ' ');
      }}

      // 7. Multiline block rendering for descriptions (lists, paragraphs, line breaks)
      const lines = text.split('\n');
      const outBlocks = [];
      let inList = false;
      let listType = '';

      for (let i = 0; i < lines.length; i++) {{
        const line = lines[i];
        const ulMatch = line.match(/^\\s*[*-]\\s+(.+)$/);
        const olMatch = line.match(/^\\s*\\d+\\.\\s+(.+)$/);

        if (ulMatch) {{
          if (!inList || listType !== 'ul') {{
            if (inList) outBlocks.push(`</${{listType}}>`);
            outBlocks.push('<ul>');
            inList = true;
            listType = 'ul';
          }}
          outBlocks.push(`<li>${{ulMatch[1]}}</li>`);
        }} else if (olMatch) {{
          if (!inList || listType !== 'ol') {{
            if (inList) outBlocks.push(`</${{listType}}>`);
            outBlocks.push('<ol>');
            inList = true;
            listType = 'ol';
          }}
          outBlocks.push(`<li>${{olMatch[1]}}</li>`);
        }} else {{
          if (inList) {{
            outBlocks.push(`</${{listType}}>`);
            inList = false;
            listType = '';
          }}
          if (line.trim() === '') {{
            outBlocks.push('<div style="height: 4px;"></div>');
          }} else {{
            outBlocks.push(`<div>${{line}}</div>`);
          }}
        }}
      }}
      if (inList) {{
        outBlocks.push(`</${{listType}}>`);
      }}
      return outBlocks.join('');
    }}

    // Window Init
    window.addEventListener('DOMContentLoaded', () => {{
      initTheme();
      initProjectStyle();
      initTaskStyle();
      initFilterDropdowns();
      applyFilters();
    }});

    window.addEventListener('resize', () => {{
      renderTimelineChart();
    }});
  </script>
</body>
</html>
"""


def export_html(
    records: List[Dict[str, Any]],
    output_path: str,
    include_labels: bool = True,
    include_descriptions: bool = True,
    include_priorities: bool = True,
    include_due_dates: bool = True,
    title: str = "Todoist Trace - Activity Dashboard",
) -> None:
    """Generate and write interactive HTML dashboard to disk."""
    html_content = generate_html(
        records,
        include_labels=include_labels,
        include_descriptions=include_descriptions,
        include_priorities=include_priorities,
        include_due_dates=include_due_dates,
        title=title,
    )
    dest = Path(output_path).expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_content, encoding="utf-8")
