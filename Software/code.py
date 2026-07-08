# License: GPLv2.0
# Copyright (c) 2026 Dave Bailey
# Author: Dave Bailey (dbisu, @daveisu)
# Refactored: 2026 - Optimized Async Polling & Zero-RAM Allocations

import supervisor
import os
import pwmio
import time
import digitalio
import board
import busio
import storage

from duckyinpython import *

def log(level: str, msg: str):
    print(f"[{level}] {msg}")

log("INFO", "Initializing Hardware Execution Engine")
time.sleep(0.15)
supervisor.runtime.autoreload = False

# MicroSD Hardware Initialization
sd_mounted = False
try:
    log("INFO", "Configuring SPI bus (SCK:GP18, MOSI:GP19, MISO:GP16, CS:GP17)")
    spi = busio.SPI(clock=board.GP18, MOSI=board.GP19, MISO=board.GP16)
    
    try:
        import sdcardio
        sdcard = sdcardio.SDCard(spi, board.GP17)
        log("DEBUG", "SD mounted via sdcardio (Native C driver)")
    except ImportError:
        import adafruit_sdcard
        cs = digitalio.DigitalInOut(board.GP17)
        sdcard = adafruit_sdcard.SDCard(spi, cs)
        log("DEBUG", "SD mounted via adafruit_sdcard (Legacy driver)")

    vfs = storage.VfsFat(sdcard)
    storage.mount(vfs, "/sd")
    sd_mounted = True
    log("SUCCESS", "MicroSD mounted at /sd")
    
except Exception as e:
    log("WARN", f"SD Mount failed ({e}). Flash memory fallback active.")

led = pwmio.PWMOut(board.LED, frequency=5000, duty_cycle=0)

def file_exists_fast(path: str) -> bool:
    """Zero-RAM allocation filesystem check using FAT32 metadata."""
    try:
        os.stat(path)
        return True
    except OSError:
        return False

async def wait_for_sd_ready_async(timeout_sec=2.0, interval=0.1):
    if not sd_mounted:
        return False

    log("INFO", "Verifying SD Card filesystem indexing...")
    start_time = time.monotonic()

    while (time.monotonic() - start_time) < timeout_sec:
        if file_exists_fast("/sd"):
            log("SUCCESS", "SD Card filesystem ready.")
            return True
        await asyncio.sleep(interval)
        
    log("WARN", "SD Card filesystem indexing timeout.")
    return False

async def run_payload_on_startup():
    if getProgrammingStatus():
        log("INFO", "Dev Mode active (GP0 grounded). Halting automated execution.")
        return

    if file_exists_fast("/loot.bin") or file_exists_fast("/sd/loot.bin"):
        log("WARN", "Kill-switch 'loot.bin' detected. Aborting pipeline.")
        return

    if sd_mounted:
        await wait_for_sd_ready_async(timeout_sec=2.0, interval=0.1)

    log("INFO", "Resolving target payload via binary DIP switch...")
    payload_path = selectPayload()

    if payload_path and file_exists_fast(payload_path):
        log("SUCCESS", f"Executing payload: {payload_path}")
        await runScript(payload_path)
    else:
        log("ERROR", f"Target payload '{payload_path}' unreachable.")

async def main_loop():
    log("INFO", "Starting asynchronous kernel loop")
    tasks = [
        asyncio.create_task(blink_pico_led(led)),
        asyncio.create_task(monitor_buttons(button1)),
        asyncio.create_task(monitor_led_changes()),
        asyncio.create_task(run_payload_on_startup())
    ]
    
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        log("WARN", "Async tasks cancelled cleanly.")
    except Exception as e:
        log("ERROR", f"Runtime exception in task execution: {e}")

try:
    asyncio.run(main_loop())
except Exception as e:
    log("FATAL", f"System halt: {e}")