import webbrowser
import datetime
import os
import subprocess
import threading
import time
import re
import socket
import ctypes
from urllib.parse import quote_plus
import pywhatkit
try:
    from sentence_transformers import SentenceTransformer, util
except Exception:
    SentenceTransformer = None
    util = None

# === Import your custom handlers ===
from diagnostics import get_cpu_usage, get_ram_usage, get_battery_status, get_disk_usage
from powershell_cmds import empty_recycle_bin, open_settings
from app_control import open_app, close_app, list_processes
from memory import remember, recall, forget

import sys
from PyQt5.QtWidgets import QApplication
from camera_access import (
    CameraAccessError,
    list_cameras,
    scan_object_pipeline,
)

# === Chat AI model for fallback (lazy-loaded) ===
_MODEL = None
_MODEL_ERROR = None

def _get_semantic_model():
    global _MODEL, _MODEL_ERROR
    if _MODEL is not None or _MODEL_ERROR is not None:
        return _MODEL
    if SentenceTransformer is None or util is None:
        _MODEL_ERROR = "sentence-transformers not available"
        return None
    try:
        _MODEL = SentenceTransformer("paraphrase-MiniLM-L6-v2")
        return _MODEL
    except Exception as e:
        _MODEL_ERROR = str(e)
        return None

# === Local data files ===
NOTES_FILE = "notes.txt"
TASKS_FILE = "tasks.txt"

# === Shutdown handler ===
def shutdown_sam(speak):
    speak("Shutting down. Goodbye.")
    QApplication.quit()
    sys.exit(0)

# === Helpers ===
def run_powershell(script):
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "").strip()
            return False, error_text if error_text else "PowerShell command failed."
        return True, (result.stdout or "").strip()
    except Exception as e:
        return False, str(e)

VOLUME_PS_BASE = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace Audio {
  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"),
   InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int f(); int g(); int h(); int i();
    int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
    int j();
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int k(); int l(); int m(); int n();
    int SetMute(bool bMute, Guid pguidEventContext);
    int GetMute(out bool pbMute);
  }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"),
   InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice {
    int Activate(ref Guid id, int clsCtx, int activationParams, out IAudioEndpointVolume aev);
  }
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"),
   InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator {
    int f();
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint);
  }
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
  class MMDeviceEnumeratorComObject { }
  public class AudioManager {
    public static IAudioEndpointVolume GetAudioEndpointVolume() {
      IMMDeviceEnumerator enumerator = new MMDeviceEnumeratorComObject() as IMMDeviceEnumerator;
      IMMDevice device;
      enumerator.GetDefaultAudioEndpoint(0, 1, out device);
      IAudioEndpointVolume aev;
      Guid guid = typeof(IAudioEndpointVolume).GUID;
      device.Activate(ref guid, 23, 0, out aev);
      return aev;
    }
  }
}
'@
$vol = [Audio.AudioManager]::GetAudioEndpointVolume()
"""

# === INTENTS ===
INTENTS = {
    # Web & Media
    "search youtube": lambda speak, cmd: speak(handle_youtube_search(cmd)),
    "play on youtube": lambda speak, cmd: speak(handle_play_on_youtube(cmd)),
    "play music": lambda speak, cmd: (speak("Playing trending music on YouTube."), pywhatkit.playonyt("top trending music")),
    "play": lambda speak, cmd: speak(handle_play_query(cmd)),
    "open youtube": lambda speak, cmd: (speak("Opening YouTube."), webbrowser.open("https://youtube.com")),
    "open google": lambda speak, cmd: (speak("Opening Google."), webbrowser.open("https://google.com")),
    "what is the time": lambda speak, cmd: speak("The time is " + datetime.datetime.now().strftime("%I:%M %p")),
    "search google": lambda speak, cmd: handle_google_search(cmd, speak),
    "open netflix": lambda speak, cmd: (speak("Opening Netflix."), webbrowser.open("https://netflix.com")),
    "open spotify": lambda speak, cmd: (speak("Opening Spotify."), webbrowser.open("https://open.spotify.com")),
    "open github": lambda speak, cmd: (speak("Opening GitHub."), webbrowser.open("https://github.com")),
    "open site": lambda speak, cmd: speak(handle_open_target(cmd)),
    "draft email": lambda speak, cmd: speak(handle_email_draft(cmd)),
    "whatsapp message": lambda speak, cmd: speak(handle_whatsapp_draft(cmd)),
    "read clipboard": lambda speak, cmd: speak(read_clipboard()),

    # Camera
    "scan object": lambda speak, cmd: speak(handle_scan_object(cmd)),
    "list cameras": lambda speak, cmd: speak(handle_list_cameras()),
    "open camera": lambda speak, cmd: speak(handle_scan_object(cmd)),

    # System Status
    "check cpu usage": lambda speak, cmd: speak(get_cpu_usage()),
    "check ram usage": lambda speak, cmd: speak(get_ram_usage()),
    "battery status": lambda speak, cmd: speak(get_battery_status()),
    "disk usage": lambda speak, cmd: speak(get_disk_usage()),

    # System Tools
    "empty recycle bin": lambda speak, cmd: speak(empty_recycle_bin()),
    "open windows settings": lambda speak, cmd: speak(open_settings()),
    "open downloads": lambda speak, cmd: speak(open_downloads()),
    "open documents": lambda speak, cmd: speak(open_documents()),
    "lock screen": lambda speak, cmd: speak(lock_screen()),
    "sleep": lambda speak, cmd: speak(sleep_system()),
    "restart": lambda speak, cmd: speak(restart_system()),
    "take screenshot": lambda speak, cmd: speak(take_screenshot()),
    "show ip": lambda speak, cmd: speak(show_ip()),
    "uptime": lambda speak, cmd: speak(get_uptime()),
    "set volume": lambda speak, cmd: speak(handle_set_volume(cmd)),
    "mute": lambda speak, cmd: speak(set_mute(True)),
    "unmute": lambda speak, cmd: speak(set_mute(False)),
    "toggle wifi": lambda speak, cmd: speak(toggle_wifi()),
    "toggle bluetooth": lambda speak, cmd: speak(toggle_bluetooth()),
    "brightness up": lambda speak, cmd: speak(adjust_brightness(10)),
    "brightness down": lambda speak, cmd: speak(adjust_brightness(-10)),
    "kill process": lambda speak, cmd: speak(handle_kill_process(cmd)),

    # App Control
    "open app": lambda speak, cmd: speak(handle_open_target(cmd)),
    "close app": lambda speak, cmd: speak(close_app(cmd)),
    "list running tasks": lambda speak, cmd: speak(list_processes()),

    # Productivity
    "start timer": lambda speak, cmd: speak(handle_start_timer(cmd, speak)),
    "set reminder": lambda speak, cmd: speak(handle_set_reminder(cmd, speak)),
    "create note": lambda speak, cmd: speak(handle_create_note(cmd)),
    "task list": lambda speak, cmd: speak(read_task_list()),

    # Shutdown
    "shutdown": lambda speak, cmd: shutdown_sam(speak),
    "bye": lambda speak, cmd: shutdown_sam(speak),
    "turn off": lambda speak, cmd: shutdown_sam(speak),

    # Memory
    "remember something": lambda speak, cmd: handle_remember(cmd, speak),
    "recall something": lambda speak, cmd: handle_recall(cmd, speak),
    "forget something": lambda speak, cmd: handle_forget(cmd, speak),
}

# === Keyword patterns for intent detection ===
INTENT_PATTERNS = {
    # Web & Media
    "search youtube": ["search youtube", "youtube search", "search on youtube"],
    "play on youtube": ["on youtube", "play on youtube"],
    "play music": ["play music", "play song", "youtube music"],
    "play": ["play "],
    "open youtube": ["open youtube", "launch youtube", "youtube homepage", "youtube"],
    "open google": ["open google", "google homepage"],
    "search google": ["search google for", "search google", "search for", "google this", "look up"],
    "open netflix": ["open netflix", "netflix"],
    "open spotify": ["open spotify", "spotify"],
    "open github": ["open github", "github"],
    "draft email": ["draft email", "write email", "compose email", "send email", "email to", "email "],
    "whatsapp message": ["whatsapp message", "message on whatsapp", "send whatsapp", "whatsapp to", "whatsapp "],
    "read clipboard": ["read clipboard", "clipboard"],
    "what is the time": ["what is the time", "tell me the time", "current time"],

    # Camera
    "scan object": ["scan object", "scan this", "identify object", "recognize object", "detect object"],
    "list cameras": ["list cameras", "available cameras", "camera list"],
    "open camera": ["open camera", "camera on", "turn on camera"],
   

    # System Status
    "check cpu usage": ["cpu usage", "processor usage"],
    "check ram usage": ["ram usage", "memory usage"],
    "battery status": ["battery status", "battery level"],
    "disk usage": ["disk usage", "storage left"],

    # System Tools
    "empty recycle bin": ["empty recycle bin", "clear trash"],
    "open windows settings": ["windows settings", "open settings"],
    "open downloads": ["open downloads", "downloads folder", "download folder", "downloads"],
    "open documents": ["open documents", "documents folder", "document folder", "documents"],
    "lock screen": ["lock screen", "lock pc", "lock computer"],
    "sleep": ["sleep", "go to sleep"],
    "restart": ["restart", "reboot"],
    "take screenshot": ["take screenshot", "screenshot", "screen clip", "snip"],
    "show ip": ["show ip", "ip address", "local ip", "what is my ip"],
    "uptime": ["uptime", "system uptime", "how long running"],
    "set volume": ["set volume", "volume to", "volume "],
    "unmute": ["unmute", "turn sound on", "sound on"],
    "mute": ["mute", "mute volume"],
    "toggle wifi": ["toggle wifi", "wifi on", "wifi off"],
    "toggle bluetooth": ["toggle bluetooth", "bluetooth on", "bluetooth off"],
    "brightness up": ["brightness up", "increase brightness"],
    "brightness down": ["brightness down", "decrease brightness"],
    "kill process": ["kill process", "end process", "terminate process"],

    # App Control
    "open app": ["open app", "open application", "launch app", "launch application"],
    "close app": ["close app", "close application", "close "],
    "list running tasks": ["running tasks", "tasklist", "running programs", "list running tasks"],

    # Productivity
    "start timer": ["start timer", "set timer", "timer for"],
    "set reminder": ["set reminder", "remind me", "reminder to"],
    "create note": ["create note", "make note", "note this", "write note"],
    "task list": ["task list", "my tasks", "what's on my task list", "what is on my task list"],

    # Shutdown
    "shutdown": ["shutdown sam", "turn off", "shut down"],
    "bye": ["bye", "see you", "goodbye"],
    "turn off": ["turn off sam"],

    # Memory
    "remember something": ["remember", "my name is", "store this"],
    "recall something": ["what is my", "do you remember"],
    "forget something": ["forget", "remove memory"],
    "open site": ["open "],
}

# === Google Search ===
def handle_google_search(command, speak):
    command = command.lower()
    match = re.search(r"(search google for|search google|search for|google for|google this|look up)\s+(.+)", command)
    query = match.group(2).strip() if match else ""
    if not query and command.startswith("search "):
        query = command.split("search", 1)[-1].strip()
    if not query and command.startswith("google "):
        query = command.split("google", 1)[-1].strip()
    if query:
        speak(f"Searching Google for {query}.")
        pywhatkit.search(query)
    else:
        speak("Please specify what you want to search.")

# === Utility helpers ===
def extract_after_phrases(text, phrases):
    for phrase in phrases:
        if phrase in text:
            return text.split(phrase, 1)[-1].strip()
    return ""

def extract_after_phrases_ci(text, phrases):
    lower = text.lower()
    for phrase in phrases:
        index = lower.find(phrase)
        if index != -1:
            return text[index + len(phrase):].strip()
    return ""

def pluralize(value, word):
    return f"{value} {word}" + ("s" if value != 1 else "")

def format_duration(seconds):
    seconds = int(max(0, seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days:
        parts.append(pluralize(days, "day"))
    if hours:
        parts.append(pluralize(hours, "hour"))
    if minutes:
        parts.append(pluralize(minutes, "minute"))
    if seconds or not parts:
        parts.append(pluralize(seconds, "second"))
    return " ".join(parts)

def parse_duration_seconds(text):
    text = text.lower()
    total = 0
    matches = re.findall(r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)", text)
    unit_map = {
        "second": 1, "seconds": 1, "sec": 1, "secs": 1,
        "minute": 60, "minutes": 60, "min": 60, "mins": 60,
        "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600,
    }
    for amount, unit in matches:
        total += int(amount) * unit_map[unit]
    return total if total > 0 else None

def parse_time_string(time_str):
    if not time_str:
        return None
    time_str = time_str.strip().lower().replace(".", "")
    if time_str in ["noon", "midday"]:
        hour, minute = 12, 0
    elif time_str == "midnight":
        hour, minute = 0, 0
    else:
        time_str = re.sub(r"(\d)(am|pm)$", r"\1 \2", time_str)
        formats = ["%I:%M %p", "%I %p", "%H:%M"]
        parsed = None
        for fmt in formats:
            try:
                parsed = datetime.datetime.strptime(time_str, fmt)
                break
            except ValueError:
                continue
        if not parsed:
            return None
        hour, minute = parsed.hour, parsed.minute
    now = datetime.datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return target

# === Email & Messaging ===
def parse_email_parts(cmd):
    email_match = re.search(r"[\w\.-]+@[\w\.-]+\.\w+", cmd, re.IGNORECASE)
    recipient = email_match.group(0) if email_match else ""
    subject_match = re.search(r"subject\s+(.+?)(?:\s+(message|body|saying|content)\s+|$)", cmd, re.IGNORECASE)
    subject = subject_match.group(1).strip() if subject_match else ""
    body_match = re.search(r"(message|body|saying|content)\s+(.+)$", cmd, re.IGNORECASE)
    body = body_match.group(2).strip() if body_match else ""
    if not body and recipient and not subject_match:
        tail = cmd.split(recipient, 1)[-1].strip()
        body = tail
    return recipient, subject, body

def handle_email_draft(cmd):
    recipient, subject, body = parse_email_parts(cmd)
    if not recipient:
        return "Please include an email address."
    params = f"to={quote_plus(recipient)}"
    if subject:
        params += f"&su={quote_plus(subject)}"
    if body:
        params += f"&body={quote_plus(body)}"
    url = "https://mail.google.com/mail/?view=cm&fs=1&" + params
    webbrowser.open(url)
    return "Opening Gmail draft."

def handle_whatsapp_draft(cmd):
    phone_match = re.search(r"\+?\d[\d\s\-\(\)]{6,}\d", cmd, re.IGNORECASE)
    if not phone_match:
        return "Please include a phone number with country code."
    phone_raw = phone_match.group(0)
    phone = re.sub(r"\D", "", phone_raw)
    if len(phone) < 8:
        return "That phone number looks too short. Please include country code."
    message = extract_after_phrases_ci(cmd, ["message", "saying", "text", "that"])
    if not message:
        message = cmd.replace(phone_raw, "")
        for token in ["whatsapp", "message", "send"]:
            message = re.sub(rf"\b{re.escape(token)}\b", "", message)
        message = message.strip()
    url = f"whatsapp://send?phone={phone}"
    if message:
        url += f"&text={quote_plus(message)}"
    os.system(f'start "" "{url}"')
    if message:
        return f"Opening WhatsApp message to {phone}."
    return "Opening WhatsApp. Please type your message."

# === Web & Media ===
def handle_youtube_search(cmd):
    query = extract_after_phrases_ci(cmd, ["search youtube for", "search youtube", "youtube search", "search on youtube"])
    if not query:
        return "Please specify what you want to search on YouTube."
    url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
    webbrowser.open(url)
    return f"Searching YouTube for {query}."

def handle_play_on_youtube(cmd):
    match = re.search(r"play (.+?) on youtube", cmd, re.IGNORECASE)
    if not match:
        return "Tell me what to play on YouTube."
    query = match.group(1).strip()
    if not query:
        return "Tell me what to play on YouTube."
    pywhatkit.playonyt(query)
    return f"Playing {query} on YouTube."

def handle_play_query(cmd):
    query = re.sub(r"(?i)^play\s*", "", cmd).strip()
    if not query or query in ["music", "song"]:
        return "Tell me what to play."
    pywhatkit.playonyt(query)
    return f"Playing {query} on YouTube."

def handle_open_target(cmd):
    cmd_lower = cmd.lower()
    target = extract_after_phrases(cmd_lower, ["open", "launch"])
    if not target:
        return "What should I open?"
    target = target.strip()
    for prefix in ["site ", "website ", "web site ", "app ", "application "]:
        if target.startswith(prefix):
            target = target[len(prefix):].strip()
    if target in ["app", "application", "site", "website"]:
        return "Tell me which app or site to open."
    if target in ["downloads", "download", "downloads folder", "download folder"]:
        return open_downloads()
    if target in ["documents", "document", "documents folder", "document folder"]:
        return open_documents()
    if "settings" in target:
        return open_settings()

    site_map = {
        "youtube": "https://youtube.com",
        "google": "https://google.com",
        "netflix": "https://netflix.com",
        "spotify": "https://open.spotify.com",
        "github": "https://github.com",
    }
    if target in site_map:
        webbrowser.open(site_map[target])
        return f"Opening {target}."

    app_result = open_app(target)
    if "not recognized" not in app_result.lower() and "error" not in app_result.lower():
        return app_result

    url_target = target.replace(" ", "")
    if url_target.startswith("http://") or url_target.startswith("https://"):
        webbrowser.open(url_target)
        return f"Opening {url_target}."
    if "." not in url_target:
        url_target = f"{url_target}.com"
    webbrowser.open(f"https://{url_target}")
    return f"Opening {url_target}."

def read_clipboard():
    success, output = run_powershell("Get-Clipboard")
    if not success:
        return f"Could not read clipboard: {output}"
    if not output:
        return "Clipboard is empty."
    text = output.strip()
    if len(text) > 200:
        text = text[:200] + "..."
    return f"Clipboard says: {text}"

# === Camera ===
def handle_list_cameras():
    try:
        cameras = list_cameras()
        if not cameras:
            return "No cameras detected."
        return "Available cameras: " + ", ".join(str(c) for c in cameras)
    except CameraAccessError as e:
        return f"Camera error: {e}"
    except Exception as e:
        return f"Could not list cameras: {e}"

def handle_scan_object(cmd):
    cmd_lower = cmd.lower()
    search_online = any(term in cmd_lower for term in ["search", "online", "google", "find"])
    make_svg = not any(term in cmd_lower for term in ["no svg", "no vector"])
    try:
        result = scan_object_pipeline(
            detect=True,
            make_edges=True,
            make_svg=make_svg,
            search_online=search_online,
        )
        parts = [f"Captured image: {result.get('photo_path')}."]
        if "summary" in result:
            parts.append(result["summary"])
        if "edges_path" in result:
            parts.append(f"Edges saved: {result['edges_path']}.")
        if "svg_path" in result:
            parts.append(f"SVG saved: {result['svg_path']}.")
        if "detection_error" in result:
            parts.append(f"Detection note: {result['detection_error']}")
        if "search_query" in result:
            parts.append(f"Searching online for {result['search_query']}.")
        return " ".join(parts)
    except CameraAccessError as e:
        return f"Camera error: {e}"
    except Exception as e:
        return f"Camera scan failed: {e}"

# === System Tools & Status ===
def open_folder(path, label):
    try:
        os.startfile(path)
        return f"Opening {label}."
    except Exception as e:
        return f"Could not open {label.lower()}: {e}"

def open_downloads():
    path = os.path.join(os.path.expanduser("~"), "Downloads")
    return open_folder(path, "Downloads")

def open_documents():
    path = os.path.join(os.path.expanduser("~"), "Documents")
    return open_folder(path, "Documents")

def lock_screen():
    try:
        os.system("rundll32.exe user32.dll,LockWorkStation")
        return "Locking screen."
    except Exception as e:
        return f"Could not lock screen: {e}"

def sleep_system():
    try:
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return "Putting system to sleep."
    except Exception as e:
        return f"Could not sleep: {e}"

def restart_system():
    try:
        os.system("shutdown /r /t 0")
        return "Restarting now."
    except Exception as e:
        return f"Could not restart: {e}"

def take_screenshot():
    try:
        os.system("start ms-screenclip:")
        return "Opening screen snip."
    except Exception as e:
        return f"Could not open screen snip: {e}"

def get_local_ip():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return None

def show_ip():
    ip = get_local_ip()
    if ip:
        return f"Your local IP address is {ip}."
    return "I could not determine your local IP address."

def get_uptime():
    try:
        millis = ctypes.windll.kernel32.GetTickCount64()
        seconds = int(millis / 1000)
        return f"System uptime is {format_duration(seconds)}."
    except Exception as e:
        return f"Could not get uptime: {e}"

def set_volume_level(level):
    level = max(0, min(100, int(level)))
    scalar = level / 100.0
    script = VOLUME_PS_BASE + f"$vol.SetMasterVolumeLevelScalar({scalar}, [Guid]::Empty) | Out-Null"
    success, output = run_powershell(script)
    if success:
        return f"Setting volume to {level} percent."
    return f"Could not set volume: {output}"

def set_mute(mute):
    script = VOLUME_PS_BASE + f"$vol.SetMute({str(mute).lower()}, [Guid]::Empty) | Out-Null"
    success, output = run_powershell(script)
    if success:
        return "Muted." if mute else "Unmuted."
    return f"Could not change mute: {output}"

def handle_set_volume(cmd):
    match = re.search(r"set volume to (\d{1,3})", cmd, re.IGNORECASE)
    if not match:
        match = re.search(r"volume (\d{1,3})", cmd, re.IGNORECASE)
    if not match:
        return "Please tell me a volume level between 0 and 100."
    level = int(match.group(1))
    return set_volume_level(level)

def toggle_wifi():
    script = r"""
$adapter = Get-NetAdapter | Where-Object { $_.Name -match "Wi-Fi|Wireless" } | Select-Object -First 1
if (-not $adapter) { Write-Output "No Wi-Fi adapter found."; exit 1 }
if ($adapter.Status -eq "Up") {
  Disable-NetAdapter -Name $adapter.Name -Confirm:$false | Out-Null
  Write-Output "Wi-Fi disabled."
} else {
  Enable-NetAdapter -Name $adapter.Name -Confirm:$false | Out-Null
  Write-Output "Wi-Fi enabled."
}
"""
    success, output = run_powershell(script)
    if success:
        return output or "Toggled Wi-Fi."
    return f"Could not toggle Wi-Fi: {output}"

def toggle_bluetooth():
    script = r"""
$device = Get-PnpDevice -Class Bluetooth | Select-Object -First 1
if (-not $device) { Write-Output "No Bluetooth device found."; exit 1 }
if ($device.Status -eq "OK") {
  Disable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false | Out-Null
  Write-Output "Bluetooth disabled."
} else {
  Enable-PnpDevice -InstanceId $device.InstanceId -Confirm:$false | Out-Null
  Write-Output "Bluetooth enabled."
}
"""
    success, output = run_powershell(script)
    if success:
        return output or "Toggled Bluetooth."
    return f"Could not toggle Bluetooth: {output}"

def adjust_brightness(delta):
    script = f"""
$brightness = (Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightness).CurrentBrightness
$target = [Math]::Max(0, [Math]::Min(100, $brightness + {int(delta)}))
(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, $target) | Out-Null
Write-Output "Brightness set to $target."
"""
    success, output = run_powershell(script)
    if success:
        return output or "Brightness adjusted."
    return f"Could not adjust brightness: {output}"

def handle_kill_process(cmd):
    match = re.search(r"kill process (.+)", cmd, re.IGNORECASE)
    if not match:
        return "Tell me which process to kill."
    name = match.group(1).strip().strip('"').strip("'")
    if not name:
        return "Tell me which process to kill."
    if not name.lower().endswith(".exe"):
        name = name + ".exe"
    try:
        os.system(f"taskkill /f /im {name}")
        return f"Killing {name}."
    except Exception as e:
        return f"Could not kill process: {e}"

# === Productivity ===
def handle_start_timer(cmd, speak):
    seconds = parse_duration_seconds(cmd)
    if not seconds:
        return "Please specify a duration for the timer."
    def _timer():
        time.sleep(seconds)
        speak("Timer finished.")
    threading.Thread(target=_timer, daemon=True).start()
    return f"Timer started for {format_duration(seconds)}."

def handle_set_reminder(cmd, speak):
    cmd = cmd.lower()
    match_in = re.search(r"(set reminder to|remind me to)\s+(.+?)\s+in\s+(.+)", cmd)
    match_at = re.search(r"(set reminder to|remind me to)\s+(.+?)\s+at\s+(.+)", cmd)
    if match_in:
        reminder_text = match_in.group(2).strip()
        duration_text = match_in.group(3).strip()
        seconds = parse_duration_seconds(duration_text)
        if not seconds:
            return "Please specify a valid duration for the reminder."
        remind_at = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
        schedule_reminder(reminder_text, remind_at, speak)
        return f"Reminder set for {format_duration(seconds)} from now."
    if match_at:
        reminder_text = match_at.group(2).strip()
        time_text = match_at.group(3).strip()
        remind_at = parse_time_string(time_text)
        if not remind_at:
            return "I could not understand the reminder time."
        schedule_reminder(reminder_text, remind_at, speak)
        return f"Reminder set for {remind_at.strftime('%I:%M %p')}."
    return "Tell me what to remind you about and when."

def schedule_reminder(reminder_text, remind_at, speak):
    def _reminder():
        delay = (remind_at - datetime.datetime.now()).total_seconds()
        if delay > 0:
            time.sleep(delay)
        speak(f"Reminder: {reminder_text}.")
    threading.Thread(target=_reminder, daemon=True).start()

def handle_create_note(cmd):
    text = extract_after_phrases_ci(cmd, ["create note", "make note", "note this", "write note"])
    if not text:
        return "What should I write in the note?"
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        with open(NOTES_FILE, "a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {text}\n")
        return "Note saved."
    except Exception as e:
        return f"Could not save note: {e}"

def read_task_list():
    if not os.path.exists(TASKS_FILE):
        return "Your task list is empty."
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as file:
            lines = [line.strip() for line in file if line.strip()]
        if not lines:
            return "Your task list is empty."
        preview = lines[:10]
        text = "; ".join(preview)
        if len(lines) > 10:
            text += "; and more."
        return f"Your tasks are: {text}"
    except Exception as e:
        return f"Could not read task list: {e}"

# === Main Command Dispatcher ===
def execute_command(command, speak):
    raw_command = command
    command_lower = command.lower()
    best_match = get_best_intent_match(command_lower)

    if best_match:
        print(f"Matched intent: {best_match}")
        INTENTS[best_match](speak, raw_command)
    else:
        speak("i didnt understand that")

# === Intent Matcher ===
def get_best_intent_match(user_input):
    user_input = user_input.lower()

    # 1. Keyword match (fast and rule-based)
    for intent, triggers in INTENT_PATTERNS.items():
        for trigger in triggers:
            if trigger in user_input:
                return intent

    # 2. Fallback to semantic matching (if available)
    model = _get_semantic_model()
    if model is not None:
        sentences = list(INTENTS.keys())
        embeddings = model.encode(sentences + [user_input], convert_to_tensor=True)
        cosine_scores = util.pytorch_cos_sim(embeddings[-1], embeddings[:-1])[0]
        best_score = float(cosine_scores.max())
        best_index = int(cosine_scores.argmax())

        if best_score >= 0.6:
            return sentences[best_index]
    return None

# === Memory Handlers ===
def handle_remember(cmd, speak):
    if "my name is" in cmd:
        name = cmd.split("my name is")[-1].strip()
        remember("name", name)
        speak(f"Got it. I will remember your name is {name}.")
    elif "remember" in cmd:
        parts = cmd.split("remember")[-1].strip().split(" is ")
        if len(parts) == 2:
            key, value = parts
            remember(key.strip(), value.strip())
            speak(f"Okay, I’ll remember {key.strip()} is {value.strip()}.")
        else:
            speak("What should I remember?")
    else:
        speak("Sorry, I didn’t understand what to remember.")

def handle_recall(cmd, speak):
    for keyword in ["name", "favorite", "birthday"]:
        if keyword in cmd:
            value = recall(keyword)
            if value:
                speak(f"Your {keyword} is {value}.")
            else:
                speak(f"I don't know your {keyword} yet.")
            return
    speak("I’m not sure what you want me to recall.")

def handle_forget(cmd, speak):
    for keyword in ["name", "favorite", "birthday"]:
        if keyword in cmd:
            success = forget(keyword)
            if success:
                speak(f"Okay, I’ve forgotten your {keyword}.")
            else:
                speak(f"I didn’t have your {keyword} stored.")
            return
    speak("Tell me what to forget.")
