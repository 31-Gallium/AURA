import google.generativeai as genai
import traceback
from datetime import datetime
from PIL import Image
import requests 
import json     
import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

from skills import web_skill

# --- Global variable to hold the embedding model ---
EMBEDDING_MODEL = None

def load_embedding_model(log_callback):
    """Loads the sentence-transformer model into memory."""
    global EMBEDDING_MODEL
    if EMBEDDING_MODEL is None:
        try:
            log_callback("Loading embedding model 'all-MiniLM-L6-v2'...")
            EMBEDDING_MODEL = SentenceTransformer('all-MiniLM-L6-v2')
            log_callback("Embedding model loaded successfully.")
        except Exception as e:
            log_callback(f"FATAL: Could not load embedding model: {e}")

def search_relevant_chunks(session, query_text, top_k=5): # Increased to 5 for more context
    """Searches the session's FAISS index for relevant text chunks."""
    if EMBEDDING_MODEL is None or session['faiss_index'].ntotal == 0:
        return []

    query_vector = EMBEDDING_MODEL.encode([query_text])
    
    distances, indices = session['faiss_index'].search(query_vector.astype(np.float32), top_k)
    
    relevant_chunks = [session['transcript_chunks'][i] for i in indices[0]]
    return relevant_chunks


def get_ollama_response_with_tools(app, history, user_prompt):
    """
    Generates a response from Ollama, giving it the option to use tools like web search.
    """
    log_callback = app.queue_log

    # 1. First, ask the AI to decide if a tool is needed.
    # We describe the available tools to the AI.
    tool_decision_prompt = (
        "You are a helpful assistant with access to tools. Based on the user's query, "
        "should you use a tool? Your primary tool is 'perform_web_search' for any questions about "
        "current events, recent information, or facts you don't know.\n\n"
        "If a tool is needed, respond with a JSON object like: "
        '{"tool_name": "perform_web_search", "parameters": {"query": "user\'s search query"}}\n'
        "If no tool is needed for a simple conversational response, respond with: "
        '{"tool_name": null}\n\n'
        f'USER QUERY: "{user_prompt}"\n\n'
        'JSON RESPONSE:'
    )

    # Get the AI's decision
    tool_decision_str = get_ollama_raw_response(app, tool_decision_prompt)
    
    try:
        decision_data = json.loads(tool_decision_str)
        tool_name = decision_data.get("tool_name")
        parameters = decision_data.get("parameters")
    except (json.JSONDecodeError, AttributeError):
        # If the AI fails to produce valid JSON, assume no tool is needed.
        tool_name = None
        parameters = None

    # 2. If the AI decided to use a tool, execute it.
    if tool_name == "perform_web_search" and parameters:
        query = parameters.get("query")
        log_callback(f"Ollama decided to use web search for query: '{query}'")
        app.speak_response(f"Okay, I'm looking that up for you.")
        
        # Call the actual Python function for the web search
        search_results = web_skill.perform_web_search(app, query)
        
        log_callback("Giving search results back to Ollama for final answer.")
        
        # 3. Second, give the results back to the AI to generate a final answer.
        final_answer_prompt = (
            "You are a helpful assistant. Based on the following web search results, "
            f"please provide a concise and direct answer to the user's original question.\n\n"
            f"--- WEB SEARCH RESULTS ---\n{search_results}\n\n"
            f"--- ORIGINAL QUESTION ---\n'{user_prompt}'\n\n"
            "--- FINAL ANSWER ---"
        )
        
        # This call gets the final, synthesized response.
        return get_ollama_raw_response(app, final_answer_prompt)

    # If no tool was needed, just get a normal chat response.
    else:
        log_callback("Ollama decided no tool was needed. Generating a direct response.")
        return get_ollama_chat_response(app, history, user_prompt)

def get_ollama_streaming_response(model_name, prompt, log_callback):
    """Connects to a local Ollama server to get a streaming response."""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True
    }
    try:
        with requests.post(url, json=payload, stream=True) as response:
            response.raise_for_status() 
            for line in response.iter_lines():
                if line:
                    try:
                        json_line = json.loads(line)
                        yield json_line.get("response", "")
                    except json.JSONDecodeError:
                        log_callback(f"Ollama stream: Could not decode JSON line: {line}")
    except requests.exceptions.ConnectionError:
        log_callback("Ollama connection error: Could not connect to Ollama server. Is it running?")
        yield "\n[Error: Could not connect to the local Ollama server. Please ensure it is running.]"
    except Exception as e:
        log_callback(f"Ollama Error: {e}")
        yield f"\n[Error: {e}]"

def perform_web_search(query, config, log_callback):
    log_callback(f"Web search would be performed for: {query}")
    return "No web results found (function not implemented)."

def setup_gemini(api_key, log_callback):
    """Initializes the Gemini models."""
    if not api_key or "YOUR" in api_key:
        log_callback("Gemini API key is missing or is a placeholder.")
        return None, None
    try:
        genai.configure(api_key=api_key)
        triage_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        answer_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        log_callback("Gemini models initialized successfully.")
        return triage_model, answer_model
    except Exception as e:
        log_callback(f"FATAL: Gemini setup failed: {e}\n{traceback.format_exc()}")
        return None, None

def classify_query(triage_model, question, log_callback):
    """Uses a fast AI call to classify the user's query."""
    log_callback(f"Classifying query: '{question}'")
    prompt = (
        "Classify the user's query into one of three categories: 'visual', 'web_search', or 'conversational'.\n"
        "- 'visual': The user is asking to analyze, read, or describe their screen.\n"
        "- 'web_search': The query requires real-time internet information.\n"
        "- 'conversational': The query is a simple greeting, creative request, or a command to the assistant itself.\n\n"
        "--- EXAMPLES ---\n"
        "User Query: \"what do you see on my screen?\"\nCategory: visual\n"
        "User Query: \"who is the president?\"\nCategory: web_search\n"
        "User Query: \"list all open windows\"\nCategory: conversational\n"
        "--- END EXAMPLES ---\n\n"
        f"User Query: \"{question}\"\n\n"
        "Category:"
    )
    try:
        response = triage_model.generate_content(prompt)
        classification = response.text.strip().lower()
        log_callback(f"Query classified as: '{classification}'")
        if "visual" in classification: return "visual"
        if "web_search" in classification: return "web_search"
        return "conversational"
    except Exception as e:
        log_callback(f"Error during query classification: {e}")
        return "conversational"

def get_ai_response(answer_model, history, final_prompt, log_callback):
    """A generic function to get a response from the main Gemini model."""
    try:
        if len(history) > 6: history = history[-6:]
        chat = answer_model.start_chat(history=history)
        response = chat.send_message(final_prompt)
        return response.text.strip() or "I'm sorry, I couldn't come up with a response."
    except Exception as e:
        log_callback(f"AI Error: {e}\n{traceback.format_exc()}")
        return f"Sorry, I encountered an error: {str(e)}"

def get_ollama_chat_response(app_controller, history, user_prompt):
    """
    Generates a complete chat response from the local Ollama model.
    """
    log_callback = app_controller.queue_log
    config = app_controller.config
    model_name = config.get("ollama_model", "llama3")
    
    # Simple history formatting for chat. More complex formatting can be done here.
    formatted_history = "\n".join([f"{msg['role']}: {msg['parts'][0]}" for msg in history])
    
    prompt = (
        "You are a helpful assistant. Based on the conversation history, "
        f"answer the user's latest query.\n\n--- HISTORY ---\n{formatted_history}\n\n"
        f"--- USER QUERY ---\n{user_prompt}\n\n--- ASSISTANT RESPONSE ---"
    )

    log_callback(f"Sending prompt to Ollama model: {model_name}")
    
    full_response = ""
    try:
        response_stream = get_ollama_streaming_response(model_name, prompt, log_callback)
        for chunk in response_stream:
            full_response += chunk
        return full_response.strip() or "I'm sorry, I couldn't process that."
    except Exception as e:
        log_callback(f"Ollama chat response error: {e}")
        return f"Sorry, I encountered an error with the Ollama model: {e}"
    

def get_ollama_raw_response(app_controller, prompt):
    """Gets a raw, non-chat response from the local Ollama model."""
    log_callback = app_controller.queue_log
    config = app_controller.config
    model_name = config.get("ollama_model", "llama3")
    
    full_response = ""
    try:
        # We can reuse the streaming function and just collect the response
        response_stream = get_ollama_streaming_response(model_name, prompt, log_callback)
        for chunk in response_stream:
            full_response += chunk
        return full_response.strip()
    except Exception as e:
        log_callback(f"Ollama raw response error: {e}")
        return "" # Return empty string on error


def get_streaming_summary(app_controller, session_id, new_text_batch):
    """
    Generates a live, evolving summary using the RAG pipeline.
    """
    config = app_controller.config
    log_callback = app_controller.queue_log
    session = app_controller.meeting_sessions.get(session_id)
    if not session: return

    ai_engine = config.get("ai_engine", "gemini_online")

    log_callback("RAG: Searching for relevant chunks...")
    relevant_context = search_relevant_chunks(session, new_text_batch)
    relevant_context_str = "\n".join(relevant_context)
    
    previous_summary = session.get('summary', '')

    # --- FINAL, ULTRA-SPECIFIC PROMPT ---
    prompt = (
        "You are a note-taking assistant. Your task is to update a set of meeting notes based on new information. "
        "Strictly follow these rules:\n"
        "1. Integrate the 'NEW INFORMATION' into the 'CURRENT NOTES'.\n"
        "2. For all titles or headings, you MUST enclose them in the **##Title##** format.\n"
        "3. For all main points, you MUST start the line with a `* ` (asterisk and a space).\n"
        "4. For all sub-points, you MUST start the line with a `+ ` (plus sign and a space).\n"
        "5. Do NOT add any conversational text, introductions, or conclusions. Only output the final notes.\n\n"
        "--- EXAMPLE OUTPUT FORMAT ---\n"
        "**##Key Topic A##**\n"
        "* Main point about Topic A.\n"
        "+ Sub-point with a further detail.\n"
        "**##Key Topic B##**\n"
        "* Main point about Topic B.\n"
        "-----------------------------------\n\n"
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
        try:
            generation_config = genai.types.GenerationConfig(temperature=0.1) # Lower temperature for more deterministic output
            response_stream = answer_model.generate_content(prompt, stream=True, generation_config=generation_config)
            for summary_chunk in response_stream:
                if summary_chunk.text:
                    yield summary_chunk.text
        except Exception as e:
            log_callback(f"Gemini RAG Error: {e}")
            yield f"[Error in Gemini summary: {e}]"

# --- NEW: Function for handling Q&A on a summary ---
def answer_question_on_summary(app_controller, summary, question):
    """
    Uses the selected AI to answer a question based on a provided summary.
    """
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    prompt = f"Based ONLY on the provided meeting notes below, answer the user's question. Do not use any outside knowledge. If the answer is not in the notes, say so.\n\n--- MEETING NOTES ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        log_callback(f"Answering question on summary with Ollama model: {model_name}")
        
        full_response = ""
        response_stream = get_ollama_streaming_response(model_name, prompt, log_callback)
        for chunk in response_stream:
            full_response += chunk
        return full_response.strip()

    else: # Default to Gemini Online
        log_callback("Answering question on summary with Gemini.")
        answer_model = app_controller.answer_model
        try:
            response = answer_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            log_callback(f"Gemini Q&A Error: {e}")
            return f"[Error getting answer from Gemini: {e}]"


def analyze_image(answer_model, history, image, question, log_callback):
    """Sends both an image and a text question to the Gemini model for analysis."""
    log_callback("Sending image and prompt to Gemini for visual analysis...")
    try:
        prompt = [question, image]
        response = answer_model.generate_content(prompt)
        ai_response = response.text.strip()
        history.append({"role": "user", "parts": [question]})
        history.append({"role": "model", "parts": [ai_response]})
        return ai_response or "I looked at the image, but I'm not sure how to respond."
    except Exception as e:
        log_callback(f"AI Vision Error: {e}\n{traceback.format_exc()}")
        return f"Sorry, I ran into an error trying to analyze the image."
    
def run_ai_with_tools(app, user_prompt):
    import traceback
    from skills.web_skill import perform_web_search

    log_callback = app.queue_log
    model = app.answer_model

    tools = [{
        "function_declarations": [{
            "name": "perform_web_search",
            "description": "Searches the web for up-to-date information on a given topic.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query"
                    }
                },
                "required": ["query"]
            }
        }]
    }]

    tool_functions = {
        "perform_web_search": lambda query: perform_web_search(app, query)
    }

    log_callback("Starting AI task with manual function calling loop.")

    try:
        history = [{
            "role": "user",
            "parts": [{
                "text": (
                    "SYSTEM: You are AURA, a tool-using AI assistant. You have access to tools like "
                    "`perform_web_search`. You can use them to gather real-time data before answering.\n\n"
                    + user_prompt
                )
            }]
        }]

        while True:
            response = model.generate_content(history, tools=tools)
            candidate = response.candidates[0]
            parts = candidate.content.parts

            if not parts:
                log_callback("AI returned no content parts.")
                break

            log_callback(f"Raw function_call part: {parts[0]}")

            function_call = getattr(parts[0], 'function_call', None)
            function_name = getattr(function_call, 'name', None)

            if function_call and function_name in tool_functions:
                args = {key: value for key, value in function_call.args.items()}
                log_callback(f"AI requested tool call: {function_name}({args})")

                function_to_call = tool_functions[function_name]
                tool_response_content = function_to_call(**args)

                history.append({
                    "role": "model",
                    "parts": [{"function_call": {"name": function_name, "args": args}}]
                })

                history.append({
                    "role": "function",
                    "parts": [{"function_response": {"name": function_name, "response": {"content": tool_response_content}}}]
                })

            elif function_call and function_name:
                log_callback(f"AI called unknown function: {function_name}")
                break
            else:
                if parts and hasattr(parts[0], 'text'):
                    return parts[0].text.strip()
                log_callback("AI returned a malformed or blank function_call.")
                break

    except Exception as e:
        log_callback(f"Error during AI task with tools: {e}\n{traceback.format_exc()}")
        return "I'm sorry, I encountered a complex error while processing that request."
    
def answer_question_on_summary(app_controller, summary, question):
    """
    Uses the selected AI to answer a question based on a provided summary.
    """
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    prompt = f"Based ONLY on the provided meeting summary below, answer the user's question. Do not use any outside knowledge. If the answer is not in the summary, say so.\n\n--- MEETING SUMMARY ---\n{summary}\n\n--- USER QUESTION ---\n{question}\n\n--- ANSWER ---"

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        log_callback(f"Answering question on summary with Ollama model: {model_name}")
        
        # Ollama's stream gives one word at a time, so we collect it
        full_response = ""
        response_stream = get_ollama_streaming_response(model_name, prompt, log_callback)
        for chunk in response_stream:
            full_response += chunk
        return full_response.strip()

    else: # Default to Gemini Online
        log_callback("Answering question on summary with Gemini.")
        answer_model = app_controller.answer_model
        try:
            response = answer_model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            log_callback(f"Gemini Q&A Error: {e}")
            return f"[Error getting answer from Gemini: {e}]"
        
def generate_session_title(app_controller, text_to_title):
    """
    Uses the selected AI to create a short, descriptive title for a session.
    """
    config = app_controller.config
    log_callback = app_controller.queue_log
    ai_engine = config.get("ai_engine", "gemini_online")

    prompt = f"Analyze the following text from a meeting. Create a short, descriptive title (3-5 words) that accurately describes the main topic. Respond with ONLY the title itself, and nothing else.\n\n--- TEXT ---\n{text_to_title}\n\n--- TITLE ---"

    log_callback(f"Generating session title...")

    if ai_engine == "ollama_offline":
        model_name = config.get("ollama_model", "llama3")
        # For a short, one-shot task, we don't need to stream.
        full_response = ""
        # We can reuse the streaming function and just collect the response.
        response_stream = get_ollama_streaming_response(model_name, prompt, log_callback)
        for chunk in response_stream:
            full_response += chunk
        return full_response.strip().strip('"') # Remove quotes if AI adds them

    else: # Default to Gemini Online
        answer_model = app_controller.answer_model
        try:
            response = answer_model.generate_content(prompt)
            return response.text.strip().strip('"')
        except Exception as e:
            log_callback(f"Gemini Title Generation Error: {e}")
            return "Untitled Session"