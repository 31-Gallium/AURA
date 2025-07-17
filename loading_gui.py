# test_tts.py
import os
import torch
import sounddevice as sd
import numpy as np
from TTS.api import TTS
# FIX: Import the necessary components to resolve the PyTorch loading error.
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs # <-- FIX: Added the new required class
from TTS.config.shared_configs import BaseDatasetConfig
import torch.serialization

def run_tts_test():
    """
    A simple, self-contained script to test Coqui TTS functionality.
    """
    print("--- Starting TTS Test ---")

    # --- Configuration ---
    # This should be the same model path your main application uses.
    MODEL_PATH = "tts_models/multilingual/multi-dataset/xtts_v2"
    
    # The path to the voice file you want to use for cloning.
    SPEAKER_WAV_PATH = "voices/default_voice.wav" 
    
    # The text you want the model to say.
    TEXT_TO_SPEAK = "Hello, this is a test of the text-to-speech engine. If you can hear this, the core functionality is working."

    # --- 1. Check for Speaker WAV ---
    if not os.path.exists(SPEAKER_WAV_PATH):
        print(f"WARNING: Speaker file not found at '{SPEAKER_WAV_PATH}'. The model will use its default voice.")
        speaker_wav = None
    else:
        print(f"Found speaker file at: {SPEAKER_WAV_PATH}")
        speaker_wav = SPEAKER_WAV_PATH

    # --- 2. Initialize TTS Model ---
    try:
        # FIX: Explicitly mark all required classes as safe for PyTorch to load.
        # This is required for recent versions of PyTorch due to new security policies.
        torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig, BaseDatasetConfig, XttsArgs])

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Initializing TTS model on device: {device}...")
        
        tts = TTS(MODEL_PATH).to(device)
        
        print("TTS model initialized successfully.")
    except Exception as e:
        print(f"\n---!!! FATAL ERROR !!!---")
        print(f"Failed to initialize the TTS model. Please check the model path and your installation.")
        print(f"Error: {e}")
        return

    # --- 3. Generate Audio ---
    try:
        print("\nGenerating audio waveform...")
        
        # Use the tts() method to generate audio from text.
        wav = tts.tts(
            text=TEXT_TO_SPEAK,
            speaker_wav=speaker_wav,
            language="en"
        )
        
        if wav is None:
            print("---!!! ERROR !!!---")
            print("Audio generation failed. The model returned nothing.")
            return

        # The output is a list of audio samples, convert it to a NumPy array for playback.
        audio_data = np.array(wav, dtype=np.float32)
        sample_rate = tts.synthesizer.output_sample_rate
        
        print(f"Audio generated successfully. Sample rate: {sample_rate}, Duration: {len(audio_data)/sample_rate:.2f}s")
    except Exception as e:
        print(f"\n---!!! FATAL ERROR !!!---")
        print(f"Failed to generate audio from the text.")
        print(f"Error: {e}")
        return

    # --- 4. Play Audio ---
    try:
        print("\nAttempting to play audio...")
        
        # Use sounddevice to play the NumPy array.
        sd.play(audio_data, sample_rate)
        
        # Wait for the playback to finish before the script exits.
        sd.wait()
        
        print("\n--- Test Finished ---")
        print("If you heard the audio, the TTS model and your audio output are working correctly.")
        print("The issue is likely within the main application's threading or state management.")
    except Exception as e:
        print(f"\n---!!! FATAL ERROR !!!---")
        print(f"Failed to play the generated audio. This indicates a problem with your audio device setup or the 'sounddevice' library.")
        print(f"Error: {e}")

if __name__ == "__main__":
    run_tts_test()
