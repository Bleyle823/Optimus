# Optimus

Private, offline AI inference marketplace for Nairobi warehouses — **QVAC** gateway, **WDK** USDT intents, **peaq** machine identity (agung testnet). Simulation: Webots R2025a Youbot pick-and-place.

## Prerequisites

- Node.js 22.17+ (QVAC worker; `nvm use 22.23.4` works on this machine)
- pnpm 10.x (`corepack prepare pnpm@10.34.5 --activate`)
- Webots R2025a (optional, for visual demo)

## Setup

```bash
pnpm install
pnpm -r build
cp .env.example .env
# Fill MACHINE_WALLET_MNEMONIC, GATEWAY_PRIVATE_KEY (or leave empty for ephemeral gateway key — copy address from logs)
pnpm download-models   # online once
```

Start services (three terminals):

```bash
pnpm gateway
pnpm machine-agent
pnpm --filter @optimus/dashboard dev
```

Copy `gatewayAddress` from `curl http://127.0.0.1:3030/health` into `.env` as `GATEWAY_PAYEE_ADDRESS`.

**Webots kiosk demo:** start gateway + machine-agent, then open [worlds/pick_and_place.wbt](worlds/pick_and_place.wbt) and press Play. The Youbot drives to the laptop, pays for inference (kiosk `Display` updates), then runs pick-and-place. See [docs/WEBOTS_CHANGES.md](docs/WEBOTS_CHANGES.md).

## Offline demo

1. Run gateway + machine-agent on LAN.
2. Disable Wi‑Fi.
3. Trigger fault: `pnpm demo` or dashboard scenario button.
4. `OPTIMUS_OFFLINE=1 pnpm offline-check` validates QVAC without network (after models cached).

## Monorepo

| Package | Role |
|---------|------|
| `@optimus/shared` | Zod types + rules |

Ledger and agent cache use JSON files under `./data/` (no Visual Studio / node-gyp required on Windows).
| `@optimus/gateway` | QVAC + `/quote` `/infer` |
| `@optimus/machine-agent` | Telemetry, pay, infer |
| `@optimus/wallet` | WDK adapter |
| `@optimus/peaq-setup` | NETWORK setup |
| `@optimus/settlement` | NETWORK WDK broadcast |

Docs: [docs/](docs/).
