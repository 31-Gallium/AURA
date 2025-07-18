# skills/web_skill.py
import re
import webbrowser
import socket
import requests
import urllib.parse
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

def is_online(log_callback=None):
    """Checks for a live internet connection."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        if log_callback: log_callback("Connectivity check: Online.")
        return True
    except OSError:
        if log_callback: log_callback("Connectivity check: Offline.")
        return False

def perform_web_search(app, query, **kwargs):
    """Performs a web search using DuckDuckGo and returns a summary of results."""
    app.queue_log(f"Performing web search for: {query}")
    try:
        with DDGS() as ddgs:
            # Fetch more results to increase the chance of finding relevant context
            results = [r for r in ddgs.text(query, max_results=10)] # Changed from 5 to 10
        
        if not results:
            return "I couldn't find any web results for that query."
            
        # Combine the text snippets from the search results into a single context string
        context = " ".join([f"Snippet from a webpage: {r['body']}" for r in results])
        
        # Return a generous amount of text for the main AI to summarize
        return context[:4000]

    except Exception as e:
        app.queue_log(f"Error performing web search for '{query}': {e}")
        return "I'm sorry, I ran into an error while searching the web."

def get_news_headlines(app, **kwargs):
    """Scrapes the top headlines from a reliable news source."""
    try:
        app.queue_log("Fetching news headlines from BBC News...")
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get("https://www.bbc.com/news", headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        # This selector is specific to BBC News and may need updating if their site changes
        headlines = soup.find_all('h2', {'data-testid': 'card-headline'})
        if not headlines: return "I couldn't find the headlines on the page."
        # Get the text of the first 3 headlines
        headline_texts = [h.get_text() for h in headlines[:3]]
        return "Here are the top headlines from BBC News. First: " + ". Next: ".join(headline_texts)
    except Exception as e:
        app.queue_log(f"Error scraping news: {e}")
        return "I'm sorry, I couldn't fetch the news headlines right now."

def search_in_browser(app, query, **kwargs):
    """Opens a search query in the default web browser."""
    try:
        search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query)}"
        webbrowser.open(search_url)
        return f"Okay, I'm searching for '{query}' in your browser."
    except Exception as e:
        app.queue_log(f"Error opening browser for search: {e}")
        return "I ran into an error while trying to open the browser."

def register():
    """Registers all web-related commands."""
    return {
        'perform_web_search': {
            'handler': perform_web_search,
            'regex': None,  # This skill is AI-only, it has no direct regex trigger
            'params': ['query'],
            'description': "Use for questions about news, current events, facts, or any topic that requires up-to-date information from the internet."
        },
        'get_news_headlines': {
            'handler': get_news_headlines,
            'regex': r'\b(get|read|tell me the) news(?: headlines)?\b',
            'params': [],
            'description': "Fetches and reads the latest news headlines."
        },
        'search_in_browser': {
            'handler': search_in_browser,
            'regex': r'\b(google|search for|find on the web) (.+)\b',
            'params': ['verb', 'query'], # 'verb' captures google/search for, but is unused
            'description': "Opens a Google search for a topic in the default web browser."
        }
    }