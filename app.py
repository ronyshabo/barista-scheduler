from __future__ import annotations
import os
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from flask import Flask, render_template, request

from gcal_client import fetch_events
from compute import load_employees, compute_payouts, match_baristas, Employee
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

def _daterange(start_d: date, end_d: date):
    """Yield dates from start_d up to but NOT including end_d (end-exclusive)."""
    d = start_d
    while d < end_d:
        yield d
        d += timedelta(days=1)
        
load_dotenv()

app = Flask(__name__)

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
    tz = ZoneInfo(TZ)

    start_d = date.fromisoformat(start)
    end_d   = date.fromisoformat(end)
    if end_d <= start_d:
        end_d = start_d + timedelta(days=1)

    time_min = datetime.combine(start_d, datetime.min.time(), tzinfo=tz).isoformat()
    time_max = datetime.combine(end_d,   datetime.min.time(), tzinfo=tz).isoformat()

    events = fetch_events(CALENDAR_ID, time_min, time_max)
    employees = load_employees()

    # Phase 1 → show per-day inputs
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
        )

    # Phase 2 → read per-day Opening/Closing CC tips and compute
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
    )
if __name__ == "__main__":
    app.run(debug=True)
