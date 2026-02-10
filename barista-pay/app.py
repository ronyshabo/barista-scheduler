from __future__ import annotations
import os
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from flask import Flask, render_template, request, flash, redirect, url_for, session

from gcal_client import fetch_events
from compute import load_employees, compute_payouts, compute_payouts_daily_total, parse_tip_payload, match_baristas, Employee
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import json

def _daterange(start_d: date, end_d: date):
    """Yield dates from start_d up to and including end_d (end-inclusive)."""
    d = start_d
    while d <= end_d:
        yield d
        d += timedelta(days=1)

        
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your-secret-key-here")  # For flash messages

TZ = os.getenv("TZ", "America/Chicago")
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")

@app.get("/")
def index():
    today = datetime.now().date()
    start_default = (today - timedelta(days=7)).isoformat()
    end_default = (today + timedelta(days=1)).isoformat()
    employees = load_employees()
    return render_template(
        "index.html",
        start_default=start_default,
        end_default=end_default,
        rows=None,
        summary=None,
        employees=employees,
        recognized_employees=[],
        tip_mode="shift_based",
        # NEW defaults
        cc_open_default=0.0,
        cash_open_default=0.0,
        cc_close_default=0.0,
        cash_close_default=0.0,
    )



@app.post("/refresh")
def refresh():
    start = request.form.get("start")
    end   = request.form.get("end")
    tip_mode = request.form.get("tip_mode", "shift_based")  # "shift_based" or "daily_total"
    tz = ZoneInfo(TZ)

    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)
    if end_d <= start_d:
        end_d = start_d + timedelta(days=1)

    time_min = datetime.combine(start_d, datetime.min.time(), tzinfo=tz).isoformat()
    time_max = datetime.combine(end_d,   datetime.min.time(), tzinfo=tz).isoformat()

    events = fetch_events(CALENDAR_ID, time_min, time_max)
    employees = load_employees()

    # Phase 1 → show per-day inputs or tip payload text area
    if request.form.get("tips_phase") != "1":
        dates_to_fill = [d.isoformat() for d in _daterange(start_d, end_d)]
        scheduled = {}
        for e in events:
            for emp in match_baristas(e.get("summary", ""), e.get("attendees", []), employees):
                scheduled[emp.name] = emp

        return render_template(
            "index.html",
            start_default=start,
            end_default=end,
            rows=None,
            summary=None,
            employees=employees,
            recognized_employees=sorted(scheduled.values(), key=lambda x: x.name.lower()),
            dates_to_fill=dates_to_fill,  # triggers per-day inputs in the template
            tip_mode=tip_mode,
        )

    # Phase 2 → compute based on selected mode
    if tip_mode == "daily_total":
        # Parse tip payload text
        tip_payload = request.form.get("tip_payload", "")
        daily_tips, warnings = parse_tip_payload(tip_payload, start_d, end_d)
        
        # Flash warnings if any dates were outside range
        if warnings:
            for warning in warnings:
                flash(warning, "warning")
        
        rows, summary = compute_payouts_daily_total(
            events=events,
            employees=employees,
            tz_name=TZ,
            daily_tips=daily_tips,
            open_str=os.getenv("OPEN_TIME", "08:00"),
            close_str=os.getenv("CLOSE_TIME", "21:00"),
        )
    else:
        # Original shift-based mode
        per_day_cc_open_map = {}
        per_day_cc_close_map = {}
        
        for dstr in request.form.getlist("dates"):
            per_day_cc_open_map[dstr]  = float(request.form.get(f"cc_open_{dstr}") or 0.0)
            per_day_cc_close_map[dstr] = float(request.form.get(f"cc_close_{dstr}") or 0.0)

        rows, summary = compute_payouts(
            events=events,
            employees=employees,
            tz_name=TZ,
            per_day_cc_open_map=per_day_cc_open_map,
            per_day_cc_close_map=per_day_cc_close_map,
            open_str=os.getenv("OPEN_TIME", "08:00"),
            switch_str=os.getenv("SWITCH_TIME", "14:00"),
            close_str=os.getenv("CLOSE_TIME", "21:00"),
        )

    return render_template(
        "index.html",
        start_default=start,
        end_default=end,
        rows=rows,
        summary=summary,
        employees=employees,
        recognized_employees=None,
        dates_to_fill=None,
        tip_mode=tip_mode,
    )


@app.post("/update_employees")
def update_employees():
    """Update employee base pay values."""
    try:
        employees = load_employees()
        
        # Update base pay for each employee
        for emp in employees:
            new_base = request.form.get(f"base_{emp.name}")
            if new_base is not None:
                try:
                    emp.base = float(new_base)
                except ValueError:
                    flash(f"Invalid base pay value for {emp.name}", "error")
                    return redirect(url_for("index"))
        
        # Save updated employees to JSON
        with open("employees.json", "w", encoding="utf-8") as f:
            data = []
            for emp in employees:
                emp_dict = {
                    "name": emp.name,
                    "aliases": emp.aliases,
                    "base": emp.base,
                }
                if emp.switch_override:
                    emp_dict["switch_override"] = emp.switch_override
                data.append(emp_dict)
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        flash("Employee base pay updated successfully!", "success")
        return redirect(url_for("index"))
    
    except Exception as e:
        flash(f"Error updating employees: {str(e)}", "error")
        return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
