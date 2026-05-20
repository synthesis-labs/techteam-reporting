"""
Generate trends.md (long-term view) from data/history/*.csv produced by
data/aggregate.py.

Usage:
    python dashboard/build_trends.py
    python dashboard/build_trends.py --history-dir data/history --out dashboard/trends.md
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import plotly.graph_objects as go


TOOL_COLOR = {
    "claude": "#D97706",
    "cursor": "#0D6EFD",
    "chatgpt": "#198754",
    "copilot": "#495057",
    "gemini": "#8B44AC",
}
TOOL_ORDER = ["claude", "cursor", "chatgpt", "copilot", "gemini"]
TOOL_LABEL = {
    "claude": "Claude",
    "cursor": "Cursor",
    "chatgpt": "ChatGPT",
    "copilot": "Copilot",
    "gemini": "Gemini",
}
PRODUCTIVE_TAG_COLOR = "#16a34a"
OTHER_TAG_COLOR = "#94a3b8"
CHANGE_COLOR = {"new": "#16a34a", "lost": "#dc2626", "retained": "#0F3460"}


BASE_LAYOUT = dict(
    template="simple_white",
    font=dict(family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif", size=12, color="#1f2937"),
    margin=dict(l=50, r=20, t=40, b=50),
    plot_bgcolor="white",
    paper_bgcolor="white",
    hoverlabel=dict(bgcolor="#1A1A2E", font_color="white"),
    xaxis=dict(showgrid=False, linecolor="#ADB5BD"),
    yaxis=dict(gridcolor="#f1f5f9", linecolor="#ADB5BD", zeroline=False),
)


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def render(fig: go.Figure, div_id: str) -> str:
    return fig.to_html(
        include_plotlyjs=False,
        full_html=False,
        div_id=div_id,
        config={"displayModeBar": False, "responsive": True},
    )


def latest_kpis(kpis: list[dict]) -> dict:
    return kpis[-1] if kpis else {}


def prior_kpis(kpis: list[dict]) -> dict | None:
    return kpis[-2] if len(kpis) >= 2 else None


def kpi_card(value: str, label: str, sub: str) -> str:
    return (
        f'<div class="kpi"><div class="kpi-value">{value}</div>'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-sub">{sub}</div></div>'
    )


def delta(curr: float, prev: float | None, unit: str = "pp") -> str:
    if prev is None:
        return "first snapshot"
    d = curr - prev
    if abs(d) < 0.05:
        return "no change vs prior"
    sign = "+" if d > 0 else ""
    return f"{sign}{d:.1f}{unit} vs prior month"


def fig_adoption_over_time(kpis: list[dict]) -> go.Figure:
    fig = go.Figure(layout=BASE_LAYOUT)
    fig.add_trace(go.Scatter(
        x=[k["month"] for k in kpis],
        y=[float(k["license_adoption_pct"]) for k in kpis],
        mode="lines+markers",
        name="License adoption",
        line=dict(color="#0F3460", width=3),
        marker=dict(size=8),
        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=[k["month"] for k in kpis],
        y=[float(k["project_ai_pct"]) for k in kpis],
        mode="lines+markers",
        name="Projects using AI",
        line=dict(color="#16a34a", width=3, dash="dot"),
        marker=dict(size=8),
        hovertemplate="%{x}<br>%{y:.1f}%<extra></extra>",
    ))
    fig.update_layout(
        title=None,
        yaxis_title="% adoption",
        yaxis_range=[0, 100],
        legend=dict(orientation="h", y=-0.2, x=0),
        height=380,
    )
    return fig


def fig_tool_adoption(tool_rows: list[dict]) -> go.Figure:
    by_tool: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for r in tool_rows:
        by_tool[r["tool"]].append((r["month"], float(r["pct_of_employees"])))

    fig = go.Figure(layout=BASE_LAYOUT)
    for tool in TOOL_ORDER:
        series = sorted(by_tool.get(tool, []), key=lambda x: x[0])
        if not series:
            continue
        fig.add_trace(go.Scatter(
            x=[m for m, _ in series],
            y=[v for _, v in series],
            mode="lines+markers",
            name=TOOL_LABEL[tool],
            line=dict(color=TOOL_COLOR[tool], width=2.5),
            marker=dict(size=7),
            hovertemplate=f"{TOOL_LABEL[tool]}<br>%{{x}}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_layout(
        yaxis_title="% of employees",
        yaxis_range=[0, 100],
        legend=dict(orientation="h", y=-0.2, x=0),
        height=380,
    )
    return fig


def fig_dept_heatmap(dept_rows: list[dict]) -> go.Figure:
    months = sorted({r["month"] for r in dept_rows})
    by_dept: dict[str, dict[str, float]] = defaultdict(dict)
    dept_latest_head: dict[str, int] = {}
    for r in dept_rows:
        by_dept[r["department"]][r["month"]] = float(r["adoption_pct"])
        if r["month"] == months[-1]:
            dept_latest_head[r["department"]] = int(r["headcount"])

    depts = sorted(by_dept, key=lambda d: -dept_latest_head.get(d, 0))
    z = [[by_dept[d].get(m, None) for m in months] for d in depts]

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=months,
            y=depts,
            colorscale=[[0, "#fee2e2"], [0.45, "#fef3c7"], [0.65, "#dbeafe"], [0.85, "#dcfce7"], [1, "#16a34a"]],
            zmin=0,
            zmax=100,
            colorbar=dict(title="Adoption %", thickness=12),
            hovertemplate="%{y}<br>%{x}: %{z:.0f}%<extra></extra>",
        ),
        layout=BASE_LAYOUT,
    )
    fig.update_layout(
        xaxis=dict(side="top", showgrid=False),
        yaxis=dict(autorange="reversed"),
        height=max(320, 24 * len(depts) + 80),
        margin=dict(l=200, r=20, t=60, b=30),
    )
    return fig


def fig_tag_mix(tag_rows: list[dict]) -> go.Figure:
    months = sorted({r["month"] for r in tag_rows})
    tags = sorted({r["ai_usage_tag"] for r in tag_rows})
    productive = {r["ai_usage_tag"]: r["is_productive"] == "true" for r in tag_rows}

    by_tag: dict[str, dict[str, int]] = defaultdict(dict)
    for r in tag_rows:
        by_tag[r["ai_usage_tag"]][r["month"]] = int(r["tag_count"])

    fig = go.Figure(layout=BASE_LAYOUT)
    palette_productive = ["#16a34a", "#22c55e", "#15803d", "#65a30d"]
    palette_other = ["#94a3b8", "#cbd5e1", "#64748b"]
    pi, oi = 0, 0
    for tag in tags:
        if productive[tag]:
            color = palette_productive[pi % len(palette_productive)]
            pi += 1
        else:
            color = palette_other[oi % len(palette_other)]
            oi += 1
        fig.add_trace(go.Bar(
            x=months,
            y=[by_tag[tag].get(m, 0) for m in months],
            name=tag,
            marker_color=color,
            hovertemplate=f"{tag}<br>%{{x}}: %{{y}}<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        yaxis_title="tag count",
        legend=dict(orientation="h", y=-0.25, x=0),
        height=380,
    )
    return fig


def fig_churn(churn_rows: list[dict]) -> go.Figure:
    by_month_change: dict[tuple[str, str], int] = defaultdict(int)
    for r in churn_rows:
        by_month_change[(r["month"], r["change_type"])] += int(r["count"])

    months = sorted({m for m, _ in by_month_change})
    fig = go.Figure(layout=BASE_LAYOUT)
    for change in ["new", "retained", "lost"]:
        ys = [by_month_change.get((m, change), 0) for m in months]
        if change == "lost":
            ys = [-y for y in ys]
        fig.add_trace(go.Bar(
            x=months,
            y=ys,
            name=change.title(),
            marker_color=CHANGE_COLOR[change],
            hovertemplate=f"{change.title()}: %{{customdata}} licenses<extra></extra>",
            customdata=[abs(y) for y in ys],
        ))
    fig.update_layout(
        barmode="relative",
        yaxis_title="license seats (lost shown below zero)",
        legend=dict(orientation="h", y=-0.2, x=0),
        height=380,
    )
    return fig


def fig_assessments(assessment_rows: list[dict]) -> go.Figure:
    months = sorted({r["month"] for r in assessment_rows})
    levels = sorted({r["self_level"] for r in assessment_rows})
    by = {(r["month"], r["self_level"]): float(r["share"]) for r in assessment_rows}

    palette = ["#fee2e2", "#fef3c7", "#dbeafe", "#dcfce7", "#16a34a", "#9ca3af"]
    fig = go.Figure(layout=BASE_LAYOUT)
    for i, level in enumerate(levels):
        fig.add_trace(go.Bar(
            x=months,
            y=[by.get((m, level), 0) for m in months],
            name=level,
            marker_color=palette[i % len(palette)],
            hovertemplate=f"{level}<br>%{{x}}: %{{y:.0f}}%<extra></extra>",
        ))
    fig.update_layout(
        barmode="stack",
        yaxis_title="% of respondents",
        yaxis_range=[0, 100],
        legend=dict(orientation="h", y=-0.25, x=0),
        height=380,
    )
    return fig


PLOTLY_CDN = (
    '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js" charset="utf-8"></script>'
)


def build(history_dir: Path) -> str:
    kpis = read(history_dir / "monthly_kpis.csv")
    tool_rows = read(history_dir / "tool_adoption_by_month.csv")
    dept_rows = read(history_dir / "dept_adoption_by_month.csv")
    tag_rows = read(history_dir / "tag_usage_by_month.csv")
    churn_rows = read(history_dir / "license_churn.csv")
    assessment_rows = read(history_dir / "assessments_by_month.csv")

    if not kpis:
        raise SystemExit(f"No history found at {history_dir}. Run data/aggregate.py first.")

    months = [k["month"] for k in kpis]
    n_months = len(months)
    curr = latest_kpis(kpis)
    prev = prior_kpis(kpis)

    md: list[str] = []
    md.append("---")
    md.append('title: "AI Adoption Trends"')
    md.append(f'subtitle: "{months[0]} → {months[-1]}  ·  {n_months} snapshot{"s" if n_months != 1 else ""}"')
    md.append("output-file: dashboard")
    md.append("---")
    md.append("")
    md.append(PLOTLY_CDN)
    md.append("")
    md.append(
        f'<p class="doc-meta"><strong>Synthesis Software Technologies</strong>  ·  Technology Office  ·  '
        f'Long-term view  ·  latest: {curr["snapshot_date"]}  ·  '
        f'<a href="snapshot.html">current-month snapshot →</a></p>'
    )
    md.append("")

    # KPI tiles with deltas
    md.append('<div class="kpi-grid">')
    md.append(kpi_card(
        f'{float(curr["license_adoption_pct"]):.0f}%',
        "License adoption",
        delta(float(curr["license_adoption_pct"]),
              float(prev["license_adoption_pct"]) if prev else None),
    ))
    md.append(kpi_card(
        curr["total_license_seats"],
        "Total license seats",
        delta(int(curr["total_license_seats"]),
              int(prev["total_license_seats"]) if prev else None, unit=""),
    ))
    md.append(kpi_card(
        f'{float(curr["project_ai_pct"]):.0f}%',
        "Projects using AI",
        delta(float(curr["project_ai_pct"]),
              float(prev["project_ai_pct"]) if prev else None),
    ))
    md.append(kpi_card(
        curr["assessment_responses"],
        "Assessment responses",
        delta(int(curr["assessment_responses"]),
              int(prev["assessment_responses"]) if prev else None, unit=""),
    ))
    md.append("</div>")
    md.append("")

    single_month_note = (
        '<p class="note">Only one snapshot is loaded — trend lines need at least two months. '
        'Backfill older snapshots into <code>data/&lt;YYYY-MM&gt;/raw/</code> and re-run '
        '<code>python data/load.py</code> + <code>python data/aggregate.py</code> to populate history.</p>'
    )

    md.append("## Adoption over time")
    md.append("")
    if n_months >= 2:
        md.append(render(fig_adoption_over_time(kpis), "chart-adoption"))
    else:
        md.append(single_month_note)
    md.append("")

    md.append("## License adoption by tool")
    md.append("")
    if n_months >= 2:
        md.append(render(fig_tool_adoption(tool_rows), "chart-tools"))
    else:
        md.append(single_month_note)
    md.append("")

    md.append("## Adoption by department")
    md.append("")
    md.append(
        '<p>Heatmap of department adoption % across snapshots. Departments are sorted by '
        'latest headcount; cells are blank when a department wasn\'t present that month.</p>'
    )
    md.append(render(fig_dept_heatmap(dept_rows), "chart-dept"))
    md.append("")

    md.append("## Project AI usage")
    md.append("")
    md.append(
        '<p>Stacked tag counts from the PS Project Tracker\'s <code>AI Usage</code> field. '
        'Greens are productive tags (Research, Dev, CI/CD, Complete Feature); greys are '
        '<code>No AI Usage</code> / <code>To be determined</code>.</p>'
    )
    md.append(render(fig_tag_mix(tag_rows), "chart-tags"))
    md.append("")

    md.append("## License movement")
    md.append("")
    if churn_rows:
        md.append(
            '<p>New seats added this month vs seats lost (shown below zero) and seats '
            'retained from the prior month. A retained-heavy bar means stable adoption; '
            'a new-heavy bar means active rollout.</p>'
        )
        md.append(render(fig_churn(churn_rows), "chart-churn"))
    else:
        md.append(single_month_note)
    md.append("")

    md.append("## Self-assessed maturity")
    md.append("")
    if assessment_rows:
        md.append(
            '<p>Distribution of self-reported AI maturity levels across responses '
            'each month (as % of respondents).</p>'
        )
        md.append(render(fig_assessments(assessment_rows), "chart-assessments"))
    else:
        md.append(
            '<p class="note">No assessment responses loaded yet. Drop '
            '<code>assessments.xlsx</code> into <code>data/&lt;YYYY-MM&gt;/raw/</code> '
            'and re-run <code>data/load.py</code> + <code>data/aggregate.py</code>.</p>'
        )
    md.append("")

    md.append(
        f'<p class="footer">Generated from <code>data/history/</code>. '
        f'Covers {n_months} snapshot{"s" if n_months != 1 else ""} '
        f'({months[0]} → {months[-1]}). '
        f'Re-run <code>python data/aggregate.py</code> after refreshing any snapshot.</p>'
    )

    return "\n".join(md) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history-dir",
        default=str(Path(__file__).parent.parent / "data" / "history"),
        help="path to data/history/",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "trends.md"),
        help="output trends.md path",
    )
    args = parser.parse_args()

    content = build(Path(args.history_dir))
    out_path = Path(args.out)
    out_path.write_text(content, encoding="utf-8")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
