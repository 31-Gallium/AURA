# In gui.py
import tkinter as tk
from tkinter import ttk, font, scrolledtext, messagebox, filedialog
import os

class GUI:
    def __init__(self, app_controller):
        self.app = app_controller
        self.root = self.app.root
        self.settings_window = None
        self.sidebar_animation_job = None
        self.settings_animation_job = None
        self.last_message_added = None
        
        self.scrolling_job = None
        self.scrolling_widget = None

        # --- Style & Animation Configuration ---
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
        self.SIDEBAR_ANIMATION_STEP = 40
        self.SIDEBAR_ANIMATION_DELAY = 10
        self.ANIMATION_STEP = 25
        self.ANIMATION_DELAY = 5

        self.hotkey_rows = []
        self.app_path_rows = []

        self.fs_watcher_enabled_var = tk.BooleanVar()
        self.clipboard_history_enabled_var = tk.BooleanVar()

        self.skill_toggle_vars = {}

        self.hotkey_capture_listener = None
        self.current_hotkey_str = tk.StringVar(value="Not Set")

        self.attached_file_path = tk.StringVar()


        self.routine_rows = {}
        self.action_rows = []
        self.selected_routine_name = tk.StringVar()

        self.input_device_var = tk.StringVar()
        self.loopback_device_var = tk.StringVar()
        self.mic_test_result_var = tk.StringVar()
        self.ai_engine_var = tk.StringVar()

        self.mic_level_var = tk.DoubleVar(value=0.0)
        self.meeting_volume_var = tk.DoubleVar(value=0.0)
        
        self.meeting_session_widgets = {}
        
        self.font_title = font.Font(family=self.FONT_FAMILY, size=13, weight="bold")
        self.font_body = font.Font(family=self.FONT_FAMILY, size=11)
        self.font_italic = font.Font(family=self.FONT_FAMILY, size=11, slant="italic")
        
        self.font_sidebar_button = font.Font(family=self.FONT_FAMILY, size=11)

        self.chat_ai_engine_var = tk.StringVar() # Add this line

        self._apply_theme()

        self.stt_engine_var = tk.StringVar()

        self.continuous_listening_var = tk.BooleanVar()

        self.root.attributes('-alpha', 0.0)  # Make transparent initially
        self.root.after(50, self.create_widgets)
        self.root.after(400, lambda: self.root.attributes('-alpha', 1.0))  # Fade in after 400ms


        self.root.after(50, self.create_widgets)




    def create_widgets(self):
        self.root.update_idletasks()  # Ensure window size is valid before placing

        self.sidebar_frame = tk.Frame(
            self.root,
            bg=self.COLOR_SIDEBAR,
            width=self.SIDEBAR_WIDTH_COLLAPSED
        )
        self.sidebar_frame.place(x=0, y=0, width=self.SIDEBAR_WIDTH_COLLAPSED, relheight=1)

        self.main_frame = tk.Frame(self.root, bg=self.COLOR_BG)
        self.main_frame.place(x=self.SIDEBAR_WIDTH_COLLAPSED, y=0, relheight=1, relwidth=1.0)

        # Create all views
        self.chat_view_frame = self._create_chat_view(self.main_frame)
        self.log_view_frame = self._create_logs_view(self.main_frame)
        self.settings_view_frame = self._create_settings_view(self.main_frame)
        self.meeting_view_frame = self._create_meeting_view(self.main_frame)

        self.session_sidebar_frame = self._create_session_sidebar(self.root)

            # Create a thin, visible frame on the right edge to act as a mouse-over trigger
        self.session_sidebar_trigger = tk.Frame(self.root, bg="#202124", width=12)
        self.session_sidebar_trigger.place(relx=1.0, rely=0, anchor='ne', relheight=1)

        # Bind mouse events to the trigger and the main panel itself
        self.session_sidebar_trigger.bind("<Enter>", self.handle_session_sidebar_enter)
        self.session_sidebar_frame.bind("<Leave>", self.handle_session_sidebar_leave)

        self.sidebar_frame.place(x=0, y=0, width=self.SIDEBAR_WIDTH_COLLAPSED, relheight=1)
        self.main_frame.place(x=self.SIDEBAR_WIDTH_COLLAPSED, y=0, relheight=1, relwidth=1.0)


        # Ensure settings is on top
        self.settings_view_frame.lift()

        self._update_chat_model_dropdown()
        self._create_sidebar_widgets(self.sidebar_frame)

        self.show_view("chat")
        self.update_status("Ready")

        self.sidebar_frame.bind("<Enter>", self.expand_sidebar)
        self.sidebar_frame.bind("<Leave>", self.collapse_sidebar)


    def _create_sidebar_widgets(self, parent):
        self.sidebar_content_frame = tk.Frame(parent, bg=self.COLOR_SIDEBAR)
        self.sidebar_content_frame.pack(fill='both', expand=True)
        top_frame = tk.Frame(self.sidebar_content_frame, bg=self.COLOR_SIDEBAR)
        top_frame.pack(pady=20, padx=15, fill="x", anchor="n")
        ttk.Label(top_frame, text="AURA", style="Title.TLabel").pack(anchor="w")
        
        self.status_label = ttk.Label(top_frame, text="Initializing...", style="Status.TLabel")
        self.status_label.pack(anchor="w", pady=(5, 0))
        
        nav_frame = tk.Frame(self.sidebar_content_frame, bg=self.COLOR_SIDEBAR)
        nav_frame.pack(pady=20, padx=10, fill="x")
        self.chat_button = ttk.Button(nav_frame, text="💬", style="Sidebar.TButton", command=lambda: self.show_view("chat"))
        self.chat_button.pack(fill="x", pady=(0, 5))

        self.meeting_button = ttk.Button(nav_frame, text="👥", style="Sidebar.TButton", command=lambda: self.show_view("meeting"))
        self.meeting_button.pack(fill="x", pady=(0, 5))

        self.logs_button = ttk.Button(nav_frame, text="📜", style="Sidebar.TButton", command=lambda: self.show_view("logs"))
        self.logs_button.pack(fill="x")
        
        self.settings_button = ttk.Button(self.sidebar_content_frame, text="⚙️", style="Sidebar.TButton", command=self.open_settings_window)
        self.settings_button.pack(side="bottom", fill="x", padx=10, pady=20)

    def _create_meeting_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        
        content_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        content_frame.pack(side="left", fill="both", expand=True)

        qna_frame = tk.Frame(content_frame, bg=self.COLOR_INPUT_BG)
        qna_frame.pack(side="bottom", fill="x", padx=20, pady=(10, 20))
        
        self.meeting_qna_input = tk.Entry(qna_frame, bg=self.COLOR_INPUT_BG, fg=self.COLOR_FG, font=(self.FONT_FAMILY, 12), relief="flat", insertbackground=self.COLOR_FG)
        self.meeting_qna_input.pack(side="left", fill="x", expand=True, padx=15, ipady=8)
        self.meeting_qna_input.bind("<Return>", lambda event: self.app.handle_meeting_qna())
        
        qna_send_button = ttk.Button(qna_frame, text="Ask", style="Control.TButton", command=self.app.handle_meeting_qna)
        qna_send_button.pack(side="right", padx=(0,10))
        
        paned_window = tk.PanedWindow(content_frame, orient=tk.HORIZONTAL, bg=self.COLOR_BG, sashwidth=8)
        paned_window.pack(fill="both", expand=True, padx=20, pady=(20,0))

        transcript_frame = tk.Frame(paned_window, bg=self.COLOR_CONTENT_BOX)
        transcript_header = tk.Frame(transcript_frame, bg=self.COLOR_CONTENT_BOX)
        transcript_header.pack(fill="x", pady=(5,10), padx=10)
        ttk.Label(transcript_header, text="Live Transcript", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")
        
        copy_transcript_btn = ttk.Button(transcript_header, text="📋", style="Control.TButton", width=2, command=self.app.copy_transcript_to_clipboard)
        copy_transcript_btn.pack(side="right", padx=(5,0))

        self.meeting_volume_bar = ttk.Progressbar(transcript_header, variable=self.meeting_volume_var, maximum=50, style="Level.Horizontal.TProgressbar")
        self.meeting_volume_bar.pack(side="right", fill="x", expand=True, padx=(10,0))
        self.live_transcript_display = scrolledtext.ScrolledText(transcript_frame, wrap=tk.WORD, state='disabled', relief="flat", font=("Consolas", 10), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_FG, padx=10, pady=10)
        self.live_transcript_display.pack(expand=True, fill="both")
        paned_window.add(transcript_frame)

        summary_frame = tk.Frame(paned_window, bg=self.COLOR_CONTENT_BOX)
        summary_header = tk.Frame(summary_frame, bg=self.COLOR_CONTENT_BOX)
        summary_header.pack(fill="x", pady=(5,10), padx=10)
        ttk.Label(summary_header, text="Live Summary / Q&A", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")

        self.summary_status_label = ttk.Label(summary_header, text="Thinking...", font=self.font_italic, foreground=self.COLOR_MUTED)
        
        copy_summary_btn = ttk.Button(summary_header, text="📋", style="Control.TButton", width=2, command=self.app.copy_summary_to_clipboard)
        copy_summary_btn.pack(side="right", padx=(5,0))
        
        self.live_summary_display = scrolledtext.ScrolledText(summary_frame, wrap=tk.WORD, state='disabled', relief="flat", font=self.font_body, bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_ACCENT, padx=10, pady=10)
        
        self.live_summary_display.tag_configure("title", font=self.font_title, spacing1=8, spacing3=8)
        self.live_summary_display.tag_configure("bullet", lmargin1=20, lmargin2=20, spacing1=2, spacing3=10, font=self.font_body)
        self.live_summary_display.tag_configure("bullet2", lmargin1=40, lmargin2=40, spacing1=2, spacing3=2, font=self.font_body)
        self.live_summary_display.tag_configure("question", font=self.font_italic, foreground=self.COLOR_FG_MUTED, spacing1=15)
        self.live_summary_display.tag_configure("answer", lmargin1=15, lmargin2=15, font=self.font_body, spacing1=2)

        self.live_summary_display.pack(expand=True, fill="both")
        paned_window.add(summary_frame)

        return view_frame
    
    def _create_session_sidebar(self, parent):
        """Creates the slide-out panel for meeting sessions."""
        # Create the frame with a fixed width
        session_sidebar = tk.Frame(parent, bg=self.COLOR_SIDEBAR, width=250)
        # Place it off-screen to the right initially
        session_sidebar.place(relx=1.0, rely=0, anchor="nw", width=250, relheight=1)

        session_header = tk.Frame(session_sidebar, bg=self.COLOR_SIDEBAR)
        session_header.pack(fill="x", padx=10, pady=10)
        ttk.Label(session_header, text="Meeting Sessions", font=(self.FONT_FAMILY, 11, "bold")).pack(side="left")

        new_session_btn = ttk.Button(session_header, text="+", style="Control.TButton", width=2, command=self.app.start_new_meeting_session)
        new_session_btn.pack(side="right")

        self.session_list_frame = tk.Frame(session_sidebar, bg=self.COLOR_SIDEBAR)
        self.session_list_frame.pack(fill="both", expand=True)

        return session_sidebar

    def toggle_session_sidebar(self):
        """Toggles the visibility of the session sidebar overlay."""
        # Check the current position to decide whether to open or close
        current_relx = float(self.session_sidebar_frame.place_info().get('relx', 1.0))
        
        self.show_view('meeting') # Ensure the main meeting view is visible when we open the panel

        if current_relx < 1.0:
            # If it's visible, animate it out
            self.animate_session_sidebar(1.0)
        else:
            # If it's hidden, animate it in
            target_x = (self.root.winfo_width() - 250) / self.root.winfo_width()
            self.animate_session_sidebar(target_x)

    def handle_session_sidebar_enter(self, event):
        """Called when the mouse enters the trigger area."""
        # Calculate the target position for the sidebar to be fully visible
        target_x = (self.root.winfo_width() - 250) / self.root.winfo_width()
        self.animate_session_sidebar(target_x)

    def handle_session_sidebar_leave(self, event):
        """Called when the mouse leaves the session sidebar panel."""
        self.animate_session_sidebar(1.0) # Animate back to the hidden state (off-screen)

    def animate_session_sidebar(self, target_relx):
        """Animates the session sidebar sliding in or out."""
        if hasattr(self, 'session_sidebar_animation_job'):
            self.root.after_cancel(self.session_sidebar_animation_job)

        current_relx = float(self.session_sidebar_frame.place_info().get('relx', 1.0))

        if abs(target_relx - current_relx) < 0.01:
            self.session_sidebar_frame.place_configure(relx=target_relx)
            return

        # Simple linear interpolation for smooth animation
        new_relx = current_relx + (target_relx - current_relx) * 0.2
        self.session_sidebar_frame.place_configure(relx=new_relx)

        self.session_sidebar_animation_job = self.root.after(10, lambda: self.animate_session_sidebar(target_relx))

    # --- REWRITTEN: This is the final, definitive parser logic ---
    def _insert_formatted_text(self, text_widget, text):
        for line in text.split('\n'):
            stripped_line = line.strip()
            if not stripped_line:
                text_widget.insert(tk.END, '\n')
                continue
            
            # --- THIS IS THE FIX ---
            # Unambiguously check for the unique title marker
            if stripped_line.startswith('**##') and stripped_line.endswith('##**'):
                clean_line = stripped_line.replace('**##', '').replace('##**', '').strip() + '\n'
                text_widget.insert(tk.END, clean_line, "title")
            
            # Check for SUB-BULLETS (e.g., "+ Sub-point")
            elif stripped_line.startswith('+ '):
                clean_line = "    - " + stripped_line[2:] + '\n'
                text_widget.insert(tk.END, clean_line, "bullet2")
            
            # Check for MAIN BULLET POINTS (e.g., "• Point")
            elif stripped_line.startswith(('• ', '* ', '- ')):
                clean_line = "• " + stripped_line[2:] + '\n'
                text_widget.insert(tk.END, clean_line, "bullet")

            # Check for Q&A formatting
            elif stripped_line.startswith('Q: '):
                 text_widget.insert(tk.END, stripped_line + '\n', "question")
            elif stripped_line.startswith('A: '):
                 text_widget.insert(tk.END, stripped_line + '\n', "answer")
            
            # Otherwise, it's regular text
            else:
                text_widget.insert(tk.END, stripped_line + '\n')
    
    def show_summary_status(self, text):
        if hasattr(self, 'summary_status_label'):
            self.summary_status_label.config(text=text)
            self.summary_status_label.pack(side="left", padx=(10,0))


    def hide_summary_status(self):
        if hasattr(self, 'summary_status_label'):
            self.summary_status_label.pack_forget()

    def add_meeting_session_to_list(self, session_id, title):
        """
        Creates and adds a new widget to the session list in the meeting view.
        This uses the .pack() geometry manager in a right-to-left packing order.
        """
        # A container frame for each session entry in the list.
        session_frame = ttk.Frame(self.session_list_frame, style='Sidebar.TFrame')
        session_frame.pack(fill="x", padx=5, pady=2)

        # A frame to group the control buttons together.
        button_group = ttk.Frame(session_frame, style='Sidebar.TFrame')
        # Pack the entire button group to the RIGHT side of the session_frame first.
        button_group.pack(side="right", padx=(5,0))

        # The button that displays the session title.
        select_btn = ttk.Button(session_frame, text=title, style="Session.Sidebar.TButton",
                                command=lambda: self.app.switch_active_meeting_session(session_id))
        # Now, pack the title button to the LEFT, telling it to fill and expand
        # into all the space that the button_group didn't take.
        select_btn.pack(side="left", fill="x", expand=True)


        # Add the individual control buttons to their group frame
        save_btn = ttk.Button(button_group, text="💾", style="Control.TButton", width=2,
                              command=lambda: self.app.save_meeting_session(session_id))
        save_btn.pack(side="left")

        toggle_btn = ttk.Button(button_group, text="■", style="Control.TButton", width=2,
                                command=lambda: self.app.toggle_meeting_session_status(session_id))
        toggle_btn.pack(side="left")

        delete_btn = ttk.Button(button_group, text="🗑️", style="Control.TButton", width=2,
                                command=lambda: self.app.delete_meeting_session(session_id))
        delete_btn.pack(side="left")


        # Add custom attributes and event bindings for the scrolling title effect.
        select_btn.full_text = title
        select_btn.bind("<Enter>", lambda event, b=select_btn, t=title: self.start_title_scroll(event, b, t))
        select_btn.bind("<Leave>", lambda event, b=select_btn: self.stop_title_scroll(event, b))


        # Store a reference to all the created widgets for future access.
        self.meeting_session_widgets[session_id] = {
            'frame': session_frame,
            'button': select_btn,
            'toggle_button': toggle_btn,
            'save_button': save_btn,
            'delete_button': delete_btn
        }

    def start_title_scroll(self, event, button, full_text):
        """Starts scrolling the text if it's too long for the button."""
        # Stop any previous scrolling job
        if self.scrolling_job:
            self.root.after_cancel(self.scrolling_job)
            if self.scrolling_widget and self.scrolling_widget.winfo_exists():
                 self.scrolling_widget.config(text=self.scrolling_widget.full_text)

        self.scrolling_widget = button
        
        # Measure if the text is wider than the button
        font = self.font_sidebar_button
        text_width = font.measure(full_text)
        button_width = button.winfo_width()
        
        # Only scroll if the text is actually wider than the button
        if text_width > button_width:
            # Initialize animation state
            button.scroll_pos = 0
            button.scroll_dir = 1 # 1 for forward, -1 for backward
            self._scroll_text_step(button, full_text)

    def _scroll_text_step(self, button, full_text):
        """A single step in the text scrolling animation."""
        if not button.winfo_exists() or self.scrolling_widget != button:
            return # Stop if button is destroyed or mouse has moved to another button

        # Pad the text for a smoother loop
        padded_text = "   " + full_text + "   "
        
        # The slice of text to display
        display_text = padded_text[button.scroll_pos:]
        button.config(text=display_text)
        
        button.scroll_pos += button.scroll_dir
        
        # Reverse direction at the ends
        if button.scroll_pos > len(padded_text) - 2 or button.scroll_pos < 0:
            button.scroll_dir *= -1

        self.scrolling_job = self.root.after(200, lambda: self._scroll_text_step(button, full_text))

    def stop_title_scroll(self, event, button):
        """Stops the scrolling animation and resets the text."""
        if self.scrolling_job:
            self.root.after_cancel(self.scrolling_job)
        self.scrolling_job = None
        self.scrolling_widget = None
        if button.winfo_exists():
            button.config(text=button.full_text) # Reset to full, static text

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
        self.live_summary_display.insert('1.0', summary)
        self.live_summary_display.config(state='disabled')
    
    def update_session_list_status(self, session_id, status):
        widgets = self.meeting_session_widgets.get(session_id)
        if widgets:
            original_title = self.app.meeting_sessions[session_id]['title']
            toggle_button = widgets['toggle_button']

            if status == "Active":
                toggle_button.config(text="■", state="normal") # Stop Icon
                widgets['button'].config(text=f"{original_title} (Live)")
            elif status == "Stopping...":
                toggle_button.config(text="■", state="disabled") # Disabled while stopping
                widgets['button'].config(text=f"{original_title} (Stopping...)")
            elif status == "Stopped":
                toggle_button.config(text="▶", state="normal") # Resume Icon
                widgets['button'].config(text=f"{original_title} (Stopped)")

    # --- NEW: Method to update the transcript panel ---
    def update_transcript_display(self, text_chunk):
        if hasattr(self, 'live_transcript_display') and self.live_transcript_display.winfo_exists():
            self.live_transcript_display.config(state='normal')
            self.live_transcript_display.insert(tk.END, text_chunk)
            self.live_transcript_display.see(tk.END)
            self.live_transcript_display.config(state='disabled')

    def update_summary_display(self, summary_chunk):
        if hasattr(self, 'live_summary_display') and self.live_summary_display.winfo_exists():
            self.live_summary_display.config(state='normal')
            
            if summary_chunk == "[CLEAR_SUMMARY]":
                self.live_summary_display.delete('1.0', tk.END)
            else:
                self._insert_formatted_text(self.live_summary_display, summary_chunk)

            self.live_summary_display.see(tk.END)
            self.live_summary_display.config(state='disabled')

    def update_meeting_volume(self, level):
        if hasattr(self, 'meeting_volume_var') and self.root.winfo_exists():
            self.meeting_volume_var.set(level)

    def update_session_title(self, session_id, new_title):
        widgets = self.meeting_session_widgets.get(session_id)
        if widgets and widgets['button'].winfo_exists():
            button = widgets['button']
            button.full_text = new_title # Update the stored full text
            button.config(text=new_title) # Update the display

    def update_session_list_status(self, session_id, status):
        widgets = self.meeting_session_widgets.get(session_id)
        if widgets and 'toggle_button' in widgets and widgets['toggle_button'].winfo_exists():
            original_title = self.app.meeting_sessions[session_id]['title']
            toggle_button = widgets['toggle_button']

            if status == "Active":
                toggle_button.config(text="■", state="normal") # Stop Icon
                widgets['button'].config(text=f"{original_title} (Live)")
            elif status == "Stopping...":
                toggle_button.config(text="■", state="disabled") # Disabled while stopping
                widgets['button'].config(text=f"{original_title} (Stopping...)")
            elif status == "Stopped":
                toggle_button.config(text="▶", state="normal") # Resume Icon
                widgets['button'].config(text=f"{original_title} (Stopped)")
                
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


    def open_settings_window(self):
        """This function now triggers the slide-in animation."""
        self.load_settings_to_gui()
        self.settings_view_frame.lift()
        self.animate_settings_view(0) # Animate to relx=0
    
    def close_settings_window(self):
        """This function triggers the slide-out animation."""
        self.animate_settings_view(1) # Animate to relx=1

    def _populate_settings_tabs(self, notebook):
        general_tab = ttk.Frame(notebook, style='TFrame')
        paths_tab = ttk.Frame(notebook, style='TFrame')
        features_tab = ttk.Frame(notebook, style='TFrame')
        hotkeys_tab = ttk.Frame(notebook, style='TFrame')
        skills_tab = ttk.Frame(notebook, style='TFrame')
        routines_tab = ttk.Frame(notebook, style='TFrame')
        audio_tab = ttk.Frame(notebook, style='TFrame')


        notebook.add(general_tab, text='API Keys & Paths')
        notebook.add(paths_tab, text='App Paths')
        notebook.add(features_tab, text='Features')
        notebook.add(hotkeys_tab, text='Hotkeys')
        notebook.add(skills_tab, text='Skills')
        notebook.add(routines_tab, text='Routines')
        notebook.add(audio_tab, text='Audio')

        self._populate_general_settings(general_tab)
        self._populate_app_paths_settings(paths_tab)
        self._populate_features_settings(features_tab)
        self._populate_hotkeys_tab(hotkeys_tab)
        self._populate_skills_tab(skills_tab)
        self._populate_routines_tab(routines_tab)
        self._populate_audio_tab(audio_tab)

    def _populate_general_settings(self, parent):
        frame = ttk.Frame(parent, pad=15)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # --- API Keys Section ---
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

        # --- AI Engine Selection ---
        engine_frame = ttk.Labelframe(frame, text="Conversational AI Engine", pad=10)
        engine_frame.pack(fill="x", expand=True, pady=(0, 15))
        
        self.ai_engine_var = tk.StringVar()
        ttk.Radiobutton(engine_frame, text="Gemini (Online, Requires API Key)", variable=self.ai_engine_var, value="gemini_online").pack(anchor="w")
        ttk.Radiobutton(engine_frame, text="Ollama (Offline, Requires Ollama running)", variable=self.ai_engine_var, value="ollama_offline").pack(anchor="w")

        # --- Paths Section ---
        paths_frame = ttk.Labelframe(frame, text="Model Paths", pad=10)
        paths_frame.pack(fill="x", expand=True)

        self.whisper_path_entry = create_entry(paths_frame, "Whisper Model Path:", 0)
        self.ollama_model_entry = create_entry(paths_frame, "Ollama Model Name:", 1) # To specify llama3, mixtral, etc.
        paths_frame.columnconfigure(1, weight=1)

    def _populate_skills_tab(self, parent):
        """Creates a list of all available skills with on/off toggles."""
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

                # Format the name nicely (e.g., "joke_skill.py" -> "Joke Skill")
                skill_name = " ".join(word.capitalize() for word in filename[:-3].replace("_", " ").split())
                ttk.Label(frame, text=skill_name, font=(self.FONT_FAMILY, 10)).pack(side="left")

                # Create and store the BooleanVar for this skill's toggle
                self.skill_toggle_vars[filename] = tk.BooleanVar(value=True) # Default to enabled
                
                toggle = ttk.Checkbutton(frame, style="Switch.TCheckbutton", variable=self.skill_toggle_vars[filename])
                toggle.pack(side="right")
    
    def _populate_hotkeys_tab(self, parent):
        """Creates the dynamic UI for adding/removing multiple hotkeys."""
        self.hotkey_rows = []
        
        header = ttk.Frame(parent)
        header.pack(fill="x", padx=15, pady=(15, 2))
        ttk.Label(header, text="Hotkey Combination", font=(self.FONT_FAMILY, 10, "bold"), width=30).pack(side="left")
        ttk.Label(header, text="Action", font=(self.FONT_FAMILY, 10, "bold")).pack(side="left", padx=5)

        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True, padx=15, pady=5)
        
        # This frame will hold the list of hotkey rows
        self.hotkey_inner_frame = ttk.Frame(container)
        self.hotkey_inner_frame.pack(fill="x")

        ttk.Button(parent, text="Add New Hotkey", style="Control.TButton", command=lambda: self._create_hotkey_row()).pack(pady=5, padx=15, anchor="w")

    def _create_hotkey_row(self, combination="Not Set", action=""):
        """Creates a single row in the hotkey settings UI."""
        frame = ttk.Frame(self.hotkey_inner_frame)
        frame.pack(fill="x", pady=2)
        
        combo_var = tk.StringVar(value=combination)
        action_var = tk.StringVar(value=action)
        
        # --- UI for the hotkey combination ---
        combo_label = ttk.Label(frame, textvariable=combo_var, width=30)
        combo_label.pack(side="left", padx=(0, 5))
        
        set_button = ttk.Button(frame, text="Set", style="Control.TButton", width=5)
        # Use a lambda to pass the necessary variables to the capture function
        set_button.config(command=lambda v=combo_var, b=set_button: self._start_capture_hotkey_for_row(v, b))
        set_button.pack(side="left", padx=5)

        # --- UI for the action dropdown ---
        action_options = list(self.app.hotkey_actions.keys())
        action_dropdown = ttk.Combobox(frame, textvariable=action_var, values=action_options, state="readonly")
        action_dropdown.pack(side="left", padx=5)
        
        # --- UI for the delete button ---
        delete_button = ttk.Button(frame, text="-", style="Control.TButton", width=2,
                                   command=lambda f=frame: self._delete_row(f, self.hotkey_rows))
        delete_button.pack(side="right", padx=5)

        # Store references to all the widgets in this row
        self.hotkey_rows.append({
            "frame": frame,
            "combo_var": combo_var,
            "action_var": action_var
        })

    def _start_capture_hotkey_for_row(self, combo_var, button):
        """Starts a listener to capture a hotkey for a specific row."""
        from pynput import keyboard

        button.config(text="...")
        button.config(state="disabled")
        pressed_keys = set()

        def on_press(key):
            pressed_keys.add(key)
            # Stop listening once a non-modifier key is pressed
            if key not in {keyboard.Key.ctrl_l, keyboard.Key.ctrl_r, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.shift_l, keyboard.Key.shift_r}:
                hotkey_string = self._format_hotkey(pressed_keys)
                combo_var.set(hotkey_string)
                button.config(text="Set")
                button.config(state="normal")
                return False # Stop the listener

        def on_release(key):
            if key in pressed_keys:
                pressed_keys.remove(key)

        # The listener is temporary and self-destructs
        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

    def _format_hotkey(self, keys):
        """Formats a set of pynput keys into a user-friendly string."""
        from pynput.keyboard import Key
        
        modifier_map = {
            Key.ctrl_l: 'ctrl', Key.ctrl_r: 'ctrl',
            Key.alt_l: 'alt', Key.alt_r: 'alt',
            Key.shift_l: 'shift', Key.shift_r: 'shift',
        }
        
        modifiers = set()
        regular_keys = []
        
        for key in keys:
            if key in modifier_map:
                modifiers.add(modifier_map[key])
            else:
                try:
                    key_char = key.char if key.char else key.name
                except AttributeError:
                    key_char = key.name
                if key_char:
                    regular_keys.append(key_char)

        return "+".join(sorted(list(modifiers)) + sorted(regular_keys))
    
    def _format_hotkey(self, keys):
        """Formats a set of pynput keys into a user-friendly string."""
        from pynput.keyboard import Key
        
        modifier_map = {
            Key.ctrl_l: 'ctrl', Key.ctrl_r: 'ctrl',
            Key.alt_l: 'alt', Key.alt_r: 'alt',
            Key.shift_l: 'shift', Key.shift_r: 'shift',
        }
        
        modifiers = set()
        regular_keys = []
        
        for key in keys:
            if key in modifier_map:
                modifiers.add(modifier_map[key])
            else:
                try:
                    # For regular keys like 'a', 'b'
                    key_char = key.char if key.char else key.name
                except AttributeError:
                    # For special keys like 'f1', 'space'
                    key_char = key.name
                if key_char:
                    regular_keys.append(key_char)

        # Combine all parts into the final string
        return "+".join(sorted(list(modifiers)) + sorted(regular_keys))

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

    def load_settings_to_gui(self):
        """Loads the current config into all settings UI elements."""
        if not self.settings_view_frame.winfo_exists(): return
        config = self.app.config
        audio_config = config.get("audio", {})
        
        # General Settings, App Paths, Features... (code remains the same)
        self.gemini_api_key_entry.delete(0, tk.END); self.gemini_api_key_entry.insert(0, config.get("gemini_api_key", ""))
        self.weather_api_key_entry.delete(0, tk.END); self.weather_api_key_entry.insert(0, config.get("weather_api_key", ""))
        self.whisper_path_entry.delete(0, tk.END); self.whisper_path_entry.insert(0, config.get("whisper_model_path", ""))
        
        for row in self.app_path_rows: row["frame"].destroy()
        self.app_path_rows.clear()
        for alias, path_info in config.get("app_paths", {}).items():
            path_to_display = path_info if isinstance(path_info, str) else path_info.get("path", "")
            self._create_app_path_row(self.app_path_inner_frame, alias, path_to_display)

        fs_watcher_config = config.get("file_system_watcher", {})
        self.fs_watcher_enabled_var.set(fs_watcher_config.get("enabled", False))
        self.fs_watcher_path_entry.delete(0, tk.END)
        self.fs_watcher_path_entry.insert(0, fs_watcher_config.get("path", ""))

        clipboard_config = config.get("clipboard_manager", {})
        self.clipboard_history_enabled_var.set(clipboard_config.get("enabled", False))
        
        enabled_skills = config.get("enabled_skills", {})
        for skill_file, var in self.skill_toggle_vars.items():
            is_enabled = enabled_skills.get(skill_file, True)
            var.set(is_enabled)

        # --- THIS BLOCK IS REVISED TO HANDLE OLD AND NEW CONFIGS ---
        for row in self.hotkey_rows:
            row["frame"].destroy()
        self.hotkey_rows.clear()
        
        hotkey_config = config.get("hotkeys", []) # Default to an empty list
        
        # Check if we loaded an old config (a dict) instead of the new one (a list)
        if isinstance(hotkey_config, dict):
            # This is the legacy format. Convert it.
            old_hotkey = hotkey_config.get("activation_hotkey")
            if old_hotkey and old_hotkey != "Not Set":
                # Create a single row with the old hotkey and a default action
                self._create_hotkey_row(old_hotkey, "Start Listening")
        
        elif isinstance(hotkey_config, list):
            # This is the new, correct format.
            for item in hotkey_config:
                if isinstance(item, dict):
                    self._create_hotkey_row(item.get("combination"), item.get("action"))

        # --- ADD THIS BLOCK FOR VOICE SETTINGS ---
        tts_config = config.get("tts", {})
        # Use os.path.basename to only get the filename, making it match the dropdown
        voice_filename = os.path.basename(tts_config.get("speaker_wav_path", ""))
        if hasattr(self, 'voice_selection_var'):
            self.voice_selection_var.set(voice_filename)
        # -----------------------------------------

        for widget in self.routines_list_frame.winfo_children():
            widget.destroy()
        self.routine_rows.clear()
        
        all_routines = config.get("routines", {})
        for name, actions in all_routines.items():
            self.routine_rows[name] = {"actions": actions}
            btn = ttk.Radiobutton(self.routines_list_frame, text=name, value=name, variable=self.selected_routine_name,
                                  style="Sidebar.TButton", command=lambda n=name: self._select_routine(n))
            btn.pack(fill="x", pady=2)
            self.routine_rows[name]["button"] = btn
        
        self.selected_routine_name.set("")
        self._redisplay_actions_for_selected_routine()
        self.add_action_button.config(state="disabled")

        # --- MODIFIED: Populate audio device dropdowns ---
        self.input_device_dropdown['values'] = [d['name'] for d in self.app.input_devices]
        self.loopback_device_dropdown['values'] = [d['name'] for d in self.app.loopback_devices]

        self.input_device_var.set(audio_config.get("input_device_name", ""))
        self.loopback_device_var.set(audio_config.get("loopback_device_name", ""))

        self.stt_engine_var.set(audio_config.get("stt_engine", "google_online")) # Default to Google
        self.continuous_listening_var.set(audio_config.get("continuous_listening", False))

        self.ai_engine_var.set(config.get("ai_engine", "gemini_online"))
        self.ollama_model_entry.delete(0, tk.END)
        self.ollama_model_entry.insert(0, config.get("ollama_model", "llama3"))

    def get_settings(self):
        """Gets all settings from the UI widgets and returns them as a config dict."""
        new_config = self.app.config.copy()
        
        # General, App Paths, Features... (code remains the same)
        new_config["gemini_api_key"] = self.gemini_api_key_entry.get().strip()
        new_config["weather_api_key"] = self.weather_api_key_entry.get().strip()
        new_config["whisper_model_path"] = self.whisper_path_entry.get().strip()
        
        app_paths = {}
        for row in self.app_path_rows:
            alias = row["alias"].get().strip().lower()
            new_path = row["path"].get().strip()
            if alias:
                original_entry = self.app.config.get("app_paths", {}).get(alias)
                if isinstance(original_entry, dict):
                    original_entry["path"] = new_path
                    app_paths[alias] = original_entry
                else:
                    app_paths[alias] = new_path
        new_config["app_paths"] = app_paths

        new_config["file_system_watcher"] = {
            "enabled": self.fs_watcher_enabled_var.get(),
            "path": self.fs_watcher_path_entry.get().strip()
        }
        new_config["clipboard_manager"] = {
            "enabled": self.clipboard_history_enabled_var.get()
        }

        # --- ADD THIS NEW BLOCK FOR SKILLS ---
        enabled_skills = {}
        for skill_file, var in self.skill_toggle_vars.items():
            enabled_skills[skill_file] = var.get()
        new_config["enabled_skills"] = enabled_skills
        # ------------------------------------

        hotkey_list = []
        for row in self.hotkey_rows:
            combination = row["combo_var"].get()
            action = row["action_var"].get()
            if combination != "Not Set" and action:
                hotkey_list.append({"combination": combination, "action": action})
        new_config["hotkeys"] = hotkey_list

        # --- ADD THIS BLOCK FOR VOICE SETTINGS ---
        if hasattr(self, 'voice_selection_var') and self.voice_selection_var.get():
            # We construct the full path for the config file
            full_voice_path = os.path.join("voices", self.voice_selection_var.get())
            # Ensure the "tts" key exists
            if "tts" not in new_config:
                new_config["tts"] = {}
            new_config["tts"]["speaker_wav_path"] = full_voice_path
        # -----------------------------------------

        routines_to_save = {}
        for name, data in self.routine_rows.items():
            routines_to_save[name] = data.get("actions", [])
        new_config["routines"] = routines_to_save
        
        # --- MODIFIED: Get all audio settings ---
        selected_input_name = self.input_device_var.get()
        selected_loopback_name = self.loopback_device_var.get()
        
        input_index = next((d['index'] for d in self.app.input_devices if d['name'] == selected_input_name), None)
        loopback_index = next((d['index'] for d in self.app.loopback_devices if d['name'] == selected_loopback_name), None)

        new_config["audio"] = {
            "input_device_name": selected_input_name,
            "input_device_index": input_index,
            "loopback_device_name": selected_loopback_name,
            "loopback_device_index": loopback_index,
            "stt_engine": self.stt_engine_var.get(),
            "continuous_listening": self.continuous_listening_var.get()
        }

        new_config["ai_engine"] = self.ai_engine_var.get()
        new_config["ollama_model"] = self.ollama_model_entry.get().strip()

        return new_config

    def expand_sidebar(self, event):
        if self.sidebar_animation_job: self.root.after_cancel(self.sidebar_animation_job)
        self.chat_button.config(text="💬 Chat")
        # --- NEW: Set expanded text for meeting button ---
        self.meeting_button.config(text="👥 Meeting")
        self.logs_button.config(text="📜 Logs")
        self.settings_button.config(text="⚙️ Settings")
        self.animate_sidebar(self.SIDEBAR_WIDTH_EXPANDED)

    def collapse_sidebar(self, event):
        if self.sidebar_animation_job: self.root.after_cancel(self.sidebar_animation_job)
        self.chat_button.config(text="💬")
        # --- NEW: Set collapsed text for meeting button ---
        self.meeting_button.config(text="👥")
        self.logs_button.config(text="📜")
        self.settings_button.config(text="⚙️")
        self.animate_sidebar(self.SIDEBAR_WIDTH_COLLAPSED)

    def animate_sidebar(self, target_width):
        current_width = self.sidebar_frame.winfo_width()

        # Skip if close enough
        if abs(current_width - target_width) < 2:
            self.sidebar_frame.place_configure(width=target_width)
            self.main_frame.place_configure(x=target_width)
            self._resume_layout_updates()
            return

        diff = target_width - current_width
        step = min(self.SIDEBAR_ANIMATION_STEP, abs(diff)) * (1 if diff > 0 else -1)
        new_width = current_width + step

        # Animate sidebar width
        self.sidebar_frame.place_configure(width=new_width)
        # Animate main_frame position to shift right as sidebar grows
        self.main_frame.place_configure(x=new_width)

        self._suspend_layout_updates()

        self.sidebar_animation_job = self.root.after(
            self.SIDEBAR_ANIMATION_DELAY,
            lambda: self.animate_sidebar(target_width)
        )




    def animate_settings_view(self, target_relx):
        if self.settings_animation_job:
            self.root.after_cancel(self.settings_animation_job)

        try:
            current_relx = float(self.settings_view_frame.place_info().get('relx', 1))
        except (KeyError, ValueError):
            current_relx = 1.0  # default fallback

        if abs(target_relx - current_relx) < 0.01:
            self.settings_view_frame.place_configure(relx=target_relx)
            return

        speed = 0.35  # Increase for faster speed; lower = smoother
        new_relx = current_relx + (target_relx - current_relx) * speed
        self.settings_view_frame.place_configure(relx=new_relx)

        self.settings_animation_job = self.root.after(10, lambda: self.animate_settings_view(target_relx))

    def _suspend_layout_updates(self):
        if self.meeting_view_frame.winfo_ismapped():
            self.meeting_view_frame.pack_propagate(False)
            self.meeting_view_frame.update_idletasks()

    def _resume_layout_updates(self):
        if self.meeting_view_frame.winfo_ismapped():
            self.meeting_view_frame.pack_propagate(True)
            self.meeting_view_frame.update_idletasks()


    def _create_chat_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        
        header_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        header_frame.pack(side="top", fill="x", padx=20, pady=(20, 0))

        ttk.Label(header_frame, text="AI Model:", font=self.font_body).pack(side="left", padx=(5,10))
        
        self.chat_model_selector = ttk.Combobox(
            header_frame, 
            textvariable=self.chat_ai_engine_var, 
            values=["Gemini (Online)", "Ollama (Offline)"],
            state="readonly",
            width=20
        )
        self.chat_model_selector.pack(side="left")
        self.chat_model_selector.bind("<<ComboboxSelected>>", self._on_chat_model_change)
        # -------------------------------------------------

        input_frame = tk.Frame(view_frame, bg=self.COLOR_INPUT_BG)
        input_frame.pack(side="bottom", fill="x", padx=20, pady=(10, 20))
        # ... (rest of the chat view remains the same)

        input_frame = tk.Frame(view_frame, bg=self.COLOR_INPUT_BG)
        input_frame.pack(side="bottom", fill="x", padx=20, pady=(10, 20))
        attach_button = ttk.Button(input_frame, text="📎", style="Control.TButton", width=3, command=self._attach_file)
        attach_button.pack(side="left", padx=(10, 0))
        self.chat_input = tk.Entry(input_frame, bg=self.COLOR_INPUT_BG, fg=self.COLOR_FG, font=(self.FONT_FAMILY, 12), relief="flat", insertbackground=self.COLOR_FG)
        self.chat_input.pack(side="left", fill="x", expand=True, padx=15, ipady=8)
        self.chat_input.bind("<Return>", lambda event: self.app.send_chat_message(self.chat_input.get()))
        
        controls_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        controls_frame.pack(side="bottom", fill="x", padx=20, pady=(0, 10))
        
        self.listen_button = ttk.Button(controls_frame, text="🎤 Listen", style="Control.TButton", command=self.app.start_listening)
        self.listen_button.pack(side="left", expand=True, padx=5)
        
        # --- This ensures the button is correctly created and connected ---
        self.stop_speak_button = ttk.Button(controls_frame, text="🤫 Stop Speech", style="Control.TButton", command=self.app.stop_speaking)
        self.stop_speak_button.pack(side="left", expand=True, padx=5)
        
        history_frame = tk.Frame(view_frame, bg=self.COLOR_CONTENT_BOX)
        history_frame.pack(side="top", expand=True, fill="both", padx=20, pady=(20, 0))
        
        self.chat_display = tk.Text(history_frame, wrap=tk.WORD, state='disabled', relief="flat", font=(self.FONT_FAMILY, 11), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_FG, padx=15, pady=15, spacing1=5, spacing3=15)
        scrollbar = ttk.Scrollbar(history_frame, style="TScrollbar", command=self.chat_display.yview)
        self.chat_display['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side="right", fill="y")
        self.chat_display.pack(side="left", expand=True, fill="both")
        
        self.chat_display.tag_configure("user", foreground=self.COLOR_ACCENT, font=(self.FONT_FAMILY, 11, "bold"))
        self.chat_display.tag_configure("aura", foreground=self.COLOR_FG)
        
        return view_frame
    
    def _on_chat_model_change(self, event=None):
        """Called when the user selects a new AI model in the chat view."""
        selection = self.chat_ai_engine_var.get()
        if selection == "Gemini (Online)":
            self.app.config['ai_engine'] = 'gemini_online'
        else:
            self.app.config['ai_engine'] = 'ollama_offline'
        self.app.queue_log(f"Chat AI model switched to: {self.app.config['ai_engine']}")

        self.app.clear_conversation_history()
        self.add_chat_message("AURA", f"Model switched to {selection}. Conversation history has been cleared to prevent context errors.")

    def _update_chat_model_dropdown(self):
        """Sets the dropdown to reflect the current config value."""
        current_engine = self.app.config.get("ai_engine", "gemini_online")
        if current_engine == "ollama_offline":
            self.chat_ai_engine_var.set("Ollama (Offline)")
        else:
            self.chat_ai_engine_var.set("Gemini (Online)")

    def _create_logs_view(self, parent):
        view_frame = tk.Frame(parent, bg=self.COLOR_BG, padx=20, pady=20)
        logs_container = tk.Frame(view_frame, bg=self.COLOR_CONTENT_BOX)
        logs_container.pack(expand=True, fill="both")
        self.logs_display = tk.Text(logs_container, wrap=tk.WORD, state='disabled', relief="flat", font=("Consolas", 10), bg=self.COLOR_CONTENT_BOX, fg=self.COLOR_FG_MUTED, padx=10, pady=10)
        scrollbar = ttk.Scrollbar(logs_container, style="TScrollbar", command=self.logs_display.yview)
        self.logs_display['yscrollcommand'] = scrollbar.set
        scrollbar.pack(side="right", fill="y")
        self.logs_display.pack(side="left", expand=True, fill="both")
        return view_frame
        
    def _create_settings_view(self, parent):
        """Creates the new integrated, animated settings view."""
        view_frame = tk.Frame(parent, bg=self.COLOR_BG)
        
        header_frame = tk.Frame(view_frame, bg=self.COLOR_BG)
        header_frame.pack(fill="x", padx=20, pady=(20,10))
        
        # --- THIS IS THE FIX ---
        # The back button now correctly calls `close_settings_window`
        # instead of hard-coding a return to the chat view.
        back_button = ttk.Button(header_frame, text="← Back", style="Control.TButton", command=self.close_settings_window)
        back_button.pack(side="left")
        
        ttk.Label(header_frame, text="Settings", style="Title.TLabel").pack(side="left", padx=20)
        
        save_button = ttk.Button(header_frame, text="Save Settings", style="Control.TButton", command=self.app.save_settings)
        save_button.pack(side="right")
        
        notebook = ttk.Notebook(view_frame)
        notebook.pack(expand=True, fill="both", padx=20, pady=10)
        
        self._populate_settings_tabs(notebook)
        
        view_frame.place(relx=1, rely=0, relwidth=1, relheight=1)
        return view_frame


    def add_chat_message(self, sender, message):
        if message == self.last_message_added:
            return
        self.last_message_added = message

        self.chat_display.config(state='normal')
        sender_tag = "user" if sender.lower() == "you" else "aura"
        start_index = self.chat_display.index(f"{tk.END}-1c")
        full_message = f"{sender}:\n{message}\n\n"
        self.chat_display.insert(tk.END, full_message)
        end_index = f"{start_index.split('.')[0]}.{int(start_index.split('.')[1]) + len(sender) + 1}"
        self.chat_display.tag_add(sender_tag, start_index, end_index)
        self.chat_display.see(tk.END)
        self.chat_display.config(state='disabled')

    def show_view(self, view_name):
        self.chat_button.state(['!selected'])
        self.logs_button.state(['!selected'])
        self.meeting_button.state(['!selected'])

        # Hide all main views
        self.log_view_frame.pack_forget()
        self.chat_view_frame.pack_forget()
        self.meeting_view_frame.pack_forget()

        # Only close settings if it's currently visible
        if float(self.settings_view_frame.place_info().get('relx', 1)) == 0.0:
            self.close_settings_window()

        if view_name == "chat":
            self.chat_view_frame.pack(fill="both", expand=True)
            self.chat_button.state(['selected'])
        elif view_name == "logs":
            self.log_view_frame.pack(fill="both", expand=True)
            self.logs_button.state(['selected'])
        elif view_name == "meeting":
            self.meeting_view_frame.pack(fill="both", expand=True)
            self.meeting_button.state(['selected'])


    def update_status(self, text, is_listening=False):
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.config(text=text)
        if hasattr(self, 'listen_button') and self.listen_button.winfo_exists():
            self.listen_button.config(style="Active.Control.TButton" if is_listening else "Control.TButton")

    def add_log(self, message):
        if hasattr(self, 'logs_display') and self.logs_display.winfo_exists():
            log_entry = f"[{self.app.get_timestamp()}] {message}\n"
            self.logs_display.config(state='normal')
            self.logs_display.insert(tk.END, log_entry)
            self.logs_display.see(tk.END)
            self.logs_display.config(state='disabled')
        else:
            print(f"[LOG] {message}")

    def _populate_voice_settings(self, parent):
        """Creates the UI for selecting a TTS voice."""
        voices_dir = "voices"
        try:
            available_voices = [f for f in os.listdir(voices_dir) if f.endswith(".wav")]
        except FileNotFoundError:
            available_voices = []

        if not available_voices:
            ttk.Label(parent, text="No .wav files found in 'voices' folder.").pack(pady=5)
            return

        ttk.Label(parent, text="AURA's Voice:").pack(side="left", padx=(0, 10))
        
        self.voice_selection_var = tk.StringVar()
        voice_dropdown = ttk.Combobox(parent, textvariable=self.voice_selection_var, values=available_voices, state="readonly")
        voice_dropdown.pack(side="left", fill="x", expand=True)
    
    def _populate_features_settings(self, parent):
        """Creates the UI controls for background features."""
        # --- File System Watcher Frame ---
        fs_frame = ttk.Labelframe(parent, text="File System Watcher", pad=15)
        fs_frame.pack(fill="x", expand=True, padx=10, pady=10)
        
        fs_switch = ttk.Checkbutton(fs_frame, text="Announce New Files in a Folder", style="Switch.TCheckbutton", variable=self.fs_watcher_enabled_var)
        fs_switch.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(fs_frame, text="Folder to Watch:").grid(row=1, column=0, sticky="w", padx=5)
        
        path_frame = ttk.Frame(fs_frame)
        path_frame.grid(row=1, column=1, sticky="ew")
        fs_frame.columnconfigure(1, weight=1)

        self.fs_watcher_path_entry = ttk.Entry(path_frame, width=60)
        self.fs_watcher_path_entry.pack(side="left", fill="x", expand=True)

        browse_button = ttk.Button(path_frame, text="Browse...", style="Control.TButton", command=self._browse_folder_path)
        browse_button.pack(side="left", padx=5)

        # --- Clipboard History Frame ---
        ch_frame = ttk.Labelframe(parent, text="Clipboard Manager", pad=15)
        ch_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        
        ch_switch = ttk.Checkbutton(ch_frame, text="Enable Clipboard History", style="Switch.TCheckbutton", variable=self.clipboard_history_enabled_var)
        ch_switch.pack(anchor="w")

        voice_frame = ttk.Labelframe(parent, text="Voice Selection", pad=15)
        voice_frame.pack(fill="x", expand=True, padx=10, pady=(0, 10))
        self._populate_voice_settings(voice_frame)

    def _browse_folder_path(self):
        """Opens a dialog to choose a folder and inserts it into the entry."""
        path = filedialog.askdirectory()
        if path:
            self.fs_watcher_path_entry.delete(0, tk.END)
            self.fs_watcher_path_entry.insert(0, os.path.normpath(path))
    
    def _populate_routines_tab(self, parent):
        """Creates the two-pane UI for managing routines."""
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
        """Called when a routine is selected. Updates the right pane with its actions."""
        self.selected_routine_name.set(f"Actions for: {routine_name}")
        self.add_action_button.config(state="normal")
        self._redisplay_actions_for_selected_routine()

    def _redisplay_actions_for_selected_routine(self):
        """Clears and re-draws all action widgets for the selected routine."""
        for widget in self.actions_list_frame.winfo_children():
            widget.destroy()
        
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if not name or name not in self.routine_rows:
            return

        actions = self.routine_rows[name].get("actions", [])
        for i, action_data in enumerate(actions):
            self._create_action_row(i, action_data['type'], action_data['params'])

    def _create_action_row(self, index, action_type, params):
        """Creates a visual row for a single action with Edit, Delete, Up, Down buttons."""
        frame = ttk.Frame(self.actions_list_frame, name=f"action_{index}")
        frame.pack(fill="x", pady=2)
        
        param_str = ", ".join(f"{k}: {v}" for k, v in params.items()) if params else "No parameters"
        label_text = f"{action_type} ({param_str})"
        ttk.Label(frame, text=label_text).pack(side="left", expand=True, anchor="w")
        
        # --- Control Buttons ---
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
            btn = ttk.Radiobutton(self.routines_list_frame, text=name, value=name, variable=self.selected_routine_name,
                                  style="Sidebar.TButton", command=lambda n=name: self._select_routine(n))
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
        """Deletes an action from the selected routine."""
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if name in self.routine_rows:
            del self.routine_rows[name]["actions"][index]
            self._redisplay_actions_for_selected_routine()

    def _move_action(self, index, direction):
        """Moves an action up (-1) or down (+1) in the list."""
        name = self.selected_routine_name.get().replace("Actions for: ", "")
        if name in self.routine_rows:
            actions = self.routine_rows[name]["actions"]
            new_index = index + direction
            if 0 <= new_index < len(actions):
                actions.insert(new_index, actions.pop(index))
                self._redisplay_actions_for_selected_routine()

    def _open_add_action_dialog(self, edit_index=None):
        """Opens a dialog to add a new action or edit an existing one."""
        # ... (rest of the dialog logic from the previous step remains the same)
        # ... just ensure the method signature is changed to accept edit_index=None
        dialog = tk.Toplevel(self.root)
        
        if edit_index is not None:
            name = self.selected_routine_name.get().replace("Actions for: ", "")
            action_to_edit = self.routine_rows[name]['actions'][edit_index]
            dialog.title(f"Edit Action")
        else:
            dialog.title("Add New Action")

        dialog.geometry("400x250")
        
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
                # If editing, pre-fill the value
                if edit_index is not None:
                    entry.insert(0, action_to_edit['params'].get(param_name, ''))
                param_entries[param_name] = entry

        action_dropdown.bind("<<ComboboxSelected>>", on_action_selected)

        if edit_index is not None:
            action_type_var.set(action_to_edit['type'])
            on_action_selected() # Manually trigger to populate fields for editing

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
            
            if edit_index is not None: # We are in edit mode
                self.routine_rows[selected_name]["actions"][edit_index] = new_action_data
            else: # We are in add mode
                self.routine_rows[selected_name]["actions"].append(new_action_data)
            
            self._redisplay_actions_for_selected_routine()
            dialog.destroy()

        ttk.Button(dialog, text="Save Action", command=save_action).pack(pady=10)

    def _attach_file(self):
        """Opens a file dialog and stores the selected file path."""
        # You can define specific file types, e.g., [("Word Documents", "*.docx"), ("All files", "*.*")]
        path = filedialog.askopenfilename()
        if path:
            self.attached_file_path.set(path)
            self.app.queue_log(f"Attached file: {os.path.basename(path)}")
            # Visually show the user what's attached
            self.chat_input.delete(0, tk.END)
            self.chat_input.insert(0, f"[File Attached: {os.path.basename(path)}] - Type your command...")


    def _populate_audio_tab(self, parent):
        """Creates the UI for managing audio devices and testing."""
        container = ttk.Frame(parent, pad=15)
        container.pack(fill="both", expand=True)

        # Device Selection Frame
        devices_frame = ttk.Labelframe(container, text="Device Selection", pad=15)
        devices_frame.pack(fill="x", pady=(0, 10))
        
        # --- Microphone (Input) ---
        ttk.Label(devices_frame, text="Microphone (for Commands):").grid(row=0, column=0, sticky="w", pady=2)
        self.input_device_dropdown = ttk.Combobox(devices_frame, textvariable=self.input_device_var, state="readonly", width=60)
        self.input_device_dropdown.grid(row=0, column=1, sticky="ew", padx=5)
        
        # --- NEW: Loopback Device (Meeting Audio) ---
        ttk.Label(devices_frame, text="Meeting Audio Source (Loopback):").grid(row=1, column=0, sticky="w", pady=2)
        self.loopback_device_dropdown = ttk.Combobox(devices_frame, textvariable=self.loopback_device_var, state="readonly", width=60)
        self.loopback_device_dropdown.grid(row=1, column=1, sticky="ew", padx=5)
        
        devices_frame.columnconfigure(1, weight=1)

        # Speech Recognition Engine Selection
        stt_frame = ttk.Labelframe(container, text="Speech Recognition Engine", pad=15)
        stt_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Radiobutton(stt_frame, text="Google (Online, Fast & Accurate)", variable=self.stt_engine_var, value="google_online").pack(anchor="w")
        ttk.Radiobutton(stt_frame, text="Whisper (Offline, Private)", variable=self.stt_engine_var, value="offline_whisper").pack(anchor="w")

        # Listening Mode
        continuous_frame = ttk.Labelframe(container, text="Listening Mode", pad=15)
        continuous_frame.pack(fill="x", pady=(0, 10))
        
        continuous_switch = ttk.Checkbutton(continuous_frame, text="Enable Continuous Listening", style="Switch.TCheckbutton", variable=self.continuous_listening_var)
        continuous_switch.pack(anchor="w")

        # Microphone Test Frame
        test_frame = ttk.Labelframe(container, text="Microphone Test", pad=15)
        test_frame.pack(fill="x")
        self.mic_test_button = ttk.Button(test_frame, text="Start Mic Test", style="Control.TButton", command=self.app.toggle_mic_test)
        self.mic_test_button.pack(pady=(0, 10))
        ttk.Label(test_frame, text="Input Level:").pack(anchor="w")
        self.mic_level_bar = ttk.Progressbar(test_frame, variable=self.mic_level_var, maximum=0.5, style="Level.Horizontal.TProgressbar")
        self.mic_level_bar.pack(fill="x", pady=(2, 10))
        ttk.Label(test_frame, text="Live Transcription:").pack(anchor="w")
        result_label = ttk.Label(test_frame, textvariable=self.mic_test_result_var, font=(self.FONT_FAMILY, 11, "italic"), foreground=self.COLOR_ACCENT, wraplength=500)
        result_label.pack(anchor="w", pady=5)



    def _apply_theme(self):
        style = ttk.Style()
        style.theme_use('clam')

        # --- Define Fonts ---
        font_L = font.Font(family=self.FONT_FAMILY, size=16, weight="bold")
        font_M = font.Font(family=self.FONT_FAMILY, size=11)
        font_S = font.Font(family=self.FONT_FAMILY, size=10)
        font_XS = font.Font(family=self.FONT_FAMILY, size=9)

        # --- Define new colors for button states ---
        COLOR_BTN_HOVER = "#3c4043"
        COLOR_BTN_PRESSED = "#5c6063"
        
        # --- General Widget Styling ---
        style.configure('.', background=self.COLOR_BG, foreground=self.COLOR_FG, font=font_M, borderwidth=0, focusthickness=0)
        style.configure('TFrame', background=self.COLOR_BG)
        style.configure('TLabel', background=self.COLOR_BG, foreground=self.COLOR_FG)
        style.configure('Title.TLabel', font=font_L)
        style.configure('Status.TLabel', font=font_S, foreground=self.COLOR_FG_MUTED)
        style.configure('Sidebar.TFrame', background=self.COLOR_SIDEBAR)
        style.configure('TLabelframe', background=self.COLOR_SIDEBAR, bordercolor=self.COLOR_FG_MUTED, borderwidth=1)
        style.configure('TLabelframe.Label', background=self.COLOR_SIDEBAR, foreground=self.COLOR_FG_MUTED, font=font_S)
        
        # --- Sidebar Button Styling ---
        style.configure('Sidebar.TButton', background=self.COLOR_SIDEBAR, font=font_M, padding=(20, 10), relief="flat")
        style.map('Sidebar.TButton', 
            background=[
                ('pressed', COLOR_BTN_PRESSED),
                ('active', COLOR_BTN_HOVER),
                ('selected', self.COLOR_BG)
            ]
        )
        
        # Create a new, dedicated style for the session list buttons that includes left-alignment.
        style.configure('Session.Sidebar.TButton', anchor="w", font=self.font_sidebar_button, background=self.COLOR_SIDEBAR, padding=(10, 5), relief="flat")
        style.map('Session.Sidebar.TButton', 
            background=[
                ('pressed', COLOR_BTN_PRESSED),
                ('active', COLOR_BTN_HOVER)
            ]
        )

        # --- THIS IS THE FIX ---
        # Create a new, dedicated style for the session list buttons that includes left-alignment
        style.configure('Session.Sidebar.TButton', anchor="w", font=self.font_sidebar_button, background=self.COLOR_SIDEBAR, padding=(10, 5), relief="flat")
        style.map('Session.Sidebar.TButton', 
            background=[
                ('pressed', COLOR_BTN_PRESSED),
                ('active', COLOR_BTN_HOVER)
            ]
        )
        # ------------------------

        # --- Main Control Button Styling (Listen, Stop Speech) ---
        style.configure('Control.TButton', background=self.COLOR_INPUT_BG, font=font_S, padding=5, relief="flat")
        style.map('Control.TButton', 
            background=[
                ('pressed', COLOR_BTN_PRESSED),
                ('active', COLOR_BTN_HOVER)
            ]
        )
        
        # Style for when the Listen button is active ("on")
        style.configure('Active.Control.TButton', background=self.COLOR_ACTIVE, foreground=self.COLOR_BG, font=font_S, padding=8, relief="flat")
        style.map('Active.Control.TButton', 
            background=[
                ('pressed', COLOR_BTN_PRESSED),
                ('active', self.COLOR_ACTIVE)
            ]
        )

        style.layout('Switch.TCheckbutton', [
            ('Checkbutton.padding', {'children': [
                ('Checkbutton.indicator', {'side': 'left', 'sticky': ''}),
                ('Checkbutton.focus', {'side': 'left', 'sticky': '', 'children': [
                    ('Checkbutton.label', {'sticky': 'nswe'})
                ]})
            ]})
        ])
        style.configure('Switch.TCheckbutton', font=font_M, indicatorbackground='gray', indicatordiameter=20)
        style.map('Switch.TCheckbutton',
            indicatorbackground=[('selected', self.COLOR_ACTIVE), ('!selected', self.COLOR_INPUT_BG)],
        )

        style.configure("Level.Horizontal.TProgressbar",
            troughcolor=self.COLOR_INPUT_BG,
            bordercolor=self.COLOR_SIDEBAR,
            background=self.COLOR_ACTIVE
        )

        # --- Other Widget Styles ---
        style.configure("TCombobox", fieldbackground=self.COLOR_INPUT_BG, background=self.COLOR_INPUT_BG, foreground=self.COLOR_FG, arrowcolor=self.COLOR_FG, relief="flat", padding=5)
        style.map('TCombobox', fieldbackground=[('readonly', self.COLOR_INPUT_BG)])
        style.configure("TNotebook", background=self.COLOR_BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.COLOR_BG, foreground=self.COLOR_FG_MUTED, padding=[10, 5], borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", self.COLOR_CONTENT_BOX)], foreground=[("selected", self.COLOR_ACCENT)])
        style.configure('TScrollbar', arrowcolor=self.COLOR_FG, troughcolor=self.COLOR_BG, background=self.COLOR_SIDEBAR, gripcount=0, borderwidth=0, relief="flat")

        style.configure('TEntry',
            fieldbackground=self.COLOR_INPUT_BG,
            foreground=self.COLOR_FG,
            insertbackground=self.COLOR_FG,
            borderwidth=2,
            relief="flat"
        )
        style.map('TEntry',
            bordercolor=[('focus', self.COLOR_ACCENT), ('!focus', self.COLOR_SIDEBAR)],
            lightcolor=[('focus', self.COLOR_ACCENT)]
        )