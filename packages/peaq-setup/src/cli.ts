// NETWORK: run online only to seed discovery cache for offline demo.

import { PeaqAdapter } from "./peaq-adapter.js";

const adapter = new PeaqAdapter({
  dbPath: process.env.PEAQ_CACHE_DB ?? "./data/peaq-cache.db",
  marketsBaseUrl:
    process.env.PEAQ_MARKETS_URL ?? "https://markets.peaq.xyz",
  mcrApiUrl: process.env.PEAQ_MCR_API_URL ?? "https://mcr.peaq.xyz",
});

const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3030";
const health = await fetch(`${gatewayUrl}/health`);
const h = (await health.json()) as {
  gatewayAddress?: string;
  gatewayDid?: string;
};

await adapter.cacheDiscovery({
  gatewayDid:
    process.env.MACHINE_ID ??
    h.gatewayDid ??
    process.env.GATEWAY_DID ??
    "did:peaq:pending",
  gatewayBaseUrl: gatewayUrl,
  priceUsdt: process.env.GATEWAY_PRICE_USDT ?? "0.01",
  mcrScore: 0,
});

console.info("Cached gateway discovery for offline use.", {
  gatewayUrl,
  payee: h.gatewayAddress,
});
