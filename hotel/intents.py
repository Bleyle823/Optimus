from __future__ import annotations

import json
import os

import requests

from hotel.config import load
from hotel.keys import load_role

TOKENS_URL = "https://1click.chaindefuser.com/v0/tokens"
QUOTE_URL = "https://1click.chaindefuser.com/v0/quote"


def list_tokens() -> list:
    r = requests.get(os.getenv("ONECLICK_URL", "https://1click.chaindefuser.com/v0") + "/tokens", timeout=30)
    r.raise_for_status()
    return r.json()


def dry_quote(amount: str | None = None) -> dict:
    cfg = load()
    intents = cfg.get("intents", {})
    robot = cfg["accounts"]["robot"]
    try:
        rec = load_role("robot")
        refund = rec.get("near_implicit") or robot
    except FileNotFoundError:
        refund = robot
    dest = intents.get("destination_asset", "nep141:usdt.tether-token.near")
    recipient = intents.get("refund_to") or refund
    body = {
        "dry": True,
        "swapType": "EXACT_INPUT",
        "slippageTolerance": intents.get("slippage_tolerance", 100),
        "originAsset": "nep141:wrap.near",
        "depositType": "ORIGIN_CHAIN",
        "destinationAsset": dest,
        "amount": amount or intents.get("max_amount_atomic", "100000000000000000000000"),
        "recipient": recipient,
        "recipientType": "DESTINATION_CHAIN",
        "refundTo": recipient,
        "refundType": "ORIGIN_CHAIN",
        "deadline": "2026-12-31T00:00:00.000Z",
    }
    headers = {"Content-Type": "application/json"}
    jwt = os.getenv("INTENTS_JWT")
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    url = os.getenv("ONECLICK_URL", "https://1click.chaindefuser.com/v0") + "/quote"
    r = requests.post(url, json=body, headers=headers, timeout=45)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text[:2000]}
    result = {"request": body, "http_status": r.status_code, "quote": data, "fee_note": "Q-006: without a partner JWT the fee is 0.2%"}
    print(json.dumps(result, indent=2)[:8000])
    return result


def live_quote_if_sane() -> dict:
    """Tiny mainnet fill. Requires INTENTS_LIVE=1 and typing YES."""
    from hotel.near_rpc import confirm_mainnet

    dry = dry_quote()
    quote = dry.get("quote") or {}
    if dry.get("http_status") != 200:
        raise SystemExit("dry quote failed; refusing live fill")
    confirm_mainnet("execute a tiny Intents 1Click swap")
    body = dict(dry["request"])
    body["dry"] = False
    headers = {"Content-Type": "application/json"}
    jwt = os.getenv("INTENTS_JWT")
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    url = os.getenv("ONECLICK_URL", "https://1click.chaindefuser.com/v0") + "/quote"
    r = requests.post(url, json=body, headers=headers, timeout=45)
    return {"http_status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text}
