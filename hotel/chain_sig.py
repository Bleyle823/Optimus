from __future__ import annotations

import json

from hotel.config import load
from hotel.keys import load_role
from hotel.near_rpc import NearClient, next_nonce, sign_function_call

SIGNER_TESTNET = "v1.signer-prod.testnet"


def spike() -> dict:
    """Request an Eddsa / domain-1 signature from the testnet MPC signer.

    Broadcast of the rebuilt Solana tx is left to the operator. The demo's
    credit record does not depend on this spike.
    """
    cfg = load()
    guest = load_role("guest")
    client = NearClient(cfg["rpc"], cfg.get("network", "testnet"))
    args = {
        "request": {
            "path": "hotel-raas-0",
            "payload": "0" * 64,
            "key_version": 0,
            "algo_type": "Eddsa",
        }
    }
    info = {
        "signer": SIGNER_TESTNET,
        "domain": 1,
        "keyType": "Eddsa",
        "note": "Python broadcasts any Solana tx; the contract only requests the signature.",
        "args": args,
    }
    try:
        nonce = next_nonce(client, cfg["accounts"]["guest"], guest["near_public_key"])
        signed = sign_function_call(
            guest,
            cfg["accounts"]["guest"],
            SIGNER_TESTNET,
            "sign",
            args,
            nonce,
            client.block_hash(),
            deposit=1,
            gas=300_000_000_000_000,
        )
        result = client.send(signed)
        info["tx"] = result.get("transaction", {}).get("hash")
        info["status"] = "submitted"
    except Exception as e:
        info["status"] = "not_sent"
        info["error"] = str(e)
        info["hint"] = "Fund guest.testnet and retry. Payload/API may differ by signer version."
    print(json.dumps(info, indent=2)[:8000])
    return info
