# In skills/joke_skill.py
import random

def tell_joke(app, **kwargs):
    """Selects and returns a random joke from a predefined list."""
    jokes = [
        "Why don’t scientists trust atoms? Because they make up everything!",
        "I'm reading a book on anti-gravity. It's impossible to put down!",
        "Why did the scarecrow win an award? Because he was outstanding in his field!",
        "What do you call a fake noodle? An Impasta!",
        "Why don't skeletons fight each other? They don't have the guts.",
        "I told my wife she should embrace her mistakes. She gave me a hug."
    ]
    return random.choice(jokes)

def register():
    """Registers the joke-telling command with regex."""
    return {
        'tell_joke': {
            'handler': tell_joke,
            'regex': r'tell me a joke',
            'params': []
        }
    }