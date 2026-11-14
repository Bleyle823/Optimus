from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from hotel.config import PEAQ_STATUS, RECEIPTS_DIR, ROOT, SETTLEMENT_DIR, load
from hotel.keys import load_role


MIN_CLI = (0, 0, 19)
WIN_SHIM = Path(__file__).resolve().parent / "winshim"


def _did_document(robot: dict) -> Path:
    """Public DID. The machine id is machine type plus this key, and it cannot change later."""
    cfg = load()
    doc = {
        "verificationMethods": [],
        "authentication": [],
        "serviceEndpoints": [
            {
                "id": "near-robot",
                "serviceType": "NEAR",
                "serviceEndpoint": cfg["accounts"]["robot"],
            }
        ],
    }
    SETTLEMENT_DIR.mkdir(parents=True, exist_ok=True)
    path = SETTLEMENT_DIR / "peaq_did.json"
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return path


MACHINE_ID = "77174012743344590367033095698920089416728647386143366545675443241571867865158"
OWNER_WALLET = "svm-owner"
OPERATOR_WALLET = "svm-operator"


def _activate_cmd(
    exe: str,
    robot: dict | None,
    *,
    live: bool,
    max_in: str | None = None,
    owner_wallet: str | None = None,
    phase: str | None = None,
) -> list[str]:
    pay_in = os.getenv("PEAQ_PAY_IN", "USDC")
    cmd = [exe, "activate", "--chain", "solana", "--tier", "basic", "--pay-in", pay_in]
    if phase:
        cmd.extend(["--phase", phase])
    if not live:
        cmd.extend(["--dry-run", "--json"])
    else:
        cmd.extend(["--yes", "--wait-minutes", "60"])
        if max_in:
            cmd.extend(["--max-in", str(max_in)])
        elif phase in (None, "request"):
            raise SystemExit("live activation needs --max-in from peaq-dry")
        if owner_wallet:
            cmd.extend(["--owner-wallet", owner_wallet])
        cmd.extend(["--operator-wallet", OPERATOR_WALLET])
    if robot and robot.get("solana_address") and robot.get("public_key_hex"):
        cmd.extend(
            [
                "--solana-owner",
                robot["solana_address"],
                "--manufacturer",
                robot["solana_address"],
                "--machine-type",
                "hotel-robot",
                "--credential-subject-hex",
                "0x" + robot["public_key_hex"],
                "--did-document",
                str(_did_document(robot)),
                "--max-native-fee-lamports",
                "5000000",
                "--max-native-rent-lamports",
                "20000000",
            ]
        )
    return cmd


def _stdout_json(text: str) -> dict | None:
    start = (text or "").find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        return None


def _quote_max_in(preview: dict | None) -> str | None:
    if not preview:
        return None
    obs = preview.get("observations") or {}
    quote = obs.get("activation_quote") or {}
    if quote.get("status") == "refused" or quote.get("error_code") == "INSUFFICIENT_BALANCE":
        return None
    for key in ("suggested_max_in", "max_in", "suggestedMaxIn"):
        if quote.get(key):
            return str(quote[key])
    terminal = preview.get("terminal") or {}
    for blob in (quote, preview.get("accepted_limits") or {}, terminal):
        for key in ("suggested_max_in", "max_in", "bond", "bond_amount"):
            if blob.get(key):
                return str(blob[key])
    return None


def _ensure_owner_wallet(robot: dict, env: dict) -> str:
    """Import the robot Ed25519 seed as OWS Solana wallet svm-owner. Never prints the seed."""
    if not env.get("OWS_PASSPHRASE"):
        env["OWS_PASSPHRASE"] = "hotel-local-ows"
        os.environ["OWS_PASSPHRASE"] = env["OWS_PASSPHRASE"]
    seed_hex = robot["secret_key_hex"][:64]
    private_key = "0x" + seed_hex
    try:
        from peaq_os_sdk import PeaqosClient
        from peaq_os_sdk.constants import IMPORT_CHAIN_SOLANA
    except Exception as exc:
        raise SystemExit(f"peaq OWS SDK missing ({exc}); pip install 'peaq_os_sdk[ows]'") from exc
    try:
        info = PeaqosClient.import_wallet(
            OWNER_WALLET,
            private_key,
            passphrase=env["OWS_PASSPHRASE"],
            chain=IMPORT_CHAIN_SOLANA,
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "exist" not in msg and "already" not in msg:
            raise SystemExit(f"could not import Solana owner wallet: {exc}") from exc
        info = None
        try:
            listed = PeaqosClient.list_wallets()
            for w in listed or []:
                name = getattr(w, "name", None) or (w.get("name") if isinstance(w, dict) else None)
                if name == OWNER_WALLET:
                    info = w
                    break
        except Exception:
            info = None
    addr = None
    if info is not None:
        addr = getattr(info, "solana_address", None) or getattr(info, "address", None)
        if isinstance(info, dict):
            addr = info.get("solana_address") or info.get("address")
        accounts = getattr(info, "accounts", None)
        if not addr and accounts:
            for acct in accounts:
                a = getattr(acct, "address", None) or (acct.get("address") if isinstance(acct, dict) else None)
                net = getattr(acct, "network", None) or (acct.get("network") if isinstance(acct, dict) else "")
                if a and "solana" in str(net).lower():
                    addr = a
                    break
    if addr and addr != robot["solana_address"]:
        raise SystemExit(
            f"imported OWS wallet Solana address {addr} does not match robot owner {robot['solana_address']}"
        )
    return OWNER_WALLET


def _ensure_operator_wallet(env: dict) -> str:
    """Import PEAQOS_PRIVATE_KEY as OWS EVM wallet svm-operator. Never prints the key."""
    try:
        from peaq_os_sdk import PeaqosClient
        from peaq_os_sdk.constants import IMPORT_CHAIN_EVM
    except Exception as exc:
        raise SystemExit(f"peaq OWS SDK missing ({exc})") from exc
    try:
        info = PeaqosClient.get_wallet(OPERATOR_WALLET)
        print("peaq operator", info.peaq_address)
        return OPERATOR_WALLET
    except Exception:
        pass
    key = (env.get("PEAQOS_PRIVATE_KEY") or os.getenv("PEAQOS_PRIVATE_KEY") or "").strip()
    if not key:
        raise SystemExit("PEAQOS_PRIVATE_KEY is empty; paste the peaq operator hex key in .env")
    if not key.startswith("0x"):
        key = "0x" + key
    if not env.get("OWS_PASSPHRASE"):
        env["OWS_PASSPHRASE"] = "hotel-local-ows"
        os.environ["OWS_PASSPHRASE"] = env["OWS_PASSPHRASE"]
    try:
        from peaq_os_sdk import PeaqosClient
        from peaq_os_sdk.constants import IMPORT_CHAIN_EVM
    except Exception as exc:
        raise SystemExit(f"peaq OWS SDK missing ({exc})") from exc
    try:
        PeaqosClient.import_wallet(
            OPERATOR_WALLET,
            key,
            passphrase=env["OWS_PASSPHRASE"],
            chain=IMPORT_CHAIN_EVM,
        )
    except Exception as exc:
        if "exist" not in str(exc).lower() and "already" not in str(exc).lower():
            raise SystemExit(f"could not import peaq operator wallet: {exc}") from exc
    info = PeaqosClient.get_wallet(OPERATOR_WALLET)
    print("peaq operator", info.peaq_address)
    return OPERATOR_WALLET


def _peaq_env() -> dict:
    """Fixed: let peaqos import on Windows (pwd and OWS shims under hotel/winshim)."""
    load()
    import sys

    shim = str(WIN_SHIM)
    if shim not in sys.path:
        sys.path.insert(0, shim)
    env = os.environ.copy()
    if not env.get("PEAQOS_SVM_RPC_URL") and env.get("SOLANA_RPC"):
        env["PEAQOS_SVM_RPC_URL"] = env["SOLANA_RPC"]
    env.setdefault("PEAQOS_RPC_URL", "https://peaq.api.onfinality.io/public")
    env.setdefault("PEAQOS_NETWORK", "peaq")
    env.setdefault("OWS_PASSPHRASE", "hotel-local-ows")
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = shim if not prev else shim + os.pathsep + prev
    return env


def _parse_version(text: str) -> tuple[int, int, int] | None:
    for token in text.replace(",", " ").split():
        parts = token.strip().split(".")
        if len(parts) >= 3 and all(p.isdigit() for p in parts[:3]):
            return int(parts[0]), int(parts[1]), int(parts[2])
    return None


def peaq_dry() -> dict:
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
        "command": "peaqos activate --chain solana --tier basic --dry-run",
        "live_cost": "about 0.015 SOL on the owner, quoted bond, ~0.05 PEAQ on operator wallet",
        "live_gated": "PEAQ_LIVE=1 after the testnet loop is on camera",
    }
    if not exe:
        info["status"] = "cli_missing"
        write_peaq_status(info)
        print(json.dumps(info, indent=2))
        print("Install: pip install 'peaq-os-cli[solana,ows]>=0.0.19'  (Python 3.10+)")
        return info
    try:
        ver = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20, env=_peaq_env())
        parsed = _parse_version(ver.stdout + ver.stderr)
        info["version_output"] = (ver.stdout + ver.stderr).strip()
        info["version"] = None if not parsed else ".".join(map(str, parsed))
        if parsed and parsed < MIN_CLI:
            info["status"] = "cli_too_old"
            write_peaq_status(info)
            print(json.dumps(info, indent=2))
            return info
    except Exception as e:
        info["version_error"] = str(e)
    cmd = _activate_cmd(exe, robot, live=False)
    try:
        run = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            cwd=str(ROOT),
            env=_peaq_env(),
        )
        info["dry_run_exit"] = run.returncode
        info["dry_run_stdout"] = (run.stdout or "")[-4000:]
        info["dry_run_stderr"] = (run.stderr or "")[-4000:]
        info["status"] = "ok" if run.returncode == 0 else "dry_run_failed"
    except Exception as e:
        info["status"] = "dry_run_error"
        info["error"] = str(e)
    write_peaq_status(info)
    print(json.dumps(info, indent=2)[:8000])
    return info


def write_peaq_status(info: dict) -> dict:
    """Gitignored machine identity beside receipts. Never a live Solana bond."""
    slim = {
        "solana_address": info.get("solana_owner"),
        "near_implicit": info.get("near_implicit"),
        "cli_version": info.get("version"),
        "status": info.get("status"),
        "home_chain": 5,
        "live": False,
        "command": "peaqos activate --chain solana --tier basic --dry-run",
        "note": info.get("note"),
    }
    SETTLEMENT_DIR.mkdir(parents=True, exist_ok=True)
    PEAQ_STATUS.write_text(json.dumps(slim, indent=2) + "\n", encoding="utf-8")
    info["status_path"] = str(PEAQ_STATUS)
    return slim


def activity_payload(receipt: dict) -> dict:
    return {
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
        "submitted": False,
    }


def attach_peaq(receipt: dict) -> dict:
    """Record Solana machine identity on the NEAR receipt. Does not submit on mainnet."""
    dry = peaq_dry()
    activity = activity_payload(receipt)
    receipt["solana_address"] = dry.get("solana_owner")
    receipt["near_implicit"] = dry.get("near_implicit")
    receipt["peaq"] = {
        "solana_address": dry.get("solana_owner"),
        "near_implicit": dry.get("near_implicit"),
        "status": dry.get("status"),
        "cli_version": dry.get("version"),
        "home_chain": 5,
        "activity": activity,
        "submitted": False,
    }
    return receipt


def peaq_live() -> dict:
    from hotel.near_rpc import confirm_mainnet

    load()
    if os.getenv("PEAQ_LIVE") != "1":
        raise SystemExit("refusing funded activation: set PEAQ_LIVE=1 after the testnet loop is filmed")
    confirm_mainnet("activate a peaq machine on Solana mainnet (bond is not withdrawable)")
    exe = shutil.which("peaqos") or shutil.which("peaq-os") or shutil.which("peaq-os-cli")
    if not exe:
        raise SystemExit("peaq CLI not on PATH")
    robot = load_role("robot")
    env = _peaq_env()
    dry = subprocess.run(
        _activate_cmd(exe, robot, live=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        cwd=str(ROOT),
        env=env,
    )
    preview = _stdout_json(dry.stdout or "")
    max_in = _quote_max_in(preview)
    quote = ((preview or {}).get("observations") or {}).get("activation_quote") or {}
    owner_wallet = _ensure_owner_wallet(robot, env)
    _ensure_operator_wallet(env)
    code = quote.get("error_code")
    if code == "OPERATOR_NOT_REGISTERED":
        print("operator not bound yet; running [1/7] registration on peaq")
        reg = subprocess.run(
            _activate_cmd(
                exe, robot, live=True, owner_wallet=owner_wallet, phase="registration"
            ),
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=str(ROOT),
        )
        if reg.returncode not in (0, 2):
            raise SystemExit(f"operator registration failed: exit {reg.returncode}")
        dry = subprocess.run(
            _activate_cmd(exe, robot, live=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            cwd=str(ROOT),
            env=env,
        )
        preview = _stdout_json(dry.stdout or "")
        max_in = _quote_max_in(preview)
        quote = ((preview or {}).get("observations") or {}).get("activation_quote") or {}
        code = quote.get("error_code")
    if not max_in and code == "REQUEST_ALREADY_OPEN":
        max_in = os.getenv("PEAQ_MAX_IN") or "195863"
        print("request already open; resuming with --max-in", max_in)
    if not max_in:
        raise SystemExit(
            "aborting live peaq: dry-run did not quote a bond. "
            f"exit={dry.returncode} quote_status={quote.get('status')} "
            f"error={quote.get('error_code') or (dry.stderr or '')[-500:]}"
        )
    cmd = _activate_cmd(exe, robot, live=True, max_in=max_in, owner_wallet=owner_wallet)
    run = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", env=env, cwd=str(ROOT))
    info = {
        "exit": run.returncode,
        "max_in": max_in,
        "owner_wallet": owner_wallet,
        "solana_owner": robot["solana_address"],
        "machine_id": MACHINE_ID,
    }
    write_peaq_status(
        {
            **info,
            "solana_owner": robot["solana_address"],
            "near_implicit": robot["near_implicit"],
            "status": "live_ok" if run.returncode == 0 else "live_failed",
            "version": None,
            "note": "live activation attempted",
        }
    )
    return info


def peaq_event(receipt_path: str) -> dict:
    """Activity event. Submits on Solana EventRegistry only when PEAQ_LIVE=1."""
    path = Path(receipt_path)
    if not path.exists():
        path = RECEIPTS_DIR / receipt_path
    receipt = json.loads(path.read_text(encoding="utf-8"))
    payload = activity_payload(receipt)
    if os.getenv("PEAQ_LIVE") != "1":
        print(json.dumps(payload, indent=2))
        return payload
    dry = peaq_dry()
    preview = _stdout_json(dry.get("dry_run_stdout") or "")
    terminal = (preview or {}).get("terminal") or {}
    quote = ((preview or {}).get("observations") or {}).get("activation_quote") or {}
    registered = bool(terminal.get("machine_present") or terminal.get("is_bonded"))
    registered = registered or quote.get("error_code") == "MACHINE_ALREADY_ACTIVE"
    registered = registered or "MACHINE_ALREADY_ACTIVE" in (dry.get("dry_run_stdout") or "")
    if not registered:
        payload["submitted"] = False
        payload["submit"] = "machine is not registered yet; skipped EventRegistry"
        print(json.dumps(payload, indent=2)[:4000])
        return payload
    exe = shutil.which("peaqos") or shutil.which("peaq-os") or shutil.which("peaq-os-cli")
    if not exe:
        raise SystemExit("peaq CLI not on PATH")
    robot = load_role("robot")
    env = _peaq_env()
    _ensure_owner_wallet(robot, env)
    env["PEAQOS_OWS_WALLET"] = OWNER_WALLET
    raw_path = SETTLEMENT_DIR / "peaq_event_raw.json"
    raw_path.write_text(json.dumps(payload["rawData"], indent=2) + "\n", encoding="utf-8")
    ts = str(int(__import__("time").time()))
    cmd = [
        exe,
        "qualify",
        "event",
        "--machine-id",
        MACHINE_ID,
        "--type",
        "activity",
        "--value",
        "0",
        "--ts",
        ts,
        "--trust",
        "self",
        "--source-chain",
        "same",
        "--raw-data",
        str(raw_path),
        "--yes",
    ]
    run = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        cwd=str(ROOT),
        env=env,
    )
    payload["submitted"] = run.returncode == 0
    payload["submit_exit"] = run.returncode
    payload["submit_stdout"] = (run.stdout or "")[-2000:]
    payload["submit_stderr"] = (run.stderr or "")[-2000:]
    receipt["peaq"] = {**(receipt.get("peaq") or {}), "activity": payload, "submitted": payload["submitted"]}
    path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in payload if k != "rawData"}, indent=2)[:4000])
    return payload
