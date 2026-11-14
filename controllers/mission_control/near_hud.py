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
PEAQ_STATUS = os.path.join(ROOT, "settlement", "peaq_status.json")
WEBOTS_ENV = os.path.join(ROOT, "settlement", "webots.env")
MISSION_LOG = os.path.join(ROOT, "settlement", "mission_log.json")


def settle_mode():
    # Fixed: Webots child processes do not inherit HOTEL_SETTLE; read settlement/webots.env.
    raw = os.environ.get("HOTEL_SETTLE", "").strip().lower()
    if raw in ("live", "none", "offline"):
        return raw
    if os.path.isfile(WEBOTS_ENV):
        try:
            with open(WEBOTS_ENV, "r", encoding="utf-8") as fh:
                for line in fh:
                    token = line.strip().lower()
                    if token in ("live", "none", "offline"):
                        return token
        except OSError:
            pass
    return "offline"


def _hotel_python_cmd():
    override = os.environ.get("HOTEL_PYTHON")
    if override:
        return [override]
    py_launcher = shutil.which("py")
    if py_launcher:
        for ver in ("-3.12", "-3.11", "-3.10"):
            try:
                probe = subprocess.run(
                    [py_launcher, ver, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                continue
            if probe.returncode == 0:
                return [py_launcher, ver]
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


def _is_settled_receipt(data):
    # Fixed: do not paint an open/prepared claim as a completed settlement.
    if not isinstance(data, dict):
        return False
    if data.get("settled_at"):
        return True
    if data.get("complete") or data.get("pay_supplier"):
        return True
    return False


def latest_receipt_for(skill_id, since=None, path_out=None):
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
        rec_skill = data.get("skill_id") or (data.get("args") or {}).get("skill_id")
        if rec_skill != skill_id:
            continue
        if not _is_settled_receipt(data):
            continue
        matched = False
        if want_hash and data.get("telemetry_hash") == want_hash:
            matched = True
        elif since is not None and os.path.getmtime(path) >= since - 2.0:
            matched = True
        elif want_hash is None and since is None:
            matched = True
        if matched:
            if path_out is not None:
                path_out.append(path)
            return data
    return None


def _load_peaq_status():
    if not os.path.isfile(PEAQ_STATUS):
        return {}
    try:
        with open(PEAQ_STATUS, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _peaq_activity_bits(receipt):
    peaq = receipt.get("peaq") if isinstance(receipt.get("peaq"), dict) else {}
    activity = peaq.get("activity") if isinstance(peaq.get("activity"), dict) else {}
    submitted = peaq.get("submitted")
    if submitted is None:
        submitted = activity.get("submitted")
    sig = activity.get("signature") or activity.get("tx") or ""
    if not sig and activity.get("submit_stdout"):
        sig = str(activity.get("submit_stdout"))[:80]
    if submitted is False or submitted is None:
        label = "dry"
    elif sig:
        label = sig
    else:
        label = "ok"
    return peaq, activity, submitted, label


def print_settlement_console(receipt):
    """Butler-style flushed lines. Controller still never signs."""
    claim = receipt.get("claim_id") or ""
    skill = receipt.get("skill_id") or ""
    complete_tx, complete_ex = _tx_bits(receipt.get("complete") or {})
    pay_tx, pay_ex = _tx_bits(receipt.get("pay_supplier") or {})
    refused = receipt.get("refused_quote") or {}
    reason = refused.get("reason") or refused.get("accepted") or ""
    peaq, _activity, submitted, act_label = _peaq_activity_bits(receipt)
    status = _load_peaq_status()
    solana = peaq.get("solana_address") or receipt.get("solana_address") or status.get("solana_address") or ""
    implicit = peaq.get("near_implicit") or receipt.get("near_implicit") or status.get("near_implicit") or ""
    print("[near] claim %s skill %s" % (claim, skill), flush=True)
    print("[near] complete %s %s" % (complete_tx, complete_ex), flush=True)
    print("[near] pay_supplier %s %s" % (pay_tx, pay_ex), flush=True)
    print("[near] courier refused %s" % reason, flush=True)
    print("[peaq] solana %s near %s activity %s submitted %s" % (solana, implicit, act_label, submitted), flush=True)


def paint_hud(robot, lines):
    color = 0xE8FF6A
    for i in range(8):
        text = lines[i] if i < len(lines) else ""
        try:
            robot.setLabel(i, text, 0.02, 0.04 + i * 0.045, 0.08, color, 0, "Arial")
        except Exception:
            pass


def reset_mission_log():
    folder = os.path.dirname(MISSION_LOG)
    try:
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(MISSION_LOG, "w", encoding="utf-8") as fh:
            json.dump({"started_at": time.time(), "receipts": []}, fh)
            fh.write("\n")
    except OSError:
        pass


def append_mission_log(receipt, path=None):
    complete_tx, complete_ex = _tx_bits(receipt.get("complete") or {})
    pay_tx, pay_ex = _tx_bits(receipt.get("pay_supplier") or {})
    peaq, _activity, submitted, act_label = _peaq_activity_bits(receipt)
    status = _load_peaq_status()
    entry = {
        "claim_id": receipt.get("claim_id"),
        "skill_id": receipt.get("skill_id"),
        "complete": complete_tx,
        "complete_explorer": complete_ex,
        "pay_supplier": pay_tx,
        "pay_explorer": pay_ex,
        "solana": peaq.get("solana_address") or receipt.get("solana_address") or status.get("solana_address") or "",
        "peaq_activity": act_label,
        "peaq_submitted": submitted,
        "path": path,
    }
    try:
        data = {"started_at": time.time(), "receipts": []}
        if os.path.isfile(MISSION_LOG):
            with open(MISSION_LOG, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                data = loaded
        recs = data.setdefault("receipts", [])
        recs.append(entry)
        with open(MISSION_LOG, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    except (OSError, ValueError):
        pass
    return entry


def _spawn_hotel(args):
    cmd = _hotel_python_cmd()
    if not cmd:
        return None, "NEAR: no Python 3.10 on PATH"
    log_path = os.path.join(ROOT, "settlement", "hotel_spawn.log")
    try:
        folder = os.path.dirname(log_path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        logf = open(log_path, "ab")
        logf.write(("\n--- %s ---\n" % " ".join(args)).encode("utf-8"))
        logf.flush()
        proc = subprocess.Popen(
            cmd + ["-m", "hotel.cli"] + args,
            cwd=ROOT,
            stdout=logf,
            stderr=subprocess.STDOUT,
        )
        proc._hotel_log = logf
        print("NEAR spawned", " ".join(args), cmd, flush=True)
        return proc, None
    except OSError as exc:
        return None, str(exc)[:80]


def _drain(proc):
    leftover = ""
    if proc is None:
        return leftover
    logf = getattr(proc, "_hotel_log", None)
    if logf is not None:
        try:
            logf.flush()
            logf.close()
        except Exception:
            pass
        proc._hotel_log = None
    log_path = os.path.join(ROOT, "settlement", "hotel_spawn.log")
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - 2500))
            leftover = fh.read().decode("utf-8", "replace")
    except OSError:
        leftover = ""
    if leftover:
        print(leftover[-2000:], flush=True)
    return leftover


class PrepareClaim(Behaviour):
    def __init__(self, name, blackboard, skill_id):
        super(PrepareClaim, self).__init__(name)
        self.blackboard = blackboard
        self.skill_id = skill_id
        self.robot = None
        self.proc = None
        self.mode = "offline"
        self._done = False

    def initialise(self):
        self.robot = self.blackboard.read("robot")
        self.mode = settle_mode()
        self.proc = None
        self._done = False
        if self.mode == "none":
            self._done = True
            return
        args = ["prepare-claim", "--skill", self.skill_id]
        if self.mode != "live":
            args.append("--offline")
        proc, err = _spawn_hotel(args)
        if err:
            paint_hud(self.robot, ["NEAR: prepare failed", self.skill_id, err])
            print("[near] prepare failed %s %s" % (self.skill_id, err), flush=True)
            self._done = True
            return
        self.proc = proc
        paint_hud(self.robot, ["NEAR: creating claim", "skill %s" % self.skill_id])

    def update(self):
        if self._done:
            return Status.SUCCESS
        if self.proc is None:
            self._done = True
            return Status.SUCCESS
        if self.proc.poll() is None:
            return Status.RUNNING
        leftover = _drain(self.proc)
        if self.proc.returncode != 0:
            tail = leftover.strip().splitlines()[-1][:80] if leftover.strip() else "prepare-claim exit %s" % self.proc.returncode
            paint_hud(self.robot, ["NEAR: prepare error", self.skill_id, tail])
            print("[near] prepare error %s %s" % (self.skill_id, tail), flush=True)
        else:
            print("[near] prepared %s" % self.skill_id, flush=True)
        self._done = True
        return Status.SUCCESS

    def terminate(self, new_status):
        if new_status == Status.SUCCESS:
            return
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.kill()
            except OSError:
                pass
            self.proc = None


class ShowSettlement(Behaviour):
    def __init__(self, name, blackboard, skill_id):
        super(ShowSettlement, self).__init__(name)
        self.blackboard = blackboard
        self.skill_id = skill_id
        self.mode = "offline"
        self.robot = None
        self.proc = None
        self.peaq_proc = None
        self.t0 = 0.0
        self.timeout = 90.0
        self._shown = False
        self._peaq_started = False
        self.since = 0.0
        self._receipt_path = None

    def initialise(self):
        self.robot = self.blackboard.read("robot")
        self.mode = settle_mode()
        self.proc = None
        self.peaq_proc = None
        self._shown = False
        self._peaq_started = False
        self._receipt_path = None
        self.since = time.time()
        self.t0 = time.time()
        self.timeout = 240.0
        if self.mode == "none":
            self._shown = True
            return
        paint_hud(self.robot, ["NEAR: settling...", "skill %s mode %s" % (self.skill_id, self.mode)])
        args = ["watch", "--once"]
        if self.mode != "live":
            args.append("--offline")
        proc, err = _spawn_hotel(args)
        if err:
            paint_hud(self.robot, ["NEAR: watch spawn failed", err])
            self._shown = True
            return
        self.proc = proc

    def update(self):
        if self.mode == "none" or self._shown:
            return self._finish_peaq()
        receipt = self._find_receipt()
        if receipt:
            self._paint_receipt(receipt)
            self._shown = True
            self._start_peaq()
            return self._finish_peaq()
        if self.proc is not None and self.proc.poll() is not None:
            leftover = _drain(self.proc)
            self.proc = None
            receipt = self._find_receipt()
            if receipt:
                self._paint_receipt(receipt)
                self._shown = True
                self._start_peaq()
                return self._finish_peaq()
            paint_hud(
                self.robot,
                [
                    "NEAR: watch exited, no receipt",
                    "skill %s" % self.skill_id,
                    leftover.strip().splitlines()[-1][:80] if leftover.strip() else "",
                ],
            )
            print("[near] watch no receipt %s" % self.skill_id, flush=True)
            self._shown = True
            return Status.SUCCESS
        if (time.time() - self.t0) > self.timeout:
            paint_hud(
                self.robot,
                [
                    "NEAR: timeout waiting for receipt",
                    "mode %s skill %s" % (self.mode, self.skill_id),
                ],
            )
            print("[near] settle timeout %s" % self.skill_id, flush=True)
            self._shown = True
            return Status.SUCCESS
        return Status.RUNNING

    def _find_receipt(self):
        found = []
        receipt = latest_receipt_for(self.skill_id, since=self.since, path_out=found)
        if receipt and found:
            self._receipt_path = found[0]
        return receipt

    def _start_peaq(self):
        if self._peaq_started or not self._receipt_path:
            return
        self._peaq_started = True
        proc, err = _spawn_hotel(["peaq-event", "--receipt", self._receipt_path])
        if err:
            print("[peaq] spawn failed %s" % err, flush=True)
            return
        self.peaq_proc = proc

    def _finish_peaq(self):
        if self.peaq_proc is None:
            return Status.SUCCESS
        if self.peaq_proc.poll() is None:
            if (time.time() - self.t0) > self.timeout + 60.0:
                try:
                    self.peaq_proc.kill()
                except OSError:
                    pass
                self.peaq_proc = None
                return Status.SUCCESS
            return Status.RUNNING
        leftover = _drain(self.peaq_proc)
        self.peaq_proc = None
        receipt = self._find_receipt()
        if receipt:
            print_settlement_console(receipt)
        elif leftover:
            print("[peaq] event %s" % leftover.strip().splitlines()[-1][:120], flush=True)
        return Status.SUCCESS

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
        print_settlement_console(receipt)
        append_mission_log(receipt, path=self._receipt_path)

    def terminate(self, new_status):
        if new_status == Status.SUCCESS:
            return
        for proc in (self.proc, self.peaq_proc):
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                except OSError:
                    pass
        self.proc = None
        self.peaq_proc = None


class ShowMissionSummary(Behaviour):
    def __init__(self, name, blackboard):
        super(ShowMissionSummary, self).__init__(name)
        self.blackboard = blackboard

    def update(self):
        robot = self.blackboard.read("robot")
        recs = []
        try:
            if os.path.isfile(MISSION_LOG):
                with open(MISSION_LOG, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                recs = data.get("receipts") or []
        except (OSError, ValueError):
            recs = []
        by_skill = {}
        for entry in recs:
            skill = entry.get("skill_id") or ""
            by_skill[skill] = entry
        order = ["fetch_honey", "fetch_jam", "fetch_jam_2"]
        print("[mission] DONE %s/%s skills settled" % (len(by_skill), len(order)), flush=True)
        for skill in order:
            entry = by_skill.get(skill) or {}
            print(
                "[mission] %s claim %s complete %s %s pay_supplier %s peaq %s"
                % (
                    skill,
                    entry.get("claim_id") or "-",
                    entry.get("complete") or "-",
                    entry.get("complete_explorer") or "",
                    entry.get("pay_supplier") or "-",
                    entry.get("peaq_activity") or "-",
                ),
                flush=True,
            )
        solana = ""
        if recs:
            solana = recs[-1].get("solana") or ""
        lines = ["MISSION %s/%s" % (len(by_skill), len(order))]
        for skill in order:
            entry = by_skill.get(skill) or {}
            tx = str(entry.get("complete") or "none")
            short = tx if len(tx) <= 18 else tx[:10] + ".." + tx[-6:]
            lines.append("%s %s" % (skill.replace("fetch_", ""), short))
        lines.append("peaq %s" % (solana[:28] if solana else "dry/activity"))
        paint_hud(robot, lines)
        return Status.SUCCESS
