# skills/movie_skill.py
import requests

def find_movie_info(app, movie_title, **kwargs):
    """Finds information about a movie using The Movie Database (TMDB)."""
    api_key = app.config.get("tmdb_api_key")
    if not api_key or "YOUR" in api_key:
        return "The Movie Database API key is missing from my settings."

    try:
        # First, search for the movie to get its ID
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={api_key}&query={movie_title.strip()}"
        response = requests.get(search_url)
        response.raise_for_status()
        search_results = response.json()
        
        if not search_results['results']:
            return f"I couldn't find a movie called '{movie_title}'."
        
        movie_id = search_results['results'][0]['id']
        
        # Now, get the details for that movie ID
        details_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={api_key}"
        response = requests.get(details_url)
        response.raise_for_status()
        details = response.json()

        title = details.get('title')
        overview = details.get('overview')
        release_date = details.get('release_date', 'N/A')
        rating = details.get('vote_average', 0)
        
        return (f"{title}, released on {release_date}, has a rating of {rating:.1f} out of 10. "
                f"Here's a brief summary: {overview}")

    except Exception as e:
        app.queue_log(f"TMDB Error: {e}")
        return "I had trouble looking up that movie information."

def register():
    """Registers movie database commands."""
    return {
        'find_movie_info': {
            'handler': find_movie_info,
            'regex': r'\b(?:tell me about|what is|find)\b(?: the)? movie (.+)',
            'params': ['movie_title'],
            'description': "Looks up details about a specific movie, such as its summary, release date, and rating."
        }
    }