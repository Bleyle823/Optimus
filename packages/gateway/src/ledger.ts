import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { Quote, Receipt } from "@optimus/shared";

interface LedgerFile {
  quotes: Quote[];
  usedNonces: string[];
  receipts: Receipt[];
}

function emptyLedger(): LedgerFile {
  return { quotes: [], usedNonces: [], receipts: [] };
}

export class GatewayLedger {
  private path: string;
  private data: LedgerFile;

  constructor(path: string) {
    this.path = path;
    mkdirSync(dirname(path), { recursive: true });
    try {
      this.data = JSON.parse(readFileSync(path, "utf8")) as LedgerFile;
    } catch {
      this.data = emptyLedger();
      this.flush();
    }
  }

  private mergeSettlementFromDisk() {
    try {
      const disk = JSON.parse(readFileSync(this.path, "utf8")) as LedgerFile;
      const byId = new Map(disk.receipts.map((r) => [r.receiptId, r]));
      for (const receipt of this.data.receipts) {
        const fromDisk = byId.get(receipt.receiptId);
        if (fromDisk?.txHash) {
          receipt.settlementStatus = fromDisk.settlementStatus;
          receipt.txHash = fromDisk.txHash;
        }
      }
    } catch {
      /* disk missing or invalid */
    }
  }

  private flush() {
    this.mergeSettlementFromDisk();
    writeFileSync(this.path, JSON.stringify(this.data, null, 2), "utf8");
  }

  saveQuote(quote: Quote) {
    this.data.quotes.push(quote);
    this.flush();
  }

  getQuote(quoteId: string): Quote | null {
    return this.data.quotes.find((q) => q.quoteId === quoteId) ?? null;
  }

  isNonceUsed(nonce: string): boolean {
    return this.data.usedNonces.includes(nonce);
  }

  markNonceUsed(nonce: string) {
    this.data.usedNonces.push(nonce);
    this.flush();
  }

  saveReceipt(receipt: Receipt) {
    this.data.receipts.push(receipt);
    this.flush();
  }

  listReceipts(): Receipt[] {
    return [...this.data.receipts].reverse();
  }
}
