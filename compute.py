from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Dict, Iterable, List
from datetime import datetime, timedelta, date, time

@dataclass
class Employee:
    name: str
    aliases: List[str]

def load_employees(path: str = "employees.json") -> List[Employee]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [Employee(**item) for item in data]

def match_baristas(summary: str, attendees: Iterable[str], employees: List[Employee]) -> List[Employee]:
    """Match employees by attendee email (preferred) or aliases in event title."""
    found: Dict[str, Employee] = {}
    text = summary or ""
    for emp in employees:
        # attendee email match
        for email in attendees:
            if email and email.lower() in [a.lower() for a in emp.aliases]:
                found[emp.name] = emp
                break
        # title alias match
        if emp.name not in found:
            for alias in emp.aliases + [emp.name]:
                if re.search(rf"\b{re.escape(alias)}\b", text, re.IGNORECASE):
                    found[emp.name] = emp
                    break
    return list(found.values())

# -------- Naive datetime helpers (no timezones) --------
def _parse_dt(dt_iso: str) -> datetime:
    """Return a naive datetime (strip tz if present)."""
    if len(dt_iso) == 10:  # YYYY-MM-DD (all-day)
        return datetime.fromisoformat(dt_iso)  # midnight
    dt = datetime.fromisoformat(dt_iso)  # may contain offset
    if dt.tzinfo:
        dt = dt.replace(tzinfo=None)  # strip offset
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
    tz_name: str = "",                 # accepted but not used (keeps compatibility)
    flat_per_shift: float = 50.0,
    morning_tips_total: float = 0.0,   # across the selected range
    evening_tips_total: float = 0.0,   # across the selected range
    open_str: str = "09:00",
    switch_str: str = "14:00",
    close_str: str = "21:00",
):
    """
    Base pay: EACH barista earns flat_per_shift for every event they are assigned to.
    Tips by time slots per day:
      - Morning slot [OPEN, SWITCH): morning_tips_total split evenly per day in range,
        then split equally among whoever is on-duty in that slot that day.
      - Evening slot [SWITCH, CLOSE]: same behavior for evening_tips_total.
    Opener/Closer: whoever is on-duty exactly at OPEN and CLOSE timestamps.
    """

    # 1) Base pay per event
    base_pay: Dict[str, float] = {emp.name: 0.0 for emp in employees}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        if not assignees:
            continue
        for emp in assignees:
            base_pay[emp.name] += flat_per_shift

    # 2) Determine date span from events
    if events:
        starts = [_parse_dt(e["start"]) for e in events if "start" in e]
        ends   = [_parse_dt(e["end"])   for e in events if "end" in e]
        start_day = min(starts).date()
        end_day   = (max(ends) + timedelta(days=1)).date()  # exclusive end
    else:
        today = datetime.now().date()
        start_day, end_day = today, today + timedelta(days=1)

    days_count = max(1, (end_day - start_day).days)

    OPEN   = time.fromisoformat(open_str)
    SWITCH = time.fromisoformat(switch_str)
    CLOSE  = time.fromisoformat(close_str)

    tips: Dict[str, float] = {emp.name: 0.0 for emp in employees}
    open_cnt: Dict[str, int] = {emp.name: 0 for emp in employees}
    close_cnt: Dict[str, int] = {emp.name: 0 for emp in employees}

    # Precompute per-day pools
    per_day_morning = (morning_tips_total / days_count) if morning_tips_total else 0.0
    per_day_evening = (evening_tips_total / days_count) if evening_tips_total else 0.0

    d = start_day
    while d < end_day:
        t_open   = _localize(d, OPEN)
        t_switch = _localize(d, SWITCH)
        t_close  = _localize(d, CLOSE)

        # opener / closer
        openers = _crew_covering(events, employees, t_open)
        closers = _crew_covering(events, employees, t_close)
        for emp in openers:
            open_cnt[emp.name] += 1
        for emp in closers:
            close_cnt[emp.name] += 1

        # morning crew: check at OPEN and one sample before SWITCH (if possible)
        morning_crew = {e.name: e for e in _crew_covering(events, employees, t_open)}
        sample_hour = max(OPEN.hour, min(SWITCH.hour - 1, 23))  # simple sample
        sample_min  = 30
        t_sample_m = _localize(d, time(sample_hour, sample_min))
        for e in _crew_covering(events, employees, t_sample_m):
            morning_crew[e.name] = e
        morning_crew = list(morning_crew.values())

        # evening crew: check at SWITCH and CLOSE
        evening_crew = {e.name: e for e in _crew_covering(events, employees, t_switch)}
        for e in _crew_covering(events, employees, t_close):
            evening_crew[e.name] = e
        evening_crew = list(evening_crew.values())

        # distribute per-day tips
        if morning_crew and per_day_morning:
            share = per_day_morning / len(morning_crew)
            for emp in morning_crew:
                tips[emp.name] += share
        if evening_crew and per_day_evening:
            share = per_day_evening / len(evening_crew)
            for emp in evening_crew:
                tips[emp.name] += share

        d += timedelta(days=1)

    # Build rows
    rows = []
    for emp in employees:
        total = round(base_pay[emp.name] + tips[emp.name], 2)
        rows.append({
            "name": emp.name,
            "open_shifts": open_cnt[emp.name],
            "close_shifts": close_cnt[emp.name],
            "base_pay": round(base_pay[emp.name], 2),
            "tips": round(tips[emp.name], 2),
            "total": total,
        })
    rows.sort(key=lambda r: r["name"].lower())

    summary = {
        "days": days_count,
        "total_base": round(sum(r["base_pay"] for r in rows), 2),
        "total_tips": round(sum(r["tips"] for r in rows), 2),
        "grand_total": round(sum(r["total"] for r in rows), 2),
    }
    return rows, summary