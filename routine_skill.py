# In skills/routine_skill.py
import time
import re

def run_routine(app, routine_name, **kwargs):
    """
    Finds and executes a sequence of actions defined in a routine.
    The routine_name is passed directly from the command handler's regex match.
    """
    all_routines = app.config.get("routines", {})
    
    # Case-insensitive search for the routine name
    found_routine_actions = None
    found_routine_name = ""
    for name, actions in all_routines.items():
        if name.lower() == routine_name.lower().strip():
            found_routine_actions = actions
            found_routine_name = name
            break

    if not found_routine_actions:
        return f"I couldn't find a routine named '{routine_name}'."

    app.queue_log(f"Executing routine: {found_routine_name}")
    
    # Execute each action in the sequence
    for action in found_routine_actions:
        action_type = action.get("type")
        params = action.get("params", {})
        
        if action_type in app.routine_actions:
            action_function = app.routine_actions[action_type]['function']
            action_function(params)
            
            # Wait for the initial speech to start before polling
            time.sleep(0.5) 
            # Poll the is_speaking flag. The loop will only proceed
            # once AURA has finished speaking the response for the current action.
            while app.is_speaking:
                time.sleep(0.25)
        else:
            app.queue_log(f"Unknown action type '{action_type}' in routine '{found_routine_name}'")

    # Give a final small delay before the routine ends
    time.sleep(0.5)
    return " " # Return an empty space to prevent a "command not found" fallback

def register():
    """Registers the command to run a routine using a regex pattern."""
    return {
        'run_routine': {
            'handler': run_routine,
            # This regex matches "run morning check", "start routine morning check", etc.
            'regex': r'(?:run|start)(?: routine)? (.+)',
            # This captures the routine name and maps it to the 'routine_name' parameter.
            'params': ['routine_name']
        }
    }