"""Robot implicit account on NEAR mainnet (wrap.near for Intents)."""
from __future__ import annotations

import json
import os

from hotel.keys import load_role
from hotel.near_rpc import NearClient, confirm_mainnet, explorer_tx, next_nonce, sign_function_call

WRAP_NEAR = "wrap.near"
MAINNET_RPC = os.getenv("NEAR_MAINNET_RPC", "https://rpc.mainnet.near.org")


def _robot() -> tuple[dict, str]:
    rec = load_role("robot")
    account = rec.get("near_implicit")
    if not account:
        raise SystemExit("robot key missing near_implicit")
    return rec, account


def client() -> NearClient:
    return NearClient(MAINNET_RPC, "mainnet")


def ft_balance_yocto(account_id: str) -> int:
    c = client()
    out = c.view_call(WRAP_NEAR, "ft_balance_of", {"account_id": account_id})
    raw = out.get("parsed")
    if raw is None and out.get("result"):
        raw = json.loads(bytes(out["result"]).decode())
    return int(raw) if raw is not None else 0


def storage_deposit(account_id: str, yocto: int = 125_000_000_000_000_000_000_000) -> dict:
    """Register wrap.near balance storage for account_id (pays from robot implicit)."""
    confirm_mainnet("pay wrap.near storage on mainnet")
    rec, signer = _robot()
    c = client()
    nonce = next_nonce(c, signer, rec["near_public_key"])
    signed = sign_function_call(
        rec,
        signer,
        WRAP_NEAR,
        "storage_deposit",
        {"account_id": account_id, "registration_only": True},
        nonce,
        c.block_hash(),
        deposit=yocto,
        gas=30_000_000_000_000,
    )
    result = c.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {"tx": tx, "explorer": explorer_tx("mainnet", tx, signer), "yocto": str(yocto)}


def near_deposit_wrap(amount_near: float) -> dict:
    """Native NEAR on implicit -> wNEAR."""
    confirm_mainnet("wrap NEAR on mainnet for Intents")
    yocto = int(round(amount_near * 10**24))
    if yocto <= 0:
        raise SystemExit("wrap amount must be positive")
    rec, signer = _robot()
    bal = client().view_account(signer).get("amount", "0")
    if int(bal) < yocto + 10**22:
        raise SystemExit(f"implicit native balance too low for wrap: have {int(bal)/1e24:.6f} NEAR")
    c = client()
    nonce = next_nonce(c, signer, rec["near_public_key"])
    signed = sign_function_call(
        rec,
        signer,
        WRAP_NEAR,
        "near_deposit",
        {},
        nonce,
        c.block_hash(),
        deposit=yocto,
        gas=50_000_000_000_000,
    )
    result = c.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {"tx": tx, "explorer": explorer_tx("mainnet", tx, signer), "yocto": str(yocto)}


def ft_transfer(receiver_id: str, amount_yocto: int) -> dict:
    rec, signer = _robot()
    c = client()
    nonce = next_nonce(c, signer, rec["near_public_key"])
    signed = sign_function_call(
        rec,
        signer,
        WRAP_NEAR,
        "ft_transfer",
        {"receiver_id": receiver_id, "amount": str(amount_yocto)},
        nonce,
        c.block_hash(),
        deposit=1,
        gas=80_000_000_000_000,
    )
    result = c.send(signed)
    tx = result.get("transaction", {}).get("hash", "")
    return {"tx": tx, "explorer": explorer_tx("mainnet", tx, signer), "amount": str(amount_yocto)}


def ensure_wrap_for_intents(needed_yocto: int) -> dict:
    """Storage + wrap if wNEAR balance below needed_yocto."""
    _, signer = _robot()
    out: dict = {"account": signer, "needed_yocto": str(needed_yocto)}
    bal = 0
    try:
        bal = ft_balance_yocto(signer)
    except Exception as exc:
        out["balance_error"] = str(exc)
        if os.getenv("INTENTS_LIVE") == "1" or os.getenv("HOTEL_CONFIRM") == "YES":
            out["storage"] = storage_deposit(signer)
            bal = ft_balance_yocto(signer)
    out["wrap_balance_before"] = str(bal)
    if bal < needed_yocto:
        if "storage" not in out:
            try:
                ft_balance_yocto(signer)
            except Exception:
                out["storage"] = storage_deposit(signer)
                bal = ft_balance_yocto(signer)
        shortfall = needed_yocto - bal
        wrap_near = shortfall / 10**24 + 0.002
        out["wrap"] = near_deposit_wrap(wrap_near)
        out["wrap_balance_after"] = str(ft_balance_yocto(signer))
    else:
        out["wrap_skipped"] = True
    return out