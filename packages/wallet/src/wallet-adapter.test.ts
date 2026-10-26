import { describe, expect, it } from "vitest";
import { createWalletAdapter } from "./wallet-adapter.js";

const TEST_MNEMONIC =
  "test test test test test test test test test test test junk";

describe("WalletAdapter", () => {
  it("signs and verifies payment intent offline", async () => {
    const wallet = createWalletAdapter({
      seedPhrase: TEST_MNEMONIC,
      chain: "sepolia",
    });
    const payer = await wallet.getAddress();
    const intent = await wallet.signPaymentIntent({
      quoteId: "550e8400-e29b-41d4-a716-446655440000",
      payerAddress: payer,
      payeeAddress: "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
      amountUsdt: "0.01",
      nonce: "nonce-abc-12345",
      chain: "sepolia",
    });
    expect(wallet.verifyPaymentIntent(intent)).toBe(true);
  });
});
