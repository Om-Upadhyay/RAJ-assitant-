import os
import shutil

def create_folder(name):
    try:
        os.makedirs(name)
        return f"Folder '{name}' created successfully."
    except FileExistsError:
        return f"Folder '{name}' already exists."
    except Exception as e:
        return f"Error creating folder: {e}"

def create_file(name):
    try:
        with open(name, 'w') as f:
            f.write("")  # Creates empty file
        return f"File '{name}' created successfully."
    except Exception as e:
        return f"Error creating file: {e}"

def delete_file(name):
    try:
        os.remove(name)
        return f"File '{name}' deleted successfully."
    except FileNotFoundError:
        return f"File '{name}' not found."
    except Exception as e:
        return f"Error deleting file: {e}"
