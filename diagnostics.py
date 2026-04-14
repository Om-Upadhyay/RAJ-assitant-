import psutil

def get_cpu_usage():
    usage = psutil.cpu_percent(interval=1)
    return f"Current CPU usage is {usage}%."

def get_ram_usage():
    memory = psutil.virtual_memory()
    return f"RAM usage is at {memory.percent}%."

def get_battery_status():
    battery = psutil.sensors_battery()
    if battery:
        plugged = "charging" if battery.power_plugged else "not charging"
        return f"Battery is at {battery.percent}% and is currently {plugged}."
    return "Battery status not available."

def get_disk_usage():
    usage = psutil.disk_usage('/')
    return f"Disk usage is at {usage.percent}% of total space."
