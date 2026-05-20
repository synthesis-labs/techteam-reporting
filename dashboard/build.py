"""
Generate dashboard.md from the standardised CSVs for a given month snapshot.

Usage:
    python build.py --month 2026-05
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


TOOLS = ["claude", "cursor", "chatgpt", "copilot", "gemini"]
PRODUCTIVE_AI_TAGS = {
    "Research Mode",
    "AI for Development",
    "AI in CI/CD",
    "Complete Feature Built in AI",
}


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def adoption_tier(pct: float) -> str:
    if pct >= 85:
        return "tier-excellent"
    if pct >= 65:
        return "tier-good"
    if pct >= 45:
        return "tier-fair"
    return "tier-poor"


def bar(pct: float, label: str, count: int, total: int, klass: str = "") -> str:
    width = max(0, min(100, pct))
    return (
        f'<div class="bar-row {klass}">'
        f'<span class="bar-label">{label}</span>'
        f'<div class="bar-track"><div class="bar-fill" style="width:{width:.1f}%"></div></div>'
        f'<span class="bar-value">{count} <span class="bar-pct">({pct:.0f}%)</span></span>'
        f"</div>"
    )


def build(month: str, root: Path) -> str:
    std = root / month / "standardised"
    employees = read(std / "employees.csv")
    allocations = read(std / "license_allocations.csv")
    unmatched = read(std / "unmatched.csv")
    projects = read(std / "projects.csv")
    ai_usage = read(std / "project_ai_usage.csv")

    total_employees = len(employees)

    # License adoption per employee
    licenses_by_employee: dict[str, set[str]] = defaultdict(set)
    for row in allocations:
        if row.get("employee_code"):
            licenses_by_employee[row["employee_code"]].add(row["tool"])
    employees_with_license = len(licenses_by_employee)
    license_adoption_pct = (employees_with_license / total_employees * 100) if total_employees else 0

    # Per-tool counts
    tool_counts = Counter(row["tool"] for row in allocations)
    tool_rows = []
    for tool in TOOLS:
        n = tool_counts.get(tool, 0)
        pct = (n / total_employees * 100) if total_employees else 0
        tool_rows.append((tool, n, pct))

    # Per-department adoption
    dept_headcount: Counter = Counter()
    dept_with_license: dict[str, set[str]] = defaultdict(set)
    emp_dept: dict[str, str] = {}
    for emp in employees:
        dept = emp.get("department") or "(no department)"
        dept_headcount[dept] += 1
        emp_dept[emp["employee_code"]] = dept
    for code, tools in licenses_by_employee.items():
        if code in emp_dept:
            dept_with_license[emp_dept[code]].add(code)

    dept_rows = []
    for dept, head in sorted(dept_headcount.items(), key=lambda kv: -kv[1]):
        with_lic = len(dept_with_license.get(dept, set()))
        pct = (with_lic / head * 100) if head else 0
        dept_rows.append((dept, head, with_lic, pct))

    # Project AI usage
    total_projects = len(projects)
    active_projects = sum(1 for p in projects if p.get("active") == "true")

    project_tags: dict[str, set[str]] = defaultdict(set)
    for row in ai_usage:
        project_tags[row["project_name"]].add(row["ai_usage_tag"])

    projects_using_ai = sum(
        1 for tags in project_tags.values() if tags & PRODUCTIVE_AI_TAGS
    )
    project_ai_pct = (projects_using_ai / total_projects * 100) if total_projects else 0

    tag_counts = Counter(row["ai_usage_tag"] for row in ai_usage)

    # BU breakdown of AI-using projects
    bu_total: Counter = Counter()
    bu_ai: Counter = Counter()
    for p in projects:
        bu = p.get("bu") or "(no bu)"
        bu_total[bu] += 1
        if project_tags.get(p["project_name"], set()) & PRODUCTIVE_AI_TAGS:
            bu_ai[bu] += 1

    bu_rows = []
    for bu, total in sorted(bu_total.items(), key=lambda kv: -kv[1]):
        ai = bu_ai.get(bu, 0)
        pct = (ai / total * 100) if total else 0
        bu_rows.append((bu, total, ai, pct))

    # Build markdown
    snapshot_label = f"{month}-01"

    md: list[str] = []
    md.append("---")
    md.append('title: "AI Adoption Snapshot"')
    md.append(f'subtitle: "Snapshot: {snapshot_label}"')
    md.append("---")
    md.append("")
    md.append(
        f'<p class="doc-meta"><strong>Synthesis Software Technologies</strong>  ·  Technology Office  ·  '
        f'Snapshot {snapshot_label}  ·  {total_employees} employees  ·  '
        f'<a href="dashboard.html">long-term trends →</a></p>'
    )
    md.append("")

    # Headline KPIs
    md.append('<div class="kpi-grid">')
    md.append(
        f'<div class="kpi"><div class="kpi-value">{license_adoption_pct:.0f}%</div>'
        f'<div class="kpi-label">License adoption</div>'
        f'<div class="kpi-sub">{employees_with_license} of {total_employees} employees</div></div>'
    )
    md.append(
        f'<div class="kpi"><div class="kpi-value">{len(allocations)}</div>'
        f'<div class="kpi-label">Total license seats</div>'
        f'<div class="kpi-sub">across {sum(1 for _,n,_ in tool_rows if n>0)} tools</div></div>'
    )
    md.append(
        f'<div class="kpi"><div class="kpi-value">{project_ai_pct:.0f}%</div>'
        f'<div class="kpi-label">Projects using AI</div>'
        f'<div class="kpi-sub">{projects_using_ai} of {total_projects} projects</div></div>'
    )
    md.append(
        f'<div class="kpi"><div class="kpi-value">{active_projects}</div>'
        f'<div class="kpi-label">Active projects</div>'
        f'<div class="kpi-sub">{total_projects} total tracked</div></div>'
    )
    md.append("</div>")
    md.append("")

    # License allocation by tool
    md.append("## License allocation by tool")
    md.append("")
    md.append('<div class="bar-block">')
    for tool, n, pct in tool_rows:
        klass = f"tool-{tool}"
        md.append(bar(pct, tool.title() if tool != "chatgpt" else "ChatGPT", n, total_employees, klass))
    md.append("</div>")
    md.append("")
    md.append(
        f'<p class="note">Counts reflect resolved licenses only — {len(unmatched)} '
        f"unmatched rows are excluded (see Data quality below).</p>"
    )
    md.append("")

    # Department adoption
    md.append("## Adoption by department")
    md.append("")
    md.append('<table class="adoption-table">')
    md.append("<thead><tr><th>Department</th><th>Headcount</th><th>With license</th><th>Adoption</th></tr></thead>")
    md.append("<tbody>")
    for dept, head, with_lic, pct in dept_rows:
        tier = adoption_tier(pct)
        md.append(
            f'<tr><td>{dept}</td><td>{head}</td><td>{with_lic}</td>'
            f'<td><span class="pct-pill {tier}">{pct:.0f}%</span></td></tr>'
        )
    md.append("</tbody></table>")
    md.append("")

    # Project AI usage
    md.append("## Project AI usage")
    md.append("")
    md.append(
        f'<p>Across <strong>{total_projects} projects</strong>, the '
        f"<code>AI Usage</code> field on the PS Project Tracker carries "
        f"<strong>{sum(tag_counts.values())} tags</strong>. A project can carry "
        f"multiple tags; counts below are tags, not projects.</p>"
    )
    md.append("")
    md.append('<div class="bar-block">')
    sorted_tags = sorted(tag_counts.items(), key=lambda kv: -kv[1])
    total_tags = sum(tag_counts.values())
    for tag, count in sorted_tags:
        pct = (count / total_tags * 100) if total_tags else 0
        klass = "tag-productive" if tag in PRODUCTIVE_AI_TAGS else "tag-other"
        md.append(bar(pct, tag, count, total_tags, klass))
    md.append("</div>")
    md.append("")

    # BU breakdown
    md.append("## AI-using projects by BU")
    md.append("")
    md.append('<table class="adoption-table">')
    md.append("<thead><tr><th>Business Unit</th><th>Projects</th><th>Using AI</th><th>%</th></tr></thead>")
    md.append("<tbody>")
    for bu, total, ai, pct in bu_rows:
        tier = adoption_tier(pct)
        md.append(
            f"<tr><td>{bu}</td><td>{total}</td><td>{ai}</td>"
            f'<td><span class="pct-pill {tier}">{pct:.0f}%</span></td></tr>'
        )
    md.append("</tbody></table>")
    md.append("")

    # Data quality
    md.append("## Data quality")
    md.append("")
    md.append('<div class="dq-grid">')
    md.append(
        f'<div class="dq-card"><div class="dq-value">{len(unmatched)}</div>'
        f'<div class="dq-label">Unmatched license rows</div>'
        f'<div class="dq-sub">Tool emails not found in master — needs alias resolution</div></div>'
    )
    pending_tools = sum(1 for t in TOOLS if t not in tool_counts)
    md.append(
        f'<div class="dq-card"><div class="dq-value">{pending_tools}</div>'
        f'<div class="dq-label">Tools awaiting export</div>'
        f'<div class="dq-sub">ChatGPT, Copilot, Gemini — not yet loaded for this snapshot</div></div>'
    )
    md.append(
        f'<div class="dq-card"><div class="dq-value">0</div>'
        f'<div class="dq-label">Assessment responses</div>'
        f'<div class="dq-sub">AI Maturity Self Assessment — not yet loaded</div></div>'
    )
    md.append("</div>")
    md.append("")

    md.append(
        f'<p class="footer">Generated from <code>data/{month}/standardised/</code>. '
        f"Re-run <code>python dashboard/build.py --month {month}</code> after refreshing data.</p>"
    )

    return "\n".join(md) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="snapshot folder, e.g. 2026-05")
    parser.add_argument(
        "--data-root",
        default=str(Path(__file__).parent.parent / "data"),
        help="path to data/ folder",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "snapshot.md"),
        help="output snapshot.md path",
    )
    args = parser.parse_args()

    content = build(args.month, Path(args.data_root))
    out_path = Path(args.out)
    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
