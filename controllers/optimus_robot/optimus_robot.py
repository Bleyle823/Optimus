"""Youbot pick-and-place with Optimus telemetry + decision hook (template logic preserved)."""

import json
import math
import os
import urllib.error
import urllib.request
from controller import Robot

AGENT_URL = os.environ.get("MACHINE_AGENT_URL", "http://127.0.0.1:4040/telemetry")
TELEMETRY_EVERY_STEPS = int(os.environ.get("TELEMETRY_EVERY_STEPS", "120"))
CONTEXT = os.environ.get(
    "OPTIMUS_CONTEXT",
    "Loading flowers into Cold room B, safe range 2 to 8 C",
)

robot = Robot()
timestep = int(robot.getBasicTimeStep())
step = 0
speed_scale = 1.0
halt = False

# Synthetic health state (simulator has no cold-room sensor on arm)
motor_temp_c = 35.0
vibration_mms = 2.0
temp_c = 5.0
torque_accum = 0.0

wheels = [robot.getDevice(f"wheel{i}") for i in range(1, 5)]
for wheel in wheels:
    wheel.setPosition(float("+inf"))

armMotors = [robot.getDevice(f"arm{i}") for i in range(1, 6)]
armMotors[0].setVelocity(0.2 * speed_scale)
armMotors[1].setVelocity(0.5 * speed_scale)
armMotors[2].setVelocity(0.5 * speed_scale)
armMotors[3].setVelocity(0.3 * speed_scale)

armPositionSensors = [robot.getDevice(f"arm{i}sensor") for i in range(1, 6)]
for sensor in armPositionSensors:
    sensor.enable(timestep)

finger = robot.getDevice("finger::left")
finger.setVelocity(0.03)
finger_max = finger.getMaxPosition()


def scaled(v):
    return v * speed_scale


def sample_telemetry():
    global motor_temp_c, vibration_mms, temp_c, torque_accum
    joints = [s.getValue() for s in armPositionSensors]
    torque_accum += sum(abs(j) for j in joints) * 0.001
    motor_temp_c = 30.0 + min(torque_accum, 25.0)
    vibration_mms = 2.0 + min(torque_accum * 0.15, 12.0)
    return {
        "machineId": os.environ.get("MACHINE_ID", "peaqos:machine:demo"),
        "kind": "cold_room",
        "timestamp": "2026-10-26T12:00:00Z",
        "metrics": {
            "tempC": round(temp_c, 2),
            "motorTempC": round(motor_temp_c, 2),
            "vibrationMmS": round(vibration_mms, 2),
            "joint1": round(joints[0], 3),
        },
        "context": CONTEXT,
    }


def post_telemetry():
    payload = sample_telemetry()
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        AGENT_URL, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            apply_decision(body.get("decision", {}))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        pass


def apply_decision(decision):
    global speed_scale, halt
    status = decision.get("status", "ok")
    if status == "critical":
        halt = True
        speed_scale = 0.0
        for wheel in wheels:
            wheel.setVelocity(0.0)
    elif status == "warning":
        speed_scale = 0.5
        armMotors[0].setVelocity(0.2 * speed_scale)
        armMotors[1].setVelocity(0.5 * speed_scale)
        armMotors[2].setVelocity(0.5 * speed_scale)
        armMotors[3].setVelocity(0.3 * speed_scale)
    else:
        speed_scale = 1.0


def tick():
    global step
    step += 1
    if step % TELEMETRY_EVERY_STEPS == 0:
        post_telemetry()
    if halt:
        return robot.step(timestep)
    return robot.step(timestep)


# --- pick and place sequence (from Webots template, velocities scaled) ---

for wheel in wheels:
    wheel.setVelocity(scaled(7.0))
for _ in range(520):
    if tick() == -1:
        exit()
for wheel in wheels:
    wheel.setVelocity(0.0)

armMotors[1].setPosition(-0.55)
armMotors[2].setPosition(-0.9)
armMotors[3].setPosition(-1.5)
finger.setPosition(finger_max)
while tick() != -1:
    if abs(armPositionSensors[3].getValue() - (-1.2)) < 0.01:
        break

finger.setPosition(0.013)
for _ in range(50):
    if tick() == -1:
        exit()

armMotors[1].setPosition(0)
for _ in range(200):
    if tick() == -1:
        exit()

wheels[0].setVelocity(scaled(2.5))
wheels[1].setVelocity(scaled(-2.5))
wheels[2].setVelocity(scaled(2.5))
wheels[3].setVelocity(scaled(-2.5))
for _ in range(690):
    if tick() == -1:
        exit()

wheels[1].setVelocity(scaled(2.5))
wheels[3].setVelocity(scaled(2.5))
for _ in range(900):
    if tick() == -1:
        exit()

wheels[0].setVelocity(scaled(1.0))
wheels[1].setVelocity(scaled(-1.0))
wheels[2].setVelocity(scaled(1.0))
wheels[3].setVelocity(scaled(-1.0))
for _ in range(200):
    if tick() == -1:
        exit()

wheels[1].setVelocity(scaled(1.0))
wheels[3].setVelocity(scaled(1.0))
for _ in range(300):
    if tick() == -1:
        exit()

wheels[0].setVelocity(scaled(1.0))
wheels[1].setVelocity(scaled(-1.0))
wheels[2].setVelocity(scaled(1.0))
wheels[3].setVelocity(scaled(-1.0))
for _ in range(130):
    if tick() == -1:
        exit()

wheels[1].setVelocity(scaled(1.0))
wheels[3].setVelocity(scaled(1.0))
for _ in range(310):
    if tick() == -1:
        exit()

for wheel in wheels:
    wheel.setVelocity(0.0)

armMotors[3].setPosition(0)
armMotors[2].setPosition(-0.3)
for _ in range(200):
    if tick() == -1:
        exit()
armMotors[1].setPosition(-1.0)
for _ in range(200):
    if tick() == -1:
        exit()
armMotors[3].setPosition(-1.0)
for _ in range(200):
    if tick() == -1:
        exit()
armMotors[2].setPosition(-0.4)
for _ in range(50):
    if tick() == -1:
        exit()
finger.setPosition(finger_max)
for _ in range(50):
    tick()
