from __future__ import annotations
import os
from datetime import datetime
from typing import List, Dict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TOKEN_PATH = "token.json"
CREDS_PATH = "credentials.json"  # download from Google Cloud (OAuth client ID)


def _load_creds() -> Credentials:
    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDS_PATH):
                raise FileNotFoundError(
                    "Missing credentials.json. Create an OAuth Client ID (Desktop) and place it next to app.py."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as token:
            token.write(creds.to_json())
    return creds


def fetch_events(calendar_id: str, time_min_iso: str, time_max_iso: str) -> List[Dict]:
    """
    Return list of events between ISO8601 bounds (inclusive start, exclusive end).
    Each item contains: id, summary, start, end, attendees (if any).
    """
    service = build("calendar", "v3", credentials=_load_creds())
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min_iso,
            timeMax=time_max_iso,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = []
    for e in events_result.get("items", []):
        events.append(
            {
                "id": e.get("id"),
                "summary": e.get("summary", ""),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end": e.get("end", {}).get("dateTime") or e.get("end", {}).get("date"),
                "attendees": [a.get("email", "") for a in e.get("attendees", []) if not a.get("resource")],
            }
        )
    return events
