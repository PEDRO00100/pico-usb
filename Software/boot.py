# boot.py - Hardware USB Profile & Fingerprint Manager
# Executes BEFORE USB enumeration to the host PC

import board
import digitalio
import storage
import supervisor
import usb_cdc
import usb_midi
import usb_hid

SETUP_PIN = board.GP0

def is_dev_mode_active() -> bool:
    """Safely reads hardware jumper without locking GPIO resources."""
    try:
        with digitalio.DigitalInOut(SETUP_PIN) as jumper:
            jumper.switch_to_input(pull=digitalio.Pull.UP)
            return not jumper.value
    except Exception:
        return False

def configure_usb_profile():
    supervisor.set_usb_identification(
        vid=0x1209,
        pid=0x0001,
        manufacturer="Generic",
        product="USB Keyboard"
    )
    
    if is_dev_mode_active():
        print("[BOOT] DEV MODE: Storage & Serial CDC enabled.")
        return

    # 2. Attack Mode: Minimize USB fingerprint to HID only
    print("[BOOT] ATTACK MODE: Stealth generic HID profile active.")
    storage.disable_usb_drive()
    usb_cdc.disable()
    usb_midi.disable()
    
    # 3. Configure HID interface
    usb_hid.enable(
        (usb_hid.Device.KEYBOARD, usb_hid.Device.CONSUMER_CONTROL),
        boot_device=1
    )
    try:
        usb_hid.set_interface_name("USB Keyboard")
    except AttributeError:
        pass

configure_usb_profile()