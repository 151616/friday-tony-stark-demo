"""Google Workspace tools (Calendar, Gmail) using official OAuth."""
import os
import datetime
import time as _time
from pathlib import Path
from dateutil import parser, tz
from mcp.server.fastmcp import FastMCP


def _get_iana_timezone() -> str:
    """Get the system's IANA timezone string (e.g. 'America/New_York').
    Windows reports timezone names like 'Eastern Standard Time' which
    Google Calendar doesn't accept — map them to IANA."""
    # Map common Windows timezone names to IANA
    _WIN_TO_IANA = {
        "eastern standard time": "America/New_York",
        "eastern daylight time": "America/New_York",
        "central standard time": "America/Chicago",
        "central daylight time": "America/Chicago",
        "mountain standard time": "America/Denver",
        "mountain daylight time": "America/Denver",
        "pacific standard time": "America/Los_Angeles",
        "pacific daylight time": "America/Los_Angeles",
        "alaska standard time": "America/Anchorage",
        "hawaii standard time": "Pacific/Honolulu",
        "india standard time": "Asia/Kolkata",
        "gmt standard time": "Europe/London",
        "central europe standard time": "Europe/Berlin",
        "china standard time": "Asia/Shanghai",
        "tokyo standard time": "Asia/Tokyo",
        "aus eastern standard time": "Australia/Sydney",
    }
    # Check Windows tzname
    for name in _time.tzname:
        mapped = _WIN_TO_IANA.get(name.lower())
        if mapped:
            return mapped
    # Try tzlocal if installed
    try:
        from tzlocal import get_localzone
        return str(get_localzone())
    except Exception:
        pass
    # Fallback: UTC offset
    offset_sec = -_time.timezone if _time.daylight == 0 else -_time.altzone
    hours = abs(offset_sec) // 3600
    # Etc/GMT signs are inverted: UTC-5 = Etc/GMT+5
    return f"Etc/GMT{'+' if offset_sec <= 0 else '-'}{hours}"


# Cache it once at import time
LOCAL_TIMEZONE = _get_iana_timezone()

# Calendar gets full access (read + write), Gmail stays read-only for now.
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly'
]

# Root path for securely looking up OAuth files
ROOT_DIR = Path(__file__).resolve().parents[2]
CREDS_FILE = ROOT_DIR / "credentials.json"
TOKEN_FILE = ROOT_DIR / "token.json"

def _get_credentials():
    """Retrieve and refresh user OAuth credentials."""
    import warnings
    warnings.filterwarnings("ignore") # suppress discovery warnings
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
                
        if not creds:
            if not CREDS_FILE.exists():
                return None
            
            # The local server flow opens a browser and catches the redirect
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return creds

def list_upcoming_events(days: int = 2) -> str:
    """Fetch the user's upcoming Google Calendar events over the next N days.
    Call this when the user asks what is on their schedule, agenda, or calendar."""
    
    creds = _get_credentials()
    if not creds:
        return "Sir, I do not see a credentials.json file in the root workspace. You must configure Google Cloud OAuth Developer APIs before I can access your schedule."
        
    try:
        from googleapiclient.discovery import build
        service = build('calendar', 'v3', credentials=creds, cache_discovery=False)
        
        # Call the Calendar API
        now = datetime.datetime.now(datetime.timezone.utc)
        time_min = now.isoformat()
        time_max = (now + datetime.timedelta(days=days)).isoformat()
        
        events_result = service.events().list(
            calendarId='primary', 
            timeMin=time_min,
            timeMax=time_max,
            maxResults=15, 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])

        if not events:
            return f"Your schedule is completely clear for the next {days} days."
            
        out = []
        for event in events:
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            
            # Format to a readable string
            try:
                dt = parser.isoparse(start_str)
                if dt.tzinfo:
                    dt = dt.astimezone(tz.gettz())
                display_time = dt.strftime("%A, %I:%M %p").replace(" 0", " ")
            except:
                display_time = start_str
                
            summary = event.get('summary', 'Busy / No Title')
            out.append(f"- {display_time}: {summary}")
            
        return f"Here is your agenda against the primary calendar:\\n" + "\\n".join(out)
        
    except Exception as e:
        return f"Failed to retrieve Google Calendar: {str(e)}"
            
            
def list_recent_emails(limit: int = 5) -> str:
    """Fetch the most recent unread emails from the user's Gmail inbox.
    Call this when the user asks to check their emails, scan their inbox, etc."""
    
    creds = _get_credentials()
    if not creds:
        return "Sir, I do not see a credentials.json file in the root workspace. You must configure Google Cloud OAuth Developer APIs before I can read your inbox."
        
    try:
        from googleapiclient.discovery import build
        service = build('gmail', 'v1', credentials=creds, cache_discovery=False)
        
        results = service.users().messages().list(
            userId='me',
            labelIds=['INBOX', 'UNREAD'],
            maxResults=limit
        ).execute()
        messages = results.get('messages', [])

        if not messages:
            return "You have zero unread emails in your Primary inbox."

        out = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id'], format='metadata', metadataHeaders=['Subject', 'From']).execute()
            headers = msg_data['payload']['headers']
            
            subject = "No Subject"
            sender = "Unknown Sender"
            for header in headers:
                if header['name'].lower() == 'subject':
                    subject = header['value']
                elif header['name'].lower() == 'from':
                    # Simplify sender (e.g. "GitHub <noreply@github.com>" -> "GitHub")
                    sender = header['value'].split('<')[0].strip()
                    
            snippet = msg_data.get('snippet', '')
            out.append(f"From: {sender}\\nSubject: {subject}\\nSnippet: {snippet}\\n---")
            
        return f"Here are your {len(out)} most recent unread emails:\\n" + "\\n".join(out)
        
    except Exception as e:
        return f"Failed to connect to Gmail: {str(e)}"

def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str = "",
    description: str = "",
    location: str = "",
) -> str:
    """Create a Google Calendar event.

    Args:
        title: Event name/summary.
        start_time: ISO 8601 datetime string (e.g. "2026-04-20T14:00:00").
        end_time: ISO 8601 datetime string. If empty, defaults to 1 hour after start.
        description: Optional event description/notes.
        location: Optional location string.
    """
    creds = _get_credentials()
    if not creds:
        return "No credentials.json found. Google OAuth must be configured first."

    try:
        from googleapiclient.discovery import build

        # Parse and default end_time
        local_tz = tz.gettz(LOCAL_TIMEZONE)
        current_year = datetime.date.today().year

        dt_start = parser.isoparse(start_time)
        if not dt_start.tzinfo:
            dt_start = dt_start.replace(tzinfo=local_tz)
        # Fix wrong year (LLM sometimes uses its training year)
        if dt_start.year < current_year:
            dt_start = dt_start.replace(year=current_year)

        if end_time:
            dt_end = parser.isoparse(end_time)
            if not dt_end.tzinfo:
                dt_end = dt_end.replace(tzinfo=local_tz)
            if dt_end.year < current_year:
                dt_end = dt_end.replace(year=current_year)
        else:
            dt_end = dt_start + datetime.timedelta(hours=1)

        event_body = {
            "summary": title,
            "start": {"dateTime": dt_start.isoformat(), "timeZone": LOCAL_TIMEZONE},
            "end": {"dateTime": dt_end.isoformat(), "timeZone": LOCAL_TIMEZONE},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        created = service.events().insert(calendarId="primary", body=event_body).execute()

        disp_start = dt_start.strftime("%A %B %d, %I:%M %p").replace(" 0", " ")
        return f"Created '{title}' on {disp_start}."

    except Exception as e:
        return f"Failed to create calendar event: {e}"


def _find_event_by_title(service, title: str, days_ahead: int = 30):
    """Search upcoming events for one matching the given title (case-insensitive).
    Returns (event_dict, display_start_str) or (None, error_msg)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    time_min = now.isoformat()
    time_max = (now + datetime.timedelta(days=days_ahead)).isoformat()

    results = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=50,
        singleEvents=True,
        orderBy="startTime",
        q=title,
    ).execute()
    events = results.get("items", [])

    if not events:
        return None, f"No upcoming event matching '{title}' found in the next {days_ahead} days."

    # Best match: exact case-insensitive title match first, then first result
    needle = title.lower()
    best = None
    for ev in events:
        if ev.get("summary", "").lower() == needle:
            best = ev
            break
    if not best:
        best = events[0]

    start_str = best["start"].get("dateTime", best["start"].get("date"))
    try:
        dt = parser.isoparse(start_str)
        if dt.tzinfo:
            dt = dt.astimezone(tz.gettz(LOCAL_TIMEZONE))
        disp = dt.strftime("%A %B %d, %I:%M %p").replace(" 0", " ")
    except Exception:
        disp = start_str

    return best, disp


def update_calendar_event(
    title: str,
    new_title: str = "",
    new_start_time: str = "",
    new_end_time: str = "",
    new_description: str = "",
    new_location: str = "",
) -> str:
    """Update an existing Google Calendar event found by title."""
    creds = _get_credentials()
    if not creds:
        return "No credentials.json found. Google OAuth must be configured first."

    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        event, disp = _find_event_by_title(service, title)
        if not event:
            return disp  # error message

        local_tz = tz.gettz(LOCAL_TIMEZONE)
        current_year = datetime.date.today().year

        if new_title:
            event["summary"] = new_title
        if new_start_time:
            dt = parser.isoparse(new_start_time)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=local_tz)
            if dt.year < current_year:
                dt = dt.replace(year=current_year)
            event["start"] = {"dateTime": dt.isoformat(), "timeZone": LOCAL_TIMEZONE}
        if new_end_time:
            dt = parser.isoparse(new_end_time)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=local_tz)
            if dt.year < current_year:
                dt = dt.replace(year=current_year)
            event["end"] = {"dateTime": dt.isoformat(), "timeZone": LOCAL_TIMEZONE}
        if new_description:
            event["description"] = new_description
        if new_location:
            event["location"] = new_location

        updated = service.events().update(
            calendarId="primary", eventId=event["id"], body=event
        ).execute()

        summary = updated.get("summary", title)
        return f"Updated '{summary}' ({disp})."

    except Exception as e:
        return f"Failed to update calendar event: {e}"


def delete_calendar_event(title: str, confirm: bool = False) -> str:
    """Delete a Google Calendar event found by title.
    Call with confirm=false first to show what would be deleted,
    then confirm=true to actually delete."""
    creds = _get_credentials()
    if not creds:
        return "No credentials.json found. Google OAuth must be configured first."

    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

        event, disp = _find_event_by_title(service, title)
        if not event:
            return disp

        summary = event.get("summary", title)

        if not confirm:
            return f"Found '{summary}' on {disp}. Shall I delete it?"

        service.events().delete(
            calendarId="primary", eventId=event["id"]
        ).execute()

        return f"Deleted '{summary}' ({disp}) from your calendar."

    except Exception as e:
        return f"Failed to delete calendar event: {e}"


def register(mcp: FastMCP):

    @mcp.tool(name="list_upcoming_events")
    def _list_upcoming_events(days: int = 2) -> str:
        """Fetch the user's upcoming Google Calendar events over the next N days.
        Call this when the user asks what is on their schedule, agenda, or calendar."""
        return list_upcoming_events(days)

    @mcp.tool(name="list_recent_emails")
    def _list_recent_emails(limit: int = 5) -> str:
        """Fetch the most recent unread emails from the user's Gmail inbox.
        Call this when the user asks to check their emails, scan their inbox, etc."""
        return list_recent_emails(limit)

    # Build description with today's date so the LLM uses the correct year.
    _today = datetime.date.today()
    _today_str = _today.strftime("%Y-%m-%d")
    _year = _today.year

    @mcp.tool(name="create_event", description=(
        f"Create a new Google Calendar event. Use when the user says 'schedule', "
        f"'add to my calendar', 'book', 'set a meeting', etc. "
        f"TODAY is {_today_str}. The current year is {_year}. "
        f"Parse the user's spoken time into ISO 8601 format using this date as "
        f"the reference (e.g. 'tomorrow at 2pm' → '{(_today + datetime.timedelta(days=1)).isoformat()}T14:00:00'). "
        f"If no end time is given, it defaults to 1 hour."
    ))
    def _create_event(
        title: str,
        start_time: str,
        end_time: str = "",
        description: str = "",
        location: str = "",
    ) -> str:
        return create_calendar_event(title, start_time, end_time, description, location)

    @mcp.tool(name="update_event", description=(
        f"Update an existing Google Calendar event. Use when the user says "
        f"'move my meeting', 'reschedule', 'change the time', 'rename the event', etc. "
        f"TODAY is {_today_str}. The current year is {_year}. "
        f"Searches upcoming events by title and patches the fields provided."
    ))
    def _update_event(
        title: str,
        new_title: str = "",
        new_start_time: str = "",
        new_end_time: str = "",
        new_description: str = "",
        new_location: str = "",
    ) -> str:
        """title: the current event name to find. Other params are the new values (only pass what should change)."""
        return update_calendar_event(title, new_title, new_start_time, new_end_time, new_description, new_location)

    @mcp.tool(name="delete_event", description=(
        f"Delete a Google Calendar event. Use when the user says 'cancel my meeting', "
        f"'delete the event', 'remove from calendar', etc. "
        f"ALWAYS call with confirm=false first to show what would be deleted, "
        f"then only call with confirm=true after the user explicitly confirms."
    ))
    def _delete_event(title: str, confirm: bool = False) -> str:
        """title: the event name to find and delete. confirm: false=preview, true=delete."""
        return delete_calendar_event(title, confirm)
