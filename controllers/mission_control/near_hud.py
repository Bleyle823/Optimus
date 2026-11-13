"""NEAR settlement overlay. Stdlib only (Webots Python 3.9). Do not import hotel."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import time

from py_trees.behaviour import Behaviour
from py_trees.common import Status

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RECEIPTS = os.path.join(ROOT, "settlement", "receipts")
OUTBOX = os.path.join(ROOT, "settlement", "outbox.json")


def settle_mode():
    raw = os.environ.get("HOTEL_SETTLE", "offline").strip().lower()
    if raw in ("", "offline"):
        return "offline"
    if raw in ("live", "none"):
        return raw
    return "offline"


def _hotel_python_cmd():
    override = os.environ.get("HOTEL_PYTHON")
    if override:
        return [override]
    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3.10"]
    for name in ("python", "python3"):
        found = shutil.which(name)
        if found and os.path.abspath(found) != os.path.abspath(sys.executable):
            return [found]
    if shutil.which("python"):
        return [shutil.which("python")]
    return None


def _tx_bits(blob):
    if not isinstance(blob, dict):
        return str(blob), ""
    if blob.get("complete") == "offline" or blob.get("pay_supplier") == "offline":
        return "offline", ""
    tx = blob.get("tx") or ""
    explorer = blob.get("explorer") or ""
    if not tx and isinstance(blob.get("result"), dict):
        tx = blob["result"].get("transaction", {}).get("hash", "")
    return tx or str(blob)[:48], explorer


def _outbox_hash(skill_id):
    if not os.path.isfile(OUTBOX):
        return None
    try:
        with open(OUTBOX, "r", encoding="utf-8") as fh:
            box = json.load(fh)
    except (OSError, ValueError):
        return None
    if box.get("skill_id") != skill_id:
        return None
    return box.get("telemetry_hash")


def latest_receipt_for(skill_id, since=None):
    if not os.path.isdir(RECEIPTS):
        return None
    want_hash = _outbox_hash(skill_id)
    paths = [
        p
        for p in glob.glob(os.path.join(RECEIPTS, "*.json"))
        if os.path.basename(p) != ".gitkeep"
    ]
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        if data.get("skill_id") != skill_id:
            continue
        if want_hash and data.get("telemetry_hash") == want_hash:
            return data
        if since is not None and os.path.getmtime(path) >= since - 1.0:
            return data
        if want_hash is None and since is None:
            return data
    return None


def paint_hud(robot, lines):
    color = 0xE8FF6A
    for i in range(8):
        text = lines[i] if i < len(lines) else ""
        try:
            robot.setLabel(i, text, 0.02, 0.04 + i * 0.045, 0.08, color, 0, "Arial")
        except Exception:
            pass


class ShowSettlement(Behaviour):
    def __init__(self, name, blackboard, skill_id):
        super(ShowSettlement, self).__init__(name)
        self.blackboard = blackboard
        self.skill_id = skill_id
        self.mode = "offline"
        self.robot = None
        self.proc = None
        self.t0 = 0.0
        self.timeout = 20.0
        self._shown = False
        self.since = 0.0

    def initialise(self):
        self.robot = self.blackboard.read("robot")
        self.mode = settle_mode()
        self.proc = None
        self._shown = False
        self.since = time.time()
        self.t0 = self.robot.getTime()
        if self.mode == "none":
            return
        if self.mode == "live":
            self.timeout = 60.0
            paint_hud(
                self.robot,
                [
                    "NEAR: waiting for watch --once",
                    "skill %s" % self.skill_id,
                ],
            )
            return
        self.timeout = 25.0
        paint_hud(self.robot, ["NEAR: settling offline...", "skill %s" % self.skill_id])
        cmd = _hotel_python_cmd()
        if not cmd:
            paint_hud(self.robot, ["NEAR: no Python 3.10 on PATH", "set HOTEL_PYTHON"])
            self._shown = True
            return
        try:
            self.proc = subprocess.Popen(
                cmd + ["-m", "hotel.cli", "watch", "--once", "--offline"],
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            print("NEAR watch spawned", cmd)
        except OSError as exc:
            paint_hud(self.robot, ["NEAR: watch spawn failed", str(exc)[:80]])
            self._shown = True

    def update(self):
        if self.mode == "none" or self._shown:
            return Status.SUCCESS
        receipt = latest_receipt_for(self.skill_id, since=self.since)
        if receipt:
            self._paint_receipt(receipt)
            self._shown = True
            return Status.SUCCESS
        if self.proc is not None and self.proc.poll() is not None:
            leftover = ""
            try:
                leftover = (self.proc.stdout.read() or b"").decode("utf-8", "replace")
            except Exception:
                leftover = ""
            if leftover:
                print(leftover[-1500:])
            receipt = latest_receipt_for(self.skill_id, since=self.since)
            if receipt:
                self._paint_receipt(receipt)
                self._shown = True
                return Status.SUCCESS
            paint_hud(
                self.robot,
                [
                    "NEAR: watch exited, no receipt",
                    "run create-claim --offline first",
                    leftover.strip().splitlines()[-1][:80] if leftover.strip() else "",
                ],
            )
            self._shown = True
            return Status.SUCCESS
        if (self.robot.getTime() - self.t0) > self.timeout:
            paint_hud(
                self.robot,
                [
                    "NEAR: timeout waiting for receipt",
                    "mode %s skill %s" % (self.mode, self.skill_id),
                ],
            )
            self._shown = True
            return Status.SUCCESS
        return Status.RUNNING

    def _paint_receipt(self, receipt):
        complete_tx, complete_ex = _tx_bits(receipt.get("complete") or {})
        pay_tx, pay_ex = _tx_bits(receipt.get("pay_supplier") or {})
        refused = receipt.get("refused_quote") or {}
        lines = [
            "NEAR claim %s" % receipt.get("claim_id", ""),
            "skill %s  pantry_bps %s" % (receipt.get("skill_id"), receipt.get("pantry_bps")),
            "complete %s" % complete_tx,
            "pay_supplier %s" % pay_tx,
            "courier refused: %s" % refused.get("accepted", ""),
            (refused.get("reason") or "")[:90],
            complete_ex or pay_ex,
        ]
        paint_hud(self.robot, lines)
        print("NEAR_HUD", receipt.get("claim_id"), complete_tx, pay_tx)

    def terminate(self, new_status):
        if new_status == Status.SUCCESS:
            return
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass
            self.proc = None
