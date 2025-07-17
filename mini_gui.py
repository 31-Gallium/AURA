# mini_gui.py
import tkinter as tk
from tkinter import ttk
import random
import textwrap
import time
import queue

class MiniWindow:
    def __init__(self, app_controller, main_gui):
        self.app = app_controller
        self.gui = main_gui
        self.root = self.app.root
        self.is_visible = False
        self._offset_x, self._offset_y = 0, 0
        self.num_bars, self.bar_heights, self.last_level = 8, [1] * 8, 0.0

        # State variables for time-based animation
        self.base_transcript_text = ""
        self.current_anim_text = ""
        self.current_anim_duration = 0
        self.animation_start_time = 0
        self.is_animating_text = False
        self.animation_job = None
        
        # --- FIX: Internal queue to enforce sentence order ---
        self.sentence_queue = queue.Queue()

        self.window = tk.Toplevel(self.root)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        self.window.geometry("270x294+100+100")
        self.window.configure(bg=self.gui.COLOR_CONTENT_BOX)

        try:
            from ctypes import windll, c_int, byref
            self.window.update_idletasks()
            hwnd = windll.user32.GetParent(self.window.winfo_id())
            windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, byref(c_int(2)), 4)
        except Exception:
            pass

        self.window.bind("<ButtonPress-1>", self._on_press)
        self.window.bind("<B1-Motion>", self._on_drag)
        self._create_widgets()
        self.window.withdraw()

    def _create_widgets(self):
        maximize_btn = ttk.Button(self.window, text="🔳", style="Control.TButton", width=2, command=self.gui.restore_from_mini_mode)
        maximize_btn.pack(side='top', anchor='ne', pady=5, padx=5)
        self.visualizer_canvas = tk.Canvas(self.window, height=50, bg=self.gui.COLOR_CONTENT_BOX, highlightthickness=0)
        self.visualizer_canvas.pack(fill='x', pady=5, padx=10)
        self.transcript_canvas = tk.Canvas(self.window, height=80, bg=self.gui.COLOR_CONTENT_BOX, highlightthickness=0)
        self.transcript_canvas.pack(fill='x', expand=True, padx=15)
        button_frame = ttk.Frame(self.window, style="ContentBox.TFrame")
        button_frame.pack(side='bottom', fill='x', pady=10, padx=10)
        button_frame.columnconfigure((0, 1), weight=1)
        listen_btn = ttk.Button(button_frame, text="Listen", style="Control.TButton", command=lambda: self.app.start_listening("button"))
        listen_btn.grid(row=0, column=0, sticky='ew', padx=5)
        stop_speech_btn = ttk.Button(button_frame, text="Stop", style="Control.TButton", command=self.app.stop_all_ai_activity)
        stop_speech_btn.grid(row=0, column=1, sticky='ew', padx=5)

    def add_transcript_line(self, text, is_aura=False):
        self.stop_animation()
        if is_aura:
            self.base_transcript_text = "AURA: " + text
        else:
            self.base_transcript_text = "You: " + text
        self.current_anim_text = ""
        self._draw_transcript_text()

    def prepare_for_aura_response(self):
        """Prepares the transcript area for any new response from AURA."""
        self.stop_animation()
        if "You:" in self.base_transcript_text:
            self.base_transcript_text += "\nAURA:"
        else:
            self.base_transcript_text = "AURA:"
        
        if not self.animation_job:
            self._animation_loop()

    def animate_new_sentence(self, data_packet):
        """Adds a new sentence packet to the internal queue to guarantee order."""
        self.sentence_queue.put(data_packet)

    def _update_typewriter(self):
        # If we are not currently animating a sentence, check if there's a new one in the queue.
        if not self.is_animating_text and not self.sentence_queue.empty():
            try:
                # --- FIX: Get the next sentence from the internal FIFO queue ---
                next_packet = self.sentence_queue.get_nowait()
                
                # Add a space between sentences for readability.
                self.base_transcript_text += " "
                
                self.current_anim_text = next_packet["text"]
                self.current_anim_duration = max(0.1, next_packet.get("duration", 0.0))
                self.animation_start_time = time.time() + 0.15
                self.is_animating_text = True
            except queue.Empty:
                pass # This is fine, another thread might have grabbed it.

        if not self.is_animating_text:
            return # Nothing to do if we're not animating.

        # The rest of the animation logic remains the same
        elapsed = time.time() - self.animation_start_time
        progress = min(1.0, elapsed / self.current_anim_duration) if self.current_anim_duration > 0 else 1.0
        
        num_chars_to_show = int(len(self.current_anim_text) * progress)
        visible_sentence = self.current_anim_text[:num_chars_to_show]
        full_text = self.base_transcript_text + visible_sentence
        
        if progress < 1.0:
            full_text += "▋"
        else:
            # When this sentence's animation is done, commit it to the base text
            self.base_transcript_text += self.current_anim_text
            self.current_anim_text = ""
            self.is_animating_text = False

        self._draw_transcript_text(full_text)

    def _draw_transcript_text(self, text_to_display=None):
        self.transcript_canvas.delete("all")
        if text_to_display is None:
            text_to_display = self.base_transcript_text + self.current_anim_text

        canvas_width = self.transcript_canvas.winfo_width() - 10
        if canvas_width < 20: return

        font_obj = self.gui.font_body
        all_lines = []
        for paragraph in text_to_display.split('\n'):
            wrapped_lines = textwrap.wrap(paragraph, width=35, replace_whitespace=False, drop_whitespace=False)
            all_lines.extend(wrapped_lines or [''])

        line_height = font_obj.metrics("linespace")
        if line_height <= 0: return
        
        canvas_height = self.transcript_canvas.winfo_height()
        max_visible_lines = max(1, int(canvas_height / line_height))
        visible_lines = all_lines[-max_visible_lines:]
        
        y_pos = 5
        for line in visible_lines:
            self.transcript_canvas.create_text(5, y_pos, text=line, fill="white", font=font_obj, anchor="nw")
            y_pos += line_height

    def _animation_loop(self):
        if not self.is_visible: return
        self.update_visualizer()
        self._update_typewriter()
        self.animation_job = self.root.after(33, self._animation_loop)

    def stop_animation(self):
        if self.is_animating_text:
            self.base_transcript_text += self.current_anim_text
            self.current_anim_text = ""
        self.is_animating_text = False
        # Clear the queue of any pending sentences
        while not self.sentence_queue.empty():
            try: self.sentence_queue.get_nowait()
            except queue.Empty: pass
            
    # The rest of the visualizer, show, hide, and window drag methods remain unchanged.
    def update_visualizer(self):
        level_to_show = 0.0
        if self.app.speaking_active: level_to_show = random.uniform(0.15, 0.45)
        else:
            level_to_show = self.last_level
            self.last_level *= 0.75
        for i in range(self.num_bars):
            base_height = max(1, level_to_show * 100)
            target_height = base_height * random.uniform(0.7, 1.3)
            self.bar_heights[i] += (target_height - self.bar_heights[i]) * 0.4
        self._draw_visualizer()

    def _draw_visualizer(self):
        self.visualizer_canvas.delete("all")
        canvas_width, canvas_height = self.visualizer_canvas.winfo_width(), self.visualizer_canvas.winfo_height()
        if not canvas_width or not canvas_height: return
        bar_width, gap = 12, 8
        total_width = self.num_bars * bar_width + (self.num_bars - 1) * gap
        start_x = (canvas_width - total_width) / 2
        colors = ["#7df9ff", "#50c878", "#3b1a78", "#e0b0ff", "#5d3fd3", "#00a86b", "#be0032", "#8a2be2"]
        for i, height_val in enumerate(self.bar_heights):
            height = min(height_val, canvas_height - 4)
            x0, x1 = start_x + i * (bar_width + gap), start_x + (i * (bar_width + gap)) + bar_width
            y0, y1 = (canvas_height - height) / 2, (canvas_height + height) / 2
            radius = bar_width / 2
            if height > bar_width:
                self.visualizer_canvas.create_oval(x0, y0, x1, y0 + bar_width, fill=colors[i % len(colors)], outline="")
                self.visualizer_canvas.create_oval(x0, y1 - bar_width, x1, y1, fill=colors[i % len(colors)], outline="")
                self.visualizer_canvas.create_rectangle(x0, y0 + radius, x1, y1 - radius, fill=colors[i % len(colors)], outline="")
            elif height > 0:
                self.visualizer_canvas.create_oval(x0, y0, x1, y1, fill=colors[i % len(colors)], outline="")

    def show(self):
        self.window.deiconify()
        self.is_visible = True
        self.base_transcript_text = "Awaiting command..."
        self._draw_transcript_text()
        if self.animation_job: self.root.after_cancel(self.animation_job)
        self._animation_loop()

    def hide(self):
        self.window.withdraw()
        self.is_visible = False
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        self.stop_animation()

    def _on_press(self, event):
        self._offset_x = event.x
        self._offset_y = event.y

    def _on_drag(self, event):
        x = self.window.winfo_pointerx() - self._offset_x
        y = self.window.winfo_pointery() - self.window.winfo_y()
        self.window.geometry(f"+{x}+{y}")