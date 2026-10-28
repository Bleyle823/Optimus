# QVAC integration

- **Package:** `@qvac/sdk@0.22.0` from **npm** (same version as sibling `qvac-main/packages/sdk`)
- **Adapter:** [packages/gateway/src/adapters/qvac-adapter.ts](../packages/gateway/src/adapters/qvac-adapter.ts)
- **Default model:** `LLAMA_3_2_1B_INST_Q4_0` (Llama 3.2 1B Instruct Q4_0 GGUF, ~773 MB)
- **Inference alias:** `llama-3.2-1b-instruct` on `GET /v1/models` and quotes
- **Config:** [qvac.config.json](../qvac.config.json) via `QVAC_CONFIG_PATH`
- **Download:** `pnpm download-models` (online once)
- **Offline proof:** `OPTIMUS_OFFLINE=1 pnpm offline-check`

The gateway **embeds** the SDK (`loadModel` / `completion`). You do **not** need `npm install -g @qvac/cli` or `qvac serve` for Optimus. Do **not** build `qvac-main` from source (`cmake/`, `vcpkg-overlays/`) unless npm install fails.

**WDK:** machine payments use **`@tetherto/wdk-wallet-evm`** (npm), not the sibling `wdk-main` core package (`@tetherto/wdk`).

## Prerequisites

- **Node.js 22.17+** (QVAC worker; Optimus `engines.node` is `>=22.17.0`)
- **pnpm 10.x** (`packageManager` is `pnpm@10.34.5`; `corepack enable` then `corepack prepare pnpm@10.34.5 --activate`)

Root `package.json` `pnpm.onlyBuiltDependencies` allows scripts for `esbuild` and QVAC-related packages (`bare-runtime`, `@qvac/sdk`, `@qvac/inference`, `@qvac/llm-llamacpp`, `@qvac/fabric`).

## One-time setup

```powershell
cd C:\Users\Omen\Desktop\Optimus-main
nvm use 22.23.4   # or any Node >= 22.17
corepack enable
corepack prepare pnpm@10.34.5 --activate
pnpm install
pnpm -r build
Copy-Item .env.example .env
$env:QVAC_CONFIG_PATH = (Resolve-Path .\qvac.config.json).Path
pnpm download-models
```

Weights cache under `%USERPROFILE%\.qvac\models\` (example: `Llama-3.2-1B-Instruct-Q4_0.gguf`). `.qvac/` is gitignored.

If the QVAC **registry** times out on this network, the adapter passes **`fallbackSrc`**: Hugging Face `unsloth/Llama-3.2-1B-Instruct-GGUF` (same GGUF; checksum-checked). Override with `QVAC_FALLBACK_SRC`. `qvac.config.json` sets `registryStreamTimeoutMs` to 600000.

## Verify

```powershell
$env:OPTIMUS_OFFLINE = "1"
$env:QVAC_CONFIG_PATH = (Resolve-Path .\qvac.config.json).Path
pnpm offline-check
```

Gateway with QVAC loaded:

```powershell
$env:QVAC_ENABLED = "1"
$env:QVAC_CONFIG_PATH = (Resolve-Path .\qvac.config.json).Path
pnpm gateway
# other terminal:
curl http://127.0.0.1:3030/health
```

Expect `qvacReady: true` and `modelAlias: "llama-3.2-1b-instruct"`. Optional: `pnpm smoke-gateway` (rules-first `anomaly_judgment`; model runs only when rules return `ok`).

Note: `QVAC_MODEL` in `.env` is documented; the adapter currently always loads `LLAMA_3_2_1B_INST_Q4_0`.

Record latency/RAM on your machine after first successful inference.
