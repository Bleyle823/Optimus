from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from hotel.config import OUTBOX, RECEIPTS_DIR, kill_switch, load, require_live
from hotel.keys import derive, load_role
from hotel.near_rpc import NearClient, explorer_tx, next_nonce, sign_function_call


def _client(cfg: dict) -> NearClient:
    return NearClient(cfg["rpc"], cfg.get("network", "testnet"))


def _robot_pk_record() -> dict:
    try:
        return load_role("robot-fc")
    except FileNotFoundError:
        return load_role("robot")


def quotes(cfg: dict | None = None) -> dict:
    cfg = cfg or load()
    skill = cfg["courier_quote"]["skill_id"]
    skill_price = int(cfg["skills"][skill]["price_yocto"])
    courier_price = int(cfg["courier_quote"]["price_yocto"])
    max_price = int(cfg["procurement"]["max_price_yocto"])
    pantry_ok = skill_price <= max_price
    courier_ok = courier_price <= max_price and not cfg["courier_quote"].get("must_refuse")
    refused = {
        "account": cfg["accounts"]["courier"],
        "skill_id": skill,
        "price_yocto": str(courier_price),
        "accepted": False,
        "reason": cfg["courier_quote"].get("reason", "above max price"),
    }
    accepted = {
        "account": cfg["accounts"]["robot"],
        "supplier": cfg["accounts"]["pantry"],
        "skill_id": skill,
        "price_yocto": str(skill_price),
        "accepted": pantry_ok,
        "pantry_bps": cfg["procurement"]["pantry_bps"],
    }
    if courier_ok:
        refused["accepted"] = True
    return {"accepted": accepted, "refused": refused, "kill_switch": kill_switch(cfg)}


def create_claim(skill_id: str = "fetch_honey", offline: bool = False) -> dict:
    cfg = load()
    require_live(cfg)
    q = quotes(cfg)
    if not q["accepted"]["accepted"]:
        raise SystemExit("dispatcher refused all quotes")
    skill = cfg["skills"][skill_id]
    price = int(skill["price_yocto"])
    if price > int(cfg["procurement"]["max_price_yocto"]):
        raise SystemExit("skill price above procurement.max_price_yocto")
    robot_keys = _robot_pk_record()
    guest = load_role("guest")
    deadline_ms = int(time.time() * 1000) + int(cfg["procurement"]["deadline_seconds"]) * 1000
    args = {
        "robot": cfg["accounts"]["robot"],
        "robot_pk": robot_keys["near_public_key"],
        "pantry": cfg["accounts"]["pantry"],
        "skill_id": skill_id,
        "price": str(price),
        "pantry_bps": cfg["procurement"]["pantry_bps"],
        "deadline_ms": deadline_ms,
        "token": cfg["ft_contract"],
        "refused_quote": json.dumps(q["refused"]),
    }
    if offline or not cfg.get("escrow_account"):
        claim_id = f"offline-{skill_id}-{int(time.time())}"
        rec = {"claim_id": claim_id, "offline": True, "args": args, "quotes": q}
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        (RECEIPTS_DIR / f"{claim_id}.json").write_text(json.dumps(rec, indent=2) + "\n")
        return rec
    client = _client(cfg)
    nonce = next_nonce(client, cfg["accounts"]["guest"], guest["near_public_key"])
    signed = sign_function_call(
        guest,
        cfg["accounts"]["guest"],
        cfg["escrow_account"],
        "create_claim",
        args,
        nonce,
        client.block_hash(),
    )
    result = client.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    claim_id = None
    for log in result.get("receipts_outcome", []):
        for line in log.get("outcome", {}).get("logs", []):
            if line.startswith("created "):
                claim_id = line.split(" ", 1)[1]
    rec = {"claim_id": claim_id, "tx": tx, "args": args, "quotes": q, "explorer": explorer_tx(cfg.get("network", "testnet"), tx, cfg["accounts"]["guest"])}
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    if claim_id:
        (RECEIPTS_DIR / f"{claim_id}.json").write_text(json.dumps(rec, indent=2) + "\n")
    return rec


def prepare_claim(skill_id: str = "fetch_honey", offline: bool = False) -> dict:
    rec = create_claim(skill_id, offline=offline)
    claim_id = rec.get("claim_id")
    if not claim_id:
        raise SystemExit("create_claim produced no claim_id")
    funded = fund_claim(claim_id, offline=offline)
    rec.update(funded)
    rec["skill_id"] = skill_id
    rec["prepared"] = True
    path = RECEIPTS_DIR / f"{claim_id}.json"
    if path.exists():
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored.update(rec)
        path.write_text(json.dumps(stored, indent=2, default=str) + "\n", encoding="utf-8")
        rec = stored
    return rec


def fund_claim(claim_id: str, offline: bool = False) -> dict:
    cfg = load()
    require_live(cfg)
    guest = load_role("guest")
    receipt_path = RECEIPTS_DIR / f"{claim_id}.json"
    stored = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    price = int(stored.get("args", {}).get("price") or cfg["skills"]["fetch_honey"]["price_yocto"])
    if offline or not cfg.get("escrow_account"):
        stored["funded"] = True
        stored["offline"] = True
        receipt_path.write_text(json.dumps(stored, indent=2) + "\n")
        return stored
    client = _client(cfg)
    args = {
        "receiver_id": cfg["escrow_account"],
        "amount": str(price),
        "msg": claim_id,
    }
    nonce = next_nonce(client, cfg["accounts"]["guest"], guest["near_public_key"])
    signed = sign_function_call(
        guest,
        cfg["accounts"]["guest"],
        cfg["ft_contract"],
        "ft_transfer_call",
        args,
        nonce,
        client.block_hash(),
        deposit=1,
        gas=80_000_000_000_000,
    )
    result = client.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    stored["fund_tx"] = tx
    stored["fund_explorer"] = explorer_tx(cfg.get("network", "testnet"), tx, cfg["accounts"]["guest"])
    receipt_path.write_text(json.dumps(stored, indent=2) + "\n")
    return stored


def _call_robot(method: str, args: dict, deposit: int = 0) -> dict:
    # Fixed: complete and pay_supplier are not payable, so the robot attaches no deposit.
    cfg = load()
    require_live(cfg)
    robot_acct = cfg["accounts"]["robot"]
    keys = _robot_pk_record()
    client = _client(cfg)
    nonce = next_nonce(client, robot_acct, keys["near_public_key"])
    signed = sign_function_call(
        keys,
        robot_acct,
        cfg["escrow_account"],
        method,
        args,
        nonce,
        client.block_hash(),
        deposit=deposit,
        gas=80_000_000_000_000,
    )
    result = client.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {
        "tx": tx,
        "explorer": explorer_tx(cfg.get("network", "testnet"), tx, robot_acct),
        "result": result,
    }


def complete_claim(claim_id: str, telemetry_hash: str | None, offline: bool = False) -> dict:
    if offline:
        return {"claim_id": claim_id, "complete": "offline", "telemetry_hash": telemetry_hash}
    return _call_robot("complete", {"claim_id": claim_id, "telemetry_hash": telemetry_hash})


def pay_supplier(claim_id: str, offline: bool = False) -> dict:
    if offline:
        return {"claim_id": claim_id, "pay_supplier": "offline"}
    return _call_robot("pay_supplier", {"claim_id": claim_id})


def wrap_near(amount_near: str = "0.15") -> dict:
    """Guest native NEAR -> wrap.testnet. Storage must already be registered."""
    cfg = load()
    require_live(cfg)
    yocto = int(round(float(amount_near) * 10**24))
    if yocto <= 0:
        raise SystemExit("wrap amount must be positive")
    guest = load_role("guest")
    client = _client(cfg)
    nonce = next_nonce(client, cfg["accounts"]["guest"], guest["near_public_key"])
    signed = sign_function_call(
        guest,
        cfg["accounts"]["guest"],
        cfg["ft_contract"],
        "near_deposit",
        {},
        nonce,
        client.block_hash(),
        deposit=yocto,
        gas=30_000_000_000_000,
    )
    result = client.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {
        "tx": tx,
        "yocto": str(yocto),
        "explorer": explorer_tx(cfg.get("network", "testnet"), tx, cfg["accounts"]["guest"]),
        "result": result.get("status"),
    }


def refund_claim(claim_id: str, offline: bool = False) -> dict:
    cfg = load()
    if offline:
        return {"claim_id": claim_id, "refund": "offline"}
    guest = load_role("guest")
    client = _client(cfg)
    nonce = next_nonce(client, cfg["accounts"]["guest"], guest["near_public_key"])
    signed = sign_function_call(
        guest,
        cfg["accounts"]["guest"],
        cfg["escrow_account"],
        "refund",
        {"claim_id": claim_id},
        nonce,
        client.block_hash(),
        deposit=1,
    )
    result = client.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {"tx": tx, "explorer": explorer_tx(cfg.get("network", "testnet"), tx, cfg["accounts"]["guest"])}


def simulate_skill(skill_id: str = "fetch_honey") -> dict:
    payload = {
        "skill_id": skill_id,
        "success": True,
        "gps": [0.3, 0.0, 0.0],
        "compass": [1.0, 0.0, 0.0],
        "reported_at": datetime.now(timezone.utc).isoformat(),
        "simulated": True,
    }
    payload["telemetry_hash"] = telemetry_hash(payload)
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    OUTBOX.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def read_outbox() -> dict | None:
    if not OUTBOX.exists():
        return None
    return json.loads(OUTBOX.read_text(encoding="utf-8"))


def _claim_settled(stored: dict) -> bool:
    complete = stored.get("complete")
    if stored.get("settled_at"):
        return True
    if isinstance(complete, dict) and (
        complete.get("tx") or complete.get("complete") == "offline" or complete.get("telemetry_hash")
    ):
        return True
    return False


def _open_claim_for_skill(skill_id: str) -> tuple[str | None, dict]:
    claim_files = sorted(RECEIPTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in claim_files:
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(stored, dict):
            continue
        args_skill = (stored.get("args") or {}).get("skill_id") or stored.get("skill_id")
        if args_skill != skill_id:
            continue
        if _claim_settled(stored):
            continue
        claim_id = stored.get("claim_id")
        if claim_id:
            return claim_id, stored
    return None, {}


def settle_outbox(once: bool = True, offline: bool = False) -> dict | None:
    cfg = load()
    q = quotes(cfg)
    print(json.dumps(q, indent=2))
    while True:
        box = read_outbox()
        if box and box.get("skill_id"):
            # Fixed: settle the open receipt for this skill, not the newest file.
            claim_id, stored = _open_claim_for_skill(box["skill_id"])
            if not claim_id:
                raise SystemExit("no claim receipt for this skill; run create-claim / fund-claim first")
            tel = box.get("telemetry_hash")
            complete = complete_claim(claim_id, tel, offline=offline)
            supplier = pay_supplier(claim_id, offline=offline)
            receipt = {
                "claim_id": claim_id,
                "skill_id": box.get("skill_id"),
                "webots_success": box.get("success", True),
                "telemetry_hash": tel,
                "gps": box.get("gps"),
                "compass": box.get("compass"),
                "complete": complete,
                "pay_supplier": supplier,
                "refused_quote": q["refused"],
                "accepted_quote": q["accepted"],
                "pantry_bps": cfg["procurement"]["pantry_bps"],
                "settled_at": datetime.now(timezone.utc).isoformat(),
            }
            RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
            out = RECEIPTS_DIR / f"{claim_id}.json"
            prev = json.loads(out.read_text()) if out.exists() else {}
            from hotel.peaq import attach_peaq

            attach_peaq(receipt)
            prev.update(receipt)
            out.write_text(json.dumps(prev, indent=2, default=str) + "\n")
            slim = dict(receipt)
            for key in ("complete", "pay_supplier"):
                blob = slim.get(key)
                if isinstance(blob, dict) and "result" in blob:
                    blob = dict(blob)
                    blob.pop("result", None)
                    slim[key] = blob
            print(json.dumps(slim, indent=2, default=str))
            return receipt
        if once:
            print("no settlement/outbox.json yet")
            return None
        time.sleep(2)


def telemetry_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()
