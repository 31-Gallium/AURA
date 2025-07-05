# In skills/web_skill.py
import re
import webbrowser
import socket
import requests
import urllib.parse
import subprocess
from bs4 import BeautifulSoup
from googleapiclient.discovery import build

def is_online(log_callback=None):
    """Checks for a live internet connection."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        if log_callback: log_callback("Connectivity check: Online.")
        return True
    except OSError:
        if log_callback: log_callback("Connectivity check: Offline.")
        return False

def get_weather(app, city, **kwargs):
    """Gets the weather for a specific city."""
    api_key = app.config.get("weather_api_key")
    if not api_key or "YOUR" in api_key:
        return "The Weather API key is missing. Please add it in the settings."
    base_url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key, "units": "metric"}
    try:
        response = requests.get(base_url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        weather_desc = data["weather"][0]["description"].capitalize()
        temp = data["main"]["temp"]
        return f"Currently in {city}, it's {temp:.0f} degrees Celsius with {weather_desc}."
    except Exception as e:
        app.queue_log(f"Weather error: {e}")
        return "An unexpected error occurred while getting the weather."

def get_news_headlines(app, **kwargs):
    """Scrapes the top headlines from BBC News."""
    try:
        app.queue_log("Fetching news headlines from BBC News...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get("https://www.bbc.com/news", headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        headlines = soup.find_all('h2', {'data-testid': 'card-headline'})
        if not headlines:
            return "I couldn't find the headlines on the page."
        headline_texts = [h.get_text() for h in headlines[:3]]
        return "Here are the top headlines from BBC News. First: " + ". Next: ".join(headline_texts)
    except Exception as e:
        app.queue_log(f"Error scraping news: {e}")
        return "I'm sorry, I couldn't fetch the news headlines right now."

def summarize_web_page(app, url, **kwargs):
    """Fetches content from a URL and uses an AI model to summarize it."""
    if not url.startswith('http'):
        url = 'https://' + url
    app.speak_response("Okay, I'm reading the page now. This might take a moment...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        paragraphs = soup.find_all('p')
        if not paragraphs:
            return "I couldn't find any readable text on that page."
        page_text = ' '.join(p.get_text() for p in paragraphs)[:15000]
        from ai_logic import get_ai_response
        summary_prompt = f"Please provide a concise, easy-to-understand summary of the following web page content:\n\n{page_text}"
        return get_ai_response(app.answer_model, [], summary_prompt, app.queue_log)
    except Exception as e:
        app.queue_log(f"Failed to scrape or summarize URL {url}: {e}")
        return "I'm sorry, I had trouble reading or summarizing that web page."

def search_in_browser(app, query, **kwargs):
    """Opens a search query or a direct URL in the default browser."""
    if re.search(r'\.[a-z]{2,}', query.lower()) or query.lower().startswith(('http', 'www.')):
        target_url = query if query.startswith('http') else 'https://' + query
    else:
        target_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
    try:
        webbrowser.open(target_url)
        return f"Okay, opening '{query}'."
    except Exception as e:
        app.queue_log(f"Error during browser action: {e}")
        return "I ran into an error while trying to open the browser."

def register():
    """Registers all web-related commands with regex."""
    return {
        'get_weather': {
            'handler': get_weather,
            'regex': r'what is the weather(?: like)? in (.+)',
            'params': ['city']
        },
        'get_news_headlines': {
            'handler': get_news_headlines,
            'regex': r'(?:get|read|tell me the) news headlines',
            'params': []
        },
        'summarize_web_page': {
            'handler': summarize_web_page,
            'regex': r'summarize(?: the)?(?: web)? page (.+)',
            'params': ['url']
        },
        'search_in_browser': {
            'handler': search_in_browser,
            'regex': r'(?:google|search)(?: for)? (.+)',
            'params': ['query']
        }
    }