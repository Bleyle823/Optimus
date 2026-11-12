from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from hotel.config import RECEIPTS_DIR, ROOT, load
from hotel.keys import load_role


MIN_CLI = (0, 0, 19)


def _parse_version(text: str) -> tuple[int, int, int] | None:
    for token in text.replace(",", " ").split():
        parts = token.strip().split(".")
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            return int(parts[0]), int(parts[1]), int(parts[2])
    return None


def peaq_dry() -> dict:
    cfg = load()
    robot = None
    try:
        robot = load_role("robot")
    except FileNotFoundError:
        pass
    exe = shutil.which("peaqos") or shutil.which("peaq-os") or shutil.which("peaq-os-cli")
    info = {
        "cli": exe,
        "min_version": "0.0.19",
        "note": "Bond lock is peaq subscription on Solana. It is not the NEAR task escrow.",
        "solana_owner": robot["solana_address"] if robot else None,
        "near_implicit": robot["near_implicit"] if robot else None,
        "home_chain": 5,
        "command": "peaqos activate --chain solana --dry-run",
        "live_cost": "about 0.015 SOL on the owner, quoted bond, ~0.05 PEAQ on operator wallet",
        "live_gated": "PEAQ_LIVE=1 after the testnet loop is on camera",
    }
    if not exe:
        info["status"] = "cli_missing"
        print(json.dumps(info, indent=2))
        print("Install: pip install 'peaq-os-cli[solana,ows]>=0.0.19'  (Python 3.10+)")
        return info
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
        parsed = _parse_version(ver.stdout + ver.stderr)
        info["version_output"] = (ver.stdout + ver.stderr).strip()
        info["version"] = None if not parsed else ".".join(map(str, parsed))
        if parsed and parsed < MIN_CLI:
            info["status"] = "cli_too_old"
            print(json.dumps(info, indent=2))
            return info
    except Exception as e:
        info["version_error"] = str(e)
    cmd = [exe, "activate", "--chain", "solana", "--dry-run"]
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        info["dry_run_exit"] = run.returncode
        info["dry_run_stdout"] = (run.stdout or "")[-4000:]
        info["dry_run_stderr"] = (run.stderr or "")[-4000:]
        info["status"] = "ok" if run.returncode == 0 else "dry_run_failed"
    except Exception as e:
        info["status"] = "dry_run_error"
        info["error"] = str(e)
    print(json.dumps(info, indent=2)[:8000])
    return info


def peaq_live() -> dict:
    from hotel.near_rpc import confirm_mainnet

    if os.getenv("PEAQ_LIVE") != "1":
        raise SystemExit("refusing funded activation: set PEAQ_LIVE=1 after the testnet loop is filmed")
    confirm_mainnet("activate a peaq machine on Solana mainnet (bond is not withdrawable)")
    exe = shutil.which("peaqos") or shutil.which("peaq-os") or shutil.which("peaq-os-cli")
    if not exe:
        raise SystemExit("peaq CLI not on PATH")
    run = subprocess.run([exe, "activate", "--chain", "solana"], text=True)
    return {"exit": run.returncode}


def peaq_event(receipt_path: str) -> dict:
    """Activity event payload. Does not submit until PEAQ_LIVE=1."""
    path = Path(receipt_path)
    if not path.exists():
        path = RECEIPTS_DIR / receipt_path
    receipt = json.loads(path.read_text(encoding="utf-8"))
    payload = {
        "trustLevel": 0,
        "sourceChainId_note": "NEAR is not in the trust-1 allow list (0, 3338, 8453); hashes go in rawData",
        "rawData": {
            "claim_id": receipt.get("claim_id"),
            "skill_id": receipt.get("skill_id"),
            "complete_tx": (receipt.get("complete") or {}).get("tx"),
            "pay_supplier_tx": (receipt.get("pay_supplier") or {}).get("tx"),
            "telemetry_hash": receipt.get("telemetry_hash"),
            "refused_quote": receipt.get("refused_quote"),
            "webots_success": receipt.get("webots_success"),
        },
        "revenue_event": False,
        "reason": "skill prices in config/hotel.json are under the $10 total_revenue floor; activity only",
    }
    if os.getenv("PEAQ_LIVE") == "1":
        payload["submit"] = "caller must use peaq EventRegistry with the owner key; not auto-broadcast here"
    print(json.dumps(payload, indent=2))
    return payload
