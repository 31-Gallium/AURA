# skills/wolfram_skill.py
import wolframalpha

def ask_wolfram(app, query, **kwargs):
    """Sends a query to the WolframAlpha API for a computational answer."""
    api_key = app.config.get("wolfram_alpha_appid")
    if not api_key or "YOUR" in api_key:
        return "The WolframAlpha AppID is missing from my settings."
    
    try:
        client = wolframalpha.Client(api_key)
        res = client.query(query)
        
        # The 'next(res.results).text' will get the primary plaintext result
        answer = next(res.results).text
        return f"According to WolframAlpha, the answer is: {answer}."
    except StopIteration:
        return "WolframAlpha did not have a direct answer for that."
    except Exception as e:
        app.queue_log(f"WolframAlpha Error: {e}")
        return "I had trouble getting an answer from WolframAlpha."

def register():
    """Registers WolframAlpha query commands."""
    return {
        'ask_wolfram': {
            'handler': ask_wolfram,
            'regex': r'\b(calculate|compute|ask wolfram) (.+)',
            'params': ['verb', 'query'], # 'verb' captures calculate/compute but is unused
            'description': "Use ONLY for questions that require mathematical calculations, data analysis, or specific scientific computation. Do NOT use for general questions."
        }
    }