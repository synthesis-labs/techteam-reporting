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


TOOLS = [
    "chatgpt",
    "claude",
    "cursor",
    "gemini",
    "copilot",
    "github_copilot",
    "microsoft_copilot",
]
PRODUCTIVE_AI_TAGS = {
    "Research Mode",
    "AI for Development",
    "AI in CI/CD",
    "Complete Feature Built in AI",
}

# Map each AI Usage tag to a tier — mirrors the May 2026 internal report.
# A project carrying multiple tags is assigned the highest tier it qualifies
# for. L3 > L2 > L1 > L0 > TBD.
TIER_OF_TAG = {
    "AI in CI/CD": "L3",
    "Complete Feature Built in AI": "L3",
    "AI for Development": "L2",
    "Research Mode": "L1",
    "No AI Usage": "L0",
    "To be determined": "TBD",
}
TIER_ORDER = ["L3", "L2", "L1", "L0", "TBD"]
TIER_LABEL = {
    "L3": "L3 — CI/CD & Full AI",
    "L2": "L2 — AI for Development",
    "L1": "L1 — Research",
    "L0": "L0 — No AI",
    "TBD": "TBD",
}
TIER_RANK = {"L3": 4, "L2": 3, "L1": 2, "L0": 1, "TBD": 0}

# Project rating fields parsed as floats by load.py — used in ratings-by-tier.
RATING_FIELDS = [
    "overall_rating",
    "budget_score",
    "delivery_score",
    "team_score",
    "csat_score",
    "scope_health_score",
]

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
# Matches `standardised` (primary snapshot for a month) or `standardised-<suffix>`
# (alternate views of the same month — separate snapshot IDs, not merged).
STANDARDISED_RE = re.compile(r"^standardised(?:-(?P<suffix>[A-Za-z0-9][A-Za-z0-9_-]*))?$")


def project_tier(tags: set[str]) -> str:
    """Highest tier a project qualifies for given its set of AI Usage tags."""
    best = "TBD"
    best_rank = TIER_RANK["TBD"]
    for tag in tags:
        tier = TIER_OF_TAG.get(tag, "TBD")
        if TIER_RANK[tier] > best_rank:
            best = tier
            best_rank = TIER_RANK[tier]
    return best


def parse_float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def norm_email(value: str | None) -> str:
    return (value or "").strip().lower()


def norm_code(value: str | None) -> str:
    return (value or "").strip()


def employee_indexes(snapshot: dict) -> tuple[dict[str, dict], dict[str, str], set[str]]:
    """Build employee indexes keyed by email, with master fallback.

    Current snapshot rows override master rows on conflict.
    """
    by_email: dict[str, dict] = {}
    email_by_code: dict[str, str] = {}

    for row in snapshot.get("employees_master", []):
        email = norm_email(row.get("email"))
        if not email:
            continue
        by_email[email] = row
        code = norm_code(row.get("employee_code"))
        if code and code not in email_by_code:
            email_by_code[code] = email

    current_emails: set[str] = set()
    for row in snapshot.get("employees", []):
        email = norm_email(row.get("email"))
        if not email:
            continue
        current_emails.add(email)
        by_email[email] = row
        code = norm_code(row.get("employee_code"))
        if code:
            email_by_code[code] = email

    return by_email, email_by_code, current_emails


def allocation_email(row: dict, by_email: dict[str, dict], email_by_code: dict[str, str]) -> str | None:
    source_email = norm_email(row.get("source_email"))
    if source_email and source_email in by_email:
        return source_email

    code = norm_code(row.get("employee_code"))
    if code and code in email_by_code:
        return email_by_code[code]

    return None


def write(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def snapshot_id(month: str, suffix: str | None) -> str:
    """Combine YYYY-MM + optional standardised-* suffix into a snapshot ID.

    `standardised/` → `2026-04`; `standardised-final/` → `2026-04-final`.
    """
    return f"{month}-{suffix}" if suffix else month


def discover_snapshots(data_root: Path) -> list[tuple[str, Path]]:
    """Return (snapshot_id, standardised_dir) for every snapshot under data_root.

    A snapshot is any `standardised` or `standardised-<suffix>` folder under a
    YYYY-MM month directory. Alternate snapshots stand alongside the primary
    one (they are separate views of the same period, never merged).
    """
    out: list[tuple[str, Path]] = []
    for month_dir in sorted(data_root.iterdir()):
        if not (month_dir.is_dir() and MONTH_RE.match(month_dir.name)):
            continue
        for child in sorted(month_dir.iterdir()):
            if not child.is_dir():
                continue
            m = STANDARDISED_RE.match(child.name)
            if not m:
                continue
            out.append((snapshot_id(month_dir.name, m.group("suffix")), child))
    return out


def discover_months(data_root: Path) -> list[str]:
    """Backwards-compatible: returns sorted snapshot IDs (incl. suffixed ones)."""
    return [sid for sid, _ in discover_snapshots(data_root)]


def is_alternate_snapshot(snapshot_id_: str) -> bool:
    """Suffixed snapshots (e.g. 2026-04-final) are alternate views — they
    sit alongside the primary snapshot for the same month and don't belong
    on the month-to-month churn chain."""
    return not MONTH_RE.match(snapshot_id_)


def load_snapshot(snapshot_id_: str, std: Path) -> dict:
    return {
        "month": snapshot_id_,
        "employees": read(std / "employees.csv"),
        "allocations": read(std / "license_allocations.csv"),
        "unmatched": read(std / "unmatched.csv"),
        "projects": read(std / "projects.csv"),
        "ai_usage": read(std / "project_ai_usage.csv"),
        "assessments": read(std / "assessments.csv"),
    }


def load_month(data_root: Path, snapshot_id_: str) -> dict:
    """Load a snapshot by ID. Resolves `2026-04` → `2026-04/standardised/`
    and `2026-04-final` → `2026-04/standardised-final/`.
    """
    for sid, std in discover_snapshots(data_root):
        if sid == snapshot_id_:
            return load_snapshot(sid, std)
    raise FileNotFoundError(f"No snapshot {snapshot_id_!r} under {data_root}")


def licenses_by_employee(snapshot: dict) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    by_email, email_by_code, _ = employee_indexes(snapshot)
    for row in snapshot["allocations"]:
        email = allocation_email(row, by_email, email_by_code)
        if email and row.get("tool"):
            out[email].add(row["tool"])
    return out


def resolved_tool_counts(snapshot: dict) -> Counter:
    by_email, email_by_code, _ = employee_indexes(snapshot)
    counts: Counter = Counter()
    for row in snapshot["allocations"]:
        email = allocation_email(row, by_email, email_by_code)
        tool = row.get("tool")
        if email and tool:
            counts[tool] += 1
    return counts


def monthly_kpis(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        total_emp = len(s["employees"])
        _, _, current_emails = employee_indexes(s)
        lbe = licenses_by_employee(s)
        with_lic = len({email for email in lbe if email in current_emails})
        no_tools = total_emp - with_lic
        tool_counts = resolved_tool_counts(s)

        project_tags: dict[str, set[str]] = defaultdict(set)
        for r in s["ai_usage"]:
            project_tags[r["project_name"]].add(r["ai_usage_tag"])
        projects_using_ai = sum(
            1 for tags in project_tags.values() if tags & PRODUCTIVE_AI_TAGS
        )
        total_projects = len(s["projects"])
        active_projects = sum(1 for p in s["projects"] if p.get("active") == "true")

        # For alternate snapshots like `2026-04-final`, take the YYYY-MM prefix
        # for the calendar date (`2026-04-01`); the suffix is identity, not time.
        cal_month = s["month"][:7] if not MONTH_RE.match(s["month"]) else s["month"]
        rows.append({
            "month": s["month"],
            "snapshot_date": f"{cal_month}-01",
            "total_employees": total_emp,
            "employees_with_license": with_lic,
            "employees_no_tools": no_tools,
            "license_adoption_pct": round(with_lic / total_emp * 100, 2) if total_emp else 0,
            "no_tools_pct": round(no_tools / total_emp * 100, 2) if total_emp else 0,
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
    """Per-tool seat counts. Δ vs prior is computed against the prior **primary**
    snapshot — alternate snapshots (e.g. `2026-04-final`) don't shift the chain
    forward, so May still deltas against the original April."""
    rows = []
    prev_seats: dict[str, int] = {}
    for s in snapshots:
        total_emp = len(s["employees"])
        tool_counts = resolved_tool_counts(s)
        alt = is_alternate_snapshot(s["month"])
        for tool in TOOLS:
            seats = tool_counts.get(tool, 0)
            prev = prev_seats.get(tool)
            rows.append({
                "month": s["month"],
                "tool": tool,
                "seats": seats,
                "pct_of_employees": round(seats / total_emp * 100, 2) if total_emp else 0,
                "delta_vs_prior": "" if prev is None else seats - prev,
                "prev_seats": "" if prev is None else prev,
            })
            if not alt:
                prev_seats[tool] = seats
    return rows


def tier_by_month(snapshots: list[dict]) -> list[dict]:
    """One row per (month, tier). A project gets one tier (its highest)."""
    rows = []
    for s in snapshots:
        project_tags: dict[str, set[str]] = defaultdict(set)
        for r in s["ai_usage"]:
            project_tags[r["project_name"]].add(r["ai_usage_tag"])

        # Projects with no AI Usage rows at all → not represented in
        # project_ai_usage.csv but exist in projects.csv. Surface them as TBD.
        all_projects = {p["project_name"] for p in s["projects"]}
        for p in all_projects:
            project_tags.setdefault(p, set())

        tier_counts: Counter = Counter(
            project_tier(tags) for tags in project_tags.values()
        )
        total = sum(tier_counts.values())
        for tier in TIER_ORDER:
            count = tier_counts.get(tier, 0)
            rows.append({
                "month": s["month"],
                "tier": tier,
                "tier_label": TIER_LABEL[tier],
                "project_count": count,
                "share_of_projects": round(count / total * 100, 2) if total else 0,
            })
    return rows


def ratings_by_tier_by_month(snapshots: list[dict]) -> list[dict]:
    """Mean project ratings per AI tier per month. PII-safe — projects aggregated, not listed."""
    rows = []
    for s in snapshots:
        project_tags: dict[str, set[str]] = defaultdict(set)
        for r in s["ai_usage"]:
            project_tags[r["project_name"]].add(r["ai_usage_tag"])

        tier_of_project = {
            p["project_name"]: project_tier(project_tags.get(p["project_name"], set()))
            for p in s["projects"]
        }

        by_tier_field: dict[tuple[str, str], list[float]] = defaultdict(list)
        tier_proj_count: Counter = Counter()
        for p in s["projects"]:
            tier = tier_of_project[p["project_name"]]
            tier_proj_count[tier] += 1
            for field in RATING_FIELDS:
                v = parse_float(p.get(field))
                if v is not None:
                    by_tier_field[(tier, field)].append(v)

        for tier in TIER_ORDER:
            row = {
                "month": s["month"],
                "tier": tier,
                "tier_label": TIER_LABEL[tier],
                "projects_scored": tier_proj_count.get(tier, 0),
            }
            for field in RATING_FIELDS:
                m = mean(by_tier_field.get((tier, field), []))
                row[f"mean_{field}"] = "" if m is None else round(m, 2)
            rows.append(row)
    return rows


def dept_adoption_by_month(snapshots: list[dict]) -> list[dict]:
    rows = []
    for s in snapshots:
        dept_head: Counter = Counter()
        emp_dept: dict[str, str] = {}
        for emp in s["employees"]:
            dept = emp.get("business_unit") or emp.get("department") or "(no department)"
            dept_head[dept] += 1
            email = norm_email(emp.get("email"))
            if email:
                emp_dept[email] = dept

        lbe = licenses_by_employee(s)
        dept_with: dict[str, set[str]] = defaultdict(set)
        for email in lbe:
            if email in emp_dept:
                dept_with[emp_dept[email]].add(email)

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

    Alternate snapshots (e.g. `2026-04-final`) are skipped here: they are
    separate views of the same period, not points on the monthly churn chain.
    """
    primary_only = [s for s in snapshots if not is_alternate_snapshot(s["month"])]
    agg: Counter = Counter()
    prev_month_by: dict[str, str] = {}
    for i in range(1, len(primary_only)):
        prev, curr = primary_only[i - 1], primary_only[i]
        prev_lic = licenses_by_employee(prev)
        curr_lic = licenses_by_employee(curr)
        curr_by_email, _, _ = employee_indexes(curr)
        emp_dept = {
            email: (e.get("business_unit") or e.get("department") or "(no department)")
            for email, e in curr_by_email.items()
        }
        prev_month_by[curr["month"]] = prev["month"]

        emails = set(prev_lic) | set(curr_lic)
        for email in emails:
            prev_tools = prev_lic.get(email, set())
            curr_tools = curr_lic.get(email, set())
            dept = emp_dept.get(email, "(no department)")
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
    """One row per (month, self_level) — overall L0-L4 distribution."""
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


def _level_int(self_level: str) -> int | None:
    """Parse 'Level 2' / '2' → 2. Returns None if unparseable."""
    if not self_level:
        return None
    m = re.search(r"\d+", self_level)
    return int(m.group(0)) if m else None


def assessment_alignment_by_month(snapshots: list[dict]) -> list[dict]:
    """Cross-reference self-assessed maturity vs license allocations.

    Mirrors the ExCo report's alignment matrix:
      - aligned       — L2+ self-assessed AND has ≥1 tool licensed
      - add_tools     — L2 self-assessed AND has ≥1 tool licensed but no
                        higher-tier methodology signal (folded into aligned
                        here; reported separately by the snapshot view)
      - gap           — L3+ self-assessed AND has no tools (critical gap)
      - tools_no_assess — has tools but didn't take the assessment
      - assess_no_tools — took assessment at L0/L1 with no tools
      - no_signal     — neither assessment nor tools

    PII-safe: emits counts only.
    """
    rows = []
    for s in snapshots:
        if not s["assessments"]:
            continue
        _, email_by_code, current_emails = employee_indexes(s)
        lbe = licenses_by_employee(s)
        assess_by_email: dict[str, dict] = {}
        for r in s["assessments"]:
            email = norm_email(r.get("email"))
            if not email:
                code = norm_code(r.get("employee_code"))
                email = email_by_code.get(code, "")
            if email:
                assess_by_email[email] = r

        aligned = 0          # L2+ AND has tools
        add_tools = 0        # L2 AND has tools (subset of aligned; surfaced separately)
        gap = 0              # L3+ AND no tools
        l34_total = 0        # L3+ respondents (denominator for gap %)
        l2_with_tools = 0    # L2 with tools — "move the middle" cohort
        tools_no_assess = 0  # has tools, no assessment
        assess_no_tools = 0  # has assessment, no tools, L<3
        no_signal = 0        # neither tool nor assessment

        for email in current_emails:
            has_tools = email in lbe
            assess = assess_by_email.get(email)
            level = _level_int(assess.get("self_level", "")) if assess else None

            if assess and level is not None:
                if level >= 3:
                    l34_total += 1
                    if has_tools:
                        aligned += 1
                    else:
                        gap += 1
                elif level == 2:
                    if has_tools:
                        aligned += 1
                        add_tools += 1
                        l2_with_tools += 1
                    else:
                        assess_no_tools += 1
                else:  # L0 or L1
                    if has_tools:
                        # has tools but self-assesses very low; counts toward
                        # tools_no_assess bucket conceptually — leave as aligned
                        # excluded
                        pass
                    else:
                        assess_no_tools += 1
            else:
                if has_tools:
                    tools_no_assess += 1
                else:
                    no_signal += 1

        rows.append({
            "month": s["month"],
            "aligned": aligned,
            "add_tools_l2": add_tools,
            "gap_l34_no_tools": gap,
            "l34_total": l34_total,
            "l2_with_tools": l2_with_tools,
            "tools_no_assessment": tools_no_assess,
            "assessment_no_tools": assess_no_tools,
            "no_signal": no_signal,
        })
    return rows


def _is_developer(job_title: str) -> bool:
    """Heuristic: developer-track titles. Matches Engineer/Developer/Dev Lead."""
    if not job_title:
        return False
    t = job_title.lower()
    return any(k in t for k in ("engineer", "developer", "dev lead", "tech lead"))


def assessments_by_dept_by_month(snapshots: list[dict]) -> list[dict]:
    """One row per (month, department). Mean self-level + L0-L4 counts + dev/non-dev split."""
    rows = []
    for s in snapshots:
        if not s["assessments"]:
            continue
        by_email, email_by_code, _ = employee_indexes(s)
        dept_responses: dict[str, list[dict]] = defaultdict(list)
        for r in s["assessments"]:
            email = norm_email(r.get("email"))
            if not email:
                email = email_by_code.get(norm_code(r.get("employee_code")), "")
            emp = by_email.get(email)
            dept = (emp.get("business_unit") if emp else "") or (emp.get("department") if emp else "") or "(no department)"
            dept_responses[dept].append({**r, "_dept": dept, "_emp": emp})

        for dept, resps in dept_responses.items():
            level_counts: Counter = Counter()
            parsed_level_counts: Counter = Counter()
            level_sum = 0.0
            level_n = 0
            devs = 0
            non_devs = 0
            for r in resps:
                lvl_raw = (r.get("self_level") or "").strip()
                level_counts[lvl_raw or "(no response)"] += 1
                lvl = _level_int(lvl_raw)
                if lvl is not None:
                    level_sum += lvl
                    level_n += 1
                    parsed_level_counts[lvl] += 1
                if _is_developer((r.get("_emp") or {}).get("job_title", "")):
                    devs += 1
                else:
                    non_devs += 1

            row = {
                "month": s["month"],
                "department": dept,
                "responses": len(resps),
                "developers": devs,
                "non_developers": non_devs,
                "avg_level": round(level_sum / level_n, 2) if level_n else "",
            }
            for lvl in range(5):
                row[f"level_{lvl}"] = parsed_level_counts.get(lvl, 0)
            rows.append(row)
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

    master_rows = read(data_root / "employees_master.csv")
    snapshots = [load_month(data_root, m) for m in months]
    for s in snapshots:
        s["employees_master"] = master_rows
    print(f"Aggregating {len(months)} month(s): {', '.join(months)}")

    tables = {
        "monthly_kpis.csv": (monthly_kpis(snapshots), [
            "month", "snapshot_date", "total_employees", "employees_with_license",
            "employees_no_tools", "license_adoption_pct", "no_tools_pct",
            "total_license_seats", "tools_active",
            "total_projects", "active_projects", "projects_using_ai",
            "project_ai_pct", "unmatched_count", "assessment_responses",
        ]),
        "tool_adoption_by_month.csv": (tool_adoption_by_month(snapshots), [
            "month", "tool", "seats", "pct_of_employees",
            "prev_seats", "delta_vs_prior",
        ]),
        "tier_by_month.csv": (tier_by_month(snapshots), [
            "month", "tier", "tier_label", "project_count", "share_of_projects",
        ]),
        "ratings_by_tier_by_month.csv": (ratings_by_tier_by_month(snapshots), [
            "month", "tier", "tier_label", "projects_scored",
            "mean_overall_rating", "mean_budget_score", "mean_delivery_score",
            "mean_team_score", "mean_csat_score", "mean_scope_health_score",
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
        "assessments_by_dept_by_month.csv": (assessments_by_dept_by_month(snapshots), [
            "month", "department", "responses", "developers", "non_developers",
            "avg_level", "level_0", "level_1", "level_2", "level_3", "level_4",
        ]),
        "assessment_alignment_by_month.csv": (assessment_alignment_by_month(snapshots), [
            "month", "aligned", "add_tools_l2", "gap_l34_no_tools", "l34_total",
            "l2_with_tools", "tools_no_assessment", "assessment_no_tools",
            "no_signal",
        ]),
    }

    for name, (rows, fields) in tables.items():
        write(out / name, rows, fields)
        print(f"  wrote {out / name} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
