#!/usr/bin/env python3

import asyncio
from bleak import BleakScanner
import time
import subprocess
import sys
import json
from datetime import datetime

with open("config.json", "r") as file:
    config = json.load(file)

TARGET_MAC_ADDRESS = config["TARGET_MAC_ADDRESS"]

# Constants for distance estimation
RSSI_AT_1M = config["RSSI_AT_1M"]  # Measured RSSI at 1 meter
PATH_LOSS_EXPONENT = config["PATH_LOSS_EXPONENT"]  # Adjusted based on your environment
DISTANCE_THRESHOLD_CM = config["DISTANCE_THRESHOLD_CM"]  # Distance threshold in centimeters
NEARBY_DISTANCE_CM = config["NEARBY_DISTANCE_CM"]  # Distance threshold to unlock the screen
TIME_THRESHOLD_SECONDS = config["TIME_THRESHOLD_SECONDS"]  # Time threshold to check if distance is consistently over the limit

# Global variables
distance_exceed_start_time = None
scanner = None
exit_event = asyncio.Event()
screen_locked = False

def rssi_to_distance(rssi):
    """
    Convert RSSI to distance in centimeters.
    """
    if rssi == 0:
        return float('inf')  # If RSSI is 0, return infinity as distance
    # Convert dBm to meters and then to centimeters
    distance_meters = 10 ** ((RSSI_AT_1M - rssi) / (10 * PATH_LOSS_EXPONENT))
    distance_centimeters = distance_meters * 100
    return distance_centimeters

def log_message(message):
    """
    Print log messages with a timestamp.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"{timestamp} - {message}")

def lock_screen():
    """
    Lock the Cinnamon desktop screen.
    """
    subprocess.run(["cinnamon-screensaver-command", "--lock"])
    subprocess.run(["notify-send", "AuraLock locked the screen."])
    global screen_locked
    screen_locked = True
    log_message("Screen locked.")

def unlock_screen():
    """
    Unlock the Cinnamon desktop screen.
    """
    global screen_locked
    if screen_locked:
        subprocess.run(["cinnamon-screensaver-command", "--deactivate"])
        subprocess.run(["notify-send", "AuraLock unlocked the screen."])
        screen_locked = False
        log_message("Screen unlocked.")

async def detection_callback(device, advertisement_data):
    global distance_exceed_start_time
    global scanner
    global exit_event
    global screen_locked

    if device.address == TARGET_MAC_ADDRESS:
        rssi = advertisement_data.rssi
        distance = rssi_to_distance(rssi)
        log_message(f"Device found: {device.name} ({device.address}), RSSI: {rssi} dBm, Distance: {distance:.2f} cm")

        # Check if the distance is within unlocking range
        if distance <= NEARBY_DISTANCE_CM:
            log_message(f"Device is close enough: {distance:.2f} cm")
            unlock_screen()  # Unlock the screen only if it was previously locked
            distance_exceed_start_time = None  # Reset timer if within range
        # Check if the distance exceeds the threshold
        elif distance > DISTANCE_THRESHOLD_CM:
            if distance_exceed_start_time is None:
                # Start timing if distance exceeds threshold for the first time
                distance_exceed_start_time = time.time()
            elif time.time() - distance_exceed_start_time > TIME_THRESHOLD_SECONDS:
                # Lock the screen if the distance has exceeded the threshold for the required time
                log_message(f"User too far away: {distance:.2f} cm")
                lock_screen()  # Lock the screen
                # Continue running to keep scanning
                distance_exceed_start_time = None
        else:
            # Reset the timer if the distance goes back below the threshold
            distance_exceed_start_time = None

async def run():
    global scanner
    global distance_exceed_start_time
    global exit_event
    global screen_locked

    distance_exceed_start_time = None

    # Start scanning to check if the device is present
    scanner = BleakScanner()
    await scanner.start()

    device_found = False
    start_time = time.time()

    # Wait for a few seconds to check if the device appears
    while time.time() - start_time < 15:
        devices = scanner.discovered_devices
        for device in devices:
            if device.address == TARGET_MAC_ADDRESS:
                device_name = device.name
        if any(device.address == TARGET_MAC_ADDRESS for device in devices):
            device_found = True
            subprocess.run(["notify-send", f"AuraLock found the band and started successfully.\n\nDevice Name: {device_name}\n\nDevice MAC: {TARGET_MAC_ADDRESS}"])
            break
        await asyncio.sleep(1)

    await scanner.stop()

    if not device_found:
        subprocess.run(["notify-send", "AuraLock couldn\'t find the band. AuraLock will exit now until next restart."])
        log_message("Device not found. Exiting script.")
        sys.exit(0)  # Exit if the device is not found

    # Device found, start the actual scanning
    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()

    try:
        # Wait until the exit event is set
        await exit_event.wait()
    except KeyboardInterrupt:
        log_message("Stopping scan due to keyboard interrupt...")
    finally:
        await scanner.stop()
        log_message("Exiting script.")
        sys.exit(0)

# Run the asynchronous function using asyncio.run()
if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        log_message("Interrupted by user.")
        sys.exit(0)
