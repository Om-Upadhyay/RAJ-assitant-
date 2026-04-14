import os
import subprocess

def open_app(app_name):
    try:
        if "notepad" in app_name:
            os.system("notepad")
        elif "chrome" in app_name:
            os.system("start chrome")
        elif "vscode" in app_name or "code" in app_name:
            os.system("code")
        else:
            return "App not recognized. Try 'open notepad' or 'open chrome'."
        return f"{app_name} opened successfully."
    except Exception as e:
        return f"Error opening app: {e}"

def close_app(app_name):
    try:
        if "notepad" in app_name:
            os.system("taskkill /f /im notepad.exe")
        elif "chrome" in app_name:
            os.system("taskkill /f /im chrome.exe")
        elif "vscode" in app_name or "code" in app_name:
            os.system("taskkill /f /im Code.exe")
        else:
            return "App not recognized. Try 'close notepad' or 'close chrome'."
        return f"{app_name} closed successfully."
    except Exception as e:
        return f"Error closing app: {e}"

def list_processes():
    try:
        result = subprocess.check_output("tasklist", shell=True, text=True)
        return result[:1000]  # Just the first chunk
    except Exception as e:
        return f"Error listing processes: {e}"
