"""Youbot: drive to laptop kiosk, pay for inference, then pick-and-place."""

import json
import math
import os
import urllib.error
import urllib.request
from controller import Robot

AGENT_TELEMETRY_URL = os.environ.get(
    "MACHINE_AGENT_URL", "http://127.0.0.1:4040/telemetry"
)
AGENT_BASE = AGENT_TELEMETRY_URL.rsplit("/", 1)[0]
AGENT_KIOSK_INFER_URL = os.environ.get(
    "MACHINE_AGENT_KIOSK_URL", f"{AGENT_BASE}/kiosk/infer"
)
TELEMETRY_EVERY_STEPS = int(os.environ.get("TELEMETRY_EVERY_STEPS", "120"))
CONTEXT = os.environ.get(
    "OPTIMUS_CONTEXT",
    "Cold room B — paying for inference at laptop kiosk before pick task",
)
# Stand north of wooden box(4) at (-1.34, -2.06), size 0.6 m — do not clip the crate.
KIOSK_TARGET_X = float(os.environ.get("KIOSK_TARGET_X", "-2.10"))
KIOSK_TARGET_Y = float(os.environ.get("KIOSK_TARGET_Y", "-1.15"))
KIOSK_TOLERANCE = float(os.environ.get("KIOSK_TOLERANCE", "0.20"))
MAX_NAV_STEPS = int(os.environ.get("KIOSK_MAX_STEPS", "18000"))
BOX_KEEP_X = -1.34
BOX_KEEP_Y = -2.06
BOX_KEEP_R = 0.85

# KUKA Youbot omni kinematics (Webots youbot_control/base.c)
WHEEL_RADIUS = 0.05
LX = 0.228
LY = 0.158
OMNI_K = LX + LY
MAX_WHEEL_SPEED = 3.5  # rad/s — below pick-and-place 7.0 to reduce skid
MAX_VX = 0.22  # m/s
MAX_VY = 0.22
MAX_OMEGA = 0.35  # rad/s

# Benchmark spawn. The 520-step grab only lines up from here.
SPAWN_X = -2.4
SPAWN_Y = 0.0
SPAWN_YAW = 0.0
SPAWN_TOLERANCE = 0.05
SPAWN_HEADING_TOL = 0.04
CRAB_SPEED = 0.20

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
KIOSK_STATUS_PATH = os.path.join(REPO_ROOT, "data", "kiosk-status.json")

robot = Robot()
timestep = int(robot.getBasicTimeStep())
step = 0
speed_scale = 1.0
halt = False
inference_paid = False

motor_temp_c = 35.0
vibration_mms = 2.0
temp_c = 5.0
torque_accum = 0.0

wheels = [robot.getDevice(f"wheel{i}") for i in range(1, 5)]
for wheel in wheels:
    wheel.setPosition(float("+inf"))

gps = robot.getDevice("gps")
gps.enable(timestep)
inertial = robot.getDevice("inertial")
inertial.enable(timestep)
compass = robot.getDevice("compass")
compass.enable(timestep)

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


def stop_wheels():
    for wheel in wheels:
        wheel.setVelocity(0.0)


def clamp(value, low, high):
    return max(low, min(high, value))


def base_move(vx, vy, omega):
    """Official Youbot base_move — vx/vy in m/s, omega in rad/s → wheel rad/s."""
    vx = clamp(vx, -MAX_VX, MAX_VX)
    vy = clamp(vy, -MAX_VY, MAX_VY)
    omega = clamp(omega, -MAX_OMEGA, MAX_OMEGA)
    r = WHEEL_RADIUS
    k = OMNI_K
    speeds = [
        (vx + vy + k * omega) / r,
        (vx - vy - k * omega) / r,
        (vx - vy + k * omega) / r,
        (vx + vy - k * omega) / r,
    ]
    for i, speed in enumerate(speeds):
        wheels[i].setVelocity(scaled(clamp(speed, -MAX_WHEEL_SPEED, MAX_WHEEL_SPEED)))


def robot_heading():
    """Yaw on flat floor (rad, world XY)."""
    return inertial.getRollPitchYaw()[2]


def wrap_angle(a):
    while a > math.pi:
        a -= 2 * math.pi
    while a < -math.pi:
        a += 2 * math.pi
    return a


def avoid_crate(px, py, tx, ty):
    """If the straight line would clip the laptop crate, aim north of it instead."""
    mx = (px + tx) * 0.5
    my = (py + ty) * 0.5
    if math.hypot(mx - BOX_KEEP_X, my - BOX_KEEP_Y) > BOX_KEEP_R:
        return tx, ty
    return BOX_KEEP_X, BOX_KEEP_Y + BOX_KEEP_R + 0.05


def stow_arm_for_drive():
    """Compact arm pose — extended arm shifts COM and causes wheel slip."""
    armMotors[1].setPosition(0.0)
    armMotors[2].setPosition(-0.35)
    armMotors[3].setPosition(-0.2)
    finger.setPosition(finger_max)
    for _ in range(200):
        if robot.step(timestep) == -1:
            return


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


def apply_decision(decision):
    global speed_scale, halt
    status = decision.get("status", "ok")
    if status == "critical":
        halt = True
        speed_scale = 0.0
        stop_wheels()
    elif status == "warning":
        speed_scale = 0.5
        armMotors[0].setVelocity(0.2 * speed_scale)
        armMotors[1].setVelocity(0.5 * speed_scale)
        armMotors[2].setVelocity(0.5 * speed_scale)
        armMotors[3].setVelocity(0.3 * speed_scale)
    else:
        speed_scale = 1.0


def post_json(url, payload, timeout=8):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post_telemetry():
    try:
        body = post_json(AGENT_TELEMETRY_URL, sample_telemetry())
        apply_decision(body.get("decision", {}))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass


_kiosk_state = {}


def kiosk_payload(**extra):
    body = {
        "status": "ok",
        "reason": "",
        "action": "",
        "model": "llama-3.2-1b-instruct",
        "qvacReady": False,
        "source": "rules",
        "latencyMs": 0,
        "gatewayDid": os.environ.get("MACHINE_ID")
        or os.environ.get("GATEWAY_DID", "did:peaq:pending"),
        "machineId": os.environ.get("MACHINE_ID", "peaqos:machine:demo"),
        "priceUsdt": "0.01",
        "settlement": "none",
        "receiptId": "",
        "privacy": "Telemetry stays on LAN",
    }
    body.update(_kiosk_state)
    body.update(extra)
    return body


def emit_kiosk(payload):
    global _kiosk_state
    _kiosk_state.update(payload)
    try:
        os.makedirs(os.path.dirname(KIOSK_STATUS_PATH), exist_ok=True)
        with open(KIOSK_STATUS_PATH, "w", encoding="utf-8") as handle:
            json.dump(_kiosk_state, handle)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        pass


def clear_faults():
    try:
        post_json(f"{AGENT_BASE}/fault", {"scenario": "normal"}, timeout=2)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        pass


def pay_for_inference():
    global inference_paid, halt
    stop_wheels()
    emit_kiosk(
        kiosk_payload(
            status="pending",
            reason="Requesting quote…",
            action="Signing WDK payment intent",
            settlement="pending",
        )
    )
    try:
        body = post_json(AGENT_KIOSK_INFER_URL, sample_telemetry())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        emit_kiosk(
            kiosk_payload(
                status="critical",
                reason="Agent unreachable",
                action="Start machine-agent on host",
            )
        )
        halt = True
        return False

    decision = body.get("decision", {})
    quote = body.get("quote") or {}
    receipt = body.get("receipt") or {}
    qvac = body.get("qvac") or {}
    receipt_id = str(receipt.get("receiptId", ""))
    if not receipt_id:
        emit_kiosk(
            kiosk_payload(
                status="critical",
                reason="No receipt from agent",
                action="Check machine-agent logs and .env (GATEWAY_PAYEE_ADDRESS)",
            )
        )
        halt = True
        return False
    emit_kiosk(
        kiosk_payload(
            status=decision.get("status", "ok"),
            reason=decision.get("reason", ""),
            action=decision.get("action", ""),
            source=decision.get("source", "rules"),
            latencyMs=decision.get("latencyMs", 0),
            model=qvac.get("modelAlias") or quote.get("model") or "llama-3.2-1b-instruct",
            qvacReady=bool(qvac.get("ready")),
            gatewayDid=os.environ.get("MACHINE_ID")
            or quote.get("gatewayDid")
            or receipt.get("gatewayDid")
            or os.environ.get("GATEWAY_DID", "did:peaq:pending"),
            machineId=os.environ.get("MACHINE_ID", "peaqos:machine:demo"),
            priceUsdt=quote.get("priceUsdt") or receipt.get("amountUsdt") or "0.01",
            settlement=receipt.get("settlementStatus", "pending_settlement"),
            receiptId=receipt_id[:8],
        )
    )
    apply_decision(decision)
    if decision.get("status") == "critical":
        return False
    inference_paid = True
    return True


def drive_to_xy(
    tx,
    ty,
    tolerance,
    face_yaw=None,
    heading_tolerance=0.08,
    use_crate_avoid=True,
):
    """GPS go-to. Optional final heading (rad)."""
    stall = 0
    last_dist = float("inf")
    steps = 0
    while steps < MAX_NAV_STEPS:
        if tick() == -1:
            return False
        steps += 1
        px, py, _ = gps.getValues()
        if use_crate_avoid:
            ax, ay = avoid_crate(px, py, tx, ty)
        else:
            ax, ay = tx, ty
        dx = ax - px
        dy = ay - py
        dist_goal = math.hypot(tx - px, ty - py)
        if dist_goal < tolerance:
            if face_yaw is None:
                stop_wheels()
                return True
            heading = robot_heading()
            err = wrap_angle(face_yaw - heading)
            if abs(err) < heading_tolerance:
                stop_wheels()
                return True
            base_move(0.0, 0.0, clamp(1.1 * err, -MAX_OMEGA, MAX_OMEGA))
            continue

        dist = math.hypot(dx, dy)
        if dist > last_dist - 0.0005:
            stall += 1
        else:
            stall = 0
        last_dist = dist

        heading = robot_heading()
        err = wrap_angle(math.atan2(dy, dx) - heading)

        if stall > 80:
            stop_wheels()
            for _ in range(40):
                if robot.step(timestep) == -1:
                    return False
            stall = 0
            base_move(0.0, 0.10 if err > 0 else -0.10, 0.0)
            continue

        lx = math.cos(heading) * dx + math.sin(heading) * dy
        ly = -math.sin(heading) * dx + math.cos(heading) * dy
        if dist > 0.40:
            speed = clamp(0.10 + 0.18 * min(dist, 1.2), 0.06, MAX_VX)
            n = math.hypot(lx, ly) or 1.0
            base_move(speed * lx / n, speed * ly / n, 0.10 * err)
        else:
            base_move(clamp(lx * 0.35, -0.08, 0.08), clamp(ly * 0.35, -0.08, 0.08), 0.0)
    stop_wheels()
    return False


def drive_to_kiosk():
    stow_arm_for_drive()
    return drive_to_xy(KIOSK_TARGET_X, KIOSK_TARGET_Y, KIOSK_TOLERANCE)


def zero_arm():
    armMotors[0].setVelocity(0.2)
    armMotors[1].setVelocity(0.5)
    armMotors[2].setVelocity(0.5)
    armMotors[3].setVelocity(0.3)
    for motor in armMotors:
        motor.setPosition(0.0)
    finger.setPosition(0.0)


def drive_to_spawn():
    """Steady crab-walk back to the benchmark spawn. No teleport, no stall pauses."""
    zero_arm()
    steps = 0
    while steps < MAX_NAV_STEPS:
        if tick() == -1:
            return False
        steps += 1
        px, py, _ = gps.getValues()
        dx = SPAWN_X - px
        dy = SPAWN_Y - py
        dist = math.hypot(dx, dy)
        heading = robot_heading()
        yaw_err = wrap_angle(SPAWN_YAW - heading)
        if dist < SPAWN_TOLERANCE and abs(yaw_err) < SPAWN_HEADING_TOL:
            stop_wheels()
            zero_arm()
            for _ in range(30):
                if tick() == -1:
                    return False
            return True
        lx = math.cos(heading) * dx + math.sin(heading) * dy
        ly = -math.sin(heading) * dx + math.cos(heading) * dy
        norm = math.hypot(lx, ly) or 1.0
        speed = CRAB_SPEED if dist > 0.15 else max(0.06, dist * 1.2)
        base_move(
            speed * lx / norm,
            speed * ly / norm,
            clamp(0.8 * yaw_err, -0.25, 0.25),
        )
    stop_wheels()
    return False


def tick():
    global step
    step += 1
    if step % TELEMETRY_EVERY_STEPS == 0 and inference_paid:
        post_telemetry()
    if halt:
        return robot.step(timestep)
    return robot.step(timestep)


def run_pick_and_place():
    """Official benchmark sequence: constant wheel speeds, then arm. No GPS steering."""
    for wheel in wheels:
        wheel.setVelocity(7.0)
    for _ in range(520):
        if tick() == -1:
            return
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
            return

    armMotors[1].setPosition(0)
    for _ in range(200):
        if tick() == -1:
            return

    wheels[0].setVelocity(2.5)
    wheels[1].setVelocity(-2.5)
    wheels[2].setVelocity(2.5)
    wheels[3].setVelocity(-2.5)
    for _ in range(690):
        if tick() == -1:
            return

    wheels[1].setVelocity(2.5)
    wheels[3].setVelocity(2.5)
    for _ in range(900):
        if tick() == -1:
            return

    wheels[0].setVelocity(1.0)
    wheels[1].setVelocity(-1.0)
    wheels[2].setVelocity(1.0)
    wheels[3].setVelocity(-1.0)
    for _ in range(200):
        if tick() == -1:
            return

    wheels[1].setVelocity(1.0)
    wheels[3].setVelocity(1.0)
    for _ in range(300):
        if tick() == -1:
            return

    wheels[0].setVelocity(1.0)
    wheels[1].setVelocity(-1.0)
    wheels[2].setVelocity(1.0)
    wheels[3].setVelocity(-1.0)
    for _ in range(130):
        if tick() == -1:
            return

    wheels[1].setVelocity(1.0)
    wheels[3].setVelocity(1.0)
    for _ in range(310):
        if tick() == -1:
            return

    stop_wheels()

    armMotors[3].setPosition(0)
    armMotors[2].setPosition(-0.3)
    for _ in range(200):
        if tick() == -1:
            return
    armMotors[1].setPosition(-1.0)
    for _ in range(200):
        if tick() == -1:
            return
    armMotors[3].setPosition(-1.0)
    for _ in range(200):
        if tick() == -1:
            return
    armMotors[2].setPosition(-0.4)
    for _ in range(50):
        if tick() == -1:
            return
    finger.setPosition(finger_max)
    for _ in range(50):
        tick()


# --- Mission ---
clear_faults()
emit_kiosk(
    kiosk_payload(
        reason="Driving to laptop kiosk",
        action="Pay for nearby QVAC inference",
    )
)
if not drive_to_kiosk():
    emit_kiosk(
        kiosk_payload(
            status="critical",
            reason="Could not reach kiosk",
            action="Check KIOSK_TARGET_* env",
        )
    )
elif pay_for_inference():
    emit_kiosk(
        kiosk_payload(
            reason="Paid — driving back to the belt",
            action="Crab-walk to pick start",
            settlement="pending_settlement",
        )
    )
    if not drive_to_spawn():
        emit_kiosk(
            kiosk_payload(
                status="warning",
                reason="Paid; could not reach pick start",
                action="Check spawn GPS target",
                settlement="pending_settlement",
            )
        )
    else:
        emit_kiosk(
            kiosk_payload(
                reason="At pick start — driving to the conveyor",
                action="Pick cube from conveyor",
                settlement="pending_settlement",
            )
        )
        run_pick_and_place()

while tick() != -1:
    pass
