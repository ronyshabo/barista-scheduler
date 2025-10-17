from __future__ import annotations
import os
from typing import List, Dict, Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]

# Allow overriding paths via environment for containerized deployments
TOKEN_PATH = os.getenv("GOOGLE_TOKEN_PATH", "token.json")
CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "credentials.json")  # OAuth Desktop client downloaded from Google Cloud


def _auth_new_creds():
    flow = InstalledAppFlow.from_client_secrets_file(CREDS_PATH, SCOPES)
    # avoids snap/browser issues; copy URL manually if needed
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent", open_browser=False)
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    return creds


def _load_creds():
    creds = None
    if os.path.exists(TOKEN_PATH):
        # IMPORTANT: pass the expected scopes here
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if creds and creds.valid:
        # token is good and already has correct scopes (because we passed SCOPES above)
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # still ensure scope coverage
            if not set(SCOPES).issubset(set(creds.scopes or [])):
                return _auth_new_creds()
            with open(TOKEN_PATH, "w") as f:
                f.write(creds.to_json())
            return creds
        except RefreshError:
            # fall through to fresh auth
            pass

    # Either no token, bad token, or missing scopes → new consent
    return _auth_new_creds()

def fetch_events(calendar_id: str, time_min_iso: str, time_max_iso: str, tz: str = "UTC") -> List[Dict]:
    """
    Return list of events between bounds.
    Each item contains: id, summary, description, location, htmlLink, updated,
    start, end, attendees (email + responseStatus), creator email.
    """
    service = build("calendar", "v3", credentials=_load_creds())

    fields = (
        "items(id,summary,description,location,htmlLink,updated,"
        "start,end,attendees(email,responseStatus,resource),creator(email)),nextPageToken"
    )

    out: List[Dict] = []
    page_token = None
    while True:
        events_result = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=time_min_iso,
                timeMax=time_max_iso,
                singleEvents=True,
                orderBy="startTime",
                timeZone=tz,
                maxResults=2500,
                pageToken=page_token,
                fields=fields,
            )
            .execute()
        )

        for e in events_result.get("items", []):
            attendees = []
            for a in e.get("attendees", []) or []:
                if a.get("resource"):
                    continue
                attendees.append({
                    "email": a.get("email", ""),
                    "responseStatus": a.get("responseStatus", "")
                })

            out.append({
                "id": e.get("id"),
                "summary": e.get("summary", ""),
                "description": e.get("description", ""),
                "location": e.get("location", ""),
                "htmlLink": e.get("htmlLink", ""),
                "updated": e.get("updated", ""),
                "start": e.get("start", {}).get("dateTime") or e.get("start", {}).get("date"),
                "end":   e.get("end",   {}).get("dateTime") or e.get("end",   {}).get("date"),
                "attendees": attendees,
                "creator": (e.get("creator", {}) or {}).get("email", ""),
            })

        page_token = events_result.get("nextPageToken")
        if not page_token:
            break

    return out
