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
        
        # --- FIX: We need to wrap the generator logic to handle the return ---
        def generator():
            with requests.post(url, json=payload, stream=True, timeout=120) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if line:
                        yield json.loads(line).get("response", "")
        return generator()

    except Exception as e:
        app.queue_log(f"Ollama Request Error: {e}", "ERROR")
        # --- FIX: Return None on failure ---
        return None
    
    
def get_ollama_chat_response(app, messages, model_name, temperature=0.7, output_format=None):
    """
    A generic utility to get a response from an Ollama chat model.
    Supports forcing JSON output and adjusting temperature.
    """
    url = "http://localhost:11434/api/chat"
    
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False, # Streaming is disabled for more straightforward logic
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
        # --- FIX: Return None on failure ---
        return None



# --- Main AI Logic Entry Point ---
def get_ai_response(app, history, user_prompt):
    """
    Handles complex/conversational queries using a two-step process:
    1. Tool-Calling: Tries to use a tool for specific queries.
    2. Conversational: If no tool is needed, generates a direct response.
    """
    full_text_future = Future()

    def stream_generator():
        log = app.queue_log
        
        # --- DYNAMIC TOOL LOADING ---
        # Fetch the list of all available tools from the command handler
        available_tools = app.command_handler.get_tools_for_ai()
        
        # --- Step 1: Tool-Calling Attempt ---
        tool_prompt_messages = [
            {"role": "system", "content": f"""You are a helpful AI assistant with access to tools. Analyze the user's request and decide if a tool is needed.
Respond with a JSON object. If a tool is needed, use the format: {{"tool_name": "tool_name", "parameters": {{"param_name": "value"}}}}.
If no tool is needed, respond with: {{"tool_name": null}}.

# AVAILABLE TOOLS:
{json.dumps(available_tools, indent=2)}"""},
            {"role": "user", "content": user_prompt}
        ]

        creator_model = app.config.get("ollama_model", "llama3.1")
        log(f"Asking main AI ({creator_model}) for a tool decision...")
        
        raw_decision_response = get_ollama_chat_response(app, tool_prompt_messages, creator_model, temperature=0.2, output_format="json")
        
        try:
            decision = json.loads(raw_decision_response)
        except (json.JSONDecodeError, TypeError):
            decision = {}

        tool_name = decision.get("tool_name")

        if tool_name:
            log(f"AI chose to use tool: {tool_name}")
            parameters = decision.get("parameters", {})
            
            # --- DYNAMIC TOOL DISPATCH ---
            # Find the chosen tool in the command map to get its handler function
            tool_data = app.command_handler.command_map.get(tool_name)
            
            if tool_data and 'handler' in tool_data:
                tool_handler = tool_data['handler']
                tool_result = tool_handler(app, **parameters)
                
                # --- NEW, MORE ROBUST ERROR HANDLING ---
                # Check if the result is a dictionary with an 'error' key
                if isinstance(tool_result, dict) and 'error' in tool_result:
                    error_message = tool_result['error']
                    log(f"Tool '{tool_name}' returned an error: {error_message}", "WARNING")
                    full_text_future.set_result(error_message)
                    yield error_message
                    return # Stop further processing

                # If we get here, the tool was successful and returned a string.
                final_prompt_messages = [
                    {"role": "system", "content": "You are AURA, a helpful AI assistant. A tool has provided the following information. Use it to directly and concisely answer the user's original question. Do not mention that you used a tool or that you searched for information."},
                    {"role": "user", "content": f"Information: '{tool_result}'\n\nOriginal Question: '{user_prompt}'"}
                ]

                full_response_text = get_ollama_chat_response(app, final_prompt_messages, creator_model, temperature=0.7)
                full_text_future.set_result(full_response_text)
                yield full_response_text
            else:
                log(f"Could not find a handler for the chosen tool: {tool_name}", "ERROR")
                yield f"I identified a tool to use ({tool_name}), but couldn't find the function to execute it."

        else:
            # --- Step 2: No tool was chosen, proceed with a conversational response ---
            # ... (this part of the function remains exactly the same) ...
            log("No tool chosen. Proceeding with conversational response.")
            
            conversation_messages = history + [{"role": "user", "content": user_prompt}]

            full_response_text = get_ollama_chat_response(app, conversation_messages, creator_model, temperature=0.8)
            full_text_future.set_result(full_response_text)
            yield full_response_text

            
    return stream_generator(), full_text_future

def answer_question_on_summary(app_controller, summary, question):
    """Uses the selected AI to answer a question based on a provided summary."""
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    # --- FIX: Create messages in the correct format ---
    messages = [
        {"role": "system", "content": "Based ONLY on the provided meeting notes below, answer the user's question. Do not use any outside knowledge. If the answer is not in the notes, say so."},
        {"role": "user", "content": f"--- MEETING NOTES ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"}
    ]

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        log_callback(f"Answering question on summary with Ollama model: {model_name}")
        # --- FIX: Call the correct function ---
        return get_ollama_chat_response(app_controller, messages, model_name)
    else: # Default to Gemini Online
        log_callback("Answering question on summary with Gemini.")
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Cannot answer question: Gemini model is not initialized."
        try:
            # Gemini's API uses a different format, so we keep the old prompt style here
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

    # --- FIX: Create messages in the correct format ---
    messages = [
        {"role": "system", "content": "Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else."},
        {"role": "user", "content": f"--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"}
    ]

    log_callback("Generating session title...")

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        # --- FIX: Call the correct function ---
        title = get_ollama_chat_response(app_controller, messages, model_name)
        return title.strip().strip('"')
    else: # Default to Gemini Online
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Untitled Session"
        try:
            # Gemini's API uses a different format, so we keep the old prompt style here
            prompt = f"Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else.\n\n--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"
            response = answer_model.generate_content(prompt)
            return response.text.strip().strip('"')
        except Exception as e:
            log_callback(f"Gemini Title Generation Error: {e}", "ERROR")
            return "Untitled Session"