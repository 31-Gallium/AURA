# skills/memory_skill.py
import os
import json
import re

# This import is now needed to call the main AI from within the skill
from ai_logic import get_ai_response

MEMORY_FILE = "memory.json"

def _load_memory():
    """Loads the memory list from the JSON file."""
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def _save_memory(data):
    """Saves the memory list to the JSON file."""
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def remember_fact(app, fact, **kwargs):
    """Stores a piece of information that the user provides."""
    memory = _load_memory()
    memory.append(fact.strip())
    _save_memory(memory)
    app.queue_log(f"Memory saved: '{fact}'")
    return f"Okay, I'll remember that: {fact}."

def intelligent_recall(app, query, **kwargs):
    """Uses the main AI to answer a question based on stored memories."""
    memory = _load_memory()
    if not memory:
        return "I don't have any memories stored yet."
    
    memory_context = "\n".join([f"- {fact}" for fact in memory])
    
    # This prompt asks the main AI to act as a memory expert
    prompt = (
        "You are an expert at recalling information from a specific list of facts. "
        "Based ONLY on the facts in the 'MEMORY' section below, answer the user's question. "
        "If the answer isn't in the memory, say that you don't have that information stored.\n\n"
        f"--- MEMORY ---\n{memory_context}\n\n"
        f"--- QUESTION ---\n{query}\n\n"
        "--- ANSWER ---"
    )
    
    # Use the main AI logic to get a response, but don't stream it for a direct return
    response_stream, _ = get_ai_response(app, [], prompt)
    full_response = "".join(list(response_stream))
    return full_response

def forget_fact(app, item_number, **kwargs):
    """Deletes a specific memory by its number from the list."""
    try:
        # The item_number is now passed directly as a parameter
        item_index = int(item_number) - 1
    except (ValueError, TypeError):
        return "Please specify a valid memory number to forget."

    memory = _load_memory()
    if not 0 <= item_index < len(memory):
        return "That's an invalid memory number. Say 'what do you remember' to see the list."

    forgotten_fact = memory.pop(item_index)
    _save_memory(memory)
    app.queue_log(f"Memory forgotten: '{forgotten_fact}'")
    return f"Okay, I have forgotten memory number {item_index + 1}."

def list_memories(app, **kwargs):
    """Lists all facts currently stored in memory as a numbered list."""
    memory = _load_memory()
    if not memory:
        return "I don't have any memories stored yet."

    response_parts = ["Here's what I remember:"]
    for i, fact in enumerate(memory):
        response_parts.append(f"Memory {i+1}: {fact}")
    
    # Use newlines for better formatting in the chat window
    return "\n".join(response_parts)

def register():
    """Registers all memory-related commands."""
    return {
        'remember_fact': {
            'handler': remember_fact,
            'regex': r'\bremember(?: that)? (.+)',
            'params': ['fact'],
            'description': "Stores a piece of information provided by the user for later recall."
        },
        'intelligent_recall': {
            'handler': intelligent_recall,
            'regex': r'\b(?:do you remember|what do you know about)\b (.+)',
            'params': ['query'],
            'description': "Answers a question based on previously stored memories."
        },
        'forget_fact': {
            'handler': forget_fact,
            'regex': r'\bforget memory(?: number)? (\d+)\b',
            'params': ['item_number'],
            'description': "Deletes a specific memory by its number."
        },
        'list_memories': {
            'handler': list_memories,
            'regex': r'\bwhat do you remember\b',
            'params': [],
            'description': "Lists all facts currently stored in memory."
        },
    }