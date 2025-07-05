import os
import importlib.util
import re

class CommandHandler:
    def __init__(self, app_controller):
        self.app = app_controller
        self.log = self.app.queue_log
        self.skills = {}
        self._load_skills()

    def _load_skills(self):
        skills_dir = "skills"
        if not os.path.exists(skills_dir):
            return

        self.skills.clear()
        for filename in os.listdir(skills_dir):
            if filename.endswith(".py") and not filename.startswith("__"):
                try:
                    path = os.path.join(skills_dir, filename)
                    module_name = f"skills.{filename[:-3]}"
                    spec = importlib.util.spec_from_file_location(module_name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, 'register'):
                        self.skills.update(module.register())
                        self.log(f"Successfully loaded skill: {filename}")
                except Exception as e:
                    self.log(f"Failed to load skill '{filename}': {e}")
    
    def handle(self, command, attached_file=None):
        """
        Finds and executes the best matching skill by iterating through regex patterns.
        """
        command_lower = command.lower()

        # Iterate through all registered skills
        for skill_name, info in self.skills.items():
            regex_pattern = info.get('regex')
            if not regex_pattern:
                continue

            # Check if the command matches the skill's regex
            match = re.search(regex_pattern, command_lower)
            if match:
                self.log(f"Regex match found for skill: '{skill_name}'")
                
                captured_groups = match.groups()
                param_names = info.get('params', [])
                params_dict = dict(zip(param_names, captured_groups))

                try:
                    # Call the handler with the extracted parameters
                    return info['handler'](self.app, **params_dict)
                except TypeError as e:
                    self.log(f"TypeError calling handler for '{skill_name}': {e}.")
                    return "I understood the command, but there was a parameter error."

        # If the loop finishes with no matches, fall back to the main app controller.
        self.log(f"Command '{command}' could not be matched to any skill regex.")
        return None