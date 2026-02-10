from __future__ import annotations
import json, re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Any
from datetime import datetime, timedelta, date, time
from typing import Optional
from collections import defaultdict

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

def _parse_dt(dt_iso: str, tz_name: str = "America/Chicago") -> datetime:
    """Return a naive datetime from an ISO string, converted to local timezone."""
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
        # Convert to local timezone and make naive
        from zoneinfo import ZoneInfo
        local_tz = ZoneInfo(tz_name)
        dt = dt.astimezone(local_tz).replace(tzinfo=None)
    return dt

def _on_duty_at(ts: datetime, ev_start: str, ev_end: str, tz_name: str = "America/Chicago") -> bool:
    s = _parse_dt(ev_start, tz_name)
    e = _parse_dt(ev_end, tz_name)
    return s <= ts < e

def _localize(d: date, t: time) -> datetime:
    # produce naive dt for date d at time t
    return datetime(d.year, d.month, d.day, t.hour, t.minute, t.second)

def _crew_covering(events: List[Dict], employees: List[Employee], ts: datetime, tz_name: str = "America/Chicago") -> List[Employee]:
    crew: Dict[str, Employee] = {}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        if not assignees:
            continue
        if _on_duty_at(ts, e.get("start", ""), e.get("end", ""), tz_name):
            for emp in assignees:
                crew[emp.name] = emp
    return list(crew.values())

def _crew_covering_window(events: List[Dict], employees: List[Employee], window_start: datetime, window_end: datetime, tz_name: str = "America/Chicago") -> List[Employee]:
    """Find employees whose shifts overlap with the given time window."""
    crew: Dict[str, Employee] = {}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        if not assignees:
            continue
        
        # Parse event start and end times with timezone conversion
        event_start = _parse_dt(e.get("start", ""), tz_name)
        event_end = _parse_dt(e.get("end", ""), tz_name)
        
        # Check if the event overlaps with the time window
        # An event overlaps if it starts before the window ends and ends after the window starts
        if event_start < window_end and event_end > window_start:
            for emp in assignees:
                crew[emp.name] = emp
    return list(crew.values())

def _crew_hours_in_window(events: List[Dict], employees: List[Employee], window_start: datetime, window_end: datetime, tz_name: str = "America/Chicago") -> Dict[str, float]:
    """Calculate hours worked by each employee within the given time window.
    
    Returns a dictionary mapping employee name to hours worked (as float).
    This enables weighted tip distribution based on actual time worked.
    """
    hours_by_emp: Dict[str, float] = {}
    
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        if not assignees:
            continue
        
        # Parse event start and end times with timezone conversion
        event_start = _parse_dt(e.get("start", ""), tz_name)
        event_end = _parse_dt(e.get("end", ""), tz_name)
        
        # Calculate overlap minutes with the window
        overlap_mins = _overlap_minutes(event_start, event_end, window_start, window_end)
        
        if overlap_mins > 0:
            overlap_hours = overlap_mins / 60.0
            for emp in assignees:
                hours_by_emp[emp.name] = hours_by_emp.get(emp.name, 0.0) + overlap_hours
    
    return hours_by_emp

# --------------- Hour-by-hour weighted distribution ----------------
def compute_hourly_effective_hours(events: List[Dict], employees: List[Employee], tz_name: str, 
                                   open_time: time, switch_time: time, close_time: time) -> Dict[date, Dict[str, Dict[str, float]]]:
    """
    Calculate effective hours for each barista per day, split by opening/closing windows.
    When multiple baristas work the same hour, they each get fractional credit.
    
    Returns: {date: {"opening": {barista: eff_hours}, "closing": {barista: eff_hours}}}
    """
    # Build hourly coverage: {date: {hour: [barista_names]}}
    hourly_coverage = defaultdict(lambda: defaultdict(list))
    
    for event in events:
        baristas = match_baristas(event.get("summary", ""), event.get("attendees", []), employees)
        if not baristas:
            continue
        
        start_dt = _parse_dt(event.get("start", ""), tz_name)
        end_dt = _parse_dt(event.get("end", ""), tz_name)
        
        # Iterate through each hour from start to end
        current_hour = start_dt.replace(minute=0, second=0, microsecond=0)
        
        while current_hour < end_dt:
            next_hour = current_hour + timedelta(hours=1)
            
            # Check if this event overlaps with this hour
            hour_start = current_hour
            hour_end = min(next_hour, end_dt)
            
            if start_dt < hour_end and end_dt > hour_start:
                # Calculate the fraction of this hour that overlaps
                overlap_start = max(start_dt, hour_start)
                overlap_end = min(end_dt, hour_end)
                overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
                
                if overlap_minutes > 0:
                    event_date = current_hour.date()
                    hour_num = current_hour.hour
                    
                    for barista in baristas:
                        # Store tuple: (barista_name, minutes_worked_this_hour)
                        hourly_coverage[event_date][hour_num].append((barista.name, overlap_minutes))
            
            current_hour = next_hour
    
    # Calculate effective hours per window per barista per day
    effective_by_day = {}
    
    for day, hours_data in hourly_coverage.items():
        opening_eff = defaultdict(float)
        closing_eff = defaultdict(float)
        
        for hour_num, barista_minutes_list in hours_data.items():
            hour_t = time(hour_num, 0)
            
            # Group by barista name and sum their minutes for this hour
            barista_hour_minutes = defaultdict(float)
            for barista_name, minutes in barista_minutes_list:
                barista_hour_minutes[barista_name] += minutes
            
            # Count unique baristas working this hour
            num_baristas = len(barista_hour_minutes)
            
            if num_baristas > 0:
                # Each barista gets fractional credit based on sharing
                for barista_name, minutes in barista_hour_minutes.items():
                    # Convert minutes to hours and divide by number of people sharing
                    effective_hours = (minutes / 60.0) / num_baristas
                    
                    # Assign to opening or closing window
                    if open_time <= hour_t < switch_time:
                        opening_eff[barista_name] += effective_hours
                    elif switch_time <= hour_t < close_time:
                        closing_eff[barista_name] += effective_hours
        
        effective_by_day[day] = {
            "opening": dict(opening_eff),
            "closing": dict(closing_eff)
        }
    
    return effective_by_day

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

    # Calculate base pay per shift
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

    # Get hourly effective hours (weighted for overlaps)
    effective_by_day = compute_hourly_effective_hours(events, employees, tz_name, OPEN, SWITCH, CLOSE)

    tips_cc = {emp.name: 0.0 for emp in employees}
    schedule_rows = []

    d = start_day
    while d < end_day:
        day_key = d.isoformat()
        
        # Get effective hours for this day
        day_eff = effective_by_day.get(d, {"opening": {}, "closing": {}})
        opening_eff = day_eff["opening"]
        closing_eff = day_eff["closing"]
        
        # Get tip amounts for this day
        day_cc_open  = float(per_day_cc_open_map.get(day_key, 0.0))
        day_cc_close = float(per_day_cc_close_map.get(day_key, 0.0))

        # Distribute opening tips based on effective hours
        if opening_eff and day_cc_open > 0:
            total_opening_eff = sum(opening_eff.values())
            if total_opening_eff > 0:
                for emp_name, eff_hours in opening_eff.items():
                    weight = eff_hours / total_opening_eff
                    tips_cc[emp_name] += day_cc_open * weight

        # Distribute closing tips based on effective hours
        if closing_eff and day_cc_close > 0:
            total_closing_eff = sum(closing_eff.values())
            if total_closing_eff > 0:
                for emp_name, eff_hours in closing_eff.items():
                    weight = eff_hours / total_closing_eff
                    tips_cc[emp_name] += day_cc_close * weight

        # Build schedule matrix for display
        cell = {name: "" for name in emp_names}
        
        # Determine who worked opening/closing and if shared
        open_workers = list(opening_eff.keys())
        close_workers = list(closing_eff.keys())
        
        shared_open  = len(open_workers) > 1
        shared_close = len(close_workers) > 1
        
        for name in open_workers:
            cell[name] += ("O*" if shared_open else "O")
        for name in close_workers:
            cell[name] += ("/" if cell[name] else "")
            cell[name] += ("C*" if shared_close else "C")
        
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_of_week = day_names[d.weekday()]
        schedule_rows.append({"date": d.isoformat(), "day_of_week": day_of_week, "cells": cell})

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


# --------------- Tip Payload Parsing ----------------
def parse_tip_payload(payload_text: str, start_date: date, end_date: date) -> tuple[Dict[str, float], List[str]]:
    """Parse tip payload text and extract daily tip amounts.
    
    Expected format per entry:
        02-10-2026
        12:15 AM
        Tips
        Tuesday, February 3, 2026 8:00 AM - Tuesday, February 3, 2026 9:00 PM
        $88.20
    
    Returns:
        - Dictionary mapping date (YYYY-MM-DD) to tip amount
        - List of warning messages for dates outside range
    """
    import re
    from datetime import datetime
    
    daily_tips: Dict[str, float] = {}
    warnings: List[str] = []
    
    # Split by double newlines to get individual entries
    lines = payload_text.strip().split('\n')
    
    # Pattern to match dates like "Tuesday, February 3, 2026"
    date_pattern = r'([A-Za-z]+day),\s+([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})'
    
    # Pattern to match dollar amounts like "$88.20"
    amount_pattern = r'\$\s*(\d+(?:\.\d{2})?)'
    
    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for date pattern in current line
        date_match = re.search(date_pattern, line, re.IGNORECASE)
        
        if date_match:
            # Extract date components
            month_name = date_match.group(2).lower()
            day = int(date_match.group(3))
            year = int(date_match.group(4))
            
            month = month_map.get(month_name)
            if month:
                try:
                    parsed_date = date(year, month, day)
                    
                    # Look ahead for dollar amount (usually 1 line after date line)
                    amount = None
                    for j in range(i, min(i + 3, len(lines))):
                        amount_match = re.search(amount_pattern, lines[j])
                        if amount_match:
                            amount = float(amount_match.group(1))
                            break
                    
                    if amount is not None:
                        date_key = parsed_date.isoformat()
                        
                        # Check if date is within range (inclusive on both ends)
                        if start_date <= parsed_date <= end_date:
                            daily_tips[date_key] = amount
                        else:
                            warnings.append(f"Date {date_key} (${amount:.2f}) is outside selected range and will be skipped")
                
                except ValueError:
                    # Invalid date, skip
                    pass
        
        i += 1
    
    return daily_tips, warnings


# --------------- Daily Total Effective Hours ----------------
def compute_daily_effective_hours(events: List[Dict], employees: List[Employee], tz_name: str, 
                                  open_time: time, close_time: time) -> Dict[date, Dict[str, float]]:
    """
    Calculate effective hours for each barista per day (entire day, not split by windows).
    When multiple baristas work the same hour, they each get fractional credit.
    
    Returns: {date: {barista_name: effective_hours}}
    """
    # Build hourly coverage: {date: {hour: [(barista_name, minutes)]}}
    hourly_coverage = defaultdict(lambda: defaultdict(list))
    
    for event in events:
        baristas = match_baristas(event.get("summary", ""), event.get("attendees", []), employees)
        if not baristas:
            continue
        
        start_dt = _parse_dt(event.get("start", ""), tz_name)
        end_dt = _parse_dt(event.get("end", ""), tz_name)
        
        # Iterate through each hour from start to end
        current_hour = start_dt.replace(minute=0, second=0, microsecond=0)
        
        while current_hour < end_dt:
            next_hour = current_hour + timedelta(hours=1)
            
            # Check if this event overlaps with this hour
            hour_start = current_hour
            hour_end = min(next_hour, end_dt)
            
            if start_dt < hour_end and end_dt > hour_start:
                # Calculate the fraction of this hour that overlaps
                overlap_start = max(start_dt, hour_start)
                overlap_end = min(end_dt, hour_end)
                overlap_minutes = (overlap_end - overlap_start).total_seconds() / 60
                
                if overlap_minutes > 0:
                    event_date = current_hour.date()
                    hour_num = current_hour.hour
                    
                    # Only count hours within open-close window
                    hour_t = time(hour_num, 0)
                    if open_time <= hour_t < close_time:
                        for barista in baristas:
                            hourly_coverage[event_date][hour_num].append((barista.name, overlap_minutes))
            
            current_hour = next_hour
    
    # Calculate effective hours per barista per day
    effective_by_day = {}
    
    for day, hours_data in hourly_coverage.items():
        daily_eff = defaultdict(float)
        
        for hour_num, barista_minutes_list in hours_data.items():
            # Group by barista name and sum their minutes for this hour
            barista_hour_minutes = defaultdict(float)
            for barista_name, minutes in barista_minutes_list:
                barista_hour_minutes[barista_name] += minutes
            
            # Count unique baristas working this hour
            num_baristas = len(barista_hour_minutes)
            
            if num_baristas > 0:
                # Each barista gets fractional credit based on sharing
                for barista_name, minutes in barista_hour_minutes.items():
                    # Convert minutes to hours and divide by number of people sharing
                    effective_hours = (minutes / 60.0) / num_baristas
                    daily_eff[barista_name] += effective_hours
        
        effective_by_day[day] = dict(daily_eff)
    
    return effective_by_day


# --------------- Daily Total Computation ----------------
def compute_payouts_daily_total(
    events: List[Dict],
    employees: List[Employee],
    tz_name: str = "",
    daily_tips: Dict[str, float] | None = None,
    open_str: str = "08:00",
    close_str: str = "21:00",
):
    """Compute payouts distributing daily tip totals proportionally by hours worked.
    
    Unlike the shift-based method, this distributes the entire day's tips
    across all hours worked, regardless of opening/closing windows.
    Uses hourly weighting for fair overlap distribution.
    """
    daily_tips = daily_tips or {}
    
    emp_by_name = {e.name: e for e in employees}
    emp_names = [e.name for e in employees]
    
    # Calculate base pay (per shift worked)
    base_pay = {emp.name: 0.0 for emp in employees}
    for e in events:
        assignees = match_baristas(e.get("summary", ""), e.get("attendees", []), employees)
        for emp in assignees:
            base_pay[emp.name] += float(emp_by_name[emp.name].base)
    
    # Determine date range from events
    if events:
        starts = [_parse_dt(e["start"]) for e in events if "start" in e]
        ends   = [_parse_dt(e["end"])   for e in events if "end" in e]
        start_day = min(starts).date()
        end_day   = (max(ends) + timedelta(days=1)).date()
    else:
        today = datetime.now().date()
        start_day, end_day = today, today + timedelta(days=1)
    
    days_count = max(1, (end_day - start_day).days)
    
    OPEN = time.fromisoformat(open_str)
    CLOSE = time.fromisoformat(close_str)
    
    # Get daily effective hours (weighted for overlaps)
    effective_by_day = compute_daily_effective_hours(events, employees, tz_name, OPEN, CLOSE)
    
    tips_cc = {emp.name: 0.0 for emp in employees}
    schedule_rows = []
    
    d = start_day
    while d < end_day:
        day_key = d.isoformat()
        
        # Get effective hours for this day
        day_eff = effective_by_day.get(d, {})
        
        # Get tip total for this day
        day_tips = float(daily_tips.get(day_key, 0.0))
        
        # Distribute tips based on effective hours
        if day_eff and day_tips > 0:
            total_eff_hours = sum(day_eff.values())
            if total_eff_hours > 0:
                for emp_name, eff_hours in day_eff.items():
                    weight = eff_hours / total_eff_hours
                    tips_cc[emp_name] += day_tips * weight
        
        # Build schedule matrix (simplified - just show who worked)
        cell = {name: "" for name in emp_names}
        for emp_name in day_eff.keys():
            cell[emp_name] = "✓"
        
        day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        day_of_week = day_names[d.weekday()]
        schedule_rows.append({"date": d.isoformat(), "day_of_week": day_of_week, "cells": cell})
        
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

