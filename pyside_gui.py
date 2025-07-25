# pyside_gui.py
import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QSizeGrip, QStackedWidget,
                               QLabel)
from PySide6.QtGui import QMouseEvent
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve

class CustomMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(960, 600)
        self.resize(1280, 720)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self._drag_start_position = None

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and event.position().y() < 40:
            self._drag_start_position = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_start_position is not None:
            delta = event.globalPosition().toPoint() - self._drag_start_position
            self.move(self.pos() + delta)
            self._drag_start_position = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_start_position = None

class Sidebar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        self.expanded_width = 250
        self.collapsed_width = 60
        self.setMinimumWidth(self.collapsed_width)
        self.setMaximumWidth(self.collapsed_width)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(15)
        self.chat_button = QPushButton("💬 Chat")
        self.meetings_button = QPushButton("👥 Meetings")
        self.logs_button = QPushButton("📜 Logs")
        self.settings_button = QPushButton("⚙️ Settings")
        self.layout.addWidget(self.chat_button)
        self.layout.addWidget(self.meetings_button)
        self.layout.addWidget(self.logs_button)
        self.layout.addStretch()
        self.layout.addWidget(self.settings_button)
        self.animation = QPropertyAnimation(self, b"maximumWidth")
        self.animation.setEasingCurve(QEasingCurve.InOutQuad)
        self.animation.setDuration(300)

    def enterEvent(self, event):
        self.animation.setStartValue(self.width()); self.animation.setEndValue(self.expanded_width); self.animation.start()
    def leaveEvent(self, event):
        self.animation.setStartValue(self.width()); self.animation.setEndValue(self.collapsed_width); self.animation.start()

class GUI:
    def __init__(self, app_controller):
        self.app = app_controller
        self.main_window = CustomMainWindow()
        self._setup_main_layout()

    def _setup_main_layout(self):
        main_container = self.main_window.centralWidget()
        main_container.setAutoFillBackground(True)
        main_layout = QHBoxLayout(main_container)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        self.view_stack = QStackedWidget()
        self.view_stack.setAutoFillBackground(True)
        main_layout.addWidget(self.view_stack)

        main_layout.setStretchFactor(self.sidebar, 0)
        main_layout.setStretchFactor(self.view_stack, 1)

        grip = QSizeGrip(main_container)
        grip_layout = QVBoxLayout()
        grip_layout.setContentsMargins(0,0,0,0)
        grip_layout.addStretch()
        grip_layout.addWidget(grip, 0, Qt.AlignBottom | Qt.AlignRight)
        main_layout.addLayout(grip_layout)

        self._apply_styles()
        self._setup_views()

    def _apply_styles(self):
        """Applies the final, correct styles directly to the widgets."""
        
        # CORRECT LIGHTER GRADIENT for the Sidebar
        sidebar_style = """
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                            stop:0 #3a3a3a, stop:1 #2a2a2a);
                border-right: 1px solid #404040;
            }
            QPushButton {
                color: #e3e3e3; background-color: transparent; border: none;
                text-align: left; padding: 10px; font-size: 14px; font-family: "Segoe UI";
            }
            QPushButton:hover { background-color: #4a4a4a; }
        """
        self.sidebar.setStyleSheet(sidebar_style)

        # CORRECT DARKER GRADIENT for the Content Area
        content_style = """
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                             stop:0 #282828, stop:1 #1e1e1e);
            }
        """
        self.view_stack.setStyleSheet(content_style)

        # The main container should have NO style, allowing the children to draw themselves.
        # This was the problematic line that has been REMOVED:
        # self.main_window.centralWidget().setStyleSheet("background: transparent;")

    def _setup_views(self):
        transparent_label_style = "color: #e3e3e3; background: transparent;"
        chat_view = QWidget()
        chat_view_layout = QVBoxLayout(chat_view)
        chat_view_layout.addWidget(QLabel("Chat View Content Here", alignment=Qt.AlignCenter, styleSheet=transparent_label_style))
        
        meetings_view = QWidget()
        meetings_view_layout = QVBoxLayout(meetings_view)
        meetings_view_layout.addWidget(QLabel("Meetings View Content Here", alignment=Qt.AlignCenter, styleSheet=transparent_label_style))

        logs_view = QWidget()
        logs_view_layout = QVBoxLayout(logs_view)
        logs_view_layout.addWidget(QLabel("Logs View Content Here", alignment=Qt.AlignCenter, styleSheet=transparent_label_style))

        self.view_stack.addWidget(chat_view)
        self.view_stack.addWidget(meetings_view)
        self.view_stack.addWidget(logs_view)
        
        self.sidebar.chat_button.clicked.connect(lambda: self.view_stack.setCurrentIndex(0))
        self.sidebar.meetings_button.clicked.connect(lambda: self.view_stack.setCurrentIndex(1))
        self.sidebar.logs_button.clicked.connect(lambda: self.view_stack.setCurrentIndex(2))

    def show(self):
        self.main_window.show()