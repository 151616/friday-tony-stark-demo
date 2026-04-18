"""Google Workspace tools (Calendar, Gmail) using official OAuth."""
import os
import datetime
from pathlib import Path
from dateutil import parser, tz
from mcp.server.fastmcp import FastMCP

# Define the minimum necessary read-only scopes
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
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
