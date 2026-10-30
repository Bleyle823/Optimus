# Optimus

<p align="center">
  <img src="worlds/textures/factory_logo.png" alt="Tether" width="360" />
</p>
Optimus is a robotics-as-a-service application built on **QVAC** and **peaq**. A factory robot needs private judgments (is the cold room safe, is the motor hot, is vibration a fault), but it has no GPU to run a model itself. **QVAC** on a laptop beside the line runs a local model, so the readings never leave the factory network. The robot holds its own keys through Tether’s Wallet Development Kit (**WDK**) and pays for each judgment, and **peaq** holds the robot’s on-chain identity (DID and Machine NFT).

A warehouse robot already produces the data a judgment needs: temperature, motor heat, and vibration. Sending that stream to a cloud model would export the factory’s data. **QVAC** avoids this by sitting on hardware the factory controls. It loads a local GGUF model (here, **Llama 3.2 1B Instruct, Q4_0**) and answers on the **LAN**. In this demo the gateway is the laptop in the Webots scene. It behaves like a Wi-Fi access point, except the service is **private inference**. Telemetry stays on the **LAN** and the result comes back to the robot.

A robot could carry its own GPU, but the cost would repeat for every robot on the floor, and the card would add power draw, heat, and weight to a battery-powered machine that only needs a judgment now and then. Most of the time it would sit idle. **One laptop on the LAN** can serve every robot in the plant, and updating the model means changing one machine instead of a whole fleet. An onboard GPU would keep the readings in the building too, so the reason to prefer a shared gateway is cost and reuse. It also gives the robot something to buy from, which is what makes **per-judgment billing** possible.

The project runs in the **Webots** robot simulator, which models real-world physics, so the robot’s movement, sensing, and pick-and-place behave as they would on a factory floor. The same architecture should work when deployed: a laptop running **QVAC** beside a physical robot, a wallet held by the robot, and an identity recorded on **peaq**.

This changes how robots are sold. **Robots-as-a-service** is growing fast, from an estimated **$25B** today to almost **$70B** by 2030, yet most of it runs on **flat monthly leases**. A robot that makes one delivery earns the same as one that makes a hundred, and speed, precision, and careful handling go unrewarded because the contract is a calendar, not a task. With **QVAC**, the robot can get a judgment (the room is out of range, the motor is hot) from hardware the plant controls, and **WDK** lets it pay for that judgment from a wallet it holds. The product becomes a **private decision**, settled in **USDT**, followed by the pick.

Manufacturing matters in Kenya, which is why this design fits. According to the **Kenya National Bureau of Statistics Economic Survey 2025**, manufacturing made up **7.3% of GDP** in 2024 and employed about **369,200** people, or **11.5%** of formal employment. A plant in Nairobi can put a laptop running **QVAC** next to the robot, keep temperature, vibration, and motor data in the building, and **pay only when the robot asks for a judgment**. That is a smaller commitment than an idle robot lease or a workflow that ships process data to a foreign cloud.
<p align="center">
  <img src="docs/images/youbot-pick-and-place.jpg" alt="Youbot on the factory floor next to the pick crate" width="720" />
</p>

<p align="center">
  <img src="plugins/robot_windows/pick_and_place/youbot_arm.png" alt="Youbot arm joints" height="200" />
  &nbsp;
  <img src="plugins/robot_windows/pick_and_place/youbot_wheels.png" alt="Youbot mecanum wheels" height="200" />
</p>

## Three pillars

| Pillar | What it does in Optimus |
|--------|-------------------------|
| **peaq** | Verifiable machine identity — one DID and one Machine NFT for the Youbot (see [demo machine](#this-demo-machine-peaq-mainnet) below). |
| **QVAC** | Private inference on the factory LAN — local GGUF (Llama 3.2 1B Instruct Q4_0); telemetry never leaves the building. |
| **Tether WDK** | Self-custodial wallet on the robot — EIP-191 payment intent signed on the LAN before infer; Sepolia test USDT only for optional settlement broadcast. |

Same shape as the public [Unitree G1 + QVAC](https://www.peaq.xyz/blog/peaq-brings-qvac-by-tether-to-robots-and-machines-enabling-private-ai-inference-at-the-edge) demo: a machine with a peaq identity pays a nearby private model in USDT. Optimus bills **per inference**, not per month.

## AI Yako

Built for the **AI Yako** agentic-finance track: inference runs on hardware the factory controls (“your AI”), not a remote API. The laptop Display ([`optimus_kiosk`](controllers/optimus_kiosk/optimus_kiosk.py)) and the cyan HUD in the Webots 3D view show QVAC status — model alias, robot DID, quote, receipt — so the story reads even if the lid is closed.

## Demo flow (Webots)

1. Start gateway + machine-agent (see [Setup](#setup)); optionally **one** [`pnpm settlement`](packages/settlement) worker for Sepolia receipts (do not run multiple settlement processes).
2. Open [`worlds/pick_and_place.wbt`](worlds/pick_and_place.wbt) and **Play** — the Youbot drives to the laptop kiosk (overlay: pay for nearby QVAC inference).
3. **One paid call:** the robot posts to machine-agent **`POST /kiosk/infer`** (not periodic `/telemetry`).
4. Kiosk Display: quote → sign intent → infer → receipt (source, latency in ms, ~$0.01 test USDT, receipt id).
5. Settlement (optional, testnet): WDK broadcasts test USDT on Sepolia — one tx per settled receipt.
6. The Youbot returns to the belt and picks the cube — **no second charge** for the factory task.

## Demo narration (video beats)

- **0:00** — QVAC on the LAN; Youbot registered on **peaq**; laptop is the gateway.
- **0:18** — One shared QVAC gateway serves the fleet; kiosk Display + cyan HUD show local model and DID.
- **0:48** — **peaq** identity + **QVAC** inference + **WDK** wallet; Optimus bills per inference; drive to kiosk in Webots.
- **1:00** — One USDT payment intent signed on the LAN at the laptop.
- **1:20** — Optional Sepolia settlement (test USDT); then pick without a second charge.

## Offline vs online

| Step | Network |
|------|---------|
| Download GGUF (`pnpm download-models` once) | Internet |
| QVAC infer + WDK sign + verify | **LAN only** (`QVAC_OFFLINE=1` after models are cached) |
| `POST /telemetry` (rules / health) | LAN, **no payment** |
| Sepolia USDT settlement | Internet (testnet) |

## How it fits together

```mermaid
flowchart LR
  youbot[Youbot peaqID]
  agent[machine-agent WDK]
  qvac[QVAC HTTP runtime]
  orch[peaqOS Market]
  youbot --> agent
  agent -->|"EIP-191 intent LAN"| qvac
  youbot -->|"one NFT and DID"| orch
  orch -->|"GET /v1/models POST /v1/chat/completions"| qvac
```

| Role | In this repo | peaq identity |
|------|----------------|---------------|
| Machine | Webots Youbot + [`optimus_robot`](controllers/optimus_robot/optimus_robot.py) | **Only** `did:peaq:<decimal machine id>` |
| QVAC runtime | [`pnpm gateway`](packages/gateway) on the host / laptop proto | **None.** URL on the Youbot’s orchestrator record |
| Machine agent | [`@optimus/machine-agent`](packages/machine-agent) | `/telemetry` without payment; **`POST /kiosk/infer`** with WDK sign (Webots paid path) |

The laptop Display ([`optimus_kiosk`](controllers/optimus_kiosk/optimus_kiosk.py)) is the kiosk HUD: local GGUF alias, robot DID, `source` (rules vs model), latency, USDT quote, receipt. peaq RPC does **not** print in the Webots console.

### This demo machine (peaq mainnet)

Activated **Robot**, tier **entry**, Market status **active** and identity-verified.

| | |
|--|--|
| Owner | [`0x4360d54AdB797bf75013870de1AAD152839587D0`](https://peaq.subscan.io/account/0x4360d54AdB797bf75013870de1AAD152839587D0) |
| DID | `did:peaq:89559941402598656218897526255035006056145711259135012725567383558333737842803` |
| Market | `mach_0512f484e126` |
| QVAC endpoint | `mep_fa8adae44ba3` → `http://127.0.0.1:3030` (`GET /v1/models`) |
| Explorer | [machines.peaq.xyz](https://machines.peaq.xyz/machine/89559941402598656218897526255035006056145711259135012725567383558333737842803) |
| Activation tx | [peaqscan](https://peaq.subscan.io/tx/0x5f8383e6871f86fc5952128c96b5875e737c448edccc5ff47d5232e5900d6460) |

QVAC is registered with `PUT /machines/:machId/runtime-endpoints/qvac`. Hosted orchestration cannot actually probe localhost; loopback is for a laptop-side demo. A public or tunnel URL is required if peaqOS should call the runtime from the cloud.

## Two payment rails

1. **LAN (offline after models are cached).** Webots kiosk: Youbot → machine-agent **`POST /kiosk/infer`** → EIP-191 intent ([`@tetherto/wdk-wallet-evm`](packages/wallet)) → gateway `POST /infer`. Starting the agent or posting `/telemetry` does **not** spend USDT. Needs `MACHINE_WALLET_MNEMONIC` and a stable `GATEWAY_PAYEE_ADDRESS`. No Sepolia ETH required for the kiosk itself.
2. **Online.** Scale USDT orders on peaq (Machine Market) after agent pairing. Optional Sepolia test USDT via [`pnpm settlement`](packages/settlement) is a separate WDK broadcast (`SEPOLIA_RPC`, `USDT_CONTRACT`) — run **one** settlement worker so each receipt settles once.

Do not put the peaq private key in `MACHINE_WALLET_MNEMONIC`. WDK wants a seed phrase; peaqOS wants `PEAQOS_PRIVATE_KEY`.

## Prerequisites

- Node.js 22.17+ (`nvm use 22.23.4` is fine)
- pnpm 10.x (`corepack prepare pnpm@10.34.5 --activate`)
- Webots R2025a for the factory scene
- Python 3.10+ and `peaq-os-cli` 0.0.14+ only if you will activate or talk to Machine Market (this repo uses a gitignored `.peaqos-env` on Windows)

## Setup

```bash
pnpm install
pnpm -r build
cp .env.example .env
# MACHINE_WALLET_MNEMONIC = real 12-word phrase
# GATEWAY_PRIVATE_KEY = stable ethers key (empty means a new payee every start)
pnpm download-models   # online once; Llama 3.2 1B Instruct Q4_0
```

Copy `gatewayAddress` from `GET http://127.0.0.1:3030/health` into `GATEWAY_PAYEE_ADDRESS` (must match `GATEWAY_PRIVATE_KEY`).

For peaq: set `PEAQOS_PRIVATE_KEY` locally (never commit). After `peaqos activate`, set `MACHINE_ID` and `GATEWAY_DID` to the **same** robot DID. QVAC has no API key — `QVAC_ENABLED=1` and [`qvac.config.json`](qvac.config.json) are enough.

Start:

```bash
pnpm gateway              # QVAC GGUF, /quote /infer /v1/models /v1/chat/completions
pnpm machine-agent        # /telemetry (no pay) + /kiosk/infer (WDK sign)
pnpm settlement           # optional: one process, Sepolia test USDT per receipt
pnpm --filter @optimus/dashboard dev   # optional WS feed on :5173
```

**Webots:** keep gateway + machine-agent up, open [`worlds/pick_and_place.wbt`](worlds/pick_and_place.wbt), Play. Details and overlay troubleshooting: [`docs/WEBOTS_CHANGES.md`](docs/WEBOTS_CHANGES.md).

## Offline demo

1. Gateway + machine-agent on LAN (models already cached under `~/.qvac/models` or `QVAC_MODELS_DIR`).
2. Set **`QVAC_OFFLINE=1`** in `.env` (default in [`.env.example`](.env.example)); use **`QVAC_ALLOW_NETWORK=1`** only for `pnpm download-models`.
3. Disable WAN.
4. `pnpm demo` or the dashboard scenario button, or Play in Webots.
5. `OPTIMUS_OFFLINE=1 pnpm offline-check` proves QVAC without network.

## Gateway HTTP

| Path | Use |
|------|-----|
| `GET /health` | `qvacReady`, `modelAlias`, `gatewayDid` (robot DID), `gatewayAddress` |
| `GET /v1/models` | peaqOS / OpenAI-shaped model list |
| `POST /v1/chat/completions` | peaqOS execute path (no WDK body; Scale pays on-chain) |
| `GET /quote` + `POST /infer` | Gateway LAN infer with WDK payment intent (called by agent after sign) |
| **`POST /kiosk/infer`** (machine-agent) | Webots paid path: quote, sign intent, infer once at the laptop |
| `POST /telemetry` (machine-agent) | Rules / health only — **no USDT** |

## Monorepo

Ledger and agent cache are JSON under `./data/` (gitignored).

| Package | Role |
|---------|------|
| `@optimus/shared` | Zod types + rules |
| `@optimus/gateway` | Embedded `@qvac/sdk`, quotes, infer, chat completions |
| `@optimus/machine-agent` | `/telemetry` (no pay), `/kiosk/infer` (WDK sign), spend policy |
| `@optimus/wallet` | `@tetherto/wdk-wallet-evm` (not `wdk-main` core) |
| `@optimus/peaq-setup` | Online discovery cache for offline LAN |
| `@optimus/settlement` | Optional Sepolia USDT broadcast |
| `@optimus/dashboard` | Live decision feed |

## Docs

- [`docs/QVAC_INTEGRATION.md`](docs/QVAC_INTEGRATION.md)
- [`docs/WDK_INTEGRATION.md`](docs/WDK_INTEGRATION.md)
- [`docs/NETWORK_DEPENDENCIES.md`](docs/NETWORK_DEPENDENCIES.md)
- [`docs/WEBOTS_CHANGES.md`](docs/WEBOTS_CHANGES.md) — kiosk Display, HUD, asset junctions on Windows
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/SUBMISSION.md`](docs/SUBMISSION.md)
