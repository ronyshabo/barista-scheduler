from __future__ import annotations
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request

from gcal_client import fetch_events
from compute import load_employees, compute_payouts

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
    flat_default=50.0,
    cc_tips_default=0.0,
    cash_tips_default=0.0,
)

@app.post("/refresh")
def refresh():
    start = request.form.get("start")
    end = request.form.get("end")
    flat = float(request.form.get("flat") or 50.0)
    morning_tips = float(request.form.get("morning_tips") or 0.0)
    evening_tips = float(request.form.get("evening_tips") or 0.0)

    time_min = f"{start}T00:00:00-00:00"
    time_max = f"{end}T00:00:00-00:00"

    events = fetch_events(CALENDAR_ID, time_min, time_max)
    employees = load_employees()

    rows, summary = compute_payouts(
        events=events,
        employees=employees,
        tz_name=TZ,                 # accepted by compute_payouts
        flat_per_shift=flat,
        morning_tips_total=morning_tips,
        evening_tips_total=evening_tips,
        open_str=os.getenv("OPEN_TIME", "09:00"),
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
        flat_default=flat,
        morning_tips_default=morning_tips,
        evening_tips_default=evening_tips,
    )

if __name__ == "__main__":
    app.run(debug=True)
