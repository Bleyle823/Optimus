# Network dependencies

| Feature | Package | Notes |
|---------|---------|--------|
| QVAC model first download | scripts/download-models.ts | Run once online; cache weights locally |
| peaq machine register / agent pairing / provider | packages/peaq-setup | `// NETWORK:` |
| WDK USDT broadcast | packages/wallet/network.ts, packages/settlement | Sepolia testnet only |
| MCR score fetch | packages/peaq-setup | Optional during setup |

**Not network-dependent:** `/quote`, `/infer`, telemetry POST, EIP-191 intent sign/verify, rules-based decisions, mDNS on LAN.
