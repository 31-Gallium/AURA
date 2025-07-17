import subprocess
import os
import traceback

def _find_app_in_start_menu(app_name):
    app_name_lower = app_name.lower()
    start_menu_folders = [
        os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        os.path.join(os.environ['ALLUSERSPROFILE'], 'Microsoft', 'Windows', 'Start Menu', 'Programs')
    ]
    for folder in start_menu_folders:
        for root, _, files in os.walk(folder):
            for name in files:
                if name.lower().endswith((".lnk", ".url")):
                    shortcut_name = os.path.splitext(name)[0].lower()
                    if app_name_lower in shortcut_name:
                        return os.path.join(root, name)
    return None

def launch_app(app, app_name, **kwargs):
    try:
        alias = app_name.lower().strip()
        path_info = app.config.get("app_paths", {}).get(alias)
        
        if path_info and os.path.exists(path_info):
            os.startfile(path_info)
            return f"Opening {alias}."

        shortcut_path = _find_app_in_start_menu(alias)
        if shortcut_path:
            os.startfile(shortcut_path)
            return f"Opening {alias}."

        return f"I couldn't find an application or shortcut called '{app_name}'."
    except Exception as e:
        app.queue_log(f"Error launching '{app_name}': {e}\n{traceback.format_exc()}")
        return f"I ran into an error trying to open that."

def close_app(app, app_name, **kwargs):
    try:
        target_name = app_name.strip()
        if not target_name.endswith('.exe'):
            target_name += '.exe'
        
        # Use TASKKILL which is more robust
        result = subprocess.run(f'taskkill /f /im "{target_name}"', check=True, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            return f"I've closed {app_name}."
        else:
            return f"I couldn't find a process named {target_name} to close."
            
    except subprocess.CalledProcessError:
        return f"I couldn't find an application named {app_name} running."
    except Exception as e:
        return f"I ran into an error trying to close {app_name}."

def register():
    return {
        'launch_app': {
            'handler': launch_app,
            'regex': r'\b(?:open|launch|start)\b\s(?:an? )?(.+?)(?:\s(?:app|application))?$',
            'params': ['app_name'],
            'description': "Opens or launches a specific application on the computer."
        },
        'close_app': {
            'handler': close_app,
            'regex': r'\b(?:close|quit|exit|terminate)\b\s(?:the\s)?(.+?)(?:\s(?:app|application))?$',
            'params': ['app_name'],
            'description': "Closes or terminates a running application on the computer."
        }
    }