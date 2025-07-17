# skills/recipe_skill.py
import requests

def find_recipe(app, dish_name, **kwargs):
    """Finds a recipe using the Spoonacular API."""
    api_key = app.config.get("spoonacular_api_key")
    if not api_key or "YOUR" in api_key:
        return "The Spoonacular API key is missing from my settings."
        
    try:
        search_url = f"https://api.spoonacular.com/recipes/complexSearch?apiKey={api_key}&query={dish_name.strip()}&number=1"
        response = requests.get(search_url)
        response.raise_for_status()
        results = response.json()

        if not results['results']:
            return f"I couldn't find any recipes for '{dish_name}'."
            
        recipe_id = results['results'][0]['id']
        
        # Get the recipe details, including the source URL
        details_url = f"https://api.spoonacular.com/recipes/{recipe_id}/information?apiKey={api_key}"
        response = requests.get(details_url)
        response.raise_for_status()
        details = response.json()
        
        title = details.get('title')
        source_url = details.get('sourceUrl')
        
        return f"I found a recipe for {title}. You can find the full instructions at this URL: {source_url}"
        
    except Exception as e:
        app.queue_log(f"Spoonacular API Error: {e}")
        return "I had trouble finding a recipe right now."

def register():
    """Registers recipe commands."""
    return {
        'find_recipe': {
            'handler': find_recipe,
            'regex': r'\b(?:find|get|search for) a recipe for (.+)\b',
            'params': ['dish_name'],
            'description': "Finds a recipe for a specific dish or ingredient."
        }
    }