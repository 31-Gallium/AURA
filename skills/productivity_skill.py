# skills/productivity_skill.py
import os
import json
import pyperclip
import random
from datetime import datetime

# --- Handler Functions ---

def read_clipboard(app, **kwargs):
    """Reads the current content of the system clipboard."""
    try:
        content = pyperclip.paste()
        return f"The clipboard contains: {content}" if content else "The clipboard is empty."
    except Exception as e:
        app.queue_log(f"Error reading clipboard: {e}")
        return "I had trouble accessing the clipboard."

def write_to_clipboard(app, content, **kwargs):
    """Writes specified content to the system clipboard."""
    try:
        pyperclip.copy(content)
        return f"I've copied '{content}' to the clipboard."
    except Exception as e:
        app.queue_log(f"Error writing to clipboard: {e}")
        return "I had trouble accessing the clipboard."

def read_notes(app, note_file="notes.txt", **kwargs):
    """Reads all entries from the notes.txt file."""
    try:
        if os.path.exists(note_file):
            with open(note_file, 'r', encoding='utf-8') as f:
                notes = f.read()
            return f"Here are your notes:\n{notes}" if notes.strip() else "Your notes file is empty."
        return "You don't have a notes file yet."
    except Exception as e:
        app.queue_log(f"Error with notes file: {e}")
        return "I had trouble with your notes file."

def write_note(app, content, note_file="notes.txt", **kwargs):
    """Appends a new, timestamped note to the notes.txt file."""
    try:
        with open(note_file, 'a', encoding='utf-8') as f:
            f.write(f"- {content.strip()} ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n")
        return "I've added that to your notes."
    except Exception as e:
        app.queue_log(f"Error with notes file: {e}")
        return "I had trouble with your notes file."

def _load_todo_list(todo_file="todolist.json"):
    """Helper to load the to-do list from a JSON file."""
    if os.path.exists(todo_file):
        with open(todo_file, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return []
    return []

def _save_todo_list(data, todo_file="todolist.json"):
    """Helper to save the to-do list to a JSON file."""
    with open(todo_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def read_todo_list(app, **kwargs):
    """Reads all items from the to-do list."""
    todo_list = _load_todo_list()
    if not todo_list:
        return "Your to-do list is empty."
    tasks = ", ".join([task['item'] for task in todo_list if not task.get('done')])
    return f"Your to-do list contains: {tasks}." if tasks else "You've completed all your tasks!"

def add_to_todo_list(app, item, **kwargs):
    """Adds an item to the to-do list."""
    todo_list = _load_todo_list()
    todo_list.append({"item": item.strip(), "done": False})
    _save_todo_list(todo_list)
    return f"I've added '{item.strip()}' to your to-do list."

def remove_from_todo_list(app, item, **kwargs):
    """Removes an item from the to-do list."""
    todo_list = _load_todo_list()
    item_lower = item.lower().strip()
    original_count = len(todo_list)
    todo_list = [task for task in todo_list if task['item'].lower() != item_lower]
    if len(todo_list) < original_count:
        _save_todo_list(todo_list)
        return f"I've removed '{item}' from your to-do list."
    return f"I couldn't find '{item}' on your list."

def tell_joke(app, **kwargs):
    """Returns a random joke."""
    jokes = [
        "Why don’t scientists trust atoms? Because they make up everything!",
        "I'm reading a book on anti-gravity. It's impossible to put down!",
        "Why did the scarecrow win an award? Because he was outstanding in his field!"
    ]
    return random.choice(jokes)

def show_clipboard_history(app, **kwargs):
    """Reads out the items in the clipboard history."""
    if not app.clipboard_history:
        return "Your clipboard history is empty."
    response = "Here are the latest items from your clipboard history: "
    for i, item in enumerate(app.clipboard_history[:5]):
        response += f"Item {i+1}: {item[:50]}. "
    return response

def copy_from_history(app, item_number, **kwargs):
    """Copies a specific item from the history back to the clipboard."""
    try:
        item_index = int(item_number) - 1
        if 0 <= item_index < len(app.clipboard_history):
            content_to_copy = app.clipboard_history[item_index]
            pyperclip.copy(content_to_copy)
            return f"I've copied item {item_index + 1} back to your clipboard."
        else:
            return "That's an invalid item number."
    except Exception as e:
        app.queue_log(f"Error copying from history: {e}")
        return "I had trouble copying that item from the history."

def clear_clipboard_history(app, **kwargs):
    """Clears all items from the clipboard history."""
    app.clipboard_history.clear()
    app.last_clipboard_content = ""
    app.queue_log("Clipboard history cleared by user.")
    return "I have cleared your clipboard history."

def register():
    """Registers all productivity-related commands."""
    return {
        'read_clipboard': {
            'handler': read_clipboard,
            'regex': r'\bwhat(?:\'s| is) on (?:my|the) clipboard\b',
            'params': [],
            'description': "Reads the current text content from the computer's clipboard."
        },
        'write_to_clipboard': {
            'handler': write_to_clipboard,
            'regex': r'\bcopy (.+?) to (?:my|the) clipboard\b',
            'params': ['content'],
            'description': "Writes specified content to the system clipboard."
        },
        'read_notes': {
            'handler': read_notes,
            'regex': r'\bread my notes\b',
            'params': [],
            'description': "Reads all entries from the user's notes.txt file."
        },
        'write_note': {
            'handler': write_note,
            'regex': r'\b(take a note|add a note|note down)(?: that)? (.+)',
            'params': ['command', 'content'], # command is unused, but captures the verb
            'description': "Appends a new, timestamped note to the notes.txt file."
        },
        'read_todo_list': {
            'handler': read_todo_list,
            'regex': r'\bwhat(?:\'s| is) on my to-?do list\b',
            'params': [],
            'description': "Reads all items from the to-do list."
        },
        'add_to_todo_list': {
            'handler': add_to_todo_list,
            'regex': r'\badd (.+?) to my to-?do list\b',
            'params': ['item'],
            'description': "Adds a new task to the user's to-do list."
        },
        'remove_from_todo_list': {
            'handler': remove_from_todo_list,
            'regex': r'\bremove (.+?) from my to-?do list\b',
            'params': ['item'],
            'description': "Removes a task from the to-do list."
        },
        'tell_joke': {
            'handler': tell_joke,
            'regex': r'\b(tell me a joke|make me laugh)\b',
            'params': [],
            'description': "Tells the user a random, pre-written joke."
        },
        'show_clipboard_history': {
            'handler': show_clipboard_history,
            'regex': r'\bshow(?: my)? clipboard history\b',
            'params': [],
            'description': "Reads out the latest items from the clipboard history."
        },
        'copy_from_history': {
            'handler': copy_from_history,
            'regex': r'\bcopy item (\d+) from(?: my)? history\b',
            'params': ['item_number'],
            'description': "Copies a specific item from the clipboard history back to the clipboard."
        },
        'clear_clipboard_history': {
            'handler': clear_clipboard_history,
            'regex': r'\bclear(?: my)? clipboard history\b',
            'params': [],
            'description': "Clears all items from the clipboard history."
        },
    }