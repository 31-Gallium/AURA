# main.py
from app_controller import AURAApp
from multiprocessing import freeze_support
import traceback

if __name__ == "__main__":
    # freeze_support() is necessary for creating executables with multiprocessing
    freeze_support()
    try:
        app = AURAApp()
        app.run()
    except Exception as e:
        # Log any critical error that prevents the app from even starting
        print(f"A critical error occurred during application startup: {e}")
        traceback.print_exc()

