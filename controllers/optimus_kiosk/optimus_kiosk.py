"""Draw inference payment status on the Laptop proto screen (device name: display)."""

import json
import os
from controller import Display, Robot

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
STATUS_PATH = os.path.join(REPO_ROOT, "data", "kiosk-status.json")

robot = Robot()
timestep = int(robot.getBasicTimeStep())
display = Display("display")
W = display.getWidth()
H = display.getHeight()
last_raw = ""


def draw_idle():
    display.setColor(0x0A1628)
    display.fillRectangle(0, 0, W, H)
    display.setColor(0x00D4AA)
    display.setFont("Arial", 36, True)
    display.drawText("Optimus kiosk", 28, 40)
    display.setColor(0xCCCCCC)
    display.setFont("Arial", 24, False)
    display.drawText("Waiting for the robot...", 28, 110)


def draw_status(payload):
    display.setColor(0x0A1628)
    display.fillRectangle(0, 0, W, H)
    display.setColor(0x00D4AA)
    display.setFont("Arial", 32, True)
    display.drawText("Optimus inference", 28, 24)

    status = str(payload.get("status", "?"))
    color = 0x44FF88
    if status == "warning":
        color = 0xFFCC00
    elif status == "critical":
        color = 0xFF4444
    display.setColor(color)
    display.setFont("Arial", 28, True)
    display.drawText(f"Status: {status}", 28, 90)

    display.setColor(0xEEEEEE)
    display.setFont("Arial", 24, False)
    price = payload.get("priceUsdt", "0.01")
    display.drawText(f"Quote: ${price} USDT", 28, 150)
    display.drawText(str(payload.get("reason", ""))[:42], 28, 200)
    display.drawText(str(payload.get("action", ""))[:42], 28, 250)
    display.drawText(f"Receipt: {payload.get('settlement', 'pending')}", 28, 310)


draw_idle()

while robot.step(timestep) != -1:
    try:
        with open(STATUS_PATH, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        continue
    if not raw or raw == last_raw:
        continue
    last_raw = raw
    try:
        draw_status(json.loads(raw))
    except json.JSONDecodeError:
        display.setColor(0xFF4444)
        display.drawText("Bad status file", 28, 360)
