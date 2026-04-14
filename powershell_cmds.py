import os
import subprocess

def empty_recycle_bin():
    try:
        os.system("PowerShell.exe Clear-RecycleBin -Force")
        return "Recycle Bin emptied successfully."
    except Exception as e:
        return f"Failed to empty recycle bin: {e}"

def open_settings():
    try:
        os.system("start ms-settings:")
        return "Opening Windows Settings."
    except Exception as e:
        return f"Could not open settings: {e}"
