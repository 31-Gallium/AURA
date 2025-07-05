# In skills/email_skill.py
import os
import pickle
import base64
import re
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

def authenticate_google_services(log_callback):
    """Handles OAuth 2.0 flow and token management."""
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                log_callback(f"Token refresh failed: {e}. Re-authenticating.")
                if os.path.exists('token.pickle'):
                    os.remove('token.pickle')
                creds = None
        if not creds:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
    return creds

def get_latest_emails(app, **kwargs):
    """Reads a summary of the latest emails from the inbox."""
    log_callback = app.queue_log
    try:
        creds = authenticate_google_services(log_callback)
        if not creds: return "I couldn't get permissions to check your email."
        service = build('gmail', 'v1', credentials=creds)
        results = service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=3).execute()
        messages = results.get('messages', [])
        if not messages: return "You have no new emails in your inbox."
        email_summaries = []
        for msg in messages:
            msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
            headers = msg_data['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown Sender')
            email_summaries.append(f"An email from {sender.split('<')[0].strip()} with the subject: {subject}.")
        return f"Here is a summary of your latest emails: {' '.join(email_summaries)}"
    except Exception as e:
        log_callback(f"Error with Gmail API: {e}")
        return "I had trouble accessing your emails."

def _get_confirmation_prompt(state_data):
    """Helper to generate the confirmation text consistently."""
    to, subject, body = state_data.values()
    return (f"I will send an email to {to} with the subject '{subject}'. "
            f"The message is: {body}. Should I send it?")

def start_email_conversation(app, recipient=None, **kwargs):
    """Initiates the multi-turn process of sending an email."""
    app.conversation_state = {
        "skill": "email",
        "step": "awaiting_recipient",
        "data": {"to": "", "subject": "", "body": ""}
    }
    if recipient:
        app.conversation_state['data']['to'] = recipient.strip()
        app.conversation_state['step'] = 'awaiting_subject'
        app.queue_log(f"Starting email conversation. Recipient: {recipient}")
        return "Okay, what should the subject be?"
    else:
        app.queue_log("Starting email conversation. Awaiting recipient.")
        return "Of course. Who should I send the email to?"

def handle_conversation(app, user_input):
    """Manages the state and flow of the email composition."""
    state = app.conversation_state
    user_input_lower = user_input.lower()

    if user_input_lower in ('cancel', 'stop', 'never mind', 'nevermind'):
        app.conversation_state = None
        return "Okay, I've cancelled the email."

    if state['step'] == 'awaiting_recipient':
        state['data']['to'] = user_input
        state['step'] = 'awaiting_subject'
        return "Got it. And what's the subject?"
    elif state['step'] == 'awaiting_subject':
        state['data']['subject'] = user_input
        state['step'] = 'awaiting_body'
        return "Okay, what would you like the message to say?"
    elif state['step'] == 'awaiting_body':
        state['data']['body'] += (" " + user_input) if state['data']['body'] else user_input
        state['step'] = 'awaiting_more_body'
        return "Got it. Do you want to add more to the message, or is that it?"
    elif state['step'] == 'awaiting_more_body':
        if user_input_lower in ['yes', 'yeah', 'sure', 'add more']:
            state['step'] = 'awaiting_body'
            return "Go ahead."
        else:
            state['step'] = 'awaiting_confirmation'
            return _get_confirmation_prompt(state['data'])
    elif state['step'] == 'awaiting_confirmation':
        if user_input_lower in ['yes', 'yeah', 'send it', 'sure']:
            response = _send_final_email(app, state['data'])
            app.conversation_state = None
            return response
        else:
            app.conversation_state = None
            return "Okay, I've cancelled the email."
    return "I'm sorry, I got confused. Let's start the email over."


def _send_final_email(app, email_data):
    """Helper function to construct and send the email via Gmail API."""
    try:
        app.queue_log("User confirmed. Sending email...")
        creds = authenticate_google_services(app.queue_log)
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(email_data['body'])
        message['to'] = email_data['to']
        message['subject'] = email_data['subject']
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        send_message = service.users().messages().send(userId="me", body=create_message).execute()
        return f"Okay, your email to {email_data['to']} has been sent."
    except Exception as e:
        app.queue_log(f"Failed to send email: {e}")
        return "I'm sorry, I ran into an error while trying to send the email."

def register():
    """Registers all email-related commands with regex."""
    return {
        'get_latest_emails': {
            'handler': get_latest_emails,
            'regex': r'(?:read|check) my(?: latest)? emails?',
            'params': []
        },
        'start_email_conversation': {
            'handler': start_email_conversation,
            'regex': r'(?:send|compose) an? email(?: to (.+))?',
            'params': ['recipient']
        },
    }