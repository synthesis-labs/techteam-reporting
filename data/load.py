"""
License allocation data loader (stub).

Reads raw tool exports from <month>/raw/ and writes standardised CSVs
to <month>/standardised/. See schema.md for the data model.

Usage:
    python load.py --month 2026-05
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator


SKILL_LEVEL_MAP = {
    "GRAD": "Graduate",
    "ASSOCIATE": "Associate",
    "SS": "Semi-skilled",
    "INTERMEDIATE": "Intermediate",
    "SENIOR": "Senior",
    "TECH": "Tech Lead",
    "PQM": "Mid-level Manager",
    "SM": "Senior Manager",
    "SPECIALIST": "Specialist",
    "PRINCIPAL": "Principal",
    "BU_HEAD": "BU Head",
    "DIR": "Director",
}

NBSP = "\xa0"


@dataclass
class Employee:
    employee_code: str
    first_name: str
    known_as: str
    last_name: str
    email: str
    job_title: str
    department: str
    operating_level: str
    skill_level: str


@dataclass
class Allocation:
    snapshot_date: str
    tool: str
    source_email: str
    source_name: str
    source_handle: str = ""
    employee_code: str = ""
    match_method: str = ""
    raw_role: str = ""
    raw_seat_tier: str = ""
    raw_usage: str = ""
    notes: str = ""


@dataclass
class Project:
    snapshot_date: str
    project_name: str
    client: str = ""
    bu: str = ""
    account_manager: str = ""
    project_manager: str = ""
    tech_lead: str = ""
    lifecycle: str = ""
    start_date: str = ""
    end_date: str = ""
    duration: str = ""
    overall_rating: str = ""
    quality: str = ""
    team_confidence: str = ""
    budget_health: str = ""
    delivery_health: str = ""
    team_wellbeing: str = ""
    customer_satisfaction: str = ""
    scope_health: str = ""
    billing: str = ""
    scope: str = ""
    budget: str = ""
    piia_review: str = ""
    milestones: str = ""
    documentation: str = ""
    linked_projects: str = ""
    high_care: str = ""
    budget_score: str = ""
    delivery_score: str = ""
    team_score: str = ""
    csat_score: str = ""
    scope_health_score: str = ""
    active: str = ""
    modified: str = ""
    modified_by: str = ""
    risk_issue_status: str = ""


@dataclass
class ProjectAIUsage:
    snapshot_date: str
    project_name: str
    ai_usage_tag: str


@dataclass
class Unmatched:
    snapshot_date: str
    tool: str
    source_email: str
    source_name: str
    source_handle: str
    reason: str
    suggested_employee_code: str = ""
    status: str = ""
    notes: str = ""


# ---------- helpers ----------------------------------------------------------


def strip_prefix(value: str) -> str:
    """Columns like 'OL - Senior' or 'TECH - Technology' -> text after ' - '."""
    if not value:
        return ""
    return value.split(" - ", 1)[1].strip() if " - " in value else value.strip()


def norm_email(email: str) -> str:
    return (email or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(email) and "@" in email and email != "0"


def norm_name(name: str) -> str:
    return " ".join((name or "").lower().split())


def parse_decimal_comma(value: str) -> str:
    """'4,80' -> '4.80'. Returns '' for blanks or '#Name?' errors."""
    if not value:
        return ""
    s = value.strip()
    if s.startswith("#") or s.lower() == "#name?":
        return ""
    return s.replace(",", ".") if "," in s else s


def parse_date(value: str) -> str:
    """'2026/05/07' or '2026/05/07 ' -> '2026-05-07'. '' if unparseable."""
    if not value:
        return ""
    s = value.strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return ""


def parse_bool(value: str) -> str:
    """'True'/'False' (case-insensitive) -> 'true'/'false'. Anything else -> ''."""
    s = (value or "").strip().lower()
    if s in ("true", "yes", "y", "1"):
        return "true"
    if s in ("false", "no", "n", "0"):
        return "false"
    return ""


def parse_int_or_blank(value: str) -> str:
    """'5' -> '5'. '#Name?' or '' -> ''."""
    if not value:
        return ""
    s = value.strip()
    if s.startswith("#"):
        return ""
    try:
        return str(int(float(s)))
    except ValueError:
        return ""


# ---------- employee master --------------------------------------------------


def load_employees(path: Path) -> list[Employee]:
    """Load and clean the employee master.

    TODO: confirm exact column names once a real export is in raw/employees.csv.
    The schema in CLAUDE.md says: Employee Code, First Name, Known As Name,
    Last Name, 'Email Addresss' (sic), Job Title (OL prefix), DEPARTMENT -
    Department (prefix), OL - Operating Level.
    """
    employees: list[Employee] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            ol_raw = (row.get("OL - Operating Level") or "").strip()
            ol_code = ol_raw.split(" - ", 1)[0].strip() if " - " in ol_raw else ol_raw
            employees.append(
                Employee(
                    employee_code=str(row.get("Employee Code") or "").strip(),
                    first_name=(row.get("First Name") or "").strip(),
                    known_as=(row.get("Known As Name") or "").strip(),
                    last_name=(row.get("Last Name") or "").strip(),
                    email=norm_email(row.get("Email Addresss") or row.get("Email Address") or ""),
                    job_title=strip_prefix(row.get("Job Title") or ""),
                    department=strip_prefix(row.get("DEPARTMENT - Department") or ""),
                    operating_level=ol_code,
                    skill_level=SKILL_LEVEL_MAP.get(ol_code, ol_code),
                )
            )
    return employees


# ---------- per-tool loaders -------------------------------------------------


def load_claude(path: Path, snapshot: str) -> Iterator[Allocation]:
    """Claude members export: Name, Email, Role, Status, Seat Tier."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            yield Allocation(
                snapshot_date=snapshot,
                tool="claude",
                source_email=norm_email(row.get("Email", "")),
                source_name=(row.get("Name") or "").strip(),
                raw_role=(row.get("Role") or "").strip(),
                raw_seat_tier=(row.get("Seat Tier") or "").strip(),
            )


def load_cursor(path: Path, snapshot: str) -> Iterator[Allocation]:
    """Cursor team export: Name, Email, Role, Included/Free/On-Demand Usage."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            usage = "/".join(
                [
                    (row.get("Included Usage") or "").strip(),
                    (row.get("Free Usage") or "").strip(),
                    (row.get("On-Demand Usage") or "").strip(),
                ]
            )
            yield Allocation(
                snapshot_date=snapshot,
                tool="cursor",
                source_email=norm_email(row.get("Email", "")),
                source_name=(row.get("Name") or "").strip(),
                raw_role=(row.get("Role") or "").strip(),
                raw_usage=usage,
            )


def load_chatgpt(path: Path, snapshot: str) -> Iterator[Allocation]:
    """ChatGPT export: alternating rows.

    Odd rows: 'Name / Role / Tool / Date'
    Even rows: email
    TODO: implement once a real export is available — likely needs to read raw
    lines (not csv.DictReader) and pair them.
    """
    raise NotImplementedError("ChatGPT loader pending real export sample")


def load_copilot(path: Path, snapshot: str) -> Iterator[Allocation]:
    """GitHub Copilot export: alternating rows.

    Non-@ rows: 'Name<NBSP>Handle' (separator is U+00A0).
    @ rows: email.
    TODO: implement once a real export is available. Handles will need to
    resolve via aliases.csv (source_type='handle').
    """
    raise NotImplementedError("Copilot loader pending real export sample")


def load_gemini(path: Path, snapshot: str) -> Iterator[Allocation]:
    """Gemini export with 'Email Address [Required]' column."""
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            email = row.get("Email Address [Required]") or row.get("Email") or ""
            yield Allocation(
                snapshot_date=snapshot,
                tool="gemini",
                source_email=norm_email(email),
                source_name=(row.get("Name") or "").strip(),
            )


def load_projects(path: Path, snapshot: str) -> tuple[list[Project], list[ProjectAIUsage]]:
    """PS Project Tracker — one row per project. Explodes AI Usage JSON into
    project_ai_usage rows."""
    projects: list[Project] = []
    usage: list[ProjectAIUsage] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("Project Name") or "").strip()
            if not name:
                continue
            projects.append(
                Project(
                    snapshot_date=snapshot,
                    project_name=name,
                    client=(row.get("Client") or "").strip(),
                    bu=(row.get("BU") or "").strip(),
                    account_manager=(row.get("Account Manager") or "").strip(),
                    project_manager=(row.get("Project Manager") or "").strip(),
                    tech_lead=(row.get("Tech Lead / Core Member") or "").strip(),
                    lifecycle=(row.get("Lifecycle") or "").strip(),
                    start_date=parse_date(row.get("Start Date") or ""),
                    end_date=parse_date(row.get("End Date") or ""),
                    duration=(row.get("Duration") or "").strip(),
                    overall_rating=parse_decimal_comma(row.get("OverallRating") or ""),
                    quality=(row.get("Quality") or "").strip(),
                    team_confidence=(row.get("Team Confidence") or "").strip(),
                    budget_health=(row.get("BudgetHealth") or "").strip(),
                    delivery_health=(row.get("DeliveryHealth") or "").strip(),
                    team_wellbeing=(row.get("TeamWellbeing") or "").strip(),
                    customer_satisfaction=(row.get("CustomerSatisfaction") or "").strip(),
                    scope_health=(row.get("ScopeHealth") or "").strip(),
                    billing=(row.get("Billing") or "").strip(),
                    scope=(row.get("Scope") or "").strip(),
                    budget=(row.get("Budget") or "").strip(),
                    piia_review=(row.get("PIIA Review") or "").strip(),
                    milestones=(row.get("Milestones") or "").strip(),
                    documentation=(row.get("Documentation") or "").strip(),
                    linked_projects=(row.get("Linked Projects") or "").strip(),
                    high_care=parse_bool(row.get("High Care") or ""),
                    budget_score=parse_int_or_blank(row.get("BudgetScore") or ""),
                    delivery_score=parse_int_or_blank(row.get("DeliveryScore") or ""),
                    team_score=parse_int_or_blank(row.get("TeamScore") or ""),
                    csat_score=parse_int_or_blank(row.get("CSATScore") or ""),
                    scope_health_score=parse_int_or_blank(row.get("ScopeHealthScore") or ""),
                    active=parse_bool(row.get("Active") or ""),
                    modified=parse_date(row.get("Modified") or ""),
                    modified_by=(row.get("Modified By") or "").strip(),
                    risk_issue_status=(row.get("RiskIssueStatus") or "").strip(),
                )
            )
            ai_raw = (row.get("AI Usage") or "").strip()
            if ai_raw:
                try:
                    tags = json.loads(ai_raw)
                    if isinstance(tags, list):
                        for tag in tags:
                            if isinstance(tag, str) and tag.strip():
                                usage.append(
                                    ProjectAIUsage(
                                        snapshot_date=snapshot,
                                        project_name=name,
                                        ai_usage_tag=tag.strip(),
                                    )
                                )
                except json.JSONDecodeError:
                    # Pass through as a single tag if not valid JSON
                    usage.append(
                        ProjectAIUsage(
                            snapshot_date=snapshot, project_name=name, ai_usage_tag=ai_raw
                        )
                    )
    return projects, usage


def _snake(label: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", (label or "").strip()).strip("_").lower()
    return s or "col"


def load_assessments(path: Path, snapshot: str, by_email: dict) -> list[dict]:
    """AI Maturity Self Assessment .xlsx — one row per response.

    Assumes the first sheet, first row = headers. Detects email and timestamp
    columns by name heuristics, joins to employees by email, passes other
    columns through with snake_case headers.
    """
    try:
        import openpyxl
    except ImportError:
        raise NotImplementedError("openpyxl required for load_assessments — pip install openpyxl")

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
    keys = [_snake(h) for h in headers]

    # Heuristics to locate special columns
    def find(*candidates: str) -> int | None:
        for i, k in enumerate(keys):
            if any(c in k for c in candidates):
                return i
        return None

    email_idx = find("email")
    time_idx = find("timestamp", "submitted", "completion_time", "start_time")
    level_idx = find("level", "maturity")

    out: list[dict] = []
    for raw in rows[1:]:
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in raw):
            continue
        email = norm_email(str(raw[email_idx])) if email_idx is not None and raw[email_idx] else ""
        submitted = ""
        if time_idx is not None and raw[time_idx] is not None:
            v = raw[time_idx]
            submitted = v.isoformat() if hasattr(v, "isoformat") else str(v)
        emp = by_email.get(email)
        record = {
            "snapshot_date": snapshot,
            "submitted_at": submitted,
            "submitted_email": email,
            "employee_code": emp.employee_code if emp else "",
            "match_method": "email" if emp else "unmatched",
            "self_level": str(raw[level_idx]) if level_idx is not None and raw[level_idx] is not None else "",
        }
        # Pass through remaining columns (skip the ones already extracted)
        skip = {i for i in (email_idx, time_idx, level_idx) if i is not None}
        for i, v in enumerate(raw):
            if i in skip:
                continue
            key = keys[i]
            if key in record:
                key = f"{key}_x"
            record[key] = "" if v is None else (v.isoformat() if hasattr(v, "isoformat") else str(v))
        out.append(record)
    return out


LOADERS: dict[str, Callable[[Path, str], Iterator[Allocation]]] = {
    "claude": load_claude,
    "cursor": load_cursor,
    "chatgpt": load_chatgpt,
    "copilot": load_copilot,
    "gemini": load_gemini,
}


# ---------- matching ---------------------------------------------------------


def load_aliases(path: Path) -> dict[tuple[str, str], str]:
    """(source_value, source_type) -> employee_code."""
    aliases: dict[tuple[str, str], str] = {}
    if not path.exists():
        return aliases
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["source_value"].strip().lower(), row["source_type"].strip().lower())
            aliases[key] = row["employee_code"].strip()
    return aliases


def build_indexes(employees: list[Employee]):
    by_email = {e.email: e for e in employees if is_valid_email(e.email)}
    by_full_name = {
        norm_name(f"{e.first_name} {e.last_name}"): e for e in employees if e.last_name
    }
    by_known_as_last = {
        norm_name(f"{e.known_as} {e.last_name}"): e
        for e in employees
        if e.known_as and e.last_name
    }
    return by_email, by_full_name, by_known_as_last


def resolve(
    alloc: Allocation,
    by_email,
    by_full_name,
    by_known_as_last,
    aliases,
) -> tuple[str, str]:
    """Return (employee_code, match_method). Empty employee_code means unmatched."""
    if alloc.source_email and alloc.source_email in by_email:
        return by_email[alloc.source_email].employee_code, "email"

    if alloc.source_email and (alloc.source_email, "email") in aliases:
        return aliases[(alloc.source_email, "email")], "alias"

    if alloc.source_handle and (alloc.source_handle.lower(), "handle") in aliases:
        return aliases[(alloc.source_handle.lower(), "handle")], "handle"

    name_key = norm_name(alloc.source_name)
    if name_key in by_full_name:
        return by_full_name[name_key].employee_code, "name"
    if name_key in by_known_as_last:
        return by_known_as_last[name_key].employee_code, "known_as"

    return "", "unmatched"


# ---------- write ------------------------------------------------------------


def write_csv(path: Path, rows: Iterable, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row) if hasattr(row, "__dataclass_fields__") else row)


# ---------- main -------------------------------------------------------------


def run(month_dir: Path, aliases_path: Path) -> None:
    raw = month_dir / "raw"
    out = month_dir / "standardised"
    snapshot = month_dir.name + "-01"

    employees = load_employees(raw / "employees.csv")
    aliases = load_aliases(aliases_path)
    by_email, by_full_name, by_known_as_last = build_indexes(employees)

    matched: list[Allocation] = []
    unmatched: list[Unmatched] = []

    for tool, loader in LOADERS.items():
        path = raw / f"{tool}.csv"
        if not path.exists():
            print(f"  skip {tool}: {path.name} not present")
            continue
        try:
            for alloc in loader(path, snapshot):
                code, method = resolve(alloc, by_email, by_full_name, by_known_as_last, aliases)
                alloc.employee_code = code
                alloc.match_method = method
                if code:
                    matched.append(alloc)
                else:
                    unmatched.append(
                        Unmatched(
                            snapshot_date=alloc.snapshot_date,
                            tool=alloc.tool,
                            source_email=alloc.source_email,
                            source_name=alloc.source_name,
                            source_handle=alloc.source_handle,
                            reason="no_match" if alloc.source_email or alloc.source_name else "handle_unresolved",
                        )
                    )
        except NotImplementedError as e:
            print(f"  TODO {tool}: {e}")

    write_csv(
        out / "employees.csv",
        employees,
        ["employee_code", "first_name", "known_as", "last_name", "email",
         "job_title", "department", "operating_level", "skill_level"],
    )
    write_csv(
        out / "license_allocations.csv",
        matched,
        ["snapshot_date", "tool", "source_email", "source_name", "source_handle",
         "employee_code", "match_method", "raw_role", "raw_seat_tier", "raw_usage", "notes"],
    )
    write_csv(
        out / "unmatched.csv",
        unmatched,
        ["snapshot_date", "tool", "source_email", "source_name", "source_handle",
         "reason", "suggested_employee_code", "status", "notes"],
    )

    # Projects + AI usage
    projects_path = raw / "projects.csv"
    projects: list[Project] = []
    ai_usage: list[ProjectAIUsage] = []
    if projects_path.exists():
        projects, ai_usage = load_projects(projects_path, snapshot)
        write_csv(
            out / "projects.csv",
            projects,
            [
                "snapshot_date", "project_name", "client", "bu", "account_manager",
                "project_manager", "tech_lead", "lifecycle", "start_date", "end_date",
                "duration", "overall_rating", "quality", "team_confidence",
                "budget_health", "delivery_health", "team_wellbeing",
                "customer_satisfaction", "scope_health", "billing", "scope", "budget",
                "piia_review", "milestones", "documentation", "linked_projects",
                "high_care", "budget_score", "delivery_score", "team_score",
                "csat_score", "scope_health_score", "active", "modified",
                "modified_by", "risk_issue_status",
            ],
        )
        write_csv(
            out / "project_ai_usage.csv",
            ai_usage,
            ["snapshot_date", "project_name", "ai_usage_tag"],
        )
    else:
        print("  skip projects: projects.csv not present")

    # Assessments
    assessments_path = raw / "assessments.xlsx"
    assessments: list[dict] = []
    if assessments_path.exists():
        try:
            assessments = load_assessments(assessments_path, snapshot, by_email)
            if assessments:
                fieldnames = list(assessments[0].keys())
                # Ensure standard columns come first
                lead = ["snapshot_date", "submitted_at", "submitted_email",
                        "employee_code", "match_method", "self_level"]
                ordered = [c for c in lead if c in fieldnames] + [c for c in fieldnames if c not in lead]
                with (out / "assessments.csv").open("w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=ordered)
                    w.writeheader()
                    w.writerows(assessments)
        except NotImplementedError as e:
            print(f"  TODO assessments: {e}")
    else:
        print("  skip assessments: assessments.xlsx not present")

    print(
        f"\nwrote {len(employees)} employees, {len(matched)} allocations, "
        f"{len(unmatched)} unmatched, {len(projects)} projects, "
        f"{len(ai_usage)} project_ai_usage, {len(assessments)} assessments"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="snapshot folder, e.g. 2026-05")
    parser.add_argument("--root", default=str(Path(__file__).parent), help="path to data/ folder")
    args = parser.parse_args()

    root = Path(args.root)
    run(month_dir=root / args.month, aliases_path=root / "aliases.csv")


if __name__ == "__main__":
    main()
