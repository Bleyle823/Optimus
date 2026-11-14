from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

import requests

from hotel.config import load
from hotel.keys import load_role

TOKENS_URL = "https://1click.chaindefuser.com/v0/tokens"
QUOTE_URL = "https://1click.chaindefuser.com/v0/quote"
UA = {"User-Agent": "Mozilla/5.0 hotel-raas", "Accept": "application/json"}


def _oneclick_base() -> str:
    return os.getenv("ONECLICK_URL", "https://1click.chaindefuser.com/v0").rstrip("/")


def _headers() -> dict:
    headers = {"Content-Type": "application/json", **UA}
    jwt = os.getenv("INTENTS_JWT")
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers


def _quote_body(amount: str | None, dry: bool) -> dict:
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
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "dry": dry,
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
        "deadline": deadline,
    }


def _post_quote(body: dict) -> tuple[int, dict]:
    url = _oneclick_base() + "/quote"
    r = requests.post(url, json=body, headers=_headers(), timeout=60)
    try:
        data = r.json()
    except Exception:
        data = {"status": r.status_code, "text": r.text[:2000]}
    return r.status_code, data


def list_tokens() -> list:
    r = requests.get(_oneclick_base() + "/tokens", headers=UA, timeout=30)
    r.raise_for_status()
    return r.json()


def dry_quote(amount: str | None = None) -> dict:
    body = _quote_body(amount, True)
    code, data = _post_quote(body)
    result = {
        "request": body,
        "http_status": code,
        "quote": data,
        "fee_note": "Q-006: without a partner JWT the fee is 0.2%",
    }
    print(json.dumps(result, indent=2)[:8000])
    return result


def _poll_status(deposit_address: str, max_wait_s: int = 360) -> dict:
    url = _oneclick_base() + f"/status?depositAddress={deposit_address}"
    last = {}
    t0 = time.time()
    while time.time() - t0 < max_wait_s:
        r = requests.get(url, headers=UA, timeout=45)
        try:
            last = r.json()
        except Exception:
            last = {"raw": r.text[:2000], "http_status": r.status_code}
        status = str(last.get("status", "")).upper()
        print(f"1click status: {status or last}")
        if status in {"SUCCESS", "REFUNDED", "FAILED", "INCOMPLETE_DEPOSIT"}:
            return last
        time.sleep(8)
    return last


def live_quote_if_sane() -> dict:
    """Mainnet wNEAR -> USDT via 1Click. Requires INTENTS_LIVE=1."""
    from hotel.mainnet_near import ensure_wrap_for_intents, ft_transfer
    from hotel.near_rpc import confirm_mainnet

    dry = dry_quote()
    if dry.get("http_status") != 200:
        raise SystemExit("dry quote failed; refusing live fill")
    needed = int(dry["request"]["amount"])
    confirm_mainnet("execute a tiny Intents 1Click swap")
    wrap_info = ensure_wrap_for_intents(needed)
    body = dict(dry["request"])
    body["dry"] = False
    code, live_data = _post_quote(body)
    if code != 200:
        return {"http_status": code, "wrap": wrap_info, "body": live_data}
    quote = live_data.get("quote") or live_data
    deposit = quote.get("depositAddress")
    amount_in = int(quote.get("amountIn") or needed)
    if not deposit:
        return {"http_status": code, "wrap": wrap_info, "body": live_data, "error": "missing depositAddress"}
    transfer = ft_transfer(deposit, amount_in)
    try:
        requests.post(
            _oneclick_base() + "/deposit/submit",
            json={"depositAddress": deposit, "txHash": transfer["tx"]},
            headers={"Content-Type": "application/json", **UA},
            timeout=45,
        )
    except Exception as exc:
        transfer["deposit_submit_error"] = str(exc)
    status = _poll_status(deposit)
    receipt = {
        "http_status": code,
        "wrap": wrap_info,
        "depositAddress": deposit,
        "wnear_transfer": transfer,
        "quote": {k: quote.get(k) for k in ("amountIn", "amountOut", "amountOutFormatted", "minAmountOut")},
        "status": status,
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "settlement", "receipts", "intents-live-usdt.json")
    try:
        from pathlib import Path

        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        receipt["receipt_file"] = str(p.resolve())
    except OSError:
        pass
    print(json.dumps(receipt, indent=2, default=str)[:12000])
    return receipt