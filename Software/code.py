# License : GPLv2.0
# copyright (c) 2023  Dave Bailey
# Author: Dave Bailey (dbisu, @daveisu)
# Refactored: 2026 - Optimized Async Polling & Robust SD Routing

import supervisor
import os
import pwmio
import time
import digitalio
import board
import busio
import storage

# Core Ducky imports (brings in asyncio, button1, runScript, selectPayload, etc.)
from duckyinpython import *

# --- SYSTEM LOGGER ---
def log(level, msg):
    print(f"[{level}] {msg}")

log("INFO", "Initializing Hardware Auditing Device")

# Brief electrical stabilization for the RP2040 and SPI bus components
time.sleep(0.2)
supervisor.runtime.autoreload = False

# --- MICROSD HARDWARE INITIALIZATION ---
sd_mounted = False
try:
    log("INFO", "Configuring SPI interface (SCK:GP18, MOSI:GP19, MISO:GP16, CS:GP17)")
    spi = busio.SPI(clock=board.GP18, MOSI=board.GP19, MISO=board.GP16)
    
    try:
        # Prioritize the modern, fast C-based module
        import sdcardio
        sdcard = sdcardio.SDCard(spi, board.GP17)
        log("DEBUG", "Hardware mounted via sdcardio (Native C)")
    except ImportError:
        # Fallback to legacy pure Python module
        import adafruit_sdcard
        cs = digitalio.DigitalInOut(board.GP17)
        sdcard = adafruit_sdcard.SDCard(spi, cs)
        log("DEBUG", "Hardware mounted via adafruit_sdcard (Legacy)")

    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")
    sd_mounted = True
    log("SUCCESS", "MicroSD logical volume mounted at /sd")
    
except Exception as e:
    log("ERROR", f"SD Mount Failed: {e}")
    log("WARN", "Operating in degraded mode (Internal Flash Only)")

# --- HARDWARE PERIPHERALS ---
led = pwmio.PWMOut(board.LED, frequency=5000, duty_cycle=0)

# --- CORE LOGIC ---
async def wait_for_sd_ready_async(timeout_sec=2.0, interval=0.15):
    """
    Actively polls the SD card until the filesystem cache is fully built.
    It does not search for specific files; it only verifies read capability.
    """
    if not sd_mounted:
        return False

    log("INFO", "Polling SD Card for filesystem readiness...")
    start_time = time.monotonic()

    while (time.monotonic() - start_time) < timeout_sec:
        try:
            # A successful listdir() proves the FAT32 table is fully accessible
            os.listdir("/sd")
            log("SUCCESS", "SD Card filesystem is indexed and ready for read/write operations.")
            return True
        except OSError:
            pass # Filesystem still initializing, wait and retry
        
        # Yield control to the async event loop
        await asyncio.sleep(interval)
        
    log("WARN", "Timeout reached. SD Card filesystem failed to become ready.")
    return False

async def run_payload_on_startup():
    if getProgrammingStatus():
        log("INFO", "Setup Mode Active (Jumper detected). Halting execution.")
        return

    # 1. Kill-Switch Validation
    try:
        if "loot.bin" in os.listdir("/"):
            log("WARN", "Kill-switch file 'loot.bin' found on root. Halting.")
            return
    except OSError:
        pass

    # 2. Filesystem Stabilization Phase
    if sd_mounted:
        await wait_for_sd_ready_async(timeout_sec=2.0, interval=0.15)

    # 3. Payload Selection & Routing
    log("INFO", "Delegating file selection to selectPayload()...")
    
    # selectPayload() handles checking buttons and finding the right file 
    # across both /sd/ and / (Internal Memory) automatically.
    payload_path = selectPayload()

    # 4. Execution Pipeline
    if payload_path:
        log("SUCCESS", f"Locked onto target: {payload_path}")
        await runScript(payload_path)
    else:
        log("ERROR", "Execution aborted. No valid payloads found in any storage media.")

async def main_loop():
    log("INFO", "Booting asynchronous event loop")
    
    # Task grouping for concurrent execution
    await asyncio.gather(
        blink_pico_led(led),
        monitor_buttons(button1),
        monitor_led_changes(),
        run_payload_on_startup()
    )

# --- ENTRY POINT ---
try:
    asyncio.run(main_loop())
except Exception as e:
    log("FATAL", f"Kernel panic in main loop: {e}")
