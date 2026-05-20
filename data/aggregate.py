"""
Aggregate every monthly snapshot under data/<YYYY-MM>/standardised/ into a set
of long-format history tables in data/history/. The trends dashboard reads
these — never the per-month CSVs directly.

Usage:
    python data/aggregate.py
    python data/aggregate.py --data-root data --out data/history
"""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


TOOLS = ["claude", "cursor", "chatgpt", "copilot", "gemini"]
PRODUCTIVE_AI_TAGS = {
    "Research Mode",
    "AI for Development",
    "AI in CI/CD",
    "Complete Feature Built in AI",
}
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def write(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def discover_months(data_root: Path) -> list[str]:
    return sorted(
        d.name for d in data_root.iterdir()
        if d.is_dir() and MONTH_RE.match(d.name)
        and (d / "standardised").is_dir()
    )


def load_month(data_root: Path, month: str) -> dict:
    std = data_root / month / "standardised"
    return {
        "month": month,
        "employees": read(std / "employees.csv"),
        "allocations": read(std / "license_allocations.csv"),
        "unmatched": read(std / "unmatched.csv"),
        "projects": read(std / "projects.csv"),
        "ai_usage": read(std / "project_ai_usage.csv"),
        "assessments": read(std / "assessments.csv"),
    }


def licenses_by_employee(allocations: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for row in allocations:
        if row.get("employee_code"):
            out[row["employee_code"]].add(row["tool"])
    return out


def monthly_kpis(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        total_emp = len(s["employees"])
        lbe = licenses_by_employee(s["allocations"])
        with_lic = len(lbe)
        tool_counts = Counter(r["tool"] for r in s["allocations"] if r.get("employee_code"))

        project_tags: dict[str, set[str]] = defaultdict(set)
        for r in s["ai_usage"]:
            project_tags[r["project_name"]].add(r["ai_usage_tag"])
        projects_using_ai = sum(
            1 for tags in project_tags.values() if tags & PRODUCTIVE_AI_TAGS
        )
        total_projects = len(s["projects"])
        active_projects = sum(1 for p in s["projects"] if p.get("active") == "true")

        rows.append({
            "month": s["month"],
            "snapshot_date": f"{s['month']}-01",
            "total_employees": total_emp,
            "employees_with_license": with_lic,
            "license_adoption_pct": round(with_lic / total_emp * 100, 2) if total_emp else 0,
            "total_license_seats": sum(tool_counts.values()),
            "tools_active": sum(1 for t in TOOLS if tool_counts.get(t, 0) > 0),
            "total_projects": total_projects,
            "active_projects": active_projects,
            "projects_using_ai": projects_using_ai,
            "project_ai_pct": round(projects_using_ai / total_projects * 100, 2) if total_projects else 0,
            "unmatched_count": len(s["unmatched"]),
            "assessment_responses": len(s["assessments"]),
        })
    return rows


def tool_adoption_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        total_emp = len(s["employees"])
        tool_counts = Counter(
            r["tool"] for r in s["allocations"] if r.get("employee_code")
        )
        for tool in TOOLS:
            seats = tool_counts.get(tool, 0)
            rows.append({
                "month": s["month"],
                "tool": tool,
                "seats": seats,
                "pct_of_employees": round(seats / total_emp * 100, 2) if total_emp else 0,
            })
    return rows


def dept_adoption_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        dept_head: Counter = Counter()
        emp_dept: dict[str, str] = {}
        for emp in s["employees"]:
            dept = emp.get("department") or "(no department)"
            dept_head[dept] += 1
            emp_dept[emp["employee_code"]] = dept

        lbe = licenses_by_employee(s["allocations"])
        dept_with: dict[str, set[str]] = defaultdict(set)
        for code in lbe:
            if code in emp_dept:
                dept_with[emp_dept[code]].add(code)

        for dept, head in dept_head.items():
            with_lic = len(dept_with.get(dept, set()))
            rows.append({
                "month": s["month"],
                "department": dept,
                "headcount": head,
                "with_license": with_lic,
                "adoption_pct": round(with_lic / head * 100, 2) if head else 0,
            })
    return rows


def tag_usage_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        counts = Counter(r["ai_usage_tag"] for r in s["ai_usage"])
        total = sum(counts.values())
        for tag, count in counts.items():
            rows.append({
                "month": s["month"],
                "ai_usage_tag": tag,
                "tag_count": count,
                "share_of_tags": round(count / total * 100, 2) if total else 0,
                "is_productive": "true" if tag in PRODUCTIVE_AI_TAGS else "false",
            })
    return rows


def bu_ai_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        project_tags: dict[str, set[str]] = defaultdict(set)
        for r in s["ai_usage"]:
            project_tags[r["project_name"]].add(r["ai_usage_tag"])
        bu_total: Counter = Counter()
        bu_ai: Counter = Counter()
        for p in s["projects"]:
            bu = p.get("bu") or "(no bu)"
            bu_total[bu] += 1
            if project_tags.get(p["project_name"], set()) & PRODUCTIVE_AI_TAGS:
                bu_ai[bu] += 1
        for bu, total in bu_total.items():
            ai = bu_ai.get(bu, 0)
            rows.append({
                "month": s["month"],
                "bu": bu,
                "total_projects": total,
                "using_ai": ai,
                "pct_using_ai": round(ai / total * 100, 2) if total else 0,
            })
    return rows


def license_churn(snapshots: list[dict]) -> list[dict]:
    """Pre-aggregated: one row per (month, change_type, tool, department).

    Per-employee detail is deliberately omitted — this table is published
    publicly, so it must not allow reconstruction of individual license events.
    """
    agg: Counter = Counter()
    prev_month_by: dict[str, str] = {}
    for i in range(1, len(snapshots)):
        prev, curr = snapshots[i - 1], snapshots[i]
        prev_lic = licenses_by_employee(prev["allocations"])
        curr_lic = licenses_by_employee(curr["allocations"])
        emp_dept = {
            e["employee_code"]: e.get("department") or "(no department)"
            for e in curr["employees"]
        }
        prev_month_by[curr["month"]] = prev["month"]

        codes = set(prev_lic) | set(curr_lic)
        for code in codes:
            prev_tools = prev_lic.get(code, set())
            curr_tools = curr_lic.get(code, set())
            dept = emp_dept.get(code, "(no department)")
            for tool in prev_tools | curr_tools:
                in_prev = tool in prev_tools
                in_curr = tool in curr_tools
                if in_prev and in_curr:
                    change = "retained"
                elif in_curr:
                    change = "new"
                else:
                    change = "lost"
                agg[(curr["month"], change, tool, dept)] += 1

    return [
        {
            "month": month,
            "prev_month": prev_month_by[month],
            "change_type": change,
            "tool": tool,
            "department": dept,
            "count": count,
        }
        for (month, change, tool, dept), count in sorted(agg.items())
    ]


def assessments_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        if not s["assessments"]:
            continue
        levels = Counter(
            (r.get("self_level") or "(no response)") for r in s["assessments"]
        )
        total = sum(levels.values())
        for level, count in levels.items():
            rows.append({
                "month": s["month"],
                "self_level": level,
                "count": count,
                "share": round(count / total * 100, 2) if total else 0,
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-root",
        default=str(Path(__file__).parent),
        help="path to data/ folder",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).parent / "history"),
        help="output directory for history CSVs",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    out = Path(args.out)

    months = discover_months(data_root)
    if not months:
        raise SystemExit(f"No YYYY-MM snapshots found under {data_root}")

    snapshots = [load_month(data_root, m) for m in months]
    print(f"Aggregating {len(months)} month(s): {', '.join(months)}")

    tables = {
        "monthly_kpis.csv": (monthly_kpis(snapshots), [
            "month", "snapshot_date", "total_employees", "employees_with_license",
            "license_adoption_pct", "total_license_seats", "tools_active",
            "total_projects", "active_projects", "projects_using_ai",
            "project_ai_pct", "unmatched_count", "assessment_responses",
        ]),
        "tool_adoption_by_month.csv": (tool_adoption_by_month(snapshots), [
            "month", "tool", "seats", "pct_of_employees",
        ]),
        "dept_adoption_by_month.csv": (dept_adoption_by_month(snapshots), [
            "month", "department", "headcount", "with_license", "adoption_pct",
        ]),
        "tag_usage_by_month.csv": (tag_usage_by_month(snapshots), [
            "month", "ai_usage_tag", "tag_count", "share_of_tags", "is_productive",
        ]),
        "bu_ai_by_month.csv": (bu_ai_by_month(snapshots), [
            "month", "bu", "total_projects", "using_ai", "pct_using_ai",
        ]),
        "license_churn.csv": (license_churn(snapshots), [
            "month", "prev_month", "change_type", "tool", "department", "count",
        ]),
        "assessments_by_month.csv": (assessments_by_month(snapshots), [
            "month", "self_level", "count", "share",
        ]),
    }

    for name, (rows, fields) in tables.items():
        write(out / name, rows, fields)
        print(f"  wrote {out / name} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
