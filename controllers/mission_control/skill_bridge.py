"""Write a settlement outbox when a priced skill finishes. Stdlib only (Webots Python 3.9)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime

from py_trees.behaviour import Behaviour
from py_trees.common import Status

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUTBOX = os.path.join(ROOT, "settlement", "outbox.json")


def _hash(payload):
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


class ReportSkill(Behaviour):
    def __init__(self, name, blackboard, skill_id):
        super(ReportSkill, self).__init__(name)
        self.blackboard = blackboard
        self.skill_id = skill_id
        self._done = False

    def update(self):
        if self._done:
            return Status.SUCCESS
        robot = self.blackboard.read("robot")
        gps = [None, None, None]
        compass = [None, None, None]
        try:
            g = robot.getDevice("gps")
            c = robot.getDevice("compass")
            gps = list(g.getValues())
            compass = list(c.getValues())
        except Exception:
            pass
        payload = {
            "skill_id": self.skill_id,
            "success": True,
            "gps": gps,
            "compass": compass,
            "reported_at": datetime.utcnow().isoformat() + "Z",
        }
        payload["telemetry_hash"] = _hash(payload)
        folder = os.path.dirname(OUTBOX)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        with open(OUTBOX, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        print("HOTEL_SKILL_DONE", self.skill_id, payload["telemetry_hash"])
        self._done = True
        return Status.SUCCESS


def requested_skill():
    args = [a for a in sys.argv[1:] if a and not a.startswith("-")]
    if args:
        return args[0]
    return os.environ.get("HOTEL_SKILL", "all")
