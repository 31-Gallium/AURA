# In tts.py

import os
import torch
import sounddevice as sd
import threading
import traceback
import numpy as np
import pythoncom

from TTS.api import TTS

class CoquiTTS:
    def __init__(self, config, log_callback):
        self.log = log_callback
        self.config = config
        self.model = None
        self.playback_lock = threading.Lock()
        self.stop_playback = threading.Event()
        self.speaker_wav_path = self.config.get("tts", {}).get("speaker_wav_path", "voices/default_voice.wav")
        self.initialize_model()

    def initialize_model(self):
        """Initializes the TTS model. Can be called again to reload."""
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            self.log(f"Initializing Coqui TTS on device: {device}")
            self.model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
            self.log("Coqui TTS model loaded successfully.")

            if not os.path.exists(self.speaker_wav_path):
                self.log(f"WARNING: Selected speaker wav file not found at {self.speaker_wav_path}")
                default_path = "voices/default_voice.wav"
                if os.path.exists(default_path):
                    self.speaker_wav_path = default_path
                    self.log(f"Fell back to default voice: {default_path}")
                else:
                    self.log("FATAL: Default voice also not found. TTS may fail.")
                    self.model = None
        except Exception as e:
            self.log(f"FATAL: Could not initialize Coqui TTS: {e}\n{traceback.format_exc()}")
            self.model = None

    def speak(self, text, on_done_callback):
        if not self.model or not text or self.playback_lock.locked():
            if on_done_callback: on_done_callback()
            return

        def audio_worker():
            with self.playback_lock:
                pythoncom.CoInitialize()
                try:
                    self.log(f"Processing TTS for: '{text[:40]}...'")
                    self.stop_playback.clear()
                    
                    sentences = self.model.synthesizer.split_into_sentences(text)
                    for sentence in sentences:
                        if self.stop_playback.is_set(): break
                        if not (chunk := sentence.strip()): continue
                        
                        wav = self.model.tts(
                            text=chunk, speaker_wav=self.speaker_wav_path, language="en"
                        )
                        audio_np = np.array(wav, dtype=np.float32)
                        sample_rate = self.model.synthesizer.output_sample_rate
                        
                        # --- SIMPLIFIED AND FIXED LOGIC ---
                        # This version no longer looks for a selected device and robustly handles
                        # converting mono audio to stereo for your default system device.
                        try:
                            # Query the default output device to check its channels
                            default_device_info = sd.query_devices(kind='output')
                            if audio_np.ndim == 1 and default_device_info['max_output_channels'] >= 2:
                                # If default device is stereo, convert our mono audio to stereo
                                audio_np = np.tile(audio_np.reshape(-1, 1), (1, 2))
                        except Exception as e_ch:
                            self.log(f"Could not perform channel conversion. Playing as is. Error: {e_ch}")

                        duration = len(audio_np) / sample_rate
                        # Always play on the system's default device by not specifying a device
                        sd.play(audio_np, sample_rate)
                        self.stop_playback.wait(timeout=duration)
                    
                except Exception as e:
                    self.log(f"Error during TTS audio generation or playback: {e}")
                finally:
                    self.log("Audio playback finished or stopped.")
                    sd.stop()
                    if on_done_callback: on_done_callback()
                    pythoncom.CoUninitialize()

        threading.Thread(target=audio_worker, daemon=True).start()

    def stop(self):
        """Sets the event flag and stops the audio device immediately."""
        self.log("Stop speech requested.")
        self.stop_playback.set()
        sd.stop()

    def shutdown(self):
        """Cleanly stops any active playback."""
        self.log("Shutting down TTS engine.")
        self.stop()
