import json
import os

MEMORY_FILE = "memory.json"

# Load memory from file
def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as file:
            return json.load(file)
    return {}

# Save memory to file
def save_memory(memory):
    with open(MEMORY_FILE, "w") as file:
        json.dump(memory, file, indent=4)

# Set a value
def remember(key, value):
    memory = load_memory()
    memory[key] = value
    save_memory(memory)

# Get a value
def recall(key):
    memory = load_memory()
    return memory.get(key, None)

# Forget a value
def forget(key):
    memory = load_memory()
    if key in memory:
        del memory[key]
        save_memory(memory)
        return True
    return False
