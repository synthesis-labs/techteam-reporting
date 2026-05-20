"""
Generate one snapshot-<YYYY-MM>.md per month under data/, and the
_quarto.yml that wires them into a Quarto website with a sidebar.

Usage:
    python build.py                    # all months
    python build.py --month 2026-05    # just one (for testing)
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


TOOLS = ["claude", "cursor", "chatgpt", "copilot", "gemini"]
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")

TIER_ORDER = ["L3", "L2", "L1", "L0", "TBD"]
TIER_KLASS = {  # CSS hooks for tier-coloured bars
    "L3": "tier-l3",
    "L2": "tier-l2",
    "L1": "tier-l1",
    "L0": "tier-l0",
    "TBD": "tier-tbd",
}
TOOL_DISPLAY = {
    "claude": "Claude",
    "cursor": "Cursor",
    "chatgpt": "ChatGPT",
    "copilot": "GitHub Copilot",
    "gemini": "Gemini",
}
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


def _filter_history(rows: list[dict], month: str) -> list[dict]:
    return [r for r in rows if r.get("month") == month]


def build(month: str, root: Path, history_dir: Path | None = None) -> str:
    std = root / month / "standardised"
    employees = read(std / "employees.csv")
    allocations = read(std / "license_allocations.csv")
    unmatched = read(std / "unmatched.csv")
    projects = read(std / "projects.csv")
    ai_usage = read(std / "project_ai_usage.csv")
    assessments = read(std / "assessments.csv")

    # Cross-cutting history (deltas, tier rollups, ratings-by-tier).
    # These are produced by data/aggregate.py.
    hist = history_dir if history_dir is not None else root / "history"
    tool_history = _filter_history(read(hist / "tool_adoption_by_month.csv"), month)
    tier_history = _filter_history(read(hist / "tier_by_month.csv"), month)
    ratings_history = _filter_history(read(hist / "ratings_by_tier_by_month.csv"), month)
    assessments_by_month = _filter_history(read(hist / "assessments_by_month.csv"), month)
    assessments_by_dept = _filter_history(read(hist / "assessments_by_dept_by_month.csv"), month)

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
    md.append(f'title: "Snapshot — {month}"')
    md.append(f'subtitle: "{snapshot_label}  ·  {total_employees} employees"')
    md.append(f"output-file: snapshot-{month}")
    md.append("---")
    md.append("")
    md.append(
        f'<p class="doc-meta"><strong>Synthesis Software Technologies</strong>  ·  Technology Office  ·  '
        f'Snapshot {snapshot_label}  ·  '
        f'<a href="index.html">long-term trends →</a></p>'
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

    # License allocation by tool (now with month-over-month delta)
    md.append("## License allocation by tool")
    md.append("")
    delta_by_tool = {r["tool"]: r for r in tool_history}
    md.append('<table class="adoption-table">')
    md.append(
        "<thead><tr><th>Tool</th><th>Licensed</th><th>% workforce</th>"
        "<th>Prior month</th><th>Δ</th></tr></thead>"
    )
    md.append("<tbody>")
    for tool, n, pct in tool_rows:
        h = delta_by_tool.get(tool, {})
        prev = h.get("prev_seats", "")
        delta_raw = h.get("delta_vs_prior", "")
        if delta_raw == "" or delta_raw is None:
            delta_html = '<span class="delta-none">—</span>'
        else:
            try:
                d = int(delta_raw)
                if d > 0:
                    delta_html = f'<span class="delta-up">▲ {d}</span>'
                elif d < 0:
                    delta_html = f'<span class="delta-down">▼ {abs(d)}</span>'
                else:
                    delta_html = '<span class="delta-flat">±0</span>'
            except (TypeError, ValueError):
                delta_html = '<span class="delta-none">—</span>'
        md.append(
            f'<tr><td>{TOOL_DISPLAY[tool]}</td><td>{n}</td>'
            f'<td>{pct:.1f}%</td><td>{prev or "—"}</td><td>{delta_html}</td></tr>'
        )
    md.append("</tbody></table>")
    md.append("")
    md.append(
        f'<p class="note">Counts reflect resolved licenses only — {len(unmatched)} '
        f"unmatched rows are excluded (see Data quality below). Δ compares to the prior "
        f"snapshot loaded into <code>data/history/</code>.</p>"
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

    # Project AI tier (L0-L3) — each project assigned its highest qualifying tier
    md.append("## Project AI maturity by tier")
    md.append("")
    md.append(
        f'<p>Each project is assigned to one tier — the highest it qualifies for '
        f'based on its <code>AI Usage</code> tags. <strong>L3</strong> is '
        f'CI/CD-embedded or full feature in AI; <strong>L2</strong> is AI for '
        f'development; <strong>L1</strong> is research-only; <strong>L0</strong> '
        f'is no AI; <strong>TBD</strong> are projects pending classification.</p>'
    )
    md.append("")
    tier_by = {r["tier"]: r for r in tier_history}
    tier_total = sum(int(tier_by.get(t, {}).get("project_count", 0)) for t in TIER_ORDER)
    md.append('<div class="bar-block">')
    for tier in TIER_ORDER:
        h = tier_by.get(tier, {})
        count = int(h.get("project_count", 0))
        label = h.get("tier_label", tier)
        pct = (count / tier_total * 100) if tier_total else 0
        md.append(bar(pct, label, count, tier_total, TIER_KLASS[tier]))
    md.append("</div>")
    md.append("")

    # Project ratings by tier — supports the "is AI helping?" conversation
    if any(int(r.get("projects_scored", 0)) for r in ratings_history):
        md.append("## Project performance by AI tier")
        md.append("")
        md.append(
            '<p>Mean project ratings within each tier. Useful for the "are AI-heavy '
            'projects delivering better?" question. Means are over projects with a '
            'numeric rating in that field; blank cells mean no scored projects.</p>'
        )
        md.append("")
        md.append('<table class="adoption-table">')
        md.append(
            "<thead><tr><th>Tier</th><th>Projects</th>"
            "<th>Overall</th><th>Budget</th><th>Delivery</th>"
            "<th>Team</th><th>CSAT</th></tr></thead>"
        )
        md.append("<tbody>")
        ratings_by = {r["tier"]: r for r in ratings_history}
        for tier in TIER_ORDER:
            r = ratings_by.get(tier, {})
            n = r.get("projects_scored", 0)
            if not int(n or 0):
                continue
            cells = [
                r.get("mean_overall_rating", ""),
                r.get("mean_budget_score", ""),
                r.get("mean_delivery_score", ""),
                r.get("mean_team_score", ""),
                r.get("mean_csat_score", ""),
            ]
            cells = [f"{float(c):.2f}" if c not in ("", None) else "—" for c in cells]
            md.append(
                f'<tr><td>{r.get("tier_label", tier)}</td><td>{n}</td>'
                + "".join(f"<td>{c}</td>" for c in cells)
                + "</tr>"
            )
        md.append("</tbody></table>")
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

    # Self-Assessment — AI Maturity (L0-L4)
    md.append("## Self-assessed AI maturity")
    md.append("")
    if assessments:
        total_resp = len(assessments)
        level_dist = sorted(
            ((r["self_level"], int(r["count"]), float(r["share"])) for r in assessments_by_month),
            key=lambda x: x[0],
        )
        md.append(
            f'<p><strong>{total_resp} responses</strong> from the AI Maturity '
            f'Self-Assessment. Bars show the share of respondents at each '
            f'self-assigned maturity level (L0 = no AI familiarity, '
            f'L4 = embeds AI in their workflow).</p>'
        )
        md.append("")
        md.append('<div class="bar-block">')
        for level, count, share in level_dist:
            md.append(bar(share, level, count, total_resp, "tier-l2"))
        md.append("</div>")
        md.append("")

        # Per-department breakdown
        if assessments_by_dept:
            md.append('<table class="adoption-table">')
            md.append(
                "<thead><tr><th>Department</th><th>Responses</th>"
                "<th>Avg level</th><th>Developers</th>"
                "<th>L0</th><th>L1</th><th>L2</th><th>L3</th><th>L4</th></tr></thead>"
            )
            md.append("<tbody>")
            sorted_dept = sorted(
                assessments_by_dept, key=lambda r: -int(r.get("responses", 0))
            )
            for r in sorted_dept:
                md.append(
                    f'<tr><td>{r["department"]}</td>'
                    f'<td>{r["responses"]}</td>'
                    f'<td>{r.get("avg_level", "—")}</td>'
                    f'<td>{r["developers"]}/{int(r["developers"])+int(r["non_developers"])}</td>'
                    f'<td>{r["level_0"]}</td><td>{r["level_1"]}</td>'
                    f'<td>{r["level_2"]}</td><td>{r["level_3"]}</td>'
                    f'<td>{r["level_4"]}</td></tr>'
                )
            md.append("</tbody></table>")
            md.append("")
    else:
        md.append(
            '<p class="note">No AI Maturity Self-Assessment responses loaded for '
            'this snapshot yet. Drop <code>assessments.xlsx</code> into the private '
            'repo\'s <code>&lt;YYYY-MM&gt;/raw/</code> and re-run the loader to '
            'populate this section.</p>'
        )
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
        f'<div class="dq-card"><div class="dq-value">{len(assessments)}</div>'
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


def discover_months(data_root: Path) -> list[str]:
    return sorted(
        d.name for d in data_root.iterdir()
        if d.is_dir() and MONTH_RE.match(d.name)
        and (d / "standardised").is_dir()
    )


def write_quarto_yml(months_newest_first: list[str], out: Path) -> None:
    """Generate _quarto.yml with a website sidebar listing Trends + every snapshot."""
    lines = [
        "# Auto-generated by dashboard/build.py — do not edit by hand.",
        "project:",
        "  type: website",
        "  output-dir: ../dist/dashboard",
        "  render:",
        "    - trends.md",
    ]
    for m in months_newest_first:
        lines.append(f"    - snapshot-{m}.md")

    lines += [
        "",
        "website:",
        '  title: "AI Adoption Dashboard"',
        "  sidebar:",
        "    style: docked",
        "    border: true",
        "    search: false",
        "    contents:",
        '      - text: "Trends"',
        "        href: index.html",
        '      - section: "Snapshots"',
        "        contents:",
    ]
    for m in months_newest_first:
        lines.append(f'          - text: "{m}"')
        lines.append(f"            href: snapshot-{m}.html")

    lines += [
        "",
        "format:",
        "  html:",
        "    theme: default",
        "    css: style.css",
        "    toc: false",
        "    page-layout: full",
    ]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--month",
        help="build just this month (otherwise build all months found under data/)",
    )
    parser.add_argument(
        "--data-root",
        default=str(Path(__file__).parent.parent / "data"),
        help="path to data/ folder",
    )
    parser.add_argument(
        "--dashboard-dir",
        default=str(Path(__file__).parent),
        help="output directory for snapshot-<month>.md and _quarto.yml",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    dashboard_dir = Path(args.dashboard_dir)

    if args.month:
        months = [args.month]
    else:
        months = discover_months(data_root)
        if not months:
            raise SystemExit(f"No YYYY-MM snapshots found under {data_root}")

    for m in months:
        content = build(m, data_root)
        out_path = dashboard_dir / f"snapshot-{m}.md"
        out_path.write_text(content, encoding="utf-8")
        print(f"  wrote {out_path}")

    # Regenerate _quarto.yml only when doing a full build. (A single-month
    # build is for one-off testing and shouldn't change the sidebar.)
    if not args.month:
        write_quarto_yml(sorted(months, reverse=True), dashboard_dir / "_quarto.yml")
        print(f"  wrote {dashboard_dir / '_quarto.yml'}")


if __name__ == "__main__":
    main()
