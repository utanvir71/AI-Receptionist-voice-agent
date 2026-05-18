import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

KST = ZoneInfo("Asia/Seoul")
CALENDAR_ID = "primary"


def get_calendar_service():
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(
            TOKEN_PATH,
            SCOPES
        )

    if not creds or not creds.valid:

        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_PATH,
                SCOPES
            )

            creds = flow.run_local_server(port=0)

        with open(TOKEN_PATH, "w") as token_file:
            token_file.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds
    )

    return service


def test_calendar_connection():

    service = get_calendar_service()

    calendar_list = service.calendarList().list().execute()

    items = calendar_list.get("items", [])

    return {
        "ok": True,
        "calendar_count": len(items),
        "calendar_names": [
            item.get("summary", "Unnamed Calendar")
            for item in items
        ]
    }

def find_conflicts(start_time, end_time):
    service = get_calendar_service()
    event_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_time.isoformat(),
        timeMax=end_time.isoformat(),
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return event_result.get("items", [])

def check_availability(start_time, end_time):
    conflicts = find_conflicts(start_time, end_time)
    return {
        "available": len(conflicts) == 0,
        "conflicts": conflicts,
        "conflict_count": len(conflicts),
    }

def create_reservation(customer_name, party_size, start_time, duration_minutes=90, phone=None, notes=None):
    service = get_calendar_service()
    end_time = start_time + timedelta(minutes=duration_minutes)
    availability = check_availability(start_time, end_time)

    if not availability["available"]:
        return {
            "ok": False,
            "message": "The slot is not available",
            "conflicts": availability["conflicts"],
        }
    description = f"""
        Reservation Details:
        Customer: {customer_name}
        Party Size: {party_size}
        Phone: {phone if phone else 'N/A'}
        Notes: {notes if notes else 'N/A'}
        Created by: AI receptionist
    """.strip()
    event = {
        "summary": f"Reservation - {customer_name}  - {party_size} people",
        "description": description,
        "start":{
            "dateTime": start_time.isoformat(),
            "timeZone": "Asia/Seoul"
        },
        "end":{
            "dateTime": end_time.isoformat(),
            "timeZone": "Asia/Seoul"
        },
    }
    created_event = service.events().insert(
        calendarId=CALENDAR_ID,
        body=event,
    ).execute()
    return {
        "ok" : True,
        "event_id": created_event.get("id"),
        "event_link": created_event.get("htmlLink"),
        "start_time":start_time.isoformat(),
        "end_time": end_time.isoformat(),
    }

def list_upcoming_bookings(max_results = 10):
    service = get_calendar_service()
    now = datetime.now(KST).isoformat()
    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=now,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return events_result.get("items", [])

def cancel_reservation(event_id):
    service = get_calendar_service()
    service.events().delete(
        calendarId = CALENDAR_ID,
        eventId = event_id,
    ).execute()
    return {
        "ok": True,
        "message": f"Reservation with event ID {event_id} has been cancelled.",
        "event_id": event_id
    }



if __name__ == "__main__":
    test_start = datetime(2026, 5, 18, 19, 0, tzinfo=KST)

    result = create_reservation(
        customer_name="Tanvir Test",
        party_size=2,
        start_time=test_start,
        phone="010-0000-0000",
        notes="Window seat if possible"
    )

    print(result)

    print("\nUpcoming bookings:")
    for event in list_upcoming_bookings():
        print(event.get("summary"), event.get("start"))