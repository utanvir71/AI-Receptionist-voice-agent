import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")


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


if __name__ == "__main__":

    result = test_calendar_connection()

    print(result)