from __future__ import annotations

import json
import os
from pathlib import Path

import base58
from nacl.signing import SigningKey

from hotel.config import KEYS_DIR

ROLE_FILES = {
    "robot": "robot.json",
    "pantry": "pantry.json",
    "guest": "guest.json",
    "courier": "courier.json",
    "robot-fc": "robot-function-call.json",
}


def _ensure_dir() -> Path:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    gitignore = KEYS_DIR / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n!.gitignore\n", encoding="utf-8")
    return KEYS_DIR


def derive(role: str, path: Path | None = None) -> dict:
    _ensure_dir()
    dest = path or (_ensure_dir() / ROLE_FILES[role])
    if dest.exists():
        return json.loads(dest.read_text(encoding="utf-8"))

    sk = SigningKey.generate()
    vk = sk.verify_key
    secret = bytes(sk) + bytes(vk)
    pub = bytes(vk)
    record = {
        "role": role,
        "curve": "ed25519",
        "secret_key_hex": secret.hex(),
        "public_key_hex": pub.hex(),
        "near_implicit": pub.hex(),
        "near_public_key": "ed25519:" + base58.b58encode(pub).decode("ascii"),
        "solana_address": base58.b58encode(pub).decode("ascii"),
    }
    dest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(dest, 0o600)
    except OSError:
        pass
    return record


def load_role(role: str) -> dict:
    dest = KEYS_DIR / ROLE_FILES[role]
    env_map = {
        "robot": "ROBOT_KEYFILE",
        "guest": "GUEST_KEYFILE",
        "pantry": "PANTRY_KEYFILE",
        "courier": "COURIER_KEYFILE",
        "robot-fc": "ROBOT_FC_KEYFILE",
    }
    override = os.getenv(env_map.get(role, ""))
    if override:
        dest = Path(override)
    if not dest.exists():
        raise FileNotFoundError(f"missing keyfile for {role}: {dest}")
    return json.loads(dest.read_text(encoding="utf-8"))


def signing_key(record: dict) -> SigningKey:
    raw = bytes.fromhex(record["secret_key_hex"])
    return SigningKey(raw[:32])
