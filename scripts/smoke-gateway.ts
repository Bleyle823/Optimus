import { loadRepoEnv } from "@optimus/shared";

loadRepoEnv();

const base = process.env.GATEWAY_URL ?? "http://127.0.0.1:3030";
const health = await fetch(`${base}/health`);
const h = (await health.json()) as { gatewayAddress: string };
console.info("health", h);

const quoteRes = await fetch(`${base}/quote?task=anomaly_judgment`);
const quote = await quoteRes.json();
console.info("quote", quote);

if (process.env.SMOKE_PAID_INFER !== "1") {
  console.info(
    "Skipping paid /infer (kiosk-only). Set SMOKE_PAID_INFER=1 to test payment manually.",
  );
  process.exit(0);
}

const { createWalletAdapter } = await import("@optimus/wallet");
const wallet = createWalletAdapter({
  seedPhrase:
    process.env.MACHINE_WALLET_MNEMONIC ??
    "test test test test test test test test test test test junk",
  chain: "sepolia",
});
const payer = await wallet.getAddress();
const intent = await wallet.signPaymentIntent({
  quoteId: quote.quoteId,
  payerAddress: payer,
  payeeAddress: h.gatewayAddress,
  amountUsdt: quote.priceUsdt,
  nonce: quote.nonce,
  chain: "sepolia",
});

const inferRes = await fetch(`${base}/infer`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({
    telemetry: {
      machineId: "peaqos:machine:demo",
      kind: "cold_room",
      timestamp: new Date().toISOString(),
      metrics: { tempC: 9 },
      context: "Cold room B, flowers, safe range 2 to 8 C",
    },
    history: [],
    paymentIntent: intent,
  }),
});
console.info("infer", inferRes.status, await inferRes.json());
