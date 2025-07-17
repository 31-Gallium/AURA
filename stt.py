# stt.py
import os
import numpy as np
import sounddevice as sd
import queue
import threading
import speech_recognition as sr
from faster_whisper import WhisperModel
import torch
import traceback
import resampy
import time
from openwakeword.model import Model

class SpeechToText:
    def __init__(self, app_controller, command_handler, tts_instance, config, log_callback):
        self.app = app_controller
        self.root = self.app.root
        self.command_handler = command_handler
        self.tts = tts_instance
        self.config = config
        self.log = log_callback
        self.stream = None
        
        audio_config = self.config.get("audio", {})
        self.device_index = audio_config.get("input_device_index")
        self.loopback_device_index = audio_config.get("loopback_device_index")
        self.stt_engine_preference = audio_config.get("stt_engine", "google_online")

        self.log("Initializing STT Engines...")
        self.whisper_model = self._initialize_whisper()
        self.google_recognizer = self._initialize_google_sr()
        
        self.listening_thread = None
        self.stop_listening_event = threading.Event()
        self.owwModel = None

        self._log_audio_devices()

    def _log_audio_devices(self):
        """Logs all available audio devices for debugging."""
        self.log("--- Available Audio Devices ---")
        try:
            for i, device in enumerate(sd.query_devices()):
                self.log(f"  Device {i}: {device['name']} (In: {device['max_input_channels']}, Out: {device['max_output_channels']})")
        except Exception as e:
            self.log(f"  Error querying audio devices: {e}", "ERROR")
        self.log("-----------------------------")

    def _initialize_google_sr(self):
        """Initializes the Google Speech Recognition engine and adjusts for ambient noise."""
        recognizer = sr.Recognizer()
        try:
            if self.device_index is not None:
                with sr.Microphone(device_index=self.device_index) as source:
                    self.log(f"Adjusting for ambient noise on device index {self.device_index}...")
                    recognizer.adjust_for_ambient_noise(source, duration=1)
                    self.log("Ambient noise adjustment complete.")
            else:
                self.log("No input device selected; skipping ambient noise adjustment.", "WARNING")
        except Exception as e:
            self.log(f"Could not access microphone for noise adjustment: {e}", "ERROR")
        return recognizer

    def _listen_for_wake_word(self):
        """Listens for a wake word using openWakeWord."""
        audio_stream = None
        try:
            self.log("Initializing openWakeWord engine...")
            # This should ideally be a configurable path
            model_path = "wakeword_models/hey_bobh.onnx"
            if not os.path.exists(model_path):
                self.log(f"FATAL: Wake word model not found at '{model_path}'", "ERROR")
                return

            self.owwModel = Model(wakeword_models=[model_path])
            audio_queue = queue.Queue()

            def audio_callback(indata, frames, time, status):
                if status: self.log(f"Wake word audio stream status: {status}", "WARNING")
                audio_queue.put(bytes(indata))

            device_info = sd.query_devices(self.device_index, 'input')
            native_samplerate = int(device_info['default_samplerate'])

            audio_stream = sd.RawInputStream(
                samplerate=native_samplerate, blocksize=1280,
                device=self.device_index, dtype='int16',
                channels=1, callback=audio_callback
            )
            
            self.log("Wake word listener started. Waiting for wake word...")
            with audio_stream:
                while not self.stop_listening_event.is_set():
                    try:
                        audio_chunk = audio_queue.get(timeout=0.2)
                        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)
                        
                        # Resample if necessary
                        if native_samplerate != 16000:
                            audio_float32 = audio_int16.astype(np.float32) / 32768.0
                            audio_resampled = resampy.resample(audio_float32, native_samplerate, 16000)
                            audio_int16 = (audio_resampled * 32767).astype(np.int16)
                        
                        prediction = self.owwModel.predict(audio_int16)
                        score = list(prediction.values())[0]
                        self.root.after(0, self.app.update_wakeword_score, score)
                        
                        if score > 0.05: # Detection threshold
                            self.log("Wake word detected!")
                            if not self.app.is_listening:
                                self.root.after(0, self.app.start_listening, "wakeword")
                                break # Exit loop once detected
                    except queue.Empty:
                        continue
                        
        except Exception as e:
            self.log(f"A critical error occurred with the openWakeWord engine: {e}\n{traceback.format_exc()}", "ERROR")
        finally:
            if audio_stream and not audio_stream.closed:
                audio_stream.stop()
                audio_stream.close()
            self.log("Wake word listener resources released.")

    def start_wake_word_listener(self):
        """Starts the wake word detection in a background thread."""
        if self.listening_thread is None or not self.listening_thread.is_alive():
            self.stop_listening_event.clear()
            self.listening_thread = threading.Thread(target=self._listen_for_wake_word, daemon=True)
            self.listening_thread.start()
            self.log("Background wake word listening thread started.")

    def stop_wake_word_listener(self):
        """Stops the background wake word listening thread."""
        self.stop_listening_event.set()
        self.log("Background wake word listening stopped.")

    def _initialize_whisper(self):
        """Initializes the faster-whisper model."""
        try:
            whisper_path = self.config.get("whisper_model_path")
            if not whisper_path or not os.path.exists(whisper_path):
                self.log("Whisper model path not set or model not found. Whisper STT will be unavailable.", "WARNING")
                return None
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            compute_type = "float16" if device == "cuda" else "int8"
            
            model = WhisperModel(whisper_path, device=device, compute_type=compute_type)
            self.log(f"Whisper STT model loaded successfully on {device} with compute type {compute_type}.")
            return model
        except Exception as e:
            self.log(f"Could not load Whisper model: {e}\n{traceback.format_exc()}", "ERROR")
            return None

    def start_listening(self, on_transcription_callback, is_online_func):
        """Starts listening for a command using the preferred STT engine."""
        if self.stt_engine_preference == "google_online" and is_online_func():
            self._listen_with_google(on_transcription_callback)
        elif self.stt_engine_preference == "offline_whisper" and self.whisper_model:
            self._listen_with_whisper(on_transcription_callback)
        else:
            if not is_online_func(): self.log("Google STT requires an internet connection.", "WARNING")
            if not self.whisper_model: self.log("Whisper model is not available.", "WARNING")
            self.log("Could not start listening based on current settings.", "ERROR")
            self.app.stop_listening()

    def _listen_with_google(self, callback):
        """Listens for a single command using Google Speech Recognition."""
        if self.device_index is None:
            self.log("Google STT Error: No input device is selected.", "ERROR")
            self.app.speak_response("I can't listen because no microphone is selected.")
            self.root.after(0, self.app.stop_listening)
            return

        def recognition_thread():
            try:
                with sr.Microphone(device_index=self.device_index) as source:
                    self.log(f"Listening for command via Google SR on device {self.device_index}...")
                    audio = self.google_recognizer.listen(source, phrase_time_limit=7)
                
                if self.app.is_listening:
                    self.log("Recognizing with Google...")
                    transcription = self.google_recognizer.recognize_google(audio)
                    self.root.after(0, callback, transcription)
            except sr.UnknownValueError:
                self.log("Google SR could not understand audio.", "INFO")
                self.root.after(0, self.app.speak_response, "I didn't catch that.")
            except sr.RequestError as e:
                self.log(f"Google SR request failed: {e}", "ERROR")
                self.root.after(0, self.app.speak_response, "I'm having trouble connecting to the speech service.")
            except Exception as e:
                self.log(f"Google SR error: {e}", "ERROR")
            finally:
                if self.app.is_listening:
                    self.root.after(0, self.app.stop_listening)
        
        threading.Thread(target=recognition_thread, daemon=True).start()

    def _listen_with_whisper(self, callback):
        """Listens for a single command using the offline Whisper model."""
        if not self.whisper_model: return
        self.log("Starting offline whisper listener...")
        audio_queue = queue.Queue()
        
        def audio_callback(indata, frames, time, status): audio_queue.put(bytes(indata))
        
        def process_thread():
            buffer = bytearray()
            end_time = time.time() + 5 # Listen for up to 5 seconds
            
            while time.time() < end_time and self.app.is_listening:
                try:
                    buffer.extend(audio_queue.get(timeout=0.1))
                except queue.Empty:
                    pass
            
            if not self.app.is_listening or not buffer:
                self.root.after(0, self.app.stop_listening)
                return

            try:
                self.log("Recognizing with Whisper...")
                audio_np = np.frombuffer(buffer, dtype=np.int16).astype(np.float32) / 32768.0
                segments, _ = self.whisper_model.transcribe(audio_np, beam_size=5)
                text = " ".join([seg.text for seg in segments]).strip()
                if text:
                    self.root.after(0, callback, text)
                else:
                    self.log("Whisper recognized no speech.")
            except Exception as e:
                self.log(f"Offline whisper transcription error: {e}", "ERROR")
            finally:
                self.root.after(0, self.app.stop_listening)

        try:
            self.stream = sd.RawInputStream(samplerate=16000, blocksize=4096, dtype='int16', device=self.device_index, channels=1, callback=audio_callback)
            self.stream.start()
            threading.Thread(target=process_thread, daemon=True).start()
        except Exception as e:
            self.log(f"Failed to start audio stream for offline whisper: {e}", "ERROR")
            self.app.stop_listening()

    def stop_listening(self):
        """Stops any active audio stream."""
        if self.stream and self.stream.active:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.log("STT audio stream stopped.")

    def start_live_transcription(self, session_id, on_transcription, on_volume_update):
        """Starts live transcription for meeting mode from a loopback device."""
        if self.loopback_device_index is None:
            self.log("ERROR: Cannot start meeting mode. No loopback device selected.", "ERROR")
            self.app.speak_response("I can't start meeting mode. Please select a meeting audio source in settings.")
            self.root.after(0, self.app.stop_meeting_session, session_id)
            return

        if not self.whisper_model:
            self.log("Cannot start meeting transcription: Whisper model not loaded.", "ERROR")
            self.app.stop_meeting_session(session_id)
            return
        
        self.log(f"Starting live transcription on device index: {self.loopback_device_index}")
        audio_queue = queue.Queue()

        try:
            device_info = sd.query_devices(self.loopback_device_index)
            native_samplerate = int(device_info['default_samplerate'])
            native_channels = int(device_info['max_input_channels'])
            
            def audio_callback(indata, frames, time, status):
                if self.app.meeting_sessions.get(session_id, {}).get("status") == "active":
                    audio_queue.put(bytes(indata))

            def transcription_thread():
                while self.app.meeting_sessions.get(session_id, {}).get("status") == "active":
                    try:
                        buffer = bytearray(audio_queue.get(timeout=0.5))
                        while not audio_queue.empty(): buffer.extend(audio_queue.get_nowait())
                        
                        audio_np = np.frombuffer(buffer, dtype=np.int16)
                        if native_channels > 1: audio_np = audio_np.reshape(-1, native_channels).mean(axis=1)
                        
                        audio_float = audio_np.astype(np.float32) / 32768.0
                        audio_resampled = resampy.resample(audio_float, native_samplerate, 16000) if native_samplerate != 16000 else audio_float
                        
                        self.root.after(0, on_volume_update, np.linalg.norm(audio_resampled) * 10)

                        segments, _ = self.whisper_model.transcribe(audio_resampled, beam_size=5, vad_filter=True)
                        text = " ".join([seg.text for seg in segments]).strip()
                        
                        if text: self.root.after(0, on_transcription, text + " ")
                    except queue.Empty:
                        self.root.after(0, on_volume_update, 0.0)
                    except Exception as e:
                        self.log(f"Live transcription error: {e}\n{traceback.format_exc()}", "ERROR")
                
                self.root.after(0, on_volume_update, 0.0)
                self.log("Live transcription thread finished.")

            self.stream = sd.RawInputStream(samplerate=native_samplerate, blocksize=8192, device=self.loopback_device_index, dtype='int16', channels=native_channels, callback=audio_callback)
            self.stream.start()
            threading.Thread(target=transcription_thread, daemon=True).start()

        except Exception as e:
            self.log(f"FATAL: FAILED TO START AUDIO STREAM FOR LIVE TRANSCRIPTION: {e}", "ERROR")
            self.app.speak_response("I'm sorry, I couldn't access the selected meeting audio device.")
            self.root.after(0, self.app.stop_meeting_session, session_id)

    def start_volume_visualizer(self, volume_callback):
        """Starts a stream to visualize microphone input level."""
        if not self.app.is_mic_testing or self.device_index is None: return

        volume_queue = queue.Queue()
        def audio_callback(indata, frames, time, status):
            volume_queue.put(np.linalg.norm(indata) * 10)
        
        def gui_update_thread():
            while self.app.is_mic_testing:
                try:
                    rms_val = volume_queue.get(timeout=0.1)
                    self.root.after(0, volume_callback, rms_val)
                except queue.Empty:
                    self.root.after(0, volume_callback, 0.0)
            self.root.after(0, volume_callback, 0.0)

        try:
            samplerate = int(sd.query_devices(self.device_index, 'input')['default_samplerate'])
            self.stream = sd.InputStream(device=self.device_index, channels=1, samplerate=samplerate, callback=audio_callback)
            self.stream.start()
            self.log("Starting microphone volume visualizer...")
            threading.Thread(target=gui_update_thread, daemon=True).start()
        except Exception as e:
            self.log(f"Failed to start audio stream for volume test: {e}", "ERROR")
            self.root.after(0, self.app.toggle_mic_test)
