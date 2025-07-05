# In skills/system_skill.py
import os
import re
import subprocess
import psutil
import winshell
import pyautogui
from datetime import datetime
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CLSCTX_ALL
from ctypes import cast, POINTER
import screen_brightness_control as sbc
import socket

try:
    from pytesseract import pytesseract
except ImportError:
    pytesseract = None

# --- Handler Functions ---

def set_system_volume(app, volume, **kwargs):
    """Sets the master system volume to a specific level (0-100)."""
    log_callback = app.queue_log
    try:
        level_int = int(volume)
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume_control = cast(interface, POINTER(IAudioEndpointVolume))
        volume_scalar = max(0.0, min(1.0, level_int / 100.0))
        volume_control.SetMasterVolumeLevelScalar(volume_scalar, None)
        return f"I've set the system volume to {level_int} percent."
    except Exception as e:
        log_callback(f"Error setting system volume: {e}")
        return "I couldn't change the system volume."

def set_app_volume(app, app_name, level, **kwargs):
    """Sets a specific application's volume by its name."""
    log_callback = app.queue_log
    try:
        level_int = int(level)
        sessions = AudioUtilities.GetAllSessions()
        target_app_lower = app_name.lower().strip()
        for session in sessions:
            if (session.Process and target_app_lower in session.Process.name().lower()) or \
               (session.DisplayName and target_app_lower in session.DisplayName.lower()):
                volume = session.SimpleAudioVolume
                volume.SetMasterVolume(max(0.0, min(1.0, level_int / 100.0)), None)
                return f"I've set {session.DisplayName or app_name}'s volume to {level_int} percent."
        return f"I couldn't find an app named {app_name} playing any audio."
    except Exception as e:
        log_callback(f"Error setting app volume: {e}")
        return f"I ran into an error trying to change {app_name}'s volume."

def list_audio_sessions(app, **kwargs):
    """Logs all current audio session for debugging."""
    log_callback = app.queue_log
    try:
        sessions = AudioUtilities.GetAllSessions()
        if not sessions:
            return "I don't see any applications playing audio right now."
        log_callback("--- Active Audio Sessions ---")
        for session in sessions:
            process_name = "N/A"
            if session.Process:
                process_name = session.Process.name()
            log_callback(f"DisplayName: '{session.DisplayName}' | Process: '{process_name}'")
        log_callback("-----------------------------")
        return "I've listed all active audio applications in the log for you."
    except Exception as e:
        log_callback(f"Error listing audio sessions: {e}")
        return "I ran into an error trying to list the audio sessions."

def set_system_brightness(app, level, **kwargs):
    """Sets the system display brightness to a specific level (0-100)."""
    try:
        sbc.set_brightness(int(level))
        return f"Brightness set to {level} percent."
    except Exception as e:
        app.queue_log(f"Error setting brightness: {e}")
        return "I couldn't change the screen brightness."

def control_power(app, action, **kwargs):
    """Controls system power states like shutdown and restart."""
    action = action.lower().strip()
    if "shut down" in action:
        os.system("shutdown /s /t 1")
        return "Shutting down."
    elif "restart" in action:
        os.system("shutdown /r /t 1")
        return "Restarting."
    elif "sleep" in action:
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Going to sleep."
    return "I can't perform that power action."

def open_app(app, alias, **kwargs):
    """Opens an application using its configured alias."""
    app_alias = alias.lower().strip()
    app_paths = app.config.get("app_paths", {})
    if app_alias not in app_paths:
        return f"I don't have an app called '{alias}' in my settings."
    path_info = app_paths[app_alias]
    try:
        if isinstance(path_info, dict) and "path" in path_info:
            path = path_info.get("path")
            profile = path_info.get("profile")
            command_to_run = f'"{path}" --profile-directory="{profile}"' if profile else f'"{path}"'
            subprocess.Popen(command_to_run, shell=True)
        else:
            os.startfile(path_info)
        return f"Opening {alias}."
    except Exception as e:
        app.queue_log(f"Failed to open '{alias}': {e}")
        return f"I ran into an error trying to open {alias}."

def list_processes(app, sort_by=None, **kwargs):
    """Lists running processes, with an option to sort by memory."""
    try:
        procs = [p.info for p in psutil.process_iter(['name', 'memory_info']) if p.info['name']]
        header = "Here are some of the currently running processes:"
        if sort_by and 'memory' in sort_by:
            procs.sort(key=lambda p: p['memory_info'].rss, reverse=True)
            header = "Here are the top 5 processes by memory usage:"
        response_parts = [header]
        for p in procs[:5]:
            memory_mb = p['memory_info'].rss / (1024 * 1024)
            response_parts.append(f"{p['name']}, using {memory_mb:.1f} megabytes.")
        return " ".join(response_parts)
    except Exception as e:
        app.queue_log(f"Error listing processes: {e}")
        return "I had trouble getting the list of running processes."

def terminate_process(app, process_name, **kwargs):
    """Terminates a specific process by name."""
    target_name = process_name.lower().strip()
    blacklist = {'svchost.exe', 'lsass.exe', 'wininit.exe', 'csrss.exe', 'smss.exe', 'winlogon.exe', 'services.exe', 'explorer.exe'}
    if target_name in blacklist:
        return f"I cannot terminate {target_name} as it is a critical system process."
        
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'].lower() == target_name:
            proc.terminate()
            return f"Okay, I have terminated the process {target_name}."
    return f"I could not find a running process named {target_name}."

def empty_recycle_bin(app, **kwargs):
    """Empties the Windows Recycle Bin."""
    try:
        winshell.recycle_bin().empty(confirm=False, show_progress=False, sound=False)
        return "The recycle bin has been emptied."
    except Exception as e:
        app.queue_log(f"Error emptying recycle bin: {e}")
        return "I couldn't empty the recycle bin."

def control_wifi(app, state, **kwargs):
    """Turns Wi-Fi on or off using netsh commands."""
    action = "enabled" if state.lower() == "on" else "disabled"
    command = f'netsh interface set interface "Wi-Fi" admin={action}'
    try:
        subprocess.run(command, shell=True, check=True, capture_output=True)
        return f"Wi-Fi has been turned {state}."
    except Exception as e:
        app.queue_log(f"Failed to control Wi-Fi: {e}. This may require admin privileges.")
        return "I couldn't change the Wi-Fi status. This might require administrator privileges."

def control_media(app, action, **kwargs):
    """Controls media playback by simulating media keys."""
    key_map = {"play": "playpause", "pause": "playpause", "resume": "playpause", "next": "nexttrack", "previous": "prevtrack", "mute": "volumemute"}
    action_lower = action.lower().strip()
    if action_lower not in key_map: return "I don't know how to do that action."
    try:
        pyautogui.press(key_map[action_lower])
        return f"{action.capitalize()}."
    except Exception as e:
        app.queue_log(f"Error with media control: {e}")
        return "I had trouble controlling the media."

def get_system_stats(app, **kwargs):
    """Retrieves and formats current CPU and RAM usage."""
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_info = psutil.virtual_memory()
    return f"CPU usage is at {cpu_usage} percent, and RAM usage is at {memory_info.percent} percent."

def get_battery_status(app, **kwargs):
    """Checks and reports the system's battery status."""
    battery = psutil.sensors_battery()
    if not battery: return "I couldn't detect a battery in this system."
    percent = int(battery.percent)
    is_charging = "and charging." if battery.power_plugged else "and not charging."
    return f"The battery is at {percent} percent {is_charging}"

def get_disk_space(app, drive=None, **kwargs):
    """Checks and reports free disk space."""
    target_drive = (drive.upper() + ":\\") if drive else "C:\\"
    try:
        usage = psutil.disk_usage(target_drive)
        free_gb = usage.free / (1024**3)
        return f"The {target_drive} drive has {free_gb:.1f} gigabytes of free space."
    except FileNotFoundError:
        return f"I'm sorry, I couldn't find a drive named {target_drive}."
    except Exception as e:
        app.queue_log(f"Error getting disk space: {e}")
        return "I had trouble checking the disk space."

def get_ip_address(app, **kwargs):
    """Retrieves the local IP address."""
    try:
        return f"Your local IP address is {socket.gethostbyname(socket.gethostname())}."
    except Exception as e:
        app.queue_log(f"Error fetching IP address: {e}")
        return "I was unable to determine your local IP address."

def save_screenshot(app, **kwargs):
    """Takes a screenshot and saves it to the desktop."""
    try:
        desktop_path = os.path.join(os.path.expanduser('~'), 'Desktop')
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        file_name = f"AURA_Screenshot_{timestamp}.png"
        pyautogui.screenshot(os.path.join(desktop_path, file_name))
        return f"I've saved a screenshot to your desktop named {file_name}."
    except Exception as e:
        app.queue_log(f"Error saving screenshot: {e}")
        return "I had a problem trying to save the screenshot."

def scan_screen_for_text(app, query=None, **kwargs):
    """Uses OCR to find text on the screen."""
    if not pytesseract: return "I can't scan the screen because the required OCR library is missing."
    tesseract_path = app.config.get("tesseract_cmd_path")
    if not tesseract_path or not os.path.exists(tesseract_path):
        return "My OCR engine is not configured. Please set the Tesseract path in the settings."
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
    try:
        extracted_text = pytesseract.image_to_string(pyautogui.screenshot())
        if not query:
            return f"I was able to read the following text: {extracted_text[:300]}..."
        if query.lower() in extracted_text.lower():
            return f"Yes, I found the text '{query}' on your screen."
        else:
            return f"No, I could not find '{query}' on your screen."
    except Exception as e:
        app.queue_log(f"Error during screen scan: {e}")
        return "I ran into an error while trying to scan the screen."

def get_current_date_and_time(app, **kwargs):
    """Gets and formats the current date and time."""
    now = datetime.now()
    formatted_datetime = now.strftime("%A, %B %d, %Y at %I:%M %p.")
    return f"The current date and time is {formatted_datetime}"

def register():
    """Registers all system-related commands with flexible regex patterns."""
    return {
        'set_system_volume': {
            'handler': set_system_volume,
            'regex': r'set(?: the)?(?: system)? volume to (\d+)',
            'params': ['volume']
        },
        'set_app_volume': {
            'handler': set_app_volume,
            'regex': r'set(?: the)?(?: volume for| volume of) (.+?) to (\d+)',
            'params': ['app_name', 'level']
        },
        'set_brightness': {
            'handler': set_system_brightness,
            'regex': r'set(?: the)?(?: screen)? brightness to (\d+)',
            'params': ['level']
        },
        'control_power': {
            'handler': control_power,
            'regex': r'(shut down|restart|sleep)(?: the)?(?: computer|pc|system)?',
            'params': ['action']
        },
        'open_app': {
            'handler': open_app,
            'regex': r'(?:open|launch) (.+)',
            'params': ['alias']
        },
        'list_processes': {
            'handler': list_processes,
            'regex': r'list(?: all| running)? processes(?: by (memory))?',
            'params': ['sort_by']
        },
        'terminate_process': {
            'handler': terminate_process,
            'regex': r'(?:terminate|end process) (.+)',
            'params': ['process_name']
        },
        'get_system_stats': {
            'handler': get_system_stats,
            'regex': r'(?:what is|check) system status',
            'params': []
        },
        'get_battery_status': {
            'handler': get_battery_status,
            'regex': r'(?:what is|check)(?: the)? battery status',
            'params': []
        },
        'save_screenshot': {
            'handler': save_screenshot,
            'regex': r'take a screenshot',
            'params': []
        },
        'empty_recycle_bin': {
            'handler': empty_recycle_bin,
            'regex': r'empty(?: the)? recycle bin',
            'params': []
        },
        'list_audio_sessions': {
            'handler': list_audio_sessions,
            'regex': r'list(?: active)? audio sessions',
            'params': []
        },
        'control_wifi': {
            'handler': control_wifi,
            'regex': r'turn wi-fi (on|off)',
            'params': ['state']
        },
        'control_media': {
            'handler': control_media,
            'regex': r'(play|pause|resume|next|previous|mute)(?: the)?(?: media|music|track)?',
            'params': ['action']
        },
        'get_disk_space': {
            'handler': get_disk_space,
            'regex': r'(?:check|how much) disk space(?: on drive ([a-zA-Z]))?',
            'params': ['drive']
        },
        'get_ip_address': {
            'handler': get_ip_address,
            'regex': r'(?:what is|get)(?: my)? ip address',
            'params': []
        },
        'scan_screen_for_text': {
            'handler': scan_screen_for_text,
            'regex': r'scan(?: the)? screen(?: for (.+))?',
            'params': ['query']
        },
        'get_current_date_and_time': {
            'handler': get_current_date_and_time,
            'regex': r'what(?: is|\'s)(?: the)? current (date and time|time and date|time|date)',
            'params': []
        }
    }