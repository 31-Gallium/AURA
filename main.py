# In main.py
import sys
from app_controller import AURAApp

if __name__ == "__main__":
    app = AURAApp()

    # Check if the --startup flag was passed when the script was run
    if "--startup" in sys.argv:
        # If so, call a special method in our controller
        app.run_startup_routine()
    
    # Always run the main GUI loop to show the window
    app.run()