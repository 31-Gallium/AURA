# skills/reminder_skill.py
import re
import json
import os
from datetime import datetime, timedelta
from dateutil.parser import parse

REMINDER_FILE = "reminders.json"

def _trigger_reminder(app, reminder_id, message):
    """The function that gets called by the scheduler. Speaks and then cleans up."""
    app.speak_response(f"This is a reminder: {message}")
    
    if not os.path.exists(REMINDER_FILE):
        return
        
    try:
        with open(REMINDER_FILE, 'r') as f:
            reminders = json.load(f)
        
        updated_reminders = [r for r in reminders if r['id'] != reminder_id]
        
        with open(REMINDER_FILE, 'w') as f:
            json.dump(updated_reminders, f, indent=4)
        app.queue_log(f"Completed and removed reminder ID: {reminder_id}")
    except (FileNotFoundError, json.JSONDecodeError):
        pass # File might have been deleted or emptied, which is fine.

def set_reminder(app, time_phrase, message, **kwargs):
    """Saves a reminder to a file and schedules it to be spoken."""
    try:
        # Use fuzzy parsing to understand phrases like "10 minutes" or "8 pm"
        run_date = parse(time_phrase, fuzzy=True)
        # If the parsed time is in the past on the same day, assume it's for the next day
        if run_date < datetime.now():
            run_date += timedelta(days=1)

    except ValueError:
        return f"I'm sorry, I couldn't understand the time '{time_phrase}'."
        
    if os.path.exists(REMINDER_FILE):
        try:
            with open(REMINDER_FILE, 'r') as f:
                reminders = json.load(f)
        except json.JSONDecodeError:
            reminders = []
    else:
        reminders = []
        
    new_reminder = {
        "id": str(run_date.timestamp()),
        "run_date": run_date.isoformat(),
        "message": message.strip(),
        "status": "pending"
    }
    reminders.append(new_reminder)
    
    with open(REMINDER_FILE, 'w') as f:
        json.dump(reminders, f, indent=4)
        
    app.scheduler.add_job(
        func=_trigger_reminder,
        trigger='date',
        run_date=run_date,
        args=[app, new_reminder['id'], new_reminder['message']],
        id=new_reminder['id'],
        replace_existing=True
    )
    
    formatted_time = run_date.strftime("%I:%M %p on %A, %B %d")
    app.queue_log(f"Reminder set for {run_date.isoformat()} with ID: {new_reminder['id']}")
    return f"Okay, I will remind you to {message} at {formatted_time}."

def list_reminders(app, **kwargs):
    """Lists all pending reminders from the storage file."""
    if not os.path.exists(REMINDER_FILE) or os.path.getsize(REMINDER_FILE) == 0:
        return "You have no pending reminders."

    with open(REMINDER_FILE, 'r') as f:
        reminders = json.load(f)

    if not reminders:
        return "You have no pending reminders."

    reminders.sort(key=lambda r: r['run_date'])
    
    response_parts = ["Here are your pending reminders:"]
    for i, reminder in enumerate(reminders):
        run_date = datetime.fromisoformat(reminder['run_date'])
        formatted_time = run_date.strftime("%I:%M %p on %A")
        response_parts.append(f"Number {i+1}: {reminder['message']}, scheduled for {formatted_time}.")
        
    return "\n".join(response_parts)

def delete_reminder(app, item_number, **kwargs):
    """Deletes a specific reminder by its number."""
    try:
        item_index = int(item_number) - 1
    except ValueError:
        return "Please provide a valid number."

    if not os.path.exists(REMINDER_FILE) or os.path.getsize(REMINDER_FILE) == 0:
        return "You have no reminders to delete."

    with open(REMINDER_FILE, 'r') as f:
        reminders = json.load(f)

    if not reminders: return "You have no reminders to delete."

    reminders.sort(key=lambda r: r['run_date'])

    if 0 <= item_index < len(reminders):
        reminder_to_delete = reminders.pop(item_index)
        reminder_id = reminder_to_delete['id']

        try:
            if app.scheduler.get_job(reminder_id):
                app.scheduler.remove_job(reminder_id)
                app.queue_log(f"Unscheduled job with ID: {reminder_id}")
        except Exception as e:
            app.queue_log(f"Could not unschedule job {reminder_id}: {e}")

        with open(REMINDER_FILE, 'w') as f:
            json.dump(reminders, f, indent=4)
        
        return f"Okay, I have deleted reminder number {item_index + 1}."
    else:
        return "That's an invalid reminder number."

def register():
    """Registers all reminder-related commands."""
    return {
        'set_reminder': {
            'handler': set_reminder,
            'regex': r'\bremind me (?:at|in) (.+?) to (.+)',
            'params': ['time_phrase', 'message'],
            'description': "Sets a reminder for a specific time to deliver a message."
        },
        'list_reminders': {
            'handler': list_reminders,
            'regex': r'\b(show|what are|list) my reminders\b',
            'params': [],
            'description': "Lists all currently pending reminders."
        },
        'delete_reminder': {
            'handler': delete_reminder,
            'regex': r'\b(delete|cancel|remove) reminder(?: number)? (\d+)\b',
            'params': ['item_number'],
            'description': "Deletes a specific pending reminder by its number."
        }
    }