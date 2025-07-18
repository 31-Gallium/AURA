# skills/weather_skill.py
import requests

def get_weather(app, city=None, **kwargs):
    """
    Fetches the current weather for a given location.
    If no location is specified, it uses the default from the config.
    """
    api_key = app.config.get("weather_api_key")
    if not api_key or "YOUR" in api_key:
        return "The Weather API key is missing or not set in my settings."

    if not city:
        city = app.config.get("default_location", "Dubai")
        app.queue_log(f"No weather location in command, using default: '{city}'")

    base_url = "http://api.openweathermap.org/data/2.5/weather?"
    complete_url = f"{base_url}appid={api_key}&q={city.strip()}&units=metric"

    try:
        response = requests.get(complete_url)
        response.raise_for_status()
        data = response.json()

        if data.get("cod") != 200:
            return f"Sorry, I couldn't find the weather for {city}."

        main = data.get("main", {})
        temp = main.get("temp")
        weather_desc = data.get("weather", [{}])[0].get("description", "no description")
        
        return (f"Currently in {data.get('name', city)}, it's {int(temp)} degrees Celsius"
                f" with {weather_desc}.")

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return f"I couldn't find a city named '{city}'. Please check the spelling."
        else:
            app.queue_log(f"Weather API HTTP Error: {e}")
            return "I'm having trouble connecting to the weather service right now."
    except Exception as e:
        app.queue_log(f"An error occurred in the weather skill: {e}")
        return "I'm sorry, I had trouble connecting to the weather service."


def register():
    """Registers weather commands with flexible regex patterns."""
    return {
        'get_weather_in_city': {
            'handler': get_weather,
            'regex': r'^\s*what(?:\'s| is) the (?:weather|temperature)(?: like)? in (.+)',
            'params': ['city'],
            'description': "Gets the current weather for a specific city."
        },
        'get_weather_default': {
            'handler': get_weather,
            # FIX: Added '$' to anchor the match to the end of the string.
            'regex': r'^\s*what(?:\'s| is) the (?:weather|temperature)\s*$',
            'params': [],
            'description': "Gets the current weather for the user's default location if no city is specified."
        }
    }