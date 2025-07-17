# skills/help_skill.py
import re

def _generate_example_from_regex(regex_pattern, params):
    """
    A robust helper function to turn a complex regex pattern into a simple,
    human-readable example command.
    """
    if not regex_pattern:
        return ""
        
    # Start with the raw pattern
    example = regex_pattern
    
    # Sequentially replace capture groups with named <parameters>
    capture_group_pattern = r'\((?!\?:)[^)]+\)' 
    for param in params:
        example = re.sub(capture_group_pattern, f"<{param}>", example, count=1)

    # Simplify non-capturing groups like (?:word|another|etc) to just the first word
    example = re.sub(r'\(\?:([^|)]+).*?\)', r'\1', example)

    # Clean up remaining regex syntax for readability
    example = example.replace('?', '').replace('\\b', '')
    example = example.replace('^', '').replace('$', '')
    example = example.replace('(?:', '(').replace(')', '') # Clean up group markers
    example = re.sub(r'\s+', ' ', example) # Condense multiple spaces into one

    return example.strip()

def show_help_menu(app, **kwargs):
    """
    Inspects all registered commands and generates a formatted help message.
    """
    command_map = app.command_handler.command_map
    if not command_map:
        return "There are no skills or commands currently loaded."
        
    response_parts = ["Here are the commands I understand:"]
    
    # Use a set to avoid showing duplicate-looking examples
    generated_examples = set()
    
    # Create a sorted list for a clean, predictable output
    sorted_command_names = sorted(command_map.keys())
    
    for cmd_name in sorted_command_names:
        cmd_data = command_map[cmd_name]
        regex = cmd_data.get('regex')
        params = cmd_data.get('params', [])
        
        if regex:
            example = _generate_example_from_regex(regex, params)
            if example and example not in generated_examples:
                response_parts.append(f"- {example}")
                generated_examples.add(example)
        
    # Join with newlines for clean formatting in the main chat window
    return "\n".join(response_parts)

def register():
    """Registers the help command itself."""
    return {
        'show_help': {
            'handler': show_help_menu,
            'regex': r'^/(help|commands)$',
            'params': [],
            'description': "Displays a list of all available commands and their usage."
        }
    }