# boot.py - Hardware USB Profile Manager
# Executes BEFORE USB enumeration to the host PC

import board
import digitalio
import storage

# --- CONFIGURATION ---
# This MUST be the same pin used for 'progStatusPin' in duckyinpython.py
# Standard is GP0. When connected to GND, it activates DEV MODE.
SETUP_PIN = board.GP0

def is_dev_mode_active() -> bool:
    """
    Checks the physical hardware jumper.
    Returns True if the jumper is connected to GND (Dev Mode).
    Returns False if the pin is floating (Attack Mode).
    """
    jumper = digitalio.DigitalInOut(SETUP_PIN)
    jumper.switch_to_input(pull=digitalio.Pull.UP)
    
    # If connected to GND, value is False. We invert it for readability.
    is_dev = not jumper.value 
    
    jumper.deinit() # Clean up hardware resource immediately
    return is_dev

def configure_stealth_profile():
    print("[BOOT] Evaluating Hardware Security Profile...")
    
    if is_dev_mode_active():
        # --- DEVELOPMENT MODE ---
        # Jumper is present. We need to be able to edit files.
        print("[BOOT] Dev Mode Active: USB Mass Storage ENABLED.")
        # We do nothing here, USB is visible by default.
    else:
        # --- ATTACK MODE ---
        # Jumper is removed. Hide tracks.
        print("[BOOT] Attack Mode Active: USB Mass Storage DISABLED.")
        storage.disable_usb_drive()
        
        # Optional: Disable Serial Console to be 100% invisible
        import usb_cdc
        usb_cdc.disable()

# Execute before host connection
configure_stealth_profile()