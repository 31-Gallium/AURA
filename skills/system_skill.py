# skills/system_skill.py
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
    try:
        level_int = int(re.search(r'\d+', volume).group())
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume_control = cast(interface, POINTER(IAudioEndpointVolume))
        volume_scalar = max(0.0, min(1.0, level_int / 100.0))
        volume_control.SetMasterVolumeLevelScalar(volume_scalar, None)
        return f"I've set the system volume to {level_int} percent."
    except Exception as e:
        app.queue_log(f"Error setting system volume: {e}")
        return "I couldn't change the system volume."

def set_app_volume(app, app_name, level, **kwargs):
    """Sets a specific application's volume by its name."""
    try:
        level_int = int(re.search(r'\d+', level).group())
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
        app.queue_log(f"Error setting app volume: {e}")
        return f"I ran into an error trying to change {app_name}'s volume."

def list_audio_sessions(app, **kwargs):
    """Logs all current audio session for debugging."""
    try:
        sessions = AudioUtilities.GetAllSessions()
        if not sessions:
            return "I don't see any applications playing audio right now."
        session_names = [s.Process.name() for s in sessions if s.Process]
        return f"Current audio sessions include: {', '.join(session_names)}."
    except Exception as e:
        app.queue_log(f"Error listing audio sessions: {e}")
        return "I ran into an error trying to list the audio sessions."

def set_system_brightness(app, level, **kwargs):
    """Sets the system display brightness to a specific level (0-100)."""
    try:
        level_int = int(re.search(r'\d+', level).group())
        sbc.set_brightness(level_int)
        return f"Brightness set to {level_int} percent."
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
    key_to_press = next((val for key, val in key_map.items() if key in action_lower), None)
    if not key_to_press: return "I don't know how to do that action."
    try:
        pyautogui.press(key_to_press)
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

def register():
    """Registers all system-related commands with flexible regex patterns."""
    return {
        'set_system_volume': {
            'handler': set_system_volume,
            'regex': r'\bset(?: the)?(?: system)? volume to (\d{1,3})\b',
            'params': ['volume'],
            'description': "Sets the computer's master system volume to a percentage (0-100)."
        },
        'set_app_volume': {
            'handler': set_app_volume,
            'regex': r'\bset(?: the)? volume for (.+?) to (\d{1,3})\b',
            'params': ['app_name', 'level'],
            'description': "Sets the volume for a specific application that is playing audio."
        },
        'set_brightness': {
            'handler': set_system_brightness,
            'regex': r'\bset(?: screen)? brightness to (\d{1,3})\b',
            'params': ['level'],
            'description': "Sets the screen brightness to a percentage (0-100)."
        },
        'control_power': {
            'handler': control_power,
            'regex': r'\b(shut down|restart|sleep)\b(?: the)?(?: computer|pc|system)?',
            'params': ['action'],
            'description': "Shuts down, restarts, or puts the computer to sleep."
        },
        'list_processes': {
            'handler': list_processes,
            'regex': r'\blist(?: all| running)? processes(?: by (memory))?\b',
            'params': ['sort_by'],
            'description': "Lists running computer processes, optionally sorted by memory usage."
        },
        'get_system_stats': {
            'handler': get_system_stats,
            'regex': r'\b(what is|check) system status\b',
            'params': [],
            'description': "Reports the current CPU and RAM usage."
        },
        'get_battery_status': {
            'handler': get_battery_status,
            'regex': r'\b(what is|check)(?: the)? battery status\b',
            'params': [],
            'description': "Reports the current battery level and charging status."
        },
        'save_screenshot': {
            'handler': save_screenshot,
            'regex': r'\btake a screenshot\b',
            'params': [],
            'description': "Takes a screenshot of the entire screen and saves it to the desktop."
        },
        'empty_recycle_bin': {
            'handler': empty_recycle_bin,
            'regex': r'\bempty(?: the)? recycle bin\b',
            'params': [],
            'description': "Permanently deletes all items in the Windows Recycle Bin."
        },
        'list_audio_sessions': {
            'handler': list_audio_sessions,
            'regex': r'\blist(?: active)? audio sessions\b',
            'params': [],
            'description': "Lists all applications currently making sound."
        },
        'control_wifi': {
            'handler': control_wifi,
            'regex': r'\bturn wi-fi (on|off)\b',
            'params': ['state'],
            'description': "Turns the computer's Wi-Fi on or off."
        },
        'control_media': {
            'handler': control_media,
            'regex': r'\b(play|pause|resume|next|previous|mute)\b(?: the)?(?: media|music|track|song)?',
            'params': ['action'],
            'description': "Controls media playback (play, pause, next/previous track, mute)."
        },
        'get_disk_space': {
            'handler': get_disk_space,
            'regex': r'\b(check|how much) disk space(?: on drive ([a-zA-Z]))?\b',
            'params': ['drive'],
            'description': "Reports the free disk space on a specified drive (defaults to C:)."
        },
        'get_ip_address': {
            'handler': get_ip_address,
            'regex': r'\b(what is|get)(?: my)? ip address\b',
            'params': [],
            'description': "Finds and reports the computer's local IP address."
        }
    }