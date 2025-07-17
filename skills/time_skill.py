# skills/time_skill.py
from datetime import datetime
import requests

def _get_day_suffix(d):
    """Helper function to get the correct suffix for the day (st, nd, rd, th)."""
    return "th" if 11 <= d <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(d % 10, "th")

def get_current_time(app, **kwargs):
    """Gets the user's current local time."""
    now = datetime.now()
    time_str = now.strftime("%I:%M %p").lstrip('0')
    return f"The current time is {time_str}."

def get_current_date(app, **kwargs):
    """Gets the current local date."""
    now = datetime.now()
    date_str = now.strftime(f"%A, %B {now.day}{_get_day_suffix(now.day)}, %Y")
    return f"Today's date is {date_str}."

def get_time_for_city(app, city, **kwargs):
    """Gets the current time for a specific city using an online API."""
    try:
        # Using the free worldtimeapi.org API
        # We replace spaces with underscores for the API call
        response = requests.get(f"http://worldtimeapi.org/api/timezone/{city.replace(' ', '_')}")
        response.raise_for_status()
        data = response.json()
        
        # The datetime string includes timezone info, so we can parse it directly
        city_time = datetime.fromisoformat(data['datetime'])
        time_str = city_time.strftime("%I:%M %p").lstrip('0')
        timezone = data.get('abbreviation', '')
        
        return f"The time in {city} is {time_str} {timezone}."

    except Exception as e:
        app.queue_log(f"WorldTimeAPI Error for '{city}': {e}")
        # Fallback for a common case where the city name is not a valid timezone
        if "unknown location" in str(e).lower() or "unknown timezone" in str(e).lower():
            return f"I couldn't find a timezone for '{city}'. Please try a major city in that region."
        return f"I had trouble finding the time for {city}."

def register():
    """Registers all time and date related commands."""
    return {
        'get_current_time': {
            'handler': get_current_time,
            'regex': r"\bwhat(?:\'s| is) the time\b$",
            'params': [],
            'description': "Gets the user's current local time. Use only if no specific city is mentioned."
        },
        'get_time_for_city': {
            'handler': get_time_for_city,
            'regex': r"\b(?:what(?:\'s| is)|tell me) the time in (.+)",
            'params': ['city'],
            'description': "Gets the current time for a specific city or location."
        },
        'get_date': {
            'handler': get_current_date,
            'regex': r"\bwhat(?:\'s| is) today(?:\'s)? date\b",
            'params': [],
            'description': "Gets the current local date."
        }
    }