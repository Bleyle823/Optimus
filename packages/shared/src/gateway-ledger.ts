import { readFileSync, writeFileSync } from "node:fs";
import { resolveFromRepo } from "./load-env.js";

export interface GatewayLedgerReceipt {
  receiptId: string;
  settlementStatus: string;
  lastSettlementError?: string;
  txHash?: string;
  amountUsdt?: string;
}

export interface GatewayLedger {
  receipts: GatewayLedgerReceipt[];
  [key: string]: unknown;
}

export type ReceiptStatusSummary = {
  pending_settlement: number;
  failed: number;
  settled: number;
  other: number;
};

export function resolveGatewayLedgerPath(
  repoRoot: string | null,
  gatewayDbPath = process.env.GATEWAY_DB_PATH ?? "./data/gateway.json",
): string {
  return gatewayDbPath.endsWith(".json")
    ? resolveFromRepo(repoRoot, gatewayDbPath)
    : resolveFromRepo(repoRoot, `${gatewayDbPath}.json`);
}

export function readGatewayLedger(ledgerPath: string): GatewayLedger | null {
  try {
    return JSON.parse(readFileSync(ledgerPath, "utf8")) as GatewayLedger;
  } catch {
    return null;
  }
}

export function summarizeReceipts(ledger: GatewayLedger): ReceiptStatusSummary {
  const counts: ReceiptStatusSummary = {
    pending_settlement: 0,
    failed: 0,
    settled: 0,
    other: 0,
  };
  for (const r of ledger.receipts ?? []) {
    const s = r.settlementStatus;
    if (s === "pending_settlement") counts.pending_settlement++;
    else if (s === "failed") counts.failed++;
    else if (s === "settled") counts.settled++;
    else counts.other++;
  }
  return counts;
}

/** Move legacy `failed` receipts back to the settlement queue. */
export function requeueFailedReceipts(ledgerPath: string): number {
  const file = readGatewayLedger(ledgerPath);
  if (!file?.receipts) return 0;
  let n = 0;
  for (const r of file.receipts) {
    if (r.settlementStatus === "failed") {
      r.settlementStatus = "pending_settlement";
      delete r.lastSettlementError;
      n++;
    }
  }
  if (n > 0) {
    writeFileSync(ledgerPath, JSON.stringify(file, null, 2), "utf8");
  }
  return n;
}

export function resetKioskStatus(
  repoRoot: string | null,
  path = "./data/kiosk-status.json",
): void {
  const full = resolveFromRepo(repoRoot, path);
  const payload = {
    status: "idle",
    reason: "Back online — start Webots or run smoke-e2e for a paid infer",
    action: "Play pick_and_place.wbt after gateway, agent, and settlement",
    model: "llama-3.2-1b-instruct",
    qvacReady: false,
    privacy: "Telemetry stays on LAN",
    settlement: "none",
  };
  writeFileSync(full, JSON.stringify(payload, null, 2), "utf8");
}

export function prepareLedgerForOnline(opts: {
  ledgerPath: string;
  repoRoot: string | null;
  requeueFailed?: boolean;
  resetKiosk?: boolean;
  kioskPath?: string;
}): { requeued: number; summary: ReceiptStatusSummary } {
  const requeueFailed = opts.requeueFailed !== false;
  const resetKiosk = opts.resetKiosk !== false;
  let requeued = 0;
  if (requeueFailed) requeued = requeueFailedReceipts(opts.ledgerPath);
  if (resetKiosk) resetKioskStatus(opts.repoRoot, opts.kioskPath);
  const ledger = readGatewayLedger(opts.ledgerPath);
  const summary = ledger
    ? summarizeReceipts(ledger)
    : { pending_settlement: 0, failed: 0, settled: 0, other: 0 };
  return { requeued, summary };
}
