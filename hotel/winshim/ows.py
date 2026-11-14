"""Fixed: local OWS stand-in. open-wallet-standard is not on PyPI; peaqos still imports `ows`."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import base58
from nacl.signing import SigningKey

_VAULT = Path(__file__).resolve().parents[2] / "settlement" / "ows_vault.json"
_SOLANA = "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"


def _load() -> dict:
    if not _VAULT.exists():
        return {"wallets": {}}
    return json.loads(_VAULT.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    _VAULT.parent.mkdir(parents=True, exist_ok=True)
    _VAULT.write_text(json.dumps(data), encoding="utf-8")


def _solana_account(seed_hex: str) -> dict:
    sk = SigningKey(bytes.fromhex(seed_hex[:64]))
    addr = base58.b58encode(bytes(sk.verify_key)).decode("ascii")
    return {
        "account_id": f"{_SOLANA}:{addr}",
        "address": addr,
        "chain_id": _SOLANA,
        "derivation_path": "",
    }


def _public(wallet: dict) -> dict:
    return {k: wallet[k] for k in ("id", "name", "created_at", "accounts")}


def import_wallet_private_key(
    name: str,
    private_key_hex: str,
    chain: str | None = None,
    passphrase: str | None = None,
    vault_path_opt: str | None = None,
) -> dict:
    _ = passphrase, vault_path_opt
    hex_key = private_key_hex[2:] if private_key_hex.startswith("0x") else private_key_hex
    data = _load()
    if name in data["wallets"]:
        raise RuntimeError(f"wallet {name} already exists")
    accounts = []
    if (chain or "solana") == "solana":
        accounts.append(_solana_account(hex_key))
    accounts.append(
        {
            "account_id": "eip155:3338:0x0000000000000000000000000000000000000000",
            "address": "0x0000000000000000000000000000000000000000",
            "chain_id": "eip155:3338",
            "derivation_path": "m/44'/60'/0'/0/0",
        }
    )
    rec = {
        "id": str(uuid.uuid4()),
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "seed_hex": hex_key[:64],
        "accounts": accounts,
    }
    data["wallets"][name] = rec
    data["wallets"][rec["id"]] = rec
    _save(data)
    return _public(rec)


def list_wallets(vault_path_opt: str | None = None) -> list:
    _ = vault_path_opt
    seen = set()
    out = []
    for rec in _load()["wallets"].values():
        if rec["id"] in seen:
            continue
        seen.add(rec["id"])
        out.append(_public(rec))
    return out


def get_wallet(name_or_id: str, vault_path_opt: str | None = None) -> dict:
    _ = vault_path_opt
    rec = _load()["wallets"].get(name_or_id)
    if not rec:
        raise RuntimeError(f"wallet {name_or_id} not found")
    return _public(rec)


def export_wallet(name_or_id: str, passphrase: str | None = None, vault_path_opt: str | None = None) -> str:
    _ = passphrase, vault_path_opt
    rec = _load()["wallets"].get(name_or_id)
    if not rec:
        raise RuntimeError(f"wallet {name_or_id} not found")
    return "0x" + rec["seed_hex"]


def create_wallet(*args, **kwargs):
    raise RuntimeError("create_wallet is not used; import the robot seed")


def delete_wallet(name_or_id: str, vault_path_opt: str | None = None) -> None:
    _ = vault_path_opt
    data = _load()
    rec = data["wallets"].pop(name_or_id, None)
    if rec:
        data["wallets"].pop(rec["name"], None)
        data["wallets"].pop(rec["id"], None)
        _save(data)


def _seed(name: str) -> bytes:
    rec = _load()["wallets"].get(name)
    if not rec:
        raise RuntimeError(f"wallet {name} not found")
    return bytes.fromhex(rec["seed_hex"][:64])


def sign_transaction(
    wallet: str,
    chain: str,
    tx_hex: str,
    passphrase: str | None = None,
    index: int | None = None,
    vault_path_opt: str | None = None,
) -> dict:
    _ = chain, passphrase, index, vault_path_opt
    raw = bytes.fromhex(tx_hex.removeprefix("0x"))
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction

    sk = SigningKey(_seed(wallet))
    kp = Keypair.from_bytes(bytes(sk) + bytes(sk.verify_key))
    vtx = VersionedTransaction.from_bytes(raw)
    sig = kp.sign_message(bytes(vtx.message))
    return {"signature": "0x" + bytes(sig).hex()}


def sign_message(
    wallet: str,
    chain: str,
    message: str,
    passphrase: str | None = None,
    encoding: str | None = None,
    index: int | None = None,
    vault_path_opt: str | None = None,
) -> dict:
    _ = chain, passphrase, encoding, index, vault_path_opt
    body = bytes.fromhex(message.removeprefix("0x")) if encoding == "hex" or message.startswith("0x") else message.encode()
    sig = SigningKey(_seed(wallet)).sign(body).signature
    return {"signature": "0x" + bytes(sig).hex()}


def sign_typed_data(*args, **kwargs):
    raise RuntimeError("sign_typed_data is not used for Solana onboarding")
