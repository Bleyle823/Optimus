from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

import base58
import requests
from nacl.signing import SigningKey

from hotel.keys import signing_key

ACTION_FUNCTION_CALL = 2
ACTION_ADD_KEY = 5
ACTION_DELETE_KEY = 6
CREATE_ACCOUNT = 0
TRANSFER = 3
DEPLOY_CONTRACT = 1


class NearClient:
    def __init__(self, rpc: str, network: str = "testnet"):
        self.rpc = rpc
        self.network = network

    def call(self, method: str, params: Any) -> Any:
        body = {"jsonrpc": "2.0", "id": "hotel", "method": method, "params": params}
        r = requests.post(self.rpc, json=body, timeout=90)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data["result"]

    def view_account(self, account_id: str) -> dict:
        return self.call(
            "query",
            {"request_type": "view_account", "finality": "final", "account_id": account_id},
        )

    def view_call(self, account_id: str, method_name: str, args: dict) -> dict:
        raw = base64.b64encode(json.dumps(args).encode()).decode()
        result = self.call(
            "query",
            {
                "request_type": "call_function",
                "finality": "final",
                "account_id": account_id,
                "method_name": method_name,
                "args_base64": raw,
            },
        )
        if result.get("result"):
            decoded = bytes(result["result"]).decode()
            if decoded:
                result["parsed"] = json.loads(decoded)
        return result

    def access_key(self, account_id: str, public_key: str) -> dict:
        return self.call(
            "query",
            {
                "request_type": "view_access_key",
                "finality": "final",
                "account_id": account_id,
                "public_key": public_key,
            },
        )

    def block_hash(self) -> str:
        status = self.call("status", [])
        return status["sync_info"]["latest_block_hash"]

    def send(self, signed_b64: str) -> dict:
        return self.call("broadcast_tx_commit", [signed_b64])


def _varint(n: int) -> bytes:
    """Borsh length prefix: u32 little-endian, not a compact integer."""
    return int(n).to_bytes(4, "little")


def _str(s: str) -> bytes:
    raw = s.encode()
    return _varint(len(raw)) + raw


def _u64(n: int) -> bytes:
    return int(n).to_bytes(8, "little")


def _u128(n: int) -> bytes:
    return int(n).to_bytes(16, "little")


def _public_key_bytes(near_pk: str) -> bytes:
    prefix, payload = near_pk.split(":", 1)
    if prefix != "ed25519":
        raise ValueError("only ed25519 keys")
    return b"\x00" + base58.b58decode(payload)


def sign_function_call(
    record: dict,
    signer_id: str,
    receiver_id: str,
    method: str,
    args: dict,
    nonce: int,
    block_hash_b58: str,
    deposit: int = 0,
    gas: int = 50_000_000_000_000,
) -> str:
    sk: SigningKey = signing_key(record)
    pub = bytes(sk.verify_key)
    args_bytes = json.dumps(args, separators=(",", ":")).encode()
    tx = b""
    tx += _str(signer_id)
    tx += b"\x00" + pub
    tx += _u64(nonce)
    tx += _str(receiver_id)
    tx += base58.b58decode(block_hash_b58)
    tx += _varint(1)
    tx += bytes([ACTION_FUNCTION_CALL])
    tx += _str(method)
    tx += _varint(len(args_bytes)) + args_bytes
    tx += _u64(gas)
    tx += _u128(deposit)
    digest = hashlib.sha256(tx).digest()
    sig = sk.sign(digest).signature
    signed = tx + b"\x00" + sig
    return base64.b64encode(signed).decode()


def sign_add_function_call_key(
    owner: dict,
    signer_id: str,
    new_pub_near: str,
    receiver_id: str,
    method_names: list[str],
    nonce: int,
    block_hash_b58: str,
    allowance: int | None = None,
) -> str:
    sk = signing_key(owner)
    pub = bytes(sk.verify_key)
    tx = b""
    tx += _str(signer_id)
    tx += b"\x00" + pub
    tx += _u64(nonce)
    tx += _str(signer_id)
    tx += base58.b58decode(block_hash_b58)
    tx += _varint(1)
    tx += bytes([ACTION_ADD_KEY])
    tx += _public_key_bytes(new_pub_near)
    tx += _u64(0)
    # AccessKeyPermission: FunctionCall = 0, FullAccess = 1
    tx += b"\x00"
    # allowance Option<u128>: 0 none, 1 some
    if allowance is None:
        tx += b"\x00"
    else:
        tx += b"\x01" + _u128(allowance)
    tx += _str(receiver_id)
    tx += _varint(len(method_names))
    for m in method_names:
        tx += _str(m)
    digest = hashlib.sha256(tx).digest()
    sig = sk.sign(digest).signature
    signed = tx + b"\x00" + sig
    return base64.b64encode(signed).decode()


def sign_delete_key(
    owner: dict,
    signer_id: str,
    public_key_near: str,
    nonce: int,
    block_hash_b58: str,
) -> str:
    sk = signing_key(owner)
    pub = bytes(sk.verify_key)
    tx = b""
    tx += _str(signer_id)
    tx += b"\x00" + pub
    tx += _u64(nonce)
    tx += _str(signer_id)
    tx += base58.b58decode(block_hash_b58)
    tx += _varint(1)
    tx += bytes([ACTION_DELETE_KEY])
    tx += _public_key_bytes(public_key_near)
    digest = hashlib.sha256(tx).digest()
    sig = sk.sign(digest).signature
    return base64.b64encode(tx + b"\x00" + sig).decode()


def sign_deploy(
    owner: dict,
    signer_id: str,
    wasm: bytes,
    nonce: int,
    block_hash_b58: str,
) -> str:
    sk = signing_key(owner)
    pub = bytes(sk.verify_key)
    tx = b""
    tx += _str(signer_id)
    tx += b"\x00" + pub
    tx += _u64(nonce)
    tx += _str(signer_id)
    tx += base58.b58decode(block_hash_b58)
    tx += _varint(1)
    tx += bytes([DEPLOY_CONTRACT])
    tx += _varint(len(wasm)) + wasm
    digest = hashlib.sha256(tx).digest()
    sig = sk.sign(digest).signature
    signed = tx + b"\x00" + sig
    return base64.b64encode(signed).decode()


def next_nonce(client: NearClient, account_id: str, near_pk: str) -> int:
    ak = client.access_key(account_id, near_pk)
    return int(ak["nonce"]) + 1


def explorer_tx(network: str, tx_hash: str, account_id: str) -> str:
    host = "testnet.nearblocks.io" if network != "mainnet" else "nearblocks.io"
    return f"https://{host}/txns/{tx_hash}"


def confirm_mainnet(action: str) -> None:
    if os.getenv("INTENTS_LIVE") != "1" and os.getenv("PEAQ_LIVE") != "1":
        raise SystemExit(f"refusing {action}: set the matching *_LIVE=1 env and confirm")
    answer = input(f"Type YES to {action} on mainnet: ").strip()
    if answer != "YES":
        raise SystemExit("aborted")


def wait_ms(ms: int) -> None:
    time.sleep(ms / 1000)
