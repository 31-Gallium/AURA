# app_controller.py
import tkinter as tk
from tkinter import ttk, PhotoImage, messagebox, filedialog
import threading
import json
import os
from datetime import datetime
import time
import queue
import traceback
from multiprocessing import Queue as mp_Queue
import pythoncom
import pyperclip
from pynput import keyboard
import sounddevice as sd
from playsound import playsound
from apscheduler.schedulers.background import BackgroundScheduler
import uuid
import numpy as np
import faiss
import random
import logging
from logging import LogRecord
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

import queue
from gui import AutoWrappingText

from gui import GUI
from stt import SpeechToText
from command_handler import CommandHandler
import ai_logic
from ai_logic import get_ai_response

# --- Logging Setup for Progress ---
class QueueHandler(logging.Handler):
    """Sends log records to a multiprocessing queue."""
    def __init__(self, queue):
        super().__init__()
        self.queue = queue

    def emit(self, record):
        try:
            self.queue.put(record)
        except Exception:
            self.handleError(record)

class AURAApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()  # Hide the main window initially
        self.log_queue = mp_Queue()
        self.animation_data_queue = queue.Queue()
        self.config = self.load_config()
        self.is_running = True

        # --- Initialize all attributes to prevent AttributeErrors ---
        self.gui = None
        self.command_handler = None
        self.tts_engine = None
        self.stt_engine = None
        self.triage_model = None
        self.answer_model = None
        self.active_meeting_session_id = None
        self.scheduler = BackgroundScheduler(daemon=True)
        self.stop_listening_event = threading.Event()
        self.stop_speaking_event = threading.Event()
        self.loading_complete = threading.Event()
        self.start_time = 0
        self.last_progress_value = 0
        self.LOADING_TIME_SECONDS = 15  # A reasonable default loading time

        self.conversation_history = []
        self.is_listening = False
        self.speaking_active = False
        self.is_mic_testing = False
        self.loading_failed = False
        self.is_tts_reinitializing = False
        self.stop_generating_event = threading.Event()
        self.last_spoken_text = None
        self.fs_observer = None
        self.clipboard_thread = None
        self.is_clipboard_manager_running = threading.Event()
        self.last_clipboard_content = ""
        self.global_hotkey_listener = None
        self._old_config = self.config.copy()
        self.meeting_sessions = {}
        
        def routine_proxy_open_app(**kwargs):
            alias = kwargs.get('alias')
            if alias:
                self.execute_command(f"open {alias}")

        self.routine_actions = {
            "Open Application": {"params": {"alias": "e.g., notepad"}, "func": routine_proxy_open_app},
            "Say Something": {"params": {"text": "What to say"}, "func": self.speak_response}
        }
        
        self.clipboard_history = []

        # Splash screen widgets will be stored here
        self.splash_logo_label = None
        self.splash_progress_label = None
        self.splash_progress_bar = None
        self.logo_image = None  # To prevent garbage collection

        self.input_devices = []
        self.output_devices = []
        self.loopback_devices = []

        self._initialize_config_defaults()
        self._get_audio_devices()

    def run(self):
        """Main entry point to start the application."""
        self.start_time = time.time()
        self._setup_logging_thread()
        self._setup_splash_screen()
        self.loading_thread = threading.Thread(target=self._background_loader, daemon=True)
        self.loading_thread.start()
        self._check_loading_status()
        self.root.mainloop()

    def _setup_splash_screen(self):
        """Configures the main root window to act as a splash screen."""
        self.root.title("Loading AURA")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)

        window_width, window_height = 400, 200
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        color_bg = "#1e1e1e"
        color_accent = "#8ab4f8"
        self.root.config(bg=color_bg)

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            logo_path = os.path.join(script_dir, "assets", "logo_aura_500.png")
            self.logo_image = PhotoImage(file=logo_path)
            self.splash_logo_label = tk.Label(self.root, image=self.logo_image, bg=color_bg)
        except Exception:
            self.splash_logo_label = tk.Label(self.root, text="AURA", font=("Segoe UI", 24, "bold"), fg=color_accent, bg=color_bg)
        self.splash_logo_label.pack(pady=10)

        self.splash_progress_label = tk.Label(self.root, text="Starting...", font=("Segoe UI", 10), fg="#e0e0e0", bg=color_bg)
        self.splash_progress_label.pack(pady=5)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("Horizontal.TProgressbar", troughcolor=color_bg, bordercolor=color_bg, background=color_accent)
        self.splash_progress_bar = ttk.Progressbar(self.root, orient="horizontal", length=300, mode="determinate", style="Horizontal.TProgressbar")
        self.splash_progress_bar.pack(pady=10)

        self.root.deiconify()
        self.root.update()

    def _update_splash_progress(self, message, percentage):
        """Updates the widgets on the splash screen safely."""
        if self.splash_progress_label and self.splash_progress_label.winfo_exists():
            self.splash_progress_label.config(text=message)
        if self.splash_progress_bar and self.splash_progress_bar.winfo_exists():
            self.splash_progress_bar['value'] = max(0, min(100, percentage))
        self.root.update_idletasks()

    def _setup_logging_thread(self):
        """Sets up a thread to process log messages from a queue."""
        logger = logging.getLogger('AURAApp')
        logger.setLevel(logging.INFO)
        
        if not any(isinstance(handler, QueueHandler) for handler in logger.handlers):
            logger.addHandler(QueueHandler(self.log_queue))
        logger.propagate = False

        def log_processor():
            while self.is_running:
                try:
                    record = self.log_queue.get(timeout=1)
                    if record is None: break
                    
                    log_message = record.getMessage()
                    progress_percent = getattr(record, 'progress_percent', None)
                    
                    if progress_percent is not None:
                        self.last_progress_value = max(self.last_progress_value, progress_percent)
                    
                    if not self.loading_complete.is_set():
                        self.root.after(0, self._update_splash_progress, log_message, self.last_progress_value)
                    elif self.gui and hasattr(self.gui, 'logs_display') and self.gui.logs_display.winfo_exists():
                        self.root.after(0, self.gui.add_log, log_message)
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Error in log_processor: {e}\n{traceback.format_exc()}")

        self.log_processor_thread = threading.Thread(target=log_processor, daemon=True)
        self.log_processor_thread.start()

    def queue_log(self, message, level='INFO', progress_percent=None):
        """Queues a log message to be processed by the logging thread."""
        logger = logging.getLogger('AURAApp')
        record = logging.LogRecord('AURAApp', getattr(logging, level.upper()), None, None, message, None, None)
        record.progress_percent = progress_percent
        self.log_queue.put(record)

    def _background_loader(self):
        """Loads all major components in a background thread."""
        try:
            self.queue_log("Starting background loading...", progress_percent=5)
            ai_logic.load_embedding_model(self.queue_log)
            self.queue_log("Embedding model loaded.", progress_percent=30)

            self.command_handler = CommandHandler(self)
            self.queue_log("Command handler loaded.", progress_percent=70)

            from tts import CoquiTTS
            self.tts_engine = CoquiTTS(self, self.root, self.config, self.queue_log)
            self.queue_log("TTS engine initialized.", progress_percent=80)
            
            self.stt_engine = SpeechToText(self, self.command_handler, self.tts_engine, self.config, self.queue_log)
            self.queue_log("STT engine initialized.", progress_percent=95)

            self.queue_log("All components loaded.", progress_percent=100)
        except Exception as e:
            self.queue_log(f"FATAL: {e}", level='ERROR', progress_percent=100)
            traceback.print_exc()
            self.loading_failed = True
        finally:
            self.loading_complete.set()

    def _check_loading_status(self):
        """Periodically checks if the background loading is complete."""
        if self.loading_complete.is_set():
            if self.loading_failed:
                self.on_critical_error("A component failed to load. Check logs for details.")
            else:
                self._finish_startup()
            return

        elapsed_time = time.time() - self.start_time
        progress_from_time = min(95, (elapsed_time / self.LOADING_TIME_SECONDS) * 100)
        current_progress = max(progress_from_time, self.last_progress_value)
        self._update_splash_progress("Loading components...", current_progress)

        self.root.after(100, self._check_loading_status)

    def _preload_ollama_models(self):
            """Warms up the selected Ollama models to prevent cold start delays."""
            preload_setting = self.config.get("preload_models", "None")
            if preload_setting == "None":
                return

            self.queue_log(f"Preloading Ollama models based on setting: {preload_setting}")
            
            models_to_load = []
            if preload_setting in ["Creator AI Only", "Both"]:
                models_to_load.append(self.config.get("ollama_model", "llama3.1"))
            # Note: The 'aura-router' model is no longer used in the Hybrid system
            
            def preloader_task():
                import time
                from ai_logic import get_ollama_streaming_response
                for model_name in models_to_load:
                    self.queue_log(f"Warming up model: {model_name}...")
                    try:
                        # Send a trivial prompt to force the model to load
                        list(get_ollama_streaming_response(self, "hello", model_name))
                        self.queue_log(f"Successfully preloaded {model_name}.")
                    except Exception as e:
                        self.queue_log(f"Failed to preload model {model_name}: {e}", "ERROR")
                    time.sleep(1)
            
            threading.Thread(target=preloader_task, daemon=True).start()

    def _finish_startup(self):
        """Finalizes the application startup after all components are loaded."""
        for widget in self.root.winfo_children():
            widget.destroy()

        self.root.overrideredirect(False)
        self.root.title("AURA")
        self.root.geometry("1200x800")
        self.root.resizable(True, True)
        
        self.root.update_idletasks()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (self.root.winfo_width() // 2)
        y = (screen_height // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.gui = GUI(self)
        self._poll_animation_queue()
        
        if not self.scheduler.running:
            self.scheduler.start()
            self.queue_log("Scheduler started.")

        self.queue_log("Application startup complete.")

        self._preload_ollama_models()

        def on_welcome_message_done():
            self.queue_log("Welcome message finished. Starting background services.")
            self.start_background_services()

        self.root.after(500, lambda: self.speak_response(
            "Welcome to AURA. I am online and ready.", 
            on_done=on_welcome_message_done
        ))


    def _poll_animation_queue(self):
        """Checks for new animation data from the TTS engine and sends it to the GUI."""
        try:
            # Process all pending packets in the queue
            while True:
                packet = self.animation_data_queue.get_nowait()
                if self.gui.mini_window and self.gui.mini_window.is_visible:
                    # Call the mini GUI's method to handle the new sentence
                    self.gui.mini_window.animate_new_sentence(packet)
        except queue.Empty:
            # The queue is empty, which is normal.
            pass
        finally:
            # Schedule the next check
            self.root.after(100, self._poll_animation_queue)

    def on_critical_error(self, error_message):
        """Displays a critical error message and exits the app."""
        if self.splash_progress_label:
            for widget in self.root.winfo_children():
                widget.destroy()
            self.root.update()

        messagebox.showerror("AURA - Critical Error", f"AURA could not start.\n\nError: {error_message}")
        self.exit_app()

    def on_closing(self):
        """Handles the application closing event."""
        if messagebox.askyesno("Exit", "Do you want to exit AURA?"):
            self.exit_app()

    def exit_app(self):
        """Shuts down all services and closes the application."""
        self.queue_log("Exiting application...", level='INFO')
        self.is_running = False
        
        self._save_sessions_on_exit()
        
        self.stop_hotkey_listener()
        self.stop_file_watcher()
        self.stop_clipboard_manager()
        
        if self.tts_engine: self.tts_engine.shutdown()
        if self.stt_engine: self.stt_engine.stop_listening()
        
        if self.scheduler.running:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception as e:
                self.queue_log(f"Error shutting down scheduler: {e}")
        
        if hasattr(self, 'log_queue'): self.log_queue.put(None)
        if hasattr(self, 'log_processor_thread') and self.log_processor_thread.is_alive():
            self.log_processor_thread.join(timeout=1.0)

        if self.root:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        print("Application exited.")
        os._exit(0)

    def load_config(self):
        """Loads the configuration from config.json."""
        config_path = "config.json"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                self.queue_log("Warning: config.json is corrupted. Loading defaults.", "WARNING")
                return self._get_default_config()
        return self._get_default_config()

    def _get_default_config(self):
        """Returns a default configuration dictionary."""
        return {
            "gemini_api_key": "", "weather_api_key": "",
            "whisper_model_path": "",
            "app_paths": {"notepad": "notepad.exe"},
            "sounds": {
                "activation": "sounds/activation.wav",
                "deactivation": "sounds/deactivation.wav",
            },
            "audio": {"stt_engine": "google_online", "continuous_listening": False},
            "hotkeys": [], "enabled_skills": {},
            "file_system_watcher": {"enabled": False, "path": ""},
            "clipboard_manager": {"enabled": False},
            "ai_engine": "gemini_online", "ollama_model": "llama3",
            "tts": {"speaker_wav_path": "voices/default_voice.wav"}
        }

    def _initialize_config_defaults(self):
        """Ensures essential config keys exist."""
        defaults = self._get_default_config()
        for key, value in defaults.items():
            self.config.setdefault(key, value)

    def start_background_services(self):
        """Starts all enabled background services based on the config."""
        if self.config.get("file_system_watcher", {}).get("enabled"):
            self.start_file_watcher()
        if self.config.get("clipboard_manager", {}).get("enabled"):
            self.start_clipboard_manager()
        self.start_hotkey_listener()
        if self.stt_engine:
            self.stt_engine.start_wake_word_listener()

    def send_chat_message(self, message):
        """Handles sending a message from the chat input."""
        if not message.strip(): return
        self.stop_speaking()
        attached_file = self.gui.attached_file_path.get()
        self.gui.attached_file_path.set("")
        self.gui.chat_input.delete("1.0", tk.END)
        self.gui.add_chat_message("You", message)
        self.execute_command(message, attached_file=attached_file)

    def _save_sessions_on_exit(self):
        """Saves all meeting session data to a JSON file."""
        if not self.meeting_sessions: return
        sessions_to_save = [
            {
                "id": s.get('id'), "title": s.get('title'),
                "transcript": s.get('transcript'), "summary": s.get('summary')
            } for s in self.meeting_sessions.values()
        ]
        try:
            with open("sessions.json", "w", encoding="utf-8") as f:
                json.dump(sessions_to_save, f, indent=4)
            self.queue_log("Meeting sessions saved successfully.")
        except Exception as e:
            self.queue_log(f"Error saving sessions: {e}", "ERROR")

    def start_new_meeting_session(self):
        """Creates a new, blank meeting session."""
        if any(s['status'] == 'active' for s in self.meeting_sessions.values()):
            messagebox.showwarning("Meeting in Progress", "An existing meeting session is already active.")
            return

        session_id = str(uuid.uuid4())
        session_title = f"Meeting - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        embedding_dim = ai_logic.EMBEDDING_MODEL.get_sentence_embedding_dimension()
        new_session = {
            "id": session_id, "title": session_title,
            "transcript_chunks": [], "transcript": "",
            "faiss_index": faiss.IndexFlatL2(embedding_dim),
            "summary": "", "status": "stopped",
            "transcript_queue": queue.Queue(), "summarizer_thread": None
        }
        
        self.meeting_sessions[session_id] = new_session
        self.gui.add_meeting_session_to_list(session_id, session_title)
        self.switch_active_meeting_session(session_id)
        self.toggle_meeting_session_status(session_id)

    def toggle_meeting_session_status(self, session_id):
        """Starts or stops a meeting session's transcription and summarization."""
        session = self.meeting_sessions.get(session_id)
        if not session: return

        if session['status'] == 'stopped':
            session['status'] = 'active'
            
            def on_transcription(text_chunk):
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
            
            session['summarizer_thread'] = threading.Thread(target=self._summarization_worker, args=(session_id,), daemon=True)
            session['summarizer_thread'].start()
            self.gui.update_session_list_status(session_id, "Active")

        elif session['status'] == 'active':
            session['status'] = 'stopping'
            if self.stt_engine: self.stt_engine.stop_listening()
            if session.get('transcript_queue'): session['transcript_queue'].put(None)
            self.gui.update_session_list_status(session_id, "Stopping...")

    def _summarization_worker(self, session_id):
        """Worker thread that periodically summarizes new transcript text."""
        session = self.meeting_sessions.get(session_id)
        if not session or not session.get('transcript_queue'): return

        transcript_batch = []
        batch_interval = self.config.get("meeting_mode_batch_interval", 15)
        last_update_time = time.time()
        
        while session.get('status') == 'active':
            try:
                chunk = session['transcript_queue'].get(timeout=1)
                if chunk is None: break
                transcript_batch.append(chunk)
            except queue.Empty:
                pass

            now = time.time()
            if transcript_batch and (now - last_update_time > batch_interval):
                batch_str = "".join(transcript_batch)
                transcript_batch.clear()
                
                if self.active_meeting_session_id == session_id: self.root.after(0, self.gui.show_summary_status, "Thinking...")
                
                summary_stream = ai_logic.get_streaming_summary(self, session_id, batch_str)
                
                full_summary = ""
                if self.active_meeting_session_id == session_id: self.root.after(0, self.gui.update_summary_display, "[CLEAR_SUMMARY]")
                for chunk in summary_stream:
                    if chunk != "[CLEAR_SUMMARY]":
                        full_summary += chunk
                        if self.active_meeting_session_id == session_id: self.root.after(0, self.gui.update_summary_display, chunk)

                session['summary'] = full_summary
                
                if self.active_meeting_session_id == session_id: self.root.after(0, self.gui.hide_summary_status)
                last_update_time = time.time()
        
        session['status'] = 'stopped'
        self.root.after(0, self.gui.update_session_list_status, session_id, "Stopped")

    def stop_meeting_session(self, session_id):
        """Stops an active meeting session."""
        session = self.meeting_sessions.get(session_id)
        if session and session['status'] == "active":
            session['status'] = "stopped"
            if self.stt_engine: self.stt_engine.stop_listening()
            if session.get('transcript_queue'): session['transcript_queue'].put(None)
            self.gui.update_session_list_status(session_id, "Stopped")

    def copy_transcript_to_clipboard(self):
        """Copies the active session's transcript to the clipboard."""
        if self.active_meeting_session_id and self.active_meeting_session_id in self.meeting_sessions:
            pyperclip.copy(self.meeting_sessions[self.active_meeting_session_id]['transcript'])
            self.queue_log("Transcript copied to clipboard.")

    def copy_summary_to_clipboard(self):
        """Copies the active session's summary to the clipboard."""
        if self.active_meeting_session_id and self.active_meeting_session_id in self.meeting_sessions:
            pyperclip.copy(self.meeting_sessions[self.active_meeting_session_id]['summary'])
            self.queue_log("Summary copied to clipboard.")

    def delete_meeting_session(self, session_id):
        """Deletes a meeting session."""
        if session_id in self.meeting_sessions:
            if self.meeting_sessions[session_id]['status'] == 'active':
                self.toggle_meeting_session_status(session_id)
            self.meeting_sessions.pop(session_id, None)
            self.gui.remove_session_from_list(session_id)
            if self.active_meeting_session_id == session_id:
                self.active_meeting_session_id = None
                self.gui.load_session_data("", "")

    def save_meeting_session(self, session_id):
        """Saves a meeting session to a text file."""
        session = self.meeting_sessions.get(session_id)
        if not session: return
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"{session['title'].replace(':', '-')}.txt",
            filetypes=[("Text Documents", "*.txt"), ("All Files", "*.*")]
        )
        if not file_path: return
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"--- {session['title']} ---\n\n")
                f.write("--- SUMMARY ---\n")
                f.write(f"{session['summary']}\n\n")
                f.write("--- FULL TRANSCRIPT ---\n")
                f.write(session['transcript'])
            messagebox.showinfo("Success", "Meeting session saved.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not save session: {e}")

    def handle_meeting_qna(self):
        """Handles a question asked about the current meeting summary."""
        question = self.gui.meeting_qna_input.get()
        if not question.strip() or not self.active_meeting_session_id: return
        self.gui.meeting_qna_input.delete(0, tk.END)
        session = self.meeting_sessions[self.active_meeting_session_id]
        if not session['summary'].strip():
            self.gui.update_summary_display(f"\n\nQ: {question}\nA: The summary is currently empty. Cannot answer.")
            return
        self.gui.update_summary_display(f"\n\nQ: {question}\nA: Thinking...")
        
        def answer_task():
            answer = ai_logic.answer_question_on_summary(self, session['summary'], question)
            self.root.after(0, self.gui.replace_last_qna_answer, answer)
        
        threading.Thread(target=answer_task, daemon=True).start()

    def switch_active_meeting_session(self, session_id):
        """Switches the GUI to display a different meeting session."""
        if self.active_meeting_session_id == session_id: return
        self.active_meeting_session_id = session_id
        session = self.meeting_sessions.get(session_id)
        if session:
            self.gui.show_view('meeting')
            self.gui.load_session_data(session['transcript'], session['summary'])

    def update_wakeword_score(self, score):
        """Updates the wake word detection meter in the GUI."""
        if self.gui: self.gui.update_wakeword_meter(score)

    def execute_command(self, command, attached_file=None):
        """Executes a command in a background thread."""
        if self.gui: self.gui.update_status("Thinking...")
        threading.Thread(target=self._execute_command_task, args=(command, attached_file), daemon=True).start()

    # In app_controller.py, REPLACE the existing _execute_command_task method

    def _execute_command_task(self, cmd, file_path):
        """New Hybrid Flow: Tries regex first, then falls back to AI."""
        pythoncom.CoInitialize()
        try:
            # --- Step 1: Try to handle the command with a simple, fast regex skill ---
            skill_response = self.command_handler.handle(cmd, attached_file=file_path)

            if skill_response is not None:
                # SUCCESS: A direct skill was found and executed.
                # --- FIX: Changed self.log to self.queue_log ---
                self.queue_log(f"Command '{cmd}' handled by a direct skill.")
                self.conversation_history.append({"role": "user", "parts": [cmd]})
                self.conversation_history.append({"role": "model", "parts": [skill_response]})
                if str(skill_response).strip():
                    self.root.after(0, self.speak_response, skill_response)
                else: 
                    self.root.after(0, self.return_to_idle_state)
                return

            # --- Step 2: If no skill matched, fall back to the conversational AI ---
            # --- FIX: Changed self.log to self.queue_log ---
            self.queue_log(f"No direct skill matched for '{cmd}'. Passing to conversational AI.")
            self.root.after(0, self.gui.update_action_button, "generating")
            self.root.after(0, self.gui.update_status, "AURA is thinking...")
            self.stop_generating_event.clear()

            response_stream, full_response_future = get_ai_response(self, self.conversation_history, cmd)

            aura_bubble_widget = self.gui.add_chat_message("AURA", "")
            if aura_bubble_widget:
                aura_bubble_widget.start_typewriter_animation()

            sentence_buffer = ""
            for chunk in response_stream:
                if self.stop_generating_event.is_set(): break
                for char in chunk:
                    if aura_bubble_widget: aura_bubble_widget.char_queue.put(char)
                    sentence_buffer += char
                    if char in '.!?\n':
                        to_speak = sentence_buffer.strip()
                        if to_speak: self.speak_response(to_speak)
                        sentence_buffer = ""

            if sentence_buffer.strip() and not self.stop_generating_event.is_set():
                self.speak_response(sentence_buffer.strip())

            if aura_bubble_widget: aura_bubble_widget.char_queue.put(None)
            if self.stop_generating_event.is_set(): return

            full_text = full_response_future.result(timeout=120)
            self.conversation_history.append({"role": "user", "parts": [cmd]})
            self.conversation_history.append({"role": "model", "parts": [full_text]})
            self.update_ai_monitor(full_text)

        except Exception as e:
            self.queue_log(f"Error executing command task: {e}\n{traceback.format_exc()}", "ERROR")
            if self.is_running: self.root.after(0, lambda: self.speak_response("I ran into an error processing that."))
        finally:
            # The on_speak_done_wrapper now handles returning to idle state
            pythoncom.CoUninitialize()

    def clear_conversation_history(self):
        """Clears the AI's conversational memory."""
        self.conversation_history.clear()
        self.queue_log("Conversation history cleared.")

    # ADD THIS NEW METHOD TO app_controller.py inside the AURAApp class

    def return_to_idle_state(self):
        """
        Finalizes an interaction, sets the GUI to idle, and restarts the wake word listener.
        This is the designated method to call when AURA is finished with a command/response cycle.
        """
        # A check to prevent this from running while actively listening for a command
        if self.is_listening:
            return

        self.queue_log("Interaction complete. Returning to idle state and restarting wake word listener.")
        self.speaking_active = False # Ensure state is consistent

        if self.gui and self.root.winfo_exists():
            self.gui.update_action_button("idle")
            self.gui.update_status("Ready")

        # Crucially, restart the wake word listener for the next interaction
        if self.stt_engine:
            self.stt_engine.start_wake_word_listener()

    # ADD THIS NEW METHOD TO app_controller.py inside the AURAApp class

    def stop_all_ai_activity(self):
        """
        A unified method to stop all AI-related activity, including generation and speech,
        and return the application to a ready state.
        """
        self.queue_log("Unified stop command received. Stopping all AI activity.")
        
        # 1. Signal the generation loop to stop producing new content.
        self.stop_generating_event.set()

        # 2. Stop the TTS engine from playing any current or queued audio.
        if self.tts_engine:
            self.tts_engine.stop()

        # 3. Transition the application back to the idle state.
        self.return_to_idle_state()

    def stop_speaking(self):
        """Stops all ongoing AI activity (generation and speech)."""
        self.stop_all_ai_activity()

    def stop_generation(self):
        """Stops all ongoing AI activity (generation and speech)."""
        self.stop_all_ai_activity()

    # IN app_controller.py, REPLACE the existing speak_response method with this one.

    # In app_controller.py, REPLACE the existing speak_response method with this one.

    # In app_controller.py, REPLACE the existing speak_response method.

    def speak_response(self, text, on_done=None, priority='normal'):
        """Sends a speech request to the TTS engine with robust state management."""
        if not text or not str(text).strip() or self.is_tts_reinitializing:
            if on_done: self.root.after(0, on_done)
            return

        text_to_speak = str(text)

        if priority == 'high':
            if self.tts_engine: self.tts_engine.stop()
            self.root.after(0, self.gui.add_chat_message, "AURA", text_to_speak)

        self.speaking_active = True
        self.root.after(0, self.gui.update_action_button, "speaking")
        self.root.after(0, self.gui.update_status, "Speaking...")

        def on_speak_done_wrapper():
            """
            This callback runs when the TTS engine finishes. It prioritizes a specific
            'on_done' action over the default 'return_to_idle_state' action.
            """
            if self.tts_engine and not self.tts_engine.is_busy():
                if on_done:
                    self.root.after(0, on_done)
                else:
                    self.return_to_idle_state()

        self.tts_engine.speak(text_to_speak, on_speak_done_wrapper)

    def get_timestamp(self):
        """Returns the current time as a formatted string."""
        return datetime.now().strftime("%H:%M:%S")

    def play_sound(self, sound_name):
        """Plays a sound effect from the sounds directory."""
        sound_path = self.config.get("sounds", {}).get(sound_name)
        if sound_path and os.path.exists(sound_path):
            threading.Thread(target=playsound, args=(sound_path,), daemon=True).start()


    # In app_controller.py, REPLACE the existing start_listening method with this one.

    def start_listening(self, triggered_by="unknown"):
        """Starts the STT engine to listen for a command."""
        if self.is_listening: return
        self.stop_all_ai_activity() 
        
        def _task():
            if self.stt_engine: self.stt_engine.stop_wake_word_listener()
            
            # FIX: Use the on_done callback to reliably trigger listening AFTER
            # AURA finishes speaking her prompt. This prevents the mic from
            # listening to itself.
            if triggered_by == "wakeword":
                self.speak_response(
                    random.choice(["Yes?", "I'm listening.", "Go ahead."]),
                    on_done=self._start_listening_delayed
                )
            else:
                self.play_sound("activation")
                if self.is_running:
                    self.root.after(200, self._start_listening_delayed)

        threading.Thread(target=_task, daemon=True).start()

    def _start_listening_delayed(self):
        """The part of starting to listen that must run on the main thread."""
        self.is_listening = True
        if self.gui: self.gui.update_status("Listening...", is_listening=True)
        if self.stt_engine: self.stt_engine.start_listening(self.process_speech_input, lambda: web.is_online(self.queue_log))

    def stop_listening(self):
        """Stops the STT engine from listening but does NOT restart the wake word listener."""
        self.is_listening = False
        if self.stt_engine: self.stt_engine.stop_listening()
        if self.gui: self.gui.update_status("Ready", is_listening=False)

    def process_speech_input(self, text):
        """Processes the transcribed text from the STT engine."""
        self.play_sound("deactivation")
        if self.gui:
            self.gui.add_chat_message("You", text)
            # --- FIX START ---
            # This call now correctly sets the user's command in the mini GUI
            self.gui.add_transcript_line(text, is_aura=False)
            # --- FIX END ---
        self.execute_command(text)

    def save_settings(self):
        """Saves the current GUI settings to config.json."""
        try:
            self._old_config = self.config.copy()
            self.config = self.gui.get_settings()
            with open("config.json", 'w') as f:
                json.dump(self.config, f, indent=4)
            self.manage_background_services_on_save()
            messagebox.showinfo("Success", "Settings saved. Some changes may require a restart.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def manage_background_services_on_save(self):
        """Starts/stops background services based on config changes."""
        new_config = self.config
        old_config = self._old_config
        
        if new_config.get("file_system_watcher", {}) != old_config.get("file_system_watcher", {}):
            self.stop_file_watcher()
            if new_config.get("file_system_watcher", {}).get("enabled"):
                self.start_file_watcher()

        if new_config.get("clipboard_manager", {}).get("enabled") != old_config.get("clipboard_manager", {}).get("enabled"):
            if new_config.get("clipboard_manager", {}).get("enabled"):
                self.start_clipboard_manager()
            else:
                self.stop_clipboard_manager()

        if new_config.get("hotkeys", []) != old_config.get("hotkeys", []):
            self.stop_hotkey_listener()
            self.start_hotkey_listener()
        
        if new_config.get("tts", {}).get("speaker_wav_path") != old_config.get("tts", {}).get("speaker_wav_path"):
            threading.Thread(target=self._reinitialize_tts_worker, daemon=True).start()
        
        if new_config.get("audio") != old_config.get("audio"):
            threading.Thread(target=self.reinitialize_audio_engines, daemon=True).start()

    @property
    def hotkey_actions(self):
        """Maps hotkey action names to their corresponding functions."""
        return {"Start Listening": self.start_listening, "Stop Speaking": self.stop_speaking}
        
    def start_hotkey_listener(self):
        """Starts the global hotkey listener."""
        self.stop_hotkey_listener()

        hotkey_config = self.config.get("hotkeys", [])
        if not hotkey_config: return

        try:
            hotkey_map = {
                item.get("combination").lower(): self.hotkey_actions.get(item.get("action"))
                for item in hotkey_config if item.get("combination") and item.get("action") in self.hotkey_actions
            }

            if not hotkey_map: return

            self.global_hotkey_listener = keyboard.GlobalHotKeys(hotkey_map)
            self.global_hotkey_listener.start()
            self.queue_log(f"Global hotkeys active: {list(hotkey_map.keys())}")
        except Exception as e:
            self.queue_log(f"Failed to start hotkey listener: {e}\n{traceback.format_exc()}", "ERROR")

    def stop_hotkey_listener(self):
        """Stops the global hotkey listener."""
        if self.global_hotkey_listener:
            try:
                self.global_hotkey_listener.stop()
            except Exception:
                pass
            self.global_hotkey_listener = None
            self.queue_log("Global hotkey listener stopped.")


    def update_ai_monitor(self, text):
        """Updates the diagnostic text widget in the Logs view."""
        if hasattr(self.gui, 'ai_response_monitor_text'):
            widget = self.gui.ai_response_monitor_text
            widget.config(state='normal')
            widget.delete('1.0', tk.END)
            widget.insert('1.0', text)
            widget.config(state='disabled')

    def _reinitialize_tts_worker(self):
        """Worker thread to re-initialize the TTS engine with a new voice."""
        self.is_tts_reinitializing = True
        if self.gui: self.root.after(0, self.gui.update_status, "Loading new voice...")
        if self.tts_engine: self.tts_engine.shutdown()
        
        self.tts_engine = CoquiTTS(self, self.root, self.config, self.queue_log)
        
        self.is_tts_reinitializing = False
        if self.gui: self.root.after(0, self.gui.update_status, "Ready")

    def _get_audio_devices(self):
        """Refreshes the list of available audio devices."""
        self.input_devices.clear(); self.output_devices.clear(); self.loopback_devices.clear()
        try:
            for i, device in enumerate(sd.query_devices()):
                if device['max_input_channels'] > 0:
                    self.input_devices.append({'name': device['name'], 'index': i})
                if device['max_output_channels'] > 0:
                    self.output_devices.append({'name': device['name'], 'index': i})
                if "loopback" in device['name'].lower() or "stereo mix" in device['name'].lower() or "what u hear" in device['name'].lower():
                    if device['max_input_channels'] > 0:
                        self.loopback_devices.append({'name': device['name'], 'index': i})
        except Exception as e:
            self.queue_log(f"Error detecting audio devices: {e}", 'ERROR')

    def toggle_mic_test(self):
        """Starts or stops the microphone test."""
        self.is_mic_testing = not self.is_mic_testing
        if self.is_mic_testing:
            if self.stt_engine:
                self.stt_engine.start_volume_visualizer(lambda l: self.gui.update_mic_level(l) if self.is_mic_testing else None)
            if self.gui: self.gui.mic_test_button.config(text="Stop Mic Test")
        else:
            if self.stt_engine: self.stt_engine.stop_listening()
            if self.gui:
                self.gui.mic_test_button.config(text="Start Mic Test")
                self.gui.update_mic_level(0.0)

    def reinitialize_audio_engines(self):
        """Re-initializes all audio components after settings change."""
        self.queue_log("Re-initializing audio engines...")
        self.stop_listening(); self.stop_speaking()
        time.sleep(0.5)
        
        self._get_audio_devices()
        
        if self.tts_engine: self.tts_engine.shutdown()
        if self.stt_engine: self.stt_engine.stop_listening()
        
        self.tts_engine = CoquiTTS(self, self.root, self.config, self.queue_log)
        self.stt_engine = SpeechToText(self, self.command_handler, self.tts_engine, self.config, self.queue_log)
        
        if self.gui: self.gui.load_settings_to_gui()
        if self.stt_engine: self.stt_engine.start_wake_word_listener()
        self.queue_log("Audio engines re-initialized.")
        
    def start_file_watcher(self):
        """Starts the file system watcher."""
        if self.fs_observer and self.fs_observer.is_alive(): return
        config = self.config.get("file_system_watcher", {})
        path = config.get("path")
        if not path or not os.path.isdir(path):
            self.queue_log(f"File watcher path is invalid or not set: '{path}'", "WARNING")
            return
        
        event_handler = self.FileCreationHandler(self)
        self.fs_observer = Observer()
        self.fs_observer.schedule(event_handler, path, recursive=False)
        self.fs_observer.start()
        self.queue_log(f"File watcher started on: {path}")

    def stop_file_watcher(self):
        """Stops the file system watcher."""
        if self.fs_observer and self.fs_observer.is_alive():
            self.fs_observer.stop()
            self.fs_observer.join(timeout=1)
        self.fs_observer = None
        self.queue_log("File watcher stopped.")

    def start_clipboard_manager(self):
        """Starts the clipboard monitor."""
        if self.clipboard_thread and self.clipboard_thread.is_alive(): return
        self.is_clipboard_manager_running.clear()
        self.clipboard_thread = threading.Thread(target=self._clipboard_monitor_loop, daemon=True)
        self.clipboard_thread.start()

    def stop_clipboard_manager(self):
        """Stops the clipboard monitor."""
        self.is_clipboard_manager_running.set()
        if self.clipboard_thread and self.clipboard_thread.is_alive():
            self.clipboard_thread.join(timeout=2)
        self.clipboard_history.clear()
        self.queue_log("Clipboard manager stopped.")

    def _clipboard_monitor_loop(self):
        """Worker thread to monitor clipboard changes."""
        pythoncom.CoInitialize()
        self.queue_log("Clipboard manager started.")
        while not self.is_clipboard_manager_running.is_set():
            try:
                current_content = pyperclip.paste()
                if current_content and current_content != self.last_clipboard_content:
                    self.last_clipboard_content = current_content
                    self.clipboard_history.insert(0, current_content)
                    self.clipboard_history = self.clipboard_history[:20]
            except pyperclip.PyperclipException:
                pass
            except Exception as e:
                self.queue_log(f"Clipboard monitor error: {e}", "ERROR")
            time.sleep(1.5)
        pythoncom.CoUninitialize()

    class FileCreationHandler(FileSystemEventHandler):
        """Event handler for the file system watcher."""
        def __init__(self, app_controller):
            self.app = app_controller
        def on_created(self, event):
            if not event.is_directory:
                self.app.root.after(0, self.app.speak_response, f"New file detected: {os.path.basename(event.src_path)}")
