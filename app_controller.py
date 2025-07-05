# In app_controller.py

import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import json
import os
from datetime import datetime, timedelta
import time
import queue
import traceback
from multiprocessing import Process, Queue as mp_Queue
import pythoncom
import pyperclip
from pynput import keyboard 
import sounddevice as sd
from playsound import playsound
from apscheduler.schedulers.background import BackgroundScheduler
import uuid
import numpy as np
import faiss

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from gui import GUI
from tts import CoquiTTS
from stt import SpeechToText
from command_handler import CommandHandler
import ai_logic 
from skills import system_skill
from skills import web_skill as web

class AURAApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AURA")
        self.root.geometry("1280x720")
        self.root.minsize(1024, 600)

        self.next_utterance = None

        # State and config
        self.is_listening = False
        self.is_speaking = False
        self.last_spoken_text = None
        self.tts_process = None
        self.speak_lock = threading.Lock()
        
        self.meeting_sessions = {}
        self.active_meeting_session_id = None
        
        self.transcript_queue = queue.Queue()


        self.config = self.load_config()
        self.conversation_history = []
        self.log_queue = mp_Queue()

        self.fs_observer = None
        self.clipboard_thread = None
        self.clipboard_history = []
        self.last_clipboard_content = ""
        self.is_clipboard_manager_running = threading.Event()
        self._old_config = self.config.copy() 
        
        # Initialize Core Modules
        ai_logic.load_embedding_model(self.queue_log)
        self.gui = GUI(self)
        self.tts_engine = CoquiTTS(self.config, self.queue_log)
        self.stt_engine = SpeechToText(self, self.config, self.queue_log)
        self.command_handler = CommandHandler(self)
        self.triage_model, self.answer_model = ai_logic.setup_gemini(self.config.get("gemini_api_key"), self.queue_log)
        
        self.scheduler = BackgroundScheduler(daemon=True)
        self.scheduler.start()

        self.global_hotkey_listener = None

        self.hotkey_actions = {
            "Start Listening": lambda: self.root.after(0, self.start_listening),
            "Stop Speaking": lambda: self.root.after(0, self.stop_speaking),
            "Show Clipboard History": lambda: self.root.after(0, self.execute_command, "show clipboard history"),
            "Take a Screenshot": lambda: self.root.after(0, self.execute_command, "take a screenshot"),
        }


        self.routine_actions = {
            "Speak Text": {
                "function": lambda params: self.speak_response(params.get('text', 'No text specified.')),
                "params": {"text": "string"}
            },
            "Wait": {
                "function": lambda params: time.sleep(int(params.get('seconds', 1))),
                "params": {"seconds": "number"}
            },
            "Open App": {
                "function": lambda params: self.execute_command(f"open {params.get('alias', '')}"),
                "params": {"alias": "string"}
            },
            "Get Weather": {
                "function": lambda params: self.execute_command(f"weather in {params.get('city', 'your city')}"),
                "params": {"city": "string"}
            },
            "Set System Volume": {
                "function": lambda params: self.execute_command(f"set system volume to {params.get('level', 50)}"),
                "params": {"level": "number (0-100)"}
            },
            "Terminate Process": {
                "function": lambda params: self.execute_command(f"terminate {params.get('process_name', '')}"),
                "params": {"process_name": "e.g., notepad.exe"}
            },
            "Summarize Web Page": {
                "function": lambda params: self.execute_command(f"summarize page {params.get('url', '')}"),
                "params": {"url": "string"}
            },
            "Read News Headlines": {
                "function": lambda params: self.execute_command("news headlines"),
                "params": {} 
            },
            "Read Latest Emails": {
                "function": lambda params: self.execute_command("read my email"),
                "params": {}
            },
            "List Reminders": {
                "function": lambda params: self.execute_command("show my reminders"),
                "params": {}
            },
            "Take a Screenshot": {
                "function": lambda params: self.execute_command("take a screenshot"),
                "params": {}
            },
            "Empty Recycle Bin": {
                "function": lambda params: self.execute_command("empty recycle bin"),
                "params": {}
            },
            "Tell a Joke": {
                "function": lambda params: self.execute_command("tell me a joke"),
                "params": {}
            }
        }

        self.is_tts_reinitializing = False

        self.conversation_state = None 

        self.is_mic_testing = False
        self.input_devices = []
        self.loopback_devices = []
        self._get_audio_devices()

        self._load_and_reschedule_reminders()
        # --- NEW: Load sessions and populate GUI on startup ---
        self.root.after(700, self._load_sessions_on_startup)


        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self._process_log_queue()

        self.start_background_services()

    # --- NEW: Function to load sessions from file ---
    def _load_sessions_on_startup(self):
        try:
            if os.path.exists("sessions.json"):
                with open("sessions.json", "r", encoding="utf-8") as f:
                    saved_sessions = json.load(f)
                
                for session_data in saved_sessions:
                    # Reconstruct the session object. RAG components are not persisted.
                    session_id = session_data.get('id', str(uuid.uuid4()))
                    self.meeting_sessions[session_id] = {
                        "id": session_id,
                        "title": session_data.get('title', 'Saved Session'),
                        "transcript": session_data.get('transcript', ''),
                        "summary": session_data.get('summary', ''),
                        "status": "stopped", # All loaded sessions are stopped
                        # Non-serializable parts are omitted
                    }
                self.queue_log(f"Loaded {len(self.meeting_sessions)} saved meeting sessions.")

                # Populate the GUI list after loading
                for session_id, session in self.meeting_sessions.items():
                    self.gui.add_meeting_session_to_list(session_id, session['title'])
                    self.gui.update_session_list_status(session_id, "Stopped")
                self.root.after(1000, lambda: self.gui.show_view("meeting"))


        except Exception as e:
            self.queue_log(f"Error loading sessions: {e}")


    # --- NEW: Function to save sessions to file ---
    def _save_sessions_on_exit(self):
        sessions_to_save = []
        for session in self.meeting_sessions.values():
            # Create a clean dictionary with only the data we want to save
            serializable_session = {
                "id": session.get('id'),
                "title": session.get('title'),
                "transcript": session.get('transcript'),
                "summary": session.get('summary')
            }
            sessions_to_save.append(serializable_session)
        
        try:
            with open("sessions.json", "w", encoding="utf-8") as f:
                json.dump(sessions_to_save, f, indent=4)
            self.queue_log("Meeting sessions saved successfully.")
        except Exception as e:
            self.queue_log(f"Error saving sessions: {e}")


    def start_new_meeting_session(self):
        """Creates a new meeting session and starts transcription."""
        for session in self.meeting_sessions.values():
            if session['status'] == 'active':
                messagebox.showwarning("Meeting in Progress", "An existing meeting session is already active. Please stop it before starting a new one.")
                return

        session_id = str(uuid.uuid4())
        session_title = f"Meeting - {datetime.now().strftime('%H:%M:%S')}"
        
        embedding_dim = ai_logic.EMBEDDING_MODEL.get_sentence_embedding_dimension()
        new_session = {
            "id": session_id,
            "title": session_title,
            "has_dynamic_title": False,
            "transcript_chunks": [],
            "transcript": "", 
            "faiss_index": faiss.IndexFlatL2(embedding_dim),
            "summary": "",
            "status": "stopped", # Start in a 'stopped' state initially
            "transcript_queue": None,
            "summarizer_thread": None
        }
        
        self.meeting_sessions[session_id] = new_session
        
        # Add to GUI first, then start it
        self.gui.add_meeting_session_to_list(session_id, session_title)
        self.switch_active_meeting_session(session_id)
        
        # Now, toggle it to the 'active' state
        self.toggle_meeting_session_status(session_id)
        
    def toggle_meeting_session_status(self, session_id):
        session = self.meeting_sessions.get(session_id)
        if not session: return

        if session['status'] == 'stopped':
            for s in self.meeting_sessions.values():
                if s['status'] == 'active':
                    messagebox.showwarning("Meeting in Progress", f"Session '{s['title']}' is already active. Please stop it before starting another.")
                    return
            
            self.queue_log(f"Resuming or Starting meeting session: {session['title']}")
            
            # --- THIS IS THE FIX ---
            # If resuming a previously saved session, the RAG components won't exist.
            # We must create them here before starting the transcription.
            if 'transcript_chunks' not in session:
                self.queue_log("Initializing RAG components for resumed session...")
                embedding_dim = ai_logic.EMBEDDING_MODEL.get_sentence_embedding_dimension()
                session['transcript_chunks'] = []
                session['faiss_index'] = faiss.IndexFlatL2(embedding_dim)
                # We could also re-build the index from the existing transcript here if needed
            # ------------------------

            session['status'] = 'active'
            session['transcript_queue'] = queue.Queue()

            def on_transcription(text_chunk):
                # Using a local session reference from the outer scope
                if session.get("status") == "active":
                    session['transcript_chunks'].append(text_chunk)
                    session['transcript'] += text_chunk
                    embedding = ai_logic.EMBEDDING_MODEL.encode([text_chunk])
                    session['faiss_index'].add(embedding.astype('float32'))
                    if self.active_meeting_session_id == session_id:
                        self.gui.update_transcript_display(text_chunk)
                    session['transcript_queue'].put(text_chunk)

            def on_volume(level):
                if self.active_meeting_session_id == session_id:
                    self.gui.update_meeting_volume(level)

            self.stt_engine.start_live_transcription(session_id, on_transcription, on_volume)
            
            summarizer_thread = threading.Thread(target=self._summarization_worker, args=(session_id,), daemon=True)
            summarizer_thread.start()
            session['summarizer_thread'] = summarizer_thread

            self.gui.update_session_list_status(session_id, "Active")

        # --- STOP LOGIC ---
        elif session['status'] == 'active':
            self.queue_log(f"Stopping meeting session: {session['title']}")
            session['status'] = 'stopping'
            self.stt_engine.stop_listening() 
            if 'transcript_queue' in session:
                session['transcript_queue'].put(None) 
            self.gui.update_session_list_status(session_id, "Stopping...")

    def _summarization_worker(self, session_id):
        session = self.meeting_sessions.get(session_id)
        if not session: return

        transcript_batch = []
        batch_interval = self.config.get("meeting_mode_batch_interval", 15) 
        last_update_time = time.time()
        
        main_loop_active = True
        while main_loop_active:
            try:
                chunk = session['transcript_queue'].get(timeout=1)
                if chunk is None:
                    main_loop_active = False
                else:
                    transcript_batch.append(chunk)
            except queue.Empty:
                pass

            now = time.time()
            is_final_batch = not main_loop_active and transcript_batch
            
            if transcript_batch and ((now - last_update_time > batch_interval) or is_final_batch):
                batch_str = "".join(transcript_batch)
                transcript_batch.clear()
                
                if self.active_meeting_session_id == session_id:
                    self.root.after(0, self.gui.show_summary_status, "Thinking...")

                summary_stream = ai_logic.get_streaming_summary(self, session_id, batch_str)
                
                new_summary_text = ""
                line_buffer = ""
                
                for summary_chunk in summary_stream:
                    if summary_chunk == "[CLEAR_SUMMARY]":
                        if self.active_meeting_session_id == session_id:
                            self.root.after(0, self.gui.update_summary_display, "[CLEAR_SUMMARY]")
                        continue

                    new_summary_text += summary_chunk
                    line_buffer += summary_chunk
                    if "\n" in line_buffer:
                        lines = line_buffer.split("\n")
                        line_buffer = lines.pop()
                        for line in lines:
                            if self.active_meeting_session_id == session_id:
                                self.root.after(0, self.gui.update_summary_display, line + "\n")
                
                if line_buffer and self.active_meeting_session_id == session_id:
                    self.root.after(0, self.gui.update_summary_display, line_buffer)
                
                if self.active_meeting_session_id == session_id:
                    self.root.after(0, self.gui.hide_summary_status)

                session['summary'] = new_summary_text
                
                # --- NEW: Generate title after the first summary is complete ---
                if not session.get('has_dynamic_title') and new_summary_text.strip():
                    session['has_dynamic_title'] = True
                    new_title = ai_logic.generate_session_title(self, new_summary_text)
                    if new_title:
                        session['title'] = new_title
                        self.root.after(0, self.gui.update_session_title, session_id, new_title)
                
                last_update_time = time.time()
        
        self.root.after(0, self.gui.update_session_list_status, session_id, "Stopped")
        self.queue_log(f"Summarization worker gracefully finished for session {session_id}.")


    def stop_meeting_session(self, session_id):
        session = self.meeting_sessions.get(session_id)
        if session and session['status'] == "active":
            self.queue_log(f"Stopping meeting session: {session['title']}")
            
            # The worker thread will detect this status change and perform its final summary
            session['status'] = "stopped"
            
            self.stt_engine.stop_listening() 
            
            if 'transcript_queue' in session:
                session['transcript_queue'].put(None) 
            
            self.gui.update_session_list_status(session_id, "Stopped")

    def copy_transcript_to_clipboard(self):
        if self.active_meeting_session_id:
            session = self.meeting_sessions.get(self.active_meeting_session_id)
            if session:
                pyperclip.copy(session['transcript'])
                self.queue_log("Transcript copied to clipboard.")

    def copy_summary_to_clipboard(self):
        if self.active_meeting_session_id:
            session = self.meeting_sessions.get(self.active_meeting_session_id)
            if session:
                pyperclip.copy(session['summary'])
                self.queue_log("Summary copied to clipboard.")

    def delete_meeting_session(self, session_id):
        if session_id in self.meeting_sessions:
            # Check if session is active before trying to stop
            if self.meeting_sessions[session_id].get('status') == 'active':
                self.toggle_meeting_session_status(session_id)
            
            deleted_session_title = self.meeting_sessions.pop(session_id)['title']
            
            self.gui.remove_session_from_list(session_id)
            
            if self.active_meeting_session_id == session_id:
                self.active_meeting_session_id = None
                self.gui.load_session_data("","")
            
            self.queue_log(f"Deleted meeting session: {deleted_session_title}")

    def save_meeting_session(self, session_id):
        session = self.meeting_sessions.get(session_id)
        if not session: return

        file_path = filedialog.asksaveasfilename(
            initialdir=os.getcwd(),
            title="Save Meeting",
            defaultextension=".txt",
            filetypes=[("Text Documents", "*.txt"), ("All Files", "*.*")],
            initialfile=f"{session['title']}.txt"
        )

        if not file_path: return

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"--- {session['title']} ---\n\n")
                f.write("--- SUMMARY ---\n")
                f.write(session['summary'])
                f.write("\n\n--- FULL TRANSCRIPT ---\n")
                f.write(session['transcript'])
            self.queue_log(f"Session saved to {file_path}")
            messagebox.showinfo("Success", "Meeting session saved successfully.")
        except Exception as e:
            self.queue_log(f"Error saving session: {e}")
            messagebox.showerror("Error", f"Could not save session: {e}")

    def handle_meeting_qna(self):
        question = self.gui.meeting_qna_input.get()
        if not question.strip() or self.active_meeting_session_id is None:
            return

        self.gui.meeting_qna_input.delete(0, tk.END)
        session = self.meeting_sessions.get(self.active_meeting_session_id)
        if not session: return

        summary = session['summary']
        if not summary.strip():
            self.gui.update_summary_display("\n\nQ: " + question + "\nA: I can't answer yet, the summary is still empty.")
            return

        self.gui.update_summary_display("\n\nQ: " + question + "\nA: Thinking...")

        def _task():
            response = ai_logic.answer_question_on_summary(self, summary, question)
            self.root.after(0, self.gui.replace_last_qna_answer, response)

        threading.Thread(target=_task, daemon=True).start()

    def switch_active_meeting_session(self, session_id):
        if self.active_meeting_session_id == session_id: return
        
        self.active_meeting_session_id = session_id
        session = self.meeting_sessions.get(session_id)
        if session:
            self.gui.show_view('meeting') 
            self.gui.load_session_data(session['transcript'], session['summary'])
            self.queue_log(f"Switched to session: {session['title']}")

    def replace_last_qna_answer(self, new_answer):
        if hasattr(self, 'live_summary_display') and self.live_summary_display.winfo_exists():
            self.live_summary_display.config(state='normal')
            
            # Find the start of the "A: Thinking..." placeholder
            start_pos = self.live_summary_display.search("A: Thinking...", "1.0", stopindex=tk.END, backwards=True)
            if start_pos:
                # Delete the placeholder and insert the real answer
                end_pos = f"{start_pos}+{len('A: Thinking...')}c"
                self.live_summary_display.delete(start_pos, end_pos)
                self.live_summary_display.insert(start_pos, "A: " + new_answer)

            self.live_summary_display.see(tk.END)
            self.live_summary_display.config(state='disabled')

    def _load_and_reschedule_reminders(self):
        """Loads reminders from file and reschedules them on startup."""
        reminder_file = "reminders.json"
        if not os.path.exists(reminder_file):
            return

        self.queue_log("Loading and rescheduling pending reminders...")
        
        from skills.reminder_skill import _trigger_reminder
        
        with open(reminder_file, 'r') as f:
            reminders = json.load(f)

        pending_reminders = []
        now = datetime.now()

        for reminder in reminders:
            run_date = datetime.fromisoformat(reminder['run_date'])
            if run_date > now:
                self.scheduler.add_job(
                    func=_trigger_reminder,
                    trigger='date',
                    run_date=run_date,
                    args=[self, reminder['id'], reminder['message']],
                    id=reminder['id']
                )
                pending_reminders.append(reminder)
            else:
                self.speak_response(f"Here is a missed reminder: {reminder['message']}")
        
        with open(reminder_file, 'w') as f:
            json.dump(pending_reminders, f, indent=4)
        
        self.queue_log(f"Rescheduled {len(pending_reminders)} reminders.")

    def start_background_services(self):
        """Checks the config and starts enabled background services."""
        if self.config.get("file_system_watcher", {}).get("enabled"):
            self.start_file_watcher()
        if self.config.get("clipboard_manager", {}).get("enabled"):
            self.start_clipboard_manager()
        self.start_hotkey_listener()

    def _clipboard_monitor_loop(self):
        pythoncom.CoInitialize()
        self.queue_log("Clipboard History Manager started.")
        
        try:
            while not self.is_clipboard_manager_running.is_set():
                try:
                    current_content = pyperclip.paste()
                    if current_content and current_content != self.last_clipboard_content:
                        self.last_clipboard_content = current_content
                        self.clipboard_history.insert(0, current_content)
                        if len(self.clipboard_history) > 20:
                            self.clipboard_history = self.clipboard_history[:20]
                        self.queue_log(f"Clipboard history updated with: '{current_content[:30]}...'")
                except Exception as e:
                    self.queue_log(f"Clipboard monitor loop error: {e}")
                
                time.sleep(1.5)
        finally:
            pythoncom.CoUninitialize()
            self.queue_log("Clipboard History Manager stopped.")

    def start_clipboard_manager(self):
        if self.clipboard_thread and self.clipboard_thread.is_alive():
            return
        self.is_clipboard_manager_running.clear()
        self.clipboard_thread = threading.Thread(target=self._clipboard_monitor_loop, daemon=True)
        self.clipboard_thread.start()

    def stop_clipboard_manager(self):
        self.is_clipboard_manager_running.set()
        if self.clipboard_thread and self.clipboard_thread.is_alive():
            self.clipboard_thread.join(timeout=2)
        self.clipboard_history.clear()
        self.last_clipboard_content = ""

    def start_file_watcher(self):
        if self.fs_observer and self.fs_observer.is_alive():
            return
            
        config = self.config.get("file_system_watcher", {})
        path = config.get("path")

        if not path or not os.path.isdir(path):
            self.queue_log(f"Cannot start file watcher: Path '{path}' is not a valid directory.")
            return

        event_handler = self.FileCreationHandler(self)
        self.fs_observer = Observer()
        self.fs_observer.schedule(event_handler, path, recursive=False)
        self.fs_observer.start()
        self.queue_log(f"File watcher started, monitoring folder: {path}")

    def stop_file_watcher(self):
        if self.fs_observer and self.fs_observer.is_alive():
            self.fs_observer.stop()
            self.fs_observer.join()
            self.queue_log("File watcher stopped.")
        self.fs_observer = None

    def manage_background_services_on_save(self):
        new_config = self.config
        old_config = self._old_config

        new_voice = new_config.get("tts", {}).get("speaker_wav_path")
        if new_voice and new_voice != self.tts_engine.speaker_wav_path:
            self.queue_log("Voice profile changed. Re-initializing TTS engine in background...")
            threading.Thread(target=self._reinitialize_tts_worker, daemon=True).start()

        if new_config.get("file_system_watcher", {}).get("enabled") and not old_config.get("file_system_watcher", {}).get("enabled"):
            self.start_file_watcher()
        elif not new_config.get("file_system_watcher", {}).get("enabled") and old_config.get("file_system_watcher", {}).get("enabled"):
            self.stop_file_watcher()

        if new_config.get("clipboard_manager", {}).get("enabled") and not old_config.get("clipboard_manager", {}).get("enabled"):
            self.start_clipboard_manager()
        elif not new_config.get("clipboard_manager", {}).get("enabled") and old_config.get("clipboard_manager", {}).get("enabled"):
            self.stop_clipboard_manager()

        if new_config.get("hotkeys", []) != old_config.get("hotkeys", []):
            self.queue_log("Hotkey configuration changed, restarting listener...")
            self.stop_hotkey_listener()
            self.start_hotkey_listener()

        self._old_config = self.config.copy()

    class FileCreationHandler(FileSystemEventHandler):
        def __init__(self, app_controller):
            self.app = app_controller

        def on_created(self, event):
            if not event.is_directory:
                filename = os.path.basename(event.src_path)
                folder = os.path.basename(os.path.dirname(event.src_path))
                message = f"A new file named '{filename}' has been added to your {folder} folder."
                self.app.root.after(0, self.app.speak_response, message)

    def execute_command(self, command, attached_file=None):
        self.gui.update_status("Thinking...")
        
        def _task(cmd, file_path):
            pythoncom.CoInitialize()
            try:
                response = None
                command_lower = cmd.lower()

                if self.conversation_state:
                    if command_lower in ["cancel", "never mind", "stop"]:
                        self.conversation_state = None
                        response = "Okay, I've cancelled the current task."
                    else:
                        skill_name = self.conversation_state.get("skill")
                        if skill_name == 'email':
                            from skills.email_skill import handle_conversation
                            response = handle_conversation(self, cmd)
                        elif skill_name == 'document':
                            from skills.document_skill import handle_conversation
                            response = handle_conversation(self, cmd)
                
                if response is None:
                    response = self.command_handler.handle(cmd, attached_file=file_path)
                
                if response is None:
                    query_type = ai_logic.classify_query(self.triage_model, cmd, self.queue_log)
                    
                    if query_type == "visual":
                        screenshot = system_skill.capture_screen(self.queue_log)
                        if screenshot:
                            response = ai_logic.analyze_image(self.answer_model, self.conversation_history, screenshot, cmd, self.queue_log)
                        else:
                            response = "I wasn't able to capture the screen."
                    else: 
                        selected_engine = self.config.get("ai_engine", "gemini_online")
                        self.queue_log(f"Using '{selected_engine}' for conversational response.")

                        if selected_engine == "ollama_offline":
                            # Call the new tool-enabled function for Ollama
                            response = ai_logic.get_ollama_response_with_tools(self, self.conversation_history, cmd)
                        else: # Default to Gemini
                            prompt = (f"Assuming the current date is {datetime.now().strftime('%A, %B %d, %Y')}, "
                                      f"provide a direct, conversational answer to the user query: '{cmd}'")
                            response = ai_logic.get_ai_response(self.answer_model, self.conversation_history, prompt, self.queue_log)
                            response = "The online AI is currently unavailable due to quota limits."
                        
                        self.conversation_history.append({"role": "user", "parts": [cmd]})
                        self.conversation_history.append({"role": "model", "parts": [response]})

                final_response = response or "I'm sorry, I couldn't process that."
                self.root.after(0, self.speak_response, final_response)
            finally:
                pythoncom.CoUninitialize()
        
        threading.Thread(target=_task, args=(command, attached_file), daemon=True).start()


    def clear_conversation_history(self):
        """Clears the conversational history list."""
        self.conversation_history.clear()
        self.queue_log("Conversation history cleared due to model switch.")


    def speak_response(self, text):
        if self.is_tts_reinitializing:
            self.queue_log("TTS is re-initializing. Speech request ignored.")
            def revert_status():
                if self.is_tts_reinitializing:
                    self.gui.update_status("Loading new voice...")
                else:
                    self.gui.update_status("Ready")
            self.root.after(1500, revert_status)
            return

        if not text or not text.strip():
            self.queue_log("Empty response ignored.")
            return
        
        if text == self.last_spoken_text or text == self.next_utterance:
            return

        if self.is_speaking:
            self.queue_log(f"Interrupting current speech. Queueing: '{text[:40]}...'")
            self.next_utterance = text
            self.stop_speaking()
            return
        
        self.last_spoken_text = text
        self.is_speaking = True
        self.gui.update_status("Speaking...")
        self.gui.add_chat_message("AURA", text)
        
        self.tts_engine.speak(text, self.on_speech_finished)

    def queue_log(self, message):
        self.log_queue.put(message)

    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                message = self.log_queue.get_nowait()
                self.gui.add_log(message)
            except queue.Empty:
                pass
        self.root.after(100, self._process_log_queue)

    def get_timestamp(self):
        return datetime.now().strftime("%H:%M:%S")

    def play_sound(self, sound_name):
        sound_path = self.config.get("sounds", {}).get(sound_name)
        if sound_path and os.path.exists(sound_path):
            try:
                p = Process(target=playsound, args=(sound_path,))
                p.start()
            except Exception as e:
                self.queue_log(f"Error playing sound {sound_name}: {e}")

    def start_listening(self):
        if self.is_listening:
            self.queue_log("Already in a listening state. Request ignored.")
            return
        
        self.stop_speaking()
        self.is_listening = True
        self.play_sound("activation")
        self.gui.update_status("Listening...", is_listening=True)
        self.queue_log("Listening started...")
        
        from skills import web_skill as web
        self.stt_engine.start_listening(self.process_speech_input, lambda: web.is_online(self.queue_log))

    def stop_listening(self):
        self.queue_log("Controller's stop_listening called. Forcing state reset.")
        
        self.is_listening = False
        
        if hasattr(self, 'stt_engine'):
            self.stt_engine.stop_listening()
        
        self.gui.update_status("Ready", is_listening=False)

        
    def stop_speaking(self):
        self.queue_log("Stop speaking command received by controller.")
        self.tts_engine.stop()

    def process_speech_input(self, text):
        self.queue_log(f"Heard: {text}")
        self.stop_listening()
        self.gui.add_chat_message("You", text)
        self.execute_command(text)

    def send_chat_message(self, message):
        if not message.strip(): return
        self.stop_speaking()
        attached_file = self.gui.attached_file_path.get()
        self.gui.attached_file_path.set("")
        self.gui.chat_input.delete(0, tk.END)
        self.gui.add_chat_message("You", message)
        self.execute_command(message, attached_file=attached_file)


    def on_speech_finished(self):
        self.is_speaking = False
        self.last_spoken_text = None
        
        if self.next_utterance:
            text_to_say = self.next_utterance
            self.next_utterance = None
            self.root.after(50, lambda: self.speak_response(text_to_say))
            return

        if self.config.get("audio", {}).get("continuous_listening", False):
            self.root.after(250, self.start_listening)
        else:
            if not self.is_listening:
                self.gui.update_status("Ready")

    def save_settings(self):
        try:
            old_config = self.config.copy()
            self.config = self.gui.get_settings()
            
            old_audio_config = old_config.get("audio", {})
            new_audio_config = self.config.get("audio", {})
            old_tts_config = old_config.get("tts", {})
            new_tts_config = self.config.get("tts", {})
            
            with open("config.json", 'w') as f:
                json.dump(self.config, f, indent=4)
            self.queue_log("Settings saved successfully.")

            if (old_audio_config != new_audio_config or
                old_tts_config.get("speaker_wav_path") != new_tts_config.get("speaker_wav_path")):
                self.reinitialize_audio_engines()

            if old_config.get("enabled_skills") != self.config.get("enabled_skills") or \
               old_config.get("routines") != self.config.get("routines"):
                self.queue_log("Skills or routines changed, reloading command handler...")
                self.command_handler._load_skills()

            self.manage_background_services_on_save()

            messagebox.showinfo("Success", "Settings have been saved.")

        except Exception as e:
            self.queue_log(f"ERROR saving config: {e}")
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def load_config(self):
        try:
            with open("config.json", 'r') as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "gemini_api_key": "", "Google Search_api_key": "", "Google Search_engine_id": "",
                "tesseract_cmd_path": "", "whisper_model_path": "",
                "app_paths": {"notepad": "notepad.exe"},
                "sounds": {"activation": "sounds/activation.wav", "completion": "sounds/completion.wav"}
            }


    def on_closing(self):
        # --- MODIFIED: Save sessions before closing ---
        self._save_sessions_on_exit()
        
        self.stop_hotkey_listener()
        self.stop_file_watcher()
        if self.tts_process and self.tts_process.is_alive():
            self.tts_process.terminate()
        if messagebox.askyesno("Exit", "Do you want to exit AURA?"):
            self.scheduler.shutdown()
            self.root.destroy()

    def run(self):
        self.root.mainloop()

    def run_startup_routine(self):
        self.queue_log("Startup routine triggered.")
        
        def startup_task():
            time.sleep(5)
            
            current_hour = datetime.now().hour
            if 5 <= current_hour < 12:
                greeting = "Good morning."
            elif 12 <= current_hour < 18:
                greeting = "Good afternoon."
            else:
                greeting = "Good evening."

            from skills import calendar_skill
            calendar_summary = calendar_skill.get_upcoming_events(self.queue_log)

            full_startup_message = f"{greeting} Welcome back. {calendar_summary}"

            self.speak_response(full_startup_message)

        threading.Thread(target=startup_task, daemon=True).start()

    def start_hotkey_listener(self):
        hotkey_config = self.config.get("hotkeys", [])
        hotkey_list = []

        if isinstance(hotkey_config, dict):
            old_hotkey = hotkey_config.get("activation_hotkey")
            if old_hotkey and old_hotkey != "Not Set":
                hotkey_list.append({"combination": old_hotkey, "action": "Start Listening"})
        elif isinstance(hotkey_config, list):
            hotkey_list = hotkey_config

        if not hotkey_list:
            self.queue_log("No hotkeys are configured.")
            return

        try:
            hotkey_map = {}
            for item in hotkey_list:
                combination = item.get("combination")
                action_name = item.get("action")
                
                if combination and action_name in self.hotkey_actions:
                    pynput_format = combination.replace('ctrl', '<ctrl>').replace('alt', '<alt>').replace('shift', '<shift>')
                    hotkey_map[pynput_format] = self.hotkey_actions[action_name]

            if not hotkey_map:
                self.queue_log("No valid hotkeys found to activate.")
                return

            self.global_hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self.global_hotkey_listener.start()
            self.queue_log(f"Global hotkeys are now active.")
        except Exception as e:
            self.queue_log(f"Failed to start hotkey listener: {e}")

    def stop_hotkey_listener(self):
        if self.global_hotkey_listener and self.global_hotkey_listener.is_alive():
            self.global_hotkey_listener.stop()
            self.global_hotkey_listener = None
            self.queue_log("Global hotkey listener stopped.")

    def _reinitialize_tts_worker(self):
        self.is_tts_reinitializing = True
        self.root.after(0, self.gui.update_status, "Loading new voice...")
        
        try:
            self.tts_engine.shutdown()
            self.tts_engine = CoquiTTS(self.config, self.queue_log)
        finally:
            self.is_tts_reinitializing = False
            self.root.after(0, self.gui.update_status, "Ready")

    def _get_audio_devices(self):
        """Fetches, classifies, and de-duplicates audio devices, ignoring invalid ones."""
        self.input_devices.clear()
        self.loopback_devices.clear()
        seen_mic_names = set()
        seen_loopback_names = set()
        loopback_keywords = ['stereo mix', 'loopback', 'what u hear', 'what you hear']
        ignore_keywords = ['sound mapper', 'primary sound']

        try:
            for i, device in enumerate(sd.query_devices()):
                device_name_lower = device['name'].lower()
                
                if any(keyword in device_name_lower for keyword in ignore_keywords):
                    continue

                if device['max_input_channels'] > 0:
                    is_loopback = any(keyword in device_name_lower for keyword in loopback_keywords)

                    if is_loopback:
                        if device['name'] not in seen_loopback_names:
                            self.loopback_devices.append({'index': i, **device})
                            seen_loopback_names.add(device['name'])
                    else:
                        if device['name'] not in seen_mic_names:
                            self.input_devices.append({'index': i, **device})
                            seen_mic_names.add(device['name'])

            self.queue_log(f"Found {len(self.input_devices)} unique microphones and {len(self.loopback_devices)} unique loopback devices.")

        except Exception as e:
            self.queue_log(f"Could not fetch audio devices: {e}")


    def toggle_mic_test(self):
        """Starts or stops the live microphone volume visualizer."""
        if self.is_mic_testing:
            self.is_mic_testing = False
            self.stt_engine.stop_listening()
            self.gui.mic_test_button.config(text="Start Mic Test")
            self.gui.mic_level_var.set(0.0)
            self.queue_log("Microphone test stopped.")
        else:
            self.is_mic_testing = True
            
            def volume_callback(level):
                if self.is_mic_testing:
                    self.gui.mic_level_var.set(level)

            self.stt_engine.start_volume_visualizer(volume_callback)
            self.gui.mic_test_button.config(text="Stop Mic Test")
            self.queue_log("Microphone test started.")

    def reinitialize_audio_engines(self):
        """Re-creates the STT and TTS engines with the new config."""
        self.queue_log("Audio settings changed. Re-initializing audio engines...")
        self.stop_listening()
        self.stop_speaking()
        
        time.sleep(0.5)

        self._get_audio_devices()

        self.stt_engine = SpeechToText(self, self.config, self.queue_log)
        self.tts_engine = CoquiTTS(self.config, self.queue_log)

        if self.gui and self.gui.settings_view_frame.winfo_exists():
            self.gui.load_settings_to_gui()

        self.queue_log("Audio engines re-initialized successfully.")