# In stt.py

import os
import numpy as np
import sounddevice as sd
import queue
import threading
import time
import speech_recognition as sr
from faster_whisper import WhisperModel
import torch
import traceback
import resampy

class SpeechToText:
    def __init__(self, app_controller, config, log_callback):
        self.app = app_controller
        self.root = self.app.root
        self.config = config
        self.log = log_callback
        self.stream = None
        
        audio_config = self.config.get("audio", {})
        self.device_index = audio_config.get("input_device_index")
        self.loopback_device_index = audio_config.get("loopback_device_index")
        self.stt_engine_preference = audio_config.get("stt_engine", "google_online")
        
        self.log("Initializing STT Engine...")
        self.whisper_model = self._initialize_whisper()
        
        self.google_recognizer = sr.Recognizer()
        try:
            if self.device_index is not None:
                with sr.Microphone(device_index=self.device_index) as source:
                    self.log(f"Adjusting for ambient noise on device index {self.device_index}...")
                    self.google_recognizer.adjust_for_ambient_noise(source, duration=1)
                    self.log("Ambient noise adjustment complete.")
            else:
                self.log("No input device selected; skipping ambient noise adjustment.")
        except Exception as e:
            self.log(f"Could not access microphone for noise adjustment: {e}")

    def _initialize_whisper(self):
        try:
            whisper_path = self.config.get("whisper_model_path")
            if not whisper_path or not os.path.exists(whisper_path): return None
            try:
                if torch.cuda.is_available():
                    device = "cuda"
                    compute_type = "float16"
                    self.log("CUDA device found. Whisper will run on GPU with float16.")
                else:
                    raise RuntimeError("No CUDA device found")
            except Exception:
                device = "cpu"
                compute_type = "int8"
                self.log("Whisper will run on CPU with int8.")
            
            model = WhisperModel(whisper_path, device=device, compute_type=compute_type)
            self.log("Whisper STT model loaded successfully.")
            return model
        except Exception as e:
            self.log(f"Could not load Whisper model: {e}"); return None

    # --- MODIFIED: Function signature now accepts a session_id ---
    def start_live_transcription(self, session_id, on_transcription_callback, on_volume_update_callback):
        if self.loopback_device_index is None:
            self.log("ERROR: Cannot start meeting mode. No loopback device is selected in settings.")
            self.app.speak_response("I can't start meeting mode because no meeting audio source is selected in the settings.")
            self.root.after(0, self.app.stop_meeting_session, session_id)
            return

        if not self.whisper_model:
            self.log("Cannot start meeting transcription: Whisper model not loaded.")
            self.app.stop_meeting_session(session_id)
            return
        
        self.log(f"Attempting to start live transcription for session {session_id} on device index: {self.loopback_device_index}")
        audio_queue = queue.Queue()

        try:
            # Step 1: Query the device for its native (default) settings
            device_info = sd.query_devices(self.loopback_device_index)
            native_samplerate = int(device_info['default_samplerate'])
            native_channels = int(device_info['max_input_channels'])
            self.log(f"Device '{device_info['name']}' selected. Native settings: {native_samplerate} Hz, {native_channels} channels.")
            
            # This callback will run on a high-priority thread.
            def audio_callback(indata, frames, time, status):
                if self.app.meeting_sessions.get(session_id, {}).get("status") == "active":
                    # Put the raw audio data onto the queue as is.
                    audio_queue.put(bytes(indata))

            # This thread will do the heavy lifting of converting and transcribing.
            def transcription_thread():
                vad_parameters = dict(min_silence_duration_ms=700)
                target_samplerate = 16000

                while self.app.meeting_sessions.get(session_id, {}).get("status") == "active":
                    try:
                        buffer = bytearray(audio_queue.get(timeout=0.5))
                        while not audio_queue.empty():
                             buffer.extend(audio_queue.get_nowait())
                        
                        # Convert buffer to numpy array
                        audio_np = np.frombuffer(buffer, dtype=np.int16)
                        
                        # Step 2: Convert to float and downmix to mono if necessary
                        # We reshape based on the native channel count
                        if native_channels > 1:
                            audio_np = audio_np.reshape(-1, native_channels)
                            audio_np = audio_np.mean(axis=1) # Average channels to get mono
                        
                        audio_float = audio_np.astype(np.float32) / 32768.0

                        # Step 3: Resample the audio to the 16kHz required by Whisper
                        if native_samplerate != target_samplerate:
                            audio_resampled = resampy.resample(audio_float, native_samplerate, target_samplerate)
                        else:
                            audio_resampled = audio_float
                        
                        # Update volume visualizer with the final audio going to the AI
                        volume_level = np.linalg.norm(audio_resampled) * 10
                        self.root.after(0, on_volume_update_callback, volume_level)

                        # Step 4: Transcribe the correctly formatted audio
                        segments, _ = self.whisper_model.transcribe(
                            audio_resampled, 
                            beam_size=10, language="en", vad_filter=True,
                            vad_parameters=vad_parameters, condition_on_previous_text=False)
                        
                        text = " ".join([seg.text for seg in segments]).strip()
                        
                        if text and self.app.meeting_sessions.get(session_id, {}).get("status") == "active":
                            self.root.after(0, on_transcription_callback, text + " ")
                    except queue.Empty:
                        self.root.after(0, on_volume_update_callback, 0.0)
                        continue
                    except Exception as e:
                        self.log(f"Live transcription error: {e}\n{traceback.format_exc()}")
                
                self.root.after(0, on_volume_update_callback, 0.0)
                self.log("Live transcription thread finished.")

            # Step 1 (cont.): Open the stream using the device's native settings
            self.stream = sd.RawInputStream(
                samplerate=native_samplerate,
                blocksize=8192,
                device=self.loopback_device_index, 
                dtype='int16', 
                channels=native_channels, 
                callback=audio_callback
            )
            self.stream.start()
            self.log(f"Audio stream started successfully with native device settings.")
            threading.Thread(target=transcription_thread, daemon=True).start()

        except Exception as e:
            self.log("="*50)
            self.log("FATAL: FAILED TO START AUDIO STREAM FOR LIVE TRANSCRIPTION.")
            self.log(f"DEVICE INDEX: {self.loopback_device_index}")
            self.log(f"ERROR: {e}")
            self.log(traceback.format_exc())
            self.log("="*50)
            self.app.speak_response("I'm sorry, I couldn't access the selected meeting audio device. Please check the logs for more details.")
            self.root.after(0, self.app.stop_meeting_session, session_id)

    def start_listening(self, on_transcription_callback, is_online_func):
        if self.stt_engine_preference == "google_online" and is_online_func():
            self._listen_with_google(on_transcription_callback)
        elif self.stt_engine_preference == "offline_whisper" and self.whisper_model:
            self._listen_with_whisper(on_transcription_callback)
        else:
            self.log("Could not start listening based on current settings."); self.app.stop_listening()

    def _listen_with_google(self, callback):
        if self.device_index is None:
            self.log("Google STT Error: No input device is selected.")
            self.app.speak_response("I can't listen because no microphone is selected in the settings.")
            self.root.after(0, self.app.stop_listening)
            return

        def recognition_thread():
            try:
                with sr.Microphone(device_index=self.device_index) as source:
                    self.log(f"Listening for phrase via Google SR on device {self.device_index}...")
                    audio = self.google_recognizer.listen(source, phrase_time_limit=7)
                
                if self.app.is_listening:
                    transcription = self.google_recognizer.recognize_google(audio)
                    self.root.after(0, callback, transcription)
            except (sr.UnknownValueError, sr.RequestError) as e:
                self.log(f"Google SR error: {e}")
            finally:
                self.root.after(0, self.app.stop_listening)
        threading.Thread(target=recognition_thread, daemon=True).start()

    def start_volume_visualizer(self, volume_callback):
        if not self.app.is_mic_testing:
            return
        
        if self.device_index is None:
            self.log("Mic Test Error: No input device is selected.")
            self.root.after(0, self.app.toggle_mic_test)
            return

        volume_queue = queue.Queue()

        def audio_callback(indata, frames, time, status):
            if status:
                self.log(f"Audio stream status: {status}")
            volume_norm = np.linalg.norm(indata) * 10
            volume_queue.put(volume_norm)
        
        def gui_update_thread():
            while self.app.is_mic_testing:
                try:
                    rms_val = volume_queue.get(timeout=0.1)
                    self.root.after(0, volume_callback, rms_val)
                except queue.Empty:
                    self.root.after(0, volume_callback, 0.0)
                except Exception as e:
                    self.log(f"Mic test GUI update error: {e}")
            self.root.after(0, volume_callback, 0.0)

        try:
            device_info = sd.query_devices(self.device_index, 'input')
            samplerate = int(device_info['default_samplerate'])
            self.stream = sd.InputStream(
                device=self.device_index, 
                channels=1, 
                samplerate=samplerate, 
                callback=audio_callback,
                blocksize=int(samplerate * 0.05)
            )
            self.stream.start()
            self.log("Starting microphone volume visualizer...")
            threading.Thread(target=gui_update_thread, daemon=True).start()
        except Exception as e:
            self.log(f"Failed to start audio stream for volume test: {e}")
            self.root.after(0, self.app.toggle_mic_test)

    def _listen_with_whisper(self, callback):
        if not self.whisper_model: return
        self.log("Starting offline whisper listener...")
        audio_queue = queue.Queue()
        def audio_callback(indata, frames, time, status): audio_queue.put(bytes(indata))
        def process_thread():
            buffer = bytearray()
            listen_duration = 5
            end_time = time.time() + listen_duration
            while time.time() < end_time:
                if not self.app.is_listening: break
                try: buffer.extend(audio_queue.get(timeout=0.1))
                except queue.Empty: pass
            
            if not self.app.is_listening or not buffer:
                self.root.after(0, self.app.stop_listening)
                return

            try:
                audio_np = np.frombuffer(buffer, dtype=np.int16).astype(np.float32) / 32768.0
                segments, _ = self.whisper_model.transcribe(audio_np, beam_size=5)
                text = " ".join([seg.text for seg in segments]).strip()
                if text: self.root.after(0, callback, text)
            except Exception as e:
                self.log(f"Offline whisper transcription error: {e}")
            finally:
                self.root.after(0, self.app.stop_listening)
        try:
            self.stream = sd.RawInputStream(samplerate=16000, blocksize=4096, dtype='int16', device=self.device_index, channels=1, callback=audio_callback)
            self.stream.start()
            threading.Thread(target=process_thread, daemon=True).start()
        except Exception as e:
            self.log(f"Failed to start audio stream for offline whisper: {e}"); self.app.stop_listening()
        finally:
            if self.root.winfo_exists():
                self.root.after(0, self.app.stop_listening)
        

    def stop_listening(self):
        if self.stream and self.stream.active:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            self.log("STT audio stream stopped.")