"""Draw inference payment status on the Laptop Display and a 3D-view overlay."""

import json
import os
from controller import Supervisor

# Hinge maxStop is ~0 (open). Values near -2 fold the lid onto the crate.
LID_OPEN = 0.0

robot = Supervisor()
timestep = int(robot.getBasicTimeStep())
display = robot.getDevice("display")
W = display.getWidth()
H = display.getHeight()
last_mtime = None
last_raw = ""
font_family = "Arial"
splash = None
lid_joint = None
overlay_text = "Optimus kiosk — waiting"


def status_path():
    override = os.environ.get("OPTIMUS_KIOSK_STATUS_PATH")
    if override:
        return override
    root = os.environ.get("OPTIMUS_REPO_ROOT") or os.environ.get("WEBOTS_PROJECT_HOME")
    if not root:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(root, "data", "kiosk-status.json")


STATUS_PATH = status_path()
print(f"[optimus_kiosk] status file: {STATUS_PATH}", flush=True)


def find_lid_joint():
    # Laptop is a PROTO: getSelf() has no children field. Walk from a device node.
    for dev_name in ("position sensor", "display"):
        device = robot.getDevice(dev_name)
        if device is None:
            continue
        if dev_name == "position sensor":
            try:
                device.enable(timestep)
            except Exception:
                pass
        try:
            node = robot.getFromDevice(device)
        except Exception as exc:
            print(f"[optimus_kiosk] getFromDevice({dev_name}): {exc}", flush=True)
            continue
        while node is not None:
            name = node.getTypeName()
            print(f"[optimus_kiosk] walk {name} from {dev_name}", flush=True)
            if name == "HingeJoint":
                print("[optimus_kiosk] found lid HingeJoint", flush=True)
                return node
            node = node.getParentNode()
    print("[optimus_kiosk] no HingeJoint under laptop", flush=True)
    return None


def open_lid():
    global lid_joint
    if lid_joint is None:
        return
    try:
        robot.setJointPosition(lid_joint, LID_OPEN)
        self_node = robot.getSelf()
        if self_node is not None:
            self_node.resetPhysics()
    except Exception as exc:
        print(f"[optimus_kiosk] lid open failed: {exc}", flush=True)


def set_font(size, bold=False):
    global font_family
    try:
        display.setFont(font_family, size, bold)
    except Exception:
        font_family = ""
        try:
            display.setFont("Lucida Console", size, bold)
        except Exception:
            pass


def load_splash():
    png = os.path.join(os.path.dirname(__file__), "screen_display.png")
    if not os.path.isfile(png):
        return None
    try:
        return display.imageLoad(png)
    except Exception as exc:
        print(f"[optimus_kiosk] splash load failed: {exc}", flush=True)
        return None


def paint_background():
    if splash is not None:
        display.imagePaste(splash, 0, 0, False)
        display.setAlpha(0.72)
        display.setColor(0x0A1628)
        display.fillRectangle(0, 0, W, H)
        display.setAlpha(1.0)
    else:
        display.setColor(0x0A1628)
        display.fillRectangle(0, 0, W, H)


def fmt_xyz(node):
    if node is None:
        return "—"
    p = node.getPosition()
    return f"{p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f}"


def draw_overlay(line):
    global overlay_text
    overlay_text = line[:80]
    robot.setLabel(0, overlay_text, 0.02, 0.02, 0.07, 0x00D4AA, 0.12, "Arial")
    robot.setLabel(
        1,
        "Overlays: laptop Display + Youbot/kiosk/benchmark/conveyor windows",
        0.02,
        0.08,
        0.045,
        0xCCCCCC,
        0.15,
        "Arial",
    )


def draw_scene_hud():
    youbot = robot.getFromDef("YOUbot")
    product = robot.getFromDef("PRODUCT")
    laptop = robot.getFromDef("OPTIMUS_LAPTOP")
    robot.setLabel(2, f"YOUbot  {fmt_xyz(youbot)}", 0.02, 0.78, 0.05, 0xFFAA33, 0.12, "Arial")
    robot.setLabel(3, f"Cube    {fmt_xyz(product)}", 0.02, 0.84, 0.05, 0x44FF88, 0.12, "Arial")
    robot.setLabel(4, f"Laptop  {fmt_xyz(laptop)}", 0.02, 0.90, 0.05, 0x66CCFF, 0.12, "Arial")
    robot.setLabel(
        5,
        "Metrics tab: PickAndPlaceBenchmark robot window",
        0.02,
        0.96,
        0.04,
        0xAAAAAA,
        0.2,
        "Arial",
    )


def draw_idle():
    paint_background()
    display.setColor(0x00D4AA)
    set_font(36, True)
    display.drawText("Optimus kiosk", 28, 40)
    display.setColor(0xCCCCCC)
    set_font(24, False)
    display.drawText("Waiting for the robot...", 28, 110)
    draw_overlay("Optimus kiosk — waiting for the robot")


def draw_status(payload):
    paint_background()
    display.setColor(0x00D4AA)
    set_font(32, True)
    display.drawText("Optimus inference", 28, 24)

    status = str(payload.get("status", "?"))
    color = 0x44FF88
    if status == "warning":
        color = 0xFFCC00
    elif status == "critical":
        color = 0xFF4444
    display.setColor(color)
    set_font(28, True)
    display.drawText(f"Status: {status}", 28, 90)

    display.setColor(0xEEEEEE)
    set_font(24, False)
    price = payload.get("priceUsdt", "0.01")
    reason = str(payload.get("reason", ""))[:42]
    action = str(payload.get("action", ""))[:42]
    settlement = str(payload.get("settlement", "pending"))
    display.drawText(f"Quote: ${price} USDT", 28, 150)
    display.drawText(reason, 28, 200)
    display.drawText(action, 28, 250)
    display.drawText(f"Receipt: {settlement}", 28, 310)
    draw_overlay(f"Kiosk {status} | ${price} | {reason}")


lid_joint = find_lid_joint()
open_lid()
splash = load_splash()
draw_idle()
draw_scene_hud()

steps = 0
while robot.step(timestep) != -1:
    steps += 1
    if steps % 8 == 0:
        open_lid()
    if steps % 4 == 0:
        draw_scene_hud()
    try:
        mtime = os.path.getmtime(STATUS_PATH)
        with open(STATUS_PATH, encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        continue
    if not raw:
        continue
    if mtime == last_mtime and raw == last_raw:
        continue
    last_mtime = mtime
    last_raw = raw
    try:
        draw_status(json.loads(raw))
    except json.JSONDecodeError:
        display.setColor(0xFF4444)
        set_font(24, False)
        display.drawText("Bad status file", 28, 360)
        draw_overlay("Kiosk error — bad status file")
