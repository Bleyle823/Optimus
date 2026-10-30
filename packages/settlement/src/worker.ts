// NETWORK: settlement worker — broadcast WDK txs and update receipt status.

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { broadcastUsdtTransfer } from "@optimus/wallet/network";
import {
  loadRepoEnv,
  requeueFailedReceipts,
  resolveGatewayLedgerPath,
} from "@optimus/shared";

const repoRoot = loadRepoEnv();
const ledgerPath = resolveGatewayLedgerPath(repoRoot);
const POLL_MS = Number(process.env.SETTLEMENT_POLL_MS ?? 15_000);

function usdtToUnits(amount: string): bigint {
  const [whole, frac = ""] = amount.split(".");
  const padded = (frac + "000000").slice(0, 6);
  return BigInt(whole) * 1_000_000n + BigInt(padded);
}

interface LedgerFile {
  receipts: Array<{
    receiptId: string;
    amountUsdt: string;
    settlementStatus: string;
    txHash?: string;
    lastSettlementError?: string;
  }>;
}

function readLedger(): LedgerFile | null {
  try {
    return JSON.parse(readFileSync(ledgerPath, "utf8")) as LedgerFile;
  } catch {
    return null;
  }
}

function countByStatus(status: string): number {
  const file = readLedger();
  if (!file) return -1;
  return file.receipts.filter((r) => r.settlementStatus === status).length;
}

function countPending(): number {
  return countByStatus("pending_settlement");
}

function envReady(): boolean {
  return Boolean(
    process.env.MACHINE_WALLET_MNEMONIC &&
      process.env.SEPOLIA_RPC &&
      process.env.USDT_CONTRACT &&
      process.env.GATEWAY_PAYEE_ADDRESS,
  );
}

async function settlePending(): Promise<number> {
  let file: LedgerFile;
  try {
    file = JSON.parse(readFileSync(ledgerPath, "utf8")) as LedgerFile;
  } catch (e) {
    console.warn(
      "[settlement] Cannot read ledger:",
      ledgerPath,
      e instanceof Error ? e.message : e,
    );
    return 0;
  }

  let settled = 0;
  for (const row of file.receipts) {
    if (row.settlementStatus !== "pending_settlement") continue;
    try {
      const mnemonic = process.env.MACHINE_WALLET_MNEMONIC;
      const provider = process.env.SEPOLIA_RPC;
      const usdt = process.env.USDT_CONTRACT;
      const payee = process.env.GATEWAY_PAYEE_ADDRESS;
      if (!mnemonic || !provider || !usdt || !payee) {
        console.warn(
          "[settlement] Skipped receipt (missing env):",
          row.receiptId,
          "Need MACHINE_WALLET_MNEMONIC, SEPOLIA_RPC, USDT_CONTRACT, GATEWAY_PAYEE_ADDRESS",
        );
        return settled;
      }
      const { hash } = await broadcastUsdtTransfer({
        seedPhrase: mnemonic,
        providerUrl: provider,
        usdtContract: usdt,
        to: payee,
        amountUnits: usdtToUnits(row.amountUsdt),
      });
      row.settlementStatus = "settled";
      row.txHash = hash;
      settled++;
      console.info("[settlement] Settled", row.receiptId, hash);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      row.lastSettlementError = msg;
      console.error(
        "[settlement] Broadcast failed (will retry on next poll):",
        row.receiptId,
        msg,
      );
    }
  }
  writeFileSync(ledgerPath, JSON.stringify(file, null, 2), "utf8");
  return settled;
}

async function loop(first = false) {
  if (process.env.OPTIMUS_OFFLINE === "1") {
    console.info(
      "[settlement] Idle (OPTIMUS_OFFLINE=1). Unset it to broadcast Sepolia USDT.",
    );
    return;
  }

  const pending = countPending();
  const failed = countByStatus("failed");
  const settled = countByStatus("settled");
  if (first) {
    if (pending < 0) {
      console.warn("[settlement] Ledger not readable yet — waiting for gateway receipts");
    } else if (pending === 0) {
      const extra =
        failed > 0
          ? ` (${failed} marked failed — change to pending_settlement in gateway.json to retry, or run a new kiosk infer)`
          : "";
      console.info(
        `[settlement] No pending_settlement receipts${extra}. Run kiosk infer first, then this worker broadcasts.`,
      );
      if (settled > 0) {
        console.info(`[settlement] Ledger: ${settled} settled receipt(s) already`);
      }
    } else {
      console.info(
        `[settlement] ${pending} receipt(s) pending_settlement`,
      );
    }
  } else if (pending > 0) {
    console.info(`[settlement] ${pending} receipt(s) still pending`);
  }

  await settlePending();
  setTimeout(() => loop(false), POLL_MS);
}

console.info("[settlement] Worker started");
console.info("[settlement] Ledger:", ledgerPath, existsSync(ledgerPath) ? "ok" : "MISSING");
console.info(
  "[settlement] Sepolia env:",
  envReady() ? "ok" : "INCOMPLETE — load .env or export vars",
);
console.info("[settlement] Poll interval ms:", POLL_MS);

if (
  process.env.SETTLEMENT_REQUEUE_FAILED !== "0" &&
  process.env.OPTIMUS_OFFLINE !== "1"
) {
  const requeued = requeueFailedReceipts(ledgerPath);
  if (requeued > 0) {
    console.info(
      `[settlement] Re-queued ${requeued} failed receipt(s) from last session`,
    );
  }
}

if (process.env.SETTLEMENT_ONCE === "1") {
  settlePending()
    .then((n) => {
      console.info("[settlement] once pass settled count:", n);
      process.exit(n > 0 ? 0 : countPending() > 0 ? 1 : 0);
    })
    .catch((e) => {
      console.error(e);
      process.exit(1);
    });
} else {
  loop(true);
}
