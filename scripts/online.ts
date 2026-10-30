/**
 * Fresh manual session: re-queue failed receipts, reset kiosk overlay,
 * optionally wait for gateway + agent, then one Sepolia settlement pass.
 */
import { spawnSync } from "node:child_process";
import {
  loadRepoEnv,
  prepareLedgerForOnline,
  resolveGatewayLedgerPath,
} from "@optimus/shared";

const repoRoot = loadRepoEnv();
const ledgerPath = resolveGatewayLedgerPath(repoRoot);
const waitForServices = process.argv.includes("--wait");
const skipSettle = process.argv.includes("--prepare-only");

const gatewayUrl = process.env.GATEWAY_URL ?? "http://127.0.0.1:3030";
const agentUrl = process.env.MACHINE_AGENT_URL ?? "http://127.0.0.1:4040";

async function waitUntilOk(url: string, label: string, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (Date.now() >= deadline) break;
    try {
      const res = await fetch(url);
      if (res.ok) {
        console.info(`[online] ${label} ok`);
        return true;
      }
    } catch {
      /* retry */
    }
    console.info(`[online] waiting for ${label} (${url})...`);
    await new Promise((r) => setTimeout(r, 2000));
  }
  console.error(`[online] timed out waiting for ${label}`);
  return false;
}

console.info("[online] ledger", ledgerPath);
const prep = prepareLedgerForOnline({
  ledgerPath,
  repoRoot,
  requeueFailed: true,
  resetKiosk: true,
});
console.info("[online] requeued failed receipts:", prep.requeued);
console.info("[online] receipt counts:", prep.summary);

async function main() {
  if (waitForServices) {
    if (!(await waitUntilOk(`${gatewayUrl}/health`, "gateway"))) process.exit(1);
    if (!(await waitUntilOk(`${agentUrl}/health`, "machine-agent"))) {
      process.exit(1);
    }
  }

  if (skipSettle) {
    console.info("[online] prepare-only — start services, then pnpm settlement");
    process.exit(0);
  }

  if (process.env.OPTIMUS_OFFLINE === "1") {
    console.info(
      "[online] OPTIMUS_OFFLINE=1 — skipped Sepolia settlement. Unset for testnet txs.",
    );
    process.exit(0);
  }

  const build = spawnSync(
    "pnpm",
    ["--filter", "@optimus/settlement", "run", "build"],
    {
      cwd: repoRoot ?? process.cwd(),
      stdio: "inherit",
      shell: true,
    },
  );
  if (build.status !== 0) process.exit(build.status ?? 1);

  const settle = spawnSync(
    process.execPath,
    ["packages/settlement/dist/worker.js"],
    {
      cwd: repoRoot ?? process.cwd(),
      env: {
        ...process.env,
        SETTLEMENT_ONCE: "1",
        SETTLEMENT_REQUEUE_FAILED: "0",
      },
      stdio: "inherit",
    },
  );

  console.info("");
  console.info("Manual run (fresh session):");
  console.info("  1. pnpm gateway");
  console.info("  2. pnpm machine-agent");
  console.info("  3. pnpm settlement   ← keeps settling new kiosk receipts");
  console.info("  4. Webots pick_and_place.wbt → Play");
  console.info("");
  console.info(
    "Or: pnpm online --wait   (prepare + wait for health + settle backlog)",
  );

  process.exit(settle.status ?? 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
