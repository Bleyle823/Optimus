# On-chain record (public hashes)

Judge-friendly links for successful transactions. Full JSON receipts stay gitignored under `settlement/receipts/`; this file is the committed audit trail.

**Escrow (NEAR testnet):** `optimus2-escrow-d144.testnet`  
**Robot implicit (NEAR mainnet / peaq owner):** `150410479da834a2c297586600eb0b90619d43573eb91121729e5480be27f63d`  
**Solana owner:** [`2R3A29rFMorbrhZ5bGY27ERcnttaN5xzGoAPG36cxHTr`](https://solscan.io/account/2R3A29rFMorbrhZ5bGY27ERcnttaN5xzGoAPG36cxHTr)

## NEAR testnet task escrow

### claim-4 (`fetch_honey`, live Webots + `watch --once`, 2026-11-14)

| Step | Transaction |
| --- | --- |
| `create_claim` | [5BKPQXgq8bWjdS8JU8iQEKcEE4xgtedE5PHcfPH1rWzA](https://testnet.nearblocks.io/txns/5BKPQXgq8bWjdS8JU8iQEKcEE4xgtedE5PHcfPH1rWzA) |
| `fund-claim` (`ft_transfer_call`) | [Dijs8gk1qYcXJMv4ReDACFSXTkAaQAgWzUDkrMKNqoES](https://testnet.nearblocks.io/txns/Dijs8gk1qYcXJMv4ReDACFSXTkAaQAgWzUDkrMKNqoES) |
| `complete` | [GtifFSDD78BpZ29SAnEetLjQPuXf56pYaxRAjx4iSA9W](https://testnet.nearblocks.io/txns/GtifFSDD78BpZ29SAnEetLjQPuXf56pYaxRAjx4iSA9W) |
| `pay_supplier` | [43VE9E9VFR7BZ8TyxDCbgJi12oBKrHPN6y5mNe6DvbFD](https://testnet.nearblocks.io/txns/43VE9E9VFR7BZ8TyxDCbgJi12oBKrHPN6y5mNe6DvbFD) |

Courier quote refused on receipt (same policy as config); pantry **40%** (`pantry_bps` 4000).

### claim-3 (`fetch_honey`, simulated skill + live settle, earlier run)

| Step | Transaction |
| --- | --- |
| `complete` | [CDkuc1mHHNTKAsgKEvMXkxfQ1cRyGen6oVry3AK13omn](https://testnet.nearblocks.io/txns/CDkuc1mHHNTKAsgKEvMXkxfQ1cRyGen6oVry3AK13omn) |
| `pay_supplier` | [2KsbtMBa3nwzDXNmR5GwZg9pv9LqmvSQGpsWWMtMdwxV](https://testnet.nearblocks.io/txns/2KsbtMBa3nwzDXNmR5GwZg9pv9LqmvSQGpsWWMtMdwxV) |

## peaq / Solana (mainnet machine)

Machine onboarding and activity event hashes are in [README § Registered machine](../README.md#registered-machine-peaq-on-solana).

| Kind | Transaction |
| --- | --- |
| Activity event (claim-3 `rawData`) | [3kq4G8G7wFgPWk4BeMnsUTMc5V4majisddFntapR3HR2f7gjMjYRrEHjNpqRRvkrZ1mXQxF6mcyLiDdhVzuWWYod](https://solscan.io/tx/3kq4G8G7wFgPWk4BeMnsUTMc5V4majisddFntapR3HR2f7gjMjYRrEHjNpqRRvkrZ1mXQxF6mcyLiDdhVzuWWYod) |

**Pending:** peaq activity for **claim-4** (`python -m hotel.cli peaq-event --receipt settlement/receipts/claim-4.json`).

## NEAR Intents / 1Click (mainnet)

### SOL → native NEAR (robot implicit, 2026-11-14)

| Step | Transaction |
| --- | --- |
| SOL deposit (0.005 SOL) | [Hgk98qnj6rwUgDzEtrnCnfarwbcNHnBrhpXKgfkQLhyq8nmRiiMaC9JHZLdeunnq4HEgwvYtfXdvKfMHeZJQXq9](https://solscan.io/tx/Hgk98qnj6rwUgDzEtrnCnfarwbcNHnBrhpXKgfkQLhyq8nmRiiMaC9JHZLdeunnq4HEgwvYtfXdvKfMHeZJQXq9) |
| 1Click delivery (wNEAR / credited NEAR) | [2Nd8243tcCtpSsCghbuaP1sZD22DmrjMZb7jVK7FYWkZ](https://nearblocks.io/txns/2Nd8243tcCtpSsCghbuaP1sZD22DmrjMZb7jVK7FYWkZ) |
| 1Click status | `SUCCESS` (deposit `9QJPp9jWTnK9XRMXvN3swqXBFyporS6bo9CyGRYFxCHY`) |

**Pending:** live `wNEAR` → USDT (`python -m hotel.cli intents-quote --live` with `INTENTS_LIVE=1`).

## How to refresh this file

After a new live claim or mainnet fill, copy explorer URLs from `settlement/receipts/<claim>.json` or new intent/peaq outputs into this doc. Do not commit receipt JSON (gitignored).