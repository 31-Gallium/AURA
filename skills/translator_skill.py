# skills/translator_skill.py
from googletrans import Translator, LANGUAGES

def translate_text(app, text, to_lang, **kwargs):
    """Translates a given text to a specified language."""
    try:
        translator = Translator()
        
        # Clean up the text input from potential quotes
        text_to_translate = text.strip().strip("'\"")
        target_language = to_lang.strip()
        
        dest_lang_code = None
        # Find the language code from the spoken language name
        for code, name in LANGUAGES.items():
            if target_language.lower() == name.lower():
                dest_lang_code = code
                break
        
        if not dest_lang_code:
            return f"I'm sorry, I don't recognize the language '{target_language}'."
            
        translated = translator.translate(text_to_translate, dest=dest_lang_code)
        return f"In {target_language.capitalize()}, that translates to: {translated.text}"
    except Exception as e:
        app.queue_log(f"Translation Error: {e}")
        return "I ran into an error while trying to translate that."

def register():
    """Registers translation commands."""
    return {
        'translate_text': {
            'handler': translate_text,
            'regex': r'\b(?:translate|how do you say)\b\s(?:\'|")?(.+?)(?:\'|")?\s(?:in|to)\s(.+)',
            'params': ['text', 'to_lang'],
            'description': "Translates a phrase from one language to another."
        }
    }