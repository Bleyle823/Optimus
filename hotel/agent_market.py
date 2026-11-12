from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from hotel.config import RECEIPTS_DIR, load


def _headers() -> dict:
    token = os.getenv("NEAR_AI_API_KEY", "")
    if not token:
        raise SystemExit("NEAR_AI_API_KEY is missing; listing token never belongs in the repo")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _base() -> str:
    return os.getenv("AGENT_MARKET_BASE", "https://market.near.ai").rstrip("/")


def latest_receipt() -> dict | None:
    files = sorted(RECEIPTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def receipt_markdown(receipt: dict | None) -> str:
    cfg = load()
    if not receipt:
        return "No settlement receipt yet. Run create-claim, Webots fetch_honey, then watch --once.\n"
    complete = receipt.get("complete") or {}
    supplier = receipt.get("pay_supplier") or {}
    refused = receipt.get("refused_quote") or {}
    return "\n".join(
        [
            "# Hotel RaaS deliverable",
            "",
            f"- claim id: `{receipt.get('claim_id')}`",
            f"- skill: `{receipt.get('skill_id')}`",
            f"- Webots success: `{receipt.get('webots_success')}`",
            f"- complete tx: `{complete.get('tx')}`",
            f"- pay_supplier tx: `{supplier.get('tx')}`",
            f"- telemetry hash: `{receipt.get('telemetry_hash')}`",
            f"- refused courier: `{refused.get('account')}` at `{refused.get('price_yocto')}` ({refused.get('reason')})",
            f"- robot: `{cfg['accounts']['robot']}` pantry: `{cfg['accounts']['pantry']}`",
            "",
            "Hiring this listing from the same operator does not count toward Agent Market reputation.",
            "",
        ]
    )


def register() -> dict:
    body = {
        "name": "hotel-raas-tiago",
        "description": "Pay-per-skill TIAGo in a Webots kitchen. Deliverable is a NEAR task-escrow receipt plus the Webots result.",
        "endpoint": os.getenv("AGENT_MARKET_CALLBACK", "http://127.0.0.1:8787/hire"),
    }
    url = _base() + "/v1/agents"
    r = requests.post(url, json=body, headers=_headers(), timeout=30)
    return {"status": r.status_code, "body": _safe(r)}


def poll_jobs() -> dict:
    url = _base() + "/v1/jobs"
    r = requests.get(url, headers=_headers(), timeout=30)
    return {"status": r.status_code, "body": _safe(r)}


def submit_job(job_id: str, markdown: str) -> dict:
    url = _base() + f"/v1/jobs/{job_id}/complete"
    r = requests.post(url, json={"result": markdown}, headers=_headers(), timeout=30)
    return {"status": r.status_code, "body": _safe(r)}


def heartbeat() -> dict:
    url = _base() + "/v1/agents/heartbeat"
    r = requests.post(url, json={"status": "idle"}, headers=_headers(), timeout=15)
    return {"status": r.status_code, "body": _safe(r)}


def _safe(r: requests.Response):
    try:
        return r.json()
    except Exception:
        return r.text[:2000]


def run_poll_loop() -> None:
    interval = int(os.getenv("AGENT_MARKET_POLL_SEC", "15"))
    print("Agent Market poll loop. Ctrl+C to stop. Own-hires do not score reputation.")
    while True:
        try:
            heartbeat()
            jobs = poll_jobs()
            print(json.dumps({"jobs": jobs["status"]}, indent=2))
            body = jobs.get("body")
            items = []
            if isinstance(body, dict):
                items = body.get("jobs") or body.get("data") or []
            elif isinstance(body, list):
                items = body
            md = receipt_markdown(latest_receipt())
            for job in items:
                jid = job.get("id") or job.get("job_id")
                if jid:
                    print(submit_job(str(jid), md))
        except KeyboardInterrupt:
            return
        except Exception as e:
            print("poll error:", e)
        time.sleep(interval)
