# In skills/window_skill.py
import pygetwindow as gw
import re

def list_windows(app, **kwargs):
    """Lists all currently open, non-minimized window titles."""
    try:
        all_titles = gw.getAllTitles()
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
    action_norm = "focus" if action in ["focus on", "switch to"] else action
    target_title_lower = title.strip().lower()

    try:
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
    """Registers the window control commands with regex."""
    return {
        'list_windows': {
            'handler': list_windows,
            'regex': r'list(?: all)?(?: open)? windows',
            'params': []
        },
        'manage_window': {
            'handler': manage_window_by_title,
            'regex': r'(focus on|switch to|close|minimize)(?: the)?(?: window)? (.+)',
            'params': ['action', 'title']
        }
    }