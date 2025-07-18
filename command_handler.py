# command_handler.py
import re
import traceback
import os
import importlib

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
                        # Add all registered commands to the map
                        self.command_map.update(skill_module.register())
                except Exception as e:
                    self.log(f"ERROR loading skill '{skill_name}': {e}\n{traceback.format_exc()}", "ERROR")
        self.log("Hybrid Engine regex commands loaded.")

    # --- NEW METHOD ---
    def get_tools_for_ai(self):
        """Generates a list of all available skills formatted as tools for the AI."""
        tools = []
        for name, data in self.command_map.items():
            # Only expose skills that have a description (the AI needs it to understand the tool)
            if data.get('description'):
                tool_info = {
                    "name": name,
                    "description": data['description'],
                    "parameters": {param: "string" for param in data.get('params', [])}
                }
                tools.append(tool_info)
        return tools

    def handle(self, command, attached_file=None):
        """
        Attempts to handle a command using direct regex matching.
        Returns a response string if a match is found, otherwise returns None.
        """
        command_lower = command.lower().strip()
        
        # Iterate through a sorted list for predictable behavior
        for cmd_name in sorted(self.command_map.keys()):
            cmd_data = self.command_map[cmd_name]
            regex_pattern = cmd_data.get('regex')
            
            # Skip skills that are meant to be AI-only tools
            if not regex_pattern:
                continue

            try:
                # --- FIX: Anchored regex to prevent accidental mid-sentence matches ---
                if re.match(r'^\s*' + regex_pattern.lstrip('^'), command_lower, re.IGNORECASE):
                    self.log(f"Hybrid Engine: Direct regex match found for skill '{cmd_name}'.")
                    
                    handler_func = cmd_data['handler']
                    param_names = cmd_data.get('params', [])
                    
                    # We need to re-run the search to get the match object for parameters
                    match = re.search(regex_pattern, command_lower, re.IGNORECASE)
                    kwargs = {name: match.group(i + 1) for i, name in enumerate(param_names)}
                    kwargs['command'] = command
                    kwargs['attached_file'] = attached_file
                    
                    return handler_func(self.app, **kwargs)
            except Exception as e:
                self.log(f"ERROR executing regex-matched skill '{cmd_name}': {e}\n{traceback.format_exc()}", "ERROR")
                continue
        
        # If no regex pattern matched after checking all skills, return None
        return None