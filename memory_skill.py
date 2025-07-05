# In skills/memory_skill.py

import os
import json
import re

# Define the path for our persistent memory storage file
MEMORY_FILE = "memory.json"

def _load_memory():
    """Loads the memory list from the JSON file."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f:
            try:
                # The memory is now a list of strings
                return json.load(f)
            except json.JSONDecodeError:
                return [] # Return empty list if file is corrupted or empty
    return []

def _save_memory(data):
    """Saves the memory list to the JSON file."""
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def remember_fact(app, fact, **kwargs):
    memory = _load_memory()
    memory.append(fact)
    _save_memory(memory)
    app.queue_log(f"Memory saved: '{fact}'")
    return f"Okay, I'll remember that {fact}."

def intelligent_recall(app, query, **kwargs):
    # This function now takes a specific query instead of the whole command.
    from ai_logic import get_ai_response
    memory = _load_memory()
    if not memory: return "I don't have any memories stored yet."
    memory_context = "\n".join([f"- {fact}" for fact in memory])
    prompt = (
        "Based ONLY on the facts in your memory, answer the user's question.\n"
        f"--- MEMORY ---\n{memory_context}\n"
        f"--- QUESTION ---\n{query}\n"
        "--- ANSWER ---"
    )
    return get_ai_response(app.answer_model, [], prompt, app.queue_log)

def forget_fact(app, item_number, **kwargs):
    item_index = int(item_number) - 1
    match = re.search(r'(\d+)', command)
    if not match:
        return "Please specify which memory number you want to forget. Say 'what do you remember' to see the numbered list."

    item_index = int(match.group(1)) - 1 # Convert to 0-based index
    memory = _load_memory()

    if 0 <= item_index < len(memory):
        forgotten_fact = memory.pop(item_index)
        _save_memory(memory)
        app.queue_log(f"Memory forgotten: '{forgotten_fact}'")
        return f"Okay, I have forgotten memory number {item_index + 1}."
    else:
        return "That's an invalid memory number."

def list_memories(app, command):
    """Lists all facts currently stored in memory as a numbered list."""
    memory = _load_memory()
    if not memory:
        return "I don't have any memories stored about you yet."

    response_parts = ["Here's what I remember:"]
    for i, fact in enumerate(memory):
        response_parts.append(f"Memory number {i+1}: {fact}.")
    
    return " ".join(response_parts)

def register():
    return {
        'remember_fact': {
            'handler': remember_fact,
            'regex': r'remember(?: that)? (.+)',
            'params': ['fact']
        },
        'intelligent_recall': {
            'handler': intelligent_recall,
            'regex': r'(?:do you remember|what do you know about) (.+)',
            'params': ['query']
        },
        'forget_fact': {
            'handler': forget_fact,
            'regex': r'forget memory(?: number)? (\d+)',
            'params': ['item_number']
        },
        'list_memories': {
            'handler': list_memories,
            'regex': r'what do you remember',
            'params': []
        },
    }