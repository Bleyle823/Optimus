from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "hotel.json"
KEYS_DIR = ROOT / "keys"
SETTLEMENT_DIR = ROOT / "settlement"
OUTBOX = SETTLEMENT_DIR / "outbox.json"
RECEIPTS_DIR = SETTLEMENT_DIR / "receipts"


def load() -> dict:
    load_dotenv(ROOT / ".env")
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    env_escrow = os.getenv("NEAR_ESCROW_ACCOUNT")
    if env_escrow:
        data["escrow_account"] = env_escrow
    env_ft = os.getenv("NEAR_FT_CONTRACT")
    if env_ft:
        data["ft_contract"] = env_ft
    env_rpc = os.getenv("NEAR_RPC")
    if env_rpc:
        data["rpc"] = env_rpc
    accounts = data.setdefault("accounts", {})
    for role, env_name in (
        ("guest", "NEAR_GUEST_ACCOUNT"),
        ("robot", "NEAR_ROBOT_ACCOUNT"),
        ("pantry", "NEAR_PANTRY_ACCOUNT"),
        ("courier", "NEAR_COURIER_ACCOUNT"),
    ):
        val = os.getenv(env_name)
        if val:
            accounts[role] = val
    return data


def kill_switch(cfg: dict) -> bool:
    return bool(cfg.get("procurement", {}).get("kill_switch"))


def require_live(cfg: dict) -> None:
    if kill_switch(cfg):
        raise SystemExit("procurement.kill_switch is true; refusing to transact")
