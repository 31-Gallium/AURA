# skills/window_skill.py
import pygetwindow as gw
import re

def list_windows(app, **kwargs):
    """Lists all currently open, non-minimized window titles."""
    try:
        all_titles = gw.getAllTitles()
        # Filter out empty strings that can sometimes be returned
        visible_titles = [title for title in all_titles if title]
        if not visible_titles:
            return "There are no open windows to list."
        return "Here are the currently open windows: " + ", ".join(visible_titles)
    except Exception as e:
        app.queue_log(f"Error listing windows: {e}")
        return "I had trouble getting the list of open windows."

def manage_window_by_title(app, action, title, **kwargs):
    """Focuses, minimizes, or closes a window based on its title."""
    log_callback = app.queue_log
    action_norm = "focus" if "switch to" in action else action.strip()
    target_title_lower = title.strip().lower()

    try:
        # Find the first window that contains the target title text
        target_window = next((w for w in gw.getAllWindows() if target_title_lower in w.title.lower()), None)
        
        if not target_window:
            return f"I couldn't find an open window with the title '{title}'."

        if action_norm == "focus":
            target_window.activate()
            return f"Switching to {target_window.title}."
        elif action_norm == "close":
            target_window.close()
            return f"Closed {target_window.title}."
        elif action_norm == "minimize":
            target_window.minimize()
            return f"Minimized {target_window.title}."
    except Exception as e:
        log_callback(f"Error managing window: {e}")
        return "I ran into a problem trying to manage that window."

def register():
    """Registers the window control commands."""
    return {
        'list_windows': {
            'handler': list_windows,
            'regex': r'\blist(?: all)?(?: open)? windows\b',
            'params': [],
            'description': "Lists the titles of all currently open application windows."
        },
        'manage_window': {
            'handler': manage_window_by_title,
            'regex': r'\b(focus on|switch to|close|minimize)\b(?: the)?(?: window)? (.+)',
            'params': ['action', 'title'],
            'description': "Performs an action (focus, close, minimize) on an open application window by its title."
        }
    }