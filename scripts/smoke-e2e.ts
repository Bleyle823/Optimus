/**
 * End-to-end smoke: health → kiosk paid infer → pending receipt → settlement (optional).
 * Requires gateway + machine-agent already running.
 * Loads repo `.env` automatically.
 */
import { readFileSync } from "node:fs";
import { loadRepoEnv, resolveFromRepo } from "@optimus/shared";

const repoRoot = loadRepoEnv();
const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3030";
const agentUrl = process.env.MACHINE_AGENT_URL ?? "http://127.0.0.1:4040";
const ledgerPath = resolveFromRepo(
  repoRoot,
  process.env.GATEWAY_DB_PATH ?? "./data/gateway.json",
);

const telemetry = {
  machineId: process.env.MACHINE_ID ?? "peaqos:machine:demo",
  kind: "cold_room",
  timestamp: new Date().toISOString(),
  metrics: { tempC: 9, compressorCurrent: 0.2, vibrationMmS: 8 },
  context: "Cold room B, flowers, safe range 2 to 8 C — kiosk smoke",
};

function fail(msg: string): never {
  console.error("[smoke-e2e] FAIL:", msg);
  process.exit(1);
}

console.info("[smoke-e2e] gateway", gatewayUrl);
console.info("[smoke-e2e] agent", agentUrl);
console.info("[smoke-e2e] ledger", ledgerPath);

const healthRes = await fetch(`${gatewayUrl}/health`);
if (!healthRes.ok) fail(`gateway /health ${healthRes.status}`);
const health = (await healthRes.json()) as {
  qvacReady?: boolean;
  gatewayAddress?: string;
  modelAlias?: string;
};
console.info("[smoke-e2e] health", {
  qvacReady: health.qvacReady,
  gatewayAddress: health.gatewayAddress,
  modelAlias: health.modelAlias,
});

if (process.env.GATEWAY_PAYEE_ADDRESS && health.gatewayAddress) {
  const want = process.env.GATEWAY_PAYEE_ADDRESS.toLowerCase();
  const got = health.gatewayAddress.toLowerCase();
  if (want !== got) {
    fail(
      `GATEWAY_PAYEE_ADDRESS (${want}) != gateway payee (${got}). Fix GATEWAY_PRIVATE_KEY in .env.`,
    );
  }
}

await fetch(`${agentUrl}/fault`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ scenario: "cold_room_drift" }),
});

const kioskRes = await fetch(`${agentUrl}/kiosk/infer`, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(telemetry),
});
const kioskBody = await kioskRes.json();
if (!kioskRes.ok) {
  fail(`kiosk/infer ${kioskRes.status}: ${JSON.stringify(kioskBody)}`);
}

const receipt = kioskBody.receipt as { receiptId?: string; settlementStatus?: string };
if (!receipt?.receiptId) fail("kiosk/infer returned no receipt");
if (receipt.settlementStatus !== "pending_settlement") {
  fail(`expected pending_settlement, got ${receipt.settlementStatus}`);
}
console.info("[smoke-e2e] receipt", receipt.receiptId, receipt.settlementStatus);

const ledger = JSON.parse(readFileSync(ledgerPath, "utf8")) as {
  receipts: Array<{ receiptId: string; settlementStatus: string }>;
};
const onDisk = ledger.receipts.find((r) => r.receiptId === receipt.receiptId);
if (!onDisk) fail(`receipt ${receipt.receiptId} not in ${ledgerPath}`);
console.info("[smoke-e2e] ledger ok — same path settlement uses");

if (process.env.SMOKE_SETTLE === "1") {
  console.info("[smoke-e2e] SETTLEMENT_ONCE settlement pass...");
  const { spawnSync } = await import("node:child_process");
  const r = spawnSync(
    process.execPath,
    ["packages/settlement/dist/worker.js"],
    {
      cwd: repoRoot ?? process.cwd(),
      env: { ...process.env, SETTLEMENT_ONCE: "1" },
      stdio: "inherit",
    },
  );
  if (r.status !== 0) fail("settlement once failed");
  const after = JSON.parse(readFileSync(ledgerPath, "utf8")) as {
    receipts: Array<{ receiptId: string; settlementStatus: string; txHash?: string }>;
  };
  const row = after.receipts.find((x) => x.receiptId === receipt.receiptId);
  if (row?.settlementStatus !== "settled" || !row.txHash) {
    fail(`receipt not settled: ${JSON.stringify(row)}`);
  }
  console.info("[smoke-e2e] settled tx", row.txHash);
  console.info("[smoke-e2e] PASS (infer + settlement)");
} else {
  console.info(
    "[smoke-e2e] PASS (infer). Start `pnpm settlement` to settle, or SMOKE_SETTLE=1 to auto-test.",
  );
}

process.exit(0);
