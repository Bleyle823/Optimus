# Optimus — manual test guide

**Track:** AI Yako, on-device agentic finance (QVAC + WDK)  
**Repo root:** `Optimus-main`  
**What this proves:** the QVAC judgment runs from a local model, and WDK settles one Sepolia test USDT payment for that judgment.

Paste this page into Notion. Headings become blocks. Code fences stay as code.

---

## What you are testing

| Process | Command | What it does | Pays? |
|---------|---------|--------------|-------|
| QVAC gateway | `pnpm gateway` | Loads Llama 3.2 1B from a local GGUF and serves `/health`, `/quote`, `/infer` on port 3030 | No |
| Machine agent | `pnpm machine-agent` | Listens on port 4040. Signs a WDK payment intent only when the robot calls `/kiosk/infer` | No, until the kiosk call |
| Settlement | `pnpm settlement` | Reads receipts and broadcasts **one** Sepolia test USDT transfer per `pending_settlement` receipt | Yes, testnet only |
| Webots | `worlds/pick_and_place.wbt` | Youbot drives to the laptop, pays once, then pick-and-place | Yes, once, at the laptop |

Starting `pnpm machine-agent` or `pnpm gateway` does not send a transaction. Periodic telemetry does not send one either. The paid path is `POST http://127.0.0.1:4040/kiosk/infer`, which the Youbot calls only when it reaches the laptop.

---

## What needs internet

| Step | Internet |
|------|----------|
| `pnpm install`, `pnpm -r build` | Yes, the first time |
| `pnpm download-models` | Yes, once, to cache the GGUF |
| `pnpm gateway` after the GGUF is cached | No. Logs should say `offline load from` a local `.gguf` |
| `/quote`, `/infer`, WDK intent sign and verify, Webots kiosk | No |
| `pnpm settlement` (Sepolia RPC) | Yes |
| peaq Machine Market / activation | Yes, and it is separate from this payment |

Set `QVAC_OFFLINE=1` in `.env`. Do not set `QVAC_ALLOW_NETWORK=1` on the gateway if you want the offline demo. `pnpm download-models` turns network fetch on for that one command only.

---

## One-time setup

Requirements: Node.js 22.17+, pnpm 10.x, Webots R2025a, a funded **Sepolia** payer (a little ETH for gas and test USDT on `USDT_CONTRACT`).

```powershell
cd c:\Users\Omen\Desktop\Optimus-main
corepack prepare pnpm@10.34.5 --activate
pnpm install
pnpm -r build
copy .env.example .env
pnpm download-models
```

Edit `.env` (never commit it):

| Variable | What to put |
|----------|-------------|
| `QVAC_OFFLINE` | `1` |
| `QVAC_ENABLED` | `1` |
| `MACHINE_WALLET_MNEMONIC` | 12-word BIP-39 phrase for the **WDK payer**. Not the peaq key |
| `GATEWAY_PRIVATE_KEY` | Stable hex key so the payee does not change every restart |
| `GATEWAY_PAYEE_ADDRESS` | Must match `gatewayAddress` from `GET /health` |
| `GATEWAY_DID` and `MACHINE_ID` | The Youbot DID |
| `GATEWAY_DB_PATH` | Absolute path, for example `C:/Users/Omen/Desktop/Optimus-main/data/gateway.json` |
| `SEPOLIA_RPC` | Sepolia JSON-RPC |
| `USDT_CONTRACT` | Sepolia test USDT |
| `CHAIN` | `sepolia` |

Align the payee once: start the gateway, open `http://127.0.0.1:3030/health`, copy `gatewayAddress` into `GATEWAY_PAYEE_ADDRESS`, restart the gateway.

### Automated smoke (no Webots)

Terminal 1: `pnpm gateway` — wait until `/health` shows `qvacReady: true` and logs **`ledger .../data/gateway.json`**.

Terminal 2: `pnpm machine-agent`

Terminal 3:

```powershell
pnpm smoke-e2e
```

Optional Sepolia settlement in the same command:

```powershell
$env:SMOKE_SETTLE='1'; pnpm smoke-e2e
```

You should see **`[smoke-e2e] PASS`**. Then Webots should behave the same at the laptop kiosk.

---

## Load `.env` in every PowerShell window

**Gateway, machine-agent, and settlement** load the repo `.env` automatically when you run `pnpm gateway`, `pnpm machine-agent`, or `pnpm settlement` from the repo root. **`pnpm smoke-e2e`** loads it too.

For other commands, or if you exported vars manually before, you can still run:

```powershell
cd c:\Users\Omen\Desktop\Optimus-main
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*(#|$)') { return }
  $i = $_.IndexOf('=')
  if ($i -lt 1) { return }
  Set-Item -Path ("Env:" + $_.Substring(0,$i).Trim()) -Value $_.Substring($i+1).Trim()
}
```

---

## Coming back online (fresh manual session)

After a break, or if kiosk showed **pending** but settlement said **none**, run this once from the repo root (internet needed for Sepolia):

```powershell
pnpm online
```

That will:

1. Re-queue any **`failed`** receipts from the last run back to **`pending_settlement`**
2. Reset **`data/kiosk-status.json`** so the laptop overlay is not stuck on an old receipt
3. Run **one** settlement pass for anything still pending

Then start the stack in order:

```powershell
pnpm gateway
pnpm machine-agent
pnpm settlement
```

Open Webots and play **`pick_and_place.wbt`**.

**Variants**

| Command | Use when |
|---------|----------|
| `pnpm prepare-online` | Reset ledger + kiosk only; you will start gateway/agent yourself |
| `pnpm online --wait` | Same as `online`, but waits until `/health` on gateway and agent respond first |
| `pnpm settlement:once` | Settle backlog only (also re-queues failed); services already running |

`pnpm settlement` on startup also re-queues failed receipts automatically, then polls every ~15s for new kiosk payments.

---

Use four terminals. Start the gateway first and wait until it is listening.

### 1. QVAC gateway

```powershell
pnpm gateway
```

Wait for `Gateway listening on 0.0.0.0:3030` and a line like:

`[QvacAdapter] offline load from C:\Users\...\.qvac\models\...Llama-3.2-1B-Instruct-Q4_0.gguf`

Check:

```powershell
Invoke-RestMethod http://127.0.0.1:3030/health | ConvertTo-Json
```

Expect `ok: true`, `qvacReady: true`, `modelAlias: llama-3.2-1b-instruct`, and a stable `gatewayAddress`.

**Record this for the offline half of the track.** With the model already cached, the gateway must not download from the QVAC registry or Hugging Face. If you want a strict check, disable WAN after the model is cached and start the gateway again.

### 2. Machine agent

```powershell
pnpm machine-agent
```

Expect `Server listening at http://127.0.0.1:4040`. This process does not sign a payment and does not broadcast a transaction.

### 3. Settlement (the WDK chain step)

Run **exactly one** worker:

```powershell
pnpm settlement
```

It polls `GATEWAY_DB_PATH` about every 15 seconds. For each receipt still marked `pending_settlement`, it sends 0.01 test USDT from the machine wallet to `GATEWAY_PAYEE_ADDRESS` and prints:

`Settled <receiptId> 0x...`

Stop this terminal when you are finished. A second settlement process can send duplicate transfers.

### 4. Webots

1. Open `worlds/pick_and_place.wbt` in Webots R2025a.
2. Confirm the Youbot controller is `optimus_robot`.
3. Press Play.

The robot drives to the laptop. At the kiosk it calls `POST /kiosk/infer`. The agent signs a WDK intent, the gateway runs the judgment, and a receipt is written. The laptop display and `data/kiosk-status.json` show the model, DID, source, latency, price, and a short receipt id. Then pick-and-place runs.

Do not use Save World after Play. That writes runtime poses back into the world file.

---

## Successful WDK test payment

This is the finance half of the track. Do it on **Sepolia**, never with mainnet funds.

1. Gateway and machine agent are up. One settlement worker is running. The payer has Sepolia ETH and test USDT.
2. Either press Play and let the Youbot reach the laptop, or, for a bench test only:

```powershell
$env:SMOKE_PAID_INFER = "1"
pnpm smoke-gateway
```

Default `pnpm smoke-gateway` (without that variable) checks health and a quote only. It does **not** pay.

3. Wait for `Settled <receiptId> 0x...` in the settlement terminal.
4. Open the hash on a Sepolia explorer. Confirm:
   - status success
   - from = the WDK payer derived from `MACHINE_WALLET_MNEMONIC`
   - to = the test USDT contract
   - transfer to = `GATEWAY_PAYEE_ADDRESS`
   - amount = 0.01 USDT
5. In `data/gateway.json`, that receipt’s `settlementStatus` is `settled` and `txHash` matches the explorer.

### Recorded test settlement (Sepolia)

These two receipts were settled on Sepolia test USDT (`0x0F3a990cdDb2f3675372250a0D849B53528E60f8`), payer `0xF740BEA95f386350AD1F09242E8310Bf51E48D63`, payee `0x84f189AD39823D2C7C687249d0ccC677510A929e`, amount 0.01 USDT.

| Receipt | Transaction |
|---------|-------------|
| `1cc304eb-7bc3-464e-825f-cb2871e17533` | [0xb6b699dff5d6957ab7c96356c2f59b84b9302f9c30cb722b8aca83ad2cc6f460](https://sepolia.etherscan.io/tx/0xb6b699dff5d6957ab7c96356c2f59b84b9302f9c30cb722b8aca83ad2cc6f460) |
| `8ba92152-b821-4f1b-803d-8bac737136cf` | [0x5763361916e5c5ff977c78e37921cc5f58a2fb49199190ce25a189d6897a3efb](https://sepolia.etherscan.io/tx/0x5763361916e5c5ff977c78e37921cc5f58a2fb49199190ce25a189d6897a3efb) |

Use a fresh hash from your own run in the submission if you settle again. These are testnet transfers, not mainnet USDT and not peaq transactions.

Quick local check:

```powershell
Select-String -Path data\gateway.json -Pattern 'receiptId|settlementStatus|txHash' | Select-Object -Last 12
```

---

## What each code path does

| Path | Role |
|------|------|
| `packages/gateway/src/adapters/qvac-adapter.ts` | Loads QVAC from the local GGUF when offline |
| `packages/machine-agent/src/server.ts` | `/telemetry` is free. `/kiosk/infer` signs the WDK intent and calls `/infer` |
| `packages/wallet/src/wallet-adapter.ts` | EIP-191 sign and verify. No RPC |
| `packages/wallet/src/network.ts` | Sepolia USDT broadcast. Needs internet |
| `packages/settlement/src/worker.ts` | Polls the ledger and writes `txHash` |
| `controllers/optimus_robot/optimus_robot.py` | Drives to the laptop, then calls `/kiosk/infer` once |

---

## Shut down

1. Stop Webots Play.
2. Stop settlement (`Ctrl+C`). Leave it stopped when you are not settling.
3. Stop the machine agent and the gateway.

---

## Troubleshooting

| What you see | What to do |
|--------------|------------|
| `EADDRINUSE` on 3030 or 4040 | Stop the old `node` process for gateway or agent |
| Receipt stays `pending_settlement` | One settlement process, same `GATEWAY_DB_PATH`, payer has ETH and test USDT, `SEPOLIA_RPC` is set |
| Settlement says “no pending” but kiosk shows pending | Kiosk file (`data/kiosk-status.json`) is written at payment time only. Check **`data/gateway.json` → `receipts`**. If status is `failed`, an earlier broadcast failed; set it back to `pending_settlement` or run `pnpm smoke-e2e` for a fresh receipt. |
| Verify full path without Webots | Gateway + machine-agent running → `pnpm smoke-e2e` (infer only) or `SMOKE_SETTLE=1 pnpm smoke-e2e` (infer + one settlement pass) |
| One-shot settlement | `pnpm settlement:once` after a kiosk infer |
| Intent or payee errors | `GATEWAY_PAYEE_ADDRESS` must equal `/health` `gatewayAddress` |
| Gateway tries to download | Cache the model with `pnpm download-models`, set `QVAC_OFFLINE=1`, do not set `QVAC_ALLOW_NETWORK=1` |
| Many Sepolia transfers | More than one settlement worker, or an old agent that paid on every telemetry post. Use one worker and the current `/kiosk/infer` controller. Reload the Webots world after updating the controller |
| Blank laptop screen | Gateway and agent must be running. Status is also in `data/kiosk-status.json`. See `docs/WEBOTS_CHANGES.md` |
| Huge `gateway.json` | `/quote` rows are not payments. Only `receipts` with `pending_settlement` are |
