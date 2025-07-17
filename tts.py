# tts.py

import os
import torch
import sounddevice as sd
import threading
import traceback
import numpy as np
import pythoncom
import queue
from TTS.api import TTS

# FIX: Import all necessary classes to resolve the PyTorch loading error.
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
from TTS.config.shared_configs import BaseDatasetConfig
import torch.serialization

class CoquiTTS:
    def __init__(self, app_controller, root, config, log_callback):
        self.app = app_controller
        self.root = root
        self.log = log_callback
        self.config = config
        self.animation_queue = app_controller.animation_data_queue
        self.model = None
        self.stream = None
        self.stop_event = threading.Event()

        self.text_queue = queue.Queue()
        self.audio_data_queue = queue.Queue()
        
        # --- FIX: Add a flag to track active playback ---
        self.is_playing = False

        self.initialize_model()

        self.processor_thread = threading.Thread(target=self._processor_worker, daemon=True)
        self.player_thread = threading.Thread(target=self._player_worker, daemon=True)
        self.processor_thread.start()
        self.player_thread.start()


    def initialize_model(self):
        """Initializes the Coqui TTS model."""
        try:
            torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.log(f"Initializing Coqui TTS on device: {device}")
            self.model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
            self.log("Coqui TTS model loaded successfully.")
        except Exception as e:
            self.log(f"FATAL: Could not initialize Coqui TTS. Error: {e}\n{traceback.format_exc()}", "ERROR")

    def speak(self, text, on_done_callback=None):
        """Adds text to the processing queue. This is non-blocking."""
        if not self.model or not text:
            if on_done_callback:
                self.root.after(0, on_done_callback)
            return
        self.stop_event.clear()
        self.text_queue.put((text, on_done_callback))

    def _processor_worker(self):
        """Processes text, generates audio, and sends animation data."""
        pythoncom.CoInitialize()
        while True:
            try:
                text, on_done_callback = self.text_queue.get()
                if text is None: break

                if self.stop_event.is_set():
                    if on_done_callback: self.root.after(0, on_done_callback)
                    continue
                
                text_to_synthesize = text.replace('*', '').replace('#', '').strip()
                if not text_to_synthesize:
                    if on_done_callback: self.root.after(0, on_done_callback)
                    continue

                speaker_wav_path = self.config.get("tts", {}).get("speaker_wav_path", "voices/default_voice.wav")
                sentences = self.model.synthesizer.split_into_sentences(text_to_synthesize)
                
                for i, sentence in enumerate(sentences):
                    if self.stop_event.is_set(): break
                    
                    chunk = sentence.strip()
                    if not chunk: continue

                    self.log(f"TTS Processor starting for: '{chunk[:50]}...'")
                    wav = self.model.tts(text=chunk, speaker_wav=speaker_wav_path, language="en")
                    
                    if wav and not self.stop_event.is_set():
                        # --- FIX: Calculate duration and create animation packet ---
                        samplerate = self.model.synthesizer.output_sample_rate
                        duration = len(wav) / samplerate
                        
                        animation_packet = {
                            "text": chunk,
                            "duration": duration,
                            "is_first": (i == 0) # Flag the first sentence of a response
                        }
                        self.animation_queue.put(animation_packet)
                        # --- END FIX ---
                        
                        # Put audio on the player queue as before
                        audio_packet = {"wav": np.array(wav, dtype=np.float32)}
                        self.audio_data_queue.put(audio_packet)

                if not self.stop_event.is_set() and on_done_callback:
                    self.audio_data_queue.put({"on_done": on_done_callback})

            except Exception as e:
                self.log(f"Error in TTS processor thread: {e}\n{traceback.format_exc()}", "ERROR")
        pythoncom.CoUninitialize()

    def _player_worker(self):
        """Plays audio from the audio_data_queue sequentially."""
        pythoncom.CoInitialize()
        samplerate = self.model.synthesizer.output_sample_rate if self.model else 24000
        while True:
            try:
                packet = self.audio_data_queue.get()
                if packet is None: break

                on_done_callback = packet.get("on_done")
                if on_done_callback:
                    self.root.after(0, on_done_callback)
                    continue
                
                wav_data = packet.get("wav")
                if wav_data is not None and not self.stop_event.is_set():
                    # --- FIX: Set playing state before and after playback ---
                    self.is_playing = True
                    sd.play(wav_data, samplerate)
                    sd.wait() # This is now safe because our state tracking is correct
                    self.is_playing = False

            except Exception as e:
                self.log(f"Error in TTS player thread: {e}\n{traceback.format_exc()}", "ERROR")
                self.is_playing = False # Ensure flag is reset on error
        pythoncom.CoUninitialize()

    def stop(self):
        """Stops playback and clears all queues."""
        self.log("Stop speech requested. Clearing queues.")
        self.stop_event.set()
        
        # --- FIX: Clear queues first to prevent any new items from playing ---
        while not self.text_queue.empty():
            try: self.text_queue.get_nowait()
            except queue.Empty: break
        while not self.audio_data_queue.empty():
            try: self.audio_data_queue.get_nowait()
            except queue.Empty: break

        # --- FIX: Stop sounddevice playback and reset state flag ---
        sd.stop()
        self.is_playing = False
    
    def is_busy(self):
        """Checks if the TTS system is currently processing, has pending work, or is playing audio."""
        # --- FIX: The check now includes the self.is_playing flag ---
        return self.is_playing or not self.text_queue.empty() or not self.audio_data_queue.empty()

    def shutdown(self):
        """Shuts down the TTS engine and its threads."""
        self.stop()
        self.text_queue.put((None, None))
        self.audio_data_queue.put(None)
        self.model = None
        self.log("Coqui TTS engine shut down.")