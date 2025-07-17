# skills/wikipedia_skill.py
import wikipedia

def get_wiki_summary(app, query, **kwargs):
    """Fetches a concise summary of a topic from Wikipedia."""
    try:
        # Get a summary of the first 3-4 sentences for a good overview.
        summary = wikipedia.summary(query, sentences=4, auto_suggest=True, redirect=True)
        return summary
    except wikipedia.exceptions.DisambiguationError as e:
        # If the term is ambiguous, return the top options.
        options = ", ".join(e.options[:3])
        return f"That could mean a few things, like {options}. Please be more specific."
    except wikipedia.exceptions.PageError:
        return f"I'm sorry, I couldn't find a Wikipedia page for '{query}'."
    except Exception as e:
        app.queue_log(f"Wikipedia Error: {e}")
        return "I had trouble getting information from Wikipedia."

def register():
    """Registers the Wikipedia skill. It has no direct regex trigger."""
    return {
        'get_wiki_summary': {
            'handler': get_wiki_summary,
            'regex': None, # This skill is intended to be called by the AI, not by a direct regex match.
            'params': ['query'],
            'description': "Gets a concise summary about a person, place, or topic from Wikipedia. Best for factual, encyclopedic queries."
        }
    }