# ai_logic.py
import re
import json
import requests
from concurrent.futures import Future
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import time


# --- Embedding and RAG Components ---
EMBEDDING_MODEL = None
def load_embedding_model(log_callback):
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        try:
            log_callback("Loading embedding model 'all-MiniLM-L6-v2'...")
            EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            log_callback("Embedding model loaded successfully.")
        except Exception as e:
            log_callback(f"FATAL: Could not load embedding model. Error: {e}", "ERROR")

# --- AI Communication Helper Functions ---
def _extract_json_from_response(text):
    """Finds and parses the first valid JSON object embedded in a string."""
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        json_string = json_match.group(0)
        try: return json.loads(json_string)
        except json.JSONDecodeError: return None
    return None

def get_ollama_streaming_response(app, prompt, model_name):
    """A generic utility to get a streaming response from an Ollama model."""
    try:
        url = "http://localhost:11434/api/generate"
        payload = {"model": model_name, "prompt": prompt, "stream": True, "options": {"temperature": 0.6}}
        
        def generator():
            with requests.post(url, json=payload, stream=True, timeout=120) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        yield json.loads(line).get("response", "")
        return generator()

    except Exception as e:
        app.queue_log(f"Ollama Request Error: {e}", "ERROR")
        return iter([]) # Return an empty iterator on failure
    

def get_ollama_chat_response(app, messages, model_name, temperature=0.7, output_format=None):
    """
    A generic utility to get a response from an Ollama chat model.
    Supports forcing JSON output and adjusting temperature.
    """
    url = "http://localhost:11434/api/chat"
    
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False, 
        "options": {"temperature": temperature}
    }

    if output_format:
        payload["format"] = output_format

    try:
        with requests.post(url, json=payload, stream=False, timeout=120) as response:
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
            return content
    except Exception as e:
        app.queue_log(f"Ollama Request Error: {e}", "ERROR")
        return None



# --- Main AI Logic Entry Point ---
def get_tool_decision(app, history, user_prompt, model_name, available_tools):
    """
    Calls a specialized AI model (the Router) to decide which tool to use.
    It returns a structured JSON object with the decision.
    """
    log = app.queue_log
    
    # --- MODIFIED PROMPT ---
    system_prompt = f"""You are a highly specialized AI that routes a user's request to the correct tool. Your ONLY job is to respond with a JSON object. Do not add any other text.

Your JSON response MUST contain two keys: 'tool_name' and 'parameters'.

1.  Analyze the user's request to see if it matches any of the available tools.
2.  If it matches a tool, provide the tool's name in the 'tool_name' field and extract any necessary arguments into the 'parameters' field.
3.  If the request is general conversation (e.g., "hello", "thank you") or does not match any tool, you MUST set the 'tool_name' field to null.

# AVAILABLE TOOLS:
{json.dumps(available_tools, indent=2)}

# User's Request:
{user_prompt}

# RESPONSE (JSON only):
"""
    # --- END MODIFIED PROMPT ---

    messages = [
        {"role": "system", "content": system_prompt}
    ]
    # --- THIS LINE IS NOW ACTIVE ---
    messages.extend(history) 
    messages.append({"role": "user", "content": user_prompt})

    log(f"Asking Router AI ({model_name}) for a tool decision...")
    
    raw_decision_response = get_ollama_chat_response(app, messages, model_name, temperature=0.0, output_format="json")

    try:
        decision = json.loads(raw_decision_response)
        # --- ADDED VALIDATION ---
        if 'tool_name' not in decision or 'parameters' not in decision:
            log(f"Router AI response is missing required keys. Response: {decision}", "WARNING")
            return {"tool_name": None, "parameters": {}}
        # --- END VALIDATION ---
        log(f"Router AI decided: {decision}")
        return decision
    except (json.JSONDecodeError, TypeError):
        log(f"Could not decode JSON from Router AI. Raw response: '{raw_decision_response}'", "ERROR")

        return {"tool_name": None, "parameters": {}}


def get_conversational_response_stream(app, history, user_prompt, model_name, tool_output=None):
    """
    Generates a natural, streaming response using the Chat model.
    It now correctly includes conversation history for context.
    """
    log = app.queue_log
    
    # --- PROMPT CONSTRUCTION LOGIC ---
    if tool_output:
        # If a tool was used, the prompt is about synthesizing the result
        system_prompt = "You are AURA, a helpful AI assistant. A tool has provided information. Use it to directly and concisely answer the user's original question. Do not mention the tool."
        final_user_prompt = f"Information: '{tool_output}'\n\nOriginal Question: '{user_prompt}'"
        log(f"Asking Chat AI ({model_name}) to synthesize tool output...")
    else:
        # If no tool was used, it's a direct conversational query
        system_prompt = "You are AURA, a helpful and friendly AI assistant. Please provide a direct, conversational response to the user."
        final_user_prompt = user_prompt
        log(f"Asking Chat AI ({model_name}) for a conversational response...")

    # --- NEW HISTORY FORMATTING ---
    # Build the prompt string, including the full conversation history
    full_prompt_for_streaming = f"{system_prompt}\n\n"
    for message in history:
        if message['role'] == 'user':
            full_prompt_for_streaming += f"USER: {message['content']}\n"
        elif message['role'] == 'model':
            full_prompt_for_streaming += f"ASSISTANT: {message['content']}\n"
    
    # Add the latest user prompt
    full_prompt_for_streaming += f"USER: {final_user_prompt}\nASSISTANT:"
    # --- END NEW HISTORY FORMATTING ---

    return get_ollama_streaming_response(app, full_prompt_for_streaming, model_name)

def answer_question_on_summary(app_controller, summary, question):
    """Uses the selected AI to answer a question based on a provided summary."""
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    messages = [
        {"role": "system", "content": "Based ONLY on the provided meeting notes below, answer the user's question. Do not use any outside knowledge. If the answer is not in the notes, say so."},
        {"role": "user", "content": f"--- MEETING NOTES ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"}
    ]

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        log_callback(f"Answering question on summary with Ollama model: {model_name}")
        return get_ollama_chat_response(app_controller, messages, model_name)
    else: # Default to Gemini Online
        log_callback("Answering question on summary with Gemini.")
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Cannot answer question: Gemini model is not initialized."
        try:
            prompt = f"Based ONLY on the provided meeting notes below, answer the user's question. Do not use any outside knowledge. If the answer is not in the notes, say so.\n\n--- MEETING NOTES ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"
            response = answer_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            log_callback(f"Gemini Q&A Error: {e}", "ERROR")
            return f"[Error getting answer from Gemini: {e}]"

def generate_session_title(app_controller, text_to_title):
    """Uses the selected AI to create a short, descriptive title for a session."""
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    messages = [
        {"role": "system", "content": "Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else."},
        {"role": "user", "content": f"--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"}
    ]

    log_callback("Generating session title...")

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        title = get_ollama_chat_response(app_controller, messages, model_name)
        return title.strip().strip('"')
    else: # Default to Gemini Online
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Untitled Session"
        try:
            prompt = f"Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else.\n\n--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"
            response = answer_model.generate_content(prompt)
            return response.text.strip().strip('"')
        except Exception as e:
            log_callback(f"Gemini Title Generation Error: {e}", "ERROR")
            return "Untitled Session"