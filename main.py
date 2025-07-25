# main.py
import sys
from app_controller import AURAApp
from multiprocessing import freeze_support
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

# This file is now being used for the PySide GUI
from pyside_gui import GUI

if __name__ == "__main__":
    freeze_support()
    try:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
        
        qt_app = QApplication(sys.argv)
        
        aura_app = AURAApp()
        aura_app.qt_app = qt_app
        
        gui = GUI(aura_app)
        aura_app.gui = gui
        
        gui.show()
        sys.exit(qt_app.exec())

    except Exception as e:
        print(f"A critical error occurred during application startup: {e}")
        traceback.print_exc()