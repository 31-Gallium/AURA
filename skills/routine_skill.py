# skills/routine_skill.py
import time

def run_routine(app, routine_name, **kwargs):
    """
    Finds and executes a sequence of actions defined in a routine.
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
    app.speak_response(f"Starting routine: {found_routine_name}.")
    
    # Wait for the initial announcement to finish
    while app.speaking_active:
        time.sleep(0.25)
    
    # Execute each action in the sequence
    for action in found_routine_actions:
        action_type = action.get("type")
        params = action.get("params", {})
        
        if action_type in app.routine_actions:
            action_function = app.routine_actions[action_type]['func']
            
            # The action function might return a response to be spoken
            response = action_function(**params)
            if response and isinstance(response, str):
                app.speak_response(response)
            
            # Wait for the action's spoken response to complete before the next action
            time.sleep(0.5) 
            while app.speaking_active:
                time.sleep(0.25)
        else:
            app.queue_log(f"Unknown action type '{action_type}' in routine '{found_routine_name}'")

    # Return an empty space to signify the command was handled successfully
    return " "

def register():
    """Registers the command to run a routine."""
    return {
        'run_routine': {
            'handler': run_routine,
            'regex': r'\b(run|start|execute)\b(?: routine)? (.+)',
            'params': ['verb', 'routine_name'], # 'verb' captures run/start/execute but is unused
            'description': "Executes a pre-defined sequence of actions known as a routine."
        }
    }