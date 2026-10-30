# DoraHacks — copy-paste submission (AI Yako / Optimus)

**Before you submit:** push this repo to `main` on GitHub so image links below load. Repo: `https://github.com/Bleyle823/Optimus`

**Project logo (upload in DoraHacks):** use `docs/images/youbot-pick-and-place.jpg` or `worlds/textures/factory_logo.png` from the repo.

---

## Field: Project name

```
Optimus
```

---

## Field: One-line tagline / short intro (~160 chars)

```
Factory robot pays per inference for private offline QVAC AI on the LAN—WDK wallet, peaq identity, Webots demo.
```

---

## Field: Brief description (~500 chars — if the form has a short box)

```
Optimus is RaaS built on QVAC, Tether WDK, and peaq. A KUKA Youbot in Webots drives to a laptop on the factory LAN, buys one inference from a local Llama 3.2 1B model (cached GGUF, no cloud), signs an EIP-191 USDT payment intent with its own WDK wallet, then picks on the conveyor—no second charge. Telemetry stays on the LAN; optional Sepolia test USDT settlement is separate. Pay per inference, not per month. Kenya-relevant: keep plant data in the building, pay only when the robot asks.
```

---

## Field: Detailed introduction / project description (paste entire block below)

Copy from the line `--- START ---` through `--- END ---`.

--- START ---

# Optimus: factory robot that pays per inference for private, offline AI

![Factory floor — Youbot, laptop QVAC kiosk, pick crate](https://raw.githubusercontent.com/Bleyle823/Optimus/main/docs/images/youbot-pick-and-place.jpg)

**Optimus** is a robotics-as-a-service stack on **QVAC**, **Tether WDK**, and **peaq**. A **KUKA Youbot** in **Webots** drives to a laptop on the factory **LAN**, pays for **one inference** from a local QVAC model with **its own wallet**, then completes pick-and-place.

![QVAC](https://raw.githubusercontent.com/Bleyle823/Optimus/main/worlds/textures/qvac-logo.png) ![AI Yako](https://raw.githubusercontent.com/Bleyle823/Optimus/main/worlds/textures/AIyako.png)

**Repository:** https://github.com/Bleyle823/Optimus  
**Track:** On-device agentic finance — QVAC (local AI) + WDK (self-custodial payment)

---

## Problem

- Factory robots need model decisions (cold room, motor heat, vibration) but have **no onboard GPU**.
- Cloud inference **exports plant telemetry** to a third party.
- **RaaS ~$25B → ~$70B by 2030**, yet most revenue is still **flat monthly leases**—one delivery pays the same as a hundred.
- **Kenya (KNBS Economic Survey 2025):** manufacturing **7.3% of GDP**, **~369,200** formal jobs (**11.5%**). Plants need data on-prem and **pay-per-use**, not idle leases or foreign-cloud process data.

---

## Solution / how it works

1. **QVAC** on a factory laptop loads **Llama 3.2 1B Instruct (GGUF Q4_0)** and serves **private inference on the LAN**—one gateway can serve every robot.
2. **peaq** gives the Youbot **one DID + one Machine NFT** (laptop is runtime URL only, not a second NFT).
3. At the kiosk the robot calls **`POST /kiosk/infer`**: quote → **WDK EIP-191 intent** (payer, payee, USDT, nonce) → gateway verifies **on LAN without RPC** → inference + receipt.
4. **`pnpm settlement`** (optional, separate step) broadcasts **Sepolia test USDT** and stores **txHash** on the receipt.
5. Robot returns to the conveyor; **the pick is not a second charge**.

![Kiosk display — model, DID, latency, USDT, receipt](https://raw.githubusercontent.com/Bleyle823/Optimus/main/controllers/optimus_kiosk/screen_display.png)

*Laptop kiosk + matching cyan HUD in Webots.*

**Offline proof (judging):** with `QVAC_OFFLINE=1` and cached weights, gateway logs **`[QvacAdapter] offline load from`** a local `.gguf`; infer + sign work with **Wi‑Fi off**. Settlement needs internet—show that in a **second clip**. Details: [README offline section](https://github.com/Bleyle823/Optimus#proving-qvac-runs-without-internet-demo--checks).

---

## Key features

- **Private inference** — telemetry stays on the factory LAN  
- **Offline QVAC** — after `pnpm download-models` once, no registry/HF at runtime  
- **Self-custodial WDK** — `@tetherto/wdk-wallet-evm`, BIP-39 separate from peaq key  
- **Pay per inference** — `/telemetry` does not sign; **one payment at the kiosk**  
- **peaq machine identity** — verifiable DID + Machine NFT  
- **Live kiosk + HUD** — source, latency, cost, receipt id  
- **Verifiable test settlement** — Sepolia USDT on receipt  

---

## Test payment (Sepolia)

| Item | Value |
|------|--------|
| Network | Sepolia (test) |
| USDT | `0x0F3a990cdDb2f3675372250a0D849B53528E60f8` |
| Payer (WDK) | `0xF740BEA95f386350AD1F09242E8310Bf51E48D63` |
| Payee (gateway) | `0x84f189AD39823D2C7C687249d0ccC677510A929e` |
| Amount | 0.01 USDT |
| Tx (example) | https://sepolia.etherscan.io/tx/0xb6b699dff5d6957ab7c96356c2f59b84b9302f9c30cb722b8aca83ad2cc6f460 |
| Second tx | https://sepolia.etherscan.io/tx/0x5763361916e5c5ff977c78e37921cc5f58a2fb49199190ce25a189d6897a3efb |

Receipt `1cc304eb-7bc3-464e-825f-cb2871e17533` in `data/gateway.json` settled with the first hash.

**Demo machine (peaq):** `did:peaq:89559941402598656218897526255035006056145711259135012725567383558333737842803` · market `mach_0512f484e126` · QVAC `http://127.0.0.1:3030` · [Explorer](https://machines.peaq.xyz/machine/89559941402598656218897526255035006056145711259135012725567383558333737842803)

---

## Tech stack

- **QVAC** — local inference, OpenAI-shaped HTTP on gateway  
- **Llama 3.2 1B Instruct** (GGUF Q4_0)  
- **Tether WDK** — EIP-191 payment intents  
- **peaq** — DID + Machine NFT  
- **Sepolia test USDT** — settlement worker  
- **Webots** — KUKA Youbot factory world  
- **Node.js 22+ / pnpm** — `pnpm gateway`, `pnpm machine-agent`, `pnpm settlement`  

**Code pointers:** `packages/gateway/src/adapters/qvac-adapter.ts`, `packages/wallet`, `packages/machine-agent` (`/kiosk/infer`), `controllers/optimus_robot/optimus_robot.py`

--- END ---

---

## Field: GitHub / repository URL

```
https://github.com/Bleyle823/Optimus
```

---

## Field: Demo video (paste your link when uploaded)

```
https://YOUR_VIDEO_LINK
```

**Suggested video structure (2 min):** (1) Wi‑Fi off + gateway `offline load from` + Webots kiosk infer; (2) Wi‑Fi on + one Sepolia tx; (3) pick with no second payment.

---

## Field: Additional links (optional)

| Label | URL |
|--------|-----|
| Write-up with images (repo) | https://github.com/Bleyle823/Optimus/blob/main/docs/HACKATHON_WRITEUP.md |
| Manual test / repeat demo | https://github.com/Bleyle823/Optimus/blob/main/docs/MANUAL_TEST_GUIDE.md |
| peaq + QVAC reference | https://www.peaq.xyz/blog/peaq-brings-qvac-by-tether-to-robots-and-machines-enabling-private-ai-inference-at-the-edge |

---

## Field: Technologies / tags (pick what DoraHacks offers)

```
QVAC, Tether WDK, peaq, Webots, Node.js, USDT, EIP-191, offline AI, DePIN, robotics, agentic finance
```

---

## If images do not render on DoraHacks

Upload these files manually in the project gallery or embed in the rich editor:

1. `docs/images/youbot-pick-and-place.jpg` — hero / cover  
2. `controllers/optimus_kiosk/screen_display.png` — kiosk  
3. `worlds/textures/qvac-logo.png` — QVAC  
4. Screenshot: gateway log line `[QvacAdapter] offline load from ...`  
5. Screenshot: Sepolia Etherscan for tx `0xb6b699…`  
