// NETWORK: settlement worker — broadcast WDK txs and update receipt status.

import { readFileSync, writeFileSync } from "node:fs";
import { broadcastUsdtTransfer } from "@optimus/wallet/network";

const GATEWAY_DB =
  process.env.GATEWAY_DB_PATH ?? "./data/gateway.db";
const ledgerPath = GATEWAY_DB.endsWith(".json")
  ? GATEWAY_DB
  : `${GATEWAY_DB}.json`;
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
  }>;
}

async function settlePending() {
  let file: LedgerFile;
  try {
    file = JSON.parse(readFileSync(ledgerPath, "utf8")) as LedgerFile;
  } catch {
    return;
  }

  for (const row of file.receipts) {
    if (row.settlementStatus !== "pending_settlement") continue;
    try {
      const mnemonic = process.env.MACHINE_WALLET_MNEMONIC;
      const provider = process.env.SEPOLIA_RPC;
      const usdt = process.env.USDT_CONTRACT;
      const payee = process.env.GATEWAY_PAYEE_ADDRESS;
      if (!mnemonic || !provider || !usdt || !payee) {
        console.warn("Settlement skipped: missing NETWORK env vars");
        return;
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
      console.info("Settled", row.receiptId, hash);
    } catch (e) {
      row.settlementStatus = "failed";
      console.error("Failed", row.receiptId, e);
    }
  }
  writeFileSync(ledgerPath, JSON.stringify(file, null, 2), "utf8");
}

async function loop() {
  if (process.env.OPTIMUS_OFFLINE === "1") {
    console.info("Settlement idle (OPTIMUS_OFFLINE=1)");
    return;
  }
  await settlePending();
  setTimeout(loop, POLL_MS);
}

loop();
