from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Dict, Iterable, List,Any
from datetime import datetime, timedelta, date, time
from typing import Optional

@dataclass
class Employee:
    name: str
    aliases: List[str]
    base: float = 50.0
    switch_override: Optional[str] = None  # NEW

def load_employees(path: str = "employees.json") -> List[Employee]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out = []
    for item in data:
        out.append(Employee(
            name=item["name"],
            aliases=item.get("aliases", []),
            base=float(item.get("base", 50.0)),
            switch_override=item.get("switch_override")  # may be None
        ))
    return out

def match_baristas(summary: str, attendees: Iterable, employees: List[Employee]) -> List[Employee]:
    """Match employees by attendee email (preferred) or aliases in event title."""
    found: Dict[str, Employee] = {}
    text = summary or ""

    # Normalize attendee emails whether list[str] or list[dict]
    att_emails = []
    for a in (attendees or []):
        if isinstance(a, str):
            att_emails.append(a.lower())
        elif isinstance(a, dict):
            email = (a.get("email") or "").lower()
            if email:
                att_emails.append(email)

    for emp in employees:
        # attendee email match
        for email in att_emails:
            if email and any(email == alias.lower() for alias in emp.aliases):
                found[emp.name] = emp
                break
        # title alias match
        if emp.name not in found:
            for alias in emp.aliases + [emp.name]:
                if re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
                    found[emp.name] = emp
                    break
    return list(found.values())

def _overlap_minutes(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end <= start:
        return 0
    return int((end - start).total_seconds() // 60)

# -------- Naive datetime helpers (no timezones) --------

def _parse_dt(dt_iso: str) -> datetime:
    """Return a naive datetime from an ISO string (handles 'Z' UTC)."""
    if not dt_iso:
        raise ValueError("Empty datetime string")

    # All-day events: 'YYYY-MM-DD'
    if len(dt_iso) == 10 and dt_iso[4] == '-' and dt_iso[7] == '-':
        return datetime.fromisoformat(dt_iso)  # midnight local (naive)

    s = dt_iso.strip()
    # Normalize trailing Z to RFC 3339 offset so fromisoformat can parse
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'

    dt = datetime.fromisoformat(s)  # may contain offset
    if dt.tzinfo:
        # Keep behavior consistent with your existing code: use naive
        # (drop tzinfo without converting). If you prefer localize/convert,
        # we can switch, but this matches prior logic.
        dt = dt.replace(tzinfo=None)
    return dt

def _on_duty_at(ts: datetime, ev_start: str, ev_end: str) -> bool:
    s = _parse_dt(ev_start)
    e = _parse_dt(ev_end)
    return s <= ts < e

def _localize(d: date, t: time) -> datetime:
    # produce naive dt for date d at time t
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second)

def _crew_covering(events: List[Dict], employees: List[Employee], ts: datetime) -> List[Employee]:
    crew: Dict[str, Employee] = {}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        if not assignees:
            continue
        if _on_duty_at(ts, e.get("start", ""), e.get("end", "")):
            for emp in assignees:
                crew[emp.name] = emp
    return list(crew.values())

# --------------- Core computation ----------------
def compute_payouts(
    events: List[Dict],
    employees: List[Employee],
    tz_name: str = "",
    # per-day CC tips: "YYYY-MM-DD" -> float
    per_day_cc_open_map: Dict[str, float] | None = None,
    per_day_cc_close_map: Dict[str, float] | None = None,
    open_str: str = "08:00",
    switch_str: str = "14:00",
    close_str: str = "21:00",
):
    per_day_cc_open_map = per_day_cc_open_map or {}
    per_day_cc_close_map = per_day_cc_close_map or {}

    emp_by_name = {e.name: e for e in employees}
    emp_names = [e.name for e in employees]

    base_pay = {emp.name: 0.0 for emp in employees}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        for emp in assignees:
            base_pay[emp.name] += float(emp_by_name[emp.name].base)

    if events:
        starts = [_parse_dt(e["start"]) for e in events if "start" in e]
        ends   = [_parse_dt(e["end"])   for e in events if "end" in e]
        start_day = min(starts).date()
        end_day   = (max(ends) + timedelta(days=1)).date()
    else:
        today = datetime.now().date()
        start_day, end_day = today, today + timedelta(days=1)

    days_count = max(1, (end_day - start_day).days)

    OPEN   = time.fromisoformat(open_str)
    SWITCH = time.fromisoformat(switch_str)
    CLOSE  = time.fromisoformat(close_str)

    tips_cc = {emp.name: 0.0 for emp in employees}
    schedule_rows = []

    d = start_day
    while d < end_day:
        t_open   = _localize(d, OPEN)
        t_switch = _localize(d, SWITCH)
        t_close  = _localize(d, CLOSE)

        open_window_crew = {e.name: e for e in _crew_covering(events, employees, t_open)}
        sample_hour = max(OPEN.hour, min(SWITCH.hour - 1, 23))
        t_sample_m  = _localize(d, time(sample_hour, 30))
        for e in _crew_covering(events, employees, t_sample_m):
            open_window_crew[e.name] = e
        open_window_crew = list(open_window_crew.values())

        close_window_crew = {e.name: e for e in _crew_covering(events, employees, t_switch)}
        for e in _crew_covering(events, employees, t_close):
            close_window_crew[e.name] = e
        close_window_crew = list(close_window_crew.values())

        # (Optional) per-employee switch_override block goes here if you added it
        # ... keep your override adjustment here ...

        # Per-day pools (no averaging): use exactly what you enter for this date
        day_key = d.isoformat()
        day_cc_open  = float(per_day_cc_open_map.get(day_key, 0.0))
        day_cc_close = float(per_day_cc_close_map.get(day_key, 0.0))

        if open_window_crew and day_cc_open:
            share = day_cc_open / len(open_window_crew)
            for emp in open_window_crew:
                tips_cc[emp.name] += share

        if close_window_crew and day_cc_close:
            share = day_cc_close / len(close_window_crew)
            for emp in close_window_crew:
                tips_cc[emp.name] += share

        # schedule matrix
        cell = {name: "" for name in emp_names}
        shared_open  = len(open_window_crew)  > 1
        shared_close = len(close_window_crew) > 1
        for e in open_window_crew:
            cell[e.name] += ("O*" if shared_open else "O")
        for e in close_window_crew:
            cell[e.name] += ("/" if cell[e.name] else "")
            cell[e.name] += ("C*" if shared_close else "C")
        schedule_rows.append({"date": d.isoformat(), "cells": cell})

        d += timedelta(days=1)

    rows = []
    for emp in employees:
        tip_total = tips_cc[emp.name]
        base_plus_split = round(base_pay[emp.name] + tip_total, 2)
        rows.append({
            "name": emp.name,
            "base_pay": round(base_pay[emp.name], 2),
            "tips_cc": round(tip_total, 2),
            "tips": round(tip_total, 2),
            "base_plus_split": base_plus_split,
            "total": base_plus_split,
        })
    rows.sort(key=lambda r: r["name"].lower())

    summary = {
        "days": days_count,
        "total_base": round(sum(r["base_pay"] for r in rows), 2),
        "total_cc": round(sum(r["tips_cc"] for r in rows), 2),
        "total_tips": round(sum(r["tips"] for r in rows), 2),
        "grand_total": round(sum(r["total"] for r in rows), 2),
        "schedule_headers": emp_names,
        "schedule_rows": schedule_rows,
    }
    return rows, summary

