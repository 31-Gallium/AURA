# command_handler.py
import re
import traceback
import os
import importlib
import inspect # <-- Make sure this import is present

class CommandHandler:
    def __init__(self, app_controller):
        self.app = app_controller
        self.log = self.app.queue_log
        self.command_map = {}
        self._load_skills()

    def _load_skills(self):
        """Loads all skills and their regex commands from the skills directory."""
        self.log("Loading skill commands for Hybrid Engine...")
        self.command_map.clear()
        skills_dir = "skills"
        enabled_skills = self.app.config.get("enabled_skills", {})

        for filename in os.listdir(skills_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                if not enabled_skills.get(filename, True):
                    continue
                
                skill_name = filename[:-3]
                module_name = f"skills.{skill_name}"
                try:
                    skill_module = importlib.import_module(module_name)
                    importlib.reload(skill_module)
                    if hasattr(skill_module, 'register'):
                        self.command_map.update(skill_module.register())
                except Exception as e:
                    self.log(f"ERROR loading skill '{skill_name}': {e}\n{traceback.format_exc()}", "ERROR")
        self.log("Hybrid Engine regex commands loaded.")

    # --- THIS IS THE CORRECTED METHOD ---
    def get_tools_for_ai(self):
        """Generates a list of all available skills formatted as tools for the AI."""
        tools = []
        for name, data in self.command_map.items():
            # Only expose skills that have a description for the AI to understand
            if data.get('description'):
                tool_info = {
                    "name": name,
                    "description": data['description'],
                    "parameters": {
                        "type": "object",
                        "properties": {param: {"type": "string"} for param in data.get('params', [])}
                    }
                }
                # If there are parameters, specify which are required.
                if data.get('params'):
                    tool_info["parameters"]["required"] = data.get('params', [])
                
                tools.append(tool_info)
        return tools

    def handle(self, command, attached_file=None):
        """
        Attempts to handle a command using direct regex matching.
        Returns a response string if a match is found, otherwise returns None.
        """
        command_lower = command.lower().strip()
        
        for cmd_name in sorted(self.command_map.keys()):
            cmd_data = self.command_map[cmd_name]
            regex_pattern = cmd_data.get('regex')
            
            if not regex_pattern:
                continue

            try:
                if re.match(r'^\s*' + regex_pattern.lstrip('^'), command_lower, re.IGNORECASE):
                    self.log(f"Hybrid Engine: Direct regex match found for skill '{cmd_name}'.")
                    
                    handler_func = cmd_data['handler']
                    param_names = cmd_data.get('params', [])
                    
                    match = re.search(regex_pattern, command_lower, re.IGNORECASE)
                    kwargs = {name: match.group(i + 1) for i, name in enumerate(param_names)}
                    kwargs['command'] = command
                    kwargs['attached_file'] = attached_file
                    
                    return handler_func(self.app, **kwargs)
            except Exception as e:
                self.log(f"ERROR executing regex-matched skill '{cmd_name}': {e}\n{traceback.format_exc()}", "ERROR")
                continue
        
        return None