from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from hotel.config import KEYS_DIR, load, require_live
from hotel.keys import ROLE_FILES, derive, load_role
from hotel.near_rpc import NearClient, next_nonce, sign_add_function_call_key, sign_deploy


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="hotel")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("derive-key", help="Ed25519 key: Solana address + NEAR implicit account")
    d.add_argument("--role", choices=list(ROLE_FILES), default="robot")

    sub.add_parser("quotes", help="Accept pantry path, refuse courier quote")

    c = sub.add_parser("create-claim")
    c.add_argument("--skill", default="fetch_honey")
    c.add_argument("--offline", action="store_true")

    f = sub.add_parser("fund-claim")
    f.add_argument("--claim", required=True)
    f.add_argument("--offline", action="store_true")

    sim = sub.add_parser("simulate-skill", help="Write a Webots-shaped outbox without the simulator")
    sim.add_argument("--skill", default="fetch_honey")

    w = sub.add_parser("watch", help="Wait for Webots outbox then complete + pay_supplier")
    w.add_argument("--once", action="store_true")
    w.add_argument("--offline", action="store_true")

    r = sub.add_parser("refund")
    r.add_argument("--claim", required=True)
    r.add_argument("--offline", action="store_true")

    sub.add_parser("add-function-call-key")
    dep = sub.add_parser("deploy-escrow")
    dep.add_argument("--wasm", required=True)
    sub.add_parser("init-escrow", help="Call new() on the task escrow after deploy")

    iq = sub.add_parser("intents-quote")
    iq.add_argument("--dry", action="store_true", default=True)
    iq.add_argument("--live", action="store_true")

    sub.add_parser("peaq-dry")
    sub.add_parser("peaq-live")
    pe = sub.add_parser("peaq-event")
    pe.add_argument("--receipt", required=True)

    am = sub.add_parser("agent-market")
    am.add_argument("--poll", action="store_true")
    am.add_argument("--register", action="store_true")

    sub.add_parser("chain-sig-spike")

    args = p.parse_args(argv)
    if args.cmd == "derive-key":
        rec = derive(args.role)
        print(json.dumps({k: rec[k] for k in rec if k != "secret_key_hex"}, indent=2))
        print(f"wrote {KEYS_DIR / ROLE_FILES[args.role]} (secret omitted above)")
        return
    if args.cmd == "quotes":
        from hotel.dispatcher import quotes

        print(json.dumps(quotes(), indent=2))
        return
    if args.cmd == "create-claim":
        from hotel.dispatcher import create_claim

        print(json.dumps(create_claim(args.skill, offline=args.offline), indent=2, default=str))
        return
    if args.cmd == "fund-claim":
        from hotel.dispatcher import fund_claim

        print(json.dumps(fund_claim(args.claim, offline=args.offline), indent=2, default=str))
        return
    if args.cmd == "simulate-skill":
        from hotel.dispatcher import simulate_skill

        print(json.dumps(simulate_skill(args.skill), indent=2))
        return
    if args.cmd == "watch":
        from hotel.dispatcher import settle_outbox

        settle_outbox(once=args.once, offline=args.offline)
        return
    if args.cmd == "refund":
        from hotel.dispatcher import refund_claim

        print(json.dumps(refund_claim(args.claim, offline=args.offline), indent=2, default=str))
        return
    if args.cmd == "add-function-call-key":
        _add_fc_key()
        return
    if args.cmd == "deploy-escrow":
        _deploy(args.wasm)
        return
    if args.cmd == "init-escrow":
        _init_escrow()
        return
    if args.cmd == "intents-quote":
        from hotel import intents

        if args.live:
            print(json.dumps(intents.live_quote_if_sane(), indent=2, default=str)[:8000])
        else:
            intents.dry_quote()
        return
    if args.cmd == "peaq-dry":
        from hotel.peaq import peaq_dry

        peaq_dry()
        return
    if args.cmd == "peaq-live":
        from hotel.peaq import peaq_live

        print(json.dumps(peaq_live(), indent=2))
        return
    if args.cmd == "peaq-event":
        from hotel.peaq import peaq_event

        peaq_event(args.receipt)
        return
    if args.cmd == "agent-market":
        from hotel import agent_market

        if args.register:
            print(json.dumps(agent_market.register(), indent=2)[:4000])
        print(agent_market.receipt_markdown(agent_market.latest_receipt()))
        if args.poll:
            if not os.getenv("NEAR_AI_API_KEY"):
                raise SystemExit("NEAR_AI_API_KEY is missing; poll loop not started")
            agent_market.run_poll_loop()
        return
    if args.cmd == "chain-sig-spike":
        from hotel.chain_sig import spike

        spike()
        return


def _add_fc_key() -> None:
    cfg = load()
    require_live(cfg)
    owner = load_role("robot")
    fc = derive("robot-fc")
    if not cfg.get("escrow_account"):
        print(json.dumps({"wrote": "keys/robot-function-call.json", "near_public_key": fc["near_public_key"], "note": "set escrow_account then re-run to broadcast add_key"}, indent=2))
        return
    client = NearClient(cfg["rpc"], cfg.get("network", "testnet"))
    nonce = next_nonce(client, cfg["accounts"]["robot"], owner["near_public_key"])
    signed = sign_add_function_call_key(
        owner,
        cfg["accounts"]["robot"],
        fc["near_public_key"],
        cfg["escrow_account"],
        ["complete", "pay_supplier"],
        nonce,
        client.block_hash(),
    )
    result = client.send(signed)
    print(json.dumps({"tx": result.get("transaction", {}).get("hash"), "function_call_key": fc["near_public_key"], "methods": ["complete", "pay_supplier"]}, indent=2))


def _init_escrow() -> None:
    cfg = load()
    require_live(cfg)
    if not cfg.get("escrow_account"):
        raise SystemExit("set escrow_account first")
    guest = load_role("guest")
    client = NearClient(cfg["rpc"], cfg.get("network", "testnet"))
    nonce = next_nonce(client, cfg["escrow_account"], guest["near_public_key"])
    signed = sign_function_call(
        guest,
        cfg["escrow_account"],
        cfg["escrow_account"],
        "new",
        {"owner": cfg["accounts"]["guest"]},
        nonce,
        client.block_hash(),
    )
    result = client.send(signed)
    print(json.dumps({"tx": result.get("transaction", {}).get("hash")}, indent=2))


def _deploy(wasm: str) -> None:
    cfg = load()
    require_live(cfg)
    if not cfg.get("escrow_account"):
        raise SystemExit("set NEAR_ESCROW_ACCOUNT / config escrow_account to the named contract account")
    wasm_bytes = Path(wasm).read_bytes()
    guest = load_role("guest")
    client = NearClient(cfg["rpc"], cfg.get("network", "testnet"))
    nonce = next_nonce(client, cfg["escrow_account"], guest["near_public_key"])
    signed = sign_deploy(guest, cfg["escrow_account"], wasm_bytes, nonce, client.block_hash())
    result = client.send(signed)
    print(json.dumps({"tx": result.get("transaction", {}).get("hash"), "note": "contract account must already exist and guest must be a key on it"}, indent=2))


if __name__ == "__main__":
    main()
