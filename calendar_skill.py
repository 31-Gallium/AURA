# In skills/calendar_skill.py
import os
import datetime
import pickle
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']

def authenticate_google_calendar(log_callback):
    """Handles the OAuth 2.0 flow for Google Calendar API."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log_callback(f"Token refresh failed for Calendar: {e}. Re-authenticating.")
                if os.path.exists('token.pickle'):
                    os.remove('token.pickle')
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds

def get_upcoming_events(app, **kwargs):
    """Fetches and lists the next 5 upcoming events from the primary calendar."""
    log_callback = app.queue_log
    try:
        creds = authenticate_google_calendar(log_callback)
        if not creds:
            return "I couldn't connect to your Google Calendar."
            
        service = build('calendar', 'v3', credentials=creds)
        now = datetime.datetime.utcnow().isoformat() + 'Z' 
        
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=5, singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        if not events:
            return "You have no upcoming events on your calendar."

        response_parts = ["Here are your next few events:"]
        for event in events:
            start_str = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'an untitled event')
            start_dt = datetime.datetime.fromisoformat(start_str.replace('Z', '+00:00'))
            start_time = start_dt.strftime('%I:%M %p on %A, %B %d')
            response_parts.append(f"{summary} at {start_time}.")
        
        return " ".join(response_parts)

    except Exception as e:
        log_callback(f"An error occurred with Google Calendar API: {e}")
        return "I'm sorry, I had trouble accessing your calendar."

def register():
    """Registers all calendar commands with regex."""
    return {
        'get_upcoming_events': {
            'handler': get_upcoming_events,
            'regex': r'(?:what is|what\'s) on my calendar|do i have any meetings|what are my upcoming events',
            'params': []
        }
    }