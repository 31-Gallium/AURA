# gui.py
import tkinter as tk
from tkinter import ttk, font, scrolledtext, messagebox, filedialog
import os
from datetime import datetime
from pynput import keyboard
from mini_gui import MiniWindow
import queue

class RoundedScrollbar(tk.Canvas):
    """A custom scrollbar that only draws a 'floating' thumb."""
    def __init__(self, parent, command, colors, **kwargs):
        super().__init__(parent, highlightthickness=0, bg=colors['bg'], borderwidth=0, **kwargs)
        self.command = command
        self.config(width=16)

        self.thumb_color = colors['thumb']
        self.thumb_active_color = colors['thumb_active']

        # We only create the thumb. There is no track element.
        self.thumb = self.create_rectangle(0, 0, 0, 0, fill=self.thumb_color, outline="", tags="thumb")

        self.bind("<Configure>", self._on_configure)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        self._drag_y = 0
        self._top = 0.0
        self._bottom = 1.0
        self._is_hovering = False

    def set(self, top, bottom):
        self._top, self._bottom = float(top), float(bottom)
        
        # This logic shows the scrollbar only when the content is larger than the view
        if self._bottom - self._top < 1.0:
            # Using pack() is now safe and will make the scrollbar visible
            self.pack(side="right", fill="y", padx=(0, 2))
        else:
            self.pack_forget()
            
        self._redraw()

    def _redraw(self):
        canvas_height = self.winfo_height()
        canvas_width = self.winfo_width()

        thumb_x1 = 3
        thumb_x2 = canvas_width - 3
        thumb_y1 = max(2, int(canvas_height * self._top))
        thumb_y2 = min(canvas_height - 2, int(canvas_height * self._bottom))

        self.coords(self.thumb, thumb_x1, thumb_y1, thumb_x2, thumb_y2)

    def _on_configure(self, event):
        self._redraw()

    def _on_press(self, event):
        tags = self.gettags("current")
        if "thumb" in tags:
            self._drag_y = event.y - (self.winfo_height() * self._top)
        else: # Clicked on the empty canvas, treat as a track click
            self.command("moveto", event.y / self.winfo_height())

    def _on_release(self, event):
        self._drag_y = 0

    def _on_drag(self, event):
        if self._drag_y and self.winfo_height() > 10:
            new_top_fraction = (event.y - self._drag_y) / self.winfo_height()
            self.command("moveto", new_top_fraction)

    def _on_enter(self, event):
        self._is_hovering = True
        self.itemconfig(self.thumb, fill=self.thumb_active_color)

    def _on_leave(self, event):
        self._is_hovering = False
        self.itemconfig(self.thumb, fill=self.thumb_color)

class AutoWrappingText(tk.Text):
    """A custom Text widget that automatically adjusts its height and can animate text."""
    def __init__(self, parent, **kwargs):
        # We need a reference to the root window to schedule the animation
        self.root = parent.winfo_toplevel()
        # A queue to receive characters from the AI thread
        self.char_queue = queue.Queue()
        super().__init__(parent, **kwargs)
        self.config(wrap=tk.WORD, relief="flat", borderwidth=0, highlightthickness=0, state="disabled")
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event=None):
        self._update_height()

    def _update_height(self):
        self.config(state="normal")
        try:
            height = int(self.tk.call((self, "count", "-displaylines", "1.0", "end")))
        except tk.TclError:
            height = 1
        height = max(1, height)
        self.config(height=height)
        self.config(state="disabled")

    def set_text(self, text):
        self.config(state="normal")
        self.delete("1.0", tk.END)
        self.insert("1.0", text)
        self.config(state="disabled")

    def start_typewriter_animation(self):
        """Kicks off the animation loop to display text from the queue."""
        # The delay is calculated from our target of 91 characters per second.
        # 1000ms / 91cps = ~11ms delay per character.
        delay_ms = int(1000 / 91)
        self._typewriter_loop(delay_ms)

    def _typewriter_loop(self, delay_ms):
        """The main animation loop that displays one character at a time."""
        try:
            # Get a character from the queue without blocking
            char = self.char_queue.get_nowait()

            if char is None: # A 'None' value is our signal that the stream is finished
                self._update_height() # Perform one final height update
                return

            self.config(state="normal")
            self.insert(tk.END, char)
            self.config(state="disabled")

            # --- THE FIX ---
            # Check if a word wrap might have occurred (after a space or newline)
            # and update the widget's height accordingly. This makes the bubble
            # grow during the animation.
            if char in [' ', '\n']:
                self._update_height()
            # --- END FIX ---

            # As text is added, automatically scroll to the bottom
            if hasattr(self.root, 'gui_instance'):
                 self.root.gui_instance.chat_canvas.yview_moveto(1.0)

        except queue.Empty:
            # If the queue is empty, just wait and check again later.
            pass
        finally:
            # Reschedule the next loop
            self.root.after(delay_ms, lambda: self._typewriter_loop(delay_ms))

class GUI:
    def __init__(self, app_controller):
        self.app = app_controller
        self.root = self.app.root
        self.root.gui_instance = self
        
        self.sidebar_animation_job = None
        self.settings_animation_job = None
        self.input_animation_job = None
        self.scrolling_job = None
        self.scrolling_widget = None
        self.last_message_added = None
        self._summary_buffer = ""
        self.scroll_animation_job = None
        self.scroll_velocity = 0.0

        self.FONT_FAMILY = "Segoe UI"
        self.COLOR_BG = "#131314"
        self.COLOR_SIDEBAR = "#1e1f20"
        self.COLOR_CONTENT_BOX = "#202124"
        self.COLOR_INPUT_BG = "#1e1f20"
        self.COLOR_FG = "#e3e3e3"
        self.COLOR_FG_MUTED = "#969696"
        self.COLOR_ACCENT = "#8ab4f8"
        self.COLOR_ACTIVE = "#52D171"
        self.COLOR_MUTED = "#F79F1F"
        self.SIDEBAR_WIDTH_COLLAPSED = 60
        self.SIDEBAR_WIDTH_EXPANDED = 250
        self.INPUT_TEXT_MAX_LINES = 7

        self.fs_watcher_enabled_var = tk.BooleanVar()
        self.clipboard_history_enabled_var = tk.BooleanVar()
        self.minimize_to_overlay_var = tk.BooleanVar(value=False)
        self.skill_toggle_vars = {}
        self.attached_file_path = tk.StringVar()
        self.selected_routine_name = tk.StringVar()
        self.input_device_var = tk.StringVar()
        self.loopback_device_var = tk.StringVar()
        self.mic_test_result_var = tk.StringVar()
        self.ai_engine_var = tk.StringVar()
        self.mic_level_var = tk.DoubleVar(value=0.0)
        self.meeting_volume_var = tk.DoubleVar(value=0.0)
        self.wakeword_score_var = tk.DoubleVar(value=0.0)
        self.chat_ai_engine_var = tk.StringVar()
        self.stt_engine_var = tk.StringVar()
        self.continuous_listening_var = tk.BooleanVar()
        self.voice_selection_var = tk.StringVar()

        self.hotkey_rows = []
        self.app_path_rows = []
        self.routine_rows = {}
        self.action_rows = []
        self.meeting_session_widgets = {}
        self.mini_window = None
        self.inner_input_frame = None

        self.font_title = font.Font(family=self.FONT_FAMILY, size=13, weight="bold")
        self.font_body = font.Font(family=self.FONT_FAMILY, size=11)
        self.font_italic = font.Font(family=self.FONT_FAMILY, size=11, slant="italic")
        self.font_sidebar_button = font.Font(family=self.FONT_FAMILY, size=11)

        self.input_animation_job = None
        self.active_view_name = "chat"
        self.last_root_width = 0
        self.last_root_height = 0

        self._apply_theme()
        self.create_widgets()

    def _draw_rounded_rect(self, canvas, x1, y1, x2, y2, radius, **kwargs):
        """Draws a rounded rectangle on a canvas."""
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return canvas.create_polygon(points, **kwargs)
        
    def _on_mousewheel(self, event):
        # --- THE FIX ---
        # The previous value (0.05) was too high, causing large jumps.
        # A smaller value makes the scrolling much finer and smoother.
        scroll_speed_fraction = 0.0031
        # --- END FIX ---
        
        # Normalize the scroll delta (usually 120 per tick on Windows)
        normalized_delta = event.delta / 120.0
        
        # Add to the velocity, inverting the sign for natural scrolling direction
        self.scroll_velocity += -1 * normalized_delta * scroll_speed_fraction

        # Clamp the velocity to prevent excessively large jumps from fast scrolls
        self.scroll_velocity = max(-1.0, min(1.0, self.scroll_velocity))

        # If the animation isn't already running, start it
        if not self.scroll_animation_job:
            self._perform_scroll_step()

        # Stop the event from propagating to default handlers
        return "break"

    def _perform_scroll_step(self):
        # If velocity is almost zero, stop the animation completely.
        if abs(self.scroll_velocity) < 0.001:
            self.scroll_velocity = 0
            self.scroll_animation_job = None
            return

        current_top, current_bottom = self.chat_canvas.yview()

        # If we hit the top or bottom edge, cancel the animation.
        if (current_top <= 0.0 and self.scroll_velocity < 0) or \
           (current_bottom >= 1.0 and self.scroll_velocity > 0):
            self.scroll_velocity = 0
            self.scroll_animation_job = None
            return

        # Move the canvas by the small velocity amount.
        self.chat_canvas.yview_moveto(current_top + self.scroll_velocity)

        # Apply friction to the velocity, making it slow down over time.
        self.scroll_velocity *= 0.85

        # Schedule the next frame of the animation in 15ms.
        self.scroll_animation_job = self.root.after(15, self._perform_scroll_step)

    def _scroll_input_bar(self, *args):
        """Custom scroll command to ensure the input bar scrolls one line at a time."""
        if args[0] == 'scroll':
            # Intercept the 'scroll' command and force the unit count to 1
            self.chat_input.yview_scroll(int(args[1]), "units")
        else:
            # For other commands like 'moveto', let them pass through normally
            self.chat_input.yview(*args)


    def _adjust_input_text_height(self, event=None):
        """
        Dynamically adjust the height of the input Text widget's CONTAINER based on its content.
        This method resizes the parent frame in pixels, which is more stable.
        """
        text_widget = self.chat_input
            
        try:
            num_lines = int(text_widget.tk.call((str(text_widget), 'count', '-displaylines', '1.0', 'end')))
        except tk.TclError:
            num_lines = 1
            
        clamped_lines = max(1, min(num_lines, self.INPUT_TEXT_MAX_LINES))
        
        # Calculate required height in PIXELS based on font metrics
        font_height = self.font_body.metrics("linespace")
        # Add 10px total for top/bottom padding inside the frame
        required_pixel_height = (clamped_lines * font_height) + 10 
        
        # Configure the CONTAINER's height, not the text widget's
        if self.text_clipper_frame.cget("height") != required_pixel_height:
             self.text_clipper_frame.config(height=required_pixel_height)

        # Show or hide the scrollbar using pack, which is safe inside the clipper frame
        if num_lines > self.INPUT_TEXT_MAX_LINES:
            self.input_scrollbar.pack(side="right", fill="y", padx=(0, 2))
        else:
            self.input_scrollbar.pack_forget()


    def _send_on_enter(self, event=None):
        """Sends message on Enter key, but allows Shift+Enter for newline."""
        if event and (event.state & 0x1): # Check for Shift key
            return # Let the default newline happen
        
        message = self.chat_input.get("1.0", "end-1c").strip()
        if message:
            self.app.send_chat_message(message)
            self.chat_input.delete("1.0", tk.END)
            # After sending, trigger the animation to shrink the text area
            self.root.after(10, self._adjust_input_text_height)
        
        return "break"

    def create_widgets(self):
        # ... (This function remains the same as your version) ...
        self.root.update_idletasks()
        self.mini_window = MiniWindow(self.app, self)
        self.root.bind("<Unmap>", self.handle_minimize)
        self.root.bind("<Configure>", self._on_window_resize)
        self.main_frame = tk.Frame(self.root, bg=self.COLOR_BG)
        self.main_frame.place(x=0, y=0, relwidth=1, relheight=1)
        self.sidebar_frame = tk.Frame(self.root, bg=self.COLOR_SIDEBAR, width=self.SIDEBAR_WIDTH_COLLAPSED)
        self.sidebar_frame.place(x=0, y=0, width=self.SIDEBAR_WIDTH_COLLAPSED, relheight=1)
        self.chat_view_frame = self._create_chat_view(self.main_frame)
        self.log_view_frame = self._create_logs_view(self.main_frame)
        self.settings_view_frame = self._create_settings_view(self.main_frame)
        self.meeting_view_frame = self._create_meeting_view(self.main_frame)
        self.session_sidebar_frame = self._create_session_sidebar(self.root)
        self.session_sidebar_trigger = tk.Frame(self.root, bg="#202124", width=12)
        self.session_sidebar_trigger.place(relx=1.0, rely=0, anchor='ne', relheight=1)
        self.session_sidebar_trigger.bind("<Enter>", self.handle_session_sidebar_enter)
        self.session_sidebar_frame.bind("<Leave>", self.handle_session_sidebar_leave)
        self.sidebar_frame.bind("<Enter>", self.expand_sidebar)
        self.sidebar_frame.bind("<Leave>", self.collapse_sidebar)
        self.sidebar_frame.lift()
        self.session_sidebar_frame.lift()
        self.session_sidebar_trigger.lift()
        self.settings_view_frame.lift()
        self._create_sidebar_widgets(self.sidebar_frame)
        self._update_chat_model_dropdown()
        self.show_view("chat")
        self.update_status("Ready")
        self.load_settings_to_gui()

    def _create_sidebar_widgets(self, parent):
        # ... (This function remains the same as your version) ...
        content_frame = tk.Frame(parent, bg=self.COLOR_SIDEBAR)
        content_frame.pack(fill='both', expand=True)
        top_frame = tk.Frame(content_frame, bg=self.COLOR_SIDEBAR)
        top_frame.pack(pady=20, padx=15, fill="x", anchor="n")
        ttk.Label(top_frame, text="AURA", style="Title.TLabel").pack(anchor="w")
        self.status_label = ttk.Label(top_frame, text="Initializing...", style="Status.TLabel")
        self.status_label.pack(anchor="w", pady=(5, 0))
        nav_frame = tk.Frame(content_frame, bg=self.COLOR_SIDEBAR)
        nav_frame.pack(pady=20, padx=10, fill="x")
        self.chat_button = ttk.Button(nav_frame, text="💬", style="Sidebar.TButton", command=lambda: self.show_view("chat"))
        self.chat_button.pack(fill="x", pady=(0, 5))
        self.meeting_button = ttk.Button(nav_frame, text="👥", style="Sidebar.TButton", command=lambda: self.show_view("meeting"))
        self.meeting_button.pack(fill="x", pady=(0, 5))
        self.logs_button = ttk.Button(nav_frame, text="📜", style="Sidebar.TButton", command=lambda: self.show_view("logs"))
        self.logs_button.pack(fill="x")
        self.settings_button = ttk.Button(content_frame, text="⚙️", style="Sidebar.TButton", command=self.open_settings_window)
        self.settings_button.pack(side="bottom", fill="x", padx=10, pady=20)

    def _create_meeting_view(self, parent):
        # ... (This function remains the same as your version) ...
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        content_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        content_frame.pack(side="left", fill="both", expand=True)
        qna_frame = tk.Frame(content_frame, bg=self.COLOR_INPUT_BG)
        qna_frame.pack(side="bottom", fill="x", padx=20, pady=(10, 20))
        self.meeting_qna_input = tk.Entry(qna_frame, bg=self.COLOR_INPUT_BG, fg=self.COLOR_FG, font=(self.FONT_FAMILY, 12), relief="flat", insertbackground=self.COLOR_FG)
        self.meeting_qna_input.pack(side="left", fill="x", expand=True, padx=15, ipady=8)
        self.meeting_qna_input.bind("<Return>", lambda event: self.app.handle_meeting_qna())
        ttk.Button(qna_frame, text="Ask", style="Control.TButton", command=self.app.handle_meeting_qna).pack(side="right", padx=(0,10))
        paned_window = tk.PanedWindow(content_frame, orient=tk.HORIZONTAL, bg=self.COLOR_BG, sashwidth=8, relief="flat")
        paned_window.pack(fill="both", expand=True, padx=20, pady=(20,0))
        transcript_frame = tk.Frame(paned_window, bg=self.COLOR_CONTENT_BOX)
        transcript_header = tk.Frame(transcript_frame, bg=self.COLOR_CONTENT_BOX)
        transcript_header.pack(fill="x", pady=(5,10), padx=10)
        ttk.Label(transcript_header, text="Live Transcript", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")
        ttk.Button(transcript_header, text="📋", style="Control.TButton", width=2, command=self.app.copy_transcript_to_clipboard).pack(side="right", padx=(5,0))
        self.meeting_volume_bar = ttk.Progressbar(transcript_header, variable=self.meeting_volume_var, maximum=50, style="Level.Horizontal.TProgressbar")
        self.meeting_volume_bar.pack(side="right", fill="x", expand=True, padx=(10,0))
        self.live_transcript_display = scrolledtext.ScrolledText(transcript_frame, wrap=tk.WORD, state='disabled', relief="flat", font=("Consolas", 10), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_FG, padx=10, pady=10)
        self.live_transcript_display.pack(expand=True, fill="both")
        paned_window.add(transcript_frame, minsize=200)
        summary_frame = tk.Frame(paned_window, bg=self.COLOR_CONTENT_BOX)
        summary_header = tk.Frame(summary_frame, bg=self.COLOR_CONTENT_BOX)
        summary_header.pack(fill="x", pady=(5,10), padx=10)
        ttk.Label(summary_header, text="Live Summary / Q&A", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")
        self.summary_status_label = ttk.Label(summary_header, text="Thinking...", font=self.font_italic, foreground=self.COLOR_MUTED)
        ttk.Button(summary_header, text="📋", style="Control.TButton", width=2, command=self.app.copy_summary_to_clipboard).pack(side="right", padx=(5,0))
        self.live_summary_display = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, state='disabled', relief="flat", font=self.font_body, bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_ACCENT, padx=10, pady=10)
        self.live_summary_display.tag_configure("title", font=self.font_title, spacing1=8, spacing3=8)
        self.live_summary_display.tag_configure("bullet", lmargin1=20, lmargin2=20, spacing1=2, spacing3=10, font=self.font_body)
        self.live_summary_display.tag_configure("bullet2", lmargin1=40, lmargin2=40, spacing1=2, spacing3=2, font=self.font_body)
        self.live_summary_display.tag_configure("question", font=self.font_italic, foreground=self.COLOR_FG_MUTED, spacing1=15)
        self.live_summary_display.tag_configure("answer", lmargin1=15, lmargin2=15, font=self.font_body, spacing1=2)
        self.live_summary_display.pack(expand=True, fill="both")
        paned_window.add(summary_frame, minsize=200)
        return view_frame
    
    def _on_window_resize(self, event):
    # This check ensures we only react to the main window's resize event.
        if event.widget == self.root:
            # We only re-calculate the layout if the size has actually changed.
            if self.last_root_width != event.width or self.last_root_height != event.height:
                self.last_root_width = event.width
                self.last_root_height = event.height
                # A small delay prevents update loops and ensures stability.
                self.root.after(50, lambda: self.show_view(self.active_view_name))

    def _create_session_sidebar(self, parent):
        session_sidebar = tk.Frame(parent, bg=self.COLOR_SIDEBAR, width=250)
        session_sidebar.place(relx=1.0, rely=0, anchor="nw", width=250, relheight=1)

        session_header = tk.Frame(session_sidebar, bg=self.COLOR_SIDEBAR)
        session_header.pack(fill="x", padx=10, pady=10)
        ttk.Label(session_header, text="Meeting Sessions", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")
        ttk.Button(session_header, text="+", style="Control.TButton", width=2, command=self.app.start_new_meeting_session).pack(side="right")

        self.session_list_frame = tk.Frame(session_sidebar, bg=self.COLOR_SIDEBAR)
        self.session_list_frame.pack(fill="both", expand=True)

        return session_sidebar

    def handle_session_sidebar_enter(self, event):
        target_x = (self.root.winfo_width() - 250) / self.root.winfo_width()
        self.animate_session_sidebar(target_x)

    def handle_session_sidebar_leave(self, event):
        self.animate_session_sidebar(1.0)

    def animate_session_sidebar(self, target_relx):
        if hasattr(self, 'session_sidebar_animation_job'):
            self.root.after_cancel(self.session_sidebar_animation_job)

        current_relx = float(self.session_sidebar_frame.place_info().get('relx', 1.0))
        if abs(target_relx - current_relx) < 0.01:
            self.session_sidebar_frame.place_configure(relx=target_relx)
            return

        new_relx = current_relx + (target_relx - current_relx) * 0.2
        self.session_sidebar_frame.place_configure(relx=new_relx)
        self.session_sidebar_animation_job = self.root.after(10, lambda: self.animate_session_sidebar(target_relx))

    def _insert_formatted_text(self, text_widget, text):
        lines = text.splitlines()
        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                text_widget.insert(tk.END, '\n')
                continue
            
            if stripped_line.startswith('**##') and stripped_line.endswith('##**'):
                clean_line = stripped_line.replace('**##', '').replace('##**', '').strip()
                text_widget.insert(tk.END, clean_line + '\n', "title")
            elif stripped_line.startswith('+ '):
                clean_line = "    • " + stripped_line[2:]
                text_widget.insert(tk.END, clean_line + '\n', 'bullet2')
            elif stripped_line.startswith(('• ', '* ', '- ')):
                clean_line = "• " + stripped_line[2:]
                text_widget.insert(tk.END, clean_line + '\n', "bullet")
            elif stripped_line.startswith('Q: '):
                 text_widget.insert(tk.END, stripped_line + '\n', "question")
            elif stripped_line.startswith('A: '):
                 text_widget.insert(tk.END, stripped_line + '\n', "answer")
            else:
                text_widget.insert(tk.END, stripped_line + ' ')
    
    def show_summary_status(self, text):
        if hasattr(self, 'summary_status_label'):
            self.summary_status_label.config(text=text)
            self.summary_status_label.pack(side="left", padx=(10,0))

    def hide_summary_status(self):
        if hasattr(self, 'summary_status_label'):
            self.summary_status_label.pack_forget()

    def add_meeting_session_to_list(self, session_id, title):
        session_frame = ttk.Frame(self.session_list_frame, style='Sidebar.TFrame')
        session_frame.pack(fill="x", padx=5, pady=2)

        button_group = ttk.Frame(session_frame, style='Sidebar.TFrame')
        button_group.pack(side="right", padx=(5,0))

        select_btn = ttk.Button(session_frame, text=title, style="Session.Sidebar.TButton", command=lambda: self.app.switch_active_meeting_session(session_id))
        select_btn.pack(side="left", fill="x", expand=True)

        save_btn = ttk.Button(button_group, text="💾", style="Control.TButton", width=2, command=lambda: self.app.save_meeting_session(session_id))
        save_btn.pack(side="left")
        toggle_btn = ttk.Button(button_group, text="■", style="Control.TButton", width=2, command=lambda: self.app.toggle_meeting_session_status(session_id))
        toggle_btn.pack(side="left")
        delete_btn = ttk.Button(button_group, text="🗑️", style="Control.TButton", width=2, command=lambda: self.app.delete_meeting_session(session_id))
        delete_btn.pack(side="left")

        select_btn.full_text = title
        select_btn.bind("<Enter>", lambda event, b=select_btn, t=title: self.start_title_scroll(event, b, t))
        select_btn.bind("<Leave>", lambda event, b=select_btn: self.stop_title_scroll(event, b))

        self.meeting_session_widgets[session_id] = {
            'frame': session_frame, 'button': select_btn, 'toggle_button': toggle_btn,
            'save_button': save_btn, 'delete_button': delete_btn
        }

    def start_title_scroll(self, event, button, full_text):
        if self.scrolling_job:
            self.root.after_cancel(self.scrolling_job)
            if self.scrolling_widget and self.scrolling_widget.winfo_exists():
                 self.scrolling_widget.config(text=self.scrolling_widget.full_text)

        self.scrolling_widget = button
        font = self.font_sidebar_button
        text_width = font.measure(full_text)
        button_width = button.winfo_width()
        
        if text_width > button_width:
            button.scroll_pos = 0
            button.scroll_dir = 1
            self._scroll_text_step(button, full_text)

    def _scroll_text_step(self, button, full_text):
        if not button.winfo_exists() or self.scrolling_widget != button: return

        padded_text = "   " + full_text + "   "
        display_text = padded_text[button.scroll_pos:]
        button.config(text=display_text)
        button.scroll_pos += button.scroll_dir
        
        if button.scroll_pos >= len(padded_text) - len(full_text) or button.scroll_pos < 0:
            button.scroll_dir *= -1

        self.scrolling_job = self.root.after(200, lambda: self._scroll_text_step(button, full_text))

    def stop_title_scroll(self, event, button):
        if self.scrolling_job:
            self.root.after_cancel(self.scrolling_job)
        self.scrolling_job = None
        self.scrolling_widget = None
        if button.winfo_exists():
            button.config(text=button.full_text)

    def remove_session_from_list(self, session_id):
        widgets = self.meeting_session_widgets.pop(session_id, None)
        if widgets and widgets['frame'].winfo_exists():
            widgets['frame'].destroy()
            if self.app.active_meeting_session_id == session_id:
                self.load_session_data("", "")

    def load_session_data(self, transcript, summary):
        self.live_transcript_display.config(state='normal')
        self.live_transcript_display.delete('1.0', tk.END)
        self.live_transcript_display.insert('1.0', transcript)
        self.live_transcript_display.config(state='disabled')

        self.live_summary_display.config(state='normal')
        self.live_summary_display.delete('1.0', tk.END)
        self._insert_formatted_text(self.live_summary_display, summary)
        self.live_summary_display.config(state='disabled')

    def update_wakeword_meter(self, score):
        if hasattr(self, 'wakeword_meter'):
            self.wakeword_score_var.set(score)
            threshold = 0.02
            style = "Threshold.Horizontal.TProgressbar" if score > threshold else "Accent.Horizontal.TProgressbar"
            self.wakeword_meter.config(style=style)

    def update_transcript_display(self, text_chunk):
        if hasattr(self, 'live_transcript_display') and self.live_transcript_display.winfo_exists():
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_chunk = f"[{timestamp}] {text_chunk}\n"
            self.live_transcript_display.config(state='normal')
            self.live_transcript_display.insert(tk.END, formatted_chunk)
            self.live_transcript_display.see(tk.END)
            self.live_transcript_display.config(state='disabled')

    def update_summary_display(self, summary_chunk):
        if not (hasattr(self, 'live_summary_display') and self.live_summary_display.winfo_exists()):
            return

        if summary_chunk == "[CLEAR_SUMMARY]":
            self._summary_buffer = ""
            self.live_summary_display.config(state='normal')
            self.live_summary_display.delete('1.0', tk.END)
            self.live_summary_display.config(state='disabled')
            return

        self._summary_buffer += summary_chunk
        while "\n" in self._summary_buffer:
            line, self._summary_buffer = self._summary_buffer.split("\n", 1)
            self.live_summary_display.config(state='normal')
            self._insert_formatted_text(self.live_summary_display, line + "\n")
            self.live_summary_display.see(tk.END)
            self.live_summary_display.config(state='disabled')

    def update_meeting_volume(self, level):
        if hasattr(self, 'meeting_volume_var') and self.root.winfo_exists():
            self.meeting_volume_var.set(level)

    def update_session_title(self, session_id, new_title):
        widgets = self.meeting_session_widgets.get(session_id)
        if widgets and widgets['button'].winfo_exists():
            button = widgets['button']
            button.full_text = new_title
            button.config(text=new_title)

    def update_session_list_status(self, session_id, status):
        widgets = self.meeting_session_widgets.get(session_id)
        if widgets and 'toggle_button' in widgets and widgets['toggle_button'].winfo_exists():
            original_title = self.app.meeting_sessions[session_id]['title']
            toggle_button = widgets['toggle_button']
            button = widgets['button']

            if status == "Active":
                toggle_button.config(text="■", state="normal")
                button.config(text=f"{original_title} (Live)")
            elif status == "Stopping...":
                toggle_button.config(text="■", state="disabled")
                button.config(text=f"{original_title} (Stopping...)")
            elif status == "Stopped":
                toggle_button.config(text="▶", state="normal")
                button.config(text=f"{original_title} (Stopped)")
                
    def replace_last_qna_answer(self, new_answer):
        if hasattr(self, 'live_summary_display') and self.live_summary_display.winfo_exists():
            self.live_summary_display.config(state='normal')
            start_pos = self.live_summary_display.search("A: Thinking...", "end", backwards=True, nocase=True)
            if start_pos:
                end_pos = f"{start_pos}+{len('A: Thinking...')}c"
                self.live_summary_display.delete(start_pos, end_pos)
                self._insert_formatted_text(self.live_summary_display, "A: " + new_answer)
            self.live_summary_display.see(tk.END)
            self.live_summary_display.config(state='disabled')

    def animate_sentence(self, data_packet):
        if self.mini_window and self.mini_window.is_visible:
            self.mini_window.animate_new_sentence(data_packet)

    def stop_mini_gui_animation(self):
        if self.mini_window:
            self.mini_window.stop_animation()

    def open_settings_window(self):
        self.load_settings_to_gui()
        self.settings_view_frame.lift()
        self.animate_settings_view(0)

    def close_settings_window(self):
        self.animate_settings_view(1)

    def _populate_settings_tabs(self, notebook):
        tabs = {
            'API Keys & Paths': self._populate_general_settings,
            'App Paths': self._populate_app_paths_settings,
            'Features': self._populate_features_settings,
            'Hotkeys': self._populate_hotkeys_tab,
            'Skills': self._populate_skills_tab,
            'Routines': self._populate_routines_tab,
            'Audio': self._populate_audio_tab
        }
        for text, func in tabs.items():
            tab_frame = ttk.Frame(notebook, style='TFrame')
            notebook.add(tab_frame, text=text)
            func(tab_frame)

    def handle_minimize(self, event):
        if self.minimize_to_overlay_var.get() and str(event.widget) == '.':
            self.root.withdraw()
            self.mini_window.show()

    def restore_from_mini_mode(self):
        self.mini_window.hide()
        self.root.deiconify()

    def update_mic_level(self, level):
        self.mic_level_var.set(level)
        if self.mini_window:
            self.mini_window.last_level = level

    def expand_sidebar(self, event):
        if self.sidebar_animation_job: self.root.after_cancel(self.sidebar_animation_job)
        self.chat_button.config(text="💬 Chat")
        self.meeting_button.config(text="👥 Meeting")
        self.logs_button.config(text="📜 Logs")
        self.settings_button.config(text="⚙️ Settings")
        self.animate_sidebar(self.SIDEBAR_WIDTH_EXPANDED)

    def collapse_sidebar(self, event):
        if self.sidebar_animation_job: self.root.after_cancel(self.sidebar_animation_job)
        self.chat_button.config(text="💬")
        self.meeting_button.config(text="👥")
        self.logs_button.config(text="📜")
        self.settings_button.config(text="⚙️")
        self.animate_sidebar(self.SIDEBAR_WIDTH_COLLAPSED)

    def animate_sidebar(self, target_width):
        current_width = self.sidebar_frame.winfo_width()
        if abs(current_width - target_width) < 5:
            self.sidebar_frame.place_configure(width=target_width)
            return
        step = (target_width - current_width) * 0.25
        new_width = current_width + step
        self.sidebar_frame.place_configure(width=new_width)
        self.sidebar_animation_job = self.root.after(10, lambda: self.animate_sidebar(target_width))

    def animate_settings_view(self, target_relx):
        if self.settings_animation_job: self.root.after_cancel(self.settings_animation_job)
        current_relx = float(self.settings_view_frame.place_info().get('relx', 1))
        if abs(target_relx - current_relx) < 0.01:
            self.settings_view_frame.place_configure(relx=target_relx)
            return
        new_relx = current_relx + (target_relx - current_relx) * 0.35
        self.settings_view_frame.place_configure(relx=new_relx)
        self.settings_animation_job = self.root.after(10, lambda: self.animate_settings_view(target_relx))

    def add_transcript_line(self, text, is_aura):
        """Passes transcript information to the mini GUI."""
        if self.mini_window and self.mini_window.is_visible:
            # This now correctly handles both user commands and AURA's initial phrases
            self.mini_window.add_transcript_line(text, is_aura=is_aura)

    def _create_chat_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        history_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        history_frame.pack(side="top", expand=True, fill="both")

        self.chat_canvas = tk.Canvas(history_frame, bg=self.COLOR_BG, highlightthickness=0)
        self.chat_canvas.pack(side="left", fill="both", expand=True)
        self.chat_canvas.bind("<MouseWheel>", self._on_mousewheel)

        scrollbar_colors = {
            "bg": self.COLOR_BG, "track": self.COLOR_SIDEBAR,
            "thumb": "#9e9e9e", "thumb_active": self.COLOR_ACCENT
        }
        self.chat_scrollbar = RoundedScrollbar(history_frame, command=self.chat_canvas.yview, colors=scrollbar_colors)
        self.chat_canvas.configure(yscrollcommand=self.chat_scrollbar.set)
        
        self.chat_messages_frame = tk.Frame(self.chat_canvas, bg=self.COLOR_BG)
        self.chat_messages_frame.bind("<MouseWheel>", self._on_mousewheel)

        self.chat_canvas_window = self.chat_canvas.create_window((0, 0), window=self.chat_messages_frame, anchor="nw")
        
        self.chat_spacer = tk.Frame(self.chat_messages_frame, bg=self.COLOR_BG)
        self.chat_spacer.pack(fill="both", expand=True)
        self.chat_spacer.bind("<MouseWheel>", self._on_mousewheel)

        self.chat_messages_frame.bind("<Configure>", lambda e: self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all")))
        self.chat_canvas.bind("<Configure>", lambda e: self.chat_canvas.itemconfig(self.chat_canvas_window, width=e.width))

        # --- FINAL STABLE INPUT BAR ---
        input_bubble_frame = tk.Frame(view_frame, bg=self.COLOR_INPUT_BG,
                                      borderwidth=1, relief="solid")
        input_bubble_frame.config(highlightbackground=self.COLOR_ACCENT, highlightthickness=1)
        input_bubble_frame.pack(side="bottom", fill="x", padx=150, pady=(10, 20))

        # This frame will be resized in pixels, preventing layout instability.
        self.text_clipper_frame = tk.Frame(input_bubble_frame, bg=self.COLOR_INPUT_BG)
        self.text_clipper_frame.pack(fill="x", padx=5, pady=5)
        
        # This is the key: the container won't resize to fit its children. We control its size manually.
        self.text_clipper_frame.pack_propagate(False)

        font_height = self.font_body.metrics("linespace")
        self.text_clipper_frame.config(height=font_height + 10)

        input_scrollbar_colors = {"bg": self.COLOR_INPUT_BG, "thumb": "#9e9e9e", "thumb_active": self.COLOR_ACCENT}
        self.input_scrollbar = RoundedScrollbar(self.text_clipper_frame, command=self._scroll_input_bar, colors=input_scrollbar_colors)
        
        # The Text widget's height is NOT set. It grows naturally inside the clipper frame.
        self.chat_input = tk.Text(self.text_clipper_frame, bg=self.COLOR_INPUT_BG, fg=self.COLOR_FG,
                                font=self.font_body, relief="flat", wrap=tk.WORD,
                                insertbackground=self.COLOR_FG, borderwidth=0, highlightthickness=0,
                                yscrollcommand=self.input_scrollbar.set)
        self.chat_input.pack(side="left", fill="both", expand=True)

        self.chat_input.bind("<Return>", self._send_on_enter)
        self.chat_input.bind("<KeyRelease>", self._adjust_input_text_height)
        
        separator = ttk.Separator(input_bubble_frame, orient='horizontal')
        separator.pack(fill='x', padx=5)

        button_bar = tk.Frame(input_bubble_frame, bg=self.COLOR_INPUT_BG)
        button_bar.pack(fill="x", padx=5, pady=(2, 5))

        attach_button = ttk.Button(button_bar, text="📎", style="Chat.TButton", command=self._attach_file)
        attach_button.pack(side="left")
        star_button = ttk.Button(button_bar, text="⭐", style="Chat.TButton", command=lambda: print("Star button clicked"))
        star_button.pack(side="left")
        self.action_button = ttk.Button(button_bar, text="🎤", style="Chat.TButton",
                                        command=lambda: self.app.start_listening("button"))
        self.action_button.pack(side="right")
        send_button = ttk.Button(button_bar, text="➤", style="Chat.TButton", command=lambda: self._send_on_enter())
        send_button.pack(side="right")
        # --- END FINAL STABLE INPUT BAR ---
        
        return view_frame

        # Add this entire method back into your GUI class
    def add_chat_message(self, sender, message):
        if message == self.last_message_added: return None
        self.last_message_added = message
        
        msg_widget = None

        if sender.lower() == "you":
            # This row frame spans the full width of the chat area
            row_frame = tk.Frame(self.chat_messages_frame, bg=self.COLOR_BG)
            row_frame.bind("<MouseWheel>", self._on_mousewheel)
            
            # The first column is configured to expand, pushing the actual message to the right.
            row_frame.columnconfigure(0, weight=1)
            
            bubble_frame = tk.Frame(row_frame, bg=self.COLOR_INPUT_BG)
            
            # --- WIDGET CHANGE ---
            # A Label is used for user messages because it automatically wraps its width to fit the content.
            # We calculate a max width based on the chat canvas size to handle long messages.
            max_width = self.chat_canvas.winfo_width() * 0.65

            msg_widget = tk.Label(
                bubble_frame,
                text=message,
                bg=self.COLOR_INPUT_BG,
                fg=self.COLOR_FG,
                font=self.font_body,
                wraplength=max_width,  # This makes long messages wrap onto new lines
                justify=tk.LEFT       # This aligns multiple lines of text to the left
            )
            msg_widget.bind("<MouseWheel>", self._on_mousewheel)
            msg_widget.pack(padx=10, pady=5)
            # --- END WIDGET CHANGE ---
            
            # The bubble is placed in the second, non-expanding column, anchoring it to the right.
            bubble_frame.grid(row=0, column=1, pady=(5,10), padx=(10, 10))
            bubble_frame.bind("<MouseWheel>", self._on_mousewheel)
            
            row_frame.pack(fill="x", before=self.chat_spacer)

        else: # AURA messages still use AutoWrappingText for the animation
            row_frame = tk.Frame(self.chat_messages_frame, bg=self.COLOR_BG)
            row_frame.bind("<MouseWheel>", self._on_mousewheel)

            avatar = tk.Label(row_frame, text="A", font=(self.FONT_FAMILY, 14, "bold"),
                              bg=self.COLOR_ACCENT, fg=self.COLOR_BG,
                              width=2, height=1, relief="flat")
            avatar.pack(side="left", anchor="nw", padx=(10, 15), pady=5)
            avatar.bind("<MouseWheel>", self._on_mousewheel)
            
            msg_widget = AutoWrappingText(row_frame, bg=self.COLOR_BG, fg=self.COLOR_FG, font=self.font_body)
            # This check prevents trying to set text on a widget that is animating
            if not (hasattr(msg_widget, 'char_queue') and msg_widget.char_queue.qsize() > 0):
                 msg_widget.set_text(message)
            msg_widget.bind("<MouseWheel>", self._on_mousewheel)
            
            msg_widget.pack(side="left", anchor="w", pady=(0,5), fill="x", expand=True)
            row_frame.pack(fill="x", anchor="w", before=self.chat_spacer)

        self.root.update_idletasks()
        self.chat_canvas.yview_moveto(1.0)
        
        return msg_widget

    def update_action_button(self, state="idle"):
        """Toggles the main action button based on the app's current state."""
        if not hasattr(self, 'action_button') or not self.action_button.winfo_exists():
            return

        if state == "speaking":
            self.action_button.config(text="🤫", command=self.app.stop_speaking)
        elif state == "generating":
            self.action_button.config(text="⏹️", command=self.app.stop_generation)
        else: # idle
            self.action_button.config(text="🎤", command=lambda: self.app.start_listening("button"))

    def _on_chat_model_change(self, event=None):
        selection = self.chat_ai_engine_var.get()
        new_engine = 'gemini_online' if selection == "Gemini (Online)" else 'ollama_offline'
        if self.app.config['ai_engine'] != new_engine:
            self.app.config['ai_engine'] = new_engine
            self.app.queue_log(f"Chat AI model switched to: {new_engine}")
            self.app.clear_conversation_history()
            self.add_chat_message("AURA", f"Model switched to {selection}. Conversation history has been cleared.")

    def _update_chat_model_dropdown(self):
        current_engine = self.app.config.get("ai_engine", "gemini_online")
        self.chat_ai_engine_var.set("Ollama (Offline)" if current_engine == "ollama_offline" else "Gemini (Online)")

    def _create_logs_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        
        meter_frame = ttk.Labelframe(view_frame, text="Wake Word Detection Level", style='TLabelframe')
        meter_frame.pack(side="top", fill="x", pady=(10, 10), padx=20)
        self.wakeword_meter = ttk.Progressbar(meter_frame, variable=self.wakeword_score_var, maximum=0.05, style="Accent.Horizontal.TProgressbar")
        self.wakeword_meter.pack(fill="x", expand=True, padx=10, pady=10)

        logs_container = tk.Frame(view_frame, bg=self.COLOR_CONTENT_BOX)
        logs_container.pack(side="top", expand=True, fill="both", padx=20, pady=(0, 20))
        self.logs_display = tk.Text(logs_container, wrap=tk.WORD, state='disabled', relief="flat", font=("Consolas", 10), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_FG_MUTED, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(logs_container, style="TScrollbar", command=self.logs_display.yview)
        self.logs_display['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side="right", fill="y")
        self.logs_display.pack(side="left", expand=True, fill="both")

        # --- AI Response Monitor Widget ---
        monitor_frame = ttk.Labelframe(view_frame, text="Live AI Response Monitor (for diagnostics)", style='TLabelframe')
        monitor_frame.pack(side="bottom", fill="both", expand=True, pady=(10, 0), padx=20)
        
        self.ai_response_monitor_text = tk.Text(monitor_frame, wrap=tk.WORD, state='disabled', relief="flat", font=("Consolas", 10), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_ACCENT, padx=10, pady=10)
        
        monitor_scrollbar = ttk.Scrollbar(monitor_frame, style="TScrollbar", command=self.ai_response_monitor_text.yview)
        self.ai_response_monitor_text['yscrollcommand'] = monitor_scrollbar.set
        
        monitor_scrollbar.pack(side="right", fill="y")
        self.ai_response_monitor_text.pack(side="left", expand=True, fill="both")
        
        return view_frame
        
    def _create_settings_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        
        header_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        header_frame.pack(fill="x", padx=20, pady=(20,10))
        ttk.Button(header_frame, text="← Back", style="Control.TButton", command=self.close_settings_window).pack(side="left")
        ttk.Label(header_frame, text="Settings", style="Title.TLabel").pack(side="left", padx=20)
        ttk.Button(header_frame, text="Save Settings", style="Control.TButton", command=self.app.save_settings).pack(side="right")
        
        notebook = ttk.Notebook(view_frame, style="TNotebook")
        notebook.pack(expand=True, fill="both", padx=20, pady=10)
        
        self._populate_settings_tabs(notebook)
        
        view_frame.place(relx=1, rely=0, relwidth=1, relheight=1)
        return view_frame

    def show_view(self, view_name):
        # Store the name of the currently active view
        self.active_view_name = view_name

        self.chat_button.state(['!selected'])
        self.logs_button.state(['!selected'])
        self.meeting_button.state(['!selected'])
        if hasattr(self, 'log_view_frame') and self.log_view_frame:
            self.log_view_frame.pack_forget()
        if hasattr(self, 'chat_view_frame') and self.chat_view_frame:
            self.chat_view_frame.pack_forget()
        if hasattr(self, 'meeting_view_frame') and self.meeting_view_frame:
            self.meeting_view_frame.pack_forget()
        if float(self.settings_view_frame.place_info().get('relx', 1)) < 1.0:
            self.close_settings_window()
        
        # --- LAYOUT CALCULATIONS ---
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        
        # Horizontal Padding
        content_width_ratio = 0.5 
        padx = (root_width - int(root_width * content_width_ratio)) // 2
        
        # Vertical Padding
        pady_top = int(root_height * 0.10) # 10% from the top
        pady_bottom = int(root_height * 0.05) # 5% from the bottom
        
        if view_name == "chat" and self.chat_view_frame:
            self.chat_view_frame.pack(fill="both", expand=True, padx=padx, pady=(pady_top, pady_bottom))
            self.chat_button.state(['selected'])
        elif view_name == "logs" and self.log_view_frame:
            self.log_view_frame.pack(fill="both", expand=True, padx=padx, pady=(pady_top, pady_bottom))
            self.logs_button.state(['selected'])
        elif view_name == "meeting" and self.meeting_view_frame:
            # Meeting view uses different padding, which we'll leave as is.
            self.meeting_view_frame.pack(fill="both", expand=True, padx=(self.SIDEBAR_WIDTH_COLLAPSED + 10, 20))
            self.meeting_button.state(['selected'])

    def update_status(self, text, is_listening=False):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.config(text=text)
        if hasattr(self, 'listen_button') and self.listen_button.winfo_exists():
            style = "Active.Control.TButton" if is_listening else "Control.TButton"
            self.listen_button.config(style=style)

    def add_log(self, message):
        if hasattr(self, 'logs_display') and self.logs_display.winfo_exists():
            log_entry = f"[{self.app.get_timestamp()}] {message}\n"
            self.logs_display.config(state='normal')
            self.logs_display.insert(tk.END, log_entry)
            self.logs_display.see(tk.END)
            self.logs_display.config(state='disabled')
        else:
            print(f"[LOG] {message}")

    def _attach_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.attached_file_path.set(path)
            self.app.queue_log(f"Attached file: {os.path.basename(path)}")
            self.chat_input.delete(0, tk.END)
            self.chat_input.insert(0, f"[File Attached: {os.path.basename(path)}] - Type your command...")

    def _populate_general_settings(self, parent):
        frame = ttk.Frame(parent, pad=15)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        keys_frame = ttk.Labelframe(frame, text="API Keys", pad=10)
        keys_frame.pack(fill="x", expand=True, pady=(0, 15))

        def create_entry(parent_frame, label_text, row):
            ttk.Label(parent_frame, text=label_text, anchor="w").grid(row=row, column=0, sticky="w", pady=5, padx=5)
            entry = ttk.Entry(parent_frame, width=80)
            entry.grid(row=row, column=1, sticky="ew", padx=5)
            return entry
        
        self.gemini_api_key_entry = create_entry(keys_frame, "Gemini API Key:", 0)
        self.weather_api_key_entry = create_entry(keys_frame, "OpenWeather API Key:", 1)
        keys_frame.columnconfigure(1, weight=1)

        engine_frame = ttk.Labelframe(frame, text="Conversational AI Engine", pad=10)
        engine_frame.pack(fill="x", expand=True, pady=(0, 15))

        preload_frame = ttk.Labelframe(frame, text="AI Model Performance", pad=10)
        preload_frame.pack(fill="x", expand=True, pady=(0, 15))
        
        self.preload_models_var = tk.StringVar()
        ttk.Label(preload_frame, text="Model Preloading (requires restart):").pack(anchor="w", pady=(0,5))
        
        ttk.Radiobutton(preload_frame, text="None (Load models on demand, saves memory)", variable=self.preload_models_var, value="None").pack(anchor="w")
        ttk.Radiobutton(preload_frame, text="Preload Main AI (Faster first response, uses more memory)", variable=self.preload_models_var, value="Creator AI Only").pack(anchor="w")
        
        ttk.Radiobutton(engine_frame, text="Gemini (Online, Requires API Key)", variable=self.ai_engine_var, value="gemini_online").pack(anchor="w")
        ttk.Radiobutton(engine_frame, text="Ollama (Offline, Requires Ollama running)", variable=self.ai_engine_var, value="ollama_offline").pack(anchor="w")

        paths_frame = ttk.Labelframe(frame, text="Model Paths", pad=10)
        paths_frame.pack(fill="x", expand=True)

        self.whisper_path_entry = create_entry(paths_frame, "Whisper Model Path:", 0)
        self.ollama_model_entry = create_entry(paths_frame, "Ollama Model Name:", 1)
        paths_frame.columnconfigure(1, weight=1)

    def _populate_dynamic_list(self, parent, labels, add_row_func, list_ref, inner_frame_attr):
        header = ttk.Frame(parent); header.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(header, text=labels[0], font=(self.FONT_FAMILY, 10, "bold"), width=25).pack(side="left", padx=5)
        ttk.Label(header, text=labels[1], font=(self.FONT_FAMILY, 10, "bold")).pack(side="left", padx=5)
        container = ttk.Frame(parent); container.pack(fill="both", expand=True, padx=10, pady=5)
        canvas = tk.Canvas(container, bg=self.COLOR_CONTENT_BOX, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        setattr(self, inner_frame_attr, ttk.Frame(canvas))
        inner_frame = getattr(self, inner_frame_attr)
        inner_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True); scrollbar.pack(side="right", fill="y")
        ttk.Button(parent, text=f"Add New", style="Control.TButton", command=lambda: add_row_func(inner_frame)).pack(pady=5)

    def _populate_app_paths_settings(self, parent):
        self.app_path_rows.clear()
        self._populate_dynamic_list(parent, ["App Alias (e.g., notepad)", "Path"], self._create_app_path_row, self.app_path_rows, "app_path_inner_frame")

    def _create_app_path_row(self, parent, alias="", path=""):
        frame = ttk.Frame(parent, name=f"app_{len(self.app_path_rows)}"); frame.pack(fill="x", pady=2, padx=2)
        alias_entry = ttk.Entry(frame, width=25); alias_entry.insert(0, alias); alias_entry.pack(side="left", padx=5)
        path_entry = ttk.Entry(frame); path_entry.insert(0, path); path_entry.pack(side="left", fill="x", expand=True, padx=5)
        browse = ttk.Button(frame, text="...", style="Control.TButton", width=3, command=lambda e=path_entry: self._browse_file_path(e)); browse.pack(side="left", padx=5)
        delete = ttk.Button(frame, text="-", style="Control.TButton", width=2, command=lambda: self._delete_row(frame, self.app_path_rows)); delete.pack(side="right", padx=5)
        self.app_path_rows.append({"frame": frame, "alias": alias_entry, "path": path_entry})

    def _delete_row(self, frame, row_list):
        row = next((r for r in row_list if r["frame"] == frame), None)
        if row: row_list.remove(row)
        frame.destroy()

    def _browse_file_path(self, entry):
        path = filedialog.askopenfilename(filetypes=[("Executables", "*.exe"), ("All files", "*.*")])
        if path: entry.delete(0, tk.END); entry.insert(0, os.path.normpath(path))

    def _populate_features_settings(self, parent):
        fs_frame = ttk.Labelframe(parent, text="File System Watcher", pad=15)
        fs_frame.pack(fill="x", expand=True, padx=10, pady=10)
        
        ttk.Checkbutton(fs_frame, text="Announce New Files in a Folder", style="Switch.TCheckbutton", variable=self.fs_watcher_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(fs_frame, text="Folder to Watch:").grid(row=1, column=0, sticky="w", padx=5)
        path_frame = ttk.Frame(fs_frame)
        path_frame.grid(row=1, column=1, sticky="ew")
        fs_frame.columnconfigure(1, weight=1)
        self.fs_watcher_path_entry = ttk.Entry(path_frame, width=60)
        self.fs_watcher_path_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(path_frame, text="Browse...", style="Control.TButton", command=self._browse_folder_path).pack(side="left", padx=5)

        ch_frame = ttk.Labelframe(parent, text="Clipboard Manager", pad=15)
        ch_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        ttk.Checkbutton(ch_frame, text="Enable Clipboard History", style="Switch.TCheckbutton", variable=self.clipboard_history_enabled_var).pack(anchor="w")

        voice_frame = ttk.Labelframe(parent, text="Voice Selection", pad=15)
        voice_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        self._populate_voice_settings(voice_frame)

        mini_mode_frame = ttk.Labelframe(parent, text="Compact Overlay Mode", pad=15)
        mini_mode_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        ttk.Checkbutton(mini_mode_frame, text="Minimize to a compact overlay instead of the taskbar", style="Switch.TCheckbutton", variable=self.minimize_to_overlay_var).pack(anchor="w")

    def _populate_hotkeys_tab(self, parent):
        self.hotkey_rows = []
        header = ttk.Frame(parent)
        header.pack(fill="x", padx=15, pady=(15, 2))
        ttk.Label(header, text="Hotkey Combination", font=(self.FONT_FAMILY, 10, "bold"), width=30).pack(side="left")
        ttk.Label(header, text="Action", font=(self.FONT_FAMILY, 10, "bold")).pack(side="left", padx=5)
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, padx=15, pady=5)
        self.hotkey_inner_frame = ttk.Frame(container)
        self.hotkey_inner_frame.pack(fill="x")
        ttk.Button(parent, text="Add New Hotkey", style="Control.TButton", command=lambda: self._create_hotkey_row()).pack(pady=5, padx=15, anchor="w")

    def _create_hotkey_row(self, combination="Not Set", action=""):
        frame = ttk.Frame(self.hotkey_inner_frame)
        frame.pack(fill="x", pady=2)
        
        combo_var = tk.StringVar(value=combination)
        action_var = tk.StringVar(value=action)
        
        combo_label = ttk.Label(frame, textvariable=combo_var, width=30)
        combo_label.pack(side="left", padx=(0, 5))
        
        set_button = ttk.Button(frame, text="Set", style="Control.TButton", width=5)
        set_button.config(command=lambda v=combo_var, b=set_button: self._start_capture_hotkey_for_row(v, b))
        set_button.pack(side="left", padx=5)

        action_options = list(self.app.hotkey_actions.keys())
        action_dropdown = ttk.Combobox(frame, textvariable=action_var, values=action_options, state="readonly")
        action_dropdown.pack(side="left", padx=5)
        
        delete_button = ttk.Button(frame, text="-", style="Control.TButton", width=2, command=lambda f=frame: self._delete_row(f, self.hotkey_rows))
        delete_button.pack(side="right", padx=5)

        self.hotkey_rows.append({"frame": frame, "combo_var": combo_var, "action_var": action_var})

    def _start_capture_hotkey_for_row(self, combo_var, button):
        button.config(text="...", state="disabled")
        pressed_keys = set()

        def on_press(key):
            pressed_keys.add(key)
            if key not in {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.shift_l, keyboard.Key.shift_r}:
                hotkey_string = self._format_hotkey(pressed_keys)
                combo_var.set(hotkey_string)
                button.config(text="Set", state="normal")
                return False

        def on_release(key):
            if key in pressed_keys:
                try:
                    pressed_keys.remove(key)
                except KeyError:
                    pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()
    
    def _format_hotkey(self, keys):
        modifier_map = {
            keyboard.Key.ctrl_l: 'ctrl', keyboard.Key.ctrl_r: 'ctrl',
            keyboard.Key.alt_l: 'alt', keyboard.Key.alt_r: 'alt',
            keyboard.Key.shift_l: 'shift', keyboard.Key.shift_r: 'shift',
        }
        modifiers = {modifier_map[k] for k in keys if k in modifier_map}
        regular_keys = [k.char if hasattr(k, 'char') else k.name for k in keys if k not in modifier_map]
        return "+".join(sorted(list(modifiers)) + sorted(regular_keys))

    def _populate_skills_tab(self, parent):
        container = ttk.Frame(parent, pad=15)
        container.pack(fill="both", expand=True)
        ttk.Label(container, text="Enable or disable skills. Changes will apply after saving.", wraplength=400).pack(pady=(0, 15), anchor="w")
        skills_dir = "skills"
        if not os.path.exists(skills_dir):
            ttk.Label(container, text="Could not find the 'skills' directory.").pack()
            return
        for filename in sorted(os.listdir(skills_dir)):
            if filename.endswith(".py") and not filename.startswith("__"):
                frame = ttk.Frame(container)
                frame.pack(fill="x", pady=4)
                skill_name = " ".join(word.capitalize() for word in filename[:-3].replace("_", " ").split())
                ttk.Label(frame, text=skill_name, font=(self.FONT_FAMILY, 10)).pack(side="left")
                self.skill_toggle_vars[filename] = tk.BooleanVar(value=True)
                ttk.Checkbutton(frame, style="Switch.TCheckbutton", variable=self.skill_toggle_vars[filename]).pack(side="right")

    def _populate_routines_tab(self, parent):
        self.routine_rows = {}
        main_frame = ttk.Frame(parent)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)
        
        left_pane = ttk.Frame(main_frame, width=200)
        left_pane.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left_pane, text="Routines", font=(self.FONT_FAMILY, 10, "bold")).pack(anchor="w")
        self.routines_list_frame = ttk.Frame(left_pane)
        self.routines_list_frame.pack(fill="both", expand=True, pady=5)
        btn_frame = ttk.Frame(left_pane)
        btn_frame.pack(fill="x")
        ttk.Button(btn_frame, text="Add", style="Control.TButton", command=self._add_new_routine).pack(side="left", expand=True, fill="x")
        ttk.Button(btn_frame, text="Delete", style="Control.TButton", command=self._delete_selected_routine).pack(side="left", expand=True, fill="x")

        right_pane = ttk.Frame(main_frame)
        right_pane.pack(side="left", fill="both", expand=True)
        ttk.Label(right_pane, textvariable=self.selected_routine_name, font=(self.FONT_FAMILY, 12, "bold"), foreground=self.COLOR_ACCENT).pack(anchor="w", pady=(0,5))
        self.actions_list_frame = ttk.Frame(right_pane)
        self.actions_list_frame.pack(fill="both", expand=True)
        self.add_action_button = ttk.Button(right_pane, text="Add Action to Routine", style="Control.TButton", command=lambda: self._open_add_action_dialog())
        self.add_action_button.pack(fill="x", pady=(5,0))
        self.add_action_button.config(state="disabled")

    def _select_routine(self, routine_name):
        self.selected_routine_name.set(f"Actions for: {routine_name}")
        self.add_action_button.config(state="normal")
        self._redisplay_actions_for_selected_routine()

    def _redisplay_actions_for_selected_routine(self):
        for widget in self.actions_list_frame.winfo_children():
            widget.destroy()
        
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if not name or name not in self.routine_rows:
            return

        actions = self.routine_rows[name].get("actions", [])
        for i, action_data in enumerate(actions):
            self._create_action_row(i, action_data['type'], action_data['params'])

    def _create_action_row(self, index, action_type, params):
        frame = ttk.Frame(self.actions_list_frame, name=f"action_{index}")
        frame.pack(fill="x", pady=2)
        
        param_str = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else "No parameters"
        label_text = f"{action_type} ({param_str})"
        ttk.Label(frame, text=label_text).pack(side="left", expand=True, anchor="w")
        
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="↑", style="Control.TButton", width=2, command=lambda i=index: self._move_action(i, -1)).pack(side="left")
        ttk.Button(btn_frame, text="↓", style="Control.TButton", width=2, command=lambda i=index: self._move_action(i, 1)).pack(side="left")
        ttk.Button(btn_frame, text="Edit", style="Control.TButton", width=5, command=lambda i=index: self._open_add_action_dialog(edit_index=i)).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="-", style="Control.TButton", width=2, command=lambda i=index: self._delete_action(i)).pack(side="left", padx=2)
    
    def _add_new_routine(self):
        from tkinter import simpledialog
        name = simpledialog.askstring("New Routine", "Enter a name for the new routine:", parent=self.root)
        if name and name.strip():
            if name in self.routine_rows:
                messagebox.showerror("Error", "A routine with that name already exists.")
                return
            self.routine_rows[name] = {"actions": []}
            btn = ttk.Radiobutton(self.routines_list_frame, text=name, value=name, variable=self.selected_routine_name, style="Sidebar.TButton", command=lambda n=name: self._select_routine(n))
            btn.pack(fill="x", pady=2)
            self.routine_rows[name]["button"] = btn
            btn.invoke()

    def _delete_selected_routine(self):
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if not name:
            messagebox.showerror("Error", "No routine selected to delete.")
            return
        if messagebox.askyesno("Confirm", f"Are you sure you want to delete the '{name}' routine?"):
            self.routine_rows[name]["button"].destroy()
            del self.routine_rows[name]
            self.selected_routine_name.set("")
            self._redisplay_actions_for_selected_routine()
            self.add_action_button.config(state="disabled")

    def _delete_action(self, index):
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if name in self.routine_rows:
            del self.routine_rows[name]["actions"][index]
            self._redisplay_actions_for_selected_routine()

    def _move_action(self, index, direction):
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if name in self.routine_rows:
            actions = self.routine_rows[name]["actions"]
            new_index = index + direction
            if 0 <= new_index < len(actions):
                actions.insert(new_index, actions.pop(index))
                self._redisplay_actions_for_selected_routine()

    def _open_add_action_dialog(self, edit_index=None):
        dialog = tk.Toplevel(self.root)
        dialog.transient(self.root)
        dialog.grab_set()
        
        if edit_index is not None:
            name = self.selected_routine_name.get().replace("Actions for: ", "")
            action_to_edit = self.routine_rows[name]['actions'][edit_index]
            dialog.title(f"Edit Action")
        else:
            dialog.title("Add New Action")

        dialog.geometry("400x250")
        dialog.config(bg=self.COLOR_BG)
        
        ttk.Label(dialog, text="Select an action type:").pack(pady=5)
        
        action_type_var = tk.StringVar()
        action_options = list(self.app.routine_actions.keys())
        action_dropdown = ttk.Combobox(dialog, textvariable=action_type_var, values=action_options, state="readonly")
        action_dropdown.pack(pady=5, padx=10, fill="x")

        params_frame = ttk.Frame(dialog)
        params_frame.pack(pady=10, padx=10, fill="both", expand=True)
        param_entries = {}

        def on_action_selected(event=None):
            for widget in params_frame.winfo_children(): widget.destroy()
            param_entries.clear()
            
            selected_action = action_type_var.get()
            action_info = self.app.routine_actions.get(selected_action, {})
            required_params = action_info.get("params", {})
            
            for param_name, param_type_hint in required_params.items():
                row = ttk.Frame(params_frame)
                row.pack(fill="x", pady=2)
                label_text = f"{param_name.replace('_', ' ').capitalize()}:"
                ttk.Label(row, text=label_text, width=15).pack(side="left")
                entry = ttk.Entry(row)
                entry.pack(side="left", fill="x", expand=True)
                if edit_index is not None and action_to_edit['type'] == selected_action:
                    entry.insert(0, action_to_edit['params'].get(param_name, ''))
                param_entries[param_name] = entry

        action_dropdown.bind("<<ComboboxSelected>>", on_action_selected)

        if edit_index is not None:
            action_type_var.set(action_to_edit['type'])
            on_action_selected()

        def save_action():
            action_type = action_type_var.get()
            if not action_type:
                messagebox.showerror("Error", "You must select an action type.", parent=dialog)
                return

            params = {name: widget.get().strip() for name, widget in param_entries.items()}
            for name, value in params.items():
                if not value:
                    messagebox.showerror("Error", f"The '{name}' field cannot be empty.", parent=dialog)
                    return
            
            new_action_data = {"type": action_type, "params": params}
            selected_name = self.selected_routine_name.get().replace("Actions for: ", "")
            
            if edit_index is not None:
                self.routine_rows[selected_name]["actions"][edit_index] = new_action_data
            else:
                self.routine_rows[selected_name]["actions"].append(new_action_data)
            
            self._redisplay_actions_for_selected_routine()
            dialog.destroy()

        ttk.Button(dialog, text="Save Action", style="Control.TButton", command=save_action).pack(pady=10)

    def _populate_audio_tab(self, parent):
        container = ttk.Frame(parent, pad=15)
        container.pack(fill="both", expand=True)

        devices_frame = ttk.Labelframe(container, text="Device Selection", pad=15)
        devices_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(devices_frame, text="Microphone (for Commands):").grid(row=0, column=0, sticky="w", pady=2)
        self.input_device_dropdown = ttk.Combobox(devices_frame, textvariable=self.input_device_var, state="readonly", width=60)
        self.input_device_dropdown.grid(row=0, column=1, sticky="ew", padx=5)
        
        ttk.Label(devices_frame, text="Meeting Audio Source (Loopback):").grid(row=1, column=0, sticky="w", pady=2)
        self.loopback_device_dropdown = ttk.Combobox(devices_frame, textvariable=self.loopback_device_var, state="readonly", width=60)
        self.loopback_device_dropdown.grid(row=1, column=1, sticky="ew", padx=5)
        
        devices_frame.columnconfigure(1, weight=1)

        stt_frame = ttk.Labelframe(container, text="Speech Recognition Engine", pad=15)
        stt_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Radiobutton(stt_frame, text="Google (Online, Fast & Accurate)", variable=self.stt_engine_var, value="google_online").pack(anchor="w")
        ttk.Radiobutton(stt_frame, text="Whisper (Offline, Private)", variable=self.stt_engine_var, value="offline_whisper").pack(anchor="w")

        continuous_frame = ttk.Labelframe(container, text="Listening Mode", pad=15)
        continuous_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Checkbutton(continuous_frame, text="Enable Continuous Listening", style="Switch.TCheckbutton", variable=self.continuous_listening_var).pack(anchor="w")

        test_frame = ttk.Labelframe(container, text="Microphone Test", pad=15)
        test_frame.pack(fill="x")
        self.mic_test_button = ttk.Button(test_frame, text="Start Mic Test", style="Control.TButton", command=self.app.toggle_mic_test)
        self.mic_test_button.pack(pady=(0, 10))
        ttk.Label(test_frame, text="Input Level:").pack(anchor="w")
        self.mic_level_bar = ttk.Progressbar(test_frame, variable=self.mic_level_var, maximum=0.5, style="Level.Horizontal.TProgressbar")
        self.mic_level_bar.pack(fill="x", pady=(2, 10))
        ttk.Label(test_frame, text="Live Transcription:").pack(anchor="w")
        ttk.Label(test_frame, textvariable=self.mic_test_result_var, font=(self.FONT_FAMILY, 11, "italic"), foreground=self.COLOR_ACCENT, wraplength=500).pack(anchor="w", pady=5)

    def _populate_voice_settings(self, parent):
        voices_dir = "voices"
        try:
            available_voices = [f for f in os.listdir(voices_dir) if f.endswith(".wav")]
        except FileNotFoundError:
            available_voices = []

        if not available_voices:
            ttk.Label(parent, text="No .wav files found in 'voices' folder.").pack(pady=5)
            return

        ttk.Label(parent, text="AURA's Voice:").pack(side="left", padx=(0, 10))
        
        voice_dropdown = ttk.Combobox(parent, textvariable=self.voice_selection_var, values=available_voices, state="readonly")
        voice_dropdown.pack(side="left", fill="x", expand=True)

    def load_settings_to_gui(self):
        if not self.settings_view_frame.winfo_exists(): return
        config = self.app.config
        
        self.gemini_api_key_entry.delete(0, tk.END); self.gemini_api_key_entry.insert(0, config.get("gemini_api_key", ""))
        self.weather_api_key_entry.delete(0, tk.END); self.weather_api_key_entry.insert(0, config.get("weather_api_key", ""))
        self.whisper_path_entry.delete(0, tk.END); self.whisper_path_entry.insert(0, config.get("whisper_model_path", ""))
        
        for row in self.app_path_rows: row["frame"].destroy()
        self.app_path_rows.clear()
        for alias, path in config.get("app_paths", {}).items():
            self._create_app_path_row(self.app_path_inner_frame, alias, path)

        fs_watcher_config = config.get("file_system_watcher", {})
        self.fs_watcher_enabled_var.set(fs_watcher_config.get("enabled", False))
        self.fs_watcher_path_entry.delete(0, tk.END)
        self.fs_watcher_path_entry.insert(0, fs_watcher_config.get("path", ""))

        self.clipboard_history_enabled_var.set(config.get("clipboard_manager", {}).get("enabled", False))
        self.minimize_to_overlay_var.set(config.get("minimize_to_overlay", False))
        
        enabled_skills = config.get("enabled_skills", {})
        for skill_file, var in self.skill_toggle_vars.items():
            var.set(enabled_skills.get(skill_file, True))

        for row in self.hotkey_rows: row["frame"].destroy()
        self.hotkey_rows.clear()
        for item in config.get("hotkeys", []):
            self._create_hotkey_row(item.get("combination"), item.get("action"))

        voice_filename = os.path.basename(config.get("tts", {}).get("speaker_wav_path", ""))
        self.voice_selection_var.set(voice_filename)

        for widget in self.routines_list_frame.winfo_children(): widget.destroy()
        self.routine_rows.clear()
        for name, data in config.get("routines", {}).items():
            self.routine_rows[name] = {"actions": data}
            btn = ttk.Radiobutton(self.routines_list_frame, text=name, value=name, variable=self.selected_routine_name, style="Sidebar.TButton", command=lambda n=name: self._select_routine(n))
            btn.pack(fill="x", pady=2)
            self.routine_rows[name]["button"] = btn
        self.selected_routine_name.set("")
        self._redisplay_actions_for_selected_routine()
        self.add_action_button.config(state="disabled")

        audio_config = config.get("audio", {})
        self.input_device_dropdown['values'] = [d['name'] for d in self.app.input_devices]
        self.loopback_device_dropdown['values'] = [d['name'] for d in self.app.loopback_devices]
        self.input_device_var.set(audio_config.get("input_device_name", ""))
        self.loopback_device_var.set(audio_config.get("loopback_device_name", ""))
        self.stt_engine_var.set(audio_config.get("stt_engine", "google_online"))
        self.continuous_listening_var.set(audio_config.get("continuous_listening", False))

        self.ai_engine_var.set(config.get("ai_engine", "gemini_online"))
        self.ollama_model_entry.delete(0, tk.END)
        self.ollama_model_entry.insert(0, config.get("ollama_model", "llama3"))

        self.preload_models_var.set(config.get("preload_models", "None"))

    def get_settings(self):
        new_config = self.app.config.copy()
        
        new_config["gemini_api_key"] = self.gemini_api_key_entry.get().strip()
        new_config["weather_api_key"] = self.weather_api_key_entry.get().strip()
        new_config["whisper_model_path"] = self.whisper_path_entry.get().strip()
        
        new_config["app_paths"] = {row["alias"].get().strip().lower(): row["path"].get().strip() for row in self.app_path_rows if row["alias"].get().strip()}

        new_config["file_system_watcher"] = {"enabled": self.fs_watcher_enabled_var.get(), "path": self.fs_watcher_path_entry.get().strip()}
        new_config["clipboard_manager"] = {"enabled": self.clipboard_history_enabled_var.get()}
        new_config["minimize_to_overlay"] = self.minimize_to_overlay_var.get()

        new_config["enabled_skills"] = {skill_file: var.get() for skill_file, var in self.skill_toggle_vars.items()}

        new_config["hotkeys"] = [{"combination": row["combo_var"].get(), "action": row["action_var"].get()} for row in self.hotkey_rows if row["combo_var"].get() != "Not Set" and row["action_var"].get()]

        if self.voice_selection_var.get():
            new_config.setdefault("tts", {})["speaker_wav_path"] = os.path.join("voices", self.voice_selection_var.get())

        new_config["routines"] = {name: data.get("actions", []) for name, data in self.routine_rows.items()}
        
        selected_input_name = self.input_device_var.get()
        selected_loopback_name = self.loopback_device_var.get()
        input_index = next((d['index'] for d in self.app.input_devices if d['name'] == selected_input_name), None)
        loopback_index = next((d['index'] for d in self.app.loopback_devices if d['name'] == selected_loopback_name), None)

        new_config["audio"] = {
            "input_device_name": selected_input_name, "input_device_index": input_index,
            "loopback_device_name": selected_loopback_name, "loopback_device_index": loopback_index,
            "stt_engine": self.stt_engine_var.get(), "continuous_listening": self.continuous_listening_var.get()
        }

        new_config["ai_engine"] = self.ai_engine_var.get()
        new_config["ollama_model"] = self.ollama_model_entry.get().strip()

        new_config["preload_models"] = self.preload_models_var.get()

        return new_config

    def _apply_theme(self):
        # ... (This function remains the same, just ensure TScrollbar style is correct) ...
        style = ttk.Style()
        style.theme_use('clam')
        font_L = font.Font(family=self.FONT_FAMILY, size=16, weight="bold")
        font_M = font.Font(family=self.FONT_FAMILY, size=11)
        font_S = font.Font(family=self.FONT_FAMILY, size=10)
        COLOR_BTN_HOVER = "#3c4043"
        COLOR_BTN_PRESSED = "#5c6063"
        style.configure('.', background=self.COLOR_BG, foreground=self.COLOR_FG, font=font_M, borderwidth=0, focusthickness=0)
        style.configure('TFrame', background=self.COLOR_BG)
        style.configure('ContentBox.TFrame', background=self.COLOR_CONTENT_BOX)
        style.configure('TLabel', background=self.COLOR_BG, foreground=self.COLOR_FG)
        style.configure('Title.TLabel', font=font_L)
        style.configure('Status.TLabel', font=font_S, foreground=self.COLOR_FG_MUTED)
        style.configure('Sidebar.TFrame', background=self.COLOR_SIDEBAR)
        style.configure('TLabelframe', background=self.COLOR_BG, bordercolor=self.COLOR_FG_MUTED, borderwidth=1)
        style.configure('TLabelframe.Label', background=self.COLOR_BG, foreground=self.COLOR_FG_MUTED, font=font_S)
        style.configure('Sidebar.TButton', background=self.COLOR_SIDEBAR, font=font_M, padding=(20, 10), relief="flat", anchor="w")
        style.map('Sidebar.TButton', background=[('pressed', COLOR_BTN_PRESSED), ('active', COLOR_BTN_HOVER), ('selected', self.COLOR_BG)])
        style.configure('Session.Sidebar.TButton', anchor="w", font=self.font_sidebar_button, background=self.COLOR_SIDEBAR, padding=(10, 5), relief="flat")
        style.map('Session.Sidebar.TButton', background=[('pressed', COLOR_BTN_PRESSED), ('active', COLOR_BTN_HOVER)])
        style.configure('Control.TButton', background=self.COLOR_INPUT_BG, font=font_S, padding=8, relief="flat")
        style.map('Control.TButton', background=[('pressed', COLOR_BTN_PRESSED), ('active', COLOR_BTN_HOVER)])
        style.configure('Active.Control.TButton', background=self.COLOR_ACTIVE, foreground=self.COLOR_BG, font=font_S, padding=8, relief="flat")
        style.map('Active.Control.TButton', background=[('pressed', COLOR_BTN_PRESSED), ('active', self.COLOR_ACTIVE)])
        style.configure('Chat.TButton', background=self.COLOR_INPUT_BG, font=font_M, relief="flat", borderwidth=0, focusthickness=0)
        style.map('Chat.TButton', background=[('pressed', self.COLOR_INPUT_BG), ('active', COLOR_BTN_HOVER)], foreground=[('active', self.COLOR_ACCENT)])
        
        # Define a custom layout for a thick scrollbar thumb
        style.layout('Thick.TScrollbar.layout', 
            [('Vertical.Scrollbar.trough', {'children':
                [('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})],
            'sticky': 'ns'})]
        )

        # Configure the default TScrollbar style to use our new layout and settings
        style.configure('TScrollbar', 
                        layout='Thick.TScrollbar.layout',
                        troughcolor=self.COLOR_BG, 
                        background='#9e9e9e', 
                        relief='flat',
                        width=16)

        # Map the active state for the default TScrollbar style
        style.map('TScrollbar',
            background=[('active', self.COLOR_ACCENT)]
        )

        style.layout('Switch.TCheckbutton', [('Checkbutton.padding', {'children': [('Checkbutton.indicator', {'side': 'left', 'sticky': ''}), ('Checkbutton.focus', {'side': 'left', 'sticky': '', 'children': [('Checkbutton.label', {'sticky': 'nswe'})]})]})])
        style.configure('Switch.TCheckbutton', font=font_M, indicatorbackground='gray', indicatordiameter=20)
        style.map('Switch.TCheckbutton', indicatorbackground=[('selected', self.COLOR_ACTIVE), ('!selected', self.COLOR_INPUT_BG)])
        style.configure("Level.Horizontal.TProgressbar", troughcolor=self.COLOR_INPUT_BG, bordercolor=self.COLOR_SIDEBAR, background=self.COLOR_ACTIVE)
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=self.COLOR_INPUT_BG, bordercolor=self.COLOR_SIDEBAR, background=self.COLOR_ACCENT)
        style.configure("Threshold.Horizontal.TProgressbar", troughcolor=self.COLOR_INPUT_BG, bordercolor=self.COLOR_SIDEBAR, background=self.COLOR_ACTIVE)
        style.configure("TCombobox", fieldbackground=self.COLOR_INPUT_BG, background=self.COLOR_INPUT_BG, foreground=self.COLOR_FG, arrowcolor=self.COLOR_FG, relief="flat", padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', self.COLOR_INPUT_BG)])
        style.configure("TNotebook", background=self.COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.COLOR_BG, foreground=self.COLOR_FG_MUTED, padding=[10, 5], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.COLOR_CONTENT_BOX)], foreground=[("selected", self.COLOR_ACCENT)])
        style.configure('TEntry', fieldbackground=self.COLOR_INPUT_BG, foreground=self.COLOR_FG, insertbackground=self.COLOR_FG, borderwidth=2, relief="flat")
        style.map('TEntry', bordercolor=[('focus', self.COLOR_ACCENT), ('!focus', self.COLOR_SIDEBAR)], lightcolor=[('focus', self.COLOR_ACCENT)])
    
    def _browse_folder_path(self):
        path = filedialog.askdirectory()
        if path:
            self.fs_watcher_path_entry.delete(0, tk.END)
            self.fs_watcher_path_entry.insert(0, os.path.normpath(path))