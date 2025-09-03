# Developed by SanStudio
# Auto Typer Tool - Reads text from a file and types it out automatically.

import pyautogui
import keyboard
import time
import random
import os

# --- Configuration ---
INPUT_FILE = 'input.txt'    # The name of the text file to read from.
START_HOTKEY = 'f8'         # Press this key to start/resume typing.
STOP_HOTKEY = 'esc'         # Press this key to stop/pause typing.

# Typing Speed Settings
DEFAULT_DELAY = 0.05        # Default delay between keystrokes in seconds.
USE_RANDOM_DELAY = True     # Set to True for a more natural, human-like typing speed.
RANDOM_DELAY_MIN = 0.03     # Minimum delay for random speed (seconds).
RANDOM_DELAY_MAX = 0.12     # Maximum delay for random speed (seconds).

# Feature Toggles
SKIP_EMPTY_LINES = True     # Set to True to ignore empty lines in the text file.
LOOP_TYPING = False         # Set to True to loop the text indefinitely.
PASTE_MODE = False          # Set to True to paste each line instantly instead of typing char by char.

# --- Global Variables ---
is_typing = False
last_mod_time = 0
text_to_type = []

def check_and_load_file():
    """
    Checks if the input file has been modified since the last read.
    If it has, it reloads the content into the global 'text_to_type' list.
    If the file does not exist, it creates it with default content.
    """
    global last_mod_time, text_to_type
    try:
        current_mod_time = os.path.getmtime(INPUT_FILE)
        if current_mod_time != last_mod_time:
            print(f"'{INPUT_FILE}' has been updated. Reloading content...")
            with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                text_to_type = f.readlines()
            last_mod_time = current_mod_time
            print("Content reloaded successfully.")
    except FileNotFoundError:
        print(f"'{INPUT_FILE}' not found. Creating it with default content...")
        try:
            with open(INPUT_FILE, 'w', encoding='utf-8') as f:
                f.write("Hello! This is a default text.\n\n")
                f.write("Please edit this input.txt file with the text you want to type, then save it.\n")
                f.write("The script will automatically detect the changes.\n")
            
            # After creating, load the content
            last_mod_time = os.path.getmtime(INPUT_FILE)
            with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                text_to_type = f.readlines()
            print(f"'{INPUT_FILE}' created. Please edit it and then press {START_HOTKEY} when you are ready.")
        except Exception as e:
            print(f"Error: Could not create or read '{INPUT_FILE}': {e}")
            text_to_type = []
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
        text_to_type = []

def start_typing():
    """Sets the global typing flag to True and prints a status message."""
    global is_typing
    if not is_typing:
        print("Starting typing... (Press ESC to stop)")
        # A small delay to allow the user to switch to the target window.
        time.sleep(0.5)
        is_typing = True

def stop_typing():
    """Sets the global typing flag to False and prints a status message."""
    global is_typing
    if is_typing:
        is_typing = False
        print("Typing stopped. (Press F8 to resume)")

def perform_typing():
    """
    Main typing loop. It types the content from the 'text_to_type' list
    based on the configured settings.
    """
    global is_typing
    
    while True: # Outer loop for the LOOP_TYPING feature
        check_and_load_file() # Check for file updates at the start of each loop
        if not text_to_type:
            # If the file is empty or not found, wait before retrying.
            time.sleep(1)
            continue
            
        for line in text_to_type:
            # This loop allows typing to be stopped and resumed mid-line.
            for char in line:
                if not is_typing:
                    return # Exit the function if typing is stopped.

                pyautogui.write(char, interval=get_delay())
            
            # Handle different modes after a line is complete
            if is_typing:
                if PASTE_MODE:
                    # Strip newline characters for clean pasting
                    clean_line = line.strip()
                    pyautogui.write(clean_line)
                
                if SKIP_EMPTY_LINES and not line.strip():
                    continue

                # Press Enter to go to the next line, simulating paragraph breaks.
                pyautogui.press('enter')
                time.sleep(0.1) # small pause after enter

        if not LOOP_TYPING:
            print("Finished typing the content.")
            stop_typing() # Stop automatically if not looping
            break # Exit the outer while loop
        else:
            print("Looping back to the beginning of the file.")
            time.sleep(1) # A brief pause before starting the loop again.


def get_delay():
    """Returns the appropriate delay based on configuration."""
    if USE_RANDOM_DELAY:
        return random.uniform(RANDOM_DELAY_MIN, RANDOM_DELAY_MAX)
    return DEFAULT_DELAY

def main():
    """Main function to set up hotkeys and run the primary loop."""
    print("Auto Typer is running.")
    print(f"Press '{START_HOTKEY}' to start typing.")
    print(f"Press '{STOP_HOTKEY}' to stop at any time.")
    print("Place your cursor in the desired text box.")
    
    # Set up the hotkeys
    keyboard.add_hotkey(START_HOTKEY, start_typing)
    keyboard.add_hotkey(STOP_HOTKEY, stop_typing)
    
    # Initial file load
    check_and_load_file()

    try:
        while True:
            if is_typing:
                perform_typing()
            # A non-blocking sleep to prevent high CPU usage.
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nScript terminated by user.")
    finally:
        # Clean up hotkeys
        keyboard.remove_all_hotkeys()
        print("Hotkeys removed. Exiting.")


if __name__ == "__main__":
    main()

