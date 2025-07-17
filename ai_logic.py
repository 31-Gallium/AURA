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
    url = "http://localhost:11434/api/generate"
    payload = {"model": model_name, "prompt": prompt, "stream": True, "options": {"temperature": 0.6}}
    try:
        with requests.post(url, json=payload, stream=True, timeout=120) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line: yield json.loads(line).get("response", "")
    except Exception as e:
        app.queue_log(f"Ollama Request Error: {e}", "ERROR")
        yield "[Error: Could not connect to Ollama. Please ensure it's running.]"

# --- Main AI Logic Entry Point ---
def get_ai_response(app, history, user_prompt):
    """
    Handles complex/conversational queries by using the main LLM to either
    call a power tool (like web search) or generate a direct response.
    """
    full_text_future = Future()

    def stream_generator():
        log = app.queue_log
        
        # Define the curated list of "power tools" for the AI to use
        power_tools = [
            {
                "name": "web_search",
                "description": "Use for questions about news, current events, facts, or any topic that requires up-to-date information from the internet.",
                "parameters": {"query": "The topic to search the web for."}
            },
            {
                "name": "calculate",
                "description": "Use ONLY for questions that require mathematical calculations, data analysis, or specific scientific computation.",
                "parameters": {"query": "The computational or data-based question."}
            },
            {
                "name": "create_document",
                "description": "Creates a new Word, PowerPoint, or Excel file on a topic.",
                "parameters": {"doc_type": "word, powerpoint, or excel", "topic": "The topic for the document."}
            }
        ]
        
        # This is a two-step prompt for the main AI. First, it decides on a tool.
        decision_prompt = f"""You are a helpful AI assistant with access to tools. Analyze the user's request and decide if a tool is needed.
Respond with a JSON object. If a tool is needed, use the format: {{"tool_name": "tool_name", "parameters": {{"param_name": "value"}}}}.
If no tool is needed, respond with: {{"tool_name": null}}.

# AVAILABLE TOOLS:
{json.dumps(power_tools, indent=2)}

# USER REQUEST: "{user_prompt}"

# JSON DECISION:
"""
        creator_model = app.config.get("ollama_model", "llama3.1")
        log(f"Asking main AI ({creator_model}) for a tool decision...")
        raw_decision_response = "".join(list(get_ollama_streaming_response(app, decision_prompt, creator_model)))
        decision = _extract_json_from_response(raw_decision_response)

        tool_name = decision.get("tool_name") if decision else None

        if tool_name:
            # AI chose to use a tool
            log(f"AI chose to use tool: {tool_name}")
            parameters = decision.get("parameters", {})
            
            # Find the correct handler for the chosen tool
            # NOTE: This requires your skill files to have a consistent naming scheme
            tool_handler = None
            if tool_name == "web_search":
                from skills.web_skill import perform_web_search
                tool_handler = perform_web_search
            elif tool_name == "calculate":
                from skills.wolfram_skill import ask_wolfram
                tool_handler = ask_wolfram
            elif tool_name == "create_document":
                from skills.document_skill import create_document
                tool_handler = create_document
            
            if tool_handler:
                tool_result = tool_handler(app, **parameters)
                final_prompt = f"Based on this information: \"{tool_result}\", formulate a direct and concise response to the user's original request: \"{user_prompt}\""
                
                full_response_text = ""
                for chunk in get_ollama_streaming_response(app, final_prompt, creator_model):
                    full_response_text += chunk
                    yield chunk
                full_text_future.set_result(full_response_text)
            else:
                yield "I identified a tool to use, but couldn't find the right function to execute it."

        else:
            # No tool was chosen, so have a normal conversation
            log("No tool chosen. Proceeding with conversational response.")
            history_str = "\n".join([f"{msg['role'].upper()}: {msg['parts'][0]}" for msg in history[-6:]])
            conversation_prompt = f"You are AURA, a helpful AI assistant. Continue the conversation.\n\n{history_str}\nUSER: {user_prompt}\nASSISTANT:"
            
            full_response_text = ""
            for chunk in get_ollama_streaming_response(app, conversation_prompt, creator_model):
                full_response_text += chunk
                yield chunk
            full_text_future.set_result(full_response_text)
            
    return stream_generator(), full_text_future

def get_streaming_summary(app_controller, session_id, new_text_batch):
    """Generates a live, evolving summary using the RAG pipeline."""
    config = app_controller.config
    log_callback = app_controller.queue_log
    session = app_controller.meeting_sessions.get(session_id)
    if not session: return

    ai_engine = config.get("ai_engine", "gemini_online")

    log_callback("RAG: Searching for relevant chunks...")
    relevant_context = search_relevant_chunks(session, new_text_batch)
    relevant_context_str = "\n".join(relevant_context)
    
    previous_summary = session.get('summary', '')

    prompt = (
        "You are a note-taking assistant. Your task is to update a set of meeting notes based on new information. "
        "Strictly follow these rules:\n"
        "1. Integrate the 'NEW INFORMATION' into the 'CURRENT NOTES'.\n"
        "2. For all titles or headings, you MUST enclose them in the **##Title##** format.\n"
        "3. For all main points, you MUST start the line with a `* ` (asterisk and a space).\n"
        "4. For all sub-points, you MUST start the line with a `+ ` (plus sign and a space).\n"
        "5. Do NOT add any conversational text, introductions, or conclusions. Only output the final notes.\n\n"
        f"--- CURRENT NOTES ---\n{previous_summary}\n\n"
        f"--- RELEVANT CONTEXT FROM TRANSCRIPT ---\n{relevant_context_str}\n\n"
        f"--- NEW INFORMATION ---\n{new_text_batch}\n\n"
        "--- FINAL NOTES ---"
    )

    log_callback(f"RAG: Sending final, structured prompt.")

    yield "[CLEAR_SUMMARY]"
    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        yield from get_ollama_streaming_response(model_name, prompt, log_callback)
    else: # Gemini Online
        answer_model = app_controller.answer_model
        if not answer_model:
            yield "[Error: Gemini model is not initialized. Check API key.]"
            return
        try:
            generation_config = genai.types.GenerationConfig(temperature=0.2) # Slightly higher for creativity in summarizing
            response_stream = answer_model.generate_content(prompt, stream=True, generation_config=generation_config)
            for summary_chunk in response_stream:
                if summary_chunk.text:
                    yield summary_chunk.text
        except Exception as e:
            log_callback(f"Gemini RAG Error: {e}", "ERROR")
            yield f"[Error in Gemini summary: {e}]"

def answer_question_on_summary(app_controller, summary, question):
    """Uses the selected AI to answer a question based on a provided summary."""
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    prompt = f"Based ONLY on the provided meeting notes below, answer the user's question. Do not use any outside knowledge. If the answer is not in the notes, say so.\n\n--- MEETING NOTES ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        log_callback(f"Answering question on summary with Ollama model: {model_name}")
        return get_ollama_raw_response(app_controller, prompt)
    else: # Default to Gemini Online
        log_callback("Answering question on summary with Gemini.")
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Cannot answer question: Gemini model is not initialized."
        try:
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

    prompt = f"Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else.\n\n--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"

    log_callback("Generating session title...")

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        title = get_ollama_raw_response(app_controller, prompt)
        return title.strip().strip('"')
    else: # Default to Gemini Online
        answer_model = app_controller.answer_model
        if not answer_model:
            return "Untitled Session"
        try:
            response = answer_model.generate_content(prompt)
            return response.text.strip().strip('"')
        except Exception as e:
            log_callback(f"Gemini Title Generation Error: {e}", "ERROR")
            return "Untitled Session"